"""Hand-written test inputs, never calibration roots or random workloads."""

from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from research.chapter3_deadline_reference.contract import content_hash, exact
from research.chapter3_deadline_reference.fixtures import empty_family, profile, request, occurrence, scene
from research.chapter3_deadline_reference.scheduler import build_references
from research.chapter3_deadline_reference.deadlines import make_deadlines
from research.chapter3_workload_calibration.profiles import load_catalog
from research.chapter3_workload_calibration.generator import stamp


def _old_edges(nodes):
    if len(nodes) == 2:
        return [[nodes[0], nodes[1]]]
    if len(nodes) < 4 or len(nodes) % 4:
        raise ValueError("Manual fixture requires 4n or two nodes")
    return [[nodes[0], nodes[1]], [nodes[0], nodes[2]], [nodes[1], nodes[3]], [nodes[2], nodes[3]]] + [
        [nodes[i], nodes[i + 1]] for i in range(3, len(nodes) - 1)]


def manual_bundle(*, large_nodes=8, small_nodes=4, offsets=("0", "15")):
    if not offsets or len(set(map(str, offsets))) != len(offsets):
        raise ValueError("Explicit distinct manual offsets required")
    catalog = load_catalog(Path(__file__).resolve().parents[1] / "chapter3_experiments/config_v01.json")
    data = empty_family("manual-adjustment", "branch_join")
    data["variant_id"] = "manual-base"
    data["context"] = {"fixture_only": True, "namespace": "manual-adjustment", "seed": None,
                       "initial_temperature_C": ["50"] * 4, "evaluation_window_status": "UNFROZEN"}
    data["platform"] = deepcopy(catalog["time_platform"])
    data["execution_rules"] = deepcopy(catalog["execution_rules"])
    apps, physical, traces = {}, {}, {}
    for app, count, role in (("L1", large_nodes, "large"), ("S1", small_nodes, "small")):
        nodes = [f"{app}.s{i:04d}" for i in range(1, count + 1)]
        edges = _old_edges(nodes)
        apps[app] = {"role": role, "nodes": nodes, "edges": sorted(edges),
                     "required_outputs": [nodes[-1]], "trace": {"hand_written": True}}
        for i, node in enumerate(nodes):
            d = str(5 + 2 * (i % 3))
            p = profile({"CPU1": d, "CPU2": d}, alpha="1/2", work=d)
            data["stage_profiles"][node] = p
            physical[node] = {"work_units": d, "units": {
                unit: {"d_ref_ms": d, "alpha": "1/2", "q_ref_W": "1"} for unit in p["units"]}}
            traces[node] = {"hand_written": True, "purpose": "fixture_only"}
    for index, delta in enumerate(offsets, 1):
        releases = {"L1": Fraction(0), "S1": exact(delta)}
        if releases["S1"] < 0:
            raise ValueError("Negative manual release")
        reqs, instances, edges = [], [], []
        for app in ("L1", "S1"):
            spec = apps[app]
            reqs.append(request(app + ".r1", str(releases[app]), [n + ".r1" for n in spec["nodes"]]))
            instances.extend(occurrence(n + ".r1", app + ".r1", n, ["CPU1", "CPU2"])
                             for n in spec["nodes"])
            edges.extend([[a + ".r1", b + ".r1"] for a, b in spec["edges"]])
        data["scenarios"].append(scene(f"M{index}", str(Fraction(1, len(offsets))), reqs, instances, edges))
    return stamp({"schema_version": "calibration-workload-v1", "time_contract": data,
                  "physical_platform": deepcopy(catalog["physical_platform"]), "physical_profiles": physical,
                  "applications": apps, "profile_traces": traces,
                  "provenance": {"source_sha256": catalog["source_sha256"], "namespace": "manual-adjustment",
                                 "seed": None, "root_id": "manual-adjustment", "settings_hash": content_hash({"manual": True}),
                                 "scene_pool": "manual", "compatibility_pool": "cpu_common",
                                 "scale": large_nodes + small_nodes, "base_cp_ms": {},
                                 "relative_release_factor": None, "delta_ms": None},
                  "transform": None, "formal_mapping_constraint": None, "formal_initial_solution": None,
                  "evaluation_window_ms": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"})


def manual_evidence(*, large_nodes=8, small_nodes=4, offsets=("0", "15")):
    bundle = manual_bundle(large_nodes=large_nodes, small_nodes=small_nodes, offsets=offsets)
    data = bundle["time_contract"]
    refs = build_references(data)
    deadlines = {str(exact(beta)): make_deadlines(data, refs["timetables"]["H"], beta=beta,
                                                reference_topology_id="branch_join")
                 for beta in ("1", "1.3", "1.6", "2")}
    return {"state": "TIME_CALIBRATION_COMPLETE", "workload": bundle, "reference": refs, "deadlines": deadlines,
            "fixture_only": True, "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
