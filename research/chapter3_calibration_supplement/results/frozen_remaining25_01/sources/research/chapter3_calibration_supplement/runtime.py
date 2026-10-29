"""One-shot serial time-diagnostic execution; no approval is created here."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from unittest.mock import patch

from research.chapter3_deadline_reference.run_checks import ScopeGuard
from research.chapter3_workload_calibration.runtime import (
    sha, read_json, write_gzip, read_gzip)
from .persistence import write_once, SnapshotLog, read_latest_snapshot
from .protocol import (REPO, LIMITS, require, result_path, sources, protected,
                       check_frozen, validate_approval, load_evidence, freeze)

ZERO = {"mapping_constructions": 0, "timetable_constructions": 0, "S1_projections": 0,
        "formal_method_calls": 0, "thermal_integrations": 0}


def exclusive_json(path, value):
    write_once(path, value)


def append_ledger(path, value):
    import json
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def validate_worker_context(freeze_dir, out, index, token):
    """A direct worker command must match the same approved, consumed slot."""
    freeze_dir, out = result_path(freeze_dir), result_path(out)
    plan, inv, record = check_frozen(freeze_dir)
    limits = plan.get("limits", LIMITS)
    approval = read_json(out / "approval.json")
    validate_approval(approval, record["plan_sha256"], plan=plan)
    batch = read_json(freeze_dir / "execution_claim.json")
    require(batch["output"] == str(out) and batch["plan_sha256"] == record["plan_sha256"] and
            batch["approval_sha256"] == sha(out / "approval.json"), "BATCH_CLAIM_BINDING")
    if "consumption_claim_path" in plan:
        require(read_json(result_path(plan["consumption_claim_path"])) == batch, "CONTINUATION_CONSUMPTION_BINDING")
    require(type(index) is int and 0 <= index < len(plan["calls"]), "CALL_INDEX")
    call = plan["calls"][index]
    directory = out / call["condition_id"]
    claim = read_json(directory / "call_claim.json")
    require(claim["index"] == index and claim["call"] == call and claim["token"] == token and
            claim["plan_sha256"] == record["plan_sha256"], "SLOT_CLAIM_BINDING")
    started, deadline = claim["started_monotonic"], claim["deadline_monotonic"]
    require(all(isinstance(x, (int, float)) and math.isfinite(x) for x in
                (started, deadline, batch["started_monotonic"], batch["deadline_monotonic"])), "CLOCK_INVALID")
    require(batch["deadline_monotonic"] == batch["started_monotonic"] + limits["batch_seconds"] and
            batch["started_monotonic"] <= started < deadline <= started + limits["condition_seconds"] and
            deadline <= batch["deadline_monotonic"] - limits["finalization_reserve_seconds"],
            "SLOT_BUDGET_BINDING")
    require(time.perf_counter() < deadline, "WORKER_START_AFTER_DEADLINE")
    return plan, inv, call, directory, started, deadline


def worker(freeze_dir, out, index, token):
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    directory = None
    owns_worker_claim = False
    started = time.perf_counter()
    counters = dict(ZERO)
    try:
        plan, inv, call, directory, started, deadline = validate_worker_context(freeze_dir, out, index, token)
        exclusive_json(directory / "worker_claim.json", {"token": token, "pid": os.getpid()})
        owns_worker_claim = True
        progress_log = SnapshotLog(directory / "progress")

        def progress(phase, current):
            counters.update(current)
            if time.perf_counter() >= deadline:
                raise TimeoutError("CONDITION_TIME_LIMIT")
            progress_log.append({"phase": phase, "counters": dict(counters),
                       "elapsed_s": time.perf_counter() - started})

        progress("READING_FROZEN_PARENT_AND_COMPARISONS", counters)
        comparisons = {name: load_evidence(inv, name) for name in
                       [call["parent_id"]] + call["comparison_ids"]}
        parent = comparisons[call["parent_id"]]
        progress("ARCHIVE_BINDINGS_VERIFIED", counters)
        from .condition import evaluate_supplement
        from .analysis import summarize_condition
        from research.chapter3_workload_calibration import evaluation, generator, profiles
        from research.chapter3_deadline_reference import scheduler
        constructor = evaluation.build_timetable

        def derived_only(data, *args, **kwargs):
            require(data["derivation"]["axis"] == call["axis"] and
                    data["derivation"]["parent_contract_hash"] == parent["workload"]["contract_hash"],
                    "ONLY_NEW_DERIVED_CONDITION_MAY_BE_SCHEDULED")
            return constructor(data, *args, **kwargs)

        with ExitStack() as stack:
            for module, name in ((evaluation, "choose_mapping"), (scheduler, "choose_mapping"),
                                 (generator, "build_base"), (profiles, "make_profile")):
                stack.enter_context(patch.object(module, name, side_effect=RuntimeError("NO_NEW_ROOT_MAPPING_OR_SAMPLING")))
            stack.enter_context(patch.object(evaluation, "build_timetable", derived_only))
            evidence = evaluate_supplement(call, parent, {name: comparisons[name] for name in call["comparison_ids"]},
                                          progress=progress)
        progress("TIME_DIAGNOSTIC_COMPLETE", counters)
        summary = summarize_condition(call, evidence, comparisons)
        progress("DESCRIPTIVE_SUMMARY_COMPLETE", counters)
        write_gzip(directory / "generated_workload.json.gz", evidence["workload"])
        write_gzip(directory / "evidence.json.gz", evidence)
        write_once(directory / "summary.json", summary)
        progress("PAYLOADS_SAVED", counters)
        require(counters == {**ZERO, "timetable_constructions": 3}, "EXACTLY_THREE_REFERENCE_TABLES_REQUIRED")
        require(not guard.denied_events and not guard.denied_imports, "SCOPE_FAILURE")
        write_once(directory / "result.json", {
            "state": "COMPLETE", "condition": call, "elapsed_s": time.perf_counter() - started,
            "counters": counters, "source_files": sources(), "token": token,
            "evidence_sha256": sha(directory / "evidence.json.gz"),
            "workload_sha256": sha(directory / "generated_workload.json.gz"),
            "summary_sha256": sha(directory / "summary.json"),
            "denied_imports": guard.denied_imports, "denied_events": guard.denied_events,
            "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"})
        return 0
    except (Exception, KeyboardInterrupt) as error:
        detail = {"state": "TIMEOUT" if isinstance(error, TimeoutError) else "FAILED",
                  "error": str(error), "error_type": type(error).__name__,
                  "traceback": traceback.format_exc(), "elapsed_s": time.perf_counter() - started,
                  "counters": counters, "denied_imports": guard.denied_imports,
                  "denied_events": guard.denied_events}
        if directory is not None:
            # Existing successful worker output cannot be replaced by a second launch.
            target = directory / ("worker_rejection.json" if not owns_worker_claim or
                                   (directory / "result.json").exists() else "result.json")
            if not target.exists():
                try:
                    write_once(target, detail)
                except (Exception, KeyboardInterrupt) as save_error:
                    detail["persistence_error"] = {"type": type(save_error).__name__, "error": str(save_error)}
        print(str(detail), flush=True)
        return 2


def decide_call_state(code, receipt, elapsed, limit):
    times = [elapsed, limit] + ([receipt.get("elapsed_s")] if receipt else [])
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in times) or limit <= 0:
        return "INVALID_CLOCK"
    if elapsed > limit or (receipt and receipt["elapsed_s"] > limit):
        return "TIMEOUT_OR_LATE"
    if code != 0 or not receipt or receipt.get("state") != "COMPLETE":
        return "FAILED"
    if receipt.get("denied_imports") or receipt.get("denied_events"):
        return "SCOPE_FAILURE"
    return "COMPLETE"


def accept_receipt(directory, call, claim, source_map):
    receipt = read_json(directory / "result.json")
    require(receipt["state"] == "COMPLETE" and receipt["condition"] == call and
            receipt["token"] == claim["token"], "RESULT_IDENTITY")
    require(receipt["counters"] == {**ZERO, "timetable_constructions": 3} and
            receipt["source_files"] == source_map and receipt["beta_selected"] is None and
            receipt["thermal_status"] == receipt["energy_status"] == "NOT_EVALUATED", "RESULT_SCOPE")
    for name, key in (("generated_workload.json.gz", "workload_sha256"),
                      ("evidence.json.gz", "evidence_sha256"), ("summary.json", "summary_sha256")):
        require(sha(directory / name) == receipt[key], "RESULT_PAYLOAD_HASH")
    evidence = read_gzip(directory / "evidence.json.gz")
    require(evidence["call"] == call and evidence["workload"] == read_gzip(directory / "generated_workload.json.gz"),
            "RESULT_EVIDENCE_LINK")
    return receipt, read_json(directory / "summary.json")


def launch_worker(args, logfile, deadline):
    """Only one child, no retries; worker itself forbids descendants."""
    proc = None
    with Path(logfile).open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.Popen(args, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            return proc.wait(timeout=max(.001, deadline - time.perf_counter()))
        except subprocess.TimeoutExpired:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            return -1
        except (Exception, KeyboardInterrupt):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            log.write(traceback.format_exc())
            return -2


def execute(freeze_dir, output, approval_path):
    started = time.perf_counter()  # Includes input/source/archive validation.
    freeze_dir = result_path(freeze_dir)
    plan, inv, record = check_frozen(freeze_dir)
    limits = plan.get("limits", LIMITS)
    approval_path = Path(approval_path).resolve()
    approval = read_json(approval_path)
    validate_approval(approval, record["plan_sha256"], plan=plan)
    check_frozen(freeze_dir, full_archive_check=True)
    out = result_path(output, fresh=True)
    batch_deadline = started + limits["batch_seconds"]
    claim_record = {
        "output": str(out), "plan_sha256": record["plan_sha256"], "approval_sha256": sha(approval_path),
        "started_monotonic": started, "deadline_monotonic": batch_deadline,
        "started_utc": datetime.now(timezone.utc).isoformat()}
    if "consumption_claim_path" in plan:
        shared_claim = result_path(plan["consumption_claim_path"])
        shared_claim.parent.mkdir(parents=True, exist_ok=True)
        exclusive_json(shared_claim, claim_record)
    exclusive_json(freeze_dir / "execution_claim.json", claim_record)
    rows = []
    state = "RUNNING"
    final_error = None
    additional_errors = []
    after = None

    def remember_error(error):
        nonlocal final_error
        detail = {"error": str(error), "type": type(error).__name__, "traceback": traceback.format_exc()}
        if final_error is None:
            final_error = detail
        else:
            additional_errors.append(detail)

    def save_terminal_failure(result):
        try:
            write_once(out / "terminal_failure.json", result)
        except (Exception, KeyboardInterrupt) as fallback_error:
            remember_error(fallback_error)
            print(str({"state": state, "terminal_record_saved": False,
                       "completed_conditions": result["completed_conditions"],
                       "final_error": final_error, "additional_errors": additional_errors}),
                  file=sys.stderr, flush=True)

    try:
        out.mkdir(parents=True)
        shutil.copyfile(approval_path, out / "approval.json")
        shutil.copyfile(freeze_dir / "plan.json", out / "plan.json")
        status_log = SnapshotLog(out / "status")
        for index, call in enumerate(plan["calls"]):
            if time.perf_counter() >= batch_deadline - limits["finalization_reserve_seconds"]:
                state = "STOPPED_BATCH_TIMEOUT"
                break
            check_frozen(freeze_dir)
            call_start = time.perf_counter()
            deadline = min(call_start + limits["condition_seconds"],
                           batch_deadline - limits["finalization_reserve_seconds"])
            if deadline <= call_start:
                state = "STOPPED_BATCH_TIMEOUT"
                break
            directory = out / call["condition_id"]
            directory.mkdir()
            claim = {"state": "CLAIMED", "index": index, "call": call, "token": uuid.uuid4().hex,
                     "plan_sha256": record["plan_sha256"], "started_monotonic": call_start,
                     "deadline_monotonic": deadline, "limit_seconds": deadline - call_start}
            exclusive_json(directory / "call_claim.json", claim)
            row = {"condition_id": call["condition_id"], "index": index, "state": "CLAIMED",
                   "counters": dict(ZERO)}
            rows.append(row)
            append_ledger(out / "ledger.jsonl", {**row, "claim": claim})
            args = [sys.executable, "-B", "-m", "research.chapter3_calibration_supplement.runtime",
                    "_worker", "--freeze", str(freeze_dir), "--output", str(out),
                    "--index", str(index), "--token", claim["token"]]
            code = launch_worker(args, directory / "worker.log", deadline)
            receipt_path = directory / "result.json"
            receipt = read_json(receipt_path) if receipt_path.is_file() else None
            accepted = decide_call_state(code, receipt, time.perf_counter() - call_start, claim["limit_seconds"])
            if receipt is not None:
                row["counters"] = receipt.get("counters", dict(ZERO))
            else:
                progress_record = read_latest_snapshot(directory / "progress")
                if progress_record is not None:
                    row["counters"] = progress_record.get("counters", dict(ZERO))
            if accepted == "COMPLETE":
                try:
                    receipt, summary = accept_receipt(directory, call, claim, plan["source_files"])
                    if time.perf_counter() > deadline:
                        accepted = "TIMEOUT_OR_LATE"
                    else:
                        row["summary"] = summary
                except Exception as error:
                    accepted = "EVIDENCE_FAILURE"
                    write_once(directory / "acceptance_error.json", {"error": str(error), "traceback": traceback.format_exc()})
            row.update(state=accepted, elapsed_s=time.perf_counter() - call_start, returncode=code,
                       result_sha256=sha(receipt_path) if receipt_path.is_file() else None)
            append_ledger(out / "ledger.jsonl", row)
            # Batch remains RUNNING until final source/summary/terminal persistence succeeds.
            # Full summaries remain in immutable per-condition files and final output.
            status_log.append({"state": "RUNNING", "last_condition_state": accepted,
                               "rows": [{k: v for k, v in item.items() if k not in {"summary", "error"}}
                                        for item in rows], "elapsed_s": time.perf_counter() - started})
            print(str({"condition_id": call["condition_id"], "state": accepted, "elapsed_s": row["elapsed_s"]}), flush=True)
            if accepted != "COMPLETE":
                state = "STOPPED_" + accepted
                break
        if len(rows) == len(plan["calls"]) and all(r["state"] == "COMPLETE" for r in rows):
            state = "COMPLETE"
    except (Exception, KeyboardInterrupt) as error:
        state = "STOPPED_EXCEPTION"
        remember_error(error)
        if rows and rows[-1]["state"] == "CLAIMED":
            rows[-1]["state"] = "FAILED"
            rows[-1]["error"] = final_error
    finally:
        if out.is_dir():
            try:
                after = protected()
                require(after == record["protected_files"] and sources() == plan["source_files"], "FINAL_SOURCE_OR_ARCHIVE_DRIFT")
                check_frozen(freeze_dir, full_archive_check=True)
            except Exception as error:
                state = "STOPPED_SOURCE_OR_ARCHIVE_DRIFT"
                remember_error(error)
            row_by_id = {r["condition_id"]: r for r in rows}
            coverage = [row_by_id.get(c["condition_id"], {"condition_id": c["condition_id"], "state": "NOT_RUN"})
                        for c in plan["calls"]]
            summary = None
            try:
                from .analysis import aggregate_summaries
                summary = aggregate_summaries(plan["calls"], coverage)
                write_once(out / "summary.json", summary)
            except Exception as error:
                state = "STOPPED_SUMMARY_ERROR"
                remember_error(error)
            elapsed = time.perf_counter() - started
            if elapsed > limits["batch_seconds"]:
                state = "STOPPED_BATCH_OVERRUN"
            result = {"state": state, "rows": coverage, "consumed_conditions": len(rows),
                      "completed_conditions": sum(r["state"] == "COMPLETE" for r in rows),
                      "planned_conditions": len(plan["calls"]), "elapsed_s": elapsed, "limits": limits,
                      "protected_unchanged": after == record["protected_files"],
                      "final_error": final_error, "additional_errors": additional_errors,
                      "plan_sha256": record["plan_sha256"],
                      "beta_selected": None, "formal_algorithm_calls": 0, "thermal_integrations": 0}
            try:
                write_once(out / "batch_result.json", result)
            except (Exception, KeyboardInterrupt) as error:
                previous_state = state
                state = "STOPPED_TERMINAL_PERSISTENCE"
                remember_error(error)
                result.update(state=state, final_error=final_error, additional_errors=additional_errors,
                              execution_state_before_persistence_failure=previous_state)
                # A terminal failure marker takes precedence even if fsync failed after
                # the primary file became readable. Do not overwrite or retry that file.
                save_terminal_failure(result)
            else:
                # Final serialization/flush belongs to the batch clock too.
                finished_elapsed = time.perf_counter() - started
                if finished_elapsed > limits["batch_seconds"] and state != "STOPPED_BATCH_OVERRUN":
                    previous_state = state
                    state = "STOPPED_BATCH_OVERRUN"
                    result.update(state=state, elapsed_s=finished_elapsed,
                                  execution_state_before_persistence_failure=previous_state,
                                  terminal_reason="FINAL_PERSISTENCE_EXCEEDED_BATCH_CLOCK")
                    save_terminal_failure(result)
    return 0 if state == "COMPLETE" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "freeze-remaining", "inspect", "execute", "_worker"))
    parser.add_argument("--output")
    parser.add_argument("--freeze")
    parser.add_argument("--checks")
    parser.add_argument("--approval")
    parser.add_argument("--index", type=int)
    parser.add_argument("--token")
    args = parser.parse_args(argv)
    if args.operation == "freeze-remaining":
        from .continuation import freeze as freeze_remaining
        print(freeze_remaining(args.output, args.checks))
        return 0
    if args.operation == "freeze":
        print(freeze(args.output, args.checks))
        return 0
    if args.operation == "inspect":
        plan, _, _ = check_frozen(args.freeze, full_archive_check=True)
        print({"state": "FROZEN_NOT_AUTHORIZED", "conditions": len(plan["calls"]), "limits": plan["limits"],
               "execution_authorized": False})
        return 0
    if args.operation == "_worker":
        return worker(args.freeze, args.output, args.index, args.token)
    require(args.approval is not None, "SEPARATE_USER_APPROVAL_REQUIRED")
    return execute(args.freeze, args.output, args.approval)


if __name__ == "__main__":
    raise SystemExit(main())
