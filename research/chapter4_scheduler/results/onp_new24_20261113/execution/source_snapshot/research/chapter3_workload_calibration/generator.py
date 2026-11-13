"""Explicit task construction and controlled transforms. No reference scheduling here."""

from copy import deepcopy
from fractions import Fraction

from research.chapter3_deadline_reference.contract import (
    ContractError, normalize, contract_hash, content_hash, exact, duration)
from .profiles import make_profile
from .topology import make_topology


def require(condition, code, **details):
    if not condition:
        raise ContractError(code, **details)


def _ids(app, count):
    return [f"{app}.s{i:04d}" for i in range(1, count + 1)]


def _critical_path(nodes, edges, lengths):
    pred = {n: [] for n in nodes}
    for a, b in edges:
        pred[b].append(a)
    ends = {}
    while len(ends) < len(nodes):
        ready = sorted(n for n in nodes if n not in ends and all(p in ends for p in pred[n]))
        require(bool(ready), "CP_CYCLE")
        for n in ready:
            ends[n] = lengths[n] + max((ends[p] for p in pred[n]), default=Fraction(0))
    return max(ends.values())


def scene_layout(kind):
    if kind == "A":
        return [("L1", "S1", 0), ("L1", "S2", 0), ("L1", "S1", 1),
                ("L1", "S2", 1), ("L1", "S1", 2), ("L1", "S2", 2),
                ("L1", "S1", 3), ("L1", "S2", 3)]
    require(kind == "B", "SCENE_POOL_REQUIRED")
    return [("L1", "S1", 0), ("L1", "S2", 0), ("L2", "S1", 0),
            ("L2", "S2", 0), ("L1", "S3", 0), ("L2", "S3", 0),
            ("L1", "S1", 1), ("L2", "S2", 1)]


def _request(app, nodes, release, copy_number):
    rid = f"{app}.r{copy_number}"
    return {"id": rid, "release_ms": str(release),
            "stage_instance_ids": [f"{n}.r{copy_number}" for n in nodes]}


def _scene(cid, large, small, delta, applications, profiles):
    requests, stages, edges = [], [], []
    for app, release in ((large, Fraction(0)), (small, delta)):
        spec = applications[app]
        requests.append(_request(app, spec["nodes"], release, 1))
        stages.extend({"id": f"{n}.r1", "request_id": f"{app}.r1",
                       "shared_stage_id": n, "legal_units": sorted(profiles[n]["units"])}
                      for n in spec["nodes"])
        edges.extend([[a + ".r1", b + ".r1"] for a, b in spec["edges"]])
    return {"id": cid, "weight": "1/8", "requests": requests,
            "stage_instances": stages, "dependencies": edges}


def stamp(bundle):
    bundle["time_contract"] = normalize(bundle["time_contract"])
    bundle["contract_hash"] = contract_hash(bundle["time_contract"])
    bundle["bundle_hash"] = content_hash({k: v for k, v in bundle.items() if k != "bundle_hash"})
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle):
    data = normalize(bundle["time_contract"])
    require(contract_hash(data) == bundle["contract_hash"], "TIME_HASH_DRIFT")
    require(bundle["bundle_hash"] == content_hash({k: v for k, v in bundle.items()
                                                  if k != "bundle_hash"}), "BUNDLE_HASH_DRIFT")
    require(bundle["formal_mapping_constraint"] is None and
            bundle["formal_initial_solution"] is None, "REFERENCE_MAPPING_LEAK")
    require(bundle["evaluation_window_ms"] is None, "WINDOW_NOT_FROZEN")
    require(bundle["thermal_status"] == bundle["energy_status"] == "NOT_EVALUATED", "NOT_TIME_ONLY")
    require(set(bundle["physical_profiles"]) == set(data["stage_profiles"]), "PHYSICAL_PROFILE_COVERAGE")
    for sid, profile in data["stage_profiles"].items():
        physical = bundle["physical_profiles"][sid]
        require(exact(physical["work_units"]) == exact(profile["work_units"]), "PHYSICAL_WORK_DRIFT")
        require(set(physical["units"]) == set(profile["units"]), "PHYSICAL_SUPPORT_DRIFT", stage=sid)
        for unit, p in profile["units"].items():
            q = physical["units"][unit]
            require(exact(q["d_ref_ms"]) == exact(p["d_ref_ms"]) and
                    exact(q["alpha"]) == exact(p["alpha"]), "PHYSICAL_TIME_DRIFT", stage=sid)
            require(exact(q["q_ref_W"]) > 0, "NONPOSITIVE_ACTIVITY_POWER")
    return True


def build_base(catalog, *, root_id, namespace, seed, scene_pool, compatibility_pool,
               scale, settings, parent=None):
    require(isinstance(scale, int) and scale in (6, 12, 24, 48, 96), "INVALID_SCALE")
    require(settings["reference_topology"] == "branch_join", "BASE_TOPOLOGY_REQUIRED")
    require(settings["s7_release_rule"] == "synchronous_same_application", "S7_RULE_REQUIRED")
    names = ["L1", "S1", "S2"] if scene_pool == "A" else ["L1", "L2", "S1", "S2", "S3"]
    layout = scene_layout(scene_pool)
    profiles, physical, traces, apps = {}, {}, {}, {}
    for app in names:
        nodes = _ids(app, scale * 2 // 3 if app.startswith("L") else scale // 3)
        topology = make_topology(nodes, "branch_join", key=f"{namespace}/{seed}/{root_id}/{app}/branch",
                                 settings=settings["topology"])
        apps[app] = {"role": "large" if app.startswith("L") else "small", "nodes": nodes,
                     **topology}
        for n in nodes:
            p = make_profile(catalog, namespace=namespace, seed=seed, root_id=root_id,
                             app_id=app, stage_id=n, pool=compatibility_pool,
                             settings=settings["profiles"])
            profiles[n], physical[n], traces[n] = p["time_profile"], p["physical_profile"], p["trace"]
    temp = {"stage_profiles": profiles, "platform": catalog["time_platform"]}
    cp = {}
    for app, spec in apps.items():
        if spec["role"] == "large":
            cp[app] = _critical_path(spec["nodes"], spec["edges"],
                                    {n: min(duration(temp, n, u, "H") for u in profiles[n]["units"])
                                     for n in spec["nodes"]})
    fraction = exact(settings["relative_release_factor"])
    require(fraction > 0, "POSITIVE_RELEASE_FACTOR_REQUIRED")
    grid = Fraction(5)
    delta = grid * max(1, -(-(fraction * max(cp.values())) // grid))
    data = {"schema_version": "deadline-reference-input-v1", "root_family_id": root_id,
            "variant_id": f"base_{scale}", "topology_id": "branch_join",
            "derivation": {"axis": "BASE" if parent is None else "S2",
                           "parent_contract_hash": None if parent is None else parent["contract_hash"]},
            "start_grid_ms": "5", "response_model": "stage_affine_inverse_v1",
            "context": {"namespace": namespace, "seed": seed, "initial_temperature_C": ["50"] * 4,
                        "evaluation_window_status": "UNFROZEN"},
            "execution_rules": deepcopy(catalog["execution_rules"]),
            "platform": deepcopy(catalog["time_platform"]), "stage_profiles": profiles,
            "scenarios": [_scene(f"C{i}", l, s, j * delta, apps, profiles)
                          for i, (l, s, j) in enumerate(layout, 1)]}
    bundle = stamp({"schema_version": "calibration-workload-v1", "time_contract": data,
                    "physical_platform": deepcopy(catalog["physical_platform"]),
                    "physical_profiles": physical, "applications": apps,
                    "profile_traces": traces,
                    "provenance": {"source_sha256": catalog["source_sha256"],
                                   "namespace": namespace, "seed": seed, "root_id": root_id,
                                   "settings_hash": content_hash(settings), "scene_pool": scene_pool,
                                   "compatibility_pool": compatibility_pool, "scale": scale,
                                   "base_cp_ms": {a: str(v) for a, v in cp.items()},
                                   "relative_release_factor": str(fraction), "delta_ms": str(delta)},
                    "transform": None, "formal_mapping_constraint": None,
                    "formal_initial_solution": None, "evaluation_window_ms": None,
                    "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"})
    if parent is not None:
        validate_transform(parent, bundle)
    return bundle


def _derived(base, axis, label):
    validate_bundle(base)
    out = deepcopy(base)
    out["time_contract"]["derivation"] = {"axis": axis, "parent_contract_hash": base["contract_hash"]}
    out["time_contract"]["variant_id"] = label
    out["transform"] = {"axis": axis, "parent_bundle_hash": base["bundle_hash"]}
    return out


def subset(base, count):
    require(count in (1, 2, 4, 6, 8), "S1_COUNT")
    out = _derived(base, "S1", f"s1_{count}")
    out["time_contract"]["scenarios"] = out["time_contract"]["scenarios"][:count]
    for scene in out["time_contract"]["scenarios"]:
        scene["weight"] = str(Fraction(1, count))
    return stamp(out)


def transform(base, axis, *, value, settings):
    out = _derived(base, axis, f"{axis.lower()}_{value}")
    data = out["time_contract"]
    if axis == "S4":
        require(value in ("serial", "layered"), "S4_KIND")
        data["topology_id"] = value
        for app, spec in out["applications"].items():
            p = out["provenance"]
            topology = make_topology(spec["nodes"], value,
                                     key=f"{p['namespace']}/{p['seed']}/{p['root_id']}/{app}/{value}",
                                     settings=settings["topology"])
            spec.update(topology)
        for scene in data["scenarios"]:
            scene["dependencies"] = []
            for req in scene["requests"]:
                app, copy_number = req["id"].rsplit(".r", 1)
                scene["dependencies"].extend([[a + ".r" + copy_number, b + ".r" + copy_number]
                                               for a, b in out["applications"][app]["edges"]])
    elif axis == "S5":
        factor = exact(value)
        require(factor in (Fraction(3, 4), Fraction(1), Fraction(5, 4)), "S5_FACTOR")
        out["transform"]["factor"] = str(factor)
        for sid, p in data["stage_profiles"].items():
            p["work_units"] = str(exact(p["work_units"]) * factor)
            out["physical_profiles"][sid]["work_units"] = p["work_units"]
            for unit, entry in p["units"].items():
                entry["d_ref_ms"] = str(exact(entry["d_ref_ms"]) * factor)
                out["physical_profiles"][sid]["units"][unit]["d_ref_ms"] = entry["d_ref_ms"]
    elif axis == "S6":
        require(exact(value) in (50, 78), "S6_TEMPERATURE")
        data["context"]["initial_temperature_C"] = [str(exact(value))] * 4
    elif axis == "S7":
        require(value == 2 and settings["s7_release_rule"] == "synchronous_same_application", "S7_RULE")
        for scene in data["scenarios"]:
            reqs, stages, edges = deepcopy((scene["requests"], scene["stage_instances"], scene["dependencies"]))
            for req in reqs:
                require(req["id"].endswith(".r1"), "S7_BASE_COPY_REQUIRED")
                req["id"] = req["id"][:-1] + "2"
                req["stage_instance_ids"] = [s[:-1] + "2" for s in req["stage_instance_ids"]]
            for s in stages:
                s["id"], s["request_id"] = s["id"][:-1] + "2", s["request_id"][:-1] + "2"
            edges = [[a[:-1] + "2", b[:-1] + "2"] for a, b in edges]
            scene["requests"].extend(reqs)
            scene["stage_instances"].extend(stages)
            scene["dependencies"].extend(edges)
    elif axis == "E2":
        allowed = set(value)
        require(allowed and allowed <= {"CPU1", "CPU2", "GPU0", "NPU0"}, "E2_UNITS")
        for scene in data["scenarios"]:
            for stage in scene["stage_instances"]:
                stage["legal_units"] = sorted(set(stage["legal_units"]) & allowed)
                require(bool(stage["legal_units"]), "E2_RESOURCE_UNSUPPORTED", stage=stage["shared_stage_id"])
        out["transform"]["available_units"] = sorted(allowed)
    elif axis == "S3":
        require(value in (2, 4), "S3_EQUAL_SPLIT")
        require(settings["split_rule"] == "equal_contiguous", "S3_RULE_REQUIRED")
        child_map = {s: [s + f".p{i}" for i in range(1, value + 1)] for s in data["stage_profiles"]}
        profiles, physical, traces = {}, {}, {}
        for sid, children in child_map.items():
            for child in children:
                p, q = deepcopy(data["stage_profiles"][sid]), deepcopy(out["physical_profiles"][sid])
                p["work_units"] = str(exact(p["work_units"]) / value)
                q["work_units"] = p["work_units"]
                for unit, entry in p["units"].items():
                    entry["d_ref_ms"] = str(exact(entry["d_ref_ms"]) / value)
                    q["units"][unit]["d_ref_ms"] = entry["d_ref_ms"]
                profiles[child], physical[child] = p, q
                traces[child] = {"parent_stage_id": sid, "fraction": str(Fraction(1, value)),
                                 "parent_trace_hash": content_hash(out["profile_traces"][sid])}
        for scene in data["scenarios"]:
            expanded = {}
            for stage in scene["stage_instances"]:
                suffix = ".r" + stage["request_id"].rsplit(".r", 1)[1]
                expanded[stage["id"]] = [{**stage, "id": c + suffix, "shared_stage_id": c}
                                          for c in child_map[stage["shared_stage_id"]]]
            scene["dependencies"] = [[expanded[a][-1]["id"], expanded[b][0]["id"]]
                                      for a, b in scene["dependencies"]] + [
                                          [a["id"], b["id"]] for group in expanded.values()
                                          for a, b in zip(group, group[1:])]
            scene["stage_instances"] = [s for group in expanded.values() for s in group]
            for req in scene["requests"]:
                req["stage_instance_ids"] = [s["id"] for iid in req["stage_instance_ids"] for s in expanded[iid]]
        for app, spec in out["applications"].items():
            spec["edges"] = [[child_map[a][-1], child_map[b][0]] for a, b in spec["edges"]] + [
                [a, b] for n in spec["nodes"] for a, b in zip(child_map[n], child_map[n][1:])]
            spec["nodes"] = [c for n in spec["nodes"] for c in child_map[n]]
            spec["required_outputs"] = [child_map[n][-1] for n in spec["required_outputs"]]
            spec["trace"] = {"equal_split": value, "parent_topology_hash": content_hash(base["applications"][app])}
        data["stage_profiles"], out["physical_profiles"], out["profile_traces"] = profiles, physical, traces
        out["transform"]["child_to_parent"] = {c: p for p, children in child_map.items() for c in children}
        out["transform"]["split_factor"] = value
    else:
        raise ContractError("UNSUPPORTED_TRANSFORM", axis=axis)
    stamp(out)
    validate_transform(base, out)
    return out


def request_sources(base, child):
    originals = {s["id"]: {r["id"] for r in s["requests"]} for s in base["time_contract"]["scenarios"]}
    result = {}
    for scene in child["time_contract"]["scenarios"]:
        result[scene["id"]] = {}
        for req in scene["requests"]:
            existing = req["id"] in originals[scene["id"]]
            result[scene["id"]][req["id"]] = {"source_scene": scene["id"],
                "source_request": req["id"] if existing else req["id"][:-1] + "1",
                "policy": "absolute" if existing else "same_relative"}
    return result


def inherited_mapping(base_mapping, child):
    parent = child.get("transform", {}).get("child_to_parent", {})
    ids = {s["shared_stage_id"] for sc in child["time_contract"]["scenarios"] for s in sc["stage_instances"]}
    return {sid: base_mapping[parent.get(sid, sid)] for sid in sorted(ids)}


def validate_transform(parent, child):
    validate_bundle(parent)
    validate_bundle(child)
    p, c = parent["time_contract"], child["time_contract"]
    axis = c["derivation"]["axis"]
    require(c["derivation"]["parent_contract_hash"] == parent["contract_hash"], "TRANSFORM_PARENT")
    for field in ("platform", "execution_rules", "root_family_id", "start_grid_ms", "response_model"):
        require(c[field] == p[field], "TRANSFORM_PLATFORM_DRIFT", field=field)
    require(parent["physical_platform"] == child["physical_platform"], "THERMAL_PLATFORM_DRIFT")
    if axis == "S2":
        for sid, profile in p["stage_profiles"].items():
            require(c["stage_profiles"].get(sid) == profile and
                    child["physical_profiles"][sid] == parent["physical_profiles"][sid], "S2_OLD_PROFILE_CHANGED")
        for app, old in parent["applications"].items():
            new = child["applications"][app]
            require(set(old["nodes"]) < set(new["nodes"]), "S2_NODES_NOT_ADDED")
            require(set(map(tuple, old["edges"])) <= set(map(tuple, new["edges"])), "S2_OLD_EDGES_CHANGED")
        return True
    ps = {s["id"]: s for s in p["scenarios"]}
    if axis != "S1":
        require(set(ps) == {s["id"] for s in c["scenarios"]}, "SCENES_CHANGED")
    for scene in c["scenarios"]:
        original = ps[scene["id"]]
        reqs = {r["id"]: r for r in scene["requests"]}
        for r in original["requests"]:
            require(r["id"] in reqs and reqs[r["id"]]["release_ms"] == r["release_ms"], "ORIGINAL_RELEASE_CHANGED")
        if axis not in ("S3", "S7"):
            require(scene["requests"] == original["requests"], "REQUESTS_CHANGED")
        if axis in ("S5", "S6", "E2", "S1"):
            require(scene["dependencies"] == original["dependencies"], "DAG_CHANGED")
    if axis == "S3":
        mapping = child["transform"]["child_to_parent"]
        for sid, old in p["stage_profiles"].items():
            children = [s for s in mapping if mapping[s] == sid]
            require(sum((exact(c["stage_profiles"][s]["work_units"]) for s in children), Fraction(0)) ==
                    exact(old["work_units"]), "S3_WORK_NONCONSERVATION")
            for unit in old["units"]:
                require(all(c["stage_profiles"][s]["units"][unit]["alpha"] == old["units"][unit]["alpha"]
                            for s in children), "S3_ALPHA_CHANGED")
                require(all(child["physical_profiles"][s]["units"][unit]["q_ref_W"] ==
                            parent["physical_profiles"][sid]["units"][unit]["q_ref_W"] for s in children), "S3_Q_CHANGED")
                for opp in ("H", "M", "L"):
                    require(sum((duration(c, s, unit, opp) for s in children), Fraction(0)) ==
                            duration(p, sid, unit, opp), "S3_DURATION_NONCONSERVATION")
    if axis in ("S4", "S6", "S7", "E2", "S1"):
        require(c["stage_profiles"] == p["stage_profiles"] and
                child["physical_profiles"] == parent["physical_profiles"], "UNCHANGED_PROFILES_DRIFT")
    if axis == "S5":
        factor = exact(child["transform"]["factor"])
        require(factor in (Fraction(3, 4), Fraction(1), Fraction(5, 4)), "S5_FACTOR")
        require(set(c["stage_profiles"]) == set(p["stage_profiles"]), "S5_IDENTITIES_CHANGED")
        for sid, old in p["stage_profiles"].items():
            new = c["stage_profiles"][sid]
            require(exact(new["work_units"]) == factor * exact(old["work_units"]), "S5_WORK_SCALING")
            require(set(new["units"]) == set(old["units"]), "S5_SUPPORT_CHANGED")
            for unit, entry in old["units"].items():
                np = new["units"][unit]
                require(exact(np["d_ref_ms"]) == factor * exact(entry["d_ref_ms"]), "S5_DURATION_SCALING")
                require(np["alpha"] == entry["alpha"] and np["legal_opps"] == entry["legal_opps"], "S5_RESPONSE_CHANGED")
                before = parent["physical_profiles"][sid]["units"][unit]
                after = child["physical_profiles"][sid]["units"][unit]
                require({k: v for k, v in before.items() if k != "d_ref_ms"} ==
                        {k: v for k, v in after.items() if k != "d_ref_ms"}, "S5_POWER_CHANGED")
    if axis == "S7":
        for scene in c["scenarios"]:
            original = ps[scene["id"]]
            require(len(scene["requests"]) == 2 * len(original["requests"]) and
                    len(scene["stage_instances"]) == 2 * len(original["stage_instances"]), "S7_COPY_COUNT")
            reqs = {r["id"]: r for r in scene["requests"]}
            stages = {s["id"]: s for s in scene["stage_instances"]}
            for req in original["requests"]:
                require(reqs[req["id"]] == req, "S7_ORIGINAL_REQUEST_CHANGED")
                new_id = req["id"][:-1] + "2"
                expected = {**req, "id": new_id, "stage_instance_ids": [s[:-1] + "2" for s in req["stage_instance_ids"]]}
                require(reqs.get(new_id) == expected, "S7_COPY_RELEASE_OR_MEMBERSHIP")
            for stage in original["stage_instances"]:
                require(stages.get(stage["id"]) == stage, "S7_ORIGINAL_STAGE_CHANGED")
                new_id = stage["id"][:-1] + "2"
                require(stages.get(new_id) == {**stage, "id": new_id, "request_id": stage["request_id"][:-1] + "2"},
                        "S7_COPY_STAGE_CHANGED")
            expected_edges = sorted(original["dependencies"] + [[a[:-1] + "2", b[:-1] + "2"] for a, b in original["dependencies"]])
            require(scene["dependencies"] == expected_edges, "S7_COPY_DEPENDENCIES")
    return True


def statistics(bundle):
    data = bundle["time_contract"]
    result = {}
    for scene in data["scenarios"]:
        ids = {s["shared_stage_id"] for s in scene["stage_instances"]}
        result[scene["id"]] = {
            "fixed_stage_identities": len(ids), "execution_instances": len(scene["stage_instances"]),
            "requests": len(scene["requests"]), "weight": scene["weight"],
            "work_units": str(sum((exact(data["stage_profiles"][s["shared_stage_id"]]["work_units"])
                                    for s in scene["stage_instances"]), Fraction(0))),
            "releases_ms": {r["id"]: r["release_ms"] for r in scene["requests"]}}
    active = {s["shared_stage_id"] for sc in data["scenarios"] for s in sc["stage_instances"]}
    return {"scenes": result, "family_fixed_stage_identities": len(active),
            "family_application_identities": len({s.split(".")[0] for s in active}),
            "scene_pool": bundle["provenance"]["scene_pool"],
            "compatibility_pool": bundle["provenance"]["compatibility_pool"]}
