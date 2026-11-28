"""Analyze only the sealed per-cell observations restored by reduce_lane.py."""
import bisect
import csv
import gzip
import itertools
import json
import statistics as st
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lane import CASES
ROOT=Path(__file__).resolve().parent
TABLE=ROOT/"tables"
PAIRS=(("C","A"),("D","B"),("D","A"))
COSTS=("instance_s","construct_s","search_cert_s","selection_s","handoff_s","ordinary_DP_s","thermal_DP_s","dp_cert_s","other_s")


def write(name,rows,fields=None):
    with (TABLE/name).open("w",newline="",encoding="utf8") as out:
        writer=csv.DictWriter(out,fieldnames=fields or list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare(x,y):
    if x["final_J"] is None or y["final_J"] is None:
        return dict(delta_J=None,delta_pct=None,strict="unpaired")
    delta=x["final_J"]-y["final_J"]
    strict="win" if x["high_J"]<y["low_J"] else "loss" if y["high_J"]<x["low_J"] else "overlap"
    return dict(delta_J=delta,delta_pct=100*delta/y["final_J"],strict=strict)


def distance(x,y):
    if x is None or y is None:
        return dict(requests=None,changed_device=None,same_device_changed_opp=None)
    assert len(x)==len(y)
    return dict(requests=len(x),changed_device=sum(u!=v for (u,k),(v,h) in zip(x,y)),
                same_device_changed_opp=sum(u==v and k!=h for (u,k),(v,h) in zip(x,y)))


def summarize_runs(rows):
    success=[r for r in rows if r["final_J"] is not None]
    values=[r["final_J"] for r in success]
    return dict(safe=len(success),reliable=len(success)>=2,all_three=len(success)==3,
                **{k:st.median(r[k] for r in success) if success else None for k in ("final_J","low_J","high_J","first_safe_s")},
                min_J=min(values,default=None),max_J=max(values,default=None),
                range_J=max(values)-min(values) if values else None,
                range_pct_of_median=100*(max(values)-min(values))/st.median(values) if values else None,
                unique_plans=len({r["plan"] for r in success}),unique_mappings=len({r["mapping"] for r in success}))


def pair_cells(case,rep,new,old,left,right):
    x,y=left["row"],right["row"]
    return dict(case=case,repeat=rep,pair=f"{new}-{old}",new=new,old=old,new_J=x["final_J"],old_J=y["final_J"],
                new_low_J=x["low_J"],new_high_J=x["high_J"],old_low_J=y["low_J"],old_high_J=y["high_J"],
                **compare(x,y),new_plan=x["plan"],old_plan=y["plan"],new_mapping=x["mapping"],old_mapping=y["mapping"],
                **distance(left["config"],right["config"]))


def plot(records):
    data=[]
    for b,arms in ((60,("A","C")),(600,("B","D"))):
        fig,axes=plt.subplots(4,3,figsize=(12,11),layout="constrained")
        for case,ax in zip(CASES,axes.flat):
            for label,color,name in zip(arms,("#24557a","#b44922"),("Original","Center only")):
                histories=[records[case,label,i]["updates"] for i in (1,2,3)]
                events=sorted({e["t"] for run in histories for e in run}|{float(b)})
                stamps=[[e["t"] for e in run] for run in histories]
                xs,ys=[],[]
                for t in events:
                    values=[]
                    for run,times in zip(histories,stamps):
                        index=bisect.bisect_right(times,t)-1
                        if index>=0:
                            values.append(run[index]["J"])
                    val=st.median(values) if len(values)>=2 else None
                    data.append(dict(case=case,setting=label,budget_s=b,t=t,count_SAFE=len(values),median_SAFE_J=val))
                    if val is not None:
                        xs.append(t)
                        ys.append(val)
                ax.step(xs,ys,where="post",label=name,color=color,linestyle="--" if label in "CD" else "-")
                if xs:
                    ax.scatter(xs[0],ys[0],s=10,color=color)
            ax.set(xlim=(0,b),title=case,xlabel="Elapsed time (s)",ylabel="Median SAFE energy (J)")
            ax.ticklabel_format(axis="y",useOffset=False)
            ax.grid(alpha=.22)
        axes[0,0].legend(fontsize=8)
        fig.savefig(ROOT/f"energy_{b}s.png",dpi=160)
        plt.close(fig)
    write("energy_over_time.csv",data)


def main(input_dir):
    TABLE.mkdir(exist_ok=True)
    records={}
    for case in CASES:
        with gzip.open(input_dir/f"{case}.json.gz","rt",encoding="utf8") as stream:
            for rec in json.load(stream):
                r=rec["row"]
                key=(case,r["setting"],r["repeat"])
                assert r["case"]==case and key not in records
                records[key]=rec
    cells=[records[c,a,i]["row"] for c in CASES for a in "ABCD" for i in (1,2,3)]
    assert len(cells)==144 and sum(r["charged_s"] for r in cells)<=47520
    write("cells.csv",cells)
    write("improvements.csv",[dict(repeat=r["row"]["repeat"],setting=r["row"]["setting"],**e)
                              for r in records.values() for e in r["updates"]],
          ["repeat","setting","case","arm","budget_s","t","J","mapping","plan","stage"])
    flows={}
    pairs=[]
    medians=[]
    stability=[]
    assignments=[]
    for c in CASES:
        for a in "ABCD":
            runs=[records[c,a,i]["row"] for i in (1,2,3)]
            flows[c,a]=dict(case=c,setting=a,**summarize_runs(runs))
            for i,j in itertools.combinations((1,2,3),2):
                left,right=records[c,a,i],records[c,a,j]
                stability.append(dict(case=c,setting=a,repeat_1=i,repeat_2=j,plan_1=left["row"]["plan"],
                                 plan_2=right["row"]["plan"],mapping_1=left["row"]["mapping"],mapping_2=right["row"]["mapping"],
                                 **distance(left["config"],right["config"])))
        for new,old in PAIRS:
            x,y=flows[c,new],flows[c,old]
            result=compare(x,y) if x["reliable"] and y["reliable"] else dict(delta_J=None,delta_pct=None,strict="unpaired")
            individual=[]
            for i in (1,2,3):
                left,right=records[c,new,i],records[c,old,i]
                pair=pair_cells(c,i,new,old,left,right)
                pairs.append(pair)
                individual.append(pair["strict"])
                if left["config"] is None or right["config"] is None:
                    continue
                for idx,((u,k),(v,h)) in enumerate(zip(left["config"],right["config"])):
                    if u!=v or k!=h:
                        assignments.append(dict(case=c,repeat=i,pair=pair["pair"],request_index=idx,new_device=u,new_opp=k,
                                            old_device=v,old_opp=h,changed_device=u!=v))
            medians.append(dict(case=c,pair=f"{new}-{old}",new=new,old=old,new_SAFE=x["safe"],old_SAFE=y["safe"],
                      new_J=x["final_J"],old_J=y["final_J"],new_low_J=x["low_J"],new_high_J=x["high_J"],
                      old_low_J=y["low_J"],old_high_J=y["high_J"],**result,
                      repeat_win=individual.count("win"),repeat_overlap=individual.count("overlap"),
                      repeat_loss=individual.count("loss"),repeat_unpaired=individual.count("unpaired")))
    write("flows.csv",list(flows.values()))
    write("median_pairs.csv",medians)
    write("repeat_pairs.csv",pairs)
    write("repeat_identities.csv",stability)
    write("mapping_changes.csv",assignments,["case","repeat","pair","request_index","new_device","new_opp","old_device","old_opp","changed_device"])
    costs=[]
    for a in "ABCD":
        rr=[r for r in cells if r["setting"]==a]
        costs.append(dict(setting=a,cells=len(rr),mean_charged_s=st.mean(r["charged_s"] for r in rr),
                          **{k:st.mean(r[k] for r in rr) for k in COSTS}))
    write("overheads.csv",costs)
    plot(records)
    from decision_final import report
    report(cells,flows,medians,costs)


if __name__=="__main__":
    main(Path(sys.argv[1]))
