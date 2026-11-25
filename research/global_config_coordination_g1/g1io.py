"""Frozen P1 adapters, event comparison and content-addressed evidence."""
import csv
import gzip
import hashlib
import json
import os
import sys
from fractions import Fraction as Q
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
E1 = HERE.parent / "domain_joint_optimization_e0_e1"
E2 = HERE.parent / "domain_joint_optimization_e2a"
P1 = HERE.parent / "cross_scene_taskflow_diagnostic"
OUT = HERE / "results"
sys.dont_write_bytecode = True
runtime = Path(os.environ.get("G1_ORTOOLS", REPO.parent / "P1_worktree" / ".runtime-domain-cpsat"))
sys.path[:0] = [str(E1), str(E2), str(runtime)]
import common
from compact import Layout, idle_exact
from profiles import CFG
from model import Problem, transitions, event_arrays, independent_events
from heat import evaluate
from validation import common_grid
import numpy as np

SIZES = {"S16": Q(1,10), "S32": Q(1,5), "S80": Q(1,2)}
for name, seconds in SIZES.items():
    CFG["instances"][name] = [["L","H"], seconds, 35, 1]

def problem(name):
    p = Problem(name)
    assert p.horizon == int(p.horizon) and all(x == int(x) for x in p.boundaries)
    p.horizon = int(p.horizon)
    p.boundaries = list(map(int, p.boundaries))
    idle_exact(p)
    if name in SIZES:
        assert len(p.req) == int(name[1:])
    return p

def raw(data):
    return json.dumps(data, ensure_ascii=False, separators=(",",":"), default=str, allow_nan=False).encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(raw(data) + b"\n")
    temp.replace(path)

def table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as f:
        cw = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        cw.writeheader()
        cw.writerows(rows)

def record(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(raw(data) + b"\n")

def read(path):
    return json.loads(Path(path).read_bytes())

def store(p, plan):
    rows, low = plan
    payload = raw(common.obj(p.case, (rows, Layout(p,rows).normalize(low))))
    key = sha(payload)
    path = OUT/"plans"/(key+".json.gz")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(payload, compresslevel=2,mtime=0))
    return key

def load(key):
    blob = gzip.decompress((OUT/"plans"/(key+".json.gz")).read_bytes())
    assert sha(blob)==key
    return common.decode(json.loads(blob))

def assess(p, plan, *, expected_switches=None):
    rows, low = plan
    lay = Layout(p,rows)
    low = lay.normalize(low)
    key = store(p,(rows,low))
    path = OUT/"certificates"/(key+".json")
    _,sw,_ = transitions(p,rows,low)
    if expected_switches is not None:
        assert sw == expected_switches
    if path.exists():
        return key, read(path)
    a,sa,_ = event_arrays(p,rows,low)
    b,sb = independent_events(p,rows,low)
    assert sw == sa == sb == lay.switches(low)
    x,y = common_grid(a,b)
    assert np.array_equal(x,y)
    parts = lay.components(low)
    e35 = sum(parts.values())
    from_events = np.sum((a[:,1]-a[:,0])*(a[:,2:6].sum(axis=1)+.3))/10000
    assert abs(float(e35)-from_events)<1e-9
    metrics = evaluate(p,(rows,low),cert=True,trace=True)
    trace = np.asarray(metrics.pop("events"))
    assert np.array_equal(trace[:,:14],b)
    assert abs(metrics["E_J"]-metrics["temperature_J"]-float(e35))<1e-8
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path.with_suffix(".npz"),events=trace)
    cert = dict(plan=key,case=p.case,metrics=metrics,exact_E35_J=str(e35),E35_J=float(e35),
                ref_components={k:str(v) for k,v in parts.items()},switches=sw,
                configuration_counts={f"{u}/{k}":sum(z[:2]==(u,k) for z in rows)
                                      for u,k in sorted({r[:2] for r in rows})})
    write(path,cert)
    return key,cert

def instance_csv(name):
    p = problem(name)
    path = HERE/"instances"/(name+".csv")
    table(path,p.req)
    return path
