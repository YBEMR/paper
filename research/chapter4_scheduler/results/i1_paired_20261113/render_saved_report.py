"""Describe the four saved paired results, without new scientific calls."""
from fractions import Fraction as F
import json
from pathlib import Path

REPO=next(p for a in Path(__file__).resolve().parents for p in (a,a/'paper') if (p/'research/chapter4_scheduler/i1').is_dir())
OUT=REPO/'research/chapter4_scheduler/results/i1_paired_20261113'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
s,a,plan,batch=[read(OUT/n) for n in ('summary.json','analysis.json','plan.json','batch_return.json')]
assert a['passed'],[k for k,v in a['checks'].items() if not v]
rows=s['rows'];details={d['id']:d for d in a['details']}
name=lambda v:v.replace('__n','–')
fmt=lambda v,n=3:'—' if v is None else f'{float(F(v)):.{n}f}'
arms=lambda case:{r['arm']:r for r in rows if r['case_id']==case}
text=['# ON-I1/OFF-I1 两实例配对实验', '',
    '2026-11-13。材料类型：已授权的冻结算法配对实验。范围：U01–12、U02–12各ON-I1/OFF-I1一次，共4次方法与最多4次最终SAFE复评。原I0/I1及历史结果保留，无I2、24 Stage、SA或输入调参。', '',
    '## 最终能耗与配对差异', '',
    '| 实例 | ON初解/J | OFF初解/J | ON最终/J | OFF最终/J | ON相对OFF节能 | 初解/路径可比 |',
    '|---|---:|---:|---:|---:|---:|---|']
for p in a['pairs']:
    on,off=arms(p['case_id'])['ON'],arms(p['case_id'])['OFF']
    text.append(f"| {name(p['case_id'])} | {fmt(on['initial_energy_upper_J'],9)} | {fmt(off['initial_energy_upper_J'],9)} | {fmt(on['energy_upper_J'],9)} | {fmt(off['energy_upper_J'],9)} | {fmt(p['observed_ON_vs_OFF_saving_percent'],6)}% | {'一致' if p['comparable_SAFE_pair'] else '不满足'} |")
text += ['', '能耗列为完整能量区间上界，接纳使用严格区间比较。配对可比要求两臂均有复评通过的SAFE，且初解排程、初解能量区间和初始化候选序列相同；初解元数据另去除时钟字段后比较。两臂独立运行，没有复制初解、共享缓存或为对齐结果补跑。', '',
    '| 实例/方法 | 相对自身初解节能 | 已进入搜索 | 严格接纳次数 | 终止原因 |',
    '|---|---:|---|---:|---|']
for r in rows:
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {fmt(r['saving_vs_own_initial_percent'],6)}% | {'是' if r['search_entered'] else '否'} | {r.get('graph_strict_improvements',0)} | {r['terminal']} / {r['reason']} |")
text += ['', 'U01–12回答“新初解下原阻塞路径机制是否仍有净贡献”；U02–12回答“覆盖修复后能否进入原搜索并继续节能”。两问分别由配对差值和相对自身初解的变化回答，不能仅凭I1成功初始化推断整个ON更优。', '',
    '## 额外阻塞边的实际作用', '',
    '| 实例/方法 | 结构尝试 | 额外边尝试 | 额外边结构合法 | 额外边送评 | 额外边接纳 |',
    '|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    d=details[r['id']]
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {r.get('graph_reconstruction_attempts',0)} | {r['extra_edge_graph_attempts']} | {d.get('extra_graph_states',{}).get('COMPLETE_LEGAL_CANDIDATE',0)} | {r['extra_edge_proposals']} | {r['extra_edge_accepts']} |")
text += ['', 'OFF仅关闭冻结版本的额外阻塞边调整；目标节能模式、关联任务OPP、主资源次序、排程模板、连续电热评价与严格接纳均保留。结构合法数可能含重复候选，不能与实际评价数混用。', '',
    '| 实例/方法 | 含额外边接纳步骤下降/J | 普通接纳步骤下降/J |',
    '|---|---:|---:|']
for r in rows:
    d=details[r['id']]
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {fmt(d.get('extra_accepted_step_difference_J'),9)} | {fmt(d.get('ordinary_accepted_step_difference_J'),9)} |")
text += ['', '步骤下降与ON/OFF净差是不同量：含额外边的步骤还联合改变目标/关联任务模式和资源次序，后续普通调整也会受路径影响。不能把步骤下降总和写成单条边的独立因果收益。完整接纳链、被阻塞期限、反转边与任务变化见 analysis.json。', '',
    '| 实例/ON接纳步骤 | 目标降档 | 额外反转边 | 步骤下降/J |',
    '|---|---|---|---:|']
for r in rows:
    if r['arm']!='ON':continue
    for step in details[r['id']].get('accepted_steps',[]):
        t=step['target'];edges='；'.join(' → '.join(e) for e in step['additional_reversed_edges']) or '无'
        text.append(f"| {name(r['case_id'])}/{step['accepted_step']} | {t['scene_id']} {t['shared_stage_id']} {t['old_opp']}→{t['target_opp']} | {edges} | {fmt(step['step_upper_difference_J'],9)} |")
text += ['', '## 初始化、搜索余量和完整评价成本', '',
    '| 实例/方法 | 初始化/s | 交接时刻/s | 可用搜索预算/s | 实际搜索/s | 方法总时/s | 完整评价：初始化+搜索 |',
    '|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {fmt(r.get('initialization_s'))} | {fmt(r.get('initialization_completed_at_s'))} | {fmt(r['remaining_search_budget_s'])} | {fmt(r.get('search_s'))} | {fmt(r['method_elapsed_s'])} | {r.get('initialization_full_SAFE_evaluations',0)}+{r.get('search_full_SAFE_evaluations',0)} |")
text += ['', '每次300秒总根覆盖科学导入、输入核验、完整初始化和搜索。可用搜索预算=300−初解交接时刻；实际搜索可因邻域用尽提前结束，未用时间不转移到另一臂。初始化耗时不含前置导入，因此与交接时刻不同；解释器启动、结果序列化及复评另外记录。完整评价统计包含所有调用和失败类型，表内列出完整SAFE评价，完整计数见指标。', '',
    '| 实例/方法 | 初始化停止原因 | 后备触发 | 180秒跨门限评价 | 初始化评价/s | 搜索评价/s |',
    '|---|---|---|---:|---:|---:|']
for r in rows:
    d=details[r['id']];cost=d.get('complete_evaluation_cost_s',{})
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {r['initialization_stop_reason']} | {'是' if r['fallback_used'] else '否'} | {d.get('initial_evaluations_crossing180',0)} | {fmt(cost.get('initialization'))} | {fmt(cost.get('refinement'))} |")
gates=sum(r['admission_gate_triggered'] for r in rows)
text += ['', f"180秒初始化准入门限实际触发 {gates} 次。门限限制新构造/新完整评价的准入，既有评价仍受原300秒根约束；它不是初始化硬上限，也不保证120秒搜索余量。"]
if gates==0:text += ['本批没有真实门限截断，不能从本批单独推断截断负载下的质量和初解一致性。']
if any(not p.get('both_searches_completed',False) for p in a['pairs']):
    text += ['', '本批存在未自然完成搜索的臂。即使初解相同，实际搜索余量和截断位置也会影响最终结果；差值只表示这次同总预算运行的表现，不能解释为两臂邻域均充分搜索后的纯收益。']
text += ['', '## 与此前I1初解和I0配对的关系', '',
    '| 实例/方法 | 初解排程匹配首轮I1 | 初解能量区间匹配首轮I1 |', '|---|---|---|']
for r in rows:
    d=details[r['id']]
    text.append(f"| {name(r['case_id'])}/{r['arm']}-I1 | {d.get('initial_matches_previous_I1_candidate')} | {d.get('initial_matches_previous_I1_energy')} |")
text += ['', '| U01–12方法 | 历史P3 I0最终/J | 本批I1最终/J | I1相对I0最终节能 | 最终排程相同 |', '|---|---:|---:|---:|---|']
for h in a['historical_U01_P3']:
    text.append(f"| {h['arm']} | {fmt(h['old_I0_final_energy_J'][1],9)} | {fmt(h['new_I1_final_energy_upper_J'],9)} | {fmt(h['I1_vs_I0_final_saving_percent'],6)}% | {h['same_final_candidate']} |")
text += ['', '此表只是既有I0结果的描述性参照：初始化策略与运行日期不同，不做跨批墙钟加速比较，也不把I0→I1变化当成纯阻塞边效应。U02–12的旧I0未获得初解，无合法的旧版最终能耗可作节能率分母。', '',
    '## 安全、范围和证据', '',
    f"执行冻结提交 `{plan['subject_commit']}`。运行前核对远程13f7ab7及另一研究分支7eb15d0；后者的新文件属于第三章，没有第四章源码变化。本轮510份已有源码逐字节保持，只新增配对入口和测试；输入仍为原两组12 Stage/场景、2场景、50°C、原完整合法模式和期限/窗口、共享频率域、auto-L及5ms起点。原0.001K温度包络、10⁻⁶能量绝对/相对精度、SAFE标准及ON机制均不变。", '',
    '24项模拟/回归检查通过，包括两臂共用I1、原预算根、OFF搜索计时、180秒边界、总预算耗尽保留SAFE、普通无SAFE继续下一项及技术错误停批。首次测试中一条测试调用多传参数，修正测试后通过；失败日志保留，没有消耗真实实验调用。', '',
    f"实际方法 {len([r for r in rows if r['terminal']!='NOT_RETURNED'])}/4，最终SAFE且复评通过 {s['SAFE_post_successes']}/4；方法内完整评价调用 {sum(r.get('evaluation_attempts',0) for r in rows)} 次，返回SAFE {sum(r.get('returned_SAFE_claims',0) for r in rows)}，热违规 {sum(r.get('returned_thermal_violation_receipts',0) for r in rows)}，数值未决 {sum(r.get('returned_unresolved_receipts',0) for r in rows)}，中断 {sum(r.get('interrupted_attempts',0) for r in rows)}。批次墙钟 {batch['wall_s']:.3f} 秒，0重试；源码、输入、全部失败/无改善记录及接纳链完整保留。", '',
    f"最终峰温上界最大 {max((r.get('peak_temperature_upper_C') or 0) for r in rows):.6f}°C，原温限80°C。每份正常SAFE另用独立进程/60秒根做完整复评，不反馈搜索；复评仍是同一数值实现，不是独立数值求解器或硬件校准。", '',
    '每个配置仅一次；两例均已观察，U02–12参与过初始化诊断。本轮只支持这些固定条件下的覆盖和机制结论，不证明统计显著性、普遍优势或全局最优。单次耗时差异含系统波动；即使观察到完整自然结束，也不能保证更大实例下具有相同成本。', '',
    '## 结果判断', '']
for p in a['pairs']:
    ar=arms(p['case_id']);on,off=ar['ON'],ar['OFF']
    if p['comparable_SAFE_pair']:
        gain=p['observed_ON_vs_OFF_saving_percent']
        text.append(f"- {name(p['case_id'])}：两臂初解及初始化候选路径一致。ON相对OFF净节能 {gain:.6f}%；ON/OFF相对自身初解分别节能 {on['saving_vs_own_initial_percent']:.6f}%/{off['saving_vs_own_initial_percent']:.6f}%。额外边接纳 {on['extra_edge_accepts']} 次；两臂搜索均自然结束={p['both_searches_completed']}。")
    else:text.append(f"- {name(p['case_id'])}：纯机制配对条件不满足，不能把观测最终差异直接归因于额外阻塞边；原因见逐项指标。")
u02=arms('U02__n12')
if all(r['safe'] and r['post_passed'] for r in u02.values()):
    on,off=u02['ON'],u02['OFF']
    text += ['', f"U02–12的ON搜索评价为 {on['search_full_SAFE_evaluations']} 次，OFF为 {off['search_full_SAFE_evaluations']} 次；本次实际搜索时间 {on['search_s']:.3f}/{off['search_s']:.3f} 秒，总时 {on['method_elapsed_s']:.3f}/{off['method_elapsed_s']:.3f} 秒。额外边改变了后续接纳路径，最终能耗却相同：本例支持减少本次搜索评价量，不支持额外最终节能，也不能凭单次墙钟宣称稳定加速。"]
text += ['', '本轮完成后停止。是否增加独立根、紧热条件或规模验证留作下一步决策；本轮不设计I2，不自动运行24 Stage或SA。', '',
    '证据：[全部指标](metrics.csv)、[接纳轨迹与核对](analysis.json)、[冻结计划](plan.json)、[批次记录](batch_return.json)、[模拟检查](precheck.json)。', '']
(OUT/'summary.md').write_text('\n'.join(text),encoding='utf-8')
print({'report_written':True,'safe_posts':s['SAFE_post_successes'],'gate_triggers':gates})
