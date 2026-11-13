"""Transparent common evaluation accounting and read-only result metrics."""
from copy import deepcopy
from fractions import Fraction as F
import json

from research.chapter4_scheduler.mechanism_check.run import digest

CLOCK_ORIGIN = "one caller root before selected scientific imports, input, native initialization and evaluation; serialization separate"
ORDER = (("base__R2", "HEFT", None), ("base__R2", "SA", 101), ("base__R2", "ON", None),
         *(("base__R2", "SA", n) for n in (102, 103, 104, 105)),
         *(("base__R5", "SA", n) for n in (105, 104, 103, 102)),
         ("base__R5", "ON", None), ("base__R5", "SA", 101), ("base__R5", "HEFT", None))


class EvaluationJournal:
    """Same forwarding boundary for HEFT/ON/SA; never score or alter a receipt.

The launcher temporarily exposes this callable at thermal.evaluate_candidate
so existing REAL binding identity checks still compare the same object. The
captured underlying original function is always called with unchanged objects.
"""
    def __init__(self, evaluator, budget, stream=None):
        self.original, self.budget, self.stream = evaluator, budget, stream
        self.attempts = []

    def emit(self, event):
        if self.stream is not None:
            self.stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            self.stream.flush()

    def __call__(self, instance, candidate, accuracy, budget):
        if budget is not self.budget:
            raise ValueError("EVALUATOR_ROOT_CHANGED")
        row = {"ordinal": len(self.attempts) + 1, "candidate_sha256": digest(candidate),
               "started_at_s": budget.elapsed, "state": "STARTED"}
        self.attempts.append(row)
        self.emit({"event": "START", **row, "candidate": candidate})
        try:
            receipt = self.original(instance, candidate, accuracy, budget)
            row.update(state="RETURNED", returned_at_s=budget.elapsed,
                       receipt_state=receipt.get("state") if isinstance(receipt, dict) else None,
                       receipt_type=type(receipt).__name__)
            self.emit({"event": "RETURN", **row})
            return receipt
        except BaseException as error:
            row.update(state="INTERRUPTED", returned_at_s=budget.elapsed,
                       error_type=type(error).__name__, reason=str(error))
            self.emit({"event": "INTERRUPTED", **row})
            raise


def canonical_terminal(result):
    terminal = result.get("run_terminal")
    if terminal in ("SEARCH_COMPLETED", "NORMAL_NO_SAFE"):
        return "SEARCH_COMPLETED" if result.get("safe_candidate") is not None else "NORMAL_NO_SAFE"
    if terminal == "BUDGET_EXHAUSTED":
        return terminal
    if (terminal == "UNRESOLVED_STOP" and result.get("reason") == "INITIALIZATION_NOT_COMPLETED"
            and (result.get("initialization") or {}).get("status") == "NO_SAFE_CONSTRUCTED_WITNESS"
            and result.get("safe_candidate") is None
            and all(r["receipt"]["state"] == "THERMAL_VIOLATION" for r in result.get("evaluations", []))):
        return "NORMAL_NO_SAFE"
    return "NUMERICAL_STOP" if result.get("reason") == "NUMERICAL_UNRESOLVED" else "TECHNICAL_STOP"


def safe_rows(result):
    return [r for r in result.get("evaluations", []) if r.get("accepted_safe")]


def normalize(result, journal):
    """No new physical evaluation; all SAFE acceptance comes from recorder."""
    attempts = journal.attempts
    physical_rows = [r for r in result.get("evaluations", []) if not r.get("cache_hit", False)]
    returned = [a for a in attempts if a["state"] == "RETURNED"]
    if len(physical_rows) != len(returned):
        raise ValueError("RETURNED_RECEIPT_ACCOUNTING_MISMATCH")
    if [r["candidate_sha256"] for r in physical_rows] != [a["candidate_sha256"] for a in returned]:
        raise ValueError("RETURNED_CANDIDATE_ACCOUNTING_MISMATCH")
    safe = safe_rows(result)
    first = min(safe, key=lambda r: r["receipt"]["completed_at_elapsed_s"]) if safe else None
    final = result.get("evaluation")
    final_upper = F(final["weighted_energy_J"][1]) if final else None
    strict = [r["receipt"]["completed_at_elapsed_s"] for r in safe
              if first is not None and F(r["energy"]["upper"]) < F(first["energy"]["lower"])]
    own_final = [r["receipt"]["completed_at_elapsed_s"] for r in safe
                 if final_upper is not None and F(r["energy"]["upper"]) <= final_upper]
    if final is not None and not own_final:
        raise ValueError("FINAL_SAFE_HAS_NO_VALIDATED_HISTORY")
    timing = deepcopy(result["timing"])
    timing["clock_origin"] = CLOCK_ORIGIN
    return {"schema": "chapter4-comparison-unified-v1", "terminal": canonical_terminal(result),
        "raw_terminal": result.get("run_terminal"), "raw_reason": result.get("reason"),
        "has_SAFE_archive": result.get("safe_candidate") is not None,
        "energy_interval_J": deepcopy(final["weighted_energy_J"]) if final else None,
        "safe_upper_bound_J": result.get("safe_upper_bound_J"),
        "counts": {"evaluation_attempts": len(attempts), "returned_receipts": len(returned),
            "interrupted_attempts": sum(a["state"] == "INTERRUPTED" for a in attempts),
            "returned_SAFE_claims": sum(a.get("receipt_state") == "SAFE" for a in returned),
            "validated_SAFE_receipts": sum(r.get("accepted_safe", False) for r in physical_rows),
            "returned_thermal_violation_receipts": sum(a.get("receipt_state") == "THERMAL_VIOLATION" for a in returned),
            "returned_unresolved_receipts": sum(a.get("receipt_state") == "UNRESOLVED" for a in returned),
            "unique_candidates_evaluated": len({a["candidate_sha256"] for a in attempts}),
            "cache_hits": result.get("cache_hits", 0)},
        "first_SAFE_at_s": first["receipt"]["completed_at_elapsed_s"] if first else None,
        "first_strict_improvement_over_first_SAFE_at_s": min(strict) if strict else None,
        "first_own_final_quality_at_s": min(own_final) if own_final else None,
        "best_SAFE_formed_at_s": final.get("completed_at_elapsed_s") if final else None,
        "initial_safe_snapshot_sha256": (result.get("initial_safe_snapshot") or {}).get("candidate_sha256"),
        "initialization_phase_records": [deepcopy(p) for p in timing["phase_records"]
             if p["phase"] in ("heft_initialization", "complete_initial_safe_freeze")],
        "SA_initialization_note": "First SAFE and first neighbour request are observables, not exact initialization completion" if result.get("search") else None,
        "first_neighbour_assessment_at_s": result.get("first_neighbour_assessment_at_s"),
        "native_search_metadata": deepcopy(result.get("search")), "timing": timing,
        "normal_stop": canonical_terminal(result) in ("SEARCH_COMPLETED", "BUDGET_EXHAUSTED", "NORMAL_NO_SAFE")}


def time_to_quality(result, upper):
    times = [r["receipt"]["completed_at_elapsed_s"] for r in safe_rows(result)
             if F(r["energy"]["upper"]) <= F(upper)]
    return min(times) if times else None


def conditional_statistics(values, planned):
    ordered = sorted(F(v) for v in values)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2 if n else None
    return {"SAFE_post_successes": n, "planned_runs": planned, "success_rate": n / planned,
        "energy_upper_J_median_among_successes": str(median) if median is not None else None,
        "energy_upper_J_range_among_successes": [str(ordered[0]), str(ordered[-1])] if n else None,
        "interpretation": "Conditional on valid SAFE and successful post; all seeds/failures retained separately; never best-of-five as one run"}
