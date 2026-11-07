"""Reproducible thermal/energy correctness fixtures, not research experiments.

Analytic and independent ODE calculations cross-check the implementation; only
the evaluator's directed enclosures provide its numerical guarantees. No
optimizer, historical energy answer, or formal 95-problem run is used here.
"""

import argparse
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform as host_platform
import shutil
import sys
import time
from unittest.mock import patch

import mpmath as mp
import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from inputs import build_instances, load_config
from run_precheck import fixture
from schedules import validate_schedule
import thermal as thermal_module
from thermal import Budget, evaluate_candidate, evaluate_piecewise

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
mp.mp.dps = 90


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(actual, expected):
    require(actual == expected, f"{actual!r} != {expected!r}")


def mp_exact(value):
    rational = F(value)
    return mp.mpf(rational.numerator) / rational.denominator


def contains(interval, value):
    return mp.mpf(interval[0]) <= value <= mp.mpf(interval[1])


def distance(interval, value):
    return max(0.0, float(interval[0])-float(value), float(value)-float(interval[1]))


def width(interval):
    return Decimal(interval[1])-Decimal(interval[0])


def physical(c, g, ambient="25", reference="25", external="0"):
    """Synthetic correctness fixture. Never replaces any research parameter."""
    nodes = [f"N{i}" for i in range(len(c))]
    return {
        "node_order": nodes,
        "heat_capacity_J_per_K": list(map(str, c)),
        "conductance_W_per_K": [[str(x) for x in row] for row in g],
        "ambient_temperature_degC": ambient,
        "reference_temperature_degC": reference,
        "external_common_power_W": external,
        "external_common_heat_distribution": ["0"]*len(c),
        "power_model_temperature_range_degC": ["20", "100"],
    }


def segment(p, start, end, baseline, activity, slopes, active=None):
    nodes = p["node_order"]
    return {
        "start_ms": str(start), "end_ms": str(end),
        "duration_ms": str(F(end)-F(start)),
        "domain_opps": {"fixture": "held"},
        "active_stage_ids": [] if active is None else active,
        "baseline_by_power_group_W": {"fixture": str(sum(map(F, baseline)))},
        "baseline_by_node_W": dict(zip(nodes, map(str, baseline))),
        "activity_by_node_W": dict(zip(nodes, map(str, activity))),
        "local_leakage_slope_W_per_K": dict(zip(nodes, map(str, slopes))),
        "node_power_constant_at_reference_W": {
            node: str(F(b)+F(q)) for node, b, q in zip(nodes, baseline, activity)},
        "reference_temperature_degC": p["reference_temperature_degC"],
        "external_common_power_W": p["external_common_power_W"],
        "external_common_injected_heat_W": "0",
    }


def ode_oracle(p, initial, segments):
    """Independent DOP853 trajectory, per-node integrals and power integration.

    This numerical oracle is explicitly not a validated interval integrator.
    Its differences from the enclosures are implementation diagnostics only.
    """
    nodes = p["node_order"]
    n = len(nodes)
    c = np.array([float(F(x)) for x in p["heat_capacity_J_per_K"]])
    g = np.array([[float(F(x)) for x in row] for row in p["conductance_W_per_K"]])
    ambient, reference = float(F(p["ambient_temperature_degC"])), float(F(p["reference_temperature_degC"]))
    # Physical absolute temperature, temperature integral, direct power integral.
    state = np.r_[list(map(float, initial)), np.zeros(n), 0.0]
    peak = state[:n].copy()
    peak_at = np.zeros(n)
    baseline = activity = external = correction = 0.0
    segment_records = []
    for seg in segments:
        t0, t1 = [float(F(seg[k])/1000) for k in ["start_ms", "end_ms"]]
        b = np.array([float(F(seg["baseline_by_node_W"][node])) for node in nodes])
        q = np.array([float(F(seg["activity_by_node_W"][node])) for node in nodes])
        lam = np.array([float(F(seg["local_leakage_slope_W_per_K"][node])) for node in nodes])
        ext = float(F(seg["external_common_power_W"]))
        before = state.copy()

        def rhs(_t, y):
            power = b+q+lam*(y[:n]-reference)
            return np.r_[(power-g@(y[:n]-ambient))/c, y[:n], np.sum(power)+ext]

        sol = solve_ivp(rhs, (t0, t1), state, method="DOP853", rtol=2e-13,
                        atol=2e-13, dense_output=True, max_step=(t1-t0)/8)
        require(sol.success, sol.message)
        state = sol.y[:, -1]
        dt = t1-t0
        baseline += float(np.sum(b))*dt
        activity += float(np.sum(q))*dt
        external += ext*dt
        correction += float(lam@(state[n:2*n]-before[n:2*n]-reference*dt))
        points = np.linspace(t0, t1, 65)
        roots = [[] for _ in nodes]
        for i in range(n):
            deriv = lambda t, i=i: float(rhs(t, sol.sol(t))[i])
            for a, z in zip(points, points[1:]):
                da, dz = deriv(a), deriv(z)
                if da*dz < 0:
                    roots[i].append(float(brentq(deriv, a, z, xtol=1e-14)))
            choices = [t0, t1]+roots[i]
            best = max(choices, key=lambda t: sol.sol(t)[i])
            if sol.sol(best)[i] > peak[i]:
                peak[i] = sol.sol(best)[i]
                peak_at[i] = best
        segment_records.append({"start_s": t0, "end_s": t1,
                                "stationary_points_s": dict(zip(nodes, roots))})
    components = {"baseline": baseline, "activity": activity,
                  "external_common": external, "temperature_correction": correction}
    return {"final_temperature_degC": dict(zip(nodes, map(float, state[:n]))),
            "peaks_degC": dict(zip(nodes, map(float, peak))),
            "peak_times_s": dict(zip(nodes, map(float, peak_at))),
            "temperature_integrals_K_s": dict(zip(nodes, map(float, state[n:2*n]))),
            "energy_direct_integral_J": float(state[-1]),
            "energy_component_sum_J": sum(components.values()),
            "energy_components_J": components,
            "segment_extrema": segment_records,
            "role": "independent_floating_crosscheck_not_error_certificate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE/"config_v01.json")
    parser.add_argument("--output", type=Path, default=HERE/"results/thermal_precheck01")
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    sources = [HERE/name for name in ["inputs.py", "schedules.py", "thermal.py",
                                     "run_precheck.py", "run_thermal_precheck.py"]]
    sources += [args.config.resolve(), REPO/"research/v1_evaluator/interval.py"]
    hashes = {str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p):
              hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for path in sources:
        target = folder/"source"/(path.relative_to(REPO) if path.is_relative_to(REPO) else path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    checks, records = [], {}
    start = time.monotonic()
    config = load_config(args.config)
    accuracy = config["accuracy_targets"]
    base = next(p for p in build_instances(config) if p["id"] == "base__R1")

    def save(name, value):
        (folder/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    def check(name, fn):
        try:
            detail = fn()
            checks.append({"name": name, "status": "PASS", "detail": detail})
        except Exception as exc:
            checks.append({"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
        save("checks_in_progress.json", checks)

    def run_piece(name, p, entry, limits, segs, window, budget=None, accuracy_override=None):
        record = {"kind": "correctness_fixture_not_research_case", "platform": p,
                  "entry": entry, "limits": limits, "segments": segs, "window_ms": window}
        try:
            record["result"] = evaluate_piecewise(p, entry, limits, segs, window,
                accuracy=accuracy if accuracy_override is None else accuracy_override,
                budget=budget, scene_id=name)
        except Exception as exc:
            record["result"] = {"state": "EXCEPTION", "reason": f"{type(exc).__name__}: {exc}"}
        records[name] = record
        save("fixture_results.json", records)
        return record["result"]

    def run_candidate(name, problem, candidate, budget=None):
        record = {"kind": "hand_built_correctness_fixture_not_method_output", "problem": problem,
                  "candidate": candidate}
        try:
            record["result"] = evaluate_candidate(problem, candidate, accuracy=accuracy, budget=budget)
        except Exception as exc:
            record["result"] = {"state": "EXCEPTION", "reason": f"{type(exc).__name__}: {exc}"}
        records[name] = record
        save("fixture_results.json", records)
        return record["result"]

    def scalar(name, leakage, reference):
        p = physical(["2"], [["0.5"]], reference=reference, external="0.2")
        segs = [segment(p, "0", "2000", ["1.2"], ["0.8"], [leakage], ["work"])]
        result = run_piece(name, p, ["30"], ["80"], segs, "2000")
        c, g, lam, ta, ref, dt, theta0 = map(mp_exact, ["2", "0.5", leakage, "25", reference, "2", "5"])
        rate = (g-lam)/c
        equilibrium = (mp_exact("2")+lam*(ta-ref))/(g-lam)
        final = ta+equilibrium+(theta0-equilibrium)*mp.exp(-rate*dt)
        integral_theta = equilibrium*dt+(theta0-equilibrium)*(1-mp.exp(-rate*dt))/rate
        leak_energy = lam*(integral_theta+(ta-ref)*dt)
        energy = mp_exact("4.4")+leak_energy
        records[name]["analytic_oracle"] = {"final_temperature_degC": str(final),
            "energy_J": str(energy), "temperature_correction_J": str(leak_energy)}
        check(name+"/safe", lambda: equal(result["state"], "SAFE"))
        check(name+"/analytic_final_inside_enclosure", lambda: require(
            contains(result["final_temperature_degC"]["N0"], final), "analytic temperature not enclosed"))
        check(name+"/analytic_energy_inside_enclosure", lambda: require(
            contains(result["energy_J"], energy), "analytic energy not enclosed"))
        check(name+"/leakage_component", lambda: require(
            contains(result["energy_components_J"]["temperature_correction"], leak_energy), "leakage energy not enclosed"))
        check(name+"/energy_precision", lambda: require(width(result["energy_J"]) <= Decimal("0.000001"), "energy width"))
        return p, segs, result

    scalar("scalar_no_leakage", "0", "25")
    scalar("scalar_local_leakage", "0.05", "25")
    scalar("scalar_reference_differs_from_ambient", "0.05", "20")

    # Analytic delayed peak: T0(t)=25+1.5(exp(-t)-exp(-3t)).
    # Both endpoint temperatures obey 25.5 C; the strict interior peak does not.
    coupled = physical(["1", "1"], [["2", "-1"], ["-1", "2"]])
    idle = [segment(coupled, "0", "1000", ["0", "0"], ["0", "0"], ["0", "0"])]
    peak = run_piece("coupled_idle_tail_interior_peak", coupled, ["25", "28"], ["25.5", "29"], idle, "1000")
    t_star, t_peak = mp.log(3)/2, mp.mpf(25)+1/mp.sqrt(3)
    records["coupled_idle_tail_interior_peak"]["analytic_oracle"] = {
        "peak_time_s": str(t_star), "peak_temperature_degC": str(t_peak),
        "end_temperature_degC": str(25+mp.mpf("1.5")*(mp.exp(-1)-mp.exp(-3))),
        "meaning": "no active work; heat redistribution creates an interior peak during idle"}
    check("interior_peak/endpoints_below_limit", lambda: require(
        25 < mp.mpf("25.5") and 25+mp.mpf("1.5")*(mp.exp(-1)-mp.exp(-3)) < mp.mpf("25.5"), "fixture endpoints"))
    check("interior_peak/continuous_violation_detected", lambda: equal(peak["state"], "THERMAL_VIOLATION"))
    check("interior_peak/analytic_max_enclosed", lambda: require(contains(peak["peaks_degC"]["N0"], t_peak), "interior maximum not enclosed"))
    check("interior_peak/witness_is_strict_and_inside_window", lambda: require(
        0 < F(peak["peak_witnesses"]["N0"]["time_s"]) < 1 and
        F(peak["peak_witnesses"]["N0"]["temperature_degC"][0]) > F("25.5"), "not a strict interior witness"))

    good = fixture(base)
    valid = validate_schedule(base, good)
    actual = run_candidate("unchanged_base_hand_schedule", base, good)
    check("base_fixture/safe_and_complete", lambda: require(actual["state"] == "SAFE" and all(
        v["complete"] for v in actual["scenes"].values()), "not complete safe"))
    for scene in base["scenarios"]:
        sid = scene["id"]
        oracle = ode_oracle(base["platform"], scene["entry"]["temperature_degC"], valid["scenes"][sid]["segments"])
        records["unchanged_base_hand_schedule"].setdefault("independent_ode_oracles", {})[sid] = oracle

        def compare_ode(sid=sid, oracle=oracle):
            measured = actual["scenes"][sid]
            for node in base["platform"]["node_order"]:
                require(distance(measured["final_temperature_degC"][node], oracle["final_temperature_degC"][node]) <= 2e-8, "ODE final discrepancy "+node)
                require(distance(measured["peaks_degC"][node], oracle["peaks_degC"][node]) <= 2e-8, "ODE peak discrepancy "+node)
                require(width(measured["peaks_degC"][node]) <= Decimal("0.001"), "peak width "+node)
            require(distance(measured["energy_J"], oracle["energy_direct_integral_J"]) <= 2e-10, "ODE energy discrepancy")
            require(abs(oracle["energy_direct_integral_J"]-oracle["energy_component_sum_J"]) <= 2e-10, "independent energy double sum")
            for component, value in oracle["energy_components_J"].items():
                require(distance(measured["energy_components_J"][component], value) <= 2e-10, "component "+component)
            equal(F(measured["covered_until_s"]), F(base["window_ms"])/1000)
            return {"ODE_temperature_comparison_allowance_K": 2e-8,
                    "ODE_energy_comparison_allowance_J": 2e-10,
                    "allowances_are_not_evaluator_error_bounds": True}
        check("base_fixture/independent_ODE_and_double_energy/"+sid, compare_ode)

        def exact_fixed_components(sid=sid):
            segments = valid["scenes"][sid]["segments"]
            values = {
                "baseline": sum(sum(map(F, s["baseline_by_power_group_W"].values()))*F(s["duration_ms"])/1000 for s in segments),
                "activity": sum(sum(map(F, s["activity_by_node_W"].values()))*F(s["duration_ms"])/1000 for s in segments),
                "external_common": F(".3")*F(".4")}
            for key, value in values.items():
                require(contains(actual["scenes"][sid]["energy_components_J"][key], mp_exact(value)), "fixed component "+key)
            equal(segments[-1]["active_stage_ids"], [])
            equal(F(segments[-1]["end_ms"]), F(400))
            return {key: str(value) for key, value in values.items()}
        check("base_fixture/full_window_fixed_power_accounting/"+sid, exact_fixed_components)

    def weighted():
        lo = sum(F(s["weight"])*F(actual["scenes"][s["id"]]["energy_J"][0]) for s in base["scenarios"])
        hi = sum(F(s["weight"])*F(actual["scenes"][s["id"]]["energy_J"][1]) for s in base["scenarios"])
        require(F(actual["weighted_energy_J"][0]) <= lo <= hi <= F(actual["weighted_energy_J"][1]), "weighted enclosure")
        equal(actual["safe_upper_bound_J"], actual["weighted_energy_J"][1])
    check("base_fixture/weighted_energy_only_after_all_scenes", weighted)

    def conservation():
        for scene in base["scenarios"]:
            evaluated = actual["scenes"][scene["id"]]
            oracle = records["unchanged_base_hand_schedule"]["independent_ode_oracles"][scene["id"]]
            require(distance(evaluated["conservation_energy_J"], oracle["energy_direct_integral_J"]) <= 2e-10,
                    "energy-balance identity differs from independent direct integral")
            nodes = base["platform"]["node_order"]
            ambient = F(base["platform"]["ambient_temperature_degC"])
            for node in nodes:
                ode_rise = oracle["temperature_integrals_K_s"][node]-float(ambient)*0.4
                require(distance(evaluated["temperature_rise_integrals_Ks"][node], ode_rise) <= 2e-10,
                        "temperature integral differs "+node)
            heat_lo = sum(F(evaluated["node_injected_energy_J"][node][0]) for node in nodes)
            heat_hi = sum(F(evaluated["node_injected_energy_J"][node][1]) for node in nodes)
            power_lo = F(evaluated["energy_J"][0])-F(evaluated["energy_components_J"]["external_common"][1])
            power_hi = F(evaluated["energy_J"][1])-F(evaluated["energy_components_J"]["external_common"][0])
            require(max(heat_lo, power_lo) <= min(heat_hi, power_hi), "external energy mixed into injected heat")
    check("base_fixture/independent_heat_balance_and_node_integrals", conservation)

    accel = deepcopy(good)
    for scene in base["scenarios"]:
        for row in accel["scenes"][scene["id"]]:
            shared = next(st["shared_stage_id"] for st in scene["stage_instances"] if st["id"] == row["stage_id"])
            if shared == "A.main": row.update(unit="NPU0", start_ms="10")
            elif shared == "A.post": row["start_ms"] = "40"
            elif shared == "B.main": row.update(unit="NPU0", start_ms="40")
            elif shared == "B.post": row["start_ms"] = "75"
            elif shared == "C.main": row.update(unit="GPU0", start_ms="15")
            elif shared == "C.post": row["start_ms"] = "60"
    accelerated = run_candidate("unchanged_accelerator_hand_schedule", base, accel)
    check("accelerators/safe_shared_mapping_and_NPU_queue", lambda: equal(accelerated["state"], "SAFE"))

    def accelerator_oracle():
        checked = validate_schedule(base, accel)
        for scene in base["scenarios"]:
            sid = scene["id"]
            oracle = ode_oracle(base["platform"], scene["entry"]["temperature_degC"], checked["scenes"][sid]["segments"])
            records["unchanged_accelerator_hand_schedule"].setdefault("independent_ode_oracles", {})[sid] = oracle
            require(distance(accelerated["scenes"][sid]["energy_J"], oracle["energy_direct_integral_J"]) <= 2e-10,
                    "GPU/NPU energy discrepancy")
            for node in base["platform"]["node_order"]:
                require(distance(accelerated["scenes"][sid]["final_temperature_degC"][node],
                                 oracle["final_temperature_degC"][node]) <= 2e-8,
                        "GPU/NPU local temperature discrepancy")
    check("accelerators/independent_ODE", accelerator_oracle)

    single = deepcopy(base)
    single["id"] = "fixture_single_fractional_finish"
    single["scenarios"] = single["scenarios"][:1]
    scene = single["scenarios"][0]
    scene["weight"] = "1"
    scene["requests"] = scene["requests"][:1]
    scene["requests"][0]["deadline_ms"] = "400"
    ids = set(scene["requests"][0]["stage_instance_ids"])
    scene["stage_instances"] = [s for s in scene["stage_instances"] if s["id"] in ids]
    scene["dependencies"] = [e for e in scene["dependencies"] if set(e) <= ids]
    fraction_candidate = fixture(single)
    rows = fraction_candidate["scenes"][scene["id"]]
    rows[1]["opp"] = "M"
    rows[2]["start_ms"] = "115"
    fractional = run_candidate("fractional_finish_and_idle_OPP", single, fraction_candidate)

    def fractional_oracle():
        equal(fractional["state"], "SAFE")
        checked = validate_schedule(single, fraction_candidate)
        equal(F(checked["scenes"][scene["id"]]["rows"][1]["end_ms"]), F(334, 3))
        segments = checked["scenes"][scene["id"]]["segments"]
        oracle = ode_oracle(single["platform"], scene["entry"]["temperature_degC"], segments)
        records["fractional_finish_and_idle_OPP"]["independent_ode_oracle"] = oracle
        require(distance(fractional["weighted_energy_J"], oracle["energy_direct_integral_J"]) <= 2e-10,
                "fractional finish energy discrepancy")
        require(any(F(seg["start_ms"]) == F(334, 3) and seg["domain_opps"]["CPU"] == "M"
                    for seg in segments), "fractional idle OPP missing")
        equal(F(fractional["scenes"][scene["id"]]["covered_until_s"]), F(2, 5))
    check("fractional_end/retained_without_rounding_and_full_tail", fractional_oracle)

    invalid = deepcopy(good)
    invalid["scenes"][base["scenarios"][0]["id"]][0]["start_ms"] = "1"
    bad_schedule = run_candidate("invalid_schedule_no_energy", base, invalid)
    check("invalid_schedule/no_rankable_energy", lambda: require(
        bad_schedule["state"] == "INVALID_SCHEDULE" and bad_schedule.get("weighted_energy_J") is None and
        bad_schedule.get("safe_upper_bound_J") is None, "invalid schedule exposed ranking"))

    # A zero-probability scene still belongs to the declared safety domain.
    zero = deepcopy(base)
    zero["scenarios"][0]["weight"] = "1"
    zero["scenarios"][1]["weight"] = "0"
    zero["scenarios"][1]["maximum_temperature_degC"] = ["49"]*4
    zresult = run_candidate("zero_weight_scene_unsafe", zero, good)
    check("zero_weight_scene/no_weighted_energy", lambda: require(
        zresult["state"] == "THERMAL_VIOLATION" and bool(zresult["violations"]) and
        zresult.get("weighted_energy_J") is None and zresult.get("safe_upper_bound_J") is None,
        "zero-weight unsafe scene accepted or weighted"))

    local = physical(["1", "1"], [["1", "0"], ["0", "1"]])
    local_seg = [segment(local, "0", "200", ["0.2", "0.2"], ["0", "0"], ["0.01", "0.01"])]
    unequal = run_piece("different_local_temperatures_same_OPP", local, ["30", "40"], ["80", "80"], local_seg, "200")

    def local_temperature_use():
        equal(unequal["state"], "SAFE")
        oracle = ode_oracle(local, ["30", "40"], local_seg)
        records["different_local_temperatures_same_OPP"]["independent_ode_oracle"] = oracle
        for node in ["N0", "N1"]:
            require(distance(unequal["final_temperature_degC"][node], oracle["final_temperature_degC"][node]) <= 2e-8,
                    "local temperature substituted by a shared temperature")
        require(F(unequal["node_injected_energy_J"]["N1"][0]) > F(unequal["node_injected_energy_J"]["N0"][1]),
                "hotter local node should have larger local leakage in fixture")
    check("power/local_temperature_not_domain_average", local_temperature_use)

    external = deepcopy(local)
    external["external_common_power_W"] = "7"
    external_seg = deepcopy(local_seg)
    external_seg[0]["external_common_power_W"] = "7"
    external_result = run_piece("external_power_only_changes_energy", external, ["30", "40"], ["80", "80"], external_seg, "200")
    check("power/external_common_not_injected", lambda: (
        equal(external_result["final_temperature_degC"], unequal["final_temperature_degC"]),
        equal(external_result["peaks_degC"], unequal["peaks_degC"]),
        require(contains(external_result["energy_components_J"]["external_common"], mp_exact("1.4")),
                "external energy is not fixed power times full window")))

    p = physical(["1"], [["1"]])
    segs = [segment(p, "0", "100", ["1"], ["0"], ["0"])]
    malformed = deepcopy(p)
    malformed["heat_capacity_J_per_K"] = ["0"]
    bad_input = run_piece("invalid_capacity", malformed, ["25"], ["80"], segs, "100")
    check("physical/invalid_capacity_rejected", lambda: equal(bad_input["state"], "INVALID_INPUT"))
    gap = deepcopy(segs)
    gap[0]["start_ms"] = "1"
    gap_result = run_piece("missing_initial_interval", p, ["25"], ["80"], gap, "100")
    check("physical/full_window_coverage_required", lambda: equal(gap_result["state"], "INVALID_INPUT"))

    def expire_on(event):
        def hook(actual_event, budget):
            if actual_event == event:
                budget.seconds = -1
        return hook

    before = run_piece("interrupt_before_panel", p, ["25"], ["80"], segs, "100",
                       Budget(hook=expire_on("before_panel")))
    check("interrupt/before_panel_is_unresolved", lambda: require(
        before["state"] == "UNRESOLVED" and not before["complete"] and before.get("energy_J") is None,
        "budget before first panel produced completed result"))
    after_witness = run_piece("interrupt_after_violation_commit", coupled, ["25", "28"],
        ["25.5", "29"], idle, "1000", Budget(hook=expire_on("after_violation_commit")))
    check("interrupt/committed_violation_survives", lambda: require(
        after_witness["state"] == "THERMAL_VIOLATION" and bool(after_witness["violations"]) and
        after_witness.get("energy_J") is None, "committed violation lost or post-budget energy accepted"))
    before_scene = run_piece("interrupt_before_scene_commit", p, ["25"], ["80"], segs, "100",
                            Budget(hook=expire_on("before_scene_commit")))
    check("interrupt/no_post_budget_scene_energy", lambda: require(
        before_scene["state"] == "UNRESOLVED" and before_scene.get("energy_J") is None,
        "post-budget scene energy accepted"))
    before_aggregate = run_candidate("interrupt_before_aggregate_commit", base, good,
                                     Budget(hook=expire_on("before_aggregate_commit")))
    check("interrupt/no_post_budget_weighted_energy", lambda: require(
        before_aggregate["state"] == "UNRESOLVED" and before_aggregate.get("weighted_energy_J") is None and
        before_aggregate.get("safe_upper_bound_J") is None, "post-budget aggregate accepted"))
    outer_witness = run_candidate("interrupt_outer_retains_inner_violation", zero, good,
                                  Budget(hook=expire_on("after_violation_commit")))
    check("interrupt/outer_retains_committed_inner_violation", lambda: require(
        outer_witness["state"] == "THERMAL_VIOLATION" and bool(outer_witness["violations"]) and
        outer_witness.get("weighted_energy_J") is None, "outer budget handling lost existing counterexample"))
    after_panel = run_piece("interrupt_after_panel_commit", p, ["25"], ["80"], segs, "100",
                            Budget(hook=expire_on("after_panel_commit")))
    check("interrupt/covered_prefix_is_not_full_energy", lambda: require(
        after_panel["state"] == "UNRESOLVED" and F(after_panel["covered_until_s"]) > 0 and
        not after_panel["complete"] and after_panel.get("energy_J") is None,
        "committed prefix exposed as full result"))
    no_panels = run_piece("panel_resource_limit", p, ["25"], ["80"], segs, "100", Budget(panels=0))
    check("resource_limit/unresolved_not_violation", lambda: require(
        no_panels["state"] == "UNRESOLVED" and not no_panels["violations"] and no_panels.get("energy_J") is None,
        "resource exhaustion confused with safety evidence"))
    limited_accuracy = deepcopy(accuracy)
    limited_accuracy["temperature_enclosure_width_K"] = "1e-70"
    narrow = run_piece("unattainable_peak_precision", coupled, ["25", "28"], ["80", "80"], idle,
                       "1000", Budget(refinements=3), limited_accuracy)
    check("numeric/unresolved_is_not_safe", lambda: require(
        narrow["state"] == "UNRESOLVED" and narrow.get("energy_J") is None and not narrow["violations"],
        "unresolved numeric bound became safe or violated"))
    # A rational limit just ABOVE the analytic maximum is safe mathematically,
    # but the requested finite enclosure cannot separate it from the boundary.
    # This tests thermal indeterminacy without exhausting the resource budget.
    boundary_limit = mp.nstr(mp.ceil(t_peak*mp.mpf(10)**60)/mp.mpf(10)**60, 80)
    thermal_boundary = run_piece("thermal_limit_straddles_enclosure", coupled, ["25", "28"],
        [boundary_limit, "29"], idle, "1000")
    check("numeric/thermal_boundary_is_complete_but_unresolved", lambda: require(
        thermal_boundary["state"] == "UNRESOLVED" and thermal_boundary["complete"] and
        not thermal_boundary["violations"] and not thermal_boundary["rankable_energy"] and
        F(thermal_boundary["peaks_degC"]["N0"][0]) <= F(boundary_limit) <
        F(thermal_boundary["peaks_degC"]["N0"][1]), "thermal enclosure crossing not separated from safety"))
    with patch.object(thermal_module.Panel, "value", side_effect=ArithmeticError("injected_numeric_failure")):
        numeric_fault = run_piece("injected_arithmetic_failure", p, ["25"], ["80"], segs, "100")
    check("numeric/arithmetic_failure_is_unresolved", lambda: require(
        numeric_fault["state"] == "UNRESOLVED" and numeric_fault.get("energy_J") is None and
        not numeric_fault["violations"], "numeric failure confused with physical invalidity or proof"))
    def memory_fault(event, _budget):
        if event == "before_panel":
            raise MemoryError("injected_resource_failure")
    resource_fault = run_piece("injected_memory_failure", p, ["25"], ["80"], segs, "100",
                               Budget(hook=memory_fault))
    check("resource_limit/memory_failure_is_unresolved", lambda: require(
        resource_fault["state"] == "UNRESOLVED" and resource_fault.get("energy_J") is None and
        not resource_fault["violations"], "resource failure confused with safety evidence"))
    def memory_at(event):
        def hook(observed, _budget):
            if observed == event:
                raise MemoryError("injected_resource_failure")
        return hook
    resource_witness = run_piece("memory_failure_after_committed_violation", coupled, ["25", "28"],
        ["25.5", "29"], idle, "1000", Budget(hook=memory_at("after_violation_commit")))
    check("resource_limit/memory_failure_keeps_violation", lambda: require(
        resource_witness["state"] == "THERMAL_VIOLATION" and bool(resource_witness["violations"]) and
        resource_witness.get("energy_J") is None, "resource failure erased committed evidence"))
    resource_aggregate = run_candidate("memory_failure_before_aggregate", base, good,
        Budget(hook=memory_at("before_aggregate_commit")))
    check("resource_limit/memory_failure_no_aggregate", lambda: require(
        resource_aggregate["state"] == "UNRESOLVED" and resource_aggregate.get("weighted_energy_J") is None and
        resource_aggregate.get("safe_upper_bound_J") is None, "resource failure exposed incomplete aggregate"))

    previous_input_record = HERE/"results/input_precheck03/checks.json"
    previous_hashes = json.loads(previous_input_record.read_text(encoding="utf-8"))["source_sha256"]
    # Read only a provenance hash, never a historical energy or selected answer.
    previous_config_hash = next(value for key, value in previous_hashes.items()
                                if key.replace("\\", "/").endswith("chapter3_experiments/config_v01.json"))
    config_hash = hashlib.sha256(args.config.read_bytes()).hexdigest()
    check("config/unchanged_since_input_precheck03", lambda: equal(config_hash, previous_config_hash))

    check("unchanged_input_and_sources", lambda: equal(hashes, {
        str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sources}))
    passed = sum(c["status"] == "PASS" for c in checks)
    report = {"scope": "continuous_thermal_and_energy_correctness_fixtures_only",
              "status": "PASS" if passed == len(checks) else "FAIL", "passed": passed,
              "total": len(checks), "checks": checks, "source_sha256": hashes,
              "config_sha256": config_hash, "input_precheck03_config_sha256": previous_config_hash,
              "formal_experiments_ready": False, "research_cases_run": 0,
              "not_tested": ["MILP_encoding", "HEFT_and_SA", "method_quality_or_speed"],
              "wall_seconds": time.monotonic()-start,
              "oracle_scope": "closed_form_and_floating_ODE_crosschecks_not_substitutes_for_enclosures"}
    save("checks.json", report)
    save("fixture_results.json", records)
    save("environment.json", {"python": sys.version, "executable": sys.executable,
         "platform": host_platform.platform(), "numpy": np.__version__, "scipy": scipy.__version__,
         "mpmath": mp.__version__, "source_sha256": hashes})
    print(json.dumps({k: report[k] for k in ["status", "passed", "total", "wall_seconds"]}, ensure_ascii=False))
    for item in checks:
        if item["status"] == "FAIL":
            print(item["name"]+": "+item["error"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
