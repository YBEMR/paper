"""Render12 versus24 saved evidence, without new scheduling or evaluation."""
from pathlib import Path
from fractions import Fraction as F
import csv
import json

REPO=next(p for a in Path(__file__).resolve().parents for p in (a,a/'paper') if (p/'research/chapter4_scheduler/i1').is_dir())
ROOT=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113'
OUT=ROOT/'execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
s,a,plan,batch,comp=[read(OUT/n) for n in ('summary.json','analysis.json','plan.json','batch_return.json','comparison12to24.json')]
rows=s['rows'];details={d['id']:d for d in a['details']}
fmt=lambda v,n=3:'—' if v is None else f'{float(F(v)):.{n}f}'
yes=lambda v:'是' if v else '否'
name=lambda v:v.replace('__n','–')
both=lambda x,y,n=3:fmt(x,n)+' / '+fmt(y,n)
gates=sum(r['admission_gate_triggered'] for r in rows)
t=['# U03/U04：冻结 I1/ON 的12→24 Stage比较','',
    '2026-11-13。材料类型：用户授权的规模实验结果与保存证据分析。每场景24 Stage、2场景、初温50°C；U03/U04各HEFT-I1、OFF-I1、ON-I1一次，统一300秒总预算、180秒初始化新工作准入门限；最终SAFE独立进程完整复评，每次最多60秒。原12 Stage结果直接复用，没有补跑。','',
    '## 结论','',*(OUT/'conclusions.md').read_text(encoding='utf-8').splitlines(),'',
    '## 输入扩展及比较边界','',
    f"执行冻结提交 `{plan['subject_commit']}`。原515份科学/执行源码逐字节不变，只新增24 Stage输入桥接、执行入口和必要测试；I1、ON/OFF搜索及第三章电热模型、安全标准和精度均保持。固定串行顺序：U03 HEFT→OFF→ON，U04 ON→OFF→HEFT。每臂独立构造初解，不复制初解或共享缓存。",'',
    '| 根 | Stage/场景 | 合法模式数 | 窗口/ms | C1工作量 | C2工作量 |',
    '|---|---|---|---|---|---|']
for g in a['generation']:
    m,p=g['metrics'],g['parent_metrics']
    t.append(f"| {g['case_id'][:3]} | 12→24 | {p['mode_count']}→{m['mode_count']} | {p['window_ms']}→{m['window_ms']} | {both(p['work_units_by_scene']['C1'],m['work_units_by_scene']['C1'])} | {both(p['work_units_by_scene']['C2'],m['work_units_by_scene']['C2'])} |")
t+=['','U03/U04保留原命名空间ch4-independent-i1-v1及种子2026111303/2026111304，从保存的12 Stage父输入按原S2规则扩展。原任务的物理/时间参数、合法模式和依赖边全部保留；新增任务使共享身份16→32、两场景执行24→48，其中跨场景共有身份8→16。仍为同一branch_join拓扑族；它们是已观察根的规模扩展，不是两个额外盲测根。','',
    '每根扩展一次；按原全H时间参考与β=1.3规则重新计算期限及窗口。参考只作期限/窗口推导和静态合法性检查，不注入方法初解。生成阶段0电热评价、0方法预跑、0换根/重试。总工作量与窗口并未固定，因此跨规模绝对能耗增长不能直接称为算法能效下降；节能率只在同根同规模内比较。','',
    '## 覆盖、初解和最终能耗','',
    '| 根/方法 | 12初解/J | 12最终/J | 24初解/J | 24最终/J | 24相对自身初解节能 |',
    '|---|---:|---:|---:|---:|---:|']
for c in comp['rows']:
    x,y=c['n12'],c['n24']
    t.append(f"| {c['root_id']}/{c['arm']} | {fmt(x['initial_energy_upper_J'],9)} | {fmt(x['energy_upper_J'],9)} | {fmt(y['initial_energy_upper_J'],9)} | {fmt(y['energy_upper_J'],9)} | {fmt(y['saving_vs_own_initial_percent'],6)}% |")
t+=['','能耗均为完整能量区间上界，算法按严格区间改善接纳。HEFT-I1最终解即同一I1初解器的输出；若180秒截断位置不同，同一初解器不保证三臂得到相同初解。','',
    '| 根/方法 | SAFE且复评通过：12/24 | 24首份SAFE/s | 24初始化停止原因 | 24终止/失败原因 |',
    '|---|---|---:|---|---|']
for c in comp['rows']:
    x,y=c['n12'],c['n24']
    t.append(f"| {c['root_id']}/{c['arm']} | {yes(x['safe'] and x['post_passed'])}/{yes(y['safe'] and y['post_passed'])} | {fmt(y['first_SAFE_at_s'])} | {y['initialization_stop_reason']} | {y['terminal']} / {y['reason']} / {y['failure_reason'] or y['error'] or '无'} |")
t+=['',f"24 Stage最终SAFE并复评通过{s['SAFE_post_successes']}/6；分方法为"+'，'.join(f"{arm}={sum(r['safe'] and r['post_passed'] for r in rows if r['arm']==arm)}/2" for arm in ('HEFT','OFF','ON'))+'。12 Stage此前三臂各2/2；这是固定小样本的覆盖计数，不是总体成功概率。','',
    '## 初始化、搜索与评价成本','',
    '以下每格为12 / 24 Stage，均为原300秒预算内保存的计时。','',
    '| 根/方法 | 初始化/s | 实际搜索/s | 方法总时/s | 初始化完整SAFE评次 | 搜索完整SAFE评次 |',
    '|---|---:|---:|---:|---:|---:|']
for c in comp['rows']:
    x,y=c['n12'],c['n24']
    vals=[both(x[k],y[k],0 if 'evaluations' in k else 3) for k in ('initialization_s','search_s','method_elapsed_s','initialization_full_SAFE_evaluations','search_full_SAFE_evaluations')]
    t.append('| '+c['root_id']+'/'+c['arm']+' | '+' | '.join(vals)+' |')
t+=['','方法总时从科学导入前开始，覆盖输入核验、完整初始化与搜索；初始化阶段时长不含导入，初解交接时刻包含此前成本。解释器启动、序列化和复评另行记录。HEFT交接后按定义结束。四次搜索的记录总时为300.000–300.031秒，所有接纳的SAFE均在300秒内完成；末尾预算未完成候选被拒收，未延长搜索预算。跨批及同批墙钟存在负载波动，不能将单次差异写为稳定速度倍数。','',
    '| 根/方法（24） | 初解交接/s | 搜索余量/s | 调用/返回SAFE/中断 | 单次完整评价均值/最大值/s | 评价占方法时间 |',
    '|---|---:|---:|---:|---:|---:|']
for r in rows:
    d=details[r['id']]
    t.append(f"| {r['root_id']}/{r['arm']} | {fmt(r.get('initialization_completed_at_s'))} | {fmt(r['remaining_search_budget_s'])} | {r.get('evaluation_attempts',0)}/{r.get('returned_SAFE_claims',0)}/{r.get('interrupted_attempts',0)} | {both(d.get('completed_evaluation_mean_s'),d.get('completed_evaluation_max_s'))} | {fmt(d.get('returned_evaluation_share_of_method_percent'))}% |")
t+=['',f"180秒新工作准入门限触发{gates}/6次。已准入的评价可越过180秒完成，仍受同一300秒根约束；门限不是硬截断，也不保证整120秒搜索余量。已有SAFE时停止质量调整属于带安全初解交接，不算覆盖失败。未完成评价与异常中断均保留，不混入完整评价均值；其中wall_time_limit回执表示总预算耗尽，不能误称数值不收敛。均值包含完整合法性及连续电热评价。",'',
    '| 根/方法（24） | 初始化完成评价/s | 搜索完成评价/s | 结构构造/s | 未完成返回/异常中断评价/s |',
    '|---|---:|---:|---:|---:|']
for r in rows:
    d=details[r['id']];cost=d.get('complete_evaluation_cost_s',{})
    t.append(f"| {r['root_id']}/{r['arm']} | {fmt(cost.get('initialization'))} | {fmt(cost.get('refinement'))} | {fmt(r.get('graph_construction_s'))} | {both(d.get('incomplete_returned_evaluation_time_s'),d.get('interrupted_evaluation_time_s'))} |")
t+=['','结构构造与完整评价分别计时；搜索总时还包含目标生成、资源关联和排序等成本。预算用尽不等于无安全解，最后已验证且按时形成的SAFE仍保留；不能用未完成候选覆盖它。','',
    '## 三臂可比性与阻塞边机制','',
    '| 根（24） | 三臂初解一致 | 三臂初始化序列一致 | ON/OFF机制配对成立 | ON比HEFT观测节能 | ON比OFF观测节能 |',
    '|---|---|---|---|---:|---:|']
for triple,pair in zip(a['three_arm_comparisons'],a['pairs']):
    t.append(f"| {triple['case_id'][:3]} | {yes(triple['all3_same_initial_candidate_and_energy'])} | {yes(triple['all3_same_initial_sequence'])} | {yes(pair['comparable_SAFE_pair'])} | {fmt(triple['ON_vs_HEFT_saving_percent'],6)}% | {fmt(pair['observed_ON_vs_OFF_saving_percent'],6)}% |")
t+=['','初解或初始化路径不同，只能比较同总预算下的观测方法结果，不能把最终差值直接归因于额外阻塞边。即使初解相同，搜索被预算截断也可能影响最终结果。自然结束仅代表当前声明邻域用尽，不证明全局最优。','',
    '| 根/方法（24） | 结构尝试 | 送评提案 | 严格接纳 | 额外边尝试/送评/接纳 |',
    '|---|---:|---:|---:|---:|']
for r in rows:
    t.append(f"| {r['root_id']}/{r['arm']} | {r.get('graph_reconstruction_attempts',0)} | {r.get('graph_proposals',0)} | {r.get('graph_strict_improvements',0)} | {r['extra_edge_graph_attempts']}/{r['extra_edge_proposals']}/{r['extra_edge_accepts']} |")
t+=['','所有构造失败、结构拒绝、无改善候选、接纳链与额外边失败原因见analysis.json及各次原始result.json。额外边步骤同时调整模式和资源次序，其下降量不等于单边的独立因果贡献。','',
    '## 安全、完整性与范围','',
    f"25项必要模拟/回归检查首轮通过；保存证据核对{a['checks_passed']}/{len(a['checks'])}通过。科学源码、输入、方法预算与复评标准保持；批次停止原因：{batch['stop_reason'] or '无'}，0重试，墙钟{batch['wall_s']:.3f}秒。全部6个计划槽保留，未运行槽也不能删除。",'',
    f"24 Stage方法内完整评价尝试{sum(r.get('evaluation_attempts',0) for r in rows)}次，返回SAFE {sum(r.get('returned_SAFE_claims',0) for r in rows)}次，热违规{sum(r.get('returned_thermal_violation_receipts',0) for r in rows)}，UNRESOLVED回执{sum(r.get('returned_unresolved_receipts',0) for r in rows)}，中断{sum(r.get('interrupted_attempts',0) for r in rows)}。最终峰温上界最大{max((r.get('peak_temperature_upper_C') or 0) for r in rows):.6f}°C，温限80°C。",'',
    '完整复评使用独立进程但同一数值实现，未做独立求解器或硬件标定。连续热精度、能量误差标准、共享频率域、全场景全窗口判据均与12 Stage一致。每配置仅一次，不作统计显著性或总体优势主张。本轮没有调整算法、期限生成规则或精度，没有重跑12 Stage或启动SA。','',
    '证据：[12/24全部指标](execution/metrics12to24.csv)、[24 Stage指标](execution/metrics.csv)、[规模比较](execution/comparison12to24.json)、[轨迹与核对](execution/analysis.json)、[冻结计划](execution/plan.json)、[输入生成及父系](input_generation/inputs_manifest.json)、[批次记录](execution/batch_return.json)。','']
(ROOT/'summary.md').write_text('\n'.join(t),encoding='utf-8')
combined=[]
for c in comp['rows']:
    for n in (12,24):combined.append({'root_id':c['root_id'],'arm':c['arm'],'stages_per_scene':n,**c['n'+str(n)]})
with (OUT/'metrics12to24.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(combined[0]));w.writeheader();w.writerows(combined)
print({'report_written':True,'comparison_rows':len(combined),'safe_posts':s['SAFE_post_successes'],'gates':gates})
