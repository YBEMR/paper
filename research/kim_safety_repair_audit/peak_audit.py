"""Re-integrate the 25 C reset-safe/continuous-overtemp policies from the frozen archive.

Each exact scene prefix is integrated once from its actual inherited temperatures.
Outputs contain per-node peak enclosures, first confirmed violating scene, and
global maximum excess above the common 80 C limit. No new workload is searched.
"""
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import sys
from time import perf_counter

for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np

HERE = Path(__file__).resolve().parent
JOINT = Path(os.environ.get("KIM_JOINT_INPUT", HERE.parent / "kim_scene_dvfs_admission")).resolve()
sys.path.insert(0, str(JOINT))
from scene_events import (OPPS, PLATFORM, evaluate_thermal, replay_sequence, split_workload,
                          thermal_kwargs, time_scene)

NODES = ("cpu", "gpu", "dla0", "dla1")
LIMIT = np.asarray(PLATFORM["thermal"]["limits_C"])
EXPECTED = {
    "local.csv": "0e307b74f0f173952674af20477af22c230d27902546083376f8e1f868c1c2a7",
    "space_25_A.npz": "bb3b6d48a48c1d6992aeb80cfbfa1827712ad86dd93b840dbaf90769f3133b81",
    "space_25_C.npz": "6e7155ea1a75f529dc37f9d3b50e8e1cf5bb99edc50e248918142792cd5c6726",
}


@dataclass(frozen=True)
class Step:
    energy: float
    final: np.ndarray
    low: np.ndarray
    high: np.ndarray
    status: str


def false_accepts(rows, deployment):
    local = np.zeros((4, len(OPPS)), dtype=bool)
    for r in rows:
        if r["ambient"] == "25" and r["deployment"] == deployment:
            local[int(r["scene"]), OPPS.index(r["opp"])] = int(r["status"]) == 1
    with np.load(JOINT / "raw" / f"space_25_{deployment}.npz", allow_pickle=False) as file:
        idx = np.flatnonzero(file["status"] == 2)
        energies = file["energy_j"][idx]
    digits = np.array(np.unravel_index(idx, (27,)*4)).T
    keep = local[np.arange(4), digits].all(axis=1)
    return zip(idx[keep], digits[keep], energies[keep])


def replay_deployment(scenes, rows, deployment):
    initial = np.asarray(PLATFORM["thermal"]["initial_C"])

    @lru_cache(maxsize=None)
    def events(scene, level):
        s = time_scene(PLATFORM, scenes[scene], deployment, OPPS[level])
        if not s.deadline_feasible:
            raise ValueError("A false-safe thermal candidate must meet every deadline")
        return s.duration_ns * 1e-9, s.active_w, s.transfer_w

    @lru_cache(maxsize=None)
    def prefix(levels):
        scene, level = len(levels)-1, levels[-1]
        entry = prefix(levels[:-1]).final if scene else initial
        dt, active, transfer = events(scene, level)
        kw = thermal_kwargs(PLATFORM, OPPS[level], 25, True, "base")
        result = evaluate_thermal(dt, active, transfer_W=transfer, **dict(kw, initial_C=entry))
        return Step(result["energy_J"], np.asarray(result["final_C"]),
                    np.asarray(result["peak_lower_C"]), np.asarray(result["peak_upper_C"]),
                    result["thermal_status"])

    output = []
    start = perf_counter()
    for idx, digits, stored_energy in false_accepts(rows, deployment):
        levels = tuple(map(int, digits))
        steps = [prefix(levels[:j]) for j in range(1,5)]
        low = np.stack([s.low for s in steps])
        high = np.stack([s.high for s in steps])
        violations = np.flatnonzero(np.any(low > LIMIT, axis=1))
        if len(violations) == 0 or np.any(high < low):
            raise ValueError(f"Missing violating lower bound on {deployment}/{idx}")
        first = int(violations[0])
        if any(s.status != "SAFE" for s in steps[:first]) or steps[first].status != "VIOLATION":
            raise ValueError("No definitive first violating scene")
        lower, upper = low.max(axis=0), high.max(axis=0)
        excess_lo = float(np.max(lower-LIMIT))
        excess_hi = float(np.max(upper-LIMIT))
        # Include all bracket-consistent scene/node locations in case of a tie.
        peak_pairs = np.argwhere(high-LIMIT >= excess_lo)
        j = sum(s.energy for s in steps)
        err = abs(j-stored_energy)
        if err > 1e-7:
            raise ValueError(f"Frozen continuous energy mismatch: {deployment}/{idx} {err}")
        record = dict(deployment=deployment, code=int(idx), opps=" ".join(OPPS[i] for i in levels),
                      continuous_energy_j=j, abs_energy_diff_archive_j=float(err),
                      first_violation_scene=scenes[first].name,
                      confirmed_nodes_in_first_scene="|".join(n for k,n in enumerate(NODES)
                                                             if low[first,k] > LIMIT[k]),
                      peak_excess_lo_c=excess_lo, peak_excess_hi_c=excess_hi,
                      possible_max_scene_node="|".join(f"{scenes[i].name}/{NODES[k]}" for i,k in peak_pairs))
        for k,n in enumerate(NODES):
            record[f"peak_{n}_lo_c"] = float(lower[k])
            record[f"peak_{n}_hi_c"] = float(upper[k])
        output.append(record)
    if not output:
        raise ValueError("No original false accepts")
    elapsed = perf_counter()-start
    summary = dict(full_sequences=len(output), shared_prefix_segment_integrations=prefix.cache_info().misses,
                   distinct_scene_event_schedules=events.cache_info().misses, wall_seconds=elapsed,
                   first_scene_counts=dict(Counter(r["first_violation_scene"] for r in output)),
                   first_scene_node_sets=dict(Counter(r["confirmed_nodes_in_first_scene"] for r in output)),
                   possible_peak_locations=dict(Counter(r["possible_max_scene_node"] for r in output)),
                   min_peak_excess_lower_c=min(r["peak_excess_lo_c"] for r in output),
                   max_peak_excess_upper_c=max(r["peak_excess_hi_c"] for r in output),
                   max_abs_energy_difference_archive_j=max(r["abs_energy_diff_archive_j"] for r in output),
                   maximum_excess_enclosure_width_c=max(r["peak_excess_hi_c"]-r["peak_excess_lo_c"]
                                                        for r in output))
    start = perf_counter()
    for r in (output[0], output[-1]):
        complete = replay_sequence(PLATFORM, scenes, deployment, r["opps"].split(), 25)
        if (complete["thermal_status"] != "VIOLATION" or complete["completed"] != 500
            or abs(complete["energy_j"]-r["continuous_energy_j"]) > 1e-7):
            raise ValueError("Independent uncached replay differs")
        for key, fields in (("peak_lower_c", "lo"), ("peak_upper_c", "hi")):
            archived = [r[f"peak_{n}_{fields}_c"] for n in NODES]
            np.testing.assert_allclose(complete[key], archived, rtol=0., atol=1e-8)
    summary.update(uncached_full_replay_spot_checks=2, spot_check_wall_seconds=perf_counter()-start)
    prefix.cache_clear()
    events.cache_clear()
    return output, summary


def main(raw):
    for name, expected in EXPECTED.items():
        if hashlib.sha256((JOINT/"raw"/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Input differs from 2d352e71: {name}")
    with (JOINT/"raw"/"local.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    conditions = split_workload("10s", 25)
    if not np.array_equal(LIMIT, [80]*4) or sum(len(s.requests) for s in conditions) != 500:
        raise ValueError("Frozen platform/workload mismatch")
    all_rows, stats = [], {}
    for d, expected in (("A",2742), ("C",1965)):
        records, stats[d] = replay_deployment(conditions, rows, d)
        if len(records) != expected:
            raise ValueError(f"False-safe count differs for {d}")
        all_rows.extend(records)
    raw.mkdir(parents=True, exist_ok=True)
    with (raw/"historical_peaks.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)
    summary = dict(frozen_input="2d352e715463641d6e49e4691d4b16fb02296c80",
                   input_sha256=EXPECTED, full_sequences=len(all_rows),
                   count_definition="One full waveform per target policy. Exact shared prefixes re-used; extra uncached spot checks counted separately.",
                   results=stats)
    (raw/"historical_peaks_summary.json").write_bytes(
        (json.dumps(summary, indent=2, ensure_ascii=False)+"\n").encode("utf-8"))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=HERE/"raw")
    main(parser.parse_args().raw)
