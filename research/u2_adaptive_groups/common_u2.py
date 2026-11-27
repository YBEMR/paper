"""U2 registration and pinned physical interfaces."""
import csv
import importlib.util
import inspect
import os
import sys
import textwrap
import types
from pathlib import Path
from time import perf_counter

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"u1_unified_diagnostic"))
from interface import NT, FOUR, OUT, REG, read, raw, save, sha, table, decode, cfg, witness
import numpy as np
LOCAL=("Single2","Fixed2","Adaptive2","ThermalUnion")
CASES=[r for r in read(REG/"cases.json")["cases"] if r["ambient"]==35]
assert len(CASES)==12
def lines(path):
    import json
    return [json.loads(s) for s in path.read_bytes().splitlines() if s.endswith(b"}")] if path.is_file() else []
def append(path,data):
    with path.open("ab") as f:f.write(raw(data)+b"\n")
def best(rows,cut=60):
    winner=None
    for r in rows:
        if r["t"]<=cut and r["status"]=="SAFE" and (winner is None or r["bounds"][1]<winner["bounds"][0]):
            winner=r
    return winner
def stack():
    sys.path.insert(0,str(NT/"m1i_generalization"))
    import adapter
    import mechanism
    import runner
    root=NT/"m1_transient_thermal_quota_20261126/frozen"
    shared=["preflight.py","p1/profiles.py",*["p1/"+f for f in adapter.e.p1.PIN]]
    for p in shared:assert (root/p).read_bytes()==(FOUR/p).read_bytes(),p
    spec=importlib.util.spec_from_file_location("u2_fourth_frozen",FOUR/"preflight.py")
    fourth=importlib.util.module_from_spec(spec);spec.loader.exec_module(fourth)
    # Reuse exactly NT's causal FIFO/idle reconstruction up to the certification boundary.
    original=textwrap.dedent(inspect.getsource(mechanism.Case.certify))
    head,sep,_=original.partition("    cert,trace = eng.cert(code,r)")
    assert sep and head.count("    assert r is not None")==1
    head=head.replace("def certify(","def causal_state(").replace("    assert r is not None","    if r is None: return None")
    ns=dict(mechanism.Case.certify.__globals__)
    exec(compile(head+"    return r\n","<frozen NT FIFO prefix>","exec"),ns)
    adapter.template()
    return adapter,fourth,runner,ns["causal_state"]
def make_flow(api,obj,dest):
    f=api.flow(obj,dest)
    assert table(f.p.req)==(REG/"inputs"/obj["input"]).read_bytes() and f.p.horizon==obj["horizon_ticks"]
    return f
def encoded(c):
    return bytes(k+10*(u==3) for u,k in c)
def intake(obj,src,dest,stacked):
    api,fourth,_,state=stacked
    flow=make_flow(api,obj,dest)
    eng=fourth.Engine(obj["case"],dest)
    assert table(eng.p.req)==table(flow.p.req)
    plan=read(src/"plan.json");original=read(src/"certificate.json")
    rows,low=decode(plan);config=tuple(row[:2] for row in rows[1::3])
    def replay(c):return state(flow,encoded(c))
    eng.replay=replay
    r=replay(config)
    b=eng.build(config,r)
    assert b["rows"]==rows and b["low"]==low and raw(b["switches"])==raw(original["switches"])
    d,tr=eng.cert(config,r,b)
    with np.load(src/"trace.npz") as archive:
        assert np.array_equal(archive["events"],tr)
    assert d["plan_sha256"]==src.name==original["plan_sha256"] and raw(d["metrics"])==raw(original["metrics"])
    assert d["E35_exact"]==original["E35_exact"]
    save(dest/"handoff.json",dict(plan=src.name,request_sha=obj["input_sha256"],trace_sha=sha(tr.tobytes()),
        event_rows=len(tr),switches=d["metrics"]["switch_count"],low=len(low),horizon=eng.p.horizon,J=d["metrics"]["E_J"],
        status=d["metrics"]["status"],verification_cert_s=d["cert_s"]))
    return eng,(config,r,d,tr)
def order(index,repeat):
    rotation=(index+repeat-1)%4
    arms=list(LOCAL[rotation:]+LOCAL[:rotation])
    pos=(index+repeat-1)%6
    result=["NT",*arms]
    result.insert(pos,"Q4")
    return result
def precheck(dest):
    s=stack()
    checks=[]
    for code in ("A03","C10"):
        obj=next(o for o in CASES if o["case"].startswith(code+"_"))
        historical,key=witness(code)
        f=make_flow(s[0],obj,dest/code/"NT")
        d,_=f.certify(cfg(historical["rows"]))
        assert d["plan_sha256"]==key
        eng,init=intake(obj,dest/code/"NT/evidence"/obj["case"]/key,dest/code/"fourth",s)
        checks.append(read(dest/code/"fourth/handoff.json"))
    save(dest/"gate.json",dict(search_calls=0,checks=checks))
