"""Generate manuscript-sized, editable charts from the verified summary tables."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
TABLES=ROOT/"tables"
OUT=ROOT/"figures"
METHODS=["Kim-Adapt+SAFE","Thermal-GA","full","no_heat","energy_only","directed"]
NAMES=["Kim-Adapt+SAFE","Thermal-GA","Previous full","Previous no_heat","Undirected repair","Directed repair"]
COLORS=["#333333","#95854b","#849db1","#4d8590","#c7693d","#254c91"]
MARKS=["o","s","D","^","v","P"]
TEMPS=[25,27.5,30]


def read(name):
    with (TABLES/(name+".csv")).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig,name):
    for suffix in ("pdf","svg"):
        path=OUT/(name+"."+suffix)
        fig.savefig(path,bbox_inches="tight",pad_inches=.08,metadata={"Date":None} if suffix=="svg" else None)
        if suffix=="svg":
            lines=path.read_text(encoding="utf8").splitlines()
            path.write_text("\n".join(line.rstrip() for line in lines)+"\n",encoding="utf8",newline="\n")
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":8,"axes.spines.top":False,
                         "axes.spines.right":False,"svg.fonttype":"none","svg.hashsalt":"ch3-energy-repair","pdf.fonttype":42})
    vals=[r for r in read("anytime") if r["level"]=="temperature"]
    fig,axes=plt.subplots(2,3,figsize=(7.3,4.0),sharex=True,sharey="row")
    for j,temp in enumerate(TEMPS):
        axes[0,j].set_title(f"{temp:g} °C")
        for m,label,color,marker in zip(METHODS,NAMES,COLORS,MARKS):
            rs=[r for r in vals if r["method"]==m and float(r["ambient_c"])==temp]
            x=[int(r["t_s"]) for r in rs]
            for i,y in enumerate(([float(r["mean_safe_j"]) if r["mean_safe_j"] else np.nan for r in rs],
                                  [int(r["safe"]) for r in rs])):
                axes[i,j].plot(x,y,color=color,marker=marker,markerfacecolor="none",markersize=3,
                               linewidth=1.1,label=label,zorder=4 if m=="Kim-Adapt+SAFE" else 2)
                axes[i,j].grid(axis="y",alpha=.18)
        axes[1,j].set_xlabel("Wall time (s)")
        axes[1,j].set_xticks([0,30,60,90,120])
    axes[0,0].set_ylabel("Mean best SAFE (J)")
    axes[1,0].set_ylabel("SAFE runs (of 20)")
    axes[1,0].set_yticks([0,5,10,15,20])
    fig.legend(*axes[1,0].get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False)
    fig.subplots_adjust(bottom=.25,hspace=.18,wspace=.17)
    save(fig,"anytime")
    rs=[r for r in read("summary") if r["level"]=="temperature"]
    fig,ax=plt.subplots(1,2,figsize=(6.4,2.8))
    for m,label,color,marker in zip(METHODS,NAMES,COLORS,MARKS):
        group=sorted([r for r in rs if r["method"]==m],key=lambda r:float(r["ambient_c"]))
        ax[0].plot(TEMPS,[float(r["mean_j"]) if r["mean_j"] else np.nan for r in group],
                   color=color,marker=marker,markerfacecolor="none",label=label)
    width=.34
    for idx,m in enumerate(METHODS[-2:]):
        group=sorted([r for r in rs if r["method"]==m],key=lambda r:float(r["ambient_c"]))
        ax[1].bar(np.arange(3)+(idx-.5)*width,[float(r["repair_pct"]) if r["repair_pct"] else np.nan for r in group],
                  width,color=COLORS[idx+4],hatch=("//" if idx==0 else ""))
    ax[0].set_xticks(TEMPS,["25","27.5","30"]); ax[1].set_xticks(range(3),["25","27.5","30"])
    ax[0].set_ylabel("Final SAFE energy (J)"); ax[1].set_ylabel("Hot-parent repair rate (%)")
    for a in ax: a.set_xlabel("Ambient temperature (°C)"); a.grid(axis="y",alpha=.18)
    fig.legend(*ax[0].get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False)
    fig.subplots_adjust(bottom=.38,wspace=.42)
    save(fig,"energy_and_repair")
    runs={(r["case"],r["method"],r["seed"]):r for r in read("runs")}
    fig,panels=plt.subplots(1,2,figsize=(6.5,2.65))
    for axis,other,title in zip(panels,["Kim-Adapt+SAFE","energy_only"],["Kim-Adapt+SAFE","undirected repair"]):
        axis.axhline(0,color="#555555",lw=.8)
        for i,temp in enumerate(TEMPS):
            delta=[]
            for (case,m,seed),r in runs.items():
                if m!="directed" or float(r["ambient_c"])!=temp:
                    continue
                b=runs[case,other,seed]
                if b["safe"]=="1" and r["safe"]=="1":
                    delta.append(float(b["energy_j"])-float(r["energy_j"]))
            if delta:
                axis.scatter(i+np.linspace(-.17,.17,len(delta)),delta,s=15,alpha=.85,
                             facecolors="none",edgecolors=COLORS[-1],linewidths=.85)
                axis.hlines(np.median(delta),i-.22,i+.22,color="#151515",lw=1.8)
        axis.set_title("Compared with "+title)
        axis.set_xticks(range(3),["25","27.5","30"])
        axis.set_xlabel("Ambient temperature (°C)")
        axis.grid(axis="y",alpha=.18)
    panels[0].set_ylabel("Paired energy saving (J)")
    fig.tight_layout()
    save(fig,"paired_energy")


if __name__=="__main__":
    main()
