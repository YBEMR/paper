"""Synthetic structure/clock/receipt checks. Real thermal propagation forbidden."""
import ast
from copy import deepcopy
import inspect
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, changed, FakeClock
from research.chapter4_scheduler import method as common
from research.chapter4_scheduler.blocking import method as blocking
from research.chapter4_scheduler.validation.lifecycle import execute_heft
from timing import MethodBudget
from thermal import Exhausted
import heft_method as i0
from . import initializer as i1
from . import fallback
from .admission import AdmissionClosed, require_admission

ROOT = Path(__file__).resolve().parents[3]
BASE = '4c98f681ae499bd8f0cd081bcc99a0e9d8281f5b'


def complete(candidate):
    return {'status':'COMPLETE_LEGAL_CANDIDATE','reason':None,'candidate':deepcopy(candidate)}


def failed():
    return {'status':'CONSTRUCTION_UNRESOLVED','reason':'MOCK_NO_INSERTION','candidate':None}


class I1Tests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock()
        self.budget=MethodBudget(300,clock=self.clock)
        self.config,self.instance,self.candidate=artificial_input(two_scenes=True)
        self.directory=ROOT.parent/('mock_i1_'+uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        p=self.directory.resolve()
        assert p.is_relative_to(ROOT.parent.resolve()) and p.name.startswith('mock_i1_')
        shutil.rmtree(p)

    def receipt(self,candidate=None,at=181):
        self.clock.now=1000+at
        return complete_mock(self.instance,candidate or self.candidate,self.config['accuracy_targets'],self.budget)

    def test_original_I0_and_ON_search_AST_preserved(self):
        old=subprocess.check_output(['git','show',BASE+':research/chapter3_experiments/heft_method.py'],cwd=ROOT)
        self.assertEqual(old,(ROOT/'research/chapter3_experiments/heft_method.py').read_bytes())
        old=ast.parse(subprocess.check_output(['git','show',BASE+':research/chapter4_scheduler/blocking/method.py'],cwd=ROOT,text=True))
        new=ast.parse(inspect.getsource(blocking))
        fun=lambda tree,name:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        for name in ('energy_targets','candidate_packets'):
            self.assertEqual(ast.dump(fun(old,name)),ast.dump(fun(new,name)))
        loops=lambda tree:[ast.dump(n) for n in ast.walk(fun(tree,'execute_reconstruction')) if isinstance(n,ast.While)]
        self.assertEqual(loops(old),loops(new))

    def test_fallback_insertion_AST_identical_except_priority_provider(self):
        a=ast.parse(inspect.getsource(i0.build_heft_candidate)).body[0]
        b=ast.parse(inspect.getsource(fallback.build_fallback_candidate)).body[0]
        b.name=a.name
        for node in ast.walk(b):
            if isinstance(node,ast.Name) and node.id=='deadline_ranks':node.id='upward_ranks'
        self.assertEqual(ast.dump(a),ast.dump(b))

    def test_ready_deadline_scarcity_order_includes_zero_weight_scene(self):
        modes=lambda units,d:[{'unit_id':u,'duration_ms':str(d)} for u in units]
        ins={'stage_modes':{'loose':modes(['CPU1'],300),'root':modes(['NPU0'],1),
            'scarce':modes(['GPU0'],2),'flex':modes(['CPU1','GPU0'],20)},'scenarios':[]}
        for sid,weight,tight,loose in [('A','1',200,500),('B','0',100,400)]:
            ins['scenarios'].append({'id':sid,'weight':weight,
                'requests':[{'id':'t','deadline_ms':str(tight)},{'id':'l','deadline_ms':str(loose)}],
                'stage_instances':[{'id':g,'shared_stage_id':g,'request_id':'l' if g=='loose' else 't'} for g in ins['stage_modes']],
                'dependencies':[['root','scarce'],['root','flex']]})
        _,order,error=fallback.deadline_ranks(ins,self.budget)
        self.assertIsNone(error)
        self.assertEqual(order,['root','scarce','flex','loose'])
        # Zero-weight deadline changes priority even if it conflicts with A's urgency.
        ins['scenarios'][1]['requests'][1]['deadline_ms']='50'
        self.assertEqual(fallback.deadline_ranks(ins,self.budget)[1][0],'loose')

    def test_fallback_constructor_valid_on_invented_shared_input(self):
        from schedules import validate_schedule
        from collections import Counter
        with patch('thermal.evaluate_candidate',side_effect=AssertionError('REAL_THERMAL_FORBIDDEN')):
            built=fallback.build_fallback_candidate(self.instance,self.budget)
        self.assertEqual(built['status'],'COMPLETE_LEGAL_CANDIDATE')
        self.assertEqual(validate_schedule(self.instance,built['candidate'])['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED')
        count=Counter(d['shared_stage_id'] for d in built['decisions'])
        self.assertTrue(all(n==1 for n in count.values()))

    def test_original_success_never_uses_fallback_and_crossing_evaluation_returns_safe(self):
        with patch.object(i0,'build_heft_candidate',return_value=complete(self.candidate)) as build, \
                patch.object(i1,'build_fallback_candidate',side_effect=AssertionError('UNNEEDED_FALLBACK')):
            meta=i1.run_heft_i1(self.instance,self.config,self.budget,lambda c,s:self.receipt(c),allow_auto_low=True)
        self.assertEqual(build.call_count,1)
        self.assertEqual(meta['status'],'SAFE_INIT_READY')
        self.assertEqual(meta['stop_reason'],'INIT_ADMISSION_LIMIT')
        self.assertFalse(meta['fallback_used'])
        self.assertEqual(self.budget.deadline,1300)

    def test_four_failures_then_only_one_new_construction(self):
        with patch.object(i0,'build_heft_candidate',side_effect=lambda *a,**k:failed()) as old, \
                patch.object(i1,'build_fallback_candidate',return_value=complete(self.candidate)) as new:
            meta=i1.run_heft_i1(self.instance,self.config,self.budget,lambda c,s:self.receipt(c),allow_auto_low=True)
        self.assertEqual([c.kwargs['opp_rank'] for c in old.call_args_list],[None,0,1,2])
        self.assertEqual(new.call_count,1)
        self.assertEqual(len(meta['construction_attempts']),5)
        self.assertEqual(meta['active_priority'],'deadline_scarcity')

    def test_fallback_priority_retained_in_quality_and_no_delay_stage(self):
        def build(*args,**kwargs):
            return failed() if kwargs.get('deployment_override') else complete(self.candidate)
        with patch.object(i0,'build_heft_candidate',side_effect=lambda *a,**k:failed()) as old, \
                patch.object(i1,'build_fallback_candidate',side_effect=build) as new:
            meta=i1.run_heft_i1(self.instance,self.config,self.budget,
                lambda c,s:complete_mock(self.instance,c,self.config['accuracy_targets'],self.budget),allow_auto_low=True)
        self.assertEqual(old.call_count,4)
        self.assertGreater(new.call_count,1)
        self.assertEqual(meta['quality_stages_completed'],['shared-unit','execution-opp'])
        self.assertTrue(all(e['priority_policy']=='deadline_scarcity' for e in meta['local_attempts']))
        self.assertFalse(any(e['kind']=='one-start-delay' for e in meta['local_attempts']))

    def test_original_priority_quality_prefix_equals_I0_with_mock_receipts(self):
        histories=[[],[]]
        def assessor(index):
            def assess(c,source):
                histories[index].append((source,c))
                return complete_mock(self.instance,c,self.config['accuracy_targets'],self.budget)
            return assess
        with patch('thermal.evaluate_candidate',side_effect=AssertionError('REAL_THERMAL_FORBIDDEN')):
            old=i0.run_heft(self.instance,self.config,self.budget,assessor(0),allow_auto_low=True)
            new=i1.run_heft_i1(self.instance,self.config,self.budget,assessor(1),allow_auto_low=True)
        expected=[c for src,c in histories[0] if not src.endswith('one-start-delay')]
        self.assertEqual([c for _,c in histories[1]],expected)
        self.assertFalse(new['fallback_used'])

    def test_no_work_admitted_at_180_and_total_expiry_not_masked(self):
        self.clock.now=1180
        with patch.object(i0,'build_heft_candidate',side_effect=AssertionError('CONSTRUCTION_FORBIDDEN')):
            meta=i1.run_heft_i1(self.instance,self.config,self.budget,lambda *a:None,allow_auto_low=True)
        self.assertEqual(meta['status'],'NO_SAFE_INIT_ADMISSION_LIMIT')
        self.assertEqual(meta['construction_attempts'],[])
        self.clock.now=1300
        with self.assertRaises(Exhausted):require_admission(self.budget,'test')

    def test_numerical_unknown_not_converted_into_another_fallback(self):
        with patch.object(i0,'build_heft_candidate',return_value=complete(self.candidate)) as build, \
                patch.object(i1,'build_fallback_candidate',side_effect=AssertionError('FALLBACK_FORBIDDEN')):
            with self.assertRaisesRegex(common.SearchStop,'NUMERICAL_UNRESOLVED'):
                i1.run_heft_i1(self.instance,self.config,self.budget,lambda *a:{'state':'UNRESOLVED'},allow_auto_low=True)
        self.assertEqual(build.call_count,1)

    def exercise_lifecycle(self,arm,mode='cross'):
        self.clock.now=1000
        roots,calls=[],[]
        def loader(b):
            roots.append(b)
            return deepcopy(self.config),deepcopy(self.instance)
        def build(*args,**kwargs):
            self.clock.now=1179
            return complete(self.candidate)
        def evaluate(ins,c,a,b):
            roots.append(b);calls.append(c)
            self.clock.now+=2
            if mode=='root_expiry':
                self.clock.now=1301
                return complete_mock(ins,c,a,b,formed=299)
            return complete_mock(ins,c,a,b)
        def packets(ins,c,b,**kwargs):
            roots.append(b)
            self.assertEqual(kwargs['allow_blocking_edges'],arm=='ON')
            return iter([{'state':'COMPLETE_LEGAL_CANDIDATE','candidate':changed(c,5),'additional_reversed_edges':[]}])
        from schedules import validate_schedule
        def legality(*args):
            if mode=='legality_cross':self.clock.now=1181
            return validate_schedule(*args)
        with patch.object(i0,'build_heft_candidate',side_effect=build), \
                patch.object(i1,'build_fallback_candidate',side_effect=AssertionError('EXTRA_CONSTRUCTOR_FORBIDDEN')), \
                patch('thermal.evaluate_candidate',side_effect=AssertionError('REAL_THERMAL_FORBIDDEN')), \
                patch('schedules.validate_schedule',side_effect=legality), \
                patch.object(blocking,'candidate_packets',side_effect=packets) as gen:
            bindings=common.Bindings(i1.run_heft_i1,evaluate,'MOCK_ONLY')
            folder=self.directory/(arm+'_'+mode)
            raw=execute_heft(loader,folder,bindings=bindings,budget=self.budget) if arm=='HEFT' else \
                blocking.execute_reconstruction(loader,folder,bindings=bindings,budget=self.budget,allow_blocking_edges=arm=='ON')
        self.assertTrue(all(b is self.budget for b in roots))
        self.assertEqual((self.budget.start,self.budget.deadline,self.budget.seconds),(1000,1300,300))
        return raw,calls,gen

    def test_three_arms_share_I1_and_refinement_is_not_subject_to_180_gate(self):
        for arm in ('HEFT','ON','OFF'):
            with self.subTest(arm=arm):
                raw,calls,gen=self.exercise_lifecycle(arm)
                self.assertEqual(raw['run_terminal'],'SEARCH_COMPLETED',raw.get('error'))
                self.assertEqual(raw['initialization']['status'],'SAFE_INIT_READY')
                self.assertIsNotNone(raw['initial_safe_snapshot'])
                self.assertEqual(len(calls),1 if arm=='HEFT' else 2)
                self.assertEqual(raw['evaluations'][0]['evaluation_admitted_at_s'],179)
                self.assertEqual(raw['evaluations'][0]['receipt']['completed_at_elapsed_s'],181)

    def test_final_gate_after_legality_prevents_late_actual_evaluation(self):
        raw,calls,_=self.exercise_lifecycle('HEFT','legality_cross')
        self.assertEqual(calls,[])
        self.assertEqual(raw['run_terminal'],'NORMAL_NO_SAFE')
        self.assertEqual(raw['initialization']['admission_stop']['kind'],'complete_evaluation')

    def test_global_timeout_retains_formed_safe_but_starts_no_search(self):
        raw,calls,gen=self.exercise_lifecycle('ON','root_expiry')
        self.assertEqual(raw['run_terminal'],'BUDGET_EXHAUSTED')
        self.assertIsNotNone(raw['safe_candidate'])
        self.assertIsNone(raw['initial_safe_snapshot'])
        self.assertEqual(len(calls),1)
        gen.assert_not_called()

    def test_real_version_identity_rejects_wrong_initializer(self):
        def forbidden_loader(*args):raise AssertionError('LOAD_FORBIDDEN')
        with patch('thermal.evaluate_candidate') as evaluator:
            raw=execute_heft(forbidden_loader,self.directory/'bad',budget=self.budget,
                bindings=common.Bindings(i0.run_heft,evaluator,'REAL_I1'))
        self.assertEqual(raw['run_terminal'],'TECHNICAL_STOP')
        self.assertIsNone(raw['safe_candidate'])


if __name__=='__main__':
    unittest.main()
