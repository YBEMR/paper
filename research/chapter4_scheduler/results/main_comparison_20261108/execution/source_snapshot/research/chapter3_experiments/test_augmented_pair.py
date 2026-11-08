"""Pure mocks for K135's pair routing, irreversible claims and wrapper clock."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from uuid import uuid4

import run_augmented_pair as pair


class PairTests(unittest.TestCase):
    def setUp(self):
        self.folder = pair.REPO/'.runtime/k135_wrapper_fixtures'/uuid4().hex
        self.folder.mkdir(parents=True)
        self.out = self.folder/'pair'
        self.out.mkdir()
        (self.out/'claims').mkdir()
        pair.save(self.out/'declaration.json', {'protocol': pair.PROTOCOL})
        pair.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0,
            'calls': [], 'method_budget_s_reserved': 0})
        self.d = {'input_sha256': 'instance', 'config_sha256': 'config',
            'raw_config_sha256': 'raw', 'old_opened_by_scene': {'AB': ['b'], 'AC': ['c']},
            'new_opened_by_scene': {'AB': ['a','b'], 'AC': ['a','c']}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(pair, 'GLOBAL_CLAIM', self.folder/'global_claim.json'))

    def safe(self, *, new=False, reason='WALL_TIME_LIMIT'):
        result = {'state': 'SAFE', 'reason': reason, 'safe_upper_bound_J': 1.,
            'timing': {'method_elapsed_s': 300., 'cleanup_s': 5.}}
        if new:
            result['augmented_transport'] = {'latched_unresolved': False,
                'failure_reasons': [], 'requests': []}
        return result

    def run_fake(self, side_effect=None):
        execute = self.stack.enter_context(patch.object(pair, 'execute', side_effect=side_effect or
            (lambda job, out, d: self.safe(new=job['id']!='old_n1'))))
        self.stack.enter_context(patch.object(pair, 'admission', return_value=self.d))
        return pair.run(self.out), execute

    def test_01_fixed_job_order(self):
        self.assertEqual([j['id'] for j in pair.jobs()], ['old_n1','augmented_all_opp_start'])
        self.assertEqual(pair.SECONDS, 300)
        self.assertEqual(pair.SCENE_SECONDS, 60)
        self.assertEqual(pair.CUT, 10)

    def test_02_old_route_and_options(self):
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as old, \
             patch('fixed_unit_method.execute_augmented_fixed_unit_opp_start') as new:
            pair.execute(pair.jobs()[0], self.out, self.d)
        new.assert_not_called()
        kw = old.call_args.kwargs
        self.assertEqual(kw['seconds'], 300)
        self.assertEqual(kw['scene_slice_s'], 60)
        self.assertEqual(kw['builder_options'], {'cumulative_precedence': False})
        self.assertEqual(kw['shared_deployment'], pair.SHARED)
        self.assertEqual(kw['opened_by_scene'], self.d['old_opened_by_scene'])
        self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})

    def test_03_new_route_and_same_options(self):
        with patch('neighborhood_method.execute_n1_neighborhood') as old, \
             patch('fixed_unit_method.execute_augmented_fixed_unit_opp_start', return_value={}) as new:
            pair.execute(pair.jobs()[1], self.out, self.d)
        old.assert_not_called()
        kw = new.call_args.kwargs
        self.assertNotIn('opened_by_scene', kw)
        self.assertEqual(kw['seconds'], 300)
        self.assertEqual(kw['scene_slice_s'], 60)
        self.assertEqual(kw['builder_options'], {'cumulative_precedence': False})
        self.assertEqual(kw['shared_deployment'], pair.SHARED)
        self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})

    def test_04_fresh_loader_identity_and_budget_check(self):
        budget = Mock()
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as method, \
             patch('run_neighborhood_diagnostic.fresh_input', return_value=('raw','config','instance')) as fresh, \
             patch('run_neighborhood_diagnostic.opened_stages', return_value=self.d['old_opened_by_scene']), \
             patch('scene_adapter.canonical_hash', side_effect=lambda x:x):
            pair.execute(pair.jobs()[0], self.out, self.d)
            self.assertEqual(method.call_args.args[0](budget), ('config','instance'))
        fresh.assert_called_once_with(budget)
        budget.check.assert_called_once()

    def test_05_loader_rejects_different_input(self):
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as method, \
             patch('run_neighborhood_diagnostic.fresh_input', return_value=('raw','config','changed')), \
             patch('scene_adapter.canonical_hash', side_effect=lambda x:x):
            pair.execute(pair.jobs()[0], self.out, self.d)
            self.assertRaises(ValueError, method.call_args.args[0], Mock())

    def test_06_pair_exactly_two_calls_and_claims(self):
        okay, execute = self.run_fake()
        self.assertTrue(okay)
        self.assertEqual(execute.call_count, 2)
        ledger = pair.read(self.out/'ledger.json')
        self.assertEqual(ledger['consumed'], 2)
        self.assertEqual(ledger['method_budget_s_reserved'], 600)
        self.assertTrue((self.out/'claims/old_n1.json').exists())
        self.assertTrue((self.out/'claims/augmented_all_opp_start.json').exists())
        self.assertTrue((self.out/'wrapper_timing.json').exists())

    def test_07_completed_calls_never_rerun(self):
        okay, execute = self.run_fake()
        self.assertTrue(okay)
        execute.reset_mock()
        self.assertTrue(pair.run(self.out))
        execute.assert_not_called()

    def test_08_failure_stops_second_and_preserves_U(self):
        result = self.safe()
        result['technical_state'] = 'FAILED'
        okay, execute = self.run_fake(lambda *a:result)
        self.assertFalse(okay)
        self.assertEqual(execute.call_count, 1)
        ledger = pair.read(self.out/'ledger.json')
        self.assertEqual(ledger['state'], 'BLOCKED')
        self.assertEqual(ledger['calls'][0]['safe_upper_bound_J'], 1.)
        self.assertRaises(FileExistsError, pair.run, self.out)

    def test_09_exception_consumes_and_stops(self):
        def broken(*args):
            raise RuntimeError('mock fault')
        okay, execute = self.run_fake(broken)
        self.assertFalse(okay)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(pair.read(self.out/'ledger.json')['consumed'], 1)
        self.assertRaises(FileExistsError, pair.run, self.out)

    def test_10_running_claim_cannot_resume(self):
        ledger = pair.read(self.out/'ledger.json')
        ledger.update(state='RUNNING', consumed=1, calls=[{'id':'old_n1','state':'RUNNING'}])
        pair.save(self.out/'ledger.json', ledger)
        self.stack.enter_context(patch.object(pair, 'admission', return_value=self.d))
        self.assertRaises(FileExistsError, pair.run, self.out)

    def test_11_another_out_cannot_bypass_global_claim(self):
        self.run_fake()
        other = self.folder/'other'
        other.mkdir()
        pair.save(other/'declaration.json', {'protocol':pair.PROTOCOL})
        pair.save(other/'ledger.json', {'state':'DECLARED','calls':[],'consumed':0})
        self.assertRaises(FileExistsError, pair.run, other)

    def test_12_no_budget_replenish_on_timeout(self):
        okay, execute = self.run_fake()
        self.assertTrue(okay)
        self.assertEqual(execute.call_count, 2)
        self.assertTrue(all(r['seconds']==300 for r in pair.read(self.out/'ledger.json')['calls']))

    def test_13_incomplete_cleanup_stops(self):
        def complete(job, out, d):
            path = out/job['id']/'matlab'
            path.mkdir(parents=True)
            pair.save(path/'closed.json', {'cleanup_status':'pending','returncode':None})
            result = self.safe()
            result['matlab_worker_ready'] = True
            return result
        okay, execute = self.run_fake(complete)
        self.assertFalse(okay)
        self.assertEqual(execute.call_count, 1)

    def test_14_original_source_change_stops(self):
        execute = self.stack.enter_context(patch.object(pair, 'execute', return_value=self.safe()))
        self.stack.enter_context(patch.object(pair, 'admission', side_effect=[self.d,self.d,ValueError('changed')]))
        self.assertFalse(pair.run(self.out))
        self.assertEqual(execute.call_count, 1)

    def test_15_transport_failure_latch_and_callbacks(self):
        job = pair.jobs()[1]
        self.assertTrue(pair.transport_issues(job, {}))
        result = self.safe(new=True)
        self.assertFalse(pair.transport_issues(job, result))
        result['augmented_transport']['latched_unresolved'] = True
        self.assertTrue(pair.transport_issues(job, result))
        result = self.safe(new=True)
        result['augmented_transport']['requests'] = [{'latched_unresolved':False,
            'failure_reasons': [], 'callback_publications_complete':True,
            'expected_callback_numbers':[1,2], 'checked_callback_numbers':[1]}]
        self.assertTrue(pair.transport_issues(job, result))

    def test_16_timing_keeps_method_cleanup_and_archive_separate(self):
        result = {'timing': {'method_elapsed_s':300.,
            'method_elapsed_excluding_cleanup_s':299., 'cleanup_s':5.}}
        row = pair.timing_components(311., result)
        self.assertEqual(row['method_stop_elapsed_s'], 299.)
        self.assertEqual(row['cleanup_s'], 5.)
        self.assertEqual(row['unattributed_wrapper_archive_overhead_s'], 7.)
        self.assertTrue(row['overhead_is_not_solver_time'])

    def test_17_primary_tail_serialization_in_wrapper_clock(self):
        clock = [0.]
        real_save = pair.save
        def save_timed(path, value):
            real_save(path, value)
            clock[0] += 2.
        def call(job, out, d):
            clock[0] += 10.
            return self.safe(new=job['id']!='old_n1')
        self.stack.enter_context(patch.object(pair.time, 'monotonic', side_effect=lambda:clock[0]))
        self.stack.enter_context(patch.object(pair, 'save', side_effect=save_timed))
        okay, execute = self.run_fake(call)
        self.assertTrue(okay)
        timing = pair.read(self.out/'claims/old_n1_wrapper_timing.json')
        self.assertEqual(timing['wrapper_call_and_primary_archive_wall_s'], 14.)
        self.assertFalse(timing['clock_receipt_own_serialization_included'])

    def test_18_unknown_method_not_routed(self):
        self.assertRaises(ValueError, pair.execute, {'id':'x','method':'bad'}, self.out, self.d)

    def test_19_numeric_failure_new_stops_with_prior_safe(self):
        def result(job, out, d):
            r = self.safe(new=job['id']!='old_n1')
            if job['id']!='old_n1':
                r['augmented_transport']['failure_reasons'] = ['mock numeric failure']
            return r
        okay, execute = self.run_fake(result)
        self.assertFalse(okay)
        self.assertEqual(execute.call_count, 2)
        ledger = pair.read(self.out/'ledger.json')
        self.assertEqual(ledger['calls'][0]['state'], 'COMPLETED')
        self.assertEqual(ledger['calls'][1]['safe_upper_bound_J'], 1.)


if __name__ == '__main__':
    unittest.main()
