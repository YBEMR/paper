"""Registered secondary sensitivity to the admission order of asynchronously released jobs."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RAW=Path(os.environ.get("M1G_RELEASE_RAW",ROOT/"release_raw")).resolve()


def schedule(case,method,dest):
    from collections import Counter
    from itertools import groupby
    from time import perf_counter
    from experiment import e,certify_native
    from literature import Calendar,HeatProbe,Profile,earliest_ready,hard_limit,reference,lft
    p=case.p;stats=Counter();calls=[]
    start=perf_counter()
    prof=Profile(p);book=Calendar(p)
    is_zhou=method=="Z-release"
    probe=HeatProbe(p) if is_zhou else None
    limits=None if is_zhou else reference(p,prof)
    failure=None
    for _,requests in groupby(range(len(p.req)),key=lambda j:p.req[j]["release_ms"]):
        ids=list(requests)
        stats["release_groups_entered"]+=1
        if is_zhou:
            for level,stage in enumerate(("pre","main","post")):
                queue=sorted((3*j+level for j in ids),key=lambda i:(-prof.task_factor[p.kinds[i]],i))
                for u,k in prof.order[stage]:
                    pending=[]
                    for i in queue:
                        t=book.slot(i,u,k,earliest_ready(p,book,i),hard_limit(p,i))
                        if t is None:
                            stats["timing_reject"]+=1
                        else:
                            probe.add(i,u,k,t,1);stats["thermal_probes"]+=1
                            if probe.peak()<=80:
                                book.add(i,u,k,t)
                                continue
                            probe.add(i,u,k,t,-1);stats["thermal_reject"]+=1
                        pending.append(i)
                    queue=pending
                    if not queue:
                        break
                if queue:
                    failure=queue[0]
                    break
        else:
            order=sorted((3*j+h for j in ids for h in range(3)),key=lambda i:(-prof.up[p.kinds[i]],i))
            for i in order:
                modes=prof.li_modes(p.kinds[i].split(".")[1])
                left=earliest_ready(p,book,i)
                fallback=[]
                for u,k in modes:
                    t=book.slot(i,u,k,left,hard_limit(p,i))
                    if t is None:
                        continue
                    end=t+p.dur(i,u,k)
                    if end<=limits[i]:
                        book.add(i,u,k,t)
                        break
                    fallback.append((end,u,k,t))
                else:
                    if not fallback:
                        failure=i
                        break
                    _,u,k,t=min(fallback)
                    stats["earliest_finish_fallback"]+=1
                    book.add(i,u,k,t)
        if failure is not None:
            break

    def record(stage):
        cert=certify_native(case,book,dest)
        m=cert["metrics"]
        calls.append(dict(stage=stage,t_s=perf_counter()-start,status=m["status"],E_J=m["E_J"],
                          lo=m["E_bounds"][0],hi=m["E_bounds"][1],peak_C=max(m["peak_hi"]),plan=cert["plan_sha256"]))
    if failure is None:
        record("mapping")
        if not is_zhou:
            lft(p,book,stats)
            record("LFT")
    else:
        e.p1.put(dest/"partial"/case.label/(method+".json"),dict(failed=failure,rows=book.rows))
    elapsed=perf_counter()-start
    result=dict(case=case.label,method=method,actual_s=elapsed,stats=dict(stats),failure_task=failure,
                failure_stage=p.kinds[failure] if failure is not None else None,
                assigned_stages=sum(r is not None for r in book.rows),stages=calls,
                final_status=calls[-1]["status"] if calls else "NO_CONSTRUCTION")
    e.p1.put(dest/"runs"/case.label/(method+".json"),result)
    print(case.label,method,result["final_status"],round(elapsed,3),flush=True)


def lane(i,core):
    os.sched_setaffinity(0,{core})
    dest=RAW/f"lane{i}"
    os.environ["M1G_RAW"]=str(dest)
    from experiment import case_for,e,inputs
    from literature import HeatProbe
    warm=e.p1.Engine("S32",dest/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    HeatProbe(warm.p).peak()
    for n,(_,src) in enumerate(inputs()):
        if n%7!=i:
            continue
        c=case_for(src)
        for m in (("Z-release","Li-release") if n%2==0 else ("Li-release","Z-release")):
            schedule(c,m,dest)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--lane",type=int)
    parser.add_argument("--core",type=int)
    a=parser.parse_args()
    if a.lane is not None:
        lane(a.lane,a.core)
    else:
        cores=sorted(os.sched_getaffinity(0))[-7:]
        assert len(cores)==7
        RAW.mkdir(parents=True,exist_ok=False)
        jobs=[]
        for i,core in enumerate(cores):
            with (RAW/f"lane{i}.log").open("w") as log:
                jobs.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(i),"--core",str(core)],stdout=log,stderr=subprocess.STDOUT))
        codes=[job.wait() for job in jobs]
        if any(codes):
            raise RuntimeError(codes)
