"""Read-only receipt/identity/ablation audit. No thermal, solver, or HEFT call."""
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research/chapter3_experiments"))
from research.chapter4_scheduler.mechanism_check.run import read, save, sha, digest, verify
from h02_pair_preflight.receipts import safe_receipt
from schedules import validate_schedule


def weighted_parts(instance, receipt):
    return {part: [str(sum(F(s["weight"]) * F(receipt["scenes"][s["id"]]["energy_components_J"][part][j])
                           for s in instance["scenarios"])) for j in (0, 1)]
            for part in ("activity", "baseline", "external_common", "temperature_correction")}


def main():
    execution = HERE / "execution"
    plan = read(execution / "plan.json")
    verify(plan)
    records, results, checks, receipt_count = [], {}, [], 0
    check = lambda name, passed: checks.append({"name": name, "passed": bool(passed)})
    tokens = []
    for slot in plan["slots"]:
        folder = execution / "calls" / slot["id"]
        result = read(folder / "method/result.json")
        instance, config = read(folder / "method/input_instance.json"), read(folder / "method/input_config.json")
        post = read(folder / "post_receipt.json")
        results[slot["id"]] = result
        tokens.append(result["root_context"]["root_token"])
        check(slot["id"] + ":input_identity", {"input_sha256": digest(instance), "config_sha256": digest(config)} == plan["inputs"][slot["case"]])
        check(slot["id"] + ":complete_three_stage_graphs", all(
            len(s["stage_instances"]) == 6 and len(s["dependencies"]) == 4
            and all(len(r["stage_instance_ids"]) == 3 for r in s["requests"])
            for s in instance["scenarios"]))
        check(slot["id"] + ":one_original_root", result["root_context"]["root_seconds"] == 300
            and result["timing"]["method_elapsed_s"] < 300)
        check(slot["id"] + ":toggle_bound", result["blocking_edge_adjustment_enabled"] is slot["allow_blocking_edges"])
        statuses = Counter()
        for row in result["evaluations"]:
            statuses[row["receipt"]["state"]] += 1
            legal = validate_schedule(instance, row["candidate"])
            check(slot["id"] + ":legality:" + row["candidate_sha256"], row["receipt"]["legality"] == legal
                  and legal["state"] == "SCHEDULE_VALID_THERMAL_UNCHECKED")
            check(slot["id"] + ":candidate_hash:" + row["candidate_sha256"], row["candidate_sha256"] == digest(row["candidate"]))
            if row["receipt"]["state"] == "SAFE":
                safe_receipt(instance, row["candidate"], row["receipt"], config["accuracy_targets"], 300)
                receipt_count += 1
        post_energy = safe_receipt(instance, result["safe_candidate"], post, config["accuracy_targets"], 60)
        receipt_count += 1
        initial = result["initial_safe_snapshot"]
        before = weighted_parts(instance, initial["receipt"])
        after = weighted_parts(instance, result["evaluation"])
        strict_saving = F(initial["energy"]["lower"]) - F(result["evaluation"]["weighted_energy_J"][1])
        check(slot["id"] + ":recorded_post_match", read(folder / "post_return.json")["passed"] is True
            and read(folder / "post_return.json")["energy"] == post_energy)
        check(slot["id"] + ":all_proposals_retained", all(digest(p["candidate"]) == p["candidate_sha256"]
            for p in result["graph_proposals"]))
        check(slot["id"] + ":off_has_no_extra", slot["allow_blocking_edges"] or not any(
            p.get("additional_reversed_edges") for p in result["graph_proposals"]))
        accepted = [p for p in result["graph_proposals"] if p["strict_accepted"]]
        changes = []
        for sid in initial["candidate"]["scenes"]:
            old = {r["stage_id"]: r for r in initial["candidate"]["scenes"][sid]}
            for row in result["safe_candidate"]["scenes"][sid]:
                previous = old[row["stage_id"]]
                if previous != row:
                    changes.append({"scene": sid, "stage": row["stage_id"], "before": previous, "after": row})
        records.append({"slot": slot, "status_counts": dict(statuses),
            "weighted_components_before_J": before, "weighted_components_after_J": after,
            "component_savings_J": {k: [str(F(before[k][0])-F(after[k][1])), str(F(before[k][1])-F(after[k][0]))] for k in before},
            "strict_total_saving_lower_J": str(strict_saving),
            "strict_relative_saving_lower_percent": str(100*strict_saving/F(initial["energy"]["lower"])),
            "first_safe_s": result["first_safe_at_s"], "first_graph_improvement_s": result["first_graph_strict_improvement_at_s"],
            "post_wall_s": read(folder / "post_return.json")["timing"]["method_elapsed_s"],
            "method_root_phase_records": result["timing"]["phase_records"],
            "retained_initial_unchanged": initial["candidate"] == result["safe_candidate"],
            "changes": changes, "accepted_proposal_hashes": [p["candidate_sha256"] for p in accepted],
            "final_peaks_by_scene_degC": {sid: r["peaks_degC"] for sid, r in result["evaluation"]["scenes"].items()},
            "unchanged_scene_ids": [sid for sid in initial["candidate"]["scenes"] if initial["candidate"]["scenes"][sid] == result["safe_candidate"]["scenes"][sid]]})
    for case in ("base__R1", "base__R3"):
        off, on = [next(results[s["id"]] for s in plan["slots"] if s["case"] == case
                        and s["allow_blocking_edges"] is enabled) for enabled in (False, True)]
        check(case + ":identical_full_initializer_metadata", off["initialization"] == on["initialization"])
        check(case + ":identical_ordered_initialization_candidates", [r["candidate_sha256"] for r in off["evaluations"]
            if r["phase"] == "initialization"] == [r["candidate_sha256"] for r in on["evaluations"] if r["phase"] == "initialization"])
        check(case + ":identical_base_diagnostics_and_order", off["reconstruction_attempts"] == [
            d for d in on["reconstruction_attempts"] if d["extra_resource_edge"] is None])
        check(case + ":initial_energy_exactly_equal", off["initial_safe_snapshot"]["energy"] == on["initial_safe_snapshot"]["energy"])
    check("distinct_call_root_tokens", len(set(tokens)) == 4)
    check("no_retries_or_missing_slots", len(read(execution / "batch_return.json")["consumed_method_slots"]) == 4
          and read(execution / "batch_return.json")["error"] is None)
    check("all_504_frozen_sources_dependencies_and_archives_unchanged", True)
    artifact_hashes = {p.relative_to(HERE).as_posix(): sha(p) for p in sorted(execution.rglob("*"))
                       if p.is_file() and "source_snapshot" not in p.parts}
    audit = {"created_utc": datetime.now(timezone.utc).isoformat(), "passed": all(c["passed"] for c in checks),
        "checks": checks, "check_count": len(checks), "complete_safe_receipts_read_only_audited": receipt_count,
        "new_HEFT_or_thermal_calls_in_this_audit": 0, "frozen_sources": len(plan["source_sha256"]),
        "records": records, "artifact_sha256": artifact_hashes}
    save(HERE / "audit.json", audit)
    print(json.dumps({"passed": audit["passed"], "checks": len(checks), "audited_complete_receipts": receipt_count,
                      "records": [{"slot": r["slot"]["id"], "total_saving_J": float(F(r["strict_total_saving_lower_J"])),
                        "components_saved_J": {k: float(F(v[0])) for k, v in r["component_savings_J"].items()}} for r in records]}))
    if not audit["passed"]:
        raise AssertionError([c for c in checks if not c["passed"]])


if __name__ == "__main__":
    main()
