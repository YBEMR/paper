"""Render the independent, within-run and offline comparisons separately."""
import json
import statistics as st
from collections import Counter
from analysis import main,ARC,TAB,ROOT,read


def fmt(x,n=6):
    return "—" if x is None else f"{x:.{n}f}"


def render():
    s,rows,flows,wits,opps=main()
    matched=[r for r in opps if r["matched"]]
    losses=Counter(r["case"] for r in matched if r["same_pre4"] and (r["loss_after_hot_J"] or 0)>0)
    repeated_cost=[c for c in s["loss_flows"] if losses[c]>=2]
    adopt=bool(s["repeatable"] and s["coverage"][1]>=s["coverage"][0] and s["mean_pct"] is not None and s["mean_pct"]>0 and not repeated_cost)
    s.update(adopt=adopt,repeated_matched_cost=repeated_cost)
    (TAB/"decision.json").write_text(json.dumps(s,indent=2)+"\n")
    wins=[r for r in wits if r["hot_win"]]
    new=[r for r in rows if r["arm"]=="hot"];control=[r for r in rows if r["arm"]=="multi"]
    def frac(group,k):return sum(bool(r[k]) for r in group)
    def med(rr,k):
        data=[r[k] for r in rr if r[k] is not None]
        return st.median(data) if data else None
    def mean(rr,k):return st.mean(r[k] for r in rr)
    o=frac(wits,"recovered");n=sum(r["ordinary_status"]=="SAFE" for r in wits);t=sum(r["thermal_status"]=="SAFE" for r in wits)
    fresh=sum(r["ordinary_status"]!="SAFE" and r["thermal_status"]=="SAFE" for r in wits)
    lost=sum(r["ordinary_status"]=="SAFE" and r["thermal_status"]=="HOT" for r in wits)
    hist=read(ARC/"history/gate.json")
    decision="采用条件开放超温映射的第三轮版本" if adopt else "保留第二轮四安全映射版本"
    text=["# 第三章第三轮集成优化决策报告","",f"**建议{decision}。** 在相同 60 秒预算下，当前版与再评价版的可靠覆盖分别为 {s['coverage'][0]}/12、{s['coverage'][1]}/12。{s['common']} 条共同可靠流的等权平均节能率为 {fmt(s['mean_pct'],4)}%，每流平均节省 {fmt(s['mean_J'])} J。在线 HOT-only 映射在 {len(wins)} 次运行实际取代安全在位解，同流至少两次复现的工况为{'、'.join(s['repeatable']) or '无'}。","",
        "## 独立完整算法比较","","每次从空排程开始，三次至少两次按时取得 SAFE 记为可靠覆盖。正的节能率以当前四安全映射版本为分母，按流取成功重复中位，再将各流等权平均。严格比较使用证书上下界。","",
        "| 任务流 | SAFE 次数 当前／新 | 当前版 J | 再评价版 J | 节省 J | 节能率 % | 严格判定 | HOT 提名／胜出 |","|---|---:|---:|---:|---:|---:|---|---:|"]
    names=dict(win="新版胜",tie="区间重叠",loss="当前版胜",unpaired="未配对")
    for r in flows:
        text.append(f"| {r['case']} | {r['current_safe']}／{r['new_safe']} | {fmt(r['current_J'])} | {fmt(r['new_J'])} | {fmt(r['gain_J'])} | {fmt(r['gain_pct'],4)} | {names[r['strict']]} | {r['online_nominations']}／{r['hot_wins']} |")
    p=s["paired"]
    text+=["",f"按重复序号配对，严格胜 {p.get('win',0)} 次、重叠 {p.get('tie',0)} 次、严格负 {p.get('loss',0)} 次、未配对 {p.get('unpaired',0)} 次。这些结果包含独立构造的差异。","",
        "## 超温映射在线恢复与第四位置的代价","",f"36 次新版本运行中，{sum(r['hot_only']>0 for r in new)} 次出现 HOT-only 映射，{len(wits)} 次提名，{frac(wits,'hot_started')} 次实际开始处理。普通调频交付 SAFE {n} 次，温度修正交付 SAFE {t} 次，其中首次在温度步恢复 {fresh} 次；两个阶段合计有 {o} 个提名曾获 SAFE。普通 SAFE 而温度步再次 HOT 有 {lost} 次。最终实际取代前三个安全映射端点 {len(wins)} 次。","",
        "| 任务流／重复 | 普通调频 | 温度修正 | 同次前三名 J | 最终 J | 同次追加 J | 可匹配的被换第四安全映射所能额外节省 J |","|---|---|---|---:|---:|---:|---:|"]
    for r in wits:
        op=next(o for o in opps if (o["case"],o["rep"])==(r["case"],r["rep"]))
        text.append(f"| {r['case']}／{r['rep']} | {r['ordinary_status'] or '未交付'} | {r['thermal_status'] or '未交付'} | {fmt(r['pre4_J'])} | {fmt(r.get('J'))} | {fmt(r['extra_J'])} | {fmt(op['forgone_positive_gain_J'])} |")
    text+=["",f"被替换第四安全映射的原始物理计划在独立对照中精确匹配且两阶段完成 {len(matched)}/{len(opps)} 次。可匹配部分中，原第四安全映射能严格改善新版前三名端点 {sum((r['forgone_positive_gain_J'] or 0)>0 for r in matched)} 次，能严格胜过新版最终解 {sum((r['loss_after_hot_J'] or 0)>0 for r in matched)} 次。未匹配时机会成本保留缺失值。身份相同的离线对读能量机会与 60 秒中是否来得及交付分别记录。",""]
    if wins:
        w=max(wins,key=lambda r:r["extra_J"])
        text+=[f"最大在线见证为 {w['case']} 第 {w['rep']} 次。原 HOT 排程 `{w['eligible_plan']}`，同次前三映射在位解 {fmt(w['pre4_J'])} J，最终 {fmt(w['J'])} J，追加 {fmt(w['extra_J'])} J。最终证书为 `{w['plan']}`，峰温上界 {fmt(w['peak'],3)} °C，最小期限余量 {fmt(w['slack'],3)} ms。",""]
    text+=["## 求解时间、物理指标与预算","","| 版本 | 首次 SAFE 中位 s | 最优交付中位 s | 全程均值 s | 提名／启动／完成映射 | 最高峰温 °C | 最紧期限余量 ms |","|---|---:|---:|---:|---:|---:|---:|"]
    for label,rr in (("当前版",control),("再评价版",new)):
        safe=[r for r in rr if r["status"]=="SAFE"]
        text.append(f"| {label} | {fmt(med(rr,'first_safe_s'),3)} | {fmt(med(rr,'final_best_s'),3)} | {fmt(mean(rr,'charged_s'),3)} | {sum(r['nominated'] for r in rr)}／{sum(r['started'] for r in rr)}／{sum(r['complete'] for r in rr)} | {fmt(max((r['peak'] for r in safe),default=None),3)} | {fmt(min((r['slack'] for r in safe),default=None),3)} |")
    text+=["",f"新版全程平均耗时变化 {mean(new,'charged_s')-mean(control,'charged_s'):+.3f} 秒，登记筛选平均耗时分别为 {mean(control,'selection_s'):.3f} 和 {mean(new,'selection_s'):.3f} 秒。逐次账本含实例、构造、搜索认证、交接、调频、调频认证及其余开销。","",
        "## 历史门槛与归档","",f"历史来自第二轮五流第一次多映射运行。{hist['distinct']} 个不同 HOT-only 映射进入离线诊断，其中 {len(hist['witnesses'])} 个满足在线规则且严格胜过同批历史四映射终点。核验重试计入后的历史诊断用时 {hist['total_s']:.3f}／120 核秒。正式运行 {len(rows)} 次，共 {s['charged_s']:.3f}／4320 核秒。各流通用预热合计 {s['warm_s']:.3f} 秒、归档 {s['pack_s']:.3f} 秒。正式按流去重核对了 {s['physical']:,} 份真实排程、连续证书和 31 列温度事件轨迹。","",
        f"正式计算提交 `{s['source']}`。结论限于已登记十二流、55 秒构造和 60 秒总预算；提名阈值仅用于决定第四位置。","",
        "[预登记](PROTOCOL.md) · [历史诊断](HISTORY_zh.md) · [逐流配对](tables/flows.csv) · [逐次能耗与计时](tables/runs.csv) · [全部候选身份](tables/mapping_identity.csv) · [各阶段证书](tables/stages.csv) · [HOT 转 SAFE 记录](tables/hot_witnesses.csv) · [第四位置机会成本](tables/fourth_opportunity.csv) · [完整物理证据](archive) · [SHA-256](SHA256SUMS)",""]
    (ROOT/"REPORT_zh.md").write_text("\n".join(text))

if __name__=="__main__":
    render()
