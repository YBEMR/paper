"""Write the Chinese decision report from audited independent and within-run comparisons."""
import statistics as st
from analyze import main,ROOT


def fmt(x, n=3):
    return "—" if x is None else f"{x:.{n}f}"


def median(rows,k):
    vals=[r[k] for r in rows if r.get(k) is not None]
    return st.median(vals) if vals else None


def render():
    s,rows,maps,flows=main()
    arms=[("single","首轮单映射"),("multi","最多四映射")]
    subsets={a:[r for r in rows if r["version"]==a] for a,_ in arms}
    multi=subsets["multi"]
    cases=[f["case"] for f in flows if f["additional_wins"]>=2]
    winners=[r for r in multi if r["strict_extra"]]
    decision="建议采用多映射集成版" if s["adopt"] else "建议保留首轮单映射集成版"
    out=["# 第三章第二轮集成优化决策报告","",f"**{decision}。** 单映射与多映射端到端可靠覆盖分别为 {s['reliable']['single']}/12 和 {s['reliable']['multi']}/12。在 {s['common']} 条共同可靠流上，多映射相对单映射平均节能 {fmt(s['mean_pct'],4)}%，平均每流节省 {fmt(s['mean_J'],6)} J。同次第一映射完成后，额外映射在 {len(winners)}/36 次运行获得严格追加节能，达到同一流至少两次重复标准的有 {len(cases)} 条。","",
    "## 两个完整算法的等预算比较","","每次从空排程开始。可靠覆盖要求三次中至少两次按时交付 SAFE。表内先分别取成功重复的能耗及证书上下界中位数，再逐流等权汇总。正值表示多映射节能。","",
    "| 任务流 | SAFE 次数 单／多 | 单映射 J | 多映射 J | 差值 J | 节能率 % | 区间判定 | 同次追加次数 | 同次追加中位 J |","|---|---:|---:|---:|---:|---:|---|---:|---:|"]
    names=dict(win="多映射胜",loss="单映射胜",tie="重叠",unpaired="未配对")
    for f in flows:
        out.append(f"| {f['case']} | {f['single_safe']}／{f['multi_safe']} | {fmt(f['single_J'],6)} | {fmt(f['multi_J'],6)} | {fmt(f['gain_J'],6)} | {fmt(f['gain_pct'],4)} | {names[f['strict']]} | {f['additional_wins']} | {fmt(f['median_extra_J'],6)} |")
    c=s["rep_outcomes"]
    out+=["",f"按重复序号直接配对，严格胜 {c.get('win',0)} 次、区间重叠 {c.get('tie',0)} 次、严格负 {c.get('loss',0)} 次、未配对 {c.get('unpaired',0)} 次。这组差值包含独立构造运行之间的差异。","",
    "## 同一次构造下的映射贡献","",f"多映射版按时取得首映射完整两阶段端点 {sum(r['anchor_J'] is not None for r in multi)}/36 次。实际提名 {sum(r['nominated'] for r in multi)} 个映射，启动 {sum(r['started'] for r in multi)} 个，完整结束两阶段 {sum(r['completed'] for r in multi)} 个。按时交付的普通阶段结果也可进入最终在位解。重复出现追加收益的工况为{'、'.join(cases) if cases else '无'}。","",
    "| 任务流 | 不同 SAFE 映射数范围 | 完成／提名映射总数 | 胜出映射的原提名序号（三次） | 相同胜出映射重复次数 |","|---|---:|---:|---|---:|"]
    for f in flows:
        rr=sorted([r for r in multi if r["case"]==f["case"]],key=lambda r:r["rep"])
        sizes=[r["distinct_maps"] for r in rr]
        out.append(f"| {f['case']} | {min(sizes)}–{max(sizes)} | {sum(r['completed'] for r in rr)}／{sum(r['nominated'] for r in rr)} | {'、'.join(str(r['best_rank'] or '—') for r in rr)} | {f['same_winning_mapping']} |")
    mm=[p for p in maps if p["version"]=="multi" and p["complete"]]
    out+=["","下表将每个提名映射与自身的父排程比较。普通阶段取原映射到普通在位解的变化，温度阶段取普通在位解到温度修正后在位解的变化。每行仅汇总该提名序号的已完成映射。","",
          "| 提名序号 | 完成数 | 普通阶段平均节省 J | 温度阶段平均追加 J | 最终严格取代首映射的次数 |","|---:|---:|---:|---:|---:|"]
    for i in range(1,5):
        group=[p for p in mm if p["rank"]==i]
        out.append(f"| {i} | {len(group)} | {fmt(st.mean(p['ordinary_gain_J'] for p in group) if group else None,6)} | {fmt(st.mean(p['thermal_gain_J'] for p in group) if group else None,6)} | {sum(r['best_rank']==i for r in winners)} |")
    if winners:
        r=max(winners,key=lambda r:r["extra_J"])
        out+=["",f"最大同次追加见证发生于 {r['case']} 第 {r['rep']} 次运行。首映射完成后为 {r['anchor_J']:.6f} J，原排第 {r['best_rank']} 的映射将最终认证能耗降至 {r['J']:.6f} J，追加节省 {r['extra_J']:.6f} J。最终峰温上界 {r['peak']:.3f} °C，最小期限余量 {r['slack']:.3f} ms。两个端点及全部提名轨迹见逐次与映射表。"]
    out+=["","## 交付与计算代价","","| 版本 | 首次 SAFE 中位 s | 最优交付中位 s | 全过程均值 s | 峰温最高 °C | 最小期限余量 ms | 切换数中位 |","|---|---:|---:|---:|---:|---:|---:|"]
    for a,label in arms:
        rr=subsets[a];good=[r for r in rr if r.get("status")=="SAFE"]
        out.append(f"| {label} | {fmt(median(rr,'first_safe_s'))} | {fmt(median(rr,'final_best_delivered_s'))} | {fmt(st.mean(r['charged_s'] for r in rr))} | {fmt(max((r['peak'] for r in good),default=None))} | {fmt(min((r['slack'] for r in good),default=None))} | {fmt(median(rr,'switches'),1)} |")
    out+=["","各项为每次运行的平均秒数。搜索认证含重放与原生证据写入，调频认证含物理事件构造及证据写入。其余含监督、时序检查、日志及被截止打断的未归类时间。","",
    "| 版本 | 实例 | 构造 | 搜索认证 | 登记排序 | 交接 | 已完成 DP | 调频认证 | 其余 |","|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a,label in arms:
        rr=subsets[a]
        cols=[fmt(st.mean(r[k] for r in rr)) for k in ("instance_s","construct_s","search_cert_evidence_s","selection_s","handoff_s","dp_s","dp_cert_evidence_s","other_s")]
        out.append("| "+label+" | "+" | ".join(cols)+" |")
    overhead=st.mean(r["charged_s"] for r in multi)-st.mean(r["charged_s"] for r in subsets["single"])
    out+=["",f"多映射每次平均增加 {overhead:.3f} 秒。映射数与收益来自同一批既有十二流，结论适用于本轮构造器、提名规则和 60 秒预算。排名反转表示原始认证能耗排序在固定映射调频后发生变化。其出现频率及获益工况见上表。","",
    "## 预算与复核","",f"正式运行 {len(rows)} 次，合计 {s['charged_s']:.3f}／4320 核秒。独立预检含预热 {s['gate_s']:.3f} 秒，各流通用预热合计 {s['warm_s']:.3f} 秒，离线物理归档 {s['offline_pack_s']:.3f} 秒，终审 {s['audit_s']:.3f} 秒。按流去重后逐一核验了 {s['physical']:,} 份物理排程、连续证书与可无损重建的 31 列轨迹。每流六次运行的核心、主机与轮换顺序在各自的 lane.json 中。","",
    f"正式计算源码提交 `{s['source']}`。单份物理证据可用 `python pack.py 工况 排程SHA 新目录` 恢复。","",
    "[协议](PROTOCOL.md) · [逐流配对](tables/flows.csv) · [逐次能耗、物理量与时间](tables/runs.csv) · [同序号配对](tables/paired_repeats.csv) · [全部 SAFE 映射](tables/safe_pool.csv) · [映射排名与反转](tables/mappings.csv) · [各阶段原始与接纳结果](tables/stages.csv) · [证据目录](archive) · [校验清单](SHA256SUMS)",""]
    (ROOT/"REPORT_zh.md").write_text("\n".join(out))


if __name__=="__main__":
    render()
