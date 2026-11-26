"""Generate paper figures and each figure's source table from audited endpoints."""
import csv
import shutil
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from audit_results import HERE,ROOT,RESULTS,CASES,MAIN,SEEDS,THERMAL

M=list(MAIN)
SHORT=["Greedy","GA","SA","ETA-TS","eFLS","AB","Proposed"]
MODES=["T0","T1","T2","T3"]
COL=["#6f7782","#be8859","#7971a5","#537687","#839654","#99596b","#186966"]
MARK=["o","s","^","D","v","P","*"]
FIG=RESULTS/"figures"
plt.rcParams.update({"font.family":["Times New Roman","SimSun","DejaVu Sans"],"font.size":9,
    "axes.spines.top":False,"axes.spines.right":False,"axes.linewidth":.65,"svg.fonttype":"none","svg.hashsalt":"ch3-final-figures"})


def export(fig,name,data):
    data.to_csv(FIG/(name+".csv"),index=False,lineterminator="\n")
    vector=FIG/(name+".svg")
    fig.savefig(vector,metadata={"Date":None})
    vector.write_bytes(b"\n".join(line.rstrip() for line in vector.read_bytes().splitlines())+b"\n")
    fig.savefig(FIG/(name+".png"),dpi=360)
    plt.close(fig)


def interval(ax,idx,vals,color,marker="o"):
    vals=np.array([v for v in vals if pd.notna(v)])
    if len(vals):
        ax.plot([idx,idx],[min(vals),max(vals)],color=color,lw=1.15)
        ax.scatter(idx+np.linspace(-.1,.1,len(vals)),vals,marker=".",color=color,s=10)
        ax.scatter([idx],[np.median(vals)],marker=marker,color=color,s=31,zorder=3)
    if len(vals)<3:
        ax.text(idx,.01,f"{len(vals)}/3",transform=ax.get_xaxis_transform(),ha="center",fontsize=7)


def columns(ax,labels):
    ax.set_xticks(range(len(labels)),labels,rotation=29,ha="right",fontsize=8)
    ax.set_xlim(-.5,len(labels)-.5)
    ax.grid(axis="y",lw=.4,alpha=.3)


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    allrows=pd.read_csv(RESULTS/"logical_positions.csv")
    df=allrows.query("comparison=='main'").copy()
    if "SAFE_J" not in df: df["SAFE_J"]=np.nan
    valid=df.loc[df.status=="SAFE"].copy()
    paired=pd.read_csv(RESULTS/"paired_savings.csv")
    summary=(df.groupby(["case","method"],sort=False)["SAFE_J"].agg(["count","median","min","max"]).reset_index())
    summary.to_csv(RESULTS/"main_summary.csv",index=False,lineterminator="\n")
    (paired.groupby(["case","baseline"],sort=False)["savings_pct"].agg(["count","median","min","max"])
       .reset_index().to_csv(RESULTS/"paired_summary.csv",index=False,lineterminator="\n"))
    for which,data,methods,colname,measure,labels in [
        ("01_safe_energy",df,M,"method","SAFE_J","完整 SAFE 能耗（J）"),
        ("02_paired_savings",paired,M[:-1],"baseline","savings_pct","配对节能率（%）")]:
        fig,axes=plt.subplots(3,2,figsize=(7.3,7.2),layout="constrained")
        for case,ax in zip(CASES,axes.flat):
            for i,m in enumerate(methods):
                block=data[(data["case"]==case)&(data[colname]==m)]
                interval(ax,i,block[measure],COL[i],MARK[i])
            columns(ax,SHORT[:len(methods)])
            ax.set_title(case,loc="left",fontsize=10)
            ax.set_ylabel(labels)
            if measure=="savings_pct": ax.axhline(0,color=".5",lw=.6)
        export(fig,which,data)
    abl=allrows[(allrows.comparison!="thermal")&allrows.method.isin(["Compact","AB","Proposed"])&
                allrows.case.isin(CASES[:4])].copy()
    for k in ("config_gain_J","post_gain_J"):
        if k not in abl: abl[k]=np.nan
    abl["total_gain_mJ"]=1000*(abl["config_gain_J"]+abl["post_gain_J"])
    fig,axes=plt.subplots(2,2,figsize=(7.1,4.7),layout="constrained")
    for case,ax in zip(CASES[:4],axes.flat):
        for i,seed in enumerate(SEEDS):
            block=abl[(abl.case==case)&(abl.seed==seed)].set_index("method").reindex(["Compact","AB","Proposed"])
            y=block.total_gain_mJ.where(block.status=="SAFE")
            ax.plot(range(3),y,marker=MARK[i],ls=["-","--",":"][i],lw=1,color=COL[i],label=str(seed))
        columns(ax,["Compact","AB","Proposed"])
        ax.set_ylabel("相对初解节能（mJ）")
        ax.set_title(case,loc="left",fontsize=10)
    axes.flat[0].legend(frameon=False,ncol=3,fontsize=8)
    export(fig,"03_ablation",abl)
    for ext in ("svg","png"):
        shutil.copyfile(HERE/"figure4"/("capacity_exchange."+ext),FIG/("04_capacity_exchange."+ext))
    for p in (HERE/"figure4").glob("*.csv"):
        shutil.copyfile(p,FIG/("04_"+p.name))
    fig,axes=plt.subplots(3,2,figsize=(7.3,7.0),layout="constrained")
    parts=["activity_J","residency_J","switch_J","temperature_J","public_J"]
    partcolors=["#527c93","#94adb1","#956746","#d4ab78","#d8d9dc"]
    data=[]
    for case,ax in zip(CASES,axes.flat):
        for i,m in enumerate(M):
            cell=valid[(valid.case==case)&(valid.method==m)].sort_values(["SAFE_J","seed"])
            if cell.empty:
                ax.text(i,.04,"缺",ha="center",transform=ax.get_xaxis_transform())
                continue
            # Use a real, lower-median endpoint for even counts so the parts add to a real total.
            row=cell.iloc[(len(cell)-1)//2]
            base=0
            for j,col in enumerate(parts):
                ax.bar(i,row[col],bottom=base,width=.68,color=partcolors[j],edgecolor="white",linewidth=.2)
                base+=row[col]
            data.append({k:row[k] for k in ["case","method","seed","plan","SAFE_J",*parts]})
        columns(ax,SHORT)
        ax.set_ylim(bottom=0)
        ax.set_ylabel("完整能耗（J）")
        ax.set_title(case,loc="left",fontsize=10)
    fig.legend(handles=[plt.Rectangle((0,0),1,1,color=c,label=l) for c,l in zip(partcolors,["活动","驻留","调频","温度修正","公共"])],
               loc="outside upper center",ncol=5,frameon=False)
    export(fig,"05_components",pd.DataFrame(data))
    sizes=pd.read_csv(HERE/"full_domain_bounds.csv").set_index("case").requests
    df["per_request_mJ"]=1000*df.SAFE_J/df.case.map(sizes)
    fig,ax=plt.subplots(figsize=(7.3,3.8),layout="constrained")
    for i,m in enumerate(M):
        for j,c in enumerate(CASES):
            sub=df[(df.case==c)&(df.method==m)].per_request_mJ.dropna()
            if len(sub):
                x=j+(i-3)*.10
                ax.vlines(x,sub.min(),sub.max(),color=COL[i],lw=1)
                ax.scatter(x,sub.median(),color=COL[i],marker=MARK[i],s=24,label=SHORT[i] if j==0 else None)
    ax.set_xticks(range(6),[f"{c}\n{sizes[c]} 请求" for c in CASES])
    ax.set_ylabel("每请求完整能耗（mJ）")
    ax.legend(handles=[Line2D([],[],marker=m,ls="",color=c,label=l) for m,c,l in zip(MARK,COL,SHORT)],ncol=4,frameon=False)
    export(fig,"06_workloads",df)
    th=allrows[allrows.comparison=="thermal"].copy()
    fig,axes=plt.subplots(3,3,figsize=(7.4,6.7),layout="constrained")
    for j,c in enumerate(THERMAL):
        axes[0,j].set_title(c)
        for i,mode in enumerate(MODES):
            cell=th[(th.case==c)&(th["mode"]==mode)]
            assert len(cell)==3
            for k,col in enumerate(("actual_J","peak_hi")):
                ax=axes[k,j]
                for offset,(_,r) in zip((-.12,0,.12),cell.sort_values("seed").iterrows()):
                    if r.status in ("SAFE","HOT"):
                        ax.scatter(i+offset,r[col],color=COL[i],marker="x" if r.status=="HOT" else "o",s=16)
                n=cell.status.isin(["SAFE","HOT"]).sum()
                if n<3: ax.text(i,.02,f"{n}/3",transform=ax.get_xaxis_transform(),ha="center",fontsize=7)
            n=sum(cell.status=="SAFE")
            axes[2,j].bar(i,100*n/3,color=COL[i],width=.56)
            axes[2,j].text(i,max(3,100*n/3-13),f"{n}/3",color="white" if n else ".3",ha="center",fontsize=8)
        for ax in axes[:,j]: columns(ax,MODES)
        axes[1,j].axhline(80,color="#99596b",ls=":",lw=.9)
        axes[2,j].set_ylim(0,104)
    for ax,label in zip(axes[:,0],["连续能耗（J）","峰温上界（°C）","实际 SAFE（%）"]): ax.set_ylabel(label)
    export(fig,"07_thermal_outcomes",th)
    trace=pd.read_csv(RESULTS/"temperature_trace.csv")
    fig,axes=plt.subplots(2,2,figsize=(7.1,4.6),layout="constrained")
    for ax,node in zip(axes.flat,("CPU1","CPU2","GPU","NPU")):
        for mode,style,c,label in (("continuous","-","#186966","连续"),("reset","--","#99596b","场景重置")):
            if trace.empty: continue
            t=trace[trace.evaluation==mode]
            x=t[["start_tick","end_tick"]].to_numpy().ravel()/10000
            y=t[[node+"_start_C",node+"_end_C"]].to_numpy().ravel()
            ax.plot(x,y,ls=style,color=c,label=label,lw=1.15)
            for b in t.loc[t.boundary==1,"start_tick"]:
                ax.axvline(b/10000,color=".7",ls=":",lw=.6)
        ax.set(title=node,xlabel="执行时间（s）",ylabel="温度（°C）")
    if trace.empty: axes.flat[0].text(.3,.5,"无完整 T2 排程")
    else: axes.flat[0].legend(frameon=False)
    export(fig,"08_temperature_trace",trace)
    q=pd.read_csv(RESULTS/"quality.csv").set_index("case").reindex(CASES).reset_index()
    fig,(ax,bx)=plt.subplots(1,2,figsize=(7.2,3.3),layout="constrained")
    for i,r in q.iterrows():
        ax.scatter(r.lower_J,i,marker="|",s=100,color="#354b5c")
        if pd.notna(r.best_SAFE_upper_J):
            ax.plot([r.lower_J,r.best_SAFE_upper_J],[i,i],color="#729092",lw=1.4)
            ax.scatter(r.best_SAFE_upper_J,i,color="#206b68",s=24)
            bx.scatter(r.gap_pct_of_upper,i,color="#206b68",s=24)
        else:
            bx.text(.04,i,"无 SAFE 终点",transform=bx.get_yaxis_transform(),va="center")
    for a in (ax,bx):
        a.set_yticks(range(6),CASES)
        a.invert_yaxis()
    fig.legend(handles=[Line2D([],[],marker="|",color="#354b5c",ls="",label="全域下界"),Line2D([],[],marker="o",color="#206b68",ls="",label="最佳 SAFE 上端")],loc="outside upper center",ncol=2,frameon=False)
    ax.set_xlabel("完整能耗（J）")
    bx.set_xlabel("差距占最佳 SAFE 上端（%）")
    export(fig,"09_quality",q)


if __name__=="__main__":
    main()
