"""K164 remaining38 original-budget continuation fixtures; all scientific work is mocked."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timedelta
import tempfile
import unittest
from unittest.mock import patch
import resume_controller as r
import safe_io
import resume_supervise as supervise


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
        clock_patch=patch.object(r,'remaining_calendar',return_value=19200.)
        clock_patch.start();self.addCleanup(clock_patch.stop)

    def execute(self,job,parent,d,entries):
        self.counter+=1
        folder=parent/job['id'];self.assertFalse(folder.exists());folder.mkdir()
        return {'MOCK_ONLY':True},{'input_verified':True}

    def auditor(self,*args,**kw):
        return {'execution':{'execution_status':'NORMAL_COMPLETION'},'usable_U_J':'1','current_schedule_audit':{'passed':True}}

    def post(self,*args):self.post_count+=1;return {'passed':True,'new_U':False}

    def run_mock(self,executor=None,auditor=None,post=None,admission=None,remaining=19200):
        with patch.object(r,'admission',side_effect=admission or (lambda:{'slots':r.slots()})),\
             patch.object(r,'remaining_calendar',return_value=remaining):
            return r.run(entries={'MOCK_ONLY':True},executor=executor or self.execute,
                auditor=auditor or self.auditor,post=post or self.post,clock=lambda:100.)


class ContinuationTests(Fixture):
    def test_01_exact_remaining_38_and_original_order(self):
        self.assertEqual(r.slots(),r.prior.p.slots()[2:])
        self.assertEqual(len(r.slots()),38)
        self.assertEqual([s['ordinal'] for s in r.slots()],list(range(3,41)))
        self.assertEqual([s['id'] for s in r.slots()[:6]],['heft','sa101','sa102','sa103','sa104','sa105'])
        self.assertEqual(sum(s['seconds'] for s in r.slots()),11400)

    def test_02_full_38_mock_prefix_total_40_never_first_two(self):
        self.assertTrue(self.run_mock())
        ledger=r.read(self.out/'ledger.json');terminal=r.read(self.out/'worker_terminal.json')
        self.assertEqual(self.counter,38);self.assertEqual(self.post_count,38)
        self.assertEqual(ledger['consumed_new'],38);self.assertEqual(ledger['consumed_total'],40)
        self.assertEqual(ledger['reserved_total_method_s'],12000)
        self.assertEqual(terminal['state'],'COMPLETED')
        self.assertEqual([v['slot_id'] for v in ledger['calls']],[s['slot_id'] for s in r.slots()])

    def test_03_no_restart_or_claim_reuse(self):
        self.assertTrue(self.run_mock())
        with self.assertRaises(FileExistsError):self.run_mock()
        self.assertEqual(self.counter,38)

    def test_04_old_first_two_are_rejected(self):
        ledger=r.initial_ledger()
        for slot in r.prior.p.slots()[:2]:
            with self.assertRaises(ValueError):r.claim(ledger,slot)
        self.assertEqual(ledger['consumed_total'],2)

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
        self.assertEqual(terminal['consumed_total'],3)
        self.assertEqual(terminal['state'],'BLOCKED')
        self.assertEqual(self.post_count,0)

    def test_08_numeric_unknown_stops_before_next_method(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NUMERICAL_UNRESOLVED'},'usable_U_J':None}
        self.assertFalse(self.run_mock(auditor=audit))
        self.assertEqual(self.counter,1);self.assertEqual(self.post_count,0)

    def test_09_verified_deadline_preserves_U_and_continues(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'},'usable_U_J':'1','current_schedule_audit':{'passed':True}}
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
        self.assertEqual(terminal['consumed_total'],3)
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
        self.assertEqual(r.read(self.out/'worker_terminal.json')['consumed_total'],2)
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
            self.assertGreaterEqual(status['consumed_total'],3)
            self.assertEqual(status['active']['phase'],'METHOD')
            return self.execute(job,parent,d,entries)
        self.assertTrue(self.run_mock(executor=execute))
        self.assertEqual(len(r.prior.sources()),240)

    def test_21_no_U_continues_without_post_or_zero_energy(self):
        def audit(*args, **kw):
            return {'execution': {'execution_status': 'NORMAL_COMPLETION'},
                    'usable_U_J': None, 'current_schedule_audit': {'passed': True}}
        self.assertTrue(self.run_mock(auditor=audit))
        self.assertEqual((self.counter, self.post_count), (38, 0))
        for row in r.read(self.out/'ledger.json')['calls']:
            self.assertIsNone(row['records']['usable_U_J'])
            self.assertEqual(row['postcheck']['state'], 'NOT_APPLICABLE_NO_USABLE_U')
            self.assertFalse(row['postcheck']['new_U'])
            self.assertEqual(row['postcheck_wall_s'], 0)

    def test_22_failed_current_deadline_check_stops_even_if_execution_is_normal(self):
        def audit(*args, **kw):
            return {'execution': {'execution_status': 'NORMAL_COMPLETION'},
                    'usable_U_J': '1', 'current_schedule_audit': {'passed': False}}
        self.assertFalse(self.run_mock(auditor=audit))
        self.assertEqual((self.counter, self.post_count), (1, 0))
        self.assertEqual(r.read(self.out/'worker_terminal.json')['consumed_total'], 3)

    def test_23_missing_current_deadline_check_is_not_success(self):
        def audit(*args, **kw):
            return {'execution': {'execution_status': 'NORMAL_COMPLETION'}, 'usable_U_J': '1'}
        self.assertFalse(self.run_mock(auditor=audit))
        self.assertEqual((self.counter, self.post_count), (1, 0))

    def test_24_thermal_unresolved_does_not_get_reclassified_as_seed_exhaustion(self):
        def audit(*args, **kw):
            return {'execution': {'execution_status': 'STATUS_UNRESOLVED', 'thermal_unresolved': True},
                    'usable_U_J': None, 'current_schedule_audit': {'passed': True}}
        self.assertFalse(self.run_mock(auditor=audit))
        self.assertEqual((self.counter, self.post_count), (1, 0))
        row = r.read(self.out/'claims'/(r.slots()[0]['slot_id']+'_method_return.json'))
        self.assertTrue(row['records']['execution']['thermal_unresolved'])

    def test_25_changed_300_second_slot_cannot_claim_budget(self):
        ledger = r.initial_ledger()
        slot = deepcopy(r.slots()[0]); slot['seconds'] = 301
        with self.assertRaises(ValueError): r.claim(ledger, slot)
        self.assertEqual((ledger['consumed_new'], ledger['consumed_total'], ledger['reserved_total_method_s']),
                         (0, 2, 600))

    def test_26_original_absolute_calendar_is_shared_and_tampering_is_rejected(self):
        old_declaration = {'MOCK_ONLY': True}
        r.write_new(self.old/'declaration.json', old_declaration)
        start = '2026-10-22T08:26:38.073713+00:00'
        end = '2026-10-22T13:46:38.073713+00:00'
        claim = {'protocol': r.prior.PROTOCOL, 'started_utc': start,
                 'calendar_deadline_utc': end,
                 'script_sha256': r.sha(r.prior.HERE/'deadline_supervise.py'),
                 'declaration_sha256': r.sha(self.old/'declaration.json')}
        r.write_new(self.old/'launcher_claim.json', claim)
        with patch.object(r.prior, 'OUT', self.old):
            self.assertEqual(r.deadline_utc(), datetime.fromisoformat(end))
            self.assertEqual(r.deadline_utc(), r.prior.deadline_utc())
            claim['calendar_deadline_utc'] = (datetime.fromisoformat(end)+timedelta(seconds=1)).isoformat()
            safe_io.save(self.old/'launcher_claim.json', claim)
            with self.assertRaises(ValueError): r.deadline_utc()

    def test_29_claim_rechecks_calendar_before_consuming_next_slot(self):
        ledger = r.initial_ledger()
        slot = r.slots()[0]
        with patch.object(r, 'remaining_calendar', return_value=0):
            with self.assertRaises((TimeoutError, ValueError)):
                r.claim(ledger, slot)
        self.assertEqual((ledger['consumed_new'], ledger['consumed_total'], ledger['reserved_total_method_s']),
                         (0, 2, 600))
        self.assertFalse((self.out/'claims'/(slot['slot_id']+'.json')).exists())


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
        self.assertEqual(supervise.process_terminal(0,None,{'state':'COMPLETED','consumed_new':38})['state'],'COMPLETED')
        self.assertNotEqual(supervise.process_terminal(0,None,{'state':'COMPLETED','consumed_new':37})['state'],'COMPLETED')

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


class FreezeBindingTests(unittest.TestCase):
    def report(self):
        return {'protocol': r.PROTOCOL, 'passed': True, 'tests_run': 1,
                'errors': 0, 'failures': 0, 'skipped': 0, 'error': None,
                'source_sha256': r.sources(), 'source_unchanged': True,
                'blocked_calls': {'MOCK_ONLY': 0}, 'research_calls': 0,
                'native_calls': 0, 'thermal_evaluations': 0, 'physical_models': 0}

    def test_27_freeze_binds_old_declaration_budget_and_original_deadline(self):
        with tempfile.TemporaryDirectory(dir=r.REPO/'.runtime') as tmp:
            root = Path(tmp); old = root/'old'; old.mkdir()
            r.write_new(old/'declaration.json', {'MOCK_ONLY': True, 'call_limit': 40})
            repair = root/'repair'; repair.mkdir()
            r.write_new(repair/'repair_review.json', {'MOCK_ONLY': True, 'passed': True})
            r.write_new(repair/'post_summary.json', {'MOCK_ONLY': True, 'passed': True, 'new_U': False})
            end = datetime.fromisoformat('2026-10-22T13:46:38.073713+00:00')
            gate = root/'checks.json'; r.write_new(gate, self.report())
            with patch.object(r, 'OUT', root/'new_campaign'), patch.object(r, 'OLD', old), \
                 patch.object(r, 'REPAIR', repair), patch.object(r, 'GLOBAL_CLAIM', root/'global.json'), \
                 patch.object(r, 'prior_gate', return_value=True), \
                 patch.object(r, 'remaining_calendar', return_value=100), patch.object(r, 'deadline_utc', return_value=end):
                result = r.freeze(gate)
                self.assertEqual((result['remaining_calls'], result['prior_calls']), (38, 2))
                declared = r.admission()
                self.assertEqual(declared['prior_declaration_sha256'], r.sha(old/'declaration.json'))
                self.assertEqual((declared['prior_consumed'], declared['prior_reserved_method_s']), (2, 600))
                self.assertEqual((declared['remaining_calls'], declared['remaining_reserved_method_s']), (38, 11400))
                self.assertEqual((declared['campaign_call_limit'], declared['campaign_reserved_method_s']), (40, 12000))
                self.assertEqual(declared['original_calendar_deadline_utc'], end.isoformat())
                self.assertTrue(declared['calendar_was_not_reset'])
                self.assertFalse(declared['retry_methods'])
                self.assertEqual(r.read(r.OUT/'ledger.json')['consumed_total'], 2)
                with self.assertRaises(FileExistsError): r.freeze(gate)
                altered = deepcopy(declared); altered['prior_declaration_sha256'] = 'wrong-old-declaration'
                safe_io.save(r.OUT/'declaration.json', altered)
                with self.assertRaises(ValueError): r.admission()

    def test_28_failed_prior_repair_proof_cannot_create_new_campaign(self):
        with tempfile.TemporaryDirectory(dir=r.REPO/'.runtime') as tmp:
            root = Path(tmp); gate = root/'checks.json'; r.write_new(gate, self.report())
            with patch.object(r, 'OUT', root/'absent'), patch.object(r, 'GLOBAL_CLAIM', root/'global.json'), \
                 patch.object(r, 'prior_gate', side_effect=ValueError('MOCK_REPAIR_PROOF_INCOMPLETE')):
                with self.assertRaises(ValueError): r.freeze(gate)
                self.assertFalse(r.OUT.exists())
                self.assertFalse(r.GLOBAL_CLAIM.exists())
