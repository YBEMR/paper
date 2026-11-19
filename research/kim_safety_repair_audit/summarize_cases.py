"""Export one row per registered condition without running simulations."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "new"


def summary(row):
    case = row["case"]
    selected = row["independent"] or {}
    physical = selected.get("physical", {})
    oracle = row["oracle"] or {}
    solutions = list(oracle.get("solutions", {}).values())
    first_hot = next((s["scene"] for s in physical.get("scene_rows", [])
                      if s["thermal_status"] == "VIOLATION"), None)
    data = dict(case=case["id"], historic_repeat=case["historic_repeat"],
                order=" ".join(case["order"]), dwell_by_sc0_to_sc3_frames=" ".join(map(str, case["dwell_frames"])),
                ambient_c=case["ambient"], requested=row["requested"], outcome=row["classification"],
                deployment=selected.get("deployment"), opps_in_execution_order=" ".join(selected.get("opps", [])),
                independent_score_j=selected.get("predicted_j"), continuous_energy_j=physical.get("energy_j"),
                continuous_feasible=physical.get("feasible"), completed=physical.get("completed"),
                deadline_ok=physical.get("deadline_ok"), min_slack_ms=physical.get("min_slack_ms"),
                first_overtemp_scene=first_hot)
    for k, node in enumerate(("cpu", "gpu", "dla0", "dla1")):
        for bound in ("lower", "upper"):
            peaks = physical.get("peak_" + bound + "_c")
            data[f"peak_{node}_{bound}_c"] = peaks[k] if peaks else None
    data.update(reference_method=oracle.get("method"), reference_status=oracle.get("status"),
                logical_sequences_covered=oracle.get("logical_complete_space"),
                safe_complete_sequences=0 if oracle.get("status") == "NO_SAFE" else None)
    for metric in ("deadline_failed", "overtemp", "unresolved", "prefix_thermal_evaluations", "fallback_segment_replays"):
        data[metric] = sum(s[metric] for s in solutions) if solutions and all(metric in s for s in solutions) else None
    data.update(common_selected_full_replays=int(bool(selected)),
                schedule_s=row["timing"]["scheduling_s"], independent_score_s=row["timing"]["reset_scoring_s"],
                selected_replay_s=row["timing"].get("independent_replay_s"), reference_total_s=oracle.get("total_s"),
                repair_comparison_run=row["repairs"] is not None)
    return data


def main():
    cases = json.loads((RAW / "results.json").read_bytes())
    rows = [summary(case) for case in cases]
    with (HERE / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
