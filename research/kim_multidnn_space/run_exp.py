"""Frozen exhaustive diagnostic over resident mappings and four scene clocks."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform as host
import subprocess
import sys
from time import perf_counter

for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[key] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "kim_scene_dvfs_admission"))
import run as joint
from joint_thermal import compile_scene
from scene_events import split_workload, thermal_kwargs
import adapter

BASE = "02f3f621cc9ce7f1cd991577388343fa906bbf56"
AMBIENTS = (25., 27.5, 30.)
BUDGET_SECONDS = 300.
EPS = 1e-9
OPPS = adapter.OPPS
PLATFORM = adapter.PLATFORM
SPACE = len(OPPS)**4
NODES = ("CPU", "GPU", "DLA0", "DLA1")


def put_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf8"))


def put_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_freeze(sha):
    root = HERE.parents[1]
    git = ["git", "-C", str(root)]
    if len(sha) != 40 or subprocess.check_output(git+["rev-parse", sha+"^"], text=True).strip() != BASE:
        raise ValueError("Expected a preregistration directly based on the frozen result")
    relative = HERE.relative_to(root).as_posix()
    names = subprocess.check_output(git+["ls-tree", "-r", "--name-only", sha, "--", relative], text=True).splitlines()
    manifest = {}
    for name in names:
        if Path(name).suffix not in (".py", ".json", ".md") or "/raw/" in name:
            continue
        archived = subprocess.check_output(git+["show", sha+":"+name])
        actual = (root/name).read_bytes()
        if actual.replace(b"\r\n", b"\n") != archived.replace(b"\r\n", b"\n"):
            raise ValueError("Preregistered file changed: "+name)
        manifest[name] = hashlib.sha256(archived).hexdigest()
    subprocess.run(git+["diff", "--quiet", BASE, "--", "research/kim_synthetic_platform_v1",
                        "research/kim_scene_dvfs_admission", "research/kim_safety_repair_audit",
                        "research/kim_case_b_freeze", "research/kim_thermal_v1"], check=True)
    if not np.array_equal(joint.INITIAL, PLATFORM["thermal"]["initial_C"]):
        raise ValueError("Exact reference initial state differs")
    return manifest


def best(options):
    options = [x for x in options if x is not None]
    if not options:
        return None
    floor = min(x["predicted_j"] for x in options)
    return min((x for x in options if x["predicted_j"] <= floor+EPS),
               key=lambda x: (x["deployment"], x["code"]))


def physical_choice(choice, scenes, deployment, ambient):
    if choice is None:
        return None
    mark = perf_counter()
    physical = adapter.replay(scenes, deployment, choice["opps"], ambient)
    if not physical["deadline_ok"] or physical["completed"] != physical["required"]:
        raise ArithmeticError("Selected configuration failed complete deadline replay")
    return dict(deployment=deployment, **choice, physical=physical, replay_s=perf_counter()-mark)


def array_hash(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def schedule_rows(scenes, schedules, deployment):
    rows = []
    for scene, phase in zip(scenes, schedules, strict=True):
        for opp, sched in zip(OPPS, phase, strict=True):
            compute_ns = sum(row.end_ns-row.start_ns for row in sched.rows)
            total_response_ns = sum(sched.completions_ns[req.id]-req.release_ns for req in sched.requests)
            row = dict(deployment=deployment, scene=scene.name, opp=opp,
                       deadline_ok=sched.deadline_feasible, requests=len(sched.requests),
                       completed=len(sched.completions_ns), late=len(sched.late_ids),
                       min_slack_ms=sched.min_slack_ns/1e6,
                       maximum_response_ms=sched.max_response_ns/1e6,
                       summed_request_queue_wait_ms=(total_response_ns-compute_ns)/1e6)
            for resource in ("CPU0", "CPU1", "CPU2", "CPU3", "GPU", "DLA0", "DLA1", "XFER"):
                row[resource+"_busy_ms"] = sched.busy_ns[resource]/1e6
            rows.append(row)
    return rows


def evaluate_deployment(scenes, deployment, ambient, folder):
    start = perf_counter()
    schedules = [[adapter.time_scene(scene, deployment, opp) for opp in OPPS] for scene in scenes]
    scheduling_s = perf_counter()-start
    schedules_table = schedule_rows(scenes, schedules, deployment)
    mark = perf_counter()
    tables = [[compile_scene(s.duration_ns*1e-9, s.active_w, s.transfer_w,
                             thermal_kwargs(PLATFORM, opp, ambient, True, "base"))
               if s.deadline_feasible else None for opp, s in zip(OPPS, phase, strict=True)]
              for phase in schedules]
    compile_s = perf_counter()-mark
    mark = perf_counter()
    independent, local, local_rows = joint.local_selection(tables, schedules, ambient, deployment)
    local_s = perf_counter()-mark
    mark = perf_counter()
    fixed, fixed_safe, fixed_deadline_pass, fixed_unresolved = joint.fixed_selection(tables)
    fixed_s = perf_counter()-mark
    kernels = [kernel for table in tables for kernel in table if kernel is not None]
    before = sum(kernel.fallback_calls for kernel in kernels)
    mark = perf_counter()
    optimum, status, energy, depths = joint.joint_search(tables)
    search_s = perf_counter()-mark
    fallbacks = sum(kernel.fallback_calls for kernel in kernels)-before
    counts = np.bincount(status, minlength=4)
    independent = physical_choice(independent, scenes, deployment, ambient)
    fixed = physical_choice(fixed, scenes, deployment, ambient)
    optimum = physical_choice(optimum, scenes, deployment, ambient)
    for selected in (fixed, optimum):
        if selected and (not selected["physical"]["feasible"] or
                         abs(selected["physical"]["energy_j"]-selected["predicted_j"]) > 1e-7):
            raise ArithmeticError("Continuous search disagrees with original physical evaluator")
    info = dict(deployment=deployment, independent=independent, fixed=fixed, optimum=optimum,
                logical_complete_space=SPACE, deadline_failed=int(counts[0]), safe=int(counts[1]),
                overtemp=int(counts[2]), unresolved=int(counts[3]),
                deadline_valid_prefixes=depths, prefix_thermal_evaluations=sum(depths),
                fallback_segment_replays=fallbacks,
                actual_selected_full_replays=sum(x is not None for x in (independent, fixed, optimum)),
                fixed_safe=fixed_safe, fixed_deadline_pass=fixed_deadline_pass, fixed_unresolved=fixed_unresolved,
                fixed_prefix_thermal_evaluations=4*fixed_deadline_pass,
                reset_segment_thermal_evaluations=len(kernels),
                comparisons=joint.compare_sets(local, status, energy),
                array_digest=dict(status_sha256=array_hash(status), energy_j_sha256=array_hash(energy),
                                  status_dtype=str(status.dtype), energy_dtype=str(energy.dtype), shape=[SPACE]),
                timing=dict(scheduling_s=scheduling_s, compile_s=compile_s, local_s=local_s,
                            search_s=search_s, fixed_s=fixed_s,
                            full_replay_s=sum(c["replay_s"] for c in (independent, fixed, optimum) if c),
                            total_s=perf_counter()-start))
    put_json(folder/(deployment+".json"), info)
    return info, local_rows, schedules_table, status, energy


def energy_lower_bound(scenes):
    """Nonnegative heat/leakage above 25 C leaves board and minimum idle energy."""
    power = PLATFORM["power"]
    watts = power["board_W"]+sum(min(power["idle_by_domain_W"][domain]) for domain in ("CPU", "GPU", "DLA"))
    if min(AMBIENTS) < PLATFORM["thermal"]["reference_C"] or min(PLATFORM["thermal"]["initial_C"]) < PLATFORM["thermal"]["reference_C"]:
        return 0.
    return watts*sum(scene.duration_ns for scene in scenes)*1e-9


def run_condition(scenes, ambient, deployments, output):
    output.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    records, local_rows, event_rows = [], [], []
    winner_arrays, winner = None, None
    for deployment in deployments:
        if perf_counter()-start >= BUDGET_SECONDS:
            break
        info, local, events, status, energy = evaluate_deployment(scenes, deployment, ambient, output)
        records.append(info)
        local_rows.extend(local)
        event_rows.extend(events)
        chosen = best([winner, info["optimum"]])
        if chosen is not winner:
            winner = chosen
            winner_arrays = (status.copy(), energy.copy())
        if deployment in ("A", "C"):
            np.savez_compressed(output/(deployment+"_space.npz"), status=status, energy_j=energy)
        print(f"{ambient:g} C / {deployment}: safe={info['safe']}, deadline-failed={info['deadline_failed']}", flush=True)
    if winner_arrays is not None:
        np.savez_compressed(output/"winner_space.npz", status=winner_arrays[0], energy_j=winner_arrays[1])
    independent = best([r["independent"] for r in records])
    fixed = best([r["fixed"] for r in records])
    timeline_rows = []
    for method, selected in (("fixed", fixed), ("independent", independent), ("continuous", winner)):
        if selected is None:
            continue
        for scene, opp in zip(scenes, selected["opps"], strict=True):
            schedule = adapter.time_scene(scene, selected["deployment"], opp)
            for event in schedule.rows:
                timeline_rows.append(dict(method=method, deployment=selected["deployment"], scene=scene.name,
                                          opp=opp, request=event.request, stage=event.stage, resource=event.resource,
                                          start_ns=scene.start_ns+event.start_ns, end_ns=scene.start_ns+event.end_ns,
                                          active_w=event.activity_w))
    covered = len(records) == len(deployments)
    unresolved = sum(r["unresolved"] for r in records)
    proved = covered and unresolved == 0
    upper = winner["physical"]["energy_j"] if winner else None
    lower = upper if proved and winner else energy_lower_bound(scenes)
    if proved and winner is None:
        status = "INFEASIBLE"
    elif proved:
        status = "OPTIMAL"
    else:
        status = "INCOMPLETE"
    summary = dict(ambient_c=ambient, result_status=status, optimality_proven=proved,
                   all_combinations_covered=covered, combinations_total=len(deployments),
                   combinations_evaluated=len(records), unevaluated_deployments=list(deployments[len(records):]),
                   deployment_order=list(deployments), budget_s=BUDGET_SECONDS,
                   budget_policy="Check elapsed time before each deployment; finish a started exact deployment search.",
                   logical_complete_space_total=len(deployments)*SPACE,
                   logical_complete_space_covered=len(records)*SPACE,
                   prefix_thermal_evaluations=sum(r["prefix_thermal_evaluations"] for r in records),
                   fallback_segment_replays=sum(r["fallback_segment_replays"] for r in records),
                   actual_selected_full_replays=sum(r["actual_selected_full_replays"] for r in records),
                   unresolved_sequences=unresolved,
                   independent=independent, fixed=fixed, continuous=winner, bound_lower_j=lower, bound_upper_j=upper,
                   bounds_scope="All registered combinations; minimum board and idle power is a lower bound unless exact optimum proved. Infeasible status has no attainable optimum.",
                   records=records, elapsed_s=perf_counter()-start)
    put_csv(output/"local.csv", local_rows)
    put_csv(output/"event_metrics.csv", event_rows)
    put_csv(output/"selected_timelines.csv", timeline_rows)
    put_json(output/"result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, default=HERE/"raw"/"expanded")
    args = parser.parse_args()
    manifest = check_freeze(args.freeze)
    args.out.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    joint.warmup()
    warmup_s = perf_counter()-start
    scenes = split_workload("10s", 25)
    deployments = tuple(sorted(adapter.combinations(), key=lambda d: (d not in ("A", "C"), d)))
    results = [run_condition(scenes, ambient, deployments, args.out/f"{ambient:g}C") for ambient in AMBIENTS]
    put_json(args.out/"results.json", results)
    put_json(args.out/"execution.json", dict(freeze=args.freeze, manifest_sha256=manifest,
             initial_node_c=PLATFORM["thermal"]["initial_C"], ambient_c=list(AMBIENTS), fps=25,
             service_s=10, evaluation_s=10.04, seed=None, warmup_s=warmup_s,
             elapsed_s=perf_counter()-start, os=host.platform(), python=sys.version, threads=1,
             note="Deterministic simulation. Per-deployment full arrays hash canonical raw bytes; only historical anchors and final environment winners retain NPZ copies."))


if __name__ == "__main__":
    main()
