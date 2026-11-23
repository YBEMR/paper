"""Build tables, figures and the report from archived results only. No evaluations."""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_gap import HERE, read, csv_out


def write(name, text):
    (HERE / name).write_text(text, encoding="utf-8", newline="\n")


def main():
    s = read(HERE / "summary.json")
    f = read(HERE / "frequency_attribution.json")
    verification = read(HERE / "verification.json")
    env = read(HERE / "environment.json")
    config = read(HERE / "config.json")
    assert verification["status"] == "PASS"
    cases = s["cases"]
    bests = {r["case_id"]: r for r in s["candidates"] if r["phase"] == "fixed_frequency"}
    labels = [("原始" if c["load"] == "original" else c["load"]) + f" {c['ambient_c']}℃" for c in cases]
    short = {c["case_id"]: label for c, label in zip(cases, labels)}
    metrics = []
    actual_config = []
    for c in cases:
        rows = [r for r in f["rows"] if r["case_id"] == c["case_id"]]
        phases = [r for r in s["phases"] if r["case_id"] == c["case_id"]]
        probe = next(r for r in phases if r["phase"] == "deployment_probe")
        no_safe = sum(r["no_safe"] for r in s["candidates"] if r["case_id"] == c["case_id"])
        metrics.append(dict(case_id=c["case_id"],label=short[c["case_id"]],
            certified_safe_frequency_pairs=len(rows),setfreq_loss_pairs=sum(r["within_deployment_saving_pct"]>1e-7 for r in rows),
            maximum_within_deployment_saving_pct=max(r["within_deployment_saving_pct"] for r in rows),
            final_saving_vs_best_kim_pct=c["saving_vs_best_kim_pct"],
            completed_probe=c["completed_probe_deployments"],safe_probe=c["completed_probe_deployments"]-no_safe,
            no_safe_probe=no_safe,uncompleted_probe=48-c["completed_probe_deployments"],
            probe_wall_s=c["probe_wall_s"],schedule_s=probe["time_schedule_s"],
            kernel_compile_s=probe["time_kernel_compile_s"],
            residual_s=c["probe_wall_s"]-probe["time_schedule_s"]-probe["time_kernel_compile_s"]))
        for phase in phases:
            actual_config.append(dict(case_id=c["case_id"],phase=phase["phase"],
                historical_best_seed=c["kim_seed"],new_algorithm_seeds="none",topology_sampling_seed=config["probe_seed"],
                population="not applicable",generations="not applicable",domain_size=config["domain"],
                planned_deployments=phase["planned"],completed_deployments=phase["completed"],
                frequency_codes_per_deployment=27**4,wall_limit_s=120,admission_limit_s=116,
                actual_wall_s=phase["total_wall_s"],reason=phase["reason"],
                stop="frozen list completed or time limit; no retries or added proposals",
                peak_fallback_integrations=phase.get("count_peak_fallback_integrations",0),
                event_dispatches=phase.get("count_event_dispatches",0),
                setfreq_requests=phase.get("count_setfreq_requests",0),
                unique_physical_replays=phase.get("count_unique_replays",0)))
    csv_out("figure_data.csv", metrics)
    csv_out("formal_experiment_config.csv", actual_config)

    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],
                         "axes.unicode_minus":False,"font.size":10,"svg.fonttype":"none",
                         "svg.hashsalt":"kim-gap-diagnostics-20261123","axes.spines.top":False,
                         "axes.spines.right":False})
    figdir = HERE / "figures"
    figdir.mkdir(exist_ok=True)
    def save(fig, name):
        fig.savefig(figdir / (name+".png"), dpi=180, facecolor="white")
        path=figdir / (name+".svg")
        fig.savefig(path, metadata={"Date":None})
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8",newline="\n")
        plt.close(fig)

    example=max(f["rows"],key=lambda r:r["within_deployment_saving_pct"])
    ref=next(c for c in cases if c["case_id"]==example["case_id"])
    fig, ax = plt.subplots(1,2,figsize=(11,4.8),gridspec_kw={"width_ratios":[1.3,1]})
    x=np.arange(6)
    vals=[r["maximum_within_deployment_saving_pct"] for r in metrics]
    ax[0].bar(x,vals,color="#4477AA",width=.65,label="已完成部署中的最大调频收益")
    ax[0].scatter(x,[0]*6,color="#CC6677",marker="D",s=32,zorder=3,label="相对最佳Kim的最终收益")
    for i,v in enumerate(vals):ax[0].text(i,v+.07,f"{v:.2f}%",ha="center",fontsize=9)
    ax[0].set(xticks=x,xticklabels=labels,ylim=(-.22,5.1),ylabel="节能率 (%)",title="局部调频损失 ≠ 最终算法节能空间")
    ax[0].legend(loc="upper left",frameon=False,fontsize=8)
    energies=[ref["kim_energy_j"],example["setfreq_j"],example["joint_optimum_j"]]
    ax[1].bar(range(3),energies,color=["#228833","#999999","#4477AA"],width=.65)
    for i,v in enumerate(energies):ax[1].text(i,v+.35,f"{v:.3f}",ha="center",fontsize=10)
    ax[1].set(xticks=range(3),xticklabels=["最佳Kim\nX4139374","SetFreq\nX4308295","联合调频\nX4308295"],
              ylabel="全窗系统能耗 (J)",ylim=(0,43),title="A 25℃：最大同部署收益案例")
    ax[1].text(.5,.96,"同部署降低4.013%；仍高于Kim 7.150%",transform=ax[1].transAxes,ha="center",va="top",fontsize=9)
    fig.text(.5,.025,"左图两类收益分母不同：同部署SetFreq能耗 / 本工况最佳Kim能耗；均仅覆盖本轮已完成候选。",ha="center",fontsize=9)
    fig.subplots_adjust(left=.065,right=.98,bottom=.18,top=.90,wspace=.32)
    save(fig,"frequency_regret")

    fig, ax=plt.subplots(1,2,figsize=(11,4.6),gridspec_kw={"width_ratios":[1,1.2]})
    y=np.arange(6)
    safe=np.array([r["safe_probe"] for r in metrics]);unsafe=np.array([r["no_safe_probe"] for r in metrics])
    ax[0].barh(y,safe,color="#4477AA",label="最低SAFE已认证")
    ax[0].barh(y,unsafe,left=safe,color="#CC6677",label="该部署无SAFE频率")
    ax[0].barh(y,48-safe-unsafe,left=safe+unsafe,color="#DDDDDD",label="预算内未完成")
    for i,r in enumerate(metrics):ax[0].text(r["completed_probe"]+.5,i,f"{r['completed_probe']}/48",va="center",fontsize=9)
    ax[0].set(yticks=y,yticklabels=labels,xlim=(0,55),xlabel="冻结部署候选数量",title="部署探查覆盖（不含Kim基准部署）")
    ax[0].invert_yaxis()
    ax[0].legend(loc="upper left",bbox_to_anchor=(0,-.16),frameon=False,fontsize=8)
    left=np.zeros(6)
    for field,color,label in [("schedule_s","#44AA99","事件调度与期限检查"),("kernel_compile_s","#4477AA","热系数构建"),("residual_s","#BBBBBB","其余完整墙钟成本")]:
        values=np.array([r[field] for r in metrics]);ax[1].barh(y,values,left=left,color=color,label=label);left+=values
    ax[1].axvline(120,color="#CC3311",ls="--",lw=1)
    ax[1].set(yticks=y,yticklabels=labels,xlim=(0,125),xlabel="实际墙钟时间 (s)",title="部署探查成本（每工况120秒上限）")
    ax[1].invert_yaxis()
    ax[1].legend(loc="upper left",bbox_to_anchor=(0,-.16),frameon=False,fontsize=8)
    fig.subplots_adjust(left=.075,right=.98,bottom=.28,top=.90,wspace=.30)
    save(fig,"coverage_cost")

    table=["| 工况 | 最佳Kim J | 固定部署最优 J | 本轮最好SAFE J | 节能率 | 固定/探查耗时 s | 探查完成 |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    safety=["| 工况 | 连续峰温上界 °C | 最小期限裕量 ms | 满足期限的频率序列 |",
            "|---|---:|---:|---:|"]
    for c in cases:
        table.append(f"| {short[c['case_id']]} | {c['kim_energy_j']:.6f} | {c['fixed_deployment_optimum_j']:.6f} | {c['best_this_round_j']:.6f} | {c['saving_vs_best_kim_pct']:.3f}% | {c['fixed_wall_s']:.2f} / {c['probe_wall_s']:.2f} | {c['completed_probe_deployments']}/48 |")
        b=bests[c["case_id"]]
        safety.append(f"| {short[c['case_id']]} | {b['peak_upper_c']:.6f} | {b['slack_ms']:.6f} | {b['deadline_sequences']:,} |")
    history=s["historical_proxy"]
    assert all(r["full_valid_pool_checked"] and abs(r["proxy_first_minus_best_j"])<=1e-7 for r in history)
    worst=max(history,key=lambda r:r["largest_reversal"]["energy_difference_j"])
    groups=Counter(r["group"] for r in s["candidates"] if r["phase"]=="deployment_probe")
    no_safe_rows=[r for r in s["candidates"] if r["no_safe"]]
    probe_seconds=sum(c["probe_wall_s"] for c in cases)
    schedule_share=100*sum(m["schedule_s"] for m in metrics)/probe_seconds
    kernel_share=100*sum(m["kernel_compile_s"] for m in metrics)/probe_seconds
    post_s=sum(r["offline_analysis_s"] for r in s["new_proxy"])+f["elapsed_s"]
    example_proofs=[]
    for idx in [example["setfreq_indices"],example["optimal_indices"]]:
        policy=next(r for r in s["policies"] if r["case_id"]==example["case_id"] and r["dep"]==example["dep"] and r["indices"]==idx)
        example_proofs.append(f"[{'SetFreq' if idx==example['setfreq_indices'] else '联合调频'}证书](raw/{policy['case_id']}/{policy['phase']}/{policy['proof']})")
    summary_table="\n".join(table);safety_table="\n".join(safety)
    write("README.md",f"""# Kim节能空间与缺陷定位：一次限定诊断

**结论：未找到低于六个工况最佳Kim-Anytime+SAFE的方案，实得节能率均为0%。** 六个获胜部署的完整频率域最优性已认证。其他部署确实存在SetFreq漏搜，最大同部署损失4.013%，但补回这项损失仍比最佳Kim高耗能7.150%。现有证据不支持为追求最终3%–5%节能立即开发新算法；也不构成431万域没有更优解的证明。

执行冻结：[1b03f12](https://github.com/YBEMR/paper/commit/{env['execution_commit']})；独立分支 `codex/kim-gap-diagnostics`，基于 `72afaa4`。本轮只新增此目录。旧M2、Energy-Only、Kim、物理评价器和历史数据未改；没有重跑Kim，没有使用新增网络研究线。

## 1. 六工况结果

{summary_table}

时间为两个独立冷进程各自的完整墙钟，不是合计120秒：每段上限120秒、116秒停止接纳，各运行一次。固定调频全部完成；部署探查全部按预算停止，剩余候选保留为未决。本轮最好SAFE包括已知Kim方案的完整重放，不表示发现了新方案。能耗只在同一负载内比较。

六个基准均为 **X4139374，LLL/LLL/LHL/LHL**。原始/A负载选历史种子20261121，B负载选20261123；均是各工况三个种子的最低SAFE能耗，并列按种子升序。固定部署下无温限最低**连续**能耗候选已经SAFE，因此完整频率下界直接闭合，无需热回退。核的仿射能耗与完整评价器一致到1e-7 J内。

{safety_table}

每个SAFE证书都覆盖500个请求、40 ms期限、完整10.04秒计能窗和四节点连续峰温，未用场景末温代替峰温。三种负载、25/30°C环境、四节点初温30°C、FP16、温度相关漏电及原功热参数均直接复用。负载A改变请求份额，负载B改变共现结构，详见冻结输入及[原配置](../ch3_algorithm_selection/config.json)。

## 2. SetFreq存在局部缺陷，但未损伤六个最终基准

197个已完成“部署—工况”判定中，191个有SAFE最优方案，6个证明无SAFE频率。191个含6个基准，185个为探查候选；其中58个候选存在SetFreq能耗损失，133个未发现损失（含6个基准）。这不是191个不同部署，也不是对全域抽样误差的统计估计。

最明显案例是 **A 25°C、X4308295**：

| 项目 | SetFreq | 同部署联合频率最优 |
|---|---:|---:|
| 四场景频率 | LLM/LLM/LHL/LHL | LML/LML/LHL/LHL |
| 真实全窗能耗 J | {example['setfreq_j']:.9f} | {example['joint_optimum_j']:.9f} |
| 独立场景代理总和 J | {example['setfreq_proxy_j']:.9f} | {example['optimal_policy_proxy_j']:.9f} |

该部署内节能 **{example['within_deployment_saving_pct']:.6f}%**；但最低能耗仍比本工况Kim的{ref['kim_energy_j']:.9f} J高 **{-example['versus_best_kim_saving_pct']:.6f}%**。{'; '.join(example_proofs)}。

58个改进频率策略的独立代理能耗也全部更低，支持原SetFreq有限坐标扫描遗漏更优频点。原实现从HHH出发、按GPU/CPU/DLA顺序扫描两轮；本例需要改变GPU/DLA频率组合。**不能将这58个局部缺口解释为连续热代理反转造成的损失，更不能报成超过最终Kim的节能。** 未修改原SetFreq，也未开发替代算法。

![固定部署损失与最终收益](figures/frequency_regret.png)

代理复算仅使用已归档完整轨迹：对于同一场景、频率及长度，入口温度的仿射能耗系数为 `w = slopeᵀ ∫exp(At)dt`，故 `E_reset = E_continuous - w·(T_entry−30)`。原SetFreq策略的复算代理与原记录最大误差{f['max_proxy_reconstruction_error_j']:.3g} J。这里只求已知系数并做代数还原，没有新增调度、物理回放或搜索调用。[归因脚本](frequency_attribution.py)与[逐对结果](frequency_attribution.csv)。

## 3. 部署遗漏和代理偏差：哪些得到证明

候选仅由冻结拓扑规则选出：40个切点/绑定/名额交换邻居，8个至少三个网络切点结构不同的远端部署；六工况共享列表和顺序，未按代理分数筛选。共完成191个探查部署—工况对，涉及39个不同部署，另有6次基准固定调频。完成组数为：原切点{groups['cut']}、绑定{groups['binding']}、交换{groups['exchange']}、补充切点{groups['cut_fill']}、远端{groups['distant']}。每工况只覆盖23–39/48个计划候选，全部未完成项和正在处理项保存在原始结果。

**没有找到低于最佳Kim的完整SAFE见证，故本轮未证实其部署搜索遗漏了更好最终方案。** 不能称48个候选集合全局最优，更不能称4,319,803域最优。

历史18次Kim运行的有效候选池都已完整认证；每次按代理总和排序的第一个SAFE方案，恰好也是其完整认证池中的最低真实SAFE能耗。已观察到{sum(r['ranking_inversions'] for r in history):,}次两两排序反转记录（跨种子可能重复，非独立样本），最大真实能耗反转幅度{worst['largest_reversal']['energy_difference_j']:.6f} J，来自A 30°C种子20261121。**存在排序偏差，但没有观察到由认证顺序导致的最终损失。**

Lexicase使用四场景代理向量；代理总和只用于认证池排序。因此本轮两两反转不能证明遗传选择受到了何种因果影响。没有更优遗漏见证或反事实遗传运行，也就不能把生成偏差写成已证实原因。[历史逐次审查](historical_proxy.csv)、[本轮已评估策略](new_proxy_policies.csv)、[空改进见证归因记录](attribution.json)均保留。

6个无SAFE判定均有59,049条满足期限的频率序列，全部连续超温：original 30°C的X4319802/X4139360，以及B 30°C的X4319802/X4319620/X4139360/X4134092。它们证明对应固定部署无安全频率，不意味着该工况整个部署域无解。其余191个固定部署的无温限能耗最小候选都SAFE；本轮没有出现“固定部署通过更高能耗频率回退取得SAFE”的新例子。

## 4. 成本、正确性与范围

![覆盖范围和成本](figures/coverage_cost.png)

部署探查总墙钟成本中，事件调度/期限检查约{schedule_share:.1f}%，热核系数构建约{kernel_share:.1f}%；其余为初始化、核查询、SetFreq查表、联合频率、完整认证、日志及进程收尾等。两项主成本直接分别计时；“其余”为总墙钟减去这两项，避免把包含式回放/请求明细计时重复相加。详细调用数和热回退计数见[成本表](phase_costs.csv)。进程外无求解功能的压缩/校验归档另行执行，不计为算法时间；没有免费提供预构建热核。

实验1初次SAFE用时5.76–5.85秒、实验2为3.89–4.86秒，均是**重放已知Kim输入**，不能当作从零发现优质解的速度。实验1在10.41–11.34秒完成最优性认证；历史Kim不同批次耗时不用于严格速度比。实验3归档分析和代数归因共约{post_s:.2f}秒，不追加候选或物理评价。

全部12进程正常结束，未追加运行/种子/预算。每个进程对历史获胜策略的完整物理记录和500请求明细回归相等。离线核验覆盖70个冻结源/输入文件哈希、原始文件收据、完整27⁴编码数组（总计7,818,300条期限可行序列）、197个固定部署结论、261次完整物理记录，其中255份SAFE证书和127,500条请求完成记录；核验PASS。197个结论包括191份最低SAFE证书与6份无SAFE证明，不能全部称为有解最优证书。[核验结果](verification.json)。

当前仍是冻结合成平台的模型结论。DLA合法性遵守已有拓扑/容量规则，不新增真实硬件编译、放置或功耗实测证据。

## 5. 取舍

1. **SetFreq是否有损失？** 六个最强Kim部署没有；其他已完成部署有明确损失，最大4.013%，但没有改变最终最佳部署。
2. **部署搜索是否遗漏更优SAFE？** 本轮没有找到证据。有限探查不能排除未评估域内的更优部署。
3. **连续热代理偏差是否造成实际损失？** 排序偏差存在；最终能耗损失及生成因果关系均未证实。已确认的58个调频缺口在Kim自身代理目标下也成立。
4. **是否找到最终3%–5%节能空间？** 没有。不能将局部4.013%替换为相对最强Kim的收益。
5. **改进上限是多少？** 固定六个获胜部署的全频率域，额外节能为0%（1e-7 J数值容差）；加上各工况已完成探查部署，最好值仍相同。48候选未完成部分和431万全域没有有效全局下界，故不能给出“全域至多可改进x%”的非平凡上限。
6. **是否开发新算法？** 不建议据此启动以击败最终Kim能耗为目的的新算法轮次。保留SetFreq局部漏搜作为已证实实现局限；现有证据尚不能将其转化为第三章最终节能贡献。本轮到此结束，不扩大候选、温度、负载或种子。

## 6. 交付索引

- [冻结协议](PROTOCOL.md)、[实际配置](formal_experiment_config.csv)、[环境](environment.json)、[冻结源哈希](execution_manifest.json)。
- [六工况对比CSV](comparison.csv)、[候选结论](candidate_results.csv)、[频率归因](frequency_attribution.csv)、[全部SAFE见证索引](safe_witnesses.csv)。
- [原始记录与完整频率数组](raw/)、[绘图数据](figure_data.csv)、[可编辑SVG](figures/)、[报告与绘图脚本](build_outputs.py)。
- [复算说明](REPRODUCE.md)、[归档清单](archive_manifest.json)。新数据与旧结果分目录保留；执行冻结与结果为两个不同提交。
""")
    print("Generated report, actual configuration and two PNG/SVG figures from archives only.")


if __name__ == "__main__":
    main()
