"""Reproducible 32-case manual acceptance runner; real work is intercepted.

Usage: python -B -m research.chapter3_g0.tests.run_checks --out NEW_DIRECTORY
An existing directory is rejected; failed attempts are never overwritten.
"""
import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import traceback
from unittest.mock import patch

from . import fixtures, test_domains, test_model, test_receipts, test_lifecycle


ROOT=Path(__file__).resolve().parents[3]
PACKAGE=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')


class Context:
    def __init__(self):
        self.assertions=[]

    def check(self,condition,message):
        self.assertions.append({'assertion':message,'passed':bool(condition)})
        if not condition:
            raise AssertionError(message)

    def rejects(self,callable_,message,exceptions=(ValueError,)):
        try:
            callable_()
        except exceptions as error:
            self.assertions.append({'assertion':message,'passed':True,
                'expected_error_type':type(error).__name__,'message':str(error)})
            return error
        self.check(False,message+': expected rejection missing')


@contextmanager
def prohibit_scientific_work(counters):
    """No subprocess, production planner, thermal kernel or RC factory calls.

    Original PARTIAL validation/aggregation and old row-export arithmetic are
    allowed only under their explicit handmade seams in the individual cases.
    """
    import thermal, milp, milp_coefficients, heft_method, sa_method, scene_adapter
    def denied(name):
        def fail(*args,**kwargs):
            counters[name]=counters.get(name,0)+1
            raise AssertionError('FORBIDDEN_REAL_WORK:'+name)
        return fail
    with ExitStack() as stack:
        for module,names in [(thermal,['evaluate_candidate','evaluate_piecewise']),
                             (milp,['build_model','evaluate_candidate']),
                             (milp_coefficients,['Coefficients']),
                             (heft_method,['run_heft','build_heft_candidate']),
                             (sa_method,['run_sa']),
                             (scene_adapter,['evaluate_piecewise'])]:
            for name in names:
                if hasattr(module,name):
                    stack.enter_context(patch.object(module,name,denied(module.__name__+'.'+name)))
        stack.enter_context(patch.object(milp.Model,'__init__',denied('Model.__init__')))
        for name in ('Popen','run','call','check_call','check_output'):
            stack.enter_context(patch.object(subprocess,name,denied('subprocess.'+name)))
        stack.enter_context(patch.object(os,'system',denied('os.system')))
        yield


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    output=Path(args.out).resolve()
    if output.exists():
        raise SystemExit('Existing result directory is never reused: '+str(output))
    if not output.is_relative_to(PACKAGE.resolve()):
        raise SystemExit('Manual results must stay within isolated G0 directory')
    output.mkdir(parents=True)
    runtime_sources=list(PACKAGE.glob('*.py'))+list((PACKAGE/'tests').rglob('*.py'))
    before={str(p.relative_to(ROOT)):digest(p) for p in runtime_sources}
    baseline=json.loads((PACKAGE/'tests/fixtures/protected_baseline.json').read_text(encoding='utf-8'))
    protected=dict(baseline['protected_source_sha256'])
    protected.update(baseline['frozen_input_and_contract_sha256'])
    bad=[p for p,h in protected.items() if digest(ROOT/p)!=h]
    if bad:
        save(output/'preflight_failure.json',{'reason':'PROTECTED_SOURCE_DRIFT','paths':bad})
        raise SystemExit('Protected source drift')
    save(output/'source_manifest.json',{'kind':'MANUAL_ONLY','source_sha256':before,
        'protected_baseline_sha256':digest(PACKAGE/'tests/fixtures/protected_baseline.json'),
        'python':platform.python_version(),'real_entry_enabled':False,
        'input_source':str(fixtures.PLATFORM_SOURCE.relative_to(ROOT)),
        'manual_source_note':'Platform read only; handmade tasks, no reference schedule read'})
    for relative in before:
        src=ROOT/relative
        target=output/'source_snapshot'/src.relative_to(PACKAGE)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(src.read_bytes())
    cases={f'A{i:02d}':getattr(test_domains,f'A{i:02d}') for i in range(1,16)}
    cases.update({key:getattr(test_model,key) for key in ('A16','A19')})
    cases.update({key:getattr(test_receipts,key) for key in ('A17','A18','A20','A21','A25','A28')})
    cases.update({key:getattr(test_lifecycle,key) for key in ('A22','A23','A24','A26','A27','A29','A30','A31','A32')})
    assert len(cases)==32
    counters={};records=[]; started=time.monotonic()
    # Pre-load class definitions before process sentinels; imports run no
    # planner, evaluator or model constructor. All test-body work is guarded.
    import thermal, milp, milp_coefficients, heft_method, sa_method
    with prohibit_scientific_work(counters):
        for identity,case in sorted(cases.items()):
            ctx=Context(); inputs=[]; t0=time.monotonic()
            record={'id':identity,'status':'FAIL','evidence_kind':'MANUAL_FIXTURE',
                    'source_manifest':'source_manifest.json','assertions':ctx.assertions}
            original=fixtures.bundle
            def capture(*a,**kw):
                value=original(*a,**kw);inputs.append(deepcopy(value));return value
            try:
                with ExitStack() as stack:
                    for module in (fixtures,test_domains,test_model,test_receipts,test_lifecycle):
                        stack.enter_context(patch.object(module,'bundle',capture))
                    details=case(ctx)
                    if identity in ('A08','A09'):
                        details['lifecycle']=getattr(test_lifecycle,identity+'_extra')(ctx)
                record.update(status='PASS',details=details)
            except Exception as error:
                record.update(error_type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
            record['wall_seconds']=time.monotonic()-t0
            record['input_files']=[]
            for index,(config,instance,candidate) in enumerate(inputs,1):
                path=output/'cases'/identity/f'input_{index:03d}.json'
                save(path,{'kind':'HANDMADE_NOT_FORMAL','config':config,'instance':instance,'candidate':candidate})
                record['input_files'].append({'path':str(path.relative_to(output)),'sha256':digest(path)})
            record['fixture_sha256']=digest(PACKAGE/'tests/fixtures.py')
            save(output/'cases'/identity/'receipt.json',record)
            records.append(record)
            print(identity,record['status'],record.get('message',''),flush=True)
    drift=[p for p,h in protected.items() if digest(ROOT/p)!=h]
    source_drift=[p for p,h in before.items() if digest(ROOT/p)!=h]
    unrelated=[p for p,h in baseline['preexisting_unrelated_worktree'].items() if digest(ROOT/p)!=h]
    save(output/'protection.json',{'protected_source_count':len(baseline['protected_source_sha256']),
        'frozen_artifact_count':len(baseline['frozen_input_and_contract_sha256']),
        'protected_drift':drift,'g0_source_drift_during_tests':source_drift,
        'unrelated_worktree_changed':unrelated,'forbidden_real_entry_attempts':counters,
        'real_scientific_calls':0,'thermal_integrations':0,'matlab_processes':0,
        'row_replays':'A16 manual prestored rows only, not a scientific model build'})
    passed=sum(r['status']=='PASS' for r in records)
    result={'schema':'g0-32-manual-checks-v1','kind':'MANUAL_ONLY_NOT_PERFORMANCE_OR_PHYSICAL_VALIDATION',
        'passed':passed,'total':32,'assertions':sum(len(r['assertions']) for r in records),
        'wall_seconds':time.monotonic()-started,'failed':[r['id'] for r in records if r['status']!='PASS'],
        'protection_passed':not drift and not source_drift and not unrelated and not counters,
        'cases':[{k:r[k] for k in ('id','status','wall_seconds','input_files')} for r in records],
        'next_real_execution_authorized':False}
    save(output/'checks.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False))
    return 0 if passed==32 and result['protection_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
