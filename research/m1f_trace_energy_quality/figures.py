"""Export per-order physical trajectories and full incumbent step functions."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from long_run import ROOT,inputs

FIG=ROOT/"figures"
FIG.mkdir(exist_ok=True)
available={f.name for f in font_manager.fontManager.ttflist}
cjk=next((f for f in ("Noto Sans CJK SC","Noto Sans CJK JP","Microsoft YaHei","SimHei") if f in available),"DejaVu Sans")
plt.rcParams.update({"font.family":cjk,"axes.unicode_minus":False,"font.size":10,
                     "axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"white"})
COLORS=dict(NT="#006951",NC="#aa3854",OT="#cc7418",C2="#335cac")
STYLES=dict(NT="-",NC="--",OT="-.",C2=":")
def rows(name):
    with (ROOT/"data"/name).open() as f:return list(csv.DictReader(f))

def quality():
    steps=rows("quality/improvements.csv")
    for phase in ("development8","former_holdout6"):
        names=[p.stem for ph,p in inputs() if ph==phase]
        fig,axes=plt.subplots(len(names)//2,2,figsize=(12,2.6*(len(names)//2)+1.2),layout="constrained")
        for ax,case in zip(axes.flat,names):
            for cut in (10,30):ax.axvline(cut,color="#b5b5b5",lw=.8)
            missing=[]
            for m in ("NT","NC","OT","C2"):
                r=[v for v in steps if v["case"]==case and v["method"]==m]
                if not r:
                    missing.append(m);continue
                x=[float(i["t_s"]) for i in r]; y=[float(i["E_J"]) for i in r]
                ax.step(x+[60],y+[y[-1]],where="post",color=COLORS[m],ls=STYLES[m],lw=2.3 if m=="NT" else 1.7,alpha=.92)
                ax.scatter(x,y,s=12,color=COLORS[m],zorder=5)
            if missing:ax.text(.98,.94,"未获 SAFE: "+", ".join(missing),ha="right",va="top",fontsize=8,transform=ax.transAxes)
            ax.set_title(case.replace("V","L").replace("_","  ·  "),loc="left",fontsize=11)
            ax.set_xlim(0,60);ax.set_xticks([0,10,30,60]);ax.set_ylabel("最低 SAFE 能耗（J）")
            ax.grid(axis="y",alpha=.18);ax.yaxis.set_major_locator(MaxNLocator(nbins=5,min_n_ticks=3))
        for ax in axes[-1]:ax.set_xlabel("从空搜索累计墙钟（s）")
        handles=[Line2D([0],[0],color=COLORS[m],ls=STYLES[m],lw=2,label=m) for m in COLORS]
        fig.legend(handles=handles,loc="outside upper right",ncol=4,frameon=False)
        fig.suptitle("八条开发次序" if phase=="development8" else "六条原留出次序",x=.07,ha="left",size=17)
        fig.savefig(FIG/(phase+"_quality.png"),dpi=160);plt.close(fig)

def trace():
    wins=rows("trace/physical_windows.csv")
    pick=("V640_HLHLHHLL","V320_LHHL")
    fig,axes=plt.subplots(3,2,figsize=(12,8.8),layout="constrained")
    for col,case in enumerate(pick):
        word=case.split("_")[1]
        for j,letter in enumerate(word):
            for ax in axes[:,col]:
                if letter=="H":ax.axvspan(j+.5,j+1.5,color="#f5d8bd",alpha=.38)
                ax.set_xlim(.5,len(word)+.5)
        for m in ("NC","NT"):
            r=[v for v in wins if v["case"]==case and v["method"]==m]
            x=list(range(1,1+len(r)))
            def draw(row,ys):
                axes[row,col].plot(x,ys,STYLES[m],marker="o",markersize=4,lw=2,color=COLORS[m],label=m)
            draw(0,[float(v["window_peak_hi_C"]) for v in r]);draw(1,[float(v["energy_J"]) for v in r]);draw(2,[float(v["min_deadline_slack_ms"]) for v in r])
        axes[0,col].axhline(80,color="#7d2527",lw=1,ls=":")
        for ax in axes[:,col]:
            ax.set_xticks(range(1,len(word)+1),[str(i+1)+" "+v for i,v in enumerate(word)]);ax.grid(axis="y",alpha=.18)
        axes[0,col].set_title(case.replace("V","L").replace("_"," · "),loc="left")
        axes[2,col].set_xlabel("决策窗与负载类型（底色为重载）")
    for ax,title in zip(axes[:,0],("窗内峰温上界（°C）","物理窗能耗（J）","当窗到达请求最小期限余量（ms）")):ax.set_ylabel(title)
    axes[0,0].legend(frameon=False,ncol=2);fig.suptitle("从相同负载看热状态、能耗和期限余量",x=.06,ha="left",size=16)
    fig.savefig(FIG/"cross_scene.png",dpi=160);plt.close(fig)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("which",choices=("trace","quality","all"),default="all",nargs="?")
    a=parser.parse_args()
    if a.which in ("trace","all"):trace()
    if a.which in ("quality","all"):quality()
