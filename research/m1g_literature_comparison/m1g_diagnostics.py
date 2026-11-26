"""Offline profile audit, partial-calendar blockage and cross-window physical witnesses."""
import csv
import json
from fractions import Fraction
from itertools import combinations
import numpy as np
from audit import RAW,DATA,table,read
from experiment import ROOT,e,inputs,case_for,OUT,certify_native
from literature import Calendar,Profile,hard_limit,earliest_ready
from heat import integrate


def factors(p):
    profile=Profile(p)
    records=[]; separability=[]
    for stage in ("pre","main","post"):
        modes=profile.order[stage]
        exact={}
        for kind in "AB":
            t=kind+"."+stage
            for u,k in modes:
                idle,_,busy,_=p.exact[t,u,k]
                val=(busy-idle)*p.profile[t,u,k][0]/10000
                exact[kind,u,k]=val
                records.append(dict(stage=stage,kind=kind,unit=u,OPP=k,Eact_exact_J=str(val),
                      task_factor=profile.task_factor[t],Z_factor=profile.mode_factor[stage,u,k],
                      Li_factor=profile.thermal[stage,u,k],Z_rank=modes.index((u,k))+1,Li_rank=profile.li_modes(stage).index((u,k))+1))
        minors=[];inversions=0
        for m,q in combinations(modes,2):
            a,b=exact["A",*m],exact["B",*m]
            c,d=exact["A",*q],exact["B",*q]
            minors.append((abs(a*d-b*c),m,q))
            inversions+=int((a-c)*(b-d)<0)
        determinant,m,q=max(minors)
        ratios=[float(exact["A",*m]/exact["B",*m]) for m in modes]
        separability.append(dict(stage=stage,modes=len(modes),nonzero_minors=sum(det!=0 for det,_,_ in minors),
             tested_minors=len(minors),max_abs_minor_exact_J2=str(determinant),witness_modes=str((m,q)),
             min_A_B_ratio=min(ratios),max_A_B_ratio=max(ratios),rank_reversals=inversions,
             max_relative_fit_error=profile.residual[stage]))
    table("factors.csv",records);table("separability.csv",separability)


def blocked(p,partial,stats,case,method):
    book=Calendar(p)
    for i,row in enumerate(partial["rows"]):
        if row is not None:
            book.add(i,*row)
    if method=="Zhou":
        lvl=stats["failed_stage"]
        eligible=[i for i in range(lvl,p.n,3) if book.rows[i] is None]
    else:
        eligible=[stats["failed_task"]]
    profile=Profile(p)
    result=[]
    for i in eligible:
        left=earliest_ready(p,book,i);hard=hard_limit(p,i)
        opts=[]
        for u,k in p.options[i]:
            t=book.slot(i,u,k,left,p.horizon)
            if t is not None:
                opts.append((t+p.dur(i,u,k),u,k,t))
        earliest=min(opts) if opts else None
        empty=min(left+p.dur(i,*m) for m in p.options[i])
        result.append(dict(case=case,method=method,task=i,request=i//3,stage=p.kinds[i],release_tick=p.req[i//3]["release_tick"],
                ready_tick=left,hard_finish_tick=hard,earliest_finish_with_partial=earliest[0] if earliest else None,
                best_mode=str(earliest[1:3]) if earliest else None,slack_with_partial_ms=(hard-earliest[0])/10 if earliest else None,
                empty_resource_slack_ms=(hard-empty)/10,assigned_stages=p.n-sum(r is None for r in book.rows)))
    return result


def windowed(p,trace,rows,case,method):
    # Reintegrate cut-through event segments so crossing windows are charged exactly.
    state=p.initial.copy()
    result=[]
    windows=(p.horizon-3010)//10000
    for j in range(windows):
        left=j*10000;right=(j+1)*10000 if j+1<windows else p.horizon
        ev=trace[(trace[:,1]>left)&(trace[:,0]<right),:14].copy()
        ev[:,0]=np.maximum(ev[:,0],left)-left
        ev[:,1]=np.minimum(ev[:,1],right)-left
        out=integrate(ev,state,p.G,p.cap,float(p.ta),np.empty(0,np.int64),True)
        end=out[10][-1,4:8].copy()
        ids=[i for i,r in enumerate(p.req) if left<=r["release_tick"]<(j+1)*10000]
        ops=[rows[3*i+1] for i in ids]
        result.append(dict(case=case,method=method,window=j+1,load=case.split("_")[1][j],
                 gpu_in_C=state[2],npu_in_C=state[3],gpu_out_C=end[2],npu_out_C=end[3],
                 window_peak_hi_C=max(out[2]),E_J=out[0],GPU_count=sum(u==2 for u,k,t in ops),
                 NPU_count=sum(u==3 for u,k,t in ops),min_slack_ms=min((p.req[i]["deadline_tick"]-p.finish(3*i+2,rows[3*i+2]))/10 for i in ids)))
        state=end
    return result


def main():
    cases=inputs()
    init=e.p1.Engine("S32",OUT/"profile")
    factors(init.p)
    with (DATA/"checkpoints.csv").open() as f:
        cuts=list(csv.DictReader(f))
    blocks=[];wins=[];witnesses=[]
    for i,(_,src) in enumerate(cases):
        case=src.stem
        instance=case_for(src)
        p=instance.p
        lane=RAW/f"lane{i%7}"
        for method in ("Zhou","Li"):
            part=lane/"literature/partial"/case/(method+".json")
            if part.exists():
                run=read(lane/"literature/standalone"/case/(method+".json"))
                blocks.extend(blocked(p,read(part),run["stats"],case,method))
        for r in cuts:
            if r["case"]!=case or r["budget_s"]!="60" or not r["plan"]:
                continue
            folder=(lane/"engine/physical" if r["method"] in ("NT","C2") else lane/"literature")/"evidence"/case/r["plan"]
            with np.load(folder/"trace.npz") as z:
                tr=z["events"]
            physical=read(folder/"plan.json")["rows"]
            if r["method"]=="NT":
                unrestricted=Calendar(p)
                for task,row in enumerate(physical):
                    unrestricted.add(task,*row)
                recert=certify_native(instance,unrestricted,OUT/"witness")
                assert recert["plan_sha256"]==r["plan"]
                assert recert["metrics"]["status"]=="SAFE" and abs(recert["metrics"]["E_J"]-float(r["SAFE_J"]))<1e-9
                witnesses.append(dict(case=case,plan=r["plan"],E_J=recert["metrics"]["E_J"],
                                      status="SAFE",same_physical_plan=True))
            split=windowed(p,tr,physical,case,r["method"])
            assert abs(sum(v["E_J"] for v in split)-float(r["SAFE_J"]))<1e-7
            wins.extend(split)
    if blocks:
        table("blocked_tasks.csv",blocks)
    table("thermal_windows.csv",wins)
    table("native_domain_witness.csv",witnesses)


if __name__=="__main__":
    main()
