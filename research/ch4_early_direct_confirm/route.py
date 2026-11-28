"""A synchronous yield after a committed search receipt. Only the child changes frequencies."""
import inspect
import os
import signal
import time
from pathlib import Path
import transfer as tr

f,m,online=tr.f,tr.m,tr.paired.online
T=time.perf_counter
FROZEN_MAIN=tr.main

def reserve(seeds, used, identity):
    remaining=[s for s in seeds if identity(s["point"]["plan"])!=used]
    hot=[s for s in remaining if s["point"]["status"]=="HOT"]
    assert len(hot)<=1
    safe=[s for s in remaining if s["point"]["status"]=="SAFE"]
    result=safe[:3-len(hot)]+hot
    assert len({identity(s["point"]["plan"]) for s in result}|{used})==1+len(result)<=4
    return result

class Coordination:
    def __init__(self,obj,folder,fixture=None):
        self.obj=obj;self.folder=folder;self.fixture=fixture
        self.events=folder/"pause.jsonl";self.early=folder/"early.jsonl"
        self.physical=folder/"search/physical/evidence"/obj["case"]
        self.first_seen=False;self.incumbent=None
        self.raw_log=f.log

    def keep(self,p):
        if f.strict(p,self.incumbent):self.incumbent=p

    def early_job(self,point,deadline):
        f.arm_alarm(deadline)
        dest=self.folder/"early";dest.mkdir()
        def emit(event,**kw):
            if "stage" in kw:kw["stage"]="early/"+kw["stage"]
            self.raw_log(self.early,event,**kw)
        emit("begin",task="handoff",seed=point["plan"])
        if self.fixture=="fault":raise RuntimeError("injected neutral handoff failure")
        if self.fixture=="timeout":time.sleep(4)
        eng,flow,seed=f.handoff(self.obj,dest/"handoff",self.physical,point)
        emit("end",task="handoff")
        native=eng.cert
        def measured(*a,**kw):
            emit("begin",task="dp_cert")
            d,trace=native(*a,**kw)
            emit("end",task="dp_cert",kernel_s=d["cert_s"])
            return d,trace
        eng.cert=measured
        tr.cold.direct(eng,flow,seed,dest,emit)

    def after_record(self,record,ordered,seen,deadline):
        point=m.endpoint(record["cert"]) if not self.first_seen else None
        if not point or point["status"]!="SAFE":return
        self.first_seen=True
        event=f.readlog(self.folder/"search.jsonl")[-1]
        assert event["event"]=="certificate" and point==event["point"]
        if event["t"]>14:return
        start=T();end=min(start+3,f.ORIGIN+17)
        identity=(id(ordered),id(seen),len(ordered),len(seen),record["id"],deadline)
        snapshot=(tuple(s["id"] for s in ordered),frozenset(seen)) if self.fixture else None
        assert record["id"] in seen and deadline==f.ORIGIN+17
        self.raw_log(self.events,"start",start_s=start-f.ORIGIN,until=end-f.ORIGIN,seed=point["plan"],search_delivery_s=event["t"],
            width=record["width"],rank=record["rank"],seen=len(seen),terminals=len(ordered),cert_s=record["cert_s"],pid=os.getpid())
        try:
            rc=f.worker(self.early_job,(point,end),end)["rc"]
        except RuntimeError as exc:
            rc=str(exc)
        early=f.best(f.readlog(self.early),end-f.ORIGIN)
        if early:self.keep(early["point"])
        assert identity==(id(ordered),id(seen),len(ordered),len(seen),record["id"],deadline)
        if snapshot is not None:assert snapshot==(tuple(s["id"] for s in ordered),frozenset(seen))
        self.raw_log(self.events,"resume",seed=point["plan"],rc=rc,pid=os.getpid(),search_deadline=deadline-f.ORIGIN,
            elapsed_s=T()-start,incumbent=self.incumbent["plan"],seen=len(seen),rank=record["rank"],width=record["width"])

    def late_best(self,events):
        trace=f.readlog(self.events)
        if not trace:return f.best(events,17)["point"]
        early=[e for e in f.readlog(self.early) if e["t"]<=trace[0]["until"] and e["event"]=="certificate"]
        combined=[e for e in events if e["t"]<=17 and e["event"]=="certificate"]+early
        return f.best(sorted(combined,key=lambda e:e["t"]),17)["point"]

    def install(self):
        native_bind=f.bind
        def bind(start,until,builder):
            original=native_bind(start,until,builder)
            src=inspect.getsource(m.RUN[2].timed_run)
            for old,new in (("start=perf_counter();deadline=start+budget","start=clock_start;deadline=until()"),
                            ("end=perf_counter()","end=perf_counter();deadline=until()"),
                            ("            if new>=2*width","            after_record(records[-1],ordered,seen,deadline)\n            if new>=2*width")):
                assert src.count(old)==1
                src=src.replace(old,new)
            ns=dict(original.__globals__,after_record=self.after_record)
            exec(compile(src,"<frozen search with certificate-boundary yield>","exec"),ns)
            return ns["timed_run"]
        f.bind=bind
        native_short=tr.short_clock;native_select=online.select;native_refine=online.refine
        def shortened(fn,cap):
            result=native_short(fn,cap)
            if fn is native_select:
                def select(events,physical,horizon):
                    seeds,meta=result(events,physical,horizon)
                    pauses=f.readlog(self.events)
                    if not pauses:return seeds,meta
                    def ident(k):return online.v2.identity(f.read(physical/k/"plan.json"))
                    used=ident(pauses[0]["seed"])
                    limited=reserve(seeds,used,ident)
                    return limited,dict(meta,original_seeds=meta["seeds"],seeds=[s["point"]["plan"] for s in limited],
                                        early_mapping=f.digest(used))
                return select
            if fn is native_refine:
                src=inspect.getsource(fn)
                for old,new in (("f.ORIGIN+60","f.ORIGIN+20"),('global_best=seeds[0]["point"]','global_best=late_best(events)')):
                    assert src.count(old)==1
                    src=src.replace(old,new)
                ns=dict(fn.__globals__,late_best=self.late_best)
                exec(compile(src,"<frozen tail with cross-stage incumbent>","exec"),ns)
                return ns["refine"]
            return result
        tr.short_clock=shortened
        def logged(path,event,**kw):
            self.raw_log(path,event,**kw)
            if event=="certificate" and path==self.folder/"search.jsonl":self.keep(kw["point"])
        f.log=logged

def solve(code,arm,cap,dest,fixture=None):
    if arm=="B":
        obj=next(o for o in m.u2.CASES if m.label(o)==code)
        Coordination(obj,dest,fixture).install()
    FROZEN_MAIN(code,"A" if arm=="R" else "B",cap,dest)
