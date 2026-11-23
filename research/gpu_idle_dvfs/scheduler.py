"""Fixed GPU stage order, original other-resource FIFO rules, explicit DVFS stalls."""
from heapq import heappop, heappush


class Timeline:
    def __init__(self, window):
        self.window=window
        self.changes=[(0,"L")]
        self.switches=[]
    def switch(self,t,to,tau,energy):
        old=self.changes[-1][1]
        assert old in ("L","H") and old!=to and t>=self.changes[-1][0]
        assert t+tau<=self.window
        self.switches.append(dict(start_ns=t,end_ns=t+tau,source=old,target=to,energy_j=energy))
        if tau:self.changes.append((t,"X"))
        else:assert energy==0
        self.changes.append((t+tau,to))
    def spans(self):
        unique=dict(self.changes)
        points=sorted(unique)
        return [(t,points[i+1] if i+1<len(points) else self.window,unique[t])
                for i,t in enumerate(points) if t<self.window and (i+1==len(points) or points[i+1]>t)]


def predictive_calendar(rows,window,tau,energy,dwell):
    """Perfect deterministic readiness forecast; no thermal signals or scored search.

    Power-only break-even uses the frozen H-L GPU idle intercept (0.5 W).
    Leakage savings are not used in decisions. Short gaps remain H.
    """
    busy=[]
    for row in rows:
        if row.resource!="GPU":continue
        if busy and row.start_ns==busy[-1][1]:busy[-1]=(busy[-1][0],row.end_ns)
        else:busy.append((row.start_ns,row.end_ns))
    out=Timeline(window)
    assert busy and busy[0][0]>=tau
    out.switch(busy[0][0]-tau,"H",tau,energy)
    for i,(a,b) in enumerate(busy):
        next_start=busy[i+1][0] if i+1<len(busy) else window
        roundtrip=2 if i+1<len(busy) else 1
        stable=next_start-b-roundtrip*tau
        if stable>=dwell and .5*stable*1e-9>roundtrip*energy:
            out.switch(b,"L",tau,energy)
            if roundtrip==2:out.switch(next_start-tau,"H",tau,energy)
    return out


def dispatch(events,requests,chains,gpu_order,window,*,calendar=None,simple=None):
    """Drain every request; do not drop late work or reset queues at scene borders."""
    requests=tuple(requests)
    releases=sorted(requests,key=lambda r:(r.release_ns,r.id));jobs={r.id:r for r in requests}
    queues={u:[] for u in events.RESOURCES};gpu_ready={}
    running=set();finishes=[];rows=[];completions={};gpu_index=0;cursor=0
    mode="L";idle_since=0;stable_until=0;pending=None;now=0
    timeline=calendar if calendar is not None else Timeline(window)
    changes=sorted(dict(calendar.changes).items()) if calendar else []
    change_index=0
    def enqueue(req,index,t):
        stage=chains["L"][req.app][index]
        if stage.resource=="GPU":gpu_ready[req.id,index]=t
        else:
            app_order=req.app if stage.resource in events.CPU_CORES else events.PRIORITY[req.app]
            heappush(queues[stage.resource],(t,req.release_ns,app_order,index,req.id))
    def transition(to):
        nonlocal pending,mode,stable_until
        tau,energy,dwell=simple
        timeline.switch(now,to,tau,energy)
        if tau:mode="X";pending=(now+tau,to)
        else:mode=to;stable_until=now+dwell
    iterations=0
    while True:
        iterations+=1
        if iterations>100000:raise RuntimeError("nonprogressing event loop")
        while finishes and finishes[0][0]==now:
            _,unit,rid,index=heappop(finishes);running.remove(unit)
            if unit=="GPU":idle_since=now
            req=jobs[rid]
            if index+1==len(chains["L"][req.app]):completions[rid]=now
            else:enqueue(req,index+1,now)
        while cursor<len(releases) and releases[cursor].release_ns==now:
            enqueue(releases[cursor],0,now);cursor+=1
        if pending and pending[0]==now:
            mode=pending[1];pending=None;stable_until=now+simple[2]
        while change_index<len(changes) and changes[change_index][0]==now:
            assert "GPU" not in running,"DVFS cannot interrupt a GPU stage"
            mode=changes[change_index][1];change_index+=1
        timer=None
        for unit,queue in queues.items():
            if unit in running:continue
            if unit=="GPU":
                head=gpu_order[gpu_index] if gpu_index<len(gpu_order) else None
                ready=head in gpu_ready
                if simple and mode!="X":
                    if ready and mode=="L":
                        if now>=stable_until:transition("H")
                        else:timer=stable_until
                    elif not ready and mode=="H" and now<window:
                        target=idle_since+simple[2]
                        if target>now:timer=target
                        elif now+simple[0]<=window:transition("L")
                if not ready or mode=="X":continue
                if simple and mode!="H":continue
                rid,index=head;del gpu_ready[head];gpu_index+=1
            else:
                if not queue:continue
                _,_,_,index,rid=heappop(queue)
            stage=chains[mode if unit=="GPU" else "L"][jobs[rid].app][index]
            end=now+stage.duration_ns
            rows.append(events.Row(rid,stage.name,index,unit,now,end,stage.activity_w))
            heappush(finishes,(end,unit,rid,index));running.add(unit)
        candidates=[]
        if finishes:candidates.append(finishes[0][0])
        if cursor<len(releases):candidates.append(releases[cursor].release_ns)
        if pending:candidates.append(pending[0])
        if change_index<len(changes):candidates.append(changes[change_index][0])
        if timer is not None and timer<=window:candidates.append(timer)
        if not candidates:break
        assert min(candidates)>now,(now,candidates)
        now=min(candidates)
    assert len(completions)==len(requests) and gpu_index==len(gpu_order)
    assert [(r.request,r.stage_index) for r in rows if r.resource=="GPU"]==gpu_order
    return rows,completions,timeline
