"""Summarize saved results. No scientific imports, no new experiments."""
from pathlib import Path
from fractions import Fraction as F
import json

ROOT=next(p for ancestor in Path(__file__).resolve().parents for p in (ancestor,ancestor/'paper')
          if (p/'research/chapter4_scheduler/i1').is_dir())
OUT=ROOT/'research/chapter4_scheduler/results/i1_initialization_20261112'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
s,a,plan,batch=[read(OUT/n) for n in ('summary.json','analysis.json','plan.json','batch_return.json')]
assert a['passed']
rows=s['rows'];detail={d['id']:d for d in a['details']}
name=lambda x:x.replace('__n','–')
fmt=lambda x,n=3:'—' if x is None else f'{float(F(x)):.{n}f}'
pair={r['arm']:r for r in rows if r['case_id']=='U01__n12'}
old,new=pair['I0'],pair['I1']
cut=old['method_elapsed_s']-new['method_elapsed_s']
gate=[r for r in rows if r['admission_gate_triggered']]
cross=[x for d in a['details'] for x in d['crossing_admission_evaluations']]
u02=rows[0]
text=['# I1 首轮五次初始化验证', '',
    '2026-11-12。按用户批准的最小方案实现 I1，并完成固定五次初始化运行与各一次完整复评。I0 原实现及旧结果保留，ON 搜索核心保持；本轮无真实 ON-I1/OFF-I1 配对、24 Stage 或 SA。', '',
    f"**覆盖：U02–12 原四次失败仍被复现，唯一后备构造取得完整 SAFE；I1 在本轮四个固定实例均有 SAFE，五次运行均通过复评。成本与质量：U01–12 同批 I1 比 I0 少 {cut:.3f} 秒、少 {old['evaluation_attempts']-new['evaluation_attempts']} 次完整评价，初解能耗上升 {s['comparison']['I1_energy_increase_percent']:.6f}%。** 这是单次描述性对照；U02–12 已参与 I1 诊断设计，不是盲测成功率证明。", '',
    '## 五次运行全部结果', '',
    '| 顺序 | 实例/版本 | 首 SAFE/s | 首 SAFE/J | 交接初解/J | 初始化/s | 总时/s | 完整评价数 | 复评 |',
    '|---|---|---:|---:|---:|---:|---:|---:|---|']
for i,r in enumerate(rows,1):
    d=detail[r['id']]
    text.append(f"| {i} | {name(r['case_id'])}/{r['arm']} | {fmt(r['first_SAFE_at_s'])} | {fmt(d['first_SAFE_energy_J'][1],9)} | {fmt(r['energy_upper_J'],9)} | {fmt(r['initialization_s'])} | {fmt(r['method_elapsed_s'])} | {r['evaluation_attempts']} | {'SAFE' if r['post_passed'] else '失败'} |")
text += ['', '能耗列为完整区间上界，精确上下界保存在原始结果和指标表。初始化时长仅含初始化阶段；方法总时还含科学导入、输入核验和交接。五次均为初始化专用运行，搜索耗时及搜索评价数均为0。', '',
    '## 覆盖修复来自何处', '',
    '| U02–12 初始尝试 | 排序 | 结果 |', '|---|---|---|']
for e in detail[u02['id']]['initial_constructions']:
    text.append(f"| {dict([(None,'默认'),(0,'H'),(1,'M'),(2,'L')])[e['opp_rank']]} | {e['priority_policy']} | {e['status']} / {e.get('reason') or e['assessment_state']} |")
fallback=detail[u02['id']]['initial_constructions'][-1]
text += ['', '前四次原构造的失败元数据与旧 I0 完全相同；新增的第五次仅替换就绪共享身份排序，插入与模式选择逻辑保持。后备优先序为：', '',
    '`'+' → '.join(fallback['shared_priority'])+'`', '',
    f"后备首 SAFE 为 {fmt(detail[u02['id']]['first_SAFE_energy_J'][1],9)} J，经过原两类质量调整后交接 {fmt(u02['energy_upper_J'],9)} J，严格接纳 {u02['local_accepted']} 次。其他三个 I1 实例首次原排序构造即成功，未调用后备。后续重构均沿用各自成功排序。", '',
    '该结果支持这个已知失败例的覆盖修复，不证明一般可行性完备。P1 保存的全 H 参考只是独立诊断证据，没有作为输入、候选或初解注入；新执行目录只复制了原 instance/config，不向初始化器提供生成证据。', '',
    '## 质量调整工作量', '',
    '| 实例/版本 | 阶段 | 构造数 | 结构拒绝 | 完整评价 | 严格接纳 | 评价耗时/s |',
    '|---|---|---:|---:|---:|---:|---:|']
labels={'shared-unit':'共享设备','execution-opp':'执行OPP','one-start-delay':'单步延后'}
for r in rows:
    for stage in detail[r['id']]['quality_stages']:
        text.append(f"| {name(r['case_id'])}/{r['arm']} | {labels[stage['kind']]} | {stage['constructed']} | {stage['structure_rejected']} | {stage['physical_evaluations']} | {stage['accepted']} | {fmt(stage['evaluation_wall_s'])} |")
text += ['', '上述质量阶段不含首解构造。结构拒绝表示原构造器未形成合法完整候选；它们不消耗完整电热评价。I1 的单步延后阶段预先取消，不代表这些合法候选不安全。接纳仍要求新能耗上界严格低于当前下界。', '',
    '## 180 秒准入门限和交接预算', '',
    '| 实例/版本 | 停止原因 | 交接时刻/s | 总预算剩余/s |', '|---|---|---:|---:|']
for r in rows:
    reason=r['initialization_stop_reason'] or r['initialization_status']
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {reason} | {fmt(r['initialization_completed_at_s'])} | {fmt(r['remaining_at_handoff_s'])} |")
text += ['', f"四次 I1 中准入门限触发 {len(gate)} 次，已准入评价跨越180秒返回 {len(cross)} 次。所有 I1 构造和物理评价均在180秒前获准，全部 SAFE 在原300秒根预算内完成。"]
if cross:
    for d in a['details']:
        for c in d['crossing_admission_evaluations']:
            text.append(f"- {d['id']}：{c['source']} 于 {fmt(c['admitted_at_s'])} 秒准入，{fmt(c['completed_at_s'])} 秒完成；替换档案={c['incumbent_replaced']}。")
else:
    text += ['', '本轮真实运行没有跨门限评价，因此跨门限完成、无新工作、SAFE交接及总预算耗尽语义的证据来自模拟测试。不能将“未触发”写成真实负载下验证了硬截断。']
text += ['', '180秒是新初始化工作准入门限，既有评价继续受300秒总预算约束；不保证初始化硬止于180秒或至少剩余120秒。I0 对照保留原完整增强HEFT流程，只受原300秒总预算约束；对它施加I1截断会改变强基线。实际总时/进程时/归档开销分别留存。', '',
    '## 初解质量代价与计算瓶颈', '',
    '| 实例 | I0参照 | I0初解/J | I1初解/J | I1能耗增加 | 原单步延后评价数 |',
    '|---|---|---:|---:|---:|---:|']
for c in a['comparisons']:
    text.append(f"| {name(c['case_id'])} | {'同批新跑' if c['baseline']=='same_batch_I0' else '历史P3初解'} | {fmt(c['baseline_energy_J'][1],9)} | {fmt(c['I1_energy_J'][1],9)} | {c['energy_increase_percent']:.6f}% | {c['I0_delay_evaluations']} |")
all_pre=all(c['same_full_pre_delay_path'] for c in a['comparisons'])
text += ['', ('三个原可行实例的 I1 完整候选/能耗序列，均与对应 I0 单步延后前的完整路径一致。因此本批观测到的质量代价可定位到省去尾部单步延后。' if all_pre else '候选前缀是否一致、是否完成原两类质量阶段见 analysis.json；不能预先把全部差异归于去掉单步延后。'), '',
    f"U01–12 同批方法总时由 {fmt(old['method_elapsed_s'])} 降至 {fmt(new['method_elapsed_s'])} 秒，减少 {cut:.3f} 秒（{100*cut/old['method_elapsed_s']:.3f}%）；完整评价由 {old['evaluation_attempts']} 降至 {new['evaluation_attempts']}。单次时长受系统波动影响，尚不能声称稳定加速；两个6 Stage实例仅比较历史初解质量，不计算跨批加速比。", '',
    '| 实例/版本 | 评价累计/s | 单次均值/s | 单次最大/s | 占初始化比例 |',
    '|---|---:|---:|---:|---:|']
for r in rows:
    d=detail[r['id']]
    text.append(f"| {name(r['case_id'])}/{r['arm']} | {fmt(d['complete_evaluation_wall_s'])} | {fmt(d['mean_evaluation_wall_s'])} | {fmt(d['max_evaluation_wall_s'])} | {fmt(d['evaluation_share_of_initialization_percent'])}% |")
text += ['', '节省来自减少评价次数及实际路径/计时差异，未降低连续电热精度或重写评价器。完整电热评价仍是主要成本；I1没有解决其随规模增长的成本问题。', '',
    '## 安全、版本与范围', '',
    f"冻结执行提交 `{plan['subject_commit']}`；原502份源码中499份逐字节保持，3份仅改显式版本选择、准入边界和交接状态；I0、完整热评价、合法性、预算与ON搜索核心保持。新 I1 模块独立归档，HEFT/ON/OFF入口均绑定同一个显式函数与180秒常量；三臂连接已用模拟检查，未执行真实配对搜索。82项模拟/回归检查通过；本轮 {a['check_count']} 项只读证据核对通过。", '',
    '输入仍为原四组冻结合法模式与期限/窗口、2场景、50°C初温、80°C温限、5ms合法起点、auto-L和原温度0.001K及能量绝对/相对10⁻⁶精度。科学模型与第三章对应评价核保持，未做参数重标定或改目标；实例能耗不可跨不同窗口直接排名。', '',
    f"方法内完整评价共 {sum(r['evaluation_attempts'] for r in rows)} 次；{sum(r['returned_SAFE_claims'] for r in rows)} 次返回 SAFE，热违规 {sum(r['returned_thermal_violation_receipts'] for r in rows)}，数值未决 {sum(r['returned_unresolved_receipts'] for r in rows)}，中断 {sum(r['interrupted_attempts'] for r in rows)}。五份最终候选各独立进程完整复评一次全部通过；最高最终峰温上界 {max(r['peak_temperature_upper_C'] for r in rows):.6f}°C，温限仍不活跃。批次墙钟 {batch['wall_s']:.3f} 秒，无重试/替换/筛选；所有构造失败和无改善评价均归档。", '',
    '复评沿用同一数值实现，只能验证本模型下的一致完整安全，不能作为独立数值实现或真实硬件验证。每个配置仅一次，不作显著性推断。已有I0历史与失败记录均不覆盖。', '',
    '## 本轮判断', '',
    'I1已在U02–12取得可交接的安全初解，原可行实例的初解质量仅小幅退化，初始化成本有所减少，值得保留为后续比较候选。但更早交接是否让原ON获得更好最终能耗、机制收益是否保持，仍需另行配对实验。本轮到此停止，不自动运行ON-I1/OFF-I1、24 Stage或SA，也不增加搜索机制。', '',
    '证据：[全部指标](metrics.csv)、[逐项分析](analysis.json)、[冻结方案与哈希](plan.json)、[批次记录](batch_return.json)、[模拟检查](precheck.json)。原[提案](../../i1/PROPOSAL_20261112.md)作为批准前历史保留，本报告记录其实现与执行结果。材料类型：限定初始化实验报告；状态：完成。', '']
(OUT/'summary.md').write_text('\n'.join(text),encoding='utf-8')
print({'report':str(OUT/'summary.md'),'gate_triggered':len(gate),'same_pre_delay_paths':all_pre})
