"""Blind searches and an anytime ordinary baseline. Offline labels are never imported."""
import argparse
import csv
import gzip
from collections import Counter
from time import perf_counter as clock
from common import CASES,DATA,Case,WINDOW,initial,np,p1,save,load,diverse
from expand import expand
from retain import retain,RULES

FIELDS=("window","parent","g","n","x","y","config","source","in_original","result","slack","cost","risk","peak")
def gzjson(path,obj):
    with gzip.open(path,"wb",compresslevel=5) as f:
        f.write(p1.raw(obj))

def env_case(label):
    c=Case(label,DATA/"physical")
    c.ledger(bytes([0]),0,WINDOW,2500,False,False)
    c.ledger(bytes([0]),0,WINDOW,2500,False,True)
    c.propagate(c.p.initial,np.r_[c.args[9][:,0],c.args[10][:,0]],1.)
    from heat import integrate
    ev=np.array([[0,1,*c.args[9][:,0],*c.args[10][:,0],*c.args[9][:,0]]],float)
    integrate(ev,c.p.initial,c.p.G,c.p.cap,35.,np.empty(0,np.int64),True)
    from time_check import make_filter
    make_filter(c,initial(c),0,0,0,Counter())(np.array([[0,0]],np.int64))
    return c

def snapshot(s):
    return {k:v for k,v in s.items() if k!="config"}

def search(c,gen,rule,width,budget,start,deadline,seen):
    ordinary=gen=="O"
    states=[initial(c)]
    counts=Counter();trials=[]; stages=[]; beam=[]; predictions=[]; scores=[]; certs=[]
    status="complete"
    for j in range(c.windows):
        tick=clock()
        pool,expired=expand(c,j,states,gen,not ordinary,counts,trials,deadline)
        generation=clock()-tick
        if expired or not pool:
            status="time_during_expansion" if expired else "empty"
            stages.append(dict(window=j+1,valid=len(pool),generation_s=generation,partial=True))
            states=[];break
        tick=clock()
        if ordinary:
            ordered=sorted(pool.values(),key=lambda s:(round(s["energy"],11),s["config"]))
            states=diverse(ordered,j+1==c.windows)
            chosen={s["id"] for s in states}
            limit=budget if j+1==c.windows else width
            states+= [s for s in ordered if s["id"] not in chosen][:max(0,limit-len(states))]
        else:
            states,metrics=retain(c,j,list(pool.values()),rule,counts,predictions)
            scores.append(metrics)
        selection=clock()-tick
        counts["retention_s"]+=selection
        if rule in ("time_energy","suffix") and j+1<c.windows:
            counts["look_inclusive_s"]+=selection
        beam.extend([dict(window=j+1,rank=i,**snapshot(s)) for i,s in enumerate(states,1)])
        stages.append(dict(window=j+1,valid=len(pool),generation_s=generation,retention_s=selection))
    pre_cert=clock()-start
    for i,s in enumerate(states,1):
        if s["id"] in seen:
            counts["cached_cert"]+=1
            continue
        if clock()>=deadline:
            status="time_before_certificate";break
        cert_tick=clock()
        cert,_=c.certify(s["config"])
        assert abs(s["energy"]-cert["E35_J"])<1e-8
        measured=clock()
        seen.add(s["id"])
        m=cert["metrics"]
        certs.append(dict(rank=i,config=s["id"],plan=cert["plan_sha256"],E=m["E_J"],status=m["status"],
                          peak=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],interval=m["E_bounds"],
                          elapsed_s=measured-start,cert_s=measured-cert_tick,in_time=measured<=deadline))
        if measured>deadline:
            status="certificate_completed_after_cutoff";break
    r=dict(generator=gen,rule=rule,width=width,budget=budget,counts=dict(counts),certificates=certs,
           stages=stages,status=status,before_cert_s=pre_cert,elapsed_s=clock()-start)
    return r,(trials,beam,predictions,scores)

def persist(folder,r,raw):
    folder.mkdir(parents=True,exist_ok=True)
    trials,beam,forecasts,scores=raw
    with gzip.open(folder/"candidates.csv.gz","wt",encoding="utf-8",newline="") as f:
        w=csv.writer(f);w.writerow(FIELDS);w.writerows(trials)
    gzjson(folder/"probe_details.json.gz",forecasts)
    gzjson(folder/"fourth_slot_scores.json.gz",scores)
    save(folder/"beam.json",beam)
    save(folder/"result.json",r)

def fixed(label,gen,rule):
    target=DATA/"search"/label/(gen+"_"+rule)
    if (target/"result.json").exists():
        return
    c=env_case(label); start=clock()
    r,raw=search(c,gen,rule,4,4,start,start+300,set())
    assert r["status"]=="complete" and len(r["certificates"])==4
    persist(target,r,raw)
    print(label,gen,rule,round(r["elapsed_s"],2),[round(z["E"],6) for z in r["certificates"] if z["status"]=="SAFE"],flush=True)

def ordinary(label):
    folder=DATA/"ordinary"/label
    if (folder/"budget.json").exists():
        return
    budgets={p.parent.name:load(p)["elapsed_s"] for p in (DATA/"search"/label).glob("*/result.json")}
    c=env_case(label);start=clock(); deadline=start+max(budgets.values());seen=set(); waves=[]
    for width,budget in ((4,12),(8,16),(16,32),(32,64)):
        if clock()>=deadline:break
        r,raw=search(c,"O","original",width,budget,start,deadline,seen)
        waves.append((r,raw))
        if r["status"]!="complete":break
    total=clock()-start
    for r,raw in waves:
        persist(folder/("w"+str(r["width"])),r,raw)
    save(folder/"budget.json",dict(cutoffs=budgets,actual_s=total))
    print("ordinary",label,round(total,2),[len(r["certificates"]) for r,_ in waves],flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["search","ordinary"])
    parser.add_argument("--cases",nargs="+",default=CASES,choices=CASES)
    args=parser.parse_args()
    for label in args.cases:
        if args.mode=="ordinary":
            ordinary(label);continue
        for gen in (("H","N","Hs") if label=="L800" else ("H",)):
            for rule in RULES:
                fixed(label,gen,rule)
