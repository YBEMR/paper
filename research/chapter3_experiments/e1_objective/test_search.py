"""Mock-only tests: no research schedule construction or thermal evaluation."""
import ast
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
import hashlib
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import heft_method
from e1_objective import search


class MockBudgetExpired(RuntimeError):
    pass


class MockBudget:
    def __init__(self, allowed_checks=None):
        self.allowed_checks = allowed_checks
        self.checks = 0

    def check(self):
        self.checks += 1
        if self.allowed_checks is not None and self.checks > self.allowed_checks:
            raise MockBudgetExpired('mock deadline')


def mock_instance():
    return {
        'start_grid_ms': '1', 'window_ms': '10',
        'stage_modes': {'A': [
            {'unit_id': unit, 'opp_id': opp}
            for unit in ('CPU', 'NPU') for opp in ('H', 'L')]},
        'scenarios': [
            {'id': sid, 'stage_instances': [
                {'id': iid, 'shared_stage_id': 'A'}]}
            for sid, iid in (('AB', 'a0'), ('AC', 'a1'))],
    }


def mock_candidate(instance, **overrides):
    """Fabricate rows directly; never call the real HEFT builder."""
    unit = overrides.get('deployment_override', {}).get('A', 'CPU')
    rank = overrides.get('opp_rank')
    default_opp = 'L' if rank in (1, 2) else 'H'
    return {'scenes': {
        scene['id']: [{
            'stage_id': stage['id'], 'unit': unit,
            'opp': overrides.get('opp_override', {}).get(
                (scene['id'], stage['id']), default_opp),
            'start_ms': str(overrides.get('start_floor', {}).get(
                (scene['id'], stage['id']), '0')),
        } for stage in scene['stage_instances']]
        for scene in instance['scenarios']}}


def scalar(candidate):
    rows = [row for group in candidate['scenes'].values() for row in group]
    return (Fraction(100) - (10 if rows[0]['unit'] == 'NPU' else 0)
            - 5 * sum(row['opp'] == 'L' for row in rows)
            - sum(Fraction(row['start_ms']) > 0 for row in rows))


def mock_run(module, function, objective, *, state='SAFE', score=scalar,
             allowed_checks=None, builder_none=False, assess_exception=None):
    instance, trace, receipts = mock_instance(), [], []
    budget = MockBudget(allowed_checks)

    def builder(input_instance, input_budget=None, **overrides):
        assert input_instance is instance and input_budget is budget
        trace.append(('build', deepcopy(overrides)))
        candidate = None if builder_none else mock_candidate(instance, **overrides)
        return {'candidate': candidate,
                'status': 'MOCK_CONSTRUCTION_UNRESOLVED' if candidate is None else 'MOCK_COMPLETE',
                'reason': 'MOCK_NO_CANDIDATE' if candidate is None else None,
                'opp_rank': overrides.get('opp_rank')}

    def assess(candidate, source):
        trace.append(('assess', deepcopy(candidate), source))
        if assess_exception:
            raise assess_exception('mock evaluation deadline')
        value = score(candidate)
        bounds = list(value) if isinstance(value, (tuple, list)) else [str(value), str(value)]
        result = {'state': state, objective: bounds}
        receipts.append(result)
        return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(module, 'build_heft_candidate', builder))
        stack.enter_context(patch.object(module, 'explicit_start_sets', return_value=None))
        policy = stack.enter_context(patch.object(module, 'require_heuristic_control'))
        # A mistaken call into the physical evaluator must fail, even on mocks.
        stack.enter_context(patch('thermal.evaluate_candidate', side_effect=AssertionError(
            'real thermal evaluation forbidden in search mock tests')))
        try:
            result = function(instance, {'mock': True}, budget, assess, allow_auto_low=True)
            error = None
        except MockBudgetExpired as failure:
            result, error = None, str(failure)
        policy.assert_called_once_with(instance, {'mock': True}, 'HEFT search', allow_auto_low=True)
    return result, trace, budget.checks, error, receipts


class NormalizeSearch(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        if node.name == 'run_search':
            node.name = 'run_heft'
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
        return node

    def visit_Name(self, node):
        if node.id == '_planning_interval':
            node.id = '_energy_interval'
        return node

    def visit_Constant(self, node):
        replacements = {'planning_score_J': 'weighted_energy_J',
                        'local_base_planning_score_J': 'local_base_energy_J'}
        if isinstance(node.value, str):
            node.value = replacements.get(node.value, node.value)
        return node

    def visit_keyword(self, node):
        node = self.generic_visit(node)
        if node.arg == 'local_base_planning_score_J':
            node.arg = 'local_base_energy_J'
        return node


class SearchAdaptationTests(unittest.TestCase):
    def test_original_source_identity_frozen(self):
        self.assertEqual(hashlib.sha256((ROOT / 'heft_method.py').read_bytes()).hexdigest(),
                         search.HEFT_SOURCE_SHA256)

    def test_search_body_ast_only_declared_objective_changes(self):
        old = NormalizeSearch().visit(ast.parse(inspect.getsource(heft_method.run_heft)))
        new = NormalizeSearch().visit(ast.parse(inspect.getsource(search.run_search)))
        self.assertEqual(ast.dump(old, include_attributes=False),
                         ast.dump(new, include_attributes=False))

    def test_full_score_has_identical_mock_calls_and_local_acceptance(self):
        old = mock_run(heft_method, heft_method.run_heft, 'weighted_energy_J')
        new = mock_run(search, search.run_search, 'planning_score_J')
        self.assertEqual(old[1:4], new[1:4])
        old_meta, new_meta = deepcopy(old[0]), deepcopy(new[0])
        self.assertGreater(old_meta['local_accepted'], 0)
        old_meta.pop('rule_version'); new_meta.pop('rule_version')
        old_rules, new_rules = old_meta.pop('rules'), new_meta.pop('rules')
        old_rules.pop('energy_adjustment'); new_rules.pop('energy_adjustment')
        self.assertEqual(old_rules, new_rules)
        new_meta['local_base_energy_J'] = new_meta.pop('local_base_planning_score_J')
        self.assertEqual(old_meta, new_meta)
        self.assertEqual(len(new_meta['construction_attempts']), 1)

    def test_score_direction_can_reverse_true_energy_direction(self):
        def full(candidate):
            return '200' if candidate['scenes']['AB'][0]['unit'] == 'NPU' else '100'
        def omit(candidate):
            return '1' if candidate['scenes']['AB'][0]['unit'] == 'NPU' else '2'
        full_result = mock_run(search, search.run_search, 'planning_score_J', score=full)[0]
        omit_result = mock_run(search, search.run_search, 'planning_score_J', score=omit)[0]
        self.assertEqual(full_result['local_base_candidate']['scenes']['AB'][0]['unit'], 'CPU')
        self.assertEqual(omit_result['local_base_candidate']['scenes']['AB'][0]['unit'], 'NPU')
        self.assertEqual(omit_result['local_base_planning_score_J'], ['1', '1'])
        self.assertNotIn('local_base_energy_J', omit_result)

    def test_non_safe_score_never_accepted_and_duplicate_fallbacks_unchanged(self):
        old = mock_run(heft_method, heft_method.run_heft, 'weighted_energy_J', state='UNRESOLVED')
        new = mock_run(search, search.run_search, 'planning_score_J', state='UNRESOLVED')
        self.assertEqual(old[1:4], new[1:4])
        self.assertEqual(new[0]['status'], 'NO_SAFE_CONSTRUCTED_WITNESS')
        self.assertEqual(len(new[0]['construction_attempts']), 4)
        self.assertEqual(sum(row.get('duplicate_construction', False)
                             for row in new[0]['construction_attempts']), 2)
        self.assertEqual(len(new[4]), 2)

    def test_all_constructions_unresolved_does_not_evaluate(self):
        result, _, _, error, receipts = mock_run(
            search, search.run_search, 'planning_score_J', builder_none=True)
        self.assertEqual(result['status'], 'NO_SAFE_CONSTRUCTED_WITNESS')
        self.assertEqual(receipts, [])
        self.assertIsNone(error)

    def test_overlapping_and_equal_intervals_are_not_local_strict_improvements(self):
        def overlapping(candidate):
            return ['89', '101'] if candidate['scenes']['AB'][0]['unit'] == 'NPU' else ['100', '100']
        result = mock_run(search, search.run_search, 'planning_score_J', score=overlapping)[0]
        self.assertEqual(result['local_accepted'], 0)
        self.assertEqual(result['local_base_planning_score_J'], ['100', '100'])

    def test_deadline_checkpoint_sequence_is_unchanged(self):
        for allowed in (0, 1, 3, 6, 10):
            with self.subTest(allowed=allowed):
                old = mock_run(heft_method, heft_method.run_heft, 'weighted_energy_J', allowed_checks=allowed)
                new = mock_run(search, search.run_search, 'planning_score_J', allowed_checks=allowed)
                self.assertEqual(old[1:4], new[1:4])
                self.assertEqual(new[3], 'mock deadline')

    def test_evaluator_cutoff_propagates_without_retry(self):
        result, trace, _, error, _ = mock_run(search, search.run_search, 'planning_score_J',
                                             assess_exception=MockBudgetExpired)
        self.assertIsNone(result)
        self.assertEqual(error, 'mock evaluation deadline')
        self.assertEqual(sum(row[0] == 'build' for row in trace), 1)
        self.assertEqual(sum(row[0] == 'assess' for row in trace), 1)

    def test_interval_uses_only_planning_view_field(self):
        self.assertIsNone(search._planning_interval({'state': 'SAFE', 'weighted_energy_J': ['0', '1']}))
        self.assertIsNone(search._planning_interval({'state': 'UNRESOLVED', 'planning_score_J': ['0', '1']}))
        for invalid in (['-1', '1'], ['2', '1'], ['1']):
            self.assertIsNone(search._planning_interval({'state': 'SAFE', 'planning_score_J': invalid}))
        self.assertEqual(search._planning_interval({'state': 'SAFE', 'planning_score_J': ['1/3', '2/3']}),
                         (Fraction(1, 3), Fraction(2, 3)))


if __name__ == '__main__':
    unittest.main()
