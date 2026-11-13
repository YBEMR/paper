"""K108 one-use, six-call paired diagnostic; never resumes or retries research."""
from copy import deepcopy
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import importlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import unittest

from inputs import load_config, build_instance
from heuristic_runner import canonical_hash
from q1_case import CONFIG_SHA, independent_lower_bound
import run_formal_comparison as common

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
RULES=HERE/'prefilter_diagnostic_protocol.json'
REUSED_CORE=('milp.py','milp_coefficients.py','thermal.py','schedules.py',
             'initial_point.py','initial_schedule.py','matlab_bridge.py','solve_model.m')
REFERENCE=HERE/'results/infeasible_audit01/final_common_precheck/checks.json'
TEST_MODULES=('test_prefilter_method','test_prefilter_driver','test_formal_milp','test_solver_consistency')


def stamp():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):return common.save(path,value)


def rules():
    d=json.loads(RULES.read_text(encoding='utf-8'))
    from run_warm_diagnostic import FLAGS
    if (digest(HERE/'config_v01.json')!=CONFIG_SHA or d['source_config_sha256']!=CONFIG_SHA
        or d['problem_ids']!=['base__R1','initial_78__R1','response_R__R1']
        or d['variant_order']!=['current','prefilter'] or d['seconds_per_method']!=300
        or d['expected_calls']!=6 or d['maximum_method_seconds']!=1800
        or d['common_flags']!=FLAGS or d['research_retries']!=0
        or d['worker_cleanup_watchdog_extra_seconds']!=120):
        raise ValueError('fixed overnight scope or original physical input changed')
    return d


def source_paths():
    p=common.source_paths()
    for extra in (RULES,HERE/'prefilter_diagnostic_protocol.md'):
        p[extra.relative_to(REPO).as_posix()]=extra
    return p


def signature():return {n:digest(p) for n,p in source_paths().items()}


def manifest():
    d=rules();c=load_config();identities={};jobs=[]
    for name in d['problem_ids']:
        identities[name]=canonical_hash(build_instance(c,name))
        for variant in d['variant_order']:
            jobs.append({'problem_id':name,'variant':variant,'prefilter_deadlines':variant=='prefilter',
                'method':'milp','seed':None,'seconds':300,'call_id':name+'__'+variant})
    return {'schema_version':d['schema_version'],'protocol_sha256':digest(RULES),
        'jobs':jobs,'input_sha256':identities,'calls':6,'problems':3,
        'maximum_method_seconds':1800,'original_input_config_sha256':CONFIG_SHA,
        'scope':'new paired expression diagnostic only; original 115-call approval not reused'}


def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);m=manifest()
    save(out/'manifest.json',m)
    save(out/'approval.json',{'approved':True,'manifest_sha256':canonical_hash(m),
        'user_confirmation_text':'可以，那你开始吧',
        'confirmed_scope':'preceding overnight six calls: three original R1 conditions, two variants, each 300 seconds; no rerun, extension or new case',
        'recorded_at':stamp(),'source_sha256':signature()})
    print(json.dumps({'prepared_calls':6,'maximum_method_seconds':1800,'out':str(out)}),flush=True)


class RecordedResult(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.records=[]
    def addSuccess(self,t):super().addSuccess(t);self.records.append({'name':t.id(),'passed':True})
    def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'name':t.id(),'passed':False})
    def addError(self,t,e):super().addError(t,e);self.records.append({'name':t.id(),'passed':False})
    def addSkip(self,t,reason):super().addSkip(t,reason);self.records.append({'name':t.id(),'passed':False,'skipped':reason})


def precheck(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);before=signature();start=time.monotonic()
    suite=unittest.TestSuite()
    for mod in TEST_MODULES:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(mod)))
    log=io.StringIO();r=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
    (out/'unit_checks.txt').write_text(log.getvalue(),encoding='utf-8');checks=r.records
    old=json.loads(REFERENCE.read_text(encoding='utf-8'))['source_sha256']
    core={str((HERE/n).relative_to(REPO).as_posix()):digest(HERE/n) for n in REUSED_CORE}
    checks.extend([{'name':'unchanged_physical_evaluator_initialisation_native_core',
        'passed':all(old.get(n)==h for n,h in core.items())},
        {'name':'source_input_rules_unchanged','passed':before==signature()},
        {'name':'six_declared_calls_only','passed':len(manifest()['jobs'])==6}])
    record={'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks,
        'source_sha256':signature(),'manifest_sha256':canonical_hash(manifest()),
        'elapsed_s':time.monotonic()-start,'reused_core_sha256':core,
        'research_calls':0,'native_solver_calls':0,
        'scope':'new wrapper/driver and existing small-domain correctness fixtures only; no original problem or Q1 evaluation'}
    save(out/'checks.json',record)
    for n,p in source_paths().items():
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    print(json.dumps({'passed':record['passed'],'count':len(checks),'out':str(out)}),flush=True)
    if not record['passed']:raise RuntimeError('precheck failed; record retained')


def validate_gate(precheck_record,approval_record,review_record):
    g=json.loads(Path(precheck_record).read_text(encoding='utf-8'))
    a=json.loads(Path(approval_record).read_text(encoding='utf-8'))
    r=json.loads(Path(review_record).read_text(encoding='utf-8'))
    m=manifest();s=signature();fp=canonical_hash(m);checks=g.get('checks',[])
    if (g.get('passed') is not True or not checks or g.get('count')!=len(checks)
        or not all(c.get('passed') is True for c in checks)
        or g.get('source_sha256')!=s or g.get('manifest_sha256')!=fp):
        raise ValueError('passing complete current precheck required')
    if (a.get('approved') is not True or a.get('manifest_sha256')!=fp
        or a.get('source_sha256')!=s or not a.get('user_confirmation_text')):
        raise ValueError('new concrete six-call approval required')
    if (r.get('passed') is not True or r.get('source_sha256')!=s
        or r.get('precheck_record_sha256')!=digest(precheck_record)
        or r.get('manifest_sha256')!=fp):
        raise ValueError('independent current source/precheck review required')
    return m


def claim(approval,m,out):
    path=Path(approval).resolve().with_name(Path(approval).name+'.used.json')
    with path.open('x',encoding='utf-8') as stream:
        json.dump({'manifest_sha256':canonical_hash(m),'out':str(Path(out).resolve()),
            'claimed_at':stamp(),'retries':0},stream,ensure_ascii=False,indent=2)


def worker(job,out,declaration):
    from prefilter_method import execute_prefilter_method
    d=json.loads(Path(declaration).read_text(encoding='utf-8'))
    if signature()!=d['source_sha256'] or job not in d['manifest']['jobs']:
        raise ValueError('worker source or job mismatch')
    bound={}
    def loader(budget):
        c=load_config();i=build_instance(c,job['problem_id'],budget)
        if canonical_hash(i)!=d['manifest']['input_sha256'][job['problem_id']]:
            raise ValueError('frozen input identity mismatch')
        bound.update(independent_lower_bound(i),formed_at_s=budget.elapsed);budget.check()
        return c,i
    result=execute_prefilter_method(loader,out,seconds=job['seconds'],variant=job['variant'])
    i=json.loads((Path(out)/'input_instance.json').read_text(encoding='utf-8'))
    result.update(call_id=job['call_id'],problem_id=job['problem_id'],method='milp',seed=None,
        input_sha256=canonical_hash(i),preprocessing_variant=job['variant'],
        prefilter_deadlines=job['prefilter_deadlines'],independent_lower_bound=bound or None,
        certified_lower_bound_J=bound.get('lower_bound_J'),
        source_signature_unchanged=signature()==d['source_sha256'],
        research_problem='original_full_chain',formal_comparison=False)
    if result.get('safe_candidate') is not None:
        result['safe_evidence_binding']={'input_sha256':canonical_hash(i),
            'candidate_sha256':canonical_hash(result['safe_candidate'])}
    save(Path(out)/'result.json',result)


def technical_check(result,instance,job,expected_hash):
    checked=common.technical_check(result,instance,job['seconds'],job,expected_hash)
    errors=checked['errors']
    if result.get('source_signature_unchanged') is not True:errors.append('source mismatch')
    if result.get('prefilter_deadlines') is not job['prefilter_deadlines']:errors.append('variant mismatch')
    if result.get('preprocessing_variant')!=job['variant']:errors.append('variant identity mismatch')
    if result.get('reason') in ('SOLVER_INTERFACE_ERROR','INITIALISED_SOLVER_INTERFACE_ERROR',
                                'NUMERICAL_CANDIDATE_ANOMALY'):
        errors.append('method numerical/interface error')
    if result.get('candidate_and_cache_shared_between_calls') is not False:
        errors.append('call isolation not recorded')
    if result.get('model_complete'):
        actual=result.get('model_summary',{}).get('formulation',{}).get('prefilter_deadlines',False)
        if actual is not job['prefilter_deadlines']:errors.append('built model prefilter mismatch')
    return {'passed':not errors,'errors':errors,
        'scope':'identity, timing, legality and complete receipt; no win requirement'}


def run(gate,approval,review,out):
    m=validate_gate(gate,approval,review);out=Path(out).resolve()
    if out.exists():raise FileExistsError(str(out))
    claim(approval,m,out);out.mkdir(parents=True,exist_ok=False)
    frozen={'manifest':m,'source_sha256':signature(),'approval_record_sha256':digest(approval),
        'precheck_record_sha256':digest(gate),'review_record_sha256':digest(review),'started_at':stamp()}
    save(out/'declaration.json',frozen)
    for n,p in source_paths().items():
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform()})
    calls=[];save(out/'calls.json',calls)
    for job in m['jobs']:
        if signature()!=frozen['source_sha256']:
            save(out/'stop.json',{'reason':'SOURCE_CHANGED','before':job});break
        with (out/(job['call_id']+'.claim.json')).open('x',encoding='utf-8') as stream:json.dump(job,stream)
        call_out=out/job['call_id'];started_at=stamp();start=time.monotonic();timed_out=False
        print('START '+job['call_id'],flush=True)
        with (out/(job['call_id']+'.stdout.txt')).open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_worker',
                '--job',json.dumps(job),'--out',str(call_out),'--declaration',str(out/'declaration.json')],
                cwd=HERE,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:proc.wait(timeout=job['seconds']+rules()['worker_cleanup_watchdog_extra_seconds'])
            except subprocess.TimeoutExpired:
                timed_out=True
                if sys.platform=='win32':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
                else:proc.kill()
                proc.wait(timeout=30)
        call={'job':job,'started_at':started_at,
            'process_wall_s':time.monotonic()-start,'returncode':proc.returncode,'cleanup_watchdog':timed_out}
        path=call_out/'result.json'
        if not timed_out and proc.returncode==0 and path.is_file():
            try:
                r=json.loads(path.read_text(encoding='utf-8'))
                i=json.loads((call_out/'input_instance.json').read_text(encoding='utf-8'))
                call['technical_check']=technical_check(r,i,job,m['input_sha256'][job['problem_id']])
            except Exception as error:call['technical_check']={'passed':False,'errors':[str(error)]}
        else:call['technical_check']={'passed':False,'errors':['worker failure or cleanup watchdog; no retry']}
        calls.append(call);save(out/'calls.json',calls);print('END '+job['call_id'],flush=True)
        if not call['technical_check']['passed']:
            save(out/'stop.json',{'reason':'TECHNICAL_CHECK_FAILED','call':call});break
    save(out/'source_integrity.json',{'unchanged':signature()==frozen['source_sha256'],
        'finished_at':stamp(),'calls_invoked':len(calls),'calls_expected':6})
    print(json.dumps({'calls_invoked':len(calls),'calls_expected':6,
        'technical_passed':sum(c['technical_check']['passed'] for c in calls),'out':str(out)}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','precheck','run','_worker'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--precheck',type=Path)
    p.add_argument('--approval',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--job');p.add_argument('--declaration',type=Path);a=p.parse_args()
    if a.mode=='prepare':prepare(a.out)
    elif a.mode=='precheck':precheck(a.out)
    elif a.mode=='_worker':worker(json.loads(a.job),a.out,a.declaration)
    else:run(a.precheck,a.approval,a.review,a.out)


if __name__=='__main__':main()
