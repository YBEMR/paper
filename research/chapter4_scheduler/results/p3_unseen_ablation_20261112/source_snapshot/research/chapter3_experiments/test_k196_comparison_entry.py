"""Pure manual-route and supervisor checks; no scientific calls or OS workers.

All claims and results are temporary fixtures. Imported production helpers only
inspect stored receipts; timing, thermal and search modules are replaced by fakes.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter3_experiments import k196_comparison_entry as entry
from research.chapter3_method_entry_executor import common, monitor


class Clock:
    def __init__(self, now=100.): self.now = now
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class FixedEntryChecks(unittest.TestCase):
    def setUp(self):
        runtime = entry.ROOT / '.runtime'
        runtime.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='k196_pure_', dir=runtime)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.results = self.root / 'results'
        self.results.mkdir()
        self.plan_path = self.results / 'prep/plan.json'
        self.auth_path = self.results / 'user_approval.json'
        self.output = self.results / 'batch'
        self.clock = Clock()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(entry, 'ROOT', self.root))
        self.stack.enter_context(patch.object(entry, 'RESULTS', self.results))
        self.stack.enter_context(patch.object(entry.time, 'monotonic', self.clock))
        self.stack.enter_context(patch.object(entry.time, 'sleep', self.clock.advance))
        for rel, payload in ((entry.INPUT, b'input fixture'), (entry.CONFIG, b'config fixture'),
                             (entry.ENTRY, b'entry fixture')):
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(payload)
        self.stack.enter_context(patch.object(entry, 'INPUT_SHA', entry.sha(self.root / entry.INPUT)))
        self.stack.enter_context(patch.object(entry, 'CONFIG_SHA', entry.sha(self.root / entry.CONFIG)))
        self.plan = dict(schema='k196-six-manual-v1', execution_authorized=False,
            jobs=deepcopy(entry.JOBS), scope=deepcopy(entry.SCOPE),
            input_file=entry.INPUT, input_sha256=entry.INPUT_SHA,
            config_file=entry.CONFIG, config_sha256=entry.CONFIG_SHA,
            source_sha256={entry.ENTRY: entry.sha(self.root / entry.ENTRY)},
            science_source_count=197, method_process_watchdog_seconds=405,
            historical_candidate_or_cache_input=False, reference_read_by_search=False,
            python_executable=str(Path(sys.executable).resolve()), python_version=sys.version,
            dependencies={})
        entry.save(self.plan_path, self.plan)
        self.auth = dict(schema='k196-six-user-approval-v1', approved_by_user=True,
            approval_source='USER_CURRENT_CONVERSATION', human_authorization_text='TEST_ONLY manual fixture',
            subject_commit='a'*40, plan_sha256=entry.sha(self.plan_path), scope=deepcopy(entry.SCOPE),
            output_directory=str(self.output), not_an_external_agent_loop_review=True)
        entry.save(self.auth_path, self.auth)

    def replace(self, path, value):
        Path(path).write_text(json.dumps(value), encoding='utf-8')

    def fake_git(self, *args):
        self.assertEqual(args[0], 'show')
        subject, rel = args[1].split(':', 1)
        self.assertEqual(subject, 'a'*40)
        return (self.root / rel).read_bytes()

    def test_manual_approval_exact_binding_and_subject(self):
        with patch.object(entry, 'git_bytes', side_effect=self.fake_git) as git:
            self.assertEqual(entry.authorize(self.plan_path, self.auth_path, self.output), self.plan)
            self.assertEqual(git.call_count, 2)
        for field, wrong in [('approved_by_user', False), ('plan_sha256', '0'*64),
                             ('subject_commit', 'HEAD'), ('approval_source', 'INTERNAL_AGENT')]:
            with self.subTest(field=field):
                changed = dict(self.auth, **{field: wrong})
                self.replace(self.auth_path, changed)
                with self.assertRaises(ValueError):
                    entry.authorize(self.plan_path, self.auth_path, self.output, verify_subject=False)

    def test_plan_input_scope_and_source_drift_rejected(self):
        for field, value in [('jobs', entry.JOBS[:-1]), ('reference_read_by_search', True),
                             ('scope', dict(entry.SCOPE, method_seconds_each=301))]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                entry.validate_plan(dict(self.plan, **{field: value}))
        (self.root / entry.ENTRY).write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError, 'SOURCE_DRIFT'):
            entry.authorize(self.plan_path, self.auth_path, self.output, verify_subject=False)

    def batch_patches(self, slot):
        stack = ExitStack()
        stack.enter_context(patch.object(entry, 'authorize', return_value=self.plan))
        stack.enter_context(patch.object(entry, 'verify_sources', side_effect=lambda _: self.clock.advance(3)))
        stack.enter_context(patch.object(monitor, 'default_host_probe', side_effect=lambda _: self.probe()))
        stack.enter_context(patch.object(monitor, 'host_gate', return_value={'passed': True}))
        stack.enter_context(patch.object(entry, 'run_slot', side_effect=slot))
        return stack

    def probe(self):
        self.clock.advance(2)
        return {'state': 'FIXTURE_ONLY'}

    def test_six_no_solution_calls_and_single_claim(self):
        slots = []
        def slot(*args):
            slots.append(args[4]['id'])
            self.assertEqual(args[5], 'method')
            self.assertEqual(self.clock() - args[6], 5)  # preparation already billed
            return {'status': 'NORMAL_COMPLETION', 'worker': {'safe': {'preserved': False}}}
        with self.batch_patches(slot):
            batch = entry.run(self.plan_path, self.auth_path, self.output)
            self.assertEqual(batch['state'], 'COMPLETED')
            self.assertEqual(slots, [j['id'] for j in entry.JOBS])
            self.assertEqual((batch['method_attempts'], batch['post_attempts']), (6, 0))
            with self.assertRaises(FileExistsError):
                entry.run(self.plan_path, self.auth_path, self.results / 'different_output')
            self.assertEqual(len(slots), 6)

    def test_technical_failure_stops_without_retry(self):
        with self.batch_patches(lambda *a: {'status': 'TECHNICAL_FAILURE'}):
            batch = entry.run(self.plan_path, self.auth_path, self.output)
        self.assertEqual(batch['state'], 'STOPPED')
        self.assertEqual(batch['method_attempts'], 1)
        self.assertEqual(batch['not_run'], ['sa101', 'sa102', 'sa103', 'sa104', 'sa105'])

    def test_one_post_each_safe(self):
        sequence = []
        def slot(*args):
            sequence.append((args[4]['id'], args[5]))
            self.clock.advance(10)
            return {'status': 'NORMAL_COMPLETION', 'worker': {'safe': {'preserved': True}}}
        with self.batch_patches(slot):
            batch = entry.run(self.plan_path, self.auth_path, self.output)
        self.assertEqual((batch['method_attempts'], batch['post_attempts']), (6, 6))
        self.assertEqual(sequence, [(j['id'], mode) for j in entry.JOBS for mode in ('method', 'post')])

    def test_post_safety_failure_stops_batch(self):
        def slot(*args):
            return ({'status': 'NORMAL_COMPLETION', 'worker': {'safe': {'preserved': True}}}
                    if args[5] == 'method' else {'status': 'SAFETY_FAILURE'})
        with self.batch_patches(slot):
            batch = entry.run(self.plan_path, self.auth_path, self.output)
        self.assertEqual(batch['state'], 'STOPPED')
        self.assertEqual((batch['method_attempts'], batch['post_attempts']), (1, 1))

    def test_nested_numerical_fault_distinct_from_normal_unresolved(self):
        self.assertIsNone(entry.receipt_failure({'state': 'UNRESOLVED', 'reason': 'wall_time_limit'}))
        self.assertTrue(entry.receipt_failure({'evaluations': [{'evaluation': {
            'state': 'UNRESOLVED', 'reason': 'NUMERICAL_ERROR'}}]}))

    def receipt(self, formed=299.9):
        instance = {'window_ms': '400', 'scenarios': [{'id': 's', 'weight': '1'}]}
        candidate = {'scenes': {'s': []}}
        ev = {'completed_at_elapsed_s': formed, 'state': 'SAFE', 'rankable_energy': True,
              'evidence_identity': {'input_sha256': common.canonical(instance),
                                    'candidate_sha256': common.canonical(candidate)},
              'scenes': {'s': {'state': 'SAFE', 'complete': True,
                               'covered_until_s': '2/5', 'energy_J': ['1', '1']}},
              'weighted_energy_J': ['1', '1'], 'safe_upper_bound_J': '1',
              'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'}}
        return instance, {'safe_candidate': candidate, 'evaluation': ev, 'safe_upper_bound_J': '1'}

    def test_complete_safe_strict_cutoff_and_full_window(self):
        instance, raw = self.receipt()
        self.assertTrue(common.inspect_safe_receipt(instance, raw, 300)['preserved'])
        raw['evaluation']['completed_at_elapsed_s'] = 300
        self.assertFalse(common.inspect_safe_receipt(instance, raw, 300)['preserved'])
        raw['evaluation']['completed_at_elapsed_s'] = 59.9
        self.assertTrue(common.inspect_safe_receipt(instance, raw, 60)['preserved'])
        raw['evaluation']['completed_at_elapsed_s'] = 60
        self.assertFalse(common.inspect_safe_receipt(instance, raw, 60)['preserved'])
        raw['evaluation']['completed_at_elapsed_s'] = 10
        raw['evaluation']['scenes']['s']['covered_until_s'] = '1/5'
        self.assertFalse(common.inspect_safe_receipt(instance, raw, 60)['preserved'])

    def fake_slot_runtime(self, *, exit_code=0, alive=False, cleanup=True):
        clock = self.clock
        class Provider:
            def describe(self, pid): return {'state': 'ACTIVE', 'pid': pid, 'create_time': 1.0}
        class Process:
            pid = 99999
            returncode = exit_code
            running = alive
            def poll(self): return None if self.running and clock() < 161 else self.returncode
            def wait(self, timeout): return self.returncode
            def kill(self): self.running = False
        class Monitor:
            def __init__(self, pid): self.root_identity = (pid, 1.); self.samples = []
            def sample(self): pass
            def terminate_owned(self, force): return {'fixture_signal': True}
            def cleanup_verified(self): return cleanup
            def summary(self): return {'cleanup_verified_observed_tree': cleanup}
        stack = ExitStack()
        stack.enter_context(patch.object(monitor, 'PsutilProvider', Provider))
        stack.enter_context(patch.object(monitor, 'ProcessMonitor', Monitor))
        stack.enter_context(patch.object(entry.subprocess, 'Popen', return_value=Process()))
        return stack

    def test_post_nonzero_exit_is_technical_failure(self):
        entry.save(self.output/'slots/heft__method/worker/raw_result.json', {'fixture': True})
        with self.fake_slot_runtime(exit_code=7):
            slot = entry.run_slot(self.plan_path, self.auth_path, self.plan, self.output,
                                  entry.JOBS[0], 'post', 100, 580, 2980)
        self.assertEqual(slot['status'], 'TECHNICAL_FAILURE')

    def test_post_watchdog_does_not_extend_sixty_seconds(self):
        entry.save(self.output/'slots/heft__method/worker/raw_result.json', {'fixture': True})
        with self.fake_slot_runtime(alive=True):
            slot = entry.run_slot(self.plan_path, self.auth_path, self.plan, self.output,
                                  entry.JOBS[0], 'post', 100, 580, 2980)
        self.assertEqual(slot['watchdog'], 160)
        self.assertTrue(slot['watchdog_fired'])
        self.assertEqual(slot['status'], 'POST_TIME_LIMIT_UNRESOLVED')

    def test_cleanup_failure_overrides_normal_exit(self):
        with self.fake_slot_runtime(cleanup=False):
            slot = entry.run_slot(self.plan_path, self.auth_path, self.plan, self.output,
                                  entry.JOBS[0], 'method', 100, 580, 2980)
        self.assertEqual(slot['status'], 'CLEANUP_FAILURE')

    def test_ticket_parent_identity_and_one_worker_claim(self):
        slot = self.output/'slots/heft__method'
        ticket_path = slot/'ticket.json'
        ticket = {'output': str(self.output), 'slot_id': 'heft__method', 'token': 'fixture',
                  'job': entry.JOBS[0], 'mode': 'method', 'origin': 90., 'scientific_deadline': 390.,
                  'plan': str(self.plan_path), 'approval': str(self.auth_path),
                  'plan_sha256': entry.sha(self.plan_path), 'parent_identity': [os.getppid(), 1.]}
        entry.save(ticket_path, ticket)
        entry.save(slot/'slot_claim.json', {'ticket_sha256': entry.sha(ticket_path)})
        entry.save(slot/'go.json', {'ticket_sha256': entry.sha(ticket_path), 'worker_identity': [os.getpid(), 1.]})
        entry.save(self.results/'k196_comparison_claims'/(entry.sha(self.plan_path)+'.json'),
                   {'output': str(self.output), 'approval_sha256': entry.sha(self.auth_path)})
        class Provider:
            def describe(self, pid): return {'state': 'ACTIVE', 'pid': pid, 'create_time': 1.}
        class WrongParent:
            def describe(self, pid): return {'state': 'ACTIVE', 'pid': pid, 'create_time': 2.}
        with patch.object(entry, 'authorize', return_value=self.plan), patch.object(monitor, 'PsutilProvider', WrongParent):
            with self.assertRaisesRegex(ValueError, 'PARENT_IDENTITY'):
                entry.validate_ticket(ticket_path, 'fixture')
        with patch.object(entry, 'authorize', return_value=self.plan), patch.object(monitor, 'PsutilProvider', Provider):
            with self.assertRaisesRegex(ValueError, 'TICKET_SCOPE'):
                entry.validate_ticket(ticket_path, 'wrong_token')
            entry.validate_ticket(ticket_path, 'fixture')
            with self.assertRaises(FileExistsError):
                entry.validate_ticket(ticket_path, 'fixture')

    def test_worker_uses_parent_root_before_import_and_search(self):
        ticket_path = self.output/'slots/heft__method/ticket.json'
        ticket_path.parent.mkdir(parents=True)
        ticket = {'origin': 90., 'scientific_deadline': 390., 'mode': 'method',
                  'job': entry.JOBS[0], 'plan_sha256': entry.sha(self.plan_path)}
        captured = {}
        class Exhausted(Exception): pass
        class Budget:
            def __init__(self, seconds): self.seconds = seconds; self.start = 100; self.deadline = 400
            @property
            def elapsed(self): return self_clock()-self.start
            def check(self):
                if self_clock() >= self.deadline: raise Exhausted()
        self_clock = self.clock
        def fake_search(loader, folder, **kwargs):
            captured.update(kwargs)
            return {'state': 'UNRESOLVED', 'reason': 'DECLARED_SEARCH_COMPLETED'}
        modules = {}
        for name, attrs in [('timing', {'MethodBudget': Budget}),
                            ('thermal', {'Exhausted': Exhausted, 'evaluate_candidate': lambda *a, **k: {}}),
                            ('heuristic_runner', {'execute_heuristic': fake_search}),
                            ('research.chapter3_experiments.small_whole_execution.domain_contract',
                             {'validate_candidate': lambda *a: None})]:
            module = ModuleType(name)
            module.__dict__.update(attrs); modules[name] = module
        original_read = entry.read
        def fake_read(path):
            if Path(path) == self.root/entry.INPUT: return {'scenarios': []}
            if Path(path) == self.root/entry.CONFIG: return {}
            return original_read(path)
        with patch.dict(sys.modules, modules), patch.object(entry, 'validate_ticket', return_value=(ticket, self.plan)), \
             patch.object(entry, 'read', side_effect=fake_read), patch.object(sys, 'path', list(sys.path)):
            result = entry.worker(ticket_path, 'fixture')
        self.assertEqual(result['status'], 'NORMAL_COMPLETION')
        self.assertEqual(captured['budget'].start, 90.)
        self.assertEqual(captured['budget'].deadline, 390.)
        self.assertEqual(captured['budget'].elapsed, 10.)
        self.assertEqual((captured['seconds'], captured['method'], captured['seed']), (300, 'heft', None))

    def test_post_ticket_rejects_changed_method_receipt(self):
        slot = self.output/'slots/heft__post'
        source = self.output/'slots/heft__method/worker/raw_result.json'
        entry.save(source, {'fixture': 'original'})
        ticket = {'output': str(self.output), 'slot_id': 'heft__post', 'token': 'fixture',
                  'job': entry.JOBS[0], 'mode': 'post', 'origin': 90., 'scientific_deadline': 150.,
                  'plan': str(self.plan_path), 'approval': str(self.auth_path),
                  'plan_sha256': entry.sha(self.plan_path), 'parent_identity': [os.getppid(), 1.],
                  'method_receipt_sha256': entry.sha(source)}
        entry.save(slot/'ticket.json', ticket)
        entry.save(slot/'slot_claim.json', {'ticket_sha256': entry.sha(slot/'ticket.json')})
        entry.save(self.results/'k196_comparison_claims'/(entry.sha(self.plan_path)+'.json'),
                   {'output': str(self.output), 'approval_sha256': entry.sha(self.auth_path)})
        self.replace(source, {'fixture': 'modified'})
        with patch.object(entry, 'authorize', return_value=self.plan):
            with self.assertRaisesRegex(ValueError, 'POST_SOURCE_DRIFT'):
                entry.validate_ticket(slot/'ticket.json', 'fixture')


if __name__ == '__main__':
    unittest.main()
