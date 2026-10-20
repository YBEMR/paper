"""Exact decoder and lifecycle evidence boundaries on correctness fixtures."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest

from heuristic_common import earliest_placement, decode_plan, plan_from_candidate, upward_ranks
from heuristic_runner import execute_heuristic, CandidateRecorder
from inputs import load_config
from run_milp_precheck import fixtures, independent_check
from schedules import validate_schedule
from thermal import Exhausted
from timing import MethodBudget

HERE = Path(__file__).resolve().parent


class Clock:
    now = 0.0
    def __call__(self): return self.now


class CommonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(); cls.fixtures = fixtures(cls.config)

    def case(self, name):
        instance, starts = deepcopy(self.fixtures[name])
        instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset', 'by_scene_stage_ms': starts}
        return instance

    def candidate(self, instance, unit='CPU1', opp='H', start='0'):
        return {'scenes': {sc['id']: [dict(stage_id=s['id'], unit=unit, opp=opp, start_ms=start)
            for s in sc['stage_instances']] for sc in instance['scenarios']}}

    def test_wait_replay_exact_and_no_rounding(self):
        i = self.case('one_stage_energy'); sid = i['scenarios'][0]['id']
        key = i['scenarios'][0]['stage_instances'][0]['id']
        i['start_domain']['by_scene_stage_ms'][sid][key] = ['0','45']
        c = self.candidate(i, opp='M', start='45')
        plan = plan_from_candidate(i, c)
        self.assertEqual(plan['delays'][sid][key], 9)
        replay = decode_plan(i, plan)
        self.assertEqual(c, replay)
        self.assertTrue(independent_check(i, replay)['valid'])
        mode = next(m for m in i['stage_modes']['A.pre'] if m['unit_id']=='CPU1' and m['opp_id']=='M')
        self.assertNotEqual(F(mode['duration_ms']).denominator, 1)

    def test_same_frequency_parallel_and_different_frequency_conflict(self):
        i = self.case('parallel_cpu'); sc = i['scenarios'][0]
        a,b = [s['id'] for s in sc['stage_instances']]
        first = dict(stage_id=a,unit='CPU1',opp='H',start_ms='0')
        same = earliest_placement(i,sc,b,'CPU2','H',{a:first})
        self.assertEqual(same['start_ms'],'0')
        other = earliest_placement(i,sc,b,'CPU2','M',{a:first})
        self.assertIsNotNone(other)
        self.assertGreaterEqual(F(other['start_ms']),10)
        for row in (same,other):
            c = {'scenes': {sc['id']: [first,row]}}
            self.assertTrue(independent_check(i,c)['valid'])

    def test_dependency_and_fractional_finish(self):
        i = self.case('chain_fractional'); sc = i['scenarios'][0]
        a,b = [s['id'] for s in sc['stage_instances']]
        self.assertIsNone(earliest_placement(i,sc,b,'NPU0','H',{}))
        first = dict(stage_id=a,unit='CPU1',opp='M',start_ms='0')
        after = earliest_placement(i,sc,b,'NPU0','H',{a:first})
        self.assertEqual(after['start_ms'],'15')
        c = {'scenes': {sc['id']:[first,after]}}
        self.assertTrue(independent_check(i,c)['valid'])

    def test_accelerator_queue_and_shared_mapping(self):
        i = self.case('accelerator_queue'); sc = i['scenarios'][0]
        a,b = [s['id'] for s in sc['stage_instances']]
        first = dict(stage_id=a,unit='NPU0',opp='H',start_ms='0')
        after = earliest_placement(i,sc,b,'NPU0','H',{a:first})
        self.assertEqual(after['start_ms'],'35')
        shared = self.case('shared_two_scenes'); c = self.candidate(shared, unit='CPU2')
        self.assertEqual(decode_plan(shared,plan_from_candidate(shared,c)),c)

    def test_empty_domain_no_fallback_or_infeasibility_claim(self):
        i=self.case('one_stage_energy'); sc=i['scenarios'][0]; key=sc['stage_instances'][0]['id']
        i['start_domain']['by_scene_stage_ms'][sc['id']][key]=[]
        self.assertIsNone(earliest_placement(i,sc,key,'CPU1','H',{}))

    def test_upward_rank_and_cycle(self):
        i=self.case('chain_fractional'); sc=i['scenarios'][0]
        a,b=[s['id'] for s in sc['stage_instances']]
        ranks=upward_ranks(i)[sc['id']]
        self.assertGreater(ranks[a],ranks[b])
        sc['dependencies'].append([b,a])
        with self.assertRaisesRegex(ValueError,'cyclic'): upward_ranks(i)

    def test_late_safe_receipt_preserved_but_no_new_postdeadline_evaluation(self):
        i=self.case('one_stage_energy'); c=self.candidate(i)
        clock=Clock(); budget=MethodBudget(10,clock=clock)
        def evaluator(*args):
            clock.now=11
            return {'state':'SAFE','rankable_energy':True,'weighted_energy_J':['1','2'],
                    'safe_upper_bound_J':'2','completed_at_elapsed_s':9,'violations':[]}
        rec=CandidateRecorder(i,{},budget,evaluator=evaluator)
        with self.assertRaises(Exhausted): rec.assess(c,'before-deadline')
        self.assertIsNotNone(rec.best)
        self.assertEqual(rec.first_safe_s,9)
        with self.assertRaises(Exhausted): rec.assess(c,'after-deadline')
        self.assertEqual(len(rec.evaluations),1)

    def test_unsafe_or_late_energy_not_accepted(self):
        i=self.case('one_stage_energy'); c=self.candidate(i)
        for state,formed in [('UNRESOLVED',1),('THERMAL_VIOLATION',1),('SAFE',10)]:
            clock=Clock(); budget=MethodBudget(10,clock=clock)
            def evaluator(*args):
                return {'state':state,'rankable_energy':state=='SAFE','weighted_energy_J':['1','2'],
                        'safe_upper_bound_J':'2','completed_at_elapsed_s':formed,'violations':[]}
            rec=CandidateRecorder(i,{},budget,evaluator=evaluator)
            returned = rec.assess(c,'injected')
            self.assertIsNone(rec.best)
            if state == 'SAFE':
                self.assertEqual(returned['state'], 'UNRESOLVED')
                self.assertFalse(returned['rankable_energy'])

    def test_runner_budget_starts_before_input_and_keeps_existing_safe(self):
        i=self.case('one_stage_energy'); c=self.candidate(i); clock=Clock()
        root=HERE.parents[1]/'.runtime'/'formal_correctness'
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            def loader(budget):
                self.assertEqual(budget.elapsed,0)
                clock.now=2
                return self.config,i
            def evaluator(*args):
                clock.now=4
                return {'state':'SAFE','rankable_energy':True,'weighted_energy_J':['1','2'],
                    'safe_upper_bound_J':'2','completed_at_elapsed_s':3,'violations':[]}
            def search(instance,config,budget,assess):
                assess(c,'first');clock.now=11;budget.check()
            result=execute_heuristic(loader,Path(temp)/'call',method='heft',seconds=10,
                clock=clock,evaluator=evaluator,search=search)
            self.assertEqual(result['state'],'SAFE')
            self.assertTrue(result['budget_exhausted'])
            self.assertEqual(result['first_safe_at_s'],3)
            self.assertFalse(result['independently_proven_infeasible'])


if __name__=='__main__': unittest.main(verbosity=2)
