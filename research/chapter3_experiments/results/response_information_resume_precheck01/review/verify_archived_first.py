"""Read stored K177 slot1 only: identities and rational receipt accounting.

No planner, schedule validation, thermal evaluator or optimization imports.
"""
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[5]
BASE = REPO / "research/chapter3_experiments/results"
OLD = BASE / "response_information_execution01"
OUT = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def byte_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def run():
    paths = {
        "raw": OLD / "slot_1/planner_public/method/result.json",
        "checkpoint": OLD / "slot_1/planner_public/accepted_checkpoint.json",
        "job": OLD / "slot_1/planner_public/job.json",
        "truth": OLD / "slot_1/controller_private/truth_H.json",
        "contract": OLD / "slot_1/controller_private/static_contract.json",
        "process": OLD / "slot_1/planner_public/process_receipt.json",
        "stderr": OLD / "slot_1/planner_public/stderr.log",
        "terminal": OLD / "terminal.json",
        "supervisor": BASE / "response_information_execution01_supervision/terminal.json",
        "declaration": BASE / "response_information_execution_precheck01/execution_declaration.json",
    }
    records = {k: load(v) for k, v in paths.items() if k != "stderr"}
    raw, checkpoint = records["raw"], records["checkpoint"]
    packet = records["job"]["packet"]
    truth = records["truth"]
    accepted = [r for r in raw["evaluations"] if r.get("accepted_safe") is True]
    best = min(accepted, key=lambda r: F(r["evaluation"]["safe_upper_bound_J"]))
    checks = []

    def check(name, value, detail=None):
        checks.append({"name": name, "passed": bool(value), "detail": detail})

    check("original_core_complete", raw["state"] == "SAFE" and raw["reason"] == "DECLARED_SEARCH_COMPLETED")
    check("same_original_heft", raw["method"] == "heft" and raw["seed"] is None)
    check("slot1_H_identity", packet["view"] == "H" and packet["problem_id"] == "base__R1"
          and raw["problem_id"] == "base__R1")
    check("H_public_equals_sealed_truth", packet["planner"] == truth)
    check("original_root_complete_within_120", raw["timing"]["limit_s"] == 120
          and 0 <= raw["timing"]["method_elapsed_s"] < 120, raw["timing"])
    check("original_input_hash", raw["input_sha256"] == canonical(packet["planner"]["instance"]))
    check("44_candidates_complete", len(accepted) == len(raw["evaluations"]) == raw["candidate_count"]
          == raw["thermal_evaluations"] == 44)
    check("all_44_receipts_timely", all(0 <= r["evaluation"]["completed_at_elapsed_s"] <= r["returned_at_s"] < 120 for r in accepted))
    check("original_final_is_recorder_best", raw["safe_candidate"] == best["candidate"] and raw["evaluation"] == best["evaluation"]
          and F(raw["safe_upper_bound_J"]) == F(best["evaluation"]["safe_upper_bound_J"]))
    check("checkpoint_best_matches_raw", checkpoint["best"]["candidate"] == raw["safe_candidate"]
          and checkpoint["best"]["evaluation"] == raw["evaluation"])
    check("all_candidate_receipts_bound", all(r["candidate_sha256"] == canonical(r["candidate"])
          and r["evaluation"]["evidence_identity"] == {"input_sha256": raw["input_sha256"],
               "candidate_sha256": canonical(r["candidate"])} for r in accepted))
    check("failure_is_only_export_contract", "EXTERNAL_POWER_ACCOUNTING" in paths["stderr"].read_text(encoding="utf-8")
          and records["process"]["returncode"] == 3 and records["process"]["watchdog_killed"] is False)
    ledger = records["supervisor"]["controller_ledger"]
    check("only_first_plan_consumed", ledger["plan_calls_consumed"] == 1 and ledger["audit_calls_consumed"] == 0
          and ledger["reserved_scientific_budget_s"] == 120, ledger)
    check("remaining_unstarted", all(not (OLD / f"slot_{k}").exists() for k in (2, 3, 4))
          and not (OLD / "slot_1/H_audit_private").exists())
    check("no_H_audit_feedback_formed", not (OLD / "slot_1/controller_private/frozen_candidate.json").exists()
          and not (OLD / "slot_1/H_audit_private").exists())
    ext = F(truth["instance"]["platform"]["external_common_power_W"]) * F(truth["instance"]["window_ms"])/1000
    enclosure_ok, segment_ok = [], []
    for r in accepted:
        for sid, scene in r["evaluation"]["scenes"].items():
            lo, hi = map(F, scene["energy_components_J"]["external_common"])
            enclosure_ok.append(lo <= ext <= hi)
            segments = r["evaluation"]["legality"]["scenes"][sid]["segments"]
            segment_ok.append(sum((F(s["external_common_power_W"]) * F(s["duration_ms"])/1000 for s in segments), F(0)) == ext)
    check("external_outward_enclosures_correct", all(enclosure_ok) and all(segment_ok), {"scenes": len(enclosure_ok), "exact_J": str(ext)})
    facts = {
        "review_type": "INTERNAL_INDEPENDENT_READ_ONLY_NOT_EXTERNAL_APPROVAL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Stored JSON and exact rational arithmetic only; no new search, schedule validation or thermal integration",
        "artifact_sha256": {k: {"path": v.relative_to(REPO).as_posix(), "sha256": byte_sha(v)} for k, v in paths.items()},
        "candidate_sha256": canonical(raw["safe_candidate"]),
        "input_sha256": raw["input_sha256"],
        "safe_U_J_as_recorded_not_postvalidated": raw["safe_upper_bound_J"],
        "checks": checks, "passed": all(c["passed"] for c in checks),
        "continuation_conditions": [
            "Pure replay of fixed thin export only; never rerun original slot1 planner or reevaluate 44 accepted records",
            "Use exactly original final recorder-best candidate; no replacement, repair, added candidate or second selection",
            "Preserve original 120-second consumed plan budget; slot1 post unique <=60 seconds",
            "New slots remain original order R1/R, R2/R, R2/H, each <=120 plan and unique <=60 post; combined old/new <=4 plans/4 posts/720 seconds reserved",
            "True-H post output has no path into R planner; current HEFT, physical model, tolerances and scientific response scopes unchanged",
            "Retain old exception/STOP artifacts and explicitly label this as human-authorized continuation after pure contract repair",
        ],
        "conclusion": "PASS_CONDITIONAL_READONLY_EXPORT_REPLAY_THEN_ORIGINAL_UNCONSUMED_SLOTS" if all(c["passed"] for c in checks) else "BLOCK",
    }
    target = OUT / "archived_first_review.json"
    with target.open("x", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2); f.write("\n")
    print(json.dumps({"passed": facts["passed"], "checks": len(checks), "candidate_sha256": facts["candidate_sha256"],
                      "failed": [c["name"] for c in checks if not c["passed"]]}, ensure_ascii=False))


if __name__ == "__main__":
    run()
