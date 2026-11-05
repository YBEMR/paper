"""Small offline checks. Importing or testing never starts the scientific worker."""
import ast
from copy import deepcopy
from contextlib import contextmanager
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import live_variant as diagnostic
import run_logged


class DiagnosticTests(unittest.TestCase):
    def test_original_forced_close_keeps_explicit_40_second_limit(self):
        for elapsed, expected in ((20.5,'COMPLETED'),(40.0,'COMPLETED'),(40.001,'CLEANUP_FAILURE')):
            with self.subTest(elapsed=elapsed), tempfile.TemporaryDirectory(dir=diagnostic.HERE,prefix='mock_close_') as temporary:
                root=Path(temporary).resolve();output=root/'output';manifest_path=root/'manifest.json'
                diagnostic.save(manifest_path,{})
                manifest=dict(output=str(output),claim=str(root/'claim.json'))
                entry=SimpleNamespace(base=SimpleNamespace(ROOT=root,verify_sources=Mock()))
                process=SimpleNamespace(pid=42,returncode=0,poll=lambda:0,wait=Mock(),kill=Mock())
                monitor=SimpleNamespace(root_identity=(42,1000),samples=[],cleanup_verified=Mock(return_value=True),
                    register_identities=Mock(return_value=[True]),terminate_owned=Mock(),sample=Mock(),
                    summary=Mock(return_value={'cleanup_verified_observed_tree':True}))
                module=SimpleNamespace(ProcessMonitor=Mock(return_value=monitor),
                    PsutilProvider=lambda:SimpleNamespace(describe=lambda pid:dict(pid=pid,create_time=900,state='ACTIVE')),
                    default_host_probe=lambda root:{},host_gate=lambda probe:{'passed':True})
                def spawn(*args,**kwargs):
                    session=output/'worker/method/matlab';session.mkdir(parents=True)
                    diagnostic.save(session/'closed.json',dict(status='forced_closed',cleanup_wall_seconds=elapsed,
                        process_tree_verification=dict(identities=[{'pid':51,'create_time':1000}])))
                    diagnostic.save(output/'worker/worker_result.json',dict(manifest_sha256=diagnostic.sha(manifest_path),
                        ticket_sha256=diagnostic.sha(output/'ticket.json')))
                    return process
                with patch.object(diagnostic,'HERE',root), \
                     patch.object(diagnostic,'verify_manifest',return_value=(manifest,entry,{})), \
                     patch.object(diagnostic.subprocess,'Popen',side_effect=spawn), \
                     patch.object(diagnostic,'observe'), \
                     patch.dict(sys.modules,{'research.chapter3_method_entry_executor.monitor':module,
                        'matlab_bridge':SimpleNamespace(cleanup_is_complete=lambda closed:True)}):
                    result=diagnostic.run(SimpleNamespace(manifest=str(manifest_path)))
                self.assertEqual(result['state'],expected)
                receipt=result['native_cleanup_receipts'][0]
                self.assertEqual(receipt['raw']['status'],'forced_closed')
                self.assertEqual(receipt['within_40_seconds'],elapsed<=40)
                monitor.terminate_owned.assert_not_called()

    def test_worker_hook_exception_keeps_context_and_no_second_science_call(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.HERE, prefix='mock_worker_') as temporary:
            root=Path(temporary).resolve(); output=root/'output'; output.mkdir()
            for name in ('manifest.json','input.json','config.json'):
                diagnostic.save(root/name,{})
            manifest_path=root/'manifest.json'; claim_path=root/'claim.json'
            claim=dict(manifest_sha256=diagnostic.sha(manifest_path),output=str(output),
                       scope=diagnostic.SCOPE,token='offline-token')
            diagnostic.save(claim_path,claim)
            ticket=dict(output=str(output),manifest=str(manifest_path),manifest_sha256=diagnostic.sha(manifest_path),
                claim_sha256=diagnostic.sha(claim_path),token='offline-token',origin=99.0,scientific_deadline=699.0,
                parent_identity=[diagnostic.os.getppid(),10.0],
                job=dict(id='whole_milp',method='whole_milp',seed=None,variant=diagnostic.SCOPE['method']))
            ticket_path=output/'ticket.json';diagnostic.save(ticket_path,ticket)
            diagnostic.save(output/'go.json',dict(ticket_sha256=diagnostic.sha(ticket_path),
                worker_identity=[diagnostic.os.getpid(),10.0]))
            manifest=dict(output=str(output),claim=str(claim_path))
            native=Mock(side_effect=RuntimeError('offline scientific-call failure'))
            entry=SimpleNamespace(base=SimpleNamespace(ROOT=root,INPUT='input.json',CONFIG='config.json',run_whole=native))
            calls=[]
            @contextmanager
            def install(instance,config,folder,*,origin,deadline,audit_context):
                calls.append((instance,config,folder,origin,deadline))
                audit_context['formed_heft_safe']={'fixture_existing_receipt':True}
                try:
                    yield
                finally:
                    audit_context['hook_restored']=True
            provider=SimpleNamespace(describe=lambda pid:dict(pid=pid,create_time=10.0,state='ACTIVE'))
            with patch.object(diagnostic,'HERE',root), \
                 patch.object(diagnostic,'verify_manifest',return_value=(manifest,entry,{})), \
                 patch.object(diagnostic,'configure_variant'), \
                 patch.object(diagnostic.time,'monotonic',return_value=100.0), \
                 patch.dict(sys.modules,{'live_heft_initializer':SimpleNamespace(install_initializer=install),
                    'projected_integration':SimpleNamespace(install_projection=lambda *a:__import__('contextlib').nullcontext()),
                    'research.chapter3_method_entry_executor.monitor':SimpleNamespace(PsutilProvider=lambda:provider)}):
                result=diagnostic.worker(SimpleNamespace(ticket=str(ticket_path),token='offline-token'))
            native.assert_called_once()
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][-2:],(99.0,699.0))
            self.assertEqual(result['status'],'TECHNICAL_FAILURE')
            self.assertIn('offline scientific-call failure',result['error'])
            context=diagnostic.read(output/'worker/initializer_context.json')
            self.assertTrue(context['hook_restored'])
            self.assertTrue(context['formed_heft_safe']['fixture_existing_receipt'])
            self.assertTrue((output/'worker/worker_result.json').exists())

    def test_heft_only_preserves_normal_deadline_without_integer_entry(self):
        raw = dict(safe_solution_source='initial_constructor', integer_solver_entered=False,
                   reason='wall_time_limit', milp_improved_initial_upper_bound=False,
                   strict_energy_improvement_certified=False)
        audit = {'execution': {'execution_status': 'NORMAL_TIME_LIMIT'}}
        safe = {'preserved': True, 'U_J': '1'}
        output = diagnostic.variant_outcome(raw, audit, safe, {'hook_called': True})
        self.assertEqual(output['outcome'], 'online_enhanced_heft_only')
        self.assertEqual(output['original_audit_execution_status'], 'NORMAL_TIME_LIMIT')
        self.assertFalse(output['integer_solver_entered'])

    def test_safe_heft_witness_does_not_erase_numeric_or_technical_failure(self):
        for status in ('NUMERICAL_ANOMALY_OBSERVED', 'TECHNICAL_FAILURE_CONFIRMED', 'STATUS_UNRESOLVED'):
            raw = dict(safe_solution_source='initial_constructor', integer_solver_entered=False)
            audit = {'execution': {'execution_status': status}}
            output = diagnostic.variant_outcome(raw, audit, {'preserved': True, 'U_J': '1'}, {'failed': True})
            self.assertEqual(output['outcome'], 'online_enhanced_heft_only')
            self.assertEqual(output['original_audit_execution_status'], status)
            self.assertTrue(output['final_safe_preserved'])

    def test_external_code_and_protocol_changes_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.HERE, prefix='mock_external_') as temporary:
            root = Path(temporary).resolve()
            for name in diagnostic.REQUIRED_EXTERNAL_CODE:
                (root/name).write_text('# offline fixture\n', encoding='utf-8')
            protocol = dict(schema='online-heft-milp-protocol-v1', scope=diagnostic.SCOPE,
                reference_subject_commit=diagnostic.SUBJECT_COMMIT,
                reference_plan_sha256=diagnostic.REFERENCE_SHA256,
                cleanup=dict(grace_seconds=20, total_seconds=40, watchdog_seconds=705))
            diagnostic.save(root/'protocol.json', protocol)
            with patch.object(diagnostic, 'HERE', root):
                manifest = dict(external_code_sha256=diagnostic.external_code_hashes(),
                    protocol_file=str(root/'protocol.json'), protocol_sha256=diagnostic.sha(root/'protocol.json'))
                diagnostic.verify_external_contract(manifest)
                (root/'live_heft_initializer.py').write_text('# changed\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'EXTERNAL_CODE_DRIFT'):
                    diagnostic.verify_external_contract(manifest)
                manifest['external_code_sha256'] = diagnostic.external_code_hashes()
                (root/'protocol.json').write_text('{}', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'PROTOCOL_BYTES_DRIFT'):
                    diagnostic.verify_external_contract(manifest)

    def test_single_use_is_checked_before_any_process_launch(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.HERE, prefix='mock_once_') as temporary:
            root=Path(temporary).resolve(); manifest_path=root/'manifest.json'
            manifest_path.write_text('{}', encoding='utf-8')
            claim=root/'claim.json'; claim.write_text('{}',encoding='utf-8')
            manifest=dict(output=str(root/'output'),claim=str(claim))
            with patch.object(diagnostic,'HERE',root), \
                 patch.object(diagnostic,'verify_manifest',return_value=(manifest,object(),{})), \
                 patch.object(diagnostic.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'SINGLE_USE_DIAGNOSTIC_ALREADY_CONSUMED'):
                    diagnostic.run(SimpleNamespace(manifest=str(manifest_path)))
                spawn.assert_not_called()

    def test_logged_launch_failure_has_terminal_record_and_no_retry(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.HERE, prefix='mock_logged_') as temporary:
            root=Path(temporary).resolve()
            with patch.object(run_logged,'HERE',root), \
                 patch.object(run_logged.subprocess,'Popen',side_effect=OSError('offline spawn failure')) as spawn:
                with patch('builtins.print'):
                    self.assertEqual(run_logged.main(['prepare','--manifest','unused']),2)
                spawn.assert_called_once()
            record=diagnostic.read(root/'prepare_command.json')
            self.assertEqual(record['status'],'LAUNCH_FAILED')
            self.assertIn('end_utc',record)
            self.assertTrue(record['no_retry'])
            self.assertTrue((root/'prepare.log').exists())

    def test_original_600_wiring_is_preserved(self):
        native, repaired, whole = object(), object(), object()
        base = SimpleNamespace(METHOD_SECONDS=600, METHOD_WATCHDOG_SECONDS=705,
            NATIVE_RESPONSE_VALIDATOR=native, native_session_factory=repaired, run_whole=whole)
        entry = SimpleNamespace(base=base, configure=Mock(),
            prior=SimpleNamespace(validate_response_600=native, run_whole=whole),
            repaired=SimpleNamespace(native_session_factory=repaired))
        diagnostic.configure_variant(entry)
        entry.configure.assert_called_once_with()
        self.assertEqual((base.METHOD_SECONDS, base.METHOD_WATCHDOG_SECONDS), (600,705))
        self.assertIs(base.run_whole, whole)
        base.NATIVE_RESPONSE_VALIDATOR=object()
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_600_NATIVE_VALIDATOR_REQUIRED'):
            diagnostic.configure_variant(entry)

    def test_observer_late_bytes_do_not_call_scientific_functions(self):
        path = SimpleNamespace(stat=lambda: SimpleNamespace(st_size=28, st_mtime_ns=10),
                               read_bytes=lambda: b'{"kind":"callback","x":[1]}')
        session = SimpleNamespace(glob=lambda pattern: [path] if 'event' in pattern else [])
        class Folder:
            def __truediv__(self, name):
                return session if name == 'matlab' else self
        seen, log = set(), io.StringIO()
        with patch.object(diagnostic, 'anchor', return_value=dict(monotonic_before=301, monotonic_after=301,
                                                                 utc='fixture')):
            diagnostic.observe(Folder(), 300, seen, log)
            diagnostic.observe(Folder(), 300, seen, log)
        rows = [diagnostic.json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['first_observed_after_deadline'])
        self.assertFalse(rows[0]['used_for_evaluation'])
        self.assertFalse(rows[0]['delivered_to_recorder'])

    def test_scope_drift_rejected_before_reference_import(self):
        baseline = dict(schema='bpre-online-heft-milp-600-v1', scope=deepcopy(diagnostic.SCOPE))
        for name, value in (('method_seconds', 300), ('method_calls', 2), ('post_calls', 1), ('retries', 1)):
            manifest = deepcopy(baseline); manifest['scope'][name] = value
            with patch.object(diagnostic, 'external_path', return_value=Path('fixture')), \
                 patch.object(diagnostic, 'read', return_value=manifest), \
                 patch.object(diagnostic, 'verify_reference') as source:
                with self.assertRaisesRegex(ValueError, 'VARIANT_SCOPE_DRIFT'):
                    diagnostic.verify_manifest('fixture', check_git=False)
                source.assert_not_called()

    def test_syntax_and_no_freeze_or_batch_run_calls(self):
        source = Path(diagnostic.__file__).read_text(encoding='utf-8')
        tree = ast.parse(source)
        compile(tree, diagnostic.__file__, 'exec')
        prohibited = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr in ('freeze', 'execute_formal_milp', 'evaluate_candidate', 'assess')]
        self.assertEqual(prohibited, [])

    def test_bad_cleanup_and_observer_io_still_reclaims_tree_and_writes_terminal(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.HERE, prefix='mock_cleanup_') as temporary:
            root = Path(temporary).resolve(); output = root / 'output'; manifest_path = root / 'manifest.json'
            manifest_path.write_text('{}', encoding='utf-8')
            manifest = dict(output=str(output), claim=str(root / 'claim.json'))
            entry = SimpleNamespace(base=SimpleNamespace(ROOT=root, verify_sources=Mock()))
            process = SimpleNamespace(pid=42, returncode=0, poll=lambda: 0, wait=Mock(), kill=Mock())
            monitor = SimpleNamespace(root_identity=(42, 1000), samples=[],
                cleanup_verified=Mock(side_effect=[False, True]),
                terminate_owned=Mock(return_value=[]), register_identities=Mock(),
                sample=Mock(side_effect=OSError('sample fixture failure')),
                summary=Mock(return_value={'cleanup_verified_observed_tree': True}))
            module = SimpleNamespace(ProcessMonitor=Mock(return_value=monitor),
                PsutilProvider=lambda: SimpleNamespace(describe=lambda pid: dict(pid=pid, create_time=900, state='ACTIVE')),
                default_host_probe=lambda root: {}, host_gate=lambda probe: {'passed': True})
            def spawn(*args, **kwargs):
                session = output / 'worker' / 'method' / 'matlab'; session.mkdir(parents=True)
                (session / 'session.json').write_text('{}', encoding='utf-8')
                (session / 'closed.json').write_text('{bad json', encoding='utf-8')
                return process
            actual_save = diagnostic.save
            def faulty_save(path, value):
                if Path(path).name == 'memory_samples.json':
                    raise OSError('memory log fixture failure')
                actual_save(path, value)
            with patch.object(diagnostic, 'HERE', root), \
                 patch.object(diagnostic, 'verify_manifest', return_value=(manifest, entry, {})), \
                 patch.object(diagnostic.subprocess, 'Popen', side_effect=spawn), \
                 patch.object(diagnostic, 'observe', side_effect=OSError('observer fixture failure')), \
                 patch.object(diagnostic, 'save', side_effect=faulty_save), \
                 patch.dict(sys.modules, {'research.chapter3_method_entry_executor.monitor': module,
                                          'matlab_bridge': SimpleNamespace(cleanup_is_complete=lambda receipt: True)}):
                result = diagnostic.run(SimpleNamespace(manifest=str(manifest_path)))
            monitor.terminate_owned.assert_called_once_with(force=True)
            self.assertEqual(result['state'], 'CLEANUP_FAILURE')
            self.assertTrue(result['missing_native_cleanup_receipt'])
            self.assertTrue((output / 'controller_result.json').is_file())
            operations = [item['operation'] for item in result['cleanup_errors']]
            self.assertTrue(any(name.startswith('admit_native_receipt:') for name in operations))
            for name in ('monitor_final_sample', 'save_memory_samples', 'terminal_observation'):
                self.assertIn(name, operations)


if __name__ == '__main__':
    unittest.main()
