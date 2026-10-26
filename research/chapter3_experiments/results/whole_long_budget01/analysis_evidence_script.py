"""Static MAT/archived JSON identity audit; never construct or evaluate a model."""
from __future__ import annotations

import csv
import gc
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.io import loadmat, whosmat


HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
OLD = RESULTS / "p0_execution01/calls/base__R1/whole_milp"
NEW = HERE / "method"
ALLOWED_MAT_DIFFERENCES = {"remaining_s"}


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def strictly_equal(left, right):
    if sparse.issparse(left) or sparse.issparse(right):
        if not sparse.issparse(left) or not sparse.issparse(right):
            return False
        return (left.shape == right.shape and left.dtype == right.dtype
                and np.array_equal(left.indptr, right.indptr)
                and np.array_equal(left.indices, right.indices)
                and np.array_equal(left.data, right.data))
    if hasattr(left, "_fieldnames") or hasattr(right, "_fieldnames"):
        return (getattr(left, "_fieldnames", None) == getattr(right, "_fieldnames", None)
                and all(strictly_equal(getattr(left, name), getattr(right, name))
                        for name in left._fieldnames))
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        if not isinstance(left, np.ndarray) or not isinstance(right, np.ndarray):
            return False
        if left.shape != right.shape or left.dtype != right.dtype:
            return False
        if left.dtype == object:
            return all(strictly_equal(a, b) for a, b in zip(left.flat, right.flat))
        return bool(np.array_equal(left, right))
    return type(left) is type(right) and left == right


def describe(value):
    result = {"shape": list(value.shape), "dtype": str(value.dtype)}
    if sparse.issparse(value):
        result.update(format=value.format, nnz=int(value.nnz),
                      data_sha256=hashlib.sha256(value.data.tobytes()).hexdigest(),
                      indices_sha256=hashlib.sha256(value.indices.tobytes()).hexdigest(),
                      indptr_sha256=hashlib.sha256(value.indptr.tobytes()).hexdigest())
    elif value.dtype != object:
        result["array_bytes_sha256"] = hashlib.sha256(value.tobytes()).hexdigest()
        if value.size <= 3:
            result["values"] = value.tolist()
    return result


def main():
    old_mat = OLD / "matlab/request_000001.mat"
    new_mat = NEW / "matlab/request_000001.mat"
    old_keys = {name: {"shape": list(shape), "matlab_type": kind}
                for name, shape, kind in whosmat(old_mat)}
    new_keys = {name: {"shape": list(shape), "matlab_type": kind}
                for name, shape, kind in whosmat(new_mat)}
    rows = []
    for name in sorted(old_keys.keys() | new_keys.keys()):
        row = {"key": name, "present_in_old": name in old_keys,
               "present_in_new": name in new_keys,
               "difference_allowed": name in ALLOWED_MAT_DIFFERENCES}
        if name in old_keys and name in new_keys:
            a = loadmat(old_mat, variable_names=[name], struct_as_record=False)[name]
            b = loadmat(new_mat, variable_names=[name], struct_as_record=False)[name]
            row.update(old=describe(a), new=describe(b), strictly_equal=bool(strictly_equal(a, b)))
            del a, b
            gc.collect()
        else:
            row["strictly_equal"] = False
        rows.append(row)

    old_result = read_json(OLD / "result.json")
    new_initial = read_json(NEW / "initial_receipt_checkpoint.json")["initialisation"]
    old_initial = old_result["initialisation"]
    old_candidate = old_initial["witness"]["candidate"]
    new_candidate = new_initial["witness"]["candidate"]
    old_input = read_json(OLD / "input_instance.json")
    declaration = read_json(HERE / "declaration.json")
    declared_new_input_hash = declaration["input_declaration"]["input_sha256"]
    old_initial_energy = old_initial["witness"]["evaluation"]["weighted_energy_J"]
    new_initial_energy = new_initial["witness"]["evaluation"]["weighted_energy_J"]
    old_native_response = read_json(OLD / "matlab/request_000001.response.json")
    initial_equality = {
        "old_candidate_sha256": canonical_hash(old_candidate),
        "new_candidate_sha256": canonical_hash(new_candidate),
        "candidates_identical": old_candidate == new_candidate,
        "old_input_canonical_sha256": canonical_hash(old_input),
        "new_input_sha256_from_frozen_declaration": declared_new_input_hash,
        "input_identity_matches_declaration": canonical_hash(old_input) == declared_new_input_hash,
        "new_input_check_scope": "frozen declaration plus exact original numerical payload; final method result not yet required",
        "old_weighted_energy_J": old_initial_energy,
        "new_weighted_energy_J": new_initial_energy,
        "complete_initial_energy_identical": old_initial_energy == new_initial_energy,
        "old_initial_completed_at_s": old_initial["completed_at_s"],
        "new_initial_completed_at_s": new_initial["completed_at_s"],
        "old_numerical_admission": old_initial["completion"]["numerical_acceptance"],
        "new_numerical_admission": new_initial["completion"]["numerical_acceptance"],
        "source_initial_checkpoint_old": str(OLD / "initial_receipt_checkpoint.json"),
        "source_initial_checkpoint_new": str(NEW / "initial_receipt_checkpoint.json"),
    }
    with (RESULTS / "p0_resume01/analysis01/results40.csv").open(encoding="utf-8-sig", newline="") as stream:
        history = [{k: row.get(k) for k in ["method", "safe_U_exact", "method_root_s", "return_inclusive_s",
                                          "matlab_startup_s", "first_SAFE_s", "first_strict_improvement_s",
                                          "phase1_U_J", "phase2_U_J"]}
                   for row in csv.DictReader(stream)
                   if row["problem_id"] == "base__R1" and row["method"] in {"whole_milp", "anchor_linked4", "heft"}]
    passed = (old_keys == new_keys
              and all(row["strictly_equal"] or row["difference_allowed"] for row in rows)
              and initial_equality["candidates_identical"]
              and initial_equality["input_identity_matches_declaration"]
              and initial_equality["complete_initial_energy_identical"])
    output = {
        "protocol": "K187-static-original-vs-long-MAT-identity-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "read existing MAT arrays and JSON only; no optimization, model build, thermal integration, or candidate evaluation",
        "passed": passed,
        "allowed_mat_differences": {"remaining_s": "300-second versus 3600-second root budget; mathematical coefficients and initial point must remain exactly identical"},
        "key_inventory_identical": old_keys == new_keys,
        "old_mat": {"path": str(old_mat), "bytes": old_mat.stat().st_size, "sha256": file_hash(old_mat), "keys": old_keys},
        "new_mat": {"path": str(new_mat), "bytes": new_mat.stat().st_size, "sha256": file_hash(new_mat), "keys": new_keys},
        "comparisons": rows,
        "initial_and_input_identity": initial_equality,
        "old_model_summary": old_result["model_summary"],
        "old_timing": old_result["timing"],
        "old_diagnostic": old_result["diagnostic"],
        "old_native_options": old_native_response["options"],
        "old_native_response_scope": "late response only; not new budget-valid evidence",
        "old_independent_bound": read_json(OLD / "independent_bounds.json"),
        "historical_P0_R1_comparison": history,
        "budget_interpretation": "new whole-MILP run has 3600 seconds, old whole/C/HEFT had a 300-second ceiling; energy comparison is descriptive, not equal-budget superiority",
        "scientific_calls_created_by_this_audit": 0,
    }
    (HERE / "readonly_matrix_identity.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "keys": len(rows),
                      "different_keys": [row["key"] for row in rows if not row["strictly_equal"]],
                      "initial_candidate_equal": initial_equality["candidates_identical"],
                      "input_identity_equal": initial_equality["input_identity_matches_declaration"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
