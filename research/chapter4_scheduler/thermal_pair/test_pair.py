"""Artificial pair-loader/root/state tests; no real search or propagation."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from timing import MethodBudget
from research.chapter4_scheduler.tests.test_method import FakeClock,artificial_input,complete_mock
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest
from research.chapter4_scheduler.comparison.core import CLOCK_ORIGIN
from research.chapter3_method_entry_preparation.prepare import validate_common_input
from . import input as inputs
from . import run

class InputTests(unittest.TestCase):
    def base(self):
        value=read(inputs.SOURCE);return value,value['config'],value['instance']
    def test50_is_original_bytes_semantically(self):
        v,c,i=self.base();dc,di=inputs.derive(c,i,'50');self.assertEqual((dc,di),(c,i));self.assertIsNot(dc,c)
    def test78_only_changes_entry_and_mirrored_default(self):
        v,c,i=self.base();before=digest(v);dc,di=inputs.derive(c,i,'78');self.assertTrue(inputs.validate_pair(dc,di,'78'))
        self.assertEqual(dc['defaults']['initial_temperature_degC'],'78')
        for scene in di['scenarios']:self.assertEqual(scene['entry']['temperature_degC'],['78']*4)
        dc['defaults']['initial_temperature_degC']='50'
        for scene in di['scenarios']:scene['entry']['temperature_degC']=['50']*4
        self.assertEqual((dc,di),(c,i));self.assertEqual(digest(v),before)
    def test_reject_other_temperature_or_bool(self):
        v,c,i=self.base()
        for t in ('77','80',78,True):
            with self.subTest(t=t),self.assertRaises(ValueError):inputs.derive(c,i,t)
    def test_reject_any_other_input_change(self):
        v,c,i=self.base()
        for field in ('limit','platform','window','accuracy','mode'):
            dc,di=inputs.derive(c,i,'78')
            if field=='limit':di['scenarios'][0]['maximum_temperature_degC'][0]='81'
            elif field=='platform':di['platform']['ambient_temperature_degC']='26'
            elif field=='window':di['window_ms']='400'
            elif field=='accuracy':dc['accuracy_targets']['energy_absolute_error_J']='1'
            else:next(iter(di['stage_modes'].values())).pop()
            with self.subTest(field=field),self.assertRaises(ValueError):inputs.validate_pair(dc,di,'78')
    def test_original_contract_rejects_derived_and_is_not_overwritten(self):
        v,c,i=self.base();dc,di=inputs.derive(c,i,'78');v['config'],v['instance']=dc,di
        with self.assertRaises(Exception):validate_common_input(v)
        self.assertTrue(validate_common_input(read(inputs.SOURCE)))
    def test_fresh_loads_share_no_mutable_input(self):
        b=MethodBudget(5);c,i=inputs.load_pair(b,'50');c2,i2=inputs.load_pair(b,'78')
        i['scenarios'][0]['entry']['temperature_degC'][0]='99';self.assertEqual(i2['scenarios'][0]['entry']['temperature_degC'],['78']*4)
        self.assertEqual(b.seconds,5)

class PlanAndStateTests(unittest.TestCase):
    def plan(self):return {'schema':'c01-original-ON-initial-temperature-pair-v1','purpose':'C01_ON_INITIAL_TEMPERATURE_PAIR','paired_temperature_experiment':True,'slots':deepcopy(run.SLOTS),'limits':deepcopy(run.LIMITS),'input_file_sha256':run.SOURCE_SHA256,'thread_environment':deepcopy(run.THREADS)}
    def test_exact_two_original_ON_calls(self):
        p=self.plan();run.validate_plan(p);self.assertEqual([s['temperature'] for s in p['slots']],['50','78']);self.assertEqual(p['limits']['method_s'],300)
    def test_changed_scope_rejected(self):
        for k in ('slots','limits','purpose'):
            p=self.plan()
            if k=='slots':p[k].append(deepcopy(p[k][0]))
            elif k=='limits':p[k]['method_s']=600
            else:p[k]='OLD_PLAN'
            with self.subTest(k=k),self.assertRaises(ValueError):run.validate_plan(p)
    def test_no_SAFE_is_not_ON_completion_or_infeasibility(self):
        d=run.initialization_diagnostic({'initialization':{'status':'NO_SAFE_CONSTRUCTED_WITNESS'},'run_terminal':'UNRESOLVED_STOP'})
        self.assertFalse(d['ON_search_completed']);self.assertFalse(d['complete_SAFE_initialization']);self.assertFalse(d['infeasibility_proved'])
    def test_interrupted_init_with_archive_is_not_completed_ON(self):
        d=run.initialization_diagnostic({'safe_candidate':{},'run_terminal':'BUDGET_EXHAUSTED'})
        self.assertFalse(d['ON_search_completed']);self.assertFalse(d['complete_SAFE_initialization'])
    def test_completed_init_and_ON_are_distinct(self):
        d=run.initialization_diagnostic({'initialization':{'status':'BOUNDED_SEARCH_COMPLETED'},'initial_safe_snapshot':{},'run_terminal':'BUDGET_EXHAUSTED'})
        self.assertTrue(d['complete_SAFE_initialization']);self.assertFalse(d['ON_search_completed'])

class WorkerTests(unittest.TestCase):
    def exercise(self,temperature,mode='safe'):
        import thermal
        clock=FakeClock();original=MethodBudget
        class FixtureBudget(original):
            def __init__(self,seconds):super().__init__(seconds,clock=clock)
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='MOCK_ONLY-temperature-pair-') as tmp:
            out=Path(tmp);slot=next(s for s in run.SLOTS if s['temperature']==temperature);folder=out/'calls'/slot['id'];folder.mkdir(parents=True)
            config,instance,candidate=artificial_input(two_scenes=True)
            for scene in instance['scenarios']:scene['entry']['temperature_degC']=[temperature]*4
            save(out/'plan.json',{'slots':run.SLOTS,'inputs':{temperature:{'config_sha256':digest(config),'input_sha256':digest(instance)}}})
            save(out/'plan_identity.json',{'sha256':sha(out/'plan.json')});save(folder/'claim.json',{'slot':slot,'plan_sha256':sha(out/'plan.json')})
            def evaluator(i,c,a,b):
                clock.now+=1
                if mode=='technical':raise RuntimeError('ARTIFICIAL_FAILURE')
                receipt=complete_mock(i,c,a,b)
                # Invented thermal boxes must enclose the fixture's hot entry.
                for scene in i['scenarios']:
                    for node,t in zip(i['platform']['node_order'],scene['entry']['temperature_degC']):
                        receipt['scenes'][scene['id']]['peaks_degC'][node]=[t,t]
                        receipt['scenes'][scene['id']]['minimum_degC'][node]=[t,t]
                if mode=='no_safe':
                    receipt.update(state='THERMAL_VIOLATION',rankable_energy=False,weighted_energy_J=None,safe_upper_bound_J=None,
                        violations=[{'scene_id':'S0','node':'c1','time_s':'1/100','temperature_degC':['81','82'],'limit_degC':'80','formed_at_elapsed_s':b.elapsed}])
                return receipt
            def initializer(i,c,b,assess,**kwargs):
                self.assertEqual(b.seconds,300);assess(candidate,'heft:eft')
                return {'status':'NO_SAFE_CONSTRUCTED_WITNESS' if mode=='no_safe' else 'BOUNDED_SEARCH_COMPLETED'}
            with patch.object(run,'verify'),patch.object(run.time,'monotonic',clock),patch.dict(run.os.environ,run.THREADS), \
                    patch('timing.MethodBudget',FixtureBudget),patch.object(run,'load_pair',return_value=(config,instance)) as loads, \
                    patch('thermal.evaluate_candidate',side_effect=evaluator),patch('heft_method.run_heft',side_effect=initializer), \
                    patch('research.chapter4_scheduler.blocking.method.candidate_packets',return_value=iter(())) as packets,patch('builtins.print'):
                failed=run.worker(out,slot['id']);r=read(folder/'method_return.json');self.assertEqual(bool(failed),mode=='technical');self.assertEqual(loads.call_args.args[1],temperature)
                if mode=='safe':
                    self.assertTrue(r['initialization_diagnostic']['ON_search_completed']);save(folder/'post_claim.json',{'slot':slot,'plan_sha256':sha(out/'plan.json')})
                    self.assertFalse(run.worker(out,slot['id'],post=True));q=read(folder/'post_return.json');self.assertTrue(q['passed']);self.assertEqual(q['timing']['limit_s'],60);self.assertEqual(q['timing']['clock_origin'],CLOCK_ORIGIN)
                elif mode=='no_safe':
                    self.assertFalse(r['has_SAFE_archive']);self.assertEqual(r['terminal'],'NORMAL_NO_SAFE');self.assertFalse(r['initialization_diagnostic']['ON_search_completed']);packets.assert_not_called()
            return r
    def test_both_temperatures_same300_60_roots(self):
        for t in ('50','78'):
            with self.subTest(t=t):self.exercise(t)
    def test_no_SAFE_init_stops_before_graph(self):self.exercise('78','no_safe')
    def test_technical_failure_is_not_thermal_or_success(self):self.exercise('78','technical')

class BatchTests(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-seven-batch-") as tmp:
            out=Path(tmp);save(out/"plan.json",{"slots":run.SLOTS});save(out/"plan_identity.json",{"sha256":sha(out/"plan.json")})
            def fake(argv,**kwargs):
                phase=argv[4];slot=argv[argv.index("--slot")+1];folder=out/"calls"/slot
                self.assertEqual(argv[3],"research.chapter4_scheduler.thermal_pair.run")
                self.assertEqual(kwargs["timeout"],420 if phase=="worker" else 90)
                if mode=="timeout":raise subprocess.TimeoutExpired(argv,420,output=b"MOCK_PARTIAL")
                fail=mode=="method_failure" and phase=="worker" or mode=="post_failure" and phase=="post"
                save(folder/("method_return.json" if phase=="worker" else "post_return.json"),{"has_SAFE_archive":mode!="no_safe","normal_stop":not fail,"error":None})
                return SimpleNamespace(returncode=int(fail),stdout="MOCK_ONLY",stderr="")
            with patch.object(run,"verify"),patch.object(run,"resources",return_value={"sufficient":True}), \
                    patch.object(run.subprocess,"run",side_effect=fake) as process,patch("builtins.print"):
                failed=run.batch(out)
            r=run.read(out/"batch_return.json")
            self.assertEqual(len(r["consumed_method_slots"]),2 if mode in ("success","no_safe") else 1)
            self.assertEqual(process.call_count,4 if mode=="success" else 2 if mode=="no_safe" else 2 if mode=="post_failure" else 1)
            self.assertEqual(bool(failed),mode not in ("success","no_safe"));self.assertTrue(r["paired_temperature_experiment"])
            with patch.object(run,"verify"),self.assertRaises(FileExistsError):run.batch(out)
            if mode=="timeout":self.assertEqual((out/"calls"/run.SLOTS[0]["id"]/"worker_partial_stdout.log").read_bytes(),b"MOCK_PARTIAL")

    def test_two_methods_and_posts_once(self):self.exercise("success")
    def test_no_SAFE_preserved_without_post_or_replacement(self):self.exercise("no_safe")
    def test_method_failure_halts_future_slots(self):self.exercise("method_failure")
    def test_post_failure_halts_future_slots(self):self.exercise("post_failure")
    def test_watchdog_preserves_partial_logs_and_never_retries(self):self.exercise("timeout")


if __name__=="__main__":unittest.main()
