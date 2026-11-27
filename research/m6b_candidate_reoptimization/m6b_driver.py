"""Monotonic single-core supervisor and per-mapping physical recertification."""
import os
import time
BOOT=time.perf_counter()
CPU=min(os.sched_getaffinity(0))
os.sched_setaffinity(0,{CPU})
import gzip
import importlib.util
import json
import multiprocessing
import platform
import shutil
import sys
from pathlib import Path
from inventory import (ROOT,ARCH,SCR,GEN,METHODS,read,save,sha,raw,readcsv,census,fixture_cfg,get_map,label,material)
PREV=ROOT.parent/"m6a_global_frequency_mapping"
sys.path.insert(0,str(PREV))
spec=importlib.util.spec_from_file_location("frozen_global_diagnostic_m6a",PREV/"experiment.py")
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

def indexed(code,method):
    with gzip.open(ARCH/"identity"/code/"mappings.jsonl.gz","rt") as f:
        return {r["mapping"]:r for r in map(json.loads,f) if r["source"]==method}
def valid(d):return d is not None and d[2]["metrics"]["status"] in ("SAFE","HOT")
def snapshot(v):return ex.endpoint(v[2]) if v is not None else None
def beats(a,b):
    return a and a["status"]=="SAFE" and (not b or a["bounds"][1]<b["bounds"][0])
def restore(obj,engine,key,traces):
    p=material(label(obj));plan=read(p/(key+"-plan.json"));old=read(p/(key+"-certificate.json"))
    cfg=ex.genes(plan);r=engine.replay(cfg);assert r is not None
    built=engine.build(cfg,r)
    assert raw(built["rows"])==raw(plan["rows"]) and raw(sorted(built["low"]))==raw(plan["low"])
    d,tr=engine.cert(cfg,r,built)
    assert d["plan_sha256"]==key and ex.u2.raw(d["switches"])==ex.u2.raw(old["switches"])
    assert d["E35_exact"]==old["E35_exact"] and ex.u2.raw(d["metrics"])==ex.u2.raw(old["metrics"])
    assert sha(tr.tobytes())==traces[key]["event_array_sha256"]
    npz=engine.out/"evidence"/obj["case"]/key/"trace.npz"
    disk=sha(npz.read_bytes());assert disk==traces[key]["npz_file_sha256"],("historical NPZ mismatch",key,disk)
    return cfg,r,d,tr
def record(dest,row):
    with (dest/"mapping_events.jsonl").open("ab") as f:f.write(raw(dict(t=time.perf_counter()-ex.CLOCK,**row))+b"\n")
def evaluate(obj,eng,flow,seed,load_fallback,dest,key,observe):
    orig=snapshot(seed);observe("history",orig)
    ordinary=ex.optimize(eng,flow,seed[0],seed,dest,key+"/ordinary",False)
    ordinary_pt=snapshot(ordinary);observe("ordinary",ordinary_pt)
    reason=None
    if valid(ordinary):guide=ordinary
    else:
        reason="no_timing_feasible_result" if ordinary is None else ordinary[2]["metrics"]["status"]
        guide=load_fallback()
    assert get_map(ex.u2.encoded(guide[0]))==get_map(ex.u2.encoded(seed[0]))
    thermal=ex.optimize(eng,flow,seed[0],guide,dest,key+"/thermal",True)
    thermal_pt=snapshot(thermal);observe("thermal",thermal_pt)
    return dict(original=orig,ordinary=ordinary_pt,thermal=thermal_pt,guide=guide[2]["plan_sha256"],fallback=reason)

def preflight():
    MANIFEST=PREV/"SHA256SUMS"
    hashes={p:h for h,p in (line.split("  ",1) for line in MANIFEST.read_text().splitlines())}
    for n in ("experiment.py","dp.cpp","frequency.py"):assert sha((PREV/n).read_bytes())==hashes[n]
    rows=readcsv(GEN/"repetitions.csv")
    for obj in ex.u2.CASES:
        seeds={r["method"]:r["plan"] for r in rows if r["case"]==obj["case"] and r["repeat"]=="1" and r["regime"]=="60s" and r["method"] in METHODS}
        assert len(seeds)==2 and all(seeds.values())
        special=label(obj)=="C10"
        if special:
            dest=ARCH/"fixture";dest.mkdir(parents=True)
            eng,flow=ex.build(obj,dest);candidate=fixture_cfg(flow);fixhash=sha(candidate)
        census(obj,seeds,fixhash if special else None)
        if special:
            cfg=tuple((3,k-10) if k>=10 else (2,k) for k in candidate)
            state=eng.replay(cfg);assert state is not None
            d,tr=eng.cert(cfg,state);seed=(cfg,state,d,tr);meta=read(ARCH/"fixture_identity.json")
            assert all(r["plan"]==d["plan_sha256"] for r in meta["all_calls"])
            booked={}
            for m in METHODS:
                entry=indexed("C10",m).get(get_map(candidate))
                booked[m]=None if entry is None else {k:entry[k] for k in ("mapping","rep_status","local_safe","local_hot","hot_only")}
            fixture=evaluate(obj,eng,flow,seed,lambda:seed,dest,"fixture",lambda *ignored:None)
            save(dest/"result.json",dict(**fixture,cfg=fixhash,mapping=get_map(candidate),mapped_history=booked,
                eligible_matches=sum(r["eligible"] for r in meta["all_calls"]),all_scope_matches=len(meta["all_calls"])))
    save(ARCH/"gate_pass.json",dict(cases=12,m6a_manifest_sha=sha(MANIFEST.read_bytes()),source=os.environ["GITHUB_SHA"],
        host=platform.node(),cpu=CPU,python=sys.version))

def cell(obj,method,arm,dest):
    code=label(obj);entries=indexed(code,method)
    nominations=read(ARCH/"identity"/code/"selection.json")["methods"][method][arm]
    traces=read(material(code)/"traces.json")
    eng,flow=ex.build(obj,dest);incumbent=None
    for j,key in enumerate(nominations):
        e=entries[key];rep=e["representative"]
        record(dest,dict(kind="start",i=j,mapping=key,representative=rep,hot_only=e["hot_only"]))
        seed=restore(obj,eng,rep,traces);assert get_map(ex.u2.encoded(seed[0]))==key
        def fallback():
            return seed if e["fallback"]==rep else restore(obj,eng,e["fallback"],traces)
        current=None;ordinary_best=None
        def observe(stage,point):
            nonlocal incumbent,current,ordinary_best
            if beats(point,current):current=point
            if stage!="thermal":ordinary_best=current
            if beats(point,incumbent):
                incumbent=point
                save(dest/"incumbent.json",dict(endpoint=point,mapping=key,slot=j,stage=stage,t=time.perf_counter()-ex.CLOCK))
            record(dest,dict(kind="stage",i=j,mapping=key,stage=stage,point=point))
        results=evaluate(obj,eng,flow,seed,fallback,dest,key,observe)
        row=dict(kind="complete",i=j,mapping=key,local_safe=e["local_safe"],hot_only=e["hot_only"],**results,
                 ordinary_best=ordinary_best,best=current,running=incumbent)
        record(dest,row)
        if j==0:save(dest/"P.json",row)
    save(dest/"natural.json",dict(completed=len(nominations),best=incumbent))

def supervise(dest,limit,fn,args,charge=0.):
    dest.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    def work():
        ex.CLOCK=started;fn(*args)
    proc=multiprocessing.get_context("fork").Process(target=work);proc.start()
    proc.join(max(0,limit-charge-.2-(time.perf_counter()-started)))
    if proc.is_alive():proc.kill();proc.join();status="CAP"
    else:status="NATURAL" if proc.exitcode==0 else "ERROR"
    wall=time.perf_counter()-started+charge
    save(dest/"receipt.json",dict(wall_s=wall,limit_s=limit,status=status,rc=proc.exitcode,core=CPU,host=platform.node(),
         run=os.environ["GITHUB_RUN_ID"],source=os.environ["GITHUB_SHA"],startup_charge=charge))
    print(dest.relative_to(ARCH),status,round(wall,3),flush=True)
    assert status!="ERROR" and wall<=limit
def main():
    phase=sys.argv[1];ex.RUN=ex.u2.stack()
    if phase=="gate":
        supervise(ARCH/"gate",300,preflight,(),time.perf_counter()-BOOT)
        assert (ARCH/"gate_pass.json").is_file()
    else:
        assert read(ARCH/"gate_pass.json")["source"]==os.environ["GITHUB_SHA"]
        for ix,obj in enumerate(ex.u2.CASES):
            code=label(obj)
            if phase=="offline" and code!="C10":continue
            for j,m in enumerate(METHODS):
                arms=["ALL"] if phase=="offline" else (["S","H"] if (ix+j)%2==0 else ["H","S"])
                for arm in arms:
                    dest=ARCH/phase/code/m/arm
                    supervise(dest,600 if phase=="offline" else 120,cell,(obj,m,arm,dest))
if __name__=="__main__":main()
