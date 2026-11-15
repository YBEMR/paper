"""Exact, structural graph reconstruction for the K179 scheduling proposal.

This module never searches real inputs, calls an optimizer, evaluates heat, or
certifies a SAFE result.  ``schedules`` and ``start_domain`` are the existing
chapter-3 modules; the entry point supplies their directory on ``sys.path``.
Returned nonthermal energy is a ranking value, not a true-energy certificate.
"""

from bisect import bisect_left
from copy import deepcopy
from fractions import Fraction
from itertools import combinations

from schedules import validate_schedule
from start_domain import explicit_start_sets


class GraphInputError(ValueError):
    """An invalid declaration, never a budget-exhaustion signal."""


def _check(budget):
    if budget is not None:
        budget.check()


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise GraphInputError("NONEXACT_SCALAR")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise GraphInputError("INVALID_EXACT_SCALAR") from error


def _no_floats(value, budget):
    """Check even unused physical declarations, without converting any scalar."""
    _check(budget)
    if isinstance(value, float):
        raise GraphInputError("NONEXACT_SCALAR")
    if isinstance(value, dict):
        for item in value.values():
            _no_floats(item, budget)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _no_floats(item, budget)


def _validated(instance, candidate, budget):
    _no_floats(instance, budget)
    _no_floats(candidate, budget)
    _check(budget)
    validation = validate_schedule(instance, candidate)
    _check(budget)
    if validation.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
        raise GraphInputError("INCUMBENT_INVALID:" + validation.get("reason", "UNKNOWN"))
    return validation


def _time_key(row):
    return _q(row["start_ms"]), row["stage_id"]


def related_pairs(instance, candidate, *, budget=None):
    """Return stable resource-related pairs from a structurally valid incumbent.

    Adjacent means consecutive by actual start and Stage identity on one unit.
    CPU-domain pairs include nonadjacent tasks, since even distinct CPU cores
    share an OPP.  Pair identities are unique; metadata lists both relationships
    when appropriate.  M/H-containing pairs precede L-only pairs, then resource,
    time, Stage identity, and scene identity decide ties.
    """
    validation = _validated(instance, candidate, budget)
    units = {unit["id"]: unit for unit in instance["platform"]["units"]}
    found = []
    for sid, result in sorted(validation["scenes"].items()):
        _check(budget)
        rows = sorted(result["rows"], key=_time_key)
        by_id = {row["stage_id"]: row for row in rows}
        pairs = {}

        def add(left, right, relationship, resource_id):
            _check(budget)
            ordered = sorted((left, right), key=_time_key)
            ids = tuple(row["stage_id"] for row in ordered)
            item = pairs.setdefault(ids, {
                "scene_id": sid, "stage_ids": list(ids),
                "relationships": [], "resource_ids": [],
            })
            if relationship not in item["relationships"]:
                item["relationships"].append(relationship)
            if resource_id not in item["resource_ids"]:
                item["resource_ids"].append(resource_id)

        for uid in sorted(units):
            _check(budget)
            local = [row for row in rows if row["unit"] == uid]
            for left, right in zip(local, local[1:]):
                add(left, right, "same_unit_adjacent", uid)
        for left, right in combinations(rows, 2):
            _check(budget)
            if (units[left["unit"]].get("device_class") == "CPU"
                    and units[right["unit"]].get("device_class") == "CPU"
                    and left["domain_id"] == right["domain_id"]):
                add(left, right, "shared_cpu_domain", left["domain_id"])
        for item in pairs.values():
            _check(budget)
            item["relationships"].sort()
            item["resource_ids"].sort()
            selected = [by_id[iid] for iid in item["stage_ids"]]
            item["contains_medium_or_high"] = any(row["opp"] in ("M", "H") for row in selected)
            item["incumbent_start_ms"] = [str(_q(row["start_ms"])) for row in selected]
            resource = ("domain", selected[0]["domain_id"]) if (
                "shared_cpu_domain" in item["relationships"]) else ("unit", selected[0]["unit"])
            item["resource_kind"], item["resource_id"] = resource
            found.append(item)
    found.sort(key=lambda item: (
        not item["contains_medium_or_high"], item["resource_kind"], item["resource_id"],
        tuple(_q(t) for t in item["incumbent_start_ms"]),
        tuple(item["stage_ids"]), item["scene_id"],
    ))
    _check(budget)
    return found


def _nonthermal_energy(instance, validation, budget):
    """Use the original full-window power ledger, counting each group once."""
    totals = {"activity_J": Fraction(0), "domain_baseline_J": Fraction(0),
              "external_common_J": Fraction(0)}
    by_scene = {}
    weight_total = Fraction(0)
    for scene in instance["scenarios"]:
        _check(budget)
        weight = _q(scene["weight"])
        if weight < 0:
            raise GraphInputError("NEGATIVE_SCENE_WEIGHT")
        weight_total += weight
        subtotal = {key: Fraction(0) for key in totals}
        for segment in validation["scenes"][scene["id"]]["segments"]:
            _check(budget)
            seconds = _q(segment["duration_ms"]) / 1000
            subtotal["activity_J"] += seconds * sum(
                (_q(v) for v in segment["activity_by_node_W"].values()), Fraction(0))
            subtotal["domain_baseline_J"] += seconds * sum(
                (_q(v) for v in segment["baseline_by_power_group_W"].values()), Fraction(0))
            subtotal["external_common_J"] += seconds * _q(segment["external_common_power_W"])
        for key in totals:
            _check(budget)
            totals[key] += weight * subtotal[key]
        by_scene[scene["id"]] = {
            **{key: str(value) for key, value in subtotal.items()},
            "weight": str(weight), "nonthermal_energy_J": str(sum(subtotal.values())),
        }
    _check(budget)
    if weight_total != 1:
        raise GraphInputError("SCENE_WEIGHTS_MUST_SUM_TO_ONE")
    return str(sum(totals.values())), {key: str(value) for key, value in totals.items()}, by_scene


def reconstruct(instance, incumbent, scene_id, selected_stages, opp_overrides, *,
                orientation="incumbent", template="earliest", budget=None):
    """Reconstruct one fixed-unit, fixed-mode/order skeleton on the exact grid.

    Only selected Stage OPPs can change.  All resource conflicts are rebuilt,
    including new conflicts with unselected third parties; obsolete same-domain
    same-OPP edges are omitted.  For the selected pair only, ``reverse`` flips
    the incumbent start/id resource direction.  Other directions use that
    original stable order.  ``preserve`` keeps start floors only for unselected
    tasks outside the selected tasks' transitive *task-DAG* successors.

    Refusal covers this skeleton/template only.  No temperature or full-energy
    judgment is made.  The supplied Budget's exception always propagates.
    """
    edges = []
    try:
        initial = _validated(instance, incumbent, budget)
        if orientation not in ("incumbent", "reverse") or template not in ("earliest", "preserve"):
            raise GraphInputError("UNKNOWN_RECONSTRUCTION_POLICY")
        scenes = {scene["id"]: scene for scene in instance["scenarios"]}
        if scene_id not in scenes:
            raise GraphInputError("UNKNOWN_SCENE")
        scene = scenes[scene_id]
        old_rows = {row["stage_id"]: row for row in initial["scenes"][scene_id]["rows"]}
        if (not isinstance(selected_stages, (list, tuple)) or len(selected_stages) not in (1, 2)
                or any(not isinstance(iid, str) for iid in selected_stages)
                or len(set(selected_stages)) != len(selected_stages)
                or not set(selected_stages) <= set(old_rows)):
            raise GraphInputError("INVALID_SELECTED_STAGES")
        selected = set(selected_stages)
        if (not isinstance(opp_overrides, dict) or not set(opp_overrides) <= selected
                or any(not isinstance(opp, str) for opp in opp_overrides.values())):
            raise GraphInputError("INVALID_OPP_OVERRIDES")
        requests = {request["id"]: request for request in scene["requests"]}
        stages = {stage["id"]: stage for stage in scene["stage_instances"]}
        rows = {}
        for iid, old in old_rows.items():
            _check(budget)
            opp = opp_overrides.get(iid, old["opp"])
            matches = [mode for mode in instance["stage_modes"][stages[iid]["shared_stage_id"]]
                       if mode["unit_id"] == old["unit"] and mode["opp_id"] == opp]
            if len(matches) != 1:
                raise GraphInputError("ILLEGAL_OR_AMBIGUOUS_FIXED_UNIT_OPP")
            rows[iid] = {**old, "opp": opp, "duration_ms": str(_q(matches[0]["duration_ms"]))}
        edge_reasons = {}

        def add_edge(left, right, reason):
            _check(budget)
            edge_reasons.setdefault((left, right), set()).add(reason)

        task_successors = {iid: set() for iid in rows}
        for left, right in scene["dependencies"]:
            _check(budget)
            add_edge(left, right, "task_dependency")
            task_successors[left].add(right)
        for left_id, right_id in combinations(sorted(rows), 2):
            _check(budget)
            left, right = rows[left_id], rows[right_id]
            if left["unit"] == right["unit"]:
                reason = "same_unit"
            elif left["domain_id"] == right["domain_id"] and left["opp"] != right["opp"]:
                reason = "shared_domain_different_opp"
            else:
                continue
            ordered = sorted((left_id, right_id), key=lambda iid: _time_key(old_rows[iid]))
            if selected == {left_id, right_id} and orientation == "reverse":
                ordered.reverse()
            add_edge(ordered[0], ordered[1], reason)
        edges = [{"from": left, "to": right, "reasons": sorted(reasons)}
                 for (left, right), reasons in sorted(edge_reasons.items())]
        predecessors = {iid: set() for iid in rows}
        successors = {iid: set() for iid in rows}
        for left, right in edge_reasons:
            _check(budget)
            predecessors[right].add(left)
            successors[left].add(right)
        descendants, pending = set(selected), list(sorted(selected))
        while pending:
            _check(budget)
            current = pending.pop()
            for nxt in sorted(task_successors[current]):
                _check(budget)
                if nxt not in descendants:
                    descendants.add(nxt)
                    pending.append(nxt)
        declared = explicit_start_sets(instance, budget)
        grid, window = _q(instance["start_grid_ms"]), _q(instance["window_ms"])
        counts = {iid: len(pred) for iid, pred in predecessors.items()}
        ready = [iid for iid, count in counts.items() if count == 0]
        starts, ends, order = {}, {}, []
        while ready:
            _check(budget)
            ready.sort(key=lambda iid: _time_key(old_rows[iid]))
            iid = ready.pop(0)
            request = requests[stages[iid]["request_id"]]
            lower = max(Fraction(0), _q(request["release_ms"]))
            if template == "preserve" and iid not in descendants:
                lower = max(lower, _q(old_rows[iid]["start_ms"]))
            for pred in predecessors[iid]:
                _check(budget)
                lower = max(lower, ends[pred])
            if declared is None:
                start = -((-lower) // grid) * grid
            else:
                choices = declared[scene_id][iid]
                index = bisect_left(choices, lower)
                if index == len(choices):
                    raise GraphInputError("NO_LEGAL_START_IN_SKELETON")
                start = choices[index]
            end = start + _q(rows[iid]["duration_ms"])
            if end > window or end > _q(request["deadline_ms"]):
                raise GraphInputError("SKELETON_DEADLINE_OR_WINDOW_EXCEEDED")
            starts[iid], ends[iid] = start, end
            order.append(iid)
            for nxt in sorted(successors[iid]):
                _check(budget)
                counts[nxt] -= 1
                if counts[nxt] == 0:
                    ready.append(nxt)
        if len(order) != len(rows):
            raise GraphInputError("SKELETON_DIRECTED_CYCLE")
        candidate = deepcopy(incumbent)
        for row in candidate["scenes"][scene_id]:
            _check(budget)
            iid = row["stage_id"]
            row["opp"] = rows[iid]["opp"]
            row["start_ms"] = str(starts[iid])
        _check(budget)
        validation = validate_schedule(instance, candidate)
        _check(budget)
        if validation.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
            raise GraphInputError("RECONSTRUCTED_VALIDATION_REJECTED:" + validation.get("reason", "UNKNOWN"))
        energy, components, energy_scenes = _nonthermal_energy(instance, validation, budget)
        _check(budget)
        return {"state": "COMPLETE_LEGAL_CANDIDATE", "candidate": candidate,
                "reason": None, "scene_id": scene_id, "selected_stages": sorted(selected),
                "orientation": orientation, "template": template, "edges": edges,
                "topological_order": order, "start_ms": {iid: str(v) for iid, v in starts.items()},
                "end_ms": {iid: str(v) for iid, v in ends.items()},
                "scene_end_ms": str(max(ends.values(), default=Fraction(0))),
                "nonthermal_energy_J": energy, "nonthermal_components_J": components,
                "nonthermal_by_scene": energy_scenes,
                "thermal_status": "NOT_EVALUATED", "true_energy_status": "NOT_EVALUATED",
                "rejection_scope": "SKELETON_AND_TEMPLATE_ONLY"}
    except GraphInputError as error:
        _check(budget)
        return {"state": "RECONSTRUCTION_REJECTED", "candidate": None,
                "reason": str(error), "scene_id": scene_id, "edges": edges,
                "thermal_status": "NOT_EVALUATED", "true_energy_status": "NOT_EVALUATED",
                "rejection_scope": "SKELETON_AND_TEMPLATE_ONLY"}
