"""Render the Chinese decision from individual certificates and common-parent evidence."""
import csv
import json
import statistics as st
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def read_csv(p):
    with p.open(encoding="utf-8") as f:return list(csv.DictReader(f))
def n(x,d=4):return "—" if x is None else f"{x:.{d}f}"
def summarize_groups(groups,candidates):
    stats=[]
    for label in ["全部","A02","A06","C10","C11"]:
        gs=[g for g in groups if label=="全部" or g["case"]==label]
        rs=[r for r in candidates if (label=="全部" or r["case"]==label) and r["anchor"]=="False" and r["fifo_valid"]=="True"]
        vals=[float(g["delta_best_ref_J"]) for g in gs if g["delta_best_ref_J"]]
        def mae(field):return st.mean(abs(float(r[field])) for r in rs) if rs else None
        stats.append(dict(case=label,groups=len(gs),same_set=sum(g["set_equal"]=="True" for g in gs),
                         same_order=sum(g["order_equal"]=="True" for g in gs),
                         common_slots=sum(int(g["common"]) for g in gs),total_slots=sum(int(g["slots"]) for g in gs),
                         valid_nonanchors=len(rs),fit_MAE_J=mae("fit_error_J"),analytic_aligned_MAE_J=mae("analytic_centered_error_J"),
                         analytic_raw_MAE_J=mae("analytic_raw_difference_J"),
                         analytic_missed_lower_ref=sum(d>1e-10 for d in vals),fit_missed_lower_ref=sum(d< -1e-10 for d in vals),
                         tied_cost=sum(abs(d)<=1e-10 for d in vals),no_paired_legal=len(gs)-len(vals),
                         analytic_only_legal=sum(int(g["analytic_valid"])>0 and int(g["fit_valid"])==0 for g in gs),
                         fit_only_legal=sum(int(g["fit_valid"])>0 and int(g["analytic_valid"])==0 for g in gs)))
    with (ROOT/"tables/diagnosis.csv").open("w",newline="") as out:
        w=csv.DictWriter(out,fieldnames=stats[0],lineterminator="\n");w.writeheader();w.writerows(stats)
    return stats

def report(cells,rows,pairs,cross):
    groups=read_csv(ROOT/"diagnostic/groups.csv");candidates=read_csv(ROOT/"diagnostic/candidates.csv")
    stats=summarize_groups(groups,candidates);s=stats[0]
    codes=("A02","A06","C10","C11");sizes=(60,600);arms=("fit","analytic")
    cuts=(10,30,60,180,300,600)
    verdict={"win":"解析胜","loss":"拟合胜","overlap":"区间重叠","unpaired":"缺 SAFE"}
    report=["# 三点参考能耗拟合能否由解析画像成本替代",""]
    def add(*lines):report.extend(lines)
    def section(title):add("","## "+title,"")
    def table(headers,data):
        add("|"+"|".join(headers)+"|","|"+"|".join(["---"]*len(headers))+"|")
        for r in data:add("|"+"|".join(map(str,r))+"|")
    coverage={b:[sum(cells[c,a,b]["pt"]!={} for c in codes) for a in arms] for b in sizes}
    long=Counter(p["strict"] for p in cross)
    equal_cover=all(k[0]==k[1]==4 for k in coverage.values())
    if equal_cover and long["loss"]==0:
        add("**四流初筛支持继续验证解析替代。** 解析版在 600 秒内对四条流均达到或优于现行 60 秒端点。三个锚点仍保留，正式第三章继续采用原冻结版本。")
    elif equal_cover:
        add(f"**两版均能覆盖四条流；解析版延长预算后仍在 {long['loss']} 条流上落后于现行短预算端点。** 本轮没有预设允许损失的百分比，保留逐流严格比较和实际焦耳差，暂缓直接删除原拟合。")
    else:
        add("**本轮未同时取得四流完整共同安全覆盖。** 能耗仅在取得 SAFE 的端点之间比较，继续保留原方法。")
    section("从空排程出发的完整算法结果")
    add("能耗含全部设备执行、空闲、切换和温度相关项。差值取解析版减拟合版。严格胜负要求胜方证书能耗上界低于对方下界。","")
    table(["任务流","预算 s","拟合 J","解析 J","差 J","差 %","证书判定"],[
        [p["case"],p["fit_budget_s"],n(p["fit_J"],6),n(p["analytic_J"],6),n(p["delta_J"],6),n(p["delta_pct"]),verdict[p["strict"]]] for p in pairs])
    for b in sizes:
        scores=Counter(p["strict"] for p in pairs if p["fit_budget_s"]==b)
        add("",f"{b} 秒下，安全覆盖为拟合 {coverage[b][0]}/4、解析 {coverage[b][1]}/4；解析严格胜 {scores['win']}、重叠 {scores['overlap']}、严格负 {scores['loss']}、缺配对 {scores['unpaired']}。")
    section("多给解析版求解时间后的能耗")
    table(["任务流","拟合 60 s（J）","解析 600 s（J）","差 J","差 %","证书判定"],[
        [p["case"],n(p["fit_J"],6),n(p["analytic_J"],6),n(p["delta_J"],6),n(p["delta_pct"]),verdict[p["strict"]]] for p in cross])
    add("","每条流的长、短预算从独立进程启动。跨预算结果同时含有额外搜索时间的收益；拟合本身的作用应结合相同预算和相同父状态的比较判断。")
    section("三点拟合实际上改变了哪些选择")
    add("每条流从拟合版 60 秒正式账本取首次经过首窗、中窗、末窗时的第一个父状态；恢复其完整前缀、设备状态及温度。每个状态逐一固定 30 组合法 GPU/NPU 频档，两版使用相同容量切片、网格和候选数。每组单独展开，排除其他频档的跨组去重干扰。诊断结果不计入正式成绩。","")
    table(["流","共同组","配额集合相同","顺序也相同","共有候选槽／全部槽","解析漏较低参考能耗","拟合漏较低参考能耗","最低参考能耗持平","缺共同合法"],
          [[v["case"],v["groups"],v["same_set"],v["same_order"],f"{v['common_slots']}/{v['total_slots']}",
          v["analytic_missed_lower_ref"],v["fit_missed_lower_ref"],v["tied_cost"],v["no_paired_legal"]] for v in stats])
    add("",f"在 {s['groups']} 个共同组中，替换系数实际改变 {s['groups']-s['same_set']} 组候选集合。漏选低参考能耗按两版各自保留集合的最低合法 FIFO 值比较，数值容差为 1e−10 J，比较范围限于两版所选候选的并集。共同状态取自拟合版首次搜索路径，这一比例只描述所抽取的状态。")
    add("","原拟合估计 FIFO 前缀累计的参考增量；解析式只计算本窗口主推理相对于最低空闲基准的增量。两者绝对值包含的项目不同。以每组同一个中心锚点对齐后再比较误差，可消去父前缀和其他共同常数。训练锚点、时序失败候选不计入以下误差统计。","")
    table(["流","合法非锚点","拟合平均绝对误差 J","解析原值与账本平均绝对差 J","解析中心对齐后平均绝对误差 J"],
          [[v["case"],v["valid_nonanchors"],n(v["fit_MAE_J"],6),n(v["analytic_raw_MAE_J"],6),n(v["analytic_aligned_MAE_J"],6)] for v in stats])
    add("","[逐候选的配额、实际参考能耗、期限余量、热风险及误差](diagnostic/candidates.csv) · [逐组实际系数与最低值](diagnostic/groups.csv)")
    only=[r for r in candidates if r["fit_selected"]!=r["analytic_selected"]]
    if only:
        section("候选发生分歧的一个实例")
        example=next((g for g in groups if g["delta_best_ref_J"] and abs(float(g["delta_best_ref_J"]))>1e-10),
                     next(g for g in groups if g["set_equal"]=="False"))
        keys=("case","parent","window","gpu_opp","npu_opp")
        witness=[r for r in only if all(r[k]==example[k] for k in keys)]
        add(f"{example['case']} 第 {example['window']} 窗，GPU 频档 {example['gpu_opp']}、NPU 频档 {example['npu_opp']}。下表仅列两版选择不同的配额。风险为原热延拓分数，最终安全状态由全流连续认证给出。","")
        table(["入选版本","A/B 配额","FIFO 合法","参考增量 J","热风险 °C","余量 ticks"],[
            ["拟合" if r["fit_selected"]=="True" else "解析",r["x"]+"/"+r["y"],"是" if r["fifo_valid"]=="True" else "否",
             n(float(r["actual_ref_ledger_J"]),6),n(float(r["risk_C"]),3) if r["risk_C"] else "—",r["slack_ticks"]] for r in witness])
    section("映射、频率和热安全")
    table(["流","预算 s","设备不同请求数／总数","同设备但频档不同","解析搜索访问拟合最佳映射","解析认证过该映射","峰温上界 °C 拟合／解析","最小余量 ms 拟合／解析"],
          [[p["case"],p["fit_budget_s"],f"{p['changed_device']}/{p['requests']}" if p["requests"] else "—",p["same_device_changed_OPP"],
            {True:"是",False:"否",None:"—"}[p["fit_best_map_seen_by_analytic"]],{True:"是",False:"否",None:"—"}[p["fit_best_map_certified_by_analytic"]],
            "／".join(n(cells[p["case"],a,p["fit_budget_s"]]["row"]["peak_upper_C"],3) for a in arms),
            "／".join(n(cells[p["case"],a,p["fit_budget_s"]]["row"]["min_slack_ms"],3) for a in arms)] for p in pairs])
    add("","“访问”包含已进入完整闭合 FIFO 评价的映射及已认证映射。“认证”要求已有完整物理证书。逐流配对表还记录了解析版在拟合最佳映射上实际交付的最小 SAFE 能耗。单次限时搜索的胜负也可能受截止时已完成的工作量影响。")
    if (ROOT/"tables/request_assignments.csv").exists():add("","[两版逐请求的设备与频档](tables/request_assignments.csv)")
    section("能耗随求解时间变化")
    add("![四流各预算下的最佳安全能耗](energy_vs_time.png)","","曲线从首次取得 SAFE 时起画；此前的能耗留空。每次下降都可追溯到在线落盘的证书。[指定时间点](tables/checkpoints.csv) · [逐次改善](tables/improvements.csv)")
    section("运行耗时和不利结果")
    table(["流","预算 s","版本","首次 SAFE s","构造 s","搜索认证 s","普通／温度 DP s","调频认证 s","SAFE／HOT／模型外／未决","闭合 FIFO 失败调用"],
          [[r["case"],r["budget_s"],"拟合" if r["arm"]=="fit" else "解析",n(r["first_safe_s"],2),n(r["construct_s"],2),
            n(r["search_cert_s"],2),n(r["ordinary_DP_s"],2)+"／"+n(r["thermal_DP_s"],2),n(r["dp_cert_s"],2),
            f"{r['SAFE']}/{r['HOT']}/{r['OUT_OF_MODEL']}/{r['UNRESOLVED']}",r["timing_failed_closed_calls"]] for r in rows])
    add("","耗时来自在线起止日志，未完成调用截在有效截止点。动态规划仅计已返回的内核调用，其余及未能拆分的时间在逐格表单列。FIFO 时序失败按调用数登记，可含对同一映射的不同频档尝试。")
    section("删去的计算与保留的功能")
    add("冻结实现先把三个配额及其 FIFO 参考能耗写成三个方程，求解截距和两个配额方向的斜率，再将系数用于代表点排序。解析版删除这一处三元线性求解，用冻结的精确整数系数直接构造三个系数。令每个主推理增量系数为该频档执行时长乘以其活动功率与设备最低档空闲功率之差。按同一整数尺度排序，换算焦耳时除以模型尺度。","",
        "$$E(x,y)=a e_{AG}+b e_{BG}+(e_{AN}-e_{AG})x+(e_{BN}-e_{BG})y.$$","",
        "三个锚点仍然构造、执行 FIFO 检查并作为候选。终端锚点沿用 500 tick 网格，再按冻结规则聚合；其余候选沿用 2500 tick 网格。容量边界、平衡线、代表池、去重和补位均沿用原程序。后续束搜索、映射提名、普通调频、温度修正和连续认证完全共用。解析成本仅承担候选排序，完整能耗及其认证下界均取自物理模型。")
    section("研究范围与归档")
    count=sum(len(json.loads((ROOT/"paired_results"/c/"physical/index.json").read_bytes())["plans"]) for c in codes)
    diag=json.loads((ROOT/"diagnostic/receipt.json").read_bytes())
    add(f"正式计算 16 格，合计 {sum(r['charged_s'] for r in rows):.3f}/5280 核秒。同流同机同核，单线程；实例建立、候选评价、调频、热认证及在线写入均计时。60 秒和 600 秒独立启动，分别预留最后 5 秒调频，沿用无 SAFE 时继续搜索的规则。诊断单独用时 {diag['elapsed_s']:.3f} 秒。按流去重核验了 {count:,} 份正式物理排程。","",
        "四流各格只有一次运行，无法据此估计重复间波动。移除专用锚点和十二流三次重复需要单独的执行预算。本轮结果不更改正式论文章节及文献基线。","",
        "[完整配对与映射差异](tables/pairs.csv) · [长对短](tables/long_vs_short.csv) · [逐格指标与开销](tables/cells.csv) · [最终逐请求设备、频档、证书和温度轨迹](final_evidence.tar.gz) · [全部物理证据](paired_results) · [单计划解包器](../ch3_mapping_first_nested/restore_plan.py) · [证据校验清单](PAIRED_SHA256SUMS)")
    (ROOT/"REPORT_zh.md").write_text("\n".join(report)+"\n",encoding="utf-8")
