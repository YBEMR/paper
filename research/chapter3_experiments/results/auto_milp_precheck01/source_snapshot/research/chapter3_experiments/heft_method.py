"""Deterministic, explicitly adapted HEFT for shared multi-scenario deployment.

Source skeleton: Topcuoglu et al., TPDS 2002, sections 4.1--4.2: mean-cost
upward rank and earliest-finish idle-gap insertion. Shared identity ranking,
scenario-weighted unit choice, per-execution OPP, deterministic ties and the
single energy-descent pass below are adaptations, not claims about original
HEFT. No solver, seed constructor, historical answer or research result is read.

The constructor is deliberately incomplete. Failure is unresolved, never an
infeasibility proof. Every emitted schedule needs the common continuous
thermal/energy assessment. Search priority does not alter the legal domain.
"""

from copy import deepcopy
from control_policy import require_legacy_control
from fractions import Fraction as F

from schedules import validate_schedule
from start_domain import explicit_start_sets


RULE_VERSION = "shared-scenario-heft-energy-pass-v1"
RULES = {
    "source": "Topcuoglu et al., TPDS 2002, sections 4.1--4.2",
    "rank": "union shared-identity DAG; mean of fastest legal duration on each unit; zero transfer cost",
    "priority": "ready shared identity by descending rank_u, then identity",
    "shared_unit": "minimum weighted sum of inserted execution finish times, then weighted scene tail, then unit id",
    "insertion": "each execution deadline/id order; minimum finish, start, activity energy, OPP id",
    "fallbacks": "at most three additional high/middle/low OPP-rank constructions; no exclusion",
    "energy_adjustment": "one deterministic unit/OPP/one-successor-start pass; full-safe interval-strict descent only",
    "coverage": "bounded constructor/local neighborhood, not exhaustive; no optimality or infeasibility proof",
}


def _check(budget):
    if budget is not None:
        budget.check()


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise TypeError("exact scalar required")
    return F(value)


def upward_ranks(instance, budget=None):
    """Return exact ranks and deterministic ready/rank order, or a cycle error.

    A cyclic union across scenarios does not prove the original problem cyclic:
    it means this shared-list constructor cannot represent that input.
    """
    nodes = set(instance["stage_modes"])
    successors = {node: set() for node in nodes}
    predecessors = {node: set() for node in nodes}
    for scene in instance["scenarios"]:
        stages = {stage["id"]: stage for stage in scene["stage_instances"]}
        for left, right in scene["dependencies"]:
            _check(budget)
            a, b = stages[left]["shared_stage_id"], stages[right]["shared_stage_id"]
            successors[a].add(b)
            predecessors[b].add(a)
    means = {}
    for node in sorted(nodes):
        _check(budget)
        fastest = {}
        for mode in instance["stage_modes"][node]:
            _check(budget)
            cost = _q(mode["duration_ms"])
            if cost <= 0:
                raise ValueError("positive legal execution durations required")
            unit = mode["unit_id"]
            fastest[unit] = min(fastest.get(unit, cost), cost)
        costs = list(fastest.values())
        if not costs:
            raise ValueError("positive legal execution durations required")
        means[node] = sum(costs, F(0)) / len(costs)
    # Kahn order also detects a self-edge or cyclic shared-identity union.
    queue, ordered = sorted(node for node in nodes if not predecessors[node]), []
    pending = {node: set(values) for node, values in predecessors.items()}
    while queue:
        _check(budget)
        node = queue.pop(0)
        ordered.append(node)
        for nxt in sorted(successors[node]):
            pending[nxt].remove(node)
            if not pending[nxt]:
                queue.append(nxt)
                queue.sort()
    if len(ordered) != len(nodes):
        return None, None, "SHARED_IDENTITY_DEPENDENCY_CYCLE"
    ranks = {}
    for node in reversed(ordered):
        _check(budget)
        ranks[node] = means[node] + max((ranks[nxt] for nxt in successors[node]), default=F(0))
    remaining, done, priority = set(nodes), set(), []
    while remaining:
        _check(budget)
        ready = [node for node in remaining if predecessors[node] <= done]
        node = min(ready, key=lambda item: (-ranks[item], item))
        priority.append(node)
        remaining.remove(node)
        done.add(node)
    return ranks, priority, None


def _first_start(instance, scene_id, stage_id, earliest, deadline, mode,
                 occupied, declared, units, budget):
    grid = _q(instance["start_grid_ms"])
    duration = _q(mode["duration_ms"])
    latest = min(deadline, _q(instance["window_ms"])) - duration
    if declared is None:
        lo, hi = -((-earliest) // grid), latest // grid
        candidates = (index * grid for index in range(lo, hi + 1))
    else:
        candidates = (start for start in declared[scene_id][stage_id] if earliest <= start <= latest)
    unit, opp = mode["unit_id"], mode["opp_id"]
    domain = units[unit]["domain_id"]
    for start in candidates:
        _check(budget)
        finish = start + duration
        conflict = False
        for row in occupied:
            _check(budget)
            if max(start, row["start"]) < min(finish, row["finish"]) and (
                    unit == row["unit"] or (domain == row["domain"] and opp != row["opp"])):
                conflict = True
                break
        if not conflict:
            return {"stage_id": stage_id, "unit": unit, "opp": opp,
                    "domain": domain, "start": start, "finish": finish}
    return None


def build_heft_candidate(instance, budget=None, *, opp_rank=None,
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
    ranks, priority, failure = upward_ranks(instance, budget)
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


def _energy_interval(receipt):
    if not isinstance(receipt, dict) or receipt.get("state") != "SAFE":
        return None
    values = receipt.get("weighted_energy_J")
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return None
    lower, upper = F(values[0]), F(values[1])
    if lower < 0 or upper < lower:
        return None
    return lower, upper


def _candidate_state(candidate, instance):
    stages = {scene["id"]: {stage["id"]: stage["shared_stage_id"]
                            for stage in scene["stage_instances"]}
              for scene in instance["scenarios"]}
    deployment, opps, floors = {}, {}, {}
    for sid, rows in candidate["scenes"].items():
        for row in rows:
            deployment[stages[sid][row["stage_id"]]] = row["unit"]
            opps[(sid, row["stage_id"])] = row["opp"]
            floors[(sid, row["stage_id"])] = row["start_ms"]
    return deployment, opps, floors


def _next_start(instance, sid, iid, current, declared):
    if declared is None:
        value = current + _q(instance["start_grid_ms"])
        return value if value <= _q(instance["window_ms"]) else None
    return next((value for value in declared[sid][iid] if value > current), None)


def run_heft(instance, config, budget, assess):
    """Construct and make a single safe-energy descent pass.

    ``assess(candidate, source)`` owns common checking/cache/budget evidence and
    returns the ordinary evaluator receipt. It must independently retain the
    best valid SAFE upper bound; this function's strict interval descent only
    controls the next local base, not the result archive. Budget exhaustion
    propagates so the wrapper can preserve already committed receipts.
    """
    require_legacy_control(instance, 'HEFT search')
    require_legacy_control(config, 'HEFT configuration')
    del config  # Same expanded instance supplies all options; no hidden answers.
    meta = {"rule_version": RULE_VERSION, "rules": dict(RULES),
            "construction_attempts": [], "local_attempts": [],
            "local_accepted": 0, "coverage_status": "HEURISTIC_NOT_EXHAUSTIVE",
            "infeasibility_status": "NOT_PROVED", "optimality_status": "NOT_PROVED"}
    current, receipt = None, None
    seen = set()
    for rank in (None, 0, 1, 2):
        _check(budget)
        constructed = build_heft_candidate(instance, budget, opp_rank=rank)
        meta["construction_attempts"].append({key: value for key, value in constructed.items()
                                               if key not in ("candidate", "validation")})
        candidate = constructed["candidate"]
        if candidate is None:
            continue
        signature = tuple((sid, tuple((row["stage_id"], row["unit"], row["opp"], row["start_ms"])
                                      for row in rows))
                          for sid, rows in sorted(candidate["scenes"].items()))
        if signature in seen:
            meta["construction_attempts"][-1]["duplicate_construction"] = True
            continue
        seen.add(signature)
        result = assess(candidate, "heft:eft" if rank is None else f"heft:fallback-opp-rank-{rank}")
        if _energy_interval(result) is not None:
            current, receipt = deepcopy(candidate), result
            break
    if current is None:
        meta["status"] = "NO_SAFE_CONSTRUCTED_WITNESS"
        return meta
    declared = explicit_start_sets(instance, budget)
    identity_order = sorted(instance["stage_modes"])
    execution_order = sorted((scene["id"], stage["id"]) for scene in instance["scenarios"]
                             for stage in scene["stage_instances"])
    shared_for = {(scene["id"], stage["id"]): stage["shared_stage_id"]
                  for scene in instance["scenarios"] for stage in scene["stage_instances"]}

    def attempt(kind, details, **overrides):
        nonlocal current, receipt
        _check(budget)
        built = build_heft_candidate(instance, budget, **overrides)
        event = {"kind": kind, **details, "construction_status": built["status"], "accepted": False}
        meta["local_attempts"].append(event)
        if built["candidate"] is None:
            event["reason"] = built["reason"]
            return
        result = assess(built["candidate"], "heft:energy-pass:" + kind)
        interval, previous = _energy_interval(result), _energy_interval(receipt)
        event["assessment_state"] = result.get("state")
        if interval is not None and interval[1] < previous[0]:
            current, receipt = deepcopy(built["candidate"]), result
            event["accepted"] = True
            meta["local_accepted"] += 1

    for shared in identity_order:
        for unit in sorted({mode["unit_id"] for mode in instance["stage_modes"][shared]}):
            _check(budget)
            deployment, opps, _ = _candidate_state(current, instance)
            if unit == deployment[shared]:
                continue
            deployment[shared] = unit
            opps = {key: opp for key, opp in opps.items() if shared_for[key] != shared}
            attempt("shared-unit", {"shared_stage_id": shared, "unit": unit},
                    deployment_override=deployment, opp_override=opps)
    for key in execution_order:
        for opp in sorted({mode["opp_id"] for mode in instance["stage_modes"][shared_for[key]]}):
            _check(budget)
            deployment, opps, _ = _candidate_state(current, instance)
            if opp == opps[key]:
                continue
            opps[key] = opp
            attempt("execution-opp", {"scenario": key[0], "stage_id": key[1], "opp": opp},
                    deployment_override=deployment, opp_override=opps)
    for key in execution_order:
        _check(budget)
        deployment, opps, floors = _candidate_state(current, instance)
        nxt = _next_start(instance, key[0], key[1], _q(floors[key]), declared)
        if nxt is None:
            continue
        floors[key] = str(nxt)
        attempt("one-start-delay", {"scenario": key[0], "stage_id": key[1], "floor_ms": str(nxt)},
                deployment_override=deployment, opp_override=opps, start_floor=floors)
    meta.update(status="BOUNDED_SEARCH_COMPLETED", local_base_candidate=current,
                local_base_energy_J=receipt["weighted_energy_J"])
    return meta
