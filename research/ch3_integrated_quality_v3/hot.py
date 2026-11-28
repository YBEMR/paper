"""Mapping census and frozen DP for a timing-feasible, certified HOT-only seed."""
import importlib.util
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
V2 = ROOT.parent/"ch3_integrated_quality_v2"
spec = importlib.util.spec_from_file_location("four_safe", V2/"trial.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
f = v2.frozen
m = f.m
OUT = ROOT/"archive"


def census(events, mapping_for):
    safe, hot, plans = {}, {}, {}
    for e in events:
        if e["event"] != "certificate" or e["t"] > 55:
            continue
        pt = e["point"]
        key = pt["plan"]
        if pt["status"] not in ("SAFE", "HOT") or key in plans:
            continue
        assert pt["slack"] >= 0
        mapping = mapping_for(key)
        plans[key] = mapping
        group = safe if pt["status"]=="SAFE" else hot
        group.setdefault(mapping, []).append(e)
    return safe, hot, {k:v for k,v in hot.items() if k not in safe}, plans


def upper(e):
    return e["point"]["bounds"][1], e["t"], e["point"]["plan"]


def peak(e):
    return (e["point"]["peak"], *upper(e))


def nominees(only):
    entries = [e for records in only.values() for e in records]
    if not entries:
        return None, None
    return min(entries, key=upper), min(entries, key=peak)


def valid(trace, horizon):
    return (trace.ndim==2 and trace.shape[1]==31 and len(trace)>0 and
            np.isfinite(trace).all() and trace[0,0]==0 and trace[-1,1]==horizon and
            np.all(trace[:,1]>trace[:,0]) and np.array_equal(trace[:-1,1],trace[1:,0]))


def handoff(obj, dest, source, point):
    eng,flow=m.build(obj,dest)
    plan=f.read(source/"plan.json")
    d=f.read(source/"certificate.json")
    assert point["status"]=="HOT" and point["slack"]>=0 and m.endpoint(d)==point
    assert f.digest((source/"plan.json").read_bytes().strip())==point["plan"]
    cfg=m.genes(plan)
    replay=eng.replay(cfg)
    assert replay is not None
    b=eng.build(cfg,replay)
    assert f.raw(b["rows"])==f.raw(plan["rows"]) and f.raw(sorted(b["low"]))==f.raw(plan["low"])
    assert f.raw(b["switches"])==f.raw(d["switches"])
    with np.load(source/"trace.npz") as data:
        trace=data["events"]
    assert valid(trace,eng.p.horizon) and np.array_equal(b["ev"],trace[:,:14])
    return eng,flow,(cfg,replay,d,trace)


def refine_hot(eng,flow,seed,dest,emit):
    local=None
    guide=seed
    for stage in ("ordinary","thermal"):
        thermal=stage=="thermal"
        eng.out=dest/stage
        emit("begin",task="refinement",stage=stage,guide=guide[2]["plan_sha256"])
        result=m.optimize(eng,flow,seed[0],guide,dest,stage,thermal)
        if result is not None:
            assert tuple(x[0] for x in result[0])==tuple(x[0] for x in seed[0])
            pt=m.endpoint(result[2])
            usable=pt["status"] in ("SAFE","HOT") and valid(result[3],eng.p.horizon)
            if pt["status"]=="SAFE":
                assert usable and pt["slack"]>=0 and pt["peak"]<=80
            if not thermal and usable:
                guide=result
            if f.strict(pt,local):
                local=pt
            emit("certificate",stage=stage,point=pt)
        emit("stage_end",stage=stage,attempt=result[2]["plan_sha256"] if result else None,
             incumbent=local["plan"] if local else None)
    return local
