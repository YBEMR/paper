"""P2 real-chain lifecycle tests: all research functions mocked."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import p2_controller as r
import p2_entry as p
import p2_supervise as supervisor


class AuthorizedScopeTests(unittest.TestCase):
    def report(self):
        return {'protocol': r.PROTOCOL, 'passed': True, 'tests_run': 1, 'errors': 0,
            'failures': 0, 'skipped': 0, 'error': None, 'source_sha256': r.sources(),
            'source_unchanged': True, 'P0_critical_unchanged': True,
            'blocked_calls': {'MOCK_ONLY': 0}, 'research_calls': 0, 'native_calls': 0,
            'physical_models': 0, 'thermal_evaluations': 0}

    def test_01_preparation_and_scientific_inputs_unchanged(self):
        import prepare_p2 as prep
        self.assertFalse(prep.admission(r.BASE.parent)['authorised_to_execute'])
        self.assertEqual(len(r.sources()), 224)
        self.assertEqual((r.COUNT, r.WALL, r.POST_SECONDS), (40, 19200, 60))
        for pid in p.PROBLEMS:
            self.assertEqual(p.input_declaration(pid)[0], r.read(r.BASE)['inputs'][pid])
            self.assertEqual(prep.contrast(pid)['response_variant'], 'H')

    def test_02_lifecycle_and_supervisor_exact_inheritance(self):
        for item in r.read(r.HERE/'lineage.json'):
            source = r.REPO/item['origin']
            self.assertEqual(r.sha(source), item['sha256'])
            text = source.read_text(encoding='utf-8')
            target = (r.HERE/item['target']).read_text(encoding='utf-8')
            if item.get('functions'):
                def selected(s):
                    lines = s.splitlines(keepends=True)
                    nodes = {n.name: n for n in ast.parse(s).body if isinstance(n, ast.FunctionDef)}
                    return '\n\n'.join(''.join(lines[nodes[k].lineno-1:nodes[k].end_lineno]).rstrip()
                                       for k in item['functions'])+'\n'
                text, target = selected(text), selected(target)
            for old, new in item['replacements']:
                text = text.replace(old, new)
            self.assertEqual(text, target)

    def test_03_new_freeze_matches_preparation_without_changing_old_grant(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); gate = folder/'mock_checks.json'
            r.write_new(gate, self.report())
            prior = r.sha(r.BASE.parent/'ledger.json')
            with patch.object(r, 'OUT', folder/'new_campaign'), patch.object(r, 'GLOBAL_CLAIM', folder/'global.json'):
                result = r.freeze(gate)
                self.assertEqual(result['calls'], 40)
                self.assertEqual(result['source_files'], 224)
                d = r.admission()
                self.assertTrue(d['authorized'])
                self.assertEqual(d['P2_preparation_sha256'], r.sha(r.BASE))
                self.assertEqual(d['change_condition'], 'P0_original_H_initial_temperature_50_to_78_only')
                self.assertEqual(r.read(r.OUT/'ledger.json')['consumed_total'], 0)
                with self.assertRaises(FileExistsError): r.freeze(gate)
            self.assertEqual(r.sha(r.BASE.parent/'ledger.json'), prior)
            self.assertFalse(r.read(r.BASE)['authorised_to_execute'])

    def test_04_bad_or_old_precheck_cannot_freeze(self):
        for key, value in (('protocol', 'K158-old-budget'), ('source_sha256', {}),
                           ('passed', False), ('native_calls', 1), ('P0_critical_unchanged', False)):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); gate = folder/'bad.json'; g = self.report(); g[key] = value
                r.write_new(gate, g)
                with patch.object(r, 'OUT', folder/'new_campaign'), patch.object(r, 'GLOBAL_CLAIM', folder/'global.json'):
                    with self.assertRaises(ValueError): r.freeze(gate)
                    self.assertFalse(r.OUT.exists())

    def test_05_no_usable_safe_U_does_not_start_post_evaluation(self):
        result = r.postcheck(p.slots()[0], None, {'usable_U_J': None}, Path('.'))
        self.assertTrue(result['passed'])
        self.assertFalse(result['new_U'])
        self.assertEqual(result['state'], 'NOT_APPLICABLE_NO_USABLE_U')

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=r.REPO/'.runtime');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.out=self.root/'P1';self.out.mkdir()
        for name in ('claims','calls'):(self.out/name).mkdir()
        for name,value in (('OUT',self.out),('GLOBAL_CLAIM',self.root/'P1_global.json')):
            pp=patch.object(r,name,value);pp.start();self.addCleanup(pp.stop)
        r.write_new(self.out/'declaration.json',{'MOCK_ONLY':True})
        r.safe_io.save(self.out/'ledger.json',r.initial_ledger());r.publish_status(r.initial_ledger(),phase='DECLARED')
        self.count=0;self.posts=0
    def executor(self,job,parent,definition,entries):
        self.count+=1;folder=parent/job['id'];self.assertFalse(folder.exists());folder.mkdir()
        return {'MOCK_ONLY':True},{'input_verified':True}
    def auditor(self,*args,**kw):
        return {'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED' if kw.get('errors') else 'NORMAL_COMPLETION'},'usable_U_J':'1'}
    def post(self,*args):self.posts+=1;return {'passed':True,'new_U':False}
    def run_mock(self,executor=None,auditor=None,post=None,admission=None,remaining=19200):
        d={'slots':r.slots(),'inputs':{pid:{'problem_id':pid} for pid in p.PROBLEMS}}
        with patch.object(r,'admission',side_effect=admission or (lambda:d)),patch.object(r,'remaining_calendar',return_value=remaining):
            return r.run(clock=lambda:100.,entries={'MOCK_ONLY':True},executor=executor or self.executor,
                         auditor=auditor or self.auditor,post=post or self.post)


class LifecycleTests(Fixture):
    def test_07_full_40_mock_and_one_post_each(self):
        self.assertTrue(self.run_mock());self.assertEqual((self.count,self.posts),(40,40))
        ledger=r.read(self.out/'ledger.json');terminal=r.read(self.out/'worker_terminal.json')
        self.assertEqual(ledger['reserved_total_method_s'],12000);self.assertEqual(ledger['state'],'COMPLETED')
        self.assertEqual(terminal['consumed_total'],40);self.assertEqual(terminal['unstarted_remaining'],0)
        self.assertTrue(all((self.out/'claims'/(s['slot_id']+'_method_return.json')).is_file() for s in r.slots()))

    def test_08_no_restart(self):
        self.assertTrue(self.run_mock())
        with self.assertRaises(FileExistsError):self.run_mock()
        self.assertEqual(self.count,40)

    def test_09_failure_consumes_and_stops(self):
        def broken(*args):self.count+=1;raise RuntimeError('MOCK_NATIVE_ERROR')
        self.assertFalse(self.run_mock(executor=broken));self.assertEqual(self.count,1);self.assertEqual(self.posts,0)
        self.assertEqual(r.read(self.out/'worker_terminal.json')['consumed_total'],1)

    def test_10_post_failure_no_second_method(self):
        self.assertFalse(self.run_mock(post=lambda *a:{'passed':False,'new_U':False}))
        self.assertEqual(self.count,1);self.assertEqual(r.read(self.out/'worker_terminal.json')['state'],'BLOCKED')

    def test_11_normal_deadline_can_continue(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'},'usable_U_J':'1'}
        self.assertTrue(self.run_mock(auditor=audit));self.assertEqual(self.count,40)

    def test_12_numeric_unresolved_stops(self):
        def audit(*a,**kw):return {'execution':{'execution_status':'NUMERICAL_UNRESOLVED'},'usable_U_J':None}
        self.assertFalse(self.run_mock(auditor=audit));self.assertEqual((self.count,self.posts),(1,0))

    def test_13_calendar_zero_no_slot_consumed(self):
        self.assertFalse(self.run_mock(remaining=0));self.assertEqual(self.count,0)
        self.assertEqual(r.read(self.out/'worker_terminal.json')['unstarted_remaining'],40)

    def test_14_immutable_receipt_survives_ledger_IO_failure(self):
        original=r.safe_io.save
        def fail(path,value,**kw):
            if Path(path).name=='ledger.json' and value['calls'] and 'records' in value['calls'][-1]:
                raise PermissionError('MOCK_PERMANENT_LEDGER_LOCK')
            return original(path,value,**kw)
        with patch.object(r.safe_io,'save',side_effect=fail):self.assertFalse(self.run_mock())
        first=r.slots()[0]['slot_id'];self.assertTrue((self.out/'claims'/(first+'_method_return.json')).is_file())
        self.assertEqual(r.read(self.out/'worker_terminal.json')['state'],'STOPPED_EXCEPTION')
        self.assertEqual(self.count,1)

    def test_15_source_drift_stops_after_first_receipt(self):
        calls=0;d={'slots':r.slots(),'inputs':{pid:{'problem_id':pid} for pid in p.PROBLEMS}}
        def admit():
            nonlocal calls
            calls+=1
            if calls>2:raise ValueError('MOCK_DRIFT')
            return d
        self.assertFalse(self.run_mock(admission=admit));self.assertEqual(self.count,1)

    def test_16_claim_reorder_duplicate_old_batch_rejected(self):
        ledger=r.initial_ledger()
        with self.assertRaises(ValueError):r.claim(ledger,r.slots()[1])
        old=deepcopy(r.slots()[0]);old['problem_id']='base__R1'
        with self.assertRaises(ValueError):r.claim(ledger,old)
        r.claim(ledger,r.slots()[0],clock=lambda:1.)
        with self.assertRaises(ValueError):r.claim(ledger,r.slots()[0])

    def test_17_calendar_exact_and_tampering_rejected(self):
        start='2026-10-21T14:00:00+00:00'
        claim={'protocol':r.PROTOCOL,'started_utc':start,'calendar_deadline_utc':(datetime.fromisoformat(start)+timedelta(seconds=19200)).isoformat(),
               'script_sha256':r.sha(r.HERE/'p2_supervise.py'),'declaration_sha256':r.sha(self.out/'declaration.json')}
        r.write_new(self.out/'launcher_claim.json',claim)
        self.assertEqual(r.deadline_utc(),datetime.fromisoformat(start)+timedelta(seconds=19200))
        claim['calendar_deadline_utc']=(datetime.fromisoformat(start)+timedelta(seconds=19201)).isoformat()
        r.safe_io.save(self.out/'launcher_claim.json',claim)
        with self.assertRaises(ValueError):r.deadline_utc()

    def test_18_watchdogs_and_missing_terminal(self):
        status={'active':{'slot_start_monotonic':0.,'phase_start_monotonic':0.,'phase':'METHOD'}}
        with patch.object(r,'remaining_calendar',return_value=1000):
            self.assertIsNone(supervisor.expiry(status,419.))
            self.assertEqual(supervisor.expiry(status,420.),'METHOD_RETURN_LIMIT')
            self.assertEqual(supervisor.expiry(status,480.),'SLOT_RETURN_LIMIT')
        self.assertNotEqual(supervisor.process_terminal(0,None,None)['state'],'COMPLETED')
        self.assertNotEqual(supervisor.process_terminal(0,None,{'state':'COMPLETED','consumed_new':39})['state'],'COMPLETED')
        self.assertEqual(supervisor.process_terminal(0,None,{'state':'COMPLETED','consumed_new':40})['state'],'COMPLETED')


