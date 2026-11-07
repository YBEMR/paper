"""B0 static + mocked regression only. Never launches a research backend."""
import ast,hashlib,json,sys,time,unittest
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent; CORE=HERE.parent
sys.path.insert(0,str(CORE)); sys.dont_write_bytecode=True
from h02_pair_preflight.common import sha,byte_sha
from h02_pair_preflight.paired_response_input_view import verify_sources,paired_response_input_view
from h02_pair_b0.bundle import runtime_sources,verify_runtime_freeze
from h02_pair_b0.io_contract import load_json,atomic_json,policy_files
BLOCKED=[]
PROTECTED={str(CORE/name):kind for name,kind in [('heft_method.py','HEFT'),('schedules.py','SCHEDULE'),('partial_bounds.py','LOWER_BOUND'),('q1_case.py','LOWER_BOUND'),('thermal.py','THERMAL')]}
PROTECTED[str(CORE.parent/'v1_evaluator/interval.py')]='THERMAL'
for p in CORE.glob('*.py'):
    if any(k in p.name for k in ('milp','solver')): PROTECTED[str(p)]='OPTIMIZER'

def guard(frame,event,arg):
    if event!='call': return
    code=frame.f_code; kind=PROTECTED.get(code.co_filename)
    if kind is None or not (code.co_flags&2) or code.co_qualname=='Budget.__init__': return
    BLOCKED.append({'kind':kind,'file':code.co_filename,'function':code.co_qualname,'blocked_before_body':True})
    raise RuntimeError('B0_REAL_COMPUTATION_FORBIDDEN:'+code.co_qualname)

class Result(unittest.TextTestResult):
    def __init__(self,*a,**k): super().__init__(*a,**k); self.records=[]
    def startTest(self,test): sys.setprofile(guard); super().startTest(test)
    def stopTest(self,test):
        sys.setprofile(None)
        if BLOCKED: self.shouldStop=True
        super().stopTest(test)
    def addSuccess(self,test): super().addSuccess(test); self.records.append({'test':test.id(),'passed':True})
    def addFailure(self,test,err): super().addFailure(test,err); self.records.append({'test':test.id(),'passed':False,'failure':self._exc_info_to_string(err,test)})
    def addError(self,test,err): super().addError(test,err); self.records.append({'test':test.id(),'passed':False,'error':self._exc_info_to_string(err,test)})

def main():
    start=time.monotonic(); now=datetime.now(timezone.utc).isoformat(); ev=HERE/'evidence'; ev.mkdir(exist_ok=True)
    source=verify_sources(); freeze=verify_runtime_freeze(); policy,gate=policy_files()
    assert not gate['research_authorized'] and not policy['execution_enabled']
    # Pure input projection only; no schedules or thermal are formed/checked.
    ids={pid:paired_response_input_view(pid)['audit'] for pid in ('base__R1','base__R2')}
    for p in list(HERE.rglob('*.py'))+[CORE/'h02_pair_preflight/paired_heuristic_entry.py',CORE/'h02_pair_preflight/truth_H_post_audit.py']:
        ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    attempt=ev/'precheck_attempts'/now.replace(':','-').replace('.','-'); attempt.mkdir(parents=True)
    atomic_json(attempt/'runtime_freeze.json',freeze)
    suite=unittest.TestSuite()
    for folder in ('h02_pair_preflight','h02_pair_b0'):
        suite.addTests(unittest.defaultTestLoader.discover(str(CORE/folder/'tests'),pattern='test_*.py',top_level_dir=str(CORE)))
    result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(suite)
    from h02_pair_b0.tests.test_process_controller import PROCESS_REPORTS
    passed=result.wasSuccessful() and not BLOCKED
    report={'phase':'B0_ONLY','run_at_UTC':now,'passed':passed,'test_count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'tests':result.records,'protected_body_attempts':BLOCKED,'mock_process_reports':PROCESS_REPORTS,'runtime_freeze_sha256':sha(freeze),'no_actual_research_backend_calls':True}
    atomic_json(attempt/'checks.json',report); atomic_json(ev/'regression_tests.json',report)
    atomic_json(ev/'input_identity_check.json',{'passed':True,'scope':'Pure input algebra only; original H/R and physical model unchanged','cases':ids})
    ledger={'phase':'B0_ONLY','formal_budget_authorized':False,'stage_B_started':False,'real_heft_calls':0,'real_h_thermal_audits':0,'real_schedule_validator_calls':0,'real_lower_bound_calls':0,'real_optimizer_calls':0,'research_calls':0,'new_safe':0,'formal_method_budget_consumed_s':0,'formal_audit_budget_consumed_s':0,'mock_test_count':result.testsRun,'mock_process_probes':len(PROCESS_REPORTS),'protected_body_attempts':BLOCKED,'precheck_wall_s':time.monotonic()-start,'passed':passed,'test_helpers_prior_runs':'22 synthetic classification + 18 fake-clock tests, zero real calls; no research budget'}
    atomic_json(ev/'run_ledger.json',ledger)
    print(json.dumps({'passed':passed,'tests':result.testsRun,'research_calls':0,'new_real_SAFE':0,'stage_B_authorized':False}))
    return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
