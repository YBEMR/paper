"""Preregistered scene orders, dwell times, release streams and paired job IDs."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOINT = HERE.parent / "kim_scene_dvfs_admission"
if str(JOINT) not in sys.path:
    sys.path.insert(0, str(JOINT))
from scene_events import FROZEN, Request, partition_requests
from workloads import time_ns

DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))


def cases():
    """Return the entire design, including the two designated regression controls."""
    result = []
    for order_id, order in DESIGN["orders"].items():
        for dwell_id, frames in DESIGN["dwell_frames_by_scene"].items():
            for ambient in DESIGN["ambient_values_c"]:
                temperature_id = format(ambient, "g").replace(".", "p")
                result.append(dict(
                    id=f"{order_id}_{dwell_id}_{temperature_id}C", order_id=order_id,
                    dwell_id=dwell_id, order=list(order), dwell_frames=list(frames),
                    dwell_s=[f / DESIGN["fps"] for f in frames], ambient=ambient,
                    fps=DESIGN["fps"], historic_repeat=(order_id == "forward" and
                            dwell_id == "flat" and ambient in (25,30))))
    return result


def make_scenes(case):
    """Use canonical frame indices for job IDs, and the chosen order for time."""
    order = case["order"]
    frames = dict(zip(DESIGN["scene_key_order"], case["dwell_frames"], strict=True))
    edges = {tuple(edge) for edge in FROZEN["fsm"]["edges"]}
    if len(order) != len(frames) or set(order) != set(frames):
        raise ValueError("Each named FSM-A scene must appear once")
    if not all(pair in edges for pair in zip(order, order[1:])):
        raise ValueError("Disallowed FSM transition")
    if any(not isinstance(f, int) or f <= 0 for f in frames.values()) or sum(frames.values()) != 250:
        raise ValueError("Unregistered workload length")
    origin, canonical_starts = 0, {}
    for name, dwell in frames.items():
        canonical_starts[name] = origin
        origin += dwell
    requests, switches = [], []
    frame = 0
    fps = case["fps"]
    for scene in order:
        switches.append((time_ns(frame,fps),scene))
        for local_frame in range(frames[scene]):
            stable_frame_id = canonical_starts[scene] + local_frame
            for app in FROZEN["fsm"]["active_apps"][scene]:
                requests.append(Request(f"f{stable_frame_id:04d}-a{app}",app,
                                        time_ns(frame,fps),time_ns(frame+1,fps)))
            frame += 1
    return partition_requests(requests, switches, time_ns(frame+DESIGN["tail_frames"],fps),
                              time_ns(frame,fps))


def image_ranks(scenes):
    """Symbolic image identifiers in chronological order; physical cost is image-independent."""
    seen = {}
    ranks = {}
    for scene in scenes:
        for req in scene.requests:
            k = seen.get(req.app,0)
            ranks[req.id] = 1 + k % 2
            seen[req.app] = k + 1
    return ranks
