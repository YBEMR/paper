"""Exact complete-schedule checks and power reconstruction for chapter 3.

This module checks one supplied candidate. It does not search, propagate
temperature, integrate energy, or use any historical inputs/results.

Candidate format::

    {"scenes": {scenario_id: [
        {"stage_id": instance_id, "unit": "CPU1", "opp": "L", "start_ms": "0"}
    ]}}

All declared scenarios and Stage instances must occur exactly once. Scalars
are exact strings, integers or Fractions; binary floats are rejected. Returned
physical scalars use reduced rational strings and times remain milliseconds.
"""

from fractions import Fraction

from control_policy import AUTO_LOW_IMMEDIATE_V1, resolve_idle_policy
from start_domain import explicit_start_sets


class InvalidSchedule(ValueError):
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.reason = reason
        self.details = details


def _require(condition, reason, **details):
    if not condition:
        raise InvalidSchedule(reason, **details)


def _fraction(value):
    _require(not isinstance(value, bool) and isinstance(value, (str, int, Fraction)),
             "NONEXACT_SCALAR", value_type=type(value).__name__)
    return Fraction(value)


def _unique(items, key, reason):
    out = {}
    for item in items:
        identity = item[key]
        _require(identity not in out, reason, identity=identity)
        out[identity] = item
    return out


def _rational_dict(values):
    return {key: str(value) for key, value in values.items()}


def _check_platform(platform):
    nodes = platform["node_order"]
    _require(bool(nodes) and len(nodes) == len(set(nodes)), "INVALID_NODE_IDENTITIES")
    units = _unique(platform["units"], "id", "DUPLICATE_UNIT")
    domains = platform["domains"]
    _require(bool(units) and bool(domains), "EMPTY_PLATFORM")
    # The current package explicitly has one metered group per control domain.
    # Reject a changed schema instead of inventing allocation/OPP semantics.
    for unit_id, unit in units.items():
        domain_id = unit["domain_id"]
        _require(domain_id in domains and unit_id in domains[domain_id]["unit_ids"],
                 "INVALID_DOMAIN_MEMBERSHIP", unit=unit_id)
        _require(unit["power_group_id"] == domain_id, "UNSUPPORTED_POWER_GROUP", unit=unit_id)
        _require(unit["thermal_node_id"] in nodes, "UNKNOWN_THERMAL_NODE", unit=unit_id)
    _require(len({unit["thermal_node_id"] for unit in units.values()}) == len(units),
             "UNSUPPORTED_MULTIPLE_UNITS_PER_LOCAL_NODE")
    _require(set(unit["thermal_node_id"] for unit in units.values()) == set(nodes),
             "UNASSIGNED_LOCAL_NODE")
    for domain_id, domain in domains.items():
        members = domain["unit_ids"]
        _require(bool(members) and len(members) == len(set(members)) and
                 all(u in units and units[u]["domain_id"] == domain_id for u in members),
                 "INVALID_DOMAIN_MEMBERSHIP", domain=domain_id)
        distribution = list(map(_fraction, domain["baseline_heat_distribution"]))
        _require(len(distribution) == len(nodes) and all(v >= 0 for v in distribution)
                 and sum(distribution) == 1, "INVALID_BASELINE_DISTRIBUTION", domain=domain_id)
        _require(bool(domain["opps"]), "EMPTY_OPP_SET", domain=domain_id)
        for opp_id, opp in domain["opps"].items():
            _require(_fraction(opp["frequency_GHz"]) > 0 and _fraction(opp["voltage_V"]) > 0,
                     "INVALID_WORKING_POINT", domain=domain_id, opp=opp_id)
            _require(_fraction(domain["baseline_W"][opp_id]) >= 0 and
                     _fraction(domain["local_temperature_slope_W_per_K"][opp_id]) >= 0,
                     "INVALID_POWER_COEFFICIENT", domain=domain_id, opp=opp_id)
    _require(_fraction(platform["external_common_power_W"]) >= 0,
             "INVALID_EXTERNAL_POWER")
    _require(len(platform["external_common_heat_distribution"]) == len(nodes) and
             all(_fraction(v) == 0 for v in platform["external_common_heat_distribution"]),
             "UNSUPPORTED_EXTERNAL_HEAT_INJECTION")
    return nodes, units, domains


def _check_rules(instance):
    rules = instance["execution_rules"]
    for name in ("preemption", "migration", "in_stage_opp_change"):
        _require(rules[name] is False, "UNSUPPORTED_EXECUTION_RULE", rule=name)
    for name in ("switch_only_when_domain_empty",):
        _require(rules[name] is True, "UNSUPPORTED_EXECUTION_RULE", rule=name)
    _require(rules["interval_convention"] == "[start,end)", "UNSUPPORTED_INTERVAL_CONVENTION")
    for name in ("extra_transfer_time_ms", "extra_switch_time_ms", "extra_handoff_time_ms",
                 "extra_transfer_energy_J", "extra_switch_energy_J", "extra_handoff_energy_J"):
        _require(_fraction(rules[name]) == 0, "UNSUPPORTED_NONZERO_OVERHEAD", rule=name)
    try:
        return resolve_idle_policy(instance)
    except ValueError as error:
        raise InvalidSchedule("UNSUPPORTED_IDLE_POLICY", message=str(error)) from error


def _scene_rows(instance, scene, supplied, units, domains, shared_deployment, window, grid,
                explicit_starts=None):
    _require(isinstance(supplied, list), "SCENE_ROWS_MUST_BE_LIST", scenario=scene["id"])
    stages = _unique(scene["stage_instances"], "id", "DUPLICATE_INPUT_STAGE")
    requests = _unique(scene["requests"], "id", "DUPLICATE_INPUT_REQUEST")
    _require(bool(stages) and bool(requests), "EMPTY_SCENARIO", scenario=scene["id"])
    _require(all(st["request_id"] in requests for st in stages.values()), "UNKNOWN_STAGE_REQUEST")
    for request_id, request in requests.items():
        ids = request["stage_instance_ids"]
        _require(bool(ids) and len(ids) == len(set(ids)) and
                 set(ids) == {sid for sid, st in stages.items() if st["request_id"] == request_id},
                 "REQUEST_STAGE_MEMBERSHIP", request=request_id)
        _require(0 <= _fraction(request["release_ms"]) <= _fraction(request["deadline_ms"]) <= window,
                 "INVALID_REQUEST_WINDOW", request=request_id)
    supplied_ids = []
    for row in supplied:
        _require(isinstance(row, dict) and set(row) == {"stage_id", "unit", "opp", "start_ms"},
                 "CANDIDATE_ROW_FIELDS", scenario=scene["id"])
        supplied_ids.append(row["stage_id"])
    _require(len(supplied_ids) == len(set(supplied_ids)), "DUPLICATE_STAGE_ASSIGNMENT", scenario=scene["id"])
    _require(set(supplied_ids) == set(stages), "INCOMPLETE_STAGE_COVERAGE", scenario=scene["id"],
             missing=sorted(set(stages)-set(supplied_ids)), extra=sorted(set(supplied_ids)-set(stages)))
    rows = []
    for given in supplied:
        stage_id = given["stage_id"]
        stage = stages[stage_id]
        shared_id = stage["shared_stage_id"]
        matches = [mode for mode in instance["stage_modes"][shared_id]
                   if mode["unit_id"] == given["unit"] and mode["opp_id"] == given["opp"]]
        _require(len(matches) == 1, "ILLEGAL_OR_AMBIGUOUS_MODE", stage=stage_id)
        mode = matches[0]
        unit_id, opp_id = mode["unit_id"], mode["opp_id"]
        _require(unit_id in units, "UNKNOWN_EXECUTION_UNIT", stage=stage_id)
        unit = units[unit_id]
        domain_id = unit["domain_id"]
        _require(mode["shared_stage_id"] == shared_id and mode["domain_id"] == domain_id and
                 mode["thermal_node_id"] == unit["thermal_node_id"] and
                 mode["power_group_id"] == unit["power_group_id"] and opp_id in domains[domain_id]["opps"],
                 "MODE_PLATFORM_MISMATCH", stage=stage_id)
        physical_opp = domains[domain_id]["opps"][opp_id]
        _require(_fraction(mode["frequency_GHz"]) == _fraction(physical_opp["frequency_GHz"]) and
                 _fraction(mode["voltage_V"]) == _fraction(physical_opp["voltage_V"]),
                 "MODE_WORKING_POINT_MISMATCH", stage=stage_id)
        start = _fraction(given["start_ms"])
        duration = _fraction(mode["duration_ms"])
        power = _fraction(mode["activity_power_W"])
        _require(duration > 0 and power >= 0, "INVALID_MODE_COST", stage=stage_id)
        _require(start >= 0 and (start / grid).denominator == 1, "START_OUTSIDE_GRID", stage=stage_id)
        _require(explicit_starts is None or start in explicit_starts[scene["id"]][stage_id],
                 "START_OUTSIDE_DECLARED_DOMAIN", stage=stage_id, start_ms=str(start))
        finish = start + duration
        request = requests[stage["request_id"]]
        release, deadline = _fraction(request["release_ms"]), _fraction(request["deadline_ms"])
        _require(start >= release, "BEFORE_RELEASE", stage=stage_id)
        _require(finish <= window, "WINDOW_EXCEEDED", stage=stage_id)
        _require(finish <= deadline, "REQUEST_DEADLINE_EXCEEDED", stage=stage_id,
                 request=stage["request_id"], finish_ms=str(finish), deadline_ms=str(deadline))
        if shared_id in shared_deployment:
            _require(shared_deployment[shared_id] == unit_id, "SHARED_DEPLOYMENT_MISMATCH",
                     shared_stage_id=shared_id, expected_unit=shared_deployment[shared_id], unit=unit_id)
        else:
            shared_deployment[shared_id] = unit_id
        rows.append({"stage_id": stage_id, "shared_stage_id": shared_id,
                     "request_id": stage["request_id"], "unit": unit_id, "opp": opp_id,
                     "domain_id": domain_id, "thermal_node_id": unit["thermal_node_id"],
                     "start_ms": start, "end_ms": finish, "duration_ms": duration,
                     "activity_power_W": power, "release_ms": release, "deadline_ms": deadline})
    by_id = {row["stage_id"]: row for row in rows}
    for edge in scene["dependencies"]:
        _require(isinstance(edge, list) and len(edge) == 2 and
                 all(sid in by_id for sid in edge), "INVALID_DEPENDENCY")
        predecessor, successor = edge
        _require(by_id[predecessor]["end_ms"] <= by_id[successor]["start_ms"],
                 "DEPENDENCY_VIOLATION", predecessor=predecessor, successor=successor)
    for index, left in enumerate(rows):
        for right in rows[index+1:]:
            overlap = max(left["start_ms"], right["start_ms"]) < min(left["end_ms"], right["end_ms"])
            if not overlap:
                continue
            _require(left["unit"] != right["unit"], "EXECUTION_UNIT_OVERLAP",
                     stages=[left["stage_id"], right["stage_id"]])
            _require(left["domain_id"] != right["domain_id"] or left["opp"] == right["opp"],
                     "FREQUENCY_DOMAIN_CONFLICT", stages=[left["stage_id"], right["stage_id"]])
    return sorted(rows, key=lambda row: (row["start_ms"], row["stage_id"]))


def _power_segments(platform, scene, rows, nodes, units, domains, window, idle_policy=None):
    entry = scene["entry"]
    _require(entry["unfinished_work"] == [], "UNSUPPORTED_UNFINISHED_ENTRY_WORK")
    held = dict(entry["domain_opp"])
    _require(set(held) == set(domains) and
             all(opp in domains[domain]["opps"] for domain, opp in held.items()),
             "INVALID_ENTRY_OPPS", scenario=scene["id"])
    _require(len(entry["temperature_degC"]) == len(nodes), "INVALID_ENTRY_TEMPERATURE_DIMENSIONS")
    for value in entry["temperature_degC"]:
        _fraction(value)  # Type check only. Thermal admissibility is deliberately not claimed here.
    events = sorted({Fraction(0), window} | {row[k] for row in rows for k in ("start_ms", "end_ms")})
    out = []
    for start, finish in zip(events, events[1:]):
        new = [row for row in rows if row["start_ms"] == start]
        continuing = [row for row in rows if row["start_ms"] < start < row["end_ms"]]
        for domain in domains:
            requested = {row["opp"] for row in new if row["domain_id"] == domain}
            if not requested:
                if idle_policy == AUTO_LOW_IMMEDIATE_V1 and not any(
                        row["domain_id"] == domain for row in continuing):
                    held[domain] = "L"
                continue  # Legacy idle holds; an occupied domain never drops.
            _require(len(requested) == 1, "SIMULTANEOUS_OPP_CONFLICT", domain=domain)
            opp = next(iter(requested))
            _require(all(row["opp"] == opp for row in continuing if row["domain_id"] == domain),
                     "BUSY_DOMAIN_OPP_CHANGE", domain=domain)
            held[domain] = opp
        active = [row for row in rows if row["start_ms"] <= start < row["end_ms"]]
        group_base, node_base = {}, {node: Fraction(0) for node in nodes}
        slopes, activity = dict(node_base), dict(node_base)
        for domain_id, domain in domains.items():
            opp = held[domain_id]
            baseline = _fraction(domain["baseline_W"][opp])
            group_base[domain_id] = baseline
            for node, weight in zip(nodes, domain["baseline_heat_distribution"]):
                node_base[node] += baseline * _fraction(weight)
            slope = _fraction(domain["local_temperature_slope_W_per_K"][opp])
            for unit_id in domain["unit_ids"]:
                slopes[units[unit_id]["thermal_node_id"]] += slope
        for row in active:
            activity[row["thermal_node_id"]] += row["activity_power_W"]
        _require(sum(group_base.values()) == sum(node_base.values()), "BASELINE_ACCOUNTING_MISMATCH")
        out.append({
            "start_ms": str(start), "end_ms": str(finish), "duration_ms": str(finish-start),
            "domain_opps": dict(held), "active_stage_ids": [row["stage_id"] for row in active],
            "baseline_by_power_group_W": _rational_dict(group_base),
            "baseline_by_node_W": _rational_dict(node_base),
            "activity_by_node_W": _rational_dict(activity),
            "local_leakage_slope_W_per_K": _rational_dict(slopes),
            "node_power_constant_at_reference_W": _rational_dict({node: node_base[node]+activity[node] for node in nodes}),
            "reference_temperature_degC": str(_fraction(platform["reference_temperature_degC"])),
            "external_common_power_W": str(_fraction(platform["external_common_power_W"])),
            "external_common_injected_heat_W": "0"
        })
    return out


def validate_schedule(instance, candidate):
    """Check a complete candidate and reconstruct all power-state intervals.

    A valid result is explicitly THERMAL_UNCHECKED. It has no energy value,
    safe/optimal flag or ranking permission. Invalid input/candidate returns
    only its reason; a valid scene prefix is never exposed as a full result.
    """
    try:
        _require(instance["schema_version"] == "chapter3-input-v0.1", "UNSUPPORTED_INPUT_SCHEMA")
        idle_policy = _check_rules(instance)
        window, grid = _fraction(instance["window_ms"]), _fraction(instance["start_grid_ms"])
        _require(window > 0 and grid > 0, "INVALID_WINDOW_OR_GRID")
        explicit_starts = explicit_start_sets(instance)
        nodes, units, domains = _check_platform(instance["platform"])
        scenes = _unique(instance["scenarios"], "id", "DUPLICATE_SCENARIO")
        _require(bool(scenes), "EMPTY_SCENARIO_SET")
        _require(isinstance(candidate, dict) and set(candidate) == {"scenes"} and
                 isinstance(candidate["scenes"], dict), "CANDIDATE_FIELDS")
        _require(set(candidate["scenes"]) == set(scenes), "INCOMPLETE_SCENARIO_COVERAGE")
        shared_deployment, result_scenes = {}, {}
        for scene_id, scene in scenes.items():
            rows = _scene_rows(instance, scene, candidate["scenes"][scene_id], units, domains,
                               shared_deployment, window, grid, explicit_starts)
            segments = _power_segments(instance["platform"], scene, rows, nodes, units, domains, window, idle_policy)
            completions = {request["id"]: str(max(row["end_ms"] for row in rows
                           if row["request_id"] == request["id"])) for request in scene["requests"]}
            result_scenes[scene_id] = {
                "rows": [{key: str(value) if isinstance(value, Fraction) else value
                          for key, value in row.items()} for row in rows],
                "request_completion_ms": completions,
                "segments": segments
            }
        return {"state": "SCHEDULE_VALID_THERMAL_UNCHECKED", "problem_id": instance["id"],
                "node_order": list(nodes), "shared_deployment": shared_deployment,
                "scenes": result_scenes, "thermal_status": "NOT_EVALUATED",
                "energy_status": "NOT_EVALUATED"}
    except InvalidSchedule as error:
        return {"state": "INVALID_SCHEDULE", "reason": error.reason, "details": error.details,
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        return {"state": "INVALID_SCHEDULE", "reason": "MALFORMED_INPUT_OR_CANDIDATE",
                "details": {"error_type": type(error).__name__, "message": str(error)},
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
