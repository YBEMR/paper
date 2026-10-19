"""Hermetic K119 entry checks: no model, heat, MATLAB or research run."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_cut_pair_diagnostic as entry


class CutPairEntry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root/'core.py'
        self.core.write_text('unchanged math', encoding='utf-8')
        self.readfix = self.root/'readfix.json'
        entry.save(self.readfix, {'passed': False, 'count': 74})
        self.sources = {'core.py': entry.sha(self.core)}
        self.checks = self.root/'checks.json'
        entry.save(self.checks, {'passed': True, 'source_sha256': self.sources,
                               'read_fix_report_sha256': entry.sha(self.readfix)})
        self.patches = mock.patch.multiple(entry, REPO=self.root,
            CLAIM=self.root/'claim.json', READ_FIX=self.readfix,
            collect_sources=mock.Mock(return_value=self.sources))
        self.patches.start()
        self.out = self.root/'pair'

    def tearDown(self):
        self.patches.stop()
        self.temp.cleanup()

    def prepare(self):
        entry.prepare(self.out, self.checks)

    def test_declaration_is_fixed_and_prepare_makes_no_method_call(self):
        with mock.patch.object(entry, '_execute_one') as invoke:
            self.prepare()
        invoke.assert_not_called()
        d = entry.read(self.out/'declaration.json')
        self.assertEqual(d['settings_in_order'], [10, 1])
        self.assertEqual((d['per_call_budget_s'], d['per_call_scene_slice_s']), (300, 60))
        self.assertEqual(d['shared_deployment'], {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'})
        self.assertFalse(d['retry_allowed'])
        self.assertFalse(d['budget_extension_allowed'])
        self.assertFalse(d['historical_K116_is_control'])
        self.assertFalse((self.root/'claim.json').exists())

    def test_pair_order_independent_paths_and_consumed_claim_cannot_replay(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE', 'timing': {}}) as invoke:
            self.assertTrue(entry.run(self.out))
            self.assertEqual([c.args[1] for c in invoke.call_args_list], [10, 1])
            self.assertEqual([c.args[0].name for c in invoke.call_args_list], ['call_10', 'call_1'])
            with self.assertRaises(FileExistsError):
                entry.run(self.out)
            self.assertEqual(invoke.call_count, 2)
        r = entry.read(self.out/'run_record.json')
        self.assertEqual(r['research_calls_consumed'], 2)
        self.assertEqual(r['state'], 'PAIR_COMPLETED')

    def test_failure_is_recorded_not_retried_and_second_is_not_started(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', side_effect=RuntimeError('fixture only')) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        r = entry.read(self.out/'run_record.json')
        self.assertEqual(r['state'], 'STOPPED_TECHNICAL_FAILURE')
        self.assertEqual(r['research_calls_consumed'], 1)
        self.assertEqual(r['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_retained_safe_does_not_hide_numerical_conflict_or_start_next_call(self):
        from matlab_bridge import NUMERICAL_CONSISTENCY_UNRESOLVED
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'SAFE', 'reason': NUMERICAL_CONSISTENCY_UNRESOLVED,
                'safe_upper_bound_J': '1.0'}) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        r = entry.read(self.out/'run_record.json')
        self.assertEqual(r['state'], 'STOPPED_TECHNICAL_FAILURE')
        self.assertEqual(r['calls'][0]['method_state'], 'SAFE')
        self.assertEqual(r['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_explicit_cleanup_error_is_preserved_and_stops_second_worker(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                'cleanup_error': 'fixture cleanup exception', 'safe_upper_bound_J': '1.0'}) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        r = entry.read(self.out/'run_record.json')
        self.assertEqual(r['state'], 'STOPPED_TECHNICAL_FAILURE')
        self.assertEqual(r['calls'][0]['cleanup_error'], 'fixture cleanup exception')
        self.assertEqual(r['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_existing_cleanup_pending_marker_stops_next_without_new_exit_threshold(self):
        self.prepare()
        def pending(call, setting):
            folder = call/'invocation/matlab'
            folder.mkdir(parents=True)
            entry.save(folder/'closed.json', {'cleanup_pending_pid': 12345, 'returncode': None})
            return {'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE'}
        with mock.patch.object(entry, '_execute_one', side_effect=pending) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        r = entry.read(self.out/'run_record.json')
        self.assertEqual(r['calls'][0]['cleanup_status']['cleanup_pending_pid'], 12345)
        self.assertEqual(r['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_failed_checks_or_changed_frozen_protocol_cannot_consume_claim(self):
        report = entry.read(self.checks)
        report['passed'] = False
        entry.save(self.checks, report)
        with self.assertRaises(ValueError):
            self.prepare()
        report['passed'] = True
        entry.save(self.checks, report)
        self.prepare()
        d = entry.read(self.out/'declaration.json')
        d['per_call_budget_s'] = 301
        entry.save(self.out/'declaration.json', d)
        with mock.patch.object(entry, '_execute_one') as invoke:
            with self.assertRaises(ValueError):
                entry.run(self.out)
        invoke.assert_not_called()
        self.assertFalse((self.root/'claim.json').exists())

    def test_changed_active_source_stops_pair_without_new_search(self):
        self.prepare()
        def change_source(*args):
            self.core.write_text('concurrent edit', encoding='utf-8')
            return {'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE'}
        with mock.patch.object(entry, '_execute_one', side_effect=change_source) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        self.assertFalse(entry.read(self.out/'run_record.json')['calls'][0]['source_unchanged'])

    def test_execute_uses_fresh_loader_and_fixed_method_budget_each_time(self):
        import inputs
        import partial_method
        import control_policy
        from matlab_bridge import MatlabSession
        marker = object()
        captured = []
        def method(loader, folder, **kwargs):
            c1, i1 = loader(marker)
            c2, i2 = loader(marker)
            self.assertIsNot(c1, c2)
            self.assertIsNot(i1, i2)
            self.assertEqual(kwargs['seconds'], 300)
            self.assertEqual(kwargs['scene_slice_s'], 60)
            self.assertEqual(kwargs['shared_deployment'], entry.SHARED)
            self.assertIs(kwargs['session_factory'].func, MatlabSession)
            captured.append(kwargs['session_factory'].keywords)
            return {'state': 'fixture'}
        with mock.patch.object(inputs, 'load_config', side_effect=lambda: {'raw': True}) as load, \
                mock.patch.object(inputs, 'build_instance', side_effect=lambda c, p, budget: {'problem': p}) as expand, \
                mock.patch.object(control_policy, 'with_auto_low_idle', side_effect=deepcopy), \
                mock.patch.object(partial_method, 'execute_shared_deployment', side_effect=method):
            entry._execute_one(self.root/'call_10', 10)
            entry._execute_one(self.root/'call_1', 1)
        self.assertEqual(load.call_count, 4)
        self.assertEqual(expand.call_count, 4)
        self.assertTrue(all(c.kwargs['budget'] is marker for c in expand.call_args_list))
        self.assertEqual(captured, [{'cut_max_iterations': 10}, {'cut_max_iterations': 1}])


if __name__ == '__main__':
    unittest.main()
