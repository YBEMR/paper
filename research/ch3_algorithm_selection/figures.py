"""Manuscript plots from verified run-level tables; no absolute joules pooled across workloads."""
from collections import defaultdict
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE=Path(__file__).resolve().parent
DEST=HERE/"figures"
COLORS={"energy_only":"#096558","joint":"#3D61A7","kim_anytime":"#B45B1D","energy_safe_parent":"#823B68"}
NAMES={"energy_only":"Energy-Only","joint":"双网联合修复","kim_anytime":"Kim-Anytime+SAFE",
       "energy_safe_parent":"Energy-Only 仅 SAFE 父状态"}
MARKERS={"energy_only":"o","joint":"s","kim_anytime":"^","energy_safe_parent":"D"}


def output(fig,name):
    for ext in ("svg","pdf"):
        target=DEST/f"{name}.{ext}"
        if ext=="svg":
            fig.savefig(target,bbox_inches="tight",metadata={"Date":None})
            lines=target.read_text(encoding="utf8").splitlines()
            target.write_bytes(("\n".join(line.rstrip() for line in lines)+"\n").encode("utf8"))
        else:
            fig.savefig(target,bbox_inches="tight")
    plt.close(fig)


def main():
    DEST.mkdir(exist_ok=True)
    available={font.name for font in font_manager.fontManager.ttflist}
    candidates=["Microsoft YaHei","Noto Sans CJK SC","SimHei","DengXian","Arial Unicode MS"]
    font=next((name for name in candidates if name in available),None)
    if not font:
        raise RuntimeError("A Chinese font is required to render these figures")
    plt.rcParams.update({"font.family":font,"svg.fonttype":"none","svg.hashsalt":"ch3-selection","pdf.fonttype":42,
                         "font.size":10,"axes.spines.top":False,"axes.spines.right":False,
                         "axes.unicode_minus":False,"axes.axisbelow":True})
    with (HERE/"tables/runs.csv").open(encoding="utf8",newline="") as f:
        rows=list(csv.DictReader(f))
    bymethod=defaultdict(list)
    for r in rows:
        bymethod[r["method"]].append(r)
    primary=["energy_only","joint","kim_anytime"]
    fig,axes=plt.subplots(1,3,figsize=(10.8,3.2),sharey=True)
    for ax,field,title in zip(axes,["first_SAFE_s","near_s","exact_s"],
                              ["首次取得 SAFE","达到共同参考 +0.1%","达到共同参考值"]):
        for method in primary:
            v=bymethod[method]
            times=sorted(float(r[field]) for r in v if r[field])
            ax.step([0,*times,120],[0,*[100*(i+1)/len(v) for i in range(len(times))],100*len(times)/len(v)],
                    where="post",color=COLORS[method],label=NAMES[method],linewidth=1.8,
                    linestyle={"energy_only":"-","joint":"--","kim_anytime":"-."}[method])
        ax.set(xlim=(0,120),ylim=(0,104),xticks=[0,30,60,90,120],title=title,xlabel="实际墙钟时间（s）")
        ax.grid(axis="y",alpha=.22)
    axes[0].set_ylabel("已达到的运行比例（%）")
    fig.legend(*axes[0].get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False)
    fig.tight_layout(rect=(0,.13,1,1))
    output(fig,"time_to_quality")
    methods=primary+(["energy_safe_parent"] if "energy_safe_parent" in bymethod else [])
    fig,axes=plt.subplots(1,len(methods),figsize=(2.85*len(methods),3.1),sharey=True)
    labels=["原始 25°C","原始 30°C","A 25°C","A 30°C","B 25°C","B 30°C"]
    cases=[(l,t) for l in ("original","A","B") for t in ("25","30")]
    for ax,m in zip(axes,methods):
        for i,case in enumerate(cases):
            v=sorted((r for r in bymethod[m] if (r["load"],r["ambient_c"])==case),key=lambda r:r["seed"])
            for j,r in enumerate(v):
                if r["gap_pct"]:
                    ax.scatter(float(r["gap_pct"]),i+(j-1)*.17,marker=MARKERS[m],color=COLORS[m],s=22)
        ax.axvline(0,color="#555555",lw=.7)
        measured_gaps=[float(r["gap_pct"]) for r in rows if r["gap_pct"]]
        ax.set_xlim(-.008,max(.085,max(measured_gaps)*1.08))
        ax.grid(axis="x",alpha=.22)
        ax.set(xlabel="距本工况参考值（%）",title=NAMES[m],yticks=range(6),yticklabels=labels)
    axes[0].invert_yaxis()
    fig.tight_layout()
    output(fig,"final_gap")

    if "energy_safe_parent" in bymethod:
        fig,ax=plt.subplots(figsize=(6.4,3.3))
        for y,case in enumerate(cases):
            for j,seed in enumerate(sorted({r["seed"] for r in rows})):
                pair=[]
                for m in ("energy_only","energy_safe_parent"):
                    row=next(r for r in bymethod[m] if (r["load"],r["ambient_c"],r["seed"])==(*case,seed))
                    x=float(row["exact_s"]) if row["exact_s"] else 120.
                    pair.append(x)
                    ax.scatter(x,y+(j-1)*.20,s=22,marker=MARKERS[m] if row["exact_s"] else "x",
                               color=COLORS[m],label=NAMES[m] if y==0 and j==0 else None,zorder=3)
                ax.plot(pair,[y+(j-1)*.20]*2,lw=.9,color="#9aa2a8",zorder=2)
        ax.set(yticks=range(6),yticklabels=labels,xlabel="首次达到同工况最低已见 SAFE 能耗的时间（s）")
        ax.invert_yaxis()
        ax.grid(axis="x",alpha=.22)
        ax.legend(loc="upper center",bbox_to_anchor=(.50,1.20),ncol=2,frameon=False)
        fig.tight_layout()
        output(fig,"parent_ablation")


if __name__=="__main__":
    main()
