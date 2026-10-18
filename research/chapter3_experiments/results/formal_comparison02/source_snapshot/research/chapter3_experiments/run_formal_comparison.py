"""Prepare, precheck and later run the explicitly approved chapter-3 batch.

No formal invocation is enabled by a passing precheck alone. A separate record
of the user's concrete batch approval must name this exact reviewed manifest.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import unittest
import uuid

from inputs import load_config, build_instance
from q1_case import independent_lower_bound, CONFIG_SHA
from heuristic_runner import canonical_hash

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE/'formal_comparison_protocol.json'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    """Publish complete JSON atomically, retaining old evidence on I/O failure.

    Never open the existing target for truncation. A failed publication leaves
    the previous target and the distinct pending file available for diagnosis;
    it is still an error, never an implicit retry or a successful invocation.
    """
    path=Path(path)
    data=(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,default=str)+'\n').encode('utf-8')
    pending=path.with_name('.'+path.name+'.pending-'+uuid.uuid4().hex)
    with pending.open('xb') as stream:
        stream.write(data)
    pending.replace(path)


def protocol():
    rules = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    if digest(HERE/'config_v01.json') != CONFIG_SHA or rules['source_config_sha256'] != CONFIG_SHA:
        raise ValueError('frozen physical input changed')
    from sa_method import algorithm_parameters
    from sa_method import PROTOCOL as sa_version
    from heft_method import RULE_VERSION as heft_version
    from run_warm_diagnostic import FLAGS
    if (rules['milp_flags']!={**FLAGS,'prefilter_deadlines':False}
        or rules['heft_rules']!=heft_version or rules['sa_rules']!=sa_version):
        raise ValueError('implementation/predeclared rule or MILP flag mismatch')
    actual = algorithm_parameters()
    if any(actual.get(key) != value for key,value in rules['sa_parameters'].items()):
        raise ValueError('SA implementation/predeclared parameter mismatch')
    return rules


def source_paths():
    files = sorted(HERE.glob('*.py')) + [HERE/'solve_model.m',HERE/'config_v01.json',PROTOCOL,
        HERE/'formal_comparison_protocol.md', HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix():p for p in files}


def signature():
    return {key:digest(p) for key,p in source_paths().items()}


def manifest():
    rules = protocol()
    config=load_config()
    identities={}
    jobs = []
    for condition in rules['condition_ids']:
        for sample in rules['sample_ids']:
            problem = condition+'__'+sample
            identities[problem]=canonical_hash(build_instance(config,problem))
            for method in rules['method_order']:
                if method == 'assignment' and condition not in rules['assignment_condition_ids']: continue
                for seed in rules['sa_seeds'] if method == 'sa' else [None]:
                    jobs.append({'problem_id':problem,'method':method,'seed':seed,
                        'seconds':rules['seconds_per_method_proposed'],
                        'call_id':problem+'__'+method+('' if seed is None else '__seed'+str(seed))})
    if len(jobs) != rules['expected_calls'] or len({j['problem_id'] for j in jobs}) != rules['expected_problems']:
        raise ValueError('batch counts changed')
    if len({j['call_id'] for j in jobs}) != len(jobs): raise ValueError('duplicate call identity')
    return {'schema_version':rules['schema_version'],'protocol_sha256':digest(PROTOCOL),
        'jobs':jobs,'input_sha256':identities,'problems':rules['expected_problems'],'calls':len(jobs),
        'maximum_method_seconds':sum(j['seconds'] for j in jobs),
        'first_technical_case':rules['first_technical_case'],
        'execution_authorization': 'separate user approval required; proposal alone is not a run'}


def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    proposed=manifest()
    save(out/'proposed_manifest.json',proposed)
    save(out/'approval_record_example.json',{'approved':False,
        'manifest_sha256':canonical_hash(proposed),'user_confirmation_text':None,
        'scope':'example only; fill only after actual concrete user confirmation'})
    save(out/'source_sha256.json',signature())
    print(json.dumps({'calls':proposed['calls'],'problems':proposed['problems'],
        'maximum_method_seconds':proposed['maximum_method_seconds'],'authorized_to_run':False}),flush=True)


def technical_check(result, instance, seconds, expected_job=None, expected_input_sha256=None):
    """Saved-evidence validation, not an additional thermal search or proof."""
    from schedules import validate_schedule
    errors=[]
    actual_identity=canonical_hash(instance)
    if expected_job is not None:
        if (result.get('call_id')!=expected_job['call_id']
            or result.get('problem_id')!=expected_job['problem_id']
            or instance.get('id')!=expected_job['problem_id']
            or result.get('method')!=expected_job['method'] or result.get('seed')!=expected_job['seed']):
            errors.append('call/problem/method/seed identity mismatch')
        if (expected_input_sha256 is None or actual_identity!=expected_input_sha256
            or result.get('input_sha256')!=expected_input_sha256):
            errors.append('frozen derived input identity mismatch')
    if result.get('reason') in ('INTERFACE_ERROR','INTERFACE_OR_CONSISTENCY_ERROR'):
        errors.append('method interface error')
    if result.get('state')=='SAFE':
        candidate=result.get('safe_candidate'); receipt=result.get('evaluation') or {}
        if not candidate or validate_schedule(instance,candidate)['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED':
            errors.append('saved SAFE schedule is not legal')
        energy=receipt.get('weighted_energy_J');at=receipt.get('completed_at_elapsed_s')
        if (receipt.get('state')!='SAFE' or not receipt.get('rankable_energy') or not energy
            or not isinstance(at,(int,float)) or isinstance(at,bool) or not 0<=at<seconds):
            errors.append('missing complete in-budget SAFE receipt')
        elif F(result['safe_upper_bound_J']) != F(energy[1]): errors.append('SAFE U differs from receipt')
        if receipt.get('problem_id')!=instance.get('id'):
            errors.append('SAFE receipt belongs to a different problem')
        if expected_job is not None and result.get('safe_evidence_binding')!={
            'input_sha256':actual_identity,'candidate_sha256':canonical_hash(candidate)}:
            errors.append('saved SAFE evidence binding mismatch')
        scene_ids={sc['id'] for sc in instance['scenarios']}
        if set(receipt.get('scenes',{}))!=scene_ids:
            errors.append('SAFE receipt does not cover all scenarios')
        elif any(sc.get('state')!='SAFE' or not sc.get('complete')
                 or F(sc.get('covered_until_s','-1'))!=F(instance['window_ms'])/1000
                 for sc in receipt['scenes'].values()):
            errors.append('SAFE receipt does not cover the complete window')
    elif result.get('safe_upper_bound_J') is not None:
        errors.append('non-SAFE result has a usable U')
    if result.get('timing',{}).get('limit_s') != seconds: errors.append('method budget mismatch')
    return {'passed':not errors,'errors':errors,
        'scope':'identity/legality/receipt completeness; success or algorithm wins not required'}


class RecordedResult(unittest.TextTestResult):
    def __init__(self,*a,**k): super().__init__(*a,**k);self.records=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.records.append({'name':test.id(),'passed':True})
    def addFailure(self,test,err):
        super().addFailure(test,err);self.records.append({'name':test.id(),'passed':False,'kind':'failure'})
    def addError(self,test,err):
        super().addError(test,err);self.records.append({'name':test.id(),'passed':False,'kind':'error'})


def precheck(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();before=signature(); checks=[]
    save(out/'proposed_manifest.json',manifest())
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform()})
    for key,path in source_paths().items():
        target=out/'source_snapshot'/key;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    def check(name,action):
        try:
            result=action()
            if result is False: raise AssertionError(name)
            checks.append({'name':name,'passed':True})
            return result
        except Exception as error:
            checks.append({'name':name,'passed':False,'error':f'{type(error).__name__}: {error}'})
            return None
    import importlib
    suite=unittest.TestSuite()
    for name in ('test_heuristic_common','test_heft_method','test_sa_method','test_formal_milp',
                 'test_formal_driver','test_q1_domain'):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
    log=io.StringIO()
    tested=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
    checks.extend(tested.records)
    (out/'unit_checks.txt').write_text(log.getvalue(),encoding='utf-8')
    # Only an existing one-Stage correctness fixture receives real continuous
    # evaluation here; no original research problem or Q1 answer is computed.
    from run_milp_precheck import fixtures
    from heuristic_runner import execute_heuristic
    config=load_config(); fixture,starts=fixtures(config)['one_stage_energy']
    fixture['start_domain']={'version':1,'kind':'explicit_grid_subset','by_scene_stage_ms':starts}
    def loader(budget): budget.check();return deepcopy(config),deepcopy(fixture)
    for method,seconds,seed in [('heft',45,None),('sa',8,101)]:
        result=check('tiny/'+method+'/complete_continuous_receipt',lambda method=method,seconds=seconds,seed=seed:
            execute_heuristic(loader,out/('tiny_'+method),method=method,seconds=seconds,seed=seed))
        if result is not None:
            check('tiny/'+method+'/safe_and_same_window',lambda r=result,s=seconds:
                r['state']=='SAFE' and technical_check(r,fixture,s)['passed'])
    after=signature()
    checks.append({'name':'frozen/source_input_rules_unchanged','passed':before==after})
    record={'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks,
        'source_sha256':after,'manifest_sha256':canonical_hash(manifest()),
        'precheck_elapsed_s':time.monotonic()-started,
        'research_problem_or_Q1_evaluated':False,'matlab_or_native_solver_run':False,
        'scope':'changed interfaces and existing correctness fixtures only; native bridge history reused'}
    save(out/'checks.json',record)
    print(json.dumps({'passed':record['passed'],'count':len(checks),'out':str(out)}),flush=True)
    if not record['passed']: raise RuntimeError('failed precheck retained')


def validate_gate(precheck_record,approval_record):
    gate=json.loads(Path(precheck_record).read_text(encoding='utf-8'))
    approval=json.loads(Path(approval_record).read_text(encoding='utf-8'))
    current=manifest();fingerprint=canonical_hash(current)
    checks=gate.get('checks',[])
    if (not checks or gate.get('count')!=len(checks) or gate.get('passed') is not True
        or not all(c.get('passed') is True for c in checks)
        or gate.get('source_sha256')!=signature() or gate.get('manifest_sha256')!=fingerprint):
        raise ValueError('current complete passing precheck is required')
    if (approval.get('approved') is not True or approval.get('manifest_sha256')!=fingerprint
        or not isinstance(approval.get('user_confirmation_text'),str) or not approval['user_confirmation_text'].strip()):
        raise ValueError('concrete user batch approval is not recorded')
    return current


def claim_approval(approval_record,current,out):
    """Consume this approval once across output directories, including interrupts."""
    approval_record=Path(approval_record).resolve()
    claim=approval_record.with_name(approval_record.name+'.used.json')
    with claim.open('x',encoding='utf-8') as stream:
        json.dump({'manifest_sha256':canonical_hash(current),
            'approval_record_sha256':digest(approval_record),
            'out':str(Path(out).resolve()),'retries':0,
            'scope':'one batch invocation; interruption does not reset authorization'},stream,indent=2)
    return claim


def worker(job,out,declaration):
    frozen=json.loads(Path(declaration).read_text(encoding='utf-8'))
    if frozen['source_sha256']!=signature() or job not in frozen['manifest']['jobs']:
        raise ValueError('worker source/job identity mismatch')
    bound={}
    def loader(budget):
        config=load_config();instance=build_instance(config,job['problem_id'],budget)
        if canonical_hash(instance)!=frozen['manifest']['input_sha256'][job['problem_id']]:
            raise ValueError('loaded input differs from frozen problem')
        if job['method'] in ('milp','assignment'):
            value=independent_lower_bound(instance);budget.check()
            bound.update(value,formed_at_s=budget.elapsed)
        return config,instance
    if job['method'] in ('milp','assignment'):
        from formal_milp import execute_formal_milp
        result=execute_formal_milp(loader,out,seconds=job['seconds'],
            feedback_kind='conditional' if job['method']=='milp' else 'assignment')
        result.update(independent_lower_bound=bound or None,certified_lower_bound_J=bound.get('lower_bound_J'))
    else:
        from heuristic_runner import execute_heuristic
        result=execute_heuristic(loader,out,method=job['method'],seconds=job['seconds'],seed=job['seed'])
    saved_instance=json.loads((Path(out)/'input_instance.json').read_text(encoding='utf-8'))
    result.update(call_id=job['call_id'],problem_id=job['problem_id'],method=job['method'],seed=job['seed'],
        input_sha256=canonical_hash(saved_instance),
        research_problem='original_full_chain',source_signature_unchanged=frozen['source_sha256']==signature())
    if result.get('safe_candidate') is not None:
        # Archival identity only; creates no new physical or timing evidence.
        result['safe_evidence_binding']={'input_sha256':canonical_hash(saved_instance),
            'candidate_sha256':canonical_hash(result['safe_candidate'])}
    save(Path(out)/'result.json',result)


def run(precheck_record,approval_record,out):
    current=validate_gate(precheck_record,approval_record)
    return execute_batch(current,precheck_record,approval_record,out)


def execute_batch(current,precheck_record,approval_record,out):
    """Execute a manifest already validated by the full or continuation gate."""
    out=Path(out).resolve()
    if out.exists(): raise FileExistsError(str(out))
    claim_approval(approval_record,current,out)
    out.mkdir(parents=True,exist_ok=False)
    frozen={'manifest':current,'source_sha256':signature(),'approval_record_sha256':digest(approval_record),
        'precheck_record_sha256':digest(precheck_record),'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    if current.get('continuation_only'):
        frozen.update(prior_batch_identity=current['prior_batch_identity'],
            source_version_change='Archival atomic publication and continuation selection only; algorithms, input and safety unchanged.')
    save(out/'declaration.json',frozen)
    for key,path in source_paths().items():
        target=out/'source_snapshot'/key;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform()})
    calls=[];save(out/'calls.json',calls)
    first=current['first_technical_case']
    for job in current['jobs']:
        if signature()!=frozen['source_sha256']:
            save(out/'stop.json',{'reason':'SOURCE_CHANGED','before':job});break
        claim=out/(job['call_id']+'.claim.json')
        with claim.open('x',encoding='utf-8') as stream: json.dump(job,stream)
        started=time.monotonic();call_out=out/job['call_id']
        print('START '+job['call_id'],flush=True)
        with (out/(job['call_id']+'.stdout.txt')).open('w',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'_worker','--job',json.dumps(job),
                '--out',str(call_out),'--declaration',str(out/'declaration.json')],cwd=HERE,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        call={'job':job,'process_wall_s':time.monotonic()-started,'returncode':p.returncode}
        if p.returncode==0 and (call_out/'result.json').is_file():
            result=json.loads((call_out/'result.json').read_text(encoding='utf-8'))
            instance=json.loads((call_out/'input_instance.json').read_text(encoding='utf-8'))
            call['technical_check']=technical_check(result,instance,job['seconds'],job,
                current['input_sha256'][job['problem_id']])
            call['technical_check']['passed'] &= result.get('source_signature_unchanged') is True
        else: call['technical_check']={'passed':False,'errors':['worker failed; no retry']}
        calls.append(call);save(out/'calls.json',calls)
        print('END '+job['call_id'],flush=True)
        if not call['technical_check']['passed']:
            save(out/'stop.json',{'reason':'TECHNICAL_CHECK_FAILED','call':call});break
        first_jobs=[j for j in current['jobs'] if j['problem_id']==first]
        if len(calls)==len(first_jobs):
            name='continuation_entry_technical_check.json' if current.get('continuation_only') else 'first_pair_technical_check.json'
            save(out/name,{'passed':True,'calls':len(calls),
                'scope':('current continuation entries only; original eight-call failure unchanged'
                    if current.get('continuation_only') else 'technical acceptance only; no SAFE/energy advantage required')})
    save(out/'source_integrity.json',{'unchanged':signature()==frozen['source_sha256']})
    summarize(out)


def summarize(out):
    out=Path(out);rows=[]
    calls=json.loads((out/'calls.json').read_text(encoding='utf-8'))
    for call in calls:
        job=call['job'];path=out/job['call_id']/'result.json'
        if not path.is_file(): continue
        r=json.loads(path.read_text(encoding='utf-8'))
        diag=r.get('diagnostic',{})
        rows.append({'call_id':job['call_id'],'problem_id':job['problem_id'],'method':job['method'],
            'seed':job['seed'],'state':r['state'],'reason':r['reason'],
            'safe_upper_bound_J':r.get('safe_upper_bound_J'),'certified_lower_bound_J':r.get('certified_lower_bound_J'),
            'first_safe_at_s':r.get('first_safe_at_s',r.get('first_initial_safe_s',diag.get('first_safe_receipt_s'))),
            'first_MILP_safe_at_s':diag.get('first_safe_receipt_s'),
            'method_wall_s':r['timing']['method_elapsed_s'],'process_wall_s':call['process_wall_s'],
            'budget_exhausted':r.get('budget_exhausted',r['timing']['method_elapsed_s']>=job['seconds']),
            'coverage_complete':r.get('coverage_complete',False),
            'initial_U_J':r.get('initial_safe_upper_bound_J'),'MILP_U_J':r.get('milp_safe_upper_bound_J'),
            'strict_seed_improvement':r.get('strict_energy_improvement_certified'),
            'feedback_rows':sum(f.get('rows_added',0) for f in r.get('feedback',[])),
            'technical_check_passed':call['technical_check']['passed']})
    if rows:
        with (out/'summary.csv').open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save(out/'summary.json',{'rows':rows,'calls_completed':len(rows),
        'scope':'all call states; SAFE energies only; do not pool seeds as independent workloads',
        'poststop_only':True})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','precheck','run','summarize','_worker'])
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--precheck-record',type=Path);parser.add_argument('--approval-record',type=Path)
    parser.add_argument('--declaration',type=Path);parser.add_argument('--job')
    args=parser.parse_args()
    if args.mode=='prepare':prepare(args.out)
    elif args.mode=='precheck':precheck(args.out)
    elif args.mode=='run':run(args.precheck_record,args.approval_record,args.out)
    elif args.mode=='summarize':summarize(args.out)
    else:worker(json.loads(args.job),args.out,args.declaration)
