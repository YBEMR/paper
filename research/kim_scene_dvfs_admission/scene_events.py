"""Split frozen release streams only at real scene changes. Never reset a queue.

For an accepted stream every deadline lies on or before its scene's service
boundary. Thus an empty initial queue in the next scene is a consequence of
the verified schedule; it is never obtained by dropping work. OPP switches
are ideal (zero time/energy). The last scene's OPP covers the one-period tail.
"""
from bisect import bisect_right
import csv
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PLATFORM_DIR = HERE.parent / "kim_synthetic_platform_v1"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))
from events import Request, simulate
from profiles import build_chains, thermal_kwargs
from thermal import evaluate_thermal
from workloads import FROZEN, workload

for name in ("events", "profiles", "thermal", "workloads"):
    if Path(sys.modules[name].__file__).resolve().parent != PLATFORM_DIR:
        raise ImportError(f"{name} does not come from the pinned synthetic platform")

PLATFORM = json.loads((PLATFORM_DIR / "platform.json").read_text(encoding="utf-8"))
OPPS = tuple("".join(parts) for parts in FROZEN["clock_policy"]["constant_opp_levels"])


@dataclass(frozen=True)
class Scene:
    index: int
    name: str
    start_ns: int
    end_ns: int
    service_end_ns: int
    requests: tuple

    @property
    def duration_ns(self):
        return self.end_ns - self.start_ns


def partition_requests(requests, switches, end_ns, service_end_ns):
    """Scene bounds are absolute; contained request times are local to each scene."""
    if not switches:
        raise ValueError("expected at least one scene")
    starts = [t for t, name in switches]
    if starts[0] != 0 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError("scene switches must be strictly increasing from zero")
    if not starts[-1] < service_end_ns <= end_ns:
        raise ValueError("bad service or tail boundary")
    jobs_by_scene = [[] for _ in starts]
    ids = set()
    for job in requests:
        if job.id in ids or not 0 <= job.release_ns < service_end_ns:
            raise ValueError("duplicate ID or out-of-window arrival")
        ids.add(job.id)
        i = bisect_right(starts, job.release_ns) - 1
        service_stop = starts[i+1] if i+1 < len(starts) else service_end_ns
        if not job.release_ns <= job.deadline_ns <= service_stop:
            raise ValueError("a request deadline extends outside its active scene")
        jobs_by_scene[i].append(Request(job.id, job.app, job.release_ns-starts[i], job.deadline_ns-starts[i]))
    return tuple(Scene(i, name, t, starts[i+1] if i+1 < len(starts) else end_ns,
                       starts[i+1] if i+1 < len(starts) else service_end_ns, tuple(jobs_by_scene[i]))
                 for i, (t,name) in enumerate(switches))


def split_workload(window, fps):
    req, switches, end_ns = workload(window, fps)
    return partition_requests(req, switches, end_ns, max(job.deadline_ns for job in req))


def time_scene(platform, scene, deployment, opp):
    if opp not in OPPS or deployment not in FROZEN["deployments"]:
        raise ValueError("unknown deployment or clock triplet")
    return simulate(scene.requests, build_chains(platform, FROZEN, deployment, opp), scene.duration_ns)


def replay_sequence(platform, scenes, deployment, opps, ambient_C, *, leakage=True,
                    variation="base", reset=False):
    """Independent physical replay of one selected policy using the original solver.

    A missed deadline from an empty-queue boundary certifies that any continuation
    of this prefix is infeasible. In this case count only prefix completions and
    withhold whole-window energy; backlog across incompatible frequencies does
    not need an invented within-stage clock transition model.
    """
    if not scenes or len(opps) != len(scenes):
        raise ValueError("one OPP triplet is required for each scene")
    initial = np.array(platform["thermal"]["initial_C"], dtype=float)
    previous = initial.copy()
    peak_lo, peak_hi = initial.copy(), initial.copy()
    rows, prefixes = [], []
    total_energy, min_slack = 0., None
    required = sum(len(scene.requests) for scene in scenes)
    completed = set()
    switches = sum(a != b for a,b in zip(opps, opps[1:]))
    for index, (scene, opp) in enumerate(zip(scenes, opps)):
        if scene.index != index or (index == 0 and scene.start_ns != 0) or (
                index and scene.start_ns != scenes[index-1].end_ns):
            raise ValueError("noncontiguous scene timeline")
        sched = time_scene(platform, scene, deployment, opp)
        # Recheck individual absolute completions. Schedules never drop a job,
        # including on deadline failure; do not pass its backlog into a fresh queue.
        jobs = {q.id:q for q in scene.requests}
        if set(sched.completions_ns) != set(jobs) or completed.intersection(jobs):
            raise AssertionError("request completion coverage differs from frozen workload")
        late_ids = [rid for rid, t in sched.completions_ns.items()
                    if t+scene.start_ns > jobs[rid].deadline_ns+scene.start_ns]
        completed.update(rid for rid, t in sched.completions_ns.items()
                         if t+scene.start_ns <= scene.end_ns)
        if sched.min_slack_ns is not None:
            min_slack = sched.min_slack_ns if min_slack is None else min(min_slack, sched.min_slack_ns)
        if late_ids or not sched.deadline_feasible:
            rows.append(dict(index=index,scene=scene.name,opp=opp,required=len(jobs),
                             deadline_ok=False,late_ids=late_ids))
            return dict(feasible=False,deadline_ok=False,thermal_status="NOT_EVALUATED",
                        required=required,completed=len(completed),fully_replayed=False,
                        energy_j=None,peak_lower_c=None,peak_upper_c=None,final_c=None,
                        min_slack_ms=None if min_slack is None else min_slack/1e6,
                        switches=switches,scene_rows=rows)
        if any(t+scene.start_ns > scene.service_end_ns for t in sched.completions_ns.values()):
            raise AssertionError("accepted scene left backlog at its service boundary")
        args = thermal_kwargs(platform,opp,ambient_C,leakage,variation)
        entry = initial if reset else previous
        args["initial_C"] = entry
        h = evaluate_thermal(sched.duration_ns*1e-9,sched.active_w,
                             transfer_W=sched.transfer_w,**args)
        total_energy += h["energy_J"]
        previous = np.array(h["final_C"])
        peak_lo = np.maximum(peak_lo,h["peak_lower_C"])
        peak_hi = np.maximum(peak_hi,h["peak_upper_C"])
        prefixes.append(h["thermal_status"])
        rows.append(dict(index=index,scene=scene.name,opp=opp,start_ns=scene.start_ns,
                         end_ns=scene.end_ns,service_end_ns=scene.service_end_ns,
                         required=len(jobs),deadline_ok=True,
                         min_slack_ns=sched.min_slack_ns,entry_c=entry.tolist(),final_c=previous.tolist(),
                         energy_j=h["energy_J"],peak_lower_c=h["peak_lower_C"],
                         peak_upper_c=h["peak_upper_C"],thermal_status=h["thermal_status"]))
    if len(completed) != required:
        raise AssertionError("incomplete replay")
    status = "VIOLATION" if "VIOLATION" in prefixes else "UNRESOLVED" if "UNRESOLVED" in prefixes else "SAFE"
    return dict(feasible=status=="SAFE",deadline_ok=True,thermal_status=status,
                required=required,completed=len(completed),fully_replayed=True,
                energy_j=total_energy,peak_lower_c=peak_lo.tolist(),peak_upper_c=peak_hi.tolist(),
                final_c=previous.tolist(),min_slack_ms=None if min_slack is None else min_slack/1e6,
                switches=switches,scene_rows=rows)

@lru_cache(maxsize=1)
def _frozen_records():
    path = PLATFORM_DIR / "raw" / "candidates.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {(r["case_id"],r["deployment"],r["opp"],r["mode"]):r
                for r in csv.DictReader(stream)}


def compare_frozen_fixed(window, fps, deployment, opp, ambient_C, replay, *,
                         leakage=True, variation="base", reset=False):
    """Compare the requested constant-OPP replay to the exact archived comparison row."""
    mode = "independent" if reset else "continuous"
    cid = f"{window}_{fps}fps_{ambient_C:g}C_{'on' if leakage else 'off'}_{variation}"
    old = _frozen_records()[cid,deployment,opp,mode]
    deadline_ok = old["deadline_ok"].lower() == "true"
    if deadline_ok != replay["deadline_ok"] or int(old["required"]) != replay["required"]:
        raise AssertionError(f"frozen fixed-clock deadlines or coverage differ: {cid}/{deployment}/{opp}")
    if not deadline_ok:
        return dict(status="DEADLINE_ONLY", energy_error_j=None, peak_error_c=None)
    names = ("cpu","gpu","dla0","dla1")
    peak_error = max(abs(float(old[f"peak_{n}_c"])-v) for n,v in zip(names,replay["peak_upper_c"]))
    final_error = max(abs(float(old[f"final_{n}_c"])-v) for n,v in zip(names,replay["final_c"]))
    energy_error = abs(float(old["energy_j"])-replay["energy_j"])
    if (replay["thermal_status"] != old["thermal_status"] or
            replay["min_slack_ms"] != float(old["min_slack_ms"]) or
            replay["completed"] != int(old["completed"]) or
            energy_error > 1e-8 or peak_error > 5.1e-4 or final_error > 1e-7):
        raise AssertionError(f"frozen fixed-clock physical replay differs: {cid}/{deployment}/{opp}")
    return dict(status="MATCH",energy_error_j=energy_error,peak_error_c=peak_error,
                final_error_c=final_error)
