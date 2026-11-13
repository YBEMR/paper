"""Isolated C01 HEFT lifecycle, allowing a predeclared shorter caller root.

Copied from validation.lifecycle: only the input budget guard and the late-SAFE
cutoff use the supplied cap. Original run_heft, complete recorder, search,
acceptance and archival behavior are unchanged; 300s equivalence is tested.
"""
from copy import deepcopy
from pathlib import Path
import time
import math


def execute_heft(input_loader, workdir, *, bindings, budget):
    from research.chapter4_scheduler.blocking import method as common
    from auto_heuristic_policy import require_heuristic_control
    from timing import MethodBudget
    from thermal import Exhausted
    if (not isinstance(budget, MethodBudget) or isinstance(budget.seconds, bool)
            or not math.isfinite(budget.seconds) or not 0 < budget.seconds <= 300
            or budget.deadline != budget.start + float(budget.seconds)):
        raise ValueError("One unchanged caller-owned root in (0,300] seconds is required")
    budget.check()
    workdir=Path(workdir)
    if workdir.exists():
        raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    result={"method":"original_enhanced_HEFT_common_complete_recorder", "state":"UNRESOLVED",
        "run_terminal":None,"reason":None,"safe_candidate":None,"safe_upper_bound_J":None,
        "evaluation":None,"initial_safe_snapshot":None,"initialization":None,
        "evidence_kind":bindings.kind,"usable_as_research_evidence":False,
        "coverage_complete":False,"independently_proven_optimal":False,"independently_proven_infeasible":False,
        "candidate_or_cache_shared_between_calls":False,"blocking_edge_adjustment_enabled":None,
        "graph_proposals":[],"reconstruction_attempts":[],"graph_strict_improvements":0}
    recorder=instance=config=None
    try:
        with budget.phase("input_imports_and_context"):
            if not isinstance(bindings,common.Bindings) or bindings.kind not in ("MOCK_ONLY","REAL_CORE"):
                raise ValueError("Explicit original or mock bindings required")
            if bindings.kind=="REAL_CORE":
                from heft_method import run_heft
                from thermal import evaluate_candidate
                if bindings.initializer is not run_heft or bindings.evaluator is not evaluate_candidate:
                    raise ValueError("Real bindings must be the unchanged original functions")
            config,instance=input_loader(budget)
            require_heuristic_control(instance,config,"Enhanced HEFT",allow_auto_low=True)
            sources=common.source_identity()
            recorder=common.CompleteRecorder(instance,config,budget,bindings,sources)
            result.update(input_sha256=common.digest(instance),sources_sha256=sources,
                problem_id=instance["id"],root_context=deepcopy(recorder.context))
        with budget.phase("heft_initialization"):
            recorder.initializer_meta=bindings.initializer(instance,config,budget,recorder.assess,allow_auto_low=True)
        with budget.phase("complete_initial_safe_freeze"):
            status=(recorder.initializer_meta or {}).get("status")
            allowed={"BOUNDED_SEARCH_COMPLETED"}
            if bindings.kind=="MOCK_ONLY":allowed.add("MOCK_INITIALIZER_COMPLETED")
            if status=="NO_SAFE_CONSTRUCTED_WITNESS" and recorder.best is None:
                raise common.SearchStop("NO_SAFE_CONSTRUCTED_WITNESS")
            if status not in allowed:raise common.SearchStop("INITIALIZATION_NOT_COMPLETED")
            recorder.freeze_initial()
        result.update(run_terminal="SEARCH_COMPLETED",reason="NO_REFINEMENT_DECLARED")
    except Exhausted:
        result.update(run_terminal="BUDGET_EXHAUSTED",reason="METHOD_BUDGET_EXHAUSTED")
    except common.SearchStop as error:
        reason=str(error)
        terminal=("NORMAL_NO_SAFE" if reason=="NO_SAFE_CONSTRUCTED_WITNESS" else
            "UNRESOLVED_STOP" if reason in ("INITIALIZATION_NOT_COMPLETED","NO_COMPLETE_SAFE_HEFT_INITIALIZATION","NUMERICAL_UNRESOLVED") else
            "BUDGET_EXHAUSTED" if reason=="SAFE_FORMED_AFTER_DEADLINE" and budget.elapsed>=budget.seconds else "TECHNICAL_STOP")
        result.update(run_terminal=terminal,reason=reason)
    except Exception as error:
        result.update(run_terminal="TECHNICAL_STOP",reason="INTERFACE_ERROR",error=f"{type(error).__name__}: {error}")
    stopped=budget.elapsed
    result.update(timing=budget.summary(stopped),budget_exhausted=stopped>=budget.seconds)
    result["timing"]["clock_origin"]="caller root before scientific imports, input and initialization"
    if recorder is not None:
        final=recorder.current if recorder.current is not None else recorder.best
        if final is not None:
            result.update(state="SAFE" if bindings.kind=="REAL_CORE" else "MOCK_SAFE",
                safe_candidate=deepcopy(final["candidate"]),safe_upper_bound_J=final["energy"]["upper"],
                evaluation=deepcopy(final["receipt"]),safe_context=deepcopy(final["context"]))
        result.update(initial_safe_snapshot=deepcopy(recorder.initial),initialization=recorder.initializer_meta,
            events=deepcopy(recorder.events),evaluations=deepcopy(recorder.rows),violations=deepcopy(recorder.violations),
            first_safe_at_s=recorder.first_safe_s,first_graph_strict_improvement_at_s=None,cache_hits=recorder.cache_hits,
            usable_as_research_evidence=bindings.kind=="REAL_CORE" and final is not None
                and result["run_terminal"] not in ("TECHNICAL_STOP","UNRESOLVED_STOP"))
    archive_started=budget.clock()
    result=common.original._archivable(result)
    common.original._save(workdir/"result.json",result)
    if instance is not None:common.original._save(workdir/"input_instance.json",recorder.frozen_instance if recorder else instance)
    if config is not None:common.original._save(workdir/"input_config.json",recorder.frozen_config if recorder else config)
    common.original._save(workdir/"archive_timing.json",{"wall_s":budget.clock()-archive_started,"scope":"serialization only; no search"})
    return result
