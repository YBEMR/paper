"""Evaluate the committed design. No parameter fitting and no adaptive case selection."""
import argparse
import csv
import hashlib
import json
import platform as os_platform
import subprocess
import sys
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import numpy as np

from archive import Ledger
from events import RESOURCES, simulate
from profiles import build_chains, thermal_kwargs
from thermal import evaluate_thermal
from workloads import CONFIG, FROZEN, HERE, conditions, request_hash, workload

NODES = ("cpu", "gpu", "dla0", "dla1")


def check_freeze(sha):
    manifest = json.loads((HERE / "freeze_manifest.json").read_text(encoding="utf8"))
    git = ["git", "-C", str(HERE)]
    if len(sha) != 40 or subprocess.check_output(git + ["rev-parse", sha+"^"], text=True).strip() != CONFIG["parent"]:
        raise ValueError("Specify the full preregistration commit, directly based on the frozen input")
    blob = subprocess.check_output(git + ["show", f"{sha}:research/{HERE.name}/freeze_manifest.json"])
    if json.loads(blob) != manifest:
        raise ValueError("Freeze manifest differs from preregistered commit")
    for name, expected in manifest["sha256_lf"].items():
        # The repo has Windows checkouts. Normalize only CRLF to LF.
        actual = (HERE / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(actual).hexdigest() != expected:
            raise ValueError(f"Frozen source changed: {name}")


def dump_csv(path, rows):
    if not rows:
        raise ValueError(f"No data for {path}")
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compile_timeline(p, window, fps, d, opp):
    requests, switches, end = workload(window, fps)
    chains = build_chains(p, FROZEN, d, opp)
    schedule = simulate(requests, chains, end, [t for t, _ in switches])
    resets = [int(np.searchsorted(schedule.start_ns, t)) for t, _ in switches[1:]]
    if any(schedule.start_ns[k] != t for k, (t, s) in zip(resets, switches[1:])):
        raise ArithmeticError("Event grid failed to align with a scene change")
    return requests, schedule, resets


def evaluate(p, case, d, opp, schedule, resets, mode, trace=False):
    args = thermal_kwargs(p, opp, case["ambient_c"], case["leakage"]=="on", case["variation"])
    return evaluate_thermal(schedule.duration_ns * 1e-9, schedule.active_w, **args,
                            reset_indices=resets if mode == "independent" else (),
                            transfer_W=schedule.transfer_w, trace=trace)


def pack(case, d, opp, mode, s, h, digest):
    row = dict(**case, deployment=d, opp=opp, mode=mode,
               sched_id=f"{case['window']}_{case['fps']}_{d}_{opp}",
               request_sha256=digest, energy_j=h["energy_J"], window_s=s.window_ns/1e9,
               deadline_ok=s.deadline_feasible, thermal_ok=h["thermal_status"]=="SAFE",
               thermal_status=h["thermal_status"], required=len(s.requests),
               completed=len(s.requests)-len(s.unfinished_ids), final_completed=len(s.completions_ns),
               late_count=len(s.late_ids), max_response_ms=s.max_response_ns/1e6,
               min_slack_ms=s.min_slack_ns/1e6, last_finish_s=s.last_completion_ns/1e9,
               stages_touching_after_window=s.stages_touching_after_window,
               common_j=h["common_J"], transfer_j=h["transfer_J"])
    for i, n in enumerate(NODES):
        for prefix, field, suffix in (("peak","peak_upper_C","c"),("peak_lo","peak_lower_C","c"),
                                       ("final","final_C","c"),("activity","activity_J","j"),
                                       ("idle","idle_J","j"),("leakage","leakage_J","j")):
            row[f"{prefix}_{n}_{suffix}"] = h[field][i]
    for r in RESOURCES:
        row[f"busy_{r.lower()}_s"] = s.busy_ns[r]/1e9
        row[f"idle_{r.lower()}_s"] = s.idle_ns[r]/1e9
    return row


def fixed_regression(p):
    cases = [c for c in conditions() if (c["window"],c["fps"],c["ambient_c"],c["leakage"])
             == ("short",25,25,"on")]
    case, = cases
    records = []
    for d in ("A", "C"):
        jobs, s, resets = compile_timeline(p, "short", 25, d, CONFIG["fixed_check"])
        if len(jobs)!=8 or s.window_ns!=200_000_000 or len(resets)!=3:
            raise AssertionError("Short-window regression failed")
        digest = request_hash(jobs)
        for mode in ("independent", "continuous"):
            h = evaluate(p, case, d, "HHH", s, resets, mode)
            parts = h["common_J"]+h["transfer_J"]+sum(sum(h[key]) for key in ("idle_J","activity_J","leakage_J"))
            if abs(parts-h["energy_J"])>1e-10 or len(s.completions_ns)!=8:
                raise AssertionError("Fixed-frequency accounting failed")
            records.append(pack(case, d, "HHH", mode, s, h, digest))
    return records


def trace_sample(result):
    # Visualization samples are physical event endpoints. Also retain observed
    # extrema, both sides of every reset, and the first/last endpoint.
    times, temps = result["trace_time_s"], result["trace_C"]
    target = np.arange(0, times[-1], .05)
    indices = set(np.minimum(np.searchsorted(times, target),len(times)-1).tolist())
    indices.update((0,len(times)-1))
    indices.update(np.argmax(temps, axis=0).tolist())
    jumps = np.flatnonzero(np.diff(times)==0)
    indices.update(jumps.tolist())
    indices.update((jumps+1).tolist())
    for k in sorted(indices):
        yield {"t_s":times[k], **{n+"_c":temps[k,j] for j,n in enumerate(NODES)}}


def run(freeze, raw):
    check_freeze(freeze)
    raw.mkdir(exist_ok=True, parents=True)
    p = json.loads((HERE / "platform.json").read_text(encoding="utf8"))
    fixed = fixed_regression(p)
    dump_csv(raw / "fixed_HHH.csv", fixed)
    print("Fixed-frequency checks finished; starting preregistered enumeration.", flush=True)
    groups = defaultdict(list)
    for c in conditions():
        groups[c["window"], c["fps"]].append(c)
    candidates, traces, ledger = [], [], Ledger()
    for (window, fps), group in groups.items():
        for d in ("A", "C"):
            for levels in FROZEN["clock_policy"]["constant_opp_levels"]:
                opp = "".join(levels)
                jobs, s, resets = compile_timeline(p, window, fps, d, opp)
                ledger.add(f"{window}_{fps}_{d}_{opp}", jobs, s)
                digest = request_hash(jobs)
                for case in group:
                    want_trace = ((window,fps,opp,case["variation"],case["leakage"])
                                  == ("10s",25,"HHH","base","on"))
                    for mode in ("independent","continuous"):
                        h = evaluate(p, case, d, opp, s, resets, mode, want_trace)
                        candidates.append(pack(case, d, opp, mode, s, h, digest))
                        if want_trace:
                            traces.extend(dict(case_id=case["case_id"], deployment=d, opp=opp,
                                               mode=mode, **t) for t in trace_sample(h))
        print(f"Saved in memory: {window} / {fps} FPS", flush=True)
    ledger.save(raw)
    dump_csv(raw / "candidates.csv", candidates)
    dump_csv(raw / "traces.csv", traces)
    all_fixed = {(r["case_id"],r["deployment"],r["opp"],r["mode"]):r for r in candidates}
    if any(all_fixed[r["case_id"],r["deployment"],r["opp"],r["mode"]] != r for r in fixed):
        raise AssertionError("Fixed-frequency regression differs from enumeration")
    metadata = dict(freeze_commit=freeze, parent=CONFIG["parent"], seed=None,
                    candidate_rows=len(candidates), timing_schedules=2*27*len(groups),
                    conditions=len(list(conditions())), python=sys.version.split()[0],
                    system=os_platform.platform(), packages={n:version(n) for n in ("numpy","numba","scipy","matplotlib")})
    (raw / "run.json").write_text(json.dumps(metadata, indent=2)+"\n",encoding="utf8")


def replay(freeze, raw, decisions):
    """Rebuild schedules and re-integrate both selected policies on continuous physics."""
    check_freeze(freeze)
    p = json.loads((HERE/"platform.json").read_text(encoding="utf8"))
    cases = {c["case_id"]: c for c in conditions()}
    rows = []
    with decisions.open(encoding="utf8") as f:
        for decision in csv.DictReader(f):
            case = cases[decision["case_id"]]
            for prefix in ("ind","cont"):
                d, opp = decision[prefix+"_deployment"], decision[prefix+"_opp"]
                if not d:
                    continue
                jobs,s,resets = compile_timeline(p,case["window"],case["fps"],d,opp)
                h = evaluate(p,case,d,opp,s,resets,"continuous")
                row = pack(case,d,opp,"continuous",s,h,request_hash(jobs))
                if abs(row["energy_j"]-float(decision[prefix+"_physical_j"]))>1e-9:
                    raise AssertionError("Continuous replay energy mismatch")
                if h["thermal_status"] != decision[prefix+"_physical_thermal_status"]:
                    raise AssertionError("Continuous replay temperature mismatch")
                rows.append({"selector":prefix,**row})
    if rows:
        dump_csv(raw/"physical_replays.csv",rows)
    else:
        (raw/"physical_replays.csv").write_text("selector,case_id\n",encoding="utf8")


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--raw", type=Path, default=HERE/"raw")
    parser.add_argument("--replay-decisions", type=Path)
    args = parser.parse_args()
    if args.replay_decisions:
        replay(args.freeze,args.raw,args.replay_decisions)
    else:
        run(args.freeze,args.raw)
