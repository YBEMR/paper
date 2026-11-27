"""Restore immutable physical schedules, run certified endpoint comparisons and timed mapping tests."""
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import signal
import sys
import tarfile
import time
from pathlib import Path
import numpy as np
from frequency import solve,gate as small_gate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"archive"
OLD=ROOT.parent/"m5b_suffix_capacity/archive"
GEN=Path(os.environ["GEN"])/"research/m1i_generalization/data"
sys.path.insert(0,str(ROOT.parent/"u2_adaptive_groups"))
import common_u2 as u2
from interface import read,save,sha,raw,table
from frequency import data_for

DEV={"A02":"E","A06":"E","C10":"D","C11":"E"}
RUN=None
def label(obj):return obj["case"].split("_")[0]
def endpoint(d):
    m=d["metrics"]
    return dict(plan=d["plan_sha256"],status=m["status"],J=m["E_J"],bounds=m["E_bounds"],
                e35=d["E35_J"],switches=m["switch_count"],slack=m["min_deadline_slack_ms"],peak=max(m["peak_hi"]),
                energy={k:m[k] for k in ("base_J","activity_J","switch_J","external_J","temperature_J")})
def build(obj,folder):
    api,fourth,_,state=RUN
    flow=u2.make_flow(api,obj,folder);case=obj["case"]
    fourth.CFG["instances"][case]=[list(obj["word"]),1,35,1]
    e=fourth.Engine(case,folder)
    assert table(e.p.req)==table(flow.p.req) and all(r["deadline_ms"]-r["release_ms"]==300 and r["deadline_tick"]-r["release_tick"] in (2999,3000) for r in e.p.req)
    e.replay=lambda c:state(flow,u2.encoded(c))
    return e,flow

def genes(plan):return tuple(tuple(z[:2]) for z in plan["rows"][1::3])

def gate_one(obj,src,plan,old,trace_hash):
    dst=OUT/"recovery"/label(obj)/src
    eng,_=build(obj,dst)
    cfg=genes(plan);r=eng.replay(cfg);b=eng.build(cfg,r)
    assert raw(b["rows"])==raw(plan["rows"]) and raw(sorted(b["low"]))==raw(plan["low"])
    d,tr=eng.cert(cfg,r,b)
    assert raw(d["switches"])==raw(old["switches"]) and d["plan_sha256"]==old["plan_sha256"]
    assert d["E35_exact"]==old["E35_exact"] and raw(d["metrics"])==raw(old["metrics"])
    assert sha(tr.tobytes())==trace_hash and d["metrics"]["status"]=="SAFE"
    record=dict(**endpoint(d),trace_sha256=trace_hash,request_sha256=obj["input_sha256"],horizon=eng.p.horizon)
    save(dst/"match.json",record);return record

def correctness():
    start=time.perf_counter();tests=small_gate()
    rawrows=list(csv.DictReader((GEN/"repetitions.csv").open()))
    history=[]
    for obj in u2.CASES:
        code=label(obj);case=obj["case"]
        if code in DEV:
            p=OLD/"endpoints"/code/DEV[code]
            d=read(p/"certificate.json");key=d["plan_sha256"]
            with tarfile.open(OLD/(code+".tar.gz"),"r|gz") as arch:
                for ent in arch:
                    if ent.name=="events.json":
                        tr=json.load(arch.extractfile(ent))[key]["hash"];break
                else:raise ValueError("trace index absent")
            history.append(dict(case=code,source="dev",**gate_one(obj,"dev",read(p/"plan.json"),d,tr)))
        selected={r["method"]:r for r in rawrows if r["case"]==case and r["repeat"]=="1" and r["regime"]=="60s" and r["method"] in ("NT","ZQ-Beam")}
        assert len(selected)==2
        src=GEN/"evidence"/case
        keys={r["plan"] for r in selected.values() if r["plan"]}
        with gzip.open(src/"event_index.csv.gz","rt") as f:
            index={r["plan"]:r for r in csv.DictReader(f) if r["plan"] in keys}
        with tarfile.open(src/"physical.tar.xz","r|xz") as arc:
            bodies={}
            for ent in arc:
                key,name=ent.name.split("/")
                if key in keys:
                    bodies[key,name]=arc.extractfile(ent).read()
                    if len(bodies)==2*len(keys):break
        for method,row in selected.items():
            key=row["plan"]
            if not key or (key,"plan.json") not in bodies or (key,"certificate.json") not in bodies or key not in index:
                history.append(dict(case=code,source=method,missing=row["outcome"] if not key else "missing frozen physical member or trace index"));continue
            body=bodies[key,"plan.json"];cert=bodies[key,"certificate.json"];idx=index[key]
            assert sha(body)==idx["plan_file_sha256"] and sha(cert)==idx["certificate_file_sha256"]
            match=gate_one(obj,method,json.loads(body),json.loads(cert),idx["event_array_sha256"])
            assert match["J"]==float(row["SAFE_J"])
            history.append(dict(case=code,source=method,historical_elapsed_s=float(row["elapsed_s"]),best_at_s=float(row["best_at_s"]),**match))
    save(OUT/"gate.json",dict(tests=tests,history=history,wall_s=time.perf_counter()-start))
def initial(obj,src,eng):
    base=OUT/"recovery"/label(obj)/src
    match=read(base/"match.json");p=base/"evidence"/obj["case"]/match["plan"]
    cfg=genes(read(p/"plan.json"));r=eng.replay(cfg)
    with np.load(p/"trace.npz") as h:tr=h["events"]
    return cfg,r,read(p/"certificate.json"),tr
def unpack(eng,obj,match,p):
    if p is None:return initial(obj,"dev",eng)
    folder=p/"evidence"/obj["case"]/match["plan"]
    if not folder.is_dir():return initial(obj,"dev",eng)
    cfg=genes(read(folder/"plan.json"));r=eng.replay(cfg)
    with np.load(folder/"trace.npz") as h:tr=h["events"]
    return cfg,r,read(folder/"certificate.json"),tr

def keep(a,b):
    return b is not None and b[2]["metrics"]["status"]=="SAFE" and b[2]["metrics"]["E_bounds"][1]<a[2]["metrics"]["E_bounds"][0]
def log(folder,kind,**kw):
    with (folder/"events.jsonl").open("ab") as f:f.write(raw(dict(kind=kind,t=time.perf_counter()-CLOCK,**kw))+b"\n")
def timing(flow,cfg):
    v=flow.ledger(u2.encoded(cfg),0,flow.p.horizon,10000,True,False,True)
    return bool(v[0]),int(v[9]),float(v[1]+flow.base*flow.p.horizon/10000),v
def optimize(eng,flow,cfg,parent,folder,tag,thermal):
    for reserve in (0,13):
        new,stats,dt,obj=solve(eng,cfg,reserve,parent[3] if thermal else None)
        log(folder,"dp",tag=tag,thermal=thermal,reserve=reserve,stats=stats,elapsed_s=dt,objective=obj)
        if new is None:return None
        ok,slack,ref,v=timing(flow,new)
        if not thermal:assert abs(ref-obj)<1e-8,(ref,obj)
        if not ok:
            log(folder,"illegal_post",tag=tag,reserve=reserve,slack_ticks=slack,config=u2.encoded(new).hex(),ref=ref)
            if reserve==0:continue
            return None
        before=time.perf_counter();r=eng.replay(new);assert r is not None
        d,tr=eng.cert(new,r)
        log(folder,"physical",tag=tag,thermal=thermal,reserve=reserve,**endpoint(d),elapsed_s=time.perf_counter()-before,
            changes=sum(a!=b for a,b in zip(new,cfg)))
        return new,r,d,tr
    return None
def write_point(folder,name,result,base):
    cfg,r,d,_=result
    record=dict(**endpoint(d),changes=sum(a!=b for a,b in zip(cfg,base)),t=time.perf_counter()-CLOCK)
    save(folder/(name+".json"),record)
def both(eng,flow,parent,folder,tag,changed=None):
    cfg=changed if changed is not None else parent[0]
    ref=optimize(eng,flow,cfg,parent,folder,tag+"-ordinary",False)
    # On a changed mapping the provisional reference result may be HOT or have
    # higher physical energy. Its real trace can still guide the same mapping.
    reference=ref if ref is not None and (changed is not None or keep(parent,ref)) else parent
    if changed is None:write_point(folder,"ordinary",reference,parent[0])
    adjusted=optimize(eng,flow,cfg,reference,folder,tag+"-thermal",True)
    best=parent
    for result in (ref,adjusted):
        if keep(best,result):best=result
    if changed is None:write_point(folder,"thermal",best,parent[0])
    return best

def fixed(obj,src,arm,folder):
    eng,flow=build(obj,folder);start=initial(obj,src,eng)
    write_point(folder,"seed",start,start[0])
    if arm=="adaptive":
        native=eng.cert
        def capture(c,r,b=None):
            d,tr=native(c,r,b);log(folder,"native",**endpoint(d));return d,tr
        eng.cert=capture
        out=eng.optimize(start,"adaptive","2");save(folder/"native.json",out)
        key=out["final"]["plan_sha256"]
        best=unpack(eng,obj,endpoint(out["final"]),folder) if key!=start[2]["plan_sha256"] else start
        write_point(folder,"final",best,start[0])
    else:
        best=both(eng,flow,start,folder,src);write_point(folder,"final",best,start[0])

def devbest(obj,eng,thermal_only=False):
    base=initial(obj,"dev",eng);best=base
    for arm in (["dp"] if thermal_only else ["dp","adaptive"]):
        p=OUT/"stage1"/label(obj)/arm
        for name in ("ordinary","thermal","final"):
            f=p/(name+".json")
            if f.exists():
                r=unpack(eng,obj,read(f),p)
                if keep(best,r):best=r
    return best

def screen(eng,flow,parent,folder,turn):
    code=bytearray(u2.encoded(parent[0]));by={True:[],False:[]}
    base=parent[2]["E35_J"]
    with gzip.open(folder/("screen-"+str(turn)+".jsonl.gz"),"wt") as f:
        for i,x in enumerate(code):
            scans=[]
            for b in (range(10) if x>=10 else range(10,13)):
                code[i]=b
                v=flow.ledger(bytes(code),0,eng.p.horizon,10000,True,False,True)
                tail_over=max(int(v[2][j])+5*int(v[3][j]!=0)-eng.p.horizon for j in (0,1))
                post_over=int(np.max(v[6]+flow.args[4]))-eng.p.horizon
                gap=max(0,-int(v[9]),tail_over,post_over)
                # The frozen ledger's extrapolated energy for a horizon overrun
                # is undefined. Archive the timing outcome, exclude that OPP's score.
                e35=float(v[1]+flow.base*eng.p.horizon/10000) if tail_over<=0 and post_over<=0 else None
                scans.append(dict(code=b,feasible=bool(v[0]),max_late_ticks=max(0,-int(v[9])),gap_ticks=gap,e35=e35))
            code[i]=x
            f.write(json.dumps(dict(request=i,opps=scans),separators=(",",":"))+"\n")
            valid=any(s["feasible"] for s in scans)
            possible=[s for s in scans if s["e35"] is not None and (not valid or s["feasible"])]
            if not possible:continue
            candidate=min(possible,key=lambda x:(x["e35"],x["gap_ticks"],x["code"]))
            gain=base-candidate["e35"]
            if valid or gain>1e-9:
                by[valid].append(dict(request=i,window=eng.p.req[i]["release_tick"]//10000,gain=gain,
                    gap=candidate["gap_ticks"],code=candidate["code"],direct=valid))
    pools={}
    for valid,rows in by.items():
        shortlist=[];wins=set()
        for row in sorted(rows,key=lambda x:(-x["gain"],x["gap"],x["request"])):
            if row["window"] not in wins:
                shortlist.append(row);wins.add(row["window"])
                if len(wins)==4:break
        pools[valid]=shortlist
    log(folder,"screen",turn=turn,eligible=[len(by[True]),len(by[False])],pools=[pools[True],pools[False]])
    return pools

def counter(eng,flow,parent,folder,i,joint,tag):
    key=parent[2]["plan_sha256"]
    if not hasattr(eng,"m6_counter"):eng.m6_counter={}
    if key not in eng.m6_counter:eng.m6_counter[key]=both_counter(eng,flow,parent,folder,tag)
    only=eng.m6_counter[key]
    c=list(parent[0]);src=c[i][0];out=[]
    for k in range(3 if src==2 else 10):
        c[i]=(5-src,k);cfg=tuple(c);ok,s,ref,_=timing(flow,cfg)
        if ok:
            r=eng.replay(cfg);d,_=eng.cert(cfg,r);out.append(dict(k=k,**endpoint(d)))
        else:out.append(dict(k=k,status="TIMING",slack_ticks=s,e35=ref))
    log(folder,"factorial",tag=tag,request=i,parent=endpoint(parent[2]),freq_only=endpoint(only[2]),direct=out,joint=endpoint(joint[2]))
def both_counter(eng,flow,parent,folder,tag):
    # Same two stages as fixed-frequency refinement, without writing named endpoints.
    a=optimize(eng,flow,parent[0],parent,folder,tag+"-same-map-reference",False)
    best=a if keep(parent,a) else parent
    b=optimize(eng,flow,parent[0],best,folder,tag+"-same-map-thermal",True)
    return b if keep(best,b) else best

def mapping(obj,arm,folder):
    eng,flow=build(obj,folder);parent=devbest(obj,eng,arm=="regression");base=parent[0]
    write_point(folder,"seed",parent,base);write_point(folder,"final",parent,base)
    for turn in range(1 if arm=="regression" else 2):
        if arm=="regression":
            picks=[dict(request=i,code=10 if base[i][0]==2 else 0) for i in (399,401,0,195)]
        else:
            pools=screen(eng,flow,parent,folder,turn)
            first,second=pools[True],pools[False]
            picks=first if arm=="direct" else [r for j in range(4) for pool in (first,second) for r in pool[j:j+1]][:4]
        log(folder,"nominated",turn=turn,picks=picks,parent=endpoint(parent[2]))
        best=parent
        for row in picks:
            i=row["request"];cfg=list(parent[0]);cfg[i]=(5-cfg[i][0],row["code"]%10)
            tag=f"{turn}-{i}"
            joint=both(eng,flow,parent,folder,tag,tuple(cfg))
            log(folder,"joint",tag=tag,request=i,**endpoint(joint[2]))
            if keep(parent,joint):
                counter(eng,flow,parent,folder,i,joint,tag)
                if keep(best,joint):
                    best=joint
                    if arm!="regression":write_point(folder,"final",best,base)
        if best is parent:break
        parent=best
