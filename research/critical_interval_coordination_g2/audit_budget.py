"""Print a compact, machine-readable audit of the actual frozen runs for the final report."""
import json
from collections import Counter

from tables import ROOT, read_csv


def describe():
    rows = read_csv("summary.csv")
    pairs = read_csv("paired.csv")
    stages = {"configuration": [], "timing": []}
    for path in sorted((ROOT / "runs").glob("*/rounds.jsonl")):
        if not (path.parent / "receipt.json").exists():
            continue
        for line in path.read_bytes().splitlines():
            r = json.loads(line)
            stages[r["phase"]].append((r["round_s"], path.parent.name, r["turn"], r["solver"]["status"]))
    periods = {}
    for key, records in stages.items():
        periods[key] = {
            "rounds": len(records),
            "max_s": max(r[0] for r in records),
            "over_30_s": [[round(r[0], 5), r[1], r[2]] for r in records if r[0] > 30],
            "solver_status": dict(Counter(r[-1] for r in records)),
        }
    counts = {kind: dict(Counter(r["final_verdict"] for r in pairs if r["batch"] == kind))
              for kind in ("main", "strong")}
    return {
        "final_pair_verdicts": counts,
        "arms": dict(Counter(r["status"] for r in rows)),
        "certificates_across_arms": sum(int(r["certificates"]) for r in rows),
        "initialization_certificates": sum(int(r["certificates"]) for r in read_csv("construction.csv")),
        "charged_seconds_completed_arms": sum(float(r["charged_s"]) for r in rows if r["charged_s"]),
        "completed_max_by_budget": {k: max(float(r["charged_s"]) for r in rows if r["budget_s"] == k and r["charged_s"])
                                    for k in sorted({r["budget_s"] for r in rows if r["charged_s"]})},
        "phases": periods,
    }


if __name__ == "__main__":
    path = ROOT / "budget_audit.json"
    path.write_text(json.dumps(describe(), indent=2, ensure_ascii=False) + "\n", encoding="utf8", newline="\n")
