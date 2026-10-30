"""Bounded mocked wiring suite; no real scientific or OS process calls."""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import time
import traceback
import unittest

from ...chapter3_g0.tests.run_checks import Context, prohibit_scientific_work


ROOT=Path(__file__).resolve().parents[3]
PACKAGE=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')


class Result(unittest.TestResult):
    def __init__(self):
        super().__init__();self.records=[];self.t0={}
    def startTest(self,test):
        super().startTest(test);self.t0[test.id()]=time.monotonic()
    def addSuccess(self,test):
        super().addSuccess(test);self._record(test,'PASS')
    def addFailure(self,test,err):
        super().addFailure(test,err);self._record(test,'FAIL',err)
    def addError(self,test,err):
        super().addError(test,err);self._record(test,'ERROR',err)
    def _record(self,test,state,error=None):
        record={'id':test.id(),'status':state,'wall_seconds':time.monotonic()-self.t0[test.id()]}
        if error:record['traceback']=''.join(traceback.format_exception(*error))
        self.records.append(record);print(record['id'].rsplit('.',1)[-1],state,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    output=Path(parser.parse_args().out).resolve()
    if output.exists() or not output.is_relative_to(PACKAGE.resolve()):
        raise SystemExit('new isolated result directory required')
    output.mkdir(parents=True)
    from . import support
    support.configure(output/'scratch')
    baseline=json.loads((ROOT/'research/chapter3_g0/tests/fixtures/protected_baseline.json').read_text(encoding='utf-8'))
    protected={**baseline['protected_source_sha256'],**baseline['frozen_input_and_contract_sha256'],
               **baseline['preexisting_unrelated_worktree']}
    assert all(sha(ROOT/p)==h for p,h in protected.items()),'legacy/frozen artifacts changed'
    active=[]
    for folder in (PACKAGE,ROOT/'research/chapter3_g0'):
        active+=list(folder.glob('*.py'))+list((folder/'tests').rglob('*.py'))
    before={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in active}
    save(output/'source_manifest.json',{'kind':'SIMULATION_NOT_REAL_EXECUTION',
         'source_sha256':before,'protected_legacy_sha256':protected,
         'previous_manual_acceptance_sha256':sha(ROOT/'research/chapter3_g0/results/manual06/checks.json')})
    for p in active:
        dest=output/'source_snapshot'/p.relative_to(ROOT/'research')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    counters={};result=Result();ctx_records=[];started=time.monotonic()
    from . import test_model_backend, test_receipt_profile, test_transport, test_backend_driver, test_worker_runner, test_launch_boundaries, test_recovery_repairs
    with prohibit_scientific_work(counters):
        suite=unittest.TestSuite()
        for module in (test_receipt_profile,test_transport,test_backend_driver,test_worker_runner,test_launch_boundaries,test_recovery_repairs):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        suite.run(result)
        for name in sorted(n for n in dir(test_model_backend) if n.startswith('test_')):
            ctx=Context();record={'id':'model_backend.'+name,'status':'FAIL','assertions':ctx.assertions}
            try:
                record['details']=getattr(test_model_backend,name)(ctx);record['status']='PASS'
            except Exception:
                record['traceback']=traceback.format_exc()
            ctx_records.append(record);print(name,record['status'],flush=True)
    drift=[p for p,h in before.items() if sha(ROOT/p)!=h]
    old_drift=[p for p,h in protected.items() if sha(ROOT/p)!=h]
    records=result.records+ctx_records
    for index,record in enumerate(records,1):
        save(output/'cases'/f'{index:03d}.json',record)
    summary={'schema':'g0-real-wiring-simulation-checks-v1','kind':'MOCKED_WIRING_NOT_REAL_SCIENTIFIC_VALIDATION',
        'passed':sum(r['status']=='PASS' for r in records),'total':len(records),
        'ctx_assertions':sum(len(r.get('assertions',[])) for r in ctx_records),
        'wall_seconds':time.monotonic()-started,
        'failed':[r['id'] for r in records if r['status']!='PASS'],
        'source_drift':drift,'legacy_drift':old_drift,'forbidden_real_entry_attempts':counters,
        'real_scientific_calls':0,'matlab_processes':0,'thermal_integrations':0,
        'real_os_process_boundary_verified':False,'real_execution_authorized':False}
    save(output/'checks.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    return 0 if summary['passed']==summary['total'] and not (drift or old_drift or counters) else 1


if __name__=='__main__':raise SystemExit(main())
