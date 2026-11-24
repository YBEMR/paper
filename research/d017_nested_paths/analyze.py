"""Offline tables/figures only; no scheduling or thermal evaluator imports."""
import json,gzip
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
CFG=json.loads((HERE/"config.json").read_bytes());INPUT=json.loads((HERE/"inputs.json").read_bytes())
NODES=("cpu","gpu","dla0","dla1")
PATHS=list(INPUT["frozen"]["deployments"])
def read(name):
    with gzip.open(HERE/"raw"/name,"rt",encoding="utf-8") as f:return [json.loads(x) for x in f]
def write(name,df):df.to_csv(HERE/name,index=False,float_format="%.12g")

rows=[]
for r in read("certificates.jsonl.gz"):
    d={k:v for k,v in r.items() if not isinstance(v,(dict,list))}
    p=INPUT["frozen"]["deployments"][r["path"]]["paths"]
    d["effective_path"]="/".join(str(p[i]) if a in r["active_apps"] else "-" for i,a in enumerate([0,3]))
    for fld in ("final_C","peak_lower_C","peak_upper_C","leakage_J","idle_J","activity_J"):
        for i,n in enumerate(NODES):d[fld+"_"+n]=r.get(fld,[np.nan]*4)[i]
    for res,t in r["busy_ns"].items():d["busy_ms_"+res]=t/1e6;d["idle_ms_"+res]=r["duration_s"]*1000-t/1e6
    d["base_J"]=sum(r.get("idle_J",[])) if r["energy_J"] is not None else np.nan
    d["temperature_leakage_J"]=sum(r.get("leakage_J",[])) if r["energy_J"] is not None else np.nan
    d["total_activity_J"]=sum(r.get("activity_J",[])) if r["energy_J"] is not None else np.nan
    d["peak_C"]=max(r.get("peak_upper_C",[np.nan]))
    rows.append(d)
df=pd.DataFrame(rows)
GROUP=["load","frames","scope","ambient_C","inlet","mode"]
df["pareto"]=False
objectives=["energy_J"]+["peak_upper_C_"+n for n in NODES]+["final_C_"+n for n in NODES]+["minus_slack"]
df["minus_slack"]=-df.min_slack_ms
tol=np.array([CFG["tie_energy_J"]]+[CFG["dominance_temperature_C"]]*8+[CFG["dominance_slack_ms"]])
best=[];coverage=[]
for keys,g in df.groupby(GROUP,sort=False):
    feasible=g[g.deadline_ok]
    # Pairwise tolerance dominance: all metrics nonworse, one materially better.
    if len(feasible):
        x=feasible[objectives].to_numpy()
        dom=np.all(x[:,None,:]<=x[None,:,:]+tol,axis=2)&np.any(x[:,None,:]<x[None,:,:]-tol,axis=2)
        df.loc[feasible.index,"pareto"]=~dom.any(axis=0)
    safe=g[g.status=="SAFE"].sort_values(["energy_J","path","opp"])
    c=dict(zip(GROUP,keys));c.update(actions=len(g),safe=len(safe),deadline_failed=int((~g.deadline_ok).sum()),
        thermal_violation=int(((g.thermal_status=="VIOLATION")&g.deadline_ok).sum()),
        unresolved=int((g.status=="UNRESOLVED").sum()))
    coverage.append(c)
    if len(safe):
        b=safe.iloc[0].to_dict()
        tied=safe[safe.energy_J<=b["energy_J"]+CFG["tie_energy_J"]]
        b["cooptimal_effective_paths"]=";".join(sorted(set(tied.effective_path)))
        b["cooptimal_opps"]=";".join(sorted(set(tied.opp)))
        b["cooptimal_actions"]=";".join(tied.path+"/"+tied.opp)
        best.append(b)
best=pd.DataFrame(best);write("action_results.csv",df.drop(columns="minus_slack"))
write("coverage.csv",pd.DataFrame(coverage));write("best_actions.csv",best)
write("pareto_fronts.csv",df[df.pareto].drop(columns="minus_slack"))
schedule_rows=read("schedules.jsonl.gz")
matrix=pd.DataFrame([dict(load=r["load"],path=r["path"],opp=r["opp"],deadline_ok=r["deadline_ok"],
    min_slack_ms=min(q["deadline_ns"]-r["completions_ns"][q["id"]] for q in r["requests"])/1e6) for r in schedule_rows])
write("deadline_actions.csv",matrix)
matrix=matrix.pivot_table(index="load",columns="path",values="deadline_ok",aggfunc="sum").reindex(columns=PATHS)
matrix.to_csv(HERE/"deadline_matrix.csv")
paired=[]
for keys,g in df.groupby(["load","frames","scope","ambient_C","mode"],sort=False):
    row=dict(zip(["load","frames","scope","ambient_C","mode"],keys))
    a=g[(g.inlet=="reference")&(g.status=="SAFE")].sort_values(["energy_J","path","opp"])
    b=g[(g.inlet=="preheated")&(g.status=="SAFE")].sort_values(["energy_J","path","opp"])
    if not len(a) or not len(b):
        row.update(change="no_SAFE_in_at_least_one_state",reference_SAFE=len(a),preheated_SAFE=len(b))
        paired.append(row);continue
    x,y=a.iloc[0],b.iloc[0]
    at=a[a.energy_J<=x.energy_J+CFG["tie_energy_J"]];bt=b[b.energy_J<=y.energy_J+CFG["tie_energy_J"]]
    common=set(at.effective_path)&set(bt.effective_path)
    change="path" if not common else ("frequency_only" if not set(at.opp)&set(bt.opp) else "same")
    row.update(change=change,reference_path=x.path,preheated_path=y.path,reference_effective=x.effective_path,
        preheated_effective=y.effective_path,reference_opp=x.opp,preheated_opp=y.opp,
        reference_energy_J=x.energy_J,preheated_energy_J=y.energy_J,
        reference_peak_C=x.peak_C,preheated_peak_C=y.peak_C,
        reference_slack_ms=x.min_slack_ms,preheated_slack_ms=y.min_slack_ms,
        reference_SAFE=len(a),preheated_SAFE=len(b))
    # Retain the other inlet's optimal path, but reoptimize all its frequencies.
    for label,target,other in [("cold_using_warm_path",a,bt),("warm_using_cold_path",b,at)]:
        alt=target[target.effective_path.isin(set(other.effective_path))]
        row[label+"_status"]="SAFE" if len(alt) else "NO_SAFE"
        row[label+"_penalty_pct"]=100*(alt.energy_J.min()/target.energy_J.min()-1) if len(alt) else np.nan
    row["material_path_change"]=change=="path" and (
        row["cold_using_warm_path_status"]=="NO_SAFE" or row["warm_using_cold_path_status"]=="NO_SAFE" or
        max(row["cold_using_warm_path_penalty_pct"],row["warm_using_cold_path_penalty_pct"])>=CFG["material_energy_percent"])
    paired.append(row)
paired=pd.DataFrame(paired);write("decision_changes.csv",paired)
break_cols=GROUP+["path","effective_path","opp","energy_J","peak_C","min_slack_ms",
    "activity_J_cpu","activity_J_gpu","activity_J_dla0","activity_J_dla1","base_J",
    "temperature_leakage_J","common_J","transfer_J","cooptimal_actions"]
write("energy_breakdown.csv",best[break_cols])
summary=dict(rows=len(df),scheduled=len(schedule_rows),deadline_feasible=int(sum(r["deadline_ok"] for r in schedule_rows)),
    status=df.status.value_counts().to_dict(),paired_changes=paired.change.value_counts().to_dict(),
    material_path_pairs=int(paired.material_path_change.eq(True).sum()),
    material_by_mode=paired.groupby("mode").material_path_change.sum().to_dict(),
    all_groups=len(coverage),pareto_rows=int(df.pareto.sum()))
(HERE/"analysis_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"svg.fonttype":"none","svg.hashsalt":"d017-nested-paths"})
def figure(name,fig):
    fig.savefig(HERE/(name+".png"),dpi=180,bbox_inches="tight")
    svg=HERE/(name+".svg")
    fig.savefig(svg,bbox_inches="tight",metadata={"Date":None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
    plt.close(fig)
fig,ax=plt.subplots(figsize=(10,4))
im=ax.imshow(matrix.values,vmin=0,vmax=27,cmap="Blues")
ax.set(xticks=range(9),xticklabels=PATHS,yticks=range(len(matrix)),yticklabels=matrix.index,
    xlabel="Complete path pair (D076*/D077*: D017 physical bindings)",ylabel="Active networks")
for i in range(len(matrix)):
    for j in range(9):ax.text(j,i,int(matrix.iloc[i,j]),ha="center",va="center",color="white" if matrix.iloc[i,j]>16 else "black")
fig.colorbar(im,ax=ax,label="Deadline-feasible OPPs / 27")
figure("deadline_matrix",fig)
# An illustrative paired-state mechanism from the frozen grid, no new experiment.
PLOT_LOAD="a123";PLOT_FRAMES=62;PLOT_AMB=25
fig,axs=plt.subplots(2,3,figsize=(14,8),sharex=True,sharey=True)
colors={p:plt.get_cmap("tab10")(i) for i,p in enumerate(PATHS)}
for i,inlet in enumerate(["reference","preheated"]):
    for j,mode in enumerate(CFG["modes"]):
        ax=axs[i,j];g=df[(df.load==PLOT_LOAD)&(df.frames==PLOT_FRAMES)&(df.ambient_C==PLOT_AMB)&(df.inlet==inlet)&(df["mode"]==mode)&df.deadline_ok]
        for p in PATHS:
            z=g[g.path==p];ax.scatter(z.energy_J,z.peak_upper_C_gpu,s=18,c=[colors[p]],alpha=.55,label=p)
            z=z[z.pareto];ax.scatter(z.energy_J,z.peak_upper_C_gpu,s=55,facecolors="none",edgecolors=colors[p],linewidths=1.2)
        ax.axhline(80,color="black",ls="--",lw=.8);ax.set_title(mode+" / "+inlet);ax.grid(alpha=.2)
        if i==1:ax.set_xlabel("System energy over 2.48 s (J)")
        if j==0:ax.set_ylabel("Continuous GPU peak upper bound (C)")
handles,labels=axs[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc="lower center",ncol=9,bbox_to_anchor=(.5,-.01))
fig.suptitle("Active 1/2/3, ambient 25C. Rings: full-vector nondominated; projection alone is not dominance")
fig.tight_layout(rect=[0,.04,1,.96]);figure("pareto_projection",fig)
fig,axs=plt.subplots(1,2,figsize=(11,4),sharey=True)
components=["activity_J_cpu","activity_J_gpu","activity_J_dla0","activity_J_dla1","base_J","temperature_leakage_J","common_J","transfer_J"]
for ax,inlet in zip(axs,["reference","preheated"]):
    g=best[(best.load==PLOT_LOAD)&(best.frames==PLOT_FRAMES)&(best.ambient_C==PLOT_AMB)&(best.inlet==inlet)].set_index("mode").reindex(CFG["modes"])
    bottom=np.zeros(3)
    for c in components:
        ax.bar(range(3),g[c],bottom=bottom,label=c);bottom+=g[c].to_numpy()
    ax.set(xticks=range(3),xticklabels=["Constant","GPU idle","GPU+DLA idle"],title=inlet,ylabel="Best SAFE system energy (J)")
    for i,(_,r) in enumerate(g.iterrows()):
        ax.text(i,r.energy_J+.15,r.path+"/"+r.opp,ha="center",fontsize=8) if pd.notna(r.path) else ax.text(i,0,"No SAFE",ha="center")
handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc="lower center",ncol=4,bbox_to_anchor=(.5,-.12),fontsize=8)
fig.tight_layout();figure("energy_breakdown",fig)
print(json.dumps(summary,indent=2))
print(paired[paired.change!="same"].to_string(index=False))
