"""Activity-saving mode and one deadline-blocking edge, one method clock.

This is an interface, not an experiment launcher. The original C, HEFT and
single/pair graph implementations are unchanged. Tests supply MOCK_ONLY
initializers and invented complete receipts; real backends require explicit
bindings and a separately authorized execution protocol.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import hashlib
import math
from pathlib import Path
import time

from .. import method as original
from .. import graph_core
from . import core

Bindings, SearchStop, digest = original.Bindings, original.SearchStop, original.digest
RULE_VERSION = "saving-mode-one-deadline-blocking-edge-v1"
RULES = {
    "target": "strictly lower q*d on the current exact unit; positive scenario-weighted saving",
    "target_order": "descending exact weighted activity saving, scene, Stage id, target OPP",
    "partners": "original resource-related pairs containing target; singleton if none",
    "partner_modes": "all legal OPPs on the partner's unchanged unit; target OPP fixed",
    "orders": ["incumbent", "reverse"], "templates": ["earliest", "preserve"],
    "trace": "one maximum-finish predecessor per node; lexicographic tie; release/floor wins equality",
    "extra_order": "lexicographic original-direction resource edges on all reported deadline traces",
    "extra_limit": 1, "recursive_repair": False,
    "ranking": "exact nonthermal full-window ledger within each target/pair; never a cutoff",
    "acceptance": "complete original SAFE and new.upper < incumbent.lower",
    "scope": "fixed units; no global optimality or infeasibility claim",
}


def source_identity():
    sources = original.source_identity()
    here = Path(__file__).resolve().parent
    for path in (Path(__file__), here / "core.py", here / "__init__.py"):
        sources[path.relative_to(here.parents[1]).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


class CompleteRecorder(original.CompleteRecorder):
    """Inherit the exact old receipt/SAFE rules; additionally bind new sources."""
    def check_context(self):
        if (digest(self.instance) != self.context["input_sha256"]
                or digest(self.config) != self.context["config_sha256"]
                or digest(self.accuracy) != self.context["accuracy_sha256"]
                or repr(self.budget.start) != self.context["root_start"]
                or repr(self.budget.deadline) != self.context["root_deadline"]
                or self.budget.seconds != self.context["root_seconds"]
                or source_identity() != self.sources):
            raise SearchStop("CALL_CONTEXT_DRIFT")


def energy_targets(instance, incumbent, budget):
    """Heuristic targets, not a dominance rule or removal of legal choices."""
    validation = graph_core._validated(instance, incumbent, budget)
    weights = [graph_core._q(s["weight"]) for s in instance["scenarios"]]
    if any(w < 0 for w in weights) or sum(weights) != 1:
        raise ValueError("nonnegative scene weights summing to one required")
    targets = []
    for scene in sorted(instance["scenarios"], key=lambda s: s["id"]):
        budget.check()
        weight = graph_core._q(scene["weight"])
        if weight < 0:
            raise ValueError("negative scene weight")
        ids = {s["id"]: s["shared_stage_id"] for s in scene["stage_instances"]}
        for row in sorted(validation["scenes"][scene["id"]]["rows"], key=lambda r: r["stage_id"]):
            budget.check()
            modes = [m for m in instance["stage_modes"][ids[row["stage_id"]]]
                     if m["unit_id"] == row["unit"]]
            current = [m for m in modes if m["opp_id"] == row["opp"]]
            if len(current) != 1 or len({m["opp_id"] for m in modes}) != len(modes):
                raise ValueError("ambiguous fixed-unit modes")
            activity = lambda m: graph_core._q(m["activity_power_W"]) * graph_core._q(m["duration_ms"]) / 1000
            old = activity(current[0])
            for mode in modes:
                budget.check()
                saving = weight * (old - activity(mode))
                if saving > 0:
                    targets.append({"scene_id": scene["id"], "stage_id": row["stage_id"],
                        "shared_stage_id": ids[row["stage_id"]], "unit": row["unit"],
                        "old_opp": row["opp"], "target_opp": mode["opp_id"],
                        "weighted_activity_saving_J": str(saving)})
    budget.check()
    return sorted(targets, key=lambda t: (-F(t["weighted_activity_saving_J"]),
        t["scene_id"], t["stage_id"], t["target_opp"]))


def candidate_packets(instance, incumbent, budget, *, diagnostics=None):
    """Only a deadline failure of the same base skeleton permits an extra edge."""
    diagnostics = [] if diagnostics is None else diagnostics
    with budget.phase("activity_saving_targets"):
        targets = energy_targets(instance, incumbent, budget)
    if not targets:
        return
    with budget.phase("resource_association"):
        associations = graph_core.related_pairs(instance, incumbent, budget=budget)
    scenes = {s["id"]: s for s in instance["scenarios"]}
    emitted = set()
    for target in targets:
        budget.check()
        sid = target["scene_id"]
        actions = [a for a in associations if a["scene_id"] == sid and target["stage_id"] in a["stage_ids"]]
        if not actions:
            actions = [{"scene_id": sid, "stage_ids": [target["stage_id"]]}]
        rows = {r["stage_id"]: r for r in incumbent["scenes"][sid]}
        shared = {s["id"]: s["shared_stage_id"] for s in scenes[sid]["stage_instances"]}
        for action in actions:
            budget.check()
            selected = action["stage_ids"]
            choices = [[target["target_opp"]] if iid == target["stage_id"] else
                sorted(m["opp_id"] for m in instance["stage_modes"][shared[iid]]
                       if m["unit_id"] == rows[iid]["unit"]) for iid in selected]
            pending, seen = [], set()

            def record(packet, extra):
                budget.check()
                diagnostics.append({"target": deepcopy(target), "scene_id": sid,
                    "selected_stages": list(selected), "opp_overrides": deepcopy(overrides),
                    "orientation": orientation, "template": template,
                    "extra_resource_edge": None if extra is None else list(extra),
                    "state": packet["state"], "reason": packet.get("reason"),
                    "deadline_violations": deepcopy(packet.get("deadline_violations", [])),
                    "blocking_traces": deepcopy(packet.get("blocking_traces", [])),
                    "base_blocking_traces": deepcopy(packet.get("base_blocking_traces", [])),
                    "additional_reversed_edges": deepcopy(packet.get("additional_reversed_edges", []))})
                if packet["state"] != "COMPLETE_LEGAL_CANDIDATE":
                    return
                key = digest(packet["candidate"])
                if key not in seen and key not in emitted:
                    seen.add(key)
                    packet["energy_target"] = deepcopy(target)
                    pending.append(packet)

            for mode_tuple in product(*choices):
                overrides = dict(zip(selected, mode_tuple))
                for orientation in (("incumbent", "reverse") if len(selected) == 2 else ("incumbent",)):
                    for template in RULES["templates"]:
                        budget.check()
                        with budget.phase("blocking_graph_construct"):
                            packet = core.reconstruct(instance, incumbent, sid, selected, overrides,
                                orientation=orientation, template=template, budget=budget)
                            record(packet, None)
                            # Each trial is rebuilt from this base, never from a
                            # previously repaired (or merely worse SAFE) plan.
                            for edge in core.blocking_edges(packet):
                                budget.check()
                                repaired = core.reconstruct(instance, incumbent, sid, selected, overrides,
                                    orientation=orientation, template=template,
                                    extra_resource_edge=edge, budget=budget)
                                record(repaired, edge)
            with budget.phase("nonthermal_ranking"):
                pending.sort(key=lambda p: (F(p["nonthermal_energy_J"]), digest(p["candidate"])))
            for packet in pending:
                budget.check()
                emitted.add(digest(packet["candidate"]))
                yield packet


def execute_reconstruction(input_loader, workdir, *, bindings, seconds=300,
                           clock=time.monotonic, budget=None):
    """One bounded call; no CLI selecting research cases or granting a budget."""
    entered = clock() if budget is None else None
    from timing import MethodBudget
    from thermal import Exhausted
    if isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError("one finite root budget in (0,300] required")
    if budget is None:
        budget = MethodBudget(seconds, clock=clock)
        budget.start, budget.deadline = entered, entered + float(seconds)
    elif not isinstance(budget, MethodBudget) or float(seconds) != float(budget.seconds):
        raise ValueError("caller must supply the matching original MethodBudget")
    else:
        clock = budget.clock
        budget.check()
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    result = {"method": "activity_saving_deadline_edge_graph", "rule_version": RULE_VERSION,
        "rules": deepcopy(RULES), "state": "UNRESOLVED", "run_terminal": None,
        "reason": None, "safe_candidate": None, "safe_upper_bound_J": None,
        "evaluation": None, "coverage_complete": False,
        "independently_proven_optimal": False, "independently_proven_infeasible": False,
        "evidence_kind": getattr(bindings, "kind", "UNCONFIGURED"),
        "usable_as_research_evidence": False, "candidate_or_cache_shared_between_calls": False}
    recorder = instance = config = None
    proposals, diagnostics, accepted = [], [], 0
    try:
        with budget.phase("input_imports_and_context"):
            if not isinstance(bindings, Bindings) or bindings.kind not in ("MOCK_ONLY", "REAL_CORE"):
                raise ValueError("recognized explicit backend bindings required")
            if bindings.kind == "REAL_CORE":
                from heft_method import run_heft
                from thermal import evaluate_candidate
                if bindings.initializer is not run_heft or bindings.evaluator is not evaluate_candidate:
                    raise ValueError("real backends must be the unchanged original functions")
            if not callable(bindings.initializer) or not callable(bindings.evaluator):
                raise ValueError("callable initializer and evaluator required")
            from auto_heuristic_policy import require_heuristic_control
            config, instance = input_loader(budget)
            require_heuristic_control(instance, config, "Blocking-edge reconstruction", allow_auto_low=True)
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
            status = (recorder.initializer_meta or {}).get("status")
            allowed = {"BOUNDED_SEARCH_COMPLETED"}
            if bindings.kind == "MOCK_ONLY":
                allowed.add("MOCK_INITIALIZER_COMPLETED")
            if status not in allowed:
                raise SearchStop("INITIALIZATION_NOT_COMPLETED")
            recorder.freeze_initial()
        seen = set(recorder.cache)
        while True:
            budget.check()
            recorder.check_context()
            base = digest(recorder.current["candidate"])
            improved = False
            for packet in candidate_packets(instance, recorder.current["candidate"], budget,
                                            diagnostics=diagnostics):
                budget.check()
                if len(packet.get("additional_reversed_edges", [])) > 1:
                    raise SearchStop("INVALID_ADDITIONAL_EDGE_SCOPE")
                key = digest(packet["candidate"])
                if key in seen:
                    continue
                event = {k: deepcopy(v) for k, v in packet.items() if k != "candidate"}
                event.update(base_candidate_sha256=base, candidate_sha256=key,
                    proposed_at_s=budget.elapsed, strict_accepted=False)
                proposals.append(event)
                try:
                    recorder.assess(packet["candidate"], "graph:mode-deadline-edge")
                finally:
                    # Preserve a full receipt formed in time even if transfer
                    # reaches the next budget checkpoint after the deadline.
                    event["strict_accepted"] = digest(recorder.current["candidate"]) != base
                    accepted += int(event["strict_accepted"])
                seen.add(key)
                if event["strict_accepted"]:
                    improved = True
                    break
            if not improved:
                break
        result.update(run_terminal="SEARCH_COMPLETED", reason="NO_FURTHER_DECLARED_IMPROVEMENT")
    except Exhausted:
        result.update(run_terminal="BUDGET_EXHAUSTED", reason="METHOD_BUDGET_EXHAUSTED")
    except SearchStop as error:
        reason = str(error)
        terminal = ("UNRESOLVED_STOP" if reason in ("NO_COMPLETE_SAFE_HEFT_INITIALIZATION",
            "NUMERICAL_UNRESOLVED", "INITIALIZATION_NOT_COMPLETED") else
            "BUDGET_EXHAUSTED" if reason == "SAFE_FORMED_AFTER_DEADLINE" and
            budget.elapsed >= budget.seconds else "TECHNICAL_STOP")
        result.update(run_terminal=terminal, reason=reason)
    except MemoryError:
        result.update(run_terminal="TECHNICAL_STOP", reason="RESOURCE_LIMIT")
    except Exception as error:
        result.update(run_terminal="TECHNICAL_STOP", reason="INTERFACE_ERROR",
                      error=f"{type(error).__name__}: {error}")
    stopped = budget.elapsed
    result.update(timing=budget.summary(stopped), graph_proposals=proposals,
        reconstruction_attempts=diagnostics, graph_strict_improvements=accepted,
        budget_exhausted=stopped >= budget.seconds)
    result["timing"]["clock_origin"] = "one caller root or method entry before imports/input/initialization/reconstruction"
    if recorder is not None:
        final = recorder.current if recorder.current is not None else recorder.best
        if final is not None:
            result.update(state="MOCK_SAFE" if bindings.kind == "MOCK_ONLY" else "SAFE",
                safe_candidate=deepcopy(final["candidate"]), safe_upper_bound_J=final["energy"]["upper"],
                evaluation=deepcopy(final["receipt"]), safe_context=deepcopy(final["context"]))
        result.update(initial_safe_snapshot=deepcopy(recorder.initial), initialization=recorder.initializer_meta,
            events=deepcopy(recorder.events), evaluations=deepcopy(recorder.rows), violations=deepcopy(recorder.violations),
            first_safe_at_s=recorder.first_safe_s, first_graph_strict_improvement_at_s=recorder.first_strict_s,
            cache_hits=recorder.cache_hits, usable_as_research_evidence=bindings.kind == "REAL_CORE" and
                final is not None and result["run_terminal"] not in ("TECHNICAL_STOP", "UNRESOLVED_STOP"))
    archive_started = clock()
    result = original._archivable(result)
    original._save(workdir / "result.json", result)
    if instance is not None:
        original._save(workdir / "input_instance.json", original._archivable(
            recorder.frozen_instance if recorder is not None else instance))
    if config is not None:
        original._save(workdir / "input_config.json", original._archivable(
            recorder.frozen_config if recorder is not None else config))
    original._save(workdir / "archive_timing.json", {"wall_s": clock() - archive_started,
        "scope": "serialization of already formed evidence only"})
    return result
