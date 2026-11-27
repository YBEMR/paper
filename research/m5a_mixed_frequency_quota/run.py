"""Supervised one-shot Linux diagnostic. Every cell starts from its verified archived incumbent."""
import csv
import hashlib
import io
import json
import multiprocessing as mp
import os
import platform
import shutil
import signal
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RESULT=ROOT/"results"
CODES=["A02","A06","C10","C11"]
CPUS=sorted(os.sched_getaffinity(0))
for var in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[var]="1"
def save(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".writing")
    tmp.write_text(json.dumps(obj,default=lambda x:x.tolist(),allow_nan=False,separators=(",",":")),encoding="utf8")
    tmp.replace(path)
def read(path):
    return json.loads(path.read_bytes())
def sha(data):
    return hashlib.sha256(data).hexdigest()
def dec(code):
    return tuple((3,k-10) if k>=10 else (2,k) for k in code)
def enc(cfg):
    return bytes(k+(u==3)*10 for u,k in cfg)

def engine(code,folder):
    obj=next(o for o in u2.CASES if o["case"].startswith(code+"_"))
    flow=u2.make_flow(api,obj,folder)
    fourth.CFG["instances"][obj["case"]]=[list(obj["word"]),1,35,1]
    eng=fourth.Engine(obj["case"],folder)
    assert u2.table(eng.p.req)==u2.table(flow.p.req)
    eng.replay=lambda c:state(flow,enc(c))
    return eng,obj

def intake(code,folder, gate=False):
    eng,obj=engine(code,folder)
    folder0=ROOT/"history"/code
    plan=read(folder0/"plan.json");cert=read(folder0/"certificate.json")
    genes=tuple(tuple(row[:2]) for row in plan["rows"][1::3]);r=eng.replay(genes)
    assert r is not None
    built=eng.build(genes,r)
    hist=cert["plan_sha256"];old=cert["metrics"]
    assert sha(u2.raw(plan))==hist
    rows_delta=sum(tuple(a)!=tuple(b) for a,b in zip(plan["rows"],built["rows"]))
    low_delta=len(set(map(tuple,plan["low"]))^set(built["low"]))
    d,tr=eng.cert(genes,r,built)
    assert old["status"]==d["metrics"]["status"]=="SAFE"
    # A divergent physical handoff must be disclosed before any timed cell can start.
    audit=dict(hist=hist,reconstruction=d["plan_sha256"],rows_delta=rows_delta,low_delta=low_delta,
               history_J=old["E_J"],replay_J=d["metrics"]["E_J"],request_hash=obj["input_sha256"],
               trace_hash=sha(tr.tobytes()),switches_equal=u2.raw(cert["switches"])==u2.raw(d["switches"]),
               history_bounds=old["E_bounds"],replay_bounds=d["metrics"]["E_bounds"],
               historical_source= SOURCES[code],window_shapes=[])
    for win,ids in enumerate(eng.groups):
        segs=[]
        for dev in (2,3):
            seq=[genes[i][1] for i in ids if genes[i][0]==dev]
            segs.append(sum(i==0 or seq[i]!=seq[i-1] for i in range(len(seq))))
        audit["window_shapes"].append(segs)
    if gate:save(folder/"identity.json",audit)
    assert (rows_delta,low_delta)==(0,0) and hist==d["plan_sha256"] and audit["switches_equal"],audit
    assert max(old["E_bounds"][0],d["metrics"]["E_bounds"][0])<=min(old["E_bounds"][1],d["metrics"]["E_bounds"][1])
    return eng,(genes,r,d,tr)
SOURCES={"A02":"M3-a certified pool","A06":"U1 NT 180s","C10":"U2 Adaptive2","C11":"M1-j NT-S"}

def endpoint(d):
    m=d["metrics"]
    return dict(plan=d["plan_sha256"],status=m["status"],J=m["E_J"],bounds=m["E_bounds"],
                peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],switches=m["switch_count"],
                reference=d["E35_J"],energy={k:m[k] for k in ("base_J","activity_J","switch_J","external_J","temperature_J")})

def cell(code,method,cpu,folder,start):
    os.sched_setaffinity(0,{cpu})
    assert os.sched_getaffinity(0)=={cpu}
    from planner import generate, projections
    tick=lambda:time.perf_counter()-start
    log=(folder/"events.jsonl").open("a",buffering=1)
    def note(kind,**kwargs):
        log.write(json.dumps(dict(t=tick(),kind=kind,**kwargs),default=lambda x:x.tolist(),separators=(",",":"))+"\n")
    eng,init=intake(code,folder);cfg,r,d,tr=init
    note("intake",**endpoint(d))
    initial=enc(cfg)
    seen={initial:(r,d)}
    def assess(candidate,meta,role):
        key=sha(candidate)
        if candidate in seen:
            nr,out=seen[candidate];note("duplicate",cfg=key,role=role,meta=meta)
            return nr,out
        begin=tick();nr=eng.replay(dec(candidate));dt=tick()-begin
        if nr is None:
            note("timing_reject",cfg=key,replay_s=dt,meta=meta,role=role)
            seen[candidate]=(None,None);return None,None
        before=tick();new,_=eng.cert(dec(candidate),nr);cost=tick()-before
        note("certificate",cfg=key,replay_s=dt,cert_archive_s=cost,kernel_s=new["cert_s"],role=role,meta=meta,**endpoint(new))
        seen[candidate]=(nr,new)
        return nr,new
    if method=="B":
        native_pool=eng.candidates;native_cert=eng.cert;native_replay=eng.replay
        parent=[d];certs={initial:d};turn=[-1];is_pool=[False]
        def capture(c):
            before=tick();v=native_replay(c)
            if is_pool[0]:
                note("native_replay",cfg=sha(enc(c)),legal=v is not None,replay_s=tick()-before,
                     changes=[[i,k] for i,k in enumerate(enc(c)) if anchor[0][i]!=k])
            return v
        anchor=[initial]
        def pool(c,r,mode):
            codebytes=enc(c)
            if parent[0]["plan_sha256"]!=certs[codebytes]["plan_sha256"]:
                parent[0]=certs[codebytes];note("accepted",**endpoint(parent[0]))
            anchor[0]=codebytes;turn[0]+=1;before=tick();is_pool[0]=True
            rows,work=native_pool(c,r,mode);is_pool[0]=False
            note("generation",turn=turn[0],phase_s=tick()-before,work=work,
                 candidates=[dict(ids=x["ids"],device=x["u"],k=x["k"],cfg=sha(enc(x["c"])),ref=x["b"]["e35"]) for x in rows])
            return rows,work
        def certify(c,r,b=None):
            before=tick();v,t=native_cert(c,r,b);certs[enc(c)]=v
            note("certificate",cfg=sha(enc(c)),turn=turn[0],role="adaptive",cert_archive_s=tick()-before,kernel_s=v["cert_s"],**endpoint(v))
            return v,t
        eng.replay=capture;eng.candidates=pool;eng.cert=certify
        result=eng.optimize(init,"adaptive","2");final=result["final"]
        if final["plan_sha256"]!=parent[0]["plan_sha256"]:note("accepted",**endpoint(final))
        note("natural",reason="frozen_optimizer",rounds=result["rounds"]);return
    codebytes=initial
    for turn in range(3):
        before=tick()
        pool,coverage=generate(eng,codebytes,r,method)
        dur=tick()-before
        note("generation",turn=turn,parent=d["plan_sha256"],phase_s=dur,coverage=coverage,
             proposals=[dict(cfg=sha(x),meta=y) for x,y in pool])
        improved=[]
        for c,meta in pool:
            meta=dict(meta,turn=turn,parent=d["plan_sha256"])
            rr,dd=assess(c,meta,"search")
            if dd and dd["metrics"]["status"]=="SAFE" and dd["metrics"]["E_bounds"][1]<d["metrics"]["E_bounds"][0]:
                improved.append((dd["metrics"]["E_bounds"][1],dd["plan_sha256"],c,rr,dd,meta))
        if not improved:
            note("natural",reason="no_strict_improvement",turn=turn);return
        _,_,win,newstate,newcert,meta=min(improved,key=lambda row:row[:2])
        # Log acceptance before validation probes. Probes never compete for the incumbent.
        note("accepted",turn=turn,meta=meta,**endpoint(newcert))
        if method=="E":
            joint=next((row for row in sorted(improved,key=lambda v:v[:2]) if row[-1]["mapping"]!="original"),None)
            if joint:
                _,_,jc,_,jd,jm=joint
                ids=eng.groups[jm["win"]]
                mapcfg,freqcfg=projections(eng,codebytes,jc,jm)
                witnesses=[]
                for role,p in [("mapping_only",mapcfg),("frequency_only",freqcfg)]:
                    _,other=assess(p,dict(parent=d["plan_sha256"],win=jm["win"],patch=p[ids[0]:ids[-1]+1].hex()),role)
                    witnesses.append(endpoint(other) if other else {"status":"TIMING"})
                note("factorial",parent=endpoint(d),joint=endpoint(jd),meta=jm,singles=witnesses)
        codebytes,r,d=win,newstate,newcert
    note("natural",reason="three_rounds")

def launch(code,method,cpu):
    folder=RESULT/code/method;folder.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    proc=mp.get_context("fork").Process(target=cell,args=(code,method,cpu,folder,start));proc.start()
    proc.join(timeout=max(0,59.88-(time.perf_counter()-start)))
    if proc.is_alive():proc.kill();proc.join();status="CAP"
    else:status="NATURAL" if proc.exitcode==0 else "ERROR"
    elapsed=time.perf_counter()-start
    save(folder/"receipt.json",dict(status=status,exitcode=proc.exitcode,wall_s=elapsed,
         cpu=cpu,host=platform.node(),time_limit=60,clock="monotonic wall",single_thread=True))
    print(code,method,status,round(elapsed,3),flush=True)
    if status=="ERROR":raise RuntimeError((code,method,proc.exitcode))

def lane(idx):
    cpu=CPUS[idx%len(CPUS)];os.sched_setaffinity(0,{cpu})
    order="ABCDE"[idx:]+"ABCDE"[:idx]
    for method in order:launch(CODES[idx],method,cpu)

def main():
    global u2,api,fourth,state
    gate_start=time.perf_counter()
    signal.alarm(205)
    os.sched_setaffinity(0,{CPUS[0]})
    sys.path.insert(0,str(ROOT.parent/"u2_adaptive_groups"))
    import common_u2 as u2
    import planner
    api,fourth,_,state=u2.stack()
    for code in CODES:intake(code,RESULT/"gate"/code,True)
    save(RESULT/"gate"/"environment.json",dict(host=platform.node(),cpus=CPUS,platform=platform.platform(),
         python=sys.version,source=os.environ.get("GITHUB_SHA"),run=os.environ.get("GITHUB_RUN_ID"),
         versions={s:__import__(s).__version__ for s in ("numpy","scipy","numba")},wall_s=time.perf_counter()-gate_start))
    signal.alarm(0)
    print("Intake complete, all four physical identities matched.",flush=True)
    for start in range(0,4,len(CPUS)):
        lanes=[]
        for idx in range(start,min(4,start+len(CPUS))):
            p=mp.get_context("fork").Process(target=lane,args=(idx,));p.start();lanes.append(p)
        for p in lanes:p.join()
        if any(p.exitcode for p in lanes):raise RuntimeError("Lane failed, no retry")
if __name__=="__main__":main()
