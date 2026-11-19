"""Reconcile a sealed pressure study using its files only (no solver imports)."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

SUBJECT = "c73b6c6728794d68db33395f78c7dc94e4634e5a"
FREEZE = "553e7f0bd16d10c9545ede12b0e07c87a143938c712274f1ee91b2f31c0d3bba"
N = 27 ** 4
KINDS = ("deadline_failed", "safe", "overtemp", "unresolved")


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(condition, label):
    if not condition:
        raise ValueError(label)


def same_float(a, b):
    return abs(a - b) <= 1e-7


def expected_requests(spec, model):
    frames = dict(zip(spec["scene_order"], spec["frames_in_execution_order"], strict=True))
    offsets = {}
    offset = 0
    for scene in sorted(frames):
        offsets[scene] = offset
        offset += frames[scene]
    rows = []
    frame = 0
    for scene in spec["scene_order"]:
        for j in range(frames[scene]):
            for app in model["fsm"]["active_apps"][scene]:
                rows.append([f"f{offsets[scene]+j:04d}-a{app}", app, frame*40000000, (frame+1)*40000000])
            frame += 1
    checked(len(rows) == 500 and frame == 250, "workload size")
    checked(sha(json.dumps(rows, separators=(",", ":")).encode()) == spec["request_stream_sha256"], "frozen requests")
    return rows


def audit_cell(folder, spec, job, model, root):
    r = read(folder/"result.json")
    d = job["deployment"]
    checked(all(job[k] == r[k] for k in job) and r["subject"] == SUBJECT, "cell identity")
    checked(r["ambient_c"] == 27.5 and r["initial_c"] == [30.]*4 and
            r["request_sha256"] == spec["request_stream_sha256"], "cell physics and stream")
    with np.load(folder/"space.npz", allow_pickle=False) as a:
        states, energy = a["status"], a["energy_j"]
    checked(states.shape == energy.shape == (N,) and states.dtype == np.uint8 and energy.dtype == np.float64,
            "array shape or dtype")
    counts = dict(zip(KINDS, np.bincount(states, minlength=4).tolist(), strict=True))
    checked(counts == r["counts"] and sum(counts.values()) == r["logical_codes"] == N, "array classification")
    mask = states != 0
    checked(np.all(np.isfinite(energy[mask])) and np.all(np.isnan(energy[~mask])), "energy support")
    grid = mask.reshape((27,)*4)
    factors = [np.any(grid, axis=tuple(i for i in range(4) if i != j)) for j in range(4)]
    reconstructed = factors[0]
    for factor in factors[1:]:
        reconstructed = (reconstructed[:,None] & factor).ravel()
    checked(np.array_equal(reconstructed, mask), "non-Cartesian deadline coverage")
    hist_error = None
    if d in ("A","C"):
        h = spec["historical_ac"][d]
        original = root / h["path"]
        checked(sha(original.read_bytes()) == h["sha256"], "reference file digest")
        with np.load(original, allow_pickle=False) as a:
            checked(np.array_equal(states,a["status"]) and np.array_equal(np.isnan(energy),np.isnan(a["energy_j"])), "control mask")
            hist_error = float(np.max(np.abs(energy[mask]-a["energy_j"][mask]), initial=0))
        checked(hist_error <= 1e-7 and hist_error == r["control_max_abs_energy_error_j"], "control energy")
    strict = float(np.min(energy[states==1])) if counts["safe"] else None
    expected_cert = "UNRESOLVED" if counts["unresolved"] else "NO_SAFE" if strict is None else "MIN_SAFE"
    checked(expected_cert == r["certificate"] and strict == r["strict_minimum_known_safe_j"]
            and bool(counts["safe"]) == r["safe_witness"], "finite-domain certificate")
    domain = np.flatnonzero(states==1) if counts["safe"] else np.flatnonzero(mask)
    report = dict(**job, counts=counts, certificate=expected_cert, minimum_safe_j=strict,
                  historical_max_error_j=hist_error, build_s=r["build_s"], search_s=r["search_s"],
                  fallback_segment_integrals=r["fallback_segment_integrals"])
    if not len(domain):
        checked(r["selection"] is None and r["physical"] is None and r["full_window_replays"] == 0, "empty domain")
        return report
    floor = float(np.min(energy[domain]))
    code = int(domain[energy[domain] <= floor+1e-9][0])
    levels = ["".join(x) for x in model["clock_policy"]["constant_opp_levels"]]
    opps = [levels[code//27**i%27] for i in (3,2,1,0)]
    checked(r["selection"]["code"] == code and r["selection"]["opps"] == opps and
            r["selection"]["predicted_j"] == energy[code], "code, frequency or tie rule")
    physical = r["physical"]
    rows = read(folder/"requests.json")
    expected = expected_requests(spec, model)
    checked([[q[k] for k in ("request_id","app_id","release_ns","deadline_ns")] for q in rows] == expected
            and len({q["request_id"] for q in rows}) == 500
            and Counter(q["app_id"] for q in rows) == {i:125 for i in range(4)}, "request-level identity")
    for q in rows:
        checked(q["release_ns"] <= q["completion_ns"] <= q["deadline_ns"]
                and q["slack_ns"] == q["deadline_ns"]-q["completion_ns"], "request deadline")
    checked(physical["fully_replayed"] and physical["deadline_ok"] and physical["required"] == physical["completed"] == 500
            and r["full_window_replays"] == 1, "whole-window replay")
    inlet = [30.]*4
    lo,hi = np.array(inlet),np.array(inlet)
    start = 0
    ej = 0.
    for i,(name,frames,opp,s) in enumerate(zip(spec["scene_order"],spec["frames_in_execution_order"],opps,physical["scene_rows"],strict=True)):
        stop = start + frames*40000000
        part = [q for q in rows if start <= q["release_ns"] < stop]
        checked((s["index"],s["scene"],s["start_ns"],s["service_end_ns"],s["end_ns"],s["opp"]) ==
                (i,name,start,stop,stop+(40000000 if i==3 else 0),opp), "scene identity or tail")
        checked(all(q["scene"] == name for q in part) and s["required"] == len(part) and s["deadline_ok"]
                and s["min_slack_ns"] == min(q["slack_ns"] for q in part), "scene requests")
        checked(s["entry_c"] == inlet and len(s["final_c"]) == 4 and
                np.isfinite(s["final_c"]).all() and np.all(np.array(s["peak_lower_c"]) <= s["peak_upper_c"]), "thermal continuity")
        inlet = s["final_c"]
        lo,hi = np.maximum(lo,s["peak_lower_c"]),np.maximum(hi,s["peak_upper_c"])
        ej += s["energy_j"]
        start = stop
    state = 2 if np.any(lo>80.) else 1 if np.all(hi<=80.) else 3
    checked(state == states[code] and physical["thermal_status"] == {1:"SAFE",2:"VIOLATION",3:"UNRESOLVED"}[state]
            and physical["feasible"] == (state==1) and physical["final_c"] == inlet
            and np.array_equal(hi,physical["peak_upper_c"]) and np.array_equal(lo,physical["peak_lower_c"]),
            "window thermal certificate")
    min_slack = min(q["slack_ns"] for q in rows)/1e6
    checked(same_float(ej,physical["energy_j"]) and same_float(ej,float(energy[code])) and
            same_float(min_slack,physical["min_slack_ms"]) and same_float(80.-max(hi),r["peak_margin_c"]), "energy, slack or margin")
    return dict(report, selected_code=code, opps=opps, selected_j=physical["energy_j"], min_slack_ms=min_slack,
                peak_upper_c=float(max(hi)), peak_lower_c=float(max(lo)), request_records=len(rows))


def audit(study):
    raw = study/"raw_execution"
    root = study.parents[1]
    m = read(study/"manifest.json")
    checked(sha((study/"execution_freeze.json").read_bytes()) == FREEZE, "runtime freeze")
    model = read(root/"research/kim_multidnn_expansion/expanded_input.json")
    digests = read(raw/"sha256.json")
    actual = {p.relative_to(raw).as_posix():sha(p.read_bytes()) for p in raw.rglob("*")
              if p.is_file() and "jit" not in p.relative_to(raw).parts and p != raw/"sha256.json"}
    checked(actual == digests, "complete raw SHA256 inventory")
    ledger = [json.loads(s) for s in (raw/"ledger.jsonl").read_bytes().splitlines()]
    stop = read(raw/"stop.json")
    checked(stop["reason"]=="COMPLETE" and stop["completed"]==12 and stop["reserved_s"]==1440, "batch completion")
    checked(len(ledger)==24 and len(m["execution_order"])==12, "single-use ledger")
    summary = read(raw/"summary.json")
    checked(len(summary)==12, "summary length")
    reports = []
    for i,job in enumerate(m["execution_order"]):
        folder = raw/f"{i:02d}"
        reserve,close = ledger[2*i:2*i+2]
        checked(reserve == read(folder/"reservation.json") and reserve["event"]=="reserve" and reserve["index"]==i and
                reserve["job"]==job and reserve["subject"]==SUBJECT and reserve["freeze_sha256"]==FREEZE and
                reserve["cap_s"]==120 and reserve["cumulative_reserved_s"]==(i+1)*120, "reservation")
        checked(close["event"]=="close" and close["index"]==i and close["status"]=="COMPLETE" and close["exit_code"]==0
                and (folder/"worker.lock").read_text()==SUBJECT, "settlement")
        cert = read(folder/"finished.json")["certificate_persisted_s"]
        checked(0 < cert <= close["wall_s"] <= reserve["cap_s"] and cert == close["certificate_persisted_s"], "deadline")
        checked(summary[i] == dict(read(folder/"result.json"),process_wall_s=close["wall_s"],certificate_persisted_s=cert), "summary source")
        if i==6:
            checked(all(r["certificate"]=="NO_SAFE" and r["historical_max_error_j"]<=1e-7 for r in reports) and
                    [r["deployment"] for r in reports]==["A"]*3+["C"]*3, "six controls before expansion")
        spec = next(s for s in m["cases"] if s["id"]==job["case_id"])
        reports.append(dict(audit_cell(folder,spec,job,model,root),cert_s=cert,wall_s=close["wall_s"]))
    outcomes = {}
    for spec in m["cases"]:
        added = [r for r in reports if r["case_id"]==spec["id"] and r["deployment"] in ("D001","D015")]
        witnesses = [r["deployment"] for r in added if r["counts"]["safe"]]
        outcomes[spec["id"]] = dict(witness_deployments=witnesses,
            outcome="RESTORED" if witnesses else "NO_SAFE_IN_FOUR" if all(r["certificate"]=="NO_SAFE" for r in added) else "UNRESOLVED")
    checked(outcomes==read(raw/"interpretation.json")["cases"], "case-level inference")
    return dict(subject=SUBJECT, execution_freeze_sha256=FREEZE, status="PASS", raw_files_verified=len(actual),
                raw_manifest_sha256=sha((raw/"sha256.json").read_bytes()), reserved_s=1440,
                process_wall_s=sum(r["wall_s"] for r in reports), logical_codes=N*12,
                request_records=sum(r.get("request_records",0) for r in reports), cases=outcomes,units=reports)


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1]).resolve()),indent=2,allow_nan=False))
