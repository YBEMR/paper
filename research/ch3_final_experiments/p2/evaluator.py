"""Adapter to the frozen physical evaluator. Construct once per isolated process."""
from hashlib import sha256
from importlib import import_module, metadata
import json
from math import fsum, isfinite
from pathlib import Path
import platform
import sys

from search import Domain, OPPS, Result

FREEZE = "553e7f0bd16d10c9545ede12b0e07c87a143938c712274f1ee91b2f31c0d3bba"
CASES = {
    "forward_flat_25C": (25., ["sc0", "sc1", "sc2", "sc3"], [62, 63, 62, 63],
                         "33d20a4cf209a42879341aad6bb9d7700ead00db1e5b4da293064f62a709beea"),
    "reverse_flat_27p5C": (27.5, ["sc3", "sc2", "sc1", "sc0"], [63, 62, 63, 62],
                           "a5062c9d07f000be261549ad17e372f0ce8beb4bae3099f4f27c9dbd1a3713fe"),
}


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"frozen bytes differ: {path.name}")
    return data


def load_frozen(root):
    root = Path(root).resolve()
    manifest = json.loads(checked(root/"research/kim_pressure_feasibility/execution_freeze.json", FREEZE))
    if platform.python_version() != manifest["python"]:
        raise RuntimeError("frozen Python version differs")
    runtime = manifest["runtime_sha256"]
    checked(Path(sys.executable), runtime["python_exe"])
    for pkg, version in manifest["packages"].items():
        dist = metadata.distribution(pkg)
        if dist.version != version:
            raise RuntimeError(f"frozen package version differs: {pkg}")
        for name, expected in runtime["distributions"][pkg].items():
            checked(Path(dist.locate_file(name)), expected)
    pinned = manifest["sha256"]
    for name, expected in pinned.items():
        if "/raw" not in name and name.endswith((".json", ".py")):
            checked(root/name, expected)
    directory = root/"research/kim_pressure_feasibility"
    sys.path.insert(0, str(directory))
    unit = import_module("unit")
    for name in ("unit", "run", "scene_events", "joint_thermal", "design", "physics", "thermal",
                 "workloads", "profiles", "events"):
        path = Path(sys.modules[name].__file__).resolve().relative_to(root).as_posix()
        if path not in pinned:
            raise ImportError(f"unexpected module origin: {name}")
    return unit


class Evaluator:
    def __init__(self, root, case_id, allowed, emit):
        self.unit = unit = load_frozen(root)
        self.events = events = unit.events
        self.emit = emit
        research = Path(root)/"research"
        catalog = unit.read(research/"kim_multidnn_expansion/catalog.json")
        self.domain = Domain(catalog, allowed)
        self.expanded = unit.read(research/"kim_multidnn_expansion/expanded_input.json")
        self.binding = dict(deployment_order=self.domain.order,
                            stages={d: catalog["deployments"][d]["stages"] for d in self.domain.order})
        self.ambient, order, frames, digest = CASES[case_id]
        case = next(c for c in unit.design.cases() if c["id"] == case_id)
        self.scenes = unit.design.make_scenes(case)
        self.identity = unit.verify_stream(self.scenes, dict(request_stream_sha256=digest, scene_order=order,
                                                            frames_in_execution_order=frames))
        thermal = events.PLATFORM["thermal"]
        if not (case["ambient"] == self.ambient and case["fps"] == 25 and
                thermal["initial_C"] == [30.] * 4 and
                list(unit.joint.INITIAL) == [30.] * 4 and thermal["limits_C"] == [80.] * 4 and
                thermal["reference_C"] == 25 and events.OPPS == OPPS and unit.joint.EPS == 1e-9):
            raise ValueError("frozen platform contract differs")

    def proxy(self, dep, scene_idx, idx):
        events = self.events
        opp = OPPS[idx]
        with self.unit.fixed_deployment(self.expanded, self.binding, dep):
            sched = events.time_scene(events.PLATFORM, self.scenes[scene_idx], dep, opp)
            if not sched.deadline_feasible:
                return None
            args = events.thermal_kwargs(events.PLATFORM, opp, self.ambient, True, "base")
            if list(args["initial_C"]) != [30.] * 4 or args["ambient_C"] != self.ambient:
                raise ValueError("scene proxy inlet differs")
            thermal = events.evaluate_thermal(sched.duration_ns*1e-9, sched.active_w,
                                              transfer_W=sched.transfer_w, **args)
            return float(thermal["energy_J"])

    def replay(self, dep, indices):
        unit, events = self.unit, self.events
        if len(indices) != 4 or any(type(i) is not int or not 0 <= i < 27 for i in indices):
            raise ValueError("illegal frequency genome")
        opps = [OPPS[i] for i in indices]
        with unit.fixed_deployment(self.expanded, self.binding, dep):
            physical = events.replay_sequence(events.PLATFORM, self.scenes, dep, opps, self.ambient,
                                              leakage=True, variation="base", reset=False)
            if physical["required"] != 500:
                raise ValueError("request count changed")
            rows = []
            if physical["deadline_ok"]:
                schedules = [{idx: events.time_scene(events.PLATFORM, scene, dep, opp)}
                             for scene, idx, opp in zip(self.scenes, indices, opps, strict=True)]
                rows = unit.completions(self.scenes, schedules, opps)
                status = physical["thermal_status"]
                energies = [r["energy_j"] for r in physical["scene_rows"]]
                if any(not isfinite(x) or x < 0 for x in energies):
                    raise ValueError("invalid scene energy")
                unit.verify_replay(physical, rows, self.scenes, opps,
                                   {"SAFE": 1, "VIOLATION": 2, "UNRESOLVED": 3}[status], fsum(energies))
                if abs(physical["min_slack_ms"] - min(r["slack_ns"] for r in rows)/1e6) > 1e-12:
                    raise ValueError("whole-window deadline slack differs")
                result = Result(status, physical["completed"], physical["min_slack_ms"], physical["energy_j"],
                                tuple(physical["peak_lower_c"]), tuple(physical["peak_upper_c"]))
            else:
                last = physical["scene_rows"][-1]
                prefix = physical["scene_rows"]
                if not 1 <= len(prefix) <= 4:
                    raise ValueError("invalid deadline prefix length")
                late_ids = last["late_ids"]
                requests = {q.id for q in self.scenes[len(prefix)-1].requests}
                if (physical["fully_replayed"] or physical["feasible"] or last["deadline_ok"] or
                        physical["thermal_status"] != "NOT_EVALUATED" or physical["energy_j"] is not None or
                        any(not r["deadline_ok"] for r in prefix[:-1]) or
                        any((r["scene"], r["opp"]) != (self.scenes[j].name, opps[j])
                            for j, r in enumerate(prefix)) or
                        len(set(late_ids)) != len(late_ids) or not set(late_ids) <= requests):
                    raise ValueError("invalid interrupted physical window")
                result = Result("DEADLINE", physical["completed"], physical["min_slack_ms"], None,
                                None, None, tuple(last["late_ids"]))
            self.emit("physical", dict(request_sha256=self.identity, dep=dep, indices=indices,
                                       physical=physical, completions=rows))
            return result
