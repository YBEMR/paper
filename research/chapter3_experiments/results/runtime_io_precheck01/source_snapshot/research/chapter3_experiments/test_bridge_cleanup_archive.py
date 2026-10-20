"""Fake-process failures in startup cleanup/publication; never launch MATLAB.

Only unique ignored workspace directories are written. Native subprocess
creation and taskkill are always mocked; synthetic PIDs are never acted on.
"""
from contextlib import ExitStack
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import matlab_bridge as bridge


HERE = Path(__file__).resolve().parent
RECORDS = {'scope': 'fake process and filesystem-failure injection only',
           'native_calls': 0, 'research_calls': 0, 'checks': []}


class NoSuchProcess(Exception):
    pass


class AccessDenied(Exception):
    pass


class IdentityProcess:
    def __init__(self, pid, created, *, running=True, children=None, denied=False):
        self.pid, self.created, self.running = pid, created, running
        self.child_processes, self.denied = children or [], denied

    def create_time(self):
        return self.created

    def is_running(self):
        return self.running

    def children(self, recursive):
        if self.denied:
            raise AccessDenied('MOCK_CHILD_ENUMERATION_DENIED')
        return list(self.child_processes)


def fake_psutil(registry):
    def process(pid):
        value = registry.get(pid)
        if value is None:
            raise NoSuchProcess(pid)
        if isinstance(value, Exception):
            raise value
        return value
    return SimpleNamespace(__version__='5.9.mock', Process=process)


class FakeProc:
    pid = 98765031  # synthetic identifier; subprocess.run is patched below

    def __init__(self, *, running=True, graceful=False, exitcode=0):
        self.running, self.graceful = running, graceful
        self.exitcode = exitcode
        self.waits, self.kills = [], 0

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.graceful:
            self.running = False
        if self.running:
            raise bridge.subprocess.TimeoutExpired('FAKE_MATLAB', timeout)
        return self.exitcode

    def poll(self):
        return None if self.running else self.exitcode

    def kill(self):
        self.kills += 1
        self.running = False


class CleanupArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = HERE.parents[1] / '.runtime' / ('bridge_cleanup_' + uuid4().hex)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.spawn = self.stack.enter_context(patch.object(bridge.subprocess, 'Popen',
            side_effect=AssertionError('native process forbidden')))
        self.run = self.stack.enter_context(patch.object(bridge.subprocess, 'run',
            side_effect=AssertionError('native taskkill forbidden')))
        # Existing cleanup boundary tests do not inspect any real process ID.
        self.real_capture = bridge._capture_owned_process_tree
        self.real_verify = bridge._verify_owned_process_tree
        self.owned = {}
        def capture(proc, previous=None, *, phase):
            self.owned[proc.pid] = proc
            root = {'pid': proc.pid, 'create_time': 1000.0}
            return {'root_pid': proc.pid, 'root_identity': root,
                'identities': [root], 'capture_complete': True, 'capture_errors': [],
                'root_identity_verified': proc.poll() is None,
                'observations': [{'phase': phase, 'state': 'MOCK_OWNED_TREE'}]}
        def verify(tree):
            proc = self.owned.get((tree or {}).get('root_pid'))
            identities = [dict(item, state='EXITED' if proc and proc.poll() is not None else 'RUNNING')
                          for item in (tree or {}).get('identities', [])]
            return {'capture_complete': bool(tree and tree.get('capture_complete')),
                'identities': identities, 'verified_terminated': bool(identities and
                    all(item['state'] == 'EXITED' for item in identities))}
        self.stack.enter_context(patch.object(bridge, '_capture_owned_process_tree', side_effect=capture))
        self.stack.enter_context(patch.object(bridge, '_verify_owned_process_tree', side_effect=verify))

    def session(self, proc):
        session = bridge.MatlabSession.__new__(bridge.MatlabSession)
        session.clock = lambda: 5.0
        session.started = 0.0
        session.workdir = self.folder
        session.closed = False
        session.proc = proc
        session.log = io.BytesIO()
        return session

    def stop_failure(self):
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == 'stop':
                raise OSError(22, 'EXPLICIT_MOCK_STOP_WRITE_FAILURE')
            return original(path, *args, **kwargs)
        return patch.object(Path, 'write_text', write)

    def terminate_tree(self, proc):
        def terminate(args, **kwargs):
            self.assertEqual(args, ['taskkill', '/PID', str(proc.pid), '/T', '/F'])
            proc.running = False
            return SimpleNamespace(returncode=0)
        return terminate

    def test_stop_write_failure_still_cleans_own_fake_process_and_log(self):
        proc = FakeProc(); session = self.session(proc)
        with self.stop_failure(), patch.object(bridge.os, 'name', 'nt'), \
                patch.object(bridge.subprocess, 'run', side_effect=self.terminate_tree(proc)) as kill:
            session.close()
            session.close()  # idempotence must not issue another cleanup command
        self.assertTrue(session.closed)
        self.assertTrue(session.log.closed)
        self.assertFalse(proc.running)
        self.assertEqual(proc.waits, [20, 10])
        self.assertEqual(kill.call_count, 1)
        self.assertFalse(session.cleanup['graceful_stop_requested'])
        self.assertIn('MOCK_STOP_WRITE_FAILURE', session.cleanup['stop_write_error'])
        self.assertEqual(session.cleanup['returncode'], 0)
        saved = json.loads((self.folder / 'closed.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, session.cleanup)
        self.assertNotIn('cleanup_pending_pid', saved)
        RECORDS['checks'].append({'name': 'stop_failure_does_not_skip_owned_process_cleanup', 'passed': True})

    def test_closed_archive_failure_keeps_memory_cleanup_without_raising(self):
        proc = FakeProc(graceful=True); session = self.session(proc)
        original = bridge._json
        def archive(path, value):
            if path.name == 'closed.json':
                raise OSError(22, 'EXPLICIT_MOCK_CLOSED_ARCHIVE_FAILURE')
            return original(path, value)
        with patch.object(bridge, '_json', side_effect=archive):
            session.close()
        self.assertTrue(session.closed)
        self.assertTrue(session.log.closed)
        self.assertEqual(session.cleanup['returncode'], 0)
        self.assertIn('CLOSED_ARCHIVE_FAILURE', session.cleanup['cleanup_archive_error'])
        self.assertFalse((self.folder / 'closed.json').exists())
        RECORDS['checks'].append({'name': 'closed_archive_failure_retains_memory_receipt', 'passed': True})

    def test_startup_original_read_error_survives_stop_and_both_archive_failures(self):
        proc = FakeProc(); original_error = RuntimeError('EXPLICIT_ORIGINAL_STARTUP_READ_ERROR')
        original_json = bridge._json
        def archive(path, value):
            if path.name == 'closed.json':
                raise OSError(22, 'EXPLICIT_MOCK_CLOSED_ARCHIVE_FAILURE')
            if path.name == 'session.json' and value.get('startup_outcome') == 'FAILED_OR_DEADLINE':
                raise OSError(22, 'EXPLICIT_MOCK_FAILED_STARTUP_ARCHIVE')
            return original_json(path, value)
        with patch.object(bridge.subprocess, 'Popen', return_value=proc) as spawn, \
                patch.object(bridge.subprocess, 'run', side_effect=self.terminate_tree(proc)), \
                patch.object(bridge, '_read_json_until', side_effect=original_error) as reader, \
                patch.object(bridge, '_json', side_effect=archive), self.stop_failure():
            with self.assertRaises(RuntimeError) as raised:
                bridge.MatlabSession(self.folder / 'failed_read', total_budget_s=60)
        self.assertIs(raised.exception, original_error)
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(reader.call_count, 1)
        self.assertFalse(proc.running)
        self.assertEqual(proc.waits, [20, 10])
        cleanup = original_error.matlab_cleanup
        self.assertIn('STOP_WRITE_FAILURE', cleanup['stop_write_error'])
        self.assertIn('CLOSED_ARCHIVE_FAILURE', cleanup['cleanup_archive_error'])
        self.assertEqual(cleanup['returncode'], 0)
        self.assertIn('ORIGINAL_STARTUP_READ_ERROR', original_error.matlab_startup_metadata['startup_error'])
        self.assertIn('FAILED_STARTUP_ARCHIVE', original_error.matlab_startup_metadata['startup_archive_error'])
        self.assertTrue(spawn.call_args.kwargs['stdout'].closed)
        self.assertEqual(original_error.matlab_workdir, str((self.folder / 'failed_read').resolve()))
        RECORDS['checks'].append({'name': 'original_startup_exception_not_masked_by_cleanup_files', 'passed': True})

    def test_post_launch_session_archive_error_is_retained_as_primary_failure(self):
        proc = FakeProc(graceful=True)
        original_error = OSError(22, 'EXPLICIT_ORIGINAL_PID_SESSION_ARCHIVE_ERROR')
        original_json = bridge._json
        def archive(path, value):
            if path.name == 'closed.json':
                raise OSError(22, 'EXPLICIT_SECONDARY_CLOSED_ARCHIVE_ERROR')
            if path.name == 'session.json' and 'pid' in value:
                if value.get('startup_outcome') == 'FAILED_OR_DEADLINE':
                    raise OSError(22, 'EXPLICIT_SECONDARY_FAILED_STARTUP_ARCHIVE_ERROR')
                raise original_error
            return original_json(path, value)
        with patch.object(bridge.subprocess, 'Popen', return_value=proc) as spawn, \
                patch.object(bridge, '_read_json_until') as reader, \
                patch.object(bridge, '_json', side_effect=archive):
            with self.assertRaises(OSError) as raised:
                bridge.MatlabSession(self.folder / 'failed_pid_archive', total_budget_s=60)
        self.assertIs(raised.exception, original_error)
        self.assertEqual(spawn.call_count, 1)
        reader.assert_not_called()
        self.assertFalse(proc.running)
        self.assertEqual(proc.waits, [20])
        self.assertEqual(original_error.matlab_cleanup['returncode'], 0)
        self.assertIn('SECONDARY_CLOSED_ARCHIVE', original_error.matlab_cleanup['cleanup_archive_error'])
        self.assertIn('ORIGINAL_PID_SESSION_ARCHIVE', original_error.matlab_startup_metadata['startup_error'])
        RECORDS['checks'].append({'name': 'pid_publication_error_keeps_primary_cause', 'passed': True})

    def test_taskkill_error_falls_back_only_to_own_proc_kill(self):
        proc = FakeProc(); session = self.session(proc)
        with self.stop_failure(), patch.object(bridge.os, 'name', 'nt'), \
                patch.object(bridge.subprocess, 'run', side_effect=OSError('MOCK_TASKKILL_FAILURE')):
            session.close()
        self.assertEqual(proc.kills, 1)
        self.assertEqual(proc.waits, [20, 10])
        self.assertFalse(proc.running)
        self.assertEqual(session.cleanup['returncode'], 0)
        self.assertIn('MOCK_TASKKILL_FAILURE', session.cleanup['process_kill_error'])
        self.assertTrue(session.log.closed)

    def test_normal_fake_startup_and_close_preserve_ready_metadata_and_cut_setting(self):
        proc = FakeProc(graceful=True)
        with patch.object(bridge.subprocess, 'Popen', return_value=proc) as spawn, \
                patch.object(bridge, '_read_json_until', return_value=(
                    {'status': 'READY', 'release': '2023b'}, {'attempts': 1})):
            session = bridge.MatlabSession(self.folder / 'normal', total_budget_s=60,
                                           cut_max_iterations=10)
            self.assertEqual(session.metadata['startup_outcome'], 'READY')
            self.assertEqual(session.metadata['cut_max_iterations_declared'], 10)
            self.assertEqual(session.counter, 0)
            session.close()
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(session.cleanup['returncode'], 0)
        self.assertTrue(session.cleanup['graceful_stop_requested'])
        self.assertNotIn('cleanup_archive_error', session.cleanup)
        self.assertNotIn('stop_write_error', session.cleanup)
        self.assertTrue(session.log.closed)

    def tree_case(self, *, child_alive=False, denied=False, parent_reused=False):
        proc = FakeProc(exitcode=1)
        child = IdentityProcess(proc.pid + 1, 1001.0)
        root = IdentityProcess(proc.pid, 1000.0, children=[child], denied=denied)
        registry = {root.pid: root, child.pid: child}
        module = fake_psutil(registry)
        session = self.session(proc)
        with patch.dict(sys.modules, {'psutil': module}):
            session.process_tree = self.real_capture(proc, phase='ready')
        self.assertEqual(len(session.process_tree['identities']), 1 if denied else 2)
        if parent_reused:
            registry[root.pid] = IdentityProcess(root.pid, 9999.0)
        def terminate(args, **kwargs):
            self.assertEqual(args, ['taskkill', '/PID', str(proc.pid), '/T', '/F'])
            proc.running = root.running = False
            child.running = child_alive
            return SimpleNamespace(returncode=0)
        with patch.dict(sys.modules, {'psutil': module}), \
                patch.object(bridge, '_capture_owned_process_tree', side_effect=self.real_capture), \
                patch.object(bridge, '_verify_owned_process_tree', side_effect=self.real_verify), \
                patch.object(bridge.os, 'name', 'nt'), \
                patch.object(bridge.subprocess, 'run', side_effect=terminate) as killed:
            session.close()
        return session, proc, root, child, registry, killed

    def test_forced_exit_one_with_both_captured_identities_exited_is_complete(self):
        session, proc, _, _, _, killed = self.tree_case()
        self.assertEqual(killed.call_count, 1)
        self.assertEqual(session.cleanup['returncode'], 1)
        self.assertEqual(session.cleanup['cleanup_status'], 'forced_closed')
        self.assertTrue(session.cleanup['force_requested'])
        self.assertTrue(session.cleanup['force_termination_succeeded'])
        self.assertEqual(session.cleanup['observed_tree_identity_count'], 2)
        self.assertTrue(session.cleanup['observed_tree_verified_terminated'])
        self.assertTrue(bridge.cleanup_is_complete(session.cleanup))
        self.assertEqual(proc.waits, [20, 10])

    def test_taskkill_zero_and_parent_exit_do_not_hide_live_child(self):
        session, _, _, child, _, _ = self.tree_case(child_alive=True)
        self.assertTrue(child.running)
        self.assertEqual(session.cleanup['own_process_tree_kill_returncode'], 0)
        self.assertEqual(session.cleanup['returncode'], 1)
        self.assertEqual(session.cleanup['cleanup_status'], 'unresolved')
        self.assertFalse(session.cleanup['observed_tree_verified_terminated'])
        self.assertFalse(bridge.cleanup_is_complete(session.cleanup))

    def test_enumeration_denied_remains_unresolved_even_after_parent_exits(self):
        session, _, _, _, _, _ = self.tree_case(denied=True)
        self.assertFalse(session.cleanup['observed_tree_capture_complete'])
        self.assertEqual(session.cleanup['cleanup_status'], 'unresolved')
        self.assertFalse(bridge.cleanup_is_complete(session.cleanup))

    def test_reused_parent_pid_is_not_signalled(self):
        session, proc, _, _, _, killed = self.tree_case(parent_reused=True)
        killed.assert_not_called()
        self.assertEqual(proc.kills, 0)
        self.assertEqual(session.cleanup['cleanup_status'], 'unresolved')
        self.assertIn('force_identity_error', session.cleanup)
        self.assertFalse(bridge.cleanup_is_complete(session.cleanup))

    def test_verification_treats_reused_child_as_original_exit_without_signalling(self):
        root = {'pid': 100, 'create_time': 1000.0}
        child = {'pid': 101, 'create_time': 1001.0}
        tree = {'root_identity': root, 'identities': [root, child], 'capture_complete': True}
        with patch.dict(sys.modules, {'psutil': fake_psutil({101: IdentityProcess(101, 9999.0)})}):
            verified = self.real_verify(tree)
        self.assertTrue(verified['verified_terminated'])
        self.assertEqual(verified['identities'][1]['state'], 'PID_REUSED_ORIGINAL_EXITED')

    def test_ready_capture_is_extended_before_force_and_checks_new_descendant(self):
        proc = FakeProc()
        child = IdentityProcess(proc.pid + 1, 1001.0)
        root = IdentityProcess(proc.pid, 1000.0, children=[child])
        registry = {root.pid: root, child.pid: child}
        with patch.dict(sys.modules, {'psutil': fake_psutil(registry)}):
            first = self.real_capture(proc, phase='ready')
            later = IdentityProcess(proc.pid + 2, 1002.0)
            root.child_processes.append(later); registry[later.pid] = later
            second = self.real_capture(proc, first, phase='before_force')
        self.assertEqual(len(first['identities']), 2)
        self.assertEqual(len(second['identities']), 3)
        self.assertEqual([item['phase'] for item in second['observations']], ['ready', 'before_force'])

    def test_cleanup_helper_rejects_status_only_and_malformed_receipts(self):
        session, _, _, _, _, _ = self.tree_case()
        valid = session.cleanup
        self.assertTrue(bridge.cleanup_is_complete(valid))
        for replacement in (None, [], 'bad', {'identities': None}, {'identities': ['bad']}):
            malformed = deepcopy(valid); malformed['process_tree_verification'] = replacement
            self.assertFalse(bridge.cleanup_is_complete(malformed))
        for key in ('force_termination_succeeded', 'observed_tree_capture_complete',
                    'observed_tree_verified_terminated'):
            malformed = deepcopy(valid); malformed[key] = False
            self.assertFalse(bridge.cleanup_is_complete(malformed))
        self.assertFalse(bridge.cleanup_is_complete({'cleanup_status': 'forced_closed', 'returncode': 1}))
        self.assertTrue(bridge.cleanup_is_complete({'returncode': 0}))
        self.assertFalse(bridge.cleanup_is_complete({'returncode': 1, 'own_process_tree_kill_returncode': 0}))
        self.assertFalse(bridge.cleanup_is_complete({'returncode': 0, 'cleanup_error': 'failed'}))


if __name__ == '__main__':
    unittest.main()
