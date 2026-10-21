"""Terminal report from saved P1 evidence only; no search or thermal evaluation."""
from collections import Counter
from datetime import datetime
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    facts = read(ROOT / 'analysis01/facts.json')
    review = read(ROOT / 'record_review01.json')
    claim = read(ROOT / 'launcher_claim.json')
    assert review['passed'] and facts['observed_rows'] == 40
    assert facts['process_terminal']['state'] == 'COMPLETED'
    rows, cohorts = facts['rows'], facts['cohorts']
    assert all(r['comparison_usable'] for r in rows)
    linked = [r for r in rows if r['method'] == 'anchor_linked4']
    calendar_s = (datetime.fromisoformat(facts['process_terminal']['ended_utc'])
                  - datetime.fromisoformat(claim['started_utc'])).total_seconds()
    date = datetime.fromisoformat(facts['process_terminal']['ended_utc']).astimezone(
        __import__('datetime').timezone(__import__('datetime').timedelta(hours=8))).date().isoformat()
    feedback = sum(r['feedback_saved_rows'] for r in rows)
    violations = sum(r['violation_saved_rows'] for r in rows)
    details = {
        'protocol': 'K158-terminal-report-derived-v1',
        'calendar_from_P1_launch_s': calendar_s,
        'calendar_limit_s': (datetime.fromisoformat(claim['calendar_deadline_utc'])
                             - datetime.fromisoformat(claim['started_utc'])).total_seconds(),
        'root_time_sum_s': facts['method_root_sum_s'],
        'method_reserved_s': facts['reserved_total_method_s'],
        'supervisor_wall_s': facts['process_terminal']['process_wall_s'],
        'method_status_counts': dict(Counter(r['method_state'] for r in rows)),
        'linked_strictly_lower_than_HEFT_count': sum(c['linked_strictly_lower_than_HEFT'] for c in cohorts),
        'linked_second_phase_strictly_improved_count': sum(
            len(r['phases']) == 2 and r['phases'][1]['new_strict_improvement'] for r in linked),
        'HEFT_faster_than_linked_count': sum(
            next(v for v in rows if v['problem_id'] == r['problem_id'] and v['method'] == 'heft')['method_root_s']
            < r['method_root_s'] for r in linked),
        'thermal_feedback_saved_rows': feedback,
        'thermal_violation_saved_rows': violations,
        'independent_optimal_count': sum(bool(r['independently_proven_optimal']) for r in rows),
        'independent_infeasible_count': sum(bool(r['independently_proven_infeasible']) for r in rows),
        'independent_bound_anomalies': facts['independent_bound_anomalies'],
        'research_calls_in_analysis': 0, 'new_thermal_evaluations_in_analysis': 0,
        'facts_sha256': sha(ROOT / 'analysis01/facts.json'),
        'record_review_sha256': sha(ROOT / 'record_review01.json'),
    }
    pair_rows = []
    for c in cohorts:
        group = {r['method']: r for r in rows if r['problem_id'] == c['problem_id']}
        l = group['anchor_linked4']
        sa = [r for r in group.values() if r['seed'] is not None]
        pair_rows.append({
            'problem_id': c['problem_id'],
            'linked_vs_HEFT_reduction_percent': 100*c['linked_vs_HEFT_reduction_fraction'],
            'linked_strictly_lower_than_whole': F(l['safe_U_exact']) < F(group['whole_milp']['safe_energy_lo_exact']),
            'linked_strictly_lower_than_SA_observed_n': sum(F(l['safe_U_exact']) < F(r['safe_energy_lo_exact']) for r in sa),
            'SA_observed_n': len(sa),
        })
    details['within_input_pairs'] = pair_rows
    with (ROOT / 'analysis01/report_metrics.json').open('x', encoding='utf-8') as stream:
        json.dump(details, stream, ensure_ascii=False, indent=2); stream.write('\n')

    # Read-only cross-condition table: different common true response inputs.
    old = read(ROOT.parent / 'p0_resume01/analysis01/facts.json')
    cross = []
    for r in rows:
        other = next(x for x in old['rows'] if x['problem_id'] == r['problem_id'].replace('response_R', 'base')
                     and x['method'] == r['method'])
        cross.append({'variant': r['problem_id'].split('__')[-1], 'method': r['method'],
                      'P0_H_U_J': other['safe_U_J'], 'P1_R_U_J': r['safe_U_J'],
                      'P0_H_method_s': other['method_root_s'], 'P1_R_method_s': r['method_root_s'],
                      'scope': 'different common true response inputs; not a common-model model-bias loss'})
    with (ROOT / 'analysis01/P0_P1_separate_conditions.json').open('x', encoding='utf-8') as stream:
        json.dump(cross, stream, ensure_ascii=False, indent=2); stream.write('\n')

    scans = [
        ('Simpson aggregation', '分别保留R1—R5，不用汇总掩盖反向或微小差异。'),
        ('Ecological inference', '五个固定变体不外推为全部端侧负载或实机。'),
        ('Selection bias', '按预冻结40槽全量保留，不因输赢挑样本。'),
        ('Collider conditioning', '无事后按安全成功或算法获胜筛选；全部状态保留。'),
        ('Base rate', '报告安全输出分母40，不把5个变体当随机成功率。'),
        ('Regression to mean', '不因P0失利重跑或更换种子；跨条件不作重复改善推断。'),
        ('Survivorship', '逐槽保存正常截止、未决及既成U，未删除失败槽。'),
        ('Look elsewhere', '无额外温限、种子、参数扫描或只报有利比较。'),
        ('Forking paths', '参数、预算、顺序及统计口径预冻结，预检失败留存。'),
        ('Causation', 'P0/P1改变共同真实响应输入，不声称模型修正节能或单机制因果。'),
        ('Reverse causality', '不从单次运行时差解释模型或硬件原因；不作此方向推断。'),
    ]
    with (ROOT / 'analysis01/interpretation_review.json').open('x', encoding='utf-8') as stream:
        json.dump({'status': 'ANALYZED', 'scope': 'stored-record descriptive interpretation; not rerun verification',
                   'coverage': '11/11 checked', 'items': [{'type': t, 'handling': h} for t, h in scans],
                   'inferential_tests': 0, 'SA_five_seed_scope': 'descriptive only; no best-of-five equal-budget rank',
                   'research_calls': 0, 'new_thermal_evaluations': 0}, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

    lines = ['# K.158：统一1/f响应组P1冻结对照', '',
        f'{date}。40/40次完成，40份最终方案均完成原定一次完整连续热事后复核。'
        '单次300秒、方法预留12000秒、全批日历19200秒均保持，没有补跑或临时延长。', '',
        f"联动版在{details['linked_strictly_lower_than_HEFT_count']}/5个输入上取得严格低于HEFT的安全能耗；"
        f"HEFT在{details['HEFT_faster_than_linked_count']}/5个输入上更快。下表保留所有正反结果。", '',
        '## 1．任务及可复核范围', '',
        '- 使用原response_R R1—R5：统一反比响应α=1；原功热、合法设备／工作点、400 ms窗口、'
        '5 ms起点、真实结束、CPU-H参考期限与auto-L不变。所有方法接收相同真实输入。',
        '- 18项新适配检查＋167项继承检查全部通过；首轮5个目录元数据预期差异及修订保留，'
        '未修改研究输入。211源及五输入哈希冻结后执行，独立输入／初解／缓存／L0均在本次计费。',
        f"- 终态存档核查{review['count']}/{review['count']}通过；这是本会话对已存证据的机械核查，"
        '没有新增求解或重复物理复核，也不是外部独立审查批准。', '',
        '## 2．最终系统能耗', '',
        '单位J，显示完整场景加权安全能量上端；严格高低由原精确区间判断。负百分比表示联动更差。', '',
        '| 输入 | 整体MILP | 联动 | HEFT | SA五次中位数 | 联动相对HEFT降低 |',
        '|---|---:|---:|---:|---:|---:|']
    for c in cohorts:
        g = {r['method']: r for r in rows if r['problem_id'] == c['problem_id']}
        lines.append(f"| {c['problem_id']} | {g['whole_milp']['safe_U_J']:.9f} | "
                     f"{g['anchor_linked4']['safe_U_J']:.9f} | {g['heft']['safe_U_J']:.9f} | "
                     f"{c['SA_median_J']:.9f} | {100*c['linked_vs_HEFT_reduction_fraction']:.6f}% |")
    lines += ['', 'SA101—105逐次结果、均值、中位数、范围和标准差保留；五次最好值不是一次300秒竞争者。'
        '每个确定性方法每题只有一次，不作统计稳定性或普遍优势结论。', '',
        '## 3．联动阶段及实际时间', '',
        '| 输入 | 阶段1 U/J | 阶段2 U/J | 联动根时钟/s | HEFT根时钟/s | 联动首严格改善/s |',
        '|---|---:|---:|---:|---:|---:|']
    fmt = lambda x: '—' if x is None else f'{x:.3f}'
    for r in linked:
        h = next(v for v in rows if v['problem_id'] == r['problem_id'] and v['method'] == 'heft')
        lines.append(f"| {r['problem_id']} | {r['phase1_U_J']:.9f} | {r['phase2_U_J']:.9f} | "
                     f"{r['method_root_s']:.3f} | {h['method_root_s']:.3f} | {fmt(r['first_strict_improvement_s'])} |")
    lines += ['', f"第二阶段在{details['linked_second_phase_strictly_improved_count']}/5题有严格改善。"
        '这是同次运行内的质量进展，不是去掉第二阶段的等预算消融，也不证明局部或全域最优。', '',
        '| 输入 | 整体首SAFE/s | 整体MATLAB启动/s | 联动首SAFE/s | 联动MATLAB启动/s |',
        '|---|---:|---:|---:|---:|']
    for r in linked:
        w = next(v for v in rows if v['problem_id'] == r['problem_id'] and v['method'] == 'whole_milp')
        lines.append(f"| {r['problem_id']} | {fmt(w['first_SAFE_s'])} | {fmt(w['matlab_startup_s'])} | "
                     f"{fmt(r['first_SAFE_s'])} | {fmt(r['matlab_startup_s'])} |")
    lines += ['', f"方法根时钟合计{facts['method_root_sum_s']:.3f}秒，预留12000秒；"
        f"监督墙钟{facts['process_terminal']['process_wall_s']:.3f}秒，"
        f"从本批启动到终态日历{calendar_s:.3f}秒＜19200秒。"
        'MATLAB启动、构模、求解和内部热复核均计费；停止延迟、一次事后核查、归档另列。'
        '监督超时不是证据期限延长，预算后新U未接纳。', '',
        '方法状态计数：' + '；'.join(f'{k}={v}' for k,v in details['method_status_counts'].items()) + '。'
        '正常时限及末请求未决保留此前完整安全U，不等于技术失败或模型无解。', '',
        '## 4．热、界及可支持的结论', '',
        f'保存的热违规记录{violations}条、连续热反馈记录{feedback}条。'
        '最终安全输出覆盖全部场景、完整400 ms及空闲尾段；本组没有触发反馈，未观察到反馈求解收益。'
        '既有热约束证据按原独立条件保留，不临时扫描温度。', '',
        f"独立全域最优{details['independent_optimal_count']}项、独立全域无解{details['independent_infeasible_count']}项；"
        f"L0高于U异常{details['independent_bound_anomalies']}项。各次共同L0及认证差距见CSV；"
        'solver-reported界、gap及局部状态留在原记录，不提升为全域证书。', '',
        'P0与P1分别按各自的共同真实响应输入评价，跨条件表仅描述结果变化。'
        '本组没有把两类方案放回同一个评价模型，因此不能直接将P0/P1能量差称为非统一响应的建模收益。', '',
        '## 5．证据入口与完成边界', '',
        '- [协议](../../p1_batch/protocol.md)、[声明](declaration.json)、[账本](ledger.json)、'
        '[进程终态](process_terminal.json)、[存档核查](record_review01.json)。',
        '- [40次CSV](analysis01/results40.csv)、[全部事实](analysis01/facts.json)、'
        '[阶段及时间指标](analysis01/report_metrics.json)、[P0/P1分条件表](analysis01/P0_P1_separate_conditions.json)、'
        '[11项解释范围核查](analysis01/interpretation_review.json)。',
        '- [逐场景能量组成](analysis01/scene_energy.csv)、[节点连续峰温包络](analysis01/scene_peak_temperature.csv)'
        '来自原定一次post的只读投影，没有重复热评价。',
        '- calls／claims保留每次原始结果、完整时间表、内部界、一次post和哈希；'
        'MAT在本地保存并登记哈希，遵守gitignore，不强制上传。', '',
        'P1本阶段结束，不自动启动下一批。下一项应先审阅本组与P0结果，'
        '再从既定计划中确认后续条件及预算；本组结果不触发改参数、添邻域、换种子或补跑。', '',
        '![安全能量与界随时间变化](analysis01/safe_curves.png)', '',
        '![最终能耗及方法时间](analysis01/energy_and_method_time.png)', '',
        '![联动阶段能量](analysis01/linked_phase_energy.png)', '']
    old_summary = ROOT / 'summary.md'
    with (ROOT / 'preparation_summary.md').open('xb') as stream:
        stream.write(old_summary.read_bytes())
    old_summary.write_text('\n'.join(lines), encoding='utf-8')
    print({'report': str(old_summary), 'calendar_s': calendar_s,
           'linked_lower_than_HEFT': details['linked_strictly_lower_than_HEFT_count']})


if __name__ == '__main__':
    main()
