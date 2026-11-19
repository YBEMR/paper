"""Bounded enumeration of a frozen, resident multi-DNN deployment catalog.

This is an adapter around the unchanged event, power and continuous thermal
evaluators. No timing/power parameter is fitted to a new deployment. An
incomplete catalog search is never described as globally optimal.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import platform as host
import sys
from time import perf_counter

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JOINT = HERE.parent / "kim_scene_dvfs_admission"
AUDIT = HERE.parent / "kim_safety_repair_audit"
sys.path.insert(0, str(JOINT))
import run as joint
import scene_events as events
from joint_thermal import compile_scene
from profiles import build_chains, graph_features
sys.path.insert(0, str(AUDIT))
from design import cases, make_scenes

N = len(events.OPPS)
SIZE = N ** 4
EPS = 1e-9
CASE_BUDGET_S = 300.0
FINISH_RESERVE_S = 15.0
BASE = "02f3f621cc9ce7f1cd991577388343fa906bbf56"
NODES = ("CPU", "GPU", "DLA0", "DLA1")


def put_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def put_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_freeze(commit, manifest_path, receipt_path):
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Expected the immutable preregistration commit")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    manifest_bytes = manifest_path.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if receipt["commit"] != commit or receipt["manifest_sha256"] != digest:
        raise ValueError("Remote preregistration receipt does not bind this manifest")
    manifest = json.loads(manifest_bytes)
    if manifest["base_commit"] != BASE:
        raise ValueError("Manifest does not derive from the frozen result base")
    paths = manifest["files"]
    if not isinstance(paths, dict) or not paths:
        raise ValueError("Manifest files must be a nonempty path-to-SHA256 mapping")
    required = {
        "research/kim_multidnn_expansion/experiment.py",
        "research/kim_multidnn_expansion/catalog.py",
        "research/kim_multidnn_expansion/catalog.json",
        "research/kim_multidnn_expansion/expanded_input.json",
        "research/kim_case_b_freeze/input.json",
        "research/kim_safety_repair_audit/design.py",
        "research/kim_safety_repair_audit/design.json",
        "research/kim_scene_dvfs_admission/run.py",
        "research/kim_scene_dvfs_admission/protocol.json",
        "research/kim_scene_dvfs_admission/joint_thermal.py",
        "research/kim_scene_dvfs_admission/scene_events.py",
        "research/kim_synthetic_platform_v1/events.py",
        "research/kim_synthetic_platform_v1/profiles.py",
        "research/kim_synthetic_platform_v1/thermal.py",
        "research/kim_synthetic_platform_v1/workloads.py",
        "research/kim_synthetic_platform_v1/platform.json",
        "research/kim_synthetic_platform_v1/experiments.json",
        "research/kim_thermal_v1/physics.py",
    }
    if not required <= paths.keys():
        raise ValueError(f"Missing frozen dependencies: {sorted(required-paths.keys())}")
    for relative, expected in paths.items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Manifest path leaves the repository")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen input/source changed: {relative}")
    return dict(freeze_commit=commit, manifest_sha256=digest, checked_files=len(paths),
                source_commit=BASE)


@contextmanager
def deployment_view(frozen):
    """Install only the deployment input of the original evaluator, then restore."""
    previous = events.FROZEN
    events.FROZEN = frozen
    try:
        yield
    finally:
        events.FROZEN = previous


def deployment_order(frozen):
    """Use the catalog's sole, outcome-independent structural round-robin rule."""
    from catalog import search_order
    order = search_order()
    if len(order) != len(set(order)) or set(order) != set(frozen["deployments"]):
        raise ValueError("Catalog search order does not enumerate the frozen domain")
    if order[:2] != ["A", "C"]:
        raise ValueError("Historical controls must precede the structural rotation")
    return order


def choose(options, field="predicted_j"):
    options = [x for x in options if x is not None]
    if not options:
        return None
    floor = min(x[field] for x in options)
    return min((x for x in options if x[field] <= floor + EPS),
               key=lambda x: (x["deployment"], x["code"]))


def static_lower_bounds(frozen, scenes):
    """Relax heat/deadlines; retain all work, idle and board energy.

    At T >= reference = ambient = 25 C, all temperature-dependent leakage is
    nonnegative. Deleting it gives a lower bound, not a feasible policy. Timing
    contention changes completion time, not complete-chain activity energy.
    """
    platform = events.PLATFORM
    if min(platform["thermal"]["initial_C"]) < platform["thermal"]["reference_C"]:
        raise ValueError("Nonnegative leakage lower bound prerequisites failed")
    if any(x < 0 for values in platform["power"]["temp_slope_domain_W_K"].values() for x in values):
        raise ValueError("Negative leakage coefficient")
    rows = []
    for deployment in deployment_order(frozen):
        bests = []
        chains_by_opp = {opp: build_chains(platform, frozen, deployment, opp) for opp in events.OPPS}
        for scene in scenes:
            counts = Counter(q.app for q in scene.requests)
            energies = []
            for opp, chains in chains_by_opp.items():
                kw = events.thermal_kwargs(platform, opp, 25, True, "base")
                base = (kw["board_W"] + sum(kw["idle_W"])) * scene.duration_ns * 1e-9
                work = sum(counts[app] * sum(stage.duration_ns * 1e-9 * stage.activity_w
                                            for stage in chain)
                           for app, chain in chains.items())
                energies.append(base + work)
            bests.append(min(energies))
        rows.append(dict(deployment=deployment, lower_bound_j=sum(bests),
                         per_scene_lower_j=bests))
    return rows


def resource_row(deployment, scene, opp, schedule, frozen):
    previous = {q.id: q.release_ns for q in scene.requests}
    gpu_wait, gpu_by_app = [], Counter()
    total_by_resource = Counter()
    # Rows are in dispatch order, so each job's predecessor is already present.
    for row in schedule.rows:
        if row.resource == "GPU":
            gpu_wait.append(row.start_ns - previous[row.request])
            gpu_by_app[int(row.stage.split(".", 1)[0][3:])] += row.end_ns - row.start_ns
        total_by_resource[row.resource] += row.end_ns - row.start_ns
        previous[row.request] = row.end_ns
    entry = dict(deployment=deployment, scene=scene.name, opp=opp,
                 requests=len(scene.requests), completed_by_window=len(scene.requests)-len(schedule.unfinished_ids),
                 deadline_ok=schedule.deadline_feasible, late=len(schedule.late_ids),
                 min_slack_ms=schedule.min_slack_ns / 1e6,
                 max_response_ms=schedule.max_response_ns / 1e6,
                 gpu_wait_sum_ms=sum(gpu_wait)/1e6, gpu_wait_max_ms=max(gpu_wait, default=0)/1e6)
    for device in ("GPU", "DLA0", "DLA1", "XFER"):
        entry[device.lower()+"_busy_ms"] = schedule.busy_ns[device]/1e6
        entry[device.lower()+"_requested_service_ms"] = total_by_resource[device]/1e6
        entry[device.lower()+"_utilization"] = schedule.busy_ns[device]/scene.duration_ns
    for app in range(4):
        entry[f"app{app}_gpu_requested_ms"] = gpu_by_app[app]/1e6
    return entry


def static_mac_rows(frozen):
    image = events.PLATFORM["image"]
    result = []
    for deployment, item in frozen["deployments"].items():
        for app in frozen["applications"]:
            key = str(app["id"])
            blocks = events.PLATFORM["architecture_reference"]["graphs"][key]["blocks"]
            ops, _ = graph_features(tuple(tuple(b) for b in blocks), image["side"], image["channels"],
                                    image["bytes_per_scalar"])
            total = sum(op.mac for op in ops)
            for device, first, last in item["stages"][key]:
                mac = sum(op.mac for op in ops[first:last+1])
                result.append(dict(deployment=deployment, app=int(key), resource=device,
                                   first=first, last=last, mac=mac, network_total_mac=total,
                                   fraction=mac/total))
    return result


def replay_choice(scenes, choice, cache, counters):
    if choice is None:
        return None
    key = choice["deployment"], choice["code"]
    if key not in cache:
        started = perf_counter()
        value = events.replay_sequence(events.PLATFORM, scenes, choice["deployment"], choice["opps"], 25)
        counters["full_policy_replays"] += 1
        counters["full_replay_segment_integrations"] += len(value["scene_rows"])
        counters["full_replay_s"] += perf_counter()-started
        if not value["deadline_ok"] or value["completed"] != 500 or not value["fully_replayed"]:
            raise ArithmeticError("Selected deadline-feasible complete sequence failed physical replay")
        cache[key] = value
    return dict(**choice, physical=cache[key])


def run_case(case, frozen, output, provenance):
    start = perf_counter()
    stop = start + CASE_BUDGET_S - FINISH_RESERVE_S
    output.mkdir(parents=True, exist_ok=True)
    scenes = make_scenes(case)
    order = deployment_order(frozen)
    lower_started = perf_counter()
    lower = static_lower_bounds(frozen, scenes)
    lower_time = perf_counter()-lower_started
    put_json(output/"relaxed_lower_bounds.json", lower)
    deployment_rows, local_rows, resource_rows, same_opp_rows = [], [], [], []
    options = {"independent": [], "joint": [], "no_thermal_constraint": []}
    cache = {}
    replay_counts = dict(full_policy_replays=0, full_replay_segment_integrations=0, full_replay_s=0.)
    reference = None
    interrupted = None
    partial = None
    processed = []
    initial = np.asarray(events.PLATFORM["thermal"]["initial_C"], dtype=float)
    with deployment_view(frozen):
        for deployment in order:
            if perf_counter() >= stop:
                break
            dep_start = perf_counter()
            schedules, tables = [], []
            schedule_s = compile_s = 0.
            compiled_integrals = 0
            kernels = []
            for scene in scenes:
                scheds, table = [], []
                for opp in events.OPPS:
                    if perf_counter() >= stop:
                        interrupted = deployment
                        break
                    mark = perf_counter()
                    sched = events.time_scene(events.PLATFORM, scene, deployment, opp)
                    schedule_s += perf_counter()-mark
                    scheds.append(sched)
                    if scene.name == "sc2":
                        resource_rows.append(resource_row(deployment, scene, opp, sched, frozen))
                    kernel = None
                    if sched.deadline_feasible:
                        mark = perf_counter()
                        kw = events.thermal_kwargs(events.PLATFORM, opp, 25, True, "base")
                        kernel = compile_scene(sched.duration_ns*1e-9, sched.active_w, sched.transfer_w, kw)
                        compile_s += perf_counter()-mark
                        compiled_integrals += 1+len(kernel.upper)
                        kernels.append(kernel)
                    table.append(kernel)
                if interrupted:
                    break
                schedules.append(scheds)
                tables.append(table)
            if interrupted:
                partial = dict(deployment=deployment,
                    status="BUDGET_PARTIAL_NO_COMPLETE_SEQUENCE_CLAIM", scheduling_s=schedule_s,
                    compile_s=compile_s, compiled_scene_actions=len(kernels),
                    compilation_original_integrations=compiled_integrals,
                    elapsed_case_s=perf_counter()-start)
                put_json(output/"partial_deployment.json", partial)
                break
            if perf_counter() >= stop:
                interrupted = deployment
                partial = dict(deployment=deployment, status="BUDGET_BEFORE_LOCAL_SELECTION",
                    scheduling_s=schedule_s, compile_s=compile_s, compiled_scene_actions=len(kernels),
                    compilation_original_integrations=compiled_integrals, elapsed_case_s=perf_counter()-start)
                put_json(output/"partial_deployment.json", partial)
                break
            mark = perf_counter()
            independent, local, rows = joint.local_selection(tables, schedules, 25, deployment)
            local_s = perf_counter()-mark
            local_rows.extend(rows)
            prefix_before = sum(k.screen_calls for k in kernels)
            fallback_before = sum(k.fallback_calls for k in kernels)
            if perf_counter() >= stop:
                interrupted = deployment
                partial = dict(deployment=deployment, status="BUDGET_BEFORE_COMPLETE_SEARCH",
                    scheduling_s=schedule_s, compile_s=compile_s, compiled_scene_actions=len(kernels),
                    compilation_original_integrations=compiled_integrals,
                    independent_prefix_evaluations=prefix_before,
                    fallback_integrations=fallback_before, elapsed_case_s=perf_counter()-start)
                put_json(output/"partial_deployment.json", partial)
                break
            mark = perf_counter()
            winner, states, energy, depths = joint.joint_search(tables)
            search_s = perf_counter()-mark
            # Entire finite clock space is covered in this indivisible operation.
            # Its duration and any wall-clock overrun are recorded explicitly.
            counted = np.bincount(states, minlength=4)
            deadline_grid = np.array([[s.deadline_feasible for s in phase] for phase in schedules])
            deadline_mask = (deadline_grid[0, :, None, None, None] & deadline_grid[1, None, :, None, None]
                             & deadline_grid[2, None, None, :, None] & deadline_grid[3, None, None, None, :]).ravel()
            if not np.array_equal(states != 0, deadline_mask) or not np.array_equal(np.isfinite(energy), deadline_mask):
                raise AssertionError("Full finite action-space mask differs from deadline feasibility")
            minimum_safe = float(np.min(energy[states == 1])) if counted[1] else None
            eligible = np.flatnonzero(states != 0)
            noheat = joint.pick(eligible, energy[eligible])
            for method, choice in (("independent", independent), ("joint", winner),
                                   ("no_thermal_constraint", noheat)):
                if choice:
                    options[method].append(dict(deployment=deployment, **choice))
            mark = perf_counter()
            array_file = output/f"space_{deployment}.npz"
            np.savez_compressed(array_file, status=states, energy_j=energy)
            array_bytes = array_file.read_bytes()
            array_record = dict(path=array_file.name, bytes=len(array_bytes),
                                sha256=hashlib.sha256(array_bytes).hexdigest())
            archive_s = perf_counter()-mark
            independent = replay_choice(scenes, dict(deployment=deployment, **independent) if independent else None,
                                        cache, replay_counts)
            winner = replay_choice(scenes, dict(deployment=deployment, **winner) if winner else None,
                                   cache, replay_counts)
            if winner and (not winner["physical"]["feasible"] or
                           abs(winner["physical"]["energy_j"]-winner["predicted_j"]) > 1e-7):
                raise ArithmeticError("Compiled search winner differs from original physical replay")
            compare = joint.compare_sets(local, states, energy)
            row = dict(deployment=deployment, status="COMPLETE", logical_sequences=SIZE,
                       deadline_failed=int(counted[0]), safe=int(counted[1]),
                       overtemp=int(counted[2]), unresolved=int(counted[3]),
                       conditional_optimality_proven=not bool(counted[3]),
                       minimum_safe_array_j=minimum_safe, energy_tie_tolerance_j=EPS,
                       physical_replay_tolerance_j=1e-7,
                       compiled_scene_actions=len(kernels), compilation_original_integrations=compiled_integrals,
                       independent_prefix_evaluations=prefix_before,
                       joint_prefix_evaluations=sum(depths), deadline_legal_prefixes=depths,
                       independent_fallback_integrations=fallback_before,
                       joint_fallback_integrations=sum(k.fallback_calls for k in kernels)-fallback_before,
                       total_batch_screen_entries=sum(k.screen_calls for k in kernels),
                       scheduling_s=schedule_s, compile_s=compile_s, local_select_s=local_s,
                       joint_search_s=search_s, npz_write_s=archive_s,
                       array_archive=array_record,
                       independent=independent, joint=winner,
                       no_thermal_constraint=next((x for x in reversed(options["no_thermal_constraint"])
                                                  if x["deployment"]==deployment), None),
                       sets=compare)
            if row["total_batch_screen_entries"] != row["independent_prefix_evaluations"]+row["joint_prefix_evaluations"]:
                raise AssertionError("Thermal evaluation accounting mismatch")
            processed.append(deployment)
            if deployment == "C":
                historical = [x for x in options["joint"] if x["deployment"] in ("A", "C")]
                reference = choose(historical)
                if reference:
                    with np.load(output/"space_A.npz", allow_pickle=False) as saved:
                        code = reference["code"]
                        value = saved["energy_j"][code]
                        same_opp_rows.append(dict(deployment="A", reference_deployment=reference["deployment"],
                            code=code, opps=" ".join(reference["opps"]), status=int(saved["status"][code]),
                            continuous_j=float(value) if np.isfinite(value) else None,
                            reference_j=reference["predicted_j"]))
            if reference:
                code = reference["code"]
                same_opp_rows.append(dict(deployment=deployment, reference_deployment=reference["deployment"],
                    code=code, opps=" ".join(reference["opps"]), status=int(states[code]),
                    continuous_j=float(energy[code]) if np.isfinite(energy[code]) else None,
                    reference_j=reference["predicted_j"]))
            row["elapsed_s"] = perf_counter()-dep_start
            deployment_rows.append(row)
            put_json(output/f"deployment_{deployment}.json", row)
            print(f"{case['id']} {deployment}: {len(processed)}/{len(order)} complete, "
                  f"safe={int(counted[1])}, elapsed={perf_counter()-start:.3f}s", flush=True)
        decisions = {}
        for method in options:
            decisions[method] = replay_choice(scenes, choose(options[method]), cache, replay_counts)
            choice = decisions[method]
            if choice and method != "independent" and abs(
                    choice["physical"]["energy_j"]-choice["predicted_j"]) > 1e-7:
                raise ArithmeticError("Global selected continuous energy disagrees with replay")
        historical = {}
        for method in options:
            historical[method] = replay_choice(scenes, choose([v for v in options[method]
                                                              if v["deployment"] in ("A", "C")]),
                                               cache, replay_counts)
    complete = len(processed) == len(order)
    unresolved = sum(row["unresolved"] for row in deployment_rows)
    best = decisions["joint"]
    bound = min(row["lower_bound_j"] for row in lower)
    global_proven = complete and not unresolved
    if global_proven and best:
        bound = min(row["minimum_safe_array_j"] for row in deployment_rows if row["minimum_safe_array_j"] is not None)
    result = dict(case=case, provenance=provenance, budget_s=CASE_BUDGET_S,
                  search_start_cutoff_s=CASE_BUDGET_S-FINISH_RESERVE_S,
                  frozen_deployment_order=order, completed_deployments=processed,
                  unsearched_or_incomplete_deployments=[d for d in order if d not in processed],
                  partial_deployment=partial, coverage_complete=complete,
                  global_optimality_proven=global_proven,
                  overall_status="SAFE_EXISTS" if best else "NO_SAFE" if global_proven else "UNRESOLVED",
                  claimed_scope="entire frozen catalog" if global_proven else "completed listed deployments only",
                  logical_catalog_sequences=len(order)*SIZE,
                  logical_complete_sequences=len(processed)*SIZE,
                  summed_classifications={key:sum(r[key] for r in deployment_rows)
                                         for key in ("deadline_failed", "safe", "overtemp", "unresolved")},
                  decisions=decisions, historical_ac=historical,
                  energy_lower_bound_j=bound,
                  lower_bound_kind="exhaustive binary64 finite-domain minimum; declared energy tolerances apply" if global_proven and best else
                                   "all-catalog additive workload+idle+board relaxation; heat/deadlines removed",
                  energy_tie_tolerance_j=EPS, physical_replay_tolerance_j=1e-7,
                  directed_rounding_energy_certificate=False,
                  best_feasible_energy_j=best["physical"]["energy_j"] if best else None,
                  lower_bound_gap_pct=100*(best["physical"]["energy_j"]-bound)/bound if best else None,
                  static_lower_bound_s=lower_time,
                  compilation_original_integrations=sum(r["compilation_original_integrations"] for r in deployment_rows)
                     +(partial["compilation_original_integrations"] if partial else 0),
                  independent_prefix_evaluations=sum(r["independent_prefix_evaluations"] for r in deployment_rows)
                     +(partial.get("independent_prefix_evaluations", 0) if partial else 0),
                  joint_prefix_evaluations=sum(r["joint_prefix_evaluations"] for r in deployment_rows),
                  fallback_integrations=sum(r["independent_fallback_integrations"]+r["joint_fallback_integrations"]
                                            for r in deployment_rows)
                     +(partial.get("fallback_integrations", 0) if partial else 0), **replay_counts)
    put_csv(output/"local.csv", local_rows)
    put_csv(output/"sc2_resources.csv", resource_rows)
    put_csv(output/"same_opp_reference.csv", same_opp_rows)
    put_json(output/"deployments.json", deployment_rows)
    result["elapsed_s"] = perf_counter()-start
    result["budget_overrun_s"] = max(0., result["elapsed_s"]-CASE_BUDGET_S)
    put_json(output/"result.json", result)
    return result


def run(commit, manifest, receipt, output):
    start = perf_counter()
    provenance = verify_freeze(commit, manifest, receipt)
    from catalog import build_frozen, catalog_metadata
    frozen = build_frozen()
    if frozen != json.loads((HERE/"expanded_input.json").read_text(encoding="utf-8")):
        raise ValueError("Generated deployment input differs from frozen expanded_input.json")
    if json.loads(json.dumps(catalog_metadata())) != json.loads((HERE/"catalog.json").read_text(encoding="utf-8")):
        raise ValueError("Generated catalog metadata differs from its frozen serialization")
    output.mkdir(parents=True, exist_ok=True)
    if (output/"started.json").exists():
        raise FileExistsError("Refuse to overwrite or silently resume a prior experimental attempt")
    put_json(output/"started.json", dict(**provenance, machine=dict(python=sys.version.split()[0],
             os=host.platform(), cpu=host.processor(), threads=1), configured_cases=4,
             per_case_budget_s=CASE_BUDGET_S))
    put_json(output/"catalog_metadata.json", catalog_metadata())
    put_csv(output/"stage_mac.csv", static_mac_rows(frozen))
    registered = [case for case in cases() if case["ambient"] == 25]
    results = []
    try:
        for case in registered:
            results.append(run_case(case, frozen, output/case["id"], provenance))
        verify_freeze(commit, manifest, receipt)
    except Exception as exc:
        put_json(output/"failure.json", dict(error_type=type(exc).__name__, error=str(exc),
                 completed_cases=[r["case"]["id"] for r in results], elapsed_s=perf_counter()-start))
        raise
    put_json(output/"results.json", results)
    put_json(output/"timing.json", dict(provenance=provenance, elapsed_s=perf_counter()-start,
             summed_case_s=sum(r["elapsed_s"] for r in results),
             measurement="perf_counter; one process; one run; imports precede run; no free thermal warmup"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--manifest", type=Path, default=HERE/"freeze_manifest.json")
    parser.add_argument("--receipt", type=Path, default=HERE/"freeze_receipt.json")
    parser.add_argument("--raw", type=Path, default=HERE/"raw"/"expanded")
    arguments = parser.parse_args()
    run(arguments.freeze, arguments.manifest, arguments.receipt, arguments.raw)
