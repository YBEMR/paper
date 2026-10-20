"""K143: stored JSON/hash audit and data-only classification cases.

This is a review prototype, not the method controller. It does not import
production modules, decode candidates, compute heat, or execute a solver.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
OLD = HERE.parent/'fair_comparison_preparation01'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


DEADLINE_REASONS = {'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED',
    'BUDGET_BEFORE_FINAL_ADMISSION', 'BUDGET_DURING_ADMISSION_ARCHIVE'}


def classify(f):
    """Conservative evidence contract; never exempts a fault by reason text alone."""
    at, cutoff = f.get('safe_formed_at_s'), f.get('cutoff_s')
    numeric_time = lambda x: type(x) in (int, float) and math.isfinite(x)
    prior_safe = bool(f.get('prior_safe_verified') is True
        and f.get('prior_safe_identity_valid') is True and f.get('identities_valid') is True and numeric_time(at)
        and numeric_time(cutoff) and 0 <= at < cutoff)
    result = {'archival_evidence_retained': True, 'safe_witness_preserved': prior_safe,
        'last_request': 'UNRESOLVED', 'independently_proven_optimal': False,
        'independently_proven_infeasible': False,
        'known_violation_preserved': f.get('timely_known_violation') is True,
        'new_or_late_candidate_accepted': False}
    if (f.get('hard_errors') or f.get('identities_valid') is False
        or f.get('current_request_identity_valid') is False or f.get('cleanup_verified') is False):
        result['execution_status'] = 'TECHNICAL_FAILURE_CONFIRMED'
    elif f.get('observed_numerical_rejection') is True:
        result['execution_status'] = 'NUMERICAL_ANOMALY_OBSERVED'
    elif (f.get('identities_valid') is not True or f.get('current_request_identity_valid') is not True
        or f.get('cleanup_verified') is not True
        or f.get('observed_numerical_rejection') is not False
        or f.get('hard_errors') is None
        or f.get('prior_requests_complete') is not True
        or not numeric_time(cutoff) or cutoff <= 0):
        result['execution_status'] = 'STATUS_UNRESOLVED'
    elif (f.get('root_deadline_confirmed') is True
        and f.get('pending_response_at_cutoff') is True
        and f.get('budget_stub_refuses_candidate') is True
        and f.get('deadline_causal_trace') is True
        and f.get('deadline_reasons')
        and set(f['deadline_reasons']) <= DEADLINE_REASONS):
        result['execution_status'] = 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
    else:
        result['execution_status'] = 'STATUS_UNRESOLVED'
    return result


def strict_updates(result):
    updates = result['global_updates']
    initial = tuple(map(F, updates[0]['weighted_energy_J']))
    incumbent = initial
    rows = []
    for u in updates[1:]:
        value = tuple(map(F, u['weighted_energy_J']))
        rows.append({'phase_index':u['phase_index'], 'committed_at_s':u['committed_at_s'],
            'strict_vs_initial': value[1] < initial[0],
            'strict_vs_previous_incumbent':value[1] < incumbent[0],
            'energy_J':list(map(str,value))})
        incumbent = value
    return rows


def main():
    declaration = read(OLD/'declaration.json')
    prior = read(OLD/'execution_k142/analysis01/facts.json')
    raw = prior['raw_hashes_after']
    before = {n:sha(OLD/n) for n in raw}
    source_before = {n:sha(REPO/n) for n in declaration['source_sha256']}
    r = read(OLD/'linked_n1/result.json')
    claim = read(OLD/'claims/linked_n1_result.json')
    python = read(OLD/'linked_n1/matlab/request_000004.python.json')
    requests = r['augmented_transport']['requests']
    last = requests[-1]
    checks = [v for q in requests for v in q.get('numerical_checks', [])]
    hard = [v for v in (r.get('error'), r.get('cleanup_error'), claim.get('error')) if v]
    failed_gates = [v for v in checks if v.get('accepted') is False]
    # The aggregate accepted flag also tests budget/context. Only a rejected
    # numerical report establishes a numerical rejection; an absent report
    # stays unknown. No residual is recomputed in this review.
    numeric_failures = [v for v in failed_gates if (v.get('report') or {}).get('accepted') is False]
    numerical_rejection = (True if numeric_failures else
        None if any((v.get('report') or {}).get('accepted') is not True for v in failed_gates) else False)
    # Missing response during timed polling is expected here; permission,
    # parser and identity errors are not silently converted to this case.
    poll = python.get('publication_read') or {}
    expected_pending_poll = set((poll.get('transient_read_errors') or {})) == {'FileNotFoundError'}
    earlier_complete = all(q.get('latched_unresolved') is False
        and q.get('within_budget') is True and not q.get('failure_reasons')
        and q.get('callback_publications_complete') is True
        and q.get('expected_callback_numbers') == q.get('checked_callback_numbers') for q in requests[:-1])
    identities = source_before == declaration['source_sha256'] and before == raw
    facts = {'root_deadline_confirmed': r.get('budget_exhausted') is True
            and r.get('reason') == 'wall_time_limit',
        'cutoff_s':r['timing']['limit_s'],
        'safe_formed_at_s':r['aggregation']['completed_at_elapsed_s'],
        'prior_safe_verified': read(OLD/'execution_k142/verification.json')['passed'] is True,
        'prior_safe_identity_valid':identities,
        'identities_valid':identities, 'current_request_identity_valid':identities, 'hard_errors':hard,
        'cleanup_verified':claim['cleanup'].get('observed_tree_verified_terminated'),
        'observed_numerical_rejection':numerical_rejection,
        'prior_requests_complete':earlier_complete,
        'pending_response_at_cutoff':python.get('status') == 'BUDGET_EXHAUSTED'
            and python.get('response_may_arrive_later') is True and expected_pending_poll,
        'budget_stub_refuses_candidate':python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == [],
        'deadline_causal_trace':last.get('cancel_requested') is True
            and last.get('cancel_published_at_s') == r['timing']['limit_s']
            and last.get('native_status') == 'BUDGET_EXHAUSTED'
            and last.get('within_budget') is False,
        'deadline_reasons':last.get('failure_reasons'),
        'timely_known_violation':bool(r.get('violations'))}
    derived = classify(facts)
    cases = []
    def case(name, changes, expected, preserve=True, violation=False):
        sample = deepcopy(facts)
        sample.update(changes)
        value = classify(sample)
        passed = value['execution_status'] == expected and value['safe_witness_preserved'] is preserve
        passed = passed and value['known_violation_preserved'] is violation
        cases.append({'name':name,'changed_fields':changes,'expected_status':expected,
            'expected_safe_preserved':preserve,'passed':passed,'classification':value})
    normal = 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
    unknown = 'STATUS_UNRESOLVED'
    fault = 'TECHNICAL_FAILURE_CONFIRMED'
    case('K142_original_stored_trace', {}, normal)
    case('deadline_without_any_SAFE_is_not_infeasibility', {'prior_safe_verified':False}, normal, False)
    case('SAFE_completed_at_cutoff_not_accepted', {'safe_formed_at_s':300.0}, normal, False)
    case('SAFE_completed_before_cutoff_preserved', {'safe_formed_at_s':299.999}, normal)
    case('SAFE_completed_after_cutoff_not_accepted', {'safe_formed_at_s':300.001}, normal, False)
    case('real_exception_overrides_time_limit', {'hard_errors':['AUGMENTED_TRANSPORT_EXCEPTION']}, fault)
    case('global_identity_error_invalidates_rankable_SAFE', {'identities_valid':False}, fault, False)
    case('late_request_identity_error_preserves_independent_prior_SAFE', {'current_request_identity_valid':False}, fault)
    case('prior_SAFE_identity_corrupted_is_archived_not_rankable', {'prior_safe_identity_valid':False}, normal, False)
    case('prior_SAFE_identity_unknown_is_not_rankable', {'prior_safe_identity_valid':None}, normal, False)
    case('owned_worker_cleanup_failure_overrides_time_limit', {'cleanup_verified':False}, fault)
    case('numerical_rejection_not_hidden_by_deadline', {'observed_numerical_rejection':True}, 'NUMERICAL_ANOMALY_OBSERVED')
    case('unknown_reason_is_not_whitelisted', {'deadline_reasons':list(DEADLINE_REASONS)+['UNKNOWN_ERROR']}, unknown)
    case('missing_callback_before_deadline_not_exempted', {'root_deadline_confirmed':False}, unknown)
    case('missing_response_trace_is_unresolved', {'pending_response_at_cutoff':None}, unknown)
    case('missing_cancel_causal_trace_is_unresolved', {'deadline_causal_trace':False}, unknown)
    case('earlier_incomplete_request_not_exempted', {'prior_requests_complete':False}, unknown)
    case('unconfirmed_cleanup_is_unresolved', {'cleanup_verified':None}, unknown)
    case('unknown_numeric_gate_is_unresolved', {'observed_numerical_rejection':None}, unknown)
    case('malformed_deadline_is_unresolved', {'cutoff_s':None}, unknown, False)
    case('failure_does_not_erase_independent_earlier_SAFE', {'hard_errors':['RESOURCE_LIMIT']}, fault)
    case('known_timely_violation_survives_cutoff', {'timely_known_violation':True}, normal, True, True)
    changes = strict_updates(r)
    first_strict = next((u['committed_at_s'] for u in changes if u['strict_vs_initial']), None)
    after = {n:sha(OLD/n) for n in raw}
    source_after = {n:sha(REPO/n) for n in declaration['source_sha256']}
    invariants = {'raw301_equal_original':len(raw)==301 and before==raw and after==raw,
        'source159_equal_frozen':len(source_after)==159 and source_after==source_before==declaration['source_sha256'],
        'actual_case_normal_time_limit':derived['execution_status']==normal,
        'actual_prior_SAFE_preserved':derived['safe_witness_preserved'],
        'old_ledger_remains_BLOCKED':read(OLD/'ledger.json')['state']=='BLOCKED',
        'old_calls_remain_two':read(OLD/'ledger.json')['consumed']==2,
        'HEFT_SA_remain_unclaimed':all(not (OLD/'claims'/(n+'.json')).exists() for n in ('heft','sa101')),
        'data_only_cases_pass':all(c['passed'] for c in cases)}
    report = {'stage':'K143','scope':'offline stored evidence only; classification prototype not applied to production',
        'passed':all(invariants.values()), 'invariants':invariants,
        'data_only_case_count':len(cases), 'data_only_cases':cases,
        'facts':facts, 'derived_interpretation':derived,
        'original_controller_state':claim['state'], 'original_controller_issues':claim['technical_issues'],
        'strict_complete_energy_updates':changes, 'first_strict_improvement_vs_initial_at_s':first_strict,
        'phase2_strict_improvement_at_s':next((u['committed_at_s'] for u in changes if u['phase_index']==2 and u['strict_vs_previous_incumbent']),None),
        'saved_numerical_gate_count':len(checks),'observed_rejected_gates':failed_gates,
        'source_sha256':source_after,'raw_artifact_sha256':raw,
        'new_research_calls':0,'new_heat_evaluations':0,'new_candidate_decodes':0,
        'production_modified':False,'K142_raw_records_modified':False}
    (HERE/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('stage','passed','data_only_case_count','derived_interpretation','first_strict_improvement_vs_initial_at_s','phase2_strict_improvement_at_s','saved_numerical_gate_count','new_research_calls','production_modified')},ensure_ascii=False))
    return report['passed']

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
