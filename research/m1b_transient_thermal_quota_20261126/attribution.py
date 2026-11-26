"""Counterfactual proposal membership at IDENTICAL scheduling and thermal prefixes."""
import csv
import gzip
from collections import defaultdict
from base import ROOT,M1,Case,WINDOW,np,digest,load,save,window_types,materialize
from generator import anchors,capacity,load_planes,synthesize
from search_b import grouped_means


def advance(c,parent,j,action):
    t,a,b=window_types(c,j)
    cfg=parent["config"]+c.extension(t,a,b,*action)
    lo=j*WINDOW
    end=(j+1)*WINDOW
    final=j==c.windows-1
    right=c.p.horizon if final else end
    l=c.ledger(cfg,lo,right,2500,final,True)
    temp=parent["temperature"]
    for i,mean in enumerate(l[8]):
        temp=c.propagate(temp,mean,min(2500,right-lo-i*2500)/WINDOW)
    return dict(config=cfg,f=l[2],k=l[3],temperature=temp)


def sets(c,parent,j,pair,screened=False):
    g,n=pair
    o={v[2:] for v,_ in c.candidates(j,parent) if v[:2]==pair}
    t,a,b=window_types(c,j)
    time=load_planes(c,j,parent,g,n,a,b)
    center=c.eng.quota(parent,j,pair,(a,b))
    pilots,bal=anchors(time,center,a,b)
    vals,obs=[],[]
    lo=j*WINDOW
    final=j==c.windows-1
    right=c.p.horizon if final else lo+WINDOW
    fine=500 if final else 2500
    for xy in pilots:
        cfg=parent["config"]+c.extension(t,a,b,g,n,*xy)
        l=c.ledger(cfg,lo,right,fine,final,True)
        vals.append(l[1])
        if final:
            ds=np.minimum(fine,right-lo-fine*np.arange(len(l[8])))/WINDOW
            obs.append(np.vstack((grouped_means(l[8][:20],ds[:20],5),l[8][20:])))
        else:
            obs.append(l[8])
    durations=np.r_[np.repeat(.25,4),ds[20:]] if final else np.repeat(.25,4)
    planes=capacity(c,parent["temperature"],pilots,np.array(obs),durations,not final)
    cost=np.linalg.solve(np.column_stack((np.ones(3),pilots)),vals)
    groups={}
    if screened:
        from collections import Counter
        from time_check import make_filter
        checker=make_filter(c,parent,j,g,n,Counter())
    else:
        checker=None
    for gtype,inequalities in (("N",np.empty((0,3))),("H",planes)):
        generated=synthesize(time,inequalities,pilots,bal,cost,a,b,len(o),checker)
        for xy in sorted(o):
            if len(generated)==len(o):
                break
            if xy not in generated:
                generated.append(xy)
        groups[gtype]=set(generated)
    return o,groups["N"],groups["H"],pilots,planes


def empty(c):
    return dict(config=b"",f=(0,0),k=(0,0),temperature=c.p.initial)


def main():
    out=ROOT/"data/audit"
    out.mkdir(exist_ok=True,parents=True)
    rows=[]
    for directory in sorted((ROOT/"data/search").glob("*/HT_w4b4")):
        r=load(directory/"result.json")
        records=r["certificates"]
        best=min(records,key=lambda v:(v["status"]!="SAFE",v["E"] if v["status"]=="SAFE" else v["peak"]))
        case=r["case"]
        c=Case(case,out)
        history=next(v["history"] for v in load(directory/"beam.json") if v["id"]==best["config"])
        logs=defaultdict(set)
        with gzip.open(directory/"proposals.csv.gz","rt") as f:
            for z in csv.DictReader(f):
                logs[(int(z["window"]),z["parent"],int(z["g"]),int(z["n"]))].add((int(z["x"]),int(z["y"])))
        p=empty(c)
        for j,action in enumerate(history):
            g,n,x,y=action
            o,ng,hg,pilots,planes=sets(c,p,j,(g,n))
            parent=digest(p["config"])
            assert hg==logs[(j+1,parent,g,n)]
            v=(x,y)
            rows.append(dict(case=case,plan=best["plan"],status=best["status"],window=j+1,parent=parent,
                        g=g,n=n,x=x,y=y,in_O=v in o,in_N=v in ng,in_H=v in hg,pilot=v in pilots,
                        H_only_points=len(hg-ng),N_only_points=len(ng-hg),
                        quota_model_peak=float(max(planes@np.array([1,x,y])))))
            p=advance(c,p,j,action)
        assert digest(p["config"])==best["config"]
    with (out/"winning_paths.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    c=Case("L800",out)
    base=load(ROOT/"data/diagnostic/cold_w10.json")
    p=empty(c)
    for j,action in enumerate(base["reference_actions"][:9]):
        p=advance(c,p,j,action)
    assert digest(p["config"])==base["parent"]
    positives=[]
    with gzip.open(ROOT/"data/diagnostic/cold_w10.csv.gz","rt") as f:
        for z in csv.DictReader(f):
            if z["physical_status"]=="safe_bound":
                g,n,x,y=[int(z[s]) for s in ("g","n","x","y")]
                o,ng,hg,pilots,planes=sets(c,p,9,(g,n))
                xy=(x,y)
                positives.append(dict(action=(g,n,x,y),in_O=xy in o,in_N=xy in ng,in_H=xy in hg,
                             planned_peak=max(planes@np.array([1,x,y])),cert_peak=float(z["peak_hi"])))
    save(out/"archived_prefix_recall.json",positives)
    print("winning-path membership checked",len(rows),"steps; saved prefix recall",
          [sum(v[k] for v in positives) for k in ("in_O","in_N","in_H")])


if __name__=="__main__":
    main()
