"""Two from-empty routes sharing the frozen native search, endpoints and clock."""
import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
import multiprocessing as mp
import os
import platform
import signal
import sys
import time
from pathlib import Path
T=time.perf_counter
ROOT=Path(__file__).resolve().parent
PREV=ROOT.parent/"m6a_global_frequency_mapping"
OUT=ROOT/"archive"
CPU=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{CPU})
sys.path.insert(0,str(PREV))
spec=importlib.util.spec_from_file_location("fixed_m6a_global_adapter",PREV/"experiment.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import numpy as np
raw=m.u2.raw;save=m.save;read=m.read
def digest(b):return hashlib.sha256(b).hexdigest()
def readlog(p):
    if not p.exists():return []
    with p.open("rb") as f:return [json.loads(b) for b in f if b.endswith(b"}\n")]
def log(p,event,**fields):
    with p.open("ab",buffering=0) as f:
        f.write(raw(dict(t=T()-ORIGIN,event=event,**fields))+b"\n")
def arm_alarm(end):
    remaining=end-T()
    if remaining<=0:os._exit(90)
    signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.setitimer(signal.ITIMER_REAL,remaining)
def strict(new,old):
    return new and new["status"]=="SAFE" and (not old or new["bounds"][1]<old["bounds"][0])
def best(rows,cap=60):
    winner=None
    for e in rows:
        if e["event"]=="certificate" and e["t"]<=cap and strict(e["point"],winner["point"] if winner else None):winner=e
    return winner
def warm():
    started=T();m.RUN=m.u2.stack()
    api,fourth,runner,_=m.RUN
    # Only S32 and L320 are used to warm source-independent kernels.
    warmdir=Path(os.environ["U1_OUT"])/"neutral"
    eng=api.e.p1.Engine("S32",warmdir);eng.cert(*eng.construct("quota",1)[0])
    flow=api.template()
    cfg=bytes([0])*len(flow.p.req)
    flow.ledger(cfg,0,flow.p.horizon,10000,True,True,True)
    assert os.sched_getaffinity(0)=={CPU}
    return dict(seconds=T()-started,neutral=["S32","L320"],core=CPU,host=platform.node(),python=sys.version,
                versions={k:__import__(k).__version__ for k in ("numpy","scipy","numba")})
def bind(clock_start,until,builder):
    runner=m.RUN[2]
    src=inspect.getsource(runner.timed_run)
    for old,new in (("start=perf_counter();deadline=start+budget","start=clock_start;deadline=until()"),
                    ("end=perf_counter()","end=perf_counter();deadline=until()")):
        assert src.count(old)==1
        src=src.replace(old,new)
    ns=dict(runner.timed_run.__globals__,clock_start=clock_start,until=until,builder=builder)
    exec(compile(src,"<frozen anytime loop with the common absolute deadline>","exec"),ns)
    return ns["timed_run"]
def search(obj,version,dest):
    arm_alarm(ORIGIN+60)
    p=dest/"search.jsonl"
    log(p,"begin",task="instance")
    api=m.RUN[0];flow=m.u2.make_flow(api,obj,dest/"raw")
    log(p,"end",task="instance",request_sha=obj["input_sha256"])
    limit=[60];context=[None];count=[0];status=[None]
    original=flow.certify
    def certify(cfg):
        log(p,"begin",task="search_cert")
        d,tr=original(cfg);pt=m.endpoint(d)
        log(p,"certificate",point=pt,width=context[0],candidate=digest(cfg),kernel_s=d["cert_s"])
        if pt["status"]=="SAFE" and status[0] is None:
            status[0]=True
            if version=="integrated" and T()<ORIGIN+55:
                limit[0]=55;arm_alarm(ORIGIN+55)
        count[0]+=1
        return d,tr
    flow.certify=certify
    def wrapper(name):
        build,progress=m.RUN[2].builder(name)
        def observed(c,method,width,start,deadline,stage):
            context[0]=width
            log(p,"begin",task="construct",width=width)
            pool=build(c,method,width,start,deadline,stage)
            log(p,"end",task="construct",width=width,terminals=len(pool))
            return pool
        return observed,progress
    native=bind(ORIGIN,lambda:ORIGIN+limit[0],wrapper)
    native(flow,"NT",dest/"search",60)
    log(p,"natural",count=count[0])
def handoff(obj,dest,physical,pt):
    eng,flow=m.build(obj,dest)
    src=physical/pt["plan"]
    plan=read(src/"plan.json");d=read(src/"certificate.json")
    assert digest((src/"plan.json").read_bytes().strip())==d["plan_sha256"]==pt["plan"]
    assert m.u2.raw(m.endpoint(d))==m.u2.raw(pt) and pt["status"]=="SAFE"
    cfg=m.genes(plan);r=eng.replay(cfg);b=eng.build(cfg,r)
    assert raw(b["rows"])==raw(plan["rows"]) and raw(sorted(b["low"]))==raw(plan["low"])
    assert raw(b["switches"])==raw(d["switches"])
    with np.load(src/"trace.npz") as f:tr=f["events"]
    assert np.array_equal(b["ev"],tr[:,:14])
    return eng,flow,(cfg,r,d,tr)
def refine(obj,dest,seed):
    arm_alarm(ORIGIN+60);m.CLOCK=ORIGIN
    p=dest/"refine.jsonl";pt=seed["point"]
    log(p,"begin",task="handoff",plan=pt["plan"])
    eng,flow,init=handoff(obj,dest/"handoff",dest/"search/physical/evidence"/obj["case"],pt)
    log(p,"end",task="handoff")
    current=init
    for stage,thermal in (("ordinary",False),("thermal",True)):
        eng.out=dest/stage;old_cert=eng.cert
        def measured(*args,**kwargs):
            log(p,"begin",task="dp_cert",stage=stage)
            d,tr=old_cert(*args,**kwargs)
            log(p,"end",task="dp_cert",stage=stage,kernel_s=d["cert_s"])
            return d,tr
        eng.cert=measured
        log(p,"begin",task="refinement",stage=stage)
        result=m.optimize(eng,flow,init[0],current,dest,stage,thermal)
        eng.cert=old_cert
        if result is not None:
            assert all(a[0]==b[0] for a,b in zip(init[0],result[0]))
            log(p,"certificate",point=m.endpoint(result[2]),stage=stage)
            if m.keep(current,result):current=result
        log(p,"stage_end",stage=stage,attempt=None if result is None else result[2]["plan_sha256"],incumbent=current[2]["plan_sha256"])
    log(p,"natural")
def worker(fn,args,until):
    child=mp.get_context("fork").Process(target=fn,args=args)
    child.start();child.join(max(0,until-T()))
    if child.is_alive():child.kill();child.join()
    stop=T()-ORIGIN
    if child.exitcode not in (0,-signal.SIGALRM,-signal.SIGKILL,90):
        raise RuntimeError((fn.__name__,child.exitcode))
    return dict(rc=child.exitcode,supervisor_t=stop)
def cell(obj,rep,version,dest):
    global ORIGIN
    dest.mkdir(parents=True,exist_ok=False)
    ORIGIN=T()
    search_rc=worker(search,(obj,version,dest),ORIGIN+60)
    # One inexpensive tail record per completed certificate; scanning large histories
    # for postprocessing is charged whenever it affects the timed decision.
    records=readlog(dest/"search.jsonl");first=next((r for r in records if r["event"]=="certificate" and r["point"]["status"]=="SAFE" and r["t"]<=60),None)
    refine_allowed=version=="integrated" and first and first["t"]<55
    cut=55 if refine_allowed else 60
    seed=best(records,cut);rr=None
    if refine_allowed and seed is not None and T()<ORIGIN+60:
        rr=worker(refine,(obj,dest,seed),ORIGIN+60)
    stop=T()-ORIGIN
    save(dest/"receipt.json",dict(case=obj["case"],rep=rep,version=version,host=platform.node(),cpu=CPU,
        limit=60,cut=cut,search_rc=search_rc,refine_rc=rr,wall_including_supervision=stop,
        charged_s=min(60,stop),source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"]))
    print(obj["case"],rep,version,round(min(stop,60),3),seed["point"]["J"] if seed else None,flush=True)
def gate():
    global ORIGIN
    ORIGIN=T();w=warm();m.CLOCK=ORIGIN
    registered=Path(os.environ["GEN"])/"research/m1i_generalization/registration"
    for obj in m.u2.CASES:
        p=registered/"inputs"/obj["input"]
        assert p.read_bytes()==(m.u2.REG/"inputs"/obj["input"]).read_bytes() and digest(p.read_bytes())==obj["input_sha256"]
    assert (registered/"cases.json").read_bytes()==(m.u2.REG/"cases.json").read_bytes()
    pins={p:h for h,p in (l.split("  ",1) for l in (PREV/"SHA256SUMS").read_text().splitlines())}
    for n in ("experiment.py","frequency.py","dp.cpp"):assert digest((PREV/n).read_bytes())==pins[n]
    # Confirm the original search wrapper still matches the two exact clock edits.
    bind(ORIGIN,lambda:ORIGIN+60,m.RUN[2].builder)
    obj=next(o for o in m.u2.CASES if m.label(o)=="A06")
    root=OUT/"gate";root.mkdir(parents=True)
    e,flow=m.build(obj,root);old=ROOT.parent/"m5b_suffix_capacity/archive/endpoints/A06/E"
    plan=read(old/"plan.json");d=read(old/"certificate.json");cfg=m.genes(plan)
    actual,tr=flow.certify(m.u2.encoded(cfg))
    assert raw(actual["metrics"])==raw(d["metrics"]) and actual["plan_sha256"]==d["plan_sha256"]
    eng,flow,init=handoff(obj,root/"handoff",root/"evidence"/obj["case"],m.endpoint(d))
    result=m.both(eng,flow,init,root,"gate")
    with (PREV/"archive/endpoints.csv").open() as f:
        expected={r["stage"]:r for r in csv.DictReader(f) if r["cell"]=="stage1/A06/dp"}
    for stage in ("ordinary","thermal"):
        got=read(root/(stage+".json"))
        assert got["plan"]==expected[stage]["plan"] and got["J"]==float(expected[stage]["J"])
    save(root/"gate.json",dict(warm=w,passed=True,initial=m.endpoint(d),result=m.endpoint(result[2]),wall_s=T()-ORIGIN,
        nt=os.environ["NT_SHA"],generalization=os.environ["GEN_SHA"],dp=os.environ["DP_SHA"]))
def lane(code):
    prep=warm();obj=next(r for r in m.u2.CASES if m.label(r)==code);d=OUT/code
    schedule=[]
    for rep in (1,2,3):
        arms=["original","integrated"]
        if (obj["index"]+rep-1)%2:arms.reverse()
        for v in arms:schedule.append([rep,v])
    save(d/"lane.json",dict(warm=prep,order=schedule,case=obj["case"],input_sha=obj["input_sha256"],source=os.environ["GITHUB_SHA"]))
    for rep,v in schedule:cell(obj,rep,v,d/f"r{rep}-{v}")
if __name__=="__main__":
    if sys.argv[1]=="gate":gate()
    else:lane(sys.argv[1])
