"""Small-domain MILP checks, separate from the 95 research instances.

The Cartesian oracle below reads the mode costs directly, implements its own
legality and power-state reconstruction, and does not use the MILP encoder or
the common schedule checker. Fixtures retain the frozen physical platform,
400 ms window and 5 ms starts, while restricting only their test workload and
declared start sets. No fixture is a formal algorithm-comparison result.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import argparse
import hashlib
import json
from pathlib import Path
import platform as host_platform
import shutil
import time

from inputs import build_instances, load_config
from schedules import validate_schedule

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(left, right):
    require(left == right, f"{left!r} != {right!r}")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n",
                          encoding="utf-8")


def select_fixture(base, name, selected, start_values):
    """Trim task instances, never physical costs, deadlines, window or grid.

    selected maps original scene id to shared Stage ids. All retained modes
    and the requests' original release/deadline values are preserved.
    """
    instance = deepcopy(base)
    instance["id"] = "fixture_"+name
    scenes, starts = [], {}
    for original in base["scenarios"]:
        if original["id"] not in selected:
            continue
        scene = deepcopy(original)
        wanted = set(selected[scene["id"]])
        scene["stage_instances"] = [s for s in scene["stage_instances"]
                                    if s["shared_stage_id"] in wanted]
        ids = {s["id"] for s in scene["stage_instances"]}
        retained = []
        for request in scene["requests"]:
            request["stage_instance_ids"] = [s for s in request["stage_instance_ids"] if s in ids]
            if request["stage_instance_ids"]:
                retained.append(request)
        scene["requests"] = retained
        scene["dependencies"] = [[a, b] for a, b in scene["dependencies"] if a in ids and b in ids]
        starts[scene["id"]] = {
            s["id"]: list(map(str, start_values[s["shared_stage_id"]]))
            for s in scene["stage_instances"]}
        scenes.append(scene)
    for scene in scenes:
        scene["weight"] = str(F(1, len(scenes)))
    instance["scenarios"] = scenes
    used = {s["shared_stage_id"] for sc in scenes for s in sc["stage_instances"]}
    instance["stage_modes"] = {k: v for k, v in instance["stage_modes"].items() if k in used}
    instance["fixture_scope"] = "correctness_only_task_and_start_restriction"
    return instance, starts


def fixtures(config):
    base = next(p for p in build_instances(config) if p["id"] == "base__R1")
    ab, ac = [s["id"] for s in base["scenarios"]]
    return {
        "shared_two_scenes": select_fixture(base, "shared_two_scenes",
            {ab: ["A.pre"], ac: ["A.pre"]}, {"A.pre": [0]}),
        "parallel_cpu": select_fixture(base, "parallel_cpu",
            {ab: ["A.pre", "B.pre"]}, {"A.pre": [0, 15], "B.pre": [0, 15]}),
        "chain_fractional": select_fixture(base, "chain_fractional",
            {ab: ["A.pre", "A.main"]}, {"A.pre": [0], "A.main": [10, 15]}),
        "accelerator_queue": select_fixture(base, "accelerator_queue",
            {ab: ["A.main", "B.main"]}, {"A.main": [0], "B.main": [35]}),
        "one_stage_energy": select_fixture(base, "one_stage_energy",
            {ab: ["A.pre"]}, {"A.pre": [0]}),
    }


def candidate_key(candidate):
    return tuple((scene, tuple(sorted((row["stage_id"], row["unit"], row["opp"],
                                      str(F(row["start_ms"]))) for row in rows)))
                 for scene, rows in sorted(candidate["scenes"].items()))


def independent_assignments(instance, starts):
    """All Cartesian choices; no dependency/resource/shared-map filtering."""
    dimensions = []
    for scene in instance["scenarios"]:
        requests = {r["id"]: r for r in scene["requests"]}
        for stage in scene["stage_instances"]:
            options = []
            release = F(requests[stage["request_id"]]["release_ms"])
            for mode in instance["stage_modes"][stage["shared_stage_id"]]:
                for start in starts[scene["id"]][stage["id"]]:
                    when = F(start)
                    if when < release or when+F(mode["duration_ms"]) > F(instance["window_ms"]):
                        continue
                    options.append((scene["id"], {"stage_id": stage["id"],
                        "unit": mode["unit_id"], "opp": mode["opp_id"], "start_ms": str(when)}))
            dimensions.append(options)
    for selected in product(*dimensions):
        candidate = {"scenes": {scene["id"]: [] for scene in instance["scenarios"]}}
        for scene, row in selected:
            candidate["scenes"][scene].append(dict(row))
        yield candidate


def independent_check(instance, candidate):
    """Exact independent task and busy/idle domain-state oracle."""
    units = {u["id"]: u for u in instance["platform"]["units"]}
    domain_data = instance["platform"]["domains"]
    shared, output = {}, {}
    try:
        if set(candidate["scenes"]) != {s["id"] for s in instance["scenarios"]}:
            return {"valid": False, "reason": "scene_coverage"}
        for scene in instance["scenarios"]:
            supplied = candidate["scenes"][scene["id"]]
            stages = {s["id"]: s for s in scene["stage_instances"]}
            requests = {r["id"]: r for r in scene["requests"]}
            if len(supplied) != len(stages) or {r["stage_id"] for r in supplied} != set(stages):
                return {"valid": False, "reason": "stage_coverage"}
            rows = {}
            for row in supplied:
                stage = stages[row["stage_id"]]
                options = [m for m in instance["stage_modes"][stage["shared_stage_id"]]
                           if (m["unit_id"], m["opp_id"]) == (row["unit"], row["opp"])]
                if len(options) != 1:
                    return {"valid": False, "reason": "mode"}
                mode, when = options[0], F(row["start_ms"])
                request = requests[stage["request_id"]]
                end = when+F(mode["duration_ms"])
                if when < 0 or (when/F(instance["start_grid_ms"])).denominator != 1:
                    return {"valid": False, "reason": "start_domain"}
                if when < F(request["release_ms"]):
                    return {"valid": False, "reason": "release"}
                if end > min(F(request["deadline_ms"]), F(instance["window_ms"])):
                    return {"valid": False, "reason": "deadline"}
                key = stage["shared_stage_id"]
                if key in shared and shared[key] != row["unit"]:
                    return {"valid": False, "reason": "shared_deployment"}
                shared[key] = row["unit"]
                rows[row["stage_id"]] = dict(row, start=when, end=end, mode=mode,
                    domain=units[row["unit"]]["domain_id"])
            if any(rows[a]["end"] > rows[b]["start"] for a, b in scene["dependencies"]):
                return {"valid": False, "reason": "dependency"}
            ordered = list(rows.values())
            for index, left in enumerate(ordered):
                for right in ordered[index+1:]:
                    if left["start"] >= right["end"] or right["start"] >= left["end"]:
                        continue
                    if left["unit"] == right["unit"]:
                        return {"valid": False, "reason": "unit_exclusive"}
                    if left["domain"] == right["domain"] and left["opp"] != right["opp"]:
                        return {"valid": False, "reason": "busy_domain_conflict"}
            # Sweep ends before starts. Held OPP changes only on new work,
            # never merely because a domain becomes empty.
            events = sorted({F(0), F(instance["window_ms"])} |
                            {r[k] for r in ordered for k in ("start", "end")})
            held = dict(scene["entry"]["domain_opp"])
            pieces = []
            for start, end in zip(events, events[1:]):
                new = [r for r in ordered if r["start"] == start]
                active = [r for r in ordered if r["start"] <= start < r["end"]]
                old = [r for r in active if r["start"] < start]
                for domain in domain_data:
                    op = {r["opp"] for r in new if r["domain"] == domain}
                    if len(op) > 1:
                        return {"valid": False, "reason": "simultaneous_domain_conflict"}
                    if op:
                        selected = next(iter(op))
                        if any(r["domain"] == domain and r["opp"] != selected for r in old):
                            return {"valid": False, "reason": "busy_domain_switch"}
                        held[domain] = selected
                nodes = instance["platform"]["node_order"]
                base, activity, leak = ({node: F(0) for node in nodes} for _ in range(3))
                for domain, data in domain_data.items():
                    for node, portion in zip(nodes, data["baseline_heat_distribution"]):
                        base[node] += F(data["baseline_W"][held[domain]])*F(portion)
                    for unit in data["unit_ids"]:
                        leak[units[unit]["thermal_node_id"]] += F(data["local_temperature_slope_W_per_K"][held[domain]])
                for row in active:
                    activity[units[row["unit"]]["thermal_node_id"]] += F(row["mode"]["activity_power_W"])
                pieces.append({"start_ms": str(start), "end_ms": str(end),
                    "domain_opps": dict(held), "baseline_by_node_W": {k: str(v) for k, v in base.items()},
                    "activity_by_node_W": {k: str(v) for k, v in activity.items()},
                    "local_leakage_slope_W_per_K": {k: str(v) for k, v in leak.items()}})
            output[scene["id"]] = {"rows": rows, "segments": pieces}
        return {"valid": True, "scenes": output, "shared_deployment": shared}
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return {"valid": False, "reason": "malformed"}


def structural_checks(fixture_map, check, records):
    legal_by_fixture = {}
    observed = set()
    for name, (instance, starts) in fixture_map.items():
        items = list(independent_assignments(instance, starts))
        legal = []
        differences, accounting_errors, reasons = [], [], {}
        for candidate in items:
            own = independent_check(instance, candidate)
            common = validate_schedule(instance, candidate)
            expected = common["state"] == "SCHEDULE_VALID_THERMAL_UNCHECKED"
            if own["valid"] != expected:
                differences.append({"candidate": candidate, "oracle": own["valid"], "common": common})
            if not own["valid"]:
                reasons[own["reason"]] = reasons.get(own["reason"], 0)+1
                continue
            legal.append(candidate)
            for scene_id, values in own["scenes"].items():
                common_pieces = common["scenes"][scene_id]["segments"]
                if len(values["segments"]) != len(common_pieces):
                    accounting_errors.append("segment_count")
                else:
                    for ours, theirs in zip(values["segments"], common_pieces):
                        if any(ours[k] != theirs[k] for k in ours):
                            accounting_errors.append({"ours": ours, "theirs": theirs})
                rows = list(values["rows"].values())
                if any(r["end"].denominator != 1 for r in rows):
                    observed.add("noninteger_finish")
                observed.update(r["unit"] for r in rows)
                for i, a in enumerate(rows):
                    for b in rows[i+1:]:
                        overlap = a["start"] < b["end"] and b["start"] < a["end"]
                        if overlap and a["domain"] == b["domain"] and a["unit"] != b["unit"]:
                            observed.add("same_frequency_parallel")
                        if a["unit"] == b["unit"] == "NPU0" and not overlap:
                            observed.add("npu_queue")
            if len(instance["scenarios"]) > 1:
                observed.add("shared_across_scenes")
        check(f"oracle/{name}/all_cartesian_assignments", lambda d=differences: equal(d, []))
        check(f"oracle/{name}/power_state_sweep", lambda e=accounting_errors: equal(e, []))
        check(f"oracle/{name}/nonempty_legal_domain", lambda x=legal: require(bool(x), "empty legal domain"))
        legal_by_fixture[name] = legal
        records[name] = {"cartesian_count": len(items), "legal_count": len(legal),
            "invalid_reasons": reasons, "differences": differences, "accounting_errors": accounting_errors}
        observed.update(reasons)
    for feature in ("noninteger_finish", "CPU1", "CPU2", "GPU0", "NPU0",
                    "same_frequency_parallel", "npu_queue", "shared_across_scenes",
                    "busy_domain_conflict", "shared_deployment", "dependency", "unit_exclusive"):
        check("coverage/"+feature, lambda value=feature: require(value in observed, "feature absent: "+value))
    return legal_by_fixture


def canonical_structure_vector(model, candidate):
    """Fill scheduling auxiliaries independently from the encoder.

    For an invalid assignment, the first selected shared unit/OPP is used;
    contradictory selections must then violate a shared-link or active-lock
    row. For a legal assignment the held domain history is unique.
    """
    x = [0.0]*len(model.names)
    selected = {(scene, row["stage_id"], row["unit"], row["opp"], F(row["start_ms"]))
                for scene, rows in candidate["scenes"].items() for row in rows}
    chosen, shared = [], {}
    for option, index in zip(model.options, model.option_vars):
        key = (option["scenario_id"], option["stage_instance_id"], option["unit_id"],
               option["opp_id"], F(option["start_ms"]))
        if key in selected:
            x[index] = 1.0
            chosen.append(option)
            shared.setdefault(option["shared_stage_id"], option["unit_id"])
    for key, index in model.shared.items():
        x[index] = float(shared.get(key[0]) == key[1])
    domains = model.instance["platform"]["domains"]
    for scene in model.instance["scenarios"]:
        meta = model.scenes[scene["id"]]
        held = dict(scene["entry"]["domain_opp"])
        for l, when in enumerate(meta["events"][:-1]):
            for domain in domains:
                new = [o for o in chosen if o["scenario_id"] == scene["id"] and
                       o["domain_id"] == domain and F(o["start_ms"])/1000 == when]
                x[meta["start_indicators"][l, domain]] = float(bool(new))
                if new:
                    held[domain] = new[0]["opp_id"]
                for opp in domains[domain]["opps"]:
                    x[meta["rho"][l, domain, opp]] = float(held[domain] == opp)
            state = tuple(held[d] for d in domains)
            if (l, state) in meta["joint"]:
                x[meta["joint"][l, state]] = 1.0
    return x


def exact_row_residuals(model, vector, rows=None):
    rows = model.rows if rows is None else rows
    result = []
    for row in rows:
        lhs = sum((F.from_float(float(a))*F.from_float(float(vector[j]))
                   for j, a in row["coef"].items()), F(0))
        result.append(lhs-F.from_float(float(row["rhs"])))
    return result


def model_checks(config, fixture_map, check, records, folder):
    from milp import build_model, decode
    from thermal import Budget
    models = {}
    for name, (instance, starts) in fixture_map.items():
        model = build_model(instance, config, starts=starts,
                            budget=Budget(seconds=600), include_physics=False)
        models[name] = model
        mismatch = []
        legal_vector = None
        for candidate in independent_assignments(instance, starts):
            valid = independent_check(instance, candidate)["valid"]
            vector = canonical_structure_vector(model, candidate)
            residuals = exact_row_residuals(model, vector)
            row_valid = all(r <= 0 for r in residuals)
            if valid != row_valid:
                mismatch.append({"candidate": candidate, "oracle_valid": valid,
                    "violated_tags": [row["tag"] for row, r in zip(model.rows, residuals) if r > 0]})
            if valid:
                legal_vector = vector
        check(f"encoding/{name}/complete_cartesian_projection", lambda e=mismatch: equal(e, []))
        records[name] = dict(model.summary(), projection_mismatches=mismatch,
            projection_check="exact rational arithmetic over exported double rows; scheduling auxiliaries reconstructed independently")
        if legal_vector is not None:
            check(f"encoding/{name}/roundtrip", lambda m=model, v=legal_vector: require(
                independent_check(m.instance, decode(m, v))["valid"], "decoded invalid candidate"))
    good = models["one_stage_energy"]
    candidate = next(c for c in independent_assignments(*fixture_map["one_stage_energy"])
                     if independent_check(good.instance, c)["valid"])
    vector = canonical_structure_vector(good, candidate)
    wrong = list(vector)
    wrong[good.option_vars[0]] = 0.5
    def reject_fractional():
        try:
            decode(good, wrong)
        except ValueError:
            return
        raise AssertionError("fractional candidate accepted")
    check("decode/noninteger_rejected", reject_fractional)
    selected = next(i for i in good.option_vars if vector[i] == 1)
    tiny = list(vector); tiny[selected] = 1-5e-7
    check("decode/near_integer_independently_validated", lambda: equal(
        candidate_key(decode(good, tiny)), candidate_key(candidate)))
    def reject_production_trim():
        original = deepcopy(good.instance); original["id"] = "not_a_fixture"
        try:
            build_model(original, config, starts=fixture_map["one_stage_energy"][1],
                        budget=Budget(seconds=10), include_physics=False)
        except ValueError:
            return
        raise AssertionError("production domain was silently restricted")
    check("domain/no_reduced_production_starts", reject_production_trim)
    save(folder/"structure_models.json", records)
    return models


def full_checks(config, fixture_map, legal, models, check, folder):
    """Actual R2023b calls are correctness checks, not performance results."""
    import numpy as np
    from matlab_bridge import MatlabSession
    from milp import build_model, decode, lift_candidate, solve_with_feedback
    from thermal import Budget, evaluate_candidate
    instance, starts = fixture_map["one_stage_energy"]
    physical_model = build_model(instance, config, starts=starts, budget=Budget(seconds=600))
    thermal = []
    lifts = []
    accuracy = config["accuracy_targets"]
    for candidate in legal["one_stage_energy"]:
        evaluation = evaluate_candidate(instance, candidate, accuracy, Budget(seconds=60))
        thermal.append({"candidate": candidate, "evaluation": evaluation})
        vector = lift_candidate(physical_model, candidate)
        residuals = exact_row_residuals(physical_model, vector)
        largest = float(max(residuals, default=F(0)))
        bounds = max([0.0]+[physical_model.lb[i]-float(v) for i, v in enumerate(vector)]+
                     [float(v)-physical_model.ub[i] for i, v in enumerate(vector)])
        lifts.append({"candidate": candidate, "maximum_row_residual": largest,
                      "maximum_bound_residual": bounds,
                      "purpose": "independent matrix-exponential lifting cross-check, not a numerical certificate"})
    check("physics/all_six_options_have_safe_complete_evaluation", lambda: require(
        all(r["evaluation"]["state"] == "SAFE" for r in thermal), "some complete option unresolved/unsafe"))
    check("physics/independent_exponential_lifts_satisfy_rows", lambda: require(
        all(r["maximum_row_residual"] <= 2e-8 and r["maximum_bound_residual"] <= 2e-8 for r in lifts), str(lifts)))
    save(folder/"complete_thermal_oracle.json", thermal)
    save(folder/"independent_lifts.json", lifts)
    save(folder/"physical_model_summary.json", physical_model.summary())
    solver_records = {}
    with MatlabSession(folder/"matlab", total_budget_s=900) as session:
        for name in ("shared_two_scenes", "parallel_cpu", "chain_fractional", "accelerator_queue"):
            response = session.solve(models[name].as_solver_dict(), remaining_s=60)
            solver_records[name] = response
            check(f"solver/{name}/has_candidate", lambda r=response: require(
                r.get("accepted_for_evaluation"), str(r)))
            if response.get("accepted_for_evaluation"):
                decoded = decode(models[name], response["x"])
                solver_records[name]["decoded_candidate"] = decoded
                check(f"solver/{name}/candidate_in_independent_legal_set", lambda c=decoded, n=name:
                    require(candidate_key(c) in {candidate_key(x) for x in legal[n]}, "outside Cartesian oracle"))
        response = session.solve(physical_model.as_solver_dict(), remaining_s=60)
        solver_records["physical"] = response
        check("solver/physical/has_candidate", lambda: require(response.get("accepted_for_evaluation"), str(response)))
        if response.get("accepted_for_evaluation"):
            decoded = decode(physical_model, response["x"])
            evaluated = evaluate_candidate(instance, decoded, accuracy, Budget(seconds=60))
            solver_records["physical"]["decoded_candidate"] = decoded
            solver_records["physical"]["common_evaluation"] = evaluated
            check("solver/physical/common_evaluator_safe", lambda: equal(evaluated["state"], "SAFE"))
            if evaluated["state"] == "SAFE":
                best_upper = min(F(r["evaluation"]["weighted_energy_J"][1]) for r in thermal)
                chosen = list(map(F, evaluated["weighted_energy_J"]))
                check("solver/physical/energy_matches_exhaustive_small_domain", lambda: require(
                    chosen[0] <= best_upper and chosen[1]-best_upper <= F("0.000001"),
                    "solver candidate is not within oracle energy enclosure accuracy"))
                solver_value = sum(float(a)*float(v) for a, v in zip(physical_model.c, response["x"]))
                check("solver/physical/full_energy_objective_matches_common_evaluation", lambda: require(
                    float(chosen[0])-1e-6 <= solver_value <= float(chosen[1])+1e-6,
                    "MILP full objective disagrees with independent energy"))
        expired = session.solve(models["one_stage_energy"].as_solver_dict(), remaining_s=0)
        check("budget/expired_does_not_dispatch_solver", lambda: equal(expired["status"], "BUDGET_EXHAUSTED"))
    save(folder/"solver_results.json", solver_records)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--structural-only", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Output directory already exists; previous evidence is never overwritten")
    args.out.mkdir(parents=True)
    started = time.monotonic()
    config = load_config()
    config_hash = digest(HERE/"config_v01.json")
    sources = [HERE/x for x in ("config_v01.json", "inputs.py", "schedules.py", "thermal.py", "run_milp_precheck.py")]
    sources += [HERE/name for name in ("milp.py", "milp_coefficients.py", "matlab_bridge.py", "solve_model.m") if (HERE/name).exists()]
    hashes = {str(p.relative_to(REPO)): digest(p) for p in sources}
    snapshot = args.out/"source_snapshot"
    snapshot.mkdir()
    for path in sources:
        shutil.copy2(path, snapshot/path.name)
    checks = []
    def check(name, function):
        try:
            function()
            checks.append({"name": name, "status": "PASS"})
        except Exception as error:
            checks.append({"name": name, "status": "FAIL", "error": f"{type(error).__name__}: {error}"})
    data = fixtures(config)
    save(args.out/"fixtures.json", {name: {"instance": item[0], "starts": item[1]} for name, item in data.items()})
    counts = {}
    legal = structural_checks(data, check, counts)
    save(args.out/"oracle_counts.json", counts)
    save(args.out/"legal_candidates.json", legal)
    models = model_checks(config, data, check, {}, args.out)
    if not args.structural_only:
        check("milp/complete_integration", lambda: full_checks(config, data, legal, models, check, args.out))
    check("inputs/frozen_config_unchanged", lambda: equal(digest(HERE/"config_v01.json"), config_hash))
    check("sources/no_change_during_precheck", lambda: equal(hashes, {str(p.relative_to(REPO)): digest(p) for p in sources}))
    passed = sum(x["status"] == "PASS" for x in checks)
    report = {"status": "PASS" if passed == len(checks) else "FAIL", "passed": passed,
        "total": len(checks), "checks": checks, "source_sha256": hashes,
        "formal_experiments_ready": False, "formal_algorithm_comparison": False,
        "scope": "small_domain_structure_only" if args.structural_only else "small_domain_milp_and_feedback",
        "wall_seconds": time.monotonic()-started, "python": host_platform.python_version()}
    save(args.out/"checks.json", report)
    print(json.dumps({k: report[k] for k in ("status", "passed", "total", "wall_seconds")}, ensure_ascii=False))
    for item in checks:
        if item["status"] == "FAIL":
            print(item["name"]+": "+item["error"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
