"""K195 thin, stored-evidence admission; no scientific imports or execution.

All scientific checks are explicitly injected. ``candidate_validator(candidate)``
must be a pure restricted-domain check, returning a dictionary with either
``passed=True`` or ``state=COMPLETE_STRUCTURAL_DOMAIN_MEMBER`` and no errors.

``method_records`` returns the unchanged original audit under ``original_audit``;
``usable_U_J`` and ``retained_safe_evidence`` preserve a previously certified
in-budget SAFE even after a later technical/numerical failure. They do not imply
normal comparison eligibility. ``comparison_eligible_U_J`` and ``post_eligible``
require an original NORMAL status, verified identities and domain membership.
``domain_valid=None`` means no complete SAFE candidate was available to inspect.

``post_records`` only compares an immutable old candidate and two stored full
receipts. ``passed`` certifies this thin consistency check, not an independent
physical model. ``new_U=False`` always; the old method U is never replaced.
The caller owns the single-use claim, source binding, process isolation and
60-second absolute budget. No callback here may solve or integrate heat.
"""
from copy import deepcopy
from fractions import Fraction as Q
import math


NORMAL = frozenset(('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT',
                    'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _interval(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError('A complete two-sided energy interval is required')
    if any(isinstance(item, bool) for item in value):
        raise ValueError('Boolean energy is invalid')
    low, high = map(Q, value)
    if low < 0 or high < low:
        raise ValueError('Invalid nonnegative energy interval')
    return low, high


def _accepted_candidates(result):
    """Already accepted records only; never decode or recover a new candidate."""
    rows = []
    if result.get('safe_upper_bound_J') is not None:
        rows.append(('final', result.get('safe_candidate')))
    witness = (result.get('initialisation') or {}).get('witness')
    if isinstance(witness, dict) and witness.get('evaluation', {}).get('state') == 'SAFE':
        rows.append(('initialisation.witness', witness.get('candidate')))
    diagnostics = [result.get('diagnostic'),
                   (result.get('solver_diagnostic') or {}).get('diagnostic')]
    for number, diagnostic in enumerate(diagnostics):
        if not isinstance(diagnostic, dict):
            continue
        for index, row in enumerate(diagnostic.get('evaluations') or []):
            if isinstance(row, dict) and row.get('accepted_safe') is True:
                rows.append(('diagnostic'+str(number)+'.evaluations['+str(index)+']',
                             row.get('candidate')))
    unique = []
    for source, candidate in rows:
        if not any(candidate == existing for _, existing in unique):
            unique.append((source, candidate))
    return unique


def method_records(result, spec, folder, *, input_valid, source_valid, errors,
                   original_audit, candidate_validator):
    """Audit immutable method records with injected original and domain checks.

    No mutation of ``result``/``spec`` is performed. A callback exception fails
    closed and is reported; it does not trigger another audit or a retry.
    """
    original = None
    issues, domain_checks = [], []
    records = result if isinstance(result, dict) else {}
    try:
        original = original_audit(result, spec, folder, input_valid=input_valid,
                                  source_valid=source_valid, errors=errors)
        if not isinstance(original, dict):
            raise TypeError('Original audit did not return a dictionary')
    except Exception as error:
        issues.append('ORIGINAL_AUDIT_EXCEPTION:'+type(error).__name__+':'+str(error))
    try:
        candidates = _accepted_candidates(records)
        for source, candidate in candidates:
            check = candidate_validator(candidate)
            accepted = (isinstance(check, dict) and
                        (check.get('passed') is True or
                         check.get('state') == 'COMPLETE_STRUCTURAL_DOMAIN_MEMBER') and
                        not check.get('errors'))
            domain_checks.append({'source': source, 'accepted': accepted,
                                  'check': deepcopy(check)})
            if not accepted:
                issues.append('RESTRICTED_DOMAIN_REJECTED:'+source)
    except Exception as error:
        issues.append('DOMAIN_CHECK_EXCEPTION:'+type(error).__name__+':'+str(error))
    domain_valid = (not any(issue.startswith(('RESTRICTED_DOMAIN_', 'DOMAIN_CHECK_'))
                            for issue in issues)) if domain_checks else None
    # An exception before producing the first domain record is a rejection,
    # not the benign "no SAFE available" state.
    if any(issue.startswith('DOMAIN_CHECK_') for issue in issues):
        domain_valid = False
    status = ((original or {}).get('execution') or {}).get('execution_status')
    upper = (original or {}).get('usable_U_J')
    retained = None
    if (upper is not None and domain_valid is True and not issues
            and input_valid is True and source_valid is True):
        try:
            energy = _interval((records.get('evaluation') or {})['weighted_energy_J'])
            if Q(upper) != energy[1] or Q(records['safe_upper_bound_J']) != energy[1]:
                raise ValueError('Original U differs from final complete receipt')
            retained = {'candidate': deepcopy(records['safe_candidate']),
                'evaluation': deepcopy(records['evaluation']), 'usable_U_J': upper,
                'source': records.get('safe_solution_source'),
                'formed_at_s': records['evaluation'].get('completed_at_elapsed_s'),
                'normal_ranking_eligible': False,
                'scope': 'existing complete method receipt; no new evaluation'}
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            issues.append('FINAL_SAFE_LEDGER_MISMATCH:'+str(error))
    normal = (status in NORMAL and input_valid is True and source_valid is True
              and not errors and not issues and (domain_valid is not False))
    eligible = bool(normal and retained is not None)
    if retained is not None:
        retained['normal_ranking_eligible'] = eligible
    return {'protocol': 'K195-stored-whole-domain-admission-v1',
        'original_audit': deepcopy(original), 'original_execution_status': status,
        'domain_valid': domain_valid, 'domain_checks': domain_checks,
        'issues': issues, 'normal_terminal': bool(normal),
        'usable_U_J': upper if retained is not None else None,
        'retained_safe_evidence': retained,
        'comparison_eligible_U_J': upper if eligible else None,
        'post_eligible': eligible, 'new_U': False, 'new_physical_evaluation': False}


def post_records(old_result, fresh, candidate, spec, *, receipt_issues,
                 exact_enclosure, legality, seconds=60):
    """Pure unique-post consistency admission; never replace the old method U.

    ``receipt_issues(receipt, candidate, spec)`` and
    ``exact_enclosure(receipt, spec)`` must be original stored-field checks.
    ``legality`` is the already computed original static schedule-check record.
    Both receipts must retain all declared scenes and their original outward
    weighted energy. Fresh completion must be strictly before 60 seconds.
    """
    issues, details = [], {}
    old_upper = old_result.get('safe_upper_bound_J') if isinstance(old_result, dict) else None
    try:
        if type(seconds) not in (int, float) or seconds != 60:
            raise ValueError('Only the declared unique 60-second post is allowed')
        if not isinstance(old_result, dict) or not isinstance(fresh, dict):
            raise ValueError('Both original and post receipts are required')
        if candidate != old_result.get('safe_candidate'):
            issues.append('POST_CANDIDATE_CHANGED')
        if (not isinstance(legality, dict) or
                legality.get('state') != 'SCHEDULE_VALID_THERMAL_UNCHECKED'):
            issues.append('POST_STATIC_LEGALITY_REJECTED')
        if fresh.get('legality') != legality:
            issues.append('POST_RECEIPT_LEGALITY_MISMATCH')
        old_receipt = old_result.get('evaluation') or {}
        if old_result.get('state') != 'SAFE' or old_upper is None:
            issues.append('OLD_METHOD_HAS_NO_COMPLETE_SAFE')
        for label, receipt in (('old', old_receipt), ('post', fresh)):
            if receipt.get('state') != 'SAFE' or receipt.get('rankable_energy') is not True:
                issues.append(label.upper()+':NOT_COMPLETE_RANKABLE_SAFE')
        stamp = fresh.get('completed_at_elapsed_s')
        if not _finite(stamp) or not 0 <= stamp < seconds:
            issues.append('POST_RECEIPT_NOT_BEFORE_CUTOFF')
        scenes = set(spec['scene_spec'])
        if (not isinstance(candidate, dict) or set(candidate.get('scenes') or {}) != scenes
                or set(fresh.get('scenes') or {}) != scenes
                or set(old_receipt.get('scenes') or {}) != scenes):
            issues.append('POST_SCENE_COVERAGE_MISMATCH')
        for label, receipt in (('old', old_receipt), ('post', fresh)):
            if any(scene.get('complete') is not True for scene in
                   (receipt.get('scenes') or {}).values()):
                issues.append(label.upper()+':INCOMPLETE_SCENE')
        for label, receipt in (('old', old_receipt), ('post', fresh)):
            found = receipt_issues(receipt, candidate, spec)
            if not isinstance(found, list):
                raise TypeError('Original receipt checker did not return an issue list')
            issues.extend(label.upper()+':'+str(item) for item in found)
            exact = exact_enclosure(receipt, spec)
            details[label+'_enclosure'] = deepcopy(exact)
            if not isinstance(exact, dict) or exact.get('accepted') is not True:
                issues.append(label.upper()+':INVALID_ORIGINAL_WEIGHTED_ENCLOSURE')
        before, after = _interval(old_receipt['weighted_energy_J']), _interval(fresh['weighted_energy_J'])
        if Q(old_upper) != before[1] or Q(old_receipt['safe_upper_bound_J']) != before[1]:
            issues.append('OLD_U_LEDGER_MISMATCH')
        if Q(fresh['safe_upper_bound_J']) != after[1]:
            issues.append('POST_U_LEDGER_MISMATCH')
        if max(before[0], after[0]) > min(before[1], after[1]):
            issues.append('POST_ENERGY_NOT_REPRODUCED')
        details.update(old_energy_J=list(map(str, before)),
                       post_energy_J=list(map(str, after)))
    except Exception as error:
        issues.append('POST_AUDIT_EXCEPTION:'+type(error).__name__+':'+str(error))
    return {'protocol': 'K195-stored-unique-post-admission-v1',
        'passed': not issues, 'issues': issues, 'checks': details,
        'new_U': False, 'old_U_J_unchanged': old_upper,
        'comparison_eligible_U_J': old_upper if not issues else None,
        'new_physical_evaluation': False,
        'scope': 'stored full-receipt consistency; no search, repair or new U'}
