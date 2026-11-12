"""Ten predeclared 600 s calls; original algorithms, one common 80 C post each.

Reuses the existing immutable plan, user approval, process and resource gates.
No retry/resume and no historical solution or cache is a search input.
"""
from copy import deepcopy
from pathlib import Path
import sys
import time

from research.chapter3_experiments import natural_delivery_entry as delivery
from research.chapter3_experiments import closure_inputs

b = delivery.base
ENTRY = 'research/chapter3_experiments/closure_entry.py'
PREPARATION = closure_inputs.PREPARATION
OUTPUT = b.RESULTS/'chapter3_closure_execution01'
JOBS = [dict(id='t50_milp', method='whole_milp', seed=None, case='t50_full'),
        dict(id='t50_heft', method='heft', seed=None, case='t50_full'),
        dict(id='t50_sa101', method='sa', seed=101, case='t50_full'),
        dict(id='t50_milp_no_limit', method='whole_milp', seed=None, case='t50_no_limit'),
        *[dict(id=f't50_sa{s}',method='sa',seed=s,case='t50_full') for s in range(102,106)],
        dict(id='t78_milp', method='whole_milp',seed=None,case='t78_full'),
        dict(id='t78_milp_no_limit',method='whole_milp',seed=None,case='t78_no_limit')]
SCOPE = dict(method_calls=10, method_seconds_each=600, method_seconds_total=6000,
             post_calls_at_most=10, post_seconds_each=60, post_seconds_total_at_most=600,
             job_calendar_seconds=780, batch_calendar_seconds=7860, retries=0)
_worker = b.worker


def verify_sources(plan):
    for rel,digest in plan['source_sha256'].items():
        path=(b.ROOT/rel).resolve()
        b.require(path.is_relative_to(b.ROOT) and b.sha(path)==digest,'SOURCE_DRIFT:'+rel)
    for case in plan['cases'].values():
        for key,digest in case['sha256'].items():
            b.require(b.sha(b.ROOT/case[key])==digest,'CASE_DRIFT:'+case[key])


def validate_plan(plan):
    b.require(plan.get('schema')=='natural-full-three-manual-v1'
              and plan.get('execution_authorized') is False,'PLAN_SCHEMA')
    b.require(plan.get('jobs')==JOBS and plan.get('scope')==SCOPE,'PLAN_SCOPE')
    b.require(plan.get('builder_flags')==b.BUILDER_FLAGS and plan.get('feedback_kind')=='conditional'
              and plan.get('cut_max_iterations')==10,'SCIENCE_SETTINGS_DRIFT')
    b.require(plan.get('method_process_watchdog_seconds')==705
              and plan.get('historical_candidate_or_cache_input') is False
              and plan.get('reference_read_by_search') is False,'BOUNDARY_DRIFT')
    b.require(plan.get('delivery_policy')==delivery.POLICY
              and plan.get('numerical_representation')==delivery.prior.repaired.REPRESENTATION,'MILP_REPRESENTATION_OR_BUDGET')
    b.require(plan.get('science_source_count')==197 and ENTRY in plan['source_sha256'],'SOURCE_MANIFEST')
    b.require(plan.get('cases')==b.read(PREPARATION/'inputs.json')['cases'],'CASE_MANIFEST_DRIFT')
    b.require(plan.get('post_policy')=='one original-80C evaluation; no search/repair; expected ablation violation retained'
              and plan.get('precheck_thermal_calls')==0,'POST_OR_PRECHECK_POLICY')


def freeze(folder):
    folder=Path(folder).resolve()
    b.require(folder==PREPARATION and not (folder/'plan.json').exists(),'NEW_PLAN_REQUIRED')
    plan=deepcopy(b.read(delivery.PREPARATION/'plan.json'))
    for rel,digest in plan['source_sha256'].items():
        b.require(b.sha(b.ROOT/rel)==digest,'ORIGINAL_SOURCE_DRIFT:'+rel)
    manifest=b.read(folder/'inputs.json')
    plan.update(baseline_commit=b.git_bytes('rev-parse','HEAD').decode().strip(),
        jobs=JOBS,scope=SCOPE,cases=manifest['cases'],
        post_policy='one original-80C evaluation; no search/repair; expected ablation violation retained',
        precheck_thermal_calls=0,
        comparison='One fixed beta1 task at T0 50/78; full vs no80 planning, and MILP/HEFT/SA101-105 at50.')
    # Legacy single-input fields are replaced by explicit per-job case bindings.
    for key in ('input_file','input_sha256','config_file','config_sha256','static_size_sha256','domain_identity_sha256'):
        plan.pop(key,None)
    for rel in (ENTRY,'research/chapter3_experiments/closure_inputs.py',
                'research/chapter3_experiments/thermal_limit_ablation.py'):
        plan['source_sha256'][rel]=b.sha(b.ROOT/rel)
    plan['source_sha256'][(folder/'inputs.json').relative_to(b.ROOT).as_posix()]=b.sha(folder/'inputs.json')
    for case in manifest['cases'].values():
        for key,digest in case['sha256'].items():plan['source_sha256'][case[key]]=digest
    validate_plan(plan);verify_sources(plan)
    b.save(folder/'plan.json',plan)
    return {'plan':str(folder/'plan.json'),'sha256':b.sha(folder/'plan.json'),'authorized':False}


def set_case(case):
    b.INPUT,b.CONFIG=case['input_file'],case['config_file']
    b.STATIC=b.ROOT/case['static_size_file']


def worker(ticket_path,token):
    preliminary=b.read(ticket_path)
    b.require(preliminary['job'] in JOBS,'JOB_SCOPE')
    plan=b.read(preliminary['plan'])
    case=plan['cases'][preliminary['job']['case']]
    set_case(case)
    if preliminary['mode']=='method':return _worker(ticket_path,token)
    ticket,plan=b.validate_ticket(ticket_path,token)
    folder=Path(ticket_path).parent/'worker';folder.mkdir()
    sys.path.insert(0,str(b.EXP))
    from timing import MethodBudget
    from thermal import Exhausted,evaluate_candidate
    from schedules import validate_schedule
    from research.chapter3_method_entry_executor.common import inspect_safe_receipt
    from research.chapter3_experiments.thermal_limit_ablation import summarize_post
    budget=MethodBudget(60);budget.start,budget.deadline=ticket['origin'],ticket['scientific_deadline']
    result=dict(state='UNRESOLVED',status='NORMAL_TIME_LIMIT',error=None,job=ticket['job'],
        plan_sha256=ticket['plan_sha256'],origin=budget.start,scientific_deadline=budget.deadline)
    try:
        budget.check()
        source=Path(ticket['output'])/'slots'/(ticket['job']['id']+'__method')/'worker/raw_result.json'
        b.require(b.sha(source)==ticket['method_receipt_sha256'],'POST_SOURCE_DRIFT')
        raw=b.read(source);planning=b.read(b.ROOT/case['input_file'])
        original=b.read(b.ROOT/case['posterior_file']);config=b.read(b.ROOT/case['config_file'])
        previous=inspect_safe_receipt(planning,raw,600)
        b.require(previous['preserved'],'NO_COMPLETE_PLANNING_CANDIDATE')
        candidate=previous['candidate']
        b.require(validate_schedule(original,candidate)['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED','POST_SCHEDULE_INVALID')
        ev=evaluate_candidate(original,candidate,config['accuracy_targets'],budget)
        b.require(b.sha(source)==ticket['method_receipt_sha256'],'POST_SOURCE_CHANGED')
        failure=b.receipt_failure(ev)
        if failure:
            b.save(folder/'evaluation_failure.json',ev)
            raise RuntimeError('POST_TECHNICAL_FAILURE:'+failure)
        diagnostic=summarize_post(original,candidate,ev,cutoff_s=60)
        checked=inspect_safe_receipt(original,dict(safe_candidate=candidate,evaluation=ev,
            safe_upper_bound_J=ev.get('safe_upper_bound_J')),60)
        state=diagnostic['state']
        if state=='SAFE' and not checked['preserved']:
            b.require(ev.get('completed_at_elapsed_s',0)>=60,'INVALID_POST_SAFE_RECEIPT')
            state='UNRESOLVED'
        b.require(state in ('SAFE','UNRESOLVED','THERMAL_VIOLATION'),'UNEXPECTED_POST_STATE')
        if diagnostic['complete_physical_evaluation']:
            a,z=map(b.F,raw['evaluation']['weighted_energy_J'])
            c,d=map(b.F,diagnostic['diagnostic_weighted_energy_J'])
            b.require(max(a,c)<=min(z,d),'POST_ENERGY_CONFLICT')
        post=dict(state=state,evaluation=ev,diagnostic=diagnostic,same_candidate=candidate,
                  method_receipt_sha256=b.sha(source),new_method_result_accepted=False,safe=checked,elapsed_s=budget.elapsed)
        b.save(folder/'post_result.json',post)
        result.update(state=state,status='NORMAL_COMPLETION' if state=='SAFE' else
                      'NORMAL_UNRESOLVED' if state=='UNRESOLVED' else 'SAFETY_FAILURE')
    except Exhausted:
        result.update(state='UNRESOLVED',status='NORMAL_TIME_LIMIT')
    except Exception as error:
        result.update(status='TECHNICAL_FAILURE',error=type(error).__name__+': '+str(error))
    result['worker_elapsed_s']=budget.elapsed
    b.save(folder/'worker_result.json',result)
    return result


def expected_ablation_violation(job,post):
    return (job['case'].endswith('_no_limit') and post.get('status')=='SAFETY_FAILURE'
            and post.get('worker',{}).get('state')=='THERMAL_VIOLATION'
            and not post.get('error') and not post.get('worker',{}).get('error')
            and post.get('returncode')==0 and not post.get('watchdog_fired')
            and post.get('monitor',{}).get('cleanup_verified_observed_tree') is True)


def run(plan_path,approval_path,output):
    from research.chapter3_method_entry_executor.monitor import default_host_probe,host_gate
    plan_path,approval_path,output=map(lambda p:Path(p).resolve(),(plan_path,approval_path,output))
    b.require(output==OUTPUT,'FIXED_OUTPUT_REQUIRED')
    plan=b.authorize(plan_path,approval_path,output)
    b.require(not output.exists(),'NEW_OUTPUT_REQUIRED')
    probe=default_host_probe(b.ROOT);b.require(host_gate(probe)['passed'],'HOST_RESOURCE_GATE_FAILED')
    started=time.monotonic();deadline=started+SCOPE['batch_calendar_seconds']
    b.save(b.RESULTS/'natural_full_claims'/(b.sha(plan_path)+'.json'),dict(output=str(output),
        approval_sha256=b.sha(approval_path),scope=SCOPE,started_monotonic=started,no_resume_or_retry=True))
    output.mkdir(parents=True)
    batch=dict(state='RUNNING',plan_sha256=b.sha(plan_path),methods=[],posts=[],
               not_run=[j['id'] for j in JOBS],error=None,method_attempts=0,post_attempts=0)
    b.save(output/'host_prelaunch.json',probe)
    try:
        for job in JOBS:
            origin=time.monotonic();job_deadline=min(origin+780,deadline)
            b.require(deadline-origin>=780,'INSUFFICIENT_BATCH_CALENDAR')
            verify_sources(plan)
            probe=default_host_probe(b.ROOT);b.save(output/('host_'+job['id']+'.json'),probe)
            b.require(host_gate(probe)['passed'],'HOST_RESOURCE_GATE_FAILED')
            batch['method_attempts']+=1;batch['not_run'].remove(job['id'])
            record=b.run_slot(plan_path,approval_path,plan,output,job,'method',origin,job_deadline,deadline)
            batch['methods'].append(record);verify_sources(plan)
            b.require(record['status'] in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT',
                        'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'),'METHOD_ABNORMAL_STOP')
            if (record.get('worker',{}).get('safe') or {}).get('preserved'):
                post_origin=time.monotonic();b.require(min(job_deadline,deadline)-post_origin>=75,'INSUFFICIENT_POST_CALENDAR')
                batch['post_attempts']+=1
                post=b.run_slot(plan_path,approval_path,plan,output,job,'post',post_origin,job_deadline,deadline)
                batch['posts'].append(post);verify_sources(plan)
                b.require(post['status'] in ('NORMAL_COMPLETION','NORMAL_UNRESOLVED','NORMAL_TIME_LIMIT',
                    'POST_TIME_LIMIT_UNRESOLVED') or expected_ablation_violation(job,post),'POST_ABNORMAL_STOP')
            b.save(output/'progress'/(job['id']+'.json'),batch)
        batch['state']='COMPLETED'
    except Exception as error:
        batch.update(state='STOPPED',error=type(error).__name__+': '+str(error))
    batch['total_wall_s']=time.monotonic()-started;b.save(output/'batch.json',batch)
    return batch


def configure():
    delivery.configure()
    b.ENTRY=ENTRY;b.WORKER_MODULE='research.chapter3_experiments.closure_entry'
    b.PREPARATION=PREPARATION;b.JOBS=JOBS;b.SCOPE=SCOPE
    b.verify_sources=verify_sources;b.validate_plan=validate_plan;b.freeze=freeze
    b.worker=worker;b.run=run


if __name__=='__main__':
    configure()
    raise SystemExit(b.main())
