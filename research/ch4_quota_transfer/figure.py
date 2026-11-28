"""Plot only delivered, strictly improving certified energies."""
from decision import CASES, OUT, csvrows, med
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

def render():
    for font in ("Microsoft YaHei","Noto Sans CJK SC","SimHei"):
        if any(f.name==font for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"]=font
            break
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    curves=csvrows("improvements"); cells=csvrows("cells")
    styles={"1":("#24695c","-"),"2":("#397db4","--"),"3":("#965690","-.")}
    for ax,case in zip(axes.flat,CASES):
        rows=[r for r in cells if r["case"]==case]
        for r in rows:
            pts=[p for p in curves if all(p[k]==r[k] for k in ("case","rep","cap","arm"))]
            if not pts:continue
            xs=[float(p["t"]) for p in pts];ys=[float(p["J"]) for p in pts]
            color,ls=styles[r["rep"]]
            ax.step(xs+[float(r["cap"])],ys+[ys[-1]],where="post",c=color,ls=ls,lw=1.5)
            ax.scatter(xs,ys,c=color,s=11,zorder=3)
        hi=med(r["hi"] for r in rows if r["cap"]=="60")
        if hi:
            ax.axhline(hi,c="#343841",lw=1,ls=":")
            ax.axhline(hi*1.01,c="#a0643b",lw=1,ls=":")
        for x in (10,20):ax.axvline(x,c="#a8adb2",lw=.8,ls=":")
        ax.set(title=case,xlim=(0,61),xlabel="自冷启动起的墙钟时间（秒）",ylabel="完整系统能耗（焦耳）")
        ax.grid(axis="y",alpha=.18)
        ax.ticklabel_format(axis="y",useOffset=False,style="plain")
    handles=[Line2D([],[],color=c,ls=l,label="长预算第"+r+"次") for r,(c,l) in styles.items()]
    handles += [Line2D([],[],color=c,ls=":",label=n) for c,n in [("#343841","共同能耗目标"),("#a0643b","目标放宽百分之一")]]
    fig.legend(handles=handles,loc="outside lower center",ncol=5,frameon=False)
    fig.suptitle("安全排程交付后的能耗变化",fontsize=16)
    fig.savefig(OUT/"energy_time.png",dpi=145)
    plt.close(fig)

if __name__=="__main__": render()
