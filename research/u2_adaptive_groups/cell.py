"""One supervised timed scientific call. Native optimizers own the candidate selection and acceptance."""
import os
import sys
import time
from time import perf_counter
from types import FunctionType,MethodType
from common_u2 import *

def worker(idx,repeat,method,folder):
    obj=CASES[idx]
    folder.mkdir(parents=True,exist_ok=False)
    st=stack()
    api,fourth,runner,state=st
    assert len(os.sched_getaffinity(0))==1
    save(folder/"ready.json",{"cpu":sorted(os.sched_getaffinity(0))})
    while not (folder/"clock.json").exists():time.sleep(.002)
    ctl=read(folder/"clock.json");start=ctl["start"];charge=ctl["charge"]
    def elapsed():return perf_counter()-start+charge
    def certificate(d,tick,kind,width=None,turn=None):
        m=d["metrics"]
        append(folder/"certs.jsonl",dict(t=elapsed(),began=tick,J=m["E_J"],bounds=m["E_bounds"],status=m["status"],
            plan=d["plan_sha256"],E35=d["E35_J"],activity=m["activity_J"],base=m["base_J"],thermal=m["temperature_J"],
            peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],switches=m["switch_count"],switch_J=m["switch_J"],
            kernel_s=d["cert_s"],kind=kind,width=width,turn=turn))
    if method=="NT":
        f=make_flow(api,obj,folder)
        width=[None]
        builder=runner.builder
        def observed_builder(name):
            build,progress=builder(name)
            def observed(case,arm,w,begin,deadline,stage):
                width[0]=w
                append(folder/"widths.jsonl",dict(width=w,event="start",t=elapsed()))
                ordered=build(case,arm,w,begin,deadline,stage)
                append(folder/"widths.jsonl",dict(width=w,event="ready",t=elapsed(),terminals=len(ordered)))
                return ordered
            return observed,progress
        runner.builder=observed_builder
        native=f.certify
        def observed(config):
            tick=elapsed();d,tr=native(config);certificate(d,tick,"NT",width=width[0]);return d,tr
        f.certify=observed
        runner.timed_run(f,"NT",folder/"search",max(.001,60-elapsed()))
    else:
        if method=="Q4":
            fourth.CFG["instances"][obj["case"]]=[list(obj["word"]),1,35,1]
            eng=fourth.Engine(obj["case"],folder)
            assert table(eng.p.req)==(REG/"inputs"/obj["input"]).read_bytes()
            cr,meta=eng.construct("quota",4);save(folder/"construction.json",meta)
            if cr is None:
                save(folder/"end.json",dict(status="NO_CONSTRUCTION",t=elapsed()));return
            tick=elapsed();d,tr=eng.cert(*cr);certificate(d,tick,"Q4")
            if d["metrics"]["status"]!="SAFE":
                save(folder/"end.json",dict(status=d["metrics"]["status"],t=elapsed()));return
            init=(*cr,d,tr)
        else:
            seed=read(folder.parent/"seed.json")
            src=folder.parent/"NT/search/physical/evidence"/obj["case"]/seed["plan"]
            tick=elapsed();eng,init=intake(obj,src,folder,st)
            certificate(init[2],tick,"intake")
        native=eng.candidates
        if method=="Single2":
            func=fourth.Engine.candidates
            native=MethodType(FunctionType(func.__code__,dict(func.__globals__,FIXED={1})),eng)
        turn=[-1]
        def pool(c,r,mode):
            turn[0]+=1
            before=elapsed()
            found,work=native(c,r,mode)
            append(folder/"pools.jsonl",dict(turn=turn[0],before_t=before,ready_t=elapsed(),work=work,
                candidates=[dict(ids=x["ids"],length=len(x["ids"]),unit=x["u"],new_opp=x["k"],E35=x["b"]["e35"]) for x in found]))
            return found,work
        eng.candidates=pool
        certify=eng.cert
        def observed(c,r,b=None):
            tick=elapsed();d,tr=certify(c,r,b);certificate(d,tick,"candidate",turn=turn[0]);return d,tr
        eng.cert=observed
        group="fixed" if method in ("Single2","Fixed2") else "adaptive"
        select="union" if method in ("Q4","ThermalUnion") else "2"
        result=eng.optimize(init,group,select)
        save(folder/"rounds.json",result)
    save(folder/"end.json",dict(status="NATURAL",t=elapsed()))

if __name__=="__main__":worker(int(sys.argv[1]),int(sys.argv[2]),sys.argv[3],Path(sys.argv[4]))
