from analyze import stats,OUT
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,font_manager
from matplotlib.lines import Line2D

def plot():
    for family in ("Microsoft YaHei","Noto Sans CJK SC","SimHei"):
        if any(f.name==family for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"]=family
            break
    cells=stats.csvrows("cells");steps=stats.csvrows("improvements");flows=stats.csvrows("flow_summary")
    fig,axes=plt.subplots(4,3,figsize=(13,11),sharey="row",constrained_layout=True)
    colors=dict(A="#2c6390",B="#bc521c")
    marks={"1":"-","2":"--","3":"-."}
    for row,case in enumerate(stats.CASES):
        for col,cap in enumerate(("10","20","60")):
            ax=axes[row,col]; current=[r for r in cells if r["case"]==case and r["cap"]==cap]
            target=next(float(r["ref_hi"]) for r in flows if r["case"]==case)
            for r in current:
                pts=[p for p in steps if all(p[k]==r[k] for k in ("case","rep","cap","arm"))]
                if not pts:continue
                x=[float(p["t"]) for p in pts];y=[float(p["J"]) for p in pts]
                ax.step(x+[float(cap)],y+[y[-1]],where="post",lw=1.4,alpha=.85,c=colors[r["arm"]],ls=marks[r["rep"]])
                ax.scatter(x,y,color=colors[r["arm"]],s=9)
            ax.axhline(target,color="#42454b",lw=1,ls=":")
            ax.axhline(target*1.01,color="#5a8a67",lw=1,ls=":")
            ax.set_xlim(0,int(cap)*1.01)
            if row==0:ax.set_title(cap+" 秒预算")
            if col==0:ax.set_ylabel(case+"\n完整系统能耗（焦耳）")
            if row==3:ax.set_xlabel("求解时间（秒）")
            ax.ticklabel_format(axis="y",useOffset=False,style="plain")
            ax.grid(axis="y",alpha=.14)
            successes=[f"{arm} {sum(int(r['safe']) for r in current if r['arm']==arm)}/3" for arm in sorted({r["arm"] for r in current})]
            ax.text(.02,.96,"  ".join(successes),transform=ax.transAxes,va="top",fontsize=8,
                    bbox=dict(facecolor="white",alpha=.8,edgecolor="none",pad=1))
    legend=[Line2D([],[],color=c,label=n) for c,n in [(colors["A"],"原配额"),(colors["B"],"低成本配额")]]
    legend += [Line2D([],[],color="#393c41",ls=v,label="重复 "+k) for k,v in marks.items()]
    legend += [Line2D([],[],color=c,ls=":",label=n) for c,n in [("#42454b","同期目标"),("#5a8a67","目标放宽 1%")]]
    fig.legend(handles=legend,loc="outside lower center",ncol=7,frameon=False)
    fig.suptitle("统一预热后，首次安全交付及后续能耗改善")
    fig.savefig(OUT/"energy_time.png",dpi=140)
    plt.close(fig)
if __name__=="__main__":plot()
