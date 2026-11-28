"""Run the registered neutral admission before releasing any formal cell."""
import json
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"ch4_quota_warm_confirm"))
import warm_confirm as warm
from warm_confirm import control, ROOT, T
CASES=("A02","B07","C11","C12")

def neutral(tr,dest,mode):
    api=tr.m.RUN[0]
    reg=dest/"registration"
    (reg/"inputs").mkdir(parents=True)
    label="NEUTRAL_LL_T35"
    flow=api.Flow("LL",35,label,reg)
    data=tr.m.u2.table(flow.p.req)
    (reg/"inputs/neutral.csv").write_bytes(data)
    obj=dict(case=label,word="LL",ambient=35,horizon_ticks=flow.p.horizon,requests=len(flow.p.req),
             input="neutral.csv",input_sha256=tr.f.digest(data),windows=flow.windows)
    control.save(reg/"input.json",obj)
    api.REG=tr.m.u2.REG=reg
    tr.m.u2.CASES=[obj]
    # Fixed terminal prefix only in neutral cells; formal construction is untouched.
    count=0
    native=tr.f.log
    def bounded(path,event,**kwargs):
        nonlocal count
        native(path,event,**kwargs)
        if path==dest/"search.jsonl" and event=="certificate":
            count+=1
            if count==3:raise SystemExit(0)
    tr.f.log=bounded
    if mode=="late":os.environ["CELL_START"]=str(T()-14.03)

def dispatch(code,arm,cap,dest):
    import route
    fixture=os.environ.get("EARLY_FIXTURE")
    if fixture:neutral(route.tr,dest,fixture)
    route.solve(code,arm,cap,dest,fixture)

def check_gate():
    import route
    f=route.f
    runs={}
    for name,arm,mode in (("original","A","late"),("untriggered","B","late"),("real","B","real"),
                          ("timeout","B","timeout"),("fault","B","fault")):
        dst=ROOT/"admission"/name
        before=control.spent()
        if before+23>238:raise RuntimeError("insufficient preparation CPU")
        receipt=control.monitored(dst,["NEUTRAL",arm,"20",str(dst)],21,238,{"EARLY_FIXTURE":mode})
        receipt["cpu_s"]=control.spent()-before
        control.save(dst/"receipt.json",receipt)
        assert receipt["reason"]=="natural",(name,receipt)
        search=[e for e in f.readlog(dst/"search.jsonl") if e["event"]=="certificate"]
        tail=f.readlog(dst/"refine.jsonl")
        selection=next(e for e in tail if e.get("task")=="selection" and e["event"]=="end")
        pauses=f.readlog(dst/"pause.jsonl")
        early=f.readlog(dst/"early.jsonl")
        assert len(search)==3 and len({e["candidate"] for e in search})==3,(name,search)
        if mode=="late":
            assert not pauses and search[0]["t"]>14
        else:
            start,resume=pauses
            assert start["pid"]==resume["pid"] and start["seen"]==resume["seen"] and resume["search_deadline"]==17
            assert any(e["t"]>resume["t"] for e in search)
            points=[search[0]]+[e for e in early if e["event"]=="certificate"]
            assert f.best(points,start["until"])["point"]["plan"]==resume["incumbent"]
            assert len(selection["seeds"])<=3 and start["seed"] not in selection["seeds"]
            if mode=="real":assert any(e["event"]=="certificate" and e["point"]["status"]=="SAFE" for e in early)
            if mode in ("timeout","fault"):assert resume["rc"]!=0 and not early[-1]["event"]=="certificate"
        runs[name]=dict(points=[e["point"] for e in search],seeds=selection["seeds"],pause=pauses,
                        cpu_s=receipt["cpu_s"],candidate_hashes=[e["candidate"] for e in search])
    for key in ("points","seeds","candidate_hashes"):assert runs["original"][key]==runs["untriggered"][key],key
    def seed(i):return dict(point=dict(plan=i,status="HOT" if i==4 else "SAFE"))
    assert [s["point"]["plan"] for s in route.reserve([seed(i) for i in (1,2,3,4)],0,lambda x:x)]==[1,2,4]
    control.save(ROOT/"admission.json",dict(passed=True,runs=runs))

def lane(job):
    idx,cpu=job
    os.sched_setaffinity(0,{cpu})
    control.subreaper()
    case=CASES[idx]
    root=ROOT/"formal"/case
    root.mkdir(parents=True)
    count=0
    for rep in (1,2,3):
        order=["A","B"] if (idx+rep)%2 else ["B","A"]
        order.insert((idx+rep)%3,"R")
        for arm in order:
            cap=60 if arm=="R" else 20
            if control.spent()+cap+.25>324:
                control.save(root/"stop.json",dict(reason="CPU reserve",rep=rep,arm=arm))
                return
            dest=root/f"r{rep}-{arm}-{cap}"
            before=control.spent()
            receipt=control.monitored(dest,[case,arm,str(cap),str(dest)],cap,324)
            count+=1
            receipt.update(case=case,rep=rep,arm=arm,order=count,cpu_s=control.spent()-before)
            control.save(dest/"receipt.json",receipt)
            if receipt["reason"] in ("fault","cpu_guard"):raise RuntimeError((case,receipt))
        print("finished",case,rep,flush=True)
    control.save(root/"account.json",dict(cells=count,cpu_s=control.spent()))

def main():
    allocated=sorted(os.sched_getaffinity(0))
    cores=allocated[::2][:4]
    assert len({Path(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read_text() for c in cores})==4
    ROOT.mkdir(exist_ok=False)
    start=T()
    try:
        tr=warm.prepare(cores)
        import route
        assert route.FROZEN_MAIN is tr.main
        native=control.monitored
        control.monitored=FunctionType(native.__code__,dict(native.__globals__,subprocess=SimpleNamespace(Popen=warm.WarmChild)),
                                       native.__name__,native.__defaults__)
        tr.main=dispatch
        check_gate()
    except BaseException:
        control.save(ROOT/"preparation_account.json",dict(passed=False,cpu_s=control.spent(),limit=240,wall_s=T()-start,error=traceback.format_exc()))
        raise
    baseline=control.spent()
    control.save(ROOT/"preparation_account.json",dict(passed=True,cpu_s=baseline,limit=240,wall_s=T()-start))
    assert baseline<=240
    print("admission passed",flush=True)
    os.sched_setaffinity(0,set(allocated))
    begin=T()
    try:
        with ProcessPoolExecutor(4,mp_context=multiprocessing.get_context("fork")) as pool:
            list(pool.map(lane,enumerate(cores)))
    finally:
        actual=control.spent()-baseline
        control.save(ROOT/"formal_account.json",dict(cpu_s=actual,limit=1300,nominal=1200,cores=cores,elapsed_parallel_s=T()-begin))
    assert actual<=1300
if __name__=="__main__":main()
