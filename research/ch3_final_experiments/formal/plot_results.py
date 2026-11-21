"""Generate thesis figures from archived CSVs. No scheduling or thermal computation."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
FIG=HERE/"figures"
T=HERE/"tables"
STYLES={"CT-Joint":("#152f45","*"),"Kim-Adapt":("#ac5920","o"),
        "Kim-Adapt+SAFE":("#247d68","s"),"Thermal-GA":("#78519a","D")}
CASES=["forward_flat_25C","forward_alternating_25C","reverse_flat_25C","reverse_alternating_25C"]
CASE_NAMES=["正序原驻留","正序交替驻留","逆序原驻留","逆序交替驻留"]
for family in ("Microsoft YaHei","Noto Sans CJK SC","SimHei"):
    if family in {f.name for f in font_manager.fontManager.ttflist}:
        break
plt.rcParams.update({"font.family":family,"font.size":10,"axes.unicode_minus":False,"pdf.fonttype":42,
                     "axes.spines.top":False,"axes.spines.right":False,"axes.edgecolor":"#99a6ab",
                     "axes.labelcolor":"#20343e","text.color":"#20343e"})


def save(fig,key):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG/(key+".pdf"),bbox_inches="tight",pad_inches=.14)
    fig.savefig(FIG/(key+".png"),bbox_inches="tight",pad_inches=.14,dpi=170)
    plt.close(fig)


def legend(fig):
    handles=[Line2D([],[],color=c,marker=m,linestyle="none",markersize=9 if n=="CT-Joint" else 6,label=n)
             for n,(c,m) in STYLES.items()]
    fig.legend(handles=handles,loc="lower center",ncol=4,frameon=False,fontsize=9)


def energy_figure(letter,pressure):
    d=pd.read_csv(T/f"fig{letter}.csv")
    cases=["reverse_flat_25C","reverse_flat_27p5C"] if pressure else CASES
    labels=["25°C","27.5°C"] if pressure else CASE_NAMES
    fig,axes=plt.subplots(2,1,sharex=True,figsize=(8.5,5.8))
    fig.subplots_adjust(top=.88,bottom=.16,hspace=.19,left=.12,right=.98)
    fig.suptitle("图 G　同请求与同四部署下的安全能耗和热裕量" if pressure else
                 "图 A　25°C、81 部署下的安全能耗与同域最优差距",fontsize=14,weight="bold")
    for ax,col,y in zip(axes,["safe_energy_j","margin_c" if pressure else "gap_pct"],
                        ["全窗系统能耗（J）","热裕量（°C）" if pressure else "高于精确最优（%）"]):
        for k,(method,(color,marker)) in enumerate(STYLES.items()):
            for i,case in enumerate(cases):
                safe=d[(d["method"]==method)&(d["case"]==case)&(d["outcome"]=="SAFE")].sort_values("seed")
                if safe.empty:
                    continue
                xs=i+(k-1.5)*.16
                jitter=np.linspace(-.047,.047,len(safe)) if len(safe)>1 else np.array([0.])
                ax.scatter(xs+jitter,safe[col],s=87 if method=="CT-Joint" else 27,marker=marker,
                           color=color,alpha=.96,edgecolor="white",linewidth=.35,zorder=3)
        ax.set_ylabel(y);ax.grid(axis="y",color="#e0e7e8",lw=.7);ax.set_axisbelow(True)
        ax.ticklabel_format(axis="y",style="plain",useOffset=False)
        if col!="safe_energy_j":
            ax.axhline(0,color="#89999d",lw=.7,ls=":")
    axes[-1].set_xticks(range(len(labels)),labels);axes[-1].set_xlim(-.5,len(labels)-.5)
    legend(fig);save(fig,"fig"+letter)


def status_figure(letter,pressure):
    d=pd.read_csv(T/f"fig{letter}.csv")
    cases=["reverse_flat_25C","reverse_flat_27p5C"] if pressure else CASES
    labels=["25°C","27.5°C"] if pressure else CASE_NAMES
    fig,ax=plt.subplots(figsize=(7.4 if pressure else 8.6,3.7))
    grid=np.empty((4,len(cases)));ann=[]
    for i,method in enumerate(STYLES):
        for j,case in enumerate(cases):
            r=d[(d["method"]==method)&(d["case"]==case)].iloc[0]
            grid[i,j]=r.safe/r.n
            ann.append((i,j,f"{r.safe}/{r.n}" if method!="CT-Joint" else "SAFE（精确）"))
    from matplotlib.colors import LinearSegmentedColormap
    ax.imshow(grid,cmap=LinearSegmentedColormap.from_list("safe",["#f4ece6","#c3ded6","#235e59"]),
              vmin=0,vmax=1,aspect="auto")
    for i,j,label in ann:
        ax.text(j,i,label,ha="center",va="center",fontweight="bold",color="white" if grid[i,j]>.7 else "#183d40")
    ax.set_xticks(range(len(labels)),labels);ax.set_yticks(range(4),list(STYLES));ax.tick_params(length=0,pad=6)
    for axis in ax.spines.values():axis.set_visible(False)
    for i in np.arange(.5,4):ax.axhline(i,color="white",lw=2)
    fig.suptitle("图 F　逆序原驻留、四部署下的 SAFE 返回数" if pressure else
                 "图 B　25°C、81 部署下的 SAFE 返回数",fontsize=14,weight="bold")
    ax.set_xlabel("随机方法显示成功种子数 / 5；CT-Joint 每个工况复用一份确定性证书",labelpad=10)
    fig.tight_layout();save(fig,"fig"+letter)


def figure_c():
    ref=HERE.parent/"derived"
    archived=pd.read_csv(ref/"temperature_traces.csv")
    certs=pd.read_csv(ref/"peak_certificates.csv")
    native=pd.read_csv(HERE/"raw/figureC/samples.csv")
    import json
    proof=json.loads((HERE/"raw/figureC/certificate.json").read_bytes())["physical"]
    fig,(ax,bx)=plt.subplots(2,1,figsize=(8.5,5.7),sharex=True,constrained_layout=True)
    fig.suptitle("图 C　25°C 正序原驻留的 GPU 温度轨迹",fontsize=14,weight="bold")
    for mode,lab,col,ls in [("continuous","连续热继承","#22577a","-"),("independent","逐场景重置","#bc7624","--")]:
        d=archived[(archived.node=="gpu")&(archived.eval_mode==mode)&(archived.sample_type=="archived_sample")]
        hi=certs[(certs.solution_id==d.solution_id.iloc[0])&(certs.eval_mode==mode)].iloc[0].peak_upper_c
        ax.plot(d.t_s,d.temperature_c,color=col,ls=ls,label=f"{lab}　峰温上界 {hi:.2f}°C")
    bx.plot(native.t_ns/1e9,native.gpu_c,color="#247d68",lw=1.4,
            label=f"连续热继承　峰温上界 {max(proof['peak_upper_c']):.2f}°C")
    ax.set_title("部署 C　四个场景均用 HHH",loc="left",fontsize=10)
    bx.set_title("部署 C　LLL / LLL / LHL / LHL　按物理事件边界采样",loc="left",fontsize=10)
    for a in (ax,bx):
        for row in proof["scene_rows"][1:]:a.axvline(row["start_ns"]/1e9,color="#aebcbc",ls=":",lw=.65)
        a.axhline(80,ls=":",color="#ac4839",lw=1);a.text(.06,80.6,"80°C 温限",fontsize=8,color="#ac4839")
        a.set_ylabel("GPU 温度（°C）");a.set_ylim(25,90);a.set_xlim(0,10.04)
        a.grid(axis="y",lw=.6,color="#e2e7e7");a.legend(fontsize=9,loc="lower right")
    bx.set_xlabel("运行时间（s），含末尾 40 ms");save(fig,"figC")


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--only-c",action="store_true");a=p.parse_args()
    figure_c()
    if not a.only_c:
        energy_figure("A",False);status_figure("B",False);status_figure("F",True);energy_figure("G",True)
