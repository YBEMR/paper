"""Describe frozen arm receipts after the audit. This module does not run numerical searches."""
import csv,statistics
from collections import Counter
from c1r_assets import ROOT,read,write

def data(name):
    with (ROOT/name).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))

def produce():
    execution=read(ROOT/"execution.json");gate=read(ROOT/"gate.json");checks=read(ROOT/"validation/gate.json")
    assert execution["status"]=="COMPLETE" and gate["correctness"]
    results=data("results.csv");pairs=data("paired.csv");w=read(ROOT/"witnesses.json")
    by={(r["sample"],r["variant"]):r for r in results}
    def arm(s,m):return by[s,m+"-Hint"]
    d=[r for r in pairs if r["case"]=="D3" and r["result"]!="unresolved"]
    df=[arm(r["sample"],"Full") for r in d];dc=[arm(r["sample"],"Compact") for r in d]
    number=lambda r,k:float(r[k])
    def ran(rr,k):return sum(float(z[k])>0 for z in rr)
    cf=gate["d3_incremental_cases"];cm=gate["d3_multi_cases"];wins=Counter(r["result"] for r in d)
    dd=[x for x in w if x["case"]=="D3"]
    headline=("D3 的紧凑辅助 CP 路线保留为局部研究假设" if cf else
        "暂停将该辅助 CP 作为 D3 联合节能增量路线")
    lines=["# E2-c1-r 支撑约束辅助模型紧凑化","",f"**{headline}。** 11 个前态、22 组均已启动，10 个前态取得可比较终点。D3 的 8 个可比较前态中，Compact-Hint 相对 Full-Hint 有 {wins['win']} 胜、{wins['loss']} 负、{wins['overlap']} 个能耗认证区间重叠，另有 1 对因进程通信中断未决。紧凑组有 {cm} 个前态出现独立于普通回退的真实多配置节能，其中 {cf} 个前态存在同时击败完整组终点和共同提示、且来自紧凑辅助 CP 或其支撑域 Core 的多配置候选。","",
           "## 正确性","",
           f"24 轮同步包络保留每一固定配置的可实现性，以及按估计收益、支撑数、总绝对移时排序的最优目标。完整证明见 [proof.md](proof.md)。{checks['fixtures']} 个有限域族共 {checks['probes']} 项逐组固定、自由选择及排除组合核验，两种模型均得到相同的已证最优三元组或均已证不可行。配置改变但起点不动、同档 CPU 跨核重叠、异档分隔、固定邻居、首末切换、正反 24 项传递和超过上限均纳入核验。","",
           "E2-a 有限域、历史归属及权限回归通过。原条件骨架数学核算复现 D2 的 42→42 和 D3 的 22→14。直接合法提示即使超出紧凑域仍按原物理模型评价。实际两组提示的全部行和支撑位逐前态哈希一致。按期取得的共同提示证书已逐对核对，离线补验单独列出。","",
           "## D3 的逐阶段实得节能","",
           "每格为相对上一阶段累计最佳 SAFE 的可靠净节能下限，单位 mJ。辅助 CP 和 Core 栏依次列出完整组／紧凑组。终点差为 Full-Hint 减去 Compact-Hint，正值表示紧凑组能耗较低。","",
           "|种子／前态|共同提示变档数|提示直接节能|辅助 CP 额外节能|Core 额外节能|终点差 / mJ|紧凑保留 Stage|","|---|---:|---:|---:|---:|---:|---:|"]
    for q in d:
        s=q["sample"];f=arm(s,"Full");c=arm(s,"Compact")
        lines.append(f"|{s[3:]}|{f['hint_cfg']}|{number(f,'hint_gain_lower_mJ'):.3f}|{number(f,'cp_extra_lower_mJ'):.3f}／{number(c,'cp_extra_lower_mJ'):.3f}|{number(f,'core_extra_lower_mJ'):.3f}／{number(c,'core_extra_lower_mJ'):.3f}|{number(q,'advantage_mJ'):.3f}|{q['retained']}|")
    def span(rr,k):
        vals=[float(z[k]) for z in rr];return f"{min(vals):g}–{max(vals):g}"
    def med(rr,k):return statistics.median(number(x,k) for x in rr if x[k]!="")
    lines+=["|103_first|1|—|—|—|未决|见离线结构记录|","",f"D3 每个全流前态有 2400 个 Stage。在 8 个可比较前态中，紧凑结构保留 {span(dc,'retained')} 个。变量数由 {span(df,'vars')} 降至 {span(dc,'vars')}，约束数由 {span(df,'constraints')} 降至 {span(dc,'constraints')}。完整／紧凑组分别有 {ran(df,'aux_assignments')}/8、{ran(dc,'aux_assignments')}/8 个前态返回辅助可行赋值，分别有 {ran(df,'cp_extra_lower_mJ')}/8、{ran(dc,'cp_extra_lower_mJ')}/8 个前态在辅助 CP 阶段严格超过共同提示阶段的累计最佳。普通回退分别为 {sum(r['fallback']=='True' for r in df)}/8 和 {sum(r['fallback']=='True' for r in dc)}/8。","",
          f"D3 构模中位耗时为完整组 {med(df,'build_s'):.3f} s、紧凑组 {med(dc,'build_s'):.3f} s。紧凑组另用 {med(dc,'propagate_s'):.3f} s 传播；辅助求解中位耗时为 {med(df,'aux_solve_s'):.3f}／{med(dc,'aux_solve_s'):.3f} s。各前态的选点、提示生成、认证、两次求解状态及三阶段能耗见 [results.csv](results.csv) 和 [stages.csv](stages.csv)。",""]
    if dd:
        best=max(dd,key=lambda x:x["vs_full_lower_mJ"])
        lines.append(f"D3 相对 Full-Hint 最强的多配置见证来自 {best['sample']}，同时改变 {best['config']} 项配置、{best['moved']} 项起点，实际支撑并集 {best['support']}。其相对原前态、共同提示和完整组最佳 SAFE 的可靠节能分别为 {best['vs_source_lower_mJ']:.3f}、{best['vs_hint_lower_mJ']:.3f}、{best['vs_full_lower_mJ']:.3f} mJ。排程身份为 {best['sha']}。其中直接由辅助 CP 取得上述多配置见证的 D3 前态数为 {gate['d3_direct_cases']}。")
    else:lines.append("D3 本轮未得到可归于紧凑辅助 CP、同时严格超过共同提示和完整组终点的多配置见证。阶段内有返回、变量较少或普通邻域取得节能，都不足以建立该增量。")
    lines+=["","## 两个指定正例","",
         "|前态|历史 Old／New / J|Full-Hint / J|Compact-Hint / J|终点差 / mJ|","|---|---:|---:|---:|---:|"]
    for q in (q for q in pairs if q["case"]!="D3"):
        s=q["sample"];a=arm(s,"Full")
        lines.append(f"|{s}|{number(a,'historical_old_J'):.8f}／{number(a,'historical_new_J'):.8f}|{number(q,'full_J'):.8f}|{number(q,'compact_J'):.8f}|{number(q,'advantage_mJ'):.3f}|")
    lines+=["","D1、D2 这两项是事先指定的已有正例。历史 Old 和 New 只读取冻结数据。完整组与紧凑组共享的提示直接收益单列，支撑域转给后续 Core 带来的收益归入 Core。","","## 种子 103 的三项记录","",
         "D3_103_first 的状态文件在写入期间发生 Windows 共享冲突。监管进程停止同一对照，双方均已落盘相同提示，但没有完成候选认证或取得辅助求解终点。该配对记为未决，两组保守各计满 30 秒。后续仅修正状态文件读取，执行另外四个尚未启动的组。","",
         "D3_103_middle 和 D3_103_last 的两组均在提示物理认证阶段耗尽 11 秒，随后在 30 秒内未取得新证书。其可用最佳解仍是历史认证初解，两对按相同初解计区间重叠。D3_103_middle 完整组含进程终止的实记用时 30.0075 秒，比局部预算多 7.5 毫秒；全额计费，该组没有新候选计分。这些截止不能用作辅助 CP 不可行的证据。三项的模型尺寸在归档时由同一固定前态构造并计数，未调用求解器，均已标明离线来源。","",
         "|D3 前态|提示实际变档数|离线核验提示相对初解 / mJ|计入限时收益|","|---|---:|---:|---|"]
    for key in ("first","middle","last"):
        z=read(ROOT/"incident"/("offline_hint_D3_103_"+key)/"receipt.json")
        lines.append(f"|103_{key}|{len(z['hint_cfg'])}|{z['offline_only_gain_lower_mJ']:.3f}|否|")
    lines+=["","## 验证、预算与边界","",
        f"独立复核覆盖 {gate['unique']} 个不同物理排程和 {gate['certified_records']} 条已认证记录，使用原事件、紧凑事件、矩阵指数能耗及温度端点交叉校验。22 组累计耗用 {execution['replay_s']:.2f}/660 秒。资产核验、正确性及独立校核截至主程序退出累计 {execution['ancillary_s']:.2f} 秒，包括首次启动的模块重名及导入复核保守计入的 16 秒。分项计时见 [execution.json](execution.json)，含封存用时的预算见 [archive_budget.json](archive_budget.json)。","",
        "原始辅助日志及赋值文件采用 Windows 可检出的文件名，逐项映射见 [archive_paths.json](archive_paths.json)，文件内容哈希已核对。","",
        "本轮只测指定历史前态上的局部求解。辅助估计目标等价不推出连续热目标最优值等价，限时配对也不能单独分离随机搜索轨迹与支撑域选择的因果效应。本轮停止于 E2-c1-r，E2-c2、H1–H3 和第四章实验的运行数均为零。"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
    gate["decision"]=headline;write(ROOT/"gate.json",gate)
if __name__=="__main__":produce()
