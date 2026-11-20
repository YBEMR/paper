"""Render energy, false-admission and pressure panels from the included CSVs."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from figure_style import BLUE, DATA, GRAY, INK, ORANGE, TEAL, save, setup

CASES = ("forward_alternating_27p5C", "reverse_flat_27p5C", "reverse_alternating_27p5C")
SHORT = ("正序\n交替", "逆序\n原驻留", "逆序\n交替")
LONG = ("正序交替驻留", "逆序原驻留", "逆序交替驻留")
DEPS = ("A", "C", "D001", "D015")
STATE_STYLE = (("safe", "安全", TEAL, ""), ("overtemp", "超温", ORANGE, "///"),
               ("unresolved", "未决", GRAY, "xx"))
METHOD_STYLE = {"Max-Freq": ("最高频", "#7A8993", ""),
                "Static-DVFS": ("静态调频", BLUE, "//"),
                "Joint": ("联合调度", TEAL, "")}
DEP_STYLE = {"D001":(BLUE, ""), "D015":(TEAL, "//")}


def read(name):
    with (DATA / (name + ".csv")).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def title(ax, label):
    ax.set_title(label, loc="left", pad=11, fontsize=10.5)


def energy_axis(ax, rows, methods, heading):
    values = [float(rows[m]["minimum_safe_energy_j"]) for m in methods]
    for x, (method, value) in enumerate(zip(methods, values)):
        _, color, hatch = METHOD_STYLE[method]
        ax.bar(x,value,width=0.57,color=color,edgecolor="white",hatch=hatch,linewidth=0.5)
        ax.annotate(f"{value:.4f}",(x,value),xytext=(0,3),textcoords="offset points",
                    ha="center",va="bottom",fontsize=8.3)
    ax.set_xticks(range(len(methods)),[METHOD_STYLE[m][0] for m in methods])
    ax.set_ylim(0,72)
    ax.set_yticks((0,20,40,60))
    ax.set_xlim(-0.55,len(methods)-0.45)
    ax.set_ylabel("最低安全能耗 / J")
    ax.grid(axis="y")
    title(ax,heading)


def make_energy():
    rows = read("fig03_energy_domains")
    full = {r["method"]:r for r in rows if r["domain"]=="full81"}
    ac = {r["method"]:r for r in rows if r["domain"]=="original_AC"}
    fig=plt.figure(figsize=(7.65,4.95))
    gs=fig.add_gridspec(2,2,left=0.102,right=0.97,top=0.915,bottom=0.12,
                        hspace=0.87,wspace=0.43,height_ratios=(1.4,0.96),
                        width_ratios=(1.32,1))
    energy_axis(fig.add_subplot(gs[0,0]),full,list(METHOD_STYLE),
                "(a)  25 °C  ·  逆序原驻留，81 部署")
    energy_axis(fig.add_subplot(gs[0,1]),ac,["Static-DVFS","Joint"],
                "(b)  25 °C  ·  正序原驻留，A/C")
    ax=fig.add_subplot(gs[1,:])
    errors=read("fig03_false_admissions")
    yes=[int(x["both_safe"]) for x in errors]
    false=[int(x["reset_false_accepted"]) for x in errors]
    dep=[x["deployment"] for x in errors]
    ypos=np.arange(len(dep))
    ax.barh(ypos,yes,height=0.54,color=TEAL,label="连续安全")
    ax.barh(ypos,false,left=yes,height=0.54,color=ORANGE,edgecolor="white",linewidth=0.5,
            hatch="///",label="超温误接纳")
    ax.set_yticks(ypos,dep)
    ax.set_ylim(1.62,-0.62)
    ax.set_xlim(0,68900)
    for y,(safe,wrong) in enumerate(zip(yes,false)):
        ax.text(safe/2,y,f"{safe:,}",ha="center",va="center",color="white",fontsize=9)
        ax.annotate(f"{wrong:,}",xy=(safe+wrong,y),xytext=(5,0),textcoords="offset points",
                    ha="left",va="center",fontsize=8.7,color=INK)
    ax.set_xticks((0,15000,30000,45000,60000))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v,pos:f"{v:,.0f}"))
    ax.set_xlabel("独立重置评价接纳的频率序列数")
    ax.grid(axis="x")
    title(ax,"(c)  25 °C  ·  正序原驻留，A/C 的连续热复核")
    ax.legend(loc="lower right",bbox_to_anchor=(1.02,1.04),
              ncol=2,handlelength=1.2,columnspacing=1.3,borderaxespad=0)
    save(fig,"fig03_baselines")
    plt.close(fig)


def class_panel(ax):
    rows={(r["case_id"],r["deployment"]):r for r in read("fig05_classes")}
    positions=np.array([g*5+i for g in range(3) for i in range(4)],dtype=float)
    cells=[rows[case,dep] for case in CASES for dep in DEPS]
    base=np.zeros(len(cells))
    for key,label,color,hatch in STATE_STYLE:
        counts=np.array([int(r[key]) for r in cells])
        ax.bar(positions,counts,bottom=base,width=0.68,color=color,edgecolor="white",
               linewidth=0.5,hatch=hatch,label=label)
        base+=counts
    for x,count in zip(positions,base):
        ax.annotate(f"{int(count):,}",(x,count),xytext=(0,3),textcoords="offset points",
                    ha="center",va="bottom",fontsize=7.4)
    for g,label in enumerate(LONG):
        ax.text(g*5+1.5,-0.235,label,transform=ax.get_xaxis_transform(),ha="center",
                va="top",fontsize=9,clip_on=False)
    ax.set_xlim(-0.67,13.68)
    ax.set_ylim(0,69500)
    ax.set_yticks((0,20000,40000,60000))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{int(x):,}"))
    ax.set_xticks(positions,DEPS*3)
    ax.set_ylabel("期限合法的频率序列数")
    ax.grid(axis="y")
    ax.legend(ncol=3,loc="lower right",bbox_to_anchor=(1.0,1.04),
              columnspacing=1.2,handlelength=1.3,borderaxespad=0)


def margin_panels(axes, markers):
    values={(r["case_id"],r["deployment"]):r for r in read("fig05_margins")}
    panels=(("minimum_safe_energy_j","最低安全能耗 / J",52,(0,15,30,45),".2f"),
            ("thermal_margin_c","热裕量 / °C",12,(0,3,6,9,12),".2f"),
            ("min_deadline_slack_ms","最小期限裕量 / ms",1.5,(0,0.5,1,1.5),".3f"))
    for ax,marker,(column,label,up,ticks,nformat) in zip(axes,markers,panels):
        for dep,offset in (("D001",-0.18),("D015",0.18)):
            color,hatch=DEP_STYLE[dep]
            vals=[float(values[c,dep][column]) for c in CASES]
            x=np.arange(3)+offset
            bars=ax.bar(x,vals,width=0.34,color=color,edgecolor="white",linewidth=0.45,hatch=hatch)
            # Vertical value labels remain distinct when the two safe energies are close.
            for bar,val in zip(bars,vals):
                ax.annotate(format(val,nformat),(bar.get_x()+bar.get_width()/2,val),
                            xytext=(0,3),textcoords="offset points",ha="center",va="bottom",
                            rotation=90,fontsize=7.2,color=INK)
        ax.set_xticks(range(3),SHORT)
        ax.set_xlim(-0.56,2.56)
        ax.set_ylim(0,up*1.14)
        ax.set_yticks(ticks)
        ax.grid(axis="y")
        title(ax,f"({marker})  {label}")


def deployment_legend(fig,y):
    handles=[Patch(label=d,facecolor=color,edgecolor="white",hatch=hatch)
             for d,(color,hatch) in DEP_STYLE.items()]
    fig.legend(handles=handles,ncol=2,loc="upper center",bbox_to_anchor=(0.50,y),
               handlelength=1.35,columnspacing=1.9,borderaxespad=0)


def make_pressure():
    fig=plt.figure(figsize=(7.65,5.70))
    gs=fig.add_gridspec(2,3,left=0.102,right=0.98,top=0.915,bottom=0.145,
                        height_ratios=(1.10,1),hspace=1.05,wspace=.30)
    ax=fig.add_subplot(gs[0,:])
    class_panel(ax)
    title(ax,"(a)  27.5 °C  ·  四部署的期限合法序列分类")
    margin_panels([fig.add_subplot(gs[1,i]) for i in range(3)],"bcd")
    deployment_legend(fig,0.059)
    save(fig,"fig05_pressure")
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(7.65,2.82))
    fig.subplots_adjust(left=0.113,right=0.98,top=0.83,bottom=0.263)
    class_panel(ax)
    title(ax,"27.5 °C  ·  三种压力工况，四种部署")
    save(fig,"fig05a_pressure_classes")
    plt.close(fig)

    fig,axes=plt.subplots(1,3,figsize=(7.65,2.95))
    fig.subplots_adjust(left=0.071,right=0.975,top=0.837,bottom=0.264,wspace=0.30)
    margin_panels(axes,"abc")
    deployment_legend(fig,0.095)
    save(fig,"fig05b_pressure_margins")
    plt.close(fig)


if __name__=="__main__":
    setup()
    make_energy()
    make_pressure()
