"""Generate a compact factual report from completed paired records."""
from pathlib import Path
import json
from statistics import median
from collections import Counter
from analyze import HERE,ROOT,CFG,read

def fmt(value,n=3):
    return "未达到" if value is None else f"{value:.{n}f}"

def main():
    data=read(HERE/"summary.json")
    rows=data["runs"]
    table=["|工况|最优能耗 J|Kim SAFE/最优|EO SAFE/最优|Kim 首达 0.1% / 最优 s|EO 首达 0.1% / 最优 s|",
           "|---|---:|---:|---:|---:|---:|"]
    labels={"balanced":"均衡","concurrent":"高并发","asymmetric":"非对称"}
    codes={}
    for i,case in enumerate(CFG["cases"],1):
        ref=next(r for r in rows if r["case_id"]==case)
        label=labels[ref["load"]]+("正序" if ref["order"]=="forward" else "逆序")+("预热" if ref["thermal_start"]=="preheated" else "基准初温")
        codes[case]=label
        cols=[]
        for method in CFG["methods"]:
            c=next(c for c in data["cases"] if c["case_id"]==case and c["method"]==method)
            cols.append(c)
        k,e=cols
        table.append(f'|{label}|{ref["optimum_j"]:.6f}|{k["safe"]}/3 · {k["optimum"]}/3|{e["safe"]}/3 · {e["optimum"]}/3|'
                     f'{fmt(k["median_time_to_01pct_s_conditional"])}/{fmt(k["median_time_to_optimum_s_conditional"])}|'
                     f'{fmt(e["median_time_to_01pct_s_conditional"])}/{fmt(e["median_time_to_optimum_s_conditional"])}|')
    stats=[]
    for load in ("all","concurrent","balanced","asymmetric"):
        pair=[p for p in data["pairs"] if load=="all" or p["load"]==load]
        common=[p for p in pair if p["kim_01pct_s"] is not None and p["energy_01pct_s"] is not None]
        ratio=[p["kim_01pct_s"]/p["energy_01pct_s"] for p in common]
        stats.append(dict(load=load,pairs=len(pair),common_quality_pairs=len(common),
              energy_faster=sum(p["energy_faster_01pct"] is True for p in common),
              median_paired_speed_ratio=median(ratio) if ratio else None,
              median_paired_time_saved_s=median(p["kim_01pct_s"]-p["energy_01pct_s"] for p in common) if common else None,
              energy_saving_min_pct=min((p["energy_saving_vs_kim_pct"] for p in pair if p["both_safe"]),default=None),
              energy_saving_max_pct=max((p["energy_saving_vs_kim_pct"] for p in pair if p["both_safe"]),default=None)))
    (HERE/"aggregate.json").write_text(json.dumps(stats,indent=2)+"\n",encoding="utf-8",newline="\n")
    counts=read(HERE/"verification.json")["counts"]
    allsafe=sum(r["safe"] for r in rows); opt=sum(r["matched_optimum"] for r in rows)
    text=f"""# 冻结 12 工况的 Kim＋SAFE / Energy-Only 公平比较

基于输入冻结 [3db685b](https://github.com/YBEMR/paper/commit/3db685b74773c8e029881e459de72a0c4e8e41ee)、M2 精确诊断 [45b14f9](https://github.com/YBEMR/paper/commit/45b14f99bdb9324eedd6469609400a4ee92ed656)，执行代码与协议先冻结于 [fd461af](https://github.com/YBEMR/paper/commit/fd461afed8ea81224207aac1345e5c404116feb5)，本目录的结果提交随后归档。

## 直接结果

{len(rows)} 次正式运行，SAFE {allsafe}/{len(rows)}，达到同工况 M2 最优值 {opt}/{len(rows)}（容差 1e-7 J）。运行结束状态：{dict(Counter(r["status"] for r in rows))}。没有追加种子、改变负载或性能调参。

本轮 **Kim＋SAFE 具体指已有 Kim-Anytime＋SAFE**。它保留原遗传选择，每代额外认证一次，末尾继续验证累计候选池；使用这个较强的既有版本避免把历史“生成结束后才开始认证”当成本文方法的速度贡献。旧 Kim-Adapt＋SAFE 归档保留，本轮未重跑。

表中计时为三种子的中位数；“最优”指能耗匹配归档精确值，**启发式本身没有生成最优性证书**。0.1% 阈值也由同工况 M2 值定义；未达到者应记删失，条件中位数只针对达到者。

{chr(10).join(table)}

"""
    for s in stats:
        subset=[r for r in rows if s["load"]=="all" or r["load"]==s["load"]]
        text+=f'### {s["load"]} 配对结果\n\n'
        text+=f'- 共 {s["pairs"]} 对；两者都达到 0.1% 质量的 {s["common_quality_pairs"]} 对中，Energy-Only 更快 {s["energy_faster"]} 对。Kim/EO 配对到解时间比中位数 {fmt(s["median_paired_speed_ratio"])}；配对节省时间中位数 {fmt(s["median_paired_time_saved_s"])} s。\n'
        text+=f'- EO 相对 Kim 的最终安全节能率范围 {fmt(s["energy_saving_min_pct"],6)}% 至 {fmt(s["energy_saving_max_pct"],6)}%，仅同工况且双方 SAFE 时计算。\n'
        for method in CFG["methods"]:
            g=[r for r in subset if r["method"]==method]
            last=[r["last_unique_certificate_s"] for r in g if r["last_unique_certificate_s"] is not None]
            text+=f'- {method}：SAFE {sum(r["safe"] for r in g)}/{len(g)}，最优值匹配 {sum(r["matched_optimum"] for r in g)}/{len(g)}；进程结束中位数 {median(r["total_wall_s"] for r in g):.3f} s，最后一次新物理认证中位数 {median(last):.3f} s。\n'
        text+="\n"
    text+="## 研究取舍\n\n"
    high=[r for r in rows if r["load"]=="concurrent"]
    for method in CFG["methods"]:
        g=[r for r in high if r["method"]==method]
        text+=f'- 高并发 {method}：D017 赢家 {sum(r["deployment"]=="D017" for r in g)}/{len(g)}；同域最优值匹配 {sum(r["matched_optimum"] for r in g)}/{len(g)}。\n'
    if opt==len(rows):
        text+="- **本轮没有最终安全节能差距。** 热约束改变最低能耗部署这一问题有效性结论成立；但不能进一步推导 Energy-Only 的能耗优于 Kim。强 Kim 基线在全部冻结负载和入口状态下都有效。\n"
    slower=[p for p in data["pairs"] if p["energy_faster_01pct"] is False]
    text+=f'- 共同 0.1% 质量阈值下，Energy-Only 未更快的配对共 {len(slower)} 个，涉及：'+", ".join(sorted({codes[p["case_id"]] for p in slower}))+"。不能主张普遍更快。\n"
    text+="- **建议保留既有算法，不据此增加启发式。** M2 保留小域有限域最优证书与质量参照；Kim-Anytime＋SAFE 保留强对照；Energy-Only 的可支持优势应限定为本批中较早提供优质安全解的具体工况。81 域结果不能推翻或替代原扩展域选型证据，也不能将更早到解写成最终节能或更低总搜索成本。\n"
    text+="- 这一轮完成问题诊断后的算法公平验证，先整理现有证据；不自动扩展网络、修改负载、增加种子或新启发式。\n\n"
    text+="""## 机制与归因边界

|项目|Kim-Anytime＋SAFE|Energy-Only|
|---|---|---|
|原始合法选择|同一 81 个具体绑定，四场景各 27 档|完全相同|
|部署搜索|24 个体、最多 64 代；Lexicase、交叉、变异|能耗档案父状态；单网坐标、绑定、既有名额交换及随机重启|
|频率|原 SetFreq，每个已访问部署四场景一次|原 SetFreq 初始化/新部署，另逐场景遍历 27 档邻居|
|热处理|每代、末尾独立连续认证，不改变遗传选择|连续认证后更新安全/超温能耗档案；允许暂时超温父状态|
|排序|独立场景代理能耗|父状态平均温度下漏电能耗估计，加既有同步请求组资源需求排序|
|停止|完成 64 代并验证完累计池时可提前结束；或时间截止|冻结实现按时间截止，不以局部停滞提前退出|
|全域证书|不提供|不提供|

Energy-Only 名称不表示删除连续热信息：它关闭热点定向修复排序，但仍使用原温度相关能耗估计、连续热认证和超温父状态。非对称周期的适配仅依据实际请求计数和明确总数；本轮所有期限仍为 40 ms、所有活跃网络在场景入口均有同步请求，原同步请求组需求排序仍成立为启发式，完整期限判据从未替换为该估计。

这里比较完整的两个既有实现，**不是单机制消融**。到解时间差与认证时机、搜索路径、资源估计等共同相关，不能仅由此断言名额交换或超温父状态单独导致改进。既有扩展域消融仍是历史证据，但不能当作本 12 工况的直接消融。没有为本轮结果追加新规则。

## 可信度与局限

"""
    text+=f'- 固定见证回归通过；{counts["physical_certificates"]} 份物理输出、{counts["incumbent_ledgers"]} 份逐请求赢家证据（{counts["ledger_requests"]} 条完成记录）通过归档一致性检查。统计与图表均由原始记录重算。\n'
    text+="""- 原请求、图、功耗、频率、RC、漏电、80°C 安全上界、10.04 s 窗口及连续热继承保持不变。旧代码/原始结果未覆盖；只有新目录的接口和输出。
- 每次从进程创建开始计时，包含导入、输入哈希检查、构建候选域、SetFreq、事件调度、热评价、证据和日志。116 s 搜索接纳截止，120 s 硬上限，两方法相同。
- 汇总中的到解时间采用完整逐请求证据核对并写出的时刻，源算法内部时间另在原始 summary 保留；没有在预算外补认证后回填更早时间。
- 六通道并行、单逻辑 CPU 绑定、数值库单线程；每对同 CPU、算法顺序交替。计时可用于本批描述性配对比较，不能消除所有系统负载/处理器频率波动；三种子不足以作广泛显著性结论。
- M2 是已归档同域能耗最优参照。本轮没有重跑 M2，因此不把历史 M2 耗时与本批算法并排当作严格同机速度对照。
- 全部工况环境 25°C，基准入口 30°C；预热入口来自冻结运行过程。81 域是具体物理绑定集合，预热下不外推至 161 完整绑定域。
- 高并发同时改变网络共现和请求总量，本轮不能拆分二者效应。也不能外推为新增 DNN、任意周期相位/期限、真实硬件或 27.5/30°C 的比较。
- 最终能耗、到解时间、最终结束时间分别报告。尤其 Energy-Only 沿用时间停止，达到最好解之后仍继续搜索；较早得到解不等于较早结束或总计算成本更低。
- 原始超温和期限失败记录均保留；超温候选不参与安全节能率。

## 结果文件与复算

- [执行协议](PROTOCOL.md)、[实际配置](formal_experiment_config.csv)、[执行源哈希](execution_manifest.json)、[环境](environment.json)、[配对顺序](schedule.json)。
- [逐运行指标](tables/runs.csv)、[逐工况汇总](tables/case_summary.csv)、[种子配对](tables/paired.csv)、[安全解轨迹](tables/safe_progress.csv)、[预算检查点](tables/checkpoints.csv)、[调用成本](tables/costs.csv)。
- [验证结果](verification.json)、[接口回归](regression.json)；raw 下逐运行日志、完整热输出、逐请求赢家证书、退出记录和文件哈希。
- [安全能耗](figures/safe_energy.svg)、[同质量到解曲线](figures/time_to_quality.svg)、[到解与结束时间对照](figures/paired_time.svg)、[调用成本](figures/measured_costs.svg)。SVG/PNG 已入库，SVG 文本可编辑；PDF 由 plot.py 本地重建，遵守仓库忽略 PDF 的规则，不强制上传。成本图中的 inclusive 类别有嵌套，不能相加。
- 在仓库根运行以下命令，仅复算归档，不重新搜索：
  `python -B -X utf8 research/multidnn_algorithm_comparison/analyze.py`
  `python -B -X utf8 research/multidnn_algorithm_comparison/verify.py`
  `python -B -X utf8 research/multidnn_algorithm_comparison/plot.py`
  `python -B -X utf8 research/multidnn_algorithm_comparison/report.py`
- 正式执行须检出执行冻结版本并使用新的隔离输出副本；run.py 拒绝覆盖原始批次。不要直接删除 raw 后把新增运行混入本归档。
"""
    (HERE/"README.md").write_text(text,encoding="utf-8",newline="\n")
    print(json.dumps(stats,indent=2))
if __name__=="__main__":
    main()
