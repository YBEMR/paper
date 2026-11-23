"""Paper-ready static figures from archived summaries; no search calls."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
OUT=HERE/"figures";OUT.mkdir(exist_ok=True)
S=json.loads((HERE/"summary.json").read_bytes())
cases=S["cases"];runs=S["runs"]
labels=["Classifiers F","Classifiers R","Mixed pair F","Mixed pair R","Mixed triple F","Mixed triple R","Mixed quad F","Mixed quad R"]
plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none","pdf.fonttype":42})

def save(fig,name):
    fig.savefig(OUT/(name+".png"),dpi=240,bbox_inches="tight")
    fig.savefig(OUT/(name+".svg"),bbox_inches="tight")
    fig.savefig(OUT/(name+".pdf"),bbox_inches="tight") # PDF is ignored by repository policy; rebuild locally.
    p=OUT/(name+".svg");p.write_bytes(b"\n".join(s.rstrip() for s in p.read_bytes().splitlines())+b"\n")
    plt.close(fig)

fig,ax=plt.subplots(figsize=(8,3.1))
finite=[r["gap_pct"] for r in runs if r.get("gap_pct") is not None and r["method"].startswith("Kim")]
upper=max([0.01,*finite])*1.2
for i,c in enumerate(cases):
    rr=[r for r in runs if r["case_id"]==c["case_id"] and r["method"].startswith("Kim")]
    if c["certificate"]:
        for offset,r in zip([-.15,0,.15],rr):
            if r.get("gap_pct") is not None:ax.scatter(i+offset,max(0,r["gap_pct"]),color="#2467a6",s=28,zorder=3)
    else:
        ax.axvspan(i-.4,i+.4,color="#e7e7e7",zorder=0)
        ax.text(i,upper*.45,"Reference\nunresolved",ha="center",va="center",fontsize=8,color="#555555")
ax.set(xticks=range(8),xticklabels=labels,ylabel="Certified Kim energy gap (%)",ylim=(-upper*.08,upper))
ax.tick_params(axis="x",rotation=25);ax.axhline(0,color="#777777",lw=.6)
ax.set_title("Same-domain gap: (Kim SAFE energy − certified optimum) / Kim energy")
fig.tight_layout();save(fig,"certified_gap")

fig,axes=plt.subplots(2,4,figsize=(12,6))
for i,(ax,c) in enumerate(zip(axes.flat,cases)):
    case=c["case_id"]
    for method,color in [("Kim-Anytime+SAFE","#2467a6"),("M2-reference","#cb682c")]:
        rr=[r for r in runs if r["case_id"]==case and r["method"]==method]
        for j,r in enumerate(rr):
            points=[p for p in S["progress"] if p["case_id"]==case and p["method"]==method and p["seed"]==r["seed"]]
            if not points:continue
            xs=[p["t_s"] for p in points];ys=[p["energy_j"] for p in points]
            ax.step(xs+[120],ys+[ys[-1]],where="post",color=color,alpha=1 if j==0 else .45,lw=1.2,
                    label=method if j==0 else None)
    if c["certified_optimum_j"] is not None:ax.axhline(c["certified_optimum_j"],color="#333333",ls=":",lw=1,label="Certified optimum")
    ax.set_title(labels[i]+(" (certified)" if c["certificate"] else " (unresolved)"))
    ax.set_xlim(0,120);ax.set_xlabel("Elapsed wall time (s)");ax.set_ylabel("Best SAFE energy (J)")
    ax.grid(alpha=.2);ax.ticklabel_format(axis="y",style="plain",useOffset=False)
legend_items={}
for ax in axes.flat:
    hs,ls=ax.get_legend_handles_labels()
    for h,l in zip(hs,ls):legend_items.setdefault(l,h)
fig.legend(list(legend_items.values()),list(legend_items),loc="lower center",ncol=3,bbox_to_anchor=(.5,-.025))
fig.suptitle("First appearance of certified SAFE incumbents; each panel has its own energy scale")
fig.tight_layout();save(fig,"safe_energy_over_time")

fig,ax=plt.subplots(figsize=(10,6.5))
categories=[("Event scheduling","time_schedule_s","#4477aa"),("Affine kernel build","time_kernel_compile_s","#66ccee"),
            ("Affine queries","query","#228833"),("Direct thermal evaluation","time_direct_thermal_s","#ccbb44"),
            ("Other / initialization / logs","other","#bbbbbb")]
for i,c in enumerate(cases):
    for j,method in enumerate(["M2-reference","Kim-Anytime+SAFE"]):
        rr=[r for r in runs if r["case_id"]==c["case_id"] and r["method"]==method]
        wall=np.mean([r["total_wall_s"] for r in rr]);parts=[]
        for _,key,_ in categories[:-1]:
            parts.append(np.mean([r.get("time_query_energy_s",0)+r.get("time_query_thermal_s",0) if key=="query" else r.get(key,0) for r in rr]))
        parts.append(max(0,wall-sum(parts)));left=0
        for (label,_,color),value in zip(categories,parts):
            ax.barh(i*2+j,value,left=left,color=color,height=.78,label=label if i==j==0 else None);left+=value
ax.set_yticks(range(16),[label+" / "+m for label in labels for m in ["M2","Kim mean"]])
ax.invert_yaxis();ax.axvline(120,color="#555555",ls="--",lw=.7);ax.set_xlabel("Actual wall time (s)")
ax.set_title("Non-overlapping cost components; Kim averages three seeds")
ax.legend(loc="lower center",bbox_to_anchor=(.5,-.22),ncol=3,fontsize=8)
fig.tight_layout();save(fig,"cost_components")
print("3 figures: editable SVG, PNG; locally reproducible PDF")
