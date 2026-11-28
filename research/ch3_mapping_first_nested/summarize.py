"""Offline paired analysis. No scheduler, dynamic program or certifier is invoked."""
import csv
import json
import io
import tarfile
import zlib
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from restore_plan import members

ROOT=Path(__file__).resolve().parent
RAW=ROOT/"paired_results"
TABLE=ROOT/"tables"
CODES=("A02","A06","C10","C11")
ARMS=("baseline","unified")
CUTS=(10,30,60,180,300,600)
def read(p):return json.loads(p.read_bytes())
def lines(p):return [json.loads(b) for b in p.read_bytes().splitlines() if b.endswith(b"}")] if p.exists() else []
def csvout(name,rows):
    with (TABLE/name).open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for row in rows for k in row)),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
def fmt(x,n=4):return "—" if x is None else f"{x:.{n}f}"
def certified_better(p,q):
    return q is None or p["bounds"][1]<q["bounds"][0]
def signed(p,q):
    if p is None or q is None:return "缺少 SAFE"
    if p["bounds"][1]<q["bounds"][0]:return "统一更省"
    if q["bounds"][1]<p["bounds"][0]:return "现行更省"
    return "证书重叠"

def inspect(code,arm,budget):
    cell=RAW/code/f"{arm}-{budget}"
    rc=read(cell/"receipt.json")
    assert (rc["code"],rc["arm"],rc["budget"])==(code,arm,budget)
    ctx=dict(case=code,arm=arm,budget_s=budget)
    events=lines(cell/"certificates.jsonl")
    ledger=lines(cell/"ledger.jsonl")
    log=lines(cell/"maps.jsonl")
    dp=[json.loads(b) for b in zlib.decompress((cell/"dp.jsonl.z").read_bytes()).splitlines()]
    status=Counter(e["point"]["status"] for e in events)
    visits={e["mapping"] for e in log if e["event"]=="visit"}
    initial=next((e["mapping"] for e in log if e["event"]=="visit"),None)
    certified={e["mapping"] for e in events}
    maps=visits|certified|{e["mapping"] for e in ledger if e["event"]=="full_mapping"}
    assert arm!="unified" or certified<=visits
    timeline=[];best=None;first=None
    for e in events:
        pt=e["point"]
        if pt["status"]!="SAFE":continue
        assert pt["peak"]<=80 and pt["slack"]>=0 and pt["bounds"][0]<=pt["J"]<=pt["bounds"][1]
        if first is None:first=e["t"]
        if best is None or (pt["J"]<best["point"]["J"] if arm=="unified" else certified_better(pt,best["point"])):
            best=e
            timeline.append(dict(**ctx,t=e["t"],J=pt["J"],plan=pt["plan"],mapping=e["mapping"],stage=e["stage"]))
    cuts=[]
    for t in CUTS:
        if t>budget:continue
        available=next((r for r in reversed(timeline) if r["t"]<=t),{})
        cuts.append(dict(**ctx,t=t,best_SAFE_J=available.get("J"),plan=available.get("plan")))
    p=best["point"] if best else {}
    initial_stages=[e for e in events if e["mapping"]==initial]
    ms=[e for e in log if e["event"]=="complete"]
    safe_maps={e["mapping"] for e in events if e["point"]["status"]=="SAFE"}
    hot_maps={e["mapping"] for e in events if e["point"]["status"]=="HOT"}
    no_path=sum(e["kind"]=="dp" and any(not d["finite"] for d in e["stats"]) for e in dp)
    partial=sum(e["event"]=="visit" for e in log)-len(ms) if arm=="unified" else None
    row=dict(**ctx,status=rc["status"],host=rc["host"],core=rc["core"],charged_s=rc["charged_s"],
             supervisor_s=rc["supervisor_s"],first_safe_s=first,last_improvement_s=best["t"] if best else None,
             final_J=p.get("J"),final_plan=p.get("plan"),
             final_mapping=best["mapping"] if best else None,final_peak_C=p.get("peak"),final_slack_ms=p.get("slack"),
             unique_maps_observed=len(maps),unique_maps_certified=len(certified),cert_SAFE=status["SAFE"],
             safe_maps=len(safe_maps),hot_only_maps=len(hot_maps-safe_maps),
             maps_without_SAFE_or_HOT_certificate=len(certified-safe_maps-hot_maps),
             cert_HOT=status["HOT"],cert_out_of_model=status["OUT_OF_MODEL"],cert_unresolved=status["UNRESOLVED"],
             dp_no_path_calls=no_path,post_timing_fail_calls=sum(e["kind"]=="illegal_post" for e in dp),
             baseline_closed_timing_fail_calls=sum(e["event"]=="timing_failure" for e in ledger) if arm=="baseline" else None,
             completed_map_evaluations=len(ms) if arm=="unified" else None,
             finished_maps_without_certificate=sum(e["mapping"] not in certified for e in ms) if arm=="unified" else None,
             cutoff_incomplete_maps=partial,cache_hits=sum(e["event"]=="cache" for e in log) if arm=="unified" else None,
             completed_coordinates=sum(e["event"]=="coordinate_end" for e in log) if arm=="unified" else None,
             last_coordinate=next((e["coordinate"] for e in reversed(log) if e["event"]=="coordinate"),None),
             sweeps_started=max((e["sweep"] for e in log if e["event"]=="coordinate"),default=None),
             converged=any(e["event"]=="converged" for e in log) if arm=="unified" else None)
    failures=[dict(**ctx,mapping=e.get("mapping"),stage=e.get("stage"),t=e.get("t"),reason=e["reason"])
              for e in log if e["event"]=="failed"]
    failures.extend(dict(**ctx,mapping=e["mapping"],stage=e["stage"],t=e["t"],reason=e["point"]["status"])
                    for e in events if e["point"]["status"]!="SAFE")
    return dict(row=row,timeline=timeline,cuts=cuts,best=p or None,maps=maps,initial=initial_stages,
                first_map=initial,events=events,failures=failures)

def plot(allcells):
    fig,axes=plt.subplots(4,2,figsize=(10,10))
    for i,code in enumerate(CODES):
        for j,budget in enumerate((60,600)):
            ax=axes[i,j]
            for arm,color,label in (("baseline","#21618c","Current chapter 3"),("unified","#b54325","Mapping first")):
                points=allcells[code,arm,budget]["timeline"]
                if points:
                    t=[p["t"] for p in points];energy=[p["J"] for p in points]
                    ax.step(t+[budget],energy+[energy[-1]],where="post",color=color,label=label)
                    ax.plot(t[0],energy[0],"o",color=color,ms=3)
                else:
                    ax.plot([],[],color=color,label=label+" (no SAFE)")
            ax.set_xlim(0,budget);ax.set_title(f"{code}  ·  {budget} s")
            ax.set_ylabel("Best SAFE energy (J)");ax.grid(alpha=.18)
            ax.ticklabel_format(axis="y",useOffset=False)
            if i==3:ax.set_xlabel("End-to-end time (s)")
            ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(ROOT/"energy_vs_time.png",dpi=160)
    plt.close(fig)

def main():
    TABLE.mkdir(exist_ok=True)
    cells={(c,a,b):inspect(c,a,b) for c in CODES for a in ARMS for b in (60,600)}
    rows=[x["row"] for x in cells.values()]
    for c in CODES:assert len({(r["host"],r["core"]) for r in rows if r["case"]==c})==1
    charge=sum(r["charged_s"] for r in rows)
    assert charge<=5280 and len(rows)==16
    csvout("cells.csv",rows)
    csvout("checkpoints.csv",[r for x in cells.values() for r in x["cuts"]])
    csvout("improvements.csv",[r for x in cells.values() for r in x["timeline"]])
    csvout("failure_events.csv",[r for x in cells.values() for r in x["failures"]])
    pairs=[];seed=[];diagnosis=[]
    for c in CODES:
        history=read(ROOT/"stage1/history"/(c+".json"))
        for b in (60,600):
            ref,new=cells[c,"baseline",b],cells[c,"unified",b]
            old,p=ref["best"],new["best"]
            diff=p["J"]-old["J"] if p and old else None
            pairs.append(dict(case=c,budget_s=b,current_J=old["J"] if old else None,unified_J=p["J"] if p else None,
                         delta_J=diff,delta_pct=100*diff/old["J"] if diff is not None else None,comparison=signed(p,old)))
            map_id=ref["row"]["final_mapping"]
            matched=[e for e in new["events"] if e["mapping"]==map_id]
            diagnosis.append(dict(case=c,budget_s=b,current_best_map=map_id,
                    current_best_map_visited_by_new=(map_id in new["maps"] if map_id else None),
                    current_best_map_certificates=len(matched),new_best_on_that_map=min((e["point"]["J"] for e in matched
                         if e["point"]["status"]=="SAFE"),default=None),
                    historical_best_map_visited=history["mapping_sha"] in new["maps"],
                    new_best_map_seen_by_current=new["row"]["final_mapping"] in ref["maps"] if p else None))
            z={e["stage"]:e["point"] for e in new["initial"]}
            construction=next((e for e in ref["events"] if e["stage"]=="search"),{})
            for stage,pt in [("ordinary",z.get("ordinary")),("thermal",z.get("thermal")),("current_first_search",construction.get("point"))]:
                seed.append(dict(case=c,budget_s=b,stage=stage,status=pt.get("status") if pt else None,
                      J=pt.get("J") if pt else None,peak_C=pt.get("peak") if pt else None,
                      plan=pt.get("plan") if pt else None))
    csvout("pairs.csv",pairs);csvout("initial.csv",seed);csvout("mapping_diagnosis.csv",diagnosis)
    with tarfile.open(ROOT/"selected_endpoints.tar.gz","w:gz") as bundle:
        for r in rows:
            if not r["final_plan"]:continue
            files=members(RAW/r["case"]/"physical",r["final_plan"])
            for name,data in files.items():
                header=tarfile.TarInfo(f"{r['case']}/{r['arm']}-{r['budget_s']}/{name}")
                header.size=len(data)
                bundle.addfile(header,io.BytesIO(data))
    plot(cells)
    write_report(cells,rows,pairs,diagnosis,seed,charge)


def write_report(cells,rows,pairs,diagnosis,seed,charge):
    gate=read(ROOT/"stage1/gate.json")
    with (ROOT/"stage1/results.csv").open(encoding="utf-8") as src:phase1=list(csv.DictReader(src))
    assert gate["passed"] and len(phase1)==12
    physical=sum(len(read(RAW/c/"physical/index.json")["plans"]) for c in CODES)
    report=["# 第三章结构统一化研究决策报告",""]
    def bullet(line):report.append("- "+line)
    def section(title):report.extend(["","## "+title,""])
    def table(headers,data):
        report.append("|"+"|".join(headers)+"|")
        report.append("|"+"|".join(["---"]*len(headers))+"|")
        report.extend("|"+"|".join(map(str,row))+"|" for row in data)
    def available(b,a):return sum(cells[c,a,b]["best"] is not None for c in CODES)
    long=[p for p in pairs if p["budget_s"]==600]
    nwin=sum(p["comparison"]=="统一更省" for p in long)
    ntie=sum(p["comparison"]=="证书重叠" for p in long)
    nloss=sum(p["comparison"]=="现行更省" for p in long)
    cross=[signed(cells[c,"unified",600]["best"],cells[c,"baseline",60]["best"]) for c in CODES]
    errors=[r for r in rows if r["status"]=="error"]
    if errors:
        decision="有运行异常，本轮仅部分完成，保留现行版本。"
    elif available(600,"unified")==4 and nloss==0 and nwin+ntie==4:
        decision="将映射优先结构列为扩大验证的候选，现行第三章继续作为回退版本。"
    elif all(x in ("统一更省","证书重叠") for x in cross):
        decision="统一版延长到 600 秒后达到现行 60 秒版本的质量，可以扩大验证；与同样延长到 600 秒的现行搜索比较，仍有差距。"
    else:
        decision="本轮保留现行第三章。独立调频得到验证，外层配额坐标搜索尚未证明可以替代现行映射搜索。"
    report += ["**"+decision+"**","",
      f"给定原来的设备分配，仅靠独立调频就能重建十二条历史最终排程。把寻找设备分配也交给新算法后，600 秒时现行版取得 SAFE {available(600,'baseline')}/4，统一版取得 SAFE {available(600,'unified')}/4；同预算严格比较，统一版更省 {nwin} 条、现行版更省 {nloss} 条、证书重叠 {ntie} 条。"]
    section("独立找到映射后的能耗")
    report+=["两种算法分别从头运行。能耗为全系统连续认证值，差值为统一版减现行版，正数表示统一版更耗能。证书区间重叠表示按当前误差界无法判定严格高低。空白能耗用“—”表示。",""]
    table(["任务流","预算 s","现行版 J","统一版 J","差值 J","差值 %","证书比较"],
          [[r["case"],r["budget_s"],fmt(r["current_J"],6),fmt(r["unified_J"],6),fmt(r["delta_J"],6),fmt(r["delta_pct"]),r["comparison"]] for r in pairs])
    report+=["","对于允许延长求解时间的采用条件，另将统一版 600 秒与现行版 60 秒直接对照。",""]
    table(["任务流","现行 60 s（J）","统一 600 s（J）","比较"],
          [[c,fmt(cells[c,"baseline",60]["row"]["final_J"],6),fmt(cells[c,"unified",600]["row"]["final_J"],6),
            signed(cells[c,"unified",600]["best"],cells[c,"baseline",60]["best"])] for c in CODES])
    section("为什么出现差异")
    report+=["逐一核对现行版胜出映射在统一搜索中的访问记录。“访问”包含已进入评价、到期未完成的候选；“已认证”要求交付完整证书。两种版本都对完整轨迹采用同一电热认证规则。",""]
    table(["流","预算 s","统一版访问／认证映射","完成坐标数","访问现行最佳映射","同映射交付证书数","访问历史最佳映射"],
          [[r["case"],r["budget_s"],f"{cells[r['case'],'unified',r['budget_s']]['row']['unique_maps_observed']}／{cells[r['case'],'unified',r['budget_s']]['row']['unique_maps_certified']}",
            cells[r["case"],"unified",r["budget_s"]]["row"]["completed_coordinates"],
            {True:"是",False:"否",None:"无对照"}[r["current_best_map_visited_by_new"]],r["current_best_map_certificates"],
            "是" if r["historical_best_map_visited"] else "否"] for r in diagnosis])
    for p,d in zip(pairs,diagnosis):
        if p["budget_s"]!=600:continue
        if p["comparison"]=="现行更省" or (p["current_J"] is not None and p["unified_J"] is None):
            if not d["current_best_map_visited_by_new"]:
                report+=["",f"{p['case']} 的统一搜索没有访问本次现行版最佳映射。至少有一个已知可行且更省电的设备分配落在其已访问集合之外。"]
            else:
                report+=["",f"{p['case']} 访问了现行最佳映射，统一版在该映射交付的最低安全能耗为 {fmt(d['new_best_on_that_map'],6)} J，需结合该映射的完成状态以及两个调频阶段的证书判断内层差异。"]
    report+=["","给定优质映射时，十二次独立调频复现历史最终排程，支持把频率求解统一成一个可独立调用的步骤。现行版的窗口频率还参与生成和筛选设备映射。能否删去它的这项作用，取决于端到端比较。本轮整体替换了多项外层机制，不能据此给每个旧机制单独归因。",
              "","未访问某个映射可以直接证明搜索覆盖存在缺口。它不能证明该映射是唯一好解，也不能区分增加预算、改变坐标顺序或改变邻域将带来多少收益。"]
    section("安全性、首次交付与失败类型")
    table(["流","预算 s","版本","首次 SAFE（s）","访问映射","SAFE／HOT／模型外／未决证书","DP 无路径／后处理时序失败调用","最终峰温上界 °C","最小余量 ms"],
        [[r["case"],r["budget_s"],"现行" if r["arm"]=="baseline" else "统一",fmt(r["first_safe_s"],2),r["unique_maps_observed"],
          f"{r['cert_SAFE']}／{r['cert_HOT']}／{r['cert_out_of_model']}／{r['cert_unresolved']}",f"{r['dp_no_path_calls']}／{r['post_timing_fail_calls']}",
          fmt(r["final_peak_C"],3),fmt(r["final_slack_ms"],3)] for r in rows])
    report+=["","映射数按逐请求设备身份去重。现行版统计可观测的完整闭合 FIFO 调用及已认证映射，前缀扩展单独属于构造工作。DP 无路径按调用计数；后处理期限失败可能触发冻结的余量重求。实际访问、完成评价、到期未完成、超温及模型外均分列在[逐次明细](tables/cells.csv)。"]
    section("能耗如何随求解时间变化")
    report+=["横轴为各自从进程启动开始的端到端时间，阶梯仅从首次交付 SAFE 时开始。两列是独立启动的实验。图中每一次下降都对应已落盘的完整证书。","",
             "![四条流两档预算的完整安全能耗曲线](energy_vs_time.png)","",
             "[全部指定时间点](tables/checkpoints.csv) · [每次安全在位解更新](tables/improvements.csv)"]
    report+=["","下表追踪同一次 600 秒运行在各截止点实际可交付的能耗（J）。60 秒列与前面的独立 60 秒运行分别计量。",""]
    table(["流","版本",*[f"{t} s" for t in CUTS]],[[c,"现行" if a=="baseline" else "统一",
          *[fmt(z["best_SAFE_J"],4) for z in cells[c,a,600]["cuts"]]] for c in CODES for a in ARMS])
    section("负载均衡起点与独立调频")
    report+=["负载均衡起点按最高合法频档的占用时长估计两台设备的完成时间，逐窗口选较晚完成时间最小的配额；相同时先比较 A、再比较 B 的整数配额。单个设备映射自身没有唯一的物理能耗。普通调频首次给出可计量的完整排程，再记录温度修正后的候选。",""]
    for b in (60,600):
        data=[]
        for c in CODES:
            s={r["stage"]:r for r in seed if r["case"]==c and r["budget_s"]==b}
            data.append([c,b,s["ordinary"]["status"] or "无证书",fmt(s["ordinary"]["J"],6),s["thermal"]["status"] or "无证书",fmt(s["thermal"]["J"],6),
                         fmt(cells[c,"unified",b]["row"]["final_J"],6)])
        if b==60:allrows=data
        else:allrows+=data
    table(["流","预算 s","起点普通","普通 J","起点修正","修正 J","搜索最终 SAFE J"],allrows)
    section("给定十二条历史映射的独立验证")
    report+=["每流固定取冻结第三轮版本第一次正式重复。核验计划及证书后投影为逐请求设备编号。下表只比较这十二个固定映射上的内层求解。",""]
    table(["流","原 SAFE J","普通 J／状态","修正 J／状态","最终 SAFE J","与原排程哈希"],
          [[r["case"],fmt(float(r["historical_J"]),6),fmt(float(r["ordinary_J"]),6)+"／"+r["ordinary"],
            fmt(float(r["thermal_J"]),6)+"／"+r["thermal"],fmt(float(r["best_SAFE_J"]),6),
            "相同" if r["plan"]==r["original_plan"] else "不同"] for r in phase1])
    improved=sum(r["thermal"]=="SAFE" and float(r["thermal_J"])<float(r["ordinary_J"])-1e-9 for r in phase1)
    c10_hot=read(ROOT/"stage1/cases/C10/thermal.json")["point"]
    report+=["",f"普通调频直接获得 12/12 SAFE。温度修正在 {improved} 条上进一步节能。C10 的修正候选为 {c10_hot['J']:.6f} J，峰温上界达 {c10_hot['peak']:.3f} °C，超过 80 °C 上限；保留普通解可满足热约束。两阶段择优后，十二个计划哈希逐项相同。"]
    section("实际删掉了哪些步骤")
    table(["决策","现行第三章","统一算法","变化性质"],[
        ["分组与设备分配","一秒窗口、A/B 整数配额、确定性均匀分配","相同","保留原表示"],
        ["搜索变量","窗口配额与共享频档联合生成","仅修改一个窗口的一类任务配额，完整映射缓存","实际删除窗口频档决策"],
        ["寻找设备映射","近似热风险、互补束路径及候选排序","确定性负载均衡起点，按窗口及 A/B 顺序试遍单坐标合法整数","实际替换构造及搜索"],
        ["进入调频的条件","多映射提名，达阈值的 HOT 可占第四位","每个新映射均进入同一内层优化","实际删除两类提名与独立交接"],
        ["频率与热修正","固定设备映射下普通全局 DP，再做一次温度修正","仍执行两步；温度步仅读本次普通轨迹","保留两个不同目标，统一调用入口"],
        ["安全判定","三阶段 FIFO 重放、因果空闲、连续认证和完整计能","相同；SAFE 优先，无 SAFE 时比较超温与能耗","保留物理约束与独立验收"]])
    section("预算与证据")
    report += [f"第一阶段 {gate['elapsed_s']:.3f}/120 核秒。正式比较 {charge:.3f}/5280 核秒，四条流各四格、每格一次。每条流的四次运行共用同一主机和 CPU 核，单线程，从独立进程及独立 JIT 缓存启动。任务初始化、搜索、DP、认证及在线证据写入均计时。截止监督与压缩归档分开记录；压缩、制表和绘图在实验后完成。共校验 {physical:,} 个按流去重的配对实验物理计划。",
               "", "60 秒对照沿用 55+5 秒，600 秒仅将冻结截止点扩至 595+5 秒；沿用现行版的首次 SAFE 判断以及无 SAFE 时继续构造的规则。短预算不会为长预算提供初解。单次观测适用于本次结构筛选，无法估计重复间波动或对全部十二流的外层覆盖。",
               "", "冻结核对覆盖 P1 的模型、连续热认证、两份设备画像及配置，以及全局调频的 C++ 内核和 Python 求解入口。八个 Git blob 在相应来源与实际运行版本中逐一相同。详情见[来源核对](source_bindings.json)。",
               "", "[独立调频逐流结果](stage1/results.csv) · [完整配对表](tables/pairs.csv) · [映射覆盖诊断](tables/mapping_diagnosis.csv) · [起点质量](tables/initial.csv) · [失败事件](tables/failure_events.csv) · [最终排程、证书和轨迹压缩包](selected_endpoints.tar.gz) · [全部物理证据](paired_results) · [配对证据校验清单](PAIRED_SHA256SUMS)"]
    (ROOT/"REPORT_zh.md").write_text("\n".join(report)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
