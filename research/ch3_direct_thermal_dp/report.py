"""Summarize archived fixed-pool evaluations without invoking a solver or certificate."""
import csv
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from budget import CASES,OUT,ROOT

TABLE=ROOT/"tables"


def read(path):
    return json.loads(path.read_bytes())


def table(file, rows, headers):
    with (TABLE/file).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=headers,lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def winner(points):
    best=None
    for p in points:
        if p and p["status"]=="SAFE" and (best is None or p["bounds"][1]<best["bounds"][0]):
            best=p
    return best


def compare(x,y):
    if not x or not y:
        return None,None,"both_no_SAFE" if not x and not y else "lost_SAFE" if not x else "gained_SAFE"
    diff=x["J"]-y["J"]
    return diff,100*diff/y["J"],"lower" if x["bounds"][1]<y["bounds"][0] else "higher" if y["bounds"][1]<x["bounds"][0] else "overlap"


def fields(p):
    return dict(plan=p["plan"],status=p["status"],J=p["J"],low_J=p["bounds"][0],high_J=p["bounds"][1],E35_J=p["e35"],
                temperature_J=p["energy"]["temperature_J"],peak_upper_C=p["peak"],slack_ms=p["slack"]) if p else dict.fromkeys(
                       ("plan","status","J","low_J","high_J","E35_J","temperature_J","peak_upper_C","slack_ms"))


def markdown(header,rows):
    return ["|"+"|".join(header)+"|","|"+"|".join("---" for _ in header)+"|",*["|"+"|".join(map(str,row))+"|" for row in rows]]


def number(v,n=6):
    return "—" if v is None else f"{v:.{n}f}"


def main():
    TABLE.mkdir(exist_ok=True)
    receipt=read(OUT/"budget.json")
    manifest=read(OUT/"nominees.json") if (OUT/"nominees.json").exists() else []
    rows=[]
    stages=[]
    traces=[]
    hot=[]
    pools=[]
    lookup={}
    duplicates=Counter((r["case"],r["mapping"]) for r in manifest)
    attempts=Counter()
    unique=set()
    sources=Counter()
    frequency_rows=[]
    recorded={}
    for path in (OUT/"slots").glob("*/*.json"):
        verified=read(path)
        recorded[verified["case"],verified["seed"]]=verified["comparison"]
    indices={}
    for r in manifest:
        c,b,k=r["case"],r["budget"],r["rank"]
        x=dict(case=c,construction_s=b,rank=k,seed=r["seed"],mapping=r["mapping"],seed_status=r["point"]["status"],
               mapping_occurrences=duplicates[c,r["mapping"]],seed_ref_J=r["point"]["e35"],seed_J=r["point"]["J"],
               seed_peak_upper_C=r["point"]["peak"],nomination_s=r["nomination_s"])
        file=OUT/"slots"/c/f"{b}-{k}.json"
        written=file.exists()
        result=read(file)["comparison"] if written else {}
        if not written and (c,r["seed"]) in recorded:
            index=ROOT.parent/f"ch3_center_confirmation/lanes/{c}/r1/paired_results/{c}/physical/index.json"
            if index.exists():
                if c not in indices:
                    indices[c]=read(index)["plans"]
                ix=indices[c][r["seed"]]
                verified=recorded[c,r["seed"]]
                assert ix["mapping"]==r["mapping"] and ix["trace_sha"]==verified["trace"]
                for s,h in r["history"].items():
                    if h["point"]:
                        assert h["point"]==verified["proposed"][s]
                result=verified
        done=bool(result)
        x["completion_basis"]="written_slot" if written else "verified_identical_plan_trace" if done else "incomplete"
        outcomes=result.get("outcomes",{})
        x.update(complete=done,seed_trace=result.get("trace"),ordinary_complete_in_history=r["history"]["ordinary"]["completed"],
                 thermal_complete_in_history=r["history"]["thermal"]["completed"],A_thermal_guide=result.get("guide"))
        for arm in "ABC":
            x.update({arm+"_"+name:v for name,v in fields(outcomes.get(arm)).items()})
        for right in ("A","C"):
            val,pct,v=compare(outcomes.get("B"),outcomes.get(right)) if done else (None,None,"incomplete")
            x.update({f"B_minus_{right}_J":val,f"B_minus_{right}_pct":pct,f"B_vs_{right}":v})
        rows.append(x)
        if not done:
            continue
        lookup[c,b,k]=outcomes
        is_new=(c,r["seed"],result["trace"]) not in unique
        unique.add((c,r["seed"],result["trace"]))
        folder=OUT/"evidence"/c/"computed"/r["seed"]
        with (folder/"request_frequencies.csv").open() as stream:
            freq=list(csv.DictReader(stream))
        for a,y in (("A","seed"),("B","seed"),("C","seed"),("B","A")):
            label=f"{a}_vs_{y}_opp_changes"
            x[label]=sum(v[a]!=v[y] for v in freq) if freq and freq[0][a] and freq[0][y] else None
        if is_new:
            frequency_rows.extend(dict(case=c,seed_plan=r["seed"],**v) for v in freq)
        events=[json.loads(l) for l in (folder/"events.jsonl").read_bytes().splitlines() if l.endswith(b"}")]
        for tag in ("ordinary","thermal","direct"):
            p=result["proposed"][tag]
            src=result["source"].get(tag,"computed_direct")
            records=[e for e in events if e["kind"]=="dp" and e["tag"]==tag]
            if is_new:
                sources[tag,src]+=1
                attempts[tag]+=len(records)
            stages.append(dict(case=c,construction_s=b,rank=k,stage=tag,source=src,
                         guide=r["seed"] if tag=="direct" else result["guide"] if tag=="thermal" else None,
                         fresh_calls=len(records),fresh_reserves=",".join(str(e["reserve"]) for e in records),**fields(p)))
        for tag,z in result["traces"].items():
            if z is None:
                continue
            traces.append(dict(case=c,construction_s=b,rank=k,kind=tag,seed=r["seed"],seed_trace=result["trace"],
                               result_trace=z["trace"],peak_upper_delta_C=z["peak_upper_delta_C"],
                               **{f"{node}_max_abs_delta_C":v for node,v in zip(("pre","post","GPU","NPU"),z["max_abs_delta_C"])},
                               **{f"{node}_end_delta_C":v for node,v in zip(("pre","post","GPU","NPU"),z["end_delta_C"])}))
        if x["seed_status"]=="HOT":
            hot.append(dict(case=c,construction_s=b,rank=k,seed=r["seed"],mapping=r["mapping"],seed_peak_C=r["point"]["peak"],
                            **{arm+"_recovered":bool(outcomes[arm]) for arm in "ABC"},
                            **{arm+"_plan":outcomes[arm]["plan"] if outcomes[arm] else None for arm in "ABC"},
                            frequency_evidence=folder.relative_to(ROOT).as_posix()+"/request_frequencies.csv"))
    for c in CASES:
        for b in (60,600):
            positions=[r for r in manifest if r["case"]==c and r["budget"]==b]
            included=[lookup[c,b,r["rank"]] for r in positions if (c,b,r["rank"]) in lookup]
            complete=bool(positions) and len(included)==len(positions)
            best={a:winner(v[a] for v in included) if complete else None for a in "ABC"}
            row=dict(case=c,construction_s=b,positions=len(positions) if manifest else None,completed=len(included),complete=complete)
            for a,p in best.items():
                row.update({a+"_"+name:v for name,v in fields(p).items()})
                row[a+"_rank"]=next((r["rank"] for r in positions if complete and p and lookup[c,b,r["rank"]][a]==p),None)
            for a,y in (("B","A"),("C","A"),("B","C")):
                diff,pct,verdict=compare(best[a],best[y]) if complete else (None,None,"incomplete")
                row.update({f"{a}_minus_{y}_J":diff,f"{a}_minus_{y}_pct":pct,f"{a}_vs_{y}":verdict})
            pools.append(row)
    table("mappings.csv",rows,list(dict.fromkeys(k for r in rows for k in r)) if rows else ["case","construction_s","rank","complete"])
    table("request_frequencies.csv",frequency_rows,["case","seed_plan","request","device","seed","A","B","C","ordinary","thermal","direct"])
    table("pools.csv",pools,list(pools[0]))
    table("stages.csv",stages,list(stages[0]) if stages else ["case","construction_s","rank","stage"])
    table("trace_changes.csv",traces,list(traces[0]) if traces else ["case","construction_s","rank","kind"])
    table("hot_recovery.csv",hot,list(hot[0]) if hot else ["case","construction_s","rank","seed","A_recovered","B_recovered","C_recovered"])
    pool_counts=Counter(r["B_vs_A"] for r in pools)
    map_counts=Counter(r["B_vs_A"] for r in rows)
    lost_hot=[h for h in hot if h["A_recovered"] and not h["B_recovered"]]
    losses=[p for p in pools if p["B_vs_A"]=="higher"]
    if pool_counts["incomplete"] or len(manifest)==0:
        decision="预算内完整证据不足，保留现行两阶段流程。未完成位置及其候选池均单列。"
    elif lost_hot or pool_counts["lost_SAFE"]:
        decision="保留现行两阶段流程。直接热感知调频丢失了两阶段方法已有的安全恢复或候选池安全覆盖。"
    elif losses:
        decision="一次直接热感知调频在部分完整候选池产生可认证的能耗损失。保留两阶段作为当前实现，由用户决定是否接受表中的逐池代价。"
    elif not hot:
        decision="直接热调频在已测候选池上保持了安全覆盖与能耗质量。历史提名未提供超温恢复对照，该项仍缺验证。"
    else:
        decision="固定候选池结果支持删除普通调频阶段，并将一次直接热感知调频送入独立端到端确认。"
    source_stats=[dict(stage=t,source=s,count=n) for (t,s),n in sources.items()]
    summary=dict(decision=decision,historical_constructions=24,positions=len(rows),complete=sum(r["complete"] for r in rows),
                 unique_seed_traces=len(unique),unique_case_mappings=len(duplicates),pool_counts=dict(pool_counts),mapping_counts=dict(map_counts),
                 hot_positions=len(hot),hot_recovered={a:sum(h[a+"_recovered"] for h in hot) for a in "ABC"},
                 lost_hot_positions=len(lost_hot),historical_stage_sources=source_stats,new_DP_wrapper_calls=dict(attempts),budget=receipt)
    (ROOT/"decision.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    names={"lower":"直接版较低","overlap":"区间重叠","higher":"直接版较高","both_no_SAFE":"双方均无安全解",
           "lost_SAFE":"直接版丢失安全解","gained_SAFE":"直接版新增安全解","incomplete":"未完成"}
    lines=["# 能否用一次热感知全局调频替代两阶段调频","",f"**{decision}**","",
           f"从十二条流的单中心配额版首次 60 秒、600 秒构造提取实际提名，共 {len(manifest)} 个位置，涉及 {len(duplicates)} 个流内不同映射，完成 {summary['complete']} 个位置。经物理验证的不同原始排程与轨迹组合为 {len(unique)} 组。每个构造单独选最佳安全排程。","",
           "## 单映射与整池质量",""]
    lines+=markdown(["比较层级（直接版对两阶段）","直接版较低","区间重叠","直接版较高","失去／新增 SAFE","双方无 SAFE","未完成"],[
        [label,ct["lower"],ct["overlap"],ct["higher"],f"{ct['lost_SAFE']}／{ct['gained_SAFE']}",ct["both_no_SAFE"],ct["incomplete"]]
        for label,ct in (("实际提名位置",map_counts),("完整候选池",pool_counts))])
    lines+=["","A 为现行两阶段，B 为从原始轨迹直接热调频，C 为只做普通调频。下表为各池最终完整系统能耗中，获得连续证书的最低在位值。差额为 B 减 A，正数表示直接版耗电更多。区间重叠采用连续证书上下界判定。",""]
    lines+=markdown(["流","历史构造（秒）","完成／提名","A（J）","B（J）","C（J）","B−A（J）","变化（%）","判定"],
                    [[p["case"],p["construction_s"],f"{p['completed']}／{p['positions']}",number(p["A_J"]),number(p["B_J"]),number(p["C_J"]),
                      number(p["B_minus_A_J"]),number(p["B_minus_A_pct"],5),names[p["B_vs_A"]]] for p in pools])
    if losses:
        lines+=["","能耗较高的候选池为 "+"、".join(f"{r['case']}（{r['construction_s']} 秒构造，+{r['B_minus_A_J']:.6f} J，+{r['B_minus_A_pct']:.5f}%）" for r in losses)+"。"]
    completed=[r for r in rows if r["complete"]]
    if completed:
        changed=sum(r["A_thermal_guide"]!=r["seed"] for r in completed)
        same=sum(r["A_plan"] is not None and r["A_plan"]==r["B_plan"] for r in completed)
        lines+=["",f"按实际提名位置计，两阶段在 {changed}／{len(completed)} 处使用了不同于原始排程的热修正参考排程。两种方法在 {same} 处最终接纳了完全相同的安全排程。原始、各阶段提案及最后在位解的频档均按请求记录。[逐请求频档](tables/request_frequencies.csv)"]
        bc=Counter(p["C_vs_A"] for p in pools)
        lines+=["",f"只做普通调频相对两阶段，在完整候选池中严格较低 {bc['lower']} 个、认证区间重叠 {bc['overlap']} 个、严格较高 {bc['higher']} 个、丢失安全解 {bc['lost_SAFE']} 个。"]
    lines+=["","## 超温候选与温度轨迹","",
            f"实际完成的超温提名位置 {len(hot)} 个。两阶段、直接热调频、普通调频分别恢复 {summary['hot_recovered']['A']}、{summary['hot_recovered']['B']}、{summary['hot_recovered']['C']} 个。两阶段恢复而直接版未恢复的位置共 {len(lost_hot)} 个。按提名位置计数，重复身份可从表中核对。",""]
    if hot:
        lines+=markdown(["流","历史构造","位置","原始峰温上界（°C）","两阶段恢复","直接恢复","普通恢复"],
                    [[h["case"],h["construction_s"],h["rank"],number(h["seed_peak_C"],4),*["是" if h[a+"_recovered"] else "否" for a in "ABC"]] for h in hot])
    else:
        lines+=["两处实际超温提名均缺少直接热调频的结果。历史上已完成的恢复记录见文末的全部提名清单。"]
    if traces:
        for stage,desc in (("direct","直接调频提案"),("thermal","两阶段热修正提案")):
            data=[v for v in traces if v["kind"]==stage]
            if data:
                lines+=["",f"{desc}相对其原始排程，GPU／NPU 温度曲线最大绝对变化分别为 {max(z['GPU_max_abs_delta_C'] for z in data):.5f}／{max(z['NPU_max_abs_delta_C'] for z in data):.5f} °C。曲线比较在两条轨迹的事件边界并集上进行，节点温度按冻结 DP 的线性插值口径计算；最终安全判定使用连续认证器的峰温上界。"]
    lines+=["","## 求解规则与实际可删除的计算","",
            "两版都固定请求到设备的映射，沿用同一套全局调频状态、FIFO、切换与因果空闲规则。普通阶段调用精确整数成本内核；热感知阶段调用包含轨迹温度积分的动态规划内核。一次优化先按原期限求解，冻结规则允许在后处理时序失败时再预留 13 个 tick 重求。","",
            "直接版省去每个提名的一次普通全局调频阶段，仍执行一次热感知阶段及必要的预留重试。现行两阶段在安全初解上只用严格改善的普通结果更新参考轨迹；超温初解允许使用普通阶段有效的 SAFE 或 HOT 轨迹。普通版复用第一阶段。原始 SAFE 可作在位解，HOT 只能引导求解。每个新候选均经过完整时序重放和连续认证。","",
            f"新实际调用 solve 的次数（含预留重试、按两个设备合计为一次全局调用）为普通 {attempts['ordinary']}、两阶段热修正 {attempts['thermal']}、直接热调频 {attempts['direct']}。历史完整阶段复用来源及匹配重算计数见决策记录。历史中断阶段需要在本轮完整求解后才能进入配对。","",
            f"恢复、编译、预热、必要复算、调频、认证和科学结果落盘采用同一单核时钟。本轮累计计费 {receipt.get('cumulative_s',receipt['elapsed_s']):.3f}／600 核秒。最终制作表格及发布档案在计算结束后进行。此诊断固定提名池，无法给出新算法从空排程出发的能耗或运行时间。","",
            "[逐映射配对、能耗分量与时序余量](tables/mappings.csv) · [完整候选池配对](tables/pools.csv) · [各阶段实际提案](tables/stages.csv) · [温度轨迹变化](tables/trace_changes.csv) · [超温恢复见证](tables/hot_recovery.csv) · [提名及历史证据索引](out/nominees.json) · [证书、轨迹与逐请求频档](out/evidence) · [预算回执](out/budget.json)"]
    (ROOT/"REPORT_zh.md").write_text("\n".join(lines)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
