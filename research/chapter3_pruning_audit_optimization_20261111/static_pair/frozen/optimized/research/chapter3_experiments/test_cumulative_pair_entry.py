"""Hermetic K122 entry protocol checks; no model, heat, MATLAB or research.

SAFE values appearing in failure receipts are control-flow test doubles, not
physical evaluations or empirical evidence. All source/gate files are local
temporary fixtures; the real K121 gate is never rewritten by these tests.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_cumulative_pair_diagnostic as entry


class CumulativePairEntry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.here = self.root / 'research/chapter3_experiments'
        self.here.mkdir(parents=True)
        self.gate = self.here / 'results/cumulative_precedence_precheck02'
        self.gate.mkdir(parents=True)
        self.readfix = self.root / 'K117_verification.json'
        entry.save(self.readfix, {'passed': False, 'count': 74,
                                  'shutdown_limit': 'historical, not reclassified'})
        sources = {}
        for number in range(39):
            name = 'core_%02d.py' % number
            path = self.root / name
            path.write_text('fixture source %d\n' % number, encoding='utf-8')
            sources[name] = entry.sha(path)
        self.core = self.root / 'core_00.py'
        for name in entry.EXTRA_SOURCES:
            (self.here / name).write_text('entry fixture\n', encoding='utf-8')
        gate_checks = {'protocol': 'cumulative-precedence-integration-precheck-v1',
            'passed': True, 'source_unchanged': True, 'tests_run': 62,
            'failures': 0, 'errors': 0, 'error': None,
            'new_LP_MILP_native_thermal_trajectory_or_research_calls': 0,
            'source_sha256': sources}
        entry.save(self.gate / 'checks.json', gate_checks)
        for name in ('default_matrix_identity.json', 'archived_rows.json'):
            entry.save(self.gate / name, {'passed': True})
        entry.save(self.gate / 'independent_review.json', {'passed': True, 'source_sha256': sources})
        (self.gate / 'unittest.txt').write_text('completed K121 fixture gate\n', encoding='utf-8')
        self.patches = mock.patch.multiple(entry, REPO=self.root, HERE=self.here,
            CLAIM=self.root / 'claim01.json', K121_GATE=self.gate, READ_FIX=self.readfix)
        self.patches.start()
        self.sources = entry.collect_sources()
        self.checks = self.root / 'targeted_checks.json'
        entry.save(self.checks, {'protocol': entry.PROTOCOL, 'passed': True,
            'source_unchanged': True, 'source_sha256': self.sources,
            'test_targets': list(entry.TESTS), 'count': 11, 'failures': 0, 'errors': 0,
            'K121_evidence_sha256': entry._k121_evidence(),
            'read_fix_report_sha256': entry.sha(self.readfix)})
        self.out = self.root / 'pair'

    def tearDown(self):
        self.patches.stop()
        self.temp.cleanup()

    def prepare(self):
        entry.prepare(self.out, self.checks)

    def test_declaration_freezes_off_on_cut10_budget_and_completed_evidence(self):
        with mock.patch.object(entry, '_execute_one') as invoke:
            self.prepare()
        invoke.assert_not_called()
        declaration = entry.read(self.out / 'declaration.json')
        self.assertEqual(declaration['settings_in_order'], [False, True])
        self.assertEqual(declaration['call_names_in_order'], ['call_off', 'call_on'])
        self.assertEqual((declaration['per_call_budget_s'], declaration['per_call_scene_slice_s']), (300, 60))
        self.assertEqual(declaration['CutMaxIterations'], 10)
        self.assertEqual(declaration['shared_deployment'],
                         {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'})
        self.assertEqual(len(declaration['source_sha256']), 41)
        self.assertFalse(declaration['retry_allowed'])
        self.assertFalse(declaration['budget_extension_allowed'])
        self.assertFalse(declaration['historical_K119_is_control'])
        self.assertFalse(declaration['K121_62_checks_rerun'])
        self.assertTrue(declaration['K117_original_failed_gate_and_shutdown_limit_retained'])
        self.assertFalse(entry.CLAIM.exists())
        self.assertEqual(entry.read(self.out / 'precheck_evidence/K117_verification.json')['passed'], False)
        for name in entry.K121_FILES:
            self.assertEqual(entry.sha(self.out / 'precheck_evidence/K121' / name), entry.sha(self.gate / name))

    def test_pair_order_independent_paths_and_one_claim_prevent_replay(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'UNRESOLVED', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                'timing': {'method_elapsed_s': 300}}) as invoke:
            self.assertTrue(entry.run(self.out))
            self.assertEqual([call.args[1] for call in invoke.call_args_list], [False, True])
            self.assertEqual([call.args[0].name for call in invoke.call_args_list], ['call_off', 'call_on'])
            with self.assertRaises(FileExistsError):
                entry.run(self.out)
            self.assertEqual(invoke.call_count, 2)
        report = entry.read(self.out / 'run_record.json')
        self.assertEqual(report['research_calls_consumed'], 2)
        self.assertEqual(report['state'], 'PAIR_COMPLETED')

    def test_exception_is_recorded_without_retry_or_second_call(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', side_effect=RuntimeError('fixture only')) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertEqual(report['state'], 'STOPPED_TECHNICAL_FAILURE')
        self.assertEqual(report['research_calls_consumed'], 1)
        self.assertIn('fixture only', report['calls'][0]['error'])
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_retained_safe_does_not_hide_nested_numerical_conflict(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                'safe_upper_bound_J': '1.0', 'scenes': {'AB': {'solver_result': {
                    'rounds': [{'numerical_consistency': {
                        'state': 'NUMERICAL_ADMISSION_STATUS_CONFLICT'}}]}}}}) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertEqual(report['calls'][0]['method_state'], 'SAFE')
        self.assertEqual(report['calls'][0]['safe_upper_bound_J'], '1.0')
        self.assertTrue(report['calls'][0]['technical_issues'])
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_explicit_cleanup_error_preserves_safe_and_stops_second(self):
        self.prepare()
        with mock.patch.object(entry, '_execute_one', return_value={
                'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                'cleanup_error': 'fixture cleanup exception', 'safe_upper_bound_J': '1.0'}) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertEqual(report['calls'][0]['cleanup_error'], 'fixture cleanup exception')
        self.assertEqual(report['calls'][0]['safe_upper_bound_J'], '1.0')
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_existing_cleanup_pending_marker_blocks_second_worker(self):
        self.prepare()

        def pending(call, enabled):
            folder = call / 'invocation/matlab'
            folder.mkdir(parents=True)
            entry.save(folder / 'closed.json', {'cleanup_pending_pid': 12345, 'returncode': None})
            return {'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                    'safe_upper_bound_J': '1.0'}

        with mock.patch.object(entry, '_execute_one', side_effect=pending) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertEqual(report['calls'][0]['cleanup_status']['cleanup_pending_pid'], 12345)
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_failed_or_stale_gate_cannot_prepare_or_consume_claim(self):
        baseline = entry.read(self.gate / 'checks.json')
        bad = deepcopy(baseline)
        bad['passed'] = False
        entry.save(self.gate / 'checks.json', bad)
        with self.assertRaises(ValueError):
            self.prepare()
        entry.save(self.gate / 'checks.json', baseline)
        self.core.write_text('changed admitted source', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(entry.CLAIM.exists())
        self.assertFalse(self.out.exists())

    def test_changed_frozen_rule_or_snapshot_stops_before_method_and_claim(self):
        self.prepare()
        declaration = entry.read(self.out / 'declaration.json')
        modified = deepcopy(declaration)
        modified['CutMaxIterations'] = 1
        entry.save(self.out / 'declaration.json', modified)
        with mock.patch.object(entry, '_execute_one') as invoke:
            with self.assertRaises(ValueError):
                entry.run(self.out)
            entry.save(self.out / 'declaration.json', declaration)
            (self.out / 'source_snapshot/core_00.py').write_text('changed snapshot', encoding='utf-8')
            with self.assertRaises(ValueError):
                entry.run(self.out)
        invoke.assert_not_called()
        self.assertFalse(entry.CLAIM.exists())

    def test_active_source_change_after_first_call_is_not_hidden_or_retried(self):
        self.prepare()

        def change(call, enabled):
            self.core.write_text('concurrent edit', encoding='utf-8')
            return {'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                    'safe_upper_bound_J': '1.0'}

        with mock.patch.object(entry, '_execute_one', side_effect=change) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertFalse(report['calls'][0]['source_unchanged'])
        self.assertEqual(report['calls'][0]['safe_upper_bound_J'], '1.0')
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')

    def test_execute_passes_strict_flags_cut10_and_fresh_loaders_inside_each_budget(self):
        import control_policy
        import inputs
        import partial_method
        from matlab_bridge import MatlabSession

        marker = object()
        captured, loaders, returned_inputs = [], [], []

        def method(loader, folder, **kwargs):
            loaders.append(loader)
            config1, instance1 = loader(marker)
            config2, instance2 = loader(marker)
            self.assertIsNot(config1, config2)
            self.assertIsNot(instance1, instance2)
            returned_inputs.extend((config1, instance1, config2, instance2))
            self.assertEqual(kwargs['seconds'], 300)
            self.assertEqual(kwargs['scene_slice_s'], 60)
            self.assertEqual(kwargs['shared_deployment'], entry.SHARED)
            self.assertIsNot(kwargs['shared_deployment'], entry.SHARED)
            self.assertIs(kwargs['session_factory'].func, MatlabSession)
            self.assertEqual(kwargs['session_factory'].keywords, {'cut_max_iterations': 10})
            captured.append(kwargs['builder_options'])
            return {'state': 'MOCK_ROUTING_ONLY'}

        with mock.patch.object(inputs, 'load_config', side_effect=lambda: {'raw': True}) as load, \
                mock.patch.object(inputs, 'build_instance', side_effect=lambda config, problem, budget: {'problem': problem}) as expand, \
                mock.patch.object(control_policy, 'with_auto_low_idle', side_effect=deepcopy), \
                mock.patch.object(partial_method, 'execute_shared_deployment', side_effect=method):
            entry._execute_one(self.root / 'call_off', False)
            entry._execute_one(self.root / 'call_on', True)
        self.assertEqual(load.call_count, 4)
        self.assertEqual(expand.call_count, 4)
        self.assertTrue(all(call.kwargs['budget'] is marker for call in expand.call_args_list))
        self.assertTrue(all(call.args[1] == 'base__R1' for call in expand.call_args_list))
        self.assertEqual(captured, [{'cumulative_precedence': False}, {'cumulative_precedence': True}])
        self.assertIsNot(loaders[0], loaders[1])
        self.assertEqual(len({id(item) for item in returned_inputs}), 8)
        with self.assertRaises(ValueError):
            entry._execute_one(self.root / 'invalid', 0)

    def test_malformed_cleanup_receipt_preserves_safe_but_does_not_start_second(self):
        self.prepare()

        def malformed(call, enabled):
            folder = call / 'invocation/matlab'
            folder.mkdir(parents=True)
            (folder / 'closed.json').write_text('{', encoding='utf-8')
            return {'state': 'SAFE', 'reason': 'SCENE_SEARCH_SEQUENCE_COMPLETE',
                    'safe_upper_bound_J': '1.0'}

        with mock.patch.object(entry, '_execute_one', side_effect=malformed) as invoke:
            self.assertFalse(entry.run(self.out))
        self.assertEqual(invoke.call_count, 1)
        report = entry.read(self.out / 'run_record.json')
        self.assertTrue(report['calls'][0]['cleanup_metadata_error'])
        self.assertEqual(report['calls'][0]['safe_upper_bound_J'], '1.0')
        self.assertEqual(report['calls'][1]['state'], 'NOT_RUN_AFTER_TECHNICAL_FAILURE')


if __name__ == '__main__':
    unittest.main()
