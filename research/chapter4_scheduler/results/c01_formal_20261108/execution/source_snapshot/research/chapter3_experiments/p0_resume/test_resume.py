"""Pure continuation/IO/terminal tests; no research method or heat invocation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import resume as r
import safe_io
import supervise_resume as supervise


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=r.REPO/'.runtime')
        self.root=Path(self.temp.name).resolve();self.root.relative_to(r.REPO.resolve())
        self.addCleanup(self.temp.cleanup)
        self.out=self.root/'continuation';self.out.mkdir()
        (self.out/'claims').mkdir();(self.out/'calls').mkdir()
        self.old=self.root/'prior';(self.old/'claims').mkdir(parents=True)
        self.original_root=None
        for name,value in [('OUT',self.out),('OLD',self.old),('GLOBAL_CLAIM',self.root/'global.json')]:
            patcher=patch.object(r,name,value);patcher.start();self.addCleanup(patcher.stop)
        r.write_new(self.out/'declaration.json',{'MOCK_ONLY':True})
        safe_io.save(self.out/'ledger.json',r.initial_ledger())
        r.publish_status(r.initial_ledger(),phase='DECLARED')
        self.counter=0;self.post_count=0

    def execute(self,job,parent,d,entries):
        self.counter+=1
        folder=parent/job['id'];self.assertFalse(folder.exists());folder.mkdir()
        return {'MOCK_ONLY':True},{'input_verified':True}

    def auditor(self,*args,**kw):
        return {'execution':{'execution_status':'NORMAL_COMPLETION'},'usable_U_J':'1'}

    def post(self,*args):self.post_count+=1;return {'passed':True,'new_U':False}

    def run_mock(self,executor=None,auditor=None,post=None,admission=None,remaining=20000):
        with patch.object(r,'admission',side_effect=admission or (lambda:{'slots':r.slots()})),\
             patch.object(r,'remaining_calendar',return_value=remaining):
            return r.run(entries={'MOCK_ONLY':True},executor=executor or self.execute,
                auditor=auditor or self.auditor,post=post or self.post,clock=lambda:100.)


class ContinuationTests(Fixture):
    def test_01_exact_remaining_37_and_original_order(self):
        self.assertEqual(r.slots(),r.prior.p.slots()[3:])
        self.assertEqual(len(r.slots()),37)
        self.assertEqual([s['ordinal'] for s in r.slots()],list(range(4,41)))
        self.assertEqual([s['id'] for s in r.slots()[:5]],['sa101','sa102','sa103','sa104','sa105'])
        self.assertEqual(sum(s['seconds'] for s in r.slots()),11100)

    def test_02_full_37_mock_prefix_total_40_never_first_three(self):
        self.assertTrue(self.run_mock())
        ledger=r.read(self.out/'ledger.json');terminal=r.read(self.out/'worker_terminal.json')
        self.assertEqual(self.counter,37);self.assertEqual(self.post_count,37)
        self.assertEqual(ledger['consumed_new'],37);self.assertEqual(ledger['consumed_total'],40)
        self.assertEqual(ledger['reserved_total_method_s'],12000)
        self.assertEqual(terminal['state'],'COMPLETED')
        self.assertEqual([v['slot_id'] for v in ledger['calls']],[s['slot_id'] for s in r.slots()])

    def test_03_no_restart_or_claim_reuse(self):
        self.assertTrue(self.run_mock())
        with self.assertRaises(FileExistsError):self.run_mock()
        self.assertEqual(self.counter,37)

    def test_04_old_first_three_are_rejected(self):
        ledger=r.initial_ledger()
        for slot in r.prior.p.slots()[:3]:
            with self.assertRaises(ValueError):r.claim(ledger,slot)
        self.assertEqual(ledger['consumed_total'],3)

    def test_05_reordered_or_budget_drift_rejected(self):
        ledger=r.initial_ledger()
        with self.assertRaises(ValueError):r.claim(ledger,r.slots()[1])
        ledger['reserved_total_method_s']=0
        with self.assertRaises(ValueError):r.claim(ledger,r.slots()[0])

    def test_06_prior_claim_cannot_be_replayed(self):
        slot=r.slots()[0]
        r.write_new(self.old/'claims'/(slot['slot_id']+'.json'),{'MOCK_ONLY':True})
        with self.assertRaises(FileExistsError):r.claim(r.initial_ledger(),slot)

    def test_07_method_failure_stops_and_terminal_is_independent(self):
        def execute(*a):raise RuntimeError('MOCK_METHOD_ERROR')
        self.assertFalse(self.run_mock(executor=execute))
        terminal=r.read(self.out/'worker_terminal.json')
        self.assertEqual(terminal['consumed_total'],4)
        self.assertEqual(terminal['state'],'BLOCKED')
        self.assertEqual(self.post_count,0)

    def test_08_numeric_unknown_stops_before_next_method(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NUMERICAL_UNRESOLVED'},'usable_U_J':None}
        self.assertFalse(self.run_mock(auditor=audit))
        self.assertEqual(self.counter,1);self.assertEqual(self.post_count,0)

    def test_09_verified_deadline_preserves_U_and_continues(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'},'usable_U_J':'1'}
        self.assertTrue(self.run_mock(auditor=audit))
        self.assertTrue(all(v['records']['usable_U_J']=='1' for v in r.read(self.out/'ledger.json')['calls']))

    def test_10_post_failure_preserves_U_and_stops(self):
        self.assertFalse(self.run_mock(post=lambda *a:{'passed':False,'new_U':False}))
        self.assertEqual(self.counter,1)
        returned=r.read(self.out/'claims'/(r.slots()[0]['slot_id']+'_method_return.json'))
        self.assertEqual(returned['records']['usable_U_J'],'1')
        self.assertEqual(r.read(self.out/'worker_terminal.json')['state'],'BLOCKED')

    def test_11_permanent_ledger_rejection_retains_method_receipt_and_terminal(self):
        original=safe_io.save
        def fail(path,value,**kw):
            if Path(path).name=='ledger.json' and value['calls'] and value['calls'][-1].get('records'):
                raise PermissionError('MOCK_PERMANENT_LEDGER_DENIAL')
            return original(path,value,**kw)
        with patch.object(safe_io,'save',side_effect=fail):self.assertFalse(self.run_mock())
        self.assertEqual(self.counter,1);self.assertEqual(self.post_count,0)
        terminal=r.read(self.out/'worker_terminal.json')
        self.assertEqual(terminal['state'],'STOPPED_EXCEPTION')
        self.assertEqual(terminal['consumed_total'],4)
        receipt=r.read(self.out/'claims'/(r.slots()[0]['slot_id']+'_method_return.json'))
        self.assertEqual(receipt['records']['usable_U_J'],'1')

    def test_12_status_write_failure_does_not_start_method(self):
        original=safe_io.save
        def fail(path,value,**kw):
            if Path(path).name=='status.json':raise PermissionError('MOCK_STATUS_DENIAL')
            return original(path,value,**kw)
        with patch.object(safe_io,'save',side_effect=fail):self.assertFalse(self.run_mock())
        self.assertEqual(self.counter,0)
        self.assertEqual(r.read(self.out/'worker_terminal.json')['state'],'STOPPED_EXCEPTION')

    def test_13_original_calendar_expiry_does_not_claim_or_reset(self):
        self.assertFalse(self.run_mock(remaining=0))
        self.assertEqual(self.counter,0)
        self.assertEqual(r.read(self.out/'worker_terminal.json')['consumed_total'],3)
        self.assertEqual(r.read(self.out/'worker_terminal.json')['state'],'STOPPED_ORIGINAL_CALENDAR_LIMIT')

    def test_14_input_source_drift_after_method_stops_followup(self):
        checks=[]
        def admission():
            checks.append(1)
            if len(checks)==3:raise ValueError('MOCK_SOURCE_DRIFT')
            return {'slots':r.slots()}
        self.assertFalse(self.run_mock(admission=admission));self.assertEqual(self.counter,1)

    def test_15_claim_precedes_entry_and_old_deployment_not_changed(self):
        def execute(job,parent,d,entries):
            status=safe_io.read_small(self.out/'status.json')
            self.assertGreaterEqual(status['consumed_total'],4)
            self.assertEqual(status['active']['phase'],'METHOD')
            return self.execute(job,parent,d,entries)
        self.assertTrue(self.run_mock(executor=execute))
        self.assertEqual(len(r.prior.sources()),197)


class SupervisorTests(unittest.TestCase):
    def test_16_missing_worker_terminal_cannot_leave_false_success(self):
        result=supervise.process_terminal(0,None,None)
        self.assertEqual(result['state'],'STOPPED_PROCESS_OR_WORKER_FAILURE')
        self.assertTrue(result['stale_running_ledger_is_not_authoritative'])

    def test_17_nonzero_or_killed_worker_is_explicitly_stopped(self):
        for code,reason in ((1,None),(-1,'METHOD_RETURN_LIMIT')):
            result=supervise.process_terminal(code,reason,None)
            self.assertEqual(result['state'],'STOPPED_PROCESS_OR_WORKER_FAILURE')

    def test_18_exact_completion_terminal(self):
        self.assertEqual(supervise.process_terminal(0,None,{'state':'COMPLETED','consumed_new':37})['state'],'COMPLETED')
        self.assertNotEqual(supervise.process_terminal(0,None,{'state':'COMPLETED','consumed_new':36})['state'],'COMPLETED')

    def test_19_method_slot_and_original_deadlines(self):
        with patch.object(r,'remaining_calendar',return_value=10):
            status={'active':{'phase':'METHOD','slot_start_monotonic':0,'phase_start_monotonic':0}}
            self.assertIsNone(supervise.expiry(status,419))
            self.assertEqual(supervise.expiry(status,420),'METHOD_RETURN_LIMIT')
            status['active']['phase']='POST'
            self.assertIsNone(supervise.expiry(status,479))
            self.assertEqual(supervise.expiry(status,480),'SLOT_RETURN_LIMIT')
        with patch.object(r,'remaining_calendar',return_value=0):
            self.assertEqual(supervise.expiry({},0),'ORIGINAL_CALENDAR_LIMIT')

    def test_20_compact_status_reader_closes_and_limits_data(self):
        with tempfile.TemporaryDirectory(dir=r.REPO/'.runtime') as temp:
            path=Path(temp)/'status.json';safe_io.save(path,{'active':None})
            self.assertEqual(safe_io.read_small(path),{'active':None})
            safe_io.save(path,{'active':'x'*65536})
            with self.assertRaises(ValueError):safe_io.read_small(path)
        source=Path(supervise.__file__).read_text(encoding='utf-8')
        self.assertNotIn("read(r.OUT/'ledger.json')",source)


# Reuse the eight real Windows file fixtures against NEW safe_io, not the old
# candidate. This is test-only module replacement; research modules are unchanged.
old_tests=r.OLD/'failure_review01/test_io_candidate.py'
sys_path=str(old_tests.parent)
import sys
sys.path.insert(0,sys_path)
spec=importlib.util.spec_from_file_location('k155_io_fixture_for_k156',old_tests)
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
class NewAtomicIOTests(legacy.IOTemperatureIndependentTests):
    def setUp(self):
        patcher=patch.object(legacy,'fix',safe_io);patcher.start();self.addCleanup(patcher.stop)
        super().setUp()
