"""One independently timed D3 run; incumbent and G3 state stay in the owner."""
import gzip,json,pickle,sys,time
from pathlib import Path
import psutil
from design_d import INITIAL,clock,sha,write,core_kind
from transport import Channel
from flow_run import apply_delta

def run(folder,method,seed,cpu,start,short):
    proc=psutil.Process();proc.cpu_affinity([cpu]);folder.mkdir(parents=True,exist_ok=False)
    from g3_flow import Flow,search
    from base import Problem,archived,changes,key,obj,raw,bins
    from search import Tracker, Expired
    p=Problem("D3");initial,base=archived("D3")
    assert initial==INITIAL==key(p,base) and (p.n,len(p.req))==(2400,800)
    g,deep,cycles=(30,30,2) if short else (180,120,3)
    duration=cycles*(g+deep)
    finish=start+duration
    hist=(folder/"accepted.jsonl").open("wb");events=gzip.open(folder/"events.jsonl.gz","wb",compresslevel=1)
    phases=[];coverage=set();cp_coverage=set();counter=0;stale=0;last=None;last_plan=None
    phase="init";cycle=0;idx=None;origin="initial"
    def event(name,**data):
        events.write(raw(dict(event=name,t=clock()-start,cycle=cycle,phase=phase,it=idx,**data))+b"\n")
    channel=Channel(cpu,event,folder,method)
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
    # One startup before the first G3 segment, charged to the first cycle.
    if not channel.open(start+g-3):
        raise RuntimeError("initial worker did not reach ready during first broad stage")
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
        local_start=clock();local=min(end-.85,local_start+29.65)
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
            m=data["metrics"];on_time=data["at"]<=deadline
            event("certificate",sha=data["sha"],stage=data["stage"],source=before,metrics=m,
                  at=data["at"],on_time=on_time,cached=data["cached"],edits=data["edits"],
                  low_add=data["low_add"],low_drop=data["low_drop"])
            if on_time and m["status"]=="SAFE" and m["E_bounds"][1]<stage_best["E_bounds"][0]:
                ranked.append(data);stage_best=m
        def invoke(op,until,grant=None):
            # All construction, IPC and certificates consume the stage budget.
            job=(source,metric,before,"Hybrid-New",seed,idx,stale,until-1.65,grant)
            return channel.call(op,job,until,receive)
        if idx%4!=3:
            aux_end=min(local,local_start+10.95)
            status=invoke("auxiliary",aux_end)
            log.append(["auxiliary",status,clock()-local_start])
        grant=grants.get("cp",grants.get("hint"))
        kind=core_kind(method,idx,grant)
        event("route",grant=grant,module=kind,compact_enabled=method!="NoAux",source=before)
        if kind and clock()<local-1.6:
            status=invoke("core",local,grant)
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
        assert clock()-local_start<=30,"local wall limit"
        if log and log[0][0]=="auxiliary":assert log[0][2]<=11,"auxiliary wall limit"
        stale=0 if selected else stale+1;counter+=1;idx=None

    def record(end,before):
        row=dict(cycle=cycle,phase=phase,scheduled_end=end-start,actual_end=clock()-start,before=before,after=state())
        phases.append(row);events.flush()
        write(folder/"progress.json",row)
    try:
        for c in range(1,cycles+1):
            cycle=c;phase="G3";before=state()
            end=start+(c-1)*(g+deep)+g
            if c>1:
                boundary=start+(c-1)*(g+deep)
                while clock()<boundary:time.sleep(max(0,min(.02,boundary-clock())))
            broad(end);record(end,before)
            if before["sha"]!=last:stale=0
            while clock()<end:time.sleep(max(0,min(.02,end-clock())))
            phase="joint";before=state();end=start+c*(g+deep)
            # Final accounting and complete interpreter exit are inside the last period.
            work_end=end-(5.0 if c==cycles else .15)
            while clock()<work_end-2.3:subproblem(work_end)
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
