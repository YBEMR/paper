"""Regenerate the two-panel time/quality figure from audited tables."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE=Path(__file__).resolve().parent
STYLES={
    "Kim-Adapt+SAFE":("Kim-Adapt+SAFE","#181818","--","s"),
    "Thermal-GA":("Thermal-GA","#8a6100",":","D"),
    "full":("Coop (old)","#706a99","-.","v"),
    "no_heat":("Coop (no heat)","#888888","--","p"),
    "safe_parent":("Joint / SAFE parents","#21816b",":","^"),
    "single":("Single-network repair","#bd4c14","-.","x"),
    "joint":("Quota-coupled repair","#0072b2","-","o"),
}


def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def draw(tables,out):
    targets=read(tables/"time_to_target.csv")
    samples=read(tables/"anytime_summary.csv")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"svg.fonttype":"none","svg.hashsalt":"ch3-joint-repair",
                         "axes.spines.top":False,"axes.spines.right":False,"axes.linewidth":0.8})
    fig,axes=plt.subplots(1,2,figsize=(9.5,4.15))
    for m,(label,color,ls,marker) in STYLES.items():
        records=[r for r in targets if r["method"]==m]
        times=sorted(float(r["within_0p1pct_kim_s"]) for r in records if r["within_0p1pct_kim_s"])
        n=len(records)
        axes[0].step([0,*times,120],[0,*[100*j/n for j in range(1,len(times)+1)],100*len(times)/n],
                     where="post",label=label,color=color,ls=ls,lw=1.7)
        data=sorted((r for r in samples if r["method"]==m and r["conditional_median_gap_pct"]),
                    key=lambda r:float(r["budget_s"]))
        axes[1].plot([float(r["budget_s"]) for r in data],[float(r["conditional_median_gap_pct"]) for r in data],
                     ls=ls,color=color,marker=marker,ms=3.5,lw=1.4,markerfacecolor="white")
    axes[0].set(ylabel="Runs reaching target (%)",ylim=(-2,104),title="(a) Certified energy ≤ 1.001 × paired Kim")
    axes[1].set(ylabel="Median energy gap to final Kim (%)",title="(b) Quality among runs with a SAFE policy")
    axes[1].set_yscale("symlog",linthresh=0.10)
    axes[1].axhline(0,color="#555555",lw=0.65)
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{x:g}"))
    for ax in axes:
        ax.set(xlabel="Elapsed wall time (s)",xlim=(0,122),xticks=[0,20,40,60,80,100,120])
        ax.grid(axis="y",color="#ddd",linewidth=0.6)
    fig.legend(*axes[0].get_legend_handles_labels(),loc="lower center",ncol=4,frameon=False,fontsize=8.5)
    fig.subplots_adjust(left=.085,right=.973,top=.91,bottom=.26,wspace=.31)
    out.mkdir(parents=True,exist_ok=True)
    svg=out/"time_quality.svg"
    fig.savefig(svg,metadata={"Date":None})
    svg.write_bytes(b"\n".join(line.rstrip() for line in svg.read_bytes().splitlines())+b"\n")
    fig.savefig(out/"time_quality.png",dpi=190)
    plt.close(fig)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tables",type=Path,default=HERE/"tables")
    p.add_argument("--output",type=Path,default=HERE/"figures")
    args=p.parse_args()
    draw(args.tables,args.output)
