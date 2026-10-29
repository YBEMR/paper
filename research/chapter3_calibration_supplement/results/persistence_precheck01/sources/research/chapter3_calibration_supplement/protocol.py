"""Immutable preparation and archive bindings, without creating new workloads."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sys

from research.chapter3_deadline_reference.contract import content_hash
from research.chapter3_workload_calibration.runtime import (
    sha, write_json, read_json, read_gzip)
from research.chapter3_calibration_adjustment.manifest import (
    make_manifest, planned_conditions)
from research.chapter3_calibration_adjustment.run_checks import (
    source_files as adjustment_sources, protected_files as original_protected)

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
ACCEPTED_COMMIT = "83129881d6b720cb3975d65a400b4f77d0321cf1"
INVENTORY_PATH = REPO / "research/chapter3_calibration_adjustment/results/manual_precheck03/supplement_manifest.json"
INVENTORY_SHA = "45b11ebe43b40f5b981bbaaa2c3c5a236bf8d2258657f20799f07a1d269eedfc"
LIMITS = {"conditions": 28, "family_timetables": 84, "condition_seconds": 60,
          "batch_seconds": 1800, "finalization_reserve_seconds": 10, "retries": 0}
SCOPE = "SUPPLEMENT_28_TIME_REFERENCES_ONLY"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sources():
    result = adjustment_sources()
    result.update({p.relative_to(REPO).as_posix(): sha(p) for p in sorted(PACKAGE.glob("*.py"))})
    return result


def protected():
    result = original_protected()
    package = PACKAGE.parent / "chapter3_calibration_adjustment"
    files = list(package.glob("*.py")) + [package / "README.md"]
    # Do not enter inaccessible, discarded scratch directories.
    for name in ("manual_precheck01", "manual_precheck02", "manual_precheck03"):
        run = package / "results" / name
        files += [p for p in run.iterdir() if p.is_file()]
        files += list((run / "sources").rglob("*"))
    result.update({p.relative_to(REPO).as_posix(): sha(p) for p in files if p.is_file()})
    return result


def result_path(value, *, fresh=False):
    path = Path(value).resolve()
    allowed = (PACKAGE / "results").resolve()
    require(path != allowed and path.is_relative_to(allowed), "RESULTS_CHILD_REQUIRED")
    if fresh:
        require(not path.exists(), "OUTPUT_ALREADY_EXISTS")
    return path


def inventory():
    require(sha(INVENTORY_PATH) == INVENTORY_SHA, "ACCEPTED_INVENTORY_DRIFT")
    value = read_json(INVENTORY_PATH)
    require(value == make_manifest(REPO), "ORIGINAL_ARCHIVE_DRIFT")
    require(value["calls"] == planned_conditions(), "CALL_LIST_DRIFT")
    return value


def build_plan(inv, source_map):
    plan = {
        "schema_version": "supplement-protocol-v1", "scope": SCOPE,
        "status": "FROZEN_PROPOSAL_AWAITING_USER_APPROVAL",
        "execution_authorized": False, "accepted_implementation_commit": ACCEPTED_COMMIT,
        "inventory_sha256": INVENTORY_SHA, "inventory_content_hash": inv["manifest_hash"],
        "source_files": source_map, "limits": deepcopy(LIMITS),
        "calls": deepcopy(inv["calls"]), "betas": ["1", "1.3", "1.6", "2"],
        "formal_beta": None, "new_root_sampling": False,
        "reference_mapping": "inherit_original_parent_not_reoptimize",
        "window_policy": "group_inherited_deadlines_ceil_5ms",
        "comparison_policy": "read_original_archives_only_do_not_reschedule",
        "stop_rules": {"deadline_miss": "RECORD_CONTINUE",
                       "input_identity_construction_or_structural_error": "STOP_NO_RETRY",
                       "timeout_or_late_receipt": "STOP_NO_RETRY",
                       "source_or_archive_drift": "STOP_NO_RETRY",
                       "unstarted": "NOT_RUN_NOT_INFEASIBLE"},
        "scientific_questions": [
            "S4 repeated diamonds: reference timeliness and slack at four betas, compared with original anchor/serial/layered.",
            "S7 staggered vs synchronous: paired reference timeliness, response/slack changes, keeping original relative deadlines."],
        "interpretation": "Descriptive reference diagnostics; no formal beta selection, feasibility proof, energy or heat result.",
        "excluded": ["MILP", "HEFT", "SA", "thermal integration", "formal 50 roots", "paused experiments"],
    }
    plan["plan_hash"] = content_hash(plan)
    return plan


def approval_template(plan_sha):
    return {"schema_version": "supplement-user-approval-v1", "approved": False,
            "scope": SCOPE, "plan_sha256": plan_sha, "limits": deepcopy(LIMITS),
            "user_authorization": "", "single_use": True}


def validate_approval(value, plan_sha):
    expected_keys = set(approval_template(plan_sha))
    require(isinstance(value, dict) and set(value) == expected_keys, "APPROVAL_SCHEMA")
    require(value["approved"] is True and value["single_use"] is True, "SEPARATE_USER_APPROVAL_REQUIRED")
    require(value["scope"] == SCOPE and value["plan_sha256"] == plan_sha and
            value["limits"] == LIMITS, "APPROVAL_SCOPE_HASH_OR_BUDGET_MISMATCH")
    require(isinstance(value["user_authorization"], str) and
            value["user_authorization"].strip(), "USER_AUTHORIZATION_RECORD_REQUIRED")
    return True


def freeze(output, checks_path):
    checks_path = Path(checks_path).resolve()
    checks = read_json(checks_path)
    source_map = sources()
    require(checks.get("state") == "PASS" and checks.get("source_files") == source_map,
            "CURRENT_PURE_PRECHECK_REQUIRED")
    require(all(checks.get(k) == 0 for k in
                ("supplement_conditions_executed", "formal_algorithm_calls", "thermal_integrations")),
            "PRECHECK_SCOPE")
    inv = inventory()
    plan = build_plan(inv, source_map)
    out = result_path(output, fresh=True)
    out.mkdir(parents=True)
    write_json(out / "plan.json", plan)
    shutil.copyfile(INVENTORY_PATH, out / "inventory.json")
    for rel in source_map:
        target = out / "sources" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    write_json(out / "source_manifest.json", source_map)
    write_json(out / "approval_template.json", approval_template(sha(out / "plan.json")))
    write_json(out / "freeze.json", {
        "state": "FROZEN_NOT_AUTHORIZED", "created_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha(out / "plan.json"), "inventory_sha256": sha(out / "inventory.json"),
        "source_manifest_sha256": sha(out / "source_manifest.json"),
        "precheck_path": str(checks_path), "precheck_sha256": sha(checks_path),
        "protected_files": protected(), "python": sys.version,
        "python_executable": sys.executable, "python_executable_sha256": sha(sys.executable),
        "supplement_conditions_executed": 0, "execution_authorized": False})
    check_frozen(out, full_archive_check=True)
    return {"state": "FROZEN_NOT_AUTHORIZED", "directory": str(out),
            "plan_sha256": sha(out / "plan.json"), "limits": LIMITS}


def check_frozen(freeze_dir, *, full_archive_check=False):
    freeze_dir = result_path(freeze_dir)
    record = read_json(freeze_dir / "freeze.json")
    for name, key in (("plan.json", "plan_sha256"), ("inventory.json", "inventory_sha256"),
                      ("source_manifest.json", "source_manifest_sha256")):
        require(sha(freeze_dir / name) == record[key], "FROZEN_FILE_DRIFT:" + name)
    plan, inv = read_json(freeze_dir / "plan.json"), read_json(freeze_dir / "inventory.json")
    source_map = read_json(freeze_dir / "source_manifest.json")
    require(source_map == sources(), "FROZEN_SOURCE_DRIFT")
    for rel, digest in source_map.items():
        require(sha(freeze_dir / "sources" / rel) == digest, "SOURCE_SNAPSHOT_DRIFT:" + rel)
    require(plan == build_plan(inv, source_map), "PLAN_CONTENT_DRIFT")
    require(inv["calls"] == planned_conditions() and sha(INVENTORY_PATH) == INVENTORY_SHA and
            sha(freeze_dir / "inventory.json") == INVENTORY_SHA, "INVENTORY_DRIFT")
    require(sys.version == record["python"] and sha(sys.executable) == record["python_executable_sha256"],
            "PYTHON_IDENTITY_DRIFT")
    require(sha(record["precheck_path"]) == record["precheck_sha256"], "PRECHECK_DRIFT")
    if full_archive_check:
        require(inv == inventory(), "ARCHIVE_DRIFT")
        require(protected() == record["protected_files"], "PROTECTED_SOURCE_OR_ARCHIVE_DRIFT")
    return plan, inv, record


def load_evidence(inv, condition_id):
    """Read an old immutable result. Never generate or reschedule its workload."""
    ref = inv["archive_references"][condition_id]
    for metadata in ref["files"].values():
        path = (REPO / metadata["path"]).resolve()
        require(path.is_relative_to(REPO) and sha(path) == metadata["sha256"], "ARCHIVE_PAYLOAD_DRIFT")
    evidence = read_gzip(REPO / ref["files"]["evidence"]["path"])
    workload = read_gzip(REPO / ref["files"]["workload"]["path"])
    require(evidence["workload"] == workload and workload["bundle_hash"] == ref["bundle_hash"] and
            workload["contract_hash"] == ref["contract_hash"], "ARCHIVE_WORKLOAD_BINDING")
    require(evidence["call"] == ref["condition"], "ARCHIVE_CALL_BINDING")
    return evidence
