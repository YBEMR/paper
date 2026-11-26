"""Matched generation/ranking ablation and ordinary beam/certificate extensions."""
import argparse
import csv
import gzip
from collections import Counter,defaultdict
from itertools import groupby
from time import perf_counter
from base import ROOT,M1,Case,WINDOW,np,p1,digest,load,save,window_types,diverse
from generator import anchors,capacity,load_planes,synthesize

OUT=ROOT/"data/search"
ARMS=[(g,r,4,4) for g in ("O","N","H") for r in ("C","T")]+[("O","C",8,4),("O","C",4,8),("O","C",8,8)]


def arm_name(g,r,w,b):
    return f"{g}{r}_w{w}b{b}"


def grouped_means(m,duration,group):
    return np.array([np.average(m[i:i+group],axis=0,weights=duration[i:i+group]) for i in range(0,len(m),group)])


def run(label,gen,rank,width,budget):
    name=arm_name(gen,rank,width,budget)
    target=OUT/label/name
    if (target/"result.json").exists():
        return
    target.mkdir(parents=True,exist_ok=True)
    c=Case(label,target)
    c.ledger(bytes([0]),0,WINDOW,2500,False)
    c.propagate(c.p.initial,np.r_[c.args[9][:,0],c.args[10][:,0]],1.)
    thermal=rank=="T"
    needT=thermal or gen=="H"
    states=[dict(config=b"",id=digest(b""),f=(0,0),k=(0,0),temperature=c.p.initial,peak=max(c.p.initial),history=[])]
    rows,beam,stages,certs=[],[],[],[]
    counts=Counter()
    start=perf_counter()
    expired=False
    for j in range(c.windows):
        lo=j*WINDOW
        end=(j+1)*WINDOW
        final=j==c.windows-1
        right=c.p.horizon if final else end
        t,a,b=window_types(c,j)
        nexts={}
        tick=perf_counter()
        for parent in states:
            for (g,n),actions in groupby(c.candidates(j,parent),key=lambda pair:pair[0][:2]):
                if perf_counter()-start>=299:
                    expired=True
                    break
                original={tuple(action[2:]):tail for action,tail in actions}
                time=load_planes(c,j,parent,g,n,a,b)
                cache={}
                pilots=[]
                def trial(xy):
                    if xy in cache:
                        return cache[xy]
                    ext=original.get(xy)
                    if ext is None:
                        ext=c.extension(t,a,b,g,n,*xy)
                    cfg=parent["config"]+ext
                    k=digest(cfg)
                    if k in nexts and xy not in pilots:
                        cache[xy]=(cfg,k,None,None,None)
                        return cache[xy]
                    fine=500 if gen=="H" and final and xy in pilots else 2500
                    l=c.ledger(cfg,lo,right,fine,final,needT)
                    counts["fifo"]+=1
                    if xy in pilots:
                        counts["calibration_fifo"]+=1
                    duration=np.minimum(fine,right-lo-np.arange(len(l[8]))*fine)/WINDOW
                    cache[xy]=(cfg,k,l,duration,fine)
                    return cache[xy]
                if gen=="O":
                    chosen=list(original)
                else:
                    center=c.eng.quota(parent,j,(g,n),(a,b))
                    pilots,bal=anchors(time,center,a,b)
                    observations=[]
                    values=[]
                    for xy in pilots:
                        _,_,l,durations,fine=trial(xy)
                        values.append(l[1])
                        if gen=="H":
                            obs=l[8]
                            if final:
                                obs=np.vstack((grouped_means(obs[:20],durations[:20],5),obs[20:]))
                            observations.append(obs)
                    if gen=="H":
                        steps=np.r_[np.repeat(.25,4),durations[20:]] if final else np.repeat(.25,4)
                        planes=capacity(c,parent["temperature"],pilots,np.array(observations),steps,not final)
                    else:
                        planes=np.empty((0,3))
                    eco=np.linalg.solve(np.column_stack((np.ones(3),pilots)),values)
                    chosen=synthesize(time,planes,pilots,bal,eco,a,b,len(original))
                    for xy in original:
                        if len(chosen)>=len(original):
                            break
                        if xy not in chosen:
                            chosen.append(xy)
                    assert len(chosen)==len(original) and set(pilots)<=set(chosen)
                for xy in chosen:
                    action=(g,n,*xy)
                    cfg,key,l,duration,fine=trial(xy)
                    tag="pilot" if xy in pilots else "legacy" if xy in original else "generated"
                    info=[j+1,parent["id"],*action,key,tag,int(xy in original)]
                    counts["proposals"]+=1
                    counts["outside_old"]+=xy not in original
                    if key in nexts:
                        rows.append((*info,"duplicate",None,None,None,None))
                        continue
                    assert l is not None
                    if not l[0]:
                        rows.append((*info,"timing",l[-1],None,None,None))
                        continue
                    energy=l[1]+(c.base*c.p.horizon/WINDOW if final else 0)
                    temp=parent["temperature"]
                    peak=parent["peak"]
                    if needT:
                        means=l[8]
                        if fine==500:
                            means=grouped_means(means,duration,5)
                        qdur=np.minimum(2500,right-lo-2500*np.arange(len(means)))/WINDOW
                        for m,h in zip(means,qdur):
                            temp=c.propagate(temp,m,h)
                            peak=max(peak,max(temp))
                    risk=max(time[:,0]+time[:,1:]@xy)
                    if thermal:
                        risk=peak if final else max(peak,max(c.propagate(temp,means[:4].mean(axis=0),1)))
                    state=dict(config=cfg,id=key,f=l[2],k=l[3],temperature=temp,peak=peak,risk=risk,energy=energy,
                               drain=max(max(l[2]),max(l[6]+c.args[4][:len(cfg)])),action=action,parent=parent["id"],
                               history=parent["history"]+[action])
                    nexts[key]=state
                    rows.append((*info,"valid",l[-1],energy,risk,peak if needT else None))
            if expired:
                break
        if expired or not nexts:
            states=[]
            break
        by_energy=sorted(nexts.values(),key=lambda s:(round(s["energy"],11),s["config"]))
        states=diverse(by_energy,final)
        limit=budget if final else width
        ids={s["id"] for s in states}
        for s in by_energy:
            if len(states)>=limit:
                break
            if s["id"] not in ids:
                states.append(s)
                ids.add(s["id"])
        states=states[:limit]
        for i,s in enumerate(states,1):
            beam.append(dict(window=j+1,rank=i,**{k:s[k] for k in ("id","parent","action","history","energy","risk","drain")}))
        stages.append(dict(window=j+1,unique_valid=len(nexts),retained=len(states),seconds=perf_counter()-tick))
    search_s=perf_counter()-start
    for i,s in enumerate(states,1):
        if perf_counter()-start>=299:
            expired=True
            break
        cert,_=c.certify(s["config"])
        m=cert["metrics"]
        assert abs(s["energy"]-cert["E35_J"])<1e-8
        certs.append(dict(rank=i,config=s["id"],plan=cert["plan_sha256"],status=m["status"],E=m["E_J"],interval=m["E_bounds"],
                          peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],elapsed=perf_counter()-start))
    elapsed=perf_counter()-start
    assert elapsed<300
    if gen=="O" and width==budget==4:
        prev=load(M1/"data/e1b"/label/("C2" if rank=="C" else "D2")/"result.json")["certificates"]
        assert [v["plan"] for v in prev]==[v["plan"] for v in certs],(label,name)
    with gzip.open(target/"proposals.csv.gz","wt",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["window","parent","g","n","x","y","config","source","in_original","result","slack_ticks","ref_score","risk","predicted_peak"])
        w.writerows(rows)
    save(target/"beam.json",beam)
    save(target/"result.json",dict(case=label,arm=name,gen=gen,ranking=rank,width=width,budget=budget,counts=dict(counts),
                                 expired=expired,stages=stages,search_s=search_s,total_s=elapsed,certificates=certs))
    safe=[s for s in certs if s["status"]=="SAFE"]
    print(label,name,"SAFE",len(safe),min([s["E"] for s in safe],default=None),"minPeak",
          min([s["peak"] for s in certs],default=None),round(elapsed,2),"s",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",nargs="+",default=["L800","L640","L480","L320"],choices=["L800","L640","L480","L320"])
    args=parser.parse_args()
    assert any(w["origin"]=="not_generated" and w["status"]=="SAFE" for r in load(ROOT/"data/diagnostic/summary.json") for w in r.get("witnesses",[]))
    assert len(load(ROOT/"data/diagnostic_checks/checks.json"))>=6
    for case in args.cases:
        for arm in ARMS:
            run(case,*arm)
