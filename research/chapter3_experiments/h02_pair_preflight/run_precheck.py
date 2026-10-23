"""Reproducible Stage A static/mocked preflight; no Stage B execution path.
Run: python -B research/chapter3_experiments/h02_pair_preflight/run_precheck.py
"""
import ast,hashlib,json,os,platform,sys,time,unittest
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent; CORE=HERE.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(CORE))
from h02_pair_preflight.common import encoded,sha,byte_sha,BASE_SHA
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,verify_sources
from h02_pair_preflight.contracts import static_monotonicity_contract

COUNTERS={'real_heft_calls':0,'real_h_thermal_audits':0,'research_calls':0,'new_safe':0,'real_schedule_validator_calls':0,'real_lower_bound_calls':0,'real_optimizer_calls':0}
BLOCKED=[]
PROTECTED={str(CORE/name):key for name,key in (
    ('heft_method.py','real_heft_calls'),('schedules.py','real_schedule_validator_calls'),
    ('partial_bounds.py','real_lower_bound_calls'),('q1_case.py','real_lower_bound_calls'),
    ('thermal.py','real_h_thermal_audits'))}
PROTECTED[str(CORE.parent/'v1_evaluator'/'interval.py')]='real_h_thermal_audits'
for p in CORE.glob('*.py'):
    if any(k in p.name for k in ('milp','solver')): PROTECTED[str(p)]='real_optimizer_calls'
def guard(frame,event,arg):
    if event!='call': return
    code=frame.f_code
    key=PROTECTED.get(code.co_filename)
    if key is None or not (code.co_flags & 2) or code.co_qualname=='Budget.__init__': return
    BLOCKED.append({'file':code.co_filename,'function':code.co_qualname,'blocked_before_body':True})
    raise RuntimeError('STAGE_A_REAL_COMPUTATION_FORBIDDEN:'+code.co_qualname)

class RecordedResult(unittest.TextTestResult):
    def __init__(self,*a,**kw): super().__init__(*a,**kw); self.records=[]
    def startTest(self,test):
        sys.setprofile(guard); super().startTest(test)
    def stopTest(self,test):
        sys.setprofile(None)
        if BLOCKED: self.shouldStop=True
        super().stopTest(test)
    def addSuccess(self,test): super().addSuccess(test); self.records.append({'test':test.id(),'passed':True})
    def addFailure(self,test,err): super().addFailure(test,err); self.records.append({'test':test.id(),'passed':False,'failure':self._exc_info_to_string(err,test)})
    def addError(self,test,err): super().addError(test,err); self.records.append({'test':test.id(),'passed':False,'error':self._exc_info_to_string(err,test)})

def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    start=time.monotonic(); now=datetime.now(timezone.utc).isoformat(); ev=HERE/'evidence'; ev.mkdir(exist_ok=True)
    source=verify_sources(); pairs={}; audits={}; contracts={}
    for pid in ('base__R1','base__R2'):
        pair=paired_response_input_view(pid); pairs[pid]=pair; audits[pid]=pair['audit']
        contracts[pid]=static_monotonicity_contract(pair['truth_H']['config'],pair['truth_H']['instance'],pair['planner_R']['instance'])
    save(ev/'paired_inputs_audit.json',{'passed':True,'scope':'pure input projection, not a research run','cases':audits})
    save(ev/'static_monotonicity_contract.json',{'passed':True,'scope':'finite algebraic premises; no computed temperature trajectory or new SAFE','mathematical_argument':'See stageA_review.md; P1/P2 is conditional on the SAME complete R-legal/R-SAFE candidate, not two different searched candidates','cases':contracts})
    # Importing definitions is allowed; only invoking protected computational bodies is blocked.
    sys.setprofile(guard)
    try:
        suite=unittest.defaultTestLoader.discover(str(HERE/'tests'),pattern='test_*.py',top_level_dir=str(CORE))
        result=unittest.TextTestRunner(verbosity=1,resultclass=RecordedResult).run(suite)
    finally: sys.setprofile(None)
    from h02_pair_preflight.tests.test_isolation import WORKER_REPORTS
    passed=result.wasSuccessful() and not BLOCKED
    report={'passed':passed,'run_at_UTC':now,'test_count':result.testsRun,'failure_count':len(result.failures),'error_count':len(result.errors),'tests':result.records,'R_only_worker_reports':WORKER_REPORTS,'real_computation_guard_violations':BLOCKED,'mock_results_are_not_research_evidence':True}
    attempts=ev/'precheck_attempts'; attempts.mkdir(exist_ok=True)
    save(attempts/('attempt_'+now.replace(':','-').replace('.','-')+'.json'),report)
    save(ev/'mock_isolation_tests.json',report)
    files={str(p.relative_to(HERE)).replace('\\','/'):byte_sha(p.read_bytes()) for p in sorted(HERE.rglob('*')) if p.is_file() and p.suffix in ('.py','.md') and 'protocols' not in p.parts}
    for p in HERE.rglob('*.py'): ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    save(ev/'adapter_source_manifest.json',{'main_baseline_sha':BASE_SHA,'branch':'codex/h02-stage-a','source_files_sha256':files,'adapter_code_manifest_sha256':sha(files),'call_graph':{'paired_response_input_view':['pinned inputs.build_instance (pure input expansion)','control_policy.with_auto_low_idle','Fraction projection + whitelist + static contract'],'paired_heuristic_entry':['MOCK_ONLY runner wrapper','unchanged execute_heuristic lifecycle (search/validator/evaluator/both lower-bound aliases mocked)','CandidateRecorder.best receipt validation + immutable export'],'truth_H_post_audit':['MOCK_ONLY validator','MOCK_ONLY evaluator + one-use 60s fake budget','no repair/no feedback']},'unchanged_main_source_verified':True,'core_manifest_sha256':sha(source['core']),'stage_B_real_backend_configured':False})
    ledger=dict(COUNTERS,formal_budget_authorized=False,phase='A_ONLY',started_at_UTC=now,finished_at_UTC=datetime.now(timezone.utc).isoformat(),precheck_wall_s=time.monotonic()-start,formal_method_budget_s_consumed=0,formal_audit_budget_s_consumed=0,mock_suite_tests=result.testsRun,mock_guard_violations=BLOCKED,passed=passed,earlier_fixture_unit_run='39 standalone pure mock receipt tests; 0 real calls',attempt_history='All failed and passed integrated attempts retained in precheck_attempts; first guard rejection was a class-definition false positive, not a function or real computation',stage_B_started=False)
    save(ev/'run_ledger.json',ledger)
    print(json.dumps({'passed':passed,'tests':result.testsRun,'formal_research_calls':0,'new_real_SAFE':0,'stage_B_started':False}))
    return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
