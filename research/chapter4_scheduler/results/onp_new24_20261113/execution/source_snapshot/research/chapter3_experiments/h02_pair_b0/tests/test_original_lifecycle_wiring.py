"""B0 integration of original lifecycle with explicit mock physical seams.

Only the original timer constructor/lifecycle/Recorder bookkeeping may run.
Search, legality, thermal evaluation and both lower-bound aliases are mocks;
all SAFE-shaped records here are invented and are not research evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import heuristic_runner as hr
import partial_bounds
from timing import MethodBudget

from h02_pair_b0.backends import CoreBindings, planner_chain
from h02_pair_b0.budget import RootClock
from h02_pair_b0.tests.test_budget import FakeClock
from h02_pair_preflight.common import BASE_SHA
from h02_pair_preflight.paired_response_input_view import paired_response_input_view, planner_packet
from h02_pair_preflight.tests.fixtures import candidate_for, mock_legal_receipt, mock_safe_receipt


class OriginalLifecycleWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pure input algebra only; no candidate search or physical validation.
        cls.pair=paired_response_input_view('base__R1',BASE_SHA)

    def execute_mock_lifecycle(self, evaluator_factory, search_factory):
        packet=planner_packet(self.pair,'R')
        clock=FakeClock(1000.0)
        root=RootClock(120,clock=clock)
        clock.now=1011.0  # Input/projection/process startup already consumed 11 s.
        evaluator=Mock(side_effect=evaluator_factory(clock))
        search=Mock(side_effect=search_factory(clock))
        validator=Mock(side_effect=lambda instance,candidate:mock_legal_receipt(instance))
        bound=Mock(return_value={'lower_bound_J':'0','evidence_kind':'MOCK_ONLY'})
        forbidden_legacy_bound=Mock(side_effect=AssertionError('legacy lower bound must never run'))
        bindings=CoreBindings(hr,search,evaluator,validator,MethodBudget,hr.Exhausted,kind='MOCK_ONLY')
        original_budget,original_recorder=hr.MethodBudget,hr.CandidateRecorder
        with tempfile.TemporaryDirectory() as tmp:
            workdir=Path(tmp)/'planner'
            with patch.object(hr,'validate_schedule',validator),                 patch.object(partial_bounds,'independent_lower_bound',bound),                 patch.object(hr,'independent_lower_bound',forbidden_legacy_bound):
                out=planner_chain(bindings,packet,root,workdir)
            checkpoint=json.loads((Path(tmp)/'accepted_checkpoint.json').read_text(encoding='utf-8'))
            archived=json.loads((workdir/'result.json').read_text(encoding='utf-8'))
            archive_timing=json.loads((workdir/'archive_timing.json').read_text(encoding='utf-8'))
        self.assertIs(hr.MethodBudget,original_budget)
        self.assertIs(hr.CandidateRecorder,original_recorder)
        self.assertEqual(bindings.kind,'MOCK_ONLY')
        self.assertEqual(archived,out['raw_method_result'])
        bound.assert_called_once()
        forbidden_legacy_bound.assert_not_called()
        self.assertEqual(search.call_count,1)
        self.assertGreaterEqual(validator.call_count,1)
        self.assertEqual(out['root']['root_origin'],1000.0)
        self.assertEqual(out['root']['root_deadline'],1120.0)
        self.assertEqual(archived['timing']['limit_s'],120)
        self.assertIn('controller',archived['timing']['clock_origin'])
        self.assertEqual(bound.call_args.args[-1].start,1000.0)
        self.assertEqual(bound.call_args.args[-1].seconds,120)
        self.assertIn('serialization only',archive_timing['scope'])
        return out,checkpoint,evaluator,search

    def test_original_lifecycle_exports_first_best_not_later_higher_mock_safe(self):
        candidates=[]
        def make_evaluator(clock):
            count=[0]
            def evaluate(instance,candidate,accuracy,budget):
                count[0]+=1
                self.assertGreaterEqual(budget.elapsed,11)
                clock.now=1011.0+count[0]
                return mock_safe_receipt(instance,candidate,accuracy,
                    energy=str(count[0]),formed=budget.elapsed)
            return evaluate
        def make_search(clock):
            def run(instance,config,budget,assess):
                self.assertEqual(budget.elapsed,11)
                first=candidate_for(instance,0);second=candidate_for(instance,5)
                candidates.extend([deepcopy(first),deepcopy(second)])
                self.assertEqual(assess(first,'mock:first')['evidence_kind'],'MOCK_ONLY')
                self.assertEqual(assess(second,'mock:later')['evidence_kind'],'MOCK_ONLY')
                return {'status':'MOCK_SEARCH_COMPLETED','evidence_kind':'MOCK_ONLY',
                        'local_base_candidate':deepcopy(second)}
            return run
        out,checkpoint,evaluator,_=self.execute_mock_lifecycle(make_evaluator,make_search)
        raw=out['raw_method_result']
        self.assertEqual(evaluator.call_count,2)
        self.assertEqual(raw['state'],'SAFE')
        self.assertEqual(raw['safe_candidate'],candidates[0])
        self.assertEqual(raw['safe_solution_source'],'mock:first')
        self.assertEqual(raw['safe_upper_bound_J'],'1')
        self.assertEqual(raw['evaluation']['evidence_kind'],'MOCK_ONLY')
        self.assertEqual(raw['evaluation'],raw['evaluations'][0]['evaluation'])
        self.assertEqual(checkpoint['best'],raw['evaluations'][0])
        self.assertEqual(out['checked']['best'],checkpoint['best'])
        self.assertEqual(len(checkpoint['evaluations']),2)
        self.assertEqual(checkpoint['root_origin'],1000.0)
        self.assertEqual(checkpoint['root_limit_s'],120)
        self.assertEqual(checkpoint['kind'],'RECORDER_OBSERVATION_ONLY')
        self.assertFalse(raw['budget_exhausted'])
        self.assertEqual(raw['timing']['method_elapsed_s'],13)
        self.assertNotEqual(raw['safe_candidate'],raw['search']['local_base_candidate'])

    def test_original_lifecycle_late_return_keeps_timely_safe_and_finally_checkpoint(self):
        def make_evaluator(clock):
            def evaluate(instance,candidate,accuracy,budget):
                self.assertEqual(budget.start,1000.0)
                clock.now=1121.0  # Return after root deadline; receipt predates it.
                return mock_safe_receipt(instance,candidate,accuracy,energy='1',formed=119.9)
            return evaluate
        def make_search(clock):
            def run(instance,config,budget,assess):
                assess(candidate_for(instance),'mock:timely-late-return')
                raise AssertionError('no search continuation after budget expiration')
            return run
        out,checkpoint,evaluator,_=self.execute_mock_lifecycle(make_evaluator,make_search)
        raw=out['raw_method_result']
        self.assertEqual(evaluator.call_count,1)
        self.assertEqual(raw['state'],'SAFE')
        self.assertEqual(raw['reason'],'wall_time_limit')
        self.assertTrue(raw['budget_exhausted'])
        self.assertEqual(raw['timing']['method_elapsed_s'],121)
        self.assertEqual(raw['timing']['deadline_overshoot_s'],1)
        self.assertEqual(raw['timing']['limit_s'],120)
        self.assertEqual(raw['evaluation']['completed_at_elapsed_s'],119.9)
        self.assertEqual(raw['evaluations'][0]['returned_at_s'],121)
        self.assertEqual(raw['evaluation']['evidence_kind'],'MOCK_ONLY')
        self.assertEqual(checkpoint['archived_at_elapsed_s'],121)
        self.assertEqual(checkpoint['best'],raw['evaluations'][0])
        self.assertEqual(checkpoint['first_safe_at_s'],119.9)
        self.assertEqual(checkpoint['best'],out['checked']['best'])
        self.assertEqual(out['root']['root_deadline'],1120)
        self.assertEqual(raw['safe_solution_source'],'mock:timely-late-return')


if __name__=='__main__':unittest.main()
