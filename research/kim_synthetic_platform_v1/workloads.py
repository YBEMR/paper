"""Deterministic release grid. Time zero and the tail are shared across deployments."""
import json
from hashlib import sha256
from pathlib import Path
from events import Request

HERE = Path(__file__).resolve().parent
FROZEN_INPUT = HERE.parent / "kim_case_b_freeze" / "input.json"
CONFIG = json.loads((HERE / "experiments.json").read_text(encoding="utf-8"))
FROZEN = json.loads(FROZEN_INPUT.read_text(encoding="utf-8-sig"))


def time_ns(frame, fps):
    # Nearest integer nanosecond to the absolute rational timestamp.
    return (2 * frame * 10**9 + fps) // (2 * fps)


def workload(window, fps):
    if window not in CONFIG["windows"] or fps not in CONFIG["fps"]:
        raise ValueError((window, fps))
    block_frames = CONFIG["long_block_seconds"] * fps
    frames = {"short": 4, "10s": block_frames, "20s": 2 * block_frames}[window]
    requests, changes = [], []
    scene_for_frame = []
    if window == "short":
        scene_for_frame = list(CONFIG["order"])
    else:
        boundaries = [i * block_frames // 4 for i in range(5)]
        block = [scene for i, scene in enumerate(CONFIG["order"])
                 for _ in range(boundaries[i+1] - boundaries[i])]
        scene_for_frame = block * (frames // block_frames)
    for frame, scene in enumerate(scene_for_frame):
        release, deadline = time_ns(frame, fps), time_ns(frame + 1, fps)
        if not frame or scene != scene_for_frame[frame-1]:
            changes.append((release, scene))
        for app in FROZEN["fsm"]["active_apps"][scene]:
            requests.append(Request(f"f{frame:04d}-a{app}", app, release, deadline))
    return requests, changes, time_ns(frames + CONFIG["tail_periods"], fps)


def conditions():
    for window in CONFIG["windows"]:
        for fps in CONFIG["fps"]:
            for ambient in CONFIG["ambient_C"]:
                for leakage in CONFIG["leakage"]:
                    variations = [CONFIG["base"]]
                    if {"window":window, "fps":fps, "leakage":leakage} == CONFIG["perturb_only"]:
                        variations += CONFIG["resistance_sensitivity"]
                    for var in variations:
                        cid = f"{window}_{fps}fps_{ambient}C_{leakage}_{var}"
                        yield dict(case_id=cid, window=window, fps=fps, ambient_c=ambient,
                                   leakage=leakage, variation=var)


def request_hash(jobs):
    canonical = "\n".join(f"{j.id},{j.app},{j.release_ns},{j.deadline_ns}" for j in jobs)
    return sha256(canonical.encode("ascii")).hexdigest()
