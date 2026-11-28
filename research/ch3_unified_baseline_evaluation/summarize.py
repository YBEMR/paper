"""Audit physical evidence, compute within-flow medians and generate all plots offline."""
import csv
import gzip
import json
import statistics as st
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_integrated_quality_v1"))
import audit as q
import evidence as ev
ev.ROOT=ROOT
ARC=ROOT/"archive";TAB=ROOT/"tables";FIG=ROOT/"figures"
ARMS=("Proposed","Zhou-P1","Li-P1","GA","C2","ZQ","LQ")
CUTS=(10,30,60)
def table(name,rows):
    with (TAB/(name+".csv")).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def fmt(x,n=3):return "—" if x is None else f"{x:.{n}f}"
def mean(v):return st.mean(v) if v else None
def median(v):return st.median(v) if v else None
def auditcell(folder,rep,arm,env,certs):
    d=folder/f"r{rep}-{arm}";rc=ev.read(d/"receipt.json")
    assert rc["host"]==env["warm"]["host"] and rc["cpu"]==env["warm"]["core"] and rc["version"]==("hot" if arm=="Proposed" else arm)
    sc=ev.logs(d/"search.jsonl");rf=ev.logs(d/"refine.jsonl")
    cut=rc["cut"];end=rc["charged_s"];assert 0<end<=60 and rc["limit"]==60
    seq=sorted([e for ee,t in ((sc,cut),(rf,60)) for e in ee if e["event"]=="certificate" and e["t"]<=t],key=lambda e:e["t"])
    current=None;curve=[];times={};ctx=dict(case=folder.name,method=arm,rep=rep)
    for e in seq:
        p=e["point"];q.checked(p,certs)
        assert abs(sum(p["energy"].values())-p["J"])<1e-7
        if q.better(p,current):
            current=p;curve.append(dict(**ctx,t=e["t"],**q.describe(p)))
    for t in CUTS:times[t]=q.incumbent([e for e in seq if e["t"]<=t])
    nat=next((e for e in reversed(sc) if e["event"]=="natural"),{})
    stats=nat.get("result",{});counts=Counter(e["point"]["status"] for e in seq)
    if current:reason="SAFE"
    elif stats.get("missing_stages") or stats.get("stats",{}).get("failed_window"):reason="NO_CONSTRUCTION"
    elif counts:reason=",".join(sorted(counts))
    elif rc["search_rc"]["rc"]!=0:reason="TIMEOUT_NO_DELIVERY"
    else:reason=stats.get("stop","NO_CONSTRUCTION")
    sx=min(cut,rc["search_rc"]["supervisor_t"]);sp=q.spans
    inst=sp(sc,"instance",sx);construct=sp(sc,"construct",sx);cert=sp(sc,"search_cert",sx)
    op=sp(sc,"optimization",sx);setup=sp(sc,"ga_setup",sx)
    # GA search contains its certificate calls; remove them from its exclusive allocation.
    ga0=next((e["t"] for e in sc if e.get("task")=="ga_search"),None)
    ga=sp(sc,"ga_search",sx)-sp([e for e in sc if ga0 is not None and e["t"]>=ga0],"search_cert",sx)
    dp=sum(e["elapsed_s"] for p in d.glob("map*/events.jsonl") for e in ev.logs(p) if e["kind"]=="dp" and e["t"]<=60)
    sel=sp(rf,"selection",end);handoff=sp(rf,"handoff",end);dp_cert=sp(rf,"dp_cert",end)
    other=end-sum((inst,construct,cert,op,setup,ga,dp,sel,handoff,dp_cert))
    assert other>=-.03,(ctx,other)
    row=dict(**ctx,requests=env["count"],time_s=end,supervisor_s=rc["wall_including_supervision"],first_safe_s=curve[0]["t"] if curve else None,
        final_best_s=curve[-1]["t"] if curve else None,reason=reason,stop=stats.get("stop") or stats.get("final_status"),
        cutoff_or_interrupt=rc["search_rc"]["rc"]!=0 or bool((rc.get("refine_rc") or {}).get("rc")),certificates=len(seq),
        cert_status_counts=json.dumps(counts),stats=json.dumps(stats.get("stats",{})),missing_stages=stats.get("missing_stages"),
        host=rc["host"],core=rc["cpu"],source=rc["source"],instance_s=inst,construct_s=construct,search_replay_cert_write_s=cert,
        local_optimization_s=op,ga_setup_s=setup,ga_search_repair_s=ga,dp_s=dp,selection_s=sel,handoff_s=handoff,
        dp_cert_write_s=dp_cert,unallocated_s=other,**q.describe(current))
    return row,curve,times
def figures(cells,med,summary):
    colors=plt.get_cmap("tab10").colors
    fig,axes=plt.subplots(3,4,figsize=(15,9),sharex=True)
    plotrows=[];dist={};extra=[]
    for ax,c in zip(axes.flat,sorted(cells)):
        for j,a in enumerate(ARMS):
            rr=[r for r in summary if r["case"]==c and r["method"]==a]
            xx=sorted({0.,10.,30.,60.,*[v["t"] for i in (1,2,3) for v in cells[c][i,a][1]]})
            yy=[]
            for x in xx:
                vals=[next((s["J"] for s in reversed(cells[c][i,a][1]) if s["t"]<=x),None) for i in (1,2,3)]
                vs=[v for v in vals if v is not None];y=median(vs) if len(vs)>=2 else None
                yy.append(np.nan if y is None else y);plotrows.append(dict(case=c,method=a,t=x,reliable_J=y,safe=len(vs)))
            ax.step(xx,yy,where="post",label=a,color=colors[j],lw=1.2,ls="--" if j>=5 else "-")
        ax.set_title(c);ax.grid(alpha=.18);ax.set(xlim=(0,60),xlabel="Solver time (s)",ylabel="SAFE energy (J)")
    fig.legend(*axes.flat[0].get_legend_handles_labels(),loc="upper center",ncol=7)
    fig.tight_layout(rect=(0,0,1,.95));fig.savefig(FIG/"energy_time.png",dpi=160);plt.close(fig)
    table("energy_time",plotrows)
    for case in ("A02","C10"):
        fig,axes=plt.subplots(2,1,figsize=(8.5,7));bottom=np.zeros(len(ARMS));valid=[]
        with tempfile.TemporaryDirectory() as tmp:
            for i,a in enumerate(ARMS):
                ps=[r for r in summary if r["case"]==case and r["method"]==a and r["status"]=="SAFE"]
                if not ps:continue
                r=min(ps,key=lambda p:(abs(p["J"]-median([v["J"] for v in ps])),p["rep"]))
                folder=Path(tmp)/a;ev.restore(case,r["plan"],folder)
                with np.load(folder/"trace.npz") as h:tr=h["events"]
                axes[0].step(tr[:,1]/10000,np.max(tr[:,22:26],axis=1),where="pre",label=a,color=colors[i])
                with gzip.open(TAB/f"temperature_{case}_{a}.csv.gz","wt") as h:
                    np.savetxt(h,tr[:,[0,1,22,23,24,25]],delimiter=",",header="start_tick,end_tick,cpu0_upper_C,cpu1_upper_C,gpu_upper_C,npu_upper_C",comments="")
                valid.append((i,r))
                extra.append(dict(case=case,method=a,rep=r["rep"],plan=r["plan"],**{k:r[k] for k in ("J","base_J","activity_J","temperature_J","switch_J","external_J")}))
        for k in ("base_J","activity_J","switch_J","temperature_J","external_J"):
            vals=np.full(len(ARMS),np.nan)
            for i,r in valid:vals[i]=r[k]
            axes[1].bar(ARMS,vals,bottom=bottom,label=k);bottom+=np.nan_to_num(vals)
        axes[0].axhline(80,ls=":",color="black");axes[0].set(xlabel="Physical time (s)",ylabel="Peak upper bound (°C)")
        axes[1].set_ylabel("Energy (J)");axes[1].tick_params(axis="x",labelrotation=20)
        for ax in axes:ax.legend(fontsize=8,ncol=3);ax.grid(axis="y",alpha=.2)
        fig.suptitle(case);fig.tight_layout();fig.savefig(FIG/(case+".png"),dpi=160);plt.close(fig)
    table("representative_energy",extra)
def main():
    t0=time.perf_counter();TAB.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True)
    cells={};rows=[];curves=[];med={};endpoints=[];flows=[];pairs=[];physical=0
    for p in sorted(ARC.glob("*/lane.json")):
        folder=p.parent;c=folder.name;env=ev.read(p)
        ev.verify(folder/"physical");certs=q.certified_members(folder/"physical");physical+=len(certs)
        assert set(map(tuple,env["order"]))=={(i,a) for a in ARMS for i in (1,2,3)} and len(env["order"])==21
        cells[c]={}
        for i,a in env["order"]:
            r,curve,times=auditcell(folder,i,a,env,certs);cells[c][i,a]=r,curve,times;rows.append(r);curves+=curve
            for t,pt in times.items():endpoints.append(dict(case=c,rep=i,method=a,t=t,**q.describe(pt)))
        for a in ARMS:
            for t in CUTS:
                vals=[cells[c][i,a][2][t] for i in (1,2,3)];n=sum(q.safe(p) for p in vals);mp=q.summarize(vals)
                med[c,a,t]=(n,mp);flows.append(dict(case=c,method=a,t=t,requests=env["count"],safe=n,reliable=n>=2,J=q.J(mp),bounds=mp["bounds"] if mp else None))
        for a in ARMS[1:]:
            for t in CUTS:
                n,x=med[c,"Proposed",t];k,y=med[c,a,t];ok=min(n,k)>=2
                pairs.append(dict(case=c,baseline=a,t=t,proposed_safe=n,baseline_safe=k,proposed_J=q.J(x),baseline_J=q.J(y),
                    outcome=q.outcome(x,y) if ok else "unpaired",gain_pct=100*(y["J"]-x["J"])/y["J"] if ok else None))
    assert len(rows)==252 and len(cells)==12 and len({r["source"] for r in rows})==1
    total=sum(r["time_s"] for r in rows);assert total<=15120
    for n,rr in (("runs",rows),("endpoints",endpoints),("flows",flows),("pairs",pairs),("improvements",curves)):table(n,rr)
    figures(cells,med,rows)
    totals=[]
    for a in ARMS[1:]:
        for t in CUTS:
            pp=[r for r in pairs if r["baseline"]==a and r["t"]==t];ss=[r for r in pp if r["gain_pct"] is not None];counts=Counter(r["outcome"] for r in ss)
            totals.append(dict(baseline=a,t=t,paired=len(ss),gain_pct=mean([r["gain_pct"] for r in ss]),win=counts["win"],tie=counts["tie"],loss=counts["loss"],
                proposed_only=sum(r["proposed_safe"]>=2>r["baseline_safe"] for r in pp),baseline_only=sum(r["baseline_safe"]>=2>r["proposed_safe"] for r in pp),
                neither=sum(max(r["proposed_safe"],r["baseline_safe"])<2 for r in pp)))
    table("comparison",totals)
    txt=["# 第三章完整算法的统一性能比较","",f"七种方法各自从空开始，每个单元最多 60 秒。主比较 180 次、辅助比较 72 次。实际合计 {total:.3f}／15120 核秒。按流去重核验 {physical:,} 份完整物理排程、证书及 31 列温度轨迹。","",
    "## 安全覆盖与求解时间","","| 方法 | SAFE 次数／36 | 可靠流／12 | 三次全成功流 | 首次 SAFE 中位秒（成功运行） | 实际结束中位秒（全部运行） |","|---|---:|---:|---:|---:|---:|"]
    coverage=[]
    for a in ARMS:
        rr=[r for r in rows if r["method"]==a];success=[r for r in rr if r["status"]=="SAFE"]
        n=sum(med[c,a,60][0]>=2 for c in cells);all3=sum(med[c,a,60][0]==3 for c in cells)
        ts=median([r["first_safe_s"] for r in success]);end=median([r["time_s"] for r in rr])
        coverage.append(dict(method=a,success=len(success),reliable=n,all_three=all3,median_first_s=ts,median_end_s=end,reasons=dict(Counter(r["reason"] for r in rr))))
        txt.append(f"| {a} | {len(success)} | {n} | {all3} | {fmt(ts)} | {fmt(end)} |")
    table("coverage",coverage)
    txt+=["","## 完整安全能耗的配对比较","","先取每流成功重复的能耗中位数，双方均至少两次 SAFE 才进行配对。按逐流节能率等权平均，分母为相应基线。区间重叠记平，仅单侧成功时能耗差留空。","",
          "| 基线 | 配对流数 | Proposed 平均节能率 % | 胜／平／负 | 仅 Proposed／仅基线可靠 |","|---|---:|---:|---:|---:|"]
    for r in totals:
        if r["t"]==60:txt.append(f"| {r['baseline']} | {r['paired']} | {fmt(r['gain_pct'],4)} | {r['win']}／{r['tie']}／{r['loss']} | {r['proposed_only']}／{r['baseline_only']} |")
    txt+=["","Zhou-P1 与 Li-P1 在可用物理设备、CPU 频档和真实时间空档中逐任务安排三个阶段。ZQ 与 LQ 共享窗口配额生成器并只保留一个前缀，辅助成绩只代表这些窗口适配。GA 用本次 C2 首份 SAFE 启动；当没有安全初解，遗传算子无法进入工作阶段。不同自由度、构造器和求解策略共同影响结果。","",
    "## 十二流 60 秒能耗中位数（J）","","| 任务流 | "+" | ".join(ARMS)+" |","|---|"+"---:|"*7]
    for c in sorted(cells):txt.append("| "+c+" | "+" | ".join(fmt(q.J(med[c,a,60][1]),6) for a in ARMS)+" |")
    txt+=["","![同一轨迹截至各时刻的可靠安全能耗](figures/energy_time.png)","","曲线从该流该方法第二次重复取得安全解时开始显示，三次运行分别按各自的绝对时刻截取。提前结束后保留已交付解。缺线表示该时段可靠覆盖不足。","",
        "## 典型工况","","![A02 峰温上界与能耗组成](figures/A02.png)","","![C10 峰温上界与能耗组成](figures/C10.png)","","温度图显示各物理事件内四节点峰温上界的最大值。能耗图按原证书分解为频档驻留基值、计算活动增量、切换、温度修正和外部固定项。失败工况留空。","",
        "## 失败与适用范围",""]
    for rr in coverage:txt.append(f"- {rr['method']} 的逐次结果为 "+", ".join(f"{k} {v} 次" for k,v in rr["reasons"].items())+"。")
    for a in ARMS[1:]:
        losses=[p for p in pairs if p["t"]==60 and p["baseline"]==a and p["outcome"]=="loss"]
        if losses:txt+=["",f"相对 {a}，Proposed 的认证能耗严格较高的流为 "+", ".join(f"{p['case']}（{p['gain_pct']:.4f}%）" for p in losses)+"。比较只定位完整路线的差异，未通过消融分解来源。"]
    txt+=["",f"正式计算版本 `{rows[0]['source']}`。通用预热 {sum(ev.read(p)['warm']['seconds'] for p in ARC.glob('*/lane.json')):.3f} 秒，离线压缩 {sum(ev.read(p)['offline_s'] for p in ARC.glob('*/archive_receipt.json')):.3f} 秒。原始未完成构造（如有）在各单元 partial 目录，超时只记录已交付候选；工作进程结束和监督收尾分列。","",
    "[协议](PROTOCOL.md) · [逐流三截面](tables/flows.csv) · [逐次时间/证书/能耗分项](tables/runs.csv) · [各流配对](tables/pairs.csv) · [配对统计](tables/comparison.csv) · [绘图数据](tables) · [逐单元原始证据](archive) · [SHA-256](SHA256SUMS)",""]
    (ROOT/"REPORT_zh.md").write_text("\n".join(txt))
    (TAB/"receipt.json").write_text(json.dumps(dict(cells=len(rows),formal_core_s=total,physical=physical,analysis_s=time.perf_counter()-t0))+"\n")
if __name__=="__main__":main()
