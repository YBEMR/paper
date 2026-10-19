"""Read-only K127 saved-JSON analysis; no planning, decoding or heat work.

Requires the six declared jobs to have terminal ledger entries. Stored receipt
consistency is checked; this does not repeat physical validation or certify
solver bounds. Production modules are intentionally never imported.
"""
import argparse
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def interval(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('missing interval')
    lo, hi = map(F, value)
    if lo > hi:
        raise ValueError('reversed interval')
    return lo, hi


def timely(value, limit):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value < limit)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_witness(point, instance, limit):
    try:
        scene = next(s for s in instance['scenarios'] if s['id'] == point['scene_id'])
        index = instance['platform']['node_order'].index(point['node'])
        low, high = interval(point['temperature_degC'])
        maximum = F(scene['maximum_temperature_degC'][index])
        return (timely(point.get('formed_at_elapsed_s'), limit)
            and 0 <= F(point['time_s']) <= F(instance['window_ms']) / 1000
            and F(point['limit_degC']) == maximum and low > maximum)
    except (KeyError, ValueError, TypeError, StopIteration):
        return False


def witness_key(point):
    # Re-reading the same point/interval later does not create another
    # physical violation. Preserve the first stored formation time separately.
    return digest({key: point[key] for key in ('scene_id', 'node', 'time_s',
                                              'temperature_degC', 'limit_degC')})


def physical_safe(receipt, scene, instance, limit):
    require(receipt.get('state') == 'SAFE' and receipt.get('complete') is True,
            'physical scene not complete SAFE')
    require(receipt.get('rankable_energy') is True and receipt.get('energy_accuracy_met') is True,
            'physical scene energy not accepted')
    require(not receipt.get('violations'), 'SAFE contains violations')
    require(receipt.get('scene_id') == scene['id'], 'physical scene id mismatch')
    require(timely(receipt.get('completed_at_elapsed_s'), limit), 'late physical scene')
    require(F(receipt['covered_until_s']) == F(instance['window_ms']) / 1000,
            'physical scene does not cover full window')
    energy = interval(receipt['energy_J'])
    parts = [interval(v) for v in receipt['energy_components_J'].values()]
    part_sum = (sum((v[0] for v in parts), F(0)), sum((v[1] for v in parts), F(0)))
    balance = interval(receipt['conservation_energy_J'])
    require(max(energy[0], part_sum[0], balance[0]) <= min(energy[1], part_sum[1], balance[1]),
            'energy accounting/conservation intervals disjoint')
    nodes = instance['platform']['node_order']
    require(set(receipt['peaks_degC']) == set(nodes), 'peak node set mismatch')
    valid = list(map(F, instance['platform']['power_model_temperature_range_degC']))
    for node, maximum in zip(nodes, scene['maximum_temperature_degC']):
        low, high = interval(receipt['peaks_degC'][node])
        minimum = interval(receipt['minimum_degC'][node])
        require(high <= F(maximum), 'SAFE peak upper exceeds limit')
        require(minimum[0] >= valid[0] and high <= valid[1], 'power model range not enclosed')
    trace = receipt.get('trace', [])
    require(trace and F(trace[-1]['time_s']) == F(instance['window_ms']) / 1000,
            'trace does not finish at window end')
    return energy


def full_safe(receipt, candidate, instance, limit, method, result=None):
    require(receipt.get('state') == 'SAFE' and receipt.get('rankable_energy') is True,
            'full receipt not accepted SAFE')
    require(timely(receipt.get('completed_at_elapsed_s'), limit), 'late full SAFE')
    require(not receipt.get('violations'), 'full SAFE contains violations')
    require(receipt.get('problem_id') == instance['id'], 'problem id mismatch')
    scene_ids = {s['id'] for s in instance['scenarios']}
    require(set(receipt['scenes']) == scene_ids and set(candidate['scenes']) == scene_ids,
            'SAFE does not cover every scene')
    require(receipt.get('legality', {}).get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
            'no matching complete legality receipt')
    energy = interval(receipt['weighted_energy_J'])
    require(F(receipt['safe_upper_bound_J']) == energy[1], 'U differs from weighted upper')
    weighted = [F(0), F(0)]
    if method == 'n1':
        identity = receipt['identity']
        require(identity['full_input_sha256'] == digest(instance), 'N1 full input identity mismatch')
        require(identity['candidate_sha256'] == digest(candidate), 'N1 candidate identity mismatch')
        require(receipt['safe_candidate'] == candidate, 'N1 saved candidate differs')
        require(receipt['receipt_sha256'] == digest({k: v for k, v in receipt.items()
                                                    if k != 'receipt_sha256'}), 'N1 receipt hash mismatch')
        require(not receipt.get('receipt_errors'), 'N1 receipt errors')
        shared = receipt['shared_deployment']
        require(identity['shared_deployment_sha256'] == digest(shared), 'N1 shared identity mismatch')
        for scene in instance['scenarios']:
            sid = scene['id']; local = receipt['scenes'][sid]
            require(local['state'] == 'SAFE' and local.get('rankable_energy') is True,
                    'N1 local receipt not SAFE')
            require(timely(local.get('completed_at_elapsed_s'), limit), 'late N1 local receipt')
            require(local['receipt_sha256'] == digest({k: v for k, v in local.items()
                                                      if k != 'receipt_sha256'}), 'N1 local receipt hash mismatch')
            ident = local['identity']
            require(ident['full_input_sha256'] == digest(instance), 'N1 local input mismatch')
            require(ident['candidate_sha256'] == digest({'scenes': {sid: candidate['scenes'][sid]}}),
                    'N1 local candidate mismatch')
            require(ident['budget'] == identity['budget'], 'N1 cross-budget receipt')
            require(ident['source_sha256'] == identity['source_sha256'], 'N1 source identity mismatch')
            require(ident['shared_deployment_sha256'] == digest(shared), 'N1 local deployment mismatch')
            require(local['energy_J'] == local['result']['energy_J'], 'N1 local energy mismatch')
            local_energy = physical_safe(local['result'], scene, instance, limit)
            require(F(local['safe_upper_bound_J']) == local_energy[1], 'N1 local U mismatch')
            weight = F(scene['weight'])
            for i in range(2): weighted[i] += weight * local_energy[i]
    else:
        if method == 'milp':
            require(receipt.get('evidence_identity') == {'input_sha256': digest(instance),
                'candidate_sha256': digest(candidate)}, 'MILP input/candidate identity mismatch')
        elif result is not None:
            require(result.get('input_sha256') == digest(instance), 'heuristic input identity mismatch')
            matching = [row for row in result.get('evaluations', [])
                if row.get('accepted_safe') is True and row.get('candidate') == candidate
                and row.get('evaluation') == receipt and row.get('candidate_sha256') == digest(candidate)]
            require(bool(matching), 'heuristic SAFE lacks candidate-bound accepted saved record')
        for scene in instance['scenarios']:
            local_energy = physical_safe(receipt['scenes'][scene['id']], scene, instance, limit)
            weight = F(scene['weight'])
            for i in range(2): weighted[i] += weight * local_energy[i]
    require(energy[0] <= weighted[0] <= weighted[1] <= energy[1],
            'weighted energy does not enclose exact weighted scene intervals')
    return energy


def full_evaluations(result, method):
    if method == 'n1':
        for item in result.get('seed_attempts', []):
            if item.get('aggregation'):
                a = item['aggregation']; yield a.get('safe_candidate'), a, 'initial_constructor'
        for a in result.get('aggregation_attempts', []):
            if a: yield a.get('safe_candidate'), a, 'aggregate'
        if result.get('aggregation'):
            a = result['aggregation']; yield result.get('safe_candidate'), a, 'final'
        return
    initial = result.get('initialisation') or {}
    for item in initial.get('attempts', []):
        if item.get('evaluation'):
            yield item.get('candidate'), item['evaluation'], 'initial_constructor'
    witness = initial.get('witness') or {}
    if witness.get('evaluation'):
        yield witness.get('candidate'), witness['evaluation'], 'initial_constructor'
    diag = result.get('diagnostic') or (result.get('solver_diagnostic') or {}).get('diagnostic') or {}
    for item in diag.get('evaluations', []) + result.get('evaluations', []):
        if item.get('evaluation'):
            yield item.get('candidate'), item['evaluation'], item.get('source')
    if result.get('evaluation'):
        yield result.get('safe_candidate'), result['evaluation'], 'final'


def records_for_native(result, method):
    if method == 'n1':
        return [(sid, scene.get('solver_result') or {}) for sid, scene in result.get('scenes', {}).items()]
    return [('whole', result.get('solver_diagnostic') or result)]


def read_bound(folder, result, instance, limit):
    scopes = {}
    path = folder / 'independent_bounds.json'
    if path.exists(): scopes.update(read(path))
    scopes.update(result.get('deployment_bounds') or {})
    if result.get('independent_lower_bound'):
        scopes['L0'] = result['independent_lower_bound']
    errors = []
    for key, bound in scopes.items():
        if bound is None:
            continue
        try:
            require(bound['input_sha256'] == digest(instance), key + ' input identity mismatch')
            require(bound['solver_reported'] is False, key + ' is solver reported')
            require(timely(bound.get('formed_at_s'), limit), key + ' not timely')
            require(bound['scope'] == ('original_full_domain' if key == 'L0' else 'fixed_shared_deployment'),
                    key + ' scope mismatch')
            F(bound['lower_bound_J'])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    return scopes, errors


def analyze_job(root, job, ledger_row, declaration):
    folder = root / job['id']; result = read(folder / 'result.json')
    instance = read(folder / 'input_instance.json'); limit = result['timing']['limit_s']
    errors = []
    require(digest(instance) == declaration['input_identities'][job['condition']]['instance_sha256'],
            job['id'] + ' input differs from frozen snapshot')
    require(F(instance['window_ms']) == 400 and limit == 300, 'unexpected window/budget')
    require(instance['execution_rules']['idle_policy'] == 'auto_low_immediate_v1', 'not auto-L')
    if job['method'] == 'milp':
        require(result.get('feedback_kind') == job['feedback_kind'], 'feedback version mismatch')
    if job['method'] in ('heft', 'sa'):
        require(result.get('method') == job['method'] and result.get('seed') == job.get('seed'),
                'heuristic method/seed differs from declaration')
    evaluations, safe, violations, seen = [], [], {}, set()
    initial_attempts = []
    for index, attempt in enumerate((result.get('initialisation') or {}).get('attempts', []), 1):
        evaluation = attempt.get('evaluation') or {}
        points = [w for w in evaluation.get('violations', []) if strict_witness(w, instance, limit)]
        initial_attempts.append({'attempt': index, 'template_rank': attempt.get('template_rank'),
            'rule_version': attempt.get('rule_version'), 'domain_opps': attempt.get('domain_opps'),
            'shared_deployment': attempt.get('shared_deployment'),
            'construction_state': attempt.get('status'), 'evaluation_state': evaluation.get('state'),
            'evaluation_reason': evaluation.get('reason'),
            'candidate_sha256': digest(attempt['candidate']) if attempt.get('candidate') else None,
            'candidate': attempt.get('candidate'), 'strict_violation_points': points,
            'completed_at_elapsed_s': evaluation.get('completed_at_elapsed_s'),
            'safe_upper_bound_J': evaluation.get('safe_upper_bound_J')})
    if job['method'] == 'n1':
        for index, attempt in enumerate(result.get('seed_attempts', []), 1):
            construction = attempt.get('construction') or {}
            aggregation = attempt.get('aggregation') or {}
            points = [w for local in attempt.get('scene_evaluations', {}).values()
                      for w in local.get('violations', []) if strict_witness(w, instance, limit)]
            initial_attempts.append({'attempt': index, 'template_rank': construction.get('template_rank'),
                'rule_version': construction.get('rule_version'), 'domain_opps': construction.get('domain_opps'),
                'shared_deployment': construction.get('shared_deployment'),
                'construction_state': construction.get('status'), 'evaluation_state': attempt.get('state'),
                'evaluation_reason': attempt.get('reason'),
                'candidate_sha256': digest(construction['candidate']) if construction.get('candidate') else None,
                'candidate': construction.get('candidate'), 'strict_violation_points': points,
                'completed_at_elapsed_s': aggregation.get('completed_at_elapsed_s'),
                'safe_upper_bound_J': aggregation.get('safe_upper_bound_J')})
    for candidate, receipt, source in full_evaluations(result, job['method']):
        identity = digest([candidate, receipt])
        if identity in seen:
            continue
        seen.add(identity)
        evaluations.append({'source': source, 'state': receipt.get('state'),
            'formed_at_s': receipt.get('completed_at_elapsed_s')})
        for witness in receipt.get('violations', []):
            if strict_witness(witness, instance, limit): violations.setdefault(witness_key(witness), witness)
        if receipt.get('state') == 'SAFE':
            try:
                energy = full_safe(receipt, candidate, instance, limit, job['method'], result)
                safe.append({'at_s': receipt['completed_at_elapsed_s'], 'source': source,
                    'energy_J': [str(v) for v in energy], 'candidate_sha256': digest(candidate)})
            except (KeyError, TypeError, ValueError) as exc:
                errors.append({'source': source, 'error': str(exc)})
    # N1 model-view violations and heuristic saved violation summaries may not
    # be full-domain evaluations, but remain diagnostic witnesses.
    for item in result.get('violations', []):
        witness = item.get('witness', item)
        if strict_witness(witness, instance, limit): violations.setdefault(witness_key(witness), witness)
    updates = []
    for point in sorted(safe, key=lambda x: x['at_s']):
        if not updates or F(point['energy_J'][1]) < F(updates[-1]['energy_J'][1]):
            updates.append(point)
    final = result.get('aggregation') if job['method'] == 'n1' else result.get('evaluation')
    final_verified = None
    if result['state'] == 'SAFE':
        try:
            final_verified = full_safe(final, result['safe_candidate'], instance, limit, job['method'], result)
            require(F(result['safe_upper_bound_J']) == final_verified[1], 'result U differs from receipt')
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({'source': 'FINAL_SAFE', 'error': str(exc)})
    bounds, bound_errors = read_bound(folder, result, instance, limit)
    errors.extend({'source': 'bound', 'error': error} for error in bound_errors)
    feedback, native, report_bounds = [], [], []
    for scope, solved in records_for_native(result, job['method']):
        feedback.extend(dict(item, scene_scope=scope) for item in solved.get('feedback', []))
        diagnostic = solved.get('diagnostic') or {}
        for item in diagnostic.get('evaluations', []):
            for witness in (item.get('evaluation') or {}).get('violations', []):
                if strict_witness(witness, instance, limit): violations.setdefault(witness_key(witness), witness)
        for i, record in enumerate(solved.get('rounds', []), 1):
            native.append({'scope': scope, 'round': i, 'status': record.get('status'),
                'exitflag': record.get('exitflag'), 'budget_valid': record.get('budget_valid'),
                'intlinprog_entered': record.get('intlinprog_entered'),
                'error': record.get('error_message'), 'numerical_consistency': record.get('numerical_consistency')})
            output = record.get('output') or {}
            report_bounds.append({'scope': 'N1_one_scene_conditional' if job['method'] == 'n1' else 'whole_original_domain',
                'scene': scope, 'round': i, 'origin': 'final_output', 'lowerbound': output.get('lowerbound'),
                'fval': record.get('fval'), 'absolutegap': output.get('absolutegap'),
                'relativegap': output.get('relativegap'), 'solver_reported_only': True,
                'budget_valid': record.get('budget_valid')})
            for callback in record.get('callbacks', []):
                values = callback.get('values') or {}
                if 'lowerbound' in values:
                    report_bounds.append({'scope': 'N1_one_scene_conditional' if job['method'] == 'n1'
                        else 'whole_original_domain', 'scene': scope, 'round': i,
                        'origin': 'callback', 'lowerbound': values['lowerbound'],
                        'request_wall_seconds': callback.get('request_wall_seconds'),
                        'solver_reported_only': True, 'budget_valid': record.get('budget_valid')})
    kinds = Counter(action.get('type', 'UNKNOWN') for item in feedback for action in item.get('actions', []))
    initial = result.get('initial_global_weighted_energy_J')
    if initial is None:
        witness = (result.get('initialisation') or {}).get('witness') or {}
        initial = (witness.get('evaluation') or {}).get('weighted_energy_J')
    first_safe = min((point['at_s'] for point in safe), default=None)
    l0 = bounds.get('L0')
    gap = None
    if l0 and not bound_errors and final_verified:
        lower = F(l0['lower_bound_J']); upper = final_verified[1]
        if lower <= upper:
            gap = {'L0_J': str(lower), 'U_J': str(upper), 'absolute_J': str(upper-lower),
                   'relative': str((upper-lower)/upper), 'scope': 'original full domain independent L0'}
        else: errors.append({'source': 'bound', 'error': 'independent L0 exceeds saved safe U'})
    return {'job': job, 'ledger': ledger_row, 'raw_state': result['state'], 'reason': result.get('reason'),
        'error': result.get('error'), 'technical_state': result.get('technical_state'),
        'input_sha256': digest(instance), 'candidate_sha256': digest(result['safe_candidate'])
            if result.get('safe_candidate') else None,
        'safe_receipts_checked': len(safe), 'stored_receipt_errors': errors,
        'final_SAFE_receipt_verified': bool(result['state'] == 'SAFE' and final_verified and not errors),
        'initial_energy_J': initial, 'final_energy_J': None if final_verified is None else [str(v) for v in final_verified],
        'initialisation_attempts': initial_attempts,
        'initialisation_strict_violation_points': [point for attempt in initial_attempts
                                                  for point in attempt['strict_violation_points']],
        'initialisation_selected_candidate': ((result.get('condition') or {}).get('seed_candidate')
            if job['method'] == 'n1' else
            ((result.get('initialisation') or {}).get('witness') or {}).get('candidate')),
        'initialisation_rejections_are_not_solver_feedback': True,
        'final_U_J': result.get('safe_upper_bound_J'), 'first_SAFE_s': first_safe,
        'safe_solution_source': result.get('safe_solution_source'),
        'actual_feedback_kind': result.get('feedback_kind'), 'actual_seed': result.get('seed'),
        'N1_condition_sha256': result.get('condition_sha256'),
        'strict_improvement_over_this_call_seed': bool(initial and final_verified and final_verified[1] < F(initial[0])),
        'independent_bounds': bounds, 'independent_bound_errors': bound_errors,
        'L0_gap': gap, 'solver_reported_bounds': report_bounds,
        'independently_proven_optimal': result.get('independently_proven_optimal'),
        'independently_proven_infeasible': result.get('independently_proven_infeasible'),
        'remaining_domain': result.get('remaining_domain'),
        'feedback_records': len(feedback), 'feedback_rows': sum(f.get('rows_added', 0) for f in feedback),
        'feedback_action_counts': dict(kinds), 'feedback_log': feedback,
        'timely_distinct_saved_violation_receipts': len(violations), 'violations': list(violations.values()),
        'solver_request_attempts': result.get('solver_request_attempts', 0), 'native_rounds': native,
        'timing': result.get('timing'), 'cleanup': ledger_row.get('cleanup'),
        'candidate_count': result.get('candidate_count'), 'thermal_evaluations': result.get('thermal_evaluations'),
        'saved_evaluation_states': evaluations, 'updates': updates,
        'scope_note': 'N1 searches a seed-defined subset; L_a and N1 scene solver bounds are not global L0',
        'evidence_level': 'stored-receipt consistency; no new heat calculation, schedule decode or search'}


def main(root):
    root = Path(root).resolve(); declaration = read(root / 'declaration.json'); ledger = read(root / 'ledger.json')
    rows = {row['id']: row for row in ledger['calls']}
    expected = declaration['jobs']
    require(len(expected) == 6, 'expected six frozen jobs')
    require(all(job['id'] in rows and rows[job['id']]['state'] not in ('RUNNING', 'DECLARED')
                for job in expected), 'refusing unfinished six-job ledger')
    require(all((root / job['id'] / 'result.json').exists() for job in expected), 'missing terminal job result')
    calls = [analyze_job(root, job, rows[job['id']], declaration) for job in expected]
    out = root / 'analysis01'; out.mkdir(exist_ok=False)
    (out / 'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    facts = {'protocol': 'K127-read-only-six-call-analysis-v1', 'calls': calls,
        'ledger': ledger, 'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'one thermal pair and one exploratory four-method comparison; not statistical ranking',
        'new_solver_thermal_decode_calls': 0,
        'consumed_method_call_count': sum(row.get('consumed') is True for row in ledger['calls']),
        'declared_method_budget_total_s': ledger.get('method_limit_s_consumed'),
        'actual_method_elapsed_total_s': sum(c['timing']['method_elapsed_s'] for c in calls),
        'wrapper_wall_total_s': sum(c['ledger'].get('wrapper_wall_s', 0) for c in calls),
        'post_cutoff_cleanup_total_s': sum(c['timing'].get('cleanup_s', 0) for c in calls),
        'all_final_SAFE_receipts_consistent': all(c['raw_state'] != 'SAFE' or c['final_SAFE_receipt_verified'] for c in calls)}
    (out / 'facts.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    fields = ['job', 'method', 'condition', 'raw_state', 'reason', 'first_SAFE_s', 'initial_U_J', 'final_U_J',
        'SAFE_verified', 'L0_J', 'method_elapsed_s', 'feedback_records', 'feedback_rows',
        'point_feedback_actions', 'assignment_actions', 'timely_violation_receipts', 'solver_request_attempts',
        'independently_proven_optimal', 'independently_proven_infeasible', 'receipt_errors', 'exclusive_phases_json']
    with (out / 'results.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for c in calls:
            writer.writerow({'job': c['job']['id'], 'method': c['job']['method'], 'condition': c['job']['condition'],
                'raw_state': c['raw_state'], 'reason': c['reason'], 'first_SAFE_s': c['first_SAFE_s'],
                'initial_U_J': None if c['initial_energy_J'] is None else c['initial_energy_J'][1],
                'final_U_J': c['final_U_J'], 'SAFE_verified': c['final_SAFE_receipt_verified'],
                'L0_J': (c['independent_bounds'].get('L0') or {}).get('lower_bound_J'),
                'method_elapsed_s': c['timing']['method_elapsed_s'], 'feedback_records': c['feedback_records'],
                'feedback_rows': c['feedback_rows'],
                'point_feedback_actions': c['feedback_action_counts'].get('conditional_temperature', 0),
                'assignment_actions': c['feedback_action_counts'].get('scene_assignment_exclusion', 0),
                'timely_violation_receipts': c['timely_distinct_saved_violation_receipts'],
                'solver_request_attempts': c['solver_request_attempts'],
                'independently_proven_optimal': c['independently_proven_optimal'],
                'independently_proven_infeasible': c['independently_proven_infeasible'],
                'receipt_errors': len(c['stored_receipt_errors']),
                'exclusive_phases_json': json.dumps(c['timing'].get('phases_exclusive_s', {}), sort_keys=True)})
    with (out / 'energy_updates.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['job', 'at_s', 'source', 'energy_lower_J', 'U_J', 'candidate_sha256'])
        writer.writeheader()
        for c in calls:
            for p in c['updates']:
                writer.writerow({'job': c['job']['id'], 'at_s': p['at_s'], 'source': p['source'],
                    'energy_lower_J': p['energy_J'][0], 'U_J': p['energy_J'][1], 'candidate_sha256': p['candidate_sha256']})
    plot(out, calls)
    thermal_acceptance(root, out, calls)
    print(json.dumps({'out': str(out), 'calls': len(calls),
        'all_final_SAFE_receipts_consistent': facts['all_final_SAFE_receipts_consistent']}, ensure_ascii=False))


def plot(out, calls):
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), layout='constrained')
    for ax, phase, title in zip(axes, ('heat', 'comparison'),
            ('52 C temperature limit: continuous feedback vs assignment deletion',
             'Original 80 C limit: one exploratory call per method')):
        for c in calls:
            if c['job']['phase'] != phase: continue
            end = min(300, c['timing']['method_elapsed_s']); points = c['updates']
            if points:
                xs = [p['at_s'] for p in points]; ys = [float(F(p['energy_J'][1])) for p in points]
                ax.step(xs + [max(end, xs[-1])], ys + [ys[-1]], where='post', label=c['job']['id'])
                ax.scatter(xs, ys, s=13)
            bound = c['independent_bounds'].get('L0')
            if bound and not c['independent_bound_errors']:
                ax.plot([bound['formed_at_s'], end], [float(F(bound['lower_bound_J']))] * 2,
                        linestyle=':', alpha=.45, label=c['job']['id'] + ' independent L0')
        ax.set(xlim=(0, 300), xlabel='Elapsed method time (s)', ylabel='Weighted energy (J)', title=title)
        ax.grid(alpha=.2); ax.legend(fontsize=7)
    fig.savefig(out / 'safe_upper_and_independent_L0.png', dpi=200)
    fig.savefig(out / 'safe_upper_and_independent_L0.pdf')
    plt.close(fig)


def thermal_acceptance(root, out, calls):
    """Draw saved peak enclosures only; never invent a time trajectory."""
    base = read(root / 'base_milp/result.json')
    hot = read(root / 'heat52_conditional/result.json')
    base_input = read(root / 'base_milp/input_instance.json')
    hot_input = read(root / 'heat52_conditional/input_instance.json')
    base_attempt = next(a for a in base['initialisation']['attempts']
                        if a.get('domain_opps') and set(a['domain_opps'].values()) == {'H'})
    hot_h = next(a for a in hot['initialisation']['attempts']
                 if a.get('domain_opps') and set(a['domain_opps'].values()) == {'H'})
    h_receipt = base_attempt['evaluation']; m_receipt = hot['evaluation']
    require(digest(base_attempt['candidate']) == digest(hot_h['candidate']),
            'thermal illustration H candidates differ')
    full_safe(h_receipt, base_attempt['candidate'], base_input, 300, 'milp', base)
    full_safe(m_receipt, hot['safe_candidate'], hot_input, 300, 'milp', hot)
    require(hot_h['evaluation']['state'] == 'THERMAL_VIOLATION', 'hot H rejection absent')
    require(bool(hot_h['evaluation'].get('violations')), 'hot H has no saved point witness')
    require(set((hot['initialisation']['witness']['candidate']['scenes'])) ==
            set(hot['safe_candidate']['scenes']), 'hot selected scene set differs')
    for rows in hot['safe_candidate']['scenes'].values():
        require(all(row['opp'] == 'M' for row in rows), 'thermal illustration final schedule is not all M')
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    nodes = base_input['platform']['node_order']
    scenes = base_input['scenarios']
    require(len(scenes) == 2, 'thermal illustration expects AB/AC')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), layout='constrained', sharey=True)
    saved = []
    for ax, scene in zip(axes, scenes):
        sid = scene['id']
        require(all(F(t) == 50 for t in scene['entry']['temperature_degC']), 'unexpected entry in illustration')
        for receipt, offset, marker, color, label in (
                (h_receipt, -.12, 'o', '#d55e00', 'H: accepted at 80 C; rejected at 52 C'),
                (m_receipt, .12, 's', '#0072b2', 'M: accepted at 52 C')):
            bounds = [interval(receipt['scenes'][sid]['peaks_degC'][node]) for node in nodes]
            values = [float((lo + hi) / 2) for lo, hi in bounds]
            lower = [max(0, value - float(bound[0])) for value, bound in zip(values, bounds)]
            upper = [max(0, float(bound[1]) - value) for value, bound in zip(values, bounds)]
            xs = [i + offset for i in range(len(nodes))]
            ax.errorbar(xs, values, yerr=[lower, upper], marker=marker, linestyle='none',
                        color=color, capsize=4, label=label)
            for x, value in zip(xs, values):
                ax.annotate('%.3f' % value, (x, value), xytext=(0, 7),
                            textcoords='offset points', ha='center', fontsize=7, color=color)
            saved.append({'scene_id': sid, 'source': label,
                'peaks_degC': {node: [str(v) for v in bound] for node, bound in zip(nodes, bounds)}})
        ax.axhline(52, color='#a50026', linestyle='--', linewidth=1.1, label='52 C limit')
        ax.axhline(50, color='#666666', linestyle=':', linewidth=1, label='50 C entry')
        ax.set(xticks=list(range(len(nodes))), xticklabels=nodes,
               title=sid.split('_')[0] + ': stored full-window peak enclosures', xlabel='Thermal node')
        ax.grid(axis='y', alpha=.2)
    axes[0].set_ylabel('Peak temperature (C)')
    axes[0].legend(fontsize=6.5, loc='upper left')
    fig.suptitle('Thermal acceptance changes: same H schedule, lower-power M fallback\n'
                 'Saved peak intervals only; no new thermal evaluation or interpolated trajectory', fontsize=10)
    fig.savefig(out / 'thermal_acceptance.png', dpi=200)
    plt.close(fig)
    (out / 'thermal_acceptance_values.json').write_text(json.dumps({
        'H_candidate_sha256': digest(base_attempt['candidate']),
        'M_candidate_sha256': digest(hot['safe_candidate']), 'values': saved,
        'scope': 'archived peak enclosures only; not additional search or thermal evidence'},
        ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    main(args.run)
