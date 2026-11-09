"""Exact fixed-device reconstruction with one certified blocking-edge change.

Only structural scheduling and the original nonthermal ledger are used.  This
module never starts HEFT, an optimizer, or a thermal/energy integration.  A
rejection concerns this order skeleton/template, never the full problem.
"""
from bisect import bisect_left
from copy import deepcopy
from fractions import Fraction
from itertools import combinations

from .. import graph_core as original


GraphInputError = original.GraphInputError
_check, _q = original._check, original._q
RESOURCE_REASONS = frozenset(("same_unit", "shared_domain_different_opp"))


def _packet(scene_id, selected=(), orientation="incumbent", template="earliest"):
    return {"state": "RECONSTRUCTION_REJECTED", "candidate": None,
        "reason": None, "scene_id": scene_id, "selected_stages": sorted(selected),
        "orientation": orientation, "template": template, "edges": [],
        "topological_order": [], "start_ms": {}, "end_ms": {},
        "deadline_violations": [], "window_violations": [],
        "unavailable_starts": [], "critical_predecessors": {},
        "blocking_traces": [], "additional_reversed_edges": [],
        "thermal_status": "NOT_EVALUATED", "true_energy_status": "NOT_EVALUATED",
        "rejection_scope": "SKELETON_AND_TEMPLATE_ONLY"}


def blocking_edges(packet):
    """Stable original-direction resource edges on reported late-task chains.

    Task-dependency edges and the selected primary resource pair are excluded.
    This helper supplies proposals only; reconstruct regenerates its own base
    packet before allowing an extra edge, rather than trusting caller metadata.
    """
    if (not isinstance(packet, dict) or not packet.get("deadline_violations")
            or packet.get("reason") != "SKELETON_DEADLINE_OR_WINDOW_EXCEEDED"
            or packet.get("unavailable_starts")):
        return []
    selected = set(packet.get("selected_stages", ()))
    reasons = {(e["from"], e["to"]): set(e["reasons"])
               for e in packet.get("edges", ())}
    late = {item["stage_id"] for item in packet["deadline_violations"]}
    found = set()
    for trace in packet.get("blocking_traces", ()):
        if trace.get("stage_id") not in late:
            continue
        for edge in trace.get("edges", ()):
            key = edge["from"], edge["to"]
            why = reasons.get(key, set())
            if (why & RESOURCE_REASONS and "task_dependency" not in why
                    and not (len(selected) == 2 and set(key) == selected)):
                found.add(key)
    return sorted(found)


def _prepare(instance, incumbent, scene_id, selected_stages, opp_overrides,
             orientation, template, budget):
    initial = original._validated(instance, incumbent, budget)
    if orientation not in ("incumbent", "reverse") or template not in ("earliest", "preserve"):
        raise GraphInputError("UNKNOWN_RECONSTRUCTION_POLICY")
    scenes = {scene["id"]: scene for scene in instance["scenarios"]}
    if scene_id not in scenes:
        raise GraphInputError("UNKNOWN_SCENE")
    scene = scenes[scene_id]
    old = {row["stage_id"]: row for row in initial["scenes"][scene_id]["rows"]}
    if (not isinstance(selected_stages, (list, tuple)) or len(selected_stages) not in (1, 2)
            or any(not isinstance(iid, str) for iid in selected_stages)
            or len(set(selected_stages)) != len(selected_stages)
            or not set(selected_stages) <= set(old)):
        raise GraphInputError("INVALID_SELECTED_STAGES")
    selected = set(selected_stages)
    if (not isinstance(opp_overrides, dict) or not set(opp_overrides) <= selected
            or any(not isinstance(opp, str) for opp in opp_overrides.values())):
        raise GraphInputError("INVALID_OPP_OVERRIDES")
    requests = {request["id"]: request for request in scene["requests"]}
    stages = {stage["id"]: stage for stage in scene["stage_instances"]}
    rows = {}
    for iid, prior in old.items():
        _check(budget)
        opp = opp_overrides.get(iid, prior["opp"])
        matches = [mode for mode in instance["stage_modes"][stages[iid]["shared_stage_id"]]
                   if mode["unit_id"] == prior["unit"] and mode["opp_id"] == opp]
        if len(matches) != 1:
            raise GraphInputError("ILLEGAL_OR_AMBIGUOUS_FIXED_UNIT_OPP")
        rows[iid] = {**prior, "opp": opp, "duration_ms": str(_q(matches[0]["duration_ms"]))}
    successors = {iid: set() for iid in rows}
    for left, right in scene["dependencies"]:
        _check(budget)
        successors[left].add(right)
    descendants, pending = set(selected), list(sorted(selected))
    while pending:
        _check(budget)
        current = pending.pop()
        for following in sorted(successors[current]):
            _check(budget)
            if following not in descendants:
                descendants.add(following)
                pending.append(following)
    return {"instance": instance, "incumbent": incumbent, "scene_id": scene_id,
        "scene": scene, "old": old, "rows": rows, "requests": requests,
        "stages": stages, "selected": selected, "descendants": descendants,
        "orientation": orientation, "template": template,
        "declared": original.explicit_start_sets(instance, budget)}


def _edges(context, extra, budget):
    rows, old, selected = context["rows"], context["old"], context["selected"]
    reasons = {}
    def add(left, right, reason):
        _check(budget)
        reasons.setdefault((left, right), set()).add(reason)
    for left, right in context["scene"]["dependencies"]:
        add(left, right, "task_dependency")
    for left_id, right_id in combinations(sorted(rows), 2):
        _check(budget)
        left, right = rows[left_id], rows[right_id]
        if left["unit"] == right["unit"]:
            reason = "same_unit"
        elif left["domain_id"] == right["domain_id"] and left["opp"] != right["opp"]:
            reason = "shared_domain_different_opp"
        else:
            continue
        ordered = sorted((left_id, right_id), key=lambda iid: original._time_key(old[iid]))
        if selected == {left_id, right_id} and context["orientation"] == "reverse":
            ordered.reverse()
        if extra is not None and tuple(ordered) == extra:
            ordered.reverse()
        add(ordered[0], ordered[1], reason)
    return reasons


def _trace(packet, violation, chosen, stop_reasons, reasons, budget):
    iid = violation["stage_id"]
    reverse_chain, reverse_edges = [iid], []
    while chosen.get(iid) is not None:
        _check(budget)
        pred = chosen[iid]
        reverse_edges.append({"from": pred, "to": iid,
                              "reasons": sorted(reasons[(pred, iid)])})
        reverse_chain.append(pred)
        iid = pred
    return {"stage_id": violation["stage_id"], "request_id": violation["request_id"],
        "chain": list(reversed(reverse_chain)), "edges": list(reversed(reverse_edges)),
        "stop_reason": stop_reasons.get(iid, "NO_PREDECESSOR"), "stop_stage_id": iid}


def _propagate(context, extra, budget):
    instance, rows, old = context["instance"], context["rows"], context["old"]
    packet = _packet(context["scene_id"], context["selected"], context["orientation"], context["template"])
    packet["additional_reversed_edges"] = [] if extra is None else [list(extra)]
    reasons = _edges(context, extra, budget)
    packet["edges"] = [{"from": a, "to": b, "reasons": sorted(why)}
                       for (a, b), why in sorted(reasons.items())]
    predecessors = {iid: set() for iid in rows}
    successors = {iid: set() for iid in rows}
    for left, right in reasons:
        _check(budget)
        predecessors[right].add(left); successors[left].add(right)
    counts = {iid: len(pred) for iid, pred in predecessors.items()}
    ready = [iid for iid, count in counts.items() if count == 0]
    starts, ends, order, chosen, stop_reasons = {}, {}, [], {}, {}
    grid, window = _q(instance["start_grid_ms"]), _q(instance["window_ms"])
    while ready:
        _check(budget)
        ready.sort(key=lambda iid: original._time_key(old[iid]))
        iid = ready.pop(0); order.append(iid)
        request = context["requests"][context["stages"][iid]["request_id"]]
        base_lower = max(Fraction(0), _q(request["release_ms"]))
        if context["template"] == "preserve" and iid not in context["descendants"]:
            base_lower = max(base_lower, _q(old[iid]["start_ms"]))
        unavailable = sorted(predecessors[iid] - set(ends))
        if unavailable:
            packet["unavailable_starts"].append({"stage_id": iid,
                "reason": "PREDECESSOR_HAS_NO_LEGAL_START", "predecessors": unavailable})
        else:
            maximum = max((ends[p] for p in predecessors[iid]), default=Fraction(0))
            lower = max(base_lower, maximum)
            # A release/floor tied with a predecessor is not attributed to that edge.
            if predecessors[iid] and maximum > base_lower:
                chosen[iid] = min(p for p in predecessors[iid] if ends[p] == maximum)
            else:
                chosen[iid] = None
                stop_reasons[iid] = "RELEASE_OR_FLOOR" if predecessors[iid] else "NO_PREDECESSOR"
            declared = context["declared"]
            if declared is None:
                start = -((-lower) // grid) * grid
            else:
                choices = declared[context["scene_id"]][iid]
                index = bisect_left(choices, lower)
                start = choices[index] if index < len(choices) else None
            if start is None:
                packet["unavailable_starts"].append({"stage_id": iid,
                    "reason": "NO_LEGAL_START_IN_SKELETON", "lower_ms": str(lower)})
            else:
                end = start + _q(rows[iid]["duration_ms"])
                starts[iid], ends[iid] = start, end
                if end > _q(request["deadline_ms"]):
                    packet["deadline_violations"].append({"stage_id": iid,
                        "request_id": request["id"], "deadline_ms": str(_q(request["deadline_ms"])),
                        "end_ms": str(end), "lateness_ms": str(end-_q(request["deadline_ms"]))})
                if end > window:
                    packet["window_violations"].append({"stage_id": iid,
                        "end_ms": str(end), "window_ms": str(window)})
        for following in sorted(successors[iid]):
            _check(budget)
            counts[following] -= 1
            if counts[following] == 0:
                ready.append(following)
    packet.update(topological_order=order, start_ms={k:str(v) for k,v in starts.items()},
                  end_ms={k:str(v) for k,v in ends.items()}, critical_predecessors=chosen,
                  scene_end_ms=str(max(ends.values(), default=Fraction(0))))
    packet["deadline_violations"].sort(key=lambda v: v["stage_id"])
    for violation in packet["deadline_violations"]:
        _check(budget)
        packet["blocking_traces"].append(_trace(packet, violation, chosen, stop_reasons, reasons, budget))
    if len(order) != len(rows):
        packet["reason"] = "SKELETON_DIRECTED_CYCLE"
    elif packet["unavailable_starts"]:
        packet["reason"] = "NO_LEGAL_START_IN_SKELETON"
    elif packet["deadline_violations"] or packet["window_violations"]:
        packet["reason"] = "SKELETON_DEADLINE_OR_WINDOW_EXCEEDED"
    else:
        candidate = deepcopy(context["incumbent"])
        for row in candidate["scenes"][context["scene_id"]]:
            _check(budget)
            iid = row["stage_id"]
            row["opp"], row["start_ms"] = rows[iid]["opp"], str(starts[iid])
        _check(budget)
        validation = original.validate_schedule(instance, candidate)
        _check(budget)
        if validation.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
            packet["reason"] = "RECONSTRUCTED_VALIDATION_REJECTED:" + validation.get("reason", "UNKNOWN")
        else:
            energy, components, energy_scenes = original._nonthermal_energy(instance, validation, budget)
            packet.update(state="COMPLETE_LEGAL_CANDIDATE", candidate=candidate,
                nonthermal_energy_J=energy, nonthermal_components_J=components,
                nonthermal_by_scene=energy_scenes)
    _check(budget)
    return packet


def reconstruct(instance, incumbent, scene_id, selected_stages, opp_overrides, *,
                orientation="incumbent", template="earliest", extra_resource_edge=None, budget=None):
    """Change selected OPPs/primary order and at most one proven blocking edge.

    An extra edge must be an original-direction pair on this exact no-extra
    skeleton's deterministic late-task trace.  Never repair recursively or use
    another candidate's diagnostics.  All methods/CPU labels remain fixed.
    """
    packet = _packet(scene_id)
    try:
        context = _prepare(instance, incumbent, scene_id, selected_stages, opp_overrides,
                           orientation, template, budget)
        packet = _propagate(context, None, budget)
        if extra_resource_edge is None:
            return packet
        if (not isinstance(extra_resource_edge, (tuple, list)) or len(extra_resource_edge) != 2
                or any(not isinstance(iid, str) for iid in extra_resource_edge)
                or extra_resource_edge[0] == extra_resource_edge[1]):
            raise GraphInputError("INVALID_EXTRA_RESOURCE_EDGE")
        extra = tuple(extra_resource_edge)
        _check(budget)
        if extra not in blocking_edges(packet):
            raise GraphInputError("EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")
        base = packet
        packet = _propagate(context, extra, budget)
        packet.update(base_deadline_violations=deepcopy(base["deadline_violations"]),
                      base_blocking_traces=deepcopy(base["blocking_traces"]),
                      base_blocking_edges=[list(e) for e in blocking_edges(base)])
        _check(budget)
        return packet
    except GraphInputError as error:
        _check(budget)
        packet.update(state="RECONSTRUCTION_REJECTED", candidate=None, reason=str(error))
        return packet
