"""Apply the predeclared flow-level decision and render the Chinese confirmation report."""
import json
from collections import Counter
from pathlib import Path

from lane import CASES
ROOT=Path(__file__).resolve().parent
LABEL={"win":"简化版较低","overlap":"区间重叠","loss":"简化版较高","unpaired":"无可靠配对"}


def n(value,digits=5):
    return "—" if value is None else f"{value:.{digits}f}"


def table(header,rows):
    return ["|"+"|".join(header)+"|","|"+"|".join("---" for _ in header)+"|",
            *["|"+"|".join(map(str,row))+"|" for row in rows]]


def report(cells,flows,pairs,costs):
    buckets={p:[r for r in pairs if r["pair"]==p] for p in ("C-A","D-B","D-A")}
    cross=buckets["D-A"]
    reliable={a:{c for c in CASES if flows[c,a]["reliable"]} for a in "ABCD"}
    missed=sorted(reliable["A"]-reliable["D"])
    losses=[r for r in cross if r["strict"]=="loss"]
    uncertain=[r for r in cross if r["strict"]=="overlap" and r["new_J"]>r["old_J"]]
    if not reliable["A"]:
        status="insufficient"
        decision="原版 60 秒未形成可靠成功的参照流，本轮不足以确认替代。"
    elif missed:
        status="retain"
        decision="保留原冻结算法。简化版在 600 秒内未覆盖原版 60 秒可靠成功的全部任务流。"
    elif losses or uncertain:
        status="user_decision"
        decision="简化版覆盖了原版 60 秒可靠成功的全部任务流，但有任务流的中位能耗较高。按任务书单列差额，由用户决定是否接受。"
    else:
        status="freeze_center"
        decision="十二流最终确认通过。在允许增加求解时间的条件下，采用解析能耗并只保留负载均衡中心，冻结该配额生成机制，结束三点拟合与专用锚点的简化研究。"
    receipt=dict(decision=status,reliable_rule="at least two on-time SAFE endpoints in three cold repetitions",
                 coverage={a:sorted(v) for a,v in reliable.items()},missing_original_reliable=missed,
                 cross_strict_losses=[r["case"] for r in losses],cross_higher_estimate_with_overlap=[r["case"] for r in uncertain],
                 original="798f5586acedf0936e2786e1ca226992fab7a0ac",analytic="bc584198913484590ee175ffa7ca001ab37de72d",
                 center="b2012871943c01497cb81ecfc677cab43973b695",model="be641ce06a4f496d2b1f233a09bdfc3776738668",
                 frozen_quota_source=("research/ch3_center_only/simplified.py" if status=="freeze_center" else None),
                 formal_units=len(cells),charged_core_s=sum(r["charged_s"] for r in cells))
    (ROOT/"decision.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    lines=["# 第三章配额生成结构简化：十二流最终确认","",f"**{decision}**",""]
    lines+=table(["比较（简化版相对原版）","共同可靠流","严格较低／重叠／严格较高","逐流能耗变化范围"],[
        [name,sum(r["strict"]!="unpaired" for r in buckets[p]),
         "／".join(str(sum(r["strict"]==state for r in buckets[p])) for state in ("win","overlap","loss")),
         " 至 ".join(n(func([r["delta_pct"] for r in buckets[p] if r["delta_pct"] is not None],default=None),4)+"%" for func in (min,max))]
        for p,name in (("C-A","60 秒对 60 秒"),("D-B","600 秒对 600 秒"),("D-A","600 秒对 60 秒"))])
    lines+=["","正差表示简化版耗能更多。前两行在相同时间下比较完整算法。第三行回答多给简化版求解时间能否保持最终质量，包含额外时间带来的收益。只有两方能耗认证区间严格分离才判高低；区间重叠单列。","",
            "## 安全覆盖与重复稳定性","",
            "每条流三次独立运行，至少两次在截止前交付 SAFE 才算可靠。各流能耗与上下界分别取成功重复的中位数。空缺表示覆盖不足。",""]
    names={"A":"原版 60 秒","B":"原版 600 秒","C":"仅中心 60 秒","D":"仅中心 600 秒"}
    cover=[]
    for a,name in names.items():
        rr=[r for r in cells if r["setting"]==a]
        fs=[flows[c,a] for c in CASES]
        valid=[r for r in rr if r["final_J"] is not None]
        cover.append([name,f"{len(valid)}/36",f"{len(reliable[a])}/12",sum(x["all_three"] for x in fs),
                      sum(x["all_three"] and x["unique_plans"]==1 for x in fs),
                      sum(x["all_three"] and x["unique_mappings"]==1 for x in fs),
                      n(max((x["range_pct_of_median"] for x in fs if x["safe"]>=2),default=None),4),
                      n(max((r["peak_upper_C"] for r in valid),default=None),3),
                      n(min((r["min_slack_ms"] for r in valid),default=None),3)])
    lines+=table(["设置","SAFE 次数","可靠流","三次全成功流","三次排程相同流","三次设备映射相同流","最大流内能耗极差／中位数（%）","最高峰温上界（°C）","最小期限余量（ms）"],cover)
    lines+=["","## 逐流能耗与采用条件","",
            "表中能耗单位为 J，采用比较以原版 60 秒为分母。同为 600 秒的差距独立列出。每格的成功数、两侧认证界、三次极差和排程身份见原始表。",""]
    detail=[]
    for c in CASES:
        x={p:next(r for r in bucket if r["case"]==c) for p,bucket in buckets.items()}
        detail.append([c,*[n(flows[c,a]["final_J"]) if flows[c,a]["reliable"] else "—" for a in "ABCD"],
                       n(x["D-A"]["delta_pct"],4),n(x["D-B"]["delta_pct"],4),LABEL[x["D-A"]["strict"]]])
    lines+=table(["任务流","原版 60 秒","原版 600 秒","简化 60 秒","简化 600 秒","简化 600 对原版 60（%）","同为 600 秒（%）","采用比较"],detail)
    selection=[(pair,r) for pair in ("C-A","D-B","D-A") for r in buckets[pair] if r["strict"]=="loss" or r in uncertain]
    lines+=["","## 能耗退化与重复一致性",""]
    if selection:
        lines+=table(["比较","流","简化多耗（J）","多耗（%）","三次同编号重复：低／重叠／高／缺"],[
                     [p,r["case"],n(r["delta_J"]),n(r["delta_pct"],4),"／".join(str(r["repeat_"+s]) for s in ("win","overlap","loss","unpaired"))]
                     for p,r in selection])
    else:
        lines+=["三种比较均未出现可靠中位数的严格退化。"]
    lines+=["","同编号重复的严格胜负刻画波动。流级判定仍使用三次成功结果的中位数，逐次严格胜负不作多数表决。设备映射以每个请求的 GPU/NPU 选择为准，完整排程还包括频档等状态。","",
            "## 实际算法开销","",
            "下表是各设置全部 36 次的算术平均秒数，含未成功运行。认证时间包括搜索内认证和调频后认证。构造、认证、调频及其他项分别记账。",""]
    lines+=table(["设置","实际计费","实例","构造","搜索认证","提名","交接","普通调频核","温度修正调频核","调频后认证","其余"],[
        [names[r["setting"]],*[n(r[k],3) for k in ("mean_charged_s","instance_s","construct_s","search_cert_s","selection_s","handoff_s","ordinary_DP_s","thermal_DP_s","dp_cert_s","other_s")]] for r in costs])
    lines+=["","实际开销为单核端到端经过时间。截止时正在进行的构造和认证按可观察边界截断。调频内核只计已返回的计时记录，无法拆出的启动、日志、未完成内核等列入其余。分析、压缩与校验在各格时钟结束后进行。","",
            "## 已认证能耗随求解时间的变化","",
            "每条曲线从三次中第二次成功交付 SAFE 的时刻开始。每个时刻使用当时已经交付的安全端点取中位数；第三次首次交付时参与中位数的样本数会变化。原始逐次曲线数据保留具体时间、排程和映射。","",
            "![60 秒预算](energy_60s.png)","","![600 秒预算](energy_600s.png)","",
            "## 简化前后算法结构",""]
    lines+=table(["环节","原完整第三章","仅中心简化版"],[
        ["候选起点","均衡中心，加上沿均衡线的远点和按非共线条件构造的侧点","只预留原负载均衡中心"],
        ["配额排序的能耗系数","三个锚点预重放后解三元线性方程","从设备画像直接取各任务类型的增量能耗系数"],
        ["其余候选","容量整数切片，按能耗、负载和配额距离补充；原候选补位","同一切片、顺序、距离、槽位数及补位规则"],
        ["热预测","末窗专用锚点 50 ms 功率矩按时长合并成 250 ms","统一直接计算 250 ms 功率矩"],
        ["最终求解与接纳","时序重放、跨场景状态继承、束搜索、终端排序、多映射提名、超温映射处理、全局调频、温度修正及连续认证","复用原完整算法的这些环节"]])
    lines+=["","两版均从空排程开始。每条流使用同一运行机和同一逻辑核，四种设置的顺序随流及重复轮换。60 秒和 600 秒分别按 55+5、595+5 分配；分界前无 SAFE 时搜索可用至总截止点。每个设置按实际截止交付计分。","",
            f"本轮 {len(cells)} 个正式单元实际计费 {receipt['charged_core_s']:.3f}／47,520 核秒。原版、解析替代、仅中心和物理模型的不可变提交见[决策记录](decision.json)。","",
            "[逐流及区间](tables/flows.csv) · [中位数配对](tables/median_pairs.csv) · [逐次配对](tables/repeat_pairs.csv) · [逐次能耗、认证与计时](tables/cells.csv) · [重复间排程与映射](tables/repeat_identities.csv) · [逐请求映射及频档变化](tables/mapping_changes.csv) · [开销汇总](tables/overheads.csv) · [逐次能耗更新时间](tables/improvements.csv) · [完整物理档案](lanes)","",
            "每条流的 SHA256SUMS 对应运行时归档。每个重复目录的 final_endpoints.tar.gz 提供其最终 SAFE 排程、证书和完整 31 列轨迹。重复目录下 paired_results 中每个记录的计划哈希均可借助[还原程序](../ch3_mapping_first_nested/restore_plan.py)从同目录的 physical 索引恢复，包括未接纳的超温方案。"]
    (ROOT/"REPORT_zh.md").write_text("\n".join(lines)+"\n",encoding="utf8")
