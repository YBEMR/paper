"""Minimal original-SA lifecycle with full receipts and mutable deployment.

The unchanged run_sa owns its RNG, native initialization, mutations, uphill
current state and cooling. This module only validates/records full receipts,
keeps the best SAFE upper bound, and preserves the caller's single deadline.
It selects no research case, authorizes no comparison and creates no batch.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import math
from pathlib import Path

from research.chapter4_scheduler.blocking import method as common


@dataclass(frozen=True)
class SABindings:
    search: object
    evaluator: object
    kind: str = "MOCK_ONLY"


def source_identity():
    sources = common.source_identity()
    research = Path(__file__).resolve().parents[2]
    for path in (Path(__file__), research / "chapter3_experiments/sa_method.py",
                 research / "chapter3_experiments/heuristic_common.py"):
        sources[path.relative_to(research).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


class SARecorder(common.CompleteRecorder):
    """Inherit exact complete-evidence gates; never freeze SA deployment.

``best`` is the archive, not run_sa's current state. All valid SAFE receipts,
including more expensive ones, are returned unchanged to the original SA.
The inherited graph recorder's ``current`` remains None, so its fixed-unit
gate never applies. Cross-scene shared deployment is still validated normally.
"""
    def __init__(self, instance, config, budget, bindings, sources):
        super().__init__(instance, config, budget, bindings, sources)
        self.phase = "sa"
        self.root_clock = budget.clock
        self.requests = []
        self.evaluator_attempts = []
        self.first_neighbour_assessment_s = None
        self.first_strict_best_improvement_s = None
        # Count the actual evaluator boundary, including calls that raise
        # without returning a receipt. Legality failures and cache hits do
        # not cross this boundary. The original evaluator/arguments/return
        # are forwarded unchanged; no RNG or search decision occurs here.
        def evaluate(*args, **kwargs):
            attempt = {"candidate_sha256": common.digest(args[1]),
                "source": self.requests[-1]["source"], "started_at_s": budget.elapsed,
                "state": "STARTED"}
            self.evaluator_attempts.append(attempt)
            try:
                receipt = bindings.evaluator(*args, **kwargs)
                attempt.update(state="RETURNED", returned_at_s=budget.elapsed,
                    receipt_state=receipt.get("state") if isinstance(receipt, dict) else None)
                return receipt
            except BaseException as error:
                attempt.update(state="INTERRUPTED", returned_at_s=budget.elapsed,
                    error_type=type(error).__name__, reason=str(error))
                raise
        self.bindings = SABindings(bindings.search, evaluate, bindings.kind)

    def check_context(self):
        if (self.current is not None or self.budget.clock is not self.root_clock
                or common.digest(self.instance) != self.context["input_sha256"]
                or common.digest(self.config) != self.context["config_sha256"]
                or common.digest(self.accuracy) != self.context["accuracy_sha256"]
                or repr(self.budget.start) != self.context["root_start"]
                or repr(self.budget.deadline) != self.context["root_deadline"]
                or self.budget.seconds != self.context["root_seconds"]
                or source_identity() != self.sources):
            raise common.SearchStop("SA_CALL_CONTEXT_DRIFT")

    def freeze_initial(self):
        raise common.SearchStop("SA_DEPLOYMENT_MUST_NOT_BE_FROZEN")

    def _commit(self, row):
        previous = self.best
        accepted = previous is None or F(row["energy"]["upper"]) < F(previous["energy"]["upper"])
        row["best_archive_replaced"] = accepted
        # Compatibility field inherited from the common receipt row schema;
        # this says nothing about SA's internal current-state acceptance.
        row["incumbent_replaced"] = accepted
        if self.first_safe_s is None:
            self.first_safe_s = row["receipt"]["completed_at_elapsed_s"]
        if accepted:
            self.best = deepcopy(row)
            at = row["receipt"]["completed_at_elapsed_s"]
            self.events.append({"event": "best_SAFE_upper_bound", "phase": "sa", "at_s": at,
                "transferred_at_s": self.budget.elapsed, "candidate_sha256": row["candidate_sha256"],
                "energy": deepcopy(row["energy"])})
            if previous is not None and F(row["energy"]["upper"]) < F(previous["energy"]["lower"]):
                if self.first_strict_best_improvement_s is None:
                    self.first_strict_best_improvement_s = at
        if self.initial is None:
            self.initial = deepcopy(row)  # First native-SA complete SAFE receipt only.

    def assess(self, candidate, source):
        self.budget.check()
        if source.startswith("sa_neighbour_") and self.first_neighbour_assessment_s is None:
            self.first_neighbour_assessment_s = self.budget.elapsed
        request = {"source": source, "candidate": deepcopy(candidate),
            "candidate_sha256": common.digest(candidate), "started_at_s": self.budget.elapsed,
            "state": "STARTED"}
        self.requests.append(request)
        try:
            receipt = super().assess(candidate, source)
            request.update(state="RETURNED", receipt_state=receipt.get("state"), returned_at_s=self.budget.elapsed)
            return receipt
        except BaseException as error:
            request.update(state="INTERRUPTED_OR_REJECTED", error_type=type(error).__name__,
                reason=str(error), returned_at_s=self.budget.elapsed)
            raise


def execute_sa(input_loader, workdir, *, seed, budget, bindings=None):
    """Run original SA once on a supplied (0,300]s caller root, never reset it.

Short roots support explicitly labelled engineering smoke checks. A future
formal comparison must separately freeze its declared 300s budget and seed.
"""
    from timing import MethodBudget
    from thermal import Exhausted
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Original SA requires an explicit integer seed")
    if (not isinstance(budget, MethodBudget) or isinstance(budget.seconds, bool)
            or not math.isfinite(budget.seconds) or not 0 < budget.seconds <= 300
            or budget.deadline != budget.start + float(budget.seconds)):
        raise ValueError("One original caller-owned root in (0,300] seconds is required")
    budget.check()
    root = (budget.start, budget.deadline, budget.seconds, budget.clock)
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    result = {"method": "original_shared_deployment_SA_full_receipt_adapter", "seed": seed,
        "state": "UNRESOLVED", "run_terminal": None, "reason": None, "safe_candidate": None,
        "safe_upper_bound_J": None, "evaluation": None, "search": None,
        "initial_safe_snapshot": None, "initialization_completed": False,
        "coverage_complete": False, "independently_proven_optimal": False,
        "independently_proven_infeasible": False, "usable_as_research_evidence": False,
        "formal_comparison_result": False, "candidate_or_cache_shared_between_calls": False,
        "archive_semantics": "best validated SAFE upper endpoint; SA internal current may be worse",
        "scope": "Reusable lifecycle only; no input selection or experimental authorization"}
    recorder = instance = config = None
    try:
        with budget.phase("SA_imports_input_and_context"):
            from sa_method import run_sa, algorithm_parameters
            from thermal import evaluate_candidate
            from auto_heuristic_policy import require_heuristic_control
            if bindings is None:
                bindings = SABindings(run_sa, evaluate_candidate, "REAL_CORE")
            if not isinstance(bindings, SABindings) or bindings.kind not in ("MOCK_ONLY", "REAL_CORE"):
                raise ValueError("Explicit original or MOCK_ONLY SA bindings required")
            if not callable(bindings.search) or not callable(bindings.evaluator):
                raise ValueError("Callable original search and evaluator required")
            if bindings.kind == "REAL_CORE" and (bindings.search is not run_sa or bindings.evaluator is not evaluate_candidate):
                raise ValueError("Real SA must use unchanged run_sa and evaluate_candidate")
            result.update(evidence_kind=bindings.kind, parameters=algorithm_parameters())
            config, instance = input_loader(budget)
            require_heuristic_control(instance, config, "Original SA adapter", allow_auto_low=True)
            recorder = SARecorder(instance, config, budget, bindings, source_identity())
            result.update(problem_id=instance["id"], input_sha256=common.digest(instance),
                root_context=deepcopy(recorder.context), sources_sha256=deepcopy(recorder.sources))
        with budget.phase("original_SA_native_initialization_and_search"):
            result["search"] = bindings.search(instance, config, budget, recorder.assess, seed=seed, allow_auto_low=True)
        recorder.check_context()
        if result["search"] is None or not isinstance(result["search"], dict):
            raise common.SearchStop("MALFORMED_SA_METADATA")
        if bindings.kind == "REAL_CORE" and result["search"].get("parameters") != result["parameters"]:
            raise common.SearchStop("SA_PARAMETER_DRIFT")
        if (budget.start, budget.deadline, budget.seconds, budget.clock) != root:
            raise common.SearchStop("SA_ROOT_RESET")
        exhausted = budget.elapsed >= budget.seconds or result["search"].get("stop_reason") == "METHOD_BUDGET_EXHAUSTED"
        result.update(run_terminal="BUDGET_EXHAUSTED" if exhausted else "SEARCH_COMPLETED",
            reason="METHOD_BUDGET_EXHAUSTED" if exhausted else "DECLARED_SA_STOP")
    except Exhausted:
        result.update(run_terminal="BUDGET_EXHAUSTED", reason="METHOD_BUDGET_EXHAUSTED")
    except common.SearchStop as error:
        reason = str(error)
        result.update(run_terminal="BUDGET_EXHAUSTED" if reason == "SAFE_FORMED_AFTER_DEADLINE" and budget.elapsed >= budget.seconds else
            "UNRESOLVED_STOP" if reason == "NUMERICAL_UNRESOLVED" else "TECHNICAL_STOP", reason=reason)
    except Exception as error:
        result.update(run_terminal="TECHNICAL_STOP", reason="INTERFACE_ERROR", error=f"{type(error).__name__}: {error}")
    stopped = budget.elapsed
    result.update(timing=budget.summary(stopped), budget_exhausted=stopped >= budget.seconds)
    result["timing"]["clock_origin"] = "unchanged caller root before imports, input and all native SA work"
    if recorder is not None:
        best = recorder.best
        if best is not None:
            result.update(state="MOCK_SAFE" if bindings.kind == "MOCK_ONLY" else "SAFE",
                safe_candidate=deepcopy(best["candidate"]), safe_upper_bound_J=best["energy"]["upper"],
                evaluation=deepcopy(best["receipt"]), safe_context=deepcopy(best["context"]))
        result.update(initial_safe_snapshot=deepcopy(recorder.initial), evaluations=deepcopy(recorder.rows),
            candidate_requests=deepcopy(recorder.requests), events=deepcopy(recorder.events), violations=deepcopy(recorder.violations),
            evaluator_attempts=deepcopy(recorder.evaluator_attempts),
            cache_hits=recorder.cache_hits, candidate_count=len(recorder.requests),
            full_evaluator_calls=len(recorder.evaluator_attempts),
            returned_evaluator_receipts=sum(a["state"] == "RETURNED" for a in recorder.evaluator_attempts),
            first_safe_at_s=recorder.first_safe_s, first_neighbour_assessment_at_s=recorder.first_neighbour_assessment_s,
            first_strict_best_improvement_at_s=recorder.first_strict_best_improvement_s,
            initialization_completed=bool((result.get("search") or {}).get("initialisation_source")),
            usable_as_research_evidence=bindings.kind == "REAL_CORE" and best is not None
                and result["run_terminal"] in ("SEARCH_COMPLETED", "BUDGET_EXHAUSTED"))
    archive_started = budget.clock()
    result = common.original._archivable(result)
    common.original._save(workdir / "result.json", result)
    if instance is not None:
        common.original._save(workdir / "input_instance.json", recorder.frozen_instance if recorder else instance)
    if config is not None:
        common.original._save(workdir / "input_config.json", recorder.frozen_config if recorder else config)
    common.original._save(workdir / "archive_timing.json", {"wall_s": budget.clock() - archive_started,
        "scope": "serialization only; no new search or physical evidence"})
    return result


def dispatch_with_sa(arm, loader, workdir, budget, *, seed=None, bindings=None):
    """Explicit four-arm API, without changing the old six-slot batch/claims."""
    if arm == "SA":
        return execute_sa(loader, workdir, seed=seed, budget=budget, bindings=bindings)
    if arm not in ("HEFT", "OFF", "ON") or seed is not None:
        raise ValueError("Known arm and SA-only explicit seed required")
    if bindings is None:
        from heft_method import run_heft
        from thermal import evaluate_candidate
        bindings = common.Bindings(run_heft, evaluate_candidate, "REAL_CORE")
    from .run import dispatch
    return dispatch(arm, loader, workdir, budget, bindings)
