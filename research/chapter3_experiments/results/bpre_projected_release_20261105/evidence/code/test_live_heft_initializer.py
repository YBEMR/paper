"""Mock-only initialization wiring; no scientific imports, HEFT or MATLAB run."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from live_heft_initializer import install_initializer


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Exhausted(Exception):
    pass


class Budget:
    seconds, start, deadline = 600, 100, 700
    def __init__(self):
        self.now = 150  # Model construction/startup have already consumed 50 s.
        self.active, self.records = [], []
    @property
    def elapsed(self): return self.now-self.start
    @property
    def remaining(self): return max(0, self.deadline-self.now)
    def check(self):
        if self.now >= self.deadline: raise Exhausted('wall_time_limit')
    @contextmanager
    def phase(self, name):
        self.check(); before = self.now; self.active.append(name)
        try: yield
        finally:
            self.active.pop(); self.records.append((name, self.now-before))


def inspect(instance, raw, cutoff):
    candidate, ev = raw.get('safe_candidate'), raw.get('evaluation') or {}
    passed = (candidate is not None and ev.get('state') == 'SAFE'
        and ev.get('evidence_identity') == {'input_sha256': digest(instance), 'candidate_sha256': digest(candidate)}
        and 0 <= ev.get('completed_at_elapsed_s', cutoff) < cutoff)
    return dict(preserved=passed, candidate=deepcopy(candidate), evaluation=deepcopy(ev),
                formed_at_s=ev.get('completed_at_elapsed_s'), U_J=ev.get('safe_upper_bound_J'))


def technical_failure(value):
    if isinstance(value, dict):
        if value.get('reason') in ('INTERFACE_ERROR', 'RESOURCE_LIMIT', 'NUMERICAL_ERROR'): return value['reason']
        if value.get('error'): return value['error']
        return next((found for item in value.values() if (found := technical_failure(item))), None)
    if isinstance(value, list):
        return next((found for item in value if (found := technical_failure(item))), None)


class InitializerTests(unittest.TestCase):
    def setUp(self):
        self.instance = {'id': 'fixture_same_input'}
        self.config = {'accuracy_targets': {'energy': '1/1000'}}
        self.budget = Budget(); self.mode = 'normal'
        self.model = SimpleNamespace(instance=self.instance, budget=self.budget)
        self.candidate = {'scenes': {'fixture': []}}
        self.original_prepare = Mock(side_effect=AssertionError('old constructor must not run'))
        self.evaluate = Mock(side_effect=self.evaluation)
        self.complete = Mock(side_effect=self.completion)
        self.execute = Mock(side_effect=self.search)
        self.initial = SimpleNamespace(_digest=digest, prepare_initial_witness=self.original_prepare,
            complete_initial_point=self.complete, evaluate_model_candidate=self.evaluate)
        self.modules = {'initial_point': self.initial,
            'heuristic_runner': SimpleNamespace(execute_heuristic=self.execute),
            'thermal': SimpleNamespace(Exhausted=Exhausted),
            'research.chapter3_experiments.natural_full_entry': SimpleNamespace(receipt_failure=technical_failure),
            'research.chapter3_method_entry_executor.common': SimpleNamespace(inspect_safe_receipt=inspect)}

    def evaluation(self, model, candidate, accuracy, budget):
        self.assertIs(model, self.model); self.assertIs(budget, self.budget)
        self.assertEqual(accuracy, self.config['accuracy_targets'])
        budget.now += 2
        return dict(state='SAFE', rankable_energy=True, safe_upper_bound_J='1', weighted_energy_J=['1','1'],
            completed_at_elapsed_s=budget.elapsed,
            evidence_identity={'input_sha256': digest(model.instance), 'candidate_sha256': digest(candidate)})

    def completion(self, model, candidate, evaluation, budget):
        self.assertIs(model, self.model); self.assertIs(budget, self.budget)
        budget.check()
        if self.mode == 'completion_exhausted':
            budget.now = 700; budget.check()
        budget.now += 3
        return dict(state='INITIAL_POINT_READY', x0=[1, 0], completed_at_s=budget.elapsed)

    def search(self, loader, output, **kwargs):
        self.assertEqual(kwargs['method'], 'heft'); self.assertEqual(kwargs['seconds'], 600)
        self.assertIs(kwargs['budget'], self.budget); self.assertTrue(kwargs['allow_auto_low'])
        self.assertNotIn('search', kwargs)  # Original complete enhanced HEFT selected.
        self.assertIn('online_heft_including_archive', self.budget.active)
        config, instance = loader(self.budget)
        self.assertIs(instance, self.model.instance)
        self.budget.now += 10
        evaluation = kwargs['evaluator'](instance, self.candidate, config['accuracy_targets'], self.budget)
        raw = dict(state='SAFE', reason='DECLARED_SEARCH_COMPLETED', budget_exhausted=False,
            search={'status': 'BOUNDED_SEARCH_COMPLETED'}, safe_candidate=self.candidate,
            safe_upper_bound_J='1', evaluation=evaluation)
        self.budget.now += 8  # Simulate the archive after scientific search stopped.
        if self.mode == 'archive_error': raise OSError('fixture archive failed after SAFE')
        if self.mode == 'archive_exhausted':
            self.budget.now = 702; raw.update(reason='wall_time_limit', budget_exhausted=True)
        if self.mode in ('INTERFACE_ERROR', 'RESOURCE_LIMIT'):
            raw.update(reason=self.mode, error='fixture technical failure after SAFE')
        if self.mode == 'not_complete': raw['search']['status'] = 'FIRST_SAFE_ONLY'
        return raw

    def invoke(self):
        context = {}
        with patch.dict(sys.modules, self.modules), \
             install_initializer(self.instance, self.config, Path(__file__).parent/'never_created_mock_heft',
                 origin=100, deadline=700, audit_context=context):
            result = self.initial.prepare_initial_witness(self.model, self.config['accuracy_targets'], self.budget)
        self.assertIs(self.initial.prepare_initial_witness, self.original_prepare)
        self.original_prepare.assert_not_called()
        json.dumps(context)  # No budget, function, cache object or x0 in the audit context.
        return result, context

    def test_complete_heft_archive_and_x0_use_same_root(self):
        result, context = self.invoke()
        self.assertEqual(result['state'], 'SAFE_POINT_READY')
        self.assertEqual(context['heft_started_at_s'], 50)
        self.assertEqual(context['heft_returned_at_s'], 70)
        self.assertEqual(context['heft_total_including_archive_s'], 20)
        self.assertEqual(self.budget.records, [('online_heft_including_archive', 20)])
        self.assertEqual(context['hook_returned_at_s'], 73)
        self.assertEqual(context['root_budget_object_id'], id(self.budget))
        self.assertNotIn('x0', context['initialisation'])
        self.assertTrue(context['hook_restored'])

    def test_archive_exhaustion_keeps_timely_heft_only_without_completion(self):
        self.mode = 'archive_exhausted'; result, context = self.invoke()
        self.assertEqual(result['state'], 'SAFE_POINT_UNRESOLVED')
        self.assertIsNotNone(result['witness']); self.assertIsNone(result['x0'])
        self.assertLess(context['heft_safe_formed_at_s'], 600)
        self.complete.assert_not_called()

    def test_technical_failure_keeps_safe_but_never_admits_x0(self):
        for mode in ('INTERFACE_ERROR', 'RESOURCE_LIMIT'):
            with self.subTest(mode=mode):
                self.setUp(); self.mode = mode; result, context = self.invoke()
                self.assertEqual(result['technical_state'], 'TECHNICAL_FAILURE')
                self.assertIsNotNone(result['witness']); self.assertIsNone(result['x0'])
                self.complete.assert_not_called()

    def test_archive_exception_retains_only_in_memory_receipt_as_technical_failure(self):
        self.mode = 'archive_error'; result, context = self.invoke()
        self.assertEqual(result['technical_state'], 'TECHNICAL_FAILURE')
        self.assertIsNotNone(result['witness'])
        self.assertTrue(context['formed_heft_safe']['preserved'])
        self.assertNotIn('heft_raw', context)
        self.assertIn('archive failed', result['error'])
        self.complete.assert_not_called()

    def test_completion_exhaustion_does_not_lose_heft_or_extend_deadline(self):
        self.mode = 'completion_exhausted'; result, context = self.invoke()
        self.assertEqual(result['state'], 'SAFE_POINT_UNRESOLVED')
        self.assertIsNotNone(result['witness']); self.assertFalse(context['x0_ready'])
        self.assertEqual(self.budget.deadline, 700)

    def test_first_safe_without_completed_search_cannot_start_milp(self):
        self.mode = 'not_complete'; result, context = self.invoke()
        self.assertEqual(result['technical_state'], 'TECHNICAL_FAILURE')
        self.assertIn('FULL_ENHANCED_HEFT_DID_NOT_COMPLETE', result['error'])
        self.assertIsNotNone(result['witness']); self.complete.assert_not_called()

    def test_foreign_budget_and_second_initializer_call_are_rejected(self):
        self.model.budget = Budget()
        result, context = self.invoke()
        self.assertIn('SHARED_BUDGET_OBJECT_REQUIRED', result['error'])
        self.execute.assert_not_called()
        self.setUp()
        with patch.dict(sys.modules, self.modules), \
             install_initializer(self.instance, self.config, Path(__file__).parent/'never_created_mock_heft', origin=100, deadline=700):
            self.initial.prepare_initial_witness(self.model, self.config['accuracy_targets'], self.budget)
            with self.assertRaisesRegex(ValueError, 'SINGLE_USE'):
                self.initial.prepare_initial_witness(self.model, self.config['accuracy_targets'], self.budget)

    def test_context_restores_original_on_outer_failure(self):
        with patch.dict(sys.modules, self.modules):
            with self.assertRaisesRegex(RuntimeError, 'outer fixture'):
                with install_initializer(self.instance, self.config, Path(__file__).parent/'never_created_mock_heft', origin=100, deadline=700):
                    raise RuntimeError('outer fixture')
        self.assertIs(self.initial.prepare_initial_witness, self.original_prepare)


if __name__ == '__main__':
    unittest.main()
