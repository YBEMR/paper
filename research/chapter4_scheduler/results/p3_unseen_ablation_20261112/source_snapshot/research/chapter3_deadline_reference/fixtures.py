"""Hand-authored temporal fixtures; not a random workload generator.

Every caller supplies the scenario, release, support and reference profile.
The small numbers below are test oracles, not frozen scientific parameters.
Only platform frequency values are copied from the existing abstract platform.
"""

from copy import deepcopy


def empty_family(name, topology="manual"):
    return {
        "schema_version": "deadline-reference-input-v1",
        "root_family_id": name,
        "variant_id": "base",
        "topology_id": topology,
        "derivation": {"axis": "BASE", "parent_contract_hash": None},
        "start_grid_ms": "5",
        "response_model": "stage_affine_inverse_v1",
        "context": {"fixture_only": True},
        "execution_rules": {
            "preemption": False, "migration": False,
            "in_stage_opp_change": False, "idle_holds_last_opp": False,
            "switch_only_when_domain_empty": True,
            "idle_policy": "auto_low_immediate_v1", "idle_delay_ms": "0",
            "extra_switch_time_ms": "0", "extra_switch_energy_J": "0",
            "extra_transfer_time_ms": "0", "extra_transfer_energy_J": "0",
            "extra_handoff_time_ms": "0", "extra_handoff_energy_J": "0",
            "interval_convention": "[start,end)",
        },
        "platform": {
            "units": [
                {"id": "CPU1", "domain_id": "CPU"},
                {"id": "CPU2", "domain_id": "CPU"},
                {"id": "GPU0", "domain_id": "GPU"},
                {"id": "NPU0", "domain_id": "NPU"},
            ],
            "domains": {
                "CPU": {"reference_opp": "H", "opps": {
                    "L": {"frequency_GHz": "0.8"},
                    "M": {"frequency_GHz": "1.2"},
                    "H": {"frequency_GHz": "1.6"}}},
                "GPU": {"reference_opp": "H", "opps": {
                    "L": {"frequency_GHz": "0.4"},
                    "M": {"frequency_GHz": "0.6"},
                    "H": {"frequency_GHz": "0.8"}}},
                "NPU": {"reference_opp": "H", "opps": {
                    "L": {"frequency_GHz": "0.5"},
                    "M": {"frequency_GHz": "0.75"},
                    "H": {"frequency_GHz": "1.0"}}},
            },
        },
        "stage_profiles": {},
        "scenarios": [],
    }


def profile(unit_durations, *, alpha="1", work="1"):
    return {"work_units": work, "units": {
        unit: {"d_ref_ms": duration, "alpha": alpha,
               "legal_opps": ["L", "M", "H"]}
        for unit, duration in unit_durations.items()}}


def request(request_id, release, instance_ids):
    return {"id": request_id, "release_ms": release,
            "stage_instance_ids": list(instance_ids)}


def occurrence(instance_id, request_id, shared_id, units):
    return {"id": instance_id, "request_id": request_id,
            "shared_stage_id": shared_id, "legal_units": list(units)}


def scene(scene_id, weight, requests, occurrences, dependencies):
    return {"id": scene_id, "weight": weight, "requests": requests,
            "stage_instances": occurrences, "dependencies": dependencies}


def chain_family(durations=("5", "10", "5"), *, alpha="1"):
    data = empty_family("manual_chain", "chain")
    ids = [f"s{i}" for i in range(len(durations))]
    data["stage_profiles"] = {
        sid: profile({"CPU1": d}, alpha=alpha, work=d)
        for sid, d in zip(ids, durations)}
    data["scenarios"] = [scene("S", "1", [request("r", "0", ids)],
        [occurrence(sid, "r", sid, ["CPU1"]) for sid in ids],
        [[left, right] for left, right in zip(ids, ids[1:])])]
    return data


def diamond_family():
    data = empty_family("manual_diamond", "diamond")
    data["stage_profiles"] = {
        "pre": profile({"CPU1": "5"}, work="5"),
        "left": profile({"CPU1": "10"}, work="10"),
        "right": profile({"CPU2": "5"}, work="5"),
        "join": profile({"GPU0": "5"}, work="5"),
    }
    data["scenarios"] = [scene("S", "1",
        [request("r", "0", ["pre", "left", "right", "join"])],
        [occurrence(s, "r", s, list(p["units"]))
         for s, p in data["stage_profiles"].items()],
        [["pre", "left"], ["pre", "right"],
         ["left", "join"], ["right", "join"]])]
    return data


def gap_family():
    """A has release 0 but reserves CPU1 at 20; B(release 5) fits before A."""
    data = empty_family("manual_gap", "two_requests")
    data["stage_profiles"] = {
        "pre": profile({"GPU0": "20"}, work="20"),
        "tail": profile({"CPU1": "5"}, work="5"),
        "short": profile({"CPU1": "5"}, work="5"),
    }
    data["scenarios"] = [scene("S", "1",
        [request("A", "0", ["pre", "tail"]),
         request("B", "5", ["short"])],
        [occurrence("pre", "A", "pre", ["GPU0"]),
         occurrence("tail", "A", "tail", ["CPU1"]),
         occurrence("short", "B", "short", ["CPU1"])],
        [["pre", "tail"]])]
    return data


def separate_scenes_family():
    """CPU30 in each exclusive scene must NOT become concurrent CPU60."""
    data = empty_family("manual_exclusive_scenes")
    data["stage_profiles"] = {
        "a": profile({"CPU1": "30"}, work="30"),
        "c": profile({"CPU1": "30"}, work="30"),
        "x": profile({"CPU1": "10", "GPU0": "20"}, work="10"),
    }
    data["scenarios"] = [
        scene("S1", "1/2", [request("ra", "0", ["a"]), request("rx", "0", ["x"])],
              [occurrence("a", "ra", "a", ["CPU1"]),
               occurrence("x", "rx", "x", ["CPU1", "GPU0"])], []),
        scene("S2", "1/2", [request("rc", "0", ["c"])],
              [occurrence("c", "rc", "c", ["CPU1"])], []),
    ]
    return data


def copies_family():
    """Two copies make x's sorting load 20 > a's 15; x wins CPU1 tie."""
    data = empty_family("manual_copies")
    data["stage_profiles"] = {
        "a": profile({"CPU1": "15"}, work="15"),
        "x": profile({"CPU1": "10", "GPU0": "10"}, work="10"),
    }
    data["scenarios"] = [scene("S", "1",
        [request("r0", "0", ["a"]), request("r1", "0", ["x1"]),
         request("r2", "0", ["x2"])],
        [occurrence("a", "r0", "a", ["CPU1"]),
         occurrence("x1", "r1", "x", ["CPU1", "GPU0"]),
         occurrence("x2", "r2", "x", ["CPU1", "GPU0"])], [])]
    return data


def parallel_cpu_family():
    data = empty_family("manual_parallel_cpu")
    data["stage_profiles"] = {
        s: profile({"CPU1": "10", "CPU2": "10"}, work="10")
        for s in ("a", "b")}
    data["scenarios"] = [scene("S", "1",
        [request("ra", "0", ["a"]), request("rb", "0", ["b"])],
        [occurrence(s, "r" + s, s, ["CPU1", "CPU2"]) for s in ("a", "b")], [])]
    return data


def shared_scene_family():
    data = empty_family("manual_shared_scenes")
    data["stage_profiles"] = {"x": profile({"CPU1": "10", "CPU2": "10"}, work="10")}
    data["scenarios"] = [scene(s, "1/2", [request("r", "0", ["x"])],
        [occurrence("x", "r", "x", ["CPU1", "CPU2"])], []) for s in ("S1", "S2")]
    return data


def reverse_input_order(data):
    data = deepcopy(data)
    data["platform"]["units"].reverse()
    data["scenarios"].reverse()
    data["stage_profiles"] = dict(reversed(list(data["stage_profiles"].items())))
    for value in data["stage_profiles"].values():
        value["units"] = dict(reversed(list(value["units"].items())))
        for p in value["units"].values():
            p["legal_opps"].reverse()
    for s in data["scenarios"]:
        s["requests"].reverse()
        s["stage_instances"].reverse()
        s["dependencies"].reverse()
        for r in s["requests"]:
            r["stage_instance_ids"].reverse()
        for st in s["stage_instances"]:
            st["legal_units"].reverse()
    return data
