"""K152 stored-record audit for the full MILP invocation.

This module never decodes a vector, evaluates heat, changes an incumbent or
interprets a solver exit as a mathematical certificate.  A last native timeout
is normal only when its archived request is tied to the one root deadline.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

from completion_metrics import build_completion_metrics
from execution_status import classify_execution
from matlab_bridge import cleanup_is_complete
from run_anchor_pair import exact_enclosure
from audit_heuristic import receipt_issues
from scene_adapter import canonical_hash

SECONDS = 300
NORMAL_REASONS = frozenset({'SAFE_ENGINEERING_CONVERGENCE', 'SAFE_INCUMBENT',
    'NO_INTEGER_CANDIDATE', 'SOLVER_REPORTED_INFEASIBLE', 'OUTER_ROUND_LIMIT'})
HARD_REASONS = frozenset({'INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
    'INVALID_INPUT_OR_INTERFACE', 'INITIALISATION_ERROR',
    'INITIALISED_SOLVER_INTERFACE_ERROR'})
NUMERIC_REASONS = frozenset({'NUMERICAL_CANDIDATE_ANOMALY',
    'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED', 'NUMERICAL_ADMISSION_STATUS_CONFLICT'})


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _load(path, hard):
    if not path.is_file():
        return None
    try:
        return _read(path)
    except (OSError, ValueError, TypeError) as error:
        hard.append('UNREADABLE_ARCHIVE:'+path.name+':'+type(error).__name__)
        return None


def _diagnostics(result):
    values = [result.get('diagnostic'), (result.get('solver_diagnostic') or {}).get('diagnostic')]
    unique = []
    for value in values:
        if isinstance(value, dict) and value not in unique:
            unique.append(value)
    return unique


def _receipt_bad(evaluation, candidate, declaration):
    bad = receipt_issues(evaluation, candidate, declaration)
    try:
        if not exact_enclosure(evaluation, declaration)['accepted']:
            bad.append('WEIGHTED_ENCLOSURE_NOT_ORIGINAL_OUTWARD_SUM')
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        bad.append('MALFORMED_WEIGHTED_ENCLOSURE')
    return bad


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def result_records(result, declaration, folder, *, input_valid, source_valid, errors=None):
    """Audit existing whole-method receipts; preserve timely U on normal expiry."""
    folder = Path(folder)
    r = result if isinstance(result, dict) else {}
    hard = list(errors or [])
    reported_input = r.get('input_sha256')
    input_match = (False if input_valid is False or (reported_input is not None
        and reported_input != declaration['input_sha256']) else input_valid)
    for name, key in [('input_instance.json', 'input_sha256'), ('input_config.json', 'config_sha256')]:
        archived = _load(folder/name, hard)
        if archived is not None and canonical_hash(archived) != declaration[key]:
            input_match = False
            hard.append('ARCHIVED_INPUT_IDENTITY_MISMATCH:'+name)
    for value in _walk({k: r.get(k) for k in ('reason', 'solver_diagnostic', 'initialisation', 'rounds')}):
        if value.get('reason') in HARD_REASONS or value.get('status') in ('ERROR', 'WORKER_EXITED'):
            hard.append('METHOD_OR_REQUEST_FAILURE:'+str(value.get('reason') or value.get('status')))
        if value.get('error') or value.get('technical_state') in ('FAILED', 'TECHNICAL_FAILURE'):
            hard.append('ARCHIVED_TECHNICAL_ERROR')
    diagnostics = _diagnostics(r)
    numeric = any(v.get('reason') in NUMERIC_REASONS or v.get('state') in NUMERIC_REASONS
        or v.get('accepted_numerically') is False
        or (v.get('state') == 'REJECTED' and v.get('within_budget') is True)
        for v in _walk(r))
    safe_rows, rejected_safe_rows = [], []
    witness = (r.get('initialisation') or {}).get('witness')
    if isinstance(witness, dict):
        safe_rows.append(('initialisation.witness', witness.get('evaluation') or {}, witness.get('candidate') or {}))
    for d_index, diagnostic in enumerate(diagnostics):
        for index, row in enumerate(diagnostic.get('evaluations') or []):
            if not isinstance(row, dict):
                hard.append('MALFORMED_DIAGNOSTIC_EVALUATION')
                continue
            if row.get('accepted_safe') is True:
                candidate = row.get('candidate') or {}
                # Recorder's original identity deliberately uses its original
                # default JSON separators, rather than scene canonical_hash.
                expected = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()
                if row.get('candidate_sha256') != expected:
                    hard.append('DIAGNOSTIC_CANDIDATE_IDENTITY_MISMATCH')
                    continue
                safe_rows.append(('diagnostic'+str(d_index)+'.evaluations['+str(index)+']',
                    row.get('evaluation') or {}, candidate))
    checked = []
    for source, evaluation, candidate in safe_rows:
        bad = _receipt_bad(evaluation, candidate, declaration)
        if bad:
            hard.extend(source+':'+v for v in bad)
            rejected_safe_rows.append(source)
        else:
            checked.append((source, evaluation, candidate))
    safe = None
    filtered = deepcopy(r)
    if r.get('safe_upper_bound_J') is not None:
        evaluation, candidate = r.get('evaluation') or {}, r.get('safe_candidate') or {}
        bad = _receipt_bad(evaluation, candidate, declaration)
        if r.get('state') != 'SAFE':
            bad.append('ROOT_U_WITHOUT_SAFE_STATE')
        if not any(ev == evaluation and ca == candidate for _, ev, ca in checked):
            bad.append('FINAL_SAFE_NOT_BOUND_TO_CURRENT_CALL_ACCEPTED_RECORD')
        try:
            if F(r['safe_upper_bound_J']) != F(evaluation['safe_upper_bound_J']):
                bad.append('ROOT_U_DIFFERS_FROM_RECEIPT')
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            bad.append('MALFORMED_ROOT_U')
        if bad:
            hard.extend(bad)
            filtered['evaluation'] = None
        else:
            safe = {'verified': True, 'identity_valid': input_match, 'complete': True,
                'formed_at_s': evaluation['completed_at_elapsed_s'],
                'energy_upper_J': evaluation['safe_upper_bound_J']}
    cleanup = _load(folder/'matlab/closed.json', hard)
    isolation = ('VERIFIED' if cleanup and cleanup_is_complete(cleanup) else
        'FAILED' if cleanup else 'UNKNOWN' if r.get('matlab_worker_ready') is True else 'NOT_APPLICABLE')
    timing = r.get('timing') or {}
    elapsed = timing.get('method_elapsed_s')
    root = _load(folder/'method_budget_identity.json', hard)
    root_bound = bool(isinstance(root, dict) and root.get('clock') == 'monotonic'
        and root.get('limit_s') == SECONDS and _finite(root.get('start'))
        and _finite(root.get('deadline')) and root['deadline'] == root['start']+SECONDS)
    if not root_bound:
        hard.append('ROOT_METHOD_BUDGET_IDENTITY_NOT_BOUND')
    deadline = bool(root_bound and r.get('budget_exhausted') is True
        and r.get('reason') == 'wall_time_limit' and timing.get('limit_s') == SECONDS
        and _finite(elapsed) and elapsed >= SECONDS)
    session = _load(folder/'matlab/session.json', hard)
    if r.get('matlab_worker_ready') is True:
        if not (isinstance(session, dict) and session.get('method_deadline_bound') is True
                and root_bound and session.get('external_absolute_deadline') == root['deadline']):
            hard.append('SESSION_NOT_BOUND_TO_ROOT_DEADLINE')
    rounds = r.get('rounds') or []
    attempts = r.get('solver_request_attempts', 0)
    prior_complete = isinstance(rounds, list)
    last, causal, thermal_unknown = {'state': 'NONE'}, deadline, False
    native_audits = []
    if not isinstance(rounds, list):
        hard.append('MALFORMED_NATIVE_ROUND_LIST')
        rounds = []
    for index, returned in enumerate(rounds, 1):
        if not isinstance(returned, dict):
            hard.append('MALFORMED_NATIVE_ROUND')
            prior_complete = False
            continue
        number = returned.get('request_number')
        if type(number) is not int or number != index:
            hard.append('NATIVE_ROUND_NUMBER_MISMATCH')
            continue
        prefix = folder/'matlab'/('request_'+format(number, '06d'))
        meta = _load(prefix.with_suffix('.input.json'), hard)
        python = _load(prefix.with_suffix('.python.json'), hard)
        bound = bool(root_bound and isinstance(meta, dict) and meta.get('request_number') == number
            and meta.get('method_deadline_bound') is True and meta.get('absolute_deadline') == root['deadline'])
        exact_python = isinstance(python, dict) and python == returned
        if not bound:
            hard.append('NATIVE_REQUEST_NOT_BOUND_TO_ROOT:'+str(number))
        if not exact_python:
            hard.append('NATIVE_PYTHON_RETURN_IDENTITY_MISMATCH:'+str(number))
        complete = bool(bound and exact_python and returned.get('budget_valid') is True
            and returned.get('status') == 'SOLVED' and not returned.get('error')
            and not returned.get('numerical_consistency'))
        native_audits.append({'request_number': number, 'bound_to_root': bound,
            'python_return_matches': exact_python, 'complete': complete})
        if index < len(rounds):
            prior_complete = prior_complete and complete
            continue
        if complete:
            last = {'state': 'COMPLETE'}
            continue
        poll = (python or {}).get('publication_read') or {}
        transient = set((poll.get('transient_read_errors') or {}))
        refused = bool(deadline and bound and exact_python and prior_complete
            and returned.get('budget_valid') is False and returned.get('accepted_for_evaluation') is False
            and returned.get('x') == [])
        polling_timeout = bool(refused
            and returned.get('status') == 'BUDGET_EXHAUSTED'
            and returned.get('response_may_arrive_later') is True
            and transient <= {'FileNotFoundError'}
            and prefix.with_suffix('.cancel').is_file()
            and prefix.with_suffix('.cancel').read_text(encoding='ascii').strip() == 'budget')
        formed = returned.get('solver_response_complete_at_monotonic')
        archive_timeout = bool(refused and returned.get('status') == 'BUDGET_EXHAUSTED_BEFORE_RETURN'
            and _finite(formed) and root['start'] <= formed < root['deadline'])
        pending = polling_timeout or archive_timeout
        causal = pending
        last = {'state': 'PENDING', 'pending_at_cutoff': pending,
            'refuses_late_candidate': pending, 'deadline_causal_trace': pending,
            'deadline_reasons': (['ROOT_BUDGET_EXHAUSTED'] if polling_timeout else
                ['BUDGET_DURING_ADMISSION_ARCHIVE'] if archive_timeout else [])}
    if type(attempts) is not int or attempts != len(rounds):
        prior_complete = False
    for diagnostic in diagnostics:
        for row in diagnostic.get('evaluations') or []:
            ev = row.get('evaluation') or {}
            if ev.get('state') == 'UNRESOLVED' and ev.get('budget_exhausted') is not True:
                thermal_unknown = True
    completion = bool(not deadline and r.get('reason') in NORMAL_REASONS
        and prior_complete and last['state'] in ('NONE', 'COMPLETE'))
    context = {'input_identity_valid': input_match, 'source_identity_valid': source_valid,
        'current_request_identity_valid': input_match, 'cutoff_s': SECONDS, 'hard_errors': hard,
        'observed_numerical_rejection': numeric, 'worker_isolation': isolation,
        'prior_requests_complete': prior_complete, 'completion_verified': completion,
        'root_deadline_confirmed': deadline, 'deadline_causal_trace': causal,
        'last_request': last, 'safe_receipt': safe, 'thermal_unresolved': thermal_unknown}
    status = classify_execution(result, context)
    metrics = build_completion_metrics(filtered, uses_matlab=True, seconds=SECONDS)
    metrics['identity_valid_for_comparison'] = input_match is True and source_valid is True
    return {'execution': status, 'context': context, 'completion_metrics': metrics,
        'usable_U_J': status['usable_U_J'], 'raw_reported_U_J': r.get('safe_upper_bound_J'),
        'cleanup': cleanup, 'native_request_audit': native_audits,
        'rejected_safe_records': rejected_safe_rows,
        'scope': 'stored whole-MILP evidence only; no decode, physical replay, late acceptance or solver proof upgrade'}
