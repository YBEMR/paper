"""One new ready-list ordering on the unchanged adapted-HEFT constructor.

Only priority selection changes. Candidate insertion, unit/OPP choices, deadline
and resource checks are the original constructor body. No scientific work runs
at import; malformed inputs and exhausted budgets propagate to the caller.
"""
from fractions import Fraction as F

from heft_method import _check, _q, _first_start, upward_ranks
from schedules import validate_schedule
from start_domain import explicit_start_sets

RULE_VERSION="shared-scenario-heft-single-deadline-ready-construction-v1"


def deadline_ranks(instance,budget=None):
    """Keep original upward ranks/cycle semantics, reorder only ready identities.

    The key is earliest associated absolute request deadline, descending rank,
    then identity. A catalog identity without an execution receives window_ms
    as its priority deadline, keeping such otherwise legal directories usable.
    No application, processor type or workload identifier is hard coded.
    """
    ranks,original_priority,failure=upward_ranks(instance,budget)
    if failure:
        return ranks,original_priority,failure
    nodes=set(instance["stage_modes"])
    predecessors={node:set() for node in nodes}
    deadlines={node:None for node in nodes}
    for scene in instance["scenarios"]:
        _check(budget)
        requests={r["id"]:r for r in scene["requests"]}
        stages={stage["id"]:stage for stage in scene["stage_instances"]}
        for stage in scene["stage_instances"]:
            _check(budget)
            shared=stage["shared_stage_id"]
            deadline=_q(requests[stage["request_id"]]["deadline_ms"])
            previous=deadlines[shared]
            deadlines[shared]=deadline if previous is None else min(previous,deadline)
        for left,right in scene["dependencies"]:
            _check(budget)
            predecessors[stages[right]["shared_stage_id"]].add(stages[left]["shared_stage_id"])
    window=_q(instance["window_ms"])
    deadlines={node:window if value is None else value for node,value in deadlines.items()}
    remaining,done,priority=set(nodes),set(),[]
    while remaining:
        _check(budget)
        ready=[node for node in remaining if predecessors[node]<=done]
        if not ready:
            raise ValueError("deadline-ready ordering contradicts acyclic upward-rank result")
        node=min(ready,key=lambda item:(deadlines[item],-ranks[item],item))
        priority.append(node)
        remaining.remove(node)
        done.add(node)
    return ranks,priority,None


def build_deadline_candidate(instance, budget=None, *, opp_rank=None,
                         deployment_override=None, opp_override=None,
                         start_floor=None):
    """Construct a complete candidate and metadata, without thermal evaluation.

    Overrides restrict this one heuristic attempt only. ``opp_rank`` selects
    high/middle/low by frequency within each unit (0/1/2, clamped); None lets
    EFT compare every legal OPP. Per-execution keys are ``(scene_id, stage_id)``.
    No caller-supplied starts may extend the input's exact declared domain.
    """
    _check(budget)
    if opp_rank is not None and (isinstance(opp_rank, bool) or not isinstance(opp_rank, int)
                                 or opp_rank not in (0, 1, 2)):
        raise ValueError("opp_rank must be None, 0, 1 or 2")
    ranks, priority, failure = deadline_ranks(instance, budget)
    meta = {"rule_version": RULE_VERSION, "status": "CONSTRUCTION_UNRESOLVED",
            "candidate": None, "reason": failure, "thermal_status": "NOT_EVALUATED",
            "optimality_status": "NOT_PROVED", "opp_rank": opp_rank}
    if failure:
        return meta
    meta["rank_u_ms"] = {node: str(rank) for node, rank in sorted(ranks.items())}
    meta["shared_priority"] = priority
    units = {unit["id"]: unit for unit in instance["platform"]["units"]}
    declared = explicit_start_sets(instance, budget)
    deployment_override = deployment_override or {}
    opp_override, start_floor = opp_override or {}, start_floor or {}
    scenes = sorted(instance["scenarios"], key=lambda scene: scene["id"])
    state = {scene["id"]: {} for scene in scenes}
    deployment, decisions = {}, []
    for shared_id in priority:
        _check(budget)
        modes = instance["stage_modes"][shared_id]
        possible_units = sorted({mode["unit_id"] for mode in modes})
        if shared_id in deployment_override:
            possible_units = [unit for unit in possible_units if unit == deployment_override[shared_id]]
        unit_trials = []
        for unit in possible_units:
            _check(budget)
            trial = {scene_id: dict(rows) for scene_id, rows in state.items()}
            finish_sum, tail_sum, failed = F(0), F(0), False
            local_modes = [mode for mode in modes if mode["unit_id"] == unit]
            local_modes.sort(key=lambda mode: (-_q(mode["frequency_GHz"]), mode["opp_id"]))
            for scene in scenes:
                _check(budget)
                sid = scene["id"]
                requests = {request["id"]: request for request in scene["requests"]}
                copies = [stage for stage in scene["stage_instances"]
                          if stage["shared_stage_id"] == shared_id]
                copies.sort(key=lambda stage: (_q(requests[stage["request_id"]]["deadline_ms"]), stage["id"]))
                predecessors = {}
                for left, right in scene["dependencies"]:
                    predecessors.setdefault(right, []).append(left)
                for stage in copies:
                    _check(budget)
                    iid, key = stage["id"], (sid, stage["id"])
                    request = requests[stage["request_id"]]
                    pred = predecessors.get(iid, [])
                    if any(identity not in trial[sid] for identity in pred):
                        failed = True
                        break
                    earliest = max([F(0), _q(request["release_ms"]), _q(start_floor.get(key, "0"))] +
                                   [trial[sid][identity]["finish"] for identity in pred])
                    choices = local_modes
                    if key in opp_override:
                        choices = [mode for mode in choices if mode["opp_id"] == opp_override[key]]
                    elif opp_rank is not None:
                        choices = [choices[min(opp_rank, len(choices) - 1)]] if choices else []
                    inserts = []
                    for mode in choices:
                        row = _first_start(instance, sid, iid, earliest, _q(request["deadline_ms"]),
                                           mode, trial[sid].values(), declared, units, budget)
                        if row is not None:
                            activity = _q(mode.get("activity_energy_J",
                                str(_q(mode["activity_power_W"]) * _q(mode["duration_ms"]) / 1000)))
                            inserts.append((row["finish"], row["start"], activity, mode["opp_id"], row))
                    if not inserts:
                        failed = True
                        break
                    selected = min(inserts, key=lambda value: value[:-1])[-1]
                    trial[sid][iid] = selected
                    finish_sum += _q(scene["weight"]) * selected["finish"]
                if failed:
                    break
                tail_sum += _q(scene["weight"]) * max(
                    (row["finish"] for row in trial[sid].values()), default=F(0))
            if not failed:
                unit_trials.append((finish_sum, tail_sum, unit, trial))
        if not unit_trials:
            meta.update(reason="NO_LEGAL_EFT_INSERTION", failed_shared_stage=shared_id,
                        deployment=deployment, decisions=decisions)
            return meta
        finish_sum, tail_sum, unit, state = min(unit_trials, key=lambda value: value[:3])
        deployment[shared_id] = unit
        decisions.append({"shared_stage_id": shared_id, "unit": unit,
                          "weighted_inserted_finish_sum_ms": str(finish_sum),
                          "weighted_partial_scene_tail_ms": str(tail_sum),
                          "feasible_unit_count": len(unit_trials)})
    candidate = {"scenes": {sid: [
        {"stage_id": row["stage_id"], "unit": row["unit"], "opp": row["opp"],
         "start_ms": str(row["start"])}
        for _, row in sorted(rows.items())] for sid, rows in state.items()}}
    _check(budget)
    validation = validate_schedule(instance, candidate)
    _check(budget)
    if validation["state"] != "SCHEDULE_VALID_THERMAL_UNCHECKED":
        meta.update(reason="COMMON_LEGALITY_REJECTED", validation=validation)
    else:
        meta.update(status="COMPLETE_LEGAL_CANDIDATE", reason=None, candidate=candidate)
    meta.update(deployment=deployment, decisions=decisions)
    return meta
