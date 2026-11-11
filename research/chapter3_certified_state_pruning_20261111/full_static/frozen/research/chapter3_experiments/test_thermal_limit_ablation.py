"""Artificial receipt/row tests only; no solver or thermal trajectory calls."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

EXP = Path(__file__).resolve().parent
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))

from research.chapter3_experiments.thermal_limit_ablation import (
    COMPONENTS, _digest, planning_instance, summarize_post)


def original():
    return {'id': 'fixture_operating_limit', 'window_ms': '400',
            'platform': {'node_order': ['CPU1'], 'power_model_temperature_range_degC': ['20', '100']},
            'stage_modes': {'A.main': [{'unit_id': 'CPU1', 'opp_id': 'L'}]},
            'scenarios': [{'id': sid, 'weight': '1/2', 'maximum_temperature_degC': ['80'],
                           'entry': {'temperature_degC': ['78']}, 'dependencies': []}
                          for sid in ('AB', 'AC')]}


def receipt(instance, unsafe=False):
    candidate = {'scenes': {'AB': [], 'AC': []}}
    state = 'THERMAL_VIOLATION' if unsafe else 'SAFE'
    peak = ['81', '81.001'] if unsafe else ['79', '79.001']
    scenes = {sid: {'state': state, 'complete': True, 'covered_until_s': '2/5',
                   'completed_at_elapsed_s': 1.0, 'energy_accuracy_met': True,
                   'energy_J': ['1', '1'],
                   'energy_components_J': {name: ['1/4', '1/4'] for name in COMPONENTS},
                   'peaks_degC': {'CPU1': peak}, 'minimum_degC': {'CPU1': ['75', '75.001']}}
              for sid in ('AB', 'AC')}
    ev = {'state': state, 'problem_id': instance['id'], 'rankable_energy': not unsafe,
          'evidence_identity': {'input_sha256': _digest(instance), 'candidate_sha256': _digest(candidate)},
          'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'}, 'scenes': scenes,
          'weighted_energy_J': None if unsafe else ['1', '1'],
          'safe_upper_bound_J': None if unsafe else '1',
          'completed_at_elapsed_s': None if unsafe else 1.1,
          'violations': [{'scene_id': 'AB', 'node': 'CPU1', 'time_s': '1/10',
                          'temperature_degC': ['81', '81.001'], 'limit_degC': '80',
                          'formed_at_elapsed_s': .5}] if unsafe else []}
    return candidate, ev


class AdapterTests(unittest.TestCase):
    def test_full_view_deepcopy_and_identity(self):
        instance = original()
        view, declaration = planning_instance(instance, True)
        self.assertEqual(view, instance)
        self.assertIsNot(view, instance)
        self.assertEqual(declaration['original_input_sha256'], declaration['planning_input_sha256'])
        self.assertEqual(declaration['modified_paths'], [])

    def test_no_limit_only_ceiling_changes(self):
        instance = original(); before = deepcopy(instance)
        view, declaration = planning_instance(instance, False)
        expected = deepcopy(instance)
        for scene in expected['scenarios']:
            scene['maximum_temperature_degC'] = ['100']
        self.assertEqual(view, expected)
        self.assertEqual(instance, before)
        self.assertEqual(view['id'], instance['id'])
        self.assertEqual(declaration['planning_SAFE_scope'], 'physical_model_validity_only')
        self.assertEqual(declaration['power_model_validity_range_degC'], ['20', '100'])

    def test_unexpected_limit_or_flag_fails(self):
        with self.assertRaisesRegex(ValueError, 'BOOL'):
            planning_instance(original(), 1)
        changed = original(); changed['scenarios'][0]['maximum_temperature_degC'] = ['85']
        with self.assertRaisesRegex(ValueError, '80_C'):
            planning_instance(changed, False)

    def test_common_safe(self):
        instance = original(); candidate, ev = receipt(instance)
        report = summarize_post(instance, candidate, ev)
        self.assertTrue(report['common_80_C_feasible'])
        self.assertTrue(report['complete_physical_evaluation'])
        self.assertTrue(report['energy_is_feasible_upper_bound'])
        self.assertEqual(report['diagnostic_weighted_energy_J'], ['1', '1'])

    def test_complete_unsafe_energy_is_diagnostic_only(self):
        instance = original(); candidate, ev = receipt(instance, True); before = deepcopy(ev)
        report = summarize_post(instance, candidate, ev)
        self.assertEqual(report['state'], 'THERMAL_VIOLATION')
        self.assertFalse(report['common_80_C_feasible'])
        self.assertTrue(report['complete_physical_evaluation'])
        self.assertFalse(report['energy_is_feasible_upper_bound'])
        self.assertEqual(report['diagnostic_weighted_energy_J'], ['1', '1'])
        self.assertEqual(ev, before)
        self.assertIsNone(ev['weighted_energy_J'])
        self.assertEqual(report['new_physical_evaluations'], 0)

    def test_partial_or_late_no_full_energy(self):
        instance = original(); candidate, ev = receipt(instance, True)
        ev['scenes']['AC']['complete'] = False
        report = summarize_post(instance, candidate, ev)
        self.assertFalse(report['common_80_C_feasible'])
        self.assertFalse(report['complete_physical_evaluation'])
        self.assertIsNone(report['diagnostic_weighted_energy_J'])
        ev['scenes']['AC']['complete'] = True
        ev['scenes']['AC']['completed_at_elapsed_s'] = 60
        self.assertIsNone(summarize_post(instance, candidate, ev)['diagnostic_weighted_energy_J'])

    def test_identity_and_validity_rejection(self):
        instance = original(); candidate, ev = receipt(instance)
        view, _ = planning_instance(instance, False)
        with self.assertRaisesRegex(ValueError, 'COMMON_80_C'):
            summarize_post(view, candidate, ev)
        with self.assertRaisesRegex(ValueError, 'IDENTITY'):
            summarize_post(instance, {'scenes': {}}, ev)
        ev['scenes']['AB']['peaks_degC']['CPU1'] = ['100', '100.001']
        report = summarize_post(instance, candidate, ev)
        self.assertFalse(report['complete_physical_evaluation'])
        self.assertEqual(report['state'], 'UNRESOLVED')

    def test_no_timed_witness_no_certified_violation(self):
        instance = original(); candidate, ev = receipt(instance, True)
        ev['violations'][0]['formed_at_elapsed_s'] = 60
        report = summarize_post(instance, candidate, ev)
        self.assertIsNone(report['common_80_C_feasible'])
        self.assertEqual(report['state'], 'UNRESOLVED')
        self.assertTrue(report['complete_physical_evaluation'])

    def test_bound_plumbing_uses_new_ceiling_with_fake_coefficients(self):
        """Exercise actual row/box plumbing with invented algebraic matrices.

        Only a one-stage artificial fixture is built. All real coefficient,
        trajectory and native entry points are replaced with failure guards.
        """
        import milp
        from run_milp_precheck import select_fixture
        instance = json.loads((EXP/'results/natural_full_preparation01/input_instance.json').read_text('utf-8'))
        config = json.loads((EXP/'results/natural_full_preparation01/input_config.json').read_text('utf-8'))
        sid = instance['scenarios'][0]['id']
        fixture, starts = select_fixture(instance, 'limit_adapter_artificial', {sid: ['A.pre']}, {'A.pre': [0]})

        class Clock:
            def check(self): pass

        class InventedCoefficients:
            def __init__(self, platform, budget=None):
                self.nodes = platform['node_order']; self.n = len(self.nodes); self.calls = 0
            def power(self, state):
                return [F(1)]*self.n, [F(1, 10)]*self.n
            def get(self, state, duration):
                self.calls += 1
                # Invented identities/linear objective: not physical propagation.
                temperature = [[milp.I(int(i == j)) for j in range(2*self.n+1)] for i in range(self.n)]
                energy = [milp.I.rational(duration/100) for _ in range(2*self.n)] + [milp.I(1)]
                return {'temperature': temperature, 'energy': energy}

        no_real = AssertionError('A real scientific kernel must not run in this artificial test')
        models = []
        with patch.object(milp, 'Coefficients', InventedCoefficients), \
             patch('milp_coefficients._taylor_kernel', side_effect=no_real), \
             patch('thermal.evaluate_candidate', side_effect=no_real), \
             patch('thermal.evaluate_piecewise', side_effect=no_real), \
             patch('matlab_bridge.MatlabSession', side_effect=no_real):
            for enforce in (True, False):
                view, _ = planning_instance(fixture, enforce)
                models.append(milp.build_model(view, config, budget=Clock(), starts=starts,
                    prefilter_deadlines=True, aggregate_opp_locks=True,
                    relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True))
        full, removed = models
        self.assertEqual(full.options, removed.options)
        self.assertEqual(full.names, removed.names)
        self.assertEqual(len(full.rows), len(removed.rows))
        theta = [i for i, name in enumerate(full.names) if name.startswith('theta:')]
        self.assertTrue(theta)
        self.assertTrue(all(full.ub[i] == 55 and removed.ub[i] == 75 for i in theta))
        energy = [i for i, name in enumerate(full.names) if name.startswith('energy:')]
        self.assertTrue(all(removed.ub[i] > full.ub[i] for i in energy))
        changed = [(a, b) for a, b in zip(full.rows, removed.rows) if a != b]
        self.assertTrue(any(a['tag'].startswith('complete_energy') for a, b in changed))
        self.assertEqual(len(full.energy_bound_certificates), len(removed.energy_bound_certificates))
        self.assertTrue(full.energy_bound_certificates)


class ClosurePostWiring(unittest.TestCase):
    def run_post(self, variant='unsafe'):
        from research.chapter3_experiments import closure_entry as entry
        import thermal
        import schedules
        source = original(); planning, _ = planning_instance(source, False)
        candidate, planning_ev = receipt(planning)
        for scene in planning_ev['scenes'].values():
            scene['peaks_degC']['CPU1'] = ['81', '81.001']
        _, posterior_ev = receipt(source, True)
        if variant == 'energy_conflict':
            for scene in posterior_ev['scenes'].values():
                scene['energy_J'] = ['2', '2']
                scene['energy_components_J'] = {name: ['1/2', '1/2'] for name in COMPONENTS}
        if variant == 'late_witness':
            posterior_ev['violations'][0]['formed_at_elapsed_s'] = 60
        raw = {'safe_candidate': candidate, 'evaluation': planning_ev, 'safe_upper_bound_J': '1'}
        case = dict(input_file='planning.json', posterior_file='posterior.json',
                    config_file='config.json', static_size_file='static.json')
        plan = {'cases': {'t50_no_limit': case}}
        origin = time.monotonic()
        job = entry.JOBS[3]
        with tempfile.TemporaryDirectory(dir=EXP, prefix='thermal_adapter_mock_') as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to(EXP.resolve()))
            ticket = dict(job=job, mode='post', plan='plan.json', origin=origin,
                          scientific_deadline=origin+60, output=tmp,
                          method_receipt_sha256='fixture-hash', plan_sha256='fixture-plan')
            values = {'ticket.json': ticket, 'plan.json': plan, 'raw_result.json': raw,
                      'planning.json': planning, 'posterior.json': source,
                      'config.json': {'accuracy_targets': {}}}
            with patch.object(entry.b, 'read', side_effect=lambda p: deepcopy(values[Path(p).name])), \
                 patch.object(entry.b, 'validate_ticket', return_value=(ticket, plan)), \
                 patch.object(entry.b, 'sha', return_value='fixture-hash'), \
                 patch.multiple(entry.b, INPUT='fixture-unused', CONFIG='fixture-unused', STATIC=Path(tmp)), \
                 patch.object(thermal, 'evaluate_candidate', return_value=posterior_ev) as evaluated, \
                 patch.object(schedules, 'validate_schedule', return_value={'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'}):
                result = entry.worker(Path(tmp)/'ticket.json', 'fixture-token')
                self.assertEqual(evaluated.call_count, 1)
                self.assertEqual(evaluated.call_args.args[0], source)
                self.assertEqual(evaluated.call_args.args[1], candidate)
                post_path = Path(tmp)/'worker/post_result.json'
                post = json.loads(post_path.read_text('utf-8')) if post_path.exists() else None
        return result, post

    def test_post_original_limit_exactly_one_evaluation(self):
        result, post = self.run_post()
        self.assertEqual(result['state'], 'THERMAL_VIOLATION')
        self.assertEqual(result['status'], 'SAFETY_FAILURE')
        self.assertTrue(post['diagnostic']['complete_physical_evaluation'])
        self.assertFalse(post['diagnostic']['energy_is_feasible_upper_bound'])

    def test_post_complete_unsafe_energy_conflict_is_abnormal(self):
        result, _ = self.run_post('energy_conflict')
        self.assertEqual(result['status'], 'TECHNICAL_FAILURE')
        self.assertIn('ENERGY_CONFLICT', result['error'])

    def test_post_invalid_violation_evidence_is_unresolved(self):
        result, post = self.run_post('late_witness')
        self.assertEqual(result['state'], 'UNRESOLVED')
        self.assertEqual(result['status'], 'NORMAL_UNRESOLVED')
        self.assertIsNone(post['diagnostic']['common_80_C_feasible'])

    def test_configured_actual_600_binding(self):
        from research.chapter3_experiments import closure_entry as entry
        with patch.dict(entry.b.__dict__, dict(entry.b.__dict__)):
            entry.configure()
            self.assertEqual(entry.b.METHOD_SECONDS, 600)
            self.assertEqual(entry.b.METHOD_WATCHDOG_SECONDS, 705)
            self.assertEqual(entry.b.JOBS, entry.JOBS)
            self.assertEqual(entry.b.SCOPE, entry.SCOPE)
            self.assertIs(entry.b.native_session_factory, entry.delivery.native_session_factory)
            self.assertIs(entry.b.NATIVE_RESPONSE_VALIDATOR, entry.delivery.validate_response)
            self.assertIs(entry.b.run_whole, entry.delivery.prior.run_whole)
            self.assertIs(entry.b.worker, entry.worker)
            self.assertEqual(entry.delivery.POLICY['reserve_deduction_s'], 30)


if __name__ == '__main__':
    unittest.main()
