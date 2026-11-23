"""Original resource queues with causal DVFS hooks; frozen GPU order stays private.

The controller never receives `chains`, future releases, or GPU order. Every
clock stall changes the event timeline; all dependent stages are rescheduled.
"""
from heapq import heappop,heappush
from controller import Control


def simulate(events,Timeline,requests,chains,gpu_order,job_meta,window,strategy,setting,dwell,period,service_end):
    releases=sorted(requests,key=lambda r:(r.release_ns,r.id));jobs={r.id:r for r in requests}
    queues={u:[] for u in events.RESOURCES};gpu_ready={};running=set();finishes=[]
    rows=[];completion={};gpu_starts=[];stalls=[];cursor=0;gpu_index=0;now=0
    mode='L';stable_since=0;idle_since=0;pending=None;timeline=Timeline(window)
    ctrl=Control(strategy,setting['latency_ns'],setting['energy_j'],dwell,period,service_end,window)
    def enqueue(req,index,t):
        stage=chains['L'][req.app][index]
        if stage.resource=='GPU':
            gpu_ready[req.id,index]=t;ctrl.ready(t,req.id,index)
        else:
            app_order=req.app if stage.resource in events.CPU_CORES else events.PRIORITY[req.app]
            heappush(queues[stage.resource],(t,req.release_ns,app_order,index,req.id))
    iterations=0
    while True:
        iterations+=1
        if iterations>200000:raise RuntimeError('Nonprogressing event loop')
        while finishes and finishes[0][0]==now:
            _,unit,rid,index=heappop(finishes);running.remove(unit)
            if unit=='GPU':idle_since=now
            req=jobs[rid]
            if index+1==len(chains['L'][req.app]):completion[rid]=now
            else:enqueue(req,index+1,now)
        while cursor<len(releases) and releases[cursor].release_ns==now:
            req=releases[cursor];scene,required=job_meta[req.id]
            ctrl.release(now,req.id,req.app,req.release_ns,scene,required)
            enqueue(req,0,now);cursor+=1
        if pending and pending[0]==now:
            mode=pending[1];pending=None;stable_since=now
            ctrl.record(now,'transition_end',mode=mode)
        head=gpu_order[gpu_index] if gpu_index<len(gpu_order) else None
        required=job_meta[head[0]][1] if head in gpu_ready else None
        target,timer,reason=ctrl.choose(now,mode,'GPU' in running,required,idle_since,stable_since)
        if target is not None:
            assert 'GPU' not in running and mode in ['L','H'] and target!=mode
            timeline.switch(now,target,setting['latency_ns'],setting['energy_j'])
            ctrl.record(now,'transition_start',source=mode,target=target,reason=reason,head=list(head) if required else None)
            if setting['latency_ns']:
                mode='X';pending=(now+setting['latency_ns'],target)
            else:mode=target;stable_since=now
        for unit,queue in queues.items():
            if unit in running:continue
            if unit=='GPU':
                head=gpu_order[gpu_index] if gpu_index<len(gpu_order) else None
                if head not in gpu_ready or mode!=job_meta[head[0]][1]:continue
                rid,index=head;ready_time=gpu_ready.pop(head);gpu_index+=1
                gpu_starts.append(dict(rid=rid,stage=index,ready_ns=ready_time,start_ns=now,required=mode))
                ctrl.record(now,'gpu_start',rid=rid,stage=index,ready_ns=ready_time,required=mode)
            else:
                if not queue:continue
                _,_,_,index,rid=heappop(queue)
            level=job_meta[rid][1] if unit=='GPU' else 'L'
            stage=chains[level][jobs[rid].app][index];end=now+stage.duration_ns
            rows.append(events.Row(rid,stage.name,index,unit,now,end,stage.activity_w))
            heappush(finishes,(end,unit,rid,index));running.add(unit)
        next_times=[]
        if finishes:next_times.append(finishes[0][0])
        if cursor<len(releases):next_times.append(releases[cursor].release_ns)
        if pending:next_times.append(pending[0])
        if timer is not None and timer<=window:next_times.append(timer)
        if not next_times:break
        following=min(next_times);assert following>now,(now,following,reason)
        head=gpu_order[gpu_index] if gpu_index<len(gpu_order) else None
        if 'GPU' not in running and head in gpu_ready:
            stalls.append(dict(start_ns=now,end_ns=following,rid=head[0],stage=head[1],
                               reason='transition' if mode=='X' else 'minimum_L_residency',mode=mode))
        now=following
    assert len(completion)==len(requests) and gpu_index==len(gpu_order)
    assert [(r.request,r.stage_index) for r in rows if r.resource=='GPU']==gpu_order
    return rows,completion,timeline,dict(controller_log=ctrl.log,gpu_starts=gpu_starts,stall_segments=stalls)
