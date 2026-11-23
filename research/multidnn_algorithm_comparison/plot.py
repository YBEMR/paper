"""Editable scientific figures from archived tables only."""
import csv
import json
from pathlib import Path
from statistics import median
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
CFG=json.loads((HERE/"protocol.json").read_bytes())
DATA=json.loads((HERE/"summary.json").read_bytes())
METHODS=CFG["methods"]
NAMES={"kim_anytime_safe":"Kim-Anytime+SAFE","energy_only":"Energy-Only"}
COLORS={"kim_anytime_safe":"#bc5a2b","energy_only":"#24749b"}
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
                     "axes.spines.right":False,"svg.fonttype":"none","pdf.fonttype":42})
OUT=HERE/"figures";OUT.mkdir(exist_ok=True)
def save(fig,name):
    fig.savefig(OUT/(name+".svg"),bbox_inches="tight")
    svg=OUT/(name+".svg")
    svg.write_bytes(b"\n".join(line.rstrip() for line in svg.read_bytes().splitlines())+b"\n")
    fig.savefig(OUT/(name+".pdf"),bbox_inches="tight")
    fig.savefig(OUT/(name+".png"),dpi=220,bbox_inches="tight")
    plt.close(fig)

def energy():
    fig,axes=plt.subplots(1,3,figsize=(11.8,3.5))
    for ax,load,title in zip(axes,("balanced","concurrent","asymmetric"),("Balanced (500 requests)","Concurrent (750 requests)","Asymmetric (376 requests)")):
        cases=[c for c in CFG["cases"] if c.startswith(load+"_")]
        for j,c in enumerate(cases):
            rows=[r for r in DATA["runs"] if r["case_id"]==c]
            ax.scatter(j,rows[0]["optimum_j"],marker="_",s=400,c="black",linewidths=2,label="M2 exact" if j==0 else None,zorder=3)
            for method,offset,marker in zip(METHODS,(-.14,.14),("o","s")):
                values=[r["safe_energy_j"] for r in rows if r["method"]==method and r["safe"]]
                for k,value in enumerate(values):
                    ax.scatter(j+offset+(k-1)*.024,value,marker=marker,s=25,
                         edgecolors=COLORS[method],facecolors="none",linewidths=1.2,
                         label=NAMES[method] if j==0 and k==0 else None,zorder=4)
        ax.set_title(title);ax.set_xticks(range(4),["F / ref","F / warm","R / ref","R / warm"])
        ax.set_ylabel("Full-window SAFE energy (J)")
        ax.grid(axis="y",alpha=.18)
    axes[1].legend(fontsize=8,loc="best")
    fig.tight_layout()
    save(fig,"safe_energy")

def attainment():
    fig,axes=plt.subplots(1,2,figsize=(10.5,3.7),sharey=True)
    for ax,load,title in zip(axes,(None,"concurrent"),("All 12 cases (36 runs / method)","High concurrency (12 runs / method)")):
        times_all=[]
        for method in METHODS:
            group=[r for r in DATA["runs"] if r["method"]==method and (load is None or r["load"]==load)]
            for metric,style,description in [
                ("time_to_01pct_s","-","within 0.1%"),
                ("time_to_optimum_s","--","exact value (1e-7 J)")]:
                times=sorted(r[metric] for r in group if r[metric] is not None)
                times_all.extend(times)
                x=[0]+times+[120]
                y=[0]+[100*(i+1)/len(group) for i in range(len(times))]+[100*len(times)/len(group)]
                ax.step(x,y,where="post",color=COLORS[method],linestyle=style,
                        label=NAMES[method]+": "+description)
        # Display actual attainment range; the declared budget remains 120s.
        ax.set_xlim(0,min(120,max(times_all,default=120)*1.13+1))
        ax.set_ylim(-2,104);ax.set_title(title);ax.grid(alpha=.18)
        ax.set_xlabel("Time to certified quality (s); 120 s budget")
    axes[0].set_ylabel("Runs reaching same-case M2 reference (%)")
    axes[0].legend(fontsize=7.4,loc="lower right")
    fig.tight_layout()
    save(fig,"time_to_quality")

def paired():
    fig,axes=plt.subplots(1,2,figsize=(10.3,4.0))
    for ax,metric,title in zip(axes,("time_to_01pct_s","total_wall_s"),
                              ("Time to within 0.1% of optimum","Actual process end time")):
        maximum=1
        for load,color,marker in [("balanced","#4c78a8","o"),("concurrent","#d55e00","^"),("asymmetric","#009e73","s")]:
            x,y=[],[]
            for row in DATA["pairs"]:
                if row["load"]!=load:continue
                k=next(r for r in DATA["runs"] if r["case_id"]==row["case_id"] and r["seed"]==row["seed"] and r["method"]=="kim_anytime_safe")
                e=next(r for r in DATA["runs"] if r["case_id"]==row["case_id"] and r["seed"]==row["seed"] and r["method"]=="energy_only")
                if k[metric] is not None and e[metric] is not None:
                    x.append(k[metric]);y.append(e[metric])
            ax.scatter(x,y,color=color,marker=marker,s=30,label=load,alpha=.8)
            maximum=max([maximum,*x,*y])
        lim=maximum*1.08
        ax.plot([0,lim],[0,lim],color=".5",linewidth=1,linestyle="--")
        ax.set_xlim(0,lim);ax.set_ylim(0,lim);ax.set_aspect("equal")
        ax.set_title(title);ax.set_xlabel("Kim-Anytime+SAFE (s)");ax.set_ylabel("Energy-Only (s)")
        ax.grid(alpha=.18)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig,"paired_time")

def cost():
    rows=list(csv.DictReader((HERE/"tables/costs.csv").open()))
    fields=["initialization_s","event_schedule_s","thermal_evaluate_s","setfreq_mapping_inclusive_s","continuous_replay_inclusive_s"]
    labels=["Initialization","Event schedules","Thermal integrator","SetFreq (inclusive)","Certification (inclusive)"]
    fig,ax=plt.subplots(figsize=(8.8,3.5))
    x=np.arange(len(fields))
    for method,offset in zip(METHODS,(-.18,.18)):
        vals=[median(float(r[f]) for r in rows if r["method"]==method) for f in fields]
        ax.bar(x+offset,vals,width=.34,color=COLORS[method],label=NAMES[method])
    ax.set_xticks(x,labels,rotation=12,ha="right");ax.set_ylabel("Median time per run (s)")
    ax.set_title("Measured calls; inclusive categories overlap and must not be summed")
    ax.legend();ax.grid(axis="y",alpha=.18);fig.tight_layout()
    save(fig,"measured_costs")

if __name__=="__main__":
    energy();attainment();paired();cost()
