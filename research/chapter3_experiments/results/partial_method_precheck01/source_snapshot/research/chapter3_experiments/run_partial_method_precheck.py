"""K113 mock gate, then one separately claimed 180 s native correctness call.

No original-scale experiment or formal comparison. Native mode requires a
passing gate with the same source hashes; it starts a fresh process, input,
initial witnesses and MATLAB worker, with no mock receipt/candidate reuse.
"""
import argparse
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
REFERENCE='9327ae272feca4bc5b8918aa298e3f67e1353179'
CONFIG_SHA='615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
NATIVE_SECONDS=180
CLAIM=HERE/'results/partial_method_native_claim01.json'
SOURCES=('partial_method.py','partial_bounds.py','test_partial_method.py','test_partial_bounds.py',
    'run_partial_method_precheck.py','scene_adapter.py','scene_method.py',
    'diagnostic_search.py','formal_milp.py','initial_point.py','initial_schedule.py',
    'milp.py','milp_coefficients.py','matlab_bridge.py','solve_model.m',
    'inputs.py','start_domain.py','schedules.py','thermal.py','timing.py',
    'build_observer.py','control_policy.py','config_v01.json','run_milp_precheck.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')


def sources():
    files=[HERE/n for n in SOURCES]+[HERE.parent/'v1_evaluator/interval.py']
    return {str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in files}


def snapshot(out,hashes):
    for name in hashes:
        dest=out/'source_snapshot'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(REPO/name,dest)


def reused_gate():
    path=HERE/'results/auto_milp_precheck02/checks.json'
    gate=json.loads(path.read_text(encoding='utf-8'))
    if not gate['passed'] or any(sha(REPO/name)!=value for name,value in gate['source_sha256'].items()):
        raise ValueError('K112 expression/evaluator gate is stale')
    return {'path':str(path.relative_to(REPO)).replace('\\','/'),'sha256':sha(path),
            'checks':gate['count'],'source_sha256':gate['source_sha256']}


def historical():
    data=json.loads((HERE/'results/prefilter_protocol01/historical_integrity_before.json').read_text(encoding='utf-8'))
    hashes=data['prior_24_archives_sha256']; root=HERE/'results/formal_comparison01'
    if any(sha(root/name)!=value for name,value in hashes.items()):
        raise ValueError('Historical archive changed')
    return hashes


def prepare(out):
    out=out.resolve(); out.relative_to(REPO); out.mkdir(parents=True,exist_ok=False)
    hashes=sources(); old=reused_gate(); history=historical()
    if sha(HERE/'config_v01.json')!=CONFIG_SHA: raise ValueError('Frozen physical config changed')
    snapshot(out,hashes)
    return out,hashes,old,history


def run_mock(out):
    started=time.monotonic(); out,before,old,history=prepare(out)
    save(out/'declaration.json',{'scope':'mock lifecycle and pure algebra only',
        'correctness_ceiling_s':120,'reference_commit':REFERENCE,'source_sha256':before,
        'reused_K112':old,'actual_thermal_calls':0,'actual_model_builds':0,'native_solver_calls':0,
        'research_method_calls':0,'native_plan':{'calls':1,'budget_s':NATIVE_SECONDS,
            'fixture':'partial_lifecycle: two original scenes, one A.pre each, fixed CPU1, starts {0} ms',
            'parameters':'same frozen config, autoL only; no physical changes',
            'claim_path':str(CLAIM.relative_to(REPO)).replace('\\','/'),
            'retries':False,'extension':False,'reference_results_shared':False}})
    records=[]; stream=io.StringIO(); attempts=[]; outcome=None; error=None
    class Result(unittest.TextTestResult):
        def startTest(self,test):
            if time.monotonic()-started>=120: raise TimeoutError('Mock correctness ceiling')
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
    def forbidden(*args,**kwargs):
        attempts.append('attempt'); raise AssertionError('No actual model/thermal/native call in mock gate')
    try:
        suite=unittest.TestLoader().loadTestsFromNames(('test_partial_method','test_partial_bounds'))
        with patch('milp.Model.__init__',forbidden), patch('thermal.evaluate_piecewise',forbidden), \
                patch('scene_adapter.evaluate_piecewise',forbidden), patch('matlab_bridge.MatlabSession.__init__',forbidden):
            outcome=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
    except Exception: error=traceback.format_exc()
    (out/'unit_checks.txt').write_text(stream.getvalue(),encoding='utf-8')
    save(out/'fixture_records.json',{name:getattr(sys.modules.get(name),'RECORDS',
        getattr(sys.modules.get(name),'PRECHECK_RECORDS',{})) for name in ('test_partial_method','test_partial_bounds')})
    integrity={'source_unchanged':sources()==before,'reused_K112_still_current':reused_gate()==old,
        'old24_unchanged':historical()==history,'no_actual_physical_or_native':not attempts,
        'correctness_ceiling_respected':time.monotonic()-started<120}
    records.extend({'name':name,'passed':value} for name,value in integrity.items())
    passed=bool(outcome) and outcome.wasSuccessful() and not error and all(r['passed'] for r in records)
    report={'passed':passed,'count':len(records),'checks':records,'source_sha256':before,
        'unit_test_methods':outcome.testsRun if outcome else 0,'runner_error':error,
        'elapsed_s':time.monotonic()-started,'scope':'mock and algebra only; not physical evidence',
        'reused_K112':old,'original_historical24_sha256':history,'actual_calls_attempted':attempts}
    save(out/'checks.json',report)
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform(),
        'checked_at_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'passed':passed,'checks':len(records),'elapsed_s':report['elapsed_s'],'out':str(out)}),flush=True)
    return passed


def run_native(out,gate_path):
    gate_path=gate_path.resolve(); gate=json.loads(gate_path.read_text(encoding='utf-8'))
    if not gate['passed'] or gate['source_sha256']!=sources():
        raise ValueError('A current source-matched passing mock gate is required')
    if CLAIM.exists(): raise FileExistsError('K113 native call already claimed; no retry')
    out,before,old,history=prepare(out)
    from test_partial_method import small_input
    from partial_method import execute_shared_deployment
    from scene_adapter import canonical_hash
    config,instance=small_input()  # Declaration only; actual loader rebuilds inside its budget.
    declaration={'scope':'one native small correctness invocation, not research or comparison',
        'budget_s':NATIVE_SECONDS,'gate_sha256':sha(gate_path),'source_sha256':before,
        'input':instance,'input_sha256':canonical_hash(instance),'shared_deployment':{'A.pre':'CPU1'},
        'calls':1,'reruns_allowed':False,'budget_extension_allowed':False,
        'input_rebuilt_inside_method':True,'mock_candidate_witness_or_cache_shared':False,
        'ordering':'all scene models/seeds first, original scene order for native requests',
        'time_scope':'one MethodBudget before input through callback checks/feedback/aggregation; cleanup/archival separate'}
    save(out/'declaration.json',declaration)
    claim={'out':str(out.relative_to(REPO)).replace('\\','/'),'gate_sha256':sha(gate_path),
           'source_sha256':before,'budget_s':NATIVE_SECONDS,'state':'CLAIMED_NO_RETRY'}
    with CLAIM.open('x',encoding='utf-8') as f: json.dump(claim,f,ensure_ascii=False,indent=2)
    result=execute_shared_deployment(small_input,out/'invocation',shared_deployment={'A.pre':'CPU1'},seconds=NATIVE_SECONDS)
    # Read-only evidence checks; do not solve, reevaluate or form a new U.
    from schedules import validate_schedule
    from thermal import I
    checks=[]
    def check(name,value): checks.append({'name':name,'passed':bool(value)})
    check('source_unchanged',sources()==before)
    check('old24_unchanged',historical()==history)
    check('input_identity',result.get('identity',{}).get('full_input_sha256')==declaration['input_sha256'])
    check('worker_ready',result.get('matlab_worker_ready'))
    check('native_entered_in_budget',result.get('in_budget_solver_entry_confirmed'))
    check('all_scenes_searched',all(r.get('solver_result') is not None for r in result.get('scenes',{}).values()))
    check('matching_complete_global_SAFE',result.get('state')=='SAFE' and result.get('rankable_energy'))
    candidate=result.get('safe_candidate')
    check('full_candidate_legal',candidate is not None and validate_schedule(instance,candidate)['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED')
    aggregate=result.get('aggregation') or {}
    receipts=aggregate.get('scenes',{})
    complete=(set(receipts)=={s['id'] for s in instance['scenarios']} and
        all(r.get('state')=='SAFE' and r.get('result',{}).get('complete') and
            0<=r.get('completed_at_elapsed_s',NATIVE_SECONDS)<NATIVE_SECONDS for r in receipts.values()))
    check('all_original_scene_receipts_complete',complete)
    if complete:
        total=sum((I(*receipts[s['id']]['energy_J'])*I.rational(__import__('fractions').Fraction(s['weight']))
                   for s in instance['scenarios']),I(0))
        check('weighted_energy_not_double_counted',total.data()==result.get('weighted_energy_J'))
    check('all_global_updates_in_budget',all(0<=r['committed_at_s']<NATIVE_SECONDS for r in result.get('global_updates',[])))
    check('no_independent_infeasibility_or_optimality_claim',not result.get('independently_proven_infeasible') and not result.get('independently_proven_optimal'))
    bounds=result.get('deployment_bounds') or {}
    check('independent_bound_scopes',bounds.get('L0',{}).get('scope')=='original_full_domain' and
          bounds.get('L_a',{}).get('scope')=='fixed_shared_deployment')
    passed=all(c['passed'] for c in checks)
    report={'passed':passed,'count':len(checks),'checks':checks,'source_sha256':before,
        'gate_sha256':sha(gate_path),'native_method_calls':1,'research_method_calls':0,
        'method_elapsed_s':result.get('timing',{}).get('method_elapsed_s'),
        'safe_upper_bound_J':result.get('safe_upper_bound_J'),
        'initial_global_safe_upper_bound_J':result.get('initial_global_safe_upper_bound_J'),
        'global_updates':result.get('global_updates'),'reason':result.get('reason'),
        'scope':'saved-evidence verification only; no performance or feedback-benefit claim'}
    save(out/'verification.json',report)
    print(json.dumps({'passed':passed,'checks':len(checks),'method_elapsed_s':report['method_elapsed_s'],
        'safe_upper_bound_J':report['safe_upper_bound_J'],'out':str(out)}),flush=True)
    return passed


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--gate',type=Path)
    args=parser.parse_args()
    if args.native and args.gate is None: parser.error('--native requires --gate checks.json')
    raise SystemExit(0 if (run_native(args.out,args.gate) if args.native else run_mock(args.out)) else 1)
