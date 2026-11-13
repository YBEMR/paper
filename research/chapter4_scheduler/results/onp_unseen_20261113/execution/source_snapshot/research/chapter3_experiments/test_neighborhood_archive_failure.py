"""Post-budget archival faults must not replace already committed evidence.

All physical/solver values come from the existing fabricated lifecycle
harness. No real thermal propagation, optimizer, research input or native
solver is executed by these checks.
"""
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch

import neighborhood_method
from test_neighborhood_method import Harness


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RECORDS = {'scope': 'mock lifecycle archival fault injection; no new research evidence'}


class NeighborhoodArchiveFailureTests(unittest.TestCase):
    def setUp(self):
        root = REPO/'.runtime/neighborhood_archive_correctness'
        root.mkdir(parents=True, exist_ok=True)
        self.path = root/('case_'+uuid4().hex)
        self.path.mkdir()

    def run_failure(self, filename, **options):
        folder = self.path/'call'
        h = Harness(**options)
        if options.get('startup_error'):
            def startup_failure(*args, **kwargs):
                error = RuntimeError('MOCK_STARTUP_ERROR')
                error.matlab_cleanup = {'cleanup_wall_seconds': 0,
                                        'cleanup_archive_error': 'MOCK_CLEANUP_ARCHIVE_ERROR'}
                error.matlab_startup_metadata = {'startup_error': 'MOCK_STARTUP_ERROR',
                                                 'startup_archive_error': 'MOCK_STARTUP_ARCHIVE_ERROR'}
                raise error
            h.session_factory = startup_failure
        ordinary_save = neighborhood_method._save
        attempts = []

        def faulty_save(path, value):
            path = Path(path)
            attempts.append(path.name)
            if path.name == filename:
                raise OSError(22, 'INJECTED_ARCHIVE_INVALID_ARGUMENT', str(path)+'.tmp')
            return ordinary_save(path, value)

        with patch.object(neighborhood_method, '_save', side_effect=faulty_save):
            result = h.run(folder)
        self.assertEqual(result['technical_state'], 'FAILED')
        self.assertFalse(result['archive_complete'])
        self.assertEqual(len(result['archive_errors']), 1)
        error = result['archive_errors'][0]
        self.assertEqual(error['exception_type'], 'OSError')
        self.assertEqual(error['errno'], 22)
        self.assertEqual(error['filename'], str(folder/filename)+'.tmp')
        self.assertIn('INJECTED_ARCHIVE_INVALID_ARGUMENT', error['message'])
        self.assertEqual(attempts.count(filename), 1)
        self.assertEqual(bool(h.sessions), not options.get('startup_error', False))
        if h.sessions:
            self.assertTrue(result['session_closed_by_neighborhood'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        RECORDS[filename+'_'+str(sorted(options))] = {
            'result': result, 'archive_attempts': attempts, 'trace': h.trace}
        return result, h, attempts, folder

    def test_first_input_archive_failure_preserves_safe_and_attempts_other_files(self):
        result, h, attempts, folder = self.run_failure('input_config.json')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertEqual(result['technical_state_before_archive'], 'COMPLETED')
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        self.assertNotIn('error', result)
        self.assertEqual(result['archive_errors'][0]['stage'], 'input_config')
        self.assertTrue((folder/'input_instance.json').exists())
        saved = json.loads((folder/'result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['safe_upper_bound_J'], result['safe_upper_bound_J'])
        self.assertEqual(saved['archive_errors'], result['archive_errors'])
        self.assertTrue((folder/'archive_timing.json').exists())

    def test_result_archive_failure_returns_memory_evidence_and_records_timing(self):
        result, h, attempts, folder = self.run_failure('result.json')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        self.assertFalse((folder/'result.json').exists())
        self.assertTrue((folder/'input_config.json').exists())
        self.assertTrue((folder/'input_instance.json').exists())
        saved = json.loads((folder/'archive_timing.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['archive_complete'])
        self.assertEqual(saved['archive_errors'], result['archive_errors'])
        self.assertEqual(result['archive_errors'][0]['stage'], 'result')

    def test_archive_timing_failure_is_explicit_in_return_without_retry(self):
        result, h, attempts, folder = self.run_failure('archive_timing.json')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['archive_errors'][0]['stage'], 'archive_timing')
        self.assertFalse((folder/'archive_timing.json').exists())
        # result.json was formed before the later archival error. It is not
        # rewritten after failure; the return owns the complete technical state.
        self.assertTrue((folder/'result.json').exists())
        self.assertLess(float(result['safe_upper_bound_J']), 10)

    def test_archive_error_does_not_replace_primary_method_exception(self):
        result, h, attempts, folder = self.run_failure('input_config.json', startup_error=True)
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(float(result['safe_upper_bound_J']), 10)
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertEqual(result['error'], 'RuntimeError: MOCK_STARTUP_ERROR')
        self.assertEqual(result['technical_state_before_archive'], 'FAILED')
        self.assertEqual(result['archive_errors'][0]['exception_type'], 'OSError')
        self.assertEqual(result['startup_metadata']['startup_error'], 'MOCK_STARTUP_ERROR')
        self.assertEqual(result['startup_metadata']['startup_archive_error'], 'MOCK_STARTUP_ARCHIVE_ERROR')
        self.assertEqual(result['startup_cleanup']['cleanup_archive_error'], 'MOCK_CLEANUP_ARCHIVE_ERROR')

    def test_budget_completed_safe_survives_expiry_and_archive_failure(self):
        result, h, attempts, folder = self.run_failure('input_config.json', late_aggregate_transfer=True)
        self.assertEqual(result['state'], 'SAFE')
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        self.assertTrue(result['budget_exhausted'])
        self.assertNotEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertLess(result['aggregation']['completed_at_elapsed_s'], 60)
        self.assertGreaterEqual(result['timing']['method_elapsed_s'], 60)
        self.assertTrue(result['strict_improvement_over_initial_certified'])

    def test_old_successful_archival_path_has_no_failure_fields(self):
        result = Harness().run(self.path/'success')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertEqual(result['technical_state'], 'COMPLETED')
        self.assertNotIn('archive_errors', result)
        self.assertNotIn('archive_complete', result)
        self.assertNotIn('technical_state_before_archive', result)
        self.assertNotIn('session_cleanup', result)
        self.assertNotIn('technical_state_before_cleanup', result)
        for filename in ('input_config.json', 'input_instance.json', 'result.json', 'archive_timing.json'):
            self.assertTrue((self.path/'success'/filename).exists())

    def test_nonraising_cleanup_write_failure_preserves_memory_receipt_and_safe(self):
        h = Harness()
        ordinary_factory = h.session_factory

        def factory(*args, **kwargs):
            session = ordinary_factory(*args, **kwargs)
            ordinary_close = session.close
            def close():
                ordinary_close()
                session.cleanup = {'graceful_stop_requested': False, 'returncode': 0,
                    'cleanup_not_available_for_new_evidence': True,
                    'stop_write_error': 'OSError(22, MOCK_STOP_WRITE_ERROR)',
                    'cleanup_archive_error': 'OSError(22, MOCK_CLOSED_WRITE_ERROR)'}
            session.close = close
            return session

        h.session_factory = factory
        result = h.run(self.path/'cleanup')
        self.assertEqual(result['state'], 'SAFE')
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertNotIn('error', result)
        self.assertTrue(result['session_closed_by_neighborhood'])
        self.assertEqual(result['technical_state'], 'FAILED')
        self.assertEqual(result['technical_state_before_cleanup'], 'COMPLETED')
        self.assertEqual(result['session_cleanup'], h.sessions[0].cleanup)
        saved = json.loads((self.path/'cleanup/result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['technical_state'], 'FAILED')
        self.assertEqual(saved['session_cleanup'], result['session_cleanup'])
        self.assertEqual(saved['safe_upper_bound_J'], result['safe_upper_bound_J'])
        RECORDS['nonraising_cleanup_write_failure'] = {'result': result, 'trace': h.trace}

    def run_forced_cleanup(self, *, child_alive=False, primary_error=False):
        h = Harness(raise_after_callback=primary_error)
        ordinary_factory = h.session_factory
        receipt = {'cleanup_status': 'unresolved' if child_alive else 'forced_closed',
            'force_requested': True, 'force_termination_succeeded': True,
            'own_process_tree_kill_returncode': 0, 'returncode': 1,
            'observed_tree_verified_terminated': not child_alive,
            'observed_tree_capture_complete': True, 'observed_tree_identity_count': 2,
            'process_tree_verification': {'capture_complete': True,
                'verified_terminated': not child_alive, 'identities': [
                {'pid': 98765031, 'create_time': 100.0, 'state': 'EXITED'},
                {'pid': 98765032, 'create_time': 101.0,
                 'state': 'RUNNING' if child_alive else 'EXITED'}]}}
        def factory(*args, **kwargs):
            session = ordinary_factory(*args, **kwargs); ordinary_close = session.close
            def close():
                ordinary_close(); session.cleanup = receipt
            session.close = close
            return session
        h.session_factory = factory
        return h.run(self.path/'forced'), receipt

    def test_verified_forced_cleanup_preserves_raw_exit_without_algorithm_failure(self):
        result, receipt = self.run_forced_cleanup()
        self.assertEqual(result['technical_state'], 'COMPLETED')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['session_cleanup'], receipt)
        self.assertEqual(result['session_cleanup']['returncode'], 1)
        self.assertNotIn('technical_state_before_cleanup', result)

    def test_successful_taskkill_with_live_child_remains_technical_failure(self):
        result, receipt = self.run_forced_cleanup(child_alive=True)
        self.assertEqual(result['technical_state'], 'FAILED')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['session_cleanup'], receipt)

    def test_verified_cleanup_never_erases_primary_solver_failure(self):
        result, receipt = self.run_forced_cleanup(primary_error=True)
        self.assertEqual(result['technical_state'], 'FAILED')
        self.assertEqual(result['state'], 'SAFE')
        self.assertNotEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertEqual(result['session_cleanup'], receipt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
