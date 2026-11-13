"""Supplementary read-only checks of archived budget and path evidence."""
import json
from fractions import Fraction
from pathlib import Path

OUT = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text(encoding="utf-8"))


def main():
    analysis = read(OUT / "analysis.json")
    records = {}
    unresolved = []
    interrupted = []
    for row in analysis["rows"]:
        sid = row["id"]
        raw = read(OUT / "execution/calls" / sid / "method/result.json")
        byhash = {e["candidate_sha256"]: e for e in raw["evaluations"]}
        proposals = []
        for i, p in enumerate(raw["graph_proposals"], 1):
            e = byhash[p["candidate_sha256"]]
            proposals.append({
                "ordinal": i, "sha256": p["candidate_sha256"],
                "extra_edges": p["additional_reversed_edges"],
                "proposed_at_s": p["proposed_at_s"],
                "returned_at_s": e["returned_at_s"],
                "state": e["receipt"]["state"], "accepted": p["strict_accepted"],
                "energy_J": float(Fraction(e["receipt"]["weighted_energy_J"][1]))
                if e["receipt"].get("weighted_energy_J") else None,
            })
        for e in raw["evaluations"]:
            if e["receipt"]["state"] == "SAFE":
                continue
            assert e["receipt"]["state"] == "UNRESOLVED"
            assert e["receipt"]["reason"] == "wall_time_limit"
            assert not e["accepted_safe"] and not e["incumbent_replaced"]
            unresolved.append({"slot": sid, "sha256": e["candidate_sha256"],
                               "reason": "wall_time_limit", "accepted": False})
        if row["construction_calls_interrupted"]:
            interrupted.append({"slot": sid, "count": row["construction_calls_interrupted"],
                                "terminal": row["terminal"]})
        records[sid] = {"proposals": proposals, "startup_phases": [
            {k: p[k] for k in ("phase", "start_s", "end_s", "exclusive_s")}
            for p in raw["timing"]["phase_records"]
            if p["phase"] in ("frozen_identity_and_scientific_imports", "input_imports_and_context")
        ]}
    cache_checks = []
    for c in analysis["comparisons"]:
        if (c["arm"], c["reference"]) not in (("ON_P", "ON"), ("OFF_P", "OFF")):
            continue
        ids = {r["arm"]: r["id"] for r in analysis["rows"] if r["case_id"] == c["case_id"]}
        a, b = (analysis["details"][ids[k]] for k in (c["arm"], c["reference"]))
        different_initial = {e["sha256"] for e in a["initial_evaluations"]} ^ {
            e["sha256"] for e in b["initial_evaluations"]}
        observed_search = set(a["proposal_sequence"]) | set(b["proposal_sequence"])
        cache_checks.append({"case": c["case_id"], "arm": c["arm"],
                             "different_initial_candidates": len(different_initial),
                             "intersection_with_observed_search": sorted(different_initial & observed_search)})
    onp = records["07_U04__n24_ON_P_I1"]["proposals"]
    on = records["08_U04__n24_ON_I1"]["proposals"]
    assert [p["sha256"] for p in onp[:20]] == [p["sha256"] for p in on]
    assert onp[19]["accepted"] and on[19]["state"] == "UNRESOLVED"
    assert onp[20]["extra_edges"] and onp[20]["accepted"]
    assert len(unresolved) == 5 and sum(p["count"] for p in interrupted) == 3
    out = {"new_scientific_calls": 0, "unresolved_evaluations": unresolved,
           "budget_interrupted_constructions": interrupted, "records": records,
           "initial_cache_checks": cache_checks,
           "U04_same_20th_proposal": {"ON_P": onp[19], "ON": on[19]},
           "U04_extra_edge_21st": onp[20]}
    (OUT / "audit_details.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unresolved": len(unresolved), "interrupted_constructions": 3,
                      "cache_checks": cache_checks, "U04": out["U04_same_20th_proposal"],
                      "U04_extra": onp[20]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
