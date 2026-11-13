"""Descriptive synthesis of archived U01-U06 runs. No scheduler imports/calls."""
from collections import Counter, defaultdict
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'RESEARCH_BRIEF.md').is_file())
BASE = OUT.parent
BATCHES = [
    ('unseen_scaling_20261112', 'I0_first_roots_6_to_12'),
    ('p3_unseen_ablation_20261112', 'I0_seen_mechanism'),
    ('i1_initialization_20261112', 'I1_development_initialization'),
    ('i1_paired_20261113', 'I1_seen_mechanism'),
    ('unseen_i1_20261113', 'I1_initial_unseen'),
    ('scale24_i1_20261113', 'I1_seen_scale_extension'),
    ('onp_cost_ablation_20261113', 'ONP_development_regression'),
    ('onp_unseen_20261113', 'ONP_initial_unseen'),
    ('onp_scale24_20261113', 'ONP_seen_scale_extension')]
SOURCES = {}


def read(p):
    b = p.read_bytes()
    SOURCES[p.relative_to(REPO).as_posix()] = hashlib.sha256(b).hexdigest()
    return json.loads(b)


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def interval(v):
    return tuple(F(x) for x in v) if v else None


def csvfile(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    rows, states, traces, construction_failures = [], {}, [], []
    for batch, role in BATCHES:
        folder = BASE / batch
        sf = next(p for p in (folder / 'execution/summary.json', folder / 'summary.json') if p.exists())
        summary, plan = read(sf), read(sf.parent / 'plan.json')
        analysis_path = next(p for p in (folder / 'analysis.json', folder / 'execution/analysis.json') if p.exists())
        analysis = read(analysis_path)
        enriched = {r['id']: r for r in analysis.get('rows', [])}
        for sr in summary['rows']:
            r = {**sr, **enriched.get(sr['id'], {})}
            call = sf.parent / 'calls' / r['id']
            raw = read(call / 'method/result.json')
            assert raw['timing']['limit_s'] == 300
            ret = read(call / 'method_return.json')
            assert SOURCES[(call / 'method/result.json').relative_to(REPO).as_posix()] == ret['raw_result_sha256']
            assert r['error'] is None
            post = read(call / 'post_return.json') if (call / 'post_return.json').exists() else {}
            if r['safe']:
                assert r['post_passed'] and post['passed'] and not post['error']
            initial = raw.get('initial_safe_snapshot') or {}
            meta = raw.get('initialization') or {}
            ei = interval(initial.get('receipt', {}).get('weighted_energy_J'))
            ef = interval([r['energy_lower_J'], r['energy_upper_J']]) if r['safe'] else None
            version = raw.get('initialization_version', 'I0')
            uid = batch + '/' + r['id']
            arm = 'HEFT' if r['arm'] in ('I0', 'I1') else r['arm']
            physical = [e for e in raw['evaluations'] if not e.get('cache_hit')]
            init = [e for e in physical if e['phase'] == 'initialization']
            props = raw.get('graph_proposals', [])
            units = lambda candidate: {(scene, t['stage_id']): t['unit'] for scene, tasks in candidate['scenes'].items() for t in tasks}
            if initial:
                initial_units = units(initial['candidate'])
                assert all(units(p['candidate']) == initial_units for p in props)
                assert units(raw['safe_candidate']) == initial_units
            ie = [(e['candidate_sha256'], e['receipt']['state'], interval(e['receipt'].get('weighted_energy_J'))) for e in init]
            initial_sha = digest(initial['candidate']) if initial else None
            attempts = meta.get('construction_attempts', [])
            for j, attempt in enumerate(attempts, 1):
                if attempt.get('reason'):
                    construction_failures.append({'run_id': uid, 'root_id': r['root_id'], 'stage_count': r['stages_per_scene'],
                                                  'ordinal': j, 'reason': attempt.get('reason'),
                                                  'failed_shared_stage': attempt.get('failed_shared_stage'),
                                                  'priority': attempt.get('priority_policy'), 'opp_rank': attempt.get('opp_rank')})
            extra = sum(bool(p.get('additional_reversed_edges')) and bool(p.get('strict_accepted')) for p in props)
            row = {'run_id': uid, 'batch': batch, 'evidence_role': role, 'source_commit': plan.get('subject_commit'),
                   'root_id': r['root_id'], 'stages_per_scene': r['stages_per_scene'], 'arm': arm,
                   'initializer': version, 'initialization_only': batch == 'i1_initialization_20261112',
                   'safe': r['safe'], 'post_passed': r['post_passed'], 'terminal': r['terminal'],
                   'reason': r['reason'], 'failure_reason': r.get('failure_reason'),
                   'energy_lower_J': str(ef[0]) if ef else None, 'energy_upper_J': str(ef[1]) if ef else None,
                   'energy_J': float(ef[1]) if ef else None, 'initial_energy_J': float(ei[1]) if ei else None,
                   'saving_vs_own_initial_percent': float((ei[1] - ef[1]) / ei[1] * 100) if ei and ef else None,
                   'same_batch_HEFT_run_id': None, 'saving_vs_same_batch_HEFT_percent': None,
                   'same_initial_as_HEFT': None, 'first_SAFE_at_s': raw.get('first_safe_at_s'),
                   'fallback_used': meta.get('fallback_used', False),
                   'init_gate_hit': r.get('init_admission_gate_hit', r.get('admission_gate_triggered', meta.get('stop_reason') == 'INIT_ADMISSION_LIMIT')),
                   'method_elapsed_s': r['method_elapsed_s'], 'initialization_s': r['initialization_s'],
                   'handoff_s': r['initialization_completed_at_s'], 'search_s': r['search_s'],
                   'search_budget_exhausted': arm != 'HEFT' and r['terminal'] == 'BUDGET_EXHAUSTED',
                   'evaluation_attempts': r['evaluation_attempts'], 'complete_SAFE_evaluations': r['full_electrothermal_SAFE_evaluations'],
                   'init_SAFE_evaluations': r['initialization_full_SAFE_evaluations'], 'search_SAFE_evaluations': r['search_full_SAFE_evaluations'],
                   'unresolved_evaluations': r['returned_unresolved_receipts'], 'electrothermal_s': r['electrothermal_evaluation_s'],
                   'construction_s': r['graph_construction_s'], 'prefilter_s': r.get('prefilter_total_s', 0),
                   'construction_plus_prefilter_s': r['graph_construction_s'] + r.get('prefilter_total_s', 0),
                   'returned_constructions': r['graph_reconstruction_attempts'],
                   'actual_construction_calls': r['actual_base_calls'] + r['actual_extra_calls'] if 'actual_base_calls' in r else None,
                   'base_pruned': r.get('base_pruned', 0), 'extra_pruned': r.get('extra_pruned_individually', 0),
                   'construction_interruptions': r.get('construction_calls_interrupted'),
                   'strict_accepts': r['graph_strict_improvements'], 'extra_edge_accepts': extra,
                   'initial_candidate_sha256': initial_sha, 'input_sha256': raw['input_sha256'],
                   'raw_result_path': (call / 'method/result.json').relative_to(REPO).as_posix()}
            rows.append(row)
            states[uid] = {'initial_interval': ei, 'final_interval': ef, 'init_sequence': ie,
                           'search_proposals': [p['candidate_sha256'] for p in props],
                           'final_candidate_sha256': digest(raw['safe_candidate']) if r['safe'] else None}
            for event in raw.get('events', []):
                traces.append({'run_id': uid, 'root_id': r['root_id'], 'stages_per_scene': r['stages_per_scene'],
                               'arm': arm, 'initializer': version, 'phase': event['phase'], 'time_s': event['at_s'],
                               'energy_lower_J': event['energy']['lower'], 'energy_upper_J': event['energy']['upper'],
                               'candidate_sha256': event['candidate_sha256']})
    assert len(rows) == 59 and len({r['run_id'] for r in rows}) == 59
    groups = defaultdict(dict)
    for r in rows:
        groups[(r['batch'], r['root_id'], r['stages_per_scene'], r['initializer'])][r['arm']] = r
    pairs = []
    for key, arms in groups.items():
        for a, b, kind in [('ON', 'OFF', 'blocking_original'), ('ON_P', 'OFF_P', 'blocking_with_prefilter'),
                           ('ON_P', 'ON', 'prefilter_ON'), ('OFF_P', 'OFF', 'prefilter_OFF'),
                           ('ON', 'HEFT', 'end_to_end_HEFT'), ('ON_P', 'HEFT', 'end_to_end_HEFT'),
                           ('OFF_P', 'HEFT', 'end_to_end_HEFT'), ('OFF', 'HEFT', 'end_to_end_HEFT')]:
            if a not in arms or b not in arms:
                continue
            x, y = arms[a], arms[b]
            assert x['input_sha256'] == y['input_sha256']
            sx, sy = states[x['run_id']], states[y['run_id']]
            valid = bool(x['safe'] and y['safe'] and x['post_passed'] and y['post_passed'])
            same = bool(valid and x['initial_candidate_sha256'] == y['initial_candidate_sha256'] and sx['initial_interval'] == sy['initial_interval'])
            seq = same and sx['init_sequence'] == sy['init_sequence']
            cache_diff = {p[0] for p in sx['init_sequence']} ^ {p[0] for p in sy['init_sequence']}
            hits = len(cache_diff & (set(sx['search_proposals']) | set(sy['search_proposals'])))
            level = 'A_same_initial_and_sequence' if seq else 'B_same_initial_different_sequence' if same else 'C_different_initial_end_to_end' if valid else 'D_no_SAFE_comparison'
            outcome = 'NO_SAFE'
            gain = None
            if valid:
                u, v = sx['final_interval'], sy['final_interval']
                outcome = 'WIN' if u[1] < v[0] else 'LOSS' if v[1] < u[0] else 'TIE' if u == v else 'INTERVAL_OVERLAP'
                gain = float((v[1] - u[1]) / v[1] * 100)
            if b == 'HEFT':
                x['same_batch_HEFT_run_id'] = y['run_id']
                x['saving_vs_same_batch_HEFT_percent'] = gain
                x['same_initial_as_HEFT'] = same
            pairs.append({'batch': key[0], 'evidence_role': x['evidence_role'], 'root_id': key[1], 'stages_per_scene': key[2],
                          'initializer': key[3], 'comparison_kind': kind, 'arm': a, 'reference': b,
                          'run_id': x['run_id'], 'reference_run_id': y['run_id'], 'comparability': level,
                          'same_initial': same, 'same_initial_sequence': seq, 'initial_cache_difference_hits_search': hits,
                          'outcome': outcome, 'saving_percent': gain, 'arm_J': x['energy_J'], 'reference_J': y['energy_J'],
                          'same_final_candidate': sx['final_candidate_sha256'] == sy['final_candidate_sha256'] if valid else None,
                          'both_search_naturally_completed': a != 'HEFT' and b != 'HEFT' and x['terminal'] == y['terminal'] == 'SEARCH_COMPLETED',
                          'arm_budget_exhausted': x['search_budget_exhausted'], 'reference_budget_exhausted': y['search_budget_exhausted'],
                          'arm_construction_plus_prefilter_s': x['construction_plus_prefilter_s'],
                          'reference_construction_plus_prefilter_s': y['construction_plus_prefilter_s'],
                          'arm_actual_constructions': x['actual_construction_calls'], 'reference_actual_constructions': y['actual_construction_calls']})
    # Preserve each repeated batch as a separate observation, never as an independent parameter root.
    tallies = defaultdict(Counter)
    for p in pairs:
        k = (p['comparison_kind'], p['initializer'], p['comparability'], p['evidence_role'])
        tallies[k][p['outcome']] += 1
    tally_rows = [{'comparison_kind': k[0], 'initializer': k[1], 'comparability': k[2], 'evidence_role': k[3], **dict(v)} for k, v in tallies.items()]
    budgets = []
    for version in ('I0', 'I1'):
        for size in (6, 12, 24):
            for arm in ('HEFT', 'ON', 'OFF', 'ON_P', 'OFF_P'):
                rr = [r for r in rows if r['initializer'] == version and r['stages_per_scene'] == size and r['arm'] == arm]
                if rr:
                    budgets.append({'initializer': version, 'stage_count': size, 'arm': arm, 'runs': len(rr),
                                    'SAFE_posts': sum(bool(r['safe'] and r['post_passed']) for r in rr),
                                    'budget_exhausted': sum(r['search_budget_exhausted'] for r in rr),
                                    'init_gate_hits': sum(bool(r['init_gate_hit']) for r in rr),
                                    'fallback_runs': sum(bool(r['fallback_used']) for r in rr),
                                    'unresolved_evaluations': sum(r['unresolved_evaluations'] for r in rr)})
    fallbacks = defaultdict(list)
    for r in rows:
        if r['fallback_used']:
            fallbacks[f"{r['root_id']}__n{r['stages_per_scene']}"].append(r['run_id'])
    result = {'verification_status': 'ANALYZED', 'snapshot_commit': '2ad44d4ec153b6a518de8df13d4c632d6849d8fa',
              'new_method_or_thermal_calls': 0, 'runs': len(rows), 'SAFE_posts': sum(bool(r['safe'] and r['post_passed']) for r in rows),
              'all_search_proposals_preserve_initial_device_assignment': True,
              'unique_roots': sorted({r['root_id'] for r in rows}), 'unique_root_scales': len({(r['root_id'], r['stages_per_scene']) for r in rows}),
              'I0_runs': sum(r['initializer'] == 'I0' for r in rows), 'I1_runs': sum(r['initializer'] == 'I1' for r in rows),
              'total_method_evaluation_attempts': sum(r['evaluation_attempts'] for r in rows),
              'complete_SAFE_evaluations': sum(r['complete_SAFE_evaluations'] for r in rows),
              'unresolved_evaluations': sum(r['unresolved_evaluations'] for r in rows),
              'search_runs': sum(r['arm'] != 'HEFT' for r in rows), 'budget_exhausted_search_runs': sum(r['search_budget_exhausted'] for r in rows),
              'fallback_cases': dict(fallbacks), 'pair_tallies': tally_rows, 'budget_strata': budgets,
              'pair_count': len(pairs), 'known_limit': 'Repeated roots, scale extensions, algorithm versions and development cohorts are not independent samples.'}
    csvfile('runs.csv', rows)
    csvfile('pairs.csv', pairs)
    csvfile('pair_tallies.csv', tally_rows)
    csvfile('budget_strata.csv', budgets)
    csvfile('energy_time.csv', traces)
    csvfile('initialization_failures.csv', construction_failures)
    save('synthesis.json', result)
    save('source_files_sha256.json', SOURCES)
    print(json.dumps({k: v for k, v in result.items() if k not in ('pair_tallies', 'budget_strata', 'fallback_cases')}, indent=2))
    print('FALLBACK CASES', {k: len(v) for k, v in fallbacks.items()})


if __name__ == '__main__':
    main()
