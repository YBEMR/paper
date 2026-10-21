"""Build the terminal research report from stored evidence, with no method calls."""
from collections import Counter
from datetime import datetime
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = next(p for p in ROOT.parents if (p / 'AGENTS.md').is_file())


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    facts = read(ROOT / 'analysis01/facts.json')
    review = read(ROOT / 'record_review01.json')
    assert review['passed'] and facts['observed_rows'] == 40
    assert facts['process_terminal']['state'] == 'COMPLETED'
    rows, cohorts = facts['rows'], facts['cohorts']
    old_claim = read(ROOT.parent / 'p0_execution01/launcher_claim.json')
    calendar_s = (datetime.fromisoformat(facts['process_terminal']['ended_utc'])
                  - datetime.fromisoformat(old_claim['started_utc'])).total_seconds()
    linked = [r for r in rows if r['method'] == 'anchor_linked4']
    feedback = sum(r['feedback_saved_rows'] for r in rows)
    violations = sum(r['violation_saved_rows'] for r in rows)
    assert all(r['comparison_usable'] for r in rows)
    details = {
        'protocol': 'K156-terminal-report-derived-v1',
        'calendar_from_original_launch_s': calendar_s,
        'original_calendar_limit_s': old_claim['wall_s'],
        'root_time_sum_s': facts['method_root_sum_s'],
        'continuation_supervisor_wall_s': facts['process_terminal']['process_wall_s'],
        'method_status_counts': dict(Counter(r['method_state'] for r in rows)),
        'linked_strictly_lower_than_HEFT_count': sum(c['linked_strictly_lower_than_HEFT'] for c in cohorts),
        'linked_second_phase_strictly_improved_count': sum(
            len(r['phases']) == 2 and r['phases'][1]['new_strict_improvement'] for r in linked),
        'thermal_feedback_rows': feedback,
        'thermal_violation_rows': violations,
        'independent_optimal_count': sum(bool(r['independently_proven_optimal']) for r in rows),
        'independent_infeasible_count': sum(bool(r['independently_proven_infeasible']) for r in rows),
        'research_calls_in_this_analysis': 0,
        'new_thermal_evaluations_in_this_analysis': 0,
        'facts_sha256': hashlib.sha256((ROOT / 'analysis01/facts.json').read_bytes()).hexdigest(),
        'record_review_sha256': hashlib.sha256((ROOT / 'record_review01.json').read_bytes()).hexdigest(),
    }
    with (ROOT / 'analysis01/report_metrics.json').open('x', encoding='utf-8') as stream:
        json.dump(details, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    lines = [
        '# K.156：账本修复、37次续接及P0完整结果', '',
        '2026-10-21。原3次＋续接37次＝40次全部完成，40份最终安全方案均完成原定一次完整事后复核。'
        '前三次没有重跑，旧账本、pending、claims、源码与结果保持；未延长单次预算或原日历上限。', '',
        '联动版在R1、R2、R4、R5取得比HEFT更低的安全能耗，R3高8.662912%；'
        'R4差异只有0.011967%。HEFT五题均更快。不能据此写成普遍优于HEFT。', '',
        '## 1．修复与执行核查', '',
        '- 修复限定在执行层：Windows 5／32原子替换最多等待1秒；监督只读compact状态；'
        '不可变方法回执先落盘；worker与supervisor分别写终态。没有修改候选生成、物理模型或安全判定。',
        '- 必要预检167/167通过；首轮5项夹具接口失败及修正记录保留。'
        '终态存档核查453/453通过，属于本会话存档一致性核查，不冒称外部独立批准。',
        '- 37个新槽一次消费，前三槽未重复；203项冻结源及旧工件哈希全部保持。'
        '37次续接无技术故障、无补跑，worker／supervisor均COMPLETED、退出0。',
        '- 每次新建输入、候选、初始化与缓存，MATLAB启动、构模、求解和内部连续评价全部计费。'
        '事后复核只验证已接纳方案，不搜索、不替换原U、不补预算外候选。', '',
        '## 2．最终安全能耗', '',
        '能量单位J；列示完整场景加权系统能耗上端。负改善表示联动更差。'
        '严格高低核对使用原精确区间，表中小数仅作展示。', '',
        '| 输入 | 整体MILP | 联动 | HEFT | SA五种子中位数 | 联动相对HEFT降低 |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for c in cohorts:
        group = {r['method']: r for r in rows if r['problem_id'] == c['problem_id']}
        lines.append(f"| {c['problem_id']} | {group['whole_milp']['safe_U_J']:.9f} | "
                     f"{group['anchor_linked4']['safe_U_J']:.9f} | {group['heft']['safe_U_J']:.9f} | "
                     f"{c['SA_median_J']:.9f} | {100*c['linked_vs_HEFT_reduction_fraction']:.6f}% |")
    lines += ['',
        '每题8/8次取得可用安全输出。联动五题均低于整体MILP；与SA五次分布相比，'
        'R1／R2／R4／R5均低于对应五个已观察结果，R3高于对应五个结果。'
        '这只是本批五输入的描述，SA五次最小值不作为单次等预算竞争者。', '',
        '## 3．阶段质量与耗时', '',
        '| 输入 | 联动阶段1 U/J | 阶段2 U/J | 联动总时钟/s | HEFT总时钟/s | 联动首次严格改善/s |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for r in linked:
        heft = next(v for v in rows if v['problem_id'] == r['problem_id'] and v['method'] == 'heft')
        lines.append(f"| {r['problem_id']} | {r['phase1_U_J']:.9f} | {r['phase2_U_J']:.9f} | "
                     f"{r['method_root_s']:.3f} | {heft['method_root_s']:.3f} | {r['first_strict_improvement_s']:.3f} |")
    lines += ['',
        '两阶段在5/5题均有严格安全改善记录；第二阶段改善原阶段1的U。'
        '这证明本版在同次预算内能进一步降能耗，不构成“没有第二阶段的等预算算法”消融，'
        '也不证明已达到固定配置、局部或全域真实能耗最优。', '',
        '| 输入 | 整体首个SAFE/s | 整体MATLAB启动/s | 联动首个SAFE/s | 联动MATLAB启动/s |',
        '|---|---:|---:|---:|---:|',
    ]
    for r in linked:
        whole = next(v for v in rows if v['problem_id'] == r['problem_id'] and v['method'] == 'whole_milp')
        lines.append(f"| {r['problem_id']} | {whole['first_SAFE_s']:.3f} | {whole['matlab_startup_s']:.3f} | "
                     f"{r['first_SAFE_s']:.3f} | {r['matlab_startup_s']:.3f} |")
    lines += ['',
        f"方法根时钟合计{facts['method_root_sum_s']:.3f}秒；预留仍为3×300＋37×300＝12000秒。"
        f"续接监督墙钟{facts['process_terminal']['process_wall_s']:.3f}秒；"
        f"从原K155启动到最终终态的日历时间{calendar_s:.3f}秒，小于19200秒，包含故障诊断和准备暂停。"
        '三者含义不同，不能相加充当求解时间。实际停止／返回延迟已保留；安全证据接纳仍严格截止300秒。', '',
        '状态为10次正常完成、29次正常时限且末请求未决、1次正常时限。'
        '末请求未决未抹掉已有U；原前三次之一另有包装IO归档故障，方法状态与执行层故障分别记录。'
        'MATLAB启动差异较大，尤其整体R1／R2约54／55秒，已计费且未剔除；本批不足以确定时差原因或稳定性。', '',
        '## 4．热证据、界与证明范围', '',
        f'本批保存热违规记录{violations}、连续热反馈记录{feedback}。40份最终方案均覆盖完整场景、'
        '400 ms窗口及尾段并通过一次事后复核；这支持本批安全输出，不支持反馈产生了求解收益。'
        '不新增温度扫描或重跑以制造正例。热约束改变选择的既有K127证据仍按原条件单列。', '',
        'R1—R5独立L0依次约0.738285994、0.736830913、0.739741076、0.742190780、0.734381209 J。'
        'L0均未与最终U闭合，0项独立全域最优、0项独立全域无解，0项L0高于安全U异常。'
        '认证差距见逐调用CSV；solver内部界及局部子问题状态保留于原始结果，不提升为全域证书。', '',
        '本批采用相同科学输入与方法规则，但前三次和后37次分段执行，不能描述成无中断批次；'
        '不并入K152先导或旧hold实验。每个确定性方法每输入仅一次，不能声称统计稳定性、普遍加速或实机节能。', '',
        '## 5．文件与下一步', '',
        '- [冻结续接协议](protocol.md)、[声明](declaration.json)、[账本](ledger.json)、'
        '[worker终态](worker_terminal.json)、[process终态](process_terminal.json)。',
        '- [453项存档核查](record_review01.json)、[40次结果CSV](analysis01/results40.csv)、'
        '[原始汇总事实](analysis01/facts.json)、[衍生指标](analysis01/report_metrics.json)。',
        '- calls／claims保存逐方法原始回执、最终完整安排、一次post、计时和工件哈希；'
        '原前三次位于p0_execution01，未复制改写。MAT遵守gitignore，本地保留及hash记录，不强制上传。', '',
        '本阶段结束，不自动启动后续批次。建议先审阅本P0基准结果及R3反向表现，'
        '再确认下一组既定实验的调用和预算；不把本轮结果反向用于改参数、换种子或增加邻域。', '',
        '![安全能量随方法时间变化](analysis01/safe_curves.png)', '',
        '![最终能耗与方法时间](analysis01/energy_and_method_time.png)', '',
        '![联动两阶段安全能量](analysis01/linked_phase_energy.png)', '',
    ]
    with (ROOT / 'summary.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    print({'report': str(ROOT / 'summary.md'), 'calendar_s': calendar_s,
           'linked_lower_than_HEFT': details['linked_strictly_lower_than_HEFT_count'],
           'second_phase_improved': details['linked_second_phase_strictly_improved_count']})


if __name__ == '__main__':
    main()
