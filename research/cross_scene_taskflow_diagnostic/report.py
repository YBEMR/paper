"""Independent reconstruction, call-accounting and bounded decision report."""
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict
from importlib.metadata import version
from fractions import Fraction as Q
from pathlib import Path
from profiles import CFG, ROOT, IDS, dump, git, table
from model import Problem
from execution import FOLDERS, fetch, hydrate, loadplan


def get(filename):
    path=ROOT/filename
    return json.loads(path.read_bytes()) if path.exists() else {}


def audit(end):
    logs=[json.loads(s) for s in (ROOT/"logs/calls.jsonl").read_text(encoding="utf8").splitlines()]
    starts=[x for x in logs if x["event"]=="begin"]
    ends={(x["case"],x["method"],x["arm"]):x for x in logs if x["event"]=="end"}
    evidence={}; metrics=[]; pairrows=[]; resets=[]; out=[];summary=[]
    stop=get("logs/stop.json");checks=get("preflight/checks.json")
    gates={case:get("logs/gate_"+case+".json") for case in IDS}
    for case in IDS:
        p=Problem(case)
        local={}
        cases=[a for a in starts if a["case"]==case]
        lb=p.lower() if cases else {"total":None}
        for call in cases:
            if time.perf_counter()>=end: raise TimeoutError("audit limit")
            method=call["method"];s=call["arm"]
            rec=fetch(case,method,s)
            actual=ends.get((case,method,s),{})
            for key,field in (("best_plan","best"),("safe_plan","safe"),("hot_plan","hot")):
                ident=rec.get(key)
                if ident and ident not in evidence:
                    _,real,reset=hydrate(p,loadplan(ident),rec[field])
                    evidence[ident]=(real,reset)
                    resets.append(dict(case=case,plan=ident,continuous=real["status"],reset=reset["status"],
                        continuous_hotspot=CFG["nodes"][real["hotspot"]],reset_hotspot=CFG["nodes"][reset["hotspot"]],
                        peak_cont_C=max(real["peak_hi"]),peak_reset_C=max(reset["peak_hi"]),
                        continuous_E_J=real["E_J"],reset_E_J=reset["E_J"],reset_minus_cont_J=reset["E_J"]-real["E_J"]))
            best=rec.get("best") or {}; safe=rec.get("safe") or {};hot=rec.get("hot") or {}
            bound=rec.get("search",{}).get("conditional_lower",lb)
            lo=float(Q(bound["total"])); hi=best.get("E_bounds",[None,None])[1]
            rate=None
            original=rec.get("initial")
            if safe and original:
                if original not in evidence:
                    _,real,reset=hydrate(p,loadplan(original),None);evidence[original]=(real,reset)
                baseline=evidence[original][0]
                if baseline["status"]=="SAFE":
                    rate=100*(1-safe["E_bounds"][1]/baseline["E_bounds"][0])
            if method=="G4_group" and original:
                initial,pol=loadplan(original)
                candidate=rec.get("safe_plan")
                changes=[];added=[];removed=[]
                if candidate:
                    from model import transitions
                    final,policy=loadplan(candidate)
                    changes=[i for i in range(p.n) if initial[i]!=final[i]]
                    before=set(map(tuple,transitions(p,initial,pol,edges=True)[2]))
                    after=set(map(tuple,transitions(p,final,policy,edges=True)[2]))
                    added=sorted(after-before);removed=sorted(before-after)
                dump("g4_mechanism/"+case+"_"+s+"_changes.json",dict(changed=changes,edges_added=added,
                     edges_removed=removed,target_restored=bool(candidate),certified_saving_percent=rate))
            row=dict(case=case,method=method,arm=s,run=actual.get("state","MISSING"),result=best.get("status","UNRESOLVED"),
                     SAFE=int(bool(safe)),first_SAFE_s=rec.get("first_SAFE_s"),SAFE_E_J=safe.get("E_J"),
                     SAFE_E_lower_J=safe.get("E_bounds",[None,None])[0],SAFE_E_upper_J=safe.get("E_bounds",[None,None])[1],
                     best_E_J=best.get("E_J"),best_peak_C=max(best.get("peak_hi",[0])) if best else None,
                     deadline_slack_ms=best.get("min_deadline_slack_ms"),lower_bound_J=lo,upper_bound_J=hi,
                     optimality_gap_upper_J=None if hi is None else hi-lo,safe_saving_lower_percent=rate,
                     time_budget_s=call["budget_s"],elapsed_s=actual.get("actual_s"),candidate_count=rec.get("candidates"),
                     independent_cert_count=rec.get("certifications"),safe_plan=rec.get("safe_plan"))
            metrics.append(row)
            if method=="RF": local[s]=(lo,hi)
        if len(local)==4 and all(h is not None for l,h in local.values()):
            # Each thermal cost is nonnegative by domain inclusion.
            def cost(label):
                l0,u0=local[label+"0"];lt,ut=local[label+"theta"]
                return max(0.,lt-u0),max(0.,ut-l0)
            rl,ru=cost("R");fl,fu=cost("F")
            pairrows.append(dict(case=case,R0=local["R0"],Rtheta=local["Rtheta"],F0=local["F0"],Ftheta=local["Ftheta"],
                           delta_lower_J=rl-fu,delta_upper_J=ru-fl,confirmed=rl>fu))
        safe=[r for r in metrics if r["case"]==case and r["method"] in ("common","HEFT","ETA","SA","G3") and r["SAFE"]]
        best=min(safe,key=lambda r:r["SAFE_E_upper_J"]) if safe else {}
        g2=fetch(case,"G2").get("best") or {}
        enum=fetch(case,"G3").get("best") or {}
        cost_lb=max(0.,float(Q(lb["total"]))-g2["E_bounds"][1]) if g2 else None
        cost_ub=best.get("SAFE_E_upper_J")-float(Q(lb["total"])) if best else None
        summary.append(dict(case=case,status="EXECUTED" if cases else "NOT_RUN",requests=len(p.req),window_ms=p.horizon/10,
          best_SAFE_method=best.get("method"),best_SAFE_J=best.get("SAFE_E_J"),peak_upper_C=best.get("best_peak_C"),
          first_SAFE_s=best.get("first_SAFE_s"),safe_methods=len(safe),
          common_reference_methods_run=sum(r["case"]==case and r["method"] in ("common","HEFT","ETA","SA","G3") for r in metrics),
          G2_status=g2.get("status"),G2_J=g2.get("E_J"),G3_J=enum.get("E_J"),
          guaranteed_lb_J=lb["total"],thermal_cost_lower_J=cost_lb,thermal_cost_upper_J=cost_ub,
          certified_hot_clues=len(gates[case].get("hot_clues",[])),matched_positive=gates[case].get("matched_positive"),
          G4_targets=len(gates[case].get("g4_records",[])),
          recovered_B3=sum(bool(r["SAFE"]) for r in metrics if r["case"]==case and r["method"]=="G4_group" and r["arm"].endswith("_B3"))))
    table("summary.csv",summary)
    if metrics: table("logs/method_metrics.csv",metrics)
    if resets:
        for r in resets:
            cohort=[v for v in resets if v["case"]==r["case"]]
            for key in ("continuous","reset"):
                r[key+"_energy_rank"]=1+sum(v[key+"_E_J"]<r[key+"_E_J"] for v in cohort)
        table("certificates/reset_comparison.csv",resets)
    dump("local_rf/intervals.json",pairrows)
    def joined(rows): return "、".join(rows) if rows else "无"
    reached=[s["case"] for s in summary if s["matched_positive"]]
    threshold=[]
    for c in IDS:
        arms={r["arm"]:r for r in metrics if r["case"]==c and r["method"]=="pilot"}
        if len(arms)==3 and all(r["SAFE"] for r in arms.values()):
            if all(arms["DELTA"]["SAFE_E_upper_J"]<=.99*arms[k]["SAFE_E_lower_J"] for k in ("AB","LNS")): threshold.append(c)
    approved=len(threshold)>=2 and any(c.startswith("H") for c in threshold)
    state="执行中止" if stop else "有限验证结束"
    out=["# P1 最小立项验证结论","",f"**{state}。第三章正式算法立项{'通过' if approved else '未获批准'}。**",""]
    if stop: out+=["停止原因见 `logs/stop.json`。","","```",stop["reason"],"```",""]
    out+=["## 正确性与物理模型",""]
    if checks:
        out+=[f"G0 通过。五份原始数据通过 Git blob 校验。D0 全低频安排已独立认证，65°C 上界由不变温度区域给出。高负载场景仅 main 的最短累计占用为 {checks['high_main_min_demand_device_ms']} 设备·ms，两个加速器在相应释放—期限区间内最多提供 {checks['high_two_devices_available_ms']} 设备·ms；固定高档的合法排程已归档。",
              "","验证对象是含合成 CPU/NPU 画像、GPU 观测外推及四节点热网络的 P1 模型。",""]
    else: out+=["G0 未通过。模型正确性未决。",""]
    out+=["## 开发及留出结果","","|工况|请求数|最佳完整 SAFE 能耗/J|方法|该方案峰温上界/°C|无温限搜索结果|",
          "|---|---:|---:|---|---:|---|"]
    for s in summary:
        out.append("|{}|{}|{}|{}|{}|{}|".format(s["case"],s["requests"],format(s["best_SAFE_J"],".8f") if s["best_SAFE_J"] is not None else "—",
            s["best_SAFE_method"] or "—",format(s["peak_upper_C"],".5f") if s["peak_upper_C"] else "—",s["G2_status"] or s["status"]))
    clues=[s["case"] for s in summary if s["certified_hot_clues"]]
    out+=["","## 热约束对节能的影响","",
          "同一工况中出现通过非热约束检查、连续认证超温且包含节能目标或低于最佳已知 SAFE 能耗的候选工况为"+joined(clues)+"。"
          +"热安全最优能耗代价的可靠上下界逐行列于 `summary.csv`。"]
    for r in pairrows: out.append(f"\n{r['case']} 局部四 Stage 的 Δθ 区间为 [{r['delta_lower_J']:.6f}, {r['delta_upper_J']:.6f}] J。")
    out+=["","局部结论仅覆盖首个场景边界两侧选中的 main 及其 post。区间包含零时，联合域减少热安全代价的判断未决。"]
    if resets:
        flips=sum(r["continuous"]!=r["reset"] for r in resets)
        ranks=sum(r["continuous_energy_rank"]!=r["reset_energy_rank"] for r in resets)
        out += [f"\n共回放 {len(resets)} 个不同最终时间表。场景边界重置使 {flips} 个时间表改变安全判定，{ranks} 个改变工况内能耗名次。各方案的热点、峰温与能耗见 `certificates/reset_comparison.csv`。"]
    out+=["","## 时热关联机制与立项","",
          "同规模普通邻域对照、实际热关联 Stage 变化及严格完整窗口节能同时成立的工况为"+joined(reached)+"。",
          "全窗两项对照均达到 1% 门槛的工况为"+joined(threshold)+"。",
          "达到两工况且含留出的立项门槛。" if approved else "本轮未达到“至少两个工况且含一个留出工况”的立项门槛。时热联合算法价值仍未证实。","",
          "## 证据边界","",
          "可靠下界使用 20–100°C 内每节点最低合法基准、每个 Stage 最低合法增量及外部公共能耗。省略切换和竞争成本使该界保持保守。全局最优性只在上下界闭合时成立。表中空值表示没有相应证据。"]
    if not any(gates[c] for c in ["H1","H2","H3"]):
        out+=["","开发阶段未取得允许开启留出验证的机制结果，H1–H3 仅生成固定输入。"]
    (ROOT/"decision.md").write_text("\n".join(out)+"\n",encoding="utf8")
    for folder in set(FOLDERS.values())|{"certificates"}:
        if not (ROOT/folder).exists() or not any((ROOT/folder).iterdir()):
            dump(folder+"/status.json",dict(status="NOT_RUN",reason="gate or upstream stop"))
    dump("manifest.json",dict(freeze_commit=git("rev-parse","HEAD").decode().strip(),
       history_base=CFG["base"],edge_commit=CFG["edge_commit"],seeds=CFG["seeds"],threads=1,
       python=sys.version,platform=platform.platform(),dependencies={k:version(k) for k in ("numpy","scipy","numba","sympy","llvmlite","threadpoolctl")},
       configured_budget_s=16620,wall_limit_s=18000,reserved_calls_s=sum(c["budget_s"] for c in starts),
       calls=len(starts),safe_certificates=len([x for x,z in evidence.values() if x["status"]=="SAFE"]),
       archive="logs/calls.jsonl records completion of the audit; result bytes bound by RESULT_SHA256.json and result Git commit"))
