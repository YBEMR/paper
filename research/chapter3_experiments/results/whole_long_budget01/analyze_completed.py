"""Analyze existing completed K187 evidence. No science imports or execution.

Refuses to run before terminal.json exists. This program never waits, polls,
decodes a solver vector, constructs a model, integrates heat, or evaluates a
candidate. Native publications are not budget-valid evidence without Python
receipt/admission records. Only analysis.json and results.csv are written.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parent
METHOD = ROOT / "method"
RESULTS = ROOT.parent
OLD = RESULTS / "p0_execution01/calls/base__R1/whole_milp"
MISSING = []
READ_ERRORS = []


def read(path):
    if not path.is_file():
        MISSING.append(str(path))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        READ_ERRORS.append({"path": str(path), "error": type(exc).__name__, "detail": str(exc)})
        return None


def dig(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def sha(path):
    if not path.is_file():
        return None
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical(value):
    if not isinstance(value, dict):
        return None
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def timely(value, limit):
    return finite(value) and finite(limit) and 0 <= value < limit


def rational(value):
    try:
        return None if value is None or isinstance(value, bool) else Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def interval(evaluation):
    if not isinstance(evaluation, dict):
        return None
    pair = evaluation.get("weighted_energy_J")
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    lo, hi = map(rational, pair)
    return (lo, hi) if lo is not None and hi is not None and 0 <= lo <= hi else None


def vector_length(value):
    return len(value) if isinstance(value, list) else None


def events_from(path):
    if not path.is_file():
        MISSING.append(str(path))
        return None
    events = []
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    events.append(row)
                else:
                    raise ValueError("event must be an object")
            except (ValueError, TypeError) as exc:
                READ_ERRORS.append({"path": str(path), "line": number, "error": str(exc)})
    return events


def event_time(row):
    for value in [row.get("method_elapsed_s"), row.get("evaluation_returned_at_s"),
                  dig(row, "decode", "completed_at_s")]:
        if finite(value):
            return value
    return None


def safe_record(candidate, evaluation, source, accepted, limit):
    pair = interval(evaluation)
    stamp = dig(evaluation, "completed_at_elapsed_s")
    if (not isinstance(candidate, dict) or accepted is not True or pair is None
            or dig(evaluation, "state") != "SAFE"
            or dig(evaluation, "rankable_energy") is not True or not timely(stamp, limit)):
        return None
    return {"source": source, "candidate_sha256": canonical(candidate), "formed_at_s": stamp,
            "energy_lower_J": str(evaluation["weighted_energy_J"][0]),
            "energy_upper_J": str(evaluation["weighted_energy_J"][1]),
            "independently_rechecked_by_this_analysis": False}


def compare_options(old, new):
    if not isinstance(old, dict) or not isinstance(new, dict):
        return {"strict_equal_except_MaxTime": None, "reason": "OPTIONS_MISSING"}
    keys = set(old) | set(new)
    changes = {key: {"old": old.get(key), "new": new.get(key),
                     "present_in_old": key in old, "present_in_new": key in new}
               for key in sorted(keys) if key not in old or key not in new or old[key] != new[key]}
    return {"strict_equal_except_MaxTime": all(key == "MaxTime" for key in changes),
            "differences": changes, "allowed_difference": "MaxTime only; derived from remaining root budget"}


def summarize_checkpoint(path):
    value = read(path) or {}
    return {"path": str(path), "sha256": sha(path),
            "cutoff_s": value.get("cutoff_s"), "observed_method_elapsed_s": value.get("observed_method_elapsed_s"),
            "state": value.get("state"), "counts": value.get("counts"),
            "best_safe_upper_bound_J": dig(value, "best_safe_receipt_as_reported", "safe_upper_bound_J"),
            "latest_solver_reported_bound": value.get("latest_solver_reported_bound"),
            "new_research_calls_created_by_analysis": 0,
            "scope": "one trajectory observation, not an independent 300/900/1800/3600-second run"}


def main():
    if not (ROOT / "terminal.json").is_file():
        raise SystemExit("Refusing final analysis: terminal.json does not exist; no wait or polling performed")
    terminal = read(ROOT / "terminal.json")
    if not isinstance(terminal, dict):
        raise SystemExit("Refusing final analysis: terminal.json is unreadable")
    declaration = read(ROOT / "declaration.json") or {}
    limit = declaration.get("method_seconds")
    budget = read(METHOD / "method_budget_identity.json") or {}
    returned = read(ROOT / "method_return.json") or {}
    result = read(METHOD / "result.json")
    wrapper = read(METHOD / "wrapper_raw_result.json")
    raw = wrapper if isinstance(wrapper, dict) else result if isinstance(result, dict) else {}
    primary = result if isinstance(result, dict) else raw
    events = events_from(METHOD / "diagnostic_events.jsonl")
    retained_events = [row for row in events or [] if timely(event_time(row), limit)]
    worker = [row for row in retained_events if row.get("event") == "worker_event_received"]
    received = [row for row in retained_events if row.get("event") == "candidate_received"]
    decoded = [row for row in retained_events if row.get("event") == "candidate_decoded"]
    duplicate = [row for row in retained_events if row.get("event") == "duplicate_receipt_reused"]
    safe_events = [row for row in events or [] if row.get("event") == "candidate_evaluated"]
    checkpoint = read(METHOD / "initial_receipt_checkpoint.json") or {}
    initialization = dig(checkpoint, "initialisation") or raw.get("initialisation") or {}
    initial = safe_record(dig(initialization, "witness", "candidate"),
                          dig(initialization, "witness", "evaluation"), "initial_constructor", True, limit)
    safes = []
    for row in safe_events:
        safe = safe_record(row.get("candidate"), row.get("evaluation"), row.get("source"),
                           row.get("accepted_safe"), limit)
        if safe is not None:
            safe["evaluation_returned_at_s"] = row.get("evaluation_returned_at_s")
            safe["return_within_budget"] = timely(row.get("evaluation_returned_at_s"), limit)
            safes.append(safe)
    safes.sort(key=lambda row: row["formed_at_s"])
    incumbent = initial
    strict, nonimproving, unknown = [], [], []
    distinct = set()
    for row in safes:
        distinct.add(row["candidate_sha256"])
        if incumbent is None:
            unknown.append(row)
            incumbent = row
        elif rational(row["energy_upper_J"]) < rational(incumbent["energy_lower_J"]):
            strict.append(row)
            incumbent = row
        else:
            nonimproving.append(row)
            if rational(row["energy_upper_J"]) < rational(incumbent["energy_upper_J"]):
                incumbent = row
    initial_hash = None if initial is None else initial["candidate_sha256"]
    new_safe_hashes = distinct - ({initial_hash} if initial_hash else set())
    bounds = [{"method_elapsed_s": row.get("method_elapsed_s"), "request": row.get("request"),
               "state": row.get("state"), "lowerbound": dig(row, "values", "lowerbound"),
               "relativegap": dig(row, "values", "relativegap"),
               "fval": dig(row, "values", "fval"), "independently_certified": False}
              for row in worker if finite(dig(row, "values", "lowerbound"))]
    old = read(OLD / "result.json") or {}
    old_response = read(OLD / "matlab/request_000001.response.json") or {}
    native = []
    prefixes = sorted({path.name.split(".", 1)[0] for path in (METHOD / "matlab").glob("request_*.*")})
    for prefix in prefixes:
        path = METHOD / "matlab" / (prefix + ".response.json")
        response = read(path) or {}
        python_path = path.with_name(prefix + ".python.json")
        python = read(python_path) or {}
        published_events = []
        for event_path in sorted(path.parent.glob(prefix + ".event_*.json")):
            event = read(event_path) or {}
            length = vector_length(event.get("x"))
            consumed = next((row for row in worker if row.get("request") == prefix
                             and row.get("event_number") == event.get("event_number")), None)
            published_events.append({"path": str(event_path), "event_number": event.get("event_number"),
                "kind": event.get("kind"), "state": event.get("state"), "x_length": length,
                "request_wall_seconds": event.get("request_wall_seconds"),
                "in_budget_worker_event_received": consumed is not None,
                "method_received_at_s": None if consumed is None else consumed.get("method_elapsed_s"),
                "values": event.get("values"), "solver_reported_only": True})
        response_stamp = python.get("solver_response_complete_at_monotonic")
        stamp_valid = (finite(response_stamp) and finite(budget.get("start")) and finite(budget.get("deadline"))
                       and budget["start"] <= response_stamp < budget["deadline"])
        python_admitted = (python.get("budget_valid") is True and python.get("accepted_for_evaluation") is True
                           and stamp_valid)
        native.append({"request": prefix, "response_path": str(path), "python_path": str(python_path),
            "status": response.get("status"), "exitflag": response.get("exitflag"),
            "fval": response.get("fval"), "output": response.get("output"),
            "native_final_x_length": vector_length(response.get("x")),
            "python_returned_x_length": vector_length(python.get("x")),
            "python_status": python.get("status"), "python_budget_valid": python.get("budget_valid"),
            "python_accepted_for_evaluation": python.get("accepted_for_evaluation"),
            "solver_response_complete_at_monotonic": response_stamp,
            "response_timestamp_inside_root": stamp_valid,
            "final_vector_admitted_in_budget": python_admitted and bool(python.get("x")),
            "native_phase_seconds": response.get("phase_seconds"),
            "native_request_wall_seconds": response.get("matlab_request_wall_seconds"),
            "worker_elapsed_seconds": response.get("worker_elapsed_seconds"),
            "options": response.get("options"),
            "options_comparison_with_original": compare_options(old_response.get("options"), response.get("options")),
            "solver_warning_message": response.get("solver_warning_message"),
            "solver_warning_identifier": response.get("solver_warning_identifier"),
            "published_callback_events": published_events,
            "no_late_backfill": True,
            "numfeaspoints_is_not_a_candidate_vector": True})
    history = []
    csv_path = RESULTS / "p0_resume01/analysis01/results40.csv"
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            history = [{key: row.get(key) for key in ["method", "safe_U_exact", "method_root_s", "return_inclusive_s",
                                                       "first_SAFE_s", "first_strict_improvement_s", "matlab_startup_s"]}
                       for row in csv.DictReader(stream)
                       if row["problem_id"] == "base__R1" and row["method"] in {"whole_milp", "heft", "anchor_linked4"}]
    usable_u = dig(returned, "records", "usable_U_J")
    final_u = rational(usable_u)
    comparisons = []
    for row in history:
        baseline = rational(row["safe_U_exact"])
        delta = None if final_u is None or baseline is None else final_u - baseline
        comparisons.append({**row, "new_minus_historical_J_exact": None if delta is None else str(delta),
            "new_minus_historical_J": None if delta is None else float(delta),
            "reduction_percent": None if delta is None or baseline == 0 else float(-100 * delta / baseline),
            "same_budget": False, "scope": "descriptive unequal-budget comparison, not algorithm dominance"})
    closed = read(METHOD / "matlab/closed.json") or {}
    session = read(METHOD / "matlab/session.json") or {}
    post_return = read(ROOT / "post_return.json")
    postcheck = read(ROOT / "postcheck.json")
    shutdown_issues = []
    for phase in terminal.get("phases") or []:
        if phase.get("watchdog_stop") is True or phase.get("returncode") not in (None, 0):
            shutdown_issues.append({"source": "terminal_phase", "detail": phase})
    if closed.get("returncode") not in (None, 0):
        shutdown_issues.append({"source": "matlab_closed_returncode", "value": closed.get("returncode")})
    if closed.get("observed_tree_verified_terminated") is False:
        shutdown_issues.append({"source": "unverified_process_termination"})
    if closed.get("force_requested") is True:
        shutdown_issues.append({"source": "forced_cleanup", "succeeded": closed.get("force_termination_succeeded")})
    if returned.get("errors"):
        shutdown_issues.append({"source": "method_return_errors", "errors": returned["errors"]})
    static = read(ROOT / "readonly_matrix_identity.json") or {}
    checkpoints = [summarize_checkpoint(path) for path in sorted((ROOT / "checkpoints").glob("*.json"))]
    lower = read(METHOD / "independent_bounds.json")
    received_by_source = {row.get("source"): row.get("method_elapsed_s") for row in received}
    legal_evaluated_candidates = {}
    for row in safe_events:
        identity = canonical(row.get("candidate"))
        stamp = received_by_source.get(row.get("source"))
        if identity is not None and timely(stamp, limit):
            legal_evaluated_candidates.setdefault(identity, {"candidate_sha256": identity,
                "first_received_at_s": stamp, "source": row.get("source"),
                "evaluation_state_as_stored": dig(row, "evaluation", "state")})
    distinct_new_integers = [value for key, value in legal_evaluated_candidates.items() if key != initial_hash]
    distinct_new_integers.sort(key=lambda value: value["first_received_at_s"])
    native_events = [event for request in native for event in request["published_callback_events"]]
    row_counts = {
        "initial_complete_SAFE": None if initial is None else 1,
        "candidate_receipts_in_budget": None if events is None else len(received),
        "callback_candidate_receipts_in_budget": None if events is None else sum(":event" in str(row.get("source")) for row in received),
        "final_return_candidate_receipts_in_budget": None if events is None else sum(str(row.get("source", "")).endswith(":final") for row in received),
        "legal_decodes_in_budget": None if events is None else sum(dig(row, "decode", "state") == "LEGAL" for row in decoded),
        "distinct_legal_candidates_with_stored_evaluation": None if events is None else len(legal_evaluated_candidates),
        "distinct_legal_candidates_different_from_initial_with_stored_evaluation": None if events is None else len(distinct_new_integers),
        "duplicate_receipt_reuses_in_budget": None if events is None else len(duplicate),
        "complete_SAFE_solver_evaluations": None if events is None else len(safes),
        "distinct_complete_SAFE_solver_candidates": None if events is None else len(distinct),
        "distinct_complete_SAFE_candidates_different_from_initial": None if events is None else len(new_safe_hashes),
        "strict_interval_improvements": None if events is None else len(strict),
        "non_strictly_improving_SAFE_evaluations": None if events is None else len(nonimproving),
        "SAFE_without_prior_comparator": None if events is None else len(unknown),
        "events_excluded_for_missing_or_late_timestamp": None if events is None else len(events) - len(retained_events),
        "evaluation_states_as_stored": dict(Counter(dig(row, "evaluation", "state") for row in safe_events)),
        "native_callback_publications_with_nonempty_x_all_times": sum((event["x_length"] or 0) > 0 for event in native_events),
        "native_callback_nonempty_x_with_in_budget_receipt": sum((event["x_length"] or 0) > 0 and event["in_budget_worker_event_received"] for event in native_events),
        "native_final_responses_with_nonempty_x_all_times": sum((request["native_final_x_length"] or 0) > 0 for request in native),
        "native_final_vectors_admitted_in_budget": sum(request["final_vector_admitted_in_budget"] for request in native),
    }
    output = {
        "protocol": "K187-independent-completed-evidence-analysis-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "terminal_required_and_present": True, "terminal": terminal,
        "scope": "stored artifacts only; zero research calls/model construction/decoding/thermal integration/candidate evaluation",
        "source_result_path": str(METHOD / ("result.json" if isinstance(result, dict) else "wrapper_raw_result.json")),
        "result_present": isinstance(result, dict), "wrapper_present": isinstance(wrapper, dict),
        "result_equals_wrapper": None if not isinstance(result, dict) or not isinstance(wrapper, dict) else result == wrapper,
        "method_return": returned, "budget": budget, "declared_method_seconds": limit,
        "counts": row_counts, "initial_SAFE": initial,
        "first_candidate_received_s": min((row["method_elapsed_s"] for row in received), default=None),
        "first_distinct_new_legal_candidate_received_s": distinct_new_integers[0]["first_received_at_s"] if distinct_new_integers else None,
        "distinct_new_legal_candidates_with_evaluations": distinct_new_integers,
        "distinct_new_legal_count_scope": "only decoded candidates whose stored evaluation exposes identity; unfinished evaluation without candidate identity remains unclassified, not assumed new",
        "first_legal_decode_s": min((dig(row, "decode", "completed_at_s") for row in decoded
                                    if dig(row, "decode", "state") == "LEGAL" and finite(dig(row, "decode", "completed_at_s"))), default=None),
        "first_solver_complete_SAFE_s": min((row["formed_at_s"] for row in safes), default=None),
        "first_strict_SAFE_improvement_s": strict[0]["formed_at_s"] if strict else None,
        "solver_SAFE_records": safes, "strict_SAFE_improvements": strict,
        "reported_final_U_J": primary.get("safe_upper_bound_J"), "audit_usable_final_U_J": usable_u,
        "safe_solution_source": primary.get("safe_solution_source"),
        "final_candidate_sha256": canonical(primary.get("safe_candidate")),
        "independent_lower_bound": lower,
        "solver_reported_bounds_in_budget": bounds,
        "solver_bounds_are_independently_certified": False,
        "independently_proven_optimal_as_reported": primary.get("independently_proven_optimal"),
        "independently_proven_infeasible_as_reported": primary.get("independently_proven_infeasible"),
        "model_summary": primary.get("model_summary"), "construction": primary.get("construction"),
        "model_completed_at_s": primary.get("model_completed_at_s"),
        "matrix_completed_at_s": primary.get("matrix_completed_at_s"),
        "timing": primary.get("timing"), "session": session, "closed": closed,
        "native_requests": native, "shutdown_review_flags": shutdown_issues,
        "postcheck": {"claim": read(ROOT / "post.claim.json"), "return": post_return,
                      "state": dig(postcheck, "state"), "rankable_energy": dig(postcheck, "rankable_energy"),
                      "weighted_energy_J": dig(postcheck, "weighted_energy_J"),
                      "does_not_replace_budget_U": True},
        "checkpoints": checkpoints,
        "static_matrix_evidence": {"path": str(ROOT / "readonly_matrix_identity.json"),
                                   "sha256": sha(ROOT / "readonly_matrix_identity.json"), "passed": static.get("passed")},
        "historical_energy_comparisons": comparisons,
        "budget_interpretation": "new 3600-second whole-MILP trajectory versus old 300-second ceilings; checkpoints are not independent runs",
        "missing_files": MISSING, "read_errors": READ_ERRORS,
        "no_numfeaspoints_to_x_inference": True, "no_native_late_candidate_or_bound_backfill": True,
    }
    (ROOT / "analysis.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["run", "method", "budget_s", "safe_U_J", "root_s", "return_inclusive_s", "startup_s",
               "first_SAFE_s", "first_new_integer_receipt_s", "first_solver_SAFE_s", "first_strict_improvement_s",
               "candidate_receipts", "callback_candidate_receipts", "final_candidate_receipts", "duplicate_receipts",
               "strict_SAFE_improvements", "post_passed", "execution_status", "same_budget_comparison"]
    csv_rows = [{"run": "K187_long", "method": "whole_milp", "budget_s": limit, "safe_U_J": usable_u,
        "root_s": dig(primary, "timing", "method_elapsed_s"), "return_inclusive_s": returned.get("wall_including_cleanup_s"),
        "startup_s": dig(primary, "timing", "phases_exclusive_s", "solver_startup"),
        "first_SAFE_s": None if initial is None else initial["formed_at_s"],
        "first_new_integer_receipt_s": output["first_distinct_new_legal_candidate_received_s"],
        "first_solver_SAFE_s": output["first_solver_complete_SAFE_s"],
        "first_strict_improvement_s": output["first_strict_SAFE_improvement_s"],
        "candidate_receipts": row_counts["candidate_receipts_in_budget"],
        "callback_candidate_receipts": row_counts["callback_candidate_receipts_in_budget"],
        "final_candidate_receipts": row_counts["final_return_candidate_receipts_in_budget"],
        "duplicate_receipts": row_counts["duplicate_receipt_reuses_in_budget"],
        "strict_SAFE_improvements": row_counts["strict_interval_improvements"],
        "post_passed": dig(post_return, "passed"),
        "execution_status": dig(returned, "records", "execution", "execution_status"),
        "same_budget_comparison": False}]
    csv_rows += [{"run": "historical_P0_R1", "method": row["method"], "budget_s": 300,
        "safe_U_J": row["safe_U_exact"], "root_s": row["method_root_s"],
        "return_inclusive_s": row["return_inclusive_s"], "startup_s": row["matlab_startup_s"],
        "first_SAFE_s": row["first_SAFE_s"], "first_strict_improvement_s": row["first_strict_improvement_s"],
        "same_budget_comparison": False} for row in history]
    with (ROOT / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps({"analysis_written": True, "audit_usable_final_U_J": usable_u,
                      "counts": row_counts, "read_errors": len(READ_ERRORS)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
