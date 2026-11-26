"""Plot measured incumbent staircases and render human-readable per-order tables."""
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from summarize import DATA,ROOT,CUTS,METHODS,rows

FIG=ROOT/"figures"
FIG.mkdir(exist_ok=True)
available={f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({"font.family":next((f for f in ("Noto Sans CJK SC","Noto Sans CJK JP") if f in available),"DejaVu Sans"),
                     "axes.unicode_minus":False,"axes.spines.top":False,"axes.spines.right":False,"font.size":10})
COLORS=("#006d58","#92509b","#b47611","#b94049","#3264a1")
LINES=("-","--","-.",":","--")

def fmt(x,n=4):
    return f"{float(x):.{n}f}" if x!="" else "—"

def contrast(cases):
    import numpy as np
    from matplotlib import colors
    pairs=rows(DATA/"paired.csv")
    cols=[(k,m) for k in ("W4/K4","60s") for m in ("NC","ZQ-Beam","LQ-Beam")]
    lookup={(r["case"],r["regime"],r["right"]):r for r in pairs if r["left"]=="NT"}
    grid=np.full((len(cases),len(cols)),np.nan)
    for i,c in enumerate(cases):
        for j,(k,m) in enumerate(cols):
            value=lookup[c,k,m]["saving_pct"]
            if value:
                grid[i,j]=float(value)
    limit=max(.01,np.nanmax(np.abs(grid)))
    cmap=plt.get_cmap("PiYG").copy();cmap.set_bad("#e1e3e4")
    fig,ax=plt.subplots(figsize=(9,7),layout="constrained")
    image=ax.imshow(grid,aspect="auto",cmap=cmap,norm=colors.TwoSlopeNorm(0,-limit,limit))
    for i,c in enumerate(cases):
        for j,(k,m) in enumerate(cols):
            val=grid[i,j]
            label=f"{val:+.2f}" if np.isfinite(val) and abs(val)>=.005 else "0.00" if np.isfinite(val) else {"only_left":"仅 NT","only_right":"仅对照","neither":"均无"}[lookup[c,k,m]["result"]]
            ax.text(j,i,label,ha="center",va="center",color="white" if np.isfinite(val) and abs(val)>.65*limit else "#202020",fontsize=9)
    ax.set_yticks(range(len(cases)),[c[1:].replace("_"," · ") for c in cases])
    ax.set_xticks(range(len(cols)),[k+"\n"+m for k,m in cols])
    ax.axvline(2.5,color="white",lw=3)
    fig.colorbar(image,ax=ax,label="NT 相对列方法的节能率（%）",shrink=.75)
    ax.set_title("固定四次认证与 60 秒终点的配对节能率",loc="left",pad=12)
    fig.savefig(FIG/"paired_mechanisms.png",dpi=150);plt.close(fig)


def main():
    cuts=rows(DATA/"checkpoints.csv")
    inc=rows(DATA/"improvements.csv")
    lookup={(r["case"],r["method"],r["regime"]):r for r in cuts}
    cases=sorted({r["case"] for r in cuts},key=lambda v:(-int(v.split("_")[0][1:]),v))
    contrast(cases)
    lines=["# 逐工况结果","","每格均来自本轮实测。能耗用 J，固定规模只认首个宽四池的前四份连续证书。普通 C2 为实际效率基线。W4/K4 的结束时刻依方法与工况而异，10/30/60 秒为同一条 60 秒策略上的实时时钟截面。",""]
    for phase,title in (("development8","原八条开发次序"),("former_holdout6","原六条留出次序")):
        subset=[c for c in cases if lookup[c,"NT","60s"]["phase"]==phase]
        fig,axes=plt.subplots(len(subset)//2,2,figsize=(12,2.6*(len(subset)//2)+1),layout="constrained")
        for ax,c in zip(axes.flat,subset):
            for m,col,ls in zip(METHODS,COLORS,LINES):
                pts=[r for r in inc if r["method"]==m and r["case"]==c]
                if not pts:continue
                x=[float(r["t_s"]) for r in pts];y=[float(r["E_J"]) for r in pts]
                ax.step(x+[60],y+y[-1:],where="post",color=col,ls=ls,lw=2.2 if m=="NT" else 1.6)
                ax.scatter(x,y,color=col,s=9)
            for t in (10,30): ax.axvline(t,color=".78",lw=.7)
            ax.set_title(c[1:].replace("_"," · "),loc="left");ax.set_xlim(0,60);ax.set_xticks([0,10,30,60])
            ax.set_ylabel("最低 SAFE 能耗（J）");ax.grid(axis="y",alpha=.18)
        for ax in axes[-1]:ax.set_xlabel("从空搜索的墙钟时间（s）")
        fig.suptitle(title,x=.065,ha="left",size=17)
        fig.legend(handles=[Line2D([0],[0],color=col,ls=ls,lw=2,label=m) for m,col,ls in zip(METHODS,COLORS,LINES)],
                   loc="outside upper right",ncol=5,frameon=False)
        fig.savefig(FIG/(phase+".png"),dpi=150);plt.close(fig)
        lines+=["## "+title,"",f"![逐条已认证最低能耗曲线](figures/{phase}.png)","",
                "各格依次给出 **W4/K4 · 10 s · 30 s · 60 s** 的最低 SAFE 能耗。— 表示到点未取得 SAFE。","",
                "| 请求数 · 负载次序 | "+" | ".join(METHODS)+" |","|---|"+"---:|"*5]
        for c in subset:
            cells=[" · ".join(fmt(lookup[c,m,k]["SAFE_J"]) for k in CUTS) for m in METHODS]
            lines.append("| "+" | ".join([c[1:].replace("_"," · ")]+cells)+" |")
        lines.append("")
    lines+=["## 首解和构造开销","","每格依次为 **首次 SAFE 秒数 / 60 秒内构造及排序秒数 / 60 秒最佳解的峰温上界 °C**。各截面的相应数值、实际停止秒数、认证时间、已完成/已认证 SAFE 数及最优解哈希见[完整截面](data/checkpoints.csv)。","",
            "| 工况 | "+" | ".join(METHODS)+" |","|---|"+"---:|"*5]
    for c in cases:
        cells=[" / ".join(fmt(lookup[c,m,"60s"][k],2) for k in ("first_SAFE_s","build_sort_s","peak_C")) for m in METHODS]
        lines.append("| "+" | ".join([c[1:].replace("_"," · ")]+cells)+" |")
    lines+=["","[全部十对方法的逐工况胜负和节能率](data/paired.csv) · [逐次改善](data/improvements.csv) · [每次送验及原计划身份](data/calls.csv.gz) · [各级束宽与终端池规模](data/stages.csv)",""]
    (ROOT/"results.md").write_text("\n".join(lines),encoding="utf8")


if __name__=="__main__":
    main()
