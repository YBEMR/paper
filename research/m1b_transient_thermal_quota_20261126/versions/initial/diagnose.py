import csv
import gzip
from collections import Counter
from time import perf_counter
from base import Case, M1, ROOT, WINDOW, np, p1, digest, load, save, materialize, window_types, check_base
from events import suffix_events
from heat import integrate

OUT=ROOT/"data/diagnostic"
EMPTY=np.empty(0,np.int64)


def entry(c,trace,left):
    p=c.p
    done=trace[:,1]<=left
    last=trace[done][-1]
    temp=last[18:22].copy()
    peakhi=max(trace[done,22:26].max(),max(p.initial))
    peaklo=max(trace[done,18:22].max(),max(p.initial))-1e-6
    energy=trace[done,26:30].sum()+.3*left/WINDOW
    if last[1]<left:
        row=trace[np.count_nonzero(done),:14].copy()
        row[1]=left
        partial=integrate(row.reshape(1,14),temp,p.G,p.cap,35.,EMPTY,True)
        energy+=partial[7].sum()
        peakhi=max(peakhi,max(partial[2])+1e-6)
        peaklo=max(peaklo,max(partial[1])-1e-6)
        temp=partial[10][-1,4:8].copy()
    assert trace[:,30].max()<1e-7
    return temp,peaklo,peakhi,energy


def same_events(ev,tr,left):
    compare=tr[tr[:,1]>left,:14].copy()
    compare[0,0]=left
    # Redundant adjacent intervals may have the same four-node physics.
    all_ticks=np.unique(np.r_[ev[:,0],compare[:,0]])
    for table,other in ((ev,compare),):
        a=table[np.searchsorted(table[:,1],all_ticks,side="right"),2:]
        b=other[np.searchsorted(other[:,1],all_ticks,side="right"),2:]
        assert np.max(abs(a-b))<1e-12


def probe(c,label,arm,rank,j):
    past=M1/"data/e1b/L800"/arm
    beam=load(past/"beam.json")
    final=load(past/"result.json")["certificates"]
    result=final[rank-1]
    hist=next(r["history"] for r in beam if r["id"]==result["id"])
    cfg=materialize(c,hist)
    assert digest(cfg)==result["id"]
    left=j*WINDOW
    prefix=materialize(c,hist[:j])
    prefix_id=digest(prefix)
    assert any(r["id"]==prefix_id and r["window"]==j-1 for r in beam)
    t,a,b=window_types(c,j)
    assert (a,b)==(40,60)
    end=len(prefix)+len(t)
    continuation=cfg[end:]
    old={}
    with gzip.open(past/"trials.csv.gz","rt") as f:
        for row in csv.DictReader(f):
            if row["parent"]==prefix_id and int(row["window"])==j:
                old[row["config"]]=row["result"]
    kept={r["id"] for r in beam if r["window"]==j}
    known={s["id"] for s in final}
    certified_children={digest(materialize(c,r["history"][:j+1])) for r in beam if r["id"] in known}
    with np.load(past/"evidence/L800"/result["plan"]/"trace.npz") as f:
        trace=f["events"]
    temp,p_lo,p_hi,e_prefix=entry(c,trace,left)
    info=dict(source=arm,terminal_rank=rank,source_plan=result["plan"],window=j+1,parent=prefix_id,
              entry_C=temp.tolist(),prefix_peak_lower=p_lo,prefix_peak_upper=p_hi,reference_actions=hist,
              suffix_scope="all final actions" if not continuation else "one varying window, recorded later actions")
    if label=="hot":
        assert p_lo>80
        return dict(info,reason="certified prefix already exceeds limit; all continuations fail",witness=True)
    prefix_ledger=c.ledger(prefix,0,left,WINDOW,False,False)
    f,k=prefix_ledger[2:4]
    original=c.ledger(cfg,0,c.p.horizon,WINDOW,True,False)
    same_events(suffix_events(c,cfg,original,left),trace,left)
    reference=integrate(suffix_events(c,cfg,original,left),temp,c.p.G,c.p.cap,35.,EMPTY,True)
    assert abs(max(p_hi,max(reference[2]))-result["peak"])<1e-5
    deadline=max(c.args[5][len(prefix):end])
    best={}
    counts=Counter()
    ext_cache={}
    legal=0
    name=f"{label}_w{j+1}"
    started=perf_counter()
    with gzip.open(OUT/(name+".csv.gz"),"xt",newline="",encoding="utf-8") as stream:
        w=csv.writer(stream)
        w.writerow(["g","n","x","y","origin","certified_descendant","physical_status","E_J","peak_lo","peak_hi","slack_ticks"])
        for g,n in p1.PAIRS:
            d=c.eng.length
            for x in range(a+1):
                for y in range(b+1):
                    lg=(a-x)*d["A",2,g]+(b-y)*d["B",2,g]
                    ln=x*d["A",3,n]+y*d["B",3,n]
                    if max(max(left,f[0])+lg,max(left,f[1])+ln)>deadline:
                        counts["time_bound"]+=1
                        w.writerow([g,n,x,y,"","","time_bound","","","",""])
                        continue
                    mask=ext_cache.get((x,y))
                    if mask is None:
                        mask=np.frombuffer(c.extension(t,a,b,0,0,x,y),np.uint8)>0
                        ext_cache[x,y]=mask
                    tail=np.where(mask,n+10,g).astype(np.uint8).tobytes()
                    child=prefix+tail
                    child_id=digest(child)
                    trial=child+continuation
                    orig=("not_generated" if child_id not in old else "generated_pruned" if child_id not in kept
                          else "full_certified" if digest(trial) in known else "kept_not_full_certified")
                    descendant=child_id in certified_children
                    l=c.ledger(trial,0,c.p.horizon,WINDOW,True,False)
                    if not l[0]:
                        counts["timing"]+=1
                        w.writerow([g,n,x,y,orig,int(descendant),"timing","","","",l[-1]])
                        continue
                    legal+=1
                    ev=suffix_events(c,trial,l,left)
                    q=integrate(ev,temp,c.p.G,c.p.cap,35.,EMPTY,True)
                    # The frozen cooperative system is a contraction in infinity norm.
                    # Initial uncertainty 1e-6 C covers the archived and split entry roundoff.
                    lo=max(p_lo,max(q[1])-1e-6)
                    hi=max(p_hi,max(q[2])+1e-6)
                    energy=e_prefix+q[7].sum()+.3*(c.p.horizon-left)/WINDOW
                    status=("outside" if lo>100 else "hot" if lo>80 else "safe_bound"
                            if hi<=80 and min(q[3])-1e-6>=20 and q[6]<=1e-6 and hi-lo<=.001 else "unresolved")
                    counts[(orig,status)]+=1
                    w.writerow([g,n,x,y,orig,int(descendant),status,energy,lo,hi,l[-1]])
                    key=(orig,status)
                    if status in ("safe_bound","unresolved") and (key not in best or energy<best[key][0]):
                        best[key]=(energy,[g,n,x,y],trial,hi)
    witnesses=[]
    for (orig,status),(energy,action,config,hi) in best.items():
        cert,_=c.certify(config)
        m=cert["metrics"]
        assert abs(energy-m["E_J"])<1e-6 and abs(hi-max(m["peak_hi"]))<1e-5
        if status=="safe_bound":
            assert m["status"]=="SAFE"
        witnesses.append(dict(origin=orig,bounded_status=status,status=m["status"],action=action,E_J=m["E_J"],
                              peak_hi=max(m["peak_hi"]),plan=cert["plan_sha256"],bounds=m["E_bounds"]))
    out=dict(info,actions=sum(counts.values()),timing_legal=legal,elapsed_s=perf_counter()-started,
             histogram={"|".join(k) if isinstance(k,tuple) else k:v for k,v in counts.items()},witnesses=witnesses)
    assert out["actions"]==30*41*61
    save(OUT/(name+".json"),out)
    print(name,legal,out["histogram"],[(w["origin"],w["status"],round(w["E_J"],4)) for w in witnesses],flush=True)
    return out


def main():
    check_base()
    OUT.mkdir(parents=True,exist_ok=True)
    c=Case("L800",OUT)
    rows=[]
    for j in (7,8,9):
        for label,arm,rank in (("cold","D2",2),("regular","C2",1),("hot","D2",1)):
            cached=OUT/f"{label}_w{j+1}.json"
            if cached.exists():
                rows.append(load(cached))
            else:
                item=probe(c,label,arm,rank,j)
                save(cached,item)
                rows.append(item)
    save(OUT/"summary.json",rows)


if __name__=="__main__":
    main()
