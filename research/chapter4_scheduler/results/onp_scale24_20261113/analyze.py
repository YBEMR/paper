"""Read-only analysis of the completed 24-stage extension and saved12-stage outcomes."""
import csv
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'RESEARCH_BRIEF.md').is_file())
EX = OUT / 'execution'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csvfile(name, values):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in values for k in r)))
        w.writeheader()
        w.writerows(values)


def main():
    plan, batch, summary = (read(EX / n) for n in ('plan.json', 'batch_return.json', 'summary.json'))
    assert batch['retry_count'] == 0 and len(summary['rows']) == len(plan['slots']) == 8
    for n, h in plan['source_sha256'].items():
        assert sha(REPO / n) == sha(EX / 'source_snapshot' / n) == h, n
    for n, h in plan['input_file_sha256'].items():
        assert sha(EX / n) == h, n
    old = OUT.parent / 'onp_unseen_20261113'
    prior = read(old / 'files_sha256.json')
    for n, h in prior.items():
        assert sha(REPO / n) == h, n
    rows, details, curves, unresolved = [], {}, [], []
    packets, initialization_details, maximum_evaluated_peak = {}, {}, F(0)
    for row in summary['rows']:
        sid = row['id']
        folder = EX / 'calls' / sid
        get = lambda n: read(folder / n) if (folder / n).exists() else {}
        raw, ret, post = get('method/result.json'), get('method_return.json'), get('post_return.json')
        if not raw:
            rows.append(row)
            details[sid] = {'missing_raw_result': True, 'failure': ret}
            continue
        assert sha(folder / 'method/result.json') == ret['raw_result_sha256']
        assert raw['initialization_version'] == 'I1'
        packets[(row['root_id'], row['arm'])] = [
            {k: v for k, v in p.items() if k != 'proposed_at_s'} for p in raw.get('graph_proposals', [])]
        meta = raw.get('initialization') or {}
        first_energy = meta.get('first_SAFE_energy_J')
        initialization_details[sid] = {
            'construction_attempts': [{k: v for k, v in x.items() if not isinstance(v, (dict, list))}
                                      for x in meta.get('construction_attempts', [])],
            'first_safe_energy_J': float(F(first_energy[1])) if first_energy else None,
            'quality_saving_percent': (float(F(first_energy[1])) - row['initial_energy_J']) / float(F(first_energy[1])) * 100
            if first_energy and row['initial_energy_J'] is not None else None}
        if row['safe']:
            assert raw['evaluation']['completed_at_elapsed_s'] < 300
        physical = [e for e in raw['evaluations'] if not e.get('cache_hit', False)]
        returned = [j for j in ret['evaluation_attempts_journal'] if j['state'] == 'RETURNED']
        assert len(physical) == len(returned)
        init, search = [], []
        for e, j in zip(physical, returned):
            assert e['candidate_sha256'] == j['candidate_sha256']
            for scene in e['receipt'].get('scenes', {}).values():
                for v in scene.get('peaks_degC', {}).values():
                    maximum_evaluated_peak = max(maximum_evaluated_peak, F(v[1]))
            if e['phase'] == 'initialization':
                assert e['evaluation_admitted_at_s'] < 180
            if e.get('incumbent_replaced'):
                assert e['receipt']['completed_at_elapsed_s'] < 300
            item = {'sha256': e['candidate_sha256'], 'state': e['receipt']['state'],
                    'energy': e['receipt'].get('weighted_energy_J'),
                    'evaluation_s': j['returned_at_s'] - j['started_at_s']}
            (init if e['phase'] == 'initialization' else search).append(item)
            if e['receipt']['state'] != 'SAFE':
                assert not e.get('incumbent_replaced')
                unresolved.append({'slot': sid, 'candidate_sha256': e['candidate_sha256'],
                                   'state': e['receipt']['state'], 'reason': e['receipt'].get('reason')})
        before = raw.get('initial_safe_snapshot')
        byhash = {e['candidate_sha256']: e for e in raw['evaluations']}
        accepted_steps = []
        for ordinal, p in enumerate(raw.get('graph_proposals', []), 1):
            if not p['strict_accepted']:
                continue
            e = byhash[p['candidate_sha256']]
            assert before and F(e['receipt']['weighted_energy_J'][1]) < F(before['receipt']['weighted_energy_J'][0])
            accepted_steps.append({'proposal_ordinal': ordinal, 'sha256': p['candidate_sha256'],
                                   'extra_edges': p.get('additional_reversed_edges', []),
                                   'before_energy_J': float(F(before['receipt']['weighted_energy_J'][1])),
                                   'after_energy_J': float(F(e['receipt']['weighted_energy_J'][1])),
                                   'proposed_at_s': p['proposed_at_s'], 'returned_at_s': e['returned_at_s']})
            before = e
        if before and row['safe']:
            assert before['candidate'] == raw['safe_candidate']
        handoff = row.get('initialization_completed_at_s')
        search_eval = sum(p['exclusive_s'] for p in raw['timing']['phase_records']
                          if p['phase'] == 'complete_continuous_evaluation' and handoff is not None and p['start_s'] >= handoff)
        other = row.get('search_s', 0) - search_eval - row.get('graph_construction_s', 0) - row['prefilter_total_s']
        assert other >= -1e-6
        rr = {**row, 'first_SAFE_at_s': raw.get('first_safe_at_s'),
              'search_evaluation_s': search_eval, 'search_other_s': max(0, other),
              'pre_search_s': handoff if handoff is not None else row.get('method_elapsed_s'),
              'actual_total_construction_calls': row['actual_base_calls'] + row['actual_extra_calls'],
              'structure_plus_filter_s': row.get('graph_construction_s', 0) + row['prefilter_total_s'],
              'saving_vs_own_initial_percent': (row['initial_energy_J'] - row['energy_J']) / row['initial_energy_J'] * 100
              if row['initial_energy_J'] is not None and row['energy_J'] is not None else None,
              'full_SAFE_evaluation_mean_s': sum(e['evaluation_s'] for e in init + search if e['state'] == 'SAFE') /
              max(1, sum(e['state'] == 'SAFE' for e in init + search))}
        rows.append(rr)
        snapshot = raw.get('initial_safe_snapshot') or {}
        details[sid] = {'initial_sha256': snapshot.get('candidate_sha256'),
                        'initial_energy': snapshot.get('receipt', {}).get('weighted_energy_J'),
                        'initial_evaluations': init, 'search_evaluations': search,
                        'proposal_sequence': [p['candidate_sha256'] for p in raw.get('graph_proposals', [])],
                        'accepted_sequence': [p['candidate_sha256'] for p in raw.get('graph_proposals', []) if p['strict_accepted']],
                        'final_sha256': digest(raw['safe_candidate']) if row['safe'] else None,
                        'accepted_steps': accepted_steps,
                        'prefilter_counts': get('method/prefilter.json').get('counts', {}),
                        'initialization': raw.get('initialization'),
                        'attempt_failure_reasons': dict(Counter(d.get('reason') for d in raw.get('reconstruction_attempts', []) if d.get('reason'))),
                        'post_same_evaluator': post.get('same_numerical_evaluator')}
        for e in raw.get('events', []):
            curves.append({'slot': sid, 'case_id': row['case_id'], 'arm': row['arm'],
                           'time_s': e['at_s'], 'phase': e['phase'], 'energy_J': float(F(e['energy']['upper'])),
                           'candidate_sha256': e['candidate_sha256']})
    comparisons = []
    for case in ('U05__n24', 'U06__n24'):
        arms = {r['arm']: r for r in rows if r['case_id'] == case}
        for a, b in (('ON_P', 'ON'), ('ON_P', 'OFF_P'), ('ON_P', 'HEFT'), ('OFF_P', 'HEFT'), ('ON', 'HEFT')):
            x, y = arms[a], arms[b]
            dx, dy = details[x['id']], details[y['id']]
            ix, iy = dx.get('initial_evaluations', []), dy.get('initial_evaluations', [])
            n = next((i for i, (u, v) in enumerate(zip(ix, iy)) if u['sha256'] != v['sha256']), min(len(ix), len(iy)))
            assert all(u['energy'] == v['energy'] for u, v in zip(ix[:n], iy[:n]))
            same = bool(dx.get('initial_sha256') and dx.get('initial_sha256') == dy.get('initial_sha256') and dx['initial_energy'] == dy['initial_energy'])
            sx, sy = dx.get('proposal_sequence', []), dy.get('proposal_sequence', [])
            k = min(len(sx), len(sy))
            cache_diff = {e['sha256'] for e in ix} ^ {e['sha256'] for e in iy}
            valid = all(r['safe'] and r['post_passed'] and not r['error'] for r in (x, y))
            comparisons.append({'case_id': case, 'arm': a, 'reference': b,
                                'same_initial': same, 'same_initial_sequence': bool(ix and iy and n == len(ix) == len(iy)),
                                'initial_common_prefix': n,
                                'common_initial_arm_eval_s': sum(e['evaluation_s'] for e in ix[:n]),
                                'common_initial_reference_eval_s': sum(e['evaluation_s'] for e in iy[:n]),
                                'common_search_prefix_length': k, 'common_search_prefix_equal': sx[:k] == sy[:k],
                                'initial_cache_difference_hits_observed_search': len(cache_diff & (set(sx) | set(sy))),
                                'both_SAFE_posts': valid,
                                'same_final_candidate': dx.get('final_sha256') == dy.get('final_sha256') if valid else None,
                                'energy_saving_percent': (y['energy_J'] - x['energy_J']) / y['energy_J'] * 100 if valid else None,
                                'strict_interval_improvement': F(x['energy_upper_J']) < F(y['energy_lower_J']) if valid else None,
                                'same_final_energy_interval': (F(x['energy_lower_J']), F(x['energy_upper_J'])) ==
                                (F(y['energy_lower_J']), F(y['energy_upper_J'])) if valid else None})
    data = {'source_commit': plan['subject_commit'], 'rows': rows, 'comparisons': comparisons,
            'details': details, 'non_SAFE_evaluations': unresolved,
            'frozen_source_files_unchanged': len(plan['source_sha256']), 'prior_12_archive_files_unchanged': len(prior),
            'all_initial_admissions_before_180': True, 'all_accepted_receipts_before_300': True,
            'strict_search_acceptance_checked': True, 'new_scientific_calls_in_analysis': 0,
            'scope': 'Scale extension of the two saved observed roots; work/deadlines/window grow under fixed generation rules; same-evaluator posts; no statistical stability claim.'}
    save('analysis.json', data)
    save('supplementary_checks.json', {
        'full_ordered_proposal_payloads_equal_excluding_proposed_time': {
            root: packets.get((root, 'ON')) == packets.get((root, 'ON_P'))
            for root in ('U05', 'U06') if (root, 'ON') in packets and (root, 'ON_P') in packets},
        'initialization_details': initialization_details,
        'max_peak_across_all_evaluations_C': float(maximum_evaluated_peak),
        'new_scientific_calls': 0})
    csvfile('all_metrics.csv', rows)
    csvfile('comparisons.csv', comparisons)
    csvfile('energy_time.csv', curves)
    plot(rows, curves)
    compare_scales(rows, old)
    print(json.dumps({'SAFE_posts': sum(r['safe'] and r['post_passed'] for r in rows),
                      'rows': [{k: r.get(k) for k in ('case_id', 'arm', 'initial_energy_J', 'energy_J', 'method_elapsed_s', 'extra_edge_accepts')} for r in rows],
                      'comparisons': comparisons}, ensure_ascii=False, indent=2))


def plot(rows, curves):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'font.size': 10})
    arms = ['HEFT', 'ON', 'ON_P', 'OFF_P']
    colors = {'HEFT': '#777777', 'ON': '#c26852', 'ON_P': '#851c36', 'OFF_P': '#1b6a97'}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout='constrained')
    for ax, case in zip(axes, ('U05__n24', 'U06__n24')):
        for arm in arms:
            r = next(r for r in rows if r['case_id'] == case and r['arm'] == arm)
            ps = [p for p in curves if p['case_id'] == case and p['arm'] == arm]
            if ps:
                ax.step([p['time_s'] for p in ps] + [r['method_elapsed_s']], [p['energy_J'] for p in ps] + [ps[-1]['energy_J']],
                        where='post', color=colors[arm], label=arm.replace('_', '-'), linestyle='--' if arm.endswith('_P') else '-')
        ax.set_title(case.replace('__n', ' / ') + ' Stage')
        ax.set_xlabel('Method elapsed time (s)')
        ax.set_ylabel('Accepted SAFE energy upper bound (J)')
        ax.grid(alpha=.2)
        ax.legend()
    fig.savefig(OUT / 'energy_time.png', dpi=180)
    fig.savefig(OUT / 'energy_time.svg')
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    layers = [('pre_search_s', 'I1 + setup', '#c8c8c8'), ('search_evaluation_s', 'Search evaluation', '#82b2c9'),
              ('graph_construction_s', 'Construction', '#dc9d67'), ('prefilter_total_s', 'Prefilter', '#876ca6'), ('search_other_s', 'Other', '#6c777f')]
    for ax, case in zip(axes, ('U05__n24', 'U06__n24')):
        rs = [next(r for r in rows if r['case_id'] == case and r['arm'] == arm) for arm in arms]
        left = [0.] * len(arms)
        for key, label, color in layers:
            values = [r.get(key) or 0 for r in rs]
            ax.barh(range(len(arms)), values, left=left, label=label, color=color)
            left = [a + b for a, b in zip(left, values)]
        ax.set_yticks(range(len(arms)), [a.replace('_', '-') for a in arms])
        ax.invert_yaxis()
        ax.set_xlim(0, 310)
        ax.set_title(case.replace('__n', ' / ') + ' Stage')
        ax.set_xlabel('Recorded wall time (s)')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='outside lower center', ncol=5, fontsize=9)
    fig.savefig(OUT / 'cost_breakdown.png', dpi=180)
    fig.savefig(OUT / 'cost_breakdown.svg')
    plt.close(fig)
    for f in OUT.glob('*.svg'):
        f.write_text('\n'.join(x.rstrip() for x in f.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')


def compare_scales(rows, old):
    prior = read(old / 'analysis.json')
    oldrows = prior['rows']
    current = read(OUT / 'analysis.json')
    scale_rows, lineages, trajectory_rows = [], [], []
    for root in ('U05', 'U06'):
        generation = read(OUT / 'input_generation' / (root + '__n24') / 'generation_evidence.json')
        parent = read(old / 'input_generation' / (root + '__n12') / 'generation_evidence.json')
        assert generation['lineage']['existing_profiles_and_edges_preserved']
        assert generation['parent_generation_evidence_sha256'] == sha(old / 'input_generation' / (root + '__n12') / 'generation_evidence.json')
        before, after = parent['two_scene_evidence']['workload'], generation['two_scene_evidence']['workload']
        for sid, value in before['physical_profiles'].items():
            assert after['physical_profiles'][sid] == value
        for app, value in before['applications'].items():
            original_edges = set(map(tuple, value['edges']))
            expanded_edges = set(map(tuple, after['applications'][app]['edges']))
            assert original_edges <= expanded_edges
        lineages.append({'root': root, 'parent_evidence_sha256': generation['parent_generation_evidence_sha256'],
                         'original_physical_profiles_and_edges_preserved': True,
                         'metrics_12': parent['metrics'], 'metrics_24': generation['metrics'],
                         'scope': 'Absolute energy changes include work and window growth; not an algorithm saving percentage.'})
        for arm in ('HEFT', 'ON', 'ON_P', 'OFF_P'):
            a = next(r for r in oldrows if r['root_id'] == root and r['arm'] == arm)
            b = next(r for r in rows if r['root_id'] == root and r['arm'] == arm)
            item = {'root_id': root, 'arm': arm}
            for scale, r, source in ((12, a, prior), (24, b, current)):
                heft = next(x for x in source['rows'] if x['root_id'] == root and x['arm'] == 'HEFT')
                for key in ('safe', 'post_passed', 'terminal', 'failure_reason', 'first_SAFE_at_s', 'initial_energy_J', 'energy_J',
                            'method_elapsed_s', 'initialization_s', 'initialization_completed_at_s', 'search_s',
                            'graph_construction_s', 'prefilter_total_s', 'electrothermal_evaluation_s',
                            'initialization_full_SAFE_evaluations', 'search_full_SAFE_evaluations', 'evaluation_attempts',
                            'graph_strict_improvements', 'extra_edge_accepts', 'actual_total_construction_calls',
                            'returned_unresolved_receipts', 'construction_calls_interrupted', 'init_admission_gate_hit'):
                    item[f'{key}_{scale}'] = r.get(key)
                item[f'saving_vs_same_scale_HEFT_percent_{scale}'] = (heft['energy_J'] - r['energy_J']) / heft['energy_J'] * 100 \
                    if all(x['safe'] and x['post_passed'] for x in (heft, r)) else None
                detail = source['details'].get(r['id'], {})
                accepted = detail.get('accepted_steps', [])
                item[f'last_search_accept_at_s_{scale}'] = accepted[-1]['returned_at_s'] if accepted else None
                for ordinal, step in enumerate(accepted, 1):
                    trajectory_rows.append({'root_id': root, 'arm': arm, 'scale': scale,
                                            'accepted_ordinal': ordinal, **{k: v for k, v in step.items() if k != 'extra_edges'},
                                            'extra_edges': json.dumps(step['extra_edges'], ensure_ascii=False)})
            scale_rows.append(item)
    save('scale_comparison.json', {'rows': scale_rows, 'lineages': lineages, 'new_scientific_calls': 0,
                                  'prior_12_stage_runs_not_repeated': True})
    csvfile('scale_comparison.csv', scale_rows)
    csvfile('acceptance_steps_12_24.csv', trajectory_rows)
    plot_scale_costs(oldrows, rows)


def plot_scale_costs(oldrows, rows):
    import matplotlib.pyplot as plt
    arms = ['HEFT', 'ON', 'ON_P', 'OFF_P']
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout='constrained')
    layers = [('pre_search_s', 'I1 + setup', '#c8c8c8'), ('search_evaluation_s', 'Search evaluation', '#82b2c9'),
              ('graph_construction_s', 'Construction', '#dc9d67'), ('prefilter_total_s', 'Prefilter', '#876ca6'), ('search_other_s', 'Other', '#6c777f')]
    for axis_row, root in zip(axes, ('U05', 'U06')):
        for ax, scale, source in zip(axis_row, (12, 24), (oldrows, rows)):
            selected = [{**r, 'pre_search_s': r.get('initialization_completed_at_s') or r.get('method_elapsed_s')}
                        for arm in arms for r in source if r['root_id'] == root and r['arm'] == arm]
            left = [0.] * len(arms)
            for key, label, color in layers:
                values = [r.get(key) or 0 for r in selected]
                ax.barh(range(len(arms)), values, left=left, label=label, color=color)
                left = [a + b for a, b in zip(left, values)]
            ax.set_yticks(range(len(arms)), [a.replace('_', '-') for a in arms])
            ax.invert_yaxis()
            ax.set_xlim(0, 310)
            ax.set_title(f'{root} / {scale} Stage')
            ax.set_xlabel('Recorded wall time (s)')
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='outside lower center', ncol=5, fontsize=9)
    fig.savefig(OUT / 'scale_cost.png', dpi=180)
    fig.savefig(OUT / 'scale_cost.svg')
    plt.close(fig)
    f = OUT / 'scale_cost.svg'
    f.write_text('\n'.join(x.rstrip() for x in f.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
