"""Read-only admission of four method formats; no scientific calculation.

This module checks archived receipts and exact scheduling labels.  It never
evaluates a new candidate, repairs one, imports a solver, or supplies an initial
solution.  Worker identity must originate in the new, approved execution chain;
method snapshots cannot supply their own cross-invocation authority.
"""
from fractions import Fraction as F
import hashlib
import math
from pathlib import Path

from research.chapter3_experiments.linked_ablation_execution import audit as legacy
from research.chapter3_experiments.h02_pair_preflight.receipts import (
    safe_receipt, technical_issues)


REPO = Path(__file__).resolve().parents[3]
ARMS = {"C", "HEFT", "SINGLE", "PAIR"}
C_PROTOCOL = "fresh-seed-n1-then-linked-opp-start-warm-closed-complement-live-scenes-v1"
GRAPH_RULE = "same-call-heft-related-opp-order-graph-v1"
NORMAL_C = {"NORMAL_COMPLETION", "NORMAL_TIME_LIMIT", "NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST"}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _call_identity_errors(identity, instance, config, root_seconds):
    errors = []
    if not isinstance(identity, dict):
        return ["WORKER_IDENTITY_REQUIRED"]
    for key in ("input_verified", "source_verified", "environment_verified", "scientific_call_started"):
        if identity.get(key) is not True:
            errors.append("WORKER_" + key.upper())
    if identity.get("not_scientific") is not False or identity.get("fresh_input_calls") != 1:
        errors.append("FAKE_OR_NONUNIQUE_INPUT_WORKER")
    if identity.get("input_sha256") != legacy.canonical(instance):
        errors.append("WORKER_INPUT_IDENTITY")
    if identity.get("config_sha256") != legacy.canonical(config):
        errors.append("WORKER_CONFIG_IDENTITY")
    start, end = identity.get("root_start_s"), identity.get("root_deadline_s")
    if (not _finite(start) or not _finite(end) or identity.get("root_limit_s") != root_seconds
            or end != start + float(root_seconds)):
        errors.append("WORKER_ROOT_IDENTITY")
    manifest = identity.get("source_sha256")
    if not isinstance(manifest, dict) or not manifest:
        errors.append("FROZEN_SOURCE_MANIFEST_REQUIRED")
    else:
        for name, expected in manifest.items():
            try:
                supplied = Path(name)
                if supplied.is_absolute():
                    raise ValueError("source path must be repository relative")
                path = (REPO / supplied).resolve()
                path.relative_to(REPO)
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    errors.append("FROZEN_SOURCE_DRIFT:" + name)
            except (OSError, TypeError, ValueError):
                errors.append("FROZEN_SOURCE_UNREADABLE:" + str(name))
    return errors


def _mock_records(value):
    """Only explicit fake labels count; physical L3 is not a fake backend."""
    if isinstance(value, dict):
        if value.get("state") == "MOCK_SAFE" or value.get("evidence_kind") == "MOCK_ONLY":
            return True
        if value.get("not_scientific") is True:
            return True
        return any(_mock_records(v) for v in value.values())
    return isinstance(value, list) and any(_mock_records(v) for v in value)


def _timing_errors(result, root_seconds):
    timing = result.get("timing")
    if (not isinstance(timing, dict) or timing.get("limit_s") != root_seconds
            or not _finite(timing.get("method_elapsed_s")) or timing["method_elapsed_s"] < 0):
        return ["METHOD_ROOT_TIMING"]
    return []


def _file_errors(identity, native_evidence, result, instance, config):
    """Bind byte hashes to current files, not a canonical hash of a snapshot."""
    if not isinstance(native_evidence, dict) or "folder" not in native_evidence:
        return ["CURRENT_SLOT_FOLDER_REQUIRED_FOR_FILE_BINDING"]
    errors = []
    try:
        folder = Path(native_evidence["folder"]).resolve()
        for name, key in (("result.json", "result_sha256"),
                          ("wrapper_raw_result.json", "raw_result_sha256")):
            path = folder / name
            if legacy.sha(path) != identity.get(key) or legacy.read(path) != result:
                errors.append("CURRENT_RESULT_FILE_BINDING:" + name)
        for name, value in (("input_instance.json", instance), ("input_config.json", config)):
            if legacy.read(folder / name) != value:
                errors.append("CURRENT_INPUT_FILE_BINDING:" + name)
        declaration_sha = identity.get("declaration_sha256")
        if (not isinstance(declaration_sha, str) or len(declaration_sha) != 64
                or any(c not in "0123456789abcdef" for c in declaration_sha)):
            errors.append("WORKER_DECLARATION_BYTE_HASH_REQUIRED")
    except (OSError, KeyError, TypeError, ValueError):
        errors.append("CURRENT_SLOT_EVIDENCE_UNREADABLE")
    return errors


def _simple_terminal(arm, result, root_seconds):
    elapsed = result.get("timing", {}).get("method_elapsed_s")
    timed_out = (_finite(elapsed) and elapsed >= root_seconds
                 and result.get("budget_exhausted") is True)
    if arm == "HEFT":
        if result.get("method") != "heft" or result.get("seed") is not None:
            return None, ["HEFT_METHOD_IDENTITY"]
        if result.get("reason") == "DECLARED_SEARCH_COMPLETED" and not timed_out:
            return "NORMAL_COMPLETION", []
        if result.get("reason") in ("wall_time_limit", "METHOD_BUDGET_EXHAUSTED") and timed_out:
            return "NORMAL_TIME_LIMIT", []
        return None, ["HEFT_TERMINAL_UNRESOLVED:" + str(result.get("reason"))]
    expected = "single" if arm == "SINGLE" else "pair"
    if (result.get("method") != "related_opp_order_graph" or result.get("variant") != expected
            or result.get("rule_version") != GRAPH_RULE or result.get("evidence_kind") != "REAL_CORE"):
        return None, ["GRAPH_METHOD_OR_BACKEND_IDENTITY"]
    if result.get("run_terminal") == "SEARCH_COMPLETED" and not timed_out:
        return "NORMAL_COMPLETION", []
    if result.get("run_terminal") == "BUDGET_EXHAUSTED" and timed_out:
        return "NORMAL_TIME_LIMIT", []
    if (result.get("run_terminal") == "UNRESOLVED_STOP"
            and result.get("reason") == "NO_COMPLETE_SAFE_HEFT_INITIALIZATION"
            and not timed_out):
        return "NORMAL_NO_COMPLETE_SAFE_SEED", []
    return None, ["GRAPH_TERMINAL_UNRESOLVED:" + str(result.get("run_terminal"))]


def _source_context_errors(context, result, identity, instance, config):
    errors = []
    if not isinstance(context, dict):
        return ["GRAPH_SAFE_CONTEXT_REQUIRED"]
    expected = {"input_sha256": legacy.canonical(instance),
        "config_sha256": legacy.canonical(config),
        "accuracy_sha256": legacy.canonical(config["accuracy_targets"]),
        "root_start": repr(identity["root_start_s"]),
        "root_deadline": repr(identity["root_deadline_s"]),
        "root_seconds": identity["root_limit_s"]}
    if any(context.get(k) != v for k, v in expected.items()):
        errors.append("GRAPH_SAFE_ROOT_OR_INPUT_CONTEXT")
    root = result.get("root_context", {})
    if not isinstance(context.get("root_token"), str) or not context["root_token"]:
        errors.append("GRAPH_ROOT_TOKEN_REQUIRED")
    if root != context:
        errors.append("GRAPH_SAFE_AND_CALL_CONTEXT_DIFFER")
    sources = context.get("source_sha256")
    if not isinstance(sources, dict) or not sources or sources != result.get("sources_sha256"):
        errors.append("GRAPH_SOURCE_CONTEXT_REQUIRED")
    else:
        frozen = identity["source_sha256"]
        for name, digest in sources.items():
            key = name if name.startswith("research/") else "research/" + name
            if frozen.get(key) != digest:
                errors.append("GRAPH_SOURCE_NOT_FROZEN:" + name)
    return errors


def _initialization_only_errors(result, candidate, receipt, terminal):
    """Recognize the actual method log schema before freeze_initial ran.

    CompleteRecorder labels observations/events with phase='initialization';
    graph proposals and phase='refinement' appear only after the initial SAFE
    freeze. A budget stop here preserves the HEFT observation without inventing
    a completed initialization or any joint-search contribution.
    """
    errors = []
    if ("initial_safe_snapshot" not in result or result["initial_safe_snapshot"] is not None
            or terminal != "NORMAL_TIME_LIMIT" or type(result.get("graph_strict_improvements")) is not int
            or result["graph_strict_improvements"] != 0
            or result.get("graph_proposals") != []
            or "first_graph_strict_improvement_at_s" not in result
            or result["first_graph_strict_improvement_at_s"] is not None):
        errors.append("GRAPH_MISSING_INITIAL_FREEZE_NOT_AN_INITIALIZATION_CUTOFF")
    observations, events = result.get("evaluations"), result.get("events")
    if (not isinstance(observations, list) or not observations
            or any(not isinstance(r, dict) or r.get("phase") != "initialization"
                   or not isinstance(r.get("source"), str) or not r["source"].startswith("heft:")
                   for r in observations)):
        errors.append("GRAPH_INITIALIZATION_ONLY_OBSERVATIONS_REQUIRED")
    elif not any(r.get("accepted_safe") is True and r.get("candidate") == candidate
                 and r.get("receipt") == receipt
                 and r.get("candidate_sha256") == legacy.canonical(candidate)
                 and r.get("context") == result.get("root_context") for r in observations):
        errors.append("GRAPH_INITIALIZATION_SAFE_OBSERVATION_NOT_BOUND")
    if (not isinstance(events, list)
            or any(not isinstance(e, dict) or e.get("phase") != "initialization" for e in events)):
        errors.append("GRAPH_INITIALIZATION_ONLY_EVENTS_REQUIRED")
    return errors


def _native_errors(result, native_evidence):
    """Require actual current-slot closure, or an explicit no-native-start proof."""
    if not isinstance(native_evidence, dict) or "folder" not in native_evidence:
        return ["C_CURRENT_NATIVE_EVIDENCE_REQUIRED"], None
    try:
        folder = Path(native_evidence["folder"]).resolve()
        native = folder / "method" / "matlab"
        if native_evidence.get("native_started") is False:
            if (result.get("matlab_worker_ready") is not False or native.exists()
                    or result.get("startup_metadata") or result.get("startup_cleanup")
                    or result.get("session_total_request_count", 0) != 0
                    or result.get("solver_request_attempts", 0) != 0):
                return ["C_NO_NATIVE_START_CONTRADICTED"], folder
            return [], folder
        if native_evidence.get("native_started") is not True:
            return ["C_NATIVE_START_STATUS_REQUIRED"], folder
        path = native / "closed.json"
        if not path.is_file():
            return ["C_CURRENT_CLOSED_FILE_REQUIRED"], folder
        closure = legacy.read(path)
        if closure != native_evidence.get("closure"):
            return ["C_CLOSURE_FILE_BINDING"], folder
        if (closure.get("cleanup_status") not in ("graceful_closed", "forced_closed")
                or not legacy.cleanup_ok(closure)):
            return ["C_NATIVE_ISOLATION_UNVERIFIED"], folder
        return [], folder
    except (OSError, TypeError, ValueError):
        return ["C_NATIVE_EVIDENCE_UNREADABLE"], None


def _c_errors(result, instance, config, identity, native_evidence, root_seconds, has_safe):
    errors = []
    native_errors, folder = _native_errors(result, native_evidence)
    errors.extend(native_errors)
    if result.get("protocol") != C_PROTOCOL or result.get("scene_slice_s") != 60:
        errors.append("C_METHOD_RECIPE_IDENTITY")
    common = identity.get("common")
    if (not isinstance(common, dict) or common.get("input_sha256") != legacy.canonical(instance)
            or common.get("config_sha256") != legacy.canonical(config)):
        return errors + ["C_FROZEN_COMMON_REQUIRED"], None, None, False
    condition = result.get("condition") or {}
    scene_records = result.get("scenes") or {}
    no_native_search = (not native_errors and isinstance(native_evidence, dict)
        and native_evidence.get("native_started") is False
        and not result.get("phases")
        and isinstance(scene_records, dict)
        and all(isinstance(s, dict) and not s.get("model_complete") and not s.get("solver_result")
            for s in scene_records.values()))
    attempts = result.get("seed_attempts")
    constructor_only = (not has_safe and not condition and no_native_search
        and result.get("reason") == "NO_COMPLETE_SAFE_LINKED_SEED"
        and isinstance(attempts, list) and 1 <= len(attempts) <= 3
        and all(isinstance(a, dict) and a.get("reason") == "CONSTRUCTION_UNRESOLVED"
            and a.get("state") == "UNRESOLVED" and a.get("scene_evaluations") == {}
            and a.get("aggregation") is None
            and isinstance(a.get("construction"), dict)
            and a["construction"].get("status") == "CONSTRUCTION_UNRESOLVED" for a in attempts))
    budget = identity.get("budget_identity")
    if (budget is None and "budget_identity" in identity and constructor_only):
        # _partial_identity creates the token lazily at the first scene call;
        # all constructors can fail before that call ever occurs. The worker's
        # separate strict start/deadline/limit is still checked unconditionally.
        pass
    elif not isinstance(budget, dict):
        errors.append("C_CALLER_BUDGET_IDENTITY_REQUIRED")
    else:
        try:
            if (not isinstance(budget.get("token"), str) or not budget["token"]
                    or float(budget["start"]) != identity["root_start_s"]
                    or float(budget["seconds"]) != root_seconds):
                errors.append("C_CALLER_ROOT_TOKEN_OR_ORIGIN")
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append("C_CALLER_BUDGET_IDENTITY_MALFORMED")
    elapsed = result.get("timing", {}).get("method_elapsed_s")
    pre_condition_safe_cutoff = (has_safe and not condition and no_native_search
        and result.get("reason") == "wall_time_limit" and result.get("budget_exhausted") is True
        and _finite(elapsed) and elapsed >= root_seconds and isinstance(budget, dict))
    if condition:
        if condition.get("budget_identity") != budget:
            errors.append("C_METHOD_ROOT_NOT_CALLER_ROOT")
        errors.extend(legacy._condition_issues(result, common, "C"))
    elif has_safe and not pre_condition_safe_cutoff:
        errors.append("C_SAFE_WITHOUT_CONDITION")
    terminal = None
    if folder is not None:
        terminal, terminal_errors, numerical, _ = legacy._terminal(result, folder)
        errors.extend(terminal_errors)
        errors.extend(numerical)
        # Seed construction can normally return before any session is started.
        # This is a method no-witness state, never all-domain infeasibility.
        no_seed = (not has_safe and result.get("reason") == "NO_COMPLETE_SAFE_LINKED_SEED"
            and result.get("matlab_worker_ready") is False
            and isinstance(result.get("seed_attempts"), list) and bool(result["seed_attempts"])
            and not result.get("search_failure_latched") and not terminal_errors and not numerical)
        if no_seed:
            terminal = "NORMAL_NO_COMPLETE_SAFE_SEED"
        elif terminal not in NORMAL_C:
            errors.append("C_TERMINAL_UNRESOLVED:" + str(terminal))
    if not has_safe:
        return errors, terminal, None, bool(condition)
    receipt = result.get("aggregation")
    if not isinstance(receipt, dict):
        return errors + ["C_COMPLETE_AGGREGATE_REQUIRED"], terminal, None, bool(condition)
    errors.extend(legacy.aggregate_issues(receipt, result["safe_candidate"], instance, config,
        common, budget, identity["source_sha256"]))
    for key in ("safe_candidate", "safe_upper_bound_J", "weighted_energy_J"):
        if result.get(key) != receipt.get(key):
            errors.append("C_TOP_AGGREGATE_MISMATCH:" + key)
    snapshot = result.get("committed_safe_snapshot") or {}
    if any(snapshot.get(k) != result.get(k) for k in ("safe_candidate", "safe_upper_bound_J", "weighted_energy_J")):
        errors.append("C_COMMITTED_SNAPSHOT_MISMATCH")
    if snapshot.get("aggregation") != receipt:
        errors.append("C_SNAPSHOT_AGGREGATE_MISMATCH")
    updates = result.get("global_updates") or []
    if (not updates or updates[-1].get("safe_upper_bound_J") != result.get("safe_upper_bound_J")
            or updates[-1].get("weighted_energy_J") != result.get("weighted_energy_J")):
        errors.append("C_COMPLETE_UPDATE_LEDGER_MISMATCH")
    return errors, terminal, receipt.get("weighted_energy_J"), bool(condition)


def admit_result(arm, result, instance, config, *, root_seconds=300,
                 identity=None, native_evidence=None):
    """Return a fail-closed view of existing evidence; never alter a raw result.

    ``identity`` is the new worker's observed, frozen call envelope.  For C it
    additionally supplies the declaration's exact ``common`` and the budget
    identity captured from the actual caller-owned object. ``native_evidence``
    binds the current output folder, actual ``native_started`` flag and original
    ``method/matlab/closed.json`` object; historical snapshots cannot replace it.
    """
    out = {"eligible_for_post": False, "normal_no_safe": False,
        "technical_failure": False, "admitted_interval": None,
        "candidate_sha256": None, "errors": [], "classification": None,
        "initialization_complete": None,
        "reported_U_J": result.get("safe_upper_bound_J") if isinstance(result, dict) else None,
        "new_candidate_or_energy": False, "independently_proven_infeasible": False,
        "independently_proven_optimal": False}
    errors = out["errors"]
    try:
        if arm not in ARMS:
            errors.append("UNRECOGNIZED_FROZEN_ARM")
        if type(root_seconds) not in (int, float) or not math.isfinite(root_seconds) or root_seconds != 300:
            errors.append("ONLY_DECLARED_300_SECOND_ROOT_SUPPORTED")
        if not isinstance(result, dict) or not isinstance(instance, dict) or not isinstance(config, dict):
            raise ValueError("result, instance and config must be dictionaries")
        if errors:
            raise ValueError("unsupported execution contract")
        errors.extend(_call_identity_errors(identity, instance, config, root_seconds))
        if isinstance(identity, dict):
            errors.extend(_file_errors(identity, native_evidence, result, instance, config))
            out.update(result_sha256=identity.get("result_sha256"),
                raw_result_sha256=identity.get("raw_result_sha256"),
                declaration_sha256=identity.get("declaration_sha256"),
                input_sha256=legacy.canonical(instance), config_sha256=legacy.canonical(config))
        errors.extend(_timing_errors(result, root_seconds))
        if _mock_records(result):
            errors.append("MOCK_OR_FAKE_RESULT_NOT_SCIENTIFIC")
        if technical_issues(result):
            errors.append("OBSERVED_TECHNICAL_OR_NUMERICAL_ERROR")
        if result.get("error") or result.get("cleanup_error") or result.get("fatal_error"):
            errors.append("METHOD_OR_CLEANUP_ERROR")
        if errors:
            raise ValueError("call identity or technical evidence failed")
        candidate, upper = result.get("safe_candidate"), result.get("safe_upper_bound_J")
        has_safe = candidate is not None and upper is not None
        if (candidate is None) != (upper is None) or (result.get("state") == "SAFE" and not has_safe):
            errors.append("INCONSISTENT_TOP_SAFE_FIELDS")
        if has_safe and result.get("state") != "SAFE":
            errors.append("TOP_STATE_NOT_SAFE")
        if arm == "C" and has_safe and result.get("rankable_energy") is not True:
            errors.append("C_TOP_ENERGY_NOT_RANKABLE")
        if result.get("problem_id") != instance.get("id"):
            errors.append("RESULT_PROBLEM_IDENTITY")
        if arm == "C":
            detail, terminal, values, initialization_complete = _c_errors(result, instance, config, identity,
                native_evidence, root_seconds, has_safe)
            errors.extend(detail)
            out["initialization_complete"] = initialization_complete
        else:
            terminal, detail = _simple_terminal(arm, result, root_seconds)
            errors.extend(detail)
            values = None
            if has_safe:
                if arm in ("SINGLE", "PAIR"):
                    if result.get("usable_as_research_evidence") is not True:
                        errors.append("GRAPH_RESULT_NOT_RESEARCH_ELIGIBLE")
                    errors.extend(_source_context_errors(result.get("safe_context"), result,
                        identity, instance, config))
                elif result.get("input_sha256") != legacy.canonical(instance):
                    errors.append("HEFT_RESULT_INPUT_IDENTITY")
                receipt = result.get("evaluation")
                checked = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], root_seconds)
                values = [checked["lower"], checked["upper"]]
                if receipt["completed_at_elapsed_s"] > result["timing"]["method_elapsed_s"]:
                    errors.append("SAFE_FORMED_AFTER_METHOD_RETURN")
                if F(upper) != F(values[1]):
                    errors.append("TOP_U_DIFFERS_FROM_COMPLETE_RECEIPT")
                if arm in ("SINGLE", "PAIR"):
                    initial = result.get("initial_safe_snapshot")
                    if not isinstance(initial, dict):
                        errors.extend(_initialization_only_errors(result, candidate, receipt, terminal))
                        out["initialization_complete"] = False
                    else:
                        out["initialization_complete"] = True
                        initial_energy = safe_receipt(instance, initial["candidate"], initial["receipt"],
                            config["accuracy_targets"], root_seconds)
                        if initial.get("context") != result.get("root_context"):
                            errors.append("GRAPH_INITIAL_CONTEXT_DRIFT")
                        count = result.get("graph_strict_improvements")
                        if type(count) is not int or count < 0:
                            errors.append("GRAPH_STRICT_COUNT_INVALID")
                        elif count == 0:
                            if (candidate != initial["candidate"] or
                                    tuple(map(F, values)) != (F(initial_energy["lower"]), F(initial_energy["upper"]))):
                                errors.append("GRAPH_CHANGED_WITHOUT_STRICT_UPDATE")
                        elif F(values[1]) >= F(initial_energy["lower"]):
                            errors.append("GRAPH_STRICT_UPDATE_NOT_CERTIFIED")
        out["classification"] = terminal
        if has_safe:
            legality = legacy.schedule_audit(instance, candidate)
            errors.extend("FINAL_" + x for x in legality["errors"])
            if values is None:
                errors.append("COMPLETE_SAFE_ENERGY_INTERVAL_REQUIRED")
            else:
                lo, hi = legacy.interval(values)
                if F(upper) != hi:
                    errors.append("ADMITTED_INTERVAL_UPPER_MISMATCH")
            if not errors:
                out.update(eligible_for_post=True,
                    admitted_interval=[str(lo), str(hi)],
                    candidate_sha256=legacy.canonical(candidate))
        elif not errors and terminal is not None:
            out["normal_no_safe"] = True
    except (OSError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError, OverflowError) as error:
        errors.append("ADMISSION_EXCEPTION:" + type(error).__name__ + ":" + str(error))
    if errors:
        out.update(technical_failure=True, eligible_for_post=False,
            normal_no_safe=False, admitted_interval=None, candidate_sha256=None)
    return out
