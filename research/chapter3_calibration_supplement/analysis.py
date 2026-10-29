"""Pure time-diagnostic summaries; no files, scheduling, solving or integration.

Missed reference deadlines are observations, never infeasibility certificates.
All four beta values and all H/M/L columns are retained. This module does not
select a beta, a condition, or a favourable subset of roots.
"""

from collections import Counter
from copy import deepcopy
from fractions import Fraction

from research.chapter3_deadline_reference.contract import content_hash, exact


BETAS = ("1", "13/10", "8/5", "2")
OPPS = ("H", "M", "L")
SUMMARY_STATE = "SUPPLEMENT_CONDITION_SUMMARY_COMPLETE"


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _fraction(numerator, denominator):
    return str(Fraction(numerator, denominator)) if denominator else None


def _metrics(evidence, beta, opp):
    """Recompute exact deadline arithmetic from completed checked tables."""
    _require(evidence.get("state") == "TIME_CALIBRATION_COMPLETE", "INCOMPLETE_TIME_EVIDENCE")
    _require(evidence.get("beta_selected") is None, "BETA_MUST_REMAIN_UNSELECTED")
    check = evidence["reference"]["checks"][opp]
    _require(check["state"] == "TIME_STRUCTURAL_VALID", "TIME_CHECK_NOT_VALID")
    receipt = evidence["deadlines"][beta]
    _require(exact(receipt["beta"]) == exact(beta), "DEADLINE_BETA_MISMATCH")
    completed, deadlines = check["completions_ms"], receipt["requests"]
    _require(bool(deadlines) and set(completed) == set(deadlines), "SCENE_COMPLETION_COVERAGE")
    declared = {s["id"]: {r["id"]: exact(r["release_ms"]) for r in s["requests"]}
                for s in evidence["workload"]["time_contract"]["scenarios"]}
    _require(set(declared) == set(deadlines), "SCENE_DEADLINE_COVERAGE")
    scenes, all_rows = {}, []
    for sid, requests in sorted(deadlines.items()):
        _require(bool(requests) and set(requests) == set(completed[sid]) == set(declared[sid]),
                 "REQUEST_COMPLETION_COVERAGE")
        rows = {}
        for rid, row in sorted(requests.items()):
            release, due, relative = (exact(row[k]) for k in
                                      ("release_ms", "deadline_ms", "relative_deadline_ms"))
            finish = exact(completed[sid][rid])
            _require(release == declared[sid][rid] and relative > 0 and due == release + relative,
                     "INVALID_DEADLINE_ARITHMETIC")
            _require(finish > release, "NONPOSITIVE_REFERENCE_RESPONSE")
            slack = due - finish
            rows[rid] = {"release_ms": str(release), "finish_ms": str(finish),
                         "response_ms": str(finish - release), "deadline_ms": str(due),
                         "relative_deadline_ms": str(relative), "slack_ms": str(slack),
                         "eta": str(slack / relative), "on_time": slack >= 0}
            all_rows.append(rows[rid])
        count = sum(row["on_time"] for row in rows.values())
        scenes[sid] = {"requests": rows, "all_on_time": count == len(rows),
                       "requests_on_time": count, "request_count": len(rows),
                       "request_on_time_rate": _fraction(count, len(rows)),
                       "minimum_eta": str(min(exact(r["eta"]) for r in rows.values()))}
    request_pass = sum(row["on_time"] for row in all_rows)
    scene_pass = sum(row["all_on_time"] for row in scenes.values())
    minimum_eta = min(exact(row["eta"]) for row in all_rows)
    return {"family_all_on_time": scene_pass == len(scenes), "scenes": scenes,
            "scene_count": len(scenes), "scenes_on_time": scene_pass,
            "scene_on_time_rate": _fraction(scene_pass, len(scenes)),
            "request_count": len(all_rows), "requests_on_time": request_pass,
            "request_on_time_rate": _fraction(request_pass, len(all_rows)),
            "minimum_eta": str(minimum_eta),
            "L_minimum_eta_ge_0_1_descriptive": (minimum_eta >= Fraction(1, 10)) if opp == "L" else None,
            "maximum_lateness_ms": str(max(Fraction(0), max(-exact(r["slack_ms"]) for r in all_rows)))}


def _direction(delta):
    return "improved" if delta > 0 else "worsened" if delta < 0 else "unchanged"


def _pair(current, reference):
    _require(set(current["scenes"]) == set(reference["scenes"]), "PAIR_SCENE_COVERAGE")
    scene_counts = Counter(dict.fromkeys(("improved", "unchanged", "worsened"), 0))
    request_counts, slack_counts = scene_counts.copy(), scene_counts.copy()
    pairs = {}
    for sid, scene in current["scenes"].items():
        old = reference["scenes"][sid]
        _require(set(scene["requests"]) == set(old["requests"]), "PAIR_REQUEST_COVERAGE")
        scene_direction = _direction(int(scene["all_on_time"]) - int(old["all_on_time"]))
        scene_counts[scene_direction] += 1
        requests = {}
        for rid, row in scene["requests"].items():
            before = old["requests"][rid]
            _require(row["relative_deadline_ms"] == before["relative_deadline_ms"],
                     "PAIR_RELATIVE_DEADLINES_CHANGED")
            slack_change = exact(row["slack_ms"]) - exact(before["slack_ms"])
            status = _direction(int(row["on_time"]) - int(before["on_time"]))
            request_counts[status] += 1
            slack_counts[_direction(slack_change)] += 1
            requests[rid] = {"on_time_change": status, "slack_change_ms": str(slack_change),
                             "response_change_ms": str(exact(row["response_ms"]) - exact(before["response_ms"])),
                             "eta_change": str(exact(row["eta"]) - exact(before["eta"]))}
        pairs[sid] = {"all_on_time_change": scene_direction, "requests": requests}
    return {"family_all_on_time_change": _direction(int(current["family_all_on_time"]) -
                                                     int(reference["family_all_on_time"])),
            "scene_status_changes": dict(scene_counts), "request_status_changes": dict(request_counts),
            "request_slack_changes": dict(slack_counts), "scenes": pairs,
            "comparison_basis": "same_request_relative_response_and_slack_not_absolute_finish"}


def _structure(evidence):
    result = {}
    for app, spec in sorted(evidence["workload"]["applications"].items()):
        nodes, edges = spec["nodes"], spec["edges"]
        successors = {n: set() for n in nodes}
        predecessors = {n: set() for n in nodes}
        _require(len(nodes) == len(successors) and bool(nodes), "STRUCTURE_NODE_IDENTITIES")
        for a, b in edges:
            _require(a in successors and b in successors and a != b, "STRUCTURE_EDGE_INVALID")
            successors[a].add(b)
            predecessors[b].add(a)
        pending, distance, descendants = set(nodes), {}, {}
        while pending:
            ready = sorted(n for n in pending if predecessors[n].issubset(distance))
            _require(bool(ready), "STRUCTURE_CYCLE")
            for n in ready:
                distance[n] = 1 + max((distance[p] for p in predecessors[n]), default=0)
                pending.remove(n)
        for n in sorted(nodes, key=lambda n: distance[n], reverse=True):
            descendants[n] = set(successors[n])
            for nxt in successors[n]:
                descendants[n].update(descendants[nxt])
        incomparable = sum(b not in descendants[a] and a not in descendants[b]
                           for i, a in enumerate(nodes) for b in nodes[i + 1:])
        result[app] = {"nodes": len(nodes), "edges": len(edges),
                       "longest_path_nodes": max(distance.values()), "incomparable_pairs": incomparable}
    return {"topology_id": evidence["workload"]["time_contract"]["topology_id"],
            "applications": result, "meaning": "dependency_only_not_scheduling_latency_or_hardware_parallelism"}


def summarize_condition(call, evidence, comparisons):
    """Summarize one complete new condition with archive-derived comparisons.

    comparisons must include call.parent_id and each call.comparison_ids.
    Archive hashes and full scientific legality are enforced by the execution
    boundary. Here coverage and exact arithmetic are independently recomputed.
    """
    _require(call["axis"] in ("S4", "S7"), "UNSUPPORTED_SUPPLEMENT_AXIS")
    identifiers = [call["parent_id"]] + list(call["comparison_ids"])
    _require(all(name in comparisons for name in identifiers), "MISSING_ARCHIVED_COMPARISON")
    if call["axis"] == "S4":
        _require(len(call["comparison_ids"]) == 2, "S4_COMPARISON_COUNT")
        child_role = "branch_multi"
        roles = {child_role: evidence, "branch_join": comparisons[call["parent_id"]],
                 "serial": comparisons[call["comparison_ids"][0]],
                 "layered": comparisons[call["comparison_ids"][1]]}
        paired_roles = ("branch_join", "serial", "layered")
    else:
        _require(len(call["comparison_ids"]) == 1, "S7_COMPARISON_COUNT")
        child_role = "staggered"
        roles = {child_role: evidence, "single": comparisons[call["parent_id"]],
                 "synchronous": comparisons[call["comparison_ids"][0]]}
        paired_roles = ("synchronous",)
    origin = evidence["reference"]["mapping_origin_hash"]
    for role, value in roles.items():
        provenance = value["workload"]["provenance"]
        _require(provenance["root_id"] == call["root_id"] and provenance["scale"] == call["scale"],
                 "SUMMARY_ROOT_OR_SCALE_MISMATCH")
        _require(value["reference"]["mapping_origin_hash"] == origin, "SUMMARY_MAPPING_ORIGIN_MISMATCH")
        _require(set(value["reference"]["checks"]) == set(OPPS), "SUMMARY_OPP_COVERAGE")
        _require(set(value["deadlines"]) == set(BETAS), "SUMMARY_BETA_COVERAGE")
        _require(value.get("thermal_status") == value.get("energy_status") == "NOT_EVALUATED",
                 "SUMMARY_SCOPE_MISMATCH")
    by_beta = {}
    for beta in BETAS:
        baseline_origin = roles[next(iter(roles))]["deadlines"][beta]["deadline_origin_hash"]
        _require(all(value["deadlines"][beta]["deadline_origin_hash"] == baseline_origin for value in roles.values()),
                 "SUMMARY_DEADLINE_ORIGIN_MISMATCH")
        by_beta[beta] = {}
        for opp in OPPS:
            metrics = {role: _metrics(value, beta, opp) for role, value in roles.items()}
            by_beta[beta][opp] = {"roles": metrics,
                                  "paired": {role: _pair(metrics[child_role], metrics[role]) for role in paired_roles}}
    result = {"schema_version": "supplement-condition-summary-v1", "state": SUMMARY_STATE,
              "condition": deepcopy(call), "child_role": child_role,
              "role_bindings": {role: {"contract_hash": value["workload"]["contract_hash"],
                                        "mapping_origin_hash": value["reference"]["mapping_origin_hash"],
                                        "timetable_hashes": {opp: value["reference"]["checks"][opp]["timetable_hash"]
                                                             for opp in OPPS},
                                        "deadline_receipt_hashes": {b: value["deadlines"][b]["receipt_hash"] for b in BETAS}}
                                for role, value in roles.items()},
              "structure_by_role": {role: _structure(value) for role, value in roles.items()},
              "by_beta": by_beta, "beta_selected": None,
              "deadline_miss_meaning": "reference_not_on_time_not_problem_infeasibility",
              "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    result["summary_hash"] = content_hash(result)
    return result


def _aggregate_group(summaries):
    result = {"complete_conditions": len(summaries),
              "distinct_existing_roots": len({s["condition"]["root_id"] for s in summaries}), "by_beta": {}}
    for beta in BETAS:
        result["by_beta"][beta] = {}
        for opp in OPPS:
            roles, paired = {}, {}
            for summary in summaries:
                row = summary["by_beta"][beta][opp]
                for role, value in row["roles"].items():
                    total = roles.setdefault(role, {"conditions": 0, "families_on_time": 0,
                                                   "scenes": 0, "scenes_on_time": 0,
                                                   "requests": 0, "requests_on_time": 0, "minimum_etas": []})
                    for target, field in (("families_on_time", "family_all_on_time"),
                                          ("scenes", "scene_count"), ("scenes_on_time", "scenes_on_time"),
                                          ("requests", "request_count"), ("requests_on_time", "requests_on_time")):
                        total[target] += value[field]
                    total["conditions"] += 1
                    total["minimum_etas"].append(value["minimum_eta"])
                for role, value in row["paired"].items():
                    total = paired.setdefault(role, {level: dict.fromkeys(("improved", "unchanged", "worsened"), 0)
                                                     for level in ("families", "scenes", "requests", "request_slacks")})
                    total["families"][value["family_all_on_time_change"]] += 1
                    for target, field in (("scenes", "scene_status_changes"), ("requests", "request_status_changes"),
                                          ("request_slacks", "request_slack_changes")):
                        for key, count in value[field].items():
                            total[target][key] += count
            for value in roles.values():
                value["family_on_time_rate"] = _fraction(value["families_on_time"], value["conditions"])
                value["scene_on_time_rate"] = _fraction(value["scenes_on_time"], value["scenes"])
                value["request_on_time_rate"] = _fraction(value["requests_on_time"], value["requests"])
                etas = list(map(exact, value.pop("minimum_etas")))
                value["condition_minimum_eta_range"] = [str(min(etas)), str(max(etas))]
                value["conditions_L_minimum_eta_ge_0_1_descriptive"] = (
                    sum(v >= Fraction(1, 10) for v in etas) if opp == "L" else None)
            result["by_beta"][beta][opp] = {"roles": roles, "paired": paired}
    return result


def aggregate_summaries(planned_calls, accepted_rows):
    """Keep unavailable data outside scientific denominators, with coverage.

    Each row has condition_id (or condition.condition_id), state and, only for a
    complete result, summary. Input errors/duplicates raise; missing or incomplete
    evidence is explicitly listed and does not become an overdue reference.
    """
    planned = {c["condition_id"]: c for c in planned_calls}
    _require(len(planned) == len(planned_calls), "DUPLICATE_PLANNED_CONDITION")
    rows = {}
    for row in accepted_rows:
        key = row.get("condition_id", row.get("condition", {}).get("condition_id"))
        _require(key in planned and key not in rows, "UNKNOWN_OR_DUPLICATE_RESULT")
        rows[key] = row
    statuses, usable = [], []
    for key, call in planned.items():
        row = rows.get(key)
        state = "NOT_RUN" if row is None else row.get("state", "INCOMPLETE_RECEIPT")
        summary = row.get("summary") if row else None
        if state == "COMPLETE":
            if (not isinstance(summary, dict) or summary.get("state") != SUMMARY_STATE or
                    summary.get("condition") != call or summary.get("beta_selected") is not None or
                    summary.get("summary_hash") != content_hash({k: v for k, v in summary.items() if k != "summary_hash"})):
                state = "INCOMPLETE_OR_INVALID_SUMMARY"
            else:
                usable.append(summary)
        statuses.append({"condition_id": key, "root_id": call["root_id"], "axis": call["axis"],
                         "scale": call["scale"], "state": state})
    by_axis = {}
    for axis in ("S4", "S7"):
        subset = [s for s in usable if s["condition"]["axis"] == axis]
        by_axis[axis] = {"all_scales": _aggregate_group(subset),
                         "by_scale": {str(scale): _aggregate_group([s for s in subset if s["condition"]["scale"] == scale])
                                      for scale in sorted({c["scale"] for c in planned_calls if c["axis"] == axis})}}
    return {"schema_version": "supplement-batch-summary-v1",
            "state": "COMPLETE" if len(usable) == len(planned) else "PARTIAL",
            "planned_conditions": len(planned), "usable_conditions": len(usable),
            "planned_existing_roots": len({c["root_id"] for c in planned_calls}),
            "usable_existing_roots": len({s["condition"]["root_id"] for s in usable}),
            "condition_status_counts": dict(Counter(r["state"] for r in statuses)),
            "condition_statuses": statuses, "by_axis": by_axis, "beta_selected": None,
            "denominator_policy": "complete_cases_only_with_explicit_missing_coverage_not_independent_derived_samples",
            "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
