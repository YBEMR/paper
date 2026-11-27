"""Shared, single-thread runtime for the four registered NT arms."""
import csv
import hashlib
import json
import os
import sys
from fractions import Fraction
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parent
NT = Path(os.environ["M6_NT"]).resolve()
HISTORY = Path(os.environ["M6_HISTORY"]).resolve()
OUT = ROOT / "archive"
ARMS = {"A": (10000, 10000), "B": (10000, 2500), "C": (5000, 2500), "D": (2500, 2500)}
CODES = ("A02", "A03", "A06", "B07", "C10", "C11")
THREADS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS")
assert all(os.environ[k] == "1" for k in THREADS)
orig_cores = sorted(os.sched_getaffinity(0))
sys.path.insert(0, str(NT / "research/m1i_generalization"))
import adapter
import runner
import model
import numpy as np
from mechanism import archive_means
from threadpoolctl import threadpool_limits, threadpool_info
from design import REG, csv_bytes
from adapter import e
single = threadpool_limits(limits=1)
assert all(x["num_threads"] == 1 for x in threadpool_info())
p1 = e.p1
CASES = {r["case"].split("_")[0]: r for r in json.loads((REG/"cases.json").read_bytes())["cases"]}
flows = {}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, value):
    p1.put(path, value)

def read(path):
    return json.loads(path.read_bytes())

def recorded_requests(item):
    raw = (REG/"inputs"/item["input"]).read_bytes()
    assert sha(raw) == item["input_sha256"]
    rows = list(csv.DictReader(raw.decode().splitlines()))
    for row in rows:
        for field in ("request","scene","release_tick","deadline_tick"):
            row[field] = int(row[field])
        for field in ("release_ms","deadline_ms"):
            row[field] = Fraction(row[field])
    assert csv_bytes(rows) == raw
    assert all(r["request"] == i and r["deadline_ms"]-r["release_ms"] == 300 for i,r in enumerate(rows))
    return rows

def init_flow(code):
    item = CASES[code]
    registered = recorded_requests(item)
    # The frozen template warms the original case-independent arrays. For every
    # actual study case Problem reads the registered rows directly.
    adapter.template()
    original = model.requests
    def source(label):
        assert label == item["case"]
        return registered
    model.requests = source
    try:
        flow = adapter.flow(item, OUT/"gate"/code)
    finally:
        model.requests = original
    assert flow.p.req is registered and flow.p.horizon == item["horizon_ticks"]
    flows[code] = flow
    return flow

def set_arm(c, arm):
    width, c.information_ticks = ARMS[arm]
    c.eng.dur = width
    c.windows, remainder = divmod(c.p.horizon-3010, width)
    assert remainder == 0
    ix = c.release.searchsorted(np.arange(c.windows+1)*width)
    assert ix[0] == 0 and ix[-1] == len(c.release) and np.all(np.diff(ix)>0)
    return ix

def event_check(c, cfg, events):
    """Compare sequential prefix states with independent event replay on the same grid."""
    width = c.eng.dur
    temp, expected = c.p.initial.copy(), c.p.initial.copy()
    err_m = err_t = 0.
    cross = 0
    for j in range(c.windows):
        left = j*width
        last = j+1 == c.windows
        right = c.p.horizon if last else left+width
        count = int(c.release.searchsorted((j+1)*width))
        z = c.ledger(cfg[:count], left, right, 2500, last)
        assert z[0], (c.label,j,"illegal witness prefix")
        if not last:
            cross += int(np.count_nonzero(z[5]>right))
        for k, moment in enumerate(z[8]):
            t = left+k*2500
            end = min(t+2500, right)
            m = archive_means(events, t, end)
            err_m = max(err_m, float(np.max(np.abs(m-moment))))
            temp = c.propagate(temp, moment, (end-t)/10000)
            expected = c.propagate(expected, m, (end-t)/10000)
            err_t = max(err_t, float(np.max(np.abs(temp-expected))))
    assert err_m < 1e-8 and err_t < 1e-8, (c.label,err_m,err_t)
    ref = float((np.diff(events[:,:2]).ravel()*(events[:,2:6].sum(axis=1)+.3)).sum()/10000)
    return dict(moment_error=err_m, prefix_grid_error_K=err_t, cross_window_count=cross, integrated_E35_J=ref,
                grid_vs_continuous_end_K=float(np.max(np.abs(temp-events[-1,18:22]))))

def represent(c, cfg):
    passed = mismatch = multi = 0
    for j in range(c.windows):
        lo,hi = c.release.searchsorted([j*c.eng.dur,(j+1)*c.eng.dur])
        t,a,b = e.window_types(c,j)
        arr=np.frombuffer(cfg[lo:hi],np.uint8)
        g,n = np.unique(arr[arr<10]), np.unique(arr[arr>=10]-10)
        if max(len(g),len(n))>1:
            multi+=1
            continue
        counts = [int(np.count_nonzero((arr>=10)&(t==k))) for k in range(2)]
        restored=c.extension(t,a,b,int(g[0]) if len(g) else 0,int(n[0]) if len(n) else 0,*counts)
        if restored==cfg[lo:hi]: passed+=1
        else: mismatch+=1
    return dict(windows=c.windows, exact_windows=passed, distribution_mismatch=mismatch, mixed_opp_windows=multi,
                exact_encoding=passed==c.windows)

def config(plan):
    return bytes(k+10*(u==3) for u,k,_ in plan["rows"][1::3])

def stage():
    return dict(actions=[],groups=[],beam=[])

