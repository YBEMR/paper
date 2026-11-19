"""One complete pressure case/deployment using the pinned synthetic evaluator."""
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
sys.path.insert(0, str(RESEARCH / "kim_scene_dvfs_admission"))
import run as joint
import scene_events as events
from joint_thermal import compile_scene
sys.path.insert(0, str(RESEARCH / "kim_safety_repair_audit"))
import design

AMBIENT = 27.5
INITIAL = [30.0] * 4
LIMITS = [80.0] * 4
SIZE = 27 ** 4
ENERGY_TOL = 1e-7
SCOPE = "Frozen synthetic platform; D001/D015 have no real FP16 TensorRT engine-build and output validation."


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def absolute_requests(scenes):
    return [[q.id, q.app, scene.start_ns + q.release_ns, scene.start_ns + q.deadline_ns]
            for scene in scenes for q in scene.requests]


def verify_stream(scenes, spec):
    rows = absolute_requests(scenes)
    packed = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(packed).hexdigest()
    check(digest == spec["request_stream_sha256"], "absolute request digest")
    check(len({r[0] for r in rows}) == len(rows) == 500, "request IDs")
    check(Counter(r[1] for r in rows) == {i: 125 for i in range(4)}, "application counts")
    check(all(r[3] - r[2] == 40000000 for r in rows), "relative deadline")
    check([s.name for s in scenes] == spec["scene_order"], "scene order")
    check([s.service_end_ns - s.start_ns for s in scenes] ==
          [n * 40000000 for n in spec["frames_in_execution_order"]], "scene service windows")
    check(scenes[-1].end_ns == 10040000000 and scenes[-1].service_end_ns == 10000000000, "tail")
    return digest


@contextmanager
def fixed_deployment(expanded, manifest, deployment):
    check(deployment in manifest["deployment_order"], "deployment outside study")
    check(expanded["deployments"][deployment]["stages"] == manifest["stages"][deployment],
          "physical stages differ from registration")
    previous = events.FROZEN
    events.FROZEN = expanded
    try:
        yield
    finally:
        events.FROZEN = previous


def check_thermal(case):
    check(case["ambient"] == AMBIENT and case["fps"] == 25, "case temperature or FPS")
    thermal = events.PLATFORM["thermal"]
    check(thermal["initial_C"] == INITIAL and np.array_equal(joint.INITIAL, INITIAL), "search inlet")
    check(thermal["limits_C"] == LIMITS and thermal["reference_C"] == 25, "limits or leakage reference")
    check(len(events.OPPS) == len(set(events.OPPS)) == 27 and joint.EPS == 1e-9, "frequency domain")
    return case["ambient"]


def build_tables(scenes, deployment, ambient):
    check(ambient == AMBIENT, "compilation ambient")
    schedules, tables = [], []
    for scene in scenes:
        phase, kernels = [], []
        for opp in events.OPPS:
            schedule = events.time_scene(events.PLATFORM, scene, deployment, opp)
            phase.append(schedule)
            kernel = None
            if schedule.deadline_feasible:
                kw = events.thermal_kwargs(events.PLATFORM, opp, ambient, True, "base")
                check(kw["ambient_C"] == ambient and kw["initial_C"] == INITIAL, "kernel parameters")
                kernel = compile_scene(schedule.duration_ns * 1e-9, schedule.active_w, schedule.transfer_w, kw)
                check(kernel.kw["ambient_C"] == ambient and np.array_equal(kernel.initial, INITIAL),
                      "compiled kernel temperature")
            kernels.append(kernel)
        schedules.append(phase)
        tables.append(kernels)
    return schedules, tables


def check_arrays(states, energy, tables):
    check(states.shape == energy.shape == (SIZE,) and states.dtype == np.uint8 and
          energy.dtype == np.float64 and np.all(states <= 3), "classification domain")
    mask = np.array([True])
    for table in tables:
        mask = (mask[:, None] & np.array([k is not None for k in table])).ravel()
    check(np.array_equal(states != 0, mask) and np.isfinite(energy[mask]).all()
          and np.isnan(energy[~mask]).all(), "deadline mask and energy")
    return np.bincount(states, minlength=4).tolist()


def compare_control(states, energy, archive):
    with np.load(archive, allow_pickle=False) as saved:
        check(np.array_equal(states, saved["status"]), "archived classification mismatch")
        old = saved["energy_j"]
        check(old.shape == energy.shape and np.array_equal(np.isnan(old), np.isnan(energy)),
              "archived energy mask mismatch")
        error = float(np.max(np.abs(old[states != 0] - energy[states != 0]), initial=0))
        check(error <= ENERGY_TOL, "archived energy mismatch")
    return error


def completions(scenes, schedules, opps):
    rows = []
    for scene, phase, opp in zip(scenes, schedules, opps, strict=True):
        schedule = phase[events.OPPS.index(opp)]
        check(schedule.deadline_feasible and set(schedule.completions_ns) == {q.id for q in scene.requests},
              "selected schedule coverage")
        for q in scene.requests:
            release = scene.start_ns + q.release_ns
            deadline = scene.start_ns + q.deadline_ns
            finish = scene.start_ns + schedule.completions_ns[q.id]
            check(release <= finish <= deadline <= scene.service_end_ns, "invalid request completion")
            rows.append(dict(scene=scene.name, request_id=q.id, app_id=q.app, release_ns=release,
                             deadline_ns=deadline, completion_ns=finish, slack_ns=deadline-finish))
    check(len(rows) == len({row["request_id"] for row in rows}) == 500, "completion count")
    return rows


def verify_replay(physical, rows, scenes, opps, status, predicted):
    check(physical["fully_replayed"] and physical["deadline_ok"] and
          physical["completed"] == physical["required"] == len(rows) == 500, "complete replay")
    check(physical["thermal_status"] == {1:"SAFE", 2:"VIOLATION", 3:"UNRESOLVED"}[status]
          and physical["feasible"] == (status == 1), "thermal classification")
    check(abs(physical["energy_j"] - predicted) <= ENERGY_TOL, "full-window energy mismatch")
    inlet = INITIAL
    scene_energy = 0.
    peak_lo, peak_hi = np.array(INITIAL), np.array(INITIAL)
    for scene, opp, record in zip(scenes, opps, physical["scene_rows"], strict=True):
        requests = [r for r in rows if r["scene"] == scene.name]
        check(record["scene"] == scene.name and record["opp"] == opp and
              (record["start_ns"],record["service_end_ns"],record["end_ns"]) ==
              (scene.start_ns,scene.service_end_ns,scene.end_ns) and record["entry_c"] == inlet and
              record["required"] == len(requests) and record["deadline_ok"] and
              record["min_slack_ns"] == min(r["slack_ns"] for r in requests), "scene replay mismatch")
        inlet = record["final_c"]
        lo, hi = np.array(record["peak_lower_c"]), np.array(record["peak_upper_c"])
        check(np.isfinite(inlet).all() and np.all(lo <= hi), "scene temperature bounds")
        peak_lo, peak_hi = np.maximum(peak_lo, lo), np.maximum(peak_hi, hi)
        scene_energy += record["energy_j"]
    check(inlet == physical["final_c"] and abs(scene_energy - physical["energy_j"]) <= ENERGY_TOL
          and np.array_equal(peak_lo, physical["peak_lower_c"])
          and np.array_equal(peak_hi, physical["peak_upper_c"]), "whole-window replay accounting")
    measured = 2 if np.any(peak_lo > LIMITS) else 1 if np.all(peak_hi <= LIMITS) else 3
    check(measured == status, "whole-window peak certificate")


def run_unit(manifest, job, output):
    """Only the supervisor dispatches this function after reserving a cold unit."""
    start = perf_counter()
    case_id, deployment = job["case_id"], job["deployment"]
    spec = next(s for s in manifest["cases"] if s["id"] == case_id)
    case = next(c for c in design.cases() if c["id"] == case_id)
    ambient = check_thermal(case)
    scenes = design.make_scenes(case)
    digest = verify_stream(scenes, spec)
    expanded = read(RESEARCH / "kim_multidnn_expansion/expanded_input.json")
    with fixed_deployment(expanded, manifest, deployment):
        mark = perf_counter()
        schedules, tables = build_tables(scenes, deployment, ambient)
        build_s = perf_counter() - mark
        mark = perf_counter()
        winner, states, energy, depths = joint.joint_search(tables)
        search_s = perf_counter() - mark
        counts = check_arrays(states, energy, tables)
        safe = np.flatnonzero(states == 1)
        minimum = float(np.min(energy[safe])) if len(safe) else None
        eligible = safe if len(safe) else np.flatnonzero(states != 0)
        choice = joint.pick(eligible, energy[eligible])
        check(winner == (choice if len(safe) else None), "selection differs from frozen rule")
        np.savez_compressed(output / "space.npz", status=states, energy_j=energy)
        control_error = None
        if deployment in ("A", "C"):
            archive = spec["historical_ac"][deployment]
            control_error = compare_control(states, energy, RESEARCH.parent / archive["path"])
            check(counts == [472392, 0, 59049, 0], "A/C reference totals")
        physical = None
        mark = perf_counter()
        if choice is not None:
            rows = completions(scenes, schedules, choice["opps"])
            physical = events.replay_sequence(events.PLATFORM, scenes, deployment, choice["opps"],
                                              ambient, leakage=True, variation="base", reset=False)
            verify_replay(physical, rows, scenes, choice["opps"], int(states[choice["code"]]), choice["predicted_j"])
            (output / "requests.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf8")
        replay_s = perf_counter() - mark
    certificate = ("UNRESOLVED" if counts[3] else "MIN_SAFE" if counts[1] else "NO_SAFE")
    return dict(**job, scope=SCOPE, ambient_c=ambient, initial_c=INITIAL, request_sha256=digest,
                counts=dict(zip(("deadline_failed","safe","overtemp","unresolved"), counts)),
                logical_codes=SIZE, strict_minimum_known_safe_j=minimum, safe_witness=bool(len(safe)),
                peak_margin_c=(80. - max(physical["peak_upper_c"]) if physical else None),
                selection=choice, selection_role="SAFE" if len(safe) else "diagnostic" if choice else None,
                physical=physical, certificate=certificate, control_max_abs_energy_error_j=control_error,
                build_s=build_s, search_s=search_s, replay_and_requests_s=replay_s,
                full_window_replays=int(choice is not None), legal_prefixes=depths,
                fallback_segment_integrals=sum(k.fallback_calls for phase in tables for k in phase if k),
                unit_compute_and_array_io_s=perf_counter()-start)
