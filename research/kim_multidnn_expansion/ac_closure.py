"""Close exactly four pending A/C finite-domain optimality gaps.

No parameter changes and no new scheduling or thermal algorithm.  The original
event generator, affine continuous-thermal screen, exhaustive prefix search and
full physical replay are imported from the pinned research packages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform as host
import subprocess
import sys
from time import perf_counter

for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JOINT = HERE.parent / "kim_scene_dvfs_admission"
AUDIT = HERE.parent / "kim_safety_repair_audit"
sys.path.insert(0, str(JOINT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


joint = _load("kim_ac_frozen_joint", JOINT / "run.py")
design = _load("kim_ac_frozen_design", AUDIT / "design.py")
from joint_thermal import compile_scene
from scene_events import OPPS, PLATFORM, replay_sequence, thermal_kwargs, time_scene

BASE = "02f3f621cc9ce7f1cd991577388343fa906bbf56"
CASE_IDS = (
    "forward_flat_27p5C",
    "forward_alternating_25C",
    "reverse_flat_25C",
    "reverse_alternating_25C",
)
DEPLOYMENTS = ("A", "C")
N = len(OPPS)
EPS = 1e-9
REPLAY_TOL = 1e-7


def put_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def put_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_manifest(path, freeze):
    """Verify a preregistered SHA256 map, including all scientific dependencies.

    The caller obtains the preregistration commit through the connected GitHub
    reader.  This local check does not pretend that an incomplete download is a
    full Git checkout.  Accepted schema: {base_commit, files: {path: sha256}}.
    """
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["base_commit"] != BASE:
        raise ValueError("Wrong frozen result base")
    files = manifest["files"]
    required = {
        "research/kim_multidnn_expansion/ac_closure.py",
        "research/kim_case_b_freeze/input.json",
        "research/kim_safety_repair_audit/design.py",
        "research/kim_safety_repair_audit/design.json",
        "research/kim_safety_repair_audit/raw/new/results.json",
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
    if not required <= files.keys():
        raise ValueError(f"Missing frozen dependencies: {sorted(required - files.keys())}")
    for name, expected in files.items():
        target = (ROOT / name).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError("Manifest path escapes workspace")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen file drift: {name}")
    manifest_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = json.loads((HERE / "freeze_receipt.json").read_text(encoding="utf-8"))
    if receipt["commit"] != freeze or receipt["manifest_sha256"] != manifest_sha:
        raise ValueError("Remote preregistration receipt does not match invocation/manifest")
    return dict(manifest_sha256=manifest_sha, verified_files=len(files))


def pick_independent(candidates):
    floor = min(x["predicted_j"] for x in candidates)
    return min((x for x in candidates if x["predicted_j"] <= floor + EPS),
               key=lambda x: (x["deployment"], x["code"]))


def same_historical_choice(choice, physical, historical):
    old = historical["independent"]
    if old is None or (choice["deployment"], choice["code"], choice["opps"]) != (
            old["deployment"], old["code"], old["opps"]):
        raise AssertionError("Independent choice differs from frozen result")
    old_physical = old["physical"]
    if (abs(choice["predicted_j"] - old["predicted_j"]) > REPLAY_TOL or
            abs(physical["energy_j"] - old_physical["energy_j"]) > REPLAY_TOL or
            physical["thermal_status"] != old_physical["thermal_status"] or
            physical["completed"] != old_physical["completed"] or
            not physical["deadline_ok"]):
        raise AssertionError("Independent replay differs from frozen result")
    return {"status": "MATCH", "energy_error_j": physical["energy_j"] - old_physical["energy_j"]}


def run_case(case, historical, output):
    started = perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    mark = perf_counter()
    scenes = design.make_scenes(case)
    schedules = {d: [[time_scene(PLATFORM, scene, d, opp) for opp in OPPS]
                     for scene in scenes] for d in DEPLOYMENTS}
    schedule_s = perf_counter() - mark
    if sum(len(s.requests) for s in scenes) != 500:
        raise AssertionError("Expected the unchanged 500-request workload")
    local_rows, choices, bests, coverage, timing = [], [], [], [], []
    for deployment in DEPLOYMENTS:
        mark = perf_counter()
        tables = []
        for phase in schedules[deployment]:
            table = []
            for opp, schedule in zip(OPPS, phase, strict=True):
                kw = thermal_kwargs(PLATFORM, opp, case["ambient"], True, "base")
                table.append(compile_scene(schedule.duration_ns * 1e-9, schedule.active_w,
                                           schedule.transfer_w, kw)
                             if schedule.deadline_feasible else None)
            tables.append(table)
        compile_s = perf_counter() - mark
        kernels = [k for phase in tables for k in phase if k is not None]
        # Every compile performs one full segment integral, followed by one
        # original integral per envelope block.  These are not full sequences.
        compile_integrations = sum(1 + len(k.upper) for k in kernels)
        before = (sum(k.screen_calls for k in kernels), sum(k.fallback_calls for k in kernels))
        mark = perf_counter()
        independent, _, rows = joint.local_selection(tables, schedules[deployment], case["ambient"], deployment)
        independent_s = perf_counter() - mark
        middle = (sum(k.screen_calls for k in kernels), sum(k.fallback_calls for k in kernels))
        local_rows.extend(rows)
        if independent is not None:
            choices.append(dict(deployment=deployment, **independent))
        mark = perf_counter()
        _, states, energies, depths = joint.joint_search(tables)
        search_s = perf_counter() - mark
        after = (sum(k.screen_calls for k in kernels), sum(k.fallback_calls for k in kernels))
        counts = np.bincount(states, minlength=4)
        grid = np.array([[s.deadline_feasible for s in phase] for phase in schedules[deployment]])
        expected_deadline_mask = (grid[0, :, None, None, None] & grid[1, None, :, None, None]
                                 & grid[2, None, None, :, None] & grid[3, None, None, None, :]).ravel()
        if (len(states) != N ** 4 or int(counts.sum()) != N ** 4 or
                not np.array_equal(states != 0, expected_deadline_mask) or
                not np.array_equal(np.isfinite(energies), expected_deadline_mask) or
                sum(depths) != after[0] - middle[0]):
            raise AssertionError("Incomplete finite-domain classification or evaluation counts")
        safe = np.flatnonzero(states == 1)
        if len(safe):
            # Report the actual array minimum, not the 1e-9 J tie representative.
            code = int(safe[np.argmin(energies[safe])])
            bests.append(dict(deployment=deployment, code=code, opps=joint.decode(code),
                              predicted_j=float(energies[code])))
        coverage.append(dict(
            deployment=deployment, logical_complete_sequences=N ** 4,
            deadline_failed=int(counts[0]), safe=int(counts[1]), overtemp=int(counts[2]),
            unresolved=int(counts[3]), deadline_legal_sequences=int(sum(counts[1:])),
            deadline_legal_prefixes=depths, compiled_scene_actions=len(kernels),
            compile_original_integrations=compile_integrations,
            independent_screen_entries=middle[0] - before[0],
            independent_fallback_segment_integrations=middle[1] - before[1],
            search_prefix_thermal_evaluations=after[0] - middle[0],
            search_fallback_segment_integrations=after[1] - middle[1],
            finite_array_sha256=hashlib.sha256(states.tobytes() + energies.tobytes()).hexdigest()))
        mark = perf_counter()
        np.savez_compressed(output / f"space_{deployment}.npz", status=states, energy_j=energies)
        timing.append(dict(deployment=deployment, compile_s=compile_s,
                           independent_selection_s=independent_s, joint_search_s=search_s,
                           archive_write_s=perf_counter() - mark))
        put_json(output / f"coverage_{deployment}.json", dict(
            coverage=coverage[-1], timing=timing[-1],
            best_safe=next((x for x in bests if x["deployment"] == deployment), None)))
    if not choices or not bests:
        raise AssertionError("An originally safe case lost its feasible baseline")
    independent = pick_independent(choices)
    optimum = min(bests, key=lambda x: (x["predicted_j"], x["deployment"], x["code"]))
    mark = perf_counter()
    independent_physical = replay_sequence(PLATFORM, scenes, independent["deployment"],
                                           independent["opps"], case["ambient"])
    independent_replay_s = perf_counter() - mark
    historical_check = same_historical_choice(independent, independent_physical, historical)
    mark = perf_counter()
    optimum_physical = replay_sequence(PLATFORM, scenes, optimum["deployment"],
                                       optimum["opps"], case["ambient"])
    optimum_replay_s = perf_counter() - mark
    for p in (independent_physical, optimum_physical):
        if not p["feasible"] or not p["deadline_ok"] or p["completed"] != 500:
            raise AssertionError("A reported safe solution failed original physical replay")
    if abs(optimum_physical["energy_j"] - optimum["predicted_j"]) > REPLAY_TOL:
        raise AssertionError("Exact array energy does not match physical replay")
    unresolved = sum(row["unresolved"] for row in coverage)
    gap_j = independent_physical["energy_j"] - optimum["predicted_j"]
    if gap_j < -REPLAY_TOL:
        raise AssertionError("Independent feasible policy falls below exhaustive reference")
    numerical_gap_j = gap_j
    if abs(gap_j) <= REPLAY_TOL:
        gap_j = 0.0
    result = dict(
        case=case, baseline_commit=BASE, independent=dict(**independent, physical=independent_physical),
        optimum=dict(**optimum, physical=optimum_physical) if unresolved == 0 else None,
        best_safe_found=dict(**optimum, physical=optimum_physical),
        historical_independent_check=historical_check,
        minimum_safe_array_energy_j=optimum["predicted_j"],
        relative_gap=(gap_j / optimum["predicted_j"]) if unresolved == 0 else None,
        relative_gap_percent=100 * gap_j / optimum["predicted_j"] if unresolved == 0 else None,
        gap_j=gap_j if unresolved == 0 else None,
        gap_to_best_safe_found_j=gap_j, unrounded_numeric_gap_j=numerical_gap_j,
        optimality_proven=(unresolved == 0), unresolved_sequences=unresolved,
        optimality_status="CERTIFIED_FINITE_DOMAIN_MINIMUM" if unresolved == 0 else "BEST_SAFE_FOUND_UNRESOLVED",
        scope="A/C resident mappings, all 27^4 scene OPP sequences, frozen deterministic event policy",
        proof_scope_note="Not an optimum over arbitrary continuous schedules, new mappings or physical hardware.",
        logical_complete_sequences=2 * N ** 4, coverage=coverage,
        full_sequence_replays=2, full_sequence_replay_segment_integrations=8,
        timing=dict(scheduling_s=schedule_s, by_deployment=timing,
                    independent_full_replay_s=independent_replay_s,
                    optimum_full_replay_s=optimum_replay_s,
                    search_with_compile_s=sum(t["compile_s"] + t["joint_search_s"] for t in timing),
                    total_to_result_s=perf_counter() - started))
    put_csv(output / "local.csv", local_rows)
    put_json(output / "result.json", result)
    print(f"{case['id']}: independent={independent_physical['energy_j']:.12f} J; "
          f"reference={optimum['predicted_j']:.12f} J; gap={result['relative_gap_percent']}%; "
          f"proven={result['optimality_proven']}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True, help="Verified remote preregistration commit SHA")
    parser.add_argument("--manifest", type=Path, default=HERE / "freeze_manifest.json")
    parser.add_argument("--output", type=Path, default=HERE / "raw" / "ac_closure")
    parser.add_argument("--case", choices=CASE_IDS, help="Internal single-case worker")
    args = parser.parse_args()
    if len(args.freeze) != 40 or any(ch not in "0123456789abcdef" for ch in args.freeze):
        raise ValueError("Expected full preregistration commit SHA")
    manifest_before = check_manifest(args.manifest, args.freeze)
    started = perf_counter()
    historical = {r["case"]["id"]: r for r in json.loads((AUDIT / "raw" / "new" / "results.json").read_text(encoding="utf-8"))}
    cases = {case["id"]: case for case in design.cases()}
    if args.case:
        run_case(cases[args.case], historical[args.case], args.output)
        if check_manifest(args.manifest, args.freeze) != manifest_before:
            raise AssertionError("Manifest changed while executing")
        return
    args.output.mkdir(parents=True, exist_ok=False)
    records, workers = [], []
    for cid in CASE_IDS:
        command = [sys.executable, str(Path(__file__).resolve()), "--freeze", args.freeze,
                   "--manifest", str(args.manifest.resolve()), "--case", cid,
                   "--output", str((args.output / cid).resolve())]
        mark = perf_counter()
        with (args.output / f"{cid}.log").open("w", encoding="utf-8") as log:
            try:
                run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=False)
                status = "COMPLETED" if run.returncode == 0 else "ERROR"
                returncode = run.returncode
            except subprocess.TimeoutExpired:
                status, returncode = "TIMEOUT", None
        worker = dict(case=cid, status=status, returncode=returncode, process_cap_s=120,
                      process_elapsed_s=perf_counter() - mark)
        workers.append(worker)
        put_json(args.output / "workers.json", workers)
        if status == "COMPLETED":
            records.append(json.loads((args.output / cid / "result.json").read_text(encoding="utf-8")))
        elif status == "TIMEOUT":
            # Completed deployment arrays remain available.  The whole condition
            # is explicitly unresolved; a partial file is never an optimum proof.
            print(f"{cid}: TIMEOUT at 120 s; no complete-domain optimum claimed", flush=True)
        else:
            raise RuntimeError(f"Technical failure in {cid}; inspect its log; no retry")
    manifest_after = check_manifest(args.manifest, args.freeze)
    if manifest_after != manifest_before:
        raise AssertionError("Manifest changed while executing")
    summary = []
    for result in records:
        c = result["coverage"]
        summary.append(dict(
            case=result["case"]["id"], independent_continuous_j=result["independent"]["physical"]["energy_j"],
            optimal_safe_j=result["minimum_safe_array_energy_j"] if result["optimality_proven"] else None,
            best_safe_found_j=result["minimum_safe_array_energy_j"], gap_j=result["gap_j"],
            unrounded_numeric_gap_j=result["unrounded_numeric_gap_j"], gap_zero_tolerance_j=REPLAY_TOL,
            gap_percent=result["relative_gap_percent"], best_safe_deployment=result["best_safe_found"]["deployment"],
            best_safe_opps="/".join(result["best_safe_found"]["opps"]), optimality_proven=result["optimality_proven"],
            optimality_status=result["optimality_status"],
            logical_complete_sequences=result["logical_complete_sequences"],
            deadline_legal_sequences=sum(r["deadline_legal_sequences"] for r in c),
            safe_sequences=sum(r["safe"] for r in c), unresolved_sequences=result["unresolved_sequences"],
            prefix_thermal_evaluations=sum(r["search_prefix_thermal_evaluations"] for r in c),
            compile_original_integrations=sum(r["compile_original_integrations"] for r in c),
            independent_screen_entries=sum(r["independent_screen_entries"] for r in c),
            fallback_segment_integrations=sum(r["search_fallback_segment_integrations"] +
                                               r["independent_fallback_segment_integrations"] for r in c),
            full_sequence_replays=result["full_sequence_replays"],
            search_with_compile_s=result["timing"]["search_with_compile_s"],
            joint_search_s=sum(t["joint_search_s"] for t in result["timing"]["by_deployment"]),
            total_s=result["timing"]["total_to_result_s"]))
    if summary:
        put_csv(args.output / "summary.csv", summary)
    put_json(args.output / "summary.json", dict(
        preregistration_commit=args.freeze, baseline_commit=BASE, cases=summary, workers=workers,
        complete_cases=len(records), requested_cases=len(CASE_IDS),
        manifest=manifest_before, total_batch_s=perf_counter() - started,
        environment=dict(python=sys.version, numpy=np.__version__, platform=host.platform(), threads=1),
        timing_note="Single run, perf_counter seconds. First lazy JIT is charged to the phase that triggers it and total; no free warmup.",
        conclusion_policy="Close A/C validation regardless of gap; do not seek repair gains or tune environment."))


if __name__ == "__main__":
    main()
