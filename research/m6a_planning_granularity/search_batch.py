"""Use frozen anytime loop with an external cap and durable, per-physical-call receipts."""
import signal
import time
import traceback
from granularity_runtime import *

def online(code, arm, folder, pipe):
    c=flows[code]
    set_arm(c,arm)
    c.eng.out=folder/"native/physical"
    journal=(folder/"journal.jsonl").open("ab",buffering=0)
    traces=(folder/"candidates.jsonl").open("ab",buffering=0)
    totals={"heat_s":0.}
    propagate=c.propagate
    def timed_heat(*args):
        before=perf_counter()
        try:
            return propagate(*args)
        finally:
            totals["heat_s"]+=perf_counter()-before
    c.propagate=timed_heat
    start=perf_counter()
    def emit(kind,**kw):
        journal.write(p1.raw(dict(kind=kind,time_s=perf_counter()-start,**kw))+b"\n")
    def record(r):
        cert=r["cert"]
        emit("certificate",rank=r["rank"],width=r["width"],config=r["id"],plan=cert["plan_sha256"],
             end_s=r["end_s"],begin_s=r["start_s"],prediction=r["prediction"],E35_J=cert["E35_J"],
             physics_s=cert["cert_s"],metrics=cert["metrics"])
    c.on_cert=record
    c.on_call=lambda w,r,k,t:emit("call",width=w,rank=r,config=k,begin_s=t)
    class Actions(list):
        pass
    class Groups(list):
        def __init__(self,actions,j,w):
            self.actions,self.j,self.w=actions,j,w
            super().__init__()
        def append(self,entry):
            # The action list contains exactly this (parent, OPP-pair) group.
            traces.write(p1.raw([self.w,entry,self.actions,totals["heat_s"]])+b"\n")
            self.actions.clear()
            super().append(entry)
    def observe(c,j,parents,method,t,d,meta):
        w=meta["width"]
        if j==0:
            emit("build",width=w)
        emit("begin_layer",width=w,layer=j+1,heat_s=totals["heat_s"])
        actions=Actions()
        log=dict(actions=actions,groups=Groups(actions,j,w))
        pool,complete=e.expand(c,j,parents,method,t,d,log)
        emit("end_layer",width=w,layer=j+1,valid=len(pool),complete=complete,heat_s=totals["heat_s"])
        return pool,complete
    def builder(method):
        bound=adapter.h.with_binding(e.build,expand=observe)
        def build(*args):
            ordered=bound(*args)
            emit("build_end",width=args[2],terminal=len(ordered),heat_s=totals["heat_s"])
            if ordered:
                traces.write(p1.raw({"width":args[2],"terminal_order":[s["id"] for s in ordered],
                                     "beam":args[-1]["beam"]})+b"\n")
            return ordered
        return build,{}
    execute=adapter.h.with_binding(runner.timed_run,builder=builder)
    start=perf_counter()
    os.write(pipe,str(start).encode())
    os.close(pipe)
    execute(c,"NT",folder/"native",60.)
    emit("finished",heat_s=totals["heat_s"])

def cell(code,arm,core):
    folder=OUT/"formal"/code/arm
    folder.mkdir(parents=True,exist_ok=False)
    recv,send=os.pipe()
    pid=os.fork()
    if pid==0:
        os.close(recv)
        try:
            online(code,arm,folder,send)
        except BaseException:
            traceback.print_exc()
            os._exit(2)
        os._exit(0)
    os.close(send)
    marker=os.read(recv,64)
    os.close(recv)
    if not marker:
        os.waitpid(pid,0)
        raise RuntimeError("child failed before start")
    begin=float(marker)
    until=begin+60
    status="NATURAL"
    while True:
        child,code_status=os.waitpid(pid,os.WNOHANG)
        if child:
            assert os.waitstatus_to_exitcode(code_status)==0, (code,arm,code_status)
            break
        remaining=until-perf_counter()
        if remaining<=.008:
            os.kill(pid,signal.SIGKILL)
            os.waitpid(pid,0)
            status="HARD_CAP"
            break
        time.sleep(min(.04,max(.0005,remaining-.008)))
    used=perf_counter()-begin
    save(folder/"receipt.json",dict(core=core,host=os.uname().nodename,limit_s=60,
         status=status,wall_observed_s=used,kill_margin_s=.008))
    print("CELL",code,arm,status,round(used,3),flush=True)

def run():
    # All methods for each stream share one physical runner and logical core.
    cores=orig_cores[:min(6,len(orig_cores))]
    children=[]
    for i,core in enumerate(cores):
        pid=os.fork()
        if pid:
            children.append(pid)
            continue
        try:
            os.sched_setaffinity(0,{core})
            for idx in range(i,len(CODES),len(cores)):
                order=list(ARMS)
                for arm in order[idx%4:]+order[:idx%4]:
                    cell(CODES[idx],arm,core)
        except BaseException:
            traceback.print_exc()
            os._exit(2)
        os._exit(0)
    statuses=[os.waitpid(pid,0)[1] for pid in children]
    assert all(s==0 for s in statuses), statuses

