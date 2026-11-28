"""Draw all 180 step curves in three readable panels, preserving missing deliveries."""
import json
from summary import OUT,cases,stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

def plot():
    for fam in ("Microsoft YaHei","Noto Sans CJK SC","SimHei"):
        if any(f.name==fam for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"]=fam;break
    plt.rcParams["pdf.fonttype"]=42
    case_list=cases()
    cells=stats.csvrows("cells");steps=stats.csvrows("improvements")
    targets={r["case"]:float(r["ref_hi"]) if r["ref_hi"] else None for r in stats.csvrows("flow_summary")}
    colors=dict(A="#25608d",B="#b64c1d"); styles={"1":"-","2":"--","3":"-."}
    for i in range(0,len(case_list),4):
        group=case_list[i:i+4]
        fig,axes=plt.subplots(4,3,figsize=(13,11),sharey="row",constrained_layout=True)
        for row,case in enumerate(group):
            for col,cap in enumerate(("10","20","60")):
                ax=axes[row,col];rs=[r for r in cells if r["case"]==case and r["cap"]==cap]
                for r in rs:
                    ps=[s for s in steps if all(s[k]==r[k] for k in ("case","cap","rep","arm"))]
                    if not ps:continue
                    x=[float(p["t"]) for p in ps];y=[float(p["J"]) for p in ps]
                    ax.step(x+[float(cap)],y+[y[-1]],where="post",c=colors[r["arm"]],ls=styles[r["rep"]],lw=1.4)
                    ax.scatter(x,y,c=colors[r["arm"]],s=9)
                if targets[case] is not None:
                    for scale,c in ((1,"#343841"),(1.01,"#5a8a67")):ax.axhline(scale*targets[case],c=c,lw=1,ls=":")
                ax.set_xlim(0,1.01*int(cap));ax.grid(axis="y",alpha=.16)
                if row==0:ax.set_title(cap+" 秒预算")
                if col==0:ax.set_ylabel(case+"\n系统能耗（焦耳）")
                if row==3:ax.set_xlabel("求解时间（秒）")
                ax.ticklabel_format(axis="y",useOffset=False,style="plain")
                info=[f"{a} {sum(int(r['safe']) for r in rs if r['arm']==a)}/3" for a in sorted({r["arm"] for r in rs})]
                ax.text(.02,.96,"  ".join(info),transform=ax.transAxes,va="top",fontsize=8,
                        bbox=dict(facecolor="white",alpha=.8,edgecolor="none",pad=1))
        handles=[Line2D([],[],color=c,label=n) for c,n in ((colors["A"],"原配额"),(colors["B"],"低成本配额"))]
        handles += [Line2D([],[],color="#41474a",ls=l,label="重复 "+r) for r,l in styles.items()]
        handles += [Line2D([],[],color=c,ls=":",label=n) for c,n in (("#343841","同期目标"),("#5a8a67","容差目标"))]
        fig.legend(handles=handles,loc="outside lower center",ncol=7,frameon=False)
        fig.suptitle("安全排程交付及其后的能耗改善")
        fig.savefig(OUT/f"energy_time_{group[0]}_{group[-1]}.png",dpi=125)
        plt.close(fig)
if __name__=="__main__":plot()
