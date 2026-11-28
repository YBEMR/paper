"""Aggregate frozen SAFE certificates, common nominations and the complete timing ledger."""
import bisect
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_center_confirmation"))
from analyze_final import CASES, COSTS, compare, distance, summarize_runs

def read(p):
    return json.loads(p.read_bytes())

def write(p,rows,defaults=()):
    fields=list(dict.fromkeys([*defaults,*(k for r in rows for k in r)]))
    with p.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fields,lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def fmt(n,k=5):
    return "—" if n is None else f"{n:.{k}f}"

def md(head,rows):
    return ["|"+"|".join(map(str,r))+"|" for r in [head,["---"]*len(head),*rows]]

def plot(records,budget,out):
    fig,axes=plt.subplots(4,3,figsize=(12,11),layout="constrained")
    curves=[]
    for c,ax in zip(CASES,axes.flat):
        for arm,name,col,style in [("A","Two-stage","#21577a","-"),("B","Direct thermal","#ad4b28","--")]:
            history=[records[c,arm,budget,i]["updates"] for i in (1,2,3)]
            times=[[e["t"] for e in r] for r in history]
            xs,ys=[],[]
            for t in sorted({e["t"] for r in history for e in r}|{budget}):
                index=[bisect.bisect_right(tt,t)-1 for tt in times]
                values=[r[i]["J"] for r,i in zip(history,index) if i>=0]
                median=st.median(values) if len(values)>=2 else None
                curves.append(dict(case=c,arm=arm,t=t,successes=len(values),median_J=median))
                if median is not None:
                    xs.append(t);ys.append(median)
            ax.step(xs,ys,where="post",label=name,color=col,linestyle=style)
        ax.set(xlim=(0,budget),title=c,xlabel="End-to-end time (s)",ylabel="Certified energy (J)")
        ax.grid(alpha=.22);ax.ticklabel_format(axis="y",useOffset=False)
    axes[0,0].legend(fontsize=8)
    fig.savefig(out/"energy_vs_time.png",dpi=150)
    plt.close(fig)
    write(out/"tables/curve.csv",curves)

def load_records(path,b):
    records={}
    for c in CASES:
        with gzip.open(path/f"{c}.json.gz","rt") as f:
            data=json.load(f)
        assert len(data)==6
        for z in data:
            r=z["row"]
            key=(c,r["arm"],b,r["repeat"])
            assert key not in records and r["case"]==c and r["budget_s"]==b
            records[key]=z
    assert len(records)==72
    return records

def pair(c,a,b,ctx):
    x,y=a["row"],b["row"]
    common=set(r["mapping"] for r in a["maps"])&set(r["mapping"] for r in b["maps"])
    return dict(case=c,**ctx,A_J=x["final_J"],B_J=y["final_J"],A_low=x["low_J"],A_high=x["high_J"],
                B_low=y["low_J"],B_high=y["high_J"],**compare(y,x),A_plan=x["plan"],B_plan=y["plan"],
                A_mapping=x["mapping"],B_mapping=y["mapping"],common_nominations=len(common),
                A_winner_nominated_B=x["mapping"] in {r["mapping"] for r in b["maps"]},
                A_winner_visited_B=x["mapping"] in b["visited"],B_winner_visited_A=y["mapping"] in a["visited"],
                A_completed=x["completed_maps"],B_completed=y["completed_maps"],**distance(a["config"],b["config"]))

def rank_maps(left,right):
    for mid in sorted({r["mapping"] for z in (left,right) for r in z["maps"]}):
        x=next((r for r in left["maps"] if r["mapping"]==mid),{})
        y=next((r for r in right["maps"] if r["mapping"]==mid),{})
        exact=bool(x and y and x["seed"]==y["seed"] and x["trace"]==y["trace"])
        yield dict(mapping=mid,A_rank=x.get("rank"),B_rank=y.get("rank"),A_seed=x.get("seed"),B_seed=y.get("seed"),
                   same_seed_and_trace=exact,A_before_J=x.get("before_J"),B_before_J=y.get("before_J"),
                   A_after_J=x.get("after_J"),B_after_J=y.get("after_J"),A_completed=x.get("stages_complete"),B_completed=y.get("stages_complete"),
                   A_status=x.get("seed_status"),B_status=y.get("seed_status"),A_recovered=x.get("recovered"),B_recovered=y.get("recovered"),
                   A_final=x.get("final_winner"),B_final=y.get("final_winner"),
                   A_higher=bool(x.get("after_lo") is not None and y.get("after_hi") is not None and y["after_hi"]<x["after_lo"]),
                   B_higher=bool(y.get("after_lo") is not None and x.get("after_hi") is not None and x["after_hi"]<y["after_lo"]))

def main(budget):
    out=ROOT/"results"/str(budget)
    tab=out/"tables";tab.mkdir(parents=True)
    records=load_records(out/"reduced",budget)
    previous=load_records(ROOT/"results/60/reduced",60) if budget==600 else {}
    rows=[z["row"] for z in records.values()]
    start_fault=sum(r["s"] for r in read(ROOT/"initialization_faults.json")["entries"]) if budget==60 else 0
    charged=sum(r["charged_s"] for r in rows)
    assert charged+start_fault<=budget*72
    write(tab/"cells.csv",rows)
    write(tab/"improvements.csv",[dict(repeat=z["row"]["repeat"],**u) for z in records.values() for u in z["updates"]])
    slots=[m for z in records.values() for m in z["maps"]]
    write(tab/"mapping_energy.csv",slots,["case","arm","repeat","rank"])
    write(tab/"stage_energy.csv",[m for z in records.values() for m in z["stages"]],["case","arm","repeat","rank"])
    hot=[m for m in slots if m["seed_status"]=="HOT"]
    write(tab/"hot_witnesses.csv",hot,["case","arm","repeat","rank","seed","recovered","final_winner"])
    pairs=[];medians=[];flows=[];diagnoses=[];examples=[]
    old_records=[(budget,records)]+([(60,previous)] if previous else [])
    common=[]
    for c in CASES:
        for arm in ("A","B"):
            runs=[records[c,arm,budget,i]["row"] for i in (1,2,3)]
            flows.append(dict(case=c,arm=arm,budget_s=budget,**summarize_runs(runs)))
        for oldbudget,baseline in old_records:
            old=[baseline[c,"A",oldbudget,i] for i in (1,2,3)]
            new=[records[c,"B",budget,i] for i in (1,2,3)]
            ctx=dict(A_s=oldbudget,B_s=budget)
            local=[pair(c,x,y,dict(**ctx,repeat=i)) for i,(x,y) in enumerate(zip(old,new),1)]
            pairs.extend(local)
            a,b=(summarize_runs([z["row"] for z in rz]) for rz in (old,new))
            vs=compare(b,a) if a["reliable"] and b["reliable"] else dict(delta_J=None,delta_pct=None,strict="unpaired")
            med=dict(case=c,**ctx,A_SAFE=a["safe"],B_SAFE=b["safe"],A_J=a["final_J"],B_J=b["final_J"],A_low=a["low_J"],A_high=a["high_J"],
                     B_low=b["low_J"],B_high=b["high_J"],**vs,**{"repeat_"+k:sum(p["strict"]==k for p in local) for k in ("win","overlap","loss","unpaired")})
            medians.append(med)
            if oldbudget==budget:
                for i,(x,y) in enumerate(zip(old,new),1):
                    common.extend(dict(case=c,repeat=i,**r) for r in rank_maps(x,y))
                if vs["strict"]=="loss":
                    matches=[r for r in common if r["case"]==c]
                    exact=[r for r in matches if r["same_seed_and_trace"] and r["A_completed"] and r["B_completed"]]
                    relevant=[r for r in exact if r["A_final"] or r["B_final"]]
                    diagnoses.append(dict(case=c,delta_J=vs["delta_J"],delta_pct=vs["delta_pct"],
                        same_seed_both_completed=len(exact),same_seed_B_higher=sum(r["B_higher"] for r in exact),
                        matched_finalists=len(relevant),matched_finalists_B_higher=sum(r["B_higher"] for r in relevant),
                        different_winners=sum(p["A_mapping"]!=p["B_mapping"] for p in local),
                        A_winner_missing_B_nomination=sum(not p["A_winner_nominated_B"] for p in local),
                        unequal_completions=sum(p["A_completed"]!=p["B_completed"] for p in local)))
                    examples.extend(dict(case=c,repeat=r["repeat"],mapping=r["mapping"],seed=r["A_seed"],
                        A_after_J=r["A_after_J"],B_after_J=r["B_after_J"],B_minus_A_J=r["B_after_J"]-r["A_after_J"])
                        for r in relevant if r["A_after_J"] is not None and r["B_after_J"] is not None)
    write(tab/"flows.csv",flows);write(tab/"repeat_pairs.csv",pairs);write(tab/"median_pairs.csv",medians)
    write(tab/"common_mappings.csv",common,["case","repeat","mapping"])
    write(tab/"loss_diagnosis.csv",diagnoses,["case","delta_J","delta_pct"])
    write(tab/"matched_finalists.csv",examples,["case","repeat","mapping","seed","A_after_J","B_after_J","B_minus_A_J"])
    timing=[dict(arm=a,**{k:st.mean(r[k] for r in rows if r["arm"]==a) for k in COSTS}) for a in ("A","B")]
    write(tab/"overheads.csv",timing)
    plot(records,budget,out)
    same=[p for p in medians if p["A_s"]==budget]
    reliable=[p for p in same if p["strict"]!="unpaired"]
    missed=[p["case"] for p in same if p["A_SAFE"]>=2 and p["B_SAFE"]<2]
    average=st.mean(p["delta_pct"] for p in reliable) if reliable else None
    maximum=max(reliable,key=lambda p:p["delta_pct"],default=None)
    hot_counts={a:{k:sum(m[k] for m in hot if m["arm"]==a) for k in ("started","recovered","improved_global","final_winner","stages_complete")}|{"nominated":sum(m["arm"]==a for m in hot)} for a in ("A","B")}
    same_hot=[r for r in common if r["same_seed_and_trace"] and r["A_status"]=="HOT"]
    extra_hot=[r for r in same_hot if not r["A_completed"] and r["B_completed"] and r["B_recovered"] and not r["A_recovered"]]
    lost_hot=[r for r in same_hot if r["A_recovered"] and not r["B_recovered"]]
    result=dict(stage_s=budget,units=len(rows),charged_s=charged,initialization_fault_s=start_fault,total_core_s=charged+start_fault,
                safe={a:sum(r["final_J"] is not None for r in rows if r["arm"]==a) for a in ("A","B")},
                reliable={a:sum(r["reliable"] for r in flows if r["arm"]==a) for a in ("A","B")},
                missed=missed,mean_flow_delta_pct=average,maximum=maximum,strict=dict(Counter(p["strict"] for p in same)),hot=hot_counts,
                matched_hot=len(same_hot),newly_finished_hot=len(extra_hot),lost_matched_hot=len(lost_hot),
                phase2_review=bool(missed or not reliable or average>0.01 or maximum["delta_pct"]>0.05 or lost_hot))
    if previous:
        cross=[p for p in medians if p["A_s"]==60]
        result["B600_vs_A60"]={"strict":dict(Counter(p["strict"] for p in cross)),"mean_pct":st.mean(p["delta_pct"] for p in cross if p["delta_pct"] is not None)}
    (out/"decision.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    from narrative import report
    report(out,result,flows,medians,pairs,diagnoses,examples,timing)

if __name__=="__main__":
    main(int(sys.argv[1]))
