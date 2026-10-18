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
TERMINAL_STATES = ('COMPLETED', 'TECHNICAL_CHECK_FAILED', 'WORKER_FAILED', 'ARCHIVE_RESULT_MISSING')
INVOKED_STATES = TERMINAL_STATES+('RESULT_SAVED_AWAITING_CONTROLLER', 'IN_PROGRESS_OR_INTERRUPTED')


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
                      'completed_calls_definition': 'controller technical acceptance passed, not merely invoked',
                      'invoked_calls': sum(r['call_state'] in INVOKED_STATES for r in values),
                      'terminal_calls': sum(r['call_state'] in TERMINAL_STATES for r in values),
                      'batch_execution_finished': all(r['call_state'] in TERMINAL_STATES for r in values),
                      'technical_acceptance_complete': len(done) == len(values),
                      'safe_fraction_of_expected': len(safe)/len(values),
                      'safe_fraction_of_completed': len(safe)/len(done) if done else None,
                      'rate_is_final': all(r['call_state'] in TERMINAL_STATES for r in values),
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
                   'completed_seeds_definition': 'controller technical acceptance passed',
                   'invoked_seeds': sum(r['call_state'] in INVOKED_STATES for r in values),
                   'terminal_seeds': sum(r['call_state'] in TERMINAL_STATES for r in values),
                   'execution_finished': all(r['call_state'] in TERMINAL_STATES for r in values),
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


def _analyze_one(folder):
    """Pure reading. The caller chooses an output directory elsewhere."""
    folder = Path(folder)
    issues = []
    declaration = load(folder/'declaration.json')
    jobs = declaration['manifest']['jobs']
    calls = read_optional(folder/'calls.json', issues) or []
    declared = _unique_jobs(jobs, 'batch manifest')
    called = _unique_jobs([c['job'] for c in calls], 'controller calls')
    if any(declared.get(k) != v for k, v in called.items()):
        raise ValueError('controller call is not identical to its declared job')
    byid = {c['job']['call_id']: c for c in calls}
    stopped = (folder/'stop.json').is_file()
    rows = []
    for job in jobs:
        callpath = folder/job['call_id']
        result = read_optional(callpath/'result.json', issues)
        instance = read_optional(callpath/'input_instance.json', issues) if result is not None else None
        rows.append(call_row(job, byid.get(job['call_id']), result, instance, callpath, stopped,
                             declaration['manifest'].get('input_sha256', {}).get(job['problem_id'])))
        rows[-1].update(source_batch=str(folder.resolve()),
                        source_declaration_sha256=hashlib.sha256((folder/'declaration.json').read_bytes()).hexdigest(),
                        source_version_fingerprint=canonical_hash(declaration.get('source_sha256', {})))
    first_problem = declaration['manifest'].get('first_technical_case')
    first_rows = [r for r in rows if r['problem_id'] == first_problem]
    result = {'schema_version': 'chapter3-formal-archive-analysis-v1', 'input_directory': str(folder.resolve()),
              'analysis_started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'source_declaration_sha256': hashlib.sha256((folder/'declaration.json').read_bytes()).hexdigest(),
              'expected_calls': len(jobs), 'controller_finished_calls': len(calls),
              'call_states': dict(Counter(r['call_state'] for r in rows)),
              'technical_passed_calls': sum(r['call_state'] == 'COMPLETED' for r in rows),
              'technical_failed_calls': sum(r['call_state'] in ('TECHNICAL_CHECK_FAILED', 'WORKER_FAILED') for r in rows),
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
              'all_declared_calls_terminated': len(calls) == len(jobs) and all(
                  r['call_state'] in TERMINAL_STATES for r in rows),
              'scope': 'archive-only; no solve, decoding, thermal propagation, candidate repair or new guarantee; incomplete batches do not support overall method ranking',
              'rows': rows, **aggregate(rows)}
    return result


def _unique_jobs(jobs, label):
    byid = {job['call_id']: job for job in jobs}
    if len(byid) != len(jobs):
        raise ValueError(label+' contains duplicate call IDs')
    return byid


def _merge_manifest_checks(prior_declaration, continuation_declaration, claimed_jobs, prior_calls):
    """Exact 115-item original domain; continuation only replaces unstarted rows."""
    original = prior_declaration['manifest']
    current = continuation_declaration['manifest']
    oldjobs = _unique_jobs(original['jobs'], 'original manifest')
    newjobs = _unique_jobs(current['jobs'], 'continuation manifest')
    claims = _unique_jobs(claimed_jobs, 'prior claims')
    oldcalls = _unique_jobs([c['job'] for c in prior_calls], 'prior calls')
    if len(oldjobs) != 115 or len({j['problem_id'] for j in oldjobs.values()}) != 15:
        raise ValueError('prior manifest must be the original 15 problems and 115 calls')
    if len(claims) != 5 or len(newjobs) != 110:
        raise ValueError('continuation must exclude exactly the five prior claimed calls')
    if set(claims) != set(oldcalls):
        raise ValueError('prior claims/calls differ; continuation scope is not established')
    if any(oldjobs.get(k) != v for k, v in claims.items()) or any(claims.get(k) != v for k, v in oldcalls.items()):
        raise ValueError('prior claim/call job changed from the original declaration')
    expected_remaining = [j for j in original['jobs'] if j['call_id'] not in claims]
    if current['jobs'] != expected_remaining:
        raise ValueError('continuation is not exactly the ordered original unstarted jobs')
    if set(newjobs) & set(claims) or set(newjobs) | set(claims) != set(oldjobs):
        raise ValueError('duplicate or missing original call in merged coverage')
    if original.get('input_sha256') != current.get('input_sha256'):
        raise ValueError('continuation derived-input identities differ')
    if any(j['seconds'] != 300 for j in oldjobs.values()):
        raise ValueError('original method budget differs from 300 seconds')
    return {'passed': True, 'original_problems': 15, 'original_calls': 115,
            'prior_claimed_calls': 5, 'continuation_calls': 110,
            'no_duplicate_calls': True, 'ordered_exact_unstarted_subset': True,
            'problem_input_hashes_equal': True, 'seconds_per_call': 300,
            'original_call_ids': list(oldjobs), 'prior_claimed_call_ids': list(claims)}


def analyze(folder, prior_input=None):
    """Analyze one batch, or explicitly join the approved original/continuation."""
    if prior_input is None:
        return _analyze_one(folder)
    return _analyze_continuation(folder, prior_input)


def _join_analyses(original, continuation, coverage):
    """Keep every started old call, including failure, immutable in the union."""
    original_ids = coverage['original_call_ids']
    prior_started = set(coverage['prior_claimed_call_ids'])
    oldrows = {r['call_id']: r for r in original['rows']}
    newrows = {r['call_id']: r for r in continuation['rows']}
    rows = [oldrows[k] if k in prior_started else newrows[k] for k in original_ids]
    first_problem = original['first_technical_case']
    first_rows = [r for r in rows if r['problem_id'] == first_problem]
    finished = original['controller_finished_calls']+continuation['controller_finished_calls']
    combined = {
        'schema_version': 'chapter3-formal-archive-analysis-v2-continuation',
        'input_directory': continuation['input_directory'],
        'prior_input_directory': original['input_directory'],
        'analysis_started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'source_declaration_sha256': continuation['source_declaration_sha256'],
        'prior_source_declaration_sha256': original['source_declaration_sha256'],
        'expected_calls': 115, 'controller_finished_calls': finished,
        'call_states': dict(Counter(r['call_state'] for r in rows)),
        'technical_passed_calls': sum(r['call_state'] == 'COMPLETED' for r in rows),
        'technical_failed_calls': sum(r['call_state'] in ('TECHNICAL_CHECK_FAILED', 'WORKER_FAILED') for r in rows),
        'safe_calls': sum(r['safe'] for r in rows),
        'audit_preserved_safe_calls': sum(r['audit_preserved_safe_evidence']['preserved'] for r in rows),
        'technical_failures_with_preserved_SAFE': sum(
            r['call_state'] != 'COMPLETED' and r['audit_preserved_safe_evidence']['preserved'] for r in rows),
        'read_issues': original['read_issues']+continuation['read_issues'],
        'stop_record': continuation['stop_record'], 'prior_stop_record': original['stop_record'],
        'first_technical_case': first_problem, 'first_technical_case_expected_calls': len(first_rows),
        'first_technical_case_completed_calls': sum(r['call_state'] == 'COMPLETED' for r in first_rows),
        'first_technical_case_complete': bool(first_rows and all(
            r['call_state'] == 'COMPLETED' for r in first_rows)),
        'formal_batch_complete': finished == 115 and all(r['call_state'] == 'COMPLETED' for r in rows),
        'all_declared_calls_terminated': finished == 115 and all(
            r['call_state'] in TERMINAL_STATES for r in rows),
        'continuation_merge_checks': coverage, 'rows': rows, **aggregate(rows),
        'scope': 'explicit original+continuation archive union; original failed SA103 remains failed and audit-only; no rerun, heat evaluation or new proof',
    }
    return combined


def _continuation_provenance(folder, prior_folder, current_declaration, prior_declaration):
    """Verify declared old files and the narrowly declared source-version change."""
    folder, prior_folder = Path(folder).resolve(), Path(prior_folder).resolve()
    if folder == prior_folder:
        raise ValueError('continuation and prior input must be different directories')
    identity = current_declaration.get('prior_batch_identity')
    if not isinstance(identity, dict) or current_declaration['manifest'].get('prior_batch_identity') != identity:
        raise ValueError('continuation prior_batch_identity declaration missing or inconsistent')
    if Path(identity.get('previous_batch', '')).resolve() != prior_folder:
        raise ValueError('--prior-input does not name the declared previous batch')
    if identity.get('original_manifest_sha256') != canonical_hash(prior_declaration['manifest']):
        raise ValueError('original manifest fingerprint does not match continuation identity')
    if identity.get('source_sha256') != prior_declaration.get('source_sha256'):
        raise ValueError('prior source version differs from the continuation declaration')
    old_calls = load(prior_folder/'calls.json')
    claims = []
    required = {'declaration.json', 'calls.json', 'stop.json', 'source_integrity.json'}
    for path in prior_folder.glob('*.claim.json'):
        job = load(path)
        if path.name != job['call_id']+'.claim.json':
            raise ValueError('prior claim filename/job identity mismatch')
        claims.append(job)
        required.update((path.name, job['call_id']+'/result.json',
                         job['call_id']+'/input_instance.json', job['call_id']+'.stdout.txt'))
    fingerprints = identity.get('files_sha256')
    if not isinstance(fingerprints, dict) or not required <= set(fingerprints):
        raise ValueError('prior immutable-record hash coverage is incomplete')
    for relative, expected in fingerprints.items():
        path = (prior_folder/relative).resolve()
        if prior_folder not in path.parents or not path.is_file():
            raise ValueError('prior immutable record is missing or outside the prior directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('prior immutable record changed: '+relative)
    prior_stop = load(prior_folder/'stop.json')
    if (len(old_calls) != 5 or prior_stop.get('reason') != 'TECHNICAL_CHECK_FAILED'
        or prior_stop.get('call') != old_calls[-1]
        or not all(c.get('technical_check', {}).get('passed') is True for c in old_calls[:-1])
        or old_calls[-1].get('returncode') != 1
        or old_calls[-1].get('technical_check', {}).get('passed') is not False):
        raise ValueError('prior four accepted calls and fifth technical failure are not intact')
    if (identity.get('invoked_call_ids') != [c['job']['call_id'] for c in old_calls]
        or identity.get('technical_passed') != 4 or identity.get('technical_failed') != 1):
        raise ValueError('prior invocation/technical-status declaration differs')
    if load(prior_folder/'source_integrity.json').get('unchanged') is not True:
        raise ValueError('prior source-integrity record is not intact')
    current_manifest = current_declaration['manifest']
    if current_manifest.get('continuation_only') is not True or current_manifest.get('already_invoked') != 5:
        raise ValueError('new manifest does not explicitly declare continuation-only scope')
    coverage = _merge_manifest_checks(prior_declaration, current_declaration, claims, old_calls)
    if [c['job'] for c in old_calls] != prior_declaration['manifest']['jobs'][:5]:
        raise ValueError('prior calls are not the original five-call prefix')
    old_source, new_source = prior_declaration.get('source_sha256') or {}, current_declaration.get('source_sha256') or {}
    allowed = {'research/chapter3_experiments/run_formal_comparison.py',
               'research/chapter3_experiments/test_formal_driver.py',
               'research/chapter3_experiments/run_formal_continuation.py',
               'research/chapter3_experiments/test_formal_continuation.py'}
    changed = sorted(k for k in set(old_source) | set(new_source) if old_source.get(k) != new_source.get(k))
    declared_scope = current_declaration.get('source_version_change')
    if (not old_source or not new_source or not isinstance(declared_scope, str)
        or not declared_scope.strip() or not set(changed) <= allowed):
        raise ValueError('source version change is absent or exceeds the declared I/O continuation scope')
    return {**coverage, 'previous_batch': str(prior_folder),
            'prior_files_sha256_verified': len(fingerprints),
            'prior_source_version_fingerprint': canonical_hash(old_source),
            'continuation_source_version_fingerprint': canonical_hash(new_source),
            'source_files_changed': changed, 'declared_source_version_change': declared_scope,
            'version_scope': 'source-file boundary/declared adaptation verified; not a new algorithm-equivalence proof'}


def _analyze_continuation(folder, prior_input):
    folder, prior = Path(folder), Path(prior_input)
    current_declaration, prior_declaration = load(folder/'declaration.json'), load(prior/'declaration.json')
    coverage = _continuation_provenance(folder, prior, current_declaration, prior_declaration)
    original, continuation = _analyze_one(prior), _analyze_one(folder)
    return _join_analyses(original, continuation, coverage)


def csv_write(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def _actual_result_lines(analysis):
    """Readable final tables from the already-extracted rows, never raw search."""
    if not analysis.get('all_declared_calls_terminated'):
        return []
    rows = analysis['rows']
    sa = {s['problem_id']: s for s in analysis['sa_per_problem']}
    byproblem = defaultdict(dict)
    for row in rows:
        if row['safe'] and row['method'] != 'sa':
            byproblem[row['problem_id']][row['method']] = row
    def fmt(value, digits=6):
        return f'{float(F(value)):.{digits}f}' if value is not None else '—'
    lines = ['## 15问题的安全能量', '',
        '单位J。MILP／HEFT各一次；SA中位数与范围仅用正式SAFE种子，不取最佳种子替代SA。', '',
        '| 问题 | MILP U | HEFT U | SA中位数 [最小, 最大] | SA/HEFT中位数 [最小, 最大] | SA正式SAFE种子 |',
        '|---|---:|---:|---:|---:|---:|']
    comparisons = []
    for problem in dict.fromkeys(r['problem_id'] for r in rows):
        d, s = byproblem[problem], sa.get(problem) or {}
        med, low, high = s.get('U_median_J'), s.get('U_min_J'), s.get('U_max_J')
        heft = (d.get('heft') or {}).get('U_J')
        ratios = ([F(x)/F(heft) for x in (med, low, high)]
                  if heft is not None and F(heft) > 0 and all(x is not None for x in (med, low, high)) else None)
        normalized = ('{} [{}, {}]'.format(*(fmt(x, 4) for x in ratios)) if ratios else '—')
        lines.append(f"| {problem} | {fmt((d.get('milp') or {}).get('U_J'))} | {fmt(heft)} | "
            f"{fmt(med)} [{fmt(low)}, {fmt(high)}] | {normalized} | "
            f"{s.get('safe_seeds', 0)}/{s.get('expected_seeds', 0)} |")
        if ratios:
            comparisons.append((problem, ratios))
    lines.extend(['', '## 首个安全输出时间', '',
        '单位秒；每格为该条件内各独立调用的最小—最大值，包含本次输入、构造和启动；不是统计置信区间。', '',
        '| 条件 | MILP | HEFT | SA正式种子 | 完整赋值删除消融 |', '|---|---:|---:|---:|---:|'])
    for condition in dict.fromkeys(r['condition'] for r in rows):
        values = []
        for method in METHODS:
            times = [r['first_safe_at_s'] for r in rows if r['condition'] == condition
                     and r['method'] == method and r['safe'] and r['first_safe_at_s'] is not None]
            values.append(f'{min(times):.3f}—{max(times):.3f}' if times else '—')
        lines.append('| '+condition+' | '+' | '.join(values)+' |')
    milp = [r for r in rows if r['method'] == 'milp' and r['call_state'] == 'COMPLETED']
    assignment = [r for r in rows if r['method'] == 'assignment' and r['call_state'] == 'COMPLETED']
    same_seed = sum(r['U_J'] is not None and r['initial_U_J'] is not None
                    and F(r['U_J']) == F(r['initial_U_J']) for r in milp)
    post = sum(r['MILP_U_J'] is not None for r in milp)
    strict = sum(r['strict_MILP_seed_improvement_from_receipts'] for r in milp)
    lower = sum(values[0] < 1 for _, values in comparisons)
    worse = [(problem, values) for problem, values in comparisons if values[0] > 1]
    feedback_calls = sum(r['feedback_calls'] for r in milp+assignment)
    feedback_rows = sum(r['feedback_rows'] for r in milp+assignment)
    witness_by_method = {m: sum(r['thermal_violation_witnesses'] for r in rows if r['method'] == m)
                         for m in ('heft', 'sa')}
    gaps = [F(r['certified_gap_U_denominator']) for r in rows
            if r['safe'] and r['certified_gap_U_denominator'] is not None]
    lines.extend(['', '## 本次结果的解释', '',
        f"1. {len(milp)}次MILP中{same_seed}次最终U等于本次构造种子；{post}次另有后续MILP安全回执，{strict}次严格改善。{len(assignment)}次消融的结果单列。安全输出可由初始化取得，不能记成MILP优化收益。",
        f"2. SA中位数在{len(comparisons)}个共同成功问题中的{lower}个低于HEFT。"+
        ('；'.join(f'{p}中位数为HEFT的{float(v[0]):.4f}倍，种子范围{float(v[1]):.4f}—{float(v[2]):.4f}倍'
                  for p, v in worse) if worse else '本组未观察到SA中位数更高的问题')+
        '。这是本次声明输入和预算下的观察，不构成普遍优势。',
        f"3. HEFT／SA历史严格违规见证分别{witness_by_method['heft']}／{witness_by_method['sa']}条，属于候选热筛查；MILP与消融实际反馈共{feedback_calls}次、{feedback_rows}行，不能用前者证明后者的收益。",
        f"4. 独立已证最优{sum(r['independently_proven_optimal'] for r in rows)}项、独立已证无解{sum(r['independently_proven_infeasible'] for r in rows)}项。"+
        (f'正式SAFE的共同L0差距上界范围{float(min(gaps)):.2%}—{float(max(gaps)):.2%}，均未闭合。' if gaps else '')+
        '内部界高于U异常与认证界高于U异常分别为'+
        f"{sum(r['solver_reported_bound_above_U_anomaly'] for r in rows)}／{sum(r['certified_bound_above_U_anomaly'] for r in rows)}项。",
        '5. 各条件只在相同输入内比较方法。response_R与base的直接能量差还包含响应模型变化，不是同一实测系统中的节能率；入口配对只支持约束作用，不证明全局最优变化或反馈收益。',
        '6. 全部结论限定于本次抽象L3输入、有限启动集合与单次确定性／五种子记录；未追加参数、预算或案例。执行期／尾段总能耗因缺分段温度积分仍不可拆分。', ''])
    reported_bad = [r['problem_id'] for r in milp if r['reason'] == 'SOLVER_REPORTED_INFEASIBLE' and r['safe']]
    if reported_bad:
        lines.append('求解器状态限制：'+', '.join(reported_bad)+
            '出现solver-reported无解，同时本次独立SAFE种子仍在；仅保留工程内部状态，不解释为数学不可行。')
    return lines


def candidate_receipt_counts(result, method, seconds):
    """Count archived evaluations and their exact reasons, not new outcomes."""
    diagnostic = result.get('diagnostic') or {}
    if method in ('heft', 'sa'):
        records = result.get('evaluations') or []
    else:
        records = list((result.get('initialisation') or {}).get('attempts') or [])+list(
            diagnostic.get('evaluations') or [])
    states, unresolved, nonbudget = Counter(), Counter(), Counter()
    numeric_errors = violation_records = valid_witnesses = 0
    for record in records:
        receipt = record.get('evaluation')
        if not isinstance(receipt, dict): continue
        state, reason = receipt.get('state'), receipt.get('reason')
        states[str(state)] += 1
        if state == 'UNRESOLVED':
            unresolved[str(reason)] += 1
            if not receipt.get('budget_exhausted') and reason not in (
                    'wall_time_limit', 'panel_limit', 'peak_refinement_limit'):
                nonbudget[str(reason)] += 1
        if (receipt.get('error_type') is not None or reason in ('NUMERICAL_ERROR', 'INTERNAL_CONSISTENCY_ERROR')
            or any(sc.get('error_type') is not None or sc.get('reason') in (
                'NUMERICAL_ERROR', 'INTERNAL_CONSISTENCY_ERROR') for sc in (receipt.get('scenes') or {}).values())):
            numeric_errors += 1
        witnesses = []
        for witness in receipt.get('violations') or []:
            bounds, at = interval(witness.get('temperature_degC')), number(witness.get('formed_at_elapsed_s'))
            limit = number(witness.get('limit_degC'))
            if (bounds and limit is not None and bounds[0] > F(str(witness['limit_degC']))
                and at is not None and 0 <= at < seconds):
                witnesses.append(witness)
        if witnesses:
            violation_records += 1
            valid_witnesses += len(witnesses)
    return {'evaluation_state_counts': dict(states), 'unresolved_reason_counts': dict(unresolved),
            'nonbudget_unresolved_reason_counts': dict(nonbudget),
            'numerical_error_receipts': numeric_errors,
            'strict_violation_evaluation_records': violation_records,
            'strict_violation_point_witnesses': valid_witnesses}


def audit_candidate_receipt_states(analysis):
    rows = []
    for call in analysis['rows']:
        if call['call_state'] not in TERMINAL_STATES: continue
        path = Path(call['source_batch'])/call['call_id']/'result.json'
        if not path.is_file(): continue
        result = load(path)
        rows.append({'call_id': call['call_id'], 'method': call['method'], 'condition': call['condition'],
            'tier': 'official_technical_pass' if call['call_state'] == 'COMPLETED' else 'technical_failure_audit_only',
            **candidate_receipt_counts(result, call['method'], call['seconds_limit'])})
    tiers = {}
    for tier in dict.fromkeys(row['tier'] for row in rows):
        subset = [row for row in rows if row['tier'] == tier]
        combined = {'calls': len(subset)}
        for field in ('evaluation_state_counts', 'unresolved_reason_counts', 'nonbudget_unresolved_reason_counts'):
            totals = Counter()
            for row in subset: totals.update(row[field])
            combined[field] = dict(totals)
        for field in ('numerical_error_receipts', 'strict_violation_evaluation_records', 'strict_violation_point_witnesses'):
            combined[field] = sum(row[field] for row in subset)
        tiers[tier] = combined
    return {'scope': 'read-only evaluation-record counts/reasons; cached or unvisited candidates are not new evaluations',
            'tiers': tiers, 'rows': rows}


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
    if analysis.get('candidate_receipt_state_audit') is not None:
        (out/'candidate_receipt_state_audit.json').write_text(json.dumps(
            analysis['candidate_receipt_state_audit'], ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    if analysis.get('entry_temperature_pair_audit') is not None:
        audit = analysis['entry_temperature_pair_audit']
        (out/'entry_temperature_pair_audit.json').write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        evidence = []
        for pair in audit['pairs']:
            for candidate in pair['matched_candidates']:
                for witness in candidate['hot_strict_witnesses']:
                    evidence.append({'sample': pair['sample'], 'candidate_sha256': candidate['candidate_sha256'],
                        'cold_call_id': pair['cold_call_id'], 'hot_call_id': pair['hot_call_id'],
                        'cold_evaluation_index': candidate['cold_evaluation_index'],
                        'cold_SAFE_formed_at_s': candidate['cold_SAFE_formed_at_s'],
                        'nonentry_input_sha256': pair['input_checks']['nonentry_input_sha256'], **witness})
        csv_write(out/'entry_temperature_pair_witnesses.csv', evidence)
    lines = ['# 正式调用档案汇总', '',
        f"- 预定{analysis['expected_calls']}次；控制器已接收{analysis['controller_finished_calls']}次。",
        f"- 全部原调用已执行结束={analysis.get('all_declared_calls_terminated', False)}；技术通过{analysis['technical_passed_calls']}/{analysis['expected_calls']}，技术失败{analysis['technical_failed_calls']}次。",
        f"- 控制器正常通过且有SAFE：{analysis['safe_calls']}次。",
        f"- 档案一致性核对保留SAFE：{analysis['audit_preserved_safe_calls']}次，其中技术失败调用{analysis['technical_failures_with_preserved_SAFE']}次；后者不计入正式成功或SA能量统计。",
        f"- 首例技术配对：{analysis['first_technical_case_completed_calls']}/{analysis['first_technical_case_expected_calls']}正常通过，完整={analysis['first_technical_case_complete']}。",
        f"- 状态计数：`{json.dumps(analysis['call_states'], ensure_ascii=False)}`。", '']
    first_sa = next((r for r in analysis['sa_per_problem'] if r['problem_id'] == 'base__R1'), None)
    failed103 = next((r for r in analysis['rows'] if r['problem_id'] == 'base__R1'
                     and r['method'] == 'sa' and r['seed'] == 103
                     and r['call_state'] == 'TECHNICAL_CHECK_FAILED'), None)
    if first_sa is not None:
        lines.append(f"base R1正式SA样本：技术通过{first_sa['completed_seeds']}/{first_sa['expected_seeds']}个种子，其中SAFE {first_sa['safe_seeds']}个；中位数只由这些正式SAFE种子计算。")
    if failed103 is not None:
        lines.append('原SA103继续为技术失败；其已存SAFE只作审计，不补入正式SA样本或五种子统计。')
    lines.append('')
    lines.append('CSV中completed_calls／completed_seeds专指技术正常通过；invoked／terminal分别标记启动／终态。rate_is_final指全部已有终态，技术全部通过由technical_acceptance_complete另列；False不能单独解释为仍在运行。')
    lines.append('')
    if not analysis['formal_batch_complete']:
        lines.extend(['**尚有调用未形成终态：只描述已有证据，不作15问题总体算法排名。**'
                      if not analysis.get('all_declared_calls_terminated') else
                      '**全部调用已有终态，但技术验收并非全部通过：失败项单列，不能补记为正常成功。**',
                      'SA五种子未齐或有技术失败时，中位数与范围只描述已成功的种子；未启动和技术失败均单列，不填零、不改成不可行。', ''])
    if analysis.get('continuation_merge_checks'):
        version = analysis['continuation_merge_checks']
        lines.extend([f"合并原批次5项与续行110项，逐项覆盖原15问题／115项；无重复ID，原SA103技术失败保持。旧目录{version['prior_files_sha256_verified']}份文件哈希匹配。",
                      f"源码版本变更声明：{version['declared_source_version_change']}",
                      '逐调用保留source_batch和源码版本指纹；续行入口3项技术验收不能改写原8项验收。', ''])
    if analysis.get('entry_temperature_pair_audit') is not None:
        audit = analysis['entry_temperature_pair_audit']
        lines.extend([f"已存HEFT候选配对审计找到{audit['matched_candidate_count']}个同一候选：非入口输入相同，50°C完整SAFE，78°C有预算内严格超温点见证。匹配样本：{audit['matched_samples']}。",
                      '仅为入口热约束作用的已有证据。候选交集受到HEFT访问选择影响；不证明全局最优改变、反馈收益或算法新颖性，无匹配也不等于无热影响。', ''])
    if analysis.get('candidate_receipt_state_audit') is not None:
        for tier, counts in analysis['candidate_receipt_state_audit']['tiers'].items():
            lines.append(f"候选回执计数（{tier}，{counts['calls']}调用）：状态{counts['evaluation_state_counts']}；未分辨原因{counts['unresolved_reason_counts']}；非预算未分辨原因{counts['nonbudget_unresolved_reason_counts']}；显式数值错误回执{counts['numerical_error_receipts']}。")
        lines.extend(['这些是历史评价回执数，既不是最终失败调用数，也不是不同配置数；预算中断未分辨不改写已保留SAFE。', ''])
    lines.extend(['共同L0差距采用 `(U-L0)/U`，是有依据的最优差距上界，不是已知真实最优差距；solver-reported内部界／原生gap另列，异常不截断。',
                  'MILP初始构造器提供的安全U与后续MILP候选U分列；只有后续能量上端严格低于种子下端，才报告严格改善。',
                  '历史超温候选／点见证及入口配对属于热约束筛查证据；MILP反馈次数与新增行数只统计实际外层反馈，二者不互相代替。',
                  '归一化分母为同问题已接受HEFT的U，只保留共同SAFE。保留失败调用的SAFE属于档案审计，不修复控制器状态或新增热证明。',
                  '当前回执缺分段温度积分，执行期／尾段总能耗不可拆；三项常数功耗的拆分及全窗组成另存CSV。', ''])
    lines.extend(_actual_result_lines(analysis))
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
    incomplete = ('' if analysis['formal_batch_complete'] else
                  'TECHNICAL FAILURE RETAINED: accepted calls only\n'
                  if analysis.get('all_declared_calls_terminated') else
                  'INCOMPLETE BATCH: no overall ranking\n')
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
                        color=colors[row['method']], linestyle='--', linewidth=1, marker='x', markersize=5,
                        label=key if key not in labels else None)
                labels.add(key)
        ax.set(title=problem, xlabel='Method elapsed time (s)', ylabel='System energy (J)')
        if labels: ax.legend(fontsize=7, ncol=2)
    if incomplete: fig.suptitle(incomplete.strip())
    fig.tight_layout(); fig.savefig(out/'R1_safe_U_and_bounds.png', dpi=160); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--prior-input', type=Path,
                        help='explicit original stopped batch when --input names the 110-call continuation')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plots', action='store_true')
    parser.add_argument('--entry-temperature-audit', action='store_true',
                        help='pair already-saved identical HEFT candidates at 50/78degC; no thermal replay')
    parser.add_argument('--receipt-state-audit', action='store_true',
                        help='count saved evaluator states/reasons, keeping budget and numerical uncertainty separate')
    args = parser.parse_args()
    source, target = args.input.resolve(), args.out.resolve()
    analysis_root = Path(__file__).resolve().parent
    if (target == source or source in target.parents or analysis_root not in target.parents):
        raise ValueError('analysis output must be a new directory inside chapter3_formal_analysis')
    target.mkdir(parents=True, exist_ok=False)
    analysis = analyze(source, args.prior_input)
    if args.entry_temperature_audit:
        from audit_entry_temperature import audit_pairs
        analysis['entry_temperature_pair_audit'] = audit_pairs(analysis)
        analysis['entry_audit_source_sha256'] = hashlib.sha256(
            (Path(__file__).resolve().parent/'audit_entry_temperature.py').read_bytes()).hexdigest()
    if args.receipt_state_audit:
        analysis['candidate_receipt_state_audit'] = audit_candidate_receipt_states(analysis)
    analysis['analysis_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save_tables(analysis, target)
    if args.plots: plots(analysis, target)
    print(json.dumps({k: analysis[k] for k in ('expected_calls', 'controller_finished_calls',
        'call_states', 'safe_calls', 'formal_batch_complete')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
