"""Visualize the complete local integer diagnostic and the actual generated quotas."""
import csv
import gzip
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,font_manager
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from base import ROOT,Case,load,np
from attribution import empty,advance,sets


def main():
    src=ROOT/"data/diagnostic"
    grid=np.full((61,41),-1,int)
    palette=["#e9ecee","#d56354","#147d64"]
    with gzip.open(src/"cold_w10.csv.gz","rt") as f:
        for r in csv.DictReader(f):
            if (r["g"],r["n"])==("4","1"):
                st=r["physical_status"]
                grid[int(r["y"]),int(r["x"])]=0 if st in ("timing","time_bound") else 2 if st=="safe_bound" else 1
    assert grid.min()==0 and np.sum(grid==2)==6
    c=Case("L800",ROOT/"data/audit")
    p=empty(c)
    for i,action in enumerate(load(src/"cold_w10.json")["reference_actions"][:9]):
        p=advance(c,p,i,action)
    o,n,h,_,_=sets(c,p,9,(4,1))
    _,nt,ht,_,_=sets(c,p,9,(4,1),True)
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=font).get_name()
    plt.rcParams.update({"font.size":10,"axes.unicode_minus":False})
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),gridspec_kw={"width_ratios":[1,1.05]})
    for ax in axes:
        ax.imshow(grid,origin="lower",extent=[-.5,40.5,-.5,60.5],cmap=ListedColormap(palette),
                  norm=BoundaryNorm([-.5,.5,1.5,2.5],3),interpolation="nearest",aspect="auto")
        ax.set_xlabel("分至 NPU 的 A 类请求数 x")
    axes[0].set_ylabel("分至 NPU 的 B 类请求数 y")
    axes[0].set_title("完整整数格点",loc="left")
    axes[0].set_xlim(-.5,40.5);axes[0].set_ylim(-.5,60.5)
    axes[0].legend(handles=[Patch(color=p,label=l) for p,l in zip(palette,["期限不可行","连续超温或模型区间外","完整 SAFE"])],loc="upper right",fontsize=8)
    axes[1].set_title("安全带附近的实际生成点",loc="left")
    for vals,marker,color,label,size in [(h,"o","#2e3064","热边界",65),(ht,"x","#151515","热边界＋期限筛查",60)]:
        pts=np.array(sorted(vals))
        if marker=="o":
            axes[1].scatter(pts[:,0],pts[:,1],s=size,marker=marker,facecolors="none",edgecolors=color,linewidths=1.7,label=label)
        else:
            axes[1].scatter(pts[:,0],pts[:,1],s=size,marker=marker,c=color,linewidths=1.7,label=label)
    axes[1].set_xlim(16.5,25.5);axes[1].set_ylim(5.5,17.5)
    axes[1].set_xticks(range(17,26,2));axes[1].set_yticks(range(6,18,2))
    axes[1].legend(loc="upper right",fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT/"L800_末窗配额.png",dpi=175,bbox_inches="tight")
    plt.close(fig)


if __name__=="__main__":
    main()
