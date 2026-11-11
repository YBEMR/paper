"""Pure evidence classification for the K144 execution wrapper.

This module does not inspect files, run numerical checks or accept candidates.
The caller supplies independently checked identities and existing receipts in
``context``. Unknown fields stay unknown. A method return/solver exit flag is
never a proof of optimality or infeasibility.

Required context fields:
    input_identity_valid, source_identity_valid, current_request_identity_valid:
        True, False or None; a failed current request need not corrupt an older
        receipt whose own identity was independently verified.
    cutoff_s: positive finite root method budget.
    hard_errors: the explicitly observed error list (empty means checked).
    observed_numerical_rejection: True/False/None, based on actual reports,
        not an aggregate ``accepted=False`` that may merely reject late data.
    worker_isolation: NOT_APPLICABLE / VERIFIED / UNKNOWN / FAILED.
    prior_requests_complete, completion_verified, root_deadline_confirmed,
        deadline_causal_trace: explicit Boolean evidence, not inferred from a
        reason string or a late wall clock.
    last_request: {state: NONE/COMPLETE/PENDING/THERMAL_UNRESOLVED, ...}.
        PENDING additionally needs pending_at_cutoff, refuses_late_candidate,
        deadline_causal_trace and a nonempty known deadline_reasons list.
Optional safe_receipt is an existing complete receipt, not a new evaluation:
    verified, identity_valid, complete, formed_at_s, energy_upper_J.
    It is usable only if all identity/completeness checks pass and it formed
    strictly before the root cutoff. Local/partial/late energy is never a U.
Optional known_violation uses the same verification/time fields (no energy).
Optional numerical_checks contain existing check wrappers; only an actual
    nested report.accepted=False establishes a numerical rejection.
"""

from fractions import Fraction
import math


DEADLINE_REASONS = frozenset({
    'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED',
    'BUDGET_BEFORE_FINAL_ADMISSION',
    'BUDGET_DURING_ADMISSION_ARCHIVE',
    'ROOT_BUDGET_EXHAUSTED',
    'BUDGET_DURING_CANDIDATE_EVALUATION',
})


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _nonnegative_energy(value):
    """Keep the archived numeric representation; require a finite real value."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        return Fraction(value) >= 0
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return False


def _receipt_usable(receipt, context, *, needs_energy):
    if not isinstance(receipt, dict):
        return False
    at, cutoff = receipt.get('formed_at_s'), context.get('cutoff_s')
    return bool(
        context.get('input_identity_valid') is True
        and context.get('source_identity_valid') is True
        and receipt.get('verified') is True
        and receipt.get('identity_valid') is True
        and receipt.get('complete') is True
        and _finite_number(at) and _finite_number(cutoff)
        and 0 <= at < cutoff
        and (not needs_energy or _nonnegative_energy(receipt.get('energy_upper_J')))
    )


def classify_execution(result, context):
    """Return status and preservation decisions without changing either input.

    Classification prioritises observed faults, then actual numerical rejection,
    then missing evidence, before normal completion/deadline. Budget evidence
    can explain only an unfinished *last* request; it cannot erase an earlier
    incomplete request, identity fault, process fault or numerical rejection.
    ``archival_evidence_retained`` is not permission to rank an unsafe receipt.
    """
    supplied_context = isinstance(context, dict)
    context = context if supplied_context else {}
    raw_result_valid = isinstance(result, dict)
    result = result if raw_result_valid else {}
    safe = context.get('safe_receipt')
    safe_usable = _receipt_usable(safe, context, needs_energy=True)
    violation_usable = _receipt_usable(
        context.get('known_violation'), context, needs_energy=False)
    last = context.get('last_request')
    last = last if isinstance(last, dict) else {}
    last_state = last.get('state')
    out = {
        'schema': 'K144-execution-evidence-status-v1',
        'execution_status': 'STATUS_UNRESOLVED',
        'archival_evidence_retained': True,
        'safe_witness_preserved': safe_usable,
        'usable_U_J': safe.get('energy_upper_J') if safe_usable else None,
        'usable_safe_formed_at_s': safe.get('formed_at_s') if safe_usable else None,
        'known_violation_preserved': violation_usable,
        'last_request': last_state if last_state in ('NONE', 'COMPLETE') else 'UNRESOLVED',
        'thermal_unresolved': (context.get('thermal_unresolved') is True
                               or last_state == 'THERMAL_UNRESOLVED'),
        'new_or_late_candidate_accepted': False,
        'independently_proven_optimal': False,
        'independently_proven_infeasible': False,
        'worker_may_be_reused': False,
        'reasons': [],
    }

    errors = []
    if not raw_result_valid:
        errors.append('NO_METHOD_RESULT')
    for key in ('error', 'cleanup_error', 'fatal_error'):
        if result.get(key):
            errors.append('METHOD_' + key.upper())
    declared_errors = context.get('hard_errors')
    if declared_errors:
        errors.append('OBSERVED_HARD_ERRORS')
    for key in ('input_identity_valid', 'source_identity_valid', 'current_request_identity_valid'):
        if context.get(key) is False:
            errors.append(key.upper() + '_FAILED')
    isolation = context.get('worker_isolation')
    if isolation == 'FAILED':
        errors.append('WORKER_ISOLATION_FAILED')
    if isolation == 'NOT_APPLICABLE' and result.get('matlab_worker_ready') is True:
        errors.append('WORKER_ISOLATION_CONTRADICTS_NATIVE_WORKER')

    numeric = context.get('observed_numerical_rejection')
    checks = context.get('numerical_checks', [])
    if isinstance(checks, list):
        for check in checks:
            if (isinstance(check, dict) and isinstance(check.get('report'), dict)
                    and check['report'].get('accepted') is False):
                numeric = True
    if errors:
        out.update(execution_status='TECHNICAL_FAILURE_CONFIRMED', reasons=errors)
        # A simultaneous numeric rejection remains visible even when the
        # primary status is an independently observed technical failure.
        out['observed_numerical_rejection'] = numeric
        return out
    if numeric is True:
        out.update(execution_status='NUMERICAL_ANOMALY_OBSERVED',
                   reasons=['ACTUAL_NUMERICAL_REPORT_REJECTED'])
        return out

    missing = []
    if not supplied_context:
        missing.append('NO_EVIDENCE_CONTEXT')
    for key in ('input_identity_valid', 'source_identity_valid', 'current_request_identity_valid'):
        if context.get(key) is not True:
            missing.append(key.upper() + '_UNKNOWN')
    if not isinstance(declared_errors, list):
        missing.append('HARD_ERROR_CHECK_UNKNOWN')
    if numeric is not False:
        missing.append('NUMERICAL_CHECK_UNKNOWN')
    if not isinstance(checks, list):
        missing.append('MALFORMED_NUMERICAL_CHECK_LIST')
    if isolation not in ('NOT_APPLICABLE', 'VERIFIED'):
        missing.append('WORKER_ISOLATION_UNKNOWN')
    if context.get('prior_requests_complete') is not True:
        missing.append('EARLIER_REQUEST_NOT_CONFIRMED_COMPLETE')
    cutoff = context.get('cutoff_s')
    if not _finite_number(cutoff) or cutoff <= 0:
        missing.append('INVALID_ROOT_CUTOFF')
    if last_state not in ('NONE', 'COMPLETE', 'PENDING', 'THERMAL_UNRESOLVED'):
        missing.append('LAST_REQUEST_STATE_UNKNOWN')
    if missing:
        out['reasons'] = missing
        return out
    if out['thermal_unresolved']:
        out['reasons'] = ['THERMAL_UNRESOLVED_IS_NEITHER_SAFE_NOR_VIOLATION']
        return out

    deadline = context.get('root_deadline_confirmed')
    if deadline is True:
        if context.get('deadline_causal_trace') is not True:
            out['reasons'] = ['ROOT_DEADLINE_CAUSAL_TRACE_MISSING']
            return out
        if last_state == 'PENDING':
            reasons = last.get('deadline_reasons')
            valid_reasons = (isinstance(reasons, list) and bool(reasons)
                             and all(isinstance(reason, str) and reason in DEADLINE_REASONS
                                     for reason in reasons))
            if not (last.get('pending_at_cutoff') is True
                    and last.get('refuses_late_candidate') is True
                    and last.get('deadline_causal_trace') is True and valid_reasons):
                out['reasons'] = ['PENDING_LAST_REQUEST_NOT_EXPLAINED_BY_DEADLINE']
                return out
            out.update(execution_status='NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST',
                       reasons=['VERIFIED_ROOT_DEADLINE_LAST_REQUEST_UNRESOLVED'])
        else:
            out.update(execution_status='NORMAL_TIME_LIMIT',
                       reasons=['VERIFIED_ROOT_DEADLINE_NO_PENDING_REQUEST'])
        return out
    if (deadline is False and context.get('completion_verified') is True
            and last_state in ('NONE', 'COMPLETE')):
        out.update(execution_status='NORMAL_COMPLETION',
                   reasons=['METHOD_COMPLETION_VERIFIED_NO_PENDING_REQUEST'])
    else:
        out['reasons'] = ['METHOD_COMPLETION_OR_DEADLINE_NOT_ESTABLISHED']
    return out
