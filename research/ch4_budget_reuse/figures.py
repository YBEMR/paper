"""Three editable figures. All joules stay within the matched workload and temperature."""
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COL={"A":"#305a91","B":"#b35328","C":"#18816b"}
CASES=[("original","30"),("A","25"),("B","30")]
CN={"original":"原始","A":"负载 A","B":"负载 B"}


def table(n):
    with (HERE/"tables"/(n+".csv")).open(encoding="utf8") as f: return list(csv.DictReader(f))


def save(fig,name):
    dest=HERE/"figures";dest.mkdir(exist_ok=True)
    pdf=ROOT/"research/latex/figures/ch4_budget_reuse";pdf.mkdir(parents=True,exist_ok=True)
    target=dest/(name+".svg")
    fig.savefig(target,bbox_inches="tight",metadata={"Date":None})
    target.write_bytes(("\n".join(s.rstrip() for s in target.read_text(encoding="utf8").splitlines())+"\n").encode())
    fig.savefig(pdf/(name+".pdf"),bbox_inches="tight",metadata={"CreationDate":None})
    plt.close(fig)


def run():
    fonts={f.name for f in font_manager.fontManager.ttflist}
    font=next(f for f in ("Microsoft YaHei","Noto Sans CJK SC","SimHei") if f in fonts)
    plt.rcParams.update({"font.family":font,"svg.fonttype":"none","svg.hashsalt":"ch4-budget",
                         "pdf.fonttype":42,"font.size":9,"axes.spines.right":False,
                         "axes.spines.top":False,"axes.unicode_minus":False,"axes.axisbelow":True})
    rows=[r for r in table("runs") if r["role"]=="main"]
    arms=sorted({r["arm"] for r in rows})
    curves=defaultdict(list)
    for r in table("improvements"): curves[r["slot"]].append((float(r["time_s"]),float(r["energy_j"])))
    legend=[Line2D([0],[0],color=COL[a],label=a) for a in arms]
    fig,axes=plt.subplots(3,2,figsize=(10,7.2),sharex="col")
    for j,(l,t) in enumerate(CASES):
        group=[r for r in rows if (r["load"],r["temp"])==(l,t)]
        for ax,lim in zip(axes[j],(20,116)):
            ax.set_xlim(0,lim)
            ax.axhline(float(group[0]["ref_j"])*1.001,color="#333333",lw=.8,ls=":")
            trans=blended_transform_factory(ax.transData,ax.transAxes)
            for i,r in enumerate(group):
                vals=[v for v in curves[r["slot"]] if v[0]<=lim]
                c=COL[r["arm"]]
                first=vals[0][0] if vals else lim
                ax.plot([0,first],[.017+.011*i]*2,color=c,lw=.7,transform=trans,clip_on=False)
                if vals:
                    x,y=zip(*vals)
                    ax.step([*x,lim],[*y,y[-1]],where="post",color=c,alpha=.60,lw=1.1)
                    ax.scatter(x[0],y[0],s=7,color=c)
            low,high=ax.get_ylim()
            ax.set_ylim(low-.18*(high-low),high)
            ax.grid(axis="y",alpha=.18)
            ax.set_ylabel(f"{CN[l]} {t}°C\nSAFE 能耗（J）")
        axes[j,0].set_xticks([0,5,10,15,20]);axes[j,1].set_xticks([0,20,40,60,80,100,116])
    axes[0,0].set_title("前 20 s");axes[0,1].set_title("完整接纳窗口")
    for ax in axes[-1]: ax.set_xlabel("从创建进程前计时（s）")
    fig.legend(handles=legend+[Line2D([0],[0],ls=":",color="#333333",label="既定参考 × 1.001")],
               loc="upper center",ncol=4,frameon=False)
    fig.subplots_adjust(top=.89,hspace=.60,wspace=.24)
    save(fig,"energy_over_time")
    fig,axes=plt.subplots(1,2,figsize=(9.6,4.5),sharey=True)
    for ax,field,title in zip(axes,("first_safe_s","near_s"),("首次 SAFE","首次进入既定参考 +0.1%")):
        labels=[]
        for ci,(l,t) in enumerate(CASES):
            for si,seed in enumerate((20261121,20261122,20261123)):
                lane=ci*3+si
                labels.append(f"{CN[l]} {t}°C · {str(seed)[-2:]}")
                group=sorted([r for r in rows if (r["load"],r["temp"],r["seed"])==(l,t,str(seed))],key=lambda r:r["arm"])
                xy=[]
                for mi,r in enumerate(group):
                    if r[field]:
                        x=float(r[field]);mark={"A":"o","B":"s","C":"^"}[r["arm"]]
                    else: x=116;mark="x"
                    y=lane+(mi-(len(group)-1)/2)*.18
                    ax.scatter(x,y,color=COL[r["arm"]],marker=mark,s=25,zorder=3);xy.append((x,y))
                ax.plot(*zip(*xy),color="#a3a8aa",lw=.8)
        ax.set_title(title);ax.set_xlabel("实际墙钟时间（s）");ax.grid(axis="x",alpha=.2)
    axes[0].set_yticks(range(9),labels);axes[0].invert_yaxis()
    fig.legend(handles=legend,loc="upper center",ncol=3,frameon=False)
    fig.tight_layout(rect=(0,0,1,.9));save(fig,"paired_times")
    categories={"初始化":["initialization"],"搜索与名额选择":["search_control","candidate_generation","candidate_ranking","parent_selection","setfreq_control","allocation_rule"],
        "调度与期限":["dispatch","deadline_screen"],"SetFreq 代理":["proxy_lookup","setfreq_thermal"],
        "构核":["kernel_build"],"查核、传播与筛查":["kernel_lookup","affine_query","peak_screen","cost_observation"],
        "边界回退":["peak_fallback"],"峰温证书补算":["peak_certificate_completion"],
        "原积分":["original_continuous","final_integral"],"记录与其他":["logging","trace_io_and_control","closeout","continuous_dispatch","final_certificate"]}
    palette=["#a7afb5","#596b7b","#529aae","#326493","#c57631","#f1b958","#9f3858","#cb7894","#398868","#becfb5"]
    data=table("exclusive_costs")
    fig,axes=plt.subplots(1,3,figsize=(10,4.2))
    for ax,(role,phase,title) in zip(axes,[("fixed","whole","固定调用流 · 全程"),
                   ("main","0_to_20","真实搜索 · 0–20 s"),("main","20_to_116","真实搜索 · 20–116 s")]):
        group=[r for r in data if r["role"]==role and r["phase"]==phase]
        methods=sorted({r["arm"] for r in group});bottom=np.zeros(len(methods))
        for (label,keys),color in zip(categories.items(),palette):
            height=np.array([np.mean([sum(float(r[k]) for k in keys) for r in group if r["arm"]==a]) for a in methods])
            ax.bar(methods,height,bottom=bottom,color=color,width=.59);bottom+=height
        ax.set_title(title);ax.set_ylabel("互斥墙钟成本（s）");ax.grid(axis="y",alpha=.15)
    fig.legend(handles=[Patch(facecolor=c,label=l) for l,c in zip(categories,palette)],
               loc="lower center",ncol=5,frameon=False)
    fig.tight_layout(rect=(0,.16,1,1));save(fig,"evaluation_costs")

if __name__=="__main__": run()
