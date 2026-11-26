"""Run one-shot literature solvers, quota controls and the frozen 60 s baselines."""
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parent
OUT=Path(os.environ.get("M1G_RAW",ROOT/"raw")).resolve()
F=ROOT.parent/"m1f_trace_energy_quality"
sys.path.insert(0,str(F))
from long_run import BASE, inputs
os.environ["M1E_OUTPUT"]=str(OUT/"engine")
sys.path.insert(0,str(BASE))
# Both files have the name experiment.py. Load the immutable implementation by path.
import importlib.util
module_spec=importlib.util.spec_from_file_location("m1e_frozen",BASE/"experiment.py")
e=importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(e)
from model import independent_events, event_arrays, transitions
from heat import evaluate
from literature import Calendar, Profile, latest_finishes, lft, li_map, reference, zhou
import numpy as np

METHODS=("NT","C2","Zhou","Li","ZQ","LQ")


def case_for(path):
    size,word=path.stem.split("_")
    label="L"+size[1:]
    case=e.reordered(e.case_for(label),label,word)
    actual=Path(os.environ["M1E_OUTPUT"])/"validation_inputs"/path.name
    assert actual.read_bytes().splitlines()==path.read_bytes().splitlines()
    return case


def low_flags(p,rows):
    """Use the frozen causal idle energy rule on each physical frequency domain."""
    units,_,_=transitions(p,rows,frozenset())
    low=set()
    domains=(sorted(units[0]+units[1]),units[2],units[3])
    for dom,tasks in enumerate(domains):
        nodes=((0,1),(2,),(3,))[dom]
        last,old=0,0
        final_epoch=max(r["release_tick"] for r in p.req)//10000*10000
        for t,end,k,i in [*tasks,(p.horizon,p.horizon,0,-1)]:
            epoch=final_epoch if i<0 else p.req[i//3]["release_tick"]//10000*10000
            extra=sum(p.idle[u,old][0]-p.idle[u,0][0] for u in nodes)
            if old and last>=epoch and t-last>=5*(1+(k!=0)):
                hold=extra*(t-last)+15*(old!=k)
                drop=extra*5+15*(1+(k!=0))
                if drop<hold-1e-10:
                    low.add((dom,i))
            last=max(last,end)
            old=k
    return low


def certify_native(case,book,dest):
    p=case.p
    low=low_flags(p,book.rows)
    primary,switches,_=event_arrays(p,book.rows,low)
    secondary,independent_switches=independent_events(p,book.rows,low)
    assert switches==independent_switches and np.array_equal(primary,secondary)
    metrics=evaluate(p,(book.rows,low),cert=True,trace=True)
    arr=np.asarray(metrics.pop("events"))
    ref=np.sum((arr[:,1]-arr[:,0])*(arr[:,2:6].sum(axis=1)+.3))/10000
    assert abs(metrics["E_J"]-metrics["temperature_J"]-ref)<1e-8
    payload=dict(case=case.label,rows=book.rows,low=sorted(low))
    identity=e.p1.sha(e.p1.raw(payload))
    cert=dict(plan_sha256=identity,metrics=metrics,E35_J=float(ref),switches=switches)
    folder=dest/"evidence"/case.label/identity
    e.p1.put(folder/"plan.json",payload)
    e.p1.put(folder/"certificate.json",cert)
    np.savez_compressed(folder/"trace.npz",events=arr)
    return cert


def as_book(case,cfg):
    b=Calendar(case.p)
    led=case.ledger(cfg,0,case.p.horizon,10000,True,False)
    assert led[0]
    for j,k in enumerate(cfg):
        b.add(3*j,0,0,case.eng.ps[j])
        b.add(3*j+1,3 if k>=10 else 2,k-10 if k>=10 else k,int(led[4][j]))
        b.add(3*j+2,1,0,int(led[6][j]))
    return b


def quota(case,method,prof,stats):
    p=case.p
    limits=np.array(reference(p,prof))[1::3] if method=="LQ" else None
    ranks=np.zeros((2,13))
    modes=prof.li_modes("main") if method=="LQ" else prof.order["main"]
    for rank,(u,k) in enumerate(modes):
        ranks[:,k+(10 if u==3 else 0)]=rank
    parents=[e.initial(case)]
    actions=[]
    for j in range(case.windows):
        pool,ok=e.expand(case,j,parents,"NT",perf_counter(),float("inf"),dict(actions=[],groups=[]))
        assert ok
        left=np.searchsorted(case.release,j*10000)
        choices=[]
        for state in pool.values():
            peak=state["peak"]
            if method=="ZQ" and peak>80:
                stats["thermal_reject"]+=1
                continue
            cfg=state["config"]
            codes=np.frombuffer(cfg[left:],np.uint8)
            regret=float(ranks[case.kinds[left:len(cfg)],codes].sum())
            late=0
            if limits is not None:
                # Fixed FIFO makes post/latest-finish checks independent of the scoring approximation.
                ledger=case.ledger(cfg,0,p.horizon,10000,j+1==case.windows,False)
                late=int(np.sum(ledger[5][left:len(cfg)]>limits[left:len(cfg)]))
            choices.append(((late,regret,state["energy"],cfg),state))
        stats["valid_pool"]+=len(pool)
        if not choices:
            stats["failed_window"]=j+1
            return None,None
        winner=min(choices,key=lambda x:x[0])[1]
        parents=[winner]
        actions.append(winner["action"])
    return parents[0]["config"],actions


def quota_lft(case,cfg,actions,stats):
    p=case.p
    for j in reversed(range(case.windows)):
        left,right=case.release.searchsorted((j*10000,(j+1)*10000))
        for unit in (2,3):
            book=as_book(case,cfg)
            limits=latest_finishes(p,book)
            g,n,x,y=actions[j]
            k=g if unit==2 else n
            ids=[i for i in range(left,right) if book.rows[3*i+1][0]==unit]
            if not ids:
                continue
            for lower in range(k):
                new=(lower,n,x,y) if unit==2 else (g,lower,x,y)
                proposal=cfg[:left]+case.extension(*e.window_types(case,j),*new)+cfg[right:]
                v=case.ledger(proposal,0,p.horizon,10000,True,False)
                if v[0] and all(v[5][i]<=limits[3*i+1] for i in ids):
                    cfg=proposal
                    actions[j]=new
                    stats["LFT_lowered_windows"]+=1
                    break
    return cfg


def standalone(case,method,dest):
    stats=Counter()
    calls=[]
    t0=perf_counter()
    profile=Profile(case.p)
    def record(stage,cert):
        m=cert["metrics"]
        calls.append(dict(stage=stage,elapsed_s=perf_counter()-t0,status=m["status"],
                          plan=cert["plan_sha256"],E_J=m["E_J"],lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                          peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"]))
    missing=0
    if method in ("Zhou","Li"):
        book=zhou(case.p,profile,stats) if method=="Zhou" else li_map(case.p,profile,stats)
        missing=sum(row is None for row in book.rows)
        if missing:
            unplaced=[i for i,row in enumerate(book.rows) if row is None]
            failed=stats.get("failed_task",unplaced[0])
            stats["first_unplaced_index"]=failed
            stats["unplaced_pre"]=sum(i%3==0 for i in unplaced)
            stats["unplaced_main"]=sum(i%3==1 for i in unplaced)
            stats["unplaced_post"]=sum(i%3==2 for i in unplaced)
            e.p1.put(dest/"partial"/case.label/(method+".json"),dict(case=case.label,method=method,rows=book.rows,failed=failed))
        if not missing:
            record("mapping",certify_native(case,book,dest))
            if method=="Li":
                lft(case.p,book,stats)
                record("LFT",certify_native(case,book,dest))
    else:
        case.eng.out=dest
        cfg,actions=quota(case,method,profile,stats)
        if cfg is not None:
            record("quota_mapping",case.certify(cfg)[0])
            if method=="LQ":
                cfg=quota_lft(case,cfg,actions,stats)
                record("quota_LFT",case.certify(cfg)[0])
        else:
            missing=None
    wall=perf_counter()-t0
    result=dict(case=case.label,method=method,wall_s=wall,missing_stages=missing,stats=dict(stats),
                stages=calls,final_status=calls[-1]["status"] if calls else "NO_CONSTRUCTION")
    e.p1.put(dest/"standalone"/case.label/(method+".json"),result)
    return result

