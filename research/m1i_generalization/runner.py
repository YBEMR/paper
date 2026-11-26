"""Frozen anytime policy with deadline and empty-pool handling at every width."""
from time import perf_counter
from pathlib import Path
from adapter import builder,e

def timed_run(c,method,dest,budget=60.):
    dest=Path(dest)
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True)
    c.eng.out=dest/"physical"
    build,progress=builder(method)
    records=[];stages=[];seen=set()
    width=4
    start=perf_counter();deadline=start+budget
    while True:
        stage=dict(width=width,actions=[],groups=[],beam=[],start_s=perf_counter()-start)
        stages.append(stage)
        t=perf_counter()
        ordered=build(c,method,width,start,deadline,stage)
        now=perf_counter()
        stage.update(build_s=now-t,ready_s=now-start,terminal=len(ordered),last_window=dict(progress))
        if not ordered:
            stop="no_legal_pool" if progress.get("complete") and not progress["size"] else "deadline_during_build"
            break
        new=0
        for rank,s in enumerate(ordered,1):
            if perf_counter()>=deadline:break
            if s["id"] in seen:continue
            t=perf_counter()
            cert,_=c.certify(s["config"])
            end=perf_counter()
            assert abs(cert["E35_J"]-s["energy"])<1e-8
            seen.add(s["id"]);new+=1
            records.append(dict(width=width,rank=rank,id=s["id"],prediction=None if method=="C2" else s["peak"],
                                ref_E=s["energy"],cert=cert,cert_s=end-t,start_s=t-start,end_s=end-start))
            if new>=2*width and deadline-perf_counter()>=2*stage["build_s"]+end-t:break
        if perf_counter()>=deadline:
            stop="deadline_after_certificate" if records and records[-1]["end_s"]>budget else "deadline_between_actions"
            break
        width*=2
    wall=perf_counter()-start
    simple=[{k:v for k,v in stage.items() if k not in ("actions","groups","beam")} for stage in stages]
    # Full per-call certificates are archived separately; stage detail is outside the timer.
    for stage in stages:
        stage["action_counts"]={}
        for a in stage.pop("actions"):
            stage["action_counts"][a[9]]=stage["action_counts"].get(a[9],0)+1
        stage["group_count"]=len(stage.pop("groups"))
    e.p1.put(dest/"run.json",dict(case=c.label,method=method,budget_s=budget,wall_s=wall,stop=stop,
                                   records=records,stages=simple,search=stages))
    return wall
