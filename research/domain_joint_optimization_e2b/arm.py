"""Lightweight owner of one timed run. A separate persistent single-core process enforces the per-neighborhood wall."""
import collections,gzip,json,multiprocessing,os,sys,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
clock=time.perf_counter
def raw(x):return json.dumps(x,ensure_ascii=False,allow_nan=False,separators=(",",":"),default=str).encode()
def save(p,x):
    tmp=p.with_suffix(".tmp");tmp.write_bytes(raw(x)+b"\n");tmp.replace(p)
def physical(case,plan):return dict(case=case,rows=plan[0],low=sorted(plan[1]))
def slim(m):
    return {k:m[k] for k in ("E_J","E_bounds","peak_hi","min_deadline_slack_ms","activity_J","base_J","temperature_J","switch_J","external_J","switch_count","status")}
def launch(conn,case,method,seed,cpu):
    psutil.Process().cpu_affinity([cpu])
    from numerics import service
    service(conn,case,method,seed,cpu)
def run(case,method,seed,cpu,path,start,end,pilot):
    path.mkdir(parents=True,exist_ok=False);psutil.Process().cpu_affinity([cpu])
    if method=="G3":
        from numerics import g3
        g3(path,case,seed,start,end)
        return
    ctx=multiprocessing.get_context("spawn");curr=None;child=None;pipe=None
    idx=stale=success=0;targets=set();visited=collections.Counter();counts=collections.Counter();peak=0
    initial=None;last_cpu=0.;past_cpu=0.;accepted_sources=set()
    def stop():
        nonlocal child,pipe,past_cpu,last_cpu
        if child:
            if child.is_alive():
                try:pipe.send(None)
                except (OSError,BrokenPipeError):pass
                child.join(.10)
                if child.is_alive():child.terminate()
            child.join(2);pipe.close();child.close();child=pipe=None
            past_cpu+=last_cpu;last_cpu=0.
    with gzip.open(path/"iterations.jsonl.gz","wb",compresslevel=3) as it,gzip.open(path/"history.jsonl.gz","wb",compresslevel=2) as history,gzip.open(path/"plans.jsonl.gz","wb",compresslevel=2) as plans:
        try:
            while clock()<end-.7:
                if child is None:
                    pipe,other=ctx.Pipe();child=ctx.Process(target=launch,args=(other,case,method,seed,cpu),daemon=True)
                    child.start();other.close()
                    if not pipe.poll(max(.01,min(90,end-clock()-.35))):
                        if curr is None:raise RuntimeError("model initialization timeout")
                        break
                    ready=pipe.recv()
                    if ready[0]!="ready":raise RuntimeError(ready)
                    _,base,seedplan,seed_m,nwin,n=ready
                    if curr is None:
                        initial=best=base;curr=seedplan;m=seed_m
                        history.write(raw(dict(t=clock()-start,before=None,after=base,metrics=slim(m),actual=None))+b"\n")
                        plans.write(raw([base,physical(case,curr)])+b"\n")
                now=clock()
                boundary=min([end-.45]+[start+s-.08 for s in (180,900) if start+s-.08>now])
                if not pilot and boundary-now<1.2:
                    if boundary>=end-.46:break
                    time.sleep(max(0,boundary-now+.01));continue
                deadline=min(now+29.75,boundary)
                if deadline-now<.75:break
                pipe.send((curr,m,idx,stale,deadline-.25))
                msg=pipe.recv() if pipe.poll(max(.001,deadline-clock())) else None
                if msg is None:
                    counts["watchdog"]+=1;rec=dict(iteration=idx,source=best,window=(idx%nwin+idx//nwin+(seed-101))%nwin,
                         status="TIME_LIMIT",uncertified="in-flight state unavailable",elapsed_s=clock()-now)
                    stop();winner=None
                else:
                    if msg[0]!="result":raise RuntimeError(msg)
                    _,rec,winner,rss,last_cpu=msg;peak=max(peak,rss)
                    rec["outer_s"]=clock()-now
                    assert rec["source"]==best and rec["cp_seed"]==seed
                    if clock()>deadline+.02:
                        rec["status"]="LATE_RETURN";winner=None
                    targets.update(rec["St"])
                    counts["evaluated"]+=sum(not c["cached"] for c in rec["candidates"])
                    counts["nonseed"]+=sum(c["sha"]!=best for c in rec["candidates"])
                    counts["joint"]+=sum(c["config"]>0 and c["moved"]>0 for c in rec["candidates"])
                    counts["uncertified"]+=len(rec["uncertified"]);counts["missing_returns"]+=len(rec["unreturned"])
                    counts["fallback"]+=int(rec["operator"]["fallback"])
                visited[rec["window"]]+=1;rec["t_end"]=clock()-start
                if winner:
                    k,plan,metric,delta=winner
                    assert metric["status"]=="SAFE" and metric["E_bounds"][1]<m["E_bounds"][0]
                    history.write(raw(dict(t=rec["t_end"],iteration=idx,before=best,after=k,metrics=slim(metric),actual=delta))+b"\n")
                    rec["adopted"]=k;plans.write(raw([k,physical(case,plan)])+b"\n")
                    curr,m,best=plan,metric,k;stale=0;success+=1
                else:stale+=1
                it.write(raw(rec)+b"\n");idx+=1
                if idx%4==0 or pilot:
                    it.flush();history.flush();plans.flush()
                    save(path/"progress.json",dict(iterations=idx,elapsed=clock()-start,accepted=success,windows=len(visited),best=best))
                if pilot:break
        finally:stop()
    assert initial is not None
    save(path/"summary.json",dict(case=case,method=method,seed=seed,initial=initial,final=best,metrics=slim(m),
           accepted=success,iterations=idx,windows=visited,stages=len(targets),total_windows=nwin,reach_n=n,
           counts=counts,peak_bytes=peak,elapsed_s=clock()-start,cpu_s=past_cpu+time.process_time()))
if __name__=="__main__":
    case,method,seed,cpu,path,start,stop,pilot=sys.argv[1:]
    run(case,method,int(seed),int(cpu),Path(path),float(start),float(stop),bool(int(pilot)))
