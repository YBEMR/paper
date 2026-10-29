"""Read archived scalars and count option/event cardinalities; no model imports.

Run: python -B research/chapter3_formal_input_audit/static_scale01/static_count.py
This is an implementation audit, not an experiment or an input adapter.  It
never materializes legal option records, schedules, matrices, or trajectories.
"""
from fractions import Fraction as F
from pathlib import Path
from collections import defaultdict
import gzip
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BETA = "13/10"
DELTA = F(5)
SOURCE_FILES = (
    "research/chapter3_experiments/inputs.py",
    "research/chapter3_experiments/milp.py",
    "research/chapter3_experiments/milp_coefficients.py",
    "research/chapter3_experiments/formal_milp.py",
    "research/chapter3_experiments/p0_batch/dispatch.py",
    "research/chapter3_experiments/run_warm_diagnostic.py",
    "research/chapter3_experiments/run_initial_witness_diagnostic.py",
    "research/chapter3_experiments/long_budget_diagnostic/run_once.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ceil_q(x):
    return -((-x.numerator) // x.denominator)


def union_cardinality(intervals):
    """Cardinality of a union of integer-index intervals, without enumeration."""
    result, end = 0, None
    for lo, hi in sorted(intervals):
        if lo > hi:
            continue
        if end is None or lo > end + 1:
            result += hi - lo + 1
        elif hi > end:
            result += hi - end
        end = hi if end is None else max(end, hi)
    return result


def add_progression(groups, offset, lo, hi):
    if lo > hi:
        return
    shift = offset // DELTA
    residue = offset - DELTA * shift
    groups[residue].append((lo + shift, hi + shift))


def scene_count(contract, scene, deadlines, window):
    unit_domains = {u["id"]: u["domain_id"] for u in contract["platform"]["units"]}
    requests = {r["id"]: r for r in scene["requests"]}
    groups = defaultdict(list)
    add_progression(groups, F(0), 0, 0)
    add_progression(groups, window, 0, 0)
    raw_y = kept_y = unit_links = 0
    min_d = None
    duration_residues = set()
    for stage in scene["stage_instances"]:
        profile = contract["stage_profiles"][stage["shared_stage_id"]]
        req = requests[stage["request_id"]]
        dreq = deadlines[stage["request_id"]]
        release = F(req["release_ms"])
        assert release == F(dreq["release_ms"])
        lo = max(0, ceil_q(release / DELTA))
        latest = min(window, F(dreq["deadline_ms"]))
        for unit in stage["legal_units"]:
            attrs = profile["units"][unit]
            domain = contract["platform"]["domains"][unit_domains[unit]]
            fref = F(domain["opps"][domain["reference_opp"]]["frequency_GHz"])
            for opp in attrs["legal_opps"]:
                freq = F(domain["opps"][opp]["frequency_GHz"])
                alpha, dref = F(attrs["alpha"]), F(attrs["d_ref_ms"])
                duration = dref * ((1 - alpha) + alpha * fref / freq)
                assert duration > 0
                min_d = duration if min_d is None else min(min_d, duration)
                duration_residues.add(duration % DELTA)
                raw_hi = (window - duration) // DELTA
                raw_y += max(0, raw_hi - lo + 1)
                hi = (latest - duration) // DELTA
                count = max(0, hi - lo + 1)
                kept_y += count
                if count:
                    add_progression(groups, F(0), lo, hi)
                    add_progression(groups, duration, lo, hi)
        # milp.py:928-929 emits a link for every shared legal unit, including
        # units that retain no deadline-feasible local choices.
        unit_links += len(profile["units"])
    events = sum(union_cardinality(v) for v in groups.values())
    return {
        "scenario_id": scene["id"],
        "stage_instances": len(scene["stage_instances"]),
        "requests": len(scene["requests"]),
        "dependencies": len(scene["dependencies"]),
        "local_unit_mapping_equalities": unit_links,
        "initial_option_expansion_count": raw_y,
        "deadline_retained_y_count": kept_y,
        "exact_event_boundary_count": events,
        "exact_interval_count": events - 1,
        "distinct_duration_mod_5ms_count": len(duration_residues),
        "min_duration_ms": str(min_d),
    }


def read_archive(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def audit(path, scenario_count=8):
    evidence = read_archive(path)
    contract = evidence["workload"]["time_contract"]
    assert F(contract["start_grid_ms"]) == DELTA
    seen_support = {}
    for s in contract["scenarios"]:
        for stage in s["stage_instances"]:
            shared = stage["shared_stage_id"]
            support = frozenset(stage["legal_units"])
            assert support == frozenset(contract["stage_profiles"][shared]["units"])
            assert shared not in seen_support or seen_support[shared] == support
            seen_support[shared] = support
    deadlines = evidence["deadlines"][BETA]["requests"]
    # S1 shares the full eight-scenario deadline-derived window. S7 uses the
    # archived paired receipt, whose validity is checked against all deadlines.
    latest = max(F(r["deadline_ms"]) for ds in deadlines.values() for r in ds.values())
    minimum_window = DELTA * ceil_q(latest / DELTA)
    receipt = evidence.get("window_receipts", {}).get(BETA)
    window = F(receipt["window_ms"]) if receipt else minimum_window
    assert window >= minimum_window and window % DELTA == 0
    scenes = contract["scenarios"][:scenario_count]
    assert len(scenes) == scenario_count
    counts = [scene_count(contract, s, deadlines[s["id"]], window) for s in scenes]
    y = sum(c["deadline_retained_y_count"] for c in counts)
    k = sum(c["exact_interval_count"] for c in counts)
    t = sum(c["stage_instances"] for c in counts)
    u = sum(c["local_unit_mapping_equalities"] for c in counts)
    dep = sum(c["dependencies"] for c in counts)
    shared_count = len(contract["stage_profiles"])
    x = sum(len(p["units"]) for p in contract["stage_profiles"].values())
    active_ids = {i["shared_stage_id"] for s in scenes for i in s["stage_instances"]}
    x_active = sum(len(contract["stage_profiles"][i]["units"]) for i in active_ids)
    # These bounds assume the current whole-MILP auto-L expression, deadline
    # prefilter, aggregate locks, physics, and one energy lower-bound row per
    # interval. Q is sum of reachable joint-state counts: K <= Q <= 27 K.
    # V=Y+X+4S+21K+Q. Row count R=R0+Y+48K+A+10Q, 0<=A<=12K.
    # No candidate evaluation, feedback rows, or cumulative-precedence cuts.
    r0 = 2 * len(active_ids) + 3 * t + 2 * u + dep + 8 * scenario_count
    variable_bounds = [y + x_active + 4 * scenario_count + 22 * k,
                       y + x_active + 4 * scenario_count + 48 * k]
    row_bounds = [r0 + y + 58 * k, r0 + y + 330 * k]
    # Shallow allocations that each row necessarily owns in this CPython:
    # a five-key row dict, coefficient dict (even empty), and two-item list.
    # Not a measured model peak; all coefficient entries, variables, active
    # lists, sparse conversion, MATLAB copies, etc. are additional storage.
    container_bytes = (sys.getsizeof({"coef": {}, "rhs": 0., "tag": "",
                                     "rounding_allowance": None, "rhs_interval": [0, 0]})
                       + sys.getsizeof({}) + sys.getsizeof([0, 0]))
    # Guaranteed nonzero families: Stage/map/deadline/start rows contribute
    # 8Y; unit mutex and unit/OPP locks contribute at least 2Y since every
    # positive-length option is active in >=1 event interval. Fixed small
    # rows contribute 48K; joint/marginal/physical target columns >=18Q.
    # Q>=K. Ignore dependency and optional nonzero activity/gate coefficients.
    nnz_lower = 10 * y + 66 * k + 2 * x_active + 2 * u + 8 * scenario_count
    return {
        "archive": path.relative_to(ROOT).as_posix(), "archive_sha256": sha(path),
        "condition": path.parent.name, "beta": BETA, "scenario_count": scenario_count,
        "window_ms": str(window), "window_source": "archived_paired_window" if receipt else "full_8_scene_deadlines_ceiled_to_5ms",
        "per_scene": counts, "exact_totals": {
            "initial_option_expansion_count": sum(c["initial_option_expansion_count"] for c in counts),
            "deadline_retained_y_count": y, "interval_count": k,
            "stage_instances": t, "dependency_count": dep,
            "shared_x_all_profile_count": x, "shared_x_active_profile_count": x_active,
            "inactive_shared_profile_count": shared_count - len(active_ids),
        },
        "conditional_structural_bounds": {
            "variables": variable_bounds, "inequality_rows": row_bounds,
            "thermal_energy_conditional_rows": [10 * k, 270 * k],
            "joint_state_occurrences_Q": [k, 27 * k],
            "if_all_inactive_profiles_retained_add_variables": x - x_active,
            "if_all_inactive_profiles_retained_add_rows": 2 * (shared_count - len(active_ids)),
            "shallow_row_container_lower_bound_bytes": row_bounds[0] * container_bytes,
            "shallow_row_container_bytes_per_row": container_bytes,
            "nonzeros_lower_bound": nnz_lower,
            "compact_CSR_float64_int32_minimum_bytes": 12 * nnz_lower + 4 * (row_bounds[0] + 1),
        },
    }


def self_checks():
    # Hand arithmetic only; no task/option construction or imported code.
    assert ceil_q(F(11, 5)) == 3 and ceil_q(F(10, 5)) == 2
    assert union_cardinality([(0, 2), (2, 4), (7, 8)]) == 7
    assert union_cardinality([(0, 0), (1, 1)]) == 2
    # Starts 0,5,10; duration 7/2 -> finishes 3.5,8.5,13.5; plus W=15.
    groups = defaultdict(list)
    add_progression(groups, F(0), 0, 2)
    add_progression(groups, F(7, 2), 0, 2)
    add_progression(groups, F(15), 0, 0)
    assert sum(union_cardinality(v) for v in groups.values()) == 7
    # Shifted duration 17/2 gives the same residue but different index range.
    add_progression(groups, F(17, 2), 0, 1)
    assert sum(union_cardinality(v) for v in groups.values()) == 7
    return {"state": "PASS", "hand_arithmetic_assertions": 6}


def main():
    start = time.perf_counter()
    checks = self_checks()
    base = ROOT / "research/chapter3_workload_calibration/results/calibration01"
    selected = [base / f"C20__base_{n}/evidence.json.gz" for n in (6, 24, 96)]
    results = [audit(p, s) for p in selected for s in (1, 2, 4, 6, 8)]
    largest = ROOT / "research/chapter3_calibration_supplement/results/remaining25_execution01/C20__S7_staggered_half_base_H_v1/evidence.json.gz"
    results.append(audit(largest, 8))
    ranges = []
    for n in (6, 24, 96):
        samples = [audit(p, 8) for p in sorted(base.glob(f"C*__base_{n}/evidence.json.gz"))]
        ranges.append({"stage_count_per_scenario": n, "sample_count": len(samples),
                       "ranges_of_exact_totals": {
                           key: [min(s["exact_totals"][key] for s in samples), max(s["exact_totals"][key] for s in samples)]
                           for key in ("initial_option_expansion_count", "deadline_retained_y_count", "interval_count")},
                       "window_ms_range": [str(min(F(s["window_ms"]) for s in samples)), str(max(F(s["window_ms"]) for s in samples))],
                       "samples": samples})
    payload = {
        "schema": "read_only_formal_input_static_scale_v1", "state": "STATIC_COUNTS_COMPLETE",
        "scope": "stdlib archived-scalar arithmetic only; zero scheduling/model/solver/heat calls",
        "hypothesis": "Adapter retains archived profile response, request release/deadline and full-grid starts; current whole builder prefilters deadline-late options and uses auto-L, aggregated OPP locks and energy lower bound. No adapter has been run.",
        "exactness": "Y and event K are exact scalar catalog cardinalities under hypothesis, not measured matrices. V/rows use only profiles present in the chosen scenes and are interval bounds because Q and A are not enumerated; extra inactive-profile columns/rows are separately stated. Shared support consistency is asserted across every archived scene.",
        "formulas": {"V": "Y+X+4*S+21*K+Q", "R": "R0+Y+48*K+A+10*Q", "R0": "2*active_shared_profiles+3*stage_instances+2*local_unit_mapping_equalities+dependencies+8*S", "Q_range": "[K,27*K]", "A_range": "[0,12*K]", "NNZ_lower": "10*Y+66*K+2*X+2*local_unit_mapping_equalities+8*S"},
        "limits": ["No elapsed construction, peak memory, solve time or SAFE claim is measured.", "Current expand_options materializes window-valid choices before deadline prefilter; report both counts.", "Unused profiles should be omitted by an adapter; their optional extra X and shared-onehot rows are reported separately.", "Response durations and ends remain exact; 5ms constrains starts only.", "Joint-state and nonzero counts are not claimed exact; active incidence may dominate sparse storage.", "C20 is a declared illustrative archived family, not a formal test-family selection.", "No archived task has been converted into a formal input or model. Counts are conditional on the stated adapter semantics.", "Shallow row-container bound uses this CPython's getsizeof and current row-dictionary representation; it is not a measured total RAM requirement."],
        "runtime_for_container_sizes": sys.version,
        "self_checks": checks,
        "source_sha256": {p: sha(ROOT / p) for p in SOURCE_FILES},
        "script_sha256": sha(Path(__file__)), "illustrative_archives": results,
        "all_24_roots_base_ranges": ranges,
        "static_count_wall_seconds": time.perf_counter() - start,
    }
    dest = OUT / "static_scale_counts.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(dest), "state": payload["state"], "self_checks": checks, "seconds": payload["static_count_wall_seconds"], "illustrations": [{"condition": r["condition"], "S": r["scenario_count"], "W": r["window_ms"], "Y": r["exact_totals"]["deadline_retained_y_count"], "K": r["exact_totals"]["interval_count"], "V_bounds": r["conditional_structural_bounds"]["variables"]} for r in results]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
