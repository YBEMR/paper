"""K112 bounded small-domain correctness gate; no optimizer or research run.

Snapshots precede checks. Every named fixture uses the frozen physical
platform. Failed gates are kept, never overwritten. The ceiling is a
correctness-task limit, not a research-method performance budget.
"""
import argparse
import ast
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
REFERENCE='2e72ad6c65fcb31aad337f5eaf5515a9f549fee3'
CONFIG_SHA='615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
SOURCES=('milp.py','initial_point.py','scene_adapter.py','control_policy.py',
    'schedules.py','thermal.py','milp_coefficients.py','inputs.py','start_domain.py',
    'timing.py','matlab_bridge.py','initial_schedule.py','q1_case.py',
    'heuristic_runner.py','heuristic_common.py','heft_method.py','sa_method.py',
    'run_milp_precheck.py','run_thermal_precheck.py','run_precheck.py',
    'run_energy_bound_precheck.py','run_construction_precheck.py',
    'test_control_policy.py','test_auto_milp.py','test_partial_deployment.py',
    'run_auto_milp_precheck.py','config_v01.json')
MODULES=('test_control_policy','test_auto_milp','test_partial_deployment')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')


def definitions(raw):
    return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(raw).body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef))}


def run(out,seconds=240):
    out=out.resolve(); out.relative_to(REPO)
    out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    files=[HERE/name for name in SOURCES]+[HERE.parent/'v1_evaluator/interval.py']
    before={str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in files}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip()
    for p in files:
        target=out/'source_snapshot'/p.relative_to(REPO)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
    baseline={}
    for name in ('milp.py','thermal.py','milp_coefficients.py','schedules.py','control_policy.py'):
        raw=subprocess.check_output(['git','show',REFERENCE+':research/chapter3_experiments/'+name],cwd=REPO)
        target=out/'baseline_snapshot'/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw); baseline[name]=raw
    history=json.loads((HERE/'results/prefilter_protocol01/historical_integrity_before.json').read_text(encoding='utf-8'))['prior_24_archives_sha256']
    old=HERE/'results/formal_comparison01'
    if any(sha(old/name)!=value for name,value in history.items()):
        raise ValueError('Historical archives changed before checks')
    save(out/'declaration.json',{'scope':'small correctness fixtures only; no optimization or research calls',
        'correctness_ceiling_s':seconds,'baseline_commit':REFERENCE,'working_head_before_check':head,
        'source_sha256':before,'config_sha256':CONFIG_SHA,'native_solver_calls':0,
        'research_method_calls':0,'physical_fixture_calls_ceiling':8,
        'model_scope':'fixture_ identities only, at most 6 Stage instances and 3 scenes',
        'method_scope':'MILP formulation/completion and partial scene evaluation; no lifecycle or performance claim'})
    records=[]; stream=io.StringIO(); native_attempts=[]; model_calls=[]; physical_calls=[]

    class Result(unittest.TextTestResult):
        def startTest(self,test):
            if time.monotonic()-start>=seconds: raise TimeoutError('Correctness deadline')
            super().startTest(test)
        def addSuccess(self,test):
            records.append({'name':test.id(),'passed':True}); super().addSuccess(test)
        def addFailure(self,test,error):
            records.append({'name':test.id(),'passed':False,'kind':'failure'}); super().addFailure(test,error)
        def addError(self,test,error):
            records.append({'name':test.id(),'passed':False,'kind':'error'}); super().addError(test,error)
        def addSubTest(self,test,subtest,error):
            if error is not None: records.append({'name':subtest.id(),'passed':False,'kind':'subtest'})
            super().addSubTest(test,subtest,error)

    error=None; outcome=None
    try:
        suite=unittest.TestLoader().loadTestsFromNames(MODULES)
        import milp, thermal, scene_adapter, test_control_policy
        original_model=milp.Model.__init__; original_physical=thermal.evaluate_piecewise
        def guarded_model(self,instance,*args,**kwargs):
            if (not instance['id'].startswith('fixture_') or len(instance['scenarios'])>3 or
                sum(len(s['stage_instances']) for s in instance['scenarios'])>6):
                raise AssertionError('Only declared small fixture models are permitted')
            model_calls.append({'id':instance['id'],'scenes':len(instance['scenarios'])})
            return original_model(self,instance,*args,**kwargs)
        def forbidden_native(*args,**kwargs):
            native_attempts.append('attempted'); raise AssertionError('Optimizer startup forbidden')
        def recorded_physical(*args,**kwargs):
            if len(physical_calls)>=8: raise AssertionError('Physical fixture call ceiling')
            record={'scene_id':kwargs.get('scene_id'),'call':len(physical_calls)+1}
            physical_calls.append(record)
            result=original_physical(*args,**kwargs)
            record.update(state=result['state'],complete=result.get('complete'))
            return result
        with ExitStack() as stack:
            stack.enter_context(patch('milp.Model.__init__',guarded_model))
            stack.enter_context(patch('matlab_bridge.MatlabSession.__init__',forbidden_native))
            stack.enter_context(patch('scipy.optimize.linprog',forbidden_native))
            stack.enter_context(patch('scipy.optimize.milp',forbidden_native))
            stack.enter_context(patch.object(thermal,'evaluate_piecewise',recorded_physical))
            stack.enter_context(patch.object(scene_adapter,'evaluate_piecewise',recorded_physical))
            stack.enter_context(patch.object(test_control_policy,'evaluate_piecewise',recorded_physical))
            outcome=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
    except Exception:
        error=traceback.format_exc()
    (out/'unit_checks.txt').write_text(stream.getvalue(),encoding='utf-8')
    saved={}
    for name in MODULES:
        module=sys.modules.get(name)
        saved[name]=getattr(module,'RECORDS',getattr(module,'PRECHECK_RECORDS',{}))
    save(out/'fixture_records.json',saved)
    unchanged=lambda n: (HERE/n).read_bytes()==baseline[n]
    integrity={
        'source_unchanged_during_checks':all(sha(REPO/name)==value for name,value in before.items()),
        'config_unchanged':sha(HERE/'config_v01.json')==CONFIG_SHA,
        'continuous_evaluator_entire_source_unchanged':unchanged('thermal.py'),
        'coefficient_enclosure_entire_source_unchanged':unchanged('milp_coefficients.py'),
        'common_schedule_control_unchanged':unchanged('schedules.py'),
        'control_policy_unchanged':unchanged('control_policy.py'),
        'historical24_unchanged':all(sha(old/name)==value for name,value in history.items()),
        'no_native_or_optimizer_startup':not native_attempts,
        'fixture_models_only':all(c['id'].startswith('fixture_') for c in model_calls),
        'physical_call_ceiling':len(physical_calls)<=8,
        'reference_pinned':getattr(sys.modules.get('test_auto_milp'),'REFERENCE',None)==REFERENCE,
        'correctness_ceiling_respected':time.monotonic()-start<seconds}
    records.extend({'name':k,'passed':v} for k,v in integrity.items())
    passed=bool(records) and not error and outcome is not None and outcome.wasSuccessful() and all(r['passed'] for r in records)
    summary={'passed':passed,'count':len(records),'checks':records,
        'unit_test_methods':outcome.testsRun if outcome else 0,'runner_error':error,
        'source_sha256':before,'baseline_commit':REFERENCE,'original_historical24_sha256':history,
        'working_head_before_check':head,'elapsed_s':time.monotonic()-start,
        'model_calls':model_calls,'physical_calls':physical_calls,
        'native_attempts':native_attempts,'native_solver_calls':0,'research_method_calls':0,
        'scope':'small correctness only; neither full method readiness nor energy improvement'}
    save(out/'checks.json',summary)
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform(),
        'checked_at_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'passed':passed,'checks':len(records),'unit_methods':summary['unit_test_methods'],
                      'elapsed_s':summary['elapsed_s'],'out':str(out)}),flush=True)
    return passed


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
