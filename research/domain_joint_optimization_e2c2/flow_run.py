"""Single-core run owner. The parent alone writes evidence and owns the SAFE incumbent."""
import gzip
import json
import multiprocessing as mp
import pickle
import sys
import time
from pathlib import Path
import psutil
from settings import INITIAL, clock, sha, write

def worker_entry(pipe,cpu):
    psutil.Process().cpu_affinity([cpu])
    from cp_worker import service
    service(pipe)

def apply_delta(plan,entry):
    rows=plan[0].copy()
    for i,r in entry["edits"]:rows[i]=tuple(r)
    return rows,frozenset((set(plan[1])-set(map(tuple,entry["low_drop"])))|set(map(tuple,entry["low_add"])))

class Channel:
    def __init__(self,cpu,log):
        self.cpu=cpu;self.log=log;self.child=None;self.pipe=None

    def open(self,end):
        if self.child is not None:return True
        ctx=mp.get_context("spawn")
        self.pipe,other=ctx.Pipe()
        self.child=ctx.Process(target=worker_entry,args=(other,self.cpu),daemon=True)
        self.child.start();other.close()
        self.log("worker_start",pid=self.child.pid)
        if not self.pipe.poll(max(0,end-clock())):
            self.close(True);return False
        ack=self.pipe.recv()
        assert ack==("ready",),ack
        return True

    def close(self,force=False):
        if self.child is None:return
        pid=self.child.pid
        if not force:
            self.pipe.send(None)
            self.child.join(.12)
        if self.child.is_alive():self.child.terminate()
        self.child.join(.22)
        if self.child.is_alive():self.child.kill();self.child.join(.2)
        assert not self.child.is_alive()
        self.log("worker_exit",pid=pid,code=self.child.exitcode,deadline=force)
        self.child.close();self.pipe.close();self.child=self.pipe=None

    def call(self,op,job,end,receive):
        if not self.open(end):return "INITIALIZATION_DEADLINE"
        if clock()>=end:return "TIME_LIMIT"
        self.pipe.send((op,job))
        while self.pipe.poll(max(0,end-clock())):
            msg=self.pipe.recv()
            if msg[0]=="error":raise RuntimeError(msg[1])
            if msg[0]=="done":return msg[1]
            receive(*msg,end)
            if clock()>=end:break
        self.close(True)
        return "WORKER_DEADLINE"

def run(folder,method,seed,cpu,start,short):
    proc=psutil.Process();proc.cpu_affinity([cpu]);folder.mkdir(parents=True,exist_ok=False)
    from g3_flow import Flow,search
    from base import Problem,archived,changes,key,obj,raw,bins
    from search import Tracker, Expired
    p=Problem("D3");initial,base=archived("D3")
    assert initial==INITIAL==key(p,base) and (p.n,len(p.req))==(2400,800)
    g,deep,cycles=(20,30,2) if short else (180,120,6)
    duration=(40 if short else 1800) if method=="G3" else cycles*(g+deep)
    finish=start+duration
    hist=(folder/"accepted.jsonl").open("wb");events=gzip.open(folder/"events.jsonl.gz","wb",compresslevel=1)
    phases=[];coverage=set();cp_coverage=set();counter=0;stale=0;last=None;last_plan=None
    phase="init";cycle=0;idx=None;origin="initial"
    def event(name,**data):
        events.write(raw(dict(event=name,t=clock()-start,cycle=cycle,phase=phase,it=idx,**data))+b"\n")
    channel=Channel(cpu,event)
    class LoggedTracker(Tracker):
        def consider(self,plan,force=False):
            ident=key(p,plan)
            try:
                result=super().consider(plan,force)
            except Expired:
                event("g3_candidate",sha=ident,status="DEADLINE")
                raise
            event("g3_candidate",sha=ident,status=result["status"] if result else "FILTERED_OR_INVALID",
                  bounds=result["E_bounds"] if result else None)
            return result
    tr=LoggedTracker(p,finish-.9,thermal=True);tr.start=start
    def accepted():
        nonlocal last,last_plan
        if tr.safe is None or tr.safe_plan is last_plan:return
        plan=tr.safe_plan;ident=key(p,plan)
        if ident==last:return
        if last is None:
            patch=dict(full=obj("D3",plan))
        else:
            d=changes(p,last_plan,plan);ids=sorted(set(d["config"])|set(d["moved"]))
            patch=dict(edits=[(i,plan[0][i]) for i in ids],low_drop=d["gap_removed"],low_add=d["gap_added"],
                       cfg=d["config"],moved=d["moved"],scenes=d["scenes"],
                       moved_devices=sorted({plan[0][i][0] for i in d["moved"]}))
        record=dict(t=tr.history[-1][0],before=last,after=ident,metrics=tr.safe,cycle=cycle,phase=phase,
                    it=idx,origin=origin,**patch)
        hist.write(raw(record)+b"\n");hist.flush()
        last,last_plan=ident,plan
    tr.on_change=accepted
    tr.consider(base,force=True)
    assert tr.safe["status"]=="SAFE" and abs(tr.safe["E_J"]-63.39163095183008)<1e-10
    flow=Flow(p,tr,seed)
    def state():
        assert tr.safe_plan is tr.plan and tr.safe is tr.best and key(p,tr.plan)==last
        return dict(sha=last,E=tr.best["E_J"],bounds=tr.best["E_bounds"],steps=flow.steps,
                    rng=sha(pickle.dumps(flow.rng.getstate(),protocol=4)),index=counter,stale=stale)
    def move(item):
        coverage.update(item[1]);event("move",step=flow.steps,anchor=item[0],st=item[1])
    def broad(end):
        nonlocal origin
        origin="g3"
        tr.end=end-.62
        while clock()<tr.end:
            try:flow.step(move)
            except Expired:break

    def subproblem(end):
        nonlocal stale,counter,idx,origin
        idx=counter;before=last;source=tr.plan;metric=tr.best
        local_start=clock();local=min(end-.40,local_start+29.55)
        grants={};ranked=[];stage_best=metric;log=[]
        n=len(bins(p));window=(idx%n+idx//n+seed-101)%n
        def receive(kind,data,deadline):
            nonlocal stage_best
            if kind=="note":
                name=data.pop("event")
                if name=="start":assert data["source"]==before and data["iteration"]==idx and data["window"]==window
                if name in ("selection","core_region"):
                    tasks=data.get("ids",data.get("st",[]));coverage.update(tasks);cp_coverage.update(tasks)
                event(name,**data)
                return
            if kind=="rights":
                if data["at"]<=deadline:
                    grant_type="hint" if data["stage"]=="hint" else "cp"
                    grants.setdefault(grant_type,data)
                return
            assert kind=="cert" and data["source"]==before
            m=data["metrics"];on_time=data["at"]<=deadline and clock()<local
            event("certificate",sha=data["sha"],stage=data["stage"],source=before,metrics=m,
                  at=data["at"],on_time=on_time,cached=data["cached"],edits=data["edits"],
                  low_add=data["low_add"],low_drop=data["low_drop"])
            if on_time and m["status"]=="SAFE" and m["E_bounds"][1]<stage_best["E_bounds"][0]:
                ranked.append(data);stage_best=m
        def invoke(op,until,grant=None):
            # All construction, IPC and certificates consume the stage budget.
            job=(source,metric,before,method,seed,idx,stale,until-.12,grant)
            return channel.call(op,job,until,receive)
        if method=="Hybrid-New" and idx%4!=3:
            aux_end=min(local,local_start+10.91)
            status=invoke("auxiliary",aux_end)
            log.append(["auxiliary",status,clock()-local_start])
        if clock()<local-.45:
            status=invoke("core",local,grants.get("cp",grants.get("hint")))
            log.append(["core",status,clock()-local_start])
        assert source is tr.plan and before==last
        selected=None
        if ranked:
            candidate=ranked[-1];plan=apply_delta(source,candidate);m=candidate["metrics"]
            assert key(p,plan)==candidate["sha"] and m["E_bounds"][1]<metric["E_bounds"][0]
            # Commit only after this fixed-source subproblem. Transfer complete plan and certificate.
            tr.plan=tr.safe_plan=plan;tr.best=tr.safe=m
            tr.history.append([clock()-start,m["E_bounds"],"SAFE"])
            origin=candidate["stage"];accepted();selected=last
        event("subproblem",source=before,adopted=selected,window=window,stale_before=stale,
              local_start=local_start-start,phases=log,elapsed=clock()-local_start,
              improvements=[(v["stage"],v["sha"],v["metrics"]["E_J"],v["metrics"]["E_bounds"]) for v in ranked])
        stale=0 if selected else stale+1;counter+=1;idx=None

    def record(end,before):
        row=dict(cycle=cycle,phase=phase,scheduled_end=end-start,actual_end=clock()-start,before=before,after=state())
        phases.append(row);events.flush()
        write(folder/"progress.json",row)
    try:
        for c in range(1,(1 if method=="G3" else cycles)+1):
            cycle=c;phase="G3";before=state()
            end=finish if method=="G3" else start+(c-1)*(g+deep)+g
            if method!="G3" and c>1:
                boundary=start+(c-1)*(g+deep)
                while clock()<boundary:time.sleep(max(0,min(.02,boundary-clock())))
            broad(end);record(end,before)
            if method=="G3":break
            if before["sha"]!=last:stale=0
            while clock()<end:time.sleep(max(0,min(.02,end-clock())))
            phase="joint";before=state();end=start+c*(g+deep)
            while clock()<end-1.5:subproblem(end)
            record(end,before)
    finally:
        channel.close()
        hist.close();events.close()
    write(folder/"summary.json",dict(method=method,seed=seed,cpu=cpu,initial=initial,final=last,metrics=tr.safe,
          phases=phases,stages=len(coverage),cp_stages=len(cp_coverage),iterations=counter,moves=flow.steps,
          charged_window_s=duration,elapsed_s=clock()-start,peak_bytes=proc.memory_info().peak_wset,
          final_plan=obj("D3",tr.plan)))
if __name__=="__main__":
    folder,method,seed,cpu,t,pilot=sys.argv[1:]
    run(Path(folder),method,int(seed),int(cpu),float(t),bool(int(pilot)))
