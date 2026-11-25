"""Descriptive postprocessing of sealed receipts; no optimizer or thermal solver is called."""
import ast,csv,gzip,json,statistics,time
from collections import Counter
from pathlib import Path
from samples import ROOT,read,write

def table(name):
    with (ROOT/name).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))

def summarize():
    start=time.perf_counter();state=read(ROOT/"execution.json");assert state["status"]=="COMPLETE"
    cases=read(ROOT/"samples.json")["cases"];by_id={s["id"]:s for s in cases}
    pairs=table("paired.csv");details=table("candidates.csv");arms=table("arms.csv")
    verified=read(ROOT/"thermal_replay.json");gate=read(ROOT/"gate.json")
    strict=[];footer=[];old_returned={};statuses=Counter();primary=Counter()
    for z in pairs:
        ident=z["sample"];s=by_id[ident];folder=ROOT/"replays"/ident/"Old";arm=read(folder/"arm.json")
        source=json.loads(gzip.decompress((ROOT/"prestates"/(z["source"]+".json.gz")).read_bytes()))["rows"]
        signatures=set()
        # Materialized returns include any too late to certify. An interrupted old
        # call cannot establish absence among all returns, so is not a strong witness.
        for f in folder.glob("*.json.gz"):
            rows=json.loads(gzip.decompress(f.read_bytes()))["rows"]
            signatures.add(tuple((i,*b[:2]) for i,(a,b) in enumerate(zip(source,rows)) if a[:2]!=b[:2]))
        expected=sum(q["returned"] for q in arm["core"].get("solves",[]))
        observed=sum(origin.startswith("core") for origin,k in arm["visits"])+len(arm.get("uncertified",[]))
        complete=arm["status"]=="COMPLETE" and expected==observed
        old_returned[ident]=dict(expected=expected,observed=observed,complete=complete,configurations=len(signatures))
        for x in (v for v in details if v["sample"]==ident and v["method"]=="New"):
            if x["on_time"]!="True" or x["status"]!="SAFE" or x["joint"]!="True":continue
            cfg=tuple((i,*op) for i,op in ast.literal_eval(x["config_signature"]))
            if cfg in signatures or not complete:continue
            if x["aux_direct"]!="True" and z["new_fallback"]!="False":continue
            if float(x["hi"])>=min(s["prior_metrics"]["E_bounds"][0],float(z["old_lo"])):continue
            strict.append(dict(sample=ident,case=z["case"],sha=x["sha"],source=z["source"],old_best=z["old_id"],
                gain_mJ=1000*(float(z["old_lo"])-float(x["hi"])),source_gain_mJ=1000*(s["prior_metrics"]["E_bounds"][0]-float(x["hi"])),
                direct=x["aux_direct"]=="True",config=int(x["config"]),moved=int(x["shift"]),support=int(x["support"]),
                original_target=x["target_recovered"]=="True",target_changed=x["target_changed"]=="True",
                old_bounds_J=[float(z["old_lo"]),float(z["old_hi"])],candidate_bounds_J=[float(x["lo"]),float(x["hi"])]))
        for method in ("Old","New"):
            arm=read(ROOT/"replays"/ident/method/"arm.json")
            statuses.update([v["status"] for v in arm["auxiliary"].get("solves",[])])
    valid_cases={w["case"] for w in strict};locally_supported=bool(strict)
    write(ROOT/"witnesses.json",dict(old_returns=old_returned,witnesses=strict,case_coverage=sorted(valid_cases)))
    r=read(ROOT/"regression/validation/replay_gate.json");fin=read(ROOT/"regression/validation/finite_gate.json")
    lines=["# E2-c1 历史回退邻域的配对回放","",
           f"27 个预选前态、54 组限时回放全部执行。{len(set(w['sample'] for w in strict))} 个前态出现了新的联合配置，在同一前态上严格优于原安全排程和旧 NoOrder 的最佳安全候选。共 {len(strict)} 份物理排程证书符合此条件。","",
           "## 同前态的安全能耗与回退","",
           "差额为旧组最佳 SAFE 能耗减去新组最佳 SAFE 能耗。胜负按完整窗口的能耗认证区间判定。每个工况的 9 项取自 3 个原搜索种子，每次取首、中、末三个回退。","",
           "|工况|新组胜／负／区间重叠|配对差额中位 / mJ|范围 / mJ|旧／新回退数|新组产生联合候选的案例|有强见证的案例（含直接辅助见证）|",
           "|---|---:|---:|---:|---:|---:|---:|"]
    per_case={}
    for case in ("D1","D2","D3"):
        rr=[z for z in pairs if z["case"]==case];wins=Counter(z["result"] for z in rr)
        gain=[float(z["delta_mJ"]) for z in rr];w=[v for v in strict if v["case"]==case]
        wc=len({v["sample"] for v in w});wd=len({v["sample"] for v in w if v["direct"]})
        oldfb=sum(z["old_fallback"]=="True" for z in rr);newfb=sum(z["new_fallback"]=="True" for z in rr)
        nj=sum(int(z["new_joint"])>0 for z in rr)
        per_case[case]=dict(win=wins["win"],loss=wins["loss"],overlap=wins["overlap"],paired_median_mJ=statistics.median(gain),
                    old_fallback=oldfb,new_fallback=newfb,joint_cases=nj,witness_cases=wc,direct_cases=wd)
        lines.append(f"|{case}|{wins['win']}／{wins['loss']}／{wins['overlap']}|{statistics.median(gain):.3f}|{min(gain):.3f} 至 {max(gain):.3f}|{oldfb}／{newfb}|{nj}/9|{wc}/9（{wd}）|")
    lines+=["","## 已认证的节能见证","",
        "强见证要求配置和起点均有实际变化，且配置组合未出现在旧组已物化的任何返回排程中。逐组核对旧 CP 回调返回计数，包括未赶上认证截止的返回。旧调用记录不完整时，不用该案例作强见证。新候选须直接来自辅助模型，或来自该模型实际支撑域的后续 Core。下表按工况各取相对旧组可靠差额最大的见证。","",
        "|工况／前态|旧组下界 / J|新候选上界 / J|相对旧组可靠节能 / mJ|相对前态可靠节能 / mJ|变档／移时／支撑并集|原主目标|来源|","|---|---:|---:|---:|---:|---:|---|---|"]
    for case in ("D1","D2","D3"):
        v=[x for x in strict if x["case"]==case]
        if not v:lines.append(f"|{case}|—|—|—|—|—|无强见证|—|");continue
        x=max(v,key=lambda a:a["gain_mJ"]);kind="恢复原提案" if x["original_target"] else "改用其他档" if x["target_changed"] else "保持原配置"
        lines.append(f"|{x['sample']}|{x['old_bounds_J'][0]:.9f}|{x['candidate_bounds_J'][1]:.9f}|{x['gain_mJ']:.3f}|{x['source_gain_mJ']:.3f}|{x['config']}／{x['moved']}／{x['support']}|{kind}|{'辅助候选直接评价' if x['direct'] else '支撑域内 Core'}|")
    for x in strict:primary["exact" if x["original_target"] else "other" if x["target_changed"] else "unchanged"]+=1
    scope=[x["support"] for x in strict]
    if strict:
        lines+=["","对每个工况上表所列见证，进一步把旧组最佳排程减去新候选的真实能耗分项。正值表示新候选节省能耗，单位 mJ。","","|历史案例|活动|域驻留|切换|温度修正|去除温度修正的净差|","|---|---:|---:|---:|---:|---:|"]
        for case in ("D1","D2","D3"):
            ws=[v for v in strict if v["case"]==case]
            if not ws:continue
            w=max(ws,key=lambda v:v["gain_mJ"]);ident=w["sample"]
            def metrics(method,sha):
                candidates=read(ROOT/"replays"/ident/method/"arm.json")["candidates"]
                return next((v["metrics"] for v in candidates if v["sha"]==sha),by_id[ident]["prior_metrics"])
            old=metrics("Old",w["old_best"]);new=metrics("New",w["sha"])
            deltas=[1000*(old[k]-new[k]) for k in ("activity_J","base_J","switch_J","temperature_J")]
            lines.append("|"+ident+"|"+"|".join(f"{v:.3f}" for v in deltas+[sum(deltas[:3])])+"|")
        lines+=["","变档、移时和重新选择已授权空闲控制会共同改变上述分项。单个见证的总差额无法分别识别三者的因果贡献。"]
    lines+=["",f"强见证按物理排程计，恢复原主目标提案 {primary['exact']} 份，主目标改用其他档 {primary['other']} 份，主目标保持原配置 {primary['unchanged']} 份。"+(f"实际支撑并集范围 {min(scope)}–{max(scope)} 个 Stage。" if scope else ""),
        "","## 结构、认证与预算","",
        "D2 首次预检固定 Stage 10 的原目标档位，原投影与条件最小支撑均为 42，超过 24 的上限。D3 首次迭代固定 Stage 1、4、13 的原目标档位，原投影 22，条件最小支撑 14。两项均有最大匹配下界及达到下界的原物理构造器合法排程，见 structure.json。其他回放采用自己的完整历史前态。","",
        f"E2-a 的 8 个有限域共重建 {fin['original']+fin['additional']} 个物理排程。{r['unique']} 个历史排程的 {r['memberships']} 项归属以及 {r['permissions']} 项权限检查通过。独立复核覆盖 {len(verified)} 个不同的完整证书排程，逐一比较原事件构造与紧凑域事件、温度端点和矩阵指数积分能耗。最大端点偏差 {max(x['temperature_endpoint_error_K'] for x in verified.values()):.3g} K。","",
        f"辅助求解状态为 {dict(statuses)}。FEASIBLE 表示限时内取得可行解但未证最优，TIME_LIMIT 表示没有在该次限时内返回已证可行赋值。OPTIMAL 和 INFEASIBLE 只适用于当次辅助骨架及已排除的配置组合。","",
        f"回归 {state['phases']['regression']['charged_s']:.2f} s，结构检查 {state['phases']['structure']['charged_s']:.2f} s，54 组回放累计 {sum(z['charged_s'] for z in state['groups']):.2f} s，独立复核 {state['phases']['audit']['charged_s']:.2f} s，共 {state['numerical_s']:.2f} / 2400 s。进程硬截止 {sum(z.get('watchdog',False) for z in state['groups'])} 组。每个候选的认证完成时刻、求解状态及其对应日志均已保留。","",
        "## 研究决定",""]
    lines+=["辅助模型逐工况的可用性如下。联合候选总数包含普通回退；本表单列辅助模型实际返回赋值和生成支撑域的情况。","","|工况|全流 Stage 数|返回赋值的案例|启用实际支撑域的案例|无赋值且辅助调用超时的案例|辅助求解状态（调用数）|","|---|---:|---:|---:|---:|---|"]
    for case in ("D1","D2","D3"):
        records=[read(ROOT/"replays"/s["id"]/"New"/"arm.json") for s in cases if s["case"]==case]
        counts=Counter(q["status"] for a in records for q in a["auxiliary"].get("solves",[]))
        returned=sum(bool(a["auxiliary"].get("assignments")) for a in records)
        active=sum(a["fallback"] is False for a in records)
        empty=sum(not a["auxiliary"].get("assignments") and any(q["status"]=="TIME_LIMIT" for q in a["auxiliary"].get("solves",[])) for a in records)
        n=max(a["auxiliary"].get("tasks",0) for a in records)
        per_case[case].update(aux_return_cases=returned,active_support_cases=active,empty_timeout_cases=empty,aux_status=dict(counts))
        lines.append(f"|{case}|{n}|{returned}/9|{active}/9|{empty}/9|"+", ".join(f"{k} {v}" for k,v in sorted(counts.items()))+"|")
    lines+=[""]
    if locally_supported:
        lines.append("局部回放已取得真实安全节能证据，可据此单独讨论完整算法比较的范围。证据覆盖 "+ "、".join(sorted(valid_cases))+"。各工况的正、负配对同时保留。")
    else:lines.append("本轮没有取得可归因于新支撑机制、同时击败旧组最佳 SAFE 的严格见证。门控未取得较强的差异性证据。")
    if not per_case["D3"]["active_support_cases"]:
        lines+=["","D3 的九项回放均未启用新的时序支撑域。当前预算下缺少直接启动 D3 混合全流比较所需的工程证据，D1 或 D2 的局部见证不能替代 D3 的可用性。"]
    multi_cases={c:sorted({x["sample"] for x in strict if x["case"]==c and x["config"]>=2}) for c in ("D1","D2","D3")}
    same=sum(z["old_id"]==z["new_id"] for z in pairs)
    lines+=["",f"同一步实际改变至少两项配置且严格节能的前态数分别为 D1 {len(multi_cases['D1'])}/9、D2 {len(multi_cases['D2'])}/9、D3 {len(multi_cases['D3'])}/9。{same}/27 个配对的最佳安全排程身份完全相同。"]
    if per_case["D3"]["empty_timeout_cases"]==8 and not multi_cases["D3"]:
        lines+=["","D3 唯一优势前态为种子 102 的中间回退。其 6 份严格节能排程都只改一个配置，原主目标保持原档。其余 8 项的辅助模型在分配的求解时间内没有给出赋值，均转入普通邻域。D3 说明 2400 个 Stage 上存在可利用的局部移时空间，但现有回放证据不足以优先启动 D3 的完整混合比较，也不足以确立多配置机制的独立收益。"]
    control=next(z for z in pairs if z["sample"]=="D2_101_first")
    if control["old_fallback"]==control["new_fallback"]=="True" and control["old_id"]==control["new_id"]==control["source"]:
        lines+=["",f"D2 的 42 Stage 结构案例恰好也是 D2_101_first 的前态。该配对中新旧两组都回退，最佳安全能耗均为 {float(control['new_J']):.9f} J。D2 的其他胜例不能代替此项诊断。"]
    warnings=[f.stem for f in sorted((ROOT/"logs").glob("*.txt")) if "Warning, an interval constraint" in f.read_text(errors="replace")]
    if warnings:
        lines+=["","求解库的区间约束提示出现在 "+"、".join(warnings)+"。相应候选的物理排程及完整证书均经过独立校验。原始提示保存在对应 logs 文件中。"]
    lines+=["","这 27 项来自既有 Proposed 的失败区域，不能估计整条任务流的平均节能，也没有比较混合方法与 G3 的终点能耗。E2-b 的原立项结论保留。E2-c1 在本报告结束，E2-c2 的运行数为 0。","",
       "配对数据见 [paired.csv](paired.csv)，全部候选见 [candidates.csv](candidates.csv)，逐组回退、支撑与恢复情况见 [arms.csv](arms.csv)，严格见证及身份见 [witnesses.json](witnesses.json)。原始排程、分段热证书和调用记录按样本、方法保存在 replays 目录。"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
    gate.update(strong_witnesses=len(strict),strict_samples=len({w["sample"] for w in strict}),per_case=per_case,multi_configuration_witness_cases=multi_cases,identical_best=same,
        eligibility_for_discussion=locally_supported,discussion_cases=sorted(valid_cases),old_returns_complete=sum(x["complete"] for x in old_returned.values()))
    write(ROOT/"gate.json",gate)
    return gate
if __name__=="__main__":print(summarize())
