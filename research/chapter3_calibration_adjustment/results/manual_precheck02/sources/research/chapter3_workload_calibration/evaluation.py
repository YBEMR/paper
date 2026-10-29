"""Time-only reference evaluation with immutable baseline deadline provenance."""

from fractions import Fraction

from research.chapter3_deadline_reference.contract import exact, contract_hash, content_hash
from research.chapter3_deadline_reference.scheduler import (choose_mapping, build_timetable,
                                                           project_references)
from research.chapter3_deadline_reference.checker import check_timetable
from research.chapter3_deadline_reference.deadlines import make_deadlines, inherit_deadlines, compare_deadlines
from research.chapter3_deadline_reference.bounds import lower_bounds
from .generator import inherited_mapping, request_sources, subset, statistics, require


def _deadline_metrics(check, receipt):
    rows = []
    for scene, reqs in receipt["requests"].items():
        for rid, r in reqs.items():
            due, release = exact(r["deadline_ms"]), exact(r["release_ms"])
            finish = exact(check["completions_ms"][scene][rid])
            rows.append({"scene": scene, "request": rid, "finish_ms": str(finish),
                         "deadline_ms": str(due), "slack_ms": str(due - finish),
                         "eta": str((due - finish) / (due - release)), "on_time": finish <= due})
    by_scene = {s: all(r["on_time"] for r in rows if r["scene"] == s) for s in receipt["requests"]}
    return {"requests": rows, "all_on_time": all(by_scene.values()), "scenes_on_time": by_scene,
            "request_on_time_count": sum(r["on_time"] for r in rows), "request_count": len(rows),
            "scene_on_time_count": sum(by_scene.values()), "scene_count": len(by_scene),
            "minimum_eta": str(min(exact(r["eta"]) for r in rows))}


def evaluate_condition(bundle, config, *, parent=None, progress):
    """Exactly three constructors. A parent is a previous complete evidence object.

    progress is an external deadline/checkpoint callback, not a scientific rule.
    No old optimizer or thermal module is imported or called.
    """
    data = bundle["time_contract"]
    axis = data["derivation"]["axis"]
    is_base = axis in ("BASE", "S2")
    counters = {"mapping_constructions": 0, "timetable_constructions": 0,
                "S1_projections": 0, "formal_method_calls": 0, "thermal_integrations": 0}
    progress("INPUT_VALIDATED", counters)
    if is_base:
        counters["mapping_constructions"] += 1
        progress("MAPPING_STARTED", counters)
        record = choose_mapping(data)
        mapping = record["mapping"]
        origin = content_hash(record)
    else:
        require(parent is not None, "PARENT_EVIDENCE_REQUIRED")
        require(parent["workload"]["contract_hash"] == data["derivation"]["parent_contract_hash"], "PARENT_EVIDENCE_HASH")
        mapping = inherited_mapping(parent["reference"]["mapping_record"]["mapping"], bundle)
        record = {"contract_hash": contract_hash(data), "mapping": mapping,
                  "inherited_from": parent["reference"]["mapping_origin_hash"]}
        origin = parent["reference"]["mapping_origin_hash"]
    tables, checks = {}, {}
    for opp in ("H", "M", "L"):
        counters["timetable_constructions"] += 1
        progress(opp + "_CONSTRUCTION_STARTED", counters)
        tables[opp] = build_timetable(data, mapping, opp)
        checks[opp] = check_timetable(data, tables[opp], required_opp=opp)
        require(checks[opp]["state"] == "TIME_STRUCTURAL_VALID", "INDEPENDENT_TIME_CHECK_FAILED", check=checks[opp])
        progress(opp + "_TIME_CHECKED", counters)
    reference = {"state": "REFERENCES_COMPLETE", "contract_hash": contract_hash(data),
                 "mapping_record": record, "mapping_origin_hash": origin,
                 "timetables": tables, "checks": checks,
                 "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    deadlines, metrics = {}, {}
    for beta in config["betas"]:
        key = str(exact(beta))
        if is_base:
            receipt = make_deadlines(data, tables["H"], beta=beta, reference_topology_id="branch_join")
        else:
            receipt = inherit_deadlines(parent["workload"]["time_contract"], parent["deadlines"][key], data,
                                        request_sources=request_sources(parent["workload"], bundle))
        deadlines[key] = receipt
        metrics[key] = {opp: _deadline_metrics(checks[opp], receipt) for opp in ("H", "M", "L")}
    progress("DEADLINES_AND_DIAGNOSTICS_COMPLETE", counters)
    thresholds = {}
    # Derived thresholds use the ORIGINAL H response (D(beta=1)-a), never the derived H.
    anchor = deadlines[str(exact(config["betas"][0]))]
    anchor_beta = exact(anchor["beta"])
    for opp in ("H", "M", "L"):
        ratios = []
        for sid, reqs in anchor["requests"].items():
            for rid, r in reqs.items():
                original_response = exact(r["relative_deadline_ms"]) / anchor_beta
                ratios.append({"scene": sid, "request": rid,
                               "beta_required": str((exact(checks[opp]["completions_ms"][sid][rid]) -
                                                     exact(r["release_ms"])) / original_response)})
        thresholds[opp] = {"whole_family_beta_required": str(max(exact(r["beta_required"]) for r in ratios)),
                           "per_request": ratios}
    projections = {}
    if is_base:
        for n in (1, 2, 4, 6, 8):
            sub = subset(bundle, n)
            projected = project_references(data, reference, sub["time_contract"])
            projection_deadlines, projection_metrics = {}, {}
            for key, receipt in deadlines.items():
                inherited = inherit_deadlines(data, receipt, sub["time_contract"], request_sources=request_sources(bundle, sub))
                projection_deadlines[key] = inherited
                projection_metrics[key] = {opp: _deadline_metrics(projected["checks"][opp], inherited)
                                           for opp in ("H", "M", "L")}
            projections[str(n)] = {"contract_hash": sub["contract_hash"], "statistics": statistics(sub),
                                   "mapping_origin_hash": projected["mapping_origin_hash"],
                                   "timetable_hashes": {o: projected["checks"][o]["timetable_hash"] for o in checks},
                                   "deadlines": projection_deadlines, "metrics": projection_metrics,
                                   "formal_mapping_constraint": None, "formal_initial_solution": None}
            counters["S1_projections"] += 1
            progress(f"S1_{n}_PROJECTED", counters)
    bounds = lower_bounds(data, mapping)
    progress("CONDITION_COMPLETE", counters)
    return {"state": "TIME_CALIBRATION_COMPLETE", "workload": bundle, "reference": reference,
            "deadlines": deadlines, "metrics": metrics, "thresholds": thresholds,
            "optimistic_time_bounds": bounds, "S1_projections": projections,
            "statistics": statistics(bundle), "counters": counters,
            "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
