"""Bindings and physical evidence checks for the registered diagnostic."""
import hashlib
import json
import os
import sys
from pathlib import Path
from time import perf_counter, process_time

HERE = Path(__file__).resolve().parent
INPUTS = Path(os.environ["U3A_INPUTS"]).resolve()
OUTPUT = HERE / "results"
WORK = INPUTS / "work"
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
os.environ.update(U1_NT=str(INPUTS/"nt"), U1_FOUR=str(INPUTS/"four"),
                  U1_THREE=str(INPUTS/"p1"), U1_OUT=str(WORK), M1G_RAW=str(WORK/"warm"))
sys.path.insert(0,str(INPUTS/"u2/research/u2_adaptive_groups"))
import common_u2 as u
import numpy as np
import psutil
proc = psutil.Process()
proc.cpu_affinity(proc.cpu_affinity()[:1])
read, save, sha, raw = u.read, u.save, u.sha, u.raw

def decode(code):
    return tuple((3,v-10) if v>=10 else (2,v) for v in code)

def full(case, engine, cfg, state):
    built = engine.build(cfg, state)
    body = dict(case=case, rows=built["rows"], low=sorted(built["low"]))
    return sha(raw(body)), built

def check_trace(folder, built, horizon):
    met = read(folder/"certificate.json")["metrics"]
    with np.load(folder/"trace.npz",allow_pickle=False) as data:
        tr = data["events"]
    assert tr.shape[1]==31 and tr[0,0]==0 and tr[-1,1]==horizon
    assert np.array_equal(tr[:, :14],built["ev"])
    assert np.array_equal(tr[:-1,1],tr[1:,0]) and np.array_equal(tr[:-1,18:22],tr[1:,14:18])
    assert abs(float(tr[:,26:30].sum())+.3*horizon/10000-met["E_J"])<1e-7
    assert abs(float(tr[:,22:26].max())-max(met["peak_hi"]))<1e-7
    assert met["min_deadline_slack_ms"] >= 0
    return sha(tr.tobytes())

def row(cert):
    m=cert["metrics"]
    return dict(plan=cert["plan_sha256"],status=m["status"],J=m["E_J"],bounds=m["E_bounds"],
                peak_hi=max(m["peak_hi"]),peak_lo=max(m["peak_lo"]),slack_ms=m["min_deadline_slack_ms"],
                reference_J=cert["E35_J"],kernel_s=cert["cert_s"])

def case_context(obj, stack):
    api,fourth,_,causal=stack
    code=obj["case"].split("_")[0]
    dest=OUTPUT/code
    flow=u.make_flow(api,obj,WORK/code)
    eng=fourth.Engine(obj["case"],dest)
    blob=(u.REG/"inputs"/obj["input"]).read_bytes()
    assert sha(blob)==obj["input_sha256"] and u.table(eng.p.req)==blob and eng.p.horizon==obj["horizon_ticks"]
    return code,dest,flow,eng,causal

def times():
    return perf_counter(),process_time()

def duration(start):
    return dict(wall_s=perf_counter()-start[0],cpu_s=process_time()-start[1])
