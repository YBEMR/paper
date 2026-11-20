"""Extract figures 3-4 to 3-6 from archived arrays, without evaluating a model.

Usage: python energy_pressure_data.py path/to/research
The directory must contain kim_multidnn_expansion, kim_scene_dvfs_admission,
kim_synthetic_platform_v1 and kim_pressure_feasibility from b818777.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from figure_style import DATA

CASE_25 = ("forward_flat_25C", "forward_alternating_25C", "reverse_flat_25C",
           "reverse_alternating_25C")
DEPLOYMENTS = ("A", "C", "D001", "D015")
METHODS = ("Max-Freq", "Static-DVFS", "Joint")
STATE_NAMES = ("deadline_failed", "safe", "overtemp", "unresolved")
CODE_COUNT = 27 ** 4
STATIC = np.arange(27) * (27 ** 3 + 27 ** 2 + 27 + 1)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(name, rows):
    with (DATA / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def get_minima(deployment, path):
    with np.load(path, allow_pickle=False) as archive:
        state, energy = archive["status"], archive["energy_j"]
        assert state.shape == energy.shape == (CODE_COUNT,)
        assert np.all(state < len(STATE_NAMES))
        subsets = ([CODE_COUNT - 1], STATIC, slice(None))
        result = {}
        for method, subset in zip(METHODS, subsets):
            sub_status, sub_energy = state[subset], energy[subset]
            counts = np.bincount(sub_status, minlength=4)
            safe = sub_status == 1
            best = None
            if np.any(safe):
                safe_idx = np.flatnonzero(safe)
                assert np.isfinite(sub_energy[safe_idx]).all()
                index = int(safe_idx[np.argmin(sub_energy[safe_idx])])
                code = index if method == "Joint" else int(subset[index])
                best = (float(sub_energy[index]), deployment, code)
            result[method] = (counts, best)
        return result


def benchmark(case_id, domain, deployments):
    out = []
    for method in METHODS:
        minima = [v[method][1] for v in deployments if v[method][1] is not None]
        counts = np.sum([v[method][0] for v in deployments], axis=0)
        if minima:
            energy, _, _ = min(minima)
            tied = sorted((dep, code) for value, dep, code in minima
                          if abs(value - energy) <= 1e-10)
        else:
            energy, tied = None, []
        out.append(dict(case_id=case_id, domain=domain, deployments=len(deployments),
                        method=method, number_of_codes=int(counts.sum()),
                        **dict(zip(STATE_NAMES, map(int, counts))),
                        minimum_safe_energy_j=energy,
                        winners_at_1e_minus_10_j="|".join(f"{d}:{c}" for d,c in tied)))
    for row in out:
        current, joint = row["minimum_safe_energy_j"], out[-1]["minimum_safe_energy_j"]
        row["joint_saving_pct_vs_row"] = (100 * (current - joint) / current
                                          if current is not None and joint is not None else None)
    return out


def collect_normal(research):
    expanded = research / "kim_multidnn_expansion/raw/expanded"
    rows, false_admissions = [], []
    for case, expected_count in zip(CASE_25, (15, 33, 81, 67)):
        paths = {p.stem[6:]: p for p in (expanded / case).glob("space_*.npz")}
        assert len(paths) == expected_count
        selected = paths if case == "reverse_flat_25C" else {d: paths[d] for d in DEPLOYMENTS}
        units = {d: get_minima(d, p) for d, p in selected.items()}
        if case == "reverse_flat_25C":
            rows.extend(benchmark(case, "full81", list(units.values())))
        rows.extend(benchmark(case, "common4", [units[d] for d in DEPLOYMENTS]))

    admission = research / "kim_scene_dvfs_admission"
    originals = {d: get_minima(d,admission / f"raw/space_25_{d}.npz") for d in ("A","C")}
    rows.extend(benchmark("forward_flat_25C", "original_AC", list(originals.values())))
    for row in read_json(admission / "raw/comparison_sets.json"):
        if row["ambient"] != 25:
            continue
        dep = row["deployment"]
        counts = originals[dep]["Joint"][0]
        assert row["both_feasible"] + row["reset_only"] == row["reset_feasible"]
        assert row["both_feasible"] == counts[1] and row["reset_only"] == counts[2]
        assert row["continuous_only"] == counts[3] == 0
        false_admissions.append(dict(case_id="forward_flat_25C", deployment=dep,
            reset_accepted=row["reset_feasible"], both_safe=row["both_feasible"],
            reset_false_accepted=row["reset_only"], continuous_only=row["continuous_only"],
            false_accepted_pct=100 * row["reset_only"]/row["reset_feasible"]))
    assert sum(r["reset_accepted"] for r in false_admissions) == 118098
    write_csv("fig03_false_admissions",false_admissions)

    with (research / "kim_synthetic_platform_v1/raw/candidates.csv").open() as file:
        candidates = [r for r in csv.DictReader(file)
                      if r["case_id"] == "10s_25fps_25C_on_base" and r["mode"]=="continuous"]
    assert len(candidates)==54
    safe = [r for r in candidates if r["deadline_ok"]=="True" and r["thermal_status"]=="SAFE"]
    assert len(safe)==15
    def peak(row):
        return max(float(row["peak_" + node + "_c"]) for node in ("cpu","gpu","dla0","dla1"))
    coldest = min(safe, key=peak)
    assert coldest == min(safe, key=lambda r:float(r["energy_j"]))
    write_csv("fig03_static_min_peak", [dict(case_id="forward_flat_25C", domain="original_AC_static",
        total_static=54, safe_static=len(safe), deployment=coldest["deployment"],
        constant_opp=coldest["opp"], peak_upper_c=peak(coldest), energy_j=coldest["energy_j"])])
    return rows


def collect_pressure(research):
    root = research / "kim_pressure_feasibility"
    audit = read_json(root / "audit_27p5/audit.json")
    audited = {(u["case_id"],u["deployment"]):u for u in audit["units"]}
    cases = read_json(root / "manifest.json")["case_order"]
    units, classes, margins, baselines = {}, [], [], []
    for folder in sorted((root / "raw_execution").glob("[0-9][0-9]")):
        record = read_json(folder / "result.json")
        case, dep = record["case_id"], record["deployment"]
        certified = audited[case,dep]
        data = get_minima(dep, folder / "space.npz")
        units[case,dep] = data
        counts, best = data["Joint"]
        values = dict(zip(STATE_NAMES,map(int,counts)))
        assert values == record["counts"] == certified["counts"]
        classes.append(dict(case_id=case, deployment=dep, all_codes=CODE_COUNT,
                            deadline_legal=CODE_COUNT-values["deadline_failed"], **values))
        if best is None:
            assert certified["certificate"]=="NO_SAFE"
            continue
        energy, _, code = best
        assert code == certified["selected_code"] == record["selection"]["code"]
        assert energy == certified["minimum_safe_j"]
        assert certified["certificate"]=="MIN_SAFE"
        physical = record["physical"]
        peak = max(physical["peak_upper_c"])
        requests = read_json(folder / "requests.json")
        assert len(requests) == 500
        slack = min(r["slack_ns"] for r in requests) / 1e6
        assert abs(peak-certified["peak_upper_c"]) < 1e-9
        assert abs(slack-certified["min_slack_ms"]) < 1e-9
        margins.append(dict(case_id=case, deployment=dep, selected_code=code,
                            sequence="/".join(record["selection"]["opps"]),
                            minimum_safe_energy_j=energy, peak_upper_c=peak,
                            thermal_margin_c=80-peak, min_deadline_slack_ms=slack))
    for case in cases:
        baselines.extend(benchmark(case,"common4",[units[case,d] for d in DEPLOYMENTS]))
    assert len(classes)==12 and len(margins)==6
    write_csv("fig05_classes",sorted(classes,key=lambda r:(cases.index(r["case_id"]),r["deployment"])))
    write_csv("fig05_margins",sorted(margins,key=lambda r:(cases.index(r["case_id"]),r["deployment"])))
    return baselines


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research",type=Path)
    args=parser.parse_args()
    DATA.mkdir(exist_ok=True)
    write_csv("fig03_energy_domains",collect_normal(args.research)+collect_pressure(args.research))
