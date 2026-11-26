"""All certified incumbents, and a selected physical cross-window trajectory."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent
FIG=ROOT/"figures"
FIG.mkdir(exist_ok=True)
fonts={x.name for x in font_manager.fontManager.ttflist}
font=next((f for f in ("Noto Sans CJK SC","Noto Sans CJK JP","DejaVu Sans") if f in fonts),"DejaVu Sans")
plt.rcParams.update({"font.family":font,"axes.unicode_minus":False,"axes.spines.right":False,"axes.spines.top":False,"font.size":10})
color=dict(NT="#00745b",C2="#365aa6",Zhou="#9b4434",Li="#774c91",ZQ="#cd7a12",LQ="#a7396b")
style=dict(NT="-",C2="--",Zhou="-.",Li=":",ZQ="-.",LQ=":")
def read(name):
    with (ROOT/"data"/name).open() as f:
        return list(csv.DictReader(f))


def quality():
    s=read("improvements.csv")
    points=read("checkpoints.csv")
    for phase,title in (("development8","八条开发次序"),("former_holdout6","六条原留出次序")):
        names=list(dict.fromkeys(r["case"] for r in points if r["phase"]==phase))
        fig,axes=plt.subplots(len(names)//2,2,figsize=(12,len(names)*1.23+1.0),layout="constrained")
        for ax,case in zip(axes.flat,names):
            missing=[]
            for m in color:
                x=[float(r["t_s"]) for r in s if r["method"]==m and r["case"]==case]
                y=[float(r["E_J"]) for r in s if r["method"]==m and r["case"]==case]
                if not x:
                    missing.append(m)
                    continue
                ax.step(x+[60],y+y[-1:],where="post",color=color[m],ls=style[m],lw=2)
                ax.scatter(x,y,color=color[m],s=11)
            ax.set_title(case[1:].replace("_"," · "),loc="left")
            if missing:
                ax.text(.99,.97,"未获 SAFE  "+", ".join(missing),transform=ax.transAxes,va="top",ha="right",fontsize=8)
            for v in (10,30):
                ax.axvline(v,color="0.8",lw=.7)
            ax.set_xlim(0,60);ax.set_xticks([0,10,30,60]);ax.set_ylabel("最低 SAFE 能耗（J）");ax.grid(axis="y",alpha=.18)
        for ax in axes[-1]:
            ax.set_xlabel("从空累计墙钟（s）")
        handles=[Line2D([0],[0],color=color[m],ls=style[m],lw=2,label=m) for m in color]
        fig.legend(handles=handles,loc="outside upper right",ncol=6,frameon=False)
        fig.suptitle(title,x=.07,ha="left",size=17)
        fig.savefig(FIG/(phase+".png"),dpi=150);plt.close(fig)


def trace():
    case="V640_HLHLHHLL"
    data=[r for r in read("thermal_windows.csv") if r["case"]==case]
    word=case.split("_")[1]
    fig,axes=plt.subplots(3,1,figsize=(10,7.3),layout="constrained",sharex=True)
    for ax in axes:
        for j,v in enumerate(word,1):
            if v=="H":
                ax.axvspan(j-.5,j+.5,color="#edc5a3",alpha=.26)
        ax.grid(axis="y",alpha=.15)
    for m in color:
        rows=[r for r in data if r["method"]==m]
        if not rows:
            continue
        for ax,key in zip(axes,("gpu_out_C","E_J","min_slack_ms")):
            ax.plot([int(r["window"]) for r in rows],[float(r[key]) for r in rows],style[m],color=color[m],marker="o",label=m)
    axes[0].legend(frameon=False,ncol=6)
    for ax,label in zip(axes,("出窗 GPU 温度（°C）","物理窗能耗（J）","到达请求最小余量（ms）")):
        ax.set_ylabel(label)
    axes[-1].set_xticks(list(range(1,9)),[str(i+1)+" "+v for i,v in enumerate(word)])
    axes[-1].set_xlabel("窗口及轻重负载类型")
    fig.suptitle("L640 · HLHLHHLL    60 秒最佳 SAFE 排程",x=.08,ha="left")
    fig.savefig(FIG/"cross_scene.png",dpi=150);plt.close(fig)


def release_curve():
    case="V320_HLLH"
    base=read("release_calls.csv")
    main=read("improvements.csv")
    p=sorted((float(r["t_s"]),float(r["E_J"])) for r in base if r["case"]==case and r["method"]=="Li-release" and r["status"]=="SAFE")
    if not p:
        return
    fig,ax=plt.subplots(figsize=(8.5,3.6),layout="constrained")
    for label,data,col,ls in (("Li-release",p,"#774c91","-."),("NT",[(float(r["t_s"]),float(r["E_J"])) for r in main if r["case"]==case and r["method"]=="NT"],color["NT"],"-"),
                              ("C2",[(float(r["t_s"]),float(r["E_J"])) for r in main if r["case"]==case and r["method"]=="C2"],color["C2"],"--")):
        times,energies=zip(*data)
        ax.step([*times,60],[*energies,energies[-1]],where="post",label=label,color=col,linestyle=ls,lw=2)
        ax.scatter(times,energies,s=22,color=col)
    ax.set_xscale("log");ax.set_xlim(.09,60)
    ax.set_xticks([.1,.3,1,3,10,30,60],["0.1","0.3","1","3","10","30","60"])
    ax.set_xlabel("从空累计墙钟（s，对数刻度）");ax.set_ylabel("已认证最低 SAFE 能耗（J）")
    ax.legend(frameon=False,ncol=3);ax.grid(axis="y",alpha=.2);ax.set_title("L320 · HLLH  释放准入诊断中唯一共同 SAFE 的次序",loc="left")
    fig.savefig(FIG/"release_quality.png",dpi=150);plt.close(fig)


if __name__=="__main__":
    quality()
    trace()
    release_curve()
