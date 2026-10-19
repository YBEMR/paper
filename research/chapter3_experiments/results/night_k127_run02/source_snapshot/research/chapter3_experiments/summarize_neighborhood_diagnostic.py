"""Read-only K126 analysis; no model, thermal evaluator or optimizer imports.

Use the original stored-receipt/native-array reader, adapting only N1's fresh
seed reference and report scope. No post-budget search or reevaluation occurs.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from summarize_cut_pair import (_call, _candidate_hash, _interval, _q,
                                _read, _timely)


def save(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False)+'\n').encode('utf-8'))


def _energy_parts(aggregate, instance):
    if not aggregate:
        return None
    parts = {}
    for scene in instance['scenarios']:
        sid, weight = scene['id'], _q(scene['weight'])
        for name, value in aggregate['scenes'][sid]['result']['energy_components_J'].items():
            lo, hi = _interval(value)
            before = parts.setdefault(name, [F(0), F(0)])
            before[0] += weight*lo
            before[1] += weight*hi
    return {name: [str(v) for v in interval] for name, interval in parts.items()}


def _schedule_changes(seed, final, instance):
    if not seed or not final:
        return []
    changes = []
    for scene in instance['scenarios']:
        sid = scene['id']
        stages = {s['id']: s for s in scene['stage_instances']}
        reference = {s['stage_id']: s for s in seed['scenes'][sid]}
        for row in final['scenes'][sid]:
            previous = reference[row['stage_id']]
            assert row['unit'] == previous['unit'], 'N1 cannot change a seed unit'
            if row['opp'] != previous['opp'] or _q(row['start_ms']) != _q(previous['start_ms']):
                modes = instance['stage_modes'][stages[row['stage_id']]['shared_stage_id']]
                def describe(choice):
                    mode = next(m for m in modes if m['unit_id'] == choice['unit'] and m['opp_id'] == choice['opp'])
                    return {**choice, 'duration_ms': mode['duration_ms'],
                            'end_ms': str(_q(choice['start_ms'])+_q(mode['duration_ms'])),
                            'activity_power_W': mode['activity_power_W']}
                changes.append({'scene_id': sid, 'stage_id': row['stage_id'],
                                'seed': describe(previous), 'final': describe(row)})
    return changes


def summarize(run_folder, out_folder):
    run, out = Path(run_folder).resolve(), Path(out_folder).resolve()
    if out.exists():
        raise FileExistsError(out)
    if run == out or run.is_relative_to(out):
        raise ValueError('Output cannot contain the input run')
    declaration, record = _read(run/'declaration.json'), _read(run/'run_record.json')
    if record.get('state') in ('RUNNING', 'DECLARED_NOT_RUN'):
        raise ValueError('Refusing unfinished run')
    call_folder = run/'call_n1'
    invocation = call_folder/'invocation'
    result = _read(invocation/'result.json')
    call_record = _read(call_folder/'run_record.json')
    call = _call(call_folder, 10, call_record)
    if call['receipt_errors']:
        raise ValueError('Stored receipt consistency error: '+str(call['receipt_errors']))
    limit = call['budget_s']
    instance = _read(invocation/'input_instance.json')
    window_s = _q(instance['window_ms'])/1000
    seeds, changes, scenes = {}, [], []
    for sid, scene in result['scenes'].items():
        initial = scene.get('initialisation') or {}
        reference = initial.get('candidate')
        if reference is None and result.get('condition') is not None:
            reference = {'scenes': {sid: result['condition']['seed_candidate']['scenes'][sid]}}
        initial_hash = _candidate_hash(reference)
        seeds[sid] = initial_hash
        distinct, safe_distinct = set(), set()
        for item in scene.get('model_view_evaluations', []):
            if item.get('source') == 'initial_constructor':
                continue
            h = _candidate_hash(item.get('candidate'))
            evaluation = item.get('evaluation') or {}
            timely = _timely(item.get('received_at_s'), limit)
            is_new = h is not None and initial_hash is not None and h != initial_hash
            if timely and is_new:
                distinct.add(h)
                physical = evaluation.get('scenes') or {}
                if (evaluation.get('state') == 'SAFE' and evaluation.get('rankable_energy')
                        and _timely(evaluation.get('completed_at_elapsed_s'), limit)
                        and physical and all(p.get('complete') is True
                            and _q(p['covered_until_s']) == window_s for p in physical.values())):
                    safe_distinct.add(h)
            changes.append({'scene_id': sid, 'source': item.get('source'),
                'candidate_sha256': h, 'initial_candidate_sha256': initial_hash,
                'different_from_this_call_seed': is_new,
                'received_at_s': item.get('received_at_s'), 'received_in_budget': timely,
                'evaluation_state': evaluation.get('state'),
                'completed_at_elapsed_s': evaluation.get('completed_at_elapsed_s')})
        solved = scene.get('solver_result') or {}
        diagnostic = solved.get('diagnostic') or {}
        bound_rows = scene.get('solver_reported_bounds', [])
        for bound in bound_rows:
            assert bound.get('scope') == 'seed_defined_N1_fixed_shared_deployment_unweighted_scene'
            assert bound.get('condition_sha256') == result.get('condition_sha256')
        scenes.append({'scene_id': sid, 'reason': scene.get('reason'),
            'model_summary': scene.get('model_summary'),
            'construction': scene.get('construction'),
            'x0_injected': scene.get('x0_injected'),
            'bare_MILP_fallback': scene.get('bare_MILP_fallback'),
            'initial_point_completion': initial.get('completion'),
            'distinct_new_decoded_arrangements': len(distinct),
            'distinct_new_model_view_SAFE_arrangements': len(safe_distinct),
            'candidate_receipts_including_duplicates': diagnostic.get('candidate_receipts'),
            'recorder_duplicate_receipts': diagnostic.get('duplicate_receipts'),
            'original_receipt_cache_hits': scene.get('original_receipt_cache_hits'),
            'model_view_evaluation_count': len(scene.get('model_view_evaluations', [])),
            'timely_legal_decode_records': sum(d.get('state') == 'LEGAL'
                and d.get('within_budget') is True for d in diagnostic.get('decode_records', [])),
            'original_input_evaluation_count': len(scene.get('original_scene_evaluations', [])),
            'feedback_count': len(solved.get('feedback', [])),
            'solver_reported_bounds': bound_rows,
            'diagnostic_decode_records': diagnostic.get('decode_records', [])})
    call['decoded_candidate_changes'] = changes
    any_new = any(s['distinct_new_decoded_arrangements'] for s in scenes)
    call['candidate_outcome'] = ('CERTIFIED_STRICT_IMPROVEMENT' if call['strict_improvement_certified'] else
        'DIFFERENT_DECODED_CANDIDATE_WITHOUT_CERTIFIED_STRICT_IMPROVEMENT' if any_new else
        'NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED')
    gaps = {}
    if call['final_U_J'] is not None:
        upper = _q(call['final_U_J'])
        for key, bound in call['independent_bounds'].items():
            lower = _q(bound['lower_bound_J'])
            assert lower <= upper
            gaps[key] = {'lower_bound_J': str(lower), 'upper_bound_J': str(upper),
                'absolute_gap_J': str(upper-lower),
                'relative_gap': str((upper-lower)/upper) if upper else None,
                'scope': bound['scope'], 'independently_proven_optimal': False}
    source_files = [Path(__file__), Path(__file__).with_name('summarize_cut_pair.py')]
    seed_aggregate = next((item['aggregation'] for item in result.get('seed_attempts', [])
        if item.get('state') == 'SAFE' and item.get('aggregation') is not None), None)
    fact = {'protocol': 'K126-single-N1-read-only-analysis-v1',
        'scope': 'one fresh seed-defined N1, fixed shared deployment; not a paired performance comparison',
        'declaration': declaration, 'run_record': record, 'call': call, 'scenes': scenes,
        'seed_candidate_sha256_by_scene': seeds, 'independent_gaps': gaps,
        'weighted_energy_components_J': {'initial': _energy_parts(seed_aggregate, instance),
                                        'final': _energy_parts(result.get('aggregation'), instance)},
        'schedule_changes_from_this_call_seed': _schedule_changes(
            None if seed_aggregate is None else seed_aggregate['safe_candidate'],
            result.get('safe_candidate'), instance),
        'final_peaks_degC_by_scene': {sid: receipt['result']['peaks_degC']
            for sid, receipt in (result.get('aggregation') or {}).get('scenes', {}).items()},
        'technical_state': result.get('technical_state'),
        'independently_proven_optimal': result.get('independently_proven_optimal'),
        'independently_proven_infeasible': result.get('independently_proven_infeasible'),
        'analysis_source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        'new_search_thermal_evaluation_or_candidate_decode': 0,
        'solver_bound_scope': 'unweighted one-scene N1 conditional reports; never aggregated to system L0/La'}
    fact['distinct_count_scope'] = ('distinct arrangements confirmed by saved model-view evaluation '
        'records only; decode records, duplicate receipts and changed native auxiliary vectors counted separately')
    out.mkdir(parents=True, exist_ok=False)
    save(out/'facts.json', fact)
    save(out/'requests.json', call['requests'])
    with (out/'energy_updates.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['committed_at_s', 'source', 'energy_lower_J', 'energy_upper_J'])
        writer.writeheader()
        for item in call['updates']:
            lo, hi = _interval(item['energy_J'])
            writer.writerow({'committed_at_s': item['committed_at_s'], 'source': item['source'],
                             'energy_lower_J': str(lo), 'energy_upper_J': str(hi)})
    _plot(out, call)
    print(json.dumps({'state': call['state'], 'reason': call['reason'],
        'initial_J': None if call['initial_energy_J'] is None else float(_interval(call['initial_energy_J'])[1]),
        'final_J': None if call['final_energy_J'] is None else float(_interval(call['final_energy_J'])[1]),
        'strict_improvement': call['strict_improvement_certified'],
        'distinct_new_arrangements': sum(s['distinct_new_decoded_arrangements'] for s in scenes),
        'feedback': call['feedback_records'], 'native_requests': len(call['requests'])}), flush=True)
    return fact


def _plot(out, call):
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.2), layout='constrained')
    limit = call['budget_s']
    end = min(limit, max(0.0, call['timing']['method_elapsed_s']))
    updates = [x for x in call['updates'] if x['committed_at_s'] <= end]
    if updates:
        xs = [x['committed_at_s'] for x in updates]
        ys = [float(_interval(x['energy_J'])[1]) for x in updates]
        ax.step(xs+[end], ys+[ys[-1]], where='post', label='Original-input SAFE U(t)', linewidth=1.7)
        ax.scatter(xs, ys, s=19)
    for key, style in [('L0', ':'), ('L_a', '--')]:
        bound = call['independent_bounds'].get(key)
        if bound is not None and bound['formed_at_s'] <= end:
            ax.plot([bound['formed_at_s'], end], [float(_q(bound['lower_bound_J']))]*2,
                    linestyle=style, label='Independent '+key)
    if call['initial_energy_J'] is not None:
        start = call['initial_complete_at_s']
        ax.plot([start, end], [float(_interval(call['initial_energy_J'])[1])]*2,
                linestyle='-.', label='This call seed upper')
    if end < limit:
        ax.axvspan(end, limit, color='#888888', alpha=.12, label='Unused budget')
    ax.set(xlim=(0, limit), xlabel='Elapsed method time (s)', ylabel='Weighted energy (J)',
           title='One N1 quality diagnostic; internal scene bounds kept separate')
    ax.grid(alpha=.22)
    ax.legend(fontsize=8)
    fig.savefig(out/'n1_bounds.png', dpi=200)
    fig.savefig(out/'n1_bounds.pdf')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    summarize(args.run, args.out)
