"""Bounded deterministic construction of complete initial schedules.

This is a seed constructor, not an optimizer or an infeasibility test. It
does not read prior results, enumerate complete schedules, call a solver, or
claim thermal safety. Each successful attempt is checked structurally by the
common exact schedule checker; the caller must then evaluate the complete
continuous thermal trajectory before treating it as a safe witness.

``iter_initial_candidates`` is lazy: after each complete candidate the caller
may evaluate it and stop at the first safe witness without constructing the
remaining templates. One supplied method budget covers all attempts.
"""

from fractions import Fraction

from schedules import validate_schedule
from start_domain import explicit_start_sets


RULE_VERSION = "deterministic-initial-schedule-v1"
RULES = {
    "shared_deployment": "shared Stage id order; minimum (shortest legal unit duration, assigned reference load, unit id)",
    "domain_template": "descending frequency then OPP id; ranks 1, 2, 3, clamped and deduplicated",
    "ready_order": "request absolute deadline then Stage instance id",
    "start_selection": "first exact declared grid start after release and predecessors, satisfying unit/domain conflicts and deadline/window",
    "attempt_limit": 3,
    "failure_meaning": "CONSTRUCTION_UNRESOLVED; no infeasibility or exclusion certificate",
    "thermal_acceptance": "external complete continuous evaluation required",
}


def _check(budget):
    if budget is not None:
        budget.check()


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise TypeError("Exact scalar must be a string, integer or Fraction")
    return Fraction(value)


def _deployment(instance, budget):
    """Choose each shared Stage's unit exactly once, without trimming a domain."""
    units = {unit["id"]: unit for unit in instance["platform"]["units"]}
    loads = {unit_id: Fraction(0) for unit_id in units}
    selected, records = {}, []
    for shared_id in sorted(instance["stage_modes"]):
        _check(budget)
        shortest = {}
        for mode in instance["stage_modes"][shared_id]:
            _check(budget)
            unit_id = mode["unit_id"]
            if unit_id not in units:
                raise ValueError("Mode refers to an unknown execution unit")
            duration = _fraction(mode["duration_ms"])
            if duration <= 0:
                raise ValueError("Stage duration must be positive")
            shortest[unit_id] = min(shortest.get(unit_id, duration), duration)
        if not shortest:
            raise ValueError("Shared Stage has no legal unit")
        unit_id = min(shortest, key=lambda unit: (shortest[unit], loads[unit], unit))
        records.append({
            "shared_stage_id": shared_id,
            "unit": unit_id,
            "shortest_legal_duration_ms": str(shortest[unit_id]),
            "reference_load_before_ms": str(loads[unit_id]),
            "unit_scores": [{"unit": unit, "shortest_legal_duration_ms": str(shortest[unit]),
                             "reference_load_ms": str(loads[unit])}
                            for unit in sorted(shortest)],
        })
        selected[shared_id] = unit_id
        loads[unit_id] += shortest[unit_id]
    return selected, records


def _templates(instance, max_attempts, budget):
    domains = instance["platform"]["domains"]
    ranked = {}
    for domain_id in sorted(domains):
        _check(budget)
        opps = domains[domain_id]["opps"]
        if not opps:
            raise ValueError("Domain has no legal OPP")
        ranked[domain_id] = sorted(opps, key=lambda opp: (-_fraction(opps[opp]["frequency_GHz"]), opp))
    seen = set()
    for index in range(max_attempts):
        _check(budget)
        chosen = {domain: values[min(index, len(values)-1)] for domain, values in ranked.items()}
        identity = tuple(sorted(chosen.items()))
        if identity not in seen:
            seen.add(identity)
            yield index + 1, chosen


def _start_sets(instance, starts, grid, window, budget):
    declared = explicit_start_sets(instance, budget)
    if starts is None:
        return declared
    if not instance["id"].startswith("fixture_"):
        raise ValueError("Explicit reduced start sets are fixture-only")
    expected = {scene["id"]: {stage["id"] for stage in scene["stage_instances"]}
                for scene in instance["scenarios"]}
    if set(starts) != set(expected):
        raise ValueError("Explicit starts must cover exactly the declared scenarios")
    out = {}
    for scene_id, stage_ids in expected.items():
        _check(budget)
        if set(starts[scene_id]) != stage_ids:
            raise ValueError("Explicit starts must cover exactly the declared Stage instances")
        out[scene_id] = {}
        for stage_id in sorted(stage_ids):
            _check(budget)
            values = sorted(set(map(_fraction, starts[scene_id][stage_id])))
            if any(value < 0 or value > window or (value / grid).denominator != 1 for value in values):
                raise ValueError("Explicit start lies outside the declared grid/window")
            if declared is not None and not set(values).issubset(declared[scene_id][stage_id]):
                raise ValueError("Fixture starts must be a subset of the declared start domain")
            out[scene_id][stage_id] = values
    return out


def _scene_schedule(instance, scene, deployment, domain_opps, starts, grid, window, budget):
    """Schedule one scene by an exact non-backtracking ready-list rule."""
    requests = {request["id"]: request for request in scene["requests"]}
    stages = {stage["id"]: stage for stage in scene["stage_instances"]}
    units = {unit["id"]: unit for unit in instance["platform"]["units"]}
    predecessors = {stage_id: [] for stage_id in stages}
    for predecessor, successor in scene["dependencies"]:
        if predecessor not in stages or successor not in stages:
            raise ValueError("Dependency refers to an unknown Stage")
        predecessors[successor].append(predecessor)
    remaining, assigned, occupied = set(stages), {}, []
    while remaining:
        _check(budget)
        ready = [stage_id for stage_id in remaining
                 if all(predecessor in assigned for predecessor in predecessors[stage_id])]
        if not ready:
            return None, {"reason": "NO_READY_STAGE", "scenario": scene["id"],
                          "remaining_stage_ids": sorted(remaining)}
        stage_id = min(ready, key=lambda sid: (
            _fraction(requests[stages[sid]["request_id"]]["deadline_ms"]), sid))
        stage = stages[stage_id]
        shared_id = stage["shared_stage_id"]
        unit = deployment[shared_id]
        domain = units[unit]["domain_id"]
        opp = domain_opps[domain]
        modes = [mode for mode in instance["stage_modes"][shared_id]
                 if mode["unit_id"] == unit and mode["opp_id"] == opp]
        if len(modes) != 1:
            return None, {"reason": "TEMPLATE_MODE_UNSUPPORTED_OR_AMBIGUOUS", "scenario": scene["id"],
                          "stage_id": stage_id, "unit": unit, "opp": opp}
        duration = _fraction(modes[0]["duration_ms"])
        request = requests[stage["request_id"]]
        earliest = max([Fraction(0), _fraction(request["release_ms"])] +
                       [assigned[pred]["end"] for pred in predecessors[stage_id]])
        latest_finish = min(window, _fraction(request["deadline_ms"]))
        if starts is None:
            first_index = -((-earliest) // grid)
            last_index = (latest_finish - duration) // grid
            candidates = (index * grid for index in range(first_index, last_index + 1))
        else:
            candidates = (value for value in starts[scene["id"]][stage_id]
                          if earliest <= value and value + duration <= latest_finish)
        selected = None
        for start in candidates:
            _check(budget)
            end = start + duration
            conflict = False
            for previous in occupied:
                _check(budget)
                overlap = max(start, previous["start"]) < min(end, previous["end"])
                if overlap and (unit == previous["unit"] or
                                (domain == previous["domain"] and opp != previous["opp"])):
                    conflict = True
                    break
            if not conflict:
                selected = {"stage_id": stage_id, "unit": unit, "opp": opp,
                            "start": start, "end": end, "domain": domain}
                break
        if selected is None:
            return None, {"reason": "NO_START_FOUND_BY_FIXED_RULE", "scenario": scene["id"],
                          "stage_id": stage_id, "earliest_ms": str(earliest),
                          "latest_finish_ms": str(latest_finish), "duration_ms": str(duration),
                          "assigned_stage_count": len(assigned)}
        assigned[stage_id] = selected
        occupied.append(selected)
        remaining.remove(stage_id)
    rows = [{"stage_id": row["stage_id"], "unit": row["unit"], "opp": row["opp"],
             "start_ms": str(row["start"])} for row in occupied]
    return rows, None


def iter_initial_candidates(instance, starts=None, budget=None, max_attempts=3):
    """Yield at most three complete candidates or unresolved construction attempts.

    Failure never removes a legal choice from a later MILP. Budget exhaustion
    propagates to the caller; no incomplete candidate or budget-late candidate
    is yielded. The caller may stop iteration immediately after a safe receipt.
    Optional reduced starts have the same fixture-only meaning as build_model.
    """
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
        raise ValueError("max_attempts must be an integer in 1..3")
    _check(budget)
    grid, window = _fraction(instance["start_grid_ms"]), _fraction(instance["window_ms"])
    if grid <= 0 or window <= 0:
        raise ValueError("Window and start grid must be positive")
    reduced_starts = _start_sets(instance, starts, grid, window, budget)
    deployment, deployment_records = _deployment(instance, budget)
    for rank, domain_opps in _templates(instance, max_attempts, budget):
        _check(budget)
        record = {"rule_version": RULE_VERSION, "template_rank": rank,
                  "domain_opps": dict(domain_opps), "shared_deployment": dict(deployment),
                  "deployment_records": deployment_records,
                  "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
                  "exclusion": "NONE"}
        scenes = {}
        failure = None
        for scene in sorted(instance["scenarios"], key=lambda item: item["id"]):
            rows, failure = _scene_schedule(instance, scene, deployment, domain_opps,
                                           reduced_starts, grid, window, budget)
            if failure is not None:
                break
            scenes[scene["id"]] = rows
        if failure is not None:
            record.update(status="CONSTRUCTION_UNRESOLVED", details=failure)
        else:
            candidate = {"scenes": scenes}
            _check(budget)
            validation = validate_schedule(instance, candidate)
            _check(budget)
            if validation["state"] == "SCHEDULE_VALID_THERMAL_UNCHECKED":
                record.update(status="COMPLETE_LEGAL_CANDIDATE", candidate=candidate)
            else:
                record.update(status="CONSTRUCTION_UNRESOLVED",
                              details={"reason": "INDEPENDENT_STRUCTURAL_CHECK_REJECTED",
                                       "validation": validation})
        _check(budget)
        yield record


def construct_initial_candidates(instance, starts=None, budget=None, max_attempts=3):
    """Collect attempts for prechecks; operational callers should use the iterator."""
    attempts = list(iter_initial_candidates(instance, starts=starts, budget=budget,
                                            max_attempts=max_attempts))
    return {"rule_version": RULE_VERSION, "rules": dict(RULES), "attempts": attempts,
            "candidates": [attempt for attempt in attempts
                           if attempt["status"] == "COMPLETE_LEGAL_CANDIDATE"],
            "coverage_status": "BOUNDED_SEEDS_ONLY_NOT_EXHAUSTIVE",
            "thermal_status": "NOT_EVALUATED", "optimality_status": "NOT_PROVED"}
