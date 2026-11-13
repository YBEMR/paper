"""Read-only bindings for a proposed 28-condition supplement; no execution API."""

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

from research.chapter3_deadline_reference.contract import content_hash


SOURCE_COMMIT = "383babe9b0d8c61fd59dfbe00a14cc2427f61712"
CALIBRATION = "research/chapter3_workload_calibration/results/calibration01"
FROZEN = "research/chapter3_workload_calibration/results/frozen_calibration01"
PINS = {
    CALIBRATION + "/batch_result.json": "8d40f43624ee1c8fd0d6a84db6ad593a4feeb7aa0dc43af8793f48ed53b8761d",
    FROZEN + "/manifest.json": "9c5f22f0d9b861c56ea7cd77e3beb1e1ee0d642c11a0886d9fe2a3cae701b340",
    FROZEN + "/source_manifest.json": "f9e9f004251b86211282c5472a5e4fb60c50252bef815b839331fecf4dd02da8",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def planned_conditions():
    """Identity list only. Does not construct any workload or timetable."""
    result = []
    for number in range(9, 25):
        root = f"C{number:02d}"
        scale = 24 if number <= 16 else 96
        result.append({"condition_id": root + "__S4_branch_multi_v1",
                       "root_id": root, "scale": scale, "axis": "S4",
                       "rule": "branch_multi_v1", "parent_id": f"{root}__base_{scale}",
                       "comparison_ids": [root + "__S4_serial", root + "__S4_layered"]})
    for number in range(2, 25, 2):
        root = f"C{number:02d}"
        scale = 6 if number <= 8 else 24 if number <= 16 else 96
        result.append({"condition_id": root + "__S7_staggered_half_base_H_v1",
                       "root_id": root, "scale": scale, "axis": "S7",
                       "rule": "staggered_half_base_H_v1", "parent_id": f"{root}__base_{scale}",
                       "comparison_ids": [root + "__S7"]})
    return result


def _archive_ref(repo, condition_id, old_calls, batch_rows):
    """Verify immutable bytes and metadata, without time checking or scheduling."""
    _require(condition_id in old_calls and condition_id in batch_rows, "UNKNOWN_ARCHIVE_ID")
    directory = f"{CALIBRATION}/{condition_id}"
    result_path = directory + "/result.json"
    row = batch_rows[condition_id]
    _require(row["state"] == "COMPLETE" and row["result_sha256"] == sha(repo / result_path),
             "ARCHIVE_RESULT_DRIFT:" + condition_id)
    receipt = _read(repo / result_path)
    _require(receipt["state"] == "COMPLETE" and receipt["condition"] == old_calls[condition_id],
             "ARCHIVE_CONDITION_DRIFT")
    _require(receipt["counters"]["formal_method_calls"] == 0 and
             receipt["counters"]["thermal_integrations"] == 0 and
             receipt["thermal_status"] == receipt["energy_status"] == "NOT_EVALUATED" and
             receipt["denied_imports"] == receipt["denied_events"] == [], "ARCHIVE_SCOPE_INVALID")
    paths = {"result": {"path": result_path, "sha256": row["result_sha256"]}}
    for filename, field, key in (("evidence.json.gz", "evidence_sha256", "evidence"),
                                 ("generated_workload.json.gz", "workload_sha256", "workload")):
        path = directory + "/" + filename
        _require(sha(repo / path) == receipt[field], "ARCHIVE_PAYLOAD_DRIFT:" + path)
        paths[key] = {"path": path, "sha256": receipt[field]}
    evidence = json.loads(gzip.decompress((repo / paths["evidence"]["path"]).read_bytes()))
    workload = json.loads(gzip.decompress((repo / paths["workload"]["path"]).read_bytes()))
    _require(evidence["workload"] == workload and evidence["call"] == old_calls[condition_id],
             "ARCHIVE_EVIDENCE_LINK_DRIFT")
    _require(workload["provenance"]["root_id"] == old_calls[condition_id]["root_id"] and
             workload["provenance"]["scale"] == old_calls[condition_id]["scale"], "ARCHIVE_IDENTITY_DRIFT")
    _require(len(workload["time_contract"]["scenarios"]) == 8, "ARCHIVE_SCENE_COUNT")
    return {"condition": deepcopy(old_calls[condition_id]), "files": paths,
            "bundle_hash": workload["bundle_hash"], "contract_hash": workload["contract_hash"],
            "reference_H_timetable_hash": evidence["reference"]["checks"]["H"]["timetable_hash"],
            "deadline_receipt_hashes": {b: d["receipt_hash"] for b, d in evidence["deadlines"].items()}}


def make_manifest(repo):
    """Create a NOT_AUTHORIZED inventory from existing archive bytes only."""
    repo = Path(repo).resolve()
    for rel, digest in PINS.items():
        _require(sha(repo / rel) == digest, "PINNED_ARCHIVE_CHANGED:" + rel)
    original = _read(repo / (FROZEN + "/manifest.json"))
    batch = _read(repo / (CALIBRATION + "/batch_result.json"))
    _require(batch["state"] == "COMPLETE", "BASE_BATCH_NOT_COMPLETE")
    old_calls = {c["condition_id"]: c for c in original["calls"]}
    batch_rows = {r["condition_id"]: r for r in batch["rows"]}
    calls = planned_conditions()
    needed = sorted({name for call in calls for name in [call["parent_id"]] + call["comparison_ids"]})
    references = {name: _archive_ref(repo, name, old_calls, batch_rows) for name in needed}
    result = {
        "schema_version": "calibration-adjustment-manifest-v1",
        "status": "IMPLEMENTATION_AND_MANUAL_TESTS_ONLY",
        "execution_authorized": False,
        "source_commit": SOURCE_COMMIT, "pinned_archives": dict(PINS),
        "parent_namespace": original["configuration"]["namespace"],
        "parent_seed": original["configuration"]["seed"],
        "new_sampling": False, "new_independent_roots": 0,
        "rules": {"S4": "branch_multi_v1", "S7": "staggered_half_base_H_v1",
                  "stagger_fraction": "1/2", "grid_ms": "5",
                  "deadline_rule": "inherit_original_absolute_and_new_same_relative",
                  "mapping_rule": "inherit_parent_reference_mapping",
                  "window_rule": "paired_group_maximum_absolute_deadline_ceil_5ms"},
        "betas": deepcopy(original["configuration"]["betas"]),
        "priority_beta": "1.3", "beta_selected": None,
        "calls": calls, "archive_references": references,
        "proposed_counts": {"conditions": 28, "S4_conditions": 16, "S7_conditions": 12,
                            "existing_roots": 20, "HML_family_timetables": 84,
                            "scene_schedules": 672, "new_mapping_constructions": 0},
        "execution_limits": {"condition_seconds": None, "batch_seconds": None, "retries": 0},
        "consumed": {"supplement_conditions": 0, "supplement_timetables": 0,
                     "formal_algorithm_calls": 0, "thermal_integrations": 0},
        "stop_rules": {"input_or_construction_error": "STOP_SAVE_NO_RETRY",
                       "timeout": "STOP_SAVE_NO_RETRY", "missed_deadline": "RECORD_CONTINUE",
                       "scope_change": "REQUIRE_NEW_AUTHORIZATION"},
    }
    result["manifest_hash"] = content_hash(result)
    return result


def validate_manifest(manifest, repo):
    _require(manifest == make_manifest(repo), "SUPPLEMENT_MANIFEST_DRIFT")
    return True
