"""Make editable SVG and print-resolution PNG figures from the verified case table."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np

HERE=Path(__file__).resolve().parent
rows=list(csv.DictReader((HERE/"summary.csv").open(encoding="utf-8")))
fonts={f.name for f in font_manager.fontManager.ttflist}
font=next((f for f in ("Microsoft YaHei","Noto Sans CJK SC","SimHei") if f in fonts),None)
if font is None:
    raise SystemExit("Install a CJK font to regenerate the Chinese figures")
plt.rcParams.update({"font.family":font,"font.size":9.5,"svg.fonttype":"none","svg.hashsalt":"ch3-milp-validation",
                     "axes.spines.top":False,"axes.spines.right":False,"axes.unicode_minus":False})
names=["正序原驻留","正序交替","逆序原驻留","逆序交替","正序交替","逆序原驻留","逆序交替","固定 D019"]
y=np.array([7.6,6.6,5.6,4.6,3.,2.,1.,-.55])
navy,orange,teal="#284d72","#b65a20","#207a73"


def save(fig,stem):
    path=HERE/"figures"
    path.mkdir(exist_ok=True)
    for ext in ("svg","png"):
        fig.savefig(path/f"{stem}.{ext}",dpi=260,bbox_inches="tight",pad_inches=.12,
                    metadata={"Date":None} if ext=="svg" else None)
    plt.close(fig)


def label_axis(ax, count):
    ax.set_yticks(y[:count], [r["label"]+"  "+s for r,s in zip(rows[:count],names)])
    ax.tick_params(axis="y",length=0,pad=8)
    ax.set_ylim(y[count-1]-.65,y[0]+.8)
    ax.axhline(3.85,color="#bbc3ca",lw=.7)
    ax.grid(axis="x",color="#dce0e4",lw=.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)


def energy():
    fig,(ax,tab)=plt.subplots(1,2,figsize=(8.4,4.6),gridspec_kw={"width_ratios":[2.3,1.0]})
    fig.subplots_adjust(wspace=.10,top=.84,bottom=.20,left=.18,right=.98)
    label_axis(ax,7)
    ax.set_xlim(42.85,45.48)
    ax.set_xlabel("10.04 s 全窗安全能耗（J）")
    ax.set_title("同域安全方案",loc="left")
    tab.set_xlim(0,1)
    tab.set_ylim(ax.get_ylim())
    tab.axis("off")
    tab.set_title("Kim 相对精确值的差额",loc="center")
    for i,r in enumerate(rows[:7]):
        y0=y[i]
        milp,exact=float(r["safe_j"]),float(r["exact_j"])
        ax.scatter(exact,y0,facecolors="none",edgecolors=navy,s=105,linewidths=1.2,zorder=4)
        ax.plot(milp,y0,marker="+",color=teal,ms=8,markeredgewidth=1.5,zorder=5)
        if r["kim_safe_mean_j"]:
            kim=float(r["kim_safe_mean_j"])
            ax.scatter(kim,y0+.18,marker="^",color=orange,s=32,zorder=6)
            delta=(kim-exact)*1000
            val=f"{delta:.3f} mJ" if delta else "0 mJ"
        else:
            val="缺同域记录"
        tab.text(.5,y0,val,ha="center",va="center")
    tab.axhline(3.85,color="#bbc3ca",lw=.7)
    handles=[Line2D([],[],marker="o",markerfacecolor="none",markeredgecolor=navy,ls="none",label="历史精确值"),
             Line2D([],[],marker="+",color=teal,ls="none",label="MILP 已证最优"),
             Line2D([],[],marker="^",color=orange,ls="none",label="Kim-Adapt+SAFE（5 种子均值）")]
    fig.legend(handles=handles,loc="lower center",frameon=False,ncol=3,bbox_to_anchor=(.54,.003))
    fig.text(.18,.96,"N1–N4：25°C，81 部署       P1–P3：27.5°C，四部署",va="top")
    save(fig,"01_safe_energy")


def costs():
    fig,(ax,small)=plt.subplots(1,2,figsize=(9.4,5.0),gridspec_kw={"width_ratios":[1.55,1]})
    fig.subplots_adjust(wspace=.18,top=.89,bottom=.23,left=.17,right=.98)
    label_axis(ax,8)
    ax.axhline(.2,color="#bbc3ca",lw=.7)
    keys=["schedule_s","coefficient_s","matrix_s","solver_s","full_cert_s","other_wall_s"]
    labels=["事件调度","热系数生成","矩阵构建","MILP 求解","完整热认证","启动及其他"]
    colors=[navy,teal,"#95722e",orange,"#816294","#cbd1d6"]
    left=np.zeros(len(rows))
    for key,label,color in zip(keys,labels,colors):
        v=np.array([float(r[key]) for r in rows])
        ax.barh(y,v,left=left,height=.53,color=color,label=label)
        left+=v
    ax.set_xlabel("全流程墙钟（s）")
    ax.set_title("全流程成本",loc="left")
    ax.set_xlim(0,34)
    for key,label,color,shift,marker in zip(keys[2:5],labels[2:5],colors[2:5],[.20,0.,-.20],["s","o","^"]):
        v=[1000*float(r[key]) for r in rows]
        small.scatter(v,y+shift,s=29,marker=marker,color=color)
    small.set_ylim(ax.get_ylim())
    small.set_xlim(0,312)
    small.set_yticks([])
    small.spines["left"].set_visible(False)
    small.grid(axis="x",color="#dce0e4",lw=.6)
    for split in (3.85,.2):
        small.axhline(split,color="#bbc3ca",lw=.7)
    small.set_xlabel("单次运行累计耗时（ms）")
    small.set_title("矩阵、求解和认证的耗时细节",loc="left")
    fig.legend(*ax.get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False,
               bbox_to_anchor=(.55,0))
    save(fig,"03_wall_time")


energy()
costs()
