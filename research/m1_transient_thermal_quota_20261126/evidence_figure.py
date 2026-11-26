"""Draw certified traces and export the common-pool L480 witness."""
import csv
import gzip
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"


def get(case,arm,rank):
    folder=DATA/("e1b" if arm in ("C2","D2") else "e1")/case/arm
    row=json.loads((folder/"result.json").read_text())["certificates"][rank-1]
    with np.load(folder/"evidence"/case/row["plan"]/"trace.npz",allow_pickle=False) as f:
        curve=f["events"]
    t=np.r_[curve[0,0],curve[:,1]]/10000
    temp=np.maximum.reduce(np.vstack([curve[0,14:18],curve[:,18:22]]),axis=1)
    return row,t,temp


def main():
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=font).get_name()
    plt.rcParams.update({"axes.spines.right":False,"axes.spines.top":False,"axes.unicode_minus":False,
                         "font.size":10,"savefig.facecolor":"white"})
    fig,axes=plt.subplots(1,2,figsize=(10.6,3.75))
    for ax,(case,title,left,right,series) in zip(axes,[
        ("L480","L480  ·  相同末窗候选池",5.5,6.301,[("C",1,"C"),("D-quarter",2,"D（0.25 秒热积分）")]),
        ("L640","L640  ·  两份安全排程",7.4,8.301,[("C2",1,"C2 普通多样化"),("D2",2,"D2 热感知多样化")])]):
        for (arm,rank,name),color in zip(series,["#53426E","#117A70"]):
            row,t,temp=get(case,arm,rank)
            keep=(t>=left-.02)&(t<=right+.02)
            ax.plot(t[keep],temp[keep],label=f"{name}  {row['peak']:.3f}°C",lw=1.45,color=color)
        end=right-.301
        ax.axvspan(end,right,color="#ECEFF2",zorder=-2)
        ax.axhline(80,color="#B24933",ls="--",lw=1)
        ax.set_xlim(left,right)
        ax.set_title(title,loc="left",fontsize=12)
        ax.set_xlabel("时间（s）")
        ax.grid(axis="y",alpha=.20)
        ax.legend(fontsize=8,loc="lower left",frameon=True)
    axes[0].set_ylabel("四节点中的最高温度（°C）")
    fig.tight_layout()
    fig.savefig(ROOT/"证书温度轨迹.png",dpi=180,bbox_inches="tight")
    plt.close(fig)

    pools={}
    for arm in ("C","D","D-quarter"):
        with gzip.open(DATA/"e1/L480"/arm/"trials.csv.gz","rt") as f:
            pools[arm]={v["config"]:v for v in csv.DictReader(f) if v["window"]=="5" and v["result"]=="valid"}
    assert len(pools["C"])==79 and pools["C"].keys()==pools["D"].keys()==pools["D-quarter"].keys()
    rows=[]
    for arm,rank in (("C",1),("D-quarter",2)):
        row,_,_=get("L480",arm,rank)
        key=row["id"]
        a=pools["C"][key]
        energy=round(float(a["reference_score"]),11)
        before=sum(round(float(v["reference_score"]),11)<energy for v in pools["C"].values())
        after=sum(round(float(v["reference_score"]),11)<=energy for v in pools["C"].values())
        rows.append(dict(pool_size=79,selected_by=arm,certificate_order=rank,reference_rank_low=1+before,
                         reference_rank_high=after,parent=a["parent"],gpu=a["gpu"],npu=a["npu"],x=a["x"],y=a["y"],
                         D_peak=pools["D"][key]["pred_peak"],quarter_peak=pools["D-quarter"][key]["pred_peak"],
                         certified_peak=row["peak"],hotspot=("CPU1","CPU2","GPU","NPU")[row["hotspot"]],
                         energy_J=row["E"],status=row["status"],plan=row["plan"]))
    with (DATA/"audit/L480_common_pool.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)


if __name__=="__main__":
    main()
