"""Predefined count/time comparisons and conditional development gates."""
import json
from study import CASES,OUT,load,outcome,save,write_rows

REF=dict(L800=49.601232268650534,L640=39.02409535318941,L480=28.304176646719945,L320=18.6565960304577)
BUDGETS=(4,8,16)

def comparisons(folder):
    orders=load(folder/"orders.json")
    original=next(o for o in orders if o["method"]=="legacy")
    rows=[]
    for k in BUDGETS:
        deadline=original["records"][k-1]["total_s"]
        for o in orders:
            for mode,rec in (("count",o["records"][:k]),("time",[z for z in o["records"] if z["total_s"]<=deadline])):
                rows.append(dict(case=folder.parent.name,pool=folder.name,method=o["method"],budget=k,comparison=mode,
                            time_limit=deadline,build_s=o["build_s"],sorting_s=o["rank_s"],
                            cert_s=sum(z["cert_s"] for z in rec),**outcome(rec)))
    return rows

def stage_gate():
    folders=list((OUT/"terminal").glob("*/*/orders.json"))
    assert len(folders)==30
    table=[r for p in sorted(folders) for r in comparisons(p.parent)]
    write_rows(OUT/"terminal_ablation.csv",table)
    lookup={(r["case"],r["pool"],r["method"],r["budget"],r["comparison"]):r for r in table}
    def val(c,p,m,n=16,mode="count"):
        return lookup[c,p,m,n,mode]["best"]
    main_l800_ok=all(val("L800",p,"legacy") is not None and val("L800",p,"legacy")<=1.001*REF["L800"] for p in ("H_original","H_guarded"))
    stats=[]
    for c in CASES:
        pools=sorted({v["pool"] for v in table if v["case"]==c})
        for mode in ("count","time"):
            a={p:val(c,p,"legacy",16,mode) for p in pools}
            b={p:val(c,p,"safe_energy",16,mode) for p in pools}
            best_a=min((e for e in a.values() if e is not None),default=None)
            best_b=min((e for e in b.values() if e is not None),default=None)
            lost=[p for p in pools if a[p] is None and b[p] is not None]
            stats.append(dict(case=c,mode=mode,legacy_best=best_a,thermal_best=best_b,lost_pools=lost,
                         sufficient=not lost and (best_b is None or (best_a is not None and best_a<=best_b*1.001))))
    simple=main_l800_ok and all(v["sufficient"] for v in stats)
    gaps=[c for c in CASES if val(c,"H_original","safe_energy") is None or val(c,"H_original","safe_energy")>1.005*REF[c]]
    obj=dict(simple_enough=simple,l800_recovery=main_l800_ok,paired=stats,main_pool_quality_gaps=gaps,
             run_stage2=not simple and bool(gaps))
    save(OUT/"terminal_decision.json",obj)
    return obj

def competitive(a,b):
    # a,b map each case to its four-certificate outcome.
    u,v=a["L800"],b["L800"]
    improvement=u["best"] is not None and (v["best"] is None or u["best"]<=.999*v["best"] or
            (u["best"]<=v["best"]+1e-7 and u["first"]<v["first"]))
    controls=all(a[c]["best"] is not None and (b[c]["best"] is None or a[c]["best"]<=1.005*b[c]["best"]) for c in CASES[1:])
    # Earlier SAFE alone does not mean the reference energy was reached earlier.
    return improvement and controls

def method_outcome(case,rule,method):
    if rule in ("original","guarded"):
        path=OUT/"terminal"/case/("H_"+rule)/"orders.json"
    else:
        path=OUT/"prefix"/case/rule/"orders.json"
    records=next(o for o in load(path) if o["method"]==method)["records"][:4]
    return outcome(records),records

def freeze_choice():
    phase=load(OUT/"terminal_decision.json")
    def qualifies(rule,method,base_rule,base_method):
        a={};b={}
        for c in CASES:
            a[c],ar=method_outcome(c,rule,method);b[c],br=method_outcome(c,base_rule,base_method)
            if c=="L800" and b[c]["best"] is not None:
                target=b[c]["best"]+1e-7
                a[c]["first"]=next((r["rank"] for r in ar if r["status"]=="SAFE" and r["E"]<=target),99)
                b[c]["first"]=next(r["rank"] for r in br if r["status"]=="SAFE" and r["E"]<=target)
        return competitive(a,b)
    if qualifies("original","safe_energy","original","legacy"):
        return "original"
    if phase["run_stage2"]:
        for rule in ("time_cost","feasible_cost"):
            if qualifies(rule,"safe_energy","original","safe_energy"):return rule
    return None

if __name__=="__main__":print(json.dumps(stage_gate(),indent=2))
