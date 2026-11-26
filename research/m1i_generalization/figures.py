"""Plot all measured incumbent staircases, repeated timing and paired ambient response."""
import itertools
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D
from analyze import DATA,readcsv
from design import ROOT,REG,METHODS

COLORS=("#00796b","#5b66a4","#bd6327","#855076")

def main():
    fontnames={f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams.update({"font.family":next((n for n in ("Noto Sans CJK SC","Noto Sans CJK JP") if n in fontnames),"DejaVu Sans"),
                         "axes.unicode_minus":False,"axes.spines.right":False,"axes.spines.top":False,"font.size":9})
    directory=ROOT/"figures";directory.mkdir(exist_ok=True)
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    changes=readcsv(DATA/"improvements.csv")
    for group in "ABCD":
        items=[c for c in cases if c["group"]==group]
        fig,axes=plt.subplots(len(items),4,squeeze=False,figsize=(13,1.8*len(items)+1.2),sharex=True,sharey="row")
        for i,c in enumerate(items):
            for j,m in enumerate(METHODS):
                ax=axes[i,j];ax.grid(axis="both",color="#dde2e3",lw=.5)
                series=[]
                for rp in (1,2,3):
                    sub=[r for r in changes if (r["case"],r["method"],int(r["repeat"]))==(c["case"],m,rp)]
                    x=np.asarray([float(r["t_s"]) for r in sub]);y=np.asarray([float(r["E_J"]) for r in sub])
                    series.append((x,y))
                    if len(x):
                        ax.step(np.r_[x,60],np.r_[y,y[-1]],where="post",color=COLORS[j],ls=("-","--",":")[rp-1],lw=1,alpha=.75)
                        ax.plot(x[0],y[0],".",color=COLORS[j],ms=3)
                grid=np.unique(np.r_[0.,60.,*(x for x,_ in series)])
                med=[]
                for t in grid:
                    v=[y[np.searchsorted(x,t,side="right")-1] for x,y in series if len(x) and x[0]<=t]
                    med.append(np.median(v) if len(v)>=2 else np.nan)
                ax.step(grid,med,where="post",color="#202020",lw=1.5)
                ns=sum(bool(len(x)) for x,_ in series)
                if ns<3:ax.text(.97,.92,f"SAFE {ns}/3",ha="right",va="top",transform=ax.transAxes,color="#a23821")
                if j==0:ax.set_ylabel(c["case"].split("_")[0]+f" · {c['ambient']}°C\n能耗（J）")
                if i==0:ax.set_title(m,color=COLORS[j],loc="left",fontweight="bold")
                if i==len(items)-1:ax.set_xlabel("从构造开始的实测时间（s）")
                ax.set_xlim(0,60);ax.set_xticks([0,10,30,60])
            if not any(r["case"]==c["case"] for r in changes):
                axes[i,0].set_yticks([])
                axes[i,0].set_ylabel(c["case"].split("_")[0]+f" · {c['ambient']}°C")
        fig.suptitle(f"{group} 组 · 完整已认证最低能耗曲线",x=.07,ha="left",fontsize=15)
        legends=[Line2D([0],[0],color="#79838a",ls=s,label=f"第 {n} 次") for n,s in enumerate(("-","--",":"),1)]
        legends.append(Line2D([0],[0],color="#202020",lw=2,label="至少两次 SAFE 后的中位数"))
        fig.legend(handles=legends,loc="upper right",ncol=4,frameon=False)
        fig.tight_layout(rect=(0,0,1,.95))
        fig.savefig(directory/("quality_"+group+".png"),dpi=150);plt.close(fig)
    data=[r for r in readcsv(DATA/"ambient_paired.csv") if r["regime"]=="60s"]
    flows=sorted({r["flow"] for r in data})
    fig,axes=plt.subplots(2,2,figsize=(10,6.2),sharex=True)
    for j,flow_id in enumerate(flows):
        for k,m in enumerate(METHODS):
            sub=sorted((r for r in data if (r["flow"],r["method"])==(flow_id,m)),key=lambda r:int(r["ambient"]))
            t=np.asarray([int(r["ambient"]) for r in sub])
            axes[0,j].plot(t,[float(r["SAFE_J"]) if int(r["success"])>=2 else np.nan for r in sub],
                           color=COLORS[k],marker=("o","s","^","x")[k],label=m,ls=("-","--","-.",":")[k])
            axes[1,j].plot(t+(k-1.5)*.25,[int(r["success"]) for r in sub],color=COLORS[k],marker=("o","s","^","x")[k],ls=("-","--","-.",":")[k])
        axes[0,j].set_title(flow_id.split("_")[1]+f" · {sub[0]['requests']} 请求",loc="left")
        axes[1,j].set_yticks([0,1,2,3]);axes[1,j].set_xlabel("实际环境温度（°C）")
        for ax in axes[:,j]:ax.set_xticks([25,35,45]);ax.grid(lw=.5,alpha=.35)
    axes[0,0].set_ylabel("60 秒最低 SAFE 能耗中位数（J）");axes[1,0].set_ylabel("三次计时中取得 SAFE 的次数")
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc="upper right",ncol=4,frameon=False)
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(directory/"ambient.png",dpi=155);plt.close(fig)
if __name__=="__main__":main()
