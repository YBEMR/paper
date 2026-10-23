"""One-root HEFT initialization and strict, complete-SAFE graph refinement.

No experiment or workload is selected here. Real backends must be supplied
explicitly; this stage only exercises MOCK_ONLY bindings. The existing physical
model, HEFT rules and continuous evaluator are not modified.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction as F
from itertools import product
import hashlib
import json
import math
from pathlib import Path
import time
import uuid


RULE_VERSION = "same-call-heft-related-opp-order-graph-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Bindings:
    initializer: object
    evaluator: object
    kind: str = "MOCK_ONLY"


class SearchStop(Exception):
    """Keep previous complete evidence while stopping a non-budget failure."""


def source_identity():
    here = Path(__file__).resolve().parent
    legacy = here.parent / "chapter3_experiments"
    files = [Path(__file__), here / "graph_core.py"] + [legacy / n for n in (
        "heft_method.py", "heuristic_runner.py", "schedules.py", "start_domain.py",
        "control_policy.py", "auto_heuristic_policy.py", "thermal.py", "timing.py",
        "h02_pair_preflight/receipts.py", "h02_pair_preflight/common.py")]
    files.append(here.parent / "v1_evaluator/interval.py")
    return {str(p.relative_to(here.parent)).replace("\\", "/"):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def _timely(value, budget):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and 0 <= value < budget.seconds
        and value <= budget.elapsed)


class CompleteRecorder:
    """Reuse the existing full receipt contract, with call-local ownership.

    HEFT's best-upper semantics are retained during initialization. Afterwards,
    observations and the strict incumbent are distinct: overlapping intervals
    can never replace the incumbent. Audit/transfer of an already formed receipt
    precedes the outer expiry check; no new physical calculation follows expiry.
    """
    def __init__(self, instance, config, budget, bindings, sources):
        from h02_pair_preflight.receipts import safe_receipt, thermal_witness, technical_issues
        self.safe_receipt = safe_receipt
        self.thermal_witness = thermal_witness
        self.technical_issues = technical_issues
        self.instance, self.config = instance, config
        self.frozen_instance, self.frozen_config = deepcopy(instance), deepcopy(config)
        self.accuracy = deepcopy(config["accuracy_targets"])
        self.budget, self.bindings = budget, bindings
        self.sources = deepcopy(sources)
        self.context = {"input_sha256": digest(instance), "config_sha256": digest(config),
            "accuracy_sha256": digest(self.accuracy), "source_sha256": deepcopy(sources),
            "root_token": uuid.uuid4().hex, "root_start": repr(budget.start),
            "root_deadline": repr(budget.deadline), "root_seconds": budget.seconds}
        self.cache, self.rows, self.events, self.violations = {}, [], [], []
        self.best = self.current = self.initial = None
        self.phase = "initialization"
        self.first_safe_s = self.first_strict_s = None
        self.cache_hits = 0
        self.initializer_meta = None

    def check_context(self):
        if (digest(self.instance) != self.context["input_sha256"]
                or digest(self.config) != self.context["config_sha256"]
                or digest(self.accuracy) != self.context["accuracy_sha256"]
                or repr(self.budget.start) != self.context["root_start"]
                or repr(self.budget.deadline) != self.context["root_deadline"]
                or self.budget.seconds != self.context["root_seconds"]
                or source_identity() != self.sources):
            raise SearchStop("CALL_CONTEXT_DRIFT")

    def _commit(self, row):
        energy = row["energy"]
        if self.phase == "initialization":
            accepted = self.best is None or F(energy["upper"]) < F(self.best["energy"]["upper"])
            row["incumbent_replaced"] = accepted
            if accepted:
                self.best = deepcopy(row)
        else:
            accepted = F(energy["upper"]) < F(self.current["energy"]["lower"])
            row["incumbent_replaced"] = accepted
            if accepted:
                self.current = deepcopy(row)
        if self.first_safe_s is None:
            self.first_safe_s = row["receipt"]["completed_at_elapsed_s"]
        if accepted:
            at = row["receipt"]["completed_at_elapsed_s"]
            self.events.append({"phase": self.phase, "at_s": at,
                "transferred_at_s": self.budget.elapsed,
                "candidate_sha256": row["candidate_sha256"], "energy": deepcopy(energy)})
            if self.phase == "refinement" and self.first_strict_s is None:
                self.first_strict_s = at

    def freeze_initial(self):
        self.budget.check()
        self.check_context()
        if self.best is None:
            raise SearchStop("NO_COMPLETE_SAFE_HEFT_INITIALIZATION")
        self.initial = deepcopy(self.best)
        self.current = deepcopy(self.best)
        self.phase = "refinement"
        self.budget.check()

    def assess(self, candidate, source):
        from schedules import validate_schedule
        self.budget.check()
        self.check_context()
        supplied = deepcopy(candidate)
        identity = digest(supplied)
        with self.budget.phase("complete_legality"):
            legal = validate_schedule(self.instance, supplied)
        self.budget.check()
        if legal.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
            raise SearchStop("PROPOSED_CANDIDATE_NOT_LEGAL")
        if self.current is not None:
            fixed = self.current["shared_deployment"]
            if legal["shared_deployment"] != fixed:
                raise SearchStop("FIXED_DEPLOYMENT_DRIFT")
        if identity in self.cache:
            self.cache_hits += 1
            receipt = deepcopy(self.cache[identity])
        else:
            ei, ec, ea = deepcopy(self.instance), deepcopy(supplied), deepcopy(self.accuracy)
            before = (digest(ei), digest(ec), digest(ea))
            with self.budget.phase("complete_continuous_evaluation"):
                receipt = self.bindings.evaluator(ei, ec, ea, self.budget)
            # Archive returned evidence before checks that may stop the method.
            row = {"source": source, "phase": self.phase, "candidate": supplied,
                "candidate_sha256": identity, "receipt": deepcopy(receipt),
                "returned_at_s": self.budget.elapsed, "accepted_safe": False,
                "incumbent_replaced": False, "context": deepcopy(self.context)}
            self.rows.append(row)
            if before != (digest(ei), digest(ec), digest(ea)):
                raise SearchStop("EVALUATOR_ARGUMENT_MUTATION")
            self.check_context()
            if not isinstance(receipt, dict):
                raise SearchStop("MALFORMED_RECEIPT")
            issues = self.technical_issues(receipt)
            if (not issues and receipt.get("state") != "SAFE" and not receipt.get("violations")
                    and receipt.get("budget_exhausted") is True
                    and self.budget.elapsed >= self.budget.seconds):
                # The evaluator may hit the deadline at its first checkpoint,
                # before a receipt identity or legality section is formed.
                self.budget.check()
            if (receipt.get("problem_id") != self.instance["id"]
                    or receipt.get("evidence_identity") != {
                        "input_sha256": self.context["input_sha256"],
                        "candidate_sha256": identity}):
                raise SearchStop("RECEIPT_INPUT_OR_CANDIDATE_IDENTITY")
            if receipt.get("legality") != legal:
                raise SearchStop("RECEIPT_LEGALITY_MISMATCH")
            witnessed = []
            if receipt.get("violations"):
                witnessed = self.thermal_witness(self.instance, receipt, self.budget.seconds)
                if any(not _timely(v.get("formed_at_elapsed_s"), self.budget) for v in witnessed):
                    raise SearchStop("INVALID_VIOLATION_TIMESTAMP")
                self.violations.extend(deepcopy(witnessed))
            if receipt.get("state") == "SAFE":
                formed = receipt.get("completed_at_elapsed_s")
                if (not isinstance(formed, (int, float)) or isinstance(formed, bool)
                        or not math.isfinite(formed) or formed < 0 or formed > self.budget.elapsed):
                    row["rejection_reason"] = "INVALID_SAFE_TIMESTAMP"
                    raise SearchStop("INVALID_SAFE_TIMESTAMP")
                if formed >= self.budget.seconds:
                    row["rejection_reason"] = "SAFE_FORMED_AFTER_DEADLINE"
                    raise SearchStop("SAFE_FORMED_AFTER_DEADLINE")
                energy = self.safe_receipt(self.instance, supplied, receipt,
                    self.accuracy, self.budget.seconds)
                row.update(accepted_safe=True, energy=energy,
                    shared_deployment=deepcopy(legal["shared_deployment"]))
                self._commit(row)
                self.cache[identity] = deepcopy(receipt)
            elif receipt.get("state") == "THERMAL_VIOLATION" and witnessed:
                self.cache[identity] = deepcopy(receipt)
            elif not issues:
                raise SearchStop("NUMERICAL_UNRESOLVED")
            if issues:
                raise SearchStop("TECHNICAL_RECEIPT_ERROR")
            self.budget.check()
            return deepcopy(receipt)
        # Cached observations belong to this exact call, input and accuracy.
        if receipt.get("state") == "SAFE":
            energy = self.safe_receipt(self.instance, supplied, receipt,
                self.accuracy, self.budget.seconds)
            row = {"source": source, "phase": self.phase, "candidate": supplied,
                "candidate_sha256": identity, "receipt": deepcopy(receipt),
                "returned_at_s": self.budget.elapsed, "accepted_safe": True,
                "incumbent_replaced": False, "energy": energy, "cache_hit": True,
                "shared_deployment": deepcopy(legal["shared_deployment"]),
                "context": deepcopy(self.context)}
            self.rows.append(row)
            self._commit(row)
        self.budget.check()
        return deepcopy(receipt)


def candidate_packets(instance, incumbent, budget, *, variant="pair"):
    """Enumerate structural fixture/real candidates only when a caller runs it.

    There is no historic-answer reader. Ranking is exact NONTHERMAL energy,
    never a true-energy lower bound or an exclusion test.
    """
    from .graph_core import related_pairs, reconstruct
    if variant not in ("pair", "single"):
        raise ValueError("unknown graph variant")
    if variant == "pair":
        actions = related_pairs(instance, incumbent, budget=budget)
    else:
        actions = [{"scene_id": sid, "stage_ids": [row["stage_id"]]}
            for sid, rows in sorted(incumbent["scenes"].items())
            for row in sorted(rows, key=lambda r: r["stage_id"])]
    scenes = {s["id"]: s for s in instance["scenarios"]}
    for action in actions:
        budget.check()
        sid, selected = action["scene_id"], action["stage_ids"]
        rows = {r["stage_id"]: r for r in incumbent["scenes"][sid]}
        stages = {s["id"]: s for s in scenes[sid]["stage_instances"]}
        choices = [sorted(m["opp_id"] for m in instance["stage_modes"][stages[i]["shared_stage_id"]]
            if m["unit_id"] == rows[i]["unit"]) for i in selected]
        pending, seen = [], set()
        for mode_tuple in product(*choices):
            for orientation in (("incumbent", "reverse") if len(selected) == 2 else ("incumbent",)):
                for template in ("earliest", "preserve"):
                    budget.check()
                    with budget.phase("graph_construct_and_rank"):
                        built = reconstruct(instance, incumbent, sid, selected,
                            dict(zip(selected, mode_tuple)), orientation=orientation,
                            template=template, budget=budget)
                    if built["state"] != "COMPLETE_LEGAL_CANDIDATE":
                        continue
                    key = digest(built["candidate"])
                    if key in seen:
                        continue
                    seen.add(key)
                    pending.append(built)
        with budget.phase("nonthermal_ranking"):
            pending.sort(key=lambda b: (F(b["nonthermal_energy_J"]), digest(b["candidate"])))
        for packet in pending:
            budget.check()
            yield packet


def _archivable(value):
    """Represent invalid raw diagnostics without laundering them into scalars.

    This is serialization after stop, never receipt repair or acceptance.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_nonfinite_float": repr(value)}
    if isinstance(value, dict):
        return {k: _archivable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_archivable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"invalid_nonjson_type": type(value).__name__, "representation": repr(value)}


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n", encoding="utf-8")


def execute_reconstruction(input_loader, workdir, *, bindings, seconds=300,
                           clock=time.monotonic, variant="pair"):
    """Reusable method interface, not a research launcher or budget grant.

    A separate, approved one-shot launcher remains necessary for real research.
    Supplying test backends always produces MOCK_ONLY, nonresearch outputs.
    """
    entered = clock()
    from timing import MethodBudget
    from thermal import Exhausted
    if isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError("one finite root budget in (0,300] is required")
    budget = MethodBudget(seconds, clock=clock)
    budget.start, budget.deadline = entered, entered + float(seconds)
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    result = {"method": "related_opp_order_graph", "rule_version": RULE_VERSION,
        "variant": variant, "state": "UNRESOLVED", "run_terminal": None,
        "reason": None, "safe_candidate": None, "safe_upper_bound_J": None,
        "evaluation": None, "coverage_complete": False,
        "independently_proven_optimal": False, "independently_proven_infeasible": False,
        "evidence_kind": getattr(bindings, "kind", "UNCONFIGURED"),
        "usable_as_research_evidence": False, "candidate_or_cache_shared_between_calls": False}
    config = instance = recorder = None
    proposals, graph_accepted = [], 0
    try:
        with budget.phase("input_imports_and_context"):
            if not isinstance(bindings, Bindings) or bindings.kind not in ("MOCK_ONLY", "REAL_CORE"):
                raise ValueError("explicit recognized backend bindings required")
            if variant not in ("pair", "single"):
                raise ValueError("unknown graph variant")
            from auto_heuristic_policy import require_heuristic_control
            if bindings.kind == "REAL_CORE":
                from heft_method import run_heft
                from thermal import evaluate_candidate
                if bindings.initializer is not run_heft or bindings.evaluator is not evaluate_candidate:
                    raise ValueError("real backends must be the unchanged HEFT and complete evaluator")
            if not callable(bindings.initializer) or not callable(bindings.evaluator):
                raise ValueError("callable initializer and evaluator required")
            config, instance = input_loader(budget)
            require_heuristic_control(instance, config, "Graph reconstruction", allow_auto_low=True)
            weights = [F(s["weight"]) for s in instance["scenarios"]]
            if any(w < 0 for w in weights) or sum(weights) != 1:
                raise ValueError("nonnegative scene weights summing to one required")
            sources = source_identity()
            recorder = CompleteRecorder(instance, config, budget, bindings, sources)
            result.update(input_sha256=digest(instance), sources_sha256=sources,
                problem_id=instance["id"], root_context=deepcopy(recorder.context))
        with budget.phase("heft_initialization"):
            recorder.initializer_meta = bindings.initializer(instance, config, budget,
                recorder.assess, allow_auto_low=True)
        with budget.phase("complete_initial_safe_freeze"):
            recorder.freeze_initial()
        seen = set(recorder.cache)
        while True:
            budget.check()
            recorder.check_context()
            base = digest(recorder.current["candidate"])
            improved = False
            for packet in candidate_packets(instance, recorder.current["candidate"], budget, variant=variant):
                budget.check()
                key = digest(packet["candidate"])
                if key in seen:
                    continue
                event = {k: deepcopy(v) for k, v in packet.items() if k != "candidate"}
                event.update(base_candidate_sha256=base, candidate_sha256=key,
                    proposed_at_s=budget.elapsed, strict_accepted=False)
                proposals.append(event)
                try:
                    recorder.assess(packet["candidate"], "graph:" + variant)
                finally:
                    # A complete pre-deadline receipt may be transferred just
                    # before the outer expiry check raises. Count the saved
                    # incumbent without evaluating or constructing anything new.
                    event["strict_accepted"] = digest(recorder.current["candidate"]) != base
                    if event["strict_accepted"]:
                        graph_accepted += 1
                seen.add(key)
                if event["strict_accepted"]:
                    improved = True
                    break  # Regenerate relationships from the new full SAFE.
            if not improved:
                break
        result.update(run_terminal="SEARCH_COMPLETED", reason="NO_FURTHER_DECLARED_IMPROVEMENT")
    except Exhausted:
        result.update(run_terminal="BUDGET_EXHAUSTED", reason="METHOD_BUDGET_EXHAUSTED")
    except SearchStop as error:
        reason = str(error)
        terminal = ("UNRESOLVED_STOP" if reason in (
            "NO_COMPLETE_SAFE_HEFT_INITIALIZATION", "NUMERICAL_UNRESOLVED")
            else "BUDGET_EXHAUSTED" if reason == "SAFE_FORMED_AFTER_DEADLINE"
                and budget.elapsed >= budget.seconds else "TECHNICAL_STOP")
        result.update(run_terminal=terminal, reason=reason)
    except MemoryError:
        result.update(run_terminal="TECHNICAL_STOP", reason="RESOURCE_LIMIT")
    except Exception as error:
        result.update(run_terminal="TECHNICAL_STOP", reason="INTERFACE_ERROR",
            error=f"{type(error).__name__}: {error}")
    stopped = budget.elapsed
    result.update(timing=budget.summary(stopped), graph_proposals=proposals,
        graph_strict_improvements=graph_accepted,
        budget_exhausted=stopped >= budget.seconds)
    result["timing"]["clock_origin"] = (
        "method entry, before legacy imports, input read, HEFT and graph preparation")
    if recorder is not None:
        final = recorder.current if recorder.current is not None else recorder.best
        if final is not None:
            result.update(state="MOCK_SAFE" if bindings.kind == "MOCK_ONLY" else "SAFE",
                safe_candidate=deepcopy(final["candidate"]),
                safe_upper_bound_J=final["energy"]["upper"],
                evaluation=deepcopy(final["receipt"]), safe_context=deepcopy(final["context"]))
        result.update(initial_safe_snapshot=deepcopy(recorder.initial),
            initialization=recorder.initializer_meta, events=deepcopy(recorder.events),
            evaluations=deepcopy(recorder.rows), violations=deepcopy(recorder.violations),
            first_safe_at_s=recorder.first_safe_s,
            first_graph_strict_improvement_at_s=recorder.first_strict_s,
            cache_hits=recorder.cache_hits,
            usable_as_research_evidence=bindings.kind == "REAL_CORE" and final is not None
                and result["run_terminal"] not in ("TECHNICAL_STOP", "UNRESOLVED_STOP"))
    # Serialization only after stop: no validation, ranking, repair or physics.
    archive_started = clock()
    result = _archivable(result)
    _save(workdir / "result.json", result)
    if instance is not None:
        _save(workdir / "input_instance.json",
            _archivable(recorder.frozen_instance if recorder is not None else instance))
    if config is not None:
        _save(workdir / "input_config.json",
            _archivable(recorder.frozen_config if recorder is not None else config))
    _save(workdir / "archive_timing.json", {"wall_s": clock() - archive_started,
        "scope": "serialization of already formed evidence only"})
    return result
