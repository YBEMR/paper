"""Auto-L admission and unchanged heuristic rules on correctness fixtures.

Only two tests use real continuous physics: one complete single-Stage HEFT
invocation and one SA initialization with its next mutation stopped by a test
double.  No original-scale model, native solver or research call is made.
"""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import Mock, patch

from auto_heuristic_policy import require_heuristic_control
from control_policy import AUTO_LOW_IMMEDIATE_V1, with_auto_low_idle
from heft_method import build_heft_candidate, run_heft
from heuristic_common import earliest_placement
from heuristic_runner import CandidateRecorder, execute_heuristic
from inputs import load_config
from partial_bounds import independent_lower_bound
from run_milp_precheck import fixtures
from sa_method import algorithm_parameters, run_sa
from schedules import validate_schedule
from thermal import Exhausted
from timing import MethodBudget


HERE = Path(__file__).resolve().parent
PHYSICAL_RECORDS = {}


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class CountingBudget:
    def __init__(self, checks=1800):
        self.remaining_checks = checks

    def check(self):
        self.remaining_checks -= 1
        if self.remaining_checks < 0:
            raise Exhausted('synthetic_check_limit')


def mock_safe(*, formed=1):
    return {'state': 'SAFE', 'rankable_energy': True,
            'weighted_energy_J': ['1', '2'], 'safe_upper_bound_J': '2',
            'completed_at_elapsed_s': formed, 'violations': []}


class AutoHeuristicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixture_map = fixtures(cls.config)

    def case(self, name='one_stage_energy', *, auto=True):
        instance, starts = deepcopy(self.fixture_map[name])
        instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                                   'by_scene_stage_ms': starts}
        return with_auto_low_idle(instance) if auto else instance

    def config_for(self, auto=True):
        return with_auto_low_idle(self.config) if auto else deepcopy(self.config)

    def candidate(self, instance):
        candidate = build_heft_candidate(instance)['candidate']
        self.assertIsNotNone(candidate)
        return candidate

    def folder(self):
        root = HERE.parents[1]/'.runtime'/'auto_heuristic_correctness'
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def test_default_search_entry_still_rejects_auto_before_assessment(self):
        instance, config = self.case(), self.config_for()
        assess = Mock(side_effect=AssertionError('must reject before assessment'))
        for method in ('heft', 'sa'):
            with self.subTest(method=method), self.assertRaises(ValueError):
                if method == 'heft':
                    run_heft(instance, config, CountingBudget(), assess)
                else:
                    run_sa(instance, config, CountingBudget(), assess, 101)
        assess.assert_not_called()

    def test_explicit_opt_in_requires_matching_supported_declarations(self):
        auto, legacy = self.case(), self.case(auto=False)
        for instance, config in ((auto, self.config_for(False)),
                                 (legacy, self.config_for()),
                                 (legacy, self.config_for(False)), (auto, {})):
            with self.subTest(config=config.get('execution_rules')), self.assertRaises(ValueError):
                require_heuristic_control(instance, config, 'precheck', allow_auto_low=True)
        self.assertEqual(require_heuristic_control(auto, self.config_for(), 'precheck',
                                                  allow_auto_low=True), AUTO_LOW_IMMEDIATE_V1)
        with self.assertRaises(ValueError):
            require_heuristic_control(auto, self.config_for(), 'precheck', allow_auto_low=1)

    def test_heft_opt_in_changes_no_constructor_or_descent_rules(self):
        events = []
        outputs = []
        for auto in (False, True):
            local = []
            def assess(candidate, source):
                local.append((deepcopy(candidate), source))
                return mock_safe()
            outputs.append(run_heft(self.case(auto=auto), self.config_for(auto),
                CountingBudget(20000), assess, allow_auto_low=auto))
            events.append(local)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(events[0], events[1])
        self.assertTrue(events[0])

    def test_sa_fixed_seed_trace_is_reproducible_and_policy_only(self):
        state = random.getstate()
        traces, outputs = [], []
        parameters = algorithm_parameters()
        for auto in (False, True, True):
            instance, config = self.case('shared_two_scenes', auto=auto), self.config_for(auto)
            trace = []
            def assess(candidate, source):
                self.assertEqual(validate_schedule(instance, candidate)['state'],
                                 'SCHEDULE_VALID_THERMAL_UNCHECKED')
                trace.append((deepcopy(candidate), source))
                return mock_safe()
            outputs.append(run_sa(instance, config, CountingBudget(1800), assess, 101,
                                  allow_auto_low=auto))
            traces.append(trace)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])
        self.assertEqual(traces[0], traces[1])
        self.assertEqual(traces[1], traces[2])
        self.assertTrue(traces[0])
        self.assertEqual(algorithm_parameters(), parameters)
        self.assertEqual(random.getstate(), state)

    def test_auto_shared_frequency_conflicts_and_fractional_end_unchanged(self):
        instance = self.case('parallel_cpu')
        scene = instance['scenarios'][0]
        first, second = [stage['id'] for stage in scene['stage_instances']]
        busy = {first: dict(stage_id=first, unit='CPU1', opp='M', start_ms='0')}
        concurrent = earliest_placement(instance, scene, second, 'CPU2', 'M', busy)
        different = earliest_placement(instance, scene, second, 'CPU2', 'H', busy)
        self.assertEqual(concurrent['start_ms'], '0')
        mode = next(mode for mode in instance['stage_modes'][scene['stage_instances'][0]['shared_stage_id']]
                    if mode['unit_id'] == 'CPU1' and mode['opp_id'] == 'M')
        end = F(mode['duration_ms'])
        self.assertNotEqual(end.denominator, 1)
        # Expand only this correctness fixture's declared starts to include
        # the next exact 5ms-aligned start after the noninteger endpoint.
        aligned = -((-end)//F(instance['start_grid_ms']))*F(instance['start_grid_ms'])
        instance['start_domain']['by_scene_stage_ms'][scene['id']][second] = ['0', str(aligned)]
        different = earliest_placement(instance, scene, second, 'CPU2', 'H', busy)
        self.assertIsNotNone(different)
        self.assertEqual(F(different['start_ms']), aligned)
        for row in (concurrent, different):
            candidate = {'scenes': {scene['id']: [busy[first], row]}}
            self.assertEqual(validate_schedule(instance, candidate)['state'],
                             'SCHEDULE_VALID_THERMAL_UNCHECKED')

    def test_runner_opt_in_uses_independent_auto_bound_with_same_budget(self):
        instance, config, clock = self.case(), self.config_for(), Clock()
        candidate = self.candidate(instance)
        def loader(budget):
            self.assertEqual(budget.elapsed, 0)
            clock.now = 2
            return config, instance
        def search(case, settings, budget, assess):
            self.assertEqual(budget.elapsed, 2)
            assess(candidate, 'precheck')
            return {'stop_reason': 'CORRECTNESS_STUB_COMPLETE'}
        def evaluator(*args):
            clock.now = 4
            return mock_safe(formed=3)
        with self.folder() as folder, patch('heuristic_runner.independent_lower_bound',
                side_effect=AssertionError('legacy bound must not be called')):
            result = execute_heuristic(loader, Path(folder)/'call', method='heft', seconds=10,
                clock=clock, search=search, evaluator=evaluator,
                allow_auto_low=True)
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['control_policy'], AUTO_LOW_IMMEDIATE_V1)
        self.assertEqual(result['certified_lower_bound_J'],
                         independent_lower_bound(instance)['lower_bound_J'])
        self.assertEqual(result['independent_lower_bound']['scope'], 'original_full_domain')
        self.assertEqual(result['lower_bound_formed_at_s'], 2)
        self.assertEqual(result['timing']['limit_s'], 10)
        self.assertFalse(result['candidate_and_cache_shared_between_calls'])

    def test_runner_default_rejects_auto_without_search(self):
        search = Mock(side_effect=AssertionError('must not run'))
        with self.folder() as folder:
            result = execute_heuristic(lambda budget: (self.config_for(), self.case()),
                Path(folder)/'call', method='heft', seconds=10, search=search)
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertIsNone(result['safe_upper_bound_J'])
        search.assert_not_called()

    def test_runner_mismatched_policy_does_not_fall_back(self):
        search = Mock(side_effect=AssertionError('must not run'))
        with self.folder() as folder:
            result = execute_heuristic(lambda budget: (self.config_for(False), self.case()),
                Path(folder)/'call', method='heft', seconds=10, search=search, allow_auto_low=True)
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertNotIn('certified_lower_bound_J', result)
        search.assert_not_called()

    def test_budget_is_not_reset_after_input_expiry(self):
        clock = Clock()
        def loader(budget):
            clock.now = 11
            return self.config_for(), self.case()
        search = Mock(side_effect=AssertionError('must not run'))
        with self.folder() as folder:
            result = execute_heuristic(loader, Path(folder)/'call', method='heft', seconds=10,
                clock=clock, search=search, allow_auto_low=True)
        self.assertTrue(result['budget_exhausted'])
        self.assertNotIn('certified_lower_bound_J', result)
        search.assert_not_called()

    def test_late_safe_cannot_enter_heuristic_objective_or_upper_bound(self):
        instance, clock = self.case(), Clock()
        recorder = CandidateRecorder(instance, {}, MethodBudget(10, clock=clock),
                                    evaluator=lambda *args: mock_safe(formed=10))
        receipt = recorder.assess(self.candidate(instance), 'late_mock')
        self.assertEqual(receipt['state'], 'UNRESOLVED')
        self.assertFalse(receipt['rankable_energy'])
        self.assertIsNone(recorder.best)

    def test_committed_safe_survives_outer_expiry(self):
        instance, clock = self.case(), Clock()
        def evaluator(*args):
            clock.now = 11
            return mock_safe(formed=9)
        recorder = CandidateRecorder(instance, {}, MethodBudget(10, clock=clock), evaluator=evaluator)
        with self.assertRaises(Exhausted):
            recorder.assess(self.candidate(instance), 'committed_mock')
        self.assertEqual(recorder.best['evaluation']['safe_upper_bound_J'], '2')
        self.assertEqual(recorder.first_safe_s, 9)

    def test_committed_violation_survives_outer_expiry_without_safe_energy(self):
        instance, clock = self.case(), Clock()
        witness = {'formed_at_elapsed_s': 9, 'node': 'CPU1', 'time_s': '1/1000',
                   'temperature_degC': ['81', '82'], 'limit_degC': '80'}
        def evaluator(*args):
            clock.now = 11
            return {'state': 'THERMAL_VIOLATION', 'rankable_energy': False,
                    'weighted_energy_J': None, 'safe_upper_bound_J': None,
                    'violations': [witness]}
        recorder = CandidateRecorder(instance, {}, MethodBudget(10, clock=clock), evaluator=evaluator)
        with self.assertRaises(Exhausted):
            recorder.assess(self.candidate(instance), 'violation_mock')
        self.assertEqual(recorder.violations, [witness])
        self.assertIsNone(recorder.best)

    def _physical(self, method):
        config, instance = self.config_for(), self.case()
        with self.folder() as folder:
            result = execute_heuristic(lambda budget: (deepcopy(config), deepcopy(instance)),
                Path(folder)/method, method=method, seconds=30,
                seed=101 if method == 'sa' else None, allow_auto_low=True)
        self.assertEqual(result['state'], 'SAFE', result.get('error', result.get('reason')))
        self.assertFalse(result['independently_proven_optimal'])
        self.assertEqual(result['evaluation']['control_policy']['idle_policy'], AUTO_LOW_IMMEDIATE_V1)
        self.assertEqual(result['evaluation']['evidence_identity']['input_sha256'], result['input_sha256'])
        self.assertLess(result['first_safe_at_s'], 30)
        checked = validate_schedule(instance, result['safe_candidate'])
        self.assertEqual(checked['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        for scene in instance['scenarios']:
            segments = checked['scenes'][scene['id']]['segments']
            self.assertEqual(F(segments[-1]['end_ms']), F(400))
            self.assertTrue(all(opp == 'L' for opp in segments[-1]['domain_opps'].values()))
        PHYSICAL_RECORDS[method] = {'input': instance, 'config': config, 'result': result,
            'scope': 'single-Stage correctness fixture; no original-scale research call'}
        return result

    def test_real_heft_auto_method_complete_continuous_receipt_and_idle_tail(self):
        self._physical('heft')

    def test_real_sa_auto_initialization_complete_continuous_receipt(self):
        # Keep actual constructor, common evaluator, and the single MethodBudget;
        # prevent an unbounded correctness-test annealing run after its first
        # safe initialization. No research execution uses this test double.
        with patch('sa_method._mutate', return_value=(None, None)) as mutate:
            result = self._physical('sa')
        self.assertEqual(result['search']['initialisation_source'], 'heft')
        self.assertGreaterEqual(result['search']['counters']['safe_receipts'], 1)
        mutate.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
