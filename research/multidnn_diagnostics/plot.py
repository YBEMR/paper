"""Scientific figures from summary CSV only; SVG remains editable."""
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
plt.rcParams.update({"svg.fonttype":"none","svg.hashsalt":"multidnn-diagnostics","font.size":10,"axes.spines.top":False,
                     "axes.spines.right":False,"savefig.bbox":"tight"})


def rows(name):
    with (HERE/name).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))


def value(row,key):
    return float(row[key]) if row.get(key) else np.nan


def save(fig,path):
    fig.savefig(path,dpi=220,metadata={"Date":"2026-11-23"} if path.suffix==".svg" else None)
    if path.suffix==".svg":
        path.write_bytes(("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines())+"\n").encode())


def main():
    data=rows("summary.csv")
    out=HERE/"figures"
    out.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(13.0,4.1))
    names={"balanced":"Balanced (500 requests)","concurrent":"Concurrent (750 requests)",
           "asymmetric":"Asymmetric periods (376 requests)"}
    for ax,load in zip(axes,names):
        block=[r for r in data if r["load"]==load]
        x=np.arange(4)
        e0=[value(r,"e0_j") for r in block]
        es=[value(r,"best_safe_j") for r in block]
        ax.bar(x-.18,e0,width=.36,color="#b9b9b9",label="Unconstrained energy minimum")
        ax.bar(x+.18,es,width=.36,color="#197b8d",label="Best certified SAFE")
        for i,r in enumerate(block):
            if r["e0_thermal_status"]=="VIOLATION":
                ax.text(i-.18,e0[i]+.2,"HOT",ha="center",fontsize=8,color="#b33d2f")
            if r["safe_optimum_proven"]!="True" and np.isfinite(es[i]):
                ax.text(i+.18,es[i]+.2,"*",ha="center",color="#b33d2f")
            if not np.isfinite(es[i]):
                ax.text(i+.18,0,"No SAFE\ncertificate",rotation=90,va="bottom",ha="center",fontsize=8)
            if r["e0_proven"]!="True" and np.isfinite(e0[i]):
                ax.text(i-.18,e0[i]+.2,"*",ha="center",color="#b33d2f")
        ax.set_xticks(x,["F / cold","F / warm","R / cold","R / warm"],rotation=20)
        ax.set_title(names[load])
        ax.set_ylabel("System energy per 10.04 s (J)")
        ax.set_ylim(0,max([v for v in e0+es if np.isfinite(v)]+[1])*1.17)
        ax.grid(axis="y",alpha=.2)
        ax.set_axisbelow(True)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",ncol=2,bbox_to_anchor=(.5,-.03))
    fig.suptitle("Frozen 81-binding diagnostic domain | ambient 25°C")
    fig.tight_layout(rect=(0,.08,1,.94))
    for ext in ("svg","png"):
        save(fig,out/f"energy_diagnosis.{ext}")
    plt.close(fig)

    costs=rows("costs.csv")
    groups=[
        ("Initialization",["initialization_s"],"#b8b8b8"),
        ("Scheduling + deadline audit",["event_schedule_s","deadline_audit_s"],"#4c78a8"),
        ("Thermal kernel construction",["kernel_thermal_s","kernel_other_s"],"#72b7b2"),
        ("Energy enumeration",["affine_search_s"],"#f2cf5b"),
        ("Peak screening + fallback",["peak_screen_s","fallback_thermal_s"],"#f58518"),
        ("Full-certificate heat integration",["certificate_thermal_s"],"#b279a2"),
        ("Other / interrupted work",["array_io_s","lower_bound_s","other_and_pending_s"],"#e0e0e0")]
    fig,ax=plt.subplots(figsize=(12,5))
    x=np.arange(len(costs))
    bottom=np.zeros(len(costs))
    for label,keys,color in groups:
        y=np.array([sum(value(r,k) for k in keys) for r in costs])
        ax.bar(x,y,bottom=bottom,label=label,color=color,width=.75)
        bottom+=y
    ax.axhline(120,color="#b33d2f",linestyle="--",linewidth=1,label="120 s wall cap")
    ax.set_xticks(x,[r["case_id"].replace("balanced","B").replace("concurrent","C").replace("asymmetric","A")
                    .replace("_forward","/F").replace("_reverse","/R").replace("_reference_start","/cold")
                    .replace("_preheated","/warm") for r in costs],rotation=40,ha="right")
    ax.set_ylabel("Actual wall time (s)")
    ax.set_title("Diagnostic cost decomposition (nested timings are not double-counted)")
    ax.legend(loc="upper left",bbox_to_anchor=(1,1),frameon=False)
    fig.tight_layout()
    for ext in ("svg","png"):
        save(fig,out/f"wall_cost.{ext}")
    plt.close(fig)


if __name__=="__main__":
    main()
