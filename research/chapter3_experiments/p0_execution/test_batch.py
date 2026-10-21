"""K155 mock-only batch lifecycle and watchdog checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import batch as b
import supervise


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=b.REPO/'.runtime')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.out=self.root/'batch';self.out.mkdir()
        (self.out/'claims').mkdir();(self.out/'calls').mkdir()
        b.write_new(self.out/'declaration.json',{'MOCK_ONLY':True})
        self.ledger={'protocol':b.PROTOCOL,'state':'DECLARED','consumed':0,
                     'reserved_method_budget_s':0,'calls':[],'active':None}
        b.save(self.out/'ledger.json',self.ledger)
        self.patchers=[patch.object(b,'OUT',self.out),patch.object(b,'GLOBAL_CLAIM',self.root/'claim.json')]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
        self.slots=b.p.slots();self.counter=0

    def execute(self,job,parent,d,entries):
        self.counter+=1
        return {'MOCK_ONLY':True},{'input_verified':True}

    def audit(self,*args,**kwargs):
        return {'execution':{'execution_status':'NORMAL_COMPLETION'},'usable_U_J':'1'}

    def post(self,*args):return {'passed':True,'new_U':False}

    def run_mock(self,executor=None,auditor=None,post=None,clock=lambda:100.):
        with patch.object(b,'admission',return_value={'slots':self.slots}):
            return b.run(entries={'MOCK_ONLY':True},executor=executor or self.execute,
                auditor=auditor or self.audit,post=post or self.post,clock=clock)


class BatchTests(Fixture):
    def test_01_all_forty_once_and_12000(self):
        self.assertTrue(self.run_mock())
        ledger=b.read(self.out/'ledger.json')
        self.assertEqual(ledger['state'],'COMPLETED')
        self.assertEqual(ledger['consumed'],40)
        self.assertEqual(ledger['reserved_method_budget_s'],12000)
        self.assertEqual([r['slot_id'] for r in ledger['calls']],[r['slot_id'] for r in self.slots])
        self.assertEqual(self.counter,40)
        with self.assertRaises(FileExistsError):self.run_mock()

    def test_02_preexisting_global_claim_cannot_start(self):
        b.write_new(b.GLOBAL_CLAIM,{'MOCK_ONLY':True})
        with self.assertRaises(FileExistsError):self.run_mock()
        self.assertEqual(self.counter,0)

    def test_03_preexisting_slot_claim_cannot_start(self):
        b.write_new(self.out/'claims'/'prior.json',{'MOCK_ONLY':True})
        with self.assertRaises(FileExistsError):self.run_mock()
        self.assertEqual(self.counter,0)

    def test_04_method_exception_consumes_once_then_stops(self):
        def fail(*args):raise RuntimeError('MOCK_INTERFACE_ERROR')
        self.assertFalse(self.run_mock(executor=fail))
        ledger=b.read(self.out/'ledger.json')
        self.assertEqual(ledger['consumed'],1);self.assertEqual(ledger['state'],'BLOCKED')
        self.assertEqual(ledger['reserved_method_budget_s'],300)
        self.assertTrue((self.out/'claims'/(self.slots[0]['slot_id']+'.json')).is_file())

    def test_05_technical_status_stops_prefix(self):
        def audit(*args,**kw):return {'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},'usable_U_J':None}
        self.assertFalse(self.run_mock(auditor=audit));self.assertEqual(self.counter,1)

    def test_06_numeric_unknown_stops_prefix(self):
        def audit(*args,**kw):return {'execution':{'execution_status':'UNRESOLVED'},'usable_U_J':None}
        self.assertFalse(self.run_mock(auditor=audit));self.assertEqual(self.counter,1)

    def test_07_verified_deadline_does_not_erase_older_U(self):
        def audit(*args,**kw):return {'execution':{'execution_status':'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'},'usable_U_J':'1'}
        self.assertTrue(self.run_mock(auditor=audit))
        self.assertTrue(all(r['records']['usable_U_J']=='1' for r in b.read(self.out/'ledger.json')['calls']))

    def test_08_post_failure_stops_but_preserves_original_U(self):
        self.assertFalse(self.run_mock(post=lambda *args:{'passed':False,'reason':'MOCK_POST_UNRESOLVED'}))
        ledger=b.read(self.out/'ledger.json')
        self.assertEqual(ledger['consumed'],1)
        self.assertEqual(ledger['calls'][0]['records']['usable_U_J'],'1')
        self.assertFalse(ledger['calls'][0]['postcheck']['passed'])

    def test_09_post_exception_no_retry(self):
        def fail(*args):raise RuntimeError('MOCK_POST_EXCEPTION')
        self.assertFalse(self.run_mock(post=fail));self.assertEqual(self.counter,1)

    def test_10_persist_U_before_post_and_never_replace(self):
        def post(*args):
            ledger=b.read(self.out/'ledger.json')
            self.assertEqual(ledger['calls'][-1]['records']['usable_U_J'],'1')
            return {'passed':True,'new_U':False,'MOCK_EXTERNAL_ENERGY':'0.5'}
        self.assertTrue(self.run_mock(post=post))
        self.assertTrue(all(r['records']['usable_U_J']=='1' for r in b.read(self.out/'ledger.json')['calls']))

    def test_11_reordered_slot_rejected_before_consumption(self):
        with self.assertRaises(ValueError):b.claim_slot(self.ledger,self.slots[1])
        self.assertEqual(self.ledger['consumed'],0)

    def test_12_same_slot_or_active_cannot_consume_again(self):
        b.claim_slot(self.ledger,self.slots[0])
        with self.assertRaises(ValueError):b.claim_slot(self.ledger,self.slots[0])
        with self.assertRaises(ValueError):b.claim_slot(self.ledger,self.slots[1])

    def test_13_blocked_ledger_cannot_resume(self):
        self.ledger['state']='BLOCKED'
        with self.assertRaises(ValueError):b.claim_slot(self.ledger,self.slots[0])

    def test_14_budget_drift_rejected(self):
        self.ledger['reserved_method_budget_s']=1
        with self.assertRaises(ValueError):b.claim_slot(self.ledger,self.slots[0])

    def test_15_calendar_limit_before_first_call(self):
        values=iter([0,0,0,b.WALL])
        self.assertFalse(self.run_mock(clock=lambda:next(values)))
        self.assertEqual(self.counter,0)
        self.assertEqual(b.read(self.out/'ledger.json')['state'],'BLOCKED_CALENDAR_LIMIT')

    def test_16_source_drift_stops_before_first_claim(self):
        with patch.object(b,'admission',side_effect=ValueError('MOCK_SOURCE_DRIFT')):
            with self.assertRaises(ValueError):b.run(entries={})
        self.assertEqual(self.counter,0);self.assertFalse(b.GLOBAL_CLAIM.exists())

    def test_17_actual_authorized_scope_and_core_unchanged(self):
        self.assertEqual((b.SECONDS,b.TOTAL,b.WALL,b.SLOT_WALL,b.POST_SECONDS),(300,12000,19200,480,60))
        self.assertEqual(b.p.lineage_issues(),[])
        self.assertEqual(len(b.p.sources()),191)

    def test_18_claim_written_before_executor(self):
        def execute(job,parent,d,entries):
            ledger=b.read(self.out/'ledger.json');last=ledger['calls'][-1]
            self.assertTrue((self.out/'claims'/(last['slot_id']+'.json')).exists())
            self.assertEqual(ledger['reserved_method_budget_s'],ledger['consumed']*300)
            return self.execute(job,parent,d,entries)
        self.assertTrue(self.run_mock(executor=execute))

    def test_21_entry_owns_never_created_call_directory(self):
        def execute(job,parent,d,entries):
            folder=parent/job['id']
            self.assertFalse(folder.exists())
            folder.mkdir()
            return self.execute(job,parent,d,entries)
        self.assertTrue(self.run_mock(executor=execute))


class WatchdogTests(unittest.TestCase):
    def test_19_calendar_and_method_watchdogs(self):
        self.assertEqual(supervise.expiry({},19200,0),'CALENDAR_LIMIT')
        ledger={'active':{'slot_start_monotonic':0,'phase':'METHOD','phase_start_monotonic':0}}
        self.assertIsNone(supervise.expiry(ledger,419,419))
        self.assertEqual(supervise.expiry(ledger,420,420),'METHOD_RETURN_CLEANUP_LIMIT')

    def test_20_post_cannot_extend_method_but_slot_is_bounded(self):
        ledger={'active':{'slot_start_monotonic':0,'phase':'POST','phase_start_monotonic':310}}
        self.assertIsNone(supervise.expiry(ledger,479,479))
        self.assertEqual(supervise.expiry(ledger,480,480),'SLOT_RETURN_LIMIT')


class PostcheckTests(Fixture):
    def setUp(self):
        super().setUp()
        old=b.ROOT/'results/four_method_comparison01/heft/result.json'
        self.result=b.read(old)
        self.slot=next(s for s in self.slots if s['problem_id']=='base__R1' and s['id']=='heft')
        self.folder=self.out/'post_fixture';self.folder.mkdir()
        b.write_new(self.folder/'wrapper_raw_result.json',self.result)

    def fake_post(self,fresh):
        def evaluate(*a,**kw):
            self.assertTrue((self.folder/'postcheck.claim.json').exists())
            return deepcopy(fresh)
        return patch('thermal.evaluate_candidate',side_effect=evaluate)

    def test_22_valid_post_once_without_search_or_U_replacement(self):
        with self.fake_post(self.result['evaluation']) as evaluator:
            post=b.postcheck(self.slot,self.result,{'usable_U_J':self.result['safe_upper_bound_J']},self.folder)
            self.assertTrue(post['passed']);self.assertFalse(post['new_U'])
            self.assertEqual(evaluator.call_count,1)
            with self.assertRaises(FileExistsError):
                b.postcheck(self.slot,self.result,{'usable_U_J':'1'},self.folder)
            self.assertEqual(evaluator.call_count,1)

    def test_23_post_unknown_rejected_without_retry(self):
        with self.fake_post({'state':'UNRESOLVED','reason':'wall_time_limit','scenes':{}}):
            post=b.postcheck(self.slot,self.result,{'usable_U_J':'1'},self.folder)
            self.assertFalse(post['passed'])
            self.assertTrue((self.folder/'postcheck.claim.json').exists())

    def test_24_post_energy_disagreement_rejected(self):
        fresh=deepcopy(self.result['evaluation']);fresh['weighted_energy_J']=['100','101']
        with self.fake_post(fresh):
            post=b.postcheck(self.slot,self.result,{'usable_U_J':'1'},self.folder)
            self.assertFalse(post['passed']);self.assertFalse(post['checks']['energy_overlap'])
