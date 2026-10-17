"""Archive-only chapter-3 analysis. No solver, decoder or thermal imports.

All objective/temperature evidence is read from completed, controller-accepted
calls. Outputs are written outside the immutable experiment directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import statistics
import time


METHODS = ('milp', 'heft', 'sa', 'assignment')
SEEDS = (101, 102, 103, 104, 105)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def number(value):
    if value is None or isinstance(value, (bool, list, dict)):
        return None
    try:
        f = float(F(str(value)))
        return f if math.isfinite(f) else None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def interval(value):
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        a, b = map(lambda v: F(str(v)), value)
        return (a, b) if a <= b else None
    except (ValueError, ZeroDivisionError):
        return None


def rat(value):
    return str(value) if value is not None else None


def median(values):
    return statistics.median(values) if values else None


def min_nonmissing(values):
    values = [v for v in values if v is not None]
    return min(values) if values else None


def read_optional(path, issues):
    if not path.is_file():
        return None
    try:
        return load(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append({'file': str(path), 'error': type(error).__name__,
                       'scope': 'read snapshot only; no replacement evidence'})
        return None


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def safe_receipt(receipt, seconds):
    """Check archived acceptance fields, without recomputing safety."""
    if not isinstance(receipt, dict):
        return False
    energy = interval(receipt.get('weighted_energy_J'))
    at = number(receipt.get('completed_at_elapsed_s'))
    upper = number(receipt.get('safe_upper_bound_J'))
    return bool(receipt.get('state') == 'SAFE' and receipt.get('rankable_energy') is True
                and energy is not None and at is not None and 0 <= at < seconds
                and upper is not None and F(str(receipt['safe_upper_bound_J'])) == energy[1]
                and receipt.get('scenes') and all(
                    sc.get('state') == 'SAFE' and sc.get('complete') is True
                    for sc in receipt['scenes'].values()))


def preserved_safe_evidence(result, instance, job, expected_input_sha256=None):
    """Audit a saved receipt even if later worker archival/labels failed.

    This is never a replacement controller acceptance or a new legality/heat
    calculation. A missing final call_id is permitted only in this audit tier.
    """
    checks = {}
    result, instance = result or {}, instance or {}
    receipt = result.get('evaluation') or {}
    candidate = result.get('safe_candidate')
    try:
        actual = canonical_hash(instance)
        checks['saved_input_matches_own_hash'] = result.get('input_sha256') == actual
        checks['saved_input_matches_frozen_manifest'] = (expected_input_sha256 is not None
                                                        and actual == expected_input_sha256)
        checks['problem_method_seed_identity'] = (
            result.get('problem_id') == job['problem_id'] == instance.get('id')
            and result.get('method') == job['method'] and result.get('seed') == job['seed'])
        checks['call_id_missing_or_matching'] = result.get('call_id') in (None, job['call_id'])
        checks['saved_safe_receipt_in_budget'] = safe_receipt(receipt, job['seconds'])
        checks['safe_upper_matches_receipt'] = bool(result.get('state') == 'SAFE'
            and candidate and F(result['safe_upper_bound_J']) == F(receipt['safe_upper_bound_J']))
        checks['receipt_problem_identity'] = receipt.get('problem_id') == job['problem_id']
        legal = receipt.get('legality') or {}
        checks['stored_legality_receipt'] = (legal.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
                                              and legal.get('problem_id') == job['problem_id'])
        scenes = receipt.get('scenes') or {}
        checks['all_scenes_whole_window'] = (set(scenes) == {s['id'] for s in instance['scenarios']}
            and all(F(s.get('covered_until_s', '-1')) == F(instance['window_ms'])/1000
                    for s in scenes.values()))
        checks['candidate_linked_to_accepted_receipt'] = any(
            row.get('accepted_safe') is True and row.get('candidate') == candidate
            and row.get('evaluation') == receipt
            for row in list(result.get('evaluations') or [])
            +list((result.get('diagnostic') or {}).get('evaluations') or []))
        initial = (result.get('initialisation') or {}).get('witness') or {}
        if initial.get('candidate') == candidate and initial.get('evaluation') == receipt:
            checks['candidate_linked_to_accepted_receipt'] = True
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        checks['audit_interface_complete'] = False
    passed = bool(checks and all(checks.values()))
    records = archived_safe_records(result, job['seconds']) if passed else []
    return {'preserved': passed, 'checks': checks,
            'U_J': result.get('safe_upper_bound_J') if passed else None,
            'first_safe_at_s': min_nonmissing([number(r['evaluation']['completed_at_elapsed_s'])
                                               for r in records]) if passed else None,
            'scope': 'saved receipt consistency only; does not change failed controller/worker status'}


def archived_safe_records(result, seconds):
    """All complete in-budget receipts, including a constructor seed."""
    rows = []
    witness = (result.get('initialisation') or {}).get('witness')
    if witness and safe_receipt(witness.get('evaluation'), seconds):
        rows.append({'source': 'initial_constructor', 'evaluation': witness['evaluation']})
    diag = result.get('diagnostic') or {}
    for row in list(result.get('evaluations') or []) + list(diag.get('evaluations') or []):
        if row.get('accepted_safe') is True and safe_receipt(row.get('evaluation'), seconds):
            rows.append({'source': row.get('source'), 'evaluation': row['evaluation']})
    # Retained final evidence may be present without an event list. Do not add
    # it twice merely because it is duplicated at the result top level.
    receipt = result.get('evaluation')
    if safe_receipt(receipt, seconds):
        key = (receipt['completed_at_elapsed_s'], receipt['safe_upper_bound_J'])
        if not any((r['evaluation']['completed_at_elapsed_s'],
                    r['evaluation']['safe_upper_bound_J']) == key for r in rows):
            rows.append({'source': result.get('safe_solution_source', 'retained_final'),
                         'evaluation': receipt})
    return sorted(rows, key=lambda r: r['evaluation']['completed_at_elapsed_s'])


def solver_records(result, seconds):
    """Keep native internal information as reported; never certify/clamp it."""
    rows = []
    diag = result.get('diagnostic') or {}
    for event in diag.get('solver_progress', []):
        values = event.get('values') or {}
        at = number(event.get('method_elapsed_s'))
        try:
            request_round = int(str(event.get('request', '')).rsplit('_', 1)[-1])
        except ValueError:
            request_round = 0
        rows.append({'at_s': at, 'origin': 'received_callback',
                     'round': request_round,
                     'received_in_budget': at is not None and 0 <= at < seconds,
                     'request': event.get('request'), 'kind': event.get('kind'),
                     'phase': values.get('phase'), 'lowerbound_J': number(values.get('lowerbound')),
                     'objective_J': number(values.get('fval')),
                     'relativegap_native': number(values.get('relativegap')),
                     'absolutegap_J': number(values.get('absolutegap')),
                     'independently_certified': False})
    for index, returned in enumerate(result.get('rounds') or [], 1):
        values = returned.get('output') or {}
        rows.append({'at_s': None, 'origin': 'returned_round', 'round': index,
                     'received_in_budget': returned.get('budget_valid') is True,
                     'lowerbound_J': number(values.get('lowerbound')),
                     'objective_J': number(returned.get('fval')),
                     'relativegap_native': number(values.get('relativegap')),
                     'absolutegap_J': number(values.get('absolutegap')),
                     'exitflag': returned.get('exitflag'),
                     'solver_status': returned.get('status'),
                     'independently_certified': False})
    # A later-round callback must not be replaced by an older round's final
    # output. Round order is known; a final response has no fabricated receipt
    # timestamp and follows callbacks from its own round only.
    return sorted(rows, key=lambda r: (r['round'], r['origin'] == 'returned_round',
                                      r.get('at_s') if r.get('at_s') is not None else -1))


def energy_parts(result, instance):
    """Weighted archived components; split constant terms using saved segments.

    Temperature-correction energy lacks per-segment integrals in the current
    receipt. Full execution/tail totals therefore remain explicitly unavailable.
    No sampled-temperature integration or thermal propagation is performed.
    """
    if not instance or result.get('state') != 'SAFE':
        return {'available': False, 'reason': 'no accepted safe result/input'}
    receipt = result.get('evaluation') or {}
    scenes = receipt.get('scenes') or {}
    legality = (receipt.get('legality') or {}).get('scenes') or {}
    totals = defaultdict(lambda: [F(0), F(0)])
    split = {part: defaultdict(F) for part in ('execution', 'tail')}
    durations = []
    try:
        for scene in instance['scenarios']:
            sid, weight = scene['id'], F(scene['weight'])
            sc = scenes[sid]
            for name, raw in sc['energy_components_J'].items():
                bounds = interval(raw)
                if bounds is None:
                    raise ValueError('malformed component interval')
                totals[name][0] += weight*bounds[0]
                totals[name][1] += weight*bounds[1]
            rows = legality[sid]['rows']
            end = max((F(r['end_ms']) for r in rows), default=F(0))
            durations.append({'scene_id': sid, 'last_stage_end_ms': str(end),
                              'window_ms': str(instance['window_ms']),
                              'idle_tail_ms': str(F(instance['window_ms'])-end)})
            for segment in legality[sid]['segments']:
                start, stop = F(segment['start_ms']), F(segment['end_ms'])
                if not F(0) <= start <= stop <= F(instance['window_ms']):
                    raise ValueError('invalid archived segment')
                powers = {
                    'baseline': sum(map(F, segment['baseline_by_node_W'].values()), F(0)),
                    'activity': sum(map(F, segment['activity_by_node_W'].values()), F(0)),
                    'external_common': F(segment['external_common_power_W'])}
                lengths = {'execution': max(F(0), min(stop, end)-start),
                           'tail': max(F(0), stop-max(start, end))}
                for part, duration_ms in lengths.items():
                    for key, power in powers.items():
                        split[part][key] += weight*power*duration_ms/1000
        consistency = {key: totals[key][0] <= split['execution'][key]+split['tail'][key] <= totals[key][1]
                       for key in ('baseline', 'activity', 'external_common')}
        if not all(consistency.values()):
            raise ValueError('archived constant energy does not match saved segments')
        return {'available': True,
                'weighted_components_J': {k: [str(a), str(b)] for k, (a, b) in totals.items()},
                'weighted_constant_terms_by_period_J': {
                    period: {k: str(v) for k, v in values.items()} for period, values in split.items()},
                'period_definition': 'execution=[0,last Stage end), tail=[last Stage end,W]',
                'scene_durations': durations, 'constant_component_consistency': consistency,
                'execution_total_energy_J': None, 'tail_total_energy_J': None,
                'temperature_correction_split_available': False,
                'missing_interface': 'receipt stores whole-window temperature integrals, not per-segment integrals'}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        return {'available': False, 'reason': str(error)}


def call_row(job, call, result, instance, folder, stopped, expected_input_sha256=None):
    if call is None:
        state = ('RESULT_SAVED_AWAITING_CONTROLLER' if result is not None else
                 'IN_PROGRESS_OR_INTERRUPTED' if (folder.parent/(job['call_id']+'.claim.json')).is_file() else
                 'NOT_RUN_AFTER_STOP' if stopped else 'PENDING')
    else:
        state = 'COMPLETED' if call.get('returncode') == 0 else 'WORKER_FAILED'
        if not (call.get('technical_check') or {}).get('passed'):
            state = 'TECHNICAL_CHECK_FAILED'
        elif result is None:
            state = 'ARCHIVE_RESULT_MISSING'
    raw_result = result or {}
    preserved = preserved_safe_evidence(raw_result, instance, job, expected_input_sha256)
    result = raw_result if state == 'COMPLETED' else {}
    seconds = job['seconds']
    receipt = result.get('evaluation') or {}
    safe = bool(state == 'COMPLETED' and result.get('state') == 'SAFE'
                and safe_receipt(receipt, seconds)
                and number(result.get('safe_upper_bound_J')) is not None
                and F(result['safe_upper_bound_J']) == F(receipt['safe_upper_bound_J']))
    upper = F(result['safe_upper_bound_J']) if safe else None
    lower = number(result.get('certified_lower_bound_J')) if state == 'COMPLETED' else None
    loexact = F(str(result['certified_lower_bound_J'])) if lower is not None else None
    records = archived_safe_records(result, seconds) if state == 'COMPLETED' else []
    firstsafe = min_nonmissing([number(r['evaluation']['completed_at_elapsed_s']) for r in records]) if safe else None
    diag = result.get('diagnostic') or {}
    reported = solver_records(result, seconds) if state == 'COMPLETED' else []
    validreport = [r for r in reported if r['received_in_budget']]
    bounds = [r for r in validreport if r.get('lowerbound_J') is not None]
    latest = bounds[-1] if bounds else {}
    latestgap = [r for r in validreport if r.get('relativegap_native') is not None]
    integer = result.get('integer_solver_entered')
    if integer is None and job['method'] in ('milp', 'assignment'):
        integer = bool(number(diag.get('solver_entered_received_s')) is not None or
                       any(r.get('intlinprog_entered') for r in result.get('rounds') or []))
    initial = (result.get('initialisation') or {}).get('witness')
    initial_legal_times = [number(attempt.get('schedule_completed_at_s'))
        for attempt in (result.get('initialisation') or {}).get('attempts', [])
        if attempt.get('status') == 'COMPLETE_LEGAL_CANDIDATE'
        and number(attempt.get('schedule_completed_at_s')) is not None
        and 0 <= number(attempt.get('schedule_completed_at_s')) < seconds]
    method_legal = min_nonmissing(initial_legal_times + [number(
        result.get('first_legal_candidate_at_s', diag.get('first_legal_candidate_s')))])
    initialenergy = interval((initial or {}).get('evaluation', {}).get('weighted_energy_J'))
    milpreceipts = [r for r in records if r['source'] != 'initial_constructor']
    improved = bool(initialenergy and any(F(r['evaluation']['safe_upper_bound_J']) < initialenergy[0]
                                         for r in milpreceipts))
    # Correct the duplicate retained-final label before inferring improvement:
    # it may be the initial constructor with the same energy, which cannot pass
    # the strict non-overlap condition above.
    gap = (upper-loexact)/upper if upper is not None and upper > 0 and loexact is not None else None
    anomaly = gap is not None and gap < 0
    feedback = result.get('feedback') or []
    timing = result.get('timing') or {}
    archived_evaluations = [r.get('evaluation') or {} for r in
        list(result.get('evaluations') or [])+list(diag.get('evaluations') or [])
        +list((result.get('initialisation') or {}).get('attempts') or [])]
    raw_violations = list(result.get('violations') or []) + list(receipt.get('violations') or [])
    for item in archived_evaluations:
        raw_violations.extend(item.get('violations') or [])
    violation_keys = {json.dumps(v, ensure_ascii=False, sort_keys=True)
        for v in raw_violations if number(v.get('formed_at_elapsed_s')) is not None
        and 0 <= number(v['formed_at_elapsed_s']) < seconds}
    return {
        'call_id': job['call_id'], 'problem_id': job['problem_id'],
        'condition': job['problem_id'].rsplit('__', 1)[0],
        'sample': job['problem_id'].rsplit('__', 1)[-1],
        'method': job['method'], 'seed': job['seed'], 'call_state': state,
        'worker_returncode': call.get('returncode') if call else None,
        'controller_technical_check_passed': (call.get('technical_check') or {}).get('passed') if call else None,
        'result_state': raw_result.get('state'), 'reason': raw_result.get('reason'), 'safe': safe,
        'audit_preserved_safe_evidence': preserved,
        'U_J': rat(upper), 'energy_interval_J': receipt.get('weighted_energy_J') if safe else None,
        'certified_L0_J': rat(loexact), 'certified_gap_U_denominator': None if anomaly else rat(gap),
        'certified_bound_above_U_anomaly': anomaly,
        'solver_reported_lowerbound_J': latest.get('lowerbound_J'),
        'solver_reported_relativegap_native': (latestgap[-1]['relativegap_native'] if latestgap else None),
        'solver_reported_bound_above_U_anomaly': bool(upper is not None and
            latest.get('lowerbound_J') is not None and F(str(latest['lowerbound_J'])) > upper),
        'first_safe_at_s': firstsafe,
        'first_legal_at_s': method_legal,
        'first_MILP_legal_at_s': diag.get('first_legal_candidate_s'),
        'first_MILP_safe_at_s': diag.get('first_safe_receipt_s'),
        'integer_solver_entered': integer,
        'initial_U_J': result.get('initial_safe_upper_bound_J'),
        'MILP_U_J': result.get('milp_safe_upper_bound_J'),
        'strict_MILP_seed_improvement_from_receipts': improved,
        'strict_seed_improvement_reported': result.get('strict_energy_improvement_certified'),
        'safe_solution_source': result.get('safe_solution_source'),
        'accepted_safe_receipts': len(records), 'feedback_calls': len(feedback),
        'feedback_rows': sum(f.get('rows_added', 0) for f in feedback),
        'method_wall_s': timing.get('method_elapsed_s'),
        'process_wall_s': call.get('process_wall_s') if call else None,
        'cleanup_s': timing.get('cleanup_s'), 'seconds_limit': seconds,
        'phases_exclusive_s': timing.get('phases_exclusive_s', {}),
        'budget_exhausted': result.get('budget_exhausted'),
        'independently_proven_optimal': result.get('independently_proven_optimal', False),
        'independently_proven_infeasible': result.get('independently_proven_infeasible', False),
        'coverage_complete': result.get('coverage_complete', False),
        'input_sha256': result.get('input_sha256'),
        'thermal_violation_witnesses': len(violation_keys),
        'thermal_violation_count_scope': 'distinct archived in-budget witness records, not configurations',
        'thermal_unresolved_receipts': sum(r.get('state') == 'UNRESOLVED' for r in archived_evaluations),
        'saved_energy_parts': energy_parts(result, instance) if safe else None,
        'solver_reported_records': reported,
        'safe_timeline': [{'at_s': r['evaluation']['completed_at_elapsed_s'],
                           'U_J': r['evaluation']['safe_upper_bound_J'], 'source': r['source']}
                          for r in records],
        'L0_formed_at_s': result.get('lower_bound_formed_at_s',
            (result.get('independent_lower_bound') or {}).get('formed_at_s')),
    }


def aggregate(rows):
    """No best-of-five selection or failure-energy imputation."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['condition'], row['method']].append(row)
    rates = []
    for (condition, method), values in grouped.items():
        done = [r for r in values if r['call_state'] == 'COMPLETED']
        safe = [r for r in done if r['safe']]
        rates.append({'condition': condition, 'method': method, 'expected_calls': len(values),
                      'completed_calls': len(done), 'safe_calls': len(safe),
                      'safe_fraction_of_expected': len(safe)/len(values),
                      'safe_fraction_of_completed': len(safe)/len(done) if done else None,
                      'rate_is_final': len(done) == len(values),
                      'expected_problems': len({r['problem_id'] for r in values}),
                      'problems_with_any_safe_call': len({r['problem_id'] for r in safe}),
                      'problems_with_all_declared_calls_safe': sum(
                          all(r['safe'] for r in values if r['problem_id'] == problem)
                          for problem in {r['problem_id'] for r in values}),
                      'denominator_note': 'SA calls are seeds of the same problems, not new workloads'})
    problems = defaultdict(list)
    for row in rows:
        if row['method'] == 'sa':
            problems[row['problem_id']].append(row)
    sa = []
    for problem, values in problems.items():
        good = [r for r in values if r['safe']]
        energies = [F(r['U_J']) for r in good]
        safe_times = [r['first_safe_at_s'] for r in good if r['first_safe_at_s'] is not None]
        sa.append({'problem_id': problem, 'expected_seeds': len(values),
                   'completed_seeds': sum(r['call_state'] == 'COMPLETED' for r in values),
                   'safe_seeds': len(good), 'safe_fraction': len(good)/len(values),
                   'U_median_J': rat(median(energies)), 'U_min_J': rat(min(energies)) if energies else None,
                   'U_max_J': rat(max(energies)) if energies else None,
                   'first_safe_median_s': median(safe_times),
                   'first_safe_min_s': min(safe_times) if safe_times else None,
                   'first_safe_max_s': max(safe_times) if safe_times else None,
                   'statistics_scope': 'successful seeds only; failures retained in success count',
                   'seeds': [{'seed': r['seed'], 'call_state': r['call_state'], 'safe': r['safe'],
                              'U_J': r['U_J'], 'first_safe_at_s': r['first_safe_at_s']} for r in values]})
    byproblem = defaultdict(list)
    for row in rows:
        byproblem[row['problem_id']].append(row)
    pairs = []
    for problem, values in byproblem.items():
        heft = next((r for r in values if r['method'] == 'heft' and r['safe']), None)
        for row in values:
            record = {'problem_id': problem, 'condition': row['condition'], 'sample': row['sample'],
                      'method': row['method'], 'seed': row['seed'], 'safe': row['safe'],
                      'HEFT_safe': heft is not None, 'denominator': 'same-problem independently accepted HEFT U',
                      'ratio_U_over_HEFT_U': None, 'ratio_energy_interval': None}
            if heft and row['safe'] and F(heft['U_J']) > 0:
                record['ratio_U_over_HEFT_U'] = str(F(row['U_J'])/F(heft['U_J']))
                a, b = interval(row['energy_interval_J']), interval(heft['energy_interval_J'])
                if a and b and b[0] > 0:
                    record['ratio_energy_interval'] = [str(a[0]/b[1]), str(a[1]/b[0])]
            pairs.append(record)
    hashes = defaultdict(set)
    for row in rows:
        if row['input_sha256']:
            hashes[row['problem_id']].add(row['input_sha256'])
    return {'condition_method_success': rates, 'sa_per_problem': sa,
            'HEFT_normalized_common_success': pairs,
            'input_identity_mismatches': [k for k, v in hashes.items() if len(v) > 1]}


def analyze(folder):
    """Pure reading. The caller chooses an output directory elsewhere."""
    folder = Path(folder)
    issues = []
    declaration = load(folder/'declaration.json')
    jobs = declaration['manifest']['jobs']
    calls = read_optional(folder/'calls.json', issues) or []
    byid = {c['job']['call_id']: c for c in calls}
    stopped = (folder/'stop.json').is_file()
    rows = []
    for job in jobs:
        callpath = folder/job['call_id']
        result = read_optional(callpath/'result.json', issues)
        instance = read_optional(callpath/'input_instance.json', issues) if result is not None else None
        rows.append(call_row(job, byid.get(job['call_id']), result, instance, callpath, stopped,
                             declaration['manifest'].get('input_sha256', {}).get(job['problem_id'])))
    first_problem = declaration['manifest'].get('first_technical_case')
    first_rows = [r for r in rows if r['problem_id'] == first_problem]
    result = {'schema_version': 'chapter3-formal-archive-analysis-v1', 'input_directory': str(folder.resolve()),
              'analysis_started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'source_declaration_sha256': hashlib.sha256((folder/'declaration.json').read_bytes()).hexdigest(),
              'expected_calls': len(jobs), 'controller_finished_calls': len(calls),
              'call_states': dict(Counter(r['call_state'] for r in rows)),
              'safe_calls': sum(r['safe'] for r in rows), 'read_issues': issues,
              'audit_preserved_safe_calls': sum(r['audit_preserved_safe_evidence']['preserved'] for r in rows),
              'technical_failures_with_preserved_SAFE': sum(
                  r['call_state'] != 'COMPLETED' and r['audit_preserved_safe_evidence']['preserved'] for r in rows),
              'stop_record': read_optional(folder/'stop.json', issues),
              'first_technical_case': first_problem,
              'first_technical_case_expected_calls': len(first_rows),
              'first_technical_case_completed_calls': sum(r['call_state'] == 'COMPLETED' for r in first_rows),
              'first_technical_case_complete': bool(first_rows and all(
                  r['call_state'] == 'COMPLETED' for r in first_rows)),
              'formal_batch_complete': len(calls) == len(jobs) and all(
                  r['call_state'] == 'COMPLETED' for r in rows),
              'scope': 'archive-only; no solve, decoding, thermal propagation, candidate repair or new guarantee; incomplete batches do not support overall method ranking',
              'rows': rows, **aggregate(rows)}
    return result


def csv_write(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def save_tables(analysis, out):
    out = Path(out)
    (out/'analysis.json').write_text(json.dumps(analysis, ensure_ascii=False, indent=2,
        allow_nan=False)+'\n', encoding='utf-8')
    excluded = {'solver_reported_records', 'safe_timeline', 'saved_energy_parts', 'phases_exclusive_s'}
    csv_write(out/'calls.csv', [{k: v for k, v in r.items() if k not in excluded} for r in analysis['rows']])
    for key in ('condition_method_success', 'sa_per_problem', 'HEFT_normalized_common_success'):
        csv_write(out/(key+'.csv'), analysis[key])
    timelines, phases, parts = [], [], []
    for row in analysis['rows']:
        identity = {k: row[k] for k in ('call_id', 'problem_id', 'method', 'seed')}
        for event in row['safe_timeline']:
            timelines.append({**identity, **event, 'evidence': 'archived independent SAFE U'})
        for event in row['solver_reported_records']:
            timelines.append({**identity, **event, 'evidence': 'solver-reported only'})
        if row['certified_L0_J'] is not None:
            timelines.append({**identity, 'at_s': row['L0_formed_at_s'],
                              'L0_J': row['certified_L0_J'], 'evidence': 'independent algebraic L0'})
        phases.extend({**identity, 'phase': name, 'exclusive_seconds': value}
                      for name, value in row['phases_exclusive_s'].items())
        if row['saved_energy_parts']:
            parts.append({**identity, **row['saved_energy_parts']})
    csv_write(out/'timeline.csv', timelines)
    csv_write(out/'timing_phases.csv', phases)
    csv_write(out/'energy_components.csv', parts)
    audit_rows = [{k: row[k] for k in ('call_id', 'method', 'seed', 'call_state', 'worker_returncode')}
                  | row['audit_preserved_safe_evidence'] for row in analysis['rows']
                  if row['audit_preserved_safe_evidence']['preserved']]
    csv_write(out/'preserved_SAFE_audit.csv', audit_rows)
    lines = ['# 正式调用档案汇总', '',
        f"- 预定{analysis['expected_calls']}次；控制器已接收{analysis['controller_finished_calls']}次。",
        f"- 控制器正常通过且有SAFE：{analysis['safe_calls']}次。",
        f"- 档案一致性核对保留SAFE：{analysis['audit_preserved_safe_calls']}次，其中技术失败调用{analysis['technical_failures_with_preserved_SAFE']}次；后者不计入正式成功或SA能量统计。",
        f"- 首例技术配对：{analysis['first_technical_case_completed_calls']}/{analysis['first_technical_case_expected_calls']}正常通过，完整={analysis['first_technical_case_complete']}。",
        f"- 状态计数：`{json.dumps(analysis['call_states'], ensure_ascii=False)}`。", '']
    if not analysis['formal_batch_complete']:
        lines.extend(['**批次不完整：只描述已经形成的调用证据，不作15问题总体算法排名。**',
                      'SA五种子未齐时，中位数与范围只描述已成功的种子；未启动和技术失败均单列，不填零、不改成不可行。', ''])
    lines.extend(['认证差距采用 `(U-L0)/U`；solver-reported内部界／原生gap另列，异常不截断。',
                  '归一化分母为同问题已接受HEFT的U，只保留共同SAFE。保留失败调用的SAFE属于档案审计，不修复控制器状态或新增热证明。',
                  '当前回执缺分段温度积分，执行期／尾段总能耗不可拆；三项常数功耗的拆分及全窗组成另存CSV。', ''])
    (out/'summary.md').write_text('\n'.join(lines), encoding='utf-8')


def plots(analysis, out):
    """Small aggregate figures only; all detailed trajectories remain in CSV."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out = Path(out)
    colors = dict(milp='#1f77b4', heft='#7f7f7f', sa='#d95f02', assignment='#2ca02c')
    conditions = list(dict.fromkeys(r['condition'] for r in analysis['rows']))
    problems = list(dict.fromkeys(r['problem_id'] for r in analysis['rows']))
    normalized = analysis['HEFT_normalized_common_success']
    fig, axes = plt.subplots(1, max(1, len(conditions)), figsize=(5*len(conditions), 4), squeeze=False)
    for ax, condition in zip(axes[0], conditions):
        condproblems = [p for p in problems if p.rsplit('__', 1)[0] == condition]
        for method in METHODS:
            xs, ys, low, high = [], [], [], []
            for i, problem in enumerate(condproblems):
                values = [number(r['ratio_U_over_HEFT_U']) for r in normalized
                          if r['problem_id'] == problem and r['method'] == method
                          and r['ratio_U_over_HEFT_U'] is not None]
                if values:
                    center = median(values)
                    xs.append(i); ys.append(center); low.append(center-min(values)); high.append(max(values)-center)
            if xs:
                ax.errorbar(xs, ys, yerr=(low, high), marker='o', label=method,
                            color=colors[method], capsize=3, linestyle='--' if method == 'sa' else '-')
        ax.axhline(1, linewidth=.6, color='black')
        ax.set_xticks(range(len(condproblems)), [p.rsplit('__', 1)[-1] for p in condproblems])
        ax.set(title=condition, ylabel='U / same-case HEFT U (common SAFE only)', xlabel='problem')
        handles, labels = ax.get_legend_handles_labels()
        if handles: ax.legend(handles, labels, fontsize=8)
    incomplete = '' if analysis['formal_batch_complete'] else 'INCOMPLETE BATCH: no overall ranking\n'
    fig.suptitle(incomplete+'SA: median and min-max of successful seeds; missing values omitted')
    fig.tight_layout(); fig.savefig(out/'paired_energy_HEFT_normalized.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, max(1, len(conditions)), figsize=(5*len(conditions), 4), squeeze=False)
    for ax, condition in zip(axes[0], conditions):
        condproblems = [p for p in problems if p.rsplit('__', 1)[0] == condition]
        shown = set()
        for method in METHODS:
            for i, problem in enumerate(condproblems):
                values = [r['first_safe_at_s'] for r in analysis['rows'] if r['problem_id'] == problem
                          and r['method'] == method and r['safe'] and r['first_safe_at_s'] is not None]
                if values:
                    offset = (METHODS.index(method)-1.5)*.12
                    ax.scatter([i+offset]*len(values), values, s=24, color=colors[method],
                               alpha=.65, label=method if method not in shown else None)
                    shown.add(method)
        ax.set_xticks(range(len(condproblems)), [p.rsplit('__', 1)[-1] for p in condproblems])
        ax.set(title=condition, ylabel='First accepted SAFE (s)', xlabel='problem')
        handles, labels = ax.get_legend_handles_labels()
        if handles: ax.legend(handles, labels, fontsize=8)
    fig.suptitle(incomplete+'Failures remain missing; SA seeds shown individually')
    fig.tight_layout(); fig.savefig(out/'first_SAFE.png', dpi=160); plt.close(fig)
    # One R1 example for each original condition; no cherry-picking by outcome.
    selected = [p for p in problems if p.endswith('__R1')]
    fig, axes = plt.subplots(max(1, len(selected)), 1, figsize=(9, 3.6*max(1, len(selected))), squeeze=False)
    for ax, problem in zip(axes[:, 0], selected):
        labels = set()
        for row in analysis['rows']:
            if row['problem_id'] != problem or row['call_state'] != 'COMPLETED': continue
            end = min(row['seconds_limit'], row['method_wall_s'] or row['seconds_limit'])
            events = row['safe_timeline']
            if events:
                upper = math.inf; xs, ys = [], []
                for event in events:
                    upper = min(upper, number(event['U_J']))
                    xs.append(event['at_s']); ys.append(upper)
                xs.append(end); ys.append(upper)
                key = row['method']+' SAFE U'
                ax.step(xs, ys, where='post', color=colors[row['method']],
                        alpha=.45 if row['method'] == 'sa' else .9,
                        label=key if key not in labels else None)
                labels.add(key)
            if row['certified_L0_J'] is not None:
                key = 'independent L0'
                start = row['L0_formed_at_s']
                if start is not None:
                    ax.plot([start, end], [number(row['certified_L0_J'])]*2, color='black', linestyle=':',
                            linewidth=.8, label=key if key not in labels else None)
                    labels.add(key)
            reported = [r for r in row['solver_reported_records'] if r.get('at_s') is not None
                        and r['received_in_budget'] and r.get('lowerbound_J') is not None]
            if reported:
                key = row['method']+' solver bound (uncertified)'
                ax.plot([e['at_s'] for e in reported], [e['lowerbound_J'] for e in reported],
                        color=colors[row['method']], linestyle='--', linewidth=1,
                        label=key if key not in labels else None)
                labels.add(key)
        ax.set(title=problem, xlabel='Method elapsed time (s)', ylabel='System energy (J)')
        if labels: ax.legend(fontsize=7, ncol=2)
    if incomplete: fig.suptitle(incomplete.strip())
    fig.tight_layout(); fig.savefig(out/'R1_safe_U_and_bounds.png', dpi=160); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    source, target = args.input.resolve(), args.out.resolve()
    analysis_root = Path(__file__).resolve().parent
    if (target == source or source in target.parents or analysis_root not in target.parents):
        raise ValueError('analysis output must be a new directory inside chapter3_formal_analysis')
    target.mkdir(parents=True, exist_ok=False)
    analysis = analyze(source)
    analysis['analysis_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save_tables(analysis, target)
    if args.plots: plots(analysis, target)
    print(json.dumps({k: analysis[k] for k in ('expected_calls', 'controller_finished_calls',
        'call_states', 'safe_calls', 'formal_batch_complete')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
