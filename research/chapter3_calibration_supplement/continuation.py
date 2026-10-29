"""Freeze exactly the 25 unstarted conditions. No workloads are built here."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

from research.chapter3_deadline_reference.contract import content_hash
from . import protocol as p
from .persistence import write_once, read_terminal_record

SCHEMA = "supplement-remaining25-v1"
SCOPE = "SUPPLEMENT_REMAINING_25_TIME_REFERENCES_ONLY"
LIMITS = {**p.LIMITS, "conditions": 25, "family_timetables": 75, "batch_seconds": 1620}
PRIOR = p.PACKAGE / "results/supplement_execution01"
PRIOR_FREEZE = p.PACKAGE / "results/frozen_supplement01"
HISTORY = p.PACKAGE / "results/persistence_precheck02/historical_supplement_after.json"
HISTORY_SHA = "79e2d69bf335a27fb931cc9c5a134713aa56f899ea7b8ac63fdafa8fcba94e44"
PRIOR_BATCH_SHA = "eef85c57d4dafd3d651fcfd4eba7a39b793ca0a3bbe60686e717ed96c983561e"
CONSUMPTION = "research/chapter3_calibration_supplement/results/continuation_consumption/from_818b0e37_remaining25.json"
RETAINED = [f"C{i:02d}__S4_branch_multi_v1" for i in (9, 10, 11)]


def partition_calls(calls, rows, occupied):
    """Accept only the pinned completed prefix plus genuinely unstarted suffix."""
    ids = [c["condition_id"] for c in calls]
    p.require(len(ids) == 28 and len(set(ids)) == 28, "ORIGINAL_28_REQUIRED")
    p.require([r["condition_id"] for r in rows] == ids, "ORIGINAL_ROW_ORDER_OR_COVERAGE")
    p.require([r["condition_id"] for r in rows if r["state"] == "COMPLETE"] == RETAINED,
              "EXACT_RETAINED_THREE_REQUIRED")
    p.require(all(r["state"] == ("COMPLETE" if i < 3 else "NOT_RUN") for i, r in enumerate(rows)),
              "ONLY_NEVER_STARTED_SUFFIX_ALLOWED")
    p.require(not (set(ids[3:]) & set(occupied)), "UNSTARTED_CONDITION_ALREADY_HAS_DIRECTORY")
    return deepcopy(calls[3:])


def prior_evidence():
    p.require(p.sha(HISTORY) == HISTORY_SHA, "PRIOR_HISTORY_MANIFEST_DRIFT")
    history = p.read_json(HISTORY)
    for rel, digest in history.items():
        p.require(p.sha(p.REPO / rel) == digest, "PRIOR_ARCHIVE_DRIFT:" + rel)
    p.require(p.sha(PRIOR / "batch_result.json") == PRIOR_BATCH_SHA, "PRIOR_BATCH_DRIFT")
    p.require(not (PRIOR / "terminal_failure.json").exists(), "UNEXPECTED_PRIOR_TERMINAL_MARKER")
    batch = p.read_json(PRIOR / "batch_result.json")
    plan = p.read_json(PRIOR_FREEZE / "plan.json")
    p.require(plan["calls"] == p.planned_conditions(), "ORIGINAL_INVENTORY_CHANGED")
    p.require(batch["state"] == "STOPPED_EXCEPTION" and batch["completed_conditions"] == 3
              and batch["consumed_conditions"] == 3, "PRIOR_BATCH_NOT_EXPECTED_STOP")
    remaining = partition_calls(plan["calls"], batch["rows"],
                                [c["condition_id"] for c in plan["calls"] if (PRIOR / c["condition_id"]).exists()])
    from .runtime import accept_receipt
    for call, row in zip(plan["calls"][:3], batch["rows"][:3]):
        directory = PRIOR / call["condition_id"]
        p.require(p.sha(directory / "result.json") == row["result_sha256"], "RETAINED_RESULT_HASH")
        receipt, summary = accept_receipt(directory, call, p.read_json(directory / "call_claim.json"), plan["source_files"])
        p.require(receipt["elapsed_s"] <= row["elapsed_s"] <= 60 and row["summary"] == summary,
                  "RETAINED_TIMING_OR_SUMMARY")
    binding = {
        "prior_run": PRIOR.relative_to(p.REPO).as_posix(),
        "prior_batch_sha256": PRIOR_BATCH_SHA, "prior_plan_sha256": p.sha(PRIOR_FREEZE / "plan.json"),
        "prior_approval_sha256": p.sha(PRIOR / "approval.json"),
        "prior_claim_sha256": p.sha(PRIOR_FREEZE / "execution_claim.json"),
        "history_manifest_sha256": HISTORY_SHA, "retained_conditions": RETAINED,
        "retained_result_sha256": {r["condition_id"]: r["result_sha256"] for r in batch["rows"][:3]},
        "prior_elapsed_s": batch["elapsed_s"],
        "selection": "original_NOT_RUN_only_no_rescheduling_of_completed_conditions"
    }
    return plan, batch, remaining, binding, history


def build_plan(inv, source_map, *, prior=None):
    old_plan, batch, calls, binding, history = prior or prior_evidence()
    plan = p.build_plan(inv, source_map)
    plan.pop("plan_hash")
    plan.update(schema_version=SCHEMA, scope=SCOPE, limits=deepcopy(LIMITS), calls=calls,
                prior_execution=binding, consumption_claim_path=CONSUMPTION,
                approved_repair_commit="6ecaf9429bc921d50889d1695078a445e5a2a2e2",
                combined_reporting="old3_plus_new25_with_separate_execution_accounts")
    plan["plan_hash"] = content_hash(plan)
    return plan


def freeze(output, checks_path):
    checks_path = Path(checks_path).resolve()
    checks, source_map = p.read_json(checks_path), p.sources()
    p.require(checks.get("state") == "PASS" and checks.get("source_files") == source_map,
              "CURRENT_PURE_PRECHECK_REQUIRED")
    p.require(all(checks.get(k) == 0 for k in ("supplement_conditions_executed", "formal_algorithm_calls", "thermal_integrations")),
              "PRECHECK_SCOPE")
    inv = p.inventory()
    plan = build_plan(inv, source_map)
    out = p.result_path(output, fresh=True)
    out.mkdir(parents=True)
    write_once(out / "plan.json", plan)
    shutil.copyfile(p.INVENTORY_PATH, out / "inventory.json")
    shutil.copyfile(HISTORY, out / "prior_history.json")
    for rel in source_map:
        target = out / "sources" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p.REPO / rel, target)
    write_once(out / "source_manifest.json", source_map)
    write_once(out / "approval_template.json", p.approval_template(p.sha(out / "plan.json"), plan=plan))
    write_once(out / "freeze.json", {
        "protocol_kind": SCHEMA, "state": "FROZEN_NOT_AUTHORIZED", "created_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": p.sha(out / "plan.json"), "inventory_sha256": p.sha(out / "inventory.json"),
        "source_manifest_sha256": p.sha(out / "source_manifest.json"), "prior_history_sha256": HISTORY_SHA,
        "precheck_path": str(checks_path), "precheck_sha256": p.sha(checks_path),
        "protected_files": p.protected(), "python": sys.version,
        "python_executable_sha256": p.sha(sys.executable),
        "supplement_conditions_executed": 0, "execution_authorized": False})
    check_frozen(out, full_archive_check=True)
    return {"state": "FROZEN_NOT_AUTHORIZED", "conditions": 25, "limits": LIMITS,
            "plan_sha256": p.sha(out / "plan.json"), "directory": str(out)}


def check_frozen(directory, *, full_archive_check=False):
    directory = p.result_path(directory)
    record = p.read_json(directory / "freeze.json")
    p.require(record.get("protocol_kind") == SCHEMA, "CONTINUATION_SCHEMA")
    for name, key in (("plan.json", "plan_sha256"), ("inventory.json", "inventory_sha256"),
                      ("source_manifest.json", "source_manifest_sha256"), ("prior_history.json", "prior_history_sha256")):
        p.require(p.sha(directory / name) == record[key], "FROZEN_FILE_DRIFT:" + name)
    p.require(record["prior_history_sha256"] == HISTORY_SHA, "PRIOR_HISTORY_BINDING")
    plan, inv = p.read_json(directory / "plan.json"), p.read_json(directory / "inventory.json")
    source_map = p.read_json(directory / "source_manifest.json")
    p.require(source_map == p.sources(), "FROZEN_SOURCE_DRIFT")
    for rel, digest in source_map.items():
        p.require(p.sha(directory / "sources" / rel) == digest, "SOURCE_SNAPSHOT_DRIFT:" + rel)
    p.require(plan == build_plan(inv, source_map), "CONTINUATION_CONTENT_DRIFT")
    p.require(inv["calls"] == p.planned_conditions() and p.sha(directory / "inventory.json") == p.INVENTORY_SHA,
              "ORIGINAL_INVENTORY_DRIFT")
    p.require(sys.version == record["python"] and p.sha(sys.executable) == record["python_executable_sha256"],
              "PYTHON_IDENTITY_DRIFT")
    p.require(p.sha(record["precheck_path"]) == record["precheck_sha256"], "PRECHECK_DRIFT")
    if full_archive_check:
        p.require(inv == p.inventory() and p.protected() == record["protected_files"], "PROTECTED_ARCHIVE_DRIFT")
    return plan, inv, record


def combine_rows(old_calls, old_batch, new_calls, new_batch):
    """Pure descriptive union. Preserve distinct executions and missing outcomes."""
    p.require(new_calls == old_calls[3:], "COMBINED_NEW_DOMAIN")
    p.require([r["condition_id"] for r in new_batch["rows"]] == [c["condition_id"] for c in new_calls],
              "COMBINED_NEW_COVERAGE_OR_DUPLICATE")
    from .analysis import aggregate_summaries
    rows = deepcopy(old_batch["rows"][:3]) + deepcopy(new_batch["rows"])
    combined = aggregate_summaries(old_calls, rows)
    combined["execution_accounts"] = {
        "original": {k: old_batch[k] for k in ("state", "elapsed_s", "consumed_conditions", "completed_conditions")},
        "continuation": {k: new_batch[k] for k in ("state", "elapsed_s", "consumed_conditions", "completed_conditions")}}
    combined["condition_origin"] = {c["condition_id"]: "original" if i < 3 else "continuation"
                                    for i, c in enumerate(old_calls)}
    combined["single_execution_claim"] = False
    return combined


def combined_summary(freeze_dir, output, *, exit_code):
    """Read actual completed receipts only; no schedule construction or heat work."""
    plan, inv, record = check_frozen(freeze_dir, full_archive_check=True)
    out = p.result_path(output)
    batch = read_terminal_record(out, exit_code=exit_code)
    p.require(batch["plan_sha256"] == record["plan_sha256"] and p.sha(out / "plan.json") == record["plan_sha256"],
              "COMBINED_PLAN_BINDING")
    p.validate_approval(p.read_json(out / "approval.json"), record["plan_sha256"], plan=plan)
    from .runtime import accept_receipt
    claim = p.read_json(p.result_path(freeze_dir) / "execution_claim.json")
    p.require(claim == p.read_json(p.result_path(plan["consumption_claim_path"])) and
              claim["output"] == str(out) and claim["plan_sha256"] == record["plan_sha256"] and
              claim["approval_sha256"] == p.sha(out / "approval.json"), "COMBINED_CONSUMPTION_BINDING")
    p.require(batch["limits"] == plan["limits"] and batch["planned_conditions"] == 25, "COMBINED_BATCH_LIMITS")
    p.require([r["condition_id"] for r in batch["rows"]] == [c["condition_id"] for c in plan["calls"]],
              "COMBINED_ROW_COVERAGE")
    for call, row in zip(plan["calls"], batch["rows"]):
        if row["state"] == "COMPLETE":
            directory = out / call["condition_id"]
            receipt, summary = accept_receipt(directory, call, p.read_json(directory / "call_claim.json"), plan["source_files"])
            p.require(p.sha(directory / "result.json") == row["result_sha256"] and row["summary"] == summary,
                      "COMBINED_RESULT_BINDING")
            p.require(row["returncode"] == 0 and receipt["elapsed_s"] <= row["elapsed_s"] <= LIMITS["condition_seconds"],
                      "COMBINED_COMPLETION_CLOCK")
    original, old_batch, *_ = prior_evidence()
    return combine_rows(original["calls"], old_batch, plan["calls"], batch)
