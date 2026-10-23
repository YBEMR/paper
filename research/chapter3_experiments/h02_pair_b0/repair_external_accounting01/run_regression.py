"""Repair-only static/mock regression. Never reruns archived experiments."""
import ast, json, sys, time, unittest, hashlib
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
CORE=HERE.parents[1]
sys.path.insert(0,str(CORE)); sys.dont_write_bytecode=True
from h02_pair_b0.run_precheck import guard, BLOCKED, Result
from h02_pair_b0.bundle import verify_runtime_freeze
from h02_pair_b0.io_contract import policy_files

class GuardedResult(Result):
    def stopTest(self,test):
        super().stopTest(test)
        sys.setprofile(guard)  # Also protect the following class fixtures/teardown.

def main():
    started=time.monotonic(); stamp=datetime.now(timezone.utc).isoformat()
    output=HERE/'attempts'/stamp.replace(':','-').replace('.','-')
    output.mkdir(parents=True)
    freeze=verify_runtime_freeze(); policy,gate=policy_files()
    assert policy['execution_enabled'] is False and gate['research_authorized'] is False
    assert gate['four_slot_authorized'] is False
    oldrun=CORE/'results/h02_same_truth_execution01'
    before={str(p.relative_to(oldrun)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in oldrun.rglob('*') if p.is_file()}
    for p in [CORE/'h02_pair_preflight/receipts.py',*HERE.glob('*.py'),
              CORE/'h02_pair_b0/tests/test_external_accounting.py']:
        ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    BLOCKED.clear()
    try:
        sys.setprofile(guard)
        suite=unittest.TestSuite()
        for folder in ('h02_pair_preflight','h02_pair_b0'):
            suite.addTests(unittest.defaultTestLoader.discover(
                str(CORE/folder/'tests'),pattern='test_*.py',top_level_dir=str(CORE)))
        result=unittest.TextTestRunner(verbosity=1,resultclass=GuardedResult).run(suite)
    finally:
        sys.setprofile(None)
    after={str(p.relative_to(oldrun)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in oldrun.rglob('*') if p.is_file()}
    assert before==after,'ORIGINAL_RESEARCH_ARCHIVE_CHANGED'
    from h02_pair_b0.tests.test_process_controller import PROCESS_REPORTS
    passed=result.wasSuccessful() and not BLOCKED
    report={'scope':'EXTERNAL_COMMON_RECEIPT_REPAIR_ONLY','run_at_UTC':stamp,
      'passed':passed,'test_count':result.testsRun,'failures':len(result.failures),
      'errors':len(result.errors),'tests':result.records,'protected_body_attempts':BLOCKED,
      'mock_process_reports':PROCESS_REPORTS,'research_calls_this_task':0,
      'new_real_SAFE_this_task':0,'original_research_archive_unchanged':True,
      'archived_files_hash_checked':len(before),'runtime_sources_sha256':freeze['source_files_sha256'],
      'research_gate_closed':True,'wall_s':time.monotonic()-started}
    (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'runtime_freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (HERE/'latest_attempt.json').write_text(json.dumps({'attempt':str(output.relative_to(HERE)),
      'passed':passed,'test_count':result.testsRun},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','test_count','research_calls_this_task',
      'new_real_SAFE_this_task','research_gate_closed','wall_s')}))
    return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
