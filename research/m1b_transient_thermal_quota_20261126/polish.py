import csv
import gzip
from time import perf_counter
from base import ROOT,M1,Case,WINDOW,np,digest,load,save,window_types
from attribution import sets,empty


def projected(c,cfg):
    l=c.ledger(cfg,0,c.p.horizon,2500,True,True)
    if not l[0]:
        return None
    temp=c.p.initial.copy()
    peak=max(temp)
    energy=c.base*c.p.horizon/WINDOW+l[1]
    for i,mean in enumerate(l[8]):
        h=min(2500,c.p.horizon-2500*i)/WINDOW
        nxt=c.propagate(temp,mean,h)
        energy+=h*(mean[4:]@((temp+nxt)*.5-35.))
        peak=max(peak,max(nxt));temp=nxt
    return energy,peak


def run(label):
    root=ROOT/"data/incumbent"/label
    if (root/"result.json").exists():
        return
    root.mkdir(parents=True,exist_ok=True)
    c=Case(label,root)
    if label=="L640":
        src=M1/"data/e1b/L640/C2"
        k=next(v["plan"] for v in load(src/"result.json")["certificates"] if v["status"]=="SAFE")
    else:
        src=M1/"data/e0"
        k=next(v["plan"] for v in load(src/"gate.json")["records"] if v["case"]==label and v["status"]=="SAFE")
    ref=src/"evidence"/label/k
    record=load(ref/"certificate.json")["metrics"]
    inc=bytes(k+(10 if u==3 else 0) for u,k,_ in load(ref/"plan.json")["rows"][1::3])
    start=perf_counter()
    e0,pk=projected(c,inc)
    correction=max(record["peak_hi"])-pk
    p=empty(c)
    catalogs={g:{} for g in ("O","N","H")}
    memo={}
    raw=[]
    for j in range(c.windows):
        lo,hi=c.release.searchsorted([j*WINDOW,(j+1)*WINDOW])
        t,a,b=window_types(c,j)
        for g in range(10):
            for n in range(3):
                o,ng,hg,_,_=sets(c,p,j,(g,n))
                assert len(o)==len(ng)==len(hg)
                for xy in sorted(o|ng|hg):
                    cfg=inc[:lo]+c.extension(t,a,b,g,n,*xy)+inc[hi:]
                    if cfg==inc:
                        continue
                    if cfg not in memo:
                        memo[cfg]=projected(c,cfg)
                    est=memo[cfg]
                    belonging=[s for s,ss in (("O",o),("N",ng),("H",hg)) if xy in ss]
                    raw.append([j+1,g,n,*xy,digest(cfg),"".join(belonging),*(est or (None,None))])
                    if est:
                        for gtype in belonging:
                            catalogs[gtype].setdefault(cfg,(est[0],est[1]+correction,[j+1,g,n,*xy]))
        pre=inc[:hi]
        l=c.ledger(pre,j*WINDOW,(j+1)*WINDOW,2500,False,True)
        temp=p["temperature"]
        for q in l[8]:
            temp=c.propagate(temp,q,.25)
        p=dict(config=pre,f=l[2],k=l[3],temperature=temp)
    results={}
    for gtype,options in catalogs.items():
        low=min(options,key=lambda key:(options[key][0],key))
        ordered=[low,*sorted((v for v in options if v!=low),key=lambda key:(max(0,options[key][1]-80),options[key][0],key))[:3]]
        results[gtype]=[]
        for rank,config in enumerate(ordered,1):
            cert,_=c.certify(config)
            m=cert["metrics"]
            results[gtype].append(dict(rank=rank,action=options[config][2],plan=cert["plan_sha256"],status=m["status"],
                E=m["E_J"],interval=m["E_bounds"],peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],
                strict=m["status"]=="SAFE" and m["E_bounds"][1]<record["E_bounds"][0]))
    with gzip.open(root/"pool.csv.gz","wt",newline="") as f:
        w=csv.writer(f);w.writerow(["window","g","n","x","y","config","generators","estimated_E","uncorrected_peak"])
        w.writerows(raw)
    save(root/"result.json",dict(case=label,incumbent=k,E0=record["E_J"],E0_bounds=record["E_bounds"],peak0=max(record["peak_hi"]),
         bias=correction,valid={k:len(v) for k,v in catalogs.items()},proposals=len(raw),time_s=perf_counter()-start,certificates=results))
    print(label,{k:[round(v["E"],6) for v in vs if v["strict"]] for k,vs in results.items()},flush=True)


if __name__=="__main__":
    for case in ("L640","L480"):
        run(case)
