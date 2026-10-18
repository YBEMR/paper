"""K108 pure-Python wrapper and existing-fixture checks; no native solver.

Projection uses the independent K95 Cartesian oracle. Physical lifting and
fresh interval propagation reuse its helpers, with deadline filtering alone
genuinely removing events. These are correctness checks, not research runs.
"""
from copy import deepcopy
from fractions import Fraction as F
from functools import partial
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import formal_milp as formal
import initial_point
from initial_schedule import iter_initial_candidates
from inputs import load_config
from matlab_bridge import (NUMERICAL_CONSISTENCY_CONFLICT,
                           NUMERICAL_CONSISTENCY_UNRESOLVED)
import milp
import prefilter_method as method
from precheck_initial_witness_diagnostic import Clock, FakeModel, fake_preparation
from run_energy_bound_precheck import box_certificate_check
from run_milp_precheck import (candidate_key, exact_row_residuals, fixtures,
                              independent_assignments, independent_check)
from run_scene_precheck import (coefficient_signature, enclosed_flow, overlap,
                                row_acceptance)
from run_warm_diagnostic import FLAGS
from thermal import Budget, evaluate_candidate


HERE = Path(__file__).resolve().parent


def deadline_fixture(config=None):
    """K95 one-Stage task, original physical platform, exact M-OPP boundary."""
    instance, starts = deepcopy(fixtures(config or load_config())['one_stage_energy'])
    instance['id'] = 'fixture_prefilter_deadline_boundary'
    instance['scenarios'][0]['requests'][0]['deadline_ms'] = '34/3'
    return instance, starts


def build_fixture(instance, config, starts, enabled, *, physics=False):
    return milp.build_model(instance, config, starts=starts,
        include_physics=physics, budget=Budget(seconds=600),
        prefilter_deadlines=enabled, **FLAGS)


def admitted(model, candidate):
    try:
        return row_acceptance(model, candidate)
    except ValueError:
        # A filtered late option is outside the retained catalog by design.
        return False


class PrefilterDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixture_map = fixtures(cls.config)
        cls.fixture_map['deadline_boundary'] = deadline_fixture(cls.config)

    def test_default_is_off_and_explicit_current_preserves_original_model(self):
        instance, starts = self.fixture_map['one_stage_energy']
        self.assertIs(inspect.signature(milp.build_model).parameters[
            'prefilter_deadlines'].default, False)
        omitted = milp.build_model(instance, self.config, starts=starts,
            budget=Budget(seconds=600), **FLAGS)
        current = build_fixture(instance, self.config, starts, False, physics=True)
        for field in ('names', 'rows', 'lb', 'ub', 'integer', 'logical_binary',
                      'c', 'options', 'shared', 'scenes', 'formulation'):
            self.assertEqual(getattr(omitted, field), getattr(current, field), field)
        self.assertEqual(coefficient_signature(omitted), coefficient_signature(current))
        self.assertFalse(hasattr(current, 'preprocessing'))

    def test_all_existing_fixture_legal_projections_match_with_free_deployment(self):
        for name, (instance, starts) in self.fixture_map.items():
            with self.subTest(fixture=name):
                before = milp._digest(instance)
                candidates = list(independent_assignments(instance, starts))
                expected = {candidate_key(c) for c in candidates
                            if independent_check(instance, c)['valid']}
                current = build_fixture(instance, self.config, starts, False)
                filtered = build_fixture(instance, self.config, starts, True)
                for model in (current, filtered):
                    observed = {candidate_key(c) for c in candidates if admitted(model, c)}
                    self.assertEqual(observed, expected)
                    self.assertEqual(model.shared.keys(), current.shared.keys())
                    self.assertEqual(milp._digest(model.instance), before)
                self.assertIsNone(filtered.preprocessing['fixed_deployment'])
                self.assertIsNone(filtered.preprocessing['fixed_scene_id'])
                self.assertEqual(milp._digest(instance), before)

    def test_exact_deadline_equality_retained_but_arbitrarily_late_removed(self):
        instance, starts = self.fixture_map['deadline_boundary']
        filtered = build_fixture(instance, self.config, starts, True)
        boundary = [o for o in filtered.options if F(o['end_ms']) == F('34/3')]
        self.assertTrue(boundary, 'the exact boundary must be exercised')
        self.assertTrue(all(o['opp_id'] == 'M' for o in boundary))
        self.assertGreater(filtered.preprocessing['deadline_removed_count'], 0)
        tightened = deepcopy(instance)
        tightened['scenarios'][0]['requests'][0]['deadline_ms'] = str(F('34/3')-F(1, 10**12))
        just_late = build_fixture(tightened, self.config, starts, True)
        self.assertFalse(any(F(o['end_ms']) == F('34/3') for o in just_late.options))
        self.assertTrue(any(o['opp_id'] == 'H' for o in just_late.options))

    def test_empty_filtered_stage_retains_contradictory_onehot_and_shared_choices(self):
        instance, starts = deepcopy(self.fixture_map['deadline_boundary'])
        instance['scenarios'][0]['requests'][0]['deadline_ms'] = '1'
        current = build_fixture(instance, self.config, starts, False)
        filtered = build_fixture(instance, self.config, starts, True)
        self.assertEqual(filtered.options, [])
        self.assertTrue(filtered.preprocessing['empty_stage_option_sets'])
        self.assertEqual(filtered.shared.keys(), current.shared.keys())
        self.assertTrue(any(r['tag'] == 'stage_unique/lower' and not r['coef']
                            and r['rhs'] == -1 for r in filtered.rows))

    def test_true_deadline_only_resegmentation_lifts_and_encloses_two_schedules(self):
        instance, starts = self.fixture_map['deadline_boundary']
        before = milp._digest(instance)
        models = [build_fixture(instance, self.config, starts, flag, physics=True)
                  for flag in (False, True)]
        sid = instance['scenarios'][0]['id']
        old_events, new_events = [set(m.scenes[sid]['events']) for m in models]
        self.assertLess(new_events, old_events)
        self.assertIsNone(models[1].preprocessing['fixed_deployment'])
        legal = [c for c in independent_assignments(instance, starts)
                 if independent_check(instance, c)['valid']]
        selected = [legal[0], legal[-1]]
        self.assertNotEqual(candidate_key(selected[0]), candidate_key(selected[1]))
        for candidate in selected:
            with self.subTest(candidate=candidate_key(candidate)):
                continuous = evaluate_candidate(instance, candidate,
                    self.config['accuracy_targets'], Budget(seconds=60))
                self.assertEqual(continuous['state'], 'SAFE')
                flows = []
                for model in models:
                    vector = milp.lift_candidate(model, candidate)
                    self.assertLessEqual(max(exact_row_residuals(model, vector), default=F(0)), F('1e-9'))
                    self.assertTrue(all(a-1e-9 <= v <= b+1e-9
                                        for a, v, b in zip(model.lb, vector, model.ub)))
                    self.assertEqual(candidate_key(milp.decode(model, vector)), candidate_key(candidate))
                    flow = enclosed_flow(model, candidate, sid)
                    flows.append(flow)
                    scene = continuous['scenes'][sid]
                    self.assertTrue(overlap(flow['energy_J'], scene['energy_J']))
                    self.assertTrue(all(overlap(flow['final_temperature_degC'][node],
                                                scene['final_temperature_degC'][node])
                                        for node in instance['platform']['node_order']))
                    energy = F.from_float(float(np.dot(model.c, vector)))
                    self.assertLessEqual(F(continuous['weighted_energy_J'][0])-F('1e-12'), energy)
                    self.assertLessEqual(energy, F(continuous['weighted_energy_J'][1])+F('1e-12'))
                    self.assertTrue(all(len(row) == 4 for row in model.scenes[sid]['theta']))
                self.assertTrue(overlap(flows[0]['energy_J'], flows[1]['energy_J']))
                self.assertTrue(all(overlap(flows[0]['final_temperature_degC'][node],
                                            flows[1]['final_temperature_degC'][node])
                                    for node in instance['platform']['node_order']))
        for certificate in models[1].energy_bound_certificates:
            box_certificate_check(models[1], certificate)
        self.assertEqual(len(models[1].energy_bound_certificates),
                         len(models[1].scenes[sid]['energy']))
        self.assertEqual(milp._digest(instance), before)

    def test_initial_constructor_same_full_input_and_first_candidate(self):
        instance, starts = self.fixture_map['deadline_boundary']
        initial = []
        for enabled in (False, True):
            model = build_fixture(instance, self.config, starts, enabled)
            attempts = list(iter_initial_candidates(model.instance, starts=starts,
                budget=Budget(seconds=60), max_attempts=3))
            completed = [a['candidate'] for a in attempts if a['status'] == 'COMPLETE_LEGAL_CANDIDATE']
            self.assertTrue(completed)
            initial.append(candidate_key(completed[0]))
        self.assertEqual(initial[0], initial[1])


class PrefilterLifecycleTests(unittest.TestCase):
    def test_invalid_variant_rejected_before_delegate_or_filesystem(self):
        with patch.object(method, 'execute_formal_milp') as delegate:
            with self.assertRaisesRegex(ValueError, 'variant'):
                method.execute_prefilter_method(None, HERE/'unused_prefilter_invalid',
                                               seconds=1, variant='wrong')
        delegate.assert_not_called()

    def invoke(self, variant, *, conflict=False, construction_cost=1., expire_initial=False):
        clock = Clock()
        calls, budgets, models, preparations = [], [], [], []
        instance = {'id': 'fixture_prefilter_mock_'+variant}
        config = {'accuracy_targets': {}}
        def loader(budget):
            budgets.append(budget); clock.advance(1)
            return config, instance
        def builder(loaded, cfg, budget, progress, **flags):
            self.assertIs(loaded, instance); self.assertIs(cfg, config)
            self.assertEqual(flags, {**FLAGS, 'prefilter_deadlines': variant == 'prefilter'})
            budgets.append(budget); clock.advance(construction_cost)
            model = FakeModel(loaded, budget); models.append(model)
            return model
        class Session:
            counter = 0
            event_consumer = None
            def __init__(inner, path, total_budget_s, budget):
                inner.workdir = path; inner.budget = budget
                budgets.append(budget); clock.advance(1)
            def solve(inner, payload, **kwargs):
                inner.counter += 1; calls.append(kwargs); budgets.append(kwargs['budget'])
                clock.advance(.375)
                return {'x': [], 'exitflag': -2, 'budget_valid': True,
                        'numerical_consistency': {'state': NUMERICAL_CONSISTENCY_CONFLICT}}
            def close(inner):
                pass
        def prepare(model, accuracy, budget, starts, max_attempts):
            self.assertIsNone(starts); self.assertEqual(max_attempts, 3)
            budgets.append(budget)
            for phase, duration in [('initial_schedule_construction', .25),
                                    ('initial_continuous_evaluation', .5),
                                    ('initial_point_completion', .25)]:
                with budget.phase(phase):
                    clock.advance(duration)
            receipt = fake_preparation(instance, safe_time=budget.elapsed-.25,
                                       point_time=budget.elapsed)
            preparations.append(receipt)
            if expire_initial:
                clock.advance(20)
            return receipt
        def diagnostic(model, session, accuracy, budget, *, feedback_kind):
            self.assertEqual(feedback_kind, 'conditional')
            for _ in range(2):
                with budget.phase('matrix_export'):
                    payload = model.as_solver_dict(); clock.advance(.125)
                with budget.phase('solver_transport_and_solve'):
                    session.solve(payload, remaining_s=budget.remaining, budget=budget)
            return {'state': 'UNRESOLVED', 'reason': 'FIXTURE_END', 'rounds': [],
                    'safe_upper_bound_J': None}
        with tempfile.TemporaryDirectory(dir=HERE) as directory, \
             patch.object(initial_point, 'prepare_initial_witness', side_effect=prepare) as init, \
             patch.object(formal, 'solve_formal_diagnostic',
                          wraps=formal.solve_formal_diagnostic if conflict else diagnostic), \
             patch.object(formal, 'add_thermal_feedback') as thermal_feedback, \
             patch.object(formal, 'add_assignment_feedback') as assignment_feedback:
            out = Path(directory)/'run'
            result = method.execute_prefilter_method(loader, out, seconds=10,
                variant=variant, clock=clock, model_builder=builder, session_factory=Session)
            archived = json.loads((out/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(result, archived)
            if construction_cost < 10:
                self.assertTrue((out/'initial_receipt_checkpoint.json').exists())
                self.assertEqual(init.call_count, 1)
            else:
                init.assert_not_called()
            thermal_feedback.assert_not_called(); assignment_feedback.assert_not_called()
        return result, calls, budgets, models, preparations

    def test_same_flags_seed_x0_conditional_clock_and_all_costs_with_fresh_calls(self):
        invocations = []
        for variant in method.VARIANTS:
            result, calls, budgets, models, preparations = self.invoke(variant)
            self.assertEqual(result['state'], 'SAFE')
            self.assertEqual(result['safe_solution_source'], 'initial_constructor')
            self.assertEqual(result['safe_upper_bound_J'], '2')
            self.assertEqual(result['preprocessing_variant'], variant)
            self.assertEqual(result['prefilter_deadlines'], variant == 'prefilter')
            self.assertEqual(result['feedback_kind'], 'conditional')
            self.assertEqual(result['outer_round_limit'], 50)
            self.assertEqual(len({id(b) for b in budgets}), 1)
            self.assertEqual(len(calls), 2)
            self.assertIs(calls[0]['x0'], preparations[0]['x0'])
            self.assertNotIn('x0', calls[1])
            self.assertGreater(calls[0]['remaining_s'], calls[1]['remaining_s'])
            self.assertEqual(result['timing']['limit_s'], 10)
            totals = result['timing']['phases_exclusive_s']
            for phase, seconds in [('input_read_and_expansion', 1.), ('model_construction', 1.),
                                   ('solver_startup', 1.), ('initial_schedule_construction', .25),
                                   ('initial_continuous_evaluation', .5), ('initial_point_completion', .25),
                                   ('matrix_export', .25), ('solver_transport_and_solve', .75)]:
                self.assertEqual(totals[phase], seconds, phase)
            self.assertFalse(result['candidate_and_cache_shared_between_calls'])
            self.assertFalse(result['milp_improved_initial_upper_bound'])
            invocations.append((budgets[0], models[0], preparations[0]['x0']))
        for index in range(3):
            self.assertIsNot(invocations[0][index], invocations[1][index])

    def test_model_expiry_stops_before_startup_or_initialization_for_both(self):
        for variant in method.VARIANTS:
            result, calls, _, _, preparations = self.invoke(variant, construction_cost=12)
            self.assertEqual(result['reason'], 'wall_time_limit')
            self.assertFalse(result['model_complete'])
            self.assertFalse(result['matlab_worker_ready'])
            self.assertEqual((calls, preparations), ([], []))
            self.assertIsNone(result['safe_upper_bound_J'])

    def test_late_initial_return_preserves_formed_safe_but_cannot_start_solver(self):
        for variant in method.VARIANTS:
            result, calls, _, _, _ = self.invoke(variant, expire_initial=True)
            self.assertEqual(result['state'], 'SAFE')
            self.assertEqual(result['safe_upper_bound_J'], '2')
            self.assertEqual(calls, [])
            self.assertIsNone(result['solver_diagnostic'])
            self.assertTrue(result['budget_exhausted'])

    def test_numerical_conflict_preserves_seed_and_stops_without_feedback(self):
        for variant in method.VARIANTS:
            result, calls, _, _, _ = self.invoke(variant, conflict=True)
            self.assertEqual(result['state'], 'SAFE')
            self.assertEqual(result['reason'], NUMERICAL_CONSISTENCY_UNRESOLVED)
            self.assertEqual(result['safe_solution_source'], 'initial_constructor')
            self.assertEqual(result['safe_upper_bound_J'], '2')
            self.assertEqual(len(calls), 1)
            self.assertIn('x0', calls[0])
            self.assertEqual(result['feedback'], [])
            self.assertEqual(result['remaining_domain'], 'retained')
            self.assertFalse(result['independently_proven_infeasible'])
            self.assertFalse(result['independently_proven_optimal'])
            self.assertIsNone(result['milp_safe_upper_bound_J'])

    def test_wrapper_delegates_only_prefilter_switch_and_inherits_matlab_options(self):
        # Native option auditing already has its own regression suite; this
        # checks the pair cannot introduce variant-specific solver factories.
        sentinel_session = object()
        sentinel_builder = lambda *args, **kwargs: None
        for variant in method.VARIANTS:
            with tempfile.TemporaryDirectory(dir=HERE) as directory, \
                 patch.object(method, 'execute_formal_milp', return_value={'fixture': True}) as delegate:
                result = method.execute_prefilter_method(None, directory, seconds=17,
                    variant=variant, model_builder=sentinel_builder,
                    session_factory=sentinel_session)
                kwargs = delegate.call_args.kwargs
                self.assertEqual(kwargs['feedback_kind'], 'conditional')
                self.assertEqual(kwargs['seconds'], 17)
                self.assertIs(kwargs['session_factory'], sentinel_session)
                self.assertIsInstance(kwargs['model_builder'], partial)
                self.assertIs(kwargs['model_builder'].func, sentinel_builder)
                self.assertEqual(kwargs['model_builder'].keywords,
                                 {'prefilter_deadlines': variant == 'prefilter'})
                self.assertEqual(result['prefilter_deadlines'], variant == 'prefilter')


if __name__ == '__main__':
    unittest.main()
