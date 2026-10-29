"""Exact, archive-derived S4/S7 adjustments; no reference construction here.

The old generator and its synchronous-copy validator remain unchanged.  These
functions accept explicit parent data and preserve its profiles and deadlines.
Archive authentication and execution authorization belong to the caller.
"""

from copy import deepcopy
from fractions import Fraction

from research.chapter3_deadline_reference.contract import (
    ContractError, normalize, content_hash, exact)
from research.chapter3_deadline_reference.checker import check_timetable
from research.chapter3_deadline_reference.deadlines import _verify_receipt
from research.chapter3_workload_calibration.generator import validate_bundle, stamp
from research.chapter3_workload_calibration.topology import validate_graph


BRANCH_RULE = "branch_multi_v1"
STAGGER_RULE = "staggered_half_base_H_v1"


def _require(condition, code, **details):
    if not condition:
        raise ContractError(code, **details)


def branch_multi(nodes):
    """Declared 4n repeated diamonds, or the explicit two-node exception."""
    _require(isinstance(nodes, list) and len(nodes) >= 2 and
             all(isinstance(n, str) and n.strip() for n in nodes) and
             len(set(nodes)) == len(nodes), "BRANCH_NODE_IDENTITIES")
    count = len(nodes)
    _require(count == 2 or count % 4 == 0, "BRANCH_UNDECLARED_NODE_COUNT")
    edges = []
    if count == 2:
        edges = [[nodes[0], nodes[1]]]
    else:
        for at in range(0, count, 4):
            a, b, c, d = nodes[at:at + 4]
            edges.extend([[a, b], [a, c], [b, d], [c, d]])
            if at:
                edges.append([nodes[at - 1], a])
    edges.sort()
    graph = validate_graph(nodes, edges, [nodes[-1]], max_indegree=2,
                           max_outdegree=2, layers=None,
                           require_nonchain=count != 2, forbidden_edges=None)
    return {"edges": edges, "required_outputs": [nodes[-1]],
            "structure": {"node_count": count, "diamond_modules": count // 4,
                          "longest_path_nodes": 2 if count == 2 else 3 * (count // 4),
                          "partial_order_width": 1 if count == 2 else 2,
                          "small_graph_exception": "TWO_NODE_CHAIN" if count == 2 else None,
                          "graph_check": graph}}


def structure_metrics(nodes, edges, durations):
    """Independent exact path computation, not a resource-schedule bound proof."""
    _require(isinstance(durations, dict) and set(durations) == set(nodes), "PATH_WEIGHT_COVERAGE")
    lengths = {n: exact(durations[n]) for n in nodes}
    _require(all(d > 0 for d in lengths.values()), "NONPOSITIVE_PATH_WEIGHT")
    sinks = set(nodes) - {a for a, _ in edges}
    graph = validate_graph(nodes, edges, sorted(sinks), max_indegree=max(1, len(nodes)),
                           max_outdegree=max(1, len(nodes)), layers=None,
                           require_nonchain=False, forbidden_edges=None)
    predecessors = {n: [] for n in nodes}
    for a, b in edges:
        predecessors[b].append(a)
    time_end, count_end = {}, {}
    for n in graph["topological_order"]:
        time_end[n] = lengths[n] + max((time_end[p] for p in predecessors[n]), default=Fraction(0))
        count_end[n] = 1 + max((count_end[p] for p in predecessors[n]), default=0)
    return {"weighted_critical_path_ms": str(max(time_end.values())),
            "longest_path_nodes": max(count_end.values()),
            "incomparable_pairs": graph["incomparable_pairs"]}


def _base_bundle(base):
    validate_bundle(base)
    data = normalize(base["time_contract"])
    _require(data["derivation"]["axis"] in ("BASE", "S2") and
             data["topology_id"] == "branch_join" and base["transform"] is None,
             "ORIGINAL_BASE_REQUIRED")
    apps = base["applications"]
    _require(isinstance(apps, dict) and bool(apps), "APPLICATIONS_REQUIRED")
    nodes = []
    for app, spec in apps.items():
        _require(isinstance(app, str) and app and isinstance(spec, dict), "APPLICATION_IDENTITY")
        local = spec["nodes"]
        _require(all(n.startswith(app + ".") for n in local), "APPLICATION_NODE_IDENTITY")
        branch_multi(local)  # The approved size contract; does not generate a workload.
        nodes.extend(local)
        old_edges = ([[local[0], local[1]]] if len(local) == 2 else
                     [[local[0], local[1]], [local[0], local[2]],
                      [local[1], local[3]], [local[2], local[3]]] +
                     [[local[i], local[i + 1]] for i in range(3, len(local) - 1)])
        _require(sorted(spec["edges"]) == sorted(old_edges) and spec["required_outputs"] == [local[-1]],
                 "BASE_TOPOLOGY_METADATA_MISMATCH")
    _require(len(nodes) == len(set(nodes)) and set(nodes) == set(data["stage_profiles"]),
             "APPLICATION_PROFILE_COVERAGE")
    for scene in data["scenarios"]:
        expected_edges = []
        occurrences = {s["id"]: s for s in scene["stage_instances"]}
        for req in scene["requests"]:
            _require(req["id"].endswith(".r1"), "BASE_SINGLE_REQUEST_REQUIRED")
            app = req["id"][:-3]
            _require(app in apps, "UNKNOWN_REQUEST_APPLICATION")
            expected_ids = {n + ".r1" for n in apps[app]["nodes"]}
            _require(set(req["stage_instance_ids"]) == expected_ids, "BASE_APPLICATION_MEMBERSHIP")
            for n in apps[app]["nodes"]:
                _require(occurrences[n + ".r1"]["shared_stage_id"] == n,
                         "BASE_SHARED_IDENTITY")
            expected_edges.extend([[a + ".r1", b + ".r1"] for a, b in apps[app]["edges"]])
        _require(scene["dependencies"] == sorted(expected_edges), "BASE_APPLICATION_EDGES")
    return data


def validated_base_h(base_evidence):
    """Recheck the supplied original H table and its binding, never reconstruct it."""
    _require(isinstance(base_evidence, dict) and base_evidence.get("state") == "TIME_CALIBRATION_COMPLETE",
             "COMPLETE_BASE_EVIDENCE_REQUIRED")
    base = base_evidence["workload"]
    data = _base_bundle(base)
    reference = base_evidence["reference"]
    _require(reference.get("state") == "REFERENCES_COMPLETE" and
             reference.get("contract_hash") == base["contract_hash"], "BASE_REFERENCE_IDENTITY")
    record = reference["mapping_record"]
    _require(record.get("contract_hash") == base["contract_hash"] and
             reference.get("mapping_origin_hash") == content_hash(record), "BASE_MAPPING_ORIGIN")
    table = reference["timetables"]["H"]
    check = check_timetable(data, table, required_opp="H")
    _require(check["state"] == "TIME_STRUCTURAL_VALID", "BASE_H_INVALID", check=check)
    _require(reference["checks"]["H"] == check, "BASE_H_CHECK_DRIFT")
    _require(check["shared_deployment"] == record["mapping"], "BASE_H_MAPPING_DRIFT")
    deadlines = base_evidence["deadlines"]
    _require(isinstance(deadlines, dict) and bool(deadlines), "BASE_DEADLINES_REQUIRED")
    for key, receipt in deadlines.items():
        _verify_receipt(data, receipt)
        beta = exact(key)
        _require(beta >= 1 and exact(receipt["beta"]) == beta, "BASE_BETA_KEY")
        origin = {"contract_hash": base["contract_hash"], "h_completions_ms": check["completions_ms"],
                  "h_timetable_hash": check["timetable_hash"], "beta": str(beta),
                  "reference_topology_id": data["topology_id"]}
        _require(receipt["origin"] == origin and receipt["deadline_origin_hash"] == content_hash(origin) and
                 receipt["parent_receipt_hash"] is None and receipt["request_sources"] is None,
                 "BASE_DEADLINE_ORIGIN_DRIFT")
        for scene in data["scenarios"]:
            for req in scene["requests"]:
                release = exact(req["release_ms"])
                relative = beta * (exact(check["completions_ms"][scene["id"]][req["id"]]) - release)
                row = receipt["requests"][scene["id"]][req["id"]]
                _require(exact(row["relative_deadline_ms"]) == relative and
                         exact(row["deadline_ms"]) == release + relative, "BASE_DEADLINE_ARITHMETIC")
    return check


def _begin(base, axis, variant):
    _base_bundle(base)
    result = deepcopy(base)
    result["time_contract"]["variant_id"] = variant
    result["time_contract"]["derivation"] = {"axis": axis, "parent_contract_hash": base["contract_hash"]}
    return result


def derive_branch_multi(base_bundle):
    result = _begin(base_bundle, "S4", BRANCH_RULE)
    data = result["time_contract"]
    data["topology_id"] = BRANCH_RULE
    result["transform"] = {"axis": "S4", "parent_bundle_hash": base_bundle["bundle_hash"], "rule": BRANCH_RULE}
    for app, spec in result["applications"].items():
        new = branch_multi(spec["nodes"])
        spec.update(edges=new["edges"], required_outputs=new["required_outputs"],
                    trace={"rule": BRANCH_RULE, "parent_topology_hash": content_hash(base_bundle["applications"][app]),
                           "structure": new["structure"]})
    for scene in data["scenarios"]:
        scene["dependencies"] = []
        for req in scene["requests"]:
            app = req["id"][:-3]
            scene["dependencies"].extend([[a + ".r1", b + ".r1"]
                                           for a, b in result["applications"][app]["edges"]])
    return stamp(result)


def _stagger_metadata(base, h_check):
    shifts = {}
    for scene, rows in h_check["completions_ms"].items():
        finish = max(exact(v) for v in rows.values())
        _require(finish > 0, "NONPOSITIVE_BASE_MAKESPAN")
        shifts[scene] = str(5 * (-(-(finish / 10) // 1)))
    return {"axis": "S7", "parent_bundle_hash": base["bundle_hash"], "rule": STAGGER_RULE,
            "source_contract_hash": base["contract_hash"],
            "source_h_timetable_hash": h_check["timetable_hash"], "source_h_check_hash": content_hash(h_check),
            "scene_shifts_ms": shifts, "fraction": "1/2", "grid_ms": "5"}


def derive_staggered(base_evidence):
    check = validated_base_h(base_evidence)
    base = base_evidence["workload"]
    result = _begin(base, "S7", "s7_" + STAGGER_RULE)
    result["transform"] = _stagger_metadata(base, check)
    for scene in result["time_contract"]["scenarios"]:
        reqs, stages, edges = deepcopy((scene["requests"], scene["stage_instances"], scene["dependencies"]))
        shift = exact(result["transform"]["scene_shifts_ms"][scene["id"]])
        for req in reqs:
            req["id"] = req["id"][:-1] + "2"
            req["release_ms"] = str(exact(req["release_ms"]) + shift)
            req["stage_instance_ids"] = [iid[:-1] + "2" for iid in req["stage_instance_ids"]]
        for s in stages:
            s["id"], s["request_id"] = s["id"][:-1] + "2", s["request_id"][:-1] + "2"
        scene["requests"].extend(reqs)
        scene["stage_instances"].extend(stages)
        scene["dependencies"].extend([[a[:-1] + "2", b[:-1] + "2"] for a, b in edges])
    return stamp(result)


def validate_adjustment(base_evidence, child):
    """Strict field whitelist plus independent expected-edge/release relations."""
    check = validated_base_h(base_evidence)
    base = base_evidence["workload"]
    validate_bundle(child)
    parent, target = base["time_contract"], child["time_contract"]
    axis = target["derivation"]["axis"]
    _require(axis in ("S4", "S7"), "UNSUPPORTED_ADJUSTMENT")
    _require(set(base) == set(child), "BUNDLE_FIELDS_CHANGED")
    for field in set(base) - {"time_contract", "applications", "transform", "contract_hash", "bundle_hash"}:
        _require(child[field] == base[field], "BUNDLE_FIELD_DRIFT", field=field)
    _require(target["derivation"] == {"axis": axis, "parent_contract_hash": base["contract_hash"]},
             "ADJUSTMENT_PARENT_MISMATCH")
    for field in set(parent) - {"variant_id", "topology_id", "derivation", "scenarios"}:
        _require(target[field] == parent[field], "CONTRACT_FIELD_DRIFT", field=field)
    _require(set(child["applications"]) == set(base["applications"]), "APPLICATION_SET_CHANGED")
    expected_transform = ({"axis": "S4", "parent_bundle_hash": base["bundle_hash"], "rule": BRANCH_RULE}
                          if axis == "S4" else _stagger_metadata(base, check))
    _require(child["transform"] == expected_transform, "ADJUSTMENT_PROVENANCE_DRIFT")
    _require(target["variant_id"] == (BRANCH_RULE if axis == "S4" else "s7_" + STAGGER_RULE),
             "ADJUSTMENT_VARIANT")
    _require(target["topology_id"] == (BRANCH_RULE if axis == "S4" else parent["topology_id"]),
             "ADJUSTMENT_TOPOLOGY_ID")
    if axis == "S7":
        _require(child["applications"] == base["applications"], "S7_APPLICATION_CHANGED")
    else:
        for app, old in base["applications"].items():
            new = child["applications"][app]
            _require(set(new) == set(old), "APPLICATION_FIELDS_CHANGED")
            for field in set(old) - {"edges", "required_outputs", "trace"}:
                _require(new[field] == old[field], "APPLICATION_FIELD_DRIFT", field=field)
            shape = branch_multi(old["nodes"])
            _require(new["edges"] == shape["edges"] and new["required_outputs"] == shape["required_outputs"],
                     "MULTI_BRANCH_EDGES")
            _require(new["trace"] == {"rule": BRANCH_RULE, "parent_topology_hash": content_hash(old),
                                      "structure": shape["structure"]}, "MULTI_BRANCH_TRACE")
    originals = {s["id"]: s for s in parent["scenarios"]}
    _require(set(originals) == {s["id"] for s in target["scenarios"]}, "SCENARIO_SET_CHANGED")
    for scene in target["scenarios"]:
        old = originals[scene["id"]]
        _require(set(scene) == set(old) and scene["weight"] == old["weight"], "SCENE_FIELDS_OR_WEIGHT")
        if axis == "S4":
            _require(scene["requests"] == old["requests"] and scene["stage_instances"] == old["stage_instances"],
                     "S4_REQUEST_OR_STAGE_CHANGED")
            wanted = []
            for req in old["requests"]:
                wanted.extend([[a + ".r1", b + ".r1"] for a, b in
                               child["applications"][req["id"][:-3]]["edges"]])
            _require(scene["dependencies"] == sorted(wanted), "S4_OCCURRENCE_EDGES")
        else:
            shift = exact(expected_transform["scene_shifts_ms"][scene["id"]])
            reqs = {r["id"]: r for r in scene["requests"]}
            stages = {s["id"]: s for s in scene["stage_instances"]}
            _require(len(reqs) == 2 * len(old["requests"]) and len(stages) == 2 * len(old["stage_instances"]),
                     "S7_COPY_COUNTS")
            for req in old["requests"]:
                _require(reqs.get(req["id"]) == req, "S7_ORIGINAL_REQUEST_CHANGED")
                expected = deepcopy(req)
                expected["id"] = req["id"][:-1] + "2"
                expected["release_ms"] = str(exact(req["release_ms"]) + shift)
                expected["stage_instance_ids"] = [s[:-1] + "2" for s in req["stage_instance_ids"]]
                _require(reqs.get(expected["id"]) == expected, "S7_SHIFT_OR_MEMBERSHIP")
            for s in old["stage_instances"]:
                _require(stages.get(s["id"]) == s, "S7_ORIGINAL_INSTANCE_CHANGED")
                expected = {**s, "id": s["id"][:-1] + "2", "request_id": s["request_id"][:-1] + "2"}
                _require(stages.get(expected["id"]) == expected, "S7_COPIED_INSTANCE_CHANGED")
            wanted = old["dependencies"] + [[a[:-1] + "2", b[:-1] + "2"] for a, b in old["dependencies"]]
            _require(scene["dependencies"] == sorted(wanted), "S7_COPIED_DEPENDENCIES")
    return True
