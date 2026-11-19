"""Read-only postprocessing of the preregistered saved arrays; no simulations."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

HERE = Path(__file__).resolve().parent
INPUT = json.loads((HERE.parents[1]/"expanded_input.json").read_text(encoding="utf-8"))
OPPS = ["".join(x) for x in INPUT["clock_policy"]["constant_opp_levels"]]
N = len(OPPS)
SIZE = N**4


def decode(code):
    return [OPPS[(code//N**(3-j))%N] for j in range(4)]


def array(path, record):
    blob = path.read_bytes()
    assert len(blob) == record["bytes"]
    assert hashlib.sha256(blob).hexdigest() == record["sha256"]
    with np.load(path, allow_pickle=False) as saved:
        return saved["status"].copy(), saved["energy_j"].copy()


def analyze_case(case):
    folder = HERE/case["case"]["id"]
    rows = json.loads((folder/"deployments.json").read_text(encoding="utf-8"))
    by_id = {row["deployment"]: row for row in rows}
    assert list(by_id) == case["completed_deployments"]
    base = {d:array(folder/f"space_{d}.npz", by_id[d]["array_archive"]) for d in ("A", "C")}
    a, c = base["A"][0], base["C"][0]
    old_safe = (a == 1) | (c == 1)
    categories = dict(old_both_thermal_failed=(a == 2) & (c == 2),
                      old_both_deadline_failed=(a == 0) & (c == 0),
                      old_mixed_deadline_or_thermal=((a == 0) & (c == 2)) | ((a == 2) & (c == 0)))
    union = np.zeros(SIZE, dtype=bool)
    offload_union = union.copy()
    best_new = np.full(SIZE, np.inf)
    best_dep = np.full(SIZE, -1, dtype=np.int16)
    represented_new, multiplicity, infeasible, hhh = [], 0, [], {}
    total_bytes = 0
    for row in rows:
        d = row["deployment"]
        states, energy = array(folder/f"space_{d}.npz", row["array_archive"])
        total_bytes += row["array_archive"]["bytes"]
        counts = np.bincount(states, minlength=4)
        for i, key in enumerate(("deadline_failed", "safe", "overtemp", "unresolved")):
            assert int(counts[i]) == row[key]
        assert int(counts.sum()) == SIZE
        assert np.array_equal(states != 0, np.isfinite(energy))
        if row["safe"]:
            assert float(np.min(energy[states == 1])) == row["minimum_safe_array_j"]
        if d in ("A", "C", "D001", "D015"):
            hhh[d] = dict(code=SIZE-1, opps=decode(SIZE-1), status=int(states[-1]),
                          continuous_j=float(energy[-1]) if np.isfinite(energy[-1]) else None)
        independent = row["independent"]
        if row["safe"] == 0 and row["overtemp"] > 0 and row["unresolved"] == 0:
            infeasible.append(dict(deployment=d, deadline_legal_sequences=int(counts[2]),
                all_deadline_legal_sequences_thermal_failed=True,
                independent_selected=independent is not None,
                independent_reset_j=independent["predicted_j"] if independent else None,
                independent_continuous_j=independent["physical"]["energy_j"] if independent else None,
                independent_peak_c=max(independent["physical"]["peak_upper_c"]) if independent else None,
                independent_continuous_status=independent["physical"]["thermal_status"] if independent else None,
                reset_admitted_sequences=row["sets"]["reset_feasible"]))
        if d in ("A", "C"):
            continue
        j = len(represented_new)
        represented_new.append(d)
        safe = states == 1
        multiplicity += int(np.sum(safe & ~old_safe))
        union |= safe
        if len(INPUT["deployments"][d]["stages"]["3"]) > 1:
            offload_union |= safe
        improve = safe & (energy < best_new)
        best_new[improve], best_dep[improve] = energy[improve], j
    witnesses = {}
    for name, category in categories.items():
        codes = np.flatnonzero(union & category)
        if len(codes):
            code = int(codes[np.argmin(best_new[codes])])
            d = represented_new[int(best_dep[code])]
            witnesses[name] = dict(code=code, opps=decode(code), new_deployment=d,
                new_continuous_j=float(best_new[code]),
                old={k:dict(status=int(v[0][code]), continuous_j=float(v[1][code])
                           if np.isfinite(v[1][code]) else None) for k,v in base.items()},
                selection="post-hoc lowest saved energy among this descriptive category; not a new search")
    resource_rows = list(csv.DictReader((folder/"sc2_resources.csv").open(encoding="utf-8")))
    resources = {}
    for d in ("C", "D001", "D015"):
        r = next(x for x in resource_rows if x["deployment"] == d and x["opp"] == "HHH")
        resources[d] = {k:float(r[k]) for k in (
            "gpu_requested_service_ms", "dla0_requested_service_ms", "dla1_requested_service_ms",
            "gpu_utilization", "gpu_wait_sum_ms", "gpu_wait_max_ms", "min_slack_ms", "max_response_ms")}
        resources[d]["deadline_ok"] = r["deadline_ok"] == "True"
    for d, r in resources.items():
        r["gpu_service_reduction_vs_C_pct"] = 100*(1-r["gpu_requested_service_ms"] /
                                                     resources["C"]["gpu_requested_service_ms"])
    return dict(case=case["case"]["id"], checked_arrays=len(rows), array_bytes=total_bytes,
        interpretation="Counts of unique four-scene OPP codes are distinct from deployment-code policy counts. All counts refer only to completely searched new deployments.",
        old_ac_union_safe_codes=int(np.sum(old_safe)),
        new_deployment_union_safe_codes=int(np.sum(union)),
        new_union_safe_without_any_old_safe_same_code=int(np.sum(union & ~old_safe)),
        v3_offload_union_safe_without_any_old_safe_same_code=int(np.sum(offload_union & ~old_safe)),
        new_policy_multiplicity_without_old_safe_same_code=multiplicity,
        unique_same_code_reversals={name:int(np.sum(union & mask)) for name,mask in categories.items()},
        witness_by_category=witnesses, hhh_same_clock_saved_array_records=hhh,
        sc2_hhh_resources=resources, complete_deployment_thermal_infeasibility=infeasible,
        global_independent_selected_status=case["decisions"]["independent"]["physical"]["thermal_status"],
        compiled_search_cost_s=sum(r["joint_search_s"] for r in rows),
        complete_deployment_compile_s=sum(r["compile_s"] for r in rows),
        scientific_evaluations_added_by_this_script=0)


def main():
    cases = json.loads((HERE/"results.json").read_text(encoding="utf-8"))
    result = dict(source="postprocessing of immutable saved outputs; no evaluator imported",
                  cases=[analyze_case(case) for case in cases])
    (HERE/"derived_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                      allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps([dict(case=r["case"], checked_arrays=r["checked_arrays"],
                          reversals=r["unique_same_code_reversals"],
                          thermal_infeasible_deployments=len(r["complete_deployment_thermal_infeasibility"]))
                      for r in result["cases"]], indent=2))


if __name__ == "__main__":
    main()
