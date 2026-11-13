"""Narrow, read-only correction of the K163 root-cancel marker audit.

The frozen deadline entry is always called first. This adapter neither repairs
numerical candidates nor reads a late native response. It changes only a derived
execution classification when the complete original root-cutoff chain passes.
Original records, marker text, safe U and scientific receipts remain untouched.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT/'deadline_batch'), str(ROOT/'p0_batch'), str(ROOT)]
import deadline_entry as inherited
import audit_cutoff
from execution_status import classify_execution, DEADLINE_REASONS

PROTOCOL = 'K163-root-cutoff-cancel-overwrite-adapter-v1'
MARKER_ERROR = 'MISSING_MATCHING_ROOT_CANCEL_FILE'
OVERWRITTEN_MARKER = 'augmented numerical admission unresolved'
NORMAL = 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _numeric_reports_passed(checks):
    return (isinstance(checks, list) and all(
        isinstance(check, dict) and check.get('accepted') is True
        and isinstance(check.get('report'), dict)
        and check['report'].get('accepted') is True
        and check['report'].get('reasons') == []
        and check.get('within_budget') is True
        and _finite(check.get('completed_at_s'))
        and 0 <= check['completed_at_s'] < 300
        for check in checks))


def result_records(job, result, declaration, folder, **kw):
    """Return an explicitly labelled derived view; never mutate caller records.

    All nonmatching cases retain the inherited classification and hard errors.
    ``input_valid`` and ``source_valid`` remain mandatory original audit inputs.
    """
    original = inherited.result_records(job, result, declaration, folder, **kw)
    checked = deepcopy(original)
    audit = {
        'protocol': PROTOCOL, 'applied': False,
        'original_execution_status': original['execution']['execution_status'],
        'original_execution': deepcopy(original['execution']),
        'original_context_hard_errors': deepcopy(original['context'].get('hard_errors')),
        'original_cutoff_audit': deepcopy(original.get('cutoff_audit')),
        'original_usable_U_J': original.get('usable_U_J'),
        'new_safe_evaluation': False, 'late_candidate_accepted': False,
        'original_data_modified': False, 'new_research_authorization': False,
    }
    checked['cancel_overwrite_audit'] = audit
    try:
        context, cutoff = checked['context'], original.get('cutoff_audit') or {}
        _require(job.get('method') == 'linked_fixed_unit_opp_start', 'Not the linked method')
        _require(original['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED'
                 and context.get('hard_errors') == [MARKER_ERROR]
                 and cutoff.get('applied') is True,
                 'Not the sole inherited marker-content error after verified cutoff')
        _require((original.get('current_schedule_audit') or {}).get('passed') is True,
                 'Current deadline schedule audit did not pass')
        _require(kw.get('input_valid') is True and kw.get('source_valid') is True
                 and all(context.get(key) is True for key in (
                     'input_identity_valid', 'source_identity_valid',
                     'current_request_identity_valid', 'prior_requests_complete',
                     'root_deadline_confirmed', 'deadline_causal_trace'))
                 and context.get('worker_isolation') == 'VERIFIED'
                 and context.get('observed_numerical_rejection') is False
                 and context.get('cutoff_s') == 300
                 and context.get('completion_verified') is False
                 and context.get('thermal_unresolved') is False,
                 'Identity, prior completion, numerical, deadline or isolation proof missing')
        timing = result.get('timing') or {}
        elapsed = timing.get('method_elapsed_s')
        _require(result.get('budget_exhausted') is True
                 and result.get('reason') == 'wall_time_limit'
                 and timing.get('limit_s') == 300 and _finite(elapsed) and elapsed >= 300,
                 'Wrong root method budget or no root cutoff')
        _require(_numeric_reports_passed(context.get('numerical_checks')),
                 'A recorded numerical check is missing, rejected or late')
        requests = (result.get('augmented_transport') or {}).get('requests')
        _require(isinstance(requests, list) and bool(requests), 'No augmented request chain')
        _require(all(_numeric_reports_passed(r.get('numerical_checks')) for r in requests),
                 'A transport numerical check is missing, rejected or late')
        _require(all(audit_cutoff._complete(r) for r in requests[:-1]),
                 'An earlier request is not complete')
        request, python, metadata, scopes = audit_cutoff._last_mapping(result, folder)
        reasons, last = request.get('failure_reasons'), context.get('last_request') or {}
        cancel_at = request.get('cancel_published_at_s')
        transient = set((python.get('publication_read') or {}).get('transient_read_errors') or {})
        start = (result.get('condition') or {}).get('budget_identity', {}).get('start')
        _require(request.get('cancel_requested') is True and _finite(cancel_at)
                 and 300 <= cancel_at <= elapsed
                 and request.get('native_status') == 'BUDGET_EXHAUSTED'
                 and request.get('within_budget') is False
                 and request.get('latched_unresolved') is True
                 and isinstance(reasons, list) and bool(reasons)
                 and all(isinstance(r, str) and r in DEADLINE_REASONS for r in reasons)
                 and last.get('state') == 'PENDING' and last.get('pending_at_cutoff') is True
                 and last.get('refuses_late_candidate') is True
                 and last.get('deadline_causal_trace') is True
                 and last.get('deadline_reasons') == reasons,
                 'Last request is not explained exclusively by the root deadline')
        _require(python.get('status') == 'BUDGET_EXHAUSTED'
                 and python.get('budget_valid') is False
                 and python.get('accepted_for_evaluation') is False
                 and python.get('response_may_arrive_later') is True
                 and python.get('x') == [] and transient <= {'FileNotFoundError'}
                 and metadata.get('method_deadline_bound') is True
                 and Fraction(str(metadata['absolute_deadline'])) == Fraction(start)+300,
                 'Native result was not refused under the same absolute root deadline')
        _require(cutoff.get('method_deadline_bound') is True
                 and cutoff.get('cancel_published_at_s') == cancel_at
                 and cutoff.get('method_stop_s') == elapsed
                 and cutoff.get('absolute_deadline') == metadata['absolute_deadline']
                 and cutoff.get('exact_request_scopes') == sorted(scopes),
                 'Inherited cutoff audit does not match the final native request')
        removed = cutoff.get('removed_hard_records')
        fields = {'scope', 'reason', 'status', 'technical_state', 'error'}
        _require(isinstance(removed, list) and bool(removed) and all(
            isinstance(v, dict) and set(v) == fields and v['scope'] in scopes
            and v['status'] == 'BUDGET_EXHAUSTED'
            and all(v[k] is None for k in ('reason', 'technical_state', 'error'))
            for v in removed), 'Inherited cutoff removed an unrelated hard record')
        number = python['request_number']
        cancel = Path(folder)/'matlab'/f'request_{number:06d}.cancel'
        _require(cancel.is_file(), 'The matching final cancellation file is absent')
        _require(cancel.read_text(encoding='ascii').strip() == OVERWRITTEN_MARKER,
                 'The final cancellation marker is not the documented overwrite')
        context['hard_errors'] = []
        execution = classify_execution(result, context)
        _require(execution['execution_status'] == NORMAL,
                 'Independent classification still finds a fault or unresolved proof')
        _require(execution.get('usable_U_J') == original.get('usable_U_J')
                 and execution.get('usable_safe_formed_at_s')
                 == original['execution'].get('usable_safe_formed_at_s')
                 and execution.get('new_or_late_candidate_accepted') is False,
                 'The derived view would change a safe receipt or accept a late candidate')
        checked['execution'] = execution
        audit.update(applied=True, derived_execution_status=NORMAL,
                     derived_context_removed_error=MARKER_ERROR,
                     final_native_request_number=number,
                     exact_request_scopes=sorted(scopes),
                     matching_cancel_file_sha256=_hash(cancel),
                     matching_python_file_sha256=_hash(cancel.with_suffix('.python.json')),
                     matching_input_file_sha256=_hash(cancel.with_suffix('.input.json')),
                     explanation='The final budget cancellation marker was overwritten by '
                         '_Request.fail; all original deadline, identity, numerical, isolation '
                         'and current-schedule checks passed. Only the stored classification '
                         'is derived; the pending request remains unresolved and no late '
                         'candidate, safe U or proof is added.')
        return checked
    except (OSError, UnicodeError, KeyError, TypeError, ValueError,
            IndexError, ZeroDivisionError, OverflowError) as error:
        # A failed proof must keep the inherited hard error and original status.
        checked = deepcopy(original)
        audit['not_applied_reason'] = str(error)
        checked['cancel_overwrite_audit'] = audit
        return checked
