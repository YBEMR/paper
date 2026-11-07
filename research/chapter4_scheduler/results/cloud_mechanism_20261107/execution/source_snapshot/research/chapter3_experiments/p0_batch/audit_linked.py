from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from run_four_method_comparison import read, canonical, finite
from completion_metrics import build_completion_metrics
from execution_status import classify_execution, DEADLINE_REASONS
SECONDS = 300

def _original_aggregate_issues(receipt, candidate, declaration, condition):
    """Audit an existing aggregate and its full original-input scene receipts."""
    from scene_adapter import _receipt_hash
    errors = []
    try:
        spec, identity = declaration['scene_spec'], receipt['identity']
        seed_identity = condition['seed_receipt']['identity']
        if (receipt['state'] != 'SAFE' or receipt['rankable_energy'] is not True
                or receipt['problem_id'] != declaration['problem_id'] or receipt['safe_candidate'] != candidate
                or receipt['receipt_sha256'] != _receipt_hash(receipt)
                or receipt['legality']['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED'
                or set(receipt['scenes']) != set(spec) or set(candidate['scenes']) != set(spec)):
            errors.append('INVALID_COMPLETE_AGGREGATE')
        if (identity['full_input_sha256'] != declaration['input_sha256']
                or identity['candidate_sha256'] != canonical(candidate)
                or identity['budget'] != condition['budget_identity']
                or any(identity[k] != seed_identity[k] for k in
                       ('source_sha256', 'accuracy_sha256', 'control_policy', 'shared_deployment_sha256'))):
            errors.append('AGGREGATE_IDENTITY_MISMATCH')
        stamp = receipt['completed_at_elapsed_s']
        if not finite(stamp) or not 0 <= stamp < SECONDS:
            errors.append('AGGREGATE_OUTSIDE_BUDGET')
        low, high = map(F, receipt['weighted_energy_J'])
        if low < 0 or high < low or F(receipt['safe_upper_bound_J']) != high:
            errors.append('AGGREGATE_ENERGY_INTERVAL_INVALID')
        total_low, total_high = F(0), F(0)
        for sid, definition in spec.items():
            scene = receipt['scenes'][sid]
            physical = scene['result']
            if (scene['receipt_sha256'] != _receipt_hash(scene)
                    or scene['state'] != 'SAFE' or scene['rankable_energy'] is not True
                    or scene['identity']['candidate_sha256'] != canonical({'scenes': {sid: candidate['scenes'][sid]}})
                    or scene['identity']['full_input_sha256'] != declaration['input_sha256']
                    or scene['identity']['budget'] != condition['budget_identity']
                    or physical['state'] != 'SAFE' or physical['complete'] is not True
                    or physical['rankable_energy'] is not True):
                errors.append('INVALID_COMPLETE_SCENE:'+sid)
            window = F(definition['window_s'])
            if F(physical['covered_until_s']) != window or F(physical['trace'][-1]['time_s']) != window:
                errors.append('INCOMPLETE_WINDOW:'+sid)
            if set(physical['peaks_degC']) != set(definition['limits']):
                errors.append('MISSING_THERMAL_NODE:'+sid)
            for node, limit in definition['limits'].items():
                lower, upper = map(F, physical['peaks_degC'][node])
                if upper < lower or upper > F(limit):
                    errors.append('UNSAFE_PEAK_ENCLOSURE:'+sid+':'+node)
            lo, hi = map(F, scene['energy_J'])
            total_low += F(definition['weight'])*lo
            total_high += F(definition['weight'])*hi
        if [total_low, total_high] != [low, high]:
            errors.append('WEIGHTED_ENERGY_MISMATCH')
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        errors.append('MALFORMED_COMPLETE_AGGREGATE')
    return errors

def exact_enclosure(receipt, declaration):
    """Exact Fraction inclusion plus exact reproduction of existing 60-digit I."""
    from scene_adapter import I
    exact = [F(0), F(0)]
    replay = I(0)
    for sid, definition in declaration['scene_spec'].items():
        values = receipt['scenes'][sid]['energy_J']
        lo, hi = map(F, values)
        weight = F(definition['weight'])
        if weight < 0 or lo < 0 or hi < lo:
            return {'accepted': False, 'reason': 'INVALID_SCENE_INTERVAL_OR_WEIGHT'}
        exact[0] += weight*lo
        exact[1] += weight*hi
        replay += I(values[0], values[1])*I.rational(weight)
    lower, upper = map(F, receipt['weighted_energy_J'])
    reproduced = [F(replay.lo), F(replay.hi)]
    included = lower <= exact[0] <= exact[1] <= upper
    same_outward = [lower, upper] == reproduced
    return {'accepted': included and same_outward, 'exact_inclusion': included,
        'original_60digit_outward_endpoints_reproduced': same_outward,
        'aggregate_J': list(map(str, (lower, upper))), 'exact_weighted_J': list(map(str, exact)),
        'outward_reproduced_J': list(map(str, reproduced)),
        'lower_padding_J': str(exact[0]-lower), 'upper_padding_J': str(upper-exact[1]),
        'scope': 'same existing interval arithmetic only; no physical trajectory evaluation'}

def aggregate_issues(receipt, candidate, declaration, condition):
    issues = _original_aggregate_issues(receipt, candidate, declaration, condition)
    if 'WEIGHTED_ENERGY_MISMATCH' not in issues:
        return issues
    try:
        check = exact_enclosure(receipt, declaration)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return issues
    if check['accepted']:
        return [v for v in issues if v != 'WEIGHTED_ENERGY_MISMATCH']
    return issues

def anchor_contract_issues(job, result):
    if not isinstance(result, dict):
        return []
    errors = []
    expected = job['preeliminate_closed_anchors']
    record = result.get('linked_record_contract')
    if isinstance(record, dict):
        marker = record.get('closed_anchor_preelimination')
        if expected:
            if not isinstance(marker, dict) or marker.get('enabled') is not True or marker.get('phase_indices') != [2]:
                errors.append('ANCHOR_TOGGLE_RECORD_MISMATCH')
        elif marker is not None:
            errors.append('BASELINE_UNEXPECTED_ANCHOR_TOGGLE')
    for phase in result.get('phases') or []:
        for sid, scene in (phase.get('scenes') or {}).items():
            if scene.get('model_complete') is not True:
                continue
            summary = scene.get('model_summary') or {}
            enabled = (summary.get('formulation') or {}).get('preeliminate_closed_anchors', False)
            wanted = expected and phase.get('phase_index') == 2
            if enabled is not wanted:
                errors.append('MODEL_ANCHOR_FLAG_MISMATCH:'+sid)
            stats = (summary.get('preprocessing') or {}).get('closed_anchor_preelimination')
            if wanted and (not isinstance(stats, dict) or stats.get('complete') is not True
                    or stats.get('condition_sha256') != phase.get('condition_sha256')):
                errors.append('ANCHOR_FILTER_RECEIPT_MISSING_OR_STALE:'+sid)
            if not wanted and stats is not None:
                errors.append('ANCHOR_FILTER_OUTSIDE_SECOND_PASS:'+sid)
    return errors

def result_records(job, result, declaration, folder, *, input_valid, source_valid, errors=None):
    """Classify saved evidence. No late decoding, physical evaluation or new U."""
    from completion_metrics import build_completion_metrics
    from execution_status import classify_execution, DEADLINE_REASONS
    from matlab_bridge import cleanup_is_complete
    import run_linked_pair as inherited
    from run_neighborhood_diagnostic import technical_issues
    r = result if isinstance(result, dict) else {}
    hard = list(errors or []) + anchor_contract_issues(job, result)
    condition = r.get('condition') or {}
    identity = r.get('identity') or {}
    input_match = (input_valid is True and identity.get('full_input_sha256') == declaration['input_sha256']
                   and identity.get('config_sha256') == declaration['config_sha256'])
    if input_valid is None and not identity:
        input_match = None
    # Keep every nontransport domain/ledger/anchor check; budget-only transport
    # incompleteness is instead classified below with its causal trace.
    adapted = dict(declaration, old_opened_by_scene=declaration['first_opened_by_scene'],
                   new_opened_by_scene=declaration['linked_opened_by_job'][job['id']])
    domain_issues = inherited.transport_issues(inherited.jobs()[1], r, adapted)
    exempt = {'LATCHED_NUMERICAL_UNRESOLVED', 'REQUEST_ADMISSION_OR_CALLBACK_COVERAGE_UNRESOLVED'}
    hard.extend(v for v in domain_issues if v.get('reason') not in exempt)
    for issue in technical_issues(r):
        if issue.get('reason') != 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED':
            hard.append(issue)
    for phase in r.get('phases') or []:
        hard.extend(v for v in technical_issues({'scenes': phase.get('scenes', {})})
                    if v.get('reason') != 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED')
    cleanup_path = Path(folder)/'matlab/closed.json'
    cleanup = read(cleanup_path) if cleanup_path.is_file() else None
    isolation = ('VERIFIED' if cleanup and cleanup_is_complete(cleanup) else
                 'UNKNOWN' if r.get('matlab_worker_ready') is True else 'NOT_APPLICABLE')
    if cleanup and not cleanup_is_complete(cleanup):
        isolation = 'FAILED'
    safe = None
    aggregate = r.get('aggregation') or {}
    if r.get('safe_upper_bound_J') is not None:
        bad = aggregate_issues(aggregate, r.get('safe_candidate') or {}, declaration, condition)
        if not bad:
            safe = {'verified': True, 'identity_valid': input_match, 'complete': True,
                'formed_at_s': aggregate['completed_at_elapsed_s'], 'energy_upper_J': aggregate['safe_upper_bound_J']}
        else:
            hard.extend(bad)
    requests = (r.get('augmented_transport') or {}).get('requests', [])
    checks = [v for request in requests for v in request.get('numerical_checks', [])]
    numeric = any((v.get('report') or {}).get('accepted') is False for v in checks)
    ambiguous_checks = any(v.get('accepted') is False and (v.get('report') or {}).get('accepted') is not True for v in checks)
    if not numeric and ambiguous_checks:
        numeric = None
    timing = r.get('timing') or {}
    deadline = bool(r.get('budget_exhausted') is True and r.get('reason') == 'wall_time_limit'
                    and timing.get('limit_s') == SECONDS and finite(timing.get('method_elapsed_s'))
                    and timing['method_elapsed_s'] >= SECONDS)
    def complete(request):
        return (request.get('latched_unresolved') is False and request.get('within_budget') is True
            and not request.get('failure_reasons') and request.get('callback_publications_complete') is True
            and request.get('expected_callback_numbers') == request.get('checked_callback_numbers'))
    prior_complete = all(complete(v) for v in requests[:-1])
    last = {'state': 'NONE'}
    causal = deadline
    if requests and not complete(requests[-1]):
        request = requests[-1]
        pyfiles = sorted((Path(folder)/'matlab').glob('request_*.python.json'))
        python = read(pyfiles[-1]) if pyfiles else {}
        poll = python.get('publication_read') or {}
        transient = set((poll.get('transient_read_errors') or {}))
        reasons = request.get('failure_reasons')
        causal = bool(deadline and request.get('cancel_requested') is True
            and request.get('cancel_published_at_s') == SECONDS
            and request.get('native_status') == 'BUDGET_EXHAUSTED'
            and request.get('within_budget') is False
            and python.get('status') == 'BUDGET_EXHAUSTED'
            and python.get('response_may_arrive_later') is True
            and python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == []
            and transient <= {'FileNotFoundError'} and isinstance(reasons, list) and bool(reasons)
            and set(reasons) <= DEADLINE_REASONS)
        last = {'state': 'PENDING', 'pending_at_cutoff': causal,
            'refuses_late_candidate': causal, 'deadline_causal_trace': causal,
            'deadline_reasons': reasons}
    elif requests:
        last = {'state': 'COMPLETE'}
    if not requests and (r.get('augmented_transport') or {}).get('latched_unresolved') is True:
        hard.append('UNEXPLAINED_TRANSPORT_LATCH_WITHOUT_REQUEST')
    context = {'input_identity_valid': input_match, 'source_identity_valid': source_valid,
        'current_request_identity_valid': input_match, 'cutoff_s': SECONDS,
        'hard_errors': hard, 'observed_numerical_rejection': numeric,
        'numerical_checks': checks, 'worker_isolation': isolation,
        'prior_requests_complete': prior_complete, 'completion_verified': not deadline
            and not r.get('search_failure_latched') and bool(r.get('reason') == 'SCENE_SEARCH_SEQUENCE_COMPLETE'),
        'root_deadline_confirmed': deadline, 'deadline_causal_trace': causal,
        'last_request': last, 'safe_receipt': safe, 'thermal_unresolved': False}
    execution = classify_execution(result, context)
    return {'execution': execution, 'usable_U_J': execution['usable_U_J'], 'context': context,
        'completion_metrics': build_completion_metrics(r, uses_matlab=True, seconds=SECONDS),
        'cleanup': cleanup, 'raw_reported_U_J': r.get('safe_upper_bound_J'),
        'phase_quality': inherited.phase_quality(r), 'domain_issues': domain_issues,
        'scope': 'stored evidence only; independent physical recheck is separately archived'}
