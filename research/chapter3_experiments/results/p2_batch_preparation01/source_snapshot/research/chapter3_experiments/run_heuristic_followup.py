"""K144: prepare/mock-check an independent HEFT then SA101 followup.

No old claim or result is rewritten. Real execution requires an explicit later
--execution-authorized flag and consumes the new two-call claim once.
"""
import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
import unittest
from unittest.mock import patch

from completion_metrics import build_completion_metrics
from execution_status import classify_execution

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BASE=HERE/'results/fair_comparison_preparation01/declaration.json'
PLAN=HERE/'results/budget_end_review01/followup_protocol.json'
TARGET=HERE/'results/heft_sa_followup01'
GLOBAL_CLAIM=HERE/'results/heuristic_followup_claim01.json'
PROTOCOL='K144-independent-HEFT-SA101-status-timing-wrapper-v1'
CHECK_PROTOCOL='K144-mocked-status-timing-followup-precheck-v1'
NEW=('execution_status.py','test_execution_status.py','completion_metrics.py',
     'test_completion_metrics.py','run_heuristic_followup.py','test_heuristic_followup.py')
SECONDS=300

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def save(p,value):
    p=Path(p);pending=p.with_suffix(p.suffix+'.pending')
    with pending.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False,default=str);stream.write('\n')
    pending.replace(p)
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def jobs():return [{'id':'heft','method':'heft','seed':None},{'id':'sa101','method':'sa','seed':101}]
def local(p):
    p=Path(p).resolve();p.relative_to(REPO)
    if p!=TARGET.resolve():raise ValueError('Only the declared independent output is allowed')
    return p
def sources():
    paths=list(HERE.glob('*.py'))+[HERE/'config_v01.json',HERE/'solve_model.m',HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}
def source_gate():
    base=read(BASE)['source_sha256'];current=sources()
    extra={(HERE/n).relative_to(REPO).as_posix() for n in NEW}
    if len(base)!=159 or any(current.get(n)!=h for n,h in base.items()) or set(current)!=set(base)|extra:
        raise ValueError('Unchanged inherited159 sources and only the six K144 additions required')
    return current
def entry_points():
    from heuristic_runner import execute_heuristic
    return {'heuristic':execute_heuristic}
def fresh_input(budget=None):
    from run_neighborhood_diagnostic import fresh_input as fresh
    return fresh(budget)
def rules():
    return {'protocol':PROTOCOL,'jobs':jobs(),'method_call_limit':2,'per_method_budget_s':SECONDS,
        'research_scope':'new independent HEFT/SA batch; never splice into a completed K142 four-method round',
        'auto_low_opt_in':True,'retry_allowed':False,'extend_budget_allowed':False,
        'new_execution_authorization_required':True,'original159_unchanged':True,
        'normal_deadline_can_continue_after_isolation':True,'technical_or_unresolved_stops_remaining':True,
        'matlab_used':False,'candidate_cache_or_witness_shared':False,
        'method_clock':'unchanged root entry budget; all input/search/evaluation billed',
        'post_method_scope':'stored-receipt verification and extraction only; no new decode, heat, U or search'}
def check_gate(path,current):
    g=read(path)
    if (g.get('protocol')!=CHECK_PROTOCOL or g.get('passed') is not True
        or g.get('source_sha256')!=current or g.get('source_unchanged') is not True
        or g.get('errors')!=0 or g.get('failures')!=0 or g.get('skipped')!=0
        or g.get('error') is not None or not g.get('tests_run')
        or any(g.get('blocked_calls',{'missing':1}).values())
        or any(g.get(k)!=0 for k in ('research_calls','native_calls','physical_models','thermal_evaluations'))):
        raise ValueError('Matching complete zero-call offline precheck required')
    return g
def scene_spec(instance):
    nodes=instance['platform']['node_order']
    return {s['id']:{'weight':s['weight'],'window_s':str(F(instance['window_ms'])/1000),
        'limits':dict(zip(nodes,s['maximum_temperature_degC']))} for s in instance['scenarios']}

def prepare(out,checks):
    out=local(out)
    if out.exists() or GLOBAL_CLAIM.exists():raise FileExistsError('Prepared/claimed already; no alternate run')
    current=source_gate();check_gate(checks,current)
    plan,base=read(PLAN),read(BASE)
    if plan.get('method_order')!=jobs() or plan.get('per_method_root_budget_s')!=SECONDS:
        raise ValueError('K143 planned methods/budget changed')
    raw,config,instance=fresh_input()
    identities=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(canonical,(raw,config,instance))))
    if identities!=base['input_identities'] or identities!=plan['input_identities']:
        raise ValueError('Frozen original input changed')
    imported=time.monotonic();entry_points();import_s=time.monotonic()-imported
    out.mkdir(parents=True);(out/'claims').mkdir()
    for name,value in zip(('input_raw.json','input_config.json','input_instance.json'),(raw,config,instance)):save(out/name,value)
    for name,h in current.items():
        target=out/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,target)
        if sha(target)!=h:raise ValueError('Source changed while snapshotting')
    shutil.copyfile(checks,out/'precheck.json')
    save(out/'declaration.json',{**rules(),**identities,'input_identities':identities,
        'source_sha256':current,'original159_manifest_sha256':sha(BASE),'K143_plan_sha256':sha(PLAN),
        'precheck_sha256':sha(out/'precheck.json'),'scene_spec':scene_spec(instance),
        'input_file_sha256':{n:sha(out/n) for n in ('input_raw.json','input_config.json','input_instance.json')},
        'declared_at_utc':now()})
    save(out/'ledger.json',{'protocol':PROTOCOL,'state':'DECLARED','consumed':0,'reserved_method_budget_s':0,'calls':[]})
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform(),
        'preparation_entry_import_wall_s':import_s,'scope':'preparation only; no method/physical/native calls'})
    admission(out)
    return {'prepared':True,'source_files':len(current),'research_calls':0}

def admission(out):
    out=local(out);d=read(out/'declaration.json');current=source_gate()
    if any(d.get(k)!=v for k,v in rules().items()):raise ValueError('Frozen wrapper rules changed')
    if d.get('source_sha256')!=current or d.get('original159_manifest_sha256')!=sha(BASE) or d.get('K143_plan_sha256')!=sha(PLAN):
        raise ValueError('Source/basis/protocol changed')
    if sha(out/'precheck.json')!=d['precheck_sha256']:raise ValueError('Precheck bytes changed')
    check_gate(out/'precheck.json',current)
    for name,h in current.items():
        if sha(out/'source_snapshot'/name)!=h:raise ValueError('Frozen source snapshot changed')
    for name,h in d['input_file_sha256'].items():
        if sha(out/name)!=h:raise ValueError('Frozen input bytes changed')
    for name,key in [('input_raw.json','raw_config_sha256'),('input_config.json','config_sha256'),('input_instance.json','input_sha256')]:
        if canonical(read(out/name))!=d[key]:raise ValueError('Frozen input identity changed')
    if d['input_identities']!=read(BASE)['input_identities'] or scene_spec(read(out/'input_instance.json'))!=d['scene_spec']:
        raise ValueError('Original domain/scenes changed')
    return d

def receipt_issues(evaluation,candidate,declaration):
    """Inspect already produced proof fields; never recompute a trajectory."""
    errors=[];spec=declaration['scene_spec']
    try:
        if (evaluation.get('state')!='SAFE' or evaluation.get('rankable_energy') is not True
            or evaluation.get('problem_id')!='base__R1'
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

def execute(job,out,declaration,entries):
    if job not in jobs():raise ValueError('Unknown frozen followup method')
    identity={'input_verified':None}
    def loader(budget):
        raw,config,instance=fresh_input(budget)
        actual=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(canonical,(raw,config,instance))))
        if actual!=declaration['input_identities']:
            identity['input_verified']=False
            raise ValueError('Fresh billed input changed')
        identity['input_verified']=True;budget.check()
        return config,instance
    value=entries['heuristic'](loader,out/job['id'],method=job['method'],seed=job['seed'],seconds=SECONDS,allow_auto_low=True)
    return value,identity

def run(out,*,execution_authorized=False):
    out=local(out);ledger=read(out/'ledger.json')
    if (ledger.get('state')!='DECLARED' or ledger.get('consumed')!=0 or ledger.get('calls')
        or GLOBAL_CLAIM.exists() or any((out/'claims'/(j['id']+'.json')).exists() for j in jobs())):
        raise FileExistsError('Independent followup already claimed/consumed; no restart')
    if execution_authorized is not True:raise PermissionError('A later explicit execution authorization is required')
    d=admission(out);started=time.monotonic();imported=time.monotonic();entries=entry_points()
    save(out/'runtime_imports.json',{'wall_s':time.monotonic()-imported,'scope':'imports only; zero candidates/heat/precomputation'})
    with GLOBAL_CLAIM.open('x',encoding='utf-8') as stream:json.dump({'protocol':PROTOCOL,'out':str(out.relative_to(REPO)),'no_retry':True,'claimed_utc':now()},stream)
    okay=True
    for job in jobs():
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x',encoding='utf-8') as stream:json.dump({**job,'budget_s':SECONDS,'claimed_utc':now()},stream)
        row={**job,'state':'RUNNING','started_utc':now()};ledger['calls'].append(row)
        ledger.update(state='RUNNING',consumed=ledger['consumed']+1,reserved_method_budget_s=ledger['reserved_method_budget_s']+SECONDS)
        save(out/'ledger.json',ledger)
        result=None;identity={'input_verified':None};errors=[];method_start=time.monotonic()
        try:result,identity=execute(job,out,d,entries)
        except BaseException:errors.append(traceback.format_exc())
        returned=time.monotonic()-method_start
        source_valid=True
        try:admission(out)
        except Exception:source_valid=False;errors.append(traceback.format_exc())
        post=time.monotonic()
        try:records=result_records(result,d,input_valid=identity['input_verified'],source_valid=source_valid,errors=errors)
        except Exception:
            errors.append(traceback.format_exc());records={'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},'usable_U_J':None,'record_error':errors}
        acceptable=records['execution']['execution_status'] in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT','NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        row.update(state='COMPLETED' if acceptable else 'BLOCKED',completed_utc=now(),errors=errors,
            method_return_inclusive_wall_s=returned,source_identity_valid=source_valid,**records)
        save(out/'claims'/(job['id']+'_result.json'),row)
        row['post_method_record_wall_s']=time.monotonic()-post
        ledger['state']='RUNNING' if acceptable else 'BLOCKED';save(out/'ledger.json',ledger)
        if not acceptable:okay=False;break
    if okay:ledger['state']='COMPLETED';save(out/'ledger.json',ledger)
    save(out/'wrapper_timing.json',{'wall_s':time.monotonic()-started,'scope':'imports, independent method returns, stored-record audit and primary archives; no post-cutoff search'})
    return okay

def precheck(out):
    import subprocess
    import scipy.optimize
    import matlab_bridge
    import milp
    import thermal
    import scene_adapter
    import heuristic_runner
    out=Path(out).resolve();out.relative_to(REPO);out.mkdir(parents=True,exist_ok=False)
    before=source_gate();environment={'python':sys.version,'platform':platform.platform()}
    started=time.monotonic();captured=io.StringIO();result=None;error=None;blocked={}
    def reject(name):
        blocked[name]=0
        def fail(*a,**kw):blocked[name]+=1;raise AssertionError('Offline precheck forbids '+name)
        return fail
    targets=[(subprocess,'Popen'),(scipy.optimize,'milp'),(scipy.optimize,'linprog'),
        (matlab_bridge.MatlabSession,'__init__'),(milp,'build_model'),
        (thermal,'evaluate_candidate'),(thermal,'evaluate_piecewise'),(scene_adapter,'evaluate_piecewise'),
        (heuristic_runner,'execute_heuristic')]
    try:
        with ExitStack() as stack,redirect_stdout(captured),redirect_stderr(captured):
            for obj,name in targets:stack.enter_context(patch.object(obj,name,side_effect=reject(str(obj.__name__)+'.'+name)))
            suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in
                ('test_execution_status','test_completion_metrics','test_heuristic_followup'))
            result=unittest.TextTestRunner(stream=captured,verbosity=2).run(suite)
    except BaseException:error=traceback.format_exc();captured.write(error)
    after=sources();passed=bool(result and result.wasSuccessful() and not result.skipped and not error and before==after and not any(blocked.values()))
    report={'protocol':CHECK_PROTOCOL,'passed':passed,'tests_run':result.testsRun if result else 0,
        'errors':len(result.errors) if result else 1,'failures':len(result.failures) if result else 0,
        'skipped':len(result.skipped) if result else 0,'error':error,'source_sha256':after,
        'source_unchanged':before==after,'blocked_calls':blocked,'elapsed_s':time.monotonic()-started,
        'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0,
        'scope':'six new status/metrics/wrapper files only; unchanged159 inherited, no physical replay'}
    (out/'unittest.txt').write_text(captured.getvalue(),encoding='utf-8')
    save(out/'checks.json',report);save(out/'environment.json',environment)
    for name,h in after.items():
        target=out/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,target)
        if sha(target)!=h:raise ValueError('Source changed while archiving precheck')
    print(json.dumps({k:report[k] for k in ('passed','tests_run','errors','failures','elapsed_s')}),flush=True)
    return passed

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    for name in ('precheck','prepare','run'):m.add_argument('--'+name,action='store_true')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--checks',type=Path);p.add_argument('--execution-authorized',action='store_true')
    a=p.parse_args()
    if a.precheck:raise SystemExit(0 if precheck(a.out) else 1)
    if a.prepare:
        if a.checks is None:p.error('--prepare requires --checks')
        print(json.dumps(prepare(a.out,a.checks)));raise SystemExit(0)
    raise SystemExit(0 if run(a.out,execution_authorized=a.execution_authorized) else 1)
