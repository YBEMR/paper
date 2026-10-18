"""Small structural and mock-lifecycle checks; no MATLAB or research solve.

Synthetic violation receipts below test the exclusion interface only. They do
not claim that the frozen physical parameters produce those temperatures.
"""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import formal_milp as formal
import initial_point
from inputs import build_instance, load_config
from milp import _digest, build_model, selected_options
from precheck_initial_witness_diagnostic import Clock, FakeModel, fake_preparation
from run_milp_precheck import select_fixture, independent_assignments, candidate_key
from schedules import validate_schedule
from thermal import Exhausted
from timing import MethodBudget


class AssignmentExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        base = build_instance(cls.config, 'base__R1')
        ids = [scene['id'] for scene in base['scenarios']]
        cls.instance, cls.starts = select_fixture(base, 'feedback_scope',
            {sid: ['A.pre'] for sid in ids}, {'A.pre': [0, 5]})
        cls.instance['stage_modes']['A.pre'] = [mode for mode in
            cls.instance['stage_modes']['A.pre']
            if mode['unit_id'] == 'CPU1' and mode['opp_id'] in ('H', 'L')]
        cls.candidates = list(independent_assignments(cls.instance, cls.starts))

    def setUp(self):
        self.budget = MethodBudget(60)
        self.model = build_model(self.instance, self.config, starts=self.starts,
            include_physics=False, budget=self.budget, relax_auxiliary_integrality=True,
            strengthen_energy_lower_bounds=True)
        self.candidate = deepcopy(self.candidates[0])
        self.scene_ids = list(self.candidate['scenes'])

    def receipt(self, scenes=None):
        nodes = self.instance['platform']['node_order']
        by_id = {scene['id']: scene for scene in self.instance['scenarios']}
        witnesses = []
        for sid in (scenes or [self.scene_ids[0]]):
            limit = F(by_id[sid]['maximum_temperature_degC'][0])
            witnesses.append({'scene_id': sid, 'node': nodes[0], 'time_s': '0',
                'temperature_degC': [str(limit+1), str(limit+2)], 'limit_degC': str(limit),
                'formed_at_elapsed_s': 0.01})
        return {'state': 'THERMAL_VIOLATION', 'problem_id': self.instance['id'],
            'legality': validate_schedule(self.instance, self.candidate),
            'evidence_identity': {'input_sha256': _digest(self.instance),
                                  'candidate_sha256': _digest(self.candidate)},
            'violations': witnesses}

    def test_cut_excludes_only_failed_scene_schedule_not_deployment(self):
        before = len(self.model.rows)
        output = formal.add_assignment_feedback(self.model, self.candidate, self.receipt())
        self.assertEqual(output['rows_added'], 1)
        row = self.model.rows[before]
        sid = self.scene_ids[0]
        wanted = candidate_key({'scenes': {sid: self.candidate['scenes'][sid]}})
        excluded = accepted_same_deployment = changed_other_scene = 0
        for candidate in self.candidates:
            chosen = {column for scene in self.scene_ids
                      for _, column in selected_options(self.model, candidate, scene)}
            lhs = sum(value for column, value in row['coef'].items() if column in chosen)
            fails = lhs > row['rhs']
            same_scene = candidate_key({'scenes': {sid: candidate['scenes'][sid]}}) == wanted
            self.assertEqual(fails, same_scene)
            excluded += fails
            accepted_same_deployment += not fails
            changed_other_scene += fails and candidate_key(candidate) != candidate_key(self.candidate)
        self.assertGreater(excluded, 0)
        self.assertGreater(accepted_same_deployment, 0)
        self.assertGreater(changed_other_scene, 0)

    def test_duplicate_points_or_receipt_add_no_duplicate_cut(self):
        receipt = self.receipt([self.scene_ids[0]]*2)
        self.assertEqual(formal.add_assignment_feedback(self.model, self.candidate, receipt)['rows_added'], 1)
        self.assertEqual(formal.add_assignment_feedback(self.model, self.candidate, receipt)['rows_added'], 0)

    def test_two_violated_scenes_each_receive_own_complete_cut(self):
        output = formal.add_assignment_feedback(self.model, self.candidate,
                                                 self.receipt(self.scene_ids))
        self.assertEqual(output['rows_added'], 2)
        self.assertEqual({action['scene'] for action in output['actions']}, set(self.scene_ids))

    def test_unknown_and_safe_are_not_excluded(self):
        for state in ('UNRESOLVED', 'SAFE', 'INVALID_SCHEDULE'):
            receipt = self.receipt(); receipt['state'] = state
            before = len(self.model.rows)
            self.assertEqual(formal.add_assignment_feedback(self.model, self.candidate,
                                                             receipt)['rows_added'], 0)
            self.assertEqual(len(self.model.rows), before)

    def test_wrong_identity_illegal_candidate_or_non_strict_witness_rejected(self):
        mutations = [lambda r: r['evidence_identity'].update(candidate_sha256='wrong'),
                     lambda r: r.update(problem_id='wrong'),
                     lambda r: r.update(legality={}),
                     lambda r: r['violations'][0].update(temperature_degC=['80', '81']),
                     lambda r: r['violations'][0].update(time_s='1'),
                     lambda r: r['violations'][0].update(limit_degC='81'),
                     lambda r: r['violations'][0].update(formed_at_elapsed_s=60),
                     lambda r: r['violations'][0].pop('formed_at_elapsed_s')]
        for mutate in mutations:
            receipt = self.receipt(); mutate(receipt)
            before = len(self.model.rows)
            with self.assertRaises((ValueError, KeyError)):
                formal.add_assignment_feedback(self.model, self.candidate, receipt)
            self.assertEqual(len(self.model.rows), before)


class FakeRecorder:
    assessments = []
    def __init__(self, model, accuracy, budget, folder):
        self.budget, self.best = budget, None
        self.items = list(self.assessments)
    def poll(self, prefix):
        pass
    def assess(self, vector, source):
        candidate, evaluation = self.items.pop(0)
        if callable(evaluation):
            evaluation = evaluation(self.budget)
        if evaluation and evaluation.get('state') == 'SAFE' and evaluation.get('rankable_energy'):
            if evaluation.get('completed_at_elapsed_s', self.budget.seconds) < self.budget.seconds:
                self.best = {'candidate': candidate, 'evaluation': evaluation}
        return candidate, evaluation
    def summary(self):
        return {'fixture': True, 'remaining_assessments': len(self.items)}


class FormalLoopTests(unittest.TestCase):
    def invoke(self, *, kind='conditional', assessments=None, returned=None,
               feedback=None, max_rounds=50):
        clock = Clock(); budget = MethodBudget(10, clock=clock)
        model = FakeModel({'id': 'fixture_formal_loop'}, budget)
        self.clock, self.budget = clock, budget
        self.calls = []
        replies = list(returned or [{'x': [1], 'exitflag': 1, 'budget_valid': True,
                                   'accepted_for_evaluation': True}])
        class Session:
            workdir = Path('unused')/'matlab'
            event_consumer = None
            def solve(inner, payload, **kwargs):
                self.calls.append(kwargs)
                clock.advance(0.5)
                return replies.pop(0)
        session = Session(); FakeRecorder.assessments = assessments or []
        with patch.object(formal, 'Recorder', FakeRecorder), \
             patch.object(formal, '_checked_thermal_witnesses', return_value=[{'fixture': True}]), \
             patch.object(formal, 'add_thermal_feedback', side_effect=feedback) as conditional, \
             patch.object(formal, 'add_assignment_feedback', side_effect=feedback) as assignment:
            result = formal.solve_formal_diagnostic(model, session, {}, budget,
                                                   feedback_kind=kind, max_rounds=max_rounds)
        self.assertIsNone(session.event_consumer)
        return result, conditional.call_count, assignment.call_count

    def test_unknown_retained_without_any_cut(self):
        output, conditional, assignment = self.invoke(assessments=[({}, {'state': 'UNRESOLVED'})])
        self.assertEqual(output['reason'], 'EVALUATION_UNRESOLVED')
        self.assertEqual((conditional, assignment), (0, 0))
        self.assertFalse(output['independently_proven_infeasible'])

    def test_both_variants_share_loop_only_feedback_changes(self):
        assessment = [({}, {'state': 'THERMAL_VIOLATION'}), ({},
            {'state': 'SAFE', 'rankable_energy': True, 'safe_upper_bound_J': '1',
             'completed_at_elapsed_s': 1.})]
        replies = [{'x': [1], 'exitflag': 1, 'budget_valid': True,
                    'accepted_for_evaluation': True}]*2
        for kind in formal.FEEDBACK_KINDS:
            output, conditional, assignment = self.invoke(kind=kind, assessments=assessment,
                returned=replies, feedback=lambda *args: {'rows_added': 1})
            self.assertEqual(output['state'], 'SAFE')
            self.assertEqual(output['safe_upper_bound_J'], '1')
            self.assertEqual((conditional, assignment), (1, 0) if kind == 'conditional' else (0, 1))
            self.assertEqual(len(output['rounds']), 2)
            self.assertIs(self.calls[0]['budget'], self.calls[1]['budget'])
            self.assertGreater(self.calls[0]['remaining_s'], self.calls[1]['remaining_s'])
            self.assertFalse(output['independently_proven_optimal'])

    def test_in_budget_safe_receipt_survives_late_return(self):
        def safe_late(budget):
            stamp = budget.elapsed
            self.clock.advance(20)
            return {'state': 'SAFE', 'rankable_energy': True, 'safe_upper_bound_J': '1',
                    'completed_at_elapsed_s': stamp}
        output, _, _ = self.invoke(assessments=[({}, safe_late)])
        self.assertEqual(output['state'], 'SAFE')
        self.assertGreater(output['elapsed_s'], 10)

    def test_late_new_safe_cannot_be_accepted(self):
        def late(budget):
            self.clock.advance(20)
            return {'state': 'SAFE', 'rankable_energy': True, 'safe_upper_bound_J': '1',
                    'completed_at_elapsed_s': budget.elapsed}
        output, _, _ = self.invoke(assessments=[({}, late)])
        self.assertIsNone(output['safe_upper_bound_J'])
        self.assertEqual(output['state'], 'UNRESOLVED')

    def test_solver_infeasible_remains_solver_reported(self):
        output, _, _ = self.invoke(returned=[{'budget_valid': True, 'exitflag': -2, 'x': []}])
        self.assertEqual(output['reason'], 'SOLVER_REPORTED_INFEASIBLE')
        self.assertFalse(output['independently_proven_infeasible'])

    def test_round_cap_and_feedback_exception_retain_unresolved(self):
        output, _, _ = self.invoke(assessments=[({}, {'state': 'THERMAL_VIOLATION'})],
                                   feedback=lambda *args: {'rows_added': 1}, max_rounds=1)
        self.assertEqual(output['reason'], 'OUTER_ROUND_LIMIT')
        def bad(*args):
            raise MemoryError()
        output, _, _ = self.invoke(assessments=[({}, {'state': 'THERMAL_VIOLATION'})], feedback=bad)
        self.assertEqual(output['reason'], 'RESOURCE_LIMIT')
        self.assertEqual(output['evaluation']['state'], 'THERMAL_VIOLATION')

    def test_feedback_finished_after_deadline_is_diagnostic_only(self):
        def late_feedback(*args):
            self.clock.advance(20)
            return {'rows_added': 1}
        output, _, _ = self.invoke(assessments=[({}, {'state': 'THERMAL_VIOLATION'})],
                                   feedback=late_feedback)
        self.assertEqual(output['feedback'], [])
        self.assertFalse(output['late_feedback_diagnostics'][0]['within_budget'])
        self.assertEqual(output['evaluation']['state'], 'THERMAL_VIOLATION')
        self.assertFalse(output['independently_proven_infeasible'])
        self.assertIsNone(output['safe_upper_bound_J'])


class FormalLifecycleTests(unittest.TestCase):
    def test_invalid_kind_rejected_before_workdir_creation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            out = Path(directory)/'unused'
            with self.assertRaises(ValueError):
                formal.execute_formal_milp(None, out, seconds=1, feedback_kind='wrong')
            self.assertFalse(out.exists())

    def test_same_flags_budget_seed_checkpoint_and_x0_once_for_both_variants(self):
        for kind in formal.FEEDBACK_KINDS:
            clock = Clock(); calls = []; budget_ids = []; instance = {'id': 'fixture_formal_'+kind}
            def loader(budget):
                budget_ids.append(id(budget)); clock.advance(1)
                return {'accuracy_targets': {}}, instance
            def builder(loaded, config, budget, progress, **flags):
                from run_warm_diagnostic import FLAGS
                self.assertEqual(flags, FLAGS)
                budget_ids.append(id(budget)); clock.advance(1)
                return FakeModel(loaded, budget)
            class Session:
                counter = 0; event_consumer = None
                def __init__(self, path, total_budget_s, budget):
                    self.workdir = path; budget_ids.append(id(budget)); clock.advance(1)
                def solve(self, payload, **kwargs):
                    self.counter += 1; calls.append(kwargs); budget_ids.append(id(kwargs['budget']))
                    clock.advance(0.5)
                    return {'fixture': True}
                def close(self):
                    pass
            def prepare(model, accuracy, budget, *args):
                clock.advance(1)
                return fake_preparation(instance, safe_time=3.5, point_time=3.9)
            def diagnostic(model, session, accuracy, budget, *, feedback_kind):
                self.assertEqual(feedback_kind, kind)
                for _ in range(2):
                    session.solve(model.as_solver_dict(), remaining_s=budget.remaining, budget=budget)
                return {'state': 'UNRESOLVED', 'reason': 'FIXTURE_END', 'rounds': [],
                        'safe_upper_bound_J': None}
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory, \
                 patch.object(initial_point, 'prepare_initial_witness', side_effect=prepare), \
                 patch.object(formal, 'solve_formal_diagnostic', side_effect=diagnostic):
                out = Path(directory)/'run'
                result = formal.execute_formal_milp(loader, out, seconds=30, feedback_kind=kind,
                    clock=clock, model_builder=builder, session_factory=Session)
                self.assertTrue((out/'initial_receipt_checkpoint.json').exists())
                self.assertEqual(result['safe_upper_bound_J'], '2')
                self.assertEqual(result['safe_solution_source'], 'initial_constructor')
                self.assertEqual(result['feedback_kind'], kind)
                self.assertEqual(result['outer_round_limit'], 50)
                self.assertEqual(result['timing']['limit_s'], 30)
                self.assertEqual(len(set(budget_ids)), 1)
                self.assertEqual(len(calls), 2)
                self.assertIn('x0', calls[0])
                self.assertNotIn('x0', calls[1])
                self.assertFalse(result['milp_improved_initial_upper_bound'])

    def test_rejected_x0_keeps_safe_seed_without_entering_solver(self):
        clock = Clock(); budget = MethodBudget(30, clock=clock)
        instance = {'id': 'fixture_formal_rejected_x0'}
        model = FakeModel(instance, budget)
        seed = fake_preparation(instance, state='SAFE_POINT_REJECTED')
        seed['x0'] = None
        session = SimpleNamespace(workdir=Path('unused')/'matlab')
        with patch.object(initial_point, 'prepare_initial_witness', return_value=seed), \
             patch.object(formal, 'solve_formal_diagnostic') as diagnostic:
            result = initial_point.solve_with_initial_witness(model, session, {}, budget,
                diagnostic_solver=diagnostic)
        diagnostic.assert_not_called()
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['safe_solution_source'], 'initial_constructor')
        self.assertIsNone(result['solver_diagnostic'])
        self.assertFalse(result['milp_improved_initial_upper_bound'])


if __name__ == '__main__':
    unittest.main()
