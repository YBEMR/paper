"""K127 small auto-L formal-entry checks; no native or research solve.

The echo transport returns only this invocation's freshly constructed and
numerically admitted x0. Physical model, whole-window evaluator, constructor,
completion and production formal lifecycle are real. Synthetic point receipts
below exercise cut scope/ownership only; they are not measured violations.
"""
from copy import deepcopy
from fractions import Fraction as F
from functools import partial
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy as np

import formal_milp as formal
import initial_point
import matlab_bridge
import milp
from control_policy import AUTO_LOW_IMMEDIATE_V1, with_auto_low_idle
from inputs import load_config
from scene_adapter import canonical_hash
from schedules import validate_schedule
from test_partial_deployment import small_case
from timing import MethodBudget


HERE = Path(__file__).resolve().parent
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True,
             prefilter_deadlines=True)
RECORDS = {'scope': 'small auto-L correctness; native transport mocked; no research calls',
           'native_calls': 0, 'research_calls': 0, 'lifecycle': {}}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def tick(self):
        self.now += 0.125


class FormalAutoLifecycleTests(unittest.TestCase):
    def invoke(self, kind, *, reject_x0=False, no_seed=False):
        config = with_auto_low_idle(load_config())
        instance, _, _ = small_case()
        before = canonical_hash(instance)
        clock = Clock()
        budgets, models, sessions, requests = [], [], [], []
        test = self

        def loader(budget):
            budgets.append(budget)
            clock.tick()
            return deepcopy(config), deepcopy(instance)

        def builder(original, cfg, *, budget, **kwargs):
            budgets.append(budget)
            clock.tick()
            test.assertEqual({key: kwargs[key] for key in FLAGS}, FLAGS)
            test.assertEqual(canonical_hash(original), before)
            model = milp.build_model(original, cfg, budget=budget, **kwargs)
            models.append(model)
            return model

        class EchoSession:
            def __init__(self, folder, *, total_budget_s, budget, cut_max_iterations):
                test.assertEqual(cut_max_iterations, 10)
                budgets.append(budget)
                clock.tick()
                self.workdir = Path(folder)
                self.workdir.mkdir(parents=True, exist_ok=False)
                self.budget = budget
                self.counter = 0
                self.event_consumer = None
                self.closed = False
                sessions.append(self)

            def solve(self, payload, *, remaining_s, budget, x0=None):
                test.assertIs(budget, self.budget)
                test.assertIsNotNone(x0)
                budgets.append(budget)
                clock.tick()
                admitted = matlab_bridge._prepare(payload, x0=x0)
                test.assertTrue(admitted['x0_validation']['accepted_numerically'])
                self.counter += 1
                vector = np.asarray(x0).reshape(-1).tolist()
                prefix = self.workdir / ('request_%03d' % self.counter)
                requests.append({'budget_id': id(budget), 'remaining_s': remaining_s,
                    'dimension': len(vector), 'x0_validation': admitted['x0_validation']})
                for number, event in enumerate(({'kind': 'solver_entered'},
                        {'kind': 'incumbent', 'x': vector, 'values': {}}), 1):
                    Path(str(prefix) + '.event_%06d.json' % number).write_text(
                        json.dumps(event), encoding='utf-8')
                    if self.event_consumer is not None:
                        self.event_consumer(prefix)
                return {'status': 'SOLVED', 'x': vector, 'exitflag': 1,
                    'budget_valid': budget.remaining > 0,
                    'accepted_for_evaluation': budget.remaining > 0,
                    'intlinprog_entered': False, 'output': {}, 'callbacks': [],
                    'precheck_transport': 'fresh admitted x0 echo; no native solver'}

            def close(self):
                self.event_consumer = None
                self.closed = True

        # tempfile's mode-0700 directories are inaccessible in this Windows
        # sandbox. Use a unique ignored workspace path with inherited ACLs;
        # keep its precheck records rather than deleting or changing ACLs.
        directory = HERE.parents[1] / '.runtime' / ('night_formal_' + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        from contextlib import ExitStack
        with ExitStack() as stack:
            if reject_x0:
                stack.enter_context(patch.object(initial_point, 'complete_initial_point',
                    return_value={'state': 'INITIAL_POINT_REJECTED', 'x0': None,
                                  'reason': 'EXPLICIT_PRECHECK_REJECTION'}))
            if no_seed:
                stack.enter_context(patch.object(initial_point, 'iter_initial_candidates',
                    return_value=iter([{'status': 'CONSTRUCTION_UNRESOLVED',
                                       'details': {'reason': 'EXPLICIT_PRECHECK_NO_SEED'}}])))
            output = formal.execute_formal_milp(loader, Path(directory) / 'invocation',
                seconds=60, feedback_kind=kind, clock=clock,
                model_builder=partial(builder, prefilter_deadlines=True),
                session_factory=partial(EchoSession, cut_max_iterations=10))
            self.assertTrue((Path(directory) / 'invocation/result.json').exists())
            self.assertTrue((Path(directory) / 'invocation/initial_receipt_checkpoint.json').exists())
        self.assertEqual(len(models), 1)
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].closed)
        self.assertIsNone(sessions[0].event_consumer)
        self.assertEqual(len({id(value) for value in budgets}), 1)
        self.assertIs(models[0].budget, budgets[0])
        self.assertEqual(canonical_hash(instance), before)
        self.assertEqual(output['feedback_kind'], kind)
        self.assertEqual(output['timing']['limit_s'], 60)
        self.assertFalse(output['independently_proven_optimal'])
        self.assertFalse(output['independently_proven_infeasible'])
        self.assertFalse(output['candidate_and_cache_shared_between_calls'])
        return output, models[0], requests, before

    def test_unknown_feedback_kind_is_rejected_before_any_input_or_method_work(self):
        with patch.object(formal, 'execute_warm') as lifecycle:
            with self.assertRaises(ValueError):
                formal.execute_formal_milp(None, HERE / 'unused_night_invalid',
                                          seconds=60, feedback_kind='unknown')
        lifecycle.assert_not_called()

    def test_real_full_auto_l_entry_both_feedback_variants(self):
        pair = []
        for kind in formal.FEEDBACK_KINDS:
            with self.subTest(kind=kind):
                output, model, requests, before = self.invoke(kind)
                self.assertEqual(output['state'], 'SAFE', output.get('error'))
                self.assertEqual(output['initialisation']['state'], 'SAFE_POINT_READY')
                self.assertEqual(output['safe_solution_source'], 'initial_constructor')
                self.assertEqual(output['safe_upper_bound_J'], output['initial_safe_upper_bound_J'])
                self.assertEqual(len(requests), 1)
                self.assertEqual(output['feedback'], [])
                self.assertFalse(output['strict_energy_improvement_certified'])
                self.assertEqual(validate_schedule(model.instance, output['safe_candidate'])['state'],
                                 'SCHEDULE_VALID_THERMAL_UNCHECKED')
                evaluation = output['evaluation']
                self.assertEqual(evaluation['evidence_identity'], {
                    'input_sha256': milp._digest(model.instance),
                    'candidate_sha256': milp._digest(output['safe_candidate'])})
                self.assertTrue(evaluation['rankable_energy'])
                self.assertEqual(len(evaluation['scenes']), len(model.instance['scenarios']))
                for scene in evaluation['scenes'].values():
                    self.assertTrue(scene['complete'])
                    self.assertEqual(F(scene['covered_until_s']), F(model.instance['window_ms']) / 1000)
                self.assertEqual(model.instance['execution_rules']['idle_policy'], AUTO_LOW_IMMEDIATE_V1)
                pair.append((before, canonical_hash(output['safe_candidate']), output['weighted_energy_J']
                             if 'weighted_energy_J' in output else evaluation['weighted_energy_J']))
                RECORDS['lifecycle'][kind] = {'input_sha256': before,
                    'candidate_sha256': canonical_hash(output['safe_candidate']),
                    'safe_upper_bound_J': output['safe_upper_bound_J'],
                    'initial_state': output['initialisation']['state'],
                    'budget_seconds': output['timing']['limit_s'],
                    'requests': requests, 'whole_window_all_scenes_safe': True,
                    'transport': 'mock echo, not native'}
        self.assertEqual(pair[0], pair[1])

    def test_rejected_x0_keeps_safe_seed_without_bare_solve_for_both_variants(self):
        for kind in formal.FEEDBACK_KINDS:
            with self.subTest(kind=kind):
                output, _, requests, _ = self.invoke(kind, reject_x0=True)
                self.assertEqual(output['state'], 'SAFE')
                self.assertEqual(output['initialisation']['state'], 'SAFE_POINT_REJECTED')
                self.assertEqual(output['safe_solution_source'], 'initial_constructor')
                self.assertIsNone(output['solver_diagnostic'])
                self.assertEqual(requests, [])

    def test_missing_safe_seed_remains_unresolved_without_bare_solve(self):
        for kind in formal.FEEDBACK_KINDS:
            with self.subTest(kind=kind):
                output, _, requests, _ = self.invoke(kind, no_seed=True)
                self.assertEqual(output['state'], 'UNRESOLVED')
                self.assertIsNone(output['safe_upper_bound_J'])
                self.assertIsNone(output['solver_diagnostic'])
                self.assertEqual(requests, [])


class AutoFeedbackRowsTests(unittest.TestCase):
    """Synthetic strict witnesses verify row interfaces, not physical failures."""
    def fixture(self):
        config = with_auto_low_idle(load_config())
        instance, _, parts = small_case()
        candidate = {'scenes': {sid: deepcopy(part['scenes'][sid]) for sid, part in parts.items()}}
        budget = MethodBudget(60)
        model = milp.build_model(instance, config, budget=budget, **FLAGS)
        checked = validate_schedule(instance, candidate)
        self.assertEqual(checked['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        sid = instance['scenarios'][0]['id']
        node = instance['platform']['node_order'][0]
        limit = F(instance['scenarios'][0]['maximum_temperature_degC'][0])
        receipt = {'state': 'THERMAL_VIOLATION', 'problem_id': instance['id'],
            'legality': checked, 'evidence_identity': {'input_sha256': milp._digest(instance),
                'candidate_sha256': milp._digest(candidate)},
            'violations': [{'scene_id': sid, 'node': node, 'time_s': '1/1000',
                'temperature_degC': [str(limit + 1), str(limit + 2)],
                'limit_degC': str(limit), 'formed_at_elapsed_s': budget.elapsed}]}
        return model, candidate, receipt, sid

    def test_both_real_feedback_functions_add_the_declared_kind_on_auto_l(self):
        for kind, adder in (('conditional', milp.add_thermal_feedback),
                            ('assignment', formal.add_assignment_feedback)):
            with self.subTest(kind=kind):
                model, candidate, receipt, sid = self.fixture()
                self.assertTrue(formal._checked_thermal_witnesses(model, candidate, receipt))
                before = len(model.rows)
                result = adder(model, candidate, receipt)
                self.assertGreater(result['rows_added'], 0)
                wanted = 'conditional_temperature' if kind == 'conditional' else 'scene_assignment_exclusion'
                self.assertEqual({action['type'] for action in result['actions']}, {wanted})
                self.assertEqual({action['scene'] for action in result['actions']}, {sid})
                if kind == 'assignment':
                    selected = {column for _, column in milp.selected_options(model, candidate, sid)}
                    row = model.rows[before]
                    self.assertEqual(set(row['coef']), selected)
                    self.assertEqual(row['rhs'], len(model.instance['scenarios'][0]['stage_instances']) - 1)
                    self.assertEqual(sum(row['coef'].values()), len(selected))

    def test_common_guard_rejects_foreign_and_nonstrict_witnesses_without_rows(self):
        model, candidate, receipt, _ = self.fixture()
        before = len(model.rows)
        for mutate in (lambda r: r['evidence_identity'].update(candidate_sha256='foreign'),
                       lambda r: r.update(problem_id='foreign'),
                       lambda r: r['violations'][0].update(temperature_degC=['80', '81']),
                       lambda r: r['violations'][0].update(formed_at_elapsed_s=60)):
            invalid = deepcopy(receipt)
            mutate(invalid)
            with self.assertRaises(ValueError):
                formal._checked_thermal_witnesses(model, candidate, invalid)
            self.assertEqual(len(model.rows), before)
        receipt['state'] = 'UNRESOLVED'
        self.assertEqual(formal._checked_thermal_witnesses(model, candidate, receipt), [])
        self.assertEqual(formal.add_assignment_feedback(model, candidate, receipt)['rows_added'], 0)
        self.assertEqual(milp.add_thermal_feedback(model, candidate, receipt)['rows_added'], 0)


if __name__ == '__main__':
    unittest.main()
