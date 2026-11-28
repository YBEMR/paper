"""Cross-arm comparisons use the contemporary reference, including every failed target."""
import csv,json,statistics as s
from collections import Counter
from pathlib import Path
OUT=Path(__file__).resolve().parent/"results"
def read(name):
    with (OUT/(name+".csv")).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def write(name,rows):
    with (OUT/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def median(values):
    seq=[float(x) for x in values if x is not None and x!=""]
    return s.median(seq) if seq else None
def difference(a,b):return float(a)-float(b) if a not in (None,"") and b not in (None,"") else None
def main():
    cells=read("cells");steps=read("steps");certs=read("certificates")
    pairs=[];hits=[];flows=[]
    cases=sorted({r["case"] for r in cells})
    for case in cases:
        group=[r for r in cells if r["case"]==case]
        by={(r["arm"],r["rep"]):r for r in group}
        ref=median(r["hi"] for r in group if r["arm"]=="R")
        assert ref is not None
        def seq(row,table):
            return [r for r in table if (r["case"],r["arm"],r["rep"])==(case,row["arm"],row["rep"])]
        times={}
        for r in group:
            for tag,mult in (("strict",1),("tolerance",1.01)):
                threshold=ref*mult
                # A target is delivered by any complete SAFE receipt within bound.
                hit=next((p for p in seq(r,certs) if p["status"]=="SAFE" and float(p["hi"])<=threshold),None)
                times[r["arm"],r["rep"],tag]=float(hit["t"]) if hit else None
                hits.append(dict(case=case,arm=r["arm"],rep=r["rep"],target=tag,target_upper_J=threshold,hit=int(bool(hit)),first_hit_s=hit["t"] if hit else None,stage=hit["stage"] if hit else None,plan=hit["plan"] if hit else None))
        for rep in ("1","2","3"):
            a,b=by["A",rep],by["B",rep]
            outcome="unpaired" if "0" in (a["safe"],b["safe"]) else "B" if float(b["hi"])<float(a["lo"]) else "A" if float(a["hi"])<float(b["lo"]) else "tie"
            row=dict(case=case,rep=rep,A_first_s=a["first"],B_first_s=b["first"],B_minus_A_first_s=difference(b["first"],a["first"]),A_J=a["J"],B_J=b["J"],interval_winner=outcome,
                     B_minus_A_percent=100*(float(b["J"])/float(a["J"])-1) if outcome!="unpaired" else None,B_early_gain_J=b["early_improvement_J"],
                     A_search_certs=a["search_certs"],B_search_certs=b["search_certs"],B_post_resume_certs=b["search_after_resume"],A_finished_tail=a["tail_finished"],B_finished_tail=b["tail_finished"])
            for tag in ("strict","tolerance"):
                ta,tb=[times[arm,rep,tag] for arm in ("A","B")]
                row.update({tag+"_A_s":ta,tag+"_B_s":tb,tag+"_B_minus_A_s":difference(tb,ta),tag+"_which":"both" if ta is not None and tb is not None else "A" if ta is not None else "B" if tb is not None else "neither"})
            pairs.append(row)
        for arm in ("A","B","R"):
            part=[r for r in group if r["arm"]==arm]
            j=median(r["J"] for r in part);safe=sum(int(r["safe"]) for r in part)
            flows.append(dict(case=case,arm=arm,units=len(part),safe=safe,reliable=int(safe>=2),first_s=median(r["first"] for r in part),median_J=j,
                              ref_median_J=median(r["J"] for r in group if r["arm"]=="R"),ref_upper_J=ref,
                              gap_percent=100*(j/median(r["J"] for r in group if r["arm"]=="R")-1) if j else None,
                              strict=sum(times[arm,rep,"strict"] is not None for rep in ("1","2","3")),
                              tolerance=sum(times[arm,rep,"tolerance"] is not None for rep in ("1","2","3"))))
    write("paired",pairs);write("targets",hits);write("flow_summary",flows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(cases),2,figsize=(11,10),layout="constrained")
    colors={"A":"#5c636e","B":"#007c76","R":"#954405"}
    for i,case in enumerate(cases):
        for j,arms in enumerate((("A","B"),("R",))):
            ax=axes[i,j]
            for arm in arms:
                for rep in ("1","2","3"):
                    curve=[p for p in steps if (p["case"],p["arm"],p["rep"])==(case,arm,rep)]
                    if not curve:continue
                    t=[float(p["t"]) for p in curve];v=[float(p["J"]) for p in curve]
                    ax.step(t+[60 if arm=="R" else 20],v+[v[-1]],where="post",color=colors[arm],lw=1.25,linestyle=("-", "--", ":")[int(rep)-1],label=f"{arm}, run {rep}")
            target=next(r["ref_upper_J"] for r in flows if r["case"]==case)
            for mult in (1,1.01):ax.axhline(target*mult,color="#607bad",ls=":" if mult==1.01 else "--",alpha=.7,lw=.85)
            ax.set(xlim=(0,60 if j else 20),title=case+(" | contemporary reference" if j else " | fixed vs early"),ylabel="System energy (J)")
            ax.grid(alpha=.17)
            if i==0:ax.legend(fontsize=7,ncol=3)
            if i==len(cases)-1:ax.set_xlabel("Seconds from independent empty start")
    fig.savefig(OUT/"energy_steps.png",dpi=165);plt.close(fig)
if __name__=="__main__":main()
