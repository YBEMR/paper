from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from run_four_method_comparison import read, canonical, finite
from completion_metrics import build_completion_metrics
from execution_status import classify_execution, DEADLINE_REASONS
SECONDS = 300

def receipt_issues(evaluation,candidate,declaration):
    """Inspect already produced proof fields; never recompute a trajectory."""
    errors=[];spec=declaration['scene_spec']
    try:
        if (evaluation.get('state')!='SAFE' or evaluation.get('rankable_energy') is not True
            or evaluation.get('problem_id')!=declaration['problem_id']
            or (evaluation.get('legality') or {}).get('state')!='SCHEDULE_VALID_THERMAL_UNCHECKED'):
            errors.append('NOT_FULL_ORIGINAL_SAFE_RECEIPT')
        if set(evaluation.get('scenes',{}))!=set(spec) or set(candidate.get('scenes',{}))!=set(spec):
            errors.append('SCENE_COVERAGE_MISMATCH')
        formed=evaluation.get('completed_at_elapsed_s')
        if not finite(formed) or not 0<=formed<SECONDS:errors.append('RECEIPT_NOT_FORMED_BEFORE_CUTOFF')
        lo,hi=map(F,evaluation['weighted_energy_J'])
        if lo<0 or hi<lo or F(evaluation['safe_upper_bound_J'])!=hi:errors.append('INVALID_ENERGY_INTERVAL')
        for sid,definition in spec.items():
            scene=evaluation['scenes'][sid]
            if scene.get('state')!='SAFE' or scene.get('rankable_energy') is not True or scene.get('complete') is not True:
                errors.append('SCENE_NOT_COMPLETE_SAFE:'+sid)
            window=F(definition['window_s'])
            if F(scene['covered_until_s'])!=window or F(scene['trace'][-1]['time_s'])!=window:
                errors.append('FULL_WINDOW_OR_IDLE_TAIL_MISSING:'+sid)
            if set(scene['peaks_degC'])!=set(definition['limits']):errors.append('PEAK_NODE_COVERAGE_MISMATCH:'+sid)
            for node,limit in definition['limits'].items():
                low,high=map(F,scene['peaks_degC'][node])
                if high<low or high>F(limit):errors.append('PEAK_ENCLOSURE_NOT_SAFE:'+sid+':'+node)
    except (KeyError,TypeError,ValueError,ZeroDivisionError,IndexError):
        errors.append('MALFORMED_COMPLETE_RECEIPT')
    return errors

def result_records(result,declaration,*,input_valid,source_valid,errors=None):
    """Separate runtime status, usable old evidence and archived raw output."""
    r=result if isinstance(result,dict) else {};hard=list(errors or [])
    if r.get('reason') in ('RESOURCE_LIMIT','INTERFACE_ERROR','INVALID_INPUT_OR_INTERFACE','INITIALISATION_ERROR'):
        hard.append(r['reason'])
    reported_input=r.get('input_sha256')
    if input_valid is False or (reported_input is not None and reported_input!=declaration['input_sha256']):
        input_match=False
    elif input_valid is None:
        input_match=None
    elif reported_input is not None or (r.get('state')!='SAFE' and not r.get('safe_candidate')):
        # The loader may have completed identity validation before an L0
        # budget stop, prior to the unchanged entry publishing its identity.
        input_match=True
    else:
        input_match=None
    safe=None;filtered=deepcopy(r);evaluations=r.get('evaluations') or []
    filtered_rows=[];numeric=False;thermal_unknown=False;last={'state':'NONE'};unresolved=[]
    for row in evaluations:
        if not isinstance(row,dict):hard.append('MALFORMED_EVALUATION_RECORD');continue
        ev=row.get('evaluation') or {};copy=deepcopy(row)
        if row.get('accepted_safe') is True:
            bad=receipt_issues(ev,row.get('candidate') or {},declaration)
            if row.get('candidate_sha256')!=canonical(row.get('candidate') or {}):bad.append('CANDIDATE_IDENTITY_MISMATCH')
            if bad:
                copy['accepted_safe']=False;hard.extend('ACCEPTED_RECORD:'+v for v in bad)
        if ev.get('state')=='UNRESOLVED':
            unresolved.append({'source':row.get('source'),'reason':ev.get('reason'),
                'returned_at_s':row.get('returned_at_s'),'budget_exhausted':ev.get('budget_exhausted')})
        filtered_rows.append(copy)
        for record in [ev,*ev.get('scenes',{}).values()]:
            if record.get('reason') in ('NUMERICAL_ERROR','INTERNAL_CONSISTENCY_ERROR'):
                numeric=True
            if record.get('reason')=='RESOURCE_LIMIT':hard.append('EVALUATOR_RESOURCE_LIMIT')
            if record.get('error_type') and record.get('reason') not in ('NUMERICAL_ERROR','INTERNAL_CONSISTENCY_ERROR'):
                hard.append('EVALUATOR_EXCEPTION:'+str(record['error_type']))
    filtered['evaluations']=filtered_rows
    if r.get('state')=='SAFE':
        ev=r.get('evaluation') or {};candidate=r.get('safe_candidate') or {}
        issues=receipt_issues(ev,candidate,declaration)
        matched=any(row.get('accepted_safe') is True and row.get('candidate_sha256')==canonical(candidate)
            and row.get('candidate')==candidate and row.get('evaluation')==ev for row in filtered_rows)
        if not matched:issues.append('SAFE_NOT_BOUND_TO_ACCEPTED_CURRENT_CALL_RECORD')
        try:
            if F(r['safe_upper_bound_J'])!=F(ev['safe_upper_bound_J']):issues.append('ROOT_U_DIFFERS_FROM_RECEIPT')
        except (KeyError,TypeError,ValueError,ZeroDivisionError):issues.append('MALFORMED_ROOT_U')
        if issues:hard.extend(issues);filtered['evaluation']=None
        else:safe={'verified':True,'identity_valid':input_match,'complete':True,
            'formed_at_s':ev['completed_at_elapsed_s'],'energy_upper_J':ev['safe_upper_bound_J']}
    timing=r.get('timing') or {};elapsed=timing.get('method_elapsed_s')
    deadline=bool(r.get('budget_exhausted') is True and finite(elapsed) and elapsed>=SECONDS
        and timing.get('limit_s')==SECONDS)
    if evaluations and isinstance(evaluations[-1],dict):
        ev=evaluations[-1].get('evaluation') or {}
        incomplete=ev.get('state')=='UNRESOLVED' or (ev.get('state')=='SAFE'
            and evaluations[-1].get('accepted_safe') is not True)
        if incomplete:
            if deadline and (ev.get('budget_exhausted') is True or ev.get('reason') in ('wall_time_limit','SAFE_RECEIPT_NOT_ACCEPTED_WITHIN_BUDGET')):
                last={'state':'PENDING','pending_at_cutoff':True,'refuses_late_candidate':True,
                    'deadline_causal_trace':True,'deadline_reasons':['BUDGET_DURING_CANDIDATE_EVALUATION']}
            else:last={'state':'THERMAL_UNRESOLVED'};thermal_unknown=True
    known=None
    for witness in r.get('violations') or []:
        try:
            at=witness['formed_at_elapsed_s'];sid=witness['scene_id'];node=witness['node']
            low,high=map(F,witness['temperature_degC']);definition=declaration['scene_spec'][sid]
            if (finite(at) and 0<=at<SECONDS and 0<=F(witness['time_s'])<=F(definition['window_s'])
                and high>=low>F(definition['limits'][node]) and F(witness['limit_degC'])==F(definition['limits'][node])):
                known={'verified':True,'identity_valid':input_match,'complete':True,'formed_at_s':at};break
        except (KeyError,TypeError,ValueError,ZeroDivisionError):continue
    context={'input_identity_valid':input_match,'source_identity_valid':source_valid,
        'current_request_identity_valid':input_match,'cutoff_s':SECONDS,'hard_errors':hard,
        'observed_numerical_rejection':numeric,'worker_isolation':'NOT_APPLICABLE',
        'prior_requests_complete':True,'completion_verified':r.get('reason')=='DECLARED_SEARCH_COMPLETED',
        'root_deadline_confirmed':deadline,'deadline_causal_trace':deadline,
        'last_request':last,'safe_receipt':safe,'known_violation':known,'thermal_unresolved':thermal_unknown}
    status=classify_execution(result,context)
    metrics=build_completion_metrics(filtered,uses_matlab=False,seconds=SECONDS)
    metrics['identity_valid_for_comparison']=input_match is True and source_valid is True
    return {'execution':status,'completion_metrics':metrics,'context':context,
        'raw_reported_U_J':r.get('safe_upper_bound_J'),
        'usable_U_J':status['usable_U_J'],'unresolved_evaluation_records':unresolved,
        'scope':'existing complete receipts only; no new physical evidence or candidate accepted'}
