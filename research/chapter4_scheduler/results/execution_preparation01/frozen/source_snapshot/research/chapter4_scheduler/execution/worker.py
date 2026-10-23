"""One authorized four-arm method or one independent postcheck; never retry.

The CLI has no simulation switch and no research authorization of its own.
Before backend imports, input expansion or evaluation, load_active must verify
the separate human authorization and already-consumed slot claim. Importing
this module starts no method, native worker or thermal calculation.
"""
import argparse
from copy import deepcopy
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCIENCE = REPO / "research/chapter3_experiments"
for _root in (REPO, SCIENCE):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
from research.chapter4_scheduler.execution import protocol


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def _error(error):
    return {"type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc()}


def _folder(path, slot_id, out):
    expected = Path(path).resolve().parent / "calls" / slot_id
    out = Path(out).resolve()
    if out != expected.resolve() or not (out / "slot.claim.json").is_file():
        raise ValueError("Only the claimed frozen slot directory is permitted")
    return out


def _environment(declaration):
    frozen = declaration["environment"]
    observed = {"python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version, "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")}}
    for name in ("python_executable", "python_version", "platform", "packages"):
        if observed[name] != frozen[name]:
            raise ValueError("Frozen environment changed: " + name)
    matlab = Path(frozen["matlab_executable"]).resolve()
    observed.update(matlab_executable=str(matlab), matlab_executable_sha256=protocol.sha(matlab))
    if observed["matlab_executable_sha256"] != frozen["matlab_executable_sha256"]:
        raise ValueError("Frozen MATLAB executable changed")
    return observed


def _native_evidence(out):
    """Preserve actual bridge files; session preparation alone is not launch."""
    records = {}
    for name in ("session.json", "closed.json", "ready.json"):
        path = out / "method" / "matlab" / name
        if path.is_file():
            try:
                records[name] = {"path": str(path), "sha256": protocol.sha(path),
                                 "raw": protocol.read(path)}
            except Exception as error:
                records[name] = {"path": str(path), "error": repr(error)}
    session = records.get("session.json", {}).get("raw", {})
    ready = records.get("ready.json", {}).get("raw", {})
    pid = session.get("pid") if isinstance(session, dict) else None
    started = ((isinstance(pid, int) and not isinstance(pid, bool) and pid > 0)
               or isinstance(ready, dict) and ready.get("status") == "READY")
    return {"folder": str(out), "native_started": bool(started),
        "closure": records.get("closed.json", {}).get("raw"), "records": records,
        "scope": "actual bridge metadata; closure is checked by the independent admission gate"}


def run_method(declaration_path, slot_id, out):
    started = time.monotonic()
    declaration_path = Path(declaration_path).resolve()
    # Mandatory authorization/claim check before any selected backend import.
    declaration, slot, case = protocol.load_active(declaration_path, slot_id)
    out = _folder(declaration_path, slot_id, out)
    if (slot["method_seconds"] != 300 or declaration["budgets"]["method_s"] != 300
            or any((out / name).exists() for name in (
                "worker_started.json", "worker_identity.json", "worker_return.json",
                "wrapper_raw_result.json", "result.json", "input_instance.json", "method"))):
        raise FileExistsError("Method slot already used or root budget changed; no retry")
    from timing import MethodBudget
    budget = MethodBudget(300)
    budget.start, budget.deadline = started, started + 300
    root = (budget.start, budget.deadline, budget.seconds, budget.clock)
    identity = {"protocol": "K181-method-worker-v1", "slot_id": slot_id,
        "case_id": slot["case_id"], "arm": slot["arm"],
        "declaration_sha256": protocol.sha(declaration_path),
        "root_start_s": root[0], "root_deadline_s": root[1], "root_limit_s": root[2],
        "input_verified": False, "source_verified": False, "environment_verified": False,
        "fresh_input_calls": 0, "not_scientific": False, "scientific_call_started": False,
        "common": deepcopy(case["common"]), "source_sha256": deepcopy(declaration["source_sha256"]),
        "recipe_sha256": protocol.canonical(case["recipes"][slot["arm"]]),
        "budget_identity": None, "native_started": False,
        "input_read_before_root": False, "historical_candidate_or_cache_loaded": False}
    protocol.write_new(out / "worker_started.json", dict(identity, pid=os.getpid(),
        started_utc=protocol.now(), no_retry=True))
    raw = dispatch_record = None
    errors = []
    saved = False
    stopped = None
    try:
        budget.check()
        with budget.phase("worker_source_and_environment_identity"):
            identity["source_verified"] = protocol.verify_files(declaration)
            if not identity["source_verified"]:
                raise ValueError("Frozen sources or protected archives changed")
            identity["environment_observed"] = _environment(declaration)
            identity["environment_verified"] = True
        budget.check()

        def loader(active):
            if active is not budget or identity["fresh_input_calls"]:
                raise ValueError("Fresh input must be loaded once on this root budget")
            identity["fresh_input_calls"] += 1
            with budget.phase("worker_fresh_input_and_identity"):
                from p0_batch.run_p0 import fresh_input
                raw_config, config, instance = fresh_input(slot["case_id"], budget)
                actual = {"raw_config_sha256": protocol.canonical(raw_config),
                    "config_sha256": protocol.canonical(config), "input_sha256": protocol.canonical(instance)}
                identity.update(actual)
                common = case["common"]
                identity["input_verified"] = (actual["config_sha256"] == common["config_sha256"]
                    and actual["input_sha256"] == common["input_sha256"])
                if "raw_config_sha256" in common:
                    identity["input_verified"] &= actual["raw_config_sha256"] == common["raw_config_sha256"]
                if not identity["input_verified"]:
                    raise ValueError("Fresh P0 input or configuration differs from the frozen case")
                protocol.write_new(out / "input_raw_config.json", raw_config)
                protocol.write_new(out / "input_config.json", config)
                protocol.write_new(out / "input_instance.json", instance)
            budget.check()
            return config, instance

        from research.chapter4_scheduler.execution.backends import dispatch
        identity["scientific_call_started"] = True
        dispatch_record = dispatch(slot["arm"], loader, out / "method", budget,
                                   case["recipes"][slot["arm"]])
        raw = dispatch_record["result"]
        stopped = time.monotonic()
        identity.update(not_scientific=dispatch_record["not_scientific"],
            selected_imports_elapsed_s=dispatch_record["selected_imports_elapsed_s"],
            backend_budget_unchanged=dispatch_record["budget_unchanged"])
        if not isinstance(raw, dict):
            raise TypeError("Original method must return its unmodified result object")
        # Preserve original returned evidence before post-return identity checks.
        protocol.write_new(out / "wrapper_raw_result.json", raw)
        protocol.write_new(out / "result.json", raw)
        saved = True
        identity.update(result_sha256=protocol.sha(out / "result.json"),
                        raw_result_sha256=protocol.sha(out / "wrapper_raw_result.json"))
        if not dispatch_record["budget_unchanged"] or (
                budget.start, budget.deadline, budget.seconds, budget.clock) != root:
            raise ValueError("Backend changed the root budget; original raw evidence retained")
        token = deepcopy(getattr(budget, "_scene_adapter_budget_identity", None))
        condition_token = (raw.get("condition") or {}).get("budget_identity")
        aggregate_token = ((raw.get("aggregation") or {}).get("identity") or {}).get("budget")
        for found in (condition_token, aggregate_token):
            if found is not None:
                if token is not None and found != token:
                    raise ValueError("C result does not bind the actual root budget token")
                token = deepcopy(found)
        identity["budget_identity"] = token
        if (slot["arm"] == "C" and token is None
                and (raw.get("safe_candidate") is not None or raw.get("condition") is not None)):
            raise ValueError("Original C did not preserve its actual root budget identity")
    except BaseException as error:
        errors.append(_error(error))
    # Archival only: no new candidate, repair, solver, thermal evaluation or U.
    returned = time.monotonic()
    stopped = returned if stopped is None else stopped
    identity.update(method_returned_monotonic=stopped,
        method_root_elapsed_s=stopped - root[0], source_after_return=protocol.verify_files(declaration))
    identity["source_verified"] = identity["source_verified"] and identity["source_after_return"]
    native = _native_evidence(out)
    identity.update(native_started=native["native_started"], native_evidence=native)
    if not identity["source_verified"]:
        errors.append({"type": "SourceDrift", "message": "Frozen sources drifted during method"})
    protocol.write_new(out / "worker_identity.json", identity)
    record = {"protocol": "K181-method-return-v1", "slot_id": slot_id,
        "arm": slot["arm"], "passed": saved and not errors,
        "not_scientific": identity["not_scientific"], "original_result_saved": saved,
        "scientific_call_started": identity["scientific_call_started"],
        "worker_identity_sha256": protocol.sha(out / "worker_identity.json"),
        "root_start_s": root[0], "root_deadline_s": root[1], "root_limit_s": root[2],
        "method_root_elapsed_s": stopped - root[0], "returned_monotonic": returned,
        "native_evidence": native, "errors": errors,
        "scope": "original method result and identity only; no scientific admission verdict",
        "no_retry": True, "new_post_or_thermal_evidence": False}
    protocol.write_new(out / "worker_return.json", record)
    _emit({"slot_id": slot_id, "worker_returned": record["passed"],
           "original_result_saved": saved, "errors": errors})
    return 0 if record["passed"] else 2


def _interval(values):
    from fractions import Fraction
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("An admitted nonnegative energy interval is required")
    lo, hi = map(Fraction, values)
    if not 0 <= lo <= hi:
        raise ValueError("Invalid admitted energy interval")
    return lo, hi


def run_post(declaration_path, slot_id, out):
    started = time.monotonic()
    declaration_path = Path(declaration_path).resolve()
    declaration, slot, case = protocol.load_active(declaration_path, slot_id)
    out = _folder(declaration_path, slot_id, out)
    if (slot["post_seconds_max"] != 60 or declaration["budgets"]["post_s"] != 60
            or any((out / name).exists() for name in (
                "postcheck.claim.json", "postcheck.json", "post_return.json"))):
        raise FileExistsError("Independent postcheck already used or budget changed")
    from timing import MethodBudget
    budget = MethodBudget(60)
    budget.start, budget.deadline = started, started + 60
    audit = protocol.read(out / "audit.json")
    if audit.get("eligible_for_post") is not True:
        raise ValueError("Only an admitted normal complete SAFE is eligible for postcheck")
    claim = {"protocol": "K181-independent-post-claim-v1", "slot_id": slot_id,
        "arm": slot["arm"], "declaration_sha256": protocol.sha(declaration_path),
        "audit_sha256": protocol.sha(out / "audit.json"), "root_start_s": started,
        "root_deadline_s": started + 60, "root_limit_s": 60,
        "no_retry": True, "new_U": False, "no_search_or_repair": True}
    protocol.write_new(out / "postcheck.claim.json", claim)
    record = dict(claim, protocol="K181-independent-post-return-v1", passed=False,
                  evaluation_calls=0, errors=[], not_scientific=False)
    try:
        budget.check()
        if not protocol.verify_files(declaration):
            raise ValueError("Frozen source or protected archive drift before post")
        raw, result = protocol.read(out / "wrapper_raw_result.json"), protocol.read(out / "result.json")
        instance, config = protocol.read(out / "input_instance.json"), protocol.read(out / "input_config.json")
        candidate = result.get("safe_candidate")
        expected = {"result_sha256": protocol.sha(out / "result.json"),
            "raw_result_sha256": protocol.sha(out / "wrapper_raw_result.json"),
            "input_sha256": protocol.canonical(instance), "config_sha256": protocol.canonical(config),
            "declaration_sha256": protocol.sha(declaration_path)}
        if (raw != result or candidate is None or any(audit.get(k) != v for k, v in expected.items())
                or expected["input_sha256"] != case["common"]["input_sha256"]
                or expected["config_sha256"] != case["common"]["config_sha256"]
                or protocol.canonical(candidate) != audit.get("candidate_sha256")):
            raise ValueError("Postcheck is not bound to the admitted original complete candidate")
        old = _interval(audit.get("admitted_interval"))
        original_u = result.get("safe_upper_bound_J")
        if original_u is None or _interval([original_u, original_u])[0] != old[1]:
            raise ValueError("Original method U differs from the admitted interval")
        from thermal import evaluate_candidate
        from h02_pair_preflight.receipts import safe_receipt
        budget.check()
        record["evaluation_calls"] = 1
        fresh = evaluate_candidate(deepcopy(instance), deepcopy(candidate),
                                   deepcopy(config["accuracy_targets"]), budget)
        # Raw independent receipt, never a replacement search result or U.
        protocol.write_new(out / "postcheck.json", fresh)
        record["evaluation_elapsed_s"] = budget.elapsed
        energy = safe_receipt(instance, candidate, fresh, config["accuracy_targets"], 60)
        new = _interval([energy["lower"], energy["upper"]])
        if (budget.elapsed >= 60 or fresh.get("completed_at_elapsed_s", 60) > budget.elapsed
                or max(old[0], new[0]) > min(old[1], new[1])):
            raise ValueError("Postcheck exceeded its budget or did not reproduce the original energy")
        if (protocol.sha(out / "result.json") != expected["result_sha256"]
                or protocol.sha(out / "wrapper_raw_result.json") != expected["raw_result_sha256"]
                or not protocol.verify_files(declaration)):
            raise ValueError("Original result or frozen source changed during postcheck")
        record.update(passed=True, energy_reproduced=True, original_U_J=original_u,
            admitted_interval=audit["admitted_interval"], post_interval=fresh["weighted_energy_J"],
            candidate_sha256=audit["candidate_sha256"], postcheck_sha256=protocol.sha(out / "postcheck.json"),
            result_after_sha256=protocol.sha(out / "result.json"))
    except BaseException as error:
        record["errors"].append(_error(error))
    record.update(returned_monotonic=time.monotonic(), return_wall_s=time.monotonic() - started,
                  no_search_or_repair=True, new_U=False)
    protocol.write_new(out / "post_return.json", record)
    _emit({"slot_id": slot_id, "post_passed": record["passed"],
           "evaluation_calls": record["evaluation_calls"], "new_U": False})
    return 0 if record["passed"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("method", "post"))
    parser.add_argument("--declaration", type=Path, required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return (run_method if args.mode == "method" else run_post)(
            args.declaration, args.slot_id, args.out)
    except BaseException as error:
        _emit({"state": "WORKER_ABORTED_OR_PRECONDITION_REJECTED", "error_type": type(error).__name__,
               "message": str(error),
               "new_method_or_evaluation": "UNDETERMINED_CHECK_SLOT_EVIDENCE"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
