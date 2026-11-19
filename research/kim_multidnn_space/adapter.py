"""Resident candidate combinations evaluated by the inherited synthetic platform.

Only the resident stage table is extended. Performance, dispatch, clocks and
four-node thermal integration are imported from the frozen implementation.
"""
from copy import deepcopy
from itertools import product
import json
from math import prod
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "kim_scene_dvfs_admission"
sys.path.insert(0, str(PARENT))
from scene_events import (FROZEN, OPPS, PLATFORM, build_chains, evaluate_thermal,
                          simulate, thermal_kwargs)
from profiles import graph_features, live_bytes


def graph(app_id):
    image = PLATFORM["image"]
    blocks = PLATFORM["architecture_reference"]["graphs"][str(app_id)]["blocks"]
    return graph_features(tuple(tuple(row) for row in blocks), image["side"],
                          image["channels"], image["bytes_per_scalar"])


def validate_candidate(app_id, candidate):
    """Check full graph coverage and data carried at each admitted boundary.

    Operator admission is established by sources.md and the enumerated library.
    This function does not infer TensorRT device support from graph arithmetic.
    """
    ops, heads = graph(app_id)
    stages = candidate["stages"]
    if not candidate.get("id") or not stages:
        raise ValueError("Candidate needs an ID and at least one stage")
    if candidate.get("evidence_class") not in (
            "paper_deployment", "paper_option_constructed", "public_fp16_config_synthetic"):
        raise ValueError("Candidate has no admitted source classification")
    if not candidate.get("source") or not candidate.get("hardware_validation"):
        raise ValueError("Candidate must retain its source and hardware validation boundary")
    expected = 0
    cuts = []
    scalar = PLATFORM["image"]["bytes_per_scalar"]
    for resource, first, last in stages:
        if resource not in ("GPU", "DLA0", "DLA1"):
            raise ValueError("Unknown inference execution resource")
        if not all(isinstance(i, int) for i in (first, last)) or first != expected or not first <= last < len(ops):
            raise ValueError("Skipped, repeated or out-of-range graph operation")
        expected = last + 1
        live = sorted({i for op in ops[last+1:] for i in op.inputs if 0 <= i <= last}
                      | {i for i in heads if i <= last})
        transfer_bytes = scalar * sum(prod(ops[i].shape) for i in live)
        if transfer_bytes != live_bytes(ops, heads, last, scalar):
            raise AssertionError("Transfer omitted a future input or detection head")
        cuts.append(dict(resource=resource, first=first, last=last,
                         mac=sum(op.mac for op in ops[first:last+1]),
                         memory_bytes=sum(op.traffic_bytes for op in ops[first:last+1]),
                         live_outputs=live, transfer_bytes=transfer_bytes))
    if expected != len(ops):
        raise ValueError("Candidate does not execute the complete network")
    expected_resources = {"A": ["DLA0", "GPU"], "C": ["DLA0", "DLA1", "GPU"],
                          "E": ["GPU"]}
    resource_pattern = [stage[0] for stage in stages]
    # The two identical DLA units can carry the sole prefix of option A.
    pattern_ok = candidate.get("option") == "A" and resource_pattern in (
        ["DLA0", "GPU"], ["DLA1", "GPU"])
    if not pattern_ok and resource_pattern != expected_resources.get(candidate.get("option")):
        raise ValueError("Candidate does not match a registered pipeline template")
    return dict(app=app_id, candidate=candidate["id"], layers=len(ops),
                total_mac=sum(op.mac for op in ops), stages=cuts,
                resident_dla_stages=sum(s[0].startswith("DLA") for s in stages))


def build_catalog(library):
    apps = [str(app["id"]) for app in FROZEN["applications"]]
    if set(library["applications"]) != set(apps):
        raise ValueError("Expected exactly the four frozen networks")
    individual = []
    for app in apps:
        candidates = library["applications"][app]
        if len({c["id"] for c in candidates}) != len(candidates):
            raise ValueError("Duplicate per-application candidate ID")
        individual.extend(validate_candidate(int(app), c) for c in candidates)
    extended = deepcopy(FROZEN)
    extended["deployments"] = {}
    rows = []
    anchors = {}
    for choices in product(*(library["applications"][app] for app in apps)):
        stages = {app: deepcopy(c["stages"]) for app, c in zip(apps, choices)}
        engines = sum(s[0].startswith("DLA") for group in stages.values() for s in group)
        key = "__".join(c["id"] for c in choices)
        aliases = [name for name, d in FROZEN["deployments"].items() if d["stages"] == stages]
        if len(aliases) > 1:
            raise AssertionError("Historical aliases are not distinct")
        if aliases:
            key = aliases[0]
            anchors[key] = key
        row = dict(deployment=key, choices={app: c["id"] for app, c in zip(apps, choices)},
                   resident_dla_stages=engines, admitted=engines <= 4,
                   exclusion=None if engines <= 4 else "resident_DLA_stage_limit", stages=stages)
        rows.append(row)
        if row["admitted"]:
            if key in extended["deployments"]:
                raise ValueError("Duplicate deployment combination ID")
            extended["deployments"][key] = dict(stages=stages, resident_dla_engines=engines)
    if set(anchors) != {"A", "C"}:
        raise ValueError("Candidate library must contain exact historical A and C")
    return extended, dict(individual=individual, combinations=rows, historical_anchors=anchors)


LIBRARY = json.loads((HERE / "candidates.json").read_text(encoding="utf-8"))
FROZEN_EXT, CERTIFICATES = build_catalog(LIBRARY)
aliases = CERTIFICATES["historical_anchors"]


def combinations():
    return sorted(FROZEN_EXT["deployments"])


def certificates():
    return deepcopy(CERTIFICATES)


def time_scene(scene, deployment, opp):
    if opp not in OPPS or deployment not in FROZEN_EXT["deployments"]:
        raise ValueError("Unknown resident deployment or frequency action")
    chains = build_chains(PLATFORM, FROZEN_EXT, deployment, opp)
    return simulate(scene.requests, chains, scene.duration_ns)


def replay(scenes, deployment, opps, ambient, *, reset=False):
    """Replay complete original thermal integrals, carrying every scene inlet.

    The orchestration matches scene_events.replay_sequence and also records
    resource occupation. It stops evaluation at a deadline-invalid scene,
    because accepting a fresh queue after that point would discard backlog.
    """
    if not scenes or len(scenes) != len(opps):
        raise ValueError("One frequency triplet required per scene")
    initial = np.array(PLATFORM["thermal"]["initial_C"], dtype=float)
    previous = initial.copy()
    peak_lo, peak_hi = initial.copy(), initial.copy()
    rows, statuses = [], []
    required = sum(len(s.requests) for s in scenes)
    completed = set()
    energy = 0.
    slack = None
    switches = sum(a != b for a, b in zip(opps, opps[1:]))
    busy = {}
    for index, (scene, opp) in enumerate(zip(scenes, opps)):
        if scene.index != index or (index == 0 and scene.start_ns != 0) or (
                index and scene.start_ns != scenes[index-1].end_ns):
            raise ValueError("Scene timeline must be contiguous")
        sched = time_scene(scene, deployment, opp)
        jobs = {r.id: r for r in scene.requests}
        if set(sched.completions_ns) != set(jobs) or completed.intersection(jobs):
            raise AssertionError("Request completion coverage differs")
        completed.update(rid for rid, t in sched.completions_ns.items() if t <= scene.duration_ns)
        late = [rid for rid, t in sched.completions_ns.items() if t > jobs[rid].deadline_ns]
        if sched.min_slack_ns is not None:
            slack = sched.min_slack_ns if slack is None else min(slack, sched.min_slack_ns)
        if late or not sched.deadline_feasible:
            rows.append(dict(index=index, scene=scene.name, opp=opp, required=len(jobs),
                             deadline_ok=False, late_ids=late))
            return dict(feasible=False, deadline_ok=False, thermal_status="NOT_EVALUATED",
                        required=required, completed=len(completed), fully_replayed=False,
                        energy_j=None, peak_lower_c=None, peak_upper_c=None, final_c=None,
                        min_slack_ms=None if slack is None else slack/1e6,
                        switches=switches, scene_rows=rows)
        if any(t+scene.start_ns > scene.service_end_ns for t in sched.completions_ns.values()):
            raise AssertionError("Accepted scene left unfinished work at boundary")
        entry = initial if reset else previous
        kwargs = thermal_kwargs(PLATFORM, opp, ambient, True, "base")
        kwargs["initial_C"] = entry
        heat = evaluate_thermal(sched.duration_ns*1e-9, sched.active_w,
                                transfer_W=sched.transfer_w, **kwargs)
        energy += heat["energy_J"]
        previous = np.array(heat["final_C"])
        peak_lo = np.maximum(peak_lo, heat["peak_lower_C"])
        peak_hi = np.maximum(peak_hi, heat["peak_upper_C"])
        statuses.append(heat["thermal_status"])
        for resource, ns in sched.busy_ns.items():
            busy[resource] = busy.get(resource, 0) + ns
        rows.append(dict(index=index, scene=scene.name, opp=opp, start_ns=scene.start_ns,
                         end_ns=scene.end_ns, service_end_ns=scene.service_end_ns, required=len(jobs),
                         deadline_ok=True, min_slack_ns=sched.min_slack_ns, entry_c=entry.tolist(),
                         final_c=previous.tolist(), energy_j=heat["energy_J"],
                         peak_lower_c=heat["peak_lower_C"], peak_upper_c=heat["peak_upper_C"],
                         thermal_status=heat["thermal_status"], busy_ns=sched.busy_ns))
    if len(completed) != required:
        raise AssertionError("Incomplete request execution")
    status = "VIOLATION" if "VIOLATION" in statuses else "UNRESOLVED" if "UNRESOLVED" in statuses else "SAFE"
    return dict(feasible=status == "SAFE", deadline_ok=True, thermal_status=status,
                required=required, completed=len(completed), fully_replayed=True, energy_j=energy,
                peak_lower_c=peak_lo.tolist(), peak_upper_c=peak_hi.tolist(), final_c=previous.tolist(),
                min_slack_ms=None if slack is None else slack/1e6, switches=switches, scene_rows=rows,
                busy_ns=busy, idle_ns={resource: scenes[-1].end_ns-ns for resource, ns in busy.items()})
