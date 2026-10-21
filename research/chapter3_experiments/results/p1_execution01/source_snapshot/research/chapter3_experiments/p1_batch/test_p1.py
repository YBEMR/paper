"""P1 input/dispatch and once-only execution fixtures; no research or heat calls."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import p1_controller as r
import p1_entry as p
import p1_supervise as supervisor


class InputTests(unittest.TestCase):
    def test_01_only_declared_P1_IDS(self):
        for bad in ('base__R1','response_M__R1','initial_78__R1','response_R__R6'):
            with self.assertRaises(ValueError):p.fresh_input(bad)
            with self.assertRaises(ValueError):p.jobs(bad)

    def test_02_five_inputs_only_predeclared_response_change(self):
        for pid in p.PROBLEMS:
            with self.subTest(pid=pid):
                _,config,one=p.fresh_input(pid)
                _,baseconfig,base=p.p0.fresh_input(pid.replace('response_R__','base__'))
                self.assertEqual(config,baseconfig)
                self.assertEqual(one['platform'],base['platform'])
                self.assertEqual(one['scenarios'],base['scenarios'])
                self.assertEqual(one['duration_scale'],base['duration_scale'])
                self.assertFalse(one['ablation_input']);self.assertTrue(base['ablation_input'])
                a,b=deepcopy(one),deepcopy(base)
                for obj in (a,b):
                    for key in ('id','condition_id','experiment_group','response_variant','stage_modes','ablation_input'):obj.pop(key)
                    obj['settings'].pop('response_variant')
                self.assertEqual(a,b)

    def test_03_all_modes_inverse_formula_and_activity_energy(self):
        for pid in p.PROBLEMS:
            _,_,one=p.fresh_input(pid)
            _,_,base=p.p0.fresh_input(pid.replace('response_R__','base__'))
            for stage,modes in one['stage_modes'].items():
                old={(m['unit_id'],m['opp_id']):m for m in base['stage_modes'][stage]}
                self.assertEqual(set(old),{(m['unit_id'],m['opp_id']) for m in modes})
                for m in modes:
                    high=next(v for v in modes if v['unit_id']==m['unit_id'] and v['opp_id']=='H')
                    self.assertEqual(F(m['alpha']),1)
                    self.assertEqual(F(m['duration_ms']),F(m['d_ref_ms'])*F(high['frequency_GHz'])/F(m['frequency_GHz']))
                    self.assertEqual(F(m['activity_energy_J']),F(m['activity_power_W'])*F(m['duration_ms'])/1000)
                    a,b=deepcopy(m),deepcopy(old[(m['unit_id'],m['opp_id'])])
                    for obj in (a,b):
                        for key in ('alpha','duration_ms','activity_energy_J'):obj.pop(key)
                    self.assertEqual(a,b)

    def test_04_input_declaration_covers_full_scenes(self):
        for pid in p.PROBLEMS:
            d,triple=p.input_declaration(pid)
            self.assertEqual(d['input_identities']['input_sha256'],r.canonical(triple[2]))
            self.assertEqual(set(d['scene_spec']),{'AB_offset_0ms','AC_offset_0ms'})
            self.assertEqual([len(x) for x in d['first_opened_by_scene'].values()],[2,2])
            self.assertEqual([len(x) for x in d['linked_opened_by_job']['anchor_linked4'].values()],[4,4])

    def test_05_exact_40_slots_order_and_seeds(self):
        slots=p.slots();self.assertEqual(len(slots),40)
        self.assertEqual([s['ordinal'] for s in slots],list(range(1,41)))
        self.assertEqual(len({s['slot_id'] for s in slots}),40)
        self.assertEqual(sum(s['seconds'] for s in slots),12000)
        for i,pid in enumerate(p.PROBLEMS):
            jobs=p.jobs(pid)
            self.assertEqual([x.get('seed') for x in jobs if x['method']=='sa'],list(range(101,106)))
            self.assertEqual({x['id'] for x in jobs},{'whole_milp','anchor_linked4','heft',*('sa'+str(v) for v in range(101,106))})
            self.assertEqual([x['id'] for x in jobs],
                [x['id'] for x in p.p0.jobs('base__R'+str(i+1))])

    def test_06_inherited_function_and_file_lineage(self):
        for item in r.read(r.HERE/'lineage.json'):
            source=r.REPO/item['origin'];self.assertEqual(r.sha(source),item['sha256'])
            text=source.read_text(encoding='utf-8')
            if not item.get('whole_file'):
                lines=text.splitlines(keepends=True)
                node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==item['function'])
                text=''.join(lines[node.lineno-1:node.end_lineno]).rstrip()+'\n'
            for old,new in item['replacements']:
                self.assertIn(old,text);text=text.replace(old,new)
            if item.get('whole_file'):
                dest='p1_dispatch.py' if source.name=='dispatch.py' else 'p1_supervise.py'
                self.assertEqual((r.HERE/dest).read_text(encoding='utf-8'),text)
            else:
                dest='p1_entry.py' if item['function']=='result_records' else 'p1_controller.py'
                target=(r.HERE/dest).read_text(encoding='utf-8');lines=target.splitlines(keepends=True)
                node=next(n for n in ast.parse(target).body if isinstance(n,ast.FunctionDef) and n.name==item['function'])
                self.assertEqual(''.join(lines[node.lineno-1:node.end_lineno]).rstrip()+'\n',text)


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
               'script_sha256':r.sha(r.HERE/'p1_supervise.py'),'declaration_sha256':r.sha(self.out/'declaration.json')}
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


if __name__=='__main__':unittest.main()
