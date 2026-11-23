"""Archive-only matched comparison and figures; never calls the simulator."""
import csv
import json
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_baselines import HERE, ROOT, OLD, ORACLE, CFG, read


def csv_out(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE/name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, separators=(',', ':')) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def save_json(name, value):
    (HERE/name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode())


def save_figure(fig, stem):
    fig.savefig(HERE/(stem+'.png'), dpi=180, facecolor='white')
    fig.savefig(HERE/(stem+'.svg'), metadata={'Date': None})
    plt.close(fig)
    path = HERE/(stem+'.svg')
    path.write_bytes(('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines())+'\n').encode())


def main():
    assert read(HERE/'verification.json')['status'] == 'PASS'
    new = read(HERE/'results.json')
    old = {(r['case_id'], r['setting'], r['strategy']): r for r in read(OLD/'results.json')}
    oracle = {(r['case_id'], r['setting']): r for r in read(ORACLE/'results.json')}
    online = {(r['case_id'], r['setting'], r['strategy']): r for r in new}
    cases = list(dict.fromkeys(r['case_id'] for r in new))
    comparison, summaries, timing, energy = [], [], [], []
    for case in cases:
        baseline = read(OLD/'raw'/case/'ideal_kim.json.gz')
        old_gpu = {(r['request'], r['stage_index']): r for r in baseline['rows'] if r['resource'] == 'GPU'}
        for setting in CFG['settings']:
            sid = setting['id']; k = old[case, sid, 'kim']; o = oracle[case, sid]
            block = {'case_id': case, 'setting': sid, 'latency_us': setting['latency_ns']/1000,
                     'switch_microjoules': setting['energy_j']*1e6}
            common = block.copy()
            normalized = {}
            for strategy, r, folder, source_commit in [
                ('kim', k, OLD, '2a70dda7a04eb66758701add349d0f2848fbccc8'),
                ('reactive', online[case, sid, 'reactive'], HERE, read(HERE/'environment.json')['execution_commit']),
                ('periodic', online[case, sid, 'periodic'], HERE, read(HERE/'environment.json')['execution_commit']),
                ('oracle', o, ORACLE, CFG['base_commit']),
            ]:
                safe = r['SAFE'] and k['SAFE'] and o['SAFE']
                c = dict(common, strategy=strategy, energy_J=r['energy_J'],
                         saving_J=k['energy_J']-r['energy_J'] if safe else None,
                         saving_pct=100*(k['energy_J']-r['energy_J'])/k['energy_J'] if safe else None,
                         oracle_gap_pp=100*(r['energy_J']-o['energy_J'])/k['energy_J'] if safe else None,
                         savings_retained_pct=100*(k['energy_J']-r['energy_J'])/(k['energy_J']-o['energy_J']) if safe else None,
                         SAFE=r['SAFE'], deadline_ok=r['deadline_ok'], thermal_status=r['thermal_status'],
                         completed=r['completed'], required=r['required'], min_slack_ms=r['min_slack_ms'],
                         peak_upper_c=max(r['peak_upper_c']), peak_by_node_c=r['peak_upper_c'],
                         idle_J=sum(r['idle_J']), compute_activity_J=sum(r['activity_J'])-r['switch_energy_j'],
                         leakage_J=sum(r['leakage_J']), switch_J=r['switch_energy_j'],
                         common_J=r['common_J'], transfer_J=r['transfer_J'],
                         switch_count=r['switch_count'], gpu_low_s=r['gpu_low_s'], gpu_high_s=r['gpu_high_s'],
                         gpu_transition_s=r['gpu_transition_s'], gpu_busy_s=r['gpu_busy_s'],
                         planning_s=r['planning_s'], physics_s=r['physics_s'],
                         reused=strategy in ('kim', 'oracle'), source_commit=source_commit,
                         proof=(folder/r['proof']).relative_to(ROOT).as_posix())
                assert abs(c['energy_J']-sum(c[x] for x in ['idle_J', 'compute_activity_J', 'leakage_J', 'switch_J', 'common_J', 'transfer_J'])) < 1e-8
                comparison.append(c); normalized[strategy] = c
                for field in ['energy_J', 'saving_pct', 'oracle_gap_pp', 'savings_retained_pct', 'min_slack_ms', 'peak_upper_c']:
                    block[strategy+'_'+field] = c[field]
                if strategy not in ('reactive', 'periodic'):
                    continue
                p = read(HERE/r['proof']); audit = read(HERE/r['proof'].replace('.json.gz', '_control.json.gz'))
                counts = Counter(e['kind'] for e in audit['controller_log'])
                releases = {e['rid']: e for e in audit['controller_log'] if e['kind'] == 'release'}
                first = {}
                for e in releases.values():
                    if e['required'] == 'H':
                        first[e['scene']] = min(first.get(e['scene'], e['release_ns']), e['release_ns'])
                first_ids = {rid for rid, e in releases.items() if e['required'] == 'H' and e['release_ns'] == first[e['scene']]}
                steady_ids = {rid for rid, e in releases.items() if e['required'] == 'H' and rid not in first_ids}
                shifts = [(e['start_ns']-old_gpu[e['rid'], e['stage']]['start_ns'])/1e6 for e in audit['gpu_starts']]
                t = dict(case_id=case, setting=sid, strategy=strategy,
                         direct_dvfs_wait_ms=sum(s['end_ns']-s['start_ns'] for s in audit['stall_segments'])/1e6,
                         gpu_ready_queue_wait_ms=sum(e['start_ns']-e['ready_ns'] for e in audit['gpu_starts'])/1e6,
                         mean_start_shift_ms=float(np.mean(shifts)), max_start_shift_ms=max(shifts),
                         shifted_gpu_stages=sum(abs(x) > 1e-9 for x in shifts), total_gpu_stages=len(shifts),
                         min_slack_ms=r['min_slack_ms'],
                         first_H_frame_min_slack_ms=min(q['slack_ns'] for q in p['completions'] if q['request_id'] in first_ids)/1e6,
                         steady_H_frames_min_slack_ms=min(q['slack_ns'] for q in p['completions'] if q['request_id'] in steady_ids)/1e6,
                         forecasts=counts['forecast'], prediction_wake=counts['prediction_wake'],
                         prediction_keep_H=counts['prediction_keep_H'], forecast_expired=counts['forecast_expired'])
                timing.append(t)
            r, p, k = (normalized[s] for s in ['reactive', 'periodic', 'kim'])
            block['periodic_gain_over_reactive_pp'] = p['saving_pct']-r['saving_pct']
            block['all_SAFE'] = all(row['SAFE'] for row in normalized.values())
            summaries.append(block)
            delta = dict(case_id=case, setting=sid, periodic_minus_reactive_J=p['energy_J']-r['energy_J'])
            for field in ['idle_J', 'compute_activity_J', 'leakage_J', 'switch_J', 'common_J', 'transfer_J']:
                delta['periodic_minus_reactive_'+field] = p[field]-r[field]
            assert abs(delta['periodic_minus_reactive_J']-sum(delta['periodic_minus_reactive_'+f] for f in
                       ['idle_J', 'compute_activity_J', 'leakage_J', 'switch_J', 'common_J', 'transfer_J'])) < 1e-8
            for strategy in ['reactive', 'periodic', 'oracle']:
                row = normalized[strategy]
                delta[strategy+'_idle_saving_J'] = k['idle_J']-row['idle_J']
                delta[strategy+'_leakage_saving_J'] = k['leakage_J']-row['leakage_J']
                delta[strategy+'_extra_switch_J'] = row['switch_J']-k['switch_J']
                delta[strategy+'_compute_change_J'] = row['compute_activity_J']-k['compute_activity_J']
            energy.append(delta)
    assert len(comparison) == 72 and len(summaries) == len(energy) == 18 and len(timing) == 36
    csv_out('comparison.csv', comparison); csv_out('summary.csv', summaries)
    csv_out('timing_diagnostics.csv', timing); csv_out('energy_attribution.csv', energy)
    decision = {'scope': 'frozen six cases and three assumed overheads; no hardware or general governor claim', 'strategies': {}}
    for strategy in ['reactive', 'periodic']:
        rows = [r for r in comparison if r['strategy'] == strategy]
        d = dict(SAFE=sum(r['SAFE'] for r in rows), runs=len(rows),
                 saving_pct_range=[min(r['saving_pct'] for r in rows), max(r['saving_pct'] for r in rows)],
                 retained_pct_range=[min(r['savings_retained_pct'] for r in rows), max(r['savings_retained_pct'] for r in rows)],
                 oracle_gap_pp_range=[min(r['oracle_gap_pp'] for r in rows), max(r['oracle_gap_pp'] for r in rows)])
        d['passes_predeclared_stop_rule'] = (d['SAFE'] == 18 and d['retained_pct_range'][0] >= CFG['stop_recommendation_gain_retained_pct']
                                           and d['oracle_gap_pp_range'][1] <= CFG['stop_recommendation_oracle_gap_pp'])
        decision['strategies'][strategy] = d
    decision['periodic_gain_over_reactive_pp_range'] = [min(r['periodic_gain_over_reactive_pp'] for r in summaries), max(r['periodic_gain_over_reactive_pp'] for r in summaries)]
    decision['recommendation'] = 'Stop complex prediction development in this problem; retain ordinary idle management as a control baseline, not a new thermal algorithm.'
    save_json('decision.json', decision)

    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'], 'axes.unicode_minus': False,
                         'svg.fonttype': 'none', 'svg.hashsalt': 'gpu-idle-baselines', 'axes.spines.top': False, 'axes.spines.right': False})
    labels = [c.replace('original', '原始').replace('_', ' ').replace('C', '℃') for c in cases]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5)); x = np.arange(len(cases)); width = .25
    medium = [r for r in summaries if r['setting'] == 'medium']
    for off, strategy, label, color in [(-1, 'reactive', '响应式', '#4477AA'), (0, 'periodic', '周期感知', '#228833'), (1, 'oracle', 'Oracle日历', '#999999')]:
        axes[0].bar(x+off*width, [r[strategy+'_saving_pct'] for r in medium], width, label=label, color=color)
    axes[0].set(xticks=x, xticklabels=labels, ylabel='相对匹配Kim的净节能率 (%)', ylim=(0, 3.5), title='100 µs / 10 µJ：普通响应式已取得主要收益')
    axes[0].legend(frameon=False, ncol=3, fontsize=9)
    for strategy, marker, color, label in [('reactive', 'o', '#4477AA', '响应式'), ('periodic', 'x', '#228833', '周期感知')]:
        for off, sid in [(-.16, 'low'), (0, 'medium'), (.16, 'high')]:
            rows = [r for r in summaries if r['setting'] == sid]
            axes[1].scatter(x+off, [r[strategy+'_oracle_gap_pp'] for r in rows], marker=marker, s=45, color=color, alpha=.8, label=label if off == 0 else None)
    axes[1].set(xticks=x, xticklabels=labels, ylabel='Oracle相对在线方法的增量 (百分点)', ylim=(0, .026), title='三档开销：Oracle增量均小于0.022个百分点')
    axes[1].legend(frameon=False, fontsize=9)
    for ax in axes:
        ax.tick_params(axis='x', labelrotation=25, labelsize=9)
    fig.text(.5, .02, '新增36/36 SAFE；切频参数为假设值，非硬件实测。右图各工况从左到右为10/100/500 µs开销。', ha='center', fontsize=9)
    fig.subplots_adjust(left=.065, right=.98, top=.9, bottom=.24, wspace=.27)
    save_figure(fig, 'energy_comparison')
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.5)); x = np.arange(3); width = .32
    for off, strategy, color, label in [(-.5, 'reactive', '#4477AA', '响应式'), (.5, 'periodic', '#228833', '周期感知')]:
        rows = [next(t for t in timing if t['case_id'] == 'original_25C' and t['setting'] == s['id'] and t['strategy'] == strategy) for s in CFG['settings']]
        axes[0].bar(x+off*width, [t['direct_dvfs_wait_ms'] for t in rows], width, color=color, label=label)
        axes[1].plot(x, [t['steady_H_frames_min_slack_ms'] for t in rows], marker='o', color=color, label=label+'：后续周期')
    rows = [next(t for t in timing if t['case_id'] == 'original_25C' and t['setting'] == s['id'] and t['strategy'] == 'periodic') for s in CFG['settings']]
    axes[1].plot(x, [t['min_slack_ms'] for t in rows], '--x', color='#CC6677', label='两策略：全窗最小裕量')
    axes[0].set(ylabel='累计直接切频等待 (ms)', title='原始25℃：预测减少恢复等待', ylim=(0, 70))
    axes[1].set(ylabel='最小期限裕量 (ms)', title='新场景首周期仍限制全窗裕量', ylim=(0, .85))
    for ax in axes:
        ax.set_xticks(x, ['10 µs\n1 µJ', '100 µs\n10 µJ', '500 µs\n100 µJ'])
        ax.set_xlim(-.5, 2.5); ax.tick_params(axis='x', labelsize=9); ax.legend(frameon=False, fontsize=8)
    fig.text(.5, .02, '“后续周期”排除每个H计算场景的首帧；本批响应式本身全部按期，无避免超期的实验证据。', ha='center', fontsize=9)
    fig.subplots_adjust(left=.08, right=.97, top=.9, bottom=.22, wspace=.3)
    save_figure(fig, 'timing_comparison')
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
