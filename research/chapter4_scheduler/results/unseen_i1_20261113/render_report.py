"""Render saved six-slot evidence; no scientific imports or evaluation."""
from fractions import Fraction as F
import json
from pathlib import Path

REPO=next(p for a in Path(__file__).resolve().parents for p in (a,a/'paper') if (p/'research/chapter4_scheduler/i1').is_dir())
ROOT=REPO/'research/chapter4_scheduler/results/unseen_i1_20261113'
OUT=ROOT/'execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
s,a,plan,batch=[read(OUT/n) for n in ('summary.json','analysis.json','plan.json','batch_return.json')]
assert a['passed'],[k for k,v in a['checks'].items() if not v]
rows=s['rows'];details={d['id']:d for d in a['details']}
name=lambda v:v.replace('__n','–')
fmt=lambda v,n=3:'—' if v is None else f'{float(F(v)):.{n}f}'
yes=lambda v:'是' if v else '否'
arms=lambda case:{r['arm']:r for r in rows if r['case_id']==case}
gates=sum(r['admission_gate_triggered'] for r in rows)
text=['# 冻结 I1/ON 的两个新参数根验证','',
    '2026-11-13。U03、U04各12 Stage/场景、2场景、50°C；每根HEFT-I1、OFF-I1、ON-I1各一次。统一300秒方法总预算、180秒初始化新工作准入门限，最终SAFE另用60秒根完整复评。六次结果全部保留。固定串行顺序：U03 HEFT→OFF→ON，U04 ON→OFF→HEFT；没有重复计时或多种子方法运行。','',
    '## 结论','',*(OUT/'conclusions.md').read_text(encoding='utf-8').splitlines(),'',
    '## 覆盖与能耗','',
    '| 新根 | HEFT-I1/J | OFF-I1/J | ON-I1/J | ON比HEFT节能 | ON比OFF节能 | 三臂初解一致 |',
    '|---|---:|---:|---:|---:|---:|---|']
for t,p in zip(a['three_arm_comparisons'],a['pairs']):
    ar=arms(t['case_id'])
    text.append(f"| {name(t['case_id'])} | {fmt(ar['HEFT']['energy_upper_J'],9)} | {fmt(ar['OFF']['energy_upper_J'],9)} | {fmt(ar['ON']['energy_upper_J'],9)} | {fmt(t['ON_vs_HEFT_saving_percent'],6)}% | {fmt(p['observed_ON_vs_OFF_saving_percent'],6)}% | {yes(t['all3_same_initial_candidate_and_energy'])} |")
text+=['','能耗为完整能量区间上界，实际接纳使用严格区间改善。跨根窗口、工作量不同，仅在同根内计算节能率。三臂独立调用同一I1，未复制候选、共享缓存或为对齐结果补跑。','',
    '| 新根/方法 | 初解/J | 最终SAFE/复评 | 首份SAFE/s | 相对自身初解节能 | 终止/失败原因 |',
    '|---|---:|---|---:|---:|---|']
for r in rows:
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {fmt(r['initial_energy_upper_J'],9)} | {yes(r['safe'])}/{yes(r['post_passed'])} | {fmt(r['first_SAFE_at_s'])} | {fmt(r['saving_vs_own_initial_percent'],6)}% | {r['terminal']} / {r['reason']} / {r['failure_reason'] or '无'} |")
text+=['',f"最终SAFE并复评通过 {s['SAFE_post_successes']}/6。按方法分别报告2次中的成功次数："+'，'.join(f"{arm}={sum(r['safe'] and r['post_passed'] for r in rows if r['arm']==arm)}/2" for arm in ('HEFT','OFF','ON'))+'。样本仅两个根，不估计总体成功概率。','',
    '## 初解覆盖与预算分配','',
    '| 新根/方法 | 构造尝试：优先级/OPP/结果/失败任务 | 质量阶段停止原因 | 180秒门限 |',
    '|---|---|---|---|']
for r in rows:
    d=details[r['id']]
    c='；'.join('/'.join(str(e.get(k)) for k in ('priority_policy','opp_rank','status','failed_shared_stage')) for e in d.get('initialization_construction_attempts',[]))
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {c or '无结果'} | {r['initialization_stop_reason']} | {yes(r['admission_gate_triggered'])} |")
text+=['','原始构造的失败不等同于实例不可行；后备构造获得完整SAFE才构成安全见证。所有失败构造、未改善候选及原因保留。初解中的设备/频档质量调整与ON后续固定部署搜索分别统计。','',
    '| 新根/方法 | 初始化/s | 交接时刻/s | 搜索余量/s | 实际搜索/s | 方法总时/s | 完整SAFE评价：初解+搜索 |',
    '|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {fmt(r.get('initialization_s'))} | {fmt(r.get('initialization_completed_at_s'))} | {fmt(r['remaining_search_budget_s'])} | {fmt(r.get('search_s'))} | {fmt(r['method_elapsed_s'])} | {r.get('initialization_full_SAFE_evaluations',0)}+{r.get('search_full_SAFE_evaluations',0)} |")
text+=['','300秒预算从科学导入前开始，覆盖输入核验、初始化和搜索；搜索余量=300−初解交接时刻。初始化阶段时长不含此前导入，所以与交接时刻不同。HEFT交接后按定义结束，不使用余量搜索。解释器启动、结果序列化、进程墙钟与复评另列在指标中。',
    f"180秒准入门限共触发 {gates} 次；已经准入的评价可完成到180秒之后，始终受同一300秒根约束。门限不是初始化硬上限，也不保证固定120秒搜索余量。"+('本批未产生真实门限截断，不能验证截断后的初解质量和三臂一致性。' if gates==0 else ''),'',
    '## 完整评价成本与搜索范围','',
    '| 新根/方法 | 调用/返回SAFE/中断 | 初始化评价/s | 搜索评价/s | 单次均值/最大值/s | 返回评价占方法时间 |',
    '|---|---:|---:|---:|---:|---:|']
for r in rows:
    d=details[r['id']];cost=d.get('complete_evaluation_cost_s',{})
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {r.get('evaluation_attempts',0)}/{r.get('returned_SAFE_claims',0)}/{r.get('interrupted_attempts',0)} | {fmt(cost.get('initialization'))} | {fmt(cost.get('refinement'))} | {fmt(d.get('all_returned_evaluation_mean_s'))}/{fmt(d.get('all_returned_evaluation_max_s'))} | {fmt(d.get('returned_evaluation_share_of_method_percent'))}% |")
text+=['','评价时间由保存的调用起止时钟计算，包括完整合法性和连续电热评价；未返回的中断调用另列analysis.json，不混入完成评价均值。所有热违规、数值未决和中断计数见metrics.csv。墙钟存在机器负载波动，单次差异不证明稳定加速。','',
    '| 新根/方法 | 结构尝试 | 送评提案 | 严格接纳 | 额外边尝试/送评/接纳 |',
    '|---|---:|---:|---:|---:|']
for r in rows:
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {r.get('graph_reconstruction_attempts',0)} | {r.get('graph_proposals',0)} | {r.get('graph_strict_improvements',0)} | {r['extra_edge_graph_attempts']}/{r['extra_edge_proposals']}/{r['extra_edge_accepts']} |")
text+=['','OFF仅关闭额外阻塞边，其他节能目标、关联OPP、主要资源次序、模板、安全评价和严格接纳保持一致。结构合法候选可能重复，结构尝试不等于完整评价次数。含额外边的接纳还联合改变OPP/次序，其步骤下降不能单独归因于一条边。','',
    '| 新根 | ON/OFF相同初解及初始化序列 | 三臂相同初始化序列 | 两臂自然结束 | 最终候选相同 |',
    '|---|---|---|---|---|']
for t,p in zip(a['three_arm_comparisons'],a['pairs']):
    text.append(f"| {name(t['case_id'])} | {yes(p['comparable_SAFE_pair'])} | {yes(t['all3_same_initial_sequence'])} | {yes(p.get('both_searches_completed'))} | {yes(p['same_final_candidate'])} |")
text+=['','初解或初始化路径不同的情况下，只报告同总预算下的观测方法差异，不做纯额外边归因；若搜索被预算截断，也不能声称两臂邻域均已充分搜索。即使自然结束，仍仅穷尽当前启发式声明的邻域，不证明全局最优。','',
    '## 新参数根与科学模型','',
    f"科学源码先冻结于 `{plan['subject_commit']}`，随后才按固定种子首次生成U03/U04；此前512份源码与上一轮快照逐字节相同，仅增加新输入桥接、六槽执行入口和测试。本轮I1、ON/OFF、第三章电热模型及评价精度未修改。运行前核对原分支6d67cf2及另一研究分支223097d；后者新提交无第四章源码变化。",'',
    '| 根 | 种子 | 每场景Stage | 场景数 | 合法模式 | 窗口/ms | C1/C2工作量 |',
    '|---|---:|---:|---:|---:|---:|---:|']
for g in a['generation']:
    m=g['metrics'];w=m['work_units_by_scene']
    text.append(f"| {name(g['case_id'])} | {g['seed']} | 12 | 2 | {m['mode_count']} | {m['window_ms']} | {fmt(w['C1'])}/{fmt(w['C2'])} |")
text+=['','命名空间ch4-independent-i1-v1；沿用既有异构工作负载分布和branch_join拓扑族，直接生成12 Stage基础根，不从U01/U02修改。每根16个共享Stage身份、24次任务执行，其中8个身份跨两场景共有；场景等权，初温50°C、温限80°C，5ms起点域。','',
    '生成前固定根名、种子和协议，各根只生成一次。全H时间参考仅用于原规则期限β=1.3及窗口推导，再做静态合法性检查；生成阶段电热评价、方法预跑、重试和替换均为0。参考排程/部署只存于生成证据，方法只加载instance/config，未将其注入初解器。没有根据结果筛选参数根。','',
    '“独立新根”指此前未参与I1/ON设计的新随机参数流；仍来自同一合成分布与拓扑族，不是外部盲测数据或独立硬件平台。共享频率域、依赖、互斥、期限、全场景全窗口连续热安全、auto-L及原0.001K温度包络与10⁻⁶能量绝对/相对精度均保留。','',
    '## 完整性与边界','',
    f"23项必要模拟/回归检查首轮通过。实际方法6个固定槽，SAFE且复评通过{s['SAFE_post_successes']}次；完整评价调用{sum(r.get('evaluation_attempts',0) for r in rows)}次，返回SAFE {sum(r.get('returned_SAFE_claims',0) for r in rows)}，热违规{sum(r.get('returned_thermal_violation_receipts',0) for r in rows)}，数值未决{sum(r.get('returned_unresolved_receipts',0) for r in rows)}，中断{sum(r.get('interrupted_attempts',0) for r in rows)}。批次墙钟{batch['wall_s']:.3f}秒，0重试；批次停止原因：{batch['stop_reason'] or '无'}。",'',
    f"最终解最大峰温上界{max((r.get('peak_temperature_upper_C') or 0) for r in rows):.6f}°C。最终安全复评使用独立进程但同一数值实现，未做独立求解器验证或硬件标定；该温度条件不能据此代表紧热约束能力。",'',
    '本轮只验证两个新根，每种配置一次，不证明总体成功率、统计显著性、普遍优势或更大规模成本。旧I0、I1、U01/U02及全部新结果保留。未设计I2，未运行24 Stage或SA。','',
    '证据：[全部6次指标](execution/metrics.csv)、[轨迹及成本分析](execution/analysis.json)、[冻结计划](execution/plan.json)、[生成计划](input_generation/input_plan.json)、[生成清单](input_generation/inputs_manifest.json)、[批次记录](execution/batch_return.json)、[模拟检查](execution/precheck.json)。','']
(ROOT/'summary.md').write_text('\n'.join(text),encoding='utf-8')
print({'report_written':True,'safe_posts':s['SAFE_post_successes'],'gate_triggers':gates})
