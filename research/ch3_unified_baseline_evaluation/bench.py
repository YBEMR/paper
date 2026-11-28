import ast
import csv
import hashlib
import inspect
import json
import os
import platform
import random
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace
from collections import Counter

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_integrated_quality_v3"))
import online
from hot import f,m,v2
import numpy as np
OUT=ROOT/"archive"
ARMS=("Proposed","Zhou-P1","Li-P1","GA","C2","ZQ","LQ")
GA=Path(os.environ["GA_ROOT"])/"research"
def log(event,**kw):f.log(LEDGER,event,**kw)
def bind(fn,**kw):return types.FunctionType(fn.__code__,dict(fn.__globals__,**kw),fn.__name__,fn.__defaults__,fn.__closure__)
def defs(path,names,ns):
    tree=ast.parse(path.read_text());tree.body=[x for x in tree.body if getattr(x,"name",None) in names]
    assert len(tree.body)==len(names)
    exec(compile(tree,str(path),"exec"),ns)
    return ns
def operators():
    import bisect
    from dataclasses import dataclass
    from fractions import Fraction
    from math import lcm
    def frontier(p):
        engine=ACTIVE.eng
        return SimpleNamespace(ops=p.options[1],pre=engine.a,
            duration={(t+".main",u,k):v for (t,u,k),v in engine.length.items()},
            busy={(t+".main",u,k):v for (t,u,k),v in engine.inc.items()},
            gap=lambda u,a,b,dt:engine.gap(u,a,b,dt)[0])
    ns=dict(dataclass=dataclass,bisect_left=bisect.bisect_left,Frontier=frontier,__name__=__name__)
    model=defs(GA/"critical_interval_coordination_g2/fifo.py",{"State","Compact"},ns)
    ns["EMPTY"]=ns["State"]((0,0,0,0),((),()),0)
    ns.update(perf_counter=f.T,record=lambda path,obj:f.log(path,"generation",**obj),
              evolved_plan=lambda p,cfg:cfg)
    evo=defs(GA/"chapter3_final_evaluation/evolution.py",{"genes","repair","mutate","evolve"},ns)
    return ns
class Found(Exception):pass
def observe(cert,stage):
    point=m.endpoint(cert)
    log("certificate",point=point,stage=stage)
    return dict(J=point["J"],eligible=point["status"]=="SAFE",bounds=point["bounds"],status=point["status"])
def search(flow,dest,method):
    native=flow.certify
    def watched(cfg):
        log("begin",task="search_cert")
        result=native(cfg);observe(result[0],"C2")
        if method=="GA" and result[0]["metrics"]["status"]=="SAFE":raise Found(cfg,result[0])
        return result
    flow.certify=watched
    def builder(name):
        build,meta=m.RUN[2].builder(name)
        def timed(*args):
            log("begin",task="construct");pool=build(*args)
            log("end",task="construct",terminals=len(pool),progress=meta.copy());return pool
        return timed,meta
    try:
        f.bind(f.ORIGIN,lambda:f.ORIGIN+60,builder)(flow,"C2",dest/"search",60)
    finally:flow.certify=native
def genetic(flow,dest,rep,cfg,d):
    global ACTIVE
    ACTIVE=flow
    log("begin",task="ga_setup")
    ops=operators();model=ops["Compact"](flow.p)
    genes=tuple((3,k-10) if k>=10 else (2,k) for k in cfg)
    assert model.replay(genes) is not None
    plan=f.read(dest/"search/physical/evidence"/flow.label/d["plan_sha256"]/"plan.json")
    best=dict(eligible=True,J=d["metrics"]["E_J"],bounds=d["metrics"]["E_bounds"])
    ctx=SimpleNamespace(plan=([tuple(row) for row in plan["rows"]],plan["low"]),best=best,p=flow.p,folder=dest,elapsed=lambda:f.T()-f.ORIGIN)
    assert ops["genes"](ctx.plan)==genes
    def consider(c,until):
        log("begin",task="search_cert")
        cert,_=flow.certify(m.u2.encoded(c))
        score=observe(cert,"GA")
        if score["eligible"] and score["bounds"][1]<ctx.best["bounds"][0]:ctx.best=score
        return score
    ctx.consider=consider
    log("end",task="ga_setup");log("begin",task="ga_search")
    info=ops["evolve"](ctx,model,random.Random(100+rep),"GA",f.ORIGIN+60,dict(population=40,tournament=3,elite=2,crossover=.8))
    log("end",task="ga_search",info=info)
def literature(flow,arm,dest):
    lib=sys.modules["experiment"]
    method=arm.split("-")[0];stage=[0]
    def note(d):
        label=(["mapping","LFT"] if method in ("Zhou","Li") else ["quota_mapping","quota_LFT"])[stage[0]]
        observe(d,label);stage[0]+=1
    def native(*args):
        log("begin",task="search_cert");d=lib.certify_native(*args);note(d);return d
    original=flow.certify
    def fifo(cfg):
        log("begin",task="search_cert");d,tr=original(cfg);note(d);return d,tr
    flow.certify=fifo
    def timed(fn,label):
        def call(*args):
            log("begin",task=label);r=fn(*args);log("end",task=label);return r
        return call
    try:
        return bind(lib.standalone,certify_native=native,**{k:timed(getattr(lib,k),"construct" if k in ("zhou","li_map","quota") else "optimization") for k in ("zhou","li_map","quota","lft","quota_lft")})(flow,method,dest/"search/physical")
    finally:flow.certify=original
def execute(obj,arm,rep,dest):
    global LEDGER
    LEDGER=dest/"search.jsonl";f.arm_alarm(f.ORIGIN+60)
    log("begin",task="instance");flow=m.u2.make_flow(m.RUN[0],obj,dest/"raw")
    log("end",task="instance",input=obj["input_sha256"])
    if arm in ("C2","GA"):
        try:search(flow,dest,arm)
        except Found as e:genetic(flow,dest,rep,*e.args)
        result=dict(stop="natural")
        p=dest/"search/run.json"
        if p.exists():result["stop"]=f.read(p)["stop"]
    else:result=literature(flow,arm,dest)
    log("natural",result=result)
def warm():
    meta=f.warm();t=f.T();lib=sys.modules["experiment"]
    from literature import HeatProbe
    HeatProbe(m.RUN[0].template().p).peak()
    meta["seconds"]+=f.T()-t
    return meta
def gate():
    global LEDGER,ACTIVE
    warm();lib=sys.modules["experiment"];t=f.T();f.ORIGIN=t
    dest=OUT/"gate";dest.mkdir(parents=True)
    LEDGER=dest/"pilot.jsonl"
    reg=Path(os.environ["GEN"])/"research/m1i_generalization"
    for obj in m.u2.CASES:
        flow=m.u2.make_flow(m.RUN[0],obj,dest/"identity")
        assert f.digest((reg/"registration/inputs"/obj["input"]).read_bytes())==obj["input_sha256"]
        assert flow.p.n==3*len(flow.p.req) and flow.p.ta==35
    # Compare the exact frozen literature implementation and its unchanged pilot.
    for n in ("experiment.py","literature.py"):
        assert (Path(lib.__file__).parent/n).read_bytes()==(reg.parent/"m1g_literature_comparison"/n).read_bytes()
    import importlib.util
    path=Path(lib.__file__).with_name("pilot.py")
    spec=importlib.util.spec_from_file_location("litpilot",path)
    pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)
    pilot.ROOT=dest;pilot.OUT=dest;pilot.run()
    actual=f.read(dest/"data/pilot.json");ref=f.read(reg.parent/"m1g_literature_comparison/data/pilot.json")
    for a,b in zip(actual["runs"],ref["runs"],strict=True):
        assert [s["plan"] for s in a["stages"]]==[s["plan"] for s in b["stages"]]
    assert actual["fixture_certificates"]==ref["fixture_certificates"]
    # Exercise real callbacks, C2 handoff and a repaired full-chromosome GA generation on neutral L320.
    fixture=m.RUN[0].template();ACTIVE=fixture;folder=dest/"ga";folder.mkdir();LEDGER=folder/"search.jsonl"
    orig=operators
    try:search(fixture,folder,"GA")
    except Found as e:
        import inspect
        ops=orig()
        ev=ops["evolve"]
        ops["evolve"]=lambda *a:ev(*a,max_steps=1)
        bind(genetic,operators=lambda:ops)(fixture,folder,1,*e.args)
    else:raise AssertionError("missing neutral C2 seed")
    for method in ("Zhou-P1","Li-P1","ZQ","LQ"):
        literature(fixture,method,dest/method)
    f.save(dest/"pass.json",dict(verified=True,source=os.environ["GITHUB_SHA"],elapsed=f.T()-t))
def lane(code):
    prep=warm();obj=next(o for o in m.u2.CASES if m.label(o)==code);dest=OUT/code
    order=[]
    for rep in (1,2,3):
        start=(obj["index"]+(rep-1)*2)%7
        order.extend((rep,ARMS[(start+j*(1 if rep!=2 else -1))%7]) for j in range(7))
    f.save(dest/"lane.json",dict(case=obj["case"],warm=prep,order=order,input=obj["input_sha256"],count=len(obj["word"])*60+40*obj["word"].count("H")))
    for rep,arm in order:
        cell=dest/f"r{rep}-{arm}"
        if arm=="Proposed":
            v2.refine_many=online.refine
            v2.cell(obj,rep,"hot",cell)
        else:
            cell.mkdir();f.ORIGIN=f.T()
            rc=f.worker(execute,(obj,arm,rep,cell),f.ORIGIN+60);dt=f.T()-f.ORIGIN
            f.save(cell/"receipt.json",dict(case=obj["case"],rep=rep,version=arm,host=platform.node(),cpu=f.CPU,
                limit=60,cut=60,search_rc=rc,wall_including_supervision=dt,charged_s=min(60,dt),source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"]))
        print(code,rep,arm,flush=True)
if __name__=="__main__":
    gate() if sys.argv[1]=="gate" else lane(sys.argv[1])
