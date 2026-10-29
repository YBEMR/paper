"""Optimistic time bounds, with no LP and no temperature/energy inference."""

from fractions import Fraction
from itertools import combinations

from .contract import ContractError, normalize, exact, shared_units, duration


def lower_bounds(data, mapping):
    data = normalize(data)
    allowed = shared_units(data)
    if set(mapping) != set(allowed) or any(mapping[s] not in allowed[s] for s in allowed):
        raise ContractError("INVALID_SHARED_MAPPING")
    units = sorted(u["id"] for u in data["platform"]["units"])
    fastest = {sid: min(duration(data, sid, unit, opp)
                        for unit in allowed[sid] for opp in ("H", "M", "L")) for sid in allowed}
    result = {}
    for scene in data["scenarios"]:
        stages = {j["id"]: j for j in scene["stage_instances"]}
        reqs = {r["id"]: r for r in scene["requests"]}
        pred = {sid: [] for sid in stages}
        for left, right in scene["dependencies"]:
            pred[right].append(left)
        # Induced per-request critical paths deliberately ignore external predecessors.
        cp = {}
        for rid in reqs:
            members = set(reqs[rid]["stage_instance_ids"])
            ends = {}
            while len(ends) < len(members):
                for sid in sorted(members - ends.keys()):
                    local = [p for p in pred[sid] if p in members]
                    if all(p in ends for p in local):
                        ends[sid] = max((ends[p] for p in local), default=Fraction(0)) + fastest[stages[sid]["shared_stage_id"]]
            cp[rid] = max(ends.values())
        capacities = {}
        for size in range(1, len(units) + 1):
            for subset in combinations(units, size):
                load = sum((fastest[j["shared_stage_id"]] for j in stages.values()
                            if set(allowed[j["shared_stage_id"]]).issubset(subset)), Fraction(0))
                capacities[",".join(subset)] = load / size
        min_release = min(exact(r["release_ms"]) for r in reqs.values())
        global_lb = max([min_release + max(capacities.values())] +
                        [exact(reqs[r]["release_ms"]) + cp[r] for r in reqs])
        fixed = {unit: sum((min(duration(data, j["shared_stage_id"], unit, opp)
                                for opp in ("H", "M", "L"))
                            for j in stages.values() if mapping[j["shared_stage_id"]] == unit), Fraction(0))
                 for unit in units}
        result[scene["id"]] = {
            "request_critical_path_ms": {r: str(v) for r, v in cp.items()},
            "subset_capacity_duration_ms": {k: str(v) for k, v in capacities.items()},
            "scene_completion_lower_bound_ms": str(global_lb),
            "fixed_mapping_device_load_ms": {k: str(v) for k, v in fixed.items()},
            "fixed_mapping_completion_lower_bound_ms": str(max(global_lb, min_release + max(fixed.values()))),
            "thermal_status": "NOT_EVALUATED"}
    return result
