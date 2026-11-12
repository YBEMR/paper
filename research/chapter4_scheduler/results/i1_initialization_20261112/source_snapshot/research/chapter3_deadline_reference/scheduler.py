"""Deterministic mapping and earliest-gap scheduling (be8dd50f §3.1/3.2)."""

from copy import deepcopy
from fractions import Fraction

from .contract import (ContractError, normalize, contract_hash, content_hash,
                       exact, shared_units, duration)
from .checker import check_timetable


class ReferenceFailure(RuntimeError):
    """A construction/check failure is not a proof of task infeasibility."""


def choose_mapping(data):
    """Map once using weighted fastest H load, then lexicographic trial costs."""
    data = normalize(data)
    allowed = shared_units(data)
    units = sorted(unit["id"] for unit in data["platform"]["units"])
    scenes = data["scenarios"]
    occurrences = {(scene["id"], sid): [] for scene in scenes for sid in allowed}
    for scene in scenes:
        for stage in scene["stage_instances"]:
            occurrences[scene["id"], stage["shared_stage_id"]].append(stage["id"])
    scores = {}
    for sid in allowed:
        fastest = min(duration(data, sid, unit, "H") for unit in allowed[sid])
        scores[sid] = sum((exact(scene["weight"]) *
                           len(occurrences[scene["id"], sid]) * fastest
                           for scene in scenes), Fraction(0))
    loads = {scene["id"]: {unit: Fraction(0) for unit in units} for scene in scenes}
    mapping, decisions = {}, []
    for sid in sorted(allowed, key=lambda name: (-scores[name], name)):
        trials, costs = {}, {}
        for unit in allowed[sid]:
            trial = deepcopy(loads)
            for scene in scenes:
                trial[scene["id"]][unit] += (len(occurrences[scene["id"], sid]) *
                                              duration(data, sid, unit, "H"))
            maximum = max(value for row in trial.values() for value in row.values())
            weighted = sum((exact(scene["weight"]) * sum(trial[scene["id"]].values())
                            for scene in scenes), Fraction(0))
            costs[unit] = (maximum, weighted, unit)
            trials[unit] = trial
        unit = min(costs, key=costs.get)
        mapping[sid] = unit
        loads = trials[unit]
        decisions.append({"shared_stage_id": sid, "chosen_unit": unit,
                          "costs": {u: [str(costs[u][0]), str(costs[u][1]), u]
                                    for u in sorted(costs)}})
    return {"contract_hash": contract_hash(data), "mapping": mapping,
            "load_scores_ms": {sid: str(scores[sid]) for sid in sorted(scores)},
            "decisions": decisions,
            "loads_ms": {s: {u: str(v) for u, v in row.items()} for s, row in loads.items()}}


def _ceil_grid(value, grid):
    return -((-value) // grid) * grid


def _levels(stages, predecessors):
    levels = {}
    while len(levels) < len(stages):
        ready = sorted(s for s in stages if s not in levels and
                       all(p in levels for p in predecessors[s]))
        if not ready:
            raise ReferenceFailure("NO_READY_STAGE_AFTER_CONTRACT_VALIDATION")
        for sid in ready:
            levels[sid] = max((levels[p] + 1 for p in predecessors[sid]), default=0)
    return levels


def build_timetable(data, mapping, opp_id):
    """Low-level placement for an explicit legal mapping; no time horizon.

    build_references is the normative entry that obtains the unique mapping.
    This lower-level interface also permits hand fixtures to isolate placement.
    """
    data = normalize(data)
    if opp_id not in ("H", "M", "L"):
        raise ContractError("INVALID_REFERENCE_OPP", opp=opp_id)
    allowed = shared_units(data)
    if (not isinstance(mapping, dict) or set(mapping) != set(allowed) or
            any(mapping[s] not in allowed[s] for s in allowed)):
        raise ContractError("INVALID_SHARED_MAPPING")
    grid = exact(data["start_grid_ms"])
    output = {}
    for scene in data["scenarios"]:
        stages = {s["id"]: s for s in scene["stage_instances"]}
        requests = {r["id"]: r for r in scene["requests"]}
        pred = {sid: [] for sid in stages}
        for left, right in scene["dependencies"]:
            pred[right].append(left)
        levels = _levels(stages, pred)
        assigned, occupied = {}, {u["id"]: [] for u in data["platform"]["units"]}
        while len(assigned) < len(stages):
            ready = [sid for sid in stages if sid not in assigned and
                     all(p in assigned for p in pred[sid])]
            if not ready:
                raise ReferenceFailure("NO_READY_STAGE")
            sid = min(ready, key=lambda s: (
                exact(requests[stages[s]["request_id"]]["release_ms"]),
                levels[s], stages[s]["request_id"], s))
            stage = stages[sid]
            unit = mapping[stage["shared_stage_id"]]
            length = duration(data, stage["shared_stage_id"], unit, opp_id)
            earliest = max([Fraction(0), exact(requests[stage["request_id"]]["release_ms"])] +
                           [assigned[p]["end"] for p in pred[sid]])
            start = _ceil_grid(earliest, grid)
            for a, b, _ in sorted(occupied[unit]):
                if start + length <= a:
                    break
                if start < b and a < start + length:
                    start = _ceil_grid(b, grid)
            assigned[sid] = {"start": start, "end": start + length, "unit": unit}
            occupied[unit].append((start, start + length, sid))
        output[scene["id"]] = [
            {"stage_id": sid, "unit": assigned[sid]["unit"], "opp": opp_id,
             "start_ms": str(assigned[sid]["start"])}
            for sid in sorted(assigned)]
    return {"scenes": output}


def build_references(data):
    """One mapping, exactly one construction per H/M/L, independent checks."""
    data = normalize(data)
    record = choose_mapping(data)
    tables, checks = {}, {}
    for opp in ("H", "M", "L"):
        table = build_timetable(data, record["mapping"], opp)
        check = check_timetable(data, table, required_opp=opp)
        if check["state"] != "TIME_STRUCTURAL_VALID":
            raise ReferenceFailure("INDEPENDENT_TIME_CHECK_FAILED: " + str(check))
        tables[opp], checks[opp] = table, check
    return {"state": "REFERENCES_COMPLETE", "contract_hash": contract_hash(data),
            "mapping_origin_hash": content_hash(record), "mapping_record": record,
            "timetables": tables, "checks": checks,
            "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}


def project_references(full_data, bundle, subset_data):
    """S1 takes scenes from an existing full-family reference; no rescheduling."""
    full, sub = normalize(full_data), normalize(subset_data)
    full_hash = contract_hash(full)
    if full["derivation"]["axis"] not in ("BASE", "S2"):
        raise ContractError("S1_REQUIRES_FULL_BASE_FAMILY")
    if (sub["derivation"]["axis"] != "S1" or
            sub["derivation"]["parent_contract_hash"] != full_hash or
            bundle.get("contract_hash") != full_hash):
        raise ContractError("S1_PARENT_MISMATCH")
    record = bundle.get("mapping_record")
    if (not isinstance(record, dict) or record.get("contract_hash") != full_hash or
            bundle.get("mapping_origin_hash") != content_hash(record)):
        raise ContractError("S1_MAPPING_ORIGIN_MISMATCH")
    for key in ("root_family_id", "topology_id", "platform", "stage_profiles",
                "execution_rules", "start_grid_ms", "response_model", "context"):
        if sub[key] != full[key]:
            raise ContractError("S1_NON_SCENE_CHANGE", field=key)
    originals = {s["id"]: s for s in full["scenarios"]}
    for scene in sub["scenarios"]:
        origin = originals.get(scene["id"])
        if origin is None or {k: v for k, v in scene.items() if k != "weight"} != {
                k: v for k, v in origin.items() if k != "weight"}:
            raise ContractError("S1_SCENE_CHANGED", scene=scene["id"])
    if set(bundle.get("timetables", {})) != {"H", "M", "L"}:
        raise ContractError("INCOMPLETE_REFERENCE_BUNDLE")
    tables, checks = {}, {}
    for opp in ("H", "M", "L"):
        original_check = check_timetable(full, bundle["timetables"][opp], required_opp=opp)
        if original_check["state"] != "TIME_STRUCTURAL_VALID":
            raise ContractError("INVALID_SOURCE_REFERENCE", opp=opp)
        if original_check["shared_deployment"] != bundle["mapping_record"]["mapping"]:
            raise ContractError("REFERENCE_MAPPING_MISMATCH")
        table = {"scenes": {s["id"]: deepcopy(bundle["timetables"][opp]["scenes"][s["id"]])
                            for s in sub["scenarios"]}}
        check = check_timetable(sub, table, required_opp=opp)
        if check["state"] != "TIME_STRUCTURAL_VALID":
            raise ReferenceFailure("S1_PROJECTION_CHECK_FAILED")
        tables[opp], checks[opp] = table, check
    return {"state": "REFERENCES_COMPLETE", "contract_hash": contract_hash(sub),
            "mapping_origin_hash": bundle["mapping_origin_hash"],
            "mapping_record": deepcopy(bundle["mapping_record"]),
            "timetables": tables, "checks": checks,
            "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
