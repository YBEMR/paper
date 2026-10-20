"""Small correctness fixtures for Q1 enumeration; no study Q1 run/MATLAB."""
from copy import deepcopy
from fractions import Fraction as F
import itertools
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

from inputs import build_instances, load_config
from q1_reference import assignment_domain, execute_reference, _candidate
from run_milp_precheck import independent_assignments, independent_check, select_fixture
from thermal import I, evaluate_candidate
from timing import MethodBudget


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, value): self.value += value


def fixture(two_scenes=True, empty=False):
    config = load_config()
    base = next(i for i in build_instances(config) if i['id'] == 'base__R1')
    ab, ac = [s['id'] for s in base['scenarios']]
    selected = {ab: ['A.pre']}
    if two_scenes:
        selected[ac] = ['A.pre']
    instance, starts = select_fixture(base, 'q1_reference_only', selected, {'A.pre': [0]})
    instance['stage_modes']['A.pre'] = [m for m in instance['stage_modes']['A.pre']
        if m['unit_id'] == 'CPU1' and m['opp_id'] in ['H', 'L']]
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': starts}
    if empty:
        for by_stage in starts.values():
            for key in by_stage:
                by_stage[key] = []
    return config, instance


def fake_evaluator(clock, mode='safe', calls=None):
    calls = [] if calls is None else calls
    def evaluate(instance, candidate, accuracy, budget):
        calls.append((instance['id'], len(instance['scenarios']), deepcopy(candidate), id(budget)))
        clock.advance(.01)
        if mode == 'unknown':
            return {'state': 'UNRESOLVED', 'reason': 'INJECTED_NUMERICAL_UNRESOLVED',
                    'rankable_energy': False, 'violations': []}
        if mode == 'late_violation':
            witness = {'scene_id': instance['scenarios'][0]['id'], 'node': 'CPU1',
                       'time_s': '0', 'temperature_degC': ['90', '90'],
                       'limit_degC': '80', 'formed_at_elapsed_s': clock.value}
            clock.advance(11)
            return {'state': 'THERMAL_VIOLATION', 'violations': [witness], 'rankable_energy': False}
        if mode == 'late_safe':
            at = clock.value
            clock.advance(11)
            return {'state': 'SAFE', 'rankable_energy': True, 'violations': [],
                    'weighted_energy_J': ['1', '1'], 'completed_at_elapsed_s': at}
        if mode == 'full_expiry' and len(instance['scenarios']) > 1:
            at = clock.value
            clock.advance(11)
            return {'state': 'SAFE', 'rankable_energy': True, 'violations': [],
                    'weighted_energy_J': ['1', '1'], 'completed_at_elapsed_s': at}
        weights = {s['id']: F(s['weight']) for s in instance['scenarios']}
        energies = {sid: F(1 if rows[0]['opp'] == 'L' else 2)
                    for sid, rows in candidate['scenes'].items()}
        total = sum(weights[sid]*e for sid, e in energies.items())
        return {'state': 'SAFE', 'rankable_energy': True, 'violations': [],
                'weighted_energy_J': I.rational(total).data(),
                'completed_at_elapsed_s': clock.value}
    return evaluate


class ReferenceTests(unittest.TestCase):
    def run_call(self, config, instance, *, mode='safe', clock=None, evaluator=None, seconds=10):
        clock = clock or Clock()
        calls = []
        evaluator = evaluator or fake_evaluator(clock, mode, calls)
        # Workspace-local unique outputs avoid Windows TEMP ACL differences;
        # leave failed fixture evidence available rather than deleting it.
        out = Path(__file__).resolve().parents[2]/'.runtime'/'q1_reference_tests'/uuid.uuid4().hex
        result = execute_reference(lambda budget: (deepcopy(config), deepcopy(instance)),
            out, seconds=seconds, clock=clock, evaluator=evaluator,
            lower_bound=lambda inst: {'lower_bound_J': '0', 'source': 'fixture'})
        self.assertTrue((out/'result.json').is_file())
        return result, calls, out

    def test_complete_safe_cover_cache_and_interval_optimality(self):
        config, instance = fixture()
        result, calls, _ = self.run_call(config, instance)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['domain_counts']['joint_assignments_total'], 4)
        self.assertEqual(result['counters']['joint_committed'], 4)
        self.assertEqual(result['local_cache_size'], 4)
        self.assertEqual(result['counters']['local_cache_hits'], 4)
        self.assertEqual(F(result['safe_upper_bound_J']), F(1))
        self.assertTrue(result['independently_proven_optimal'])
        self.assertEqual(len({r[3] for r in calls}), 1)
        self.assertEqual([r['opp'] for rows in result['safe_candidate']['scenes'].values()
                          for r in rows], ['L', 'L'])

    def test_unknown_does_not_become_infeasible(self):
        config, instance = fixture()
        result, _, _ = self.run_call(config, instance, mode='unknown')
        self.assertTrue(result['coverage_complete'])
        self.assertTrue(result['numerical_unresolved'])
        self.assertEqual(result['counters']['numerical_unresolved'], 4)
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertEqual(result['certified_lower_bound_J'], '0')

    def test_empty_explicit_domain_independently_infeasible(self):
        config, instance = fixture(empty=True)
        result, calls, _ = self.run_call(config, instance)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['domain_counts']['joint_assignments_total'], 0)
        self.assertTrue(result['independently_proven_infeasible'])
        self.assertFalse(calls)

    def test_committed_violation_survives_late_return(self):
        config, instance = fixture()
        result, _, _ = self.run_call(config, instance, mode='late_violation')
        self.assertEqual(result['counters']['thermal_excluded'], 1)
        self.assertEqual(len(result['violations']), 1)
        self.assertEqual(result['counters']['joint_committed'], 1)
        self.assertTrue(result['budget_exhausted'])
        self.assertFalse(result['coverage_complete'])
        self.assertFalse(result['independently_proven_infeasible'])

    def test_safe_arriving_after_deadline_cannot_update_U(self):
        config, instance = fixture()
        result, _, _ = self.run_call(config, instance, mode='late_safe')
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertIsNotNone(result['current_candidate'])
        self.assertFalse(result['coverage_complete'])

    def test_full_recheck_expiry_retains_current_not_global_U(self):
        config, instance = fixture()
        result, _, _ = self.run_call(config, instance, mode='full_expiry')
        self.assertEqual(result['local_cache_size'], 2)
        self.assertEqual(result['counters']['full_evaluations'], 1)
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(result['coverage_complete'])
        self.assertIsNotNone(result['current_candidate'])

    def test_cross_invocation_cache_and_budget_not_shared(self):
        config, instance = fixture()
        first, _, _ = self.run_call(config, instance)
        second, _, _ = self.run_call(config, instance)
        self.assertNotEqual(first['identity']['budget']['token'], second['identity']['budget']['token'])
        self.assertEqual(first['counters']['local_evaluations'], second['counters']['local_evaluations'])

    def test_final_coverage_and_bound_commit_cannot_cross_budget(self):
        config, instance = fixture()
        clock = Clock()
        original_mark = MethodBudget.mark
        def mark(budget, event):
            if event == 'before_q1_reference_coverage_commit':
                clock.advance(11)
            return original_mark(budget, event)
        with patch.object(MethodBudget, 'mark', mark):
            result, _, _ = self.run_call(config, instance, clock=clock)
        self.assertEqual(result['counters']['joint_committed'], 4)
        self.assertFalse(result['coverage_complete'])
        self.assertIsNone(result['finite_domain_optimal_value_enclosure_J'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertEqual(result['certified_lower_bound_J'], '0')
        self.assertEqual(F(result['safe_upper_bound_J']), F(1))

    def test_legality_finished_after_deadline_does_not_commit_exclusion(self):
        config, instance = fixture()
        clock = Clock()
        def late_invalid(*args):
            clock.advance(11)
            return {'state': 'INVALID_SCHEDULE', 'reason': 'EXECUTION_UNIT_OVERLAP'}
        with patch('q1_reference.validate_schedule', late_invalid):
            result, calls, _ = self.run_call(config, instance, clock=clock)
        self.assertEqual(result['counters']['invalid_schedules'], 0)
        self.assertEqual(result['counters']['joint_committed'], 0)
        self.assertIsNone(result['first_legal_candidate_at_s'])
        self.assertIsNotNone(result['current_candidate'])
        self.assertFalse(calls)

    def test_local_unknown_and_other_scene_violation_can_exclude_joint(self):
        config, instance = fixture()
        clock = Clock()
        first_sid = instance['scenarios'][0]['id']
        def evaluate(view, candidate, accuracy, budget):
            clock.advance(.01)
            if view['scenarios'][0]['id'] == first_sid:
                return {'state': 'UNRESOLVED', 'rankable_energy': False, 'violations': []}
            return {'state': 'THERMAL_VIOLATION', 'rankable_energy': False,
                    'violations': [{'formed_at_elapsed_s': clock.value,
                        'scene_id': view['scenarios'][0]['id'], 'node': 'CPU1',
                        'time_s': '0', 'temperature_degC': ['90', '90'], 'limit_degC': '80'}]}
        result, _, _ = self.run_call(config, instance, clock=clock, evaluator=evaluate)
        self.assertTrue(result['coverage_complete'])
        self.assertTrue(result['independently_proven_infeasible'])
        self.assertFalse(result['numerical_unresolved'])
        self.assertEqual(result['local_unresolved_evaluations'], 2)

    def test_existing_workdir_rejected(self):
        config, instance = fixture()
        _, _, path = self.run_call(config, instance)
        with self.assertRaises(FileExistsError):
            execute_reference(lambda b: (config, instance), path)

    def test_domain_matches_independent_cartesian_and_shared_labels(self):
        config, instance = fixture()
        # Expand a second legal CPU label so the cross-scene shared-unit check
        # excludes mixed CPU1/CPU2 assignments while retaining both labels.
        base = next(i for i in build_instances(config) if i['id'] == 'base__R1')
        instance['stage_modes']['A.pre'] = [m for m in base['stage_modes']['A.pre']
            if m['opp_id'] == 'L']
        dims, ids, counts = assignment_domain(instance)
        scene_ids = [s['id'] for s in instance['scenarios']]
        actual = [_candidate(rows, ids, scene_ids) for rows in itertools.product(*dims)]
        actual = [c for c in actual if c is not None]
        expected = [c for c in independent_assignments(instance,
            instance['start_domain']['by_scene_stage_ms']) if independent_check(instance, c)['valid']]
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(counts['joint_assignments_total'], len(expected))
        self.assertEqual(len(expected), 2)

    def test_real_continuous_fixture_local_and_full_agree(self):
        config, instance = fixture()
        instance['stage_modes']['A.pre'] = [m for m in instance['stage_modes']['A.pre']
                                          if m['opp_id'] == 'L']
        result, _, _ = self.run_call(config, instance, evaluator=evaluate_candidate,
                                    clock=__import__('time').monotonic, seconds=30)
        self.assertTrue(result['coverage_complete'], result.get('error', result['reason']))
        self.assertEqual(result['state'], 'SAFE')
        self.assertIsNotNone(result['finite_domain_optimal_value_enclosure_J'])
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertEqual(result['counters']['full_evaluations'], 1)
        self.assertEqual(result['counters']['local_evaluations'], 2)


if __name__ == '__main__':
    unittest.main()
