"""Identify actual action changes and the overlap between the pre-registered ranking arms."""
import csv
from pathlib import Path
import numpy as np
from inspect_results import HERE, OUT, TABLES, part, read, rows, physical, write, sha, w

def main():
    case="C10"
    arms={m:read(OUT/"runs"/f"online-{case}-{m}-r1.json") for m in ("oo","oh","ho","hh")}
    units=arms["ho"]["delivery"]["attempts"]
    winner=units[-1]
    anchor=units[0]
    obj=next(r for r in w.u.CASES if r["case"].startswith(case+"_"))
    stack=w.u.stack()
    flow=w.u.make_flow(stack[0],obj,OUT)
    eng=stack[1].Engine(obj["case"],OUT)
    def path(plan):
        data=read(physical(case,plan)/"plan.json")
        cfg=tuple(tuple(row[:2]) for row in data["rows"][1::3])
        track=[]
        for j,ids in enumerate(eng.groups):
            sub=cfg[ids[0]:ids[-1]+1]
            pair=tuple(next(iter({k for u,k in sub if u==device}),0) for device in (2,3))
            parent=eng.replay(cfg[:ids[0]]) if j else dict(f=(0,0),k=(0,0))
            counts=tuple(sum(eng.kindidx[i]==t for i in ids) for t in (0,1))
            center=eng.quota(parent,j,pair,counts)
            q=tuple(sum(cfg[i][0]==3 and eng.kindidx[i]==t for i in ids) for t in (0,1))
            assert flow.extension(flow.kinds[ids],*counts,*pair,*q)==w.u.encoded(sub)
            track.append(dict(window=j+1,pair=list(pair),quota=list(q),center=list(center),delta=[q[h]-center[h] for h in (0,1)],
                parent_f=list(parent["f"]),parent_opp=list(parent["k"])))
        return cfg,track
    ca,old=path(anchor["plan"])
    cb,new=path(winner["plan"])
    changes=[dict(window=j+1,old_gpu=old[j]["pair"][0],old_npu=old[j]["pair"][1],old_A=old[j]["quota"][0],
        old_B=old[j]["quota"][1],new_gpu=new[j]["pair"][0],new_npu=new[j]["pair"][1],
        new_A=new[j]["quota"][0],new_B=new[j]["quota"][1],new_center_A=new[j]["center"][0],new_center_B=new[j]["center"][1],
        delta_A=new[j]["delta"][0],delta_B=new[j]["delta"][1],changed_requests=sum(ca[i]!=cb[i] for i in ids),
        parent_gpu_ready=new[j]["parent_f"][0],parent_npu_ready=new[j]["parent_f"][1]) for j,ids in enumerate(eng.groups)]
    rows("safe_path",changes)
    submitted={}
    base=part(arms["ho"],"base")["top"]
    for m in ("ho","hh"):
        ranking=part(arms[m],"single-pool")["ranking"]
        v=next(v for v in ranking if sha(bytes.fromhex(v["config"]))==winner["config"])
        fresh=[x for x in ranking if x["config"] not in base]
        submitted[m]=dict(raw_rank=ranking.index(v)+1,new_rank=fresh.index(v)+1,predicted=v["prediction"],
            prediction_minus_cert=None if v["prediction"] is None else v["prediction"]-winner["peak_hi"],distinct=len(ranking),new=len(fresh))
    heat=arms["ho"]["location"]["heat"]
    bands=[]
    for name,plan in (("anchor",anchor["plan"]),("safe",winner["plan"])):
        with np.load(physical(case,plan)/"trace.npz",allow_pickle=False) as arch:
            tr=arch["events"]
        for i,node in enumerate(heat["nodes"]):
            above=tr[:,22+i]>80
            edges=np.diff(np.r_[False,above,False].astype(int))
            for l,h in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
                bands.append(dict(plan=name,node=node,first_event=int(l),past_last_event=int(h),start_tick=int(tr[l,0]),
                    end_tick=int(tr[h-1,1]),events=h-l,max_upper_C=tr[l:h,22+i].max(),
                    actual_endpoint_above=bool(max(tr[l:h,14+i].max(),tr[l:h,18+i].max())>80)))
    rows("hot_event_bands",bands)
    rows("heat_sources",[dict(window=j+1,CPU1=v[0],CPU2=v[1],GPU=v[2],NPU=v[3],total=sum(v)) for j,v in enumerate(heat["source_C"])])
    err=[]
    for m in ("oh","hh"):
        for stage in ("single","adjacent"):
            a=[v for v in arms[m]["delivery"]["attempts"] if v["stage"]==stage]
            e=np.array([v["error_C"] for v in a])
            err.append(dict(method=m,stage=stage,n=len(a),mean_signed_C=e.mean(),MAE_C=np.abs(e).mean(),max_abs_C=np.abs(e).max()))
    rows("prediction_errors",err)
    write(TABLES/"mechanism.json",dict(baseline=anchor,winner=winner,ranking=submitted,
        hotspot=heat,changed_requests=sum(x["changed_requests"] for x in changes),overheat_event_bands=len(bands)))
    bobj=next(i for i in w.u.CASES if i["case"].startswith("B07_"))
    bf=w.u.make_flow(stack[0],bobj,OUT)
    b_rows=[]
    for method in ("b1","b2"):
        unit=read(OUT/"runs"/f"online-B07-{method}-r1.json")
        tables=[]
        for j in (3,4):
            ledger=part(unit,"backlog-w%02d"%(j+1))
            index={}
            ids=bf.eng.groups[j]
            types=bf.kinds[ids]
            count=tuple(int(sum(types==h)) for h in (0,1))
            for event in ledger["attempts"]:
                parent,window,g,n,x,y,dx,dy=event[:8]
                if event[-1]!=0:
                    continue
                code=bytes.fromhex(ledger["parents"][parent])+bf.extension(types,*count,g,n,x,y)
                index.setdefault(code,[g,n,x,y,dx,dy])
            tables.append((index,ids[-1]+1))
        for cert in unit["delivery"]["attempts"]:
            v=read(physical("B07",cert["plan"])/"plan.json")
            config=bytes(k+10*(u==3) for u,k,_ in v["rows"][1::3])
            track=[index[config[:end]] for index,end in tables]
            b_rows.append(dict(method=method,rank=cert["rank"],w4=track[0],w5=track[1],
                        plan=cert["plan"],status=cert["status"],peak_hi=cert["peak_hi"],slack_ms=cert["slack_ms"]))
    rows("backlog_paths",b_rows)
if __name__=="__main__":
    main()
