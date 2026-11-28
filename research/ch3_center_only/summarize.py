"""Generate Chinese decision tables from physical endpoints and offline quota diagnostics."""
from collections import Counter
from pathlib import Path
from statistics import mean

from analyze import CASES, load_csv, table, verdict

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT.parent/"ch3_analytic_quota"
LABEL = {"win":"简化版较低","loss":"简化版较高","overlap":"证书区间重叠","unpaired":"缺安全配对"}


def num(value, places=6):
    return "—" if value is None or value=="" else f"{float(value):.{places}f}"


def md(header, rows):
    return ["|"+"|".join(header)+"|", "|"+"|".join("---" for _ in header)+"|",
            *["|"+"|".join(map(str,row))+"|" for row in rows]]


def report(cells, rows, pairs, cross):
    history = load_csv(FROZEN/"tables/cells.csv")
    archived = []
    for code in CASES:
        reference = next(r for r in history if (r["case"],r["arm"],r["budget_s"])==(code,"fit","60"))
        before = dict(J=float(reference["final_J"]), bounds=[float(reference["low_J"]),float(reference["high_J"])])
        after = cells[code,"center",600]["pt"]
        delta = after["J"]-before["J"] if after else None
        archived.append(dict(case=code, archived_fit_60_J=before["J"], center_600_J=after.get("J"),
                    delta_J=delta, delta_pct=100*delta/before["J"] if after else None,strict=verdict(after,before),
                    archived_plan=reference["plan"],center_plan=after.get("plan"),archived_low_J=before["bounds"][0],
                    archived_high_J=before["bounds"][1],center_bounds=after.get("bounds")))
    table("archived_fit60_vs_center600.csv",archived)
    groups = load_csv(ROOT/"diagnostic/groups.csv")
    grids = load_csv(ROOT/"diagnostic/terminal_grid.csv")
    changes = [g for g in groups if g["set_equal"]=="False"]
    found = sum(int(g["recovered_total"]) for g in groups)
    direct = sum(int(g["recovered_direct"]) for g in groups)
    clean = all(r["final_J"] is not None for r in rows)
    long_losses = [p for p in pairs if p["anchors_budget_s"]==600 and p["strict"]=="loss"]
    hist_losses = [p for p in archived if p["strict"]=="loss"]
    lines = ["# 第三章能否取消专用非共线锚点",""]
    if not clean:
        recommendation = "四流未全部取得两种预算的安全配对。保留解析能耗和三个代表配额。"
    elif not long_losses and not hist_losses:
        recommendation = "四流结果支持将仅保留负载均衡中心的版本送入十二流确认。"
    elif hist_losses:
        worst = max(hist_losses, key=lambda r:r["delta_pct"])
        recommendation = f"简化版给到 600 秒后，仍有 {len(hist_losses)} 条流的能耗严格高于现行算法的历史 60 秒端点。最大回退出现在 {worst['case']}，为 {worst['delta_pct']:.4f}%。"
    else:
        recommendation = "简化版在四条流上均追平或优于现行算法历史 60 秒结果，但部分流在同为 600 秒时仍有能耗损失。是否保留两个额外配额，须结合下列逐流损失幅度判断。"
    lines += [f"**{recommendation}**","","## 完整系统能耗","",
              "每格从空排程启动一次。正差表示取消锚点后耗电更多。严格高低要求一方证书的能耗上界低于另一方下界，区间重叠单列。",""]
    lines += md(["任务流","预算（秒）","三锚点（J）","仅中心（J）","差（J）","差（%）","连续认证判定","改换设备请求数／总数","同设备改频请求数"],
                [[p["case"],p["anchors_budget_s"],num(p["anchors_J"]),num(p["center_J"]),num(p["delta_J"]),num(p["delta_pct"],4),
                LABEL[p["strict"]],f'{p["changed_device"]}/{p["requests"]}' if p["changed_device"] is not None else "—",p["same_device_changed_OPP"]] for p in pairs])
    lines += [""]
    for b in (60,600):
        coverage = [sum(r["final_J"] is not None for r in rows if r["arm"]==arm and r["budget_s"]==b) for arm in ("anchors","center")]
        vs = Counter(p["strict"] for p in pairs if p["anchors_budget_s"]==b)
        lines += [f"{b} 秒安全覆盖为三锚点 {coverage[0]}/4、仅中心 {coverage[1]}/4。仅中心严格较低 {vs['win']} 条、区间重叠 {vs['overlap']} 条、严格较高 {vs['loss']} 条、缺安全配对 {vs['unpaired']} 条。",""]
    safe_rows = [r for r in rows if r["final_J"] is not None]
    if safe_rows:
        lines += [f"全部已接纳端点中，最高峰温上界为 {max(r['peak_upper_C'] for r in safe_rows):.5f} °C，最小期限余量为 {min(r['min_slack_ms'] for r in safe_rows):.5f} ms。",""]
    lines += ["## 允许更多求解时间时","",
              "现行算法取上一轮三点拟合版归档的 60 秒端点。中间一列给出本轮解析三锚点的 60 秒端点，便于区分两种参照。历史结果与本轮跨机器批次，不能单独据此归因。",""]
    lines += md(["任务流","现行历史 60 秒（J）","解析三锚点 60 秒（J）","仅中心 600 秒（J）","相对现行变化（%）","相对现行判定"],
                 [[a["case"],num(a["archived_fit_60_J"]),num(p["anchors_J"]),num(a["center_600_J"]),num(a["delta_pct"],4),LABEL[a["strict"]]] for a,p in zip(archived,cross)])
    lines += ["","## 相同父状态下，候选配额发生了什么变化","",
              f"四条流各取首窗、中窗及末窗的同一条归档父前缀，每个状态检查 30 对设备频档。原解析版逐项复现上一轮归档的候选集合。360 组中有 {len(changes)} 组更换了至少一个配额。删除的 720 个专用锚点位置中，容量切片直接重选 {direct} 个，原始候选补位再找回 {found-direct} 个，余下 {720-found} 个未入选。","",
              "最低参考能耗仅在各组实际通过 FIFO 时序检查的配额中比较，平局容差为 1e−10 J。多样性取组内所有候选两两间的平均归一化欧氏距离，两个坐标分别除以窗口内对应类型的请求数。热风险取合法候选的最低预测风险。这些数据只解释筛选变化。",""]
    summary = []
    for code in (*CASES,"合计"):
        subset = [g for g in groups if code=="合计" or g["case"]==code]
        comparable = [g for g in subset if g["anchors_best_ref_J"] and g["center_best_ref_J"]]
        differences = [float(g["center_best_ref_J"])-float(g["anchors_best_ref_J"]) for g in comparable]
        before,after = [sum(int(g[arm+"_valid"]) for g in subset) for arm in ("anchors","center")]
        summary.append([code,len(subset),sum(g["set_equal"]=="False" for g in subset),
                        f"{before}／{after}",f"{sum(v< -1e-10 for v in differences)}／{sum(abs(v)<=1e-10 for v in differences)}／{sum(v>1e-10 for v in differences)}／{len(subset)-len(comparable)}",
                        "／".join(num(mean(float(g[arm+"_mean_distance"]) for g in subset),4) for arm in ("anchors","center")),
                        num(mean(float(g["center_min_risk_C"])-float(g["anchors_min_risk_C"]) for g in comparable),5) if comparable else "—"])
    lines += md(["任务流","组数","集合改变","合法候选数（三锚点／仅中心）","最低参考能耗（降／平／升／缺配对）","多样性（三锚点／仅中心）","配对最低热风险平均变化（°C）"],summary)
    lines += ["","## 末窗口热计算核对","",
              f"对末窗 4 × 30 × 3 = {len(grids)} 个原锚点，固定同一请求前缀、配额和频档，独立重放两次。50 ms 细格按实际覆盖时长加权聚合；250 ms 路径直接积分，末尾不足一格时两者都使用实际时长。时序、参考能耗、设备状态和切换决定逐项一致。八分量功率矩的最大绝对差为 {max(float(r['moment_max_error']) for r in grids):.3g}，四节点温度序列最大差 {max(float(r['temperature_max_error_C']) for r in grids):.3g} °C，峰值最大差 {max(float(r['peak_error_C']) for r in grids):.3g} °C。连续热认证仍逐排程使用原认证器。","",
              "## 实际删除的逻辑","",
              "旧版从均衡中心再构造两点。先在近均衡线上选距中心较远的配额，再用行列式选出与前两点不共线的配额，并让三点预先占用候选名额。简化版只让原均衡中心占一个名额，直接调用原整数切片与排序，空位沿用原始配额顺序补齐。一并删除三个锚点的预重放、校准记录及末窗专用细格聚合。解析能耗系数、负载评价、距离补充和配额去重沿用原实现。","",
              "各个实际入选的配额继续进行时序和热评价。后端沿用冻结第三章的父状态继承、束搜索、终端排序、多映射提名、超温映射处理、全局调频和温度修正。正式评分采用物理重放后的完整安全能耗。","",
              "## 实验口径与证据","",
              f"正式完成 {len(rows)} 格，累计计费 {sum(r['charged_s'] for r in rows):.3f} 核秒，上限 5280 核秒。每条流的四格使用同一运行机、同一逻辑核、单线程及独立冷启动。60 秒与 600 秒分别预留末尾 5 秒调频；搜索分界前无 SAFE 时允许搜索延续到总截止点。每格一次，时间截断可能影响能耗端点，四流不足以估计重复运行波动。","",
              "[同预算能耗及映射配对](tables/pairs.csv) · [历史现行 60 秒对照](tables/archived_fit60_vs_center600.csv) · [本轮解析版跨预算配对](tables/long_vs_short.csv) · [逐格证书界与时间](tables/cells.csv) · [逐请求设备及频档](tables/request_assignments.csv)","",
              "![各任务流在两个时间预算下已认证的最低完整系统能耗](energy_vs_time.png)","",
              "[完整候选及来源](diagnostic/candidates.csv) · [共同状态汇总](diagnostic/groups.csv) · [热网格逐点核对](diagnostic/terminal_grid.csv) · [简化组实际执行代码](simplified.py) · [全部在线认证归档](paired_results) · [最终排程、证书和轨迹](final_evidence.tar.gz)"]
    lines += ["", "冻结版本为完整第三章 `798f5586`、解析有锚点版及历史数据 `bc584198`、统一物理模型 `be641ce0`。本次正式运行的代码、运行机、逻辑核、预算及实际计费见各格的 `receipt.json`。比较执行前，离线诊断曾因两个同名 Python 模块导入问题停止。修正后才开始正式运行，未消费额外正式单元。"]
    (ROOT/"REPORT_zh.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
