"""Optional single round of prefix scoring, an ordinary baseline and coverage audit."""
from collections import Counter,defaultdict
import csv
import gzip
import json
from study import *
from retain import shortlist,prediction
from decisions import BUDGETS

def cost_policy(c,j,pool,rule,counts,forecasts):
    if rule not in ("time_cost","feasible_cost"):
        return retain(c,j,pool,rule,counts,forecasts)
    ordered=sorted(pool,key=lambda s:(round(s["energy"],11),s["config"]))
    original=diverse(ordered,False);states=shortlist(ordered,original)
    scores=[];eligible=[]
    for s in states:
        start=len(forecasts)
        prediction(c,s,j+1,rule=="feasible_cost",counts,forecasts)
        probes=forecasts[start:]
        timed=[v for v in probes if v["ok"]]
        good=[v for v in timed if rule=="time_cost" or v["projected_peak"]<=80]
        reason="available" if good else "predicted_hot_only" if timed else "no_timed_probe"
        counts[reason]+=1
        best=min(good,key=lambda v:(round(float(v["ref_cost"]),11),tuple(v["action"]))) if good else None
        scores.append(dict(id=s["id"],reason=reason,timed=len(timed),feasible=len(good),
                      probe=best["action"] if best else None,cost=best["ref_cost"] if best else None))
        if best:
            eligible.append((round(float(best["ref_cost"]),11),s["config"],s))
    fourth=min(eligible,key=lambda t:t[:2])[2] if eligible else original[3]
    return [*original[:3],fourth],scores

def cost_search(c,case,rule,baseline_cut):
    dest=OUT/"prefix"/case/rule
    if (dest/"orders.json").exists():return
    gen="O" if rule=="C2" else "H"
    pool,info,raw=build(c,gen,"original" if rule=="C2" else rule,cost_policy)
    order=certify_order(c,pool,"legacy" if rule=="C2" else "safe_energy",info["build_s"],wall=baseline_cut)
    raw_pool(dest,pool,info,raw);save(dest/"orders.json",[order])
    print("prefix",case,rule,winner(order["records"][:4]).get("E"),flush=True)

def phase2():
    assert load(OUT/"terminal_decision.json")["run_stage2"]
    rows=[]
    for case in CASES:
        c=case_for(case)
        src=OUT/"terminal"/case
        def historic(rule):
            return next(o for o in load(src/("H_"+rule)/"orders.json") if o["method"]=="safe_energy")
        base=historic("original")
        # Cost of cold generation is charged to each method. Give the ordinary
        # run enough time to appear at the 4/8/16 total-time cutoffs.
        for rule in ("time_cost","feasible_cost","C2"):
            cost_search(c,case,rule,base["records"][15]["total_s"])
        for rule in ("original","guarded","time_cost","feasible_cost","C2"):
            o=historic(rule) if rule in ("original","guarded") else load(OUT/"prefix"/case/rule/"orders.json")[0]
            # Prefix comparison uses the same cap of 16 across policies even
            # when one trace also contains optional anytime observations.
            for k in BUDGETS:
                limit=base["records"][k-1]["total_s"]
                for mode,recs in (("count",o["records"][:k]),("time",[r for r in o["records"][:16] if r["total_s"]<=limit])):
                    rows.append(dict(case=case,rule=rule,budget=k,comparison=mode,limit=limit,
                                build_s=o["build_s"],sort_s=o["rank_s"],**outcome(recs)))
    write_rows(OUT/"prefix_ablation.csv",rows)

def coverage():
    # Offline, after selection. Only compare identical complete sets of prefix IDs.
    source=SRC/"data/same_pool"
    with (source/"fixed_suffix_labels.csv").open(encoding="utf-8-sig") as f:
        labels=defaultdict(dict)
        for v in csv.DictReader(f):
            labels[(v["generator"],int(v["window"]))][v["id"]]=v["status"]
    with (source/"pools.csv").open(encoding="utf-8-sig") as f:
        old=list(csv.DictReader(f))
    result=[]
    for rule in ("time_cost","feasible_cost"):
        d=OUT/"prefix/L800"/rule
        with gzip.open(d/"scores.json.gz","rt") as f:scores=json.load(f)
        with gzip.open(d/"actions.csv.gz","rt") as f:
            observed=defaultdict(set)
            for z in csv.DictReader(f):
                if z["result"]=="valid":observed[int(z["window"])].add(z["config"])
        for j,sc in enumerate(scores,1):
            ids=observed[j];hashed=digest("".join(sorted(ids)).encode())
            for h in old:
                if int(h["window"])!=j or h["pool_digest"]!=hashed:continue
                group=labels[h["generator"],j];slate=[v["id"] for v in sc]
                covered=sum(k in group for k in slate)
                inside=sum(group.get(k)=="SAFE" for k in slate)
                outside=sum(z=="SAFE" and k not in slate for k,z in group.items())
                result.append(dict(rule=rule,window=j,matched_generator=h["generator"],pool=len(ids),slate=len(slate),
                              labeled=len(group),known_inside=covered,safe_inside=inside,safe_outside=outside,
                              coverage_failure=covered==len(slate) and inside==0 and outside>0))
            if not any(x["rule"]==rule and x["window"]==j for x in result):
                result.append(dict(rule=rule,window=j,pool=len(ids),slate=len(sc),matched_generator=None,coverage_failure=False))
    write_rows(OUT/"coverage.csv",result)
    save(OUT/"coverage_decision.json",dict(witnesses=[r for r in result if r["coverage_failure"]]))

if __name__=="__main__":
    phase2();coverage()
