"""Render C/D/E from the published CSVs. No model or evaluation code is imported."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
D=ROOT/"derived"
F=ROOT/"figures"
F.mkdir(exist_ok=True)
for font in ("Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC","SimHei"):
    if any(x.name==font for x in font_manager.fontManager.ttflist): break
else: raise RuntimeError("Install a Chinese font such as Noto Sans CJK SC.")
plt.rcParams.update({"font.family":font,"font.size":10,"axes.unicode_minus":False,"svg.fonttype":"none","pdf.fonttype":42,
                     "axes.spines.top":False,"axes.spines.right":False,"axes.labelcolor":"#233443","text.color":"#233443",
                     "axes.edgecolor":"#9daab1","xtick.color":"#31434b","ytick.color":"#31434b"})
BLUE="#205977"; TEAL="#187769"; RED="#a64434"; GOLD="#a76d1d"
def read(n): return pd.read_csv(D/(n+".csv"),keep_default_na=False)
def emit(fig,name):
    for ext in ("svg","png","pdf"):
        fig.savefig(F/(name+"."+ext),dpi=200,bbox_inches="tight",pad_inches=.18)
    plt.close(fig)
def tidy(ax):
    ax.grid(axis="y",color="#e1e7e8",lw=.7);ax.set_axisbelow(True)
def C():
    t=read("temperature_traces");p=read("peak_certificates")
    fig,(ax,bx)=plt.subplots(2,1,figsize=(9,6.1),sharex=True,constrained_layout=True)
    fig.suptitle("图 C　相同频率方案在两种热评价下的温度演化",fontsize=16,fontweight="bold")
    g=t[t.node=="gpu"]
    dense=g[g.sample_type=="archived_sample"]
    for mode,lab,col in [("continuous","连续热继承",BLUE),("independent","逐场景重置",GOLD)]:
        z=dense[dense.eval_mode==mode]
        peak=p[(p.eval_mode==mode)&(p.solution_id==z.solution_id.iloc[0])].iloc[0].peak_upper_c
        ax.plot(z.t_s,z.temperature_c,color=col,lw=1.8,linestyle="-" if mode=="continuous" else "--",label=f"{lab}　峰温上界 {peak:.2f}°C")
    z=g[g.sample_type=="scene_endpoint"].drop_duplicates(["t_s","temperature_c"])
    peak=p[p.solution_id==z.solution_id.iloc[0]].iloc[0].peak_upper_c
    bx.scatter(z.t_s,z.temperature_c,s=43,color=TEAL,label=f"归档边界温度　全窗认证峰温上界 {peak:.2f}°C",zorder=3)
    ax.set_title("25°C／正序原驻留　 ·　 部署 C，全窗 HHH",loc="left")
    bx.set_title("同工况安全代表　 ·　 部署 C，LLL / LLL / LHL / LHL（场景端点）",loc="left")
    ticks=sorted(pd.to_numeric(t.loc[t.scene_marker!="","scene_marker"]).unique())
    for a in (ax,bx):
        a.axhline(80,color=RED,lw=1,ls=":");a.text(.08,80.7,"80°C 温限",color=RED,fontsize=9)
        for boundary in ticks[1:-1]:a.axvline(boundary,color="#b7c3c8",lw=.65,ls=":")
        a.set_ylim(25,90);a.set_ylabel("GPU 温度（°C）");a.legend(loc="lower right",fontsize=9,framealpha=.92);tidy(a)
    for i,(left,right) in enumerate(zip(ticks[:4],ticks[1:5])):ax.text((left+right)/2,85.5,f"SC{i}",ha="center",color="#687980",fontsize=8)
    bx.set_xticks(ticks[:4]+[ticks[-1]]);bx.set_xlim(-.09,ticks[-1]+.12);bx.set_xlabel("运行时间（s），含末尾 0.04 s")
    emit(fig,"figC")
def Dplot():
    d=read("reset_confusion");q=read("pressure_classification")
    fig,(a,b)=plt.subplots(1,2,figsize=(11,4.15),gridspec_kw={"width_ratios":[1,1.3]},constrained_layout=True)
    fig.suptitle("图 D　重置评价的误收与压力工况的连续热分类",fontsize=15,fontweight="bold")
    a.bar(d.deployment,d.false_accept_pct,color=[GOLD,GOLD,BLUE],width=.57)
    for i,r in enumerate(d.itertuples()):a.text(i,r.false_accept_pct+.12,f"{r.false_accept_pct:.2f}%\n{r.false_accept:,}/{r.assumed_safe:,}",ha="center",va="bottom",fontsize=9)
    a.set_ylim(0,6.3);a.set_ylabel("误收数 / 重置判安全数（%）");a.set_xlabel("部署");tidy(a)
    a.set_title("25°C 正序原驻留",loc="left")
    cases=["forward_alternating_27p5C","reverse_flat_27p5C","reverse_alternating_27p5C"]
    deps=["A","C","D001","D015"]
    matrix=np.array([[q[(q.instance_id==c)&(q.deployment==dep)].iloc[0].safe / q[(q.instance_id==c)&(q.deployment==dep)].iloc[0].deadline_legal for dep in deps] for c in cases])
    b.imshow(matrix,vmin=0,vmax=1,cmap=ListedColormap(["#f4dbd5","#c1e2d9"]),aspect="auto")
    for i,c in enumerate(cases):
        for j,dep in enumerate(deps):
            r=q[(q.instance_id==c)&(q.deployment==dep)].iloc[0]
            b.text(j,i,f"{r.safe:,}\n/ {r.deadline_legal:,}",ha="center",va="center",fontsize=9)
    b.set_yticks(range(3),["正序交替","逆序原驻留","逆序交替"]);b.set_xticks(range(4),deps);b.set_xlabel("部署　 ·　 格中为安全数 / 满足期限数")
    b.set_title("27.5°C 连续热分类",loc="left")
    emit(fig,"figD")
def E():
    d=read("ablation_results").set_index("ablation_id")
    keys=["FixA-Static-DVFS","FixA-Scene-DVFS","Select81-Static-DVFS","Select81-Scene-DVFS"]
    d=d.loc[keys]
    fig,a=plt.subplots(figsize=(8.7,4.4),layout="constrained")
    fig.suptitle("图 E　常驻部署与场景调频对最低安全能耗的影响",fontsize=15,fontweight="bold")
    pos=[0,.77,1.95,2.72];a.bar(pos,d.best_safe_j,width=.6,color=[BLUE,TEAL,BLUE,TEAL])
    for x,r in zip(pos,d.itertuples()):
        a.text(x,r.best_safe_j+.7,f"{r.best_safe_j:.3f} J\n节能 {r.delta_pct:.2f}%",ha="center",fontsize=10)
    a.set_xticks(pos,["固定 A\n整窗同频","固定 A\n逐场景调频","81 部署可选\n整窗同频","81 部署可选\n逐场景调频"])
    a.set_ylabel("最低 SAFE 系统能耗（J）");a.set_ylim(0,59);tidy(a)
    a.set_title("25°C 逆序原驻留　 ·　 节能率统一以固定 A、整窗同频为分母",loc="left")
    emit(fig,"figE")
if __name__=="__main__": C();Dplot();E()
