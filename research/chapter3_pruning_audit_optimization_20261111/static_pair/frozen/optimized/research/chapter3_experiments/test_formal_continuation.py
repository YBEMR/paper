"""Continuation coverage/authorization checks without research or MATLAB calls.

The prior batch below is a tiny *record* fixture with the real 115-job schema.
All workers are replaced in controller tests; no thermal evaluation is run.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_formal_comparison as original
import run_formal_continuation as driver


HERE = Path(__file__).resolve().parent
SOURCE_KEY = 'research/chapter3_experiments/run_formal_comparison.py'
CURRENT_SIGNATURE = {SOURCE_KEY: 'current-source'}


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_manifest = original.manifest()

    def setUp(self):
        replacement = patch.object(original, 'signature', return_value=CURRENT_SIGNATURE)
        replacement.start(); self.addCleanup(replacement.stop)

    def temporary(self):
        root = HERE.parents[1]/'.runtime'/'formal_correctness'
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def previous(self, root):
        previous = Path(root)/'previous'
        previous.mkdir()
        snapshot = previous/'source_snapshot'/SOURCE_KEY
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text('historical source fixture only', encoding='utf-8')
        original.save(previous/'declaration.json', {
            'manifest': deepcopy(self.original_manifest),
            'source_sha256': {SOURCE_KEY: original.digest(snapshot)},
            'approval_record_sha256': 'historical-approval',
            'precheck_record_sha256': 'historical-precheck',
            'started_at': '2026-10-17T22:40:51+0800'})
        calls = []
        for index, job in enumerate(self.original_manifest['jobs'][:5]):
            call = {'job': deepcopy(job), 'process_wall_s': 1,
                    'returncode': 0 if index<4 else 1,
                    'technical_check': {'passed': index<4, 'errors': [] if index<4 else ['fixture failure']}}
            calls.append(call)
            original.save(previous/(job['call_id']+'.claim.json'), job)
            call_dir = previous/job['call_id']; call_dir.mkdir()
            original.save(call_dir/'result.json', {'state': 'UNRESOLVED', 'fixture_only': True})
            original.save(call_dir/'input_instance.json', {'id': job['problem_id'], 'fixture_only': True})
            (previous/(job['call_id']+'.stdout.txt')).write_text('fixture worker only', encoding='utf-8')
        original.save(previous/'calls.json', calls)
        original.save(previous/'stop.json', {'reason': 'TECHNICAL_CHECK_FAILED', 'call': calls[-1]})
        original.save(previous/'source_integrity.json', {'unchanged': True})
        return previous

    @staticmethod
    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))

    @staticmethod
    def bytes_under(root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in Path(root).rglob('*') if path.is_file()}

    def records(self, root, previous):
        proposed = driver.remaining_manifest(previous)
        fingerprint = original.canonical_hash(proposed)
        gate = {'passed': True, 'count': 1,
                'checks': [{'name': 'fixture-only', 'passed': True}],
                'source_sha256': CURRENT_SIGNATURE,
                'manifest_sha256': fingerprint}
        approval = {'approved': True, 'manifest_sha256': fingerprint,
                    'user_confirmation_text': 'TEST ONLY: continue the never-invoked 110 calls'}
        gate_path = Path(root)/'precheck.json'
        approval_path = Path(root)/'approval.json'
        original.save(gate_path, gate); original.save(approval_path, approval)
        return gate_path, approval_path, gate, approval, proposed

    def test_remaining_manifest_excludes_all_five_started_calls_including_failure(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            before = self.bytes_under(previous)
            remaining = driver.remaining_manifest(previous)
            self.assertEqual(remaining['calls'], 110)
            self.assertEqual(remaining['problems'], 15)
            self.assertEqual(remaining['already_invoked'], 5)
            self.assertEqual(remaining['maximum_method_seconds'], 110*300)
            self.assertEqual(remaining['input_sha256'], self.original_manifest['input_sha256'])
            self.assertEqual(remaining['jobs'], self.original_manifest['jobs'][5:])
            self.assertEqual(remaining['first_technical_case'], 'base__R1')
            self.assertEqual([job['seed'] for job in remaining['jobs'][:2]], [104, 105])
            self.assertTrue({job['call_id'] for job in remaining['jobs']}.isdisjoint(
                job['call_id'] for job in self.original_manifest['jobs'][:5]))
            self.assertEqual(before, self.bytes_under(previous))

    def test_missing_or_extra_claim_refuses_to_infer_unstarted_scope(self):
        for mutation in ('missing', 'extra', 'changed'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                first = self.original_manifest['jobs'][0]
                if mutation=='missing':
                    (previous/(first['call_id']+'.claim.json')).unlink()
                elif mutation=='extra':
                    extra = self.original_manifest['jobs'][5]
                    original.save(previous/(extra['call_id']+'.claim.json'), extra)
                else:
                    changed = deepcopy(first); changed['seconds'] = 301
                    original.save(previous/(first['call_id']+'.claim.json'), changed)
                with self.assertRaises(ValueError): driver.remaining_manifest(previous)

    def test_prior_calls_must_be_unique_exact_original_prefix(self):
        for mutation in ('reorder', 'duplicate', 'wrong-seed', 'more-calls-than-claims'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                calls = self.read(previous/'calls.json')
                if mutation=='reorder': calls[0], calls[1] = calls[1], calls[0]
                elif mutation=='duplicate': calls[1] = deepcopy(calls[0])
                elif mutation=='wrong-seed': calls[-1]['job']['seed'] = 999
                else: calls.append(deepcopy(calls[-1]))
                original.save(previous/'calls.json', calls)
                with self.assertRaises(ValueError): driver.remaining_manifest(previous)

    def test_prior_stop_and_manifest_identity_must_match(self):
        for mutation in ('missing-stop', 'wrong-stop-call', 'changed-manifest'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                if mutation=='missing-stop': (previous/'stop.json').unlink()
                elif mutation=='wrong-stop-call':
                    stop = self.read(previous/'stop.json')
                    stop['call']['job'] = self.original_manifest['jobs'][0]
                    original.save(previous/'stop.json', stop)
                else:
                    declaration = self.read(previous/'declaration.json')
                    declaration['manifest']['jobs'][0]['seconds'] = 301
                    original.save(previous/'declaration.json', declaration)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    driver.remaining_manifest(previous)

    def test_current_passing_precheck_and_new_concrete_approval_are_required(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            gate_path, approval_path, _, _, proposed = self.records(temp, previous)
            with patch.object(original, 'signature', return_value=CURRENT_SIGNATURE):
                self.assertEqual(driver.validate_gate(gate_path, approval_path, previous), proposed)

    def test_old_115_call_approval_and_unconfirmed_example_are_rejected(self):
        for mutation in ('old-approval', 'example', 'empty-confirmation'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                gate_path, approval_path, _, approval, _ = self.records(temp, previous)
                if mutation=='old-approval':
                    approval['manifest_sha256'] = original.canonical_hash(self.original_manifest)
                elif mutation=='example': approval['approved'] = False
                else: approval['user_confirmation_text'] = ' '
                original.save(approval_path, approval)
                with patch.object(original, 'signature', return_value=CURRENT_SIGNATURE):
                    with self.assertRaises(ValueError):
                        driver.validate_gate(gate_path, approval_path, previous)

    def test_changed_source_failed_or_partial_precheck_is_rejected(self):
        for mutation in ('source', 'failed', 'partial', 'missing-checks', 'changed-manifest'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                gate_path, approval_path, gate, _, _ = self.records(temp, previous)
                if mutation=='source': gate['source_sha256'] = {'fixture.py': 'old'}
                elif mutation=='failed': gate['checks'][0]['passed'] = False
                elif mutation=='partial': gate['count'] = 2
                elif mutation=='missing-checks': gate['checks'] = []
                else: gate['manifest_sha256'] = 'changed'
                original.save(gate_path, gate)
                with patch.object(original, 'signature', return_value=CURRENT_SIGNATURE):
                    with self.assertRaises(ValueError):
                        driver.validate_gate(gate_path, approval_path, previous)

    def test_prior_record_change_invalidates_already_prechecked_continuation(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            gate_path, approval_path, _, _, _ = self.records(temp, previous)
            calls = self.read(previous/'calls.json')
            calls[0]['process_wall_s'] = 2
            original.save(previous/'calls.json', calls)
            with patch.object(original, 'signature', return_value=CURRENT_SIGNATURE):
                with self.assertRaises(ValueError):
                    driver.validate_gate(gate_path, approval_path, previous)

    def test_unapproved_gate_is_rejected_before_output_or_worker(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            before = self.bytes_under(previous)
            out = Path(temp)/'continuation'
            with patch.object(driver, 'validate_gate', side_effect=ValueError('fixture not approved')), \
                 patch('subprocess.run') as worker:
                with self.assertRaisesRegex(ValueError, 'fixture not approved'):
                    driver.run('not-read-precheck.json', 'not-read-approval.json', previous, out)
                worker.assert_not_called()
            self.assertFalse(out.exists())
            self.assertEqual(before, self.bytes_under(previous))

    def test_unregistered_worker_activity_is_not_called_never_invoked(self):
        for mutation in ('directory', 'stdout'):
            with self.subTest(mutation=mutation), self.temporary() as temp:
                previous = self.previous(temp)
                pending = self.original_manifest['jobs'][5]['call_id']
                if mutation=='directory': (previous/pending).mkdir()
                else: (previous/(pending+'.stdout.txt')).write_text('unregistered activity', encoding='utf-8')
                with self.assertRaises(ValueError): driver.remaining_manifest(previous)

    def test_prior_snapshot_and_method_source_changes_are_rejected(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            (previous/'source_snapshot'/SOURCE_KEY).write_text('changed snapshot', encoding='utf-8')
            with self.assertRaises(ValueError): driver.remaining_manifest(previous)
        with self.temporary() as temp:
            previous = self.previous(temp)
            with patch.object(original, 'signature', return_value={**CURRENT_SIGNATURE,
                    'research/chapter3_experiments/thermal.py': 'changed method source'}):
                with self.assertRaises(ValueError): driver.remaining_manifest(previous)

    def fake_worker(self, call_log, *, fail_at=1):
        def invoke(command, **kwargs):
            job = json.loads(command[command.index('--job')+1])
            call_log.append(job)
            call_out = Path(command[command.index('--out')+1]); call_out.mkdir()
            original.save(call_out/'input_instance.json', {'id': job['problem_id']})
            original.save(call_out/'result.json', {
                'state': 'UNRESOLVED', 'reason': 'BUDGET',
                'source_signature_unchanged': True,
                'timing': {'limit_s': job['seconds'], 'method_elapsed_s': 300}})
            return SimpleNamespace(returncode=1 if len(call_log)==fail_at else 0)
        return invoke

    def test_technical_failure_stops_remainder_and_original_files_are_unchanged(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            gate_path, approval_path, _, _, proposed = self.records(temp, previous)
            before = self.bytes_under(previous); invoked = []; out = Path(temp)/'continuation'
            with patch.object(original, 'source_paths', return_value={}), \
                 patch('subprocess.run', side_effect=self.fake_worker(invoked)):
                driver.run(gate_path, approval_path, previous, out)
            self.assertEqual(invoked, proposed['jobs'][:1])
            self.assertEqual(self.read(out/'stop.json')['reason'], 'TECHNICAL_CHECK_FAILED')
            self.assertEqual(len(self.read(out/'calls.json')), 1)
            self.assertFalse((out/(proposed['jobs'][1]['call_id']+'.claim.json')).exists())
            self.assertFalse((out/'first_pair_technical_check.json').exists())
            self.assertEqual(before, self.bytes_under(previous))

    def test_new_approval_is_single_use_across_output_directories(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            gate_path, approval_path, _, _, _ = self.records(temp, previous)
            invoked = []
            with patch.object(original, 'source_paths', return_value={}), \
                 patch('subprocess.run', side_effect=self.fake_worker(invoked)):
                driver.run(gate_path, approval_path, previous, Path(temp)/'first')
                with self.assertRaises((FileExistsError, ValueError)):
                    driver.run(gate_path, approval_path, previous, Path(temp)/'second')
            self.assertEqual(len(invoked), 1)
            self.assertFalse((Path(temp)/'second').exists())
            self.assertEqual(len(list(Path(temp).glob('approval.json.used.json'))), 1)

    def test_three_continuation_entry_successes_do_not_relabel_original_eight(self):
        with self.temporary() as temp:
            previous = self.previous(temp)
            gate_path, approval_path, _, _, proposed = self.records(temp, previous)
            before = self.bytes_under(previous); invoked = []; out = Path(temp)/'continuation'
            with patch.object(original, 'source_paths', return_value={}), \
                 patch.object(original, 'technical_check', return_value={'passed': True, 'errors': []}), \
                 patch('subprocess.run', side_effect=self.fake_worker(invoked, fail_at=4)):
                driver.run(gate_path, approval_path, previous, out)
            self.assertEqual(invoked, proposed['jobs'][:4])
            entry = self.read(out/'continuation_entry_technical_check.json')
            self.assertIs(entry['passed'], True); self.assertEqual(entry['calls'], 3)
            self.assertFalse((out/'first_pair_technical_check.json').exists())
            self.assertFalse((previous/'first_pair_technical_check.json').exists())
            self.assertEqual(before, self.bytes_under(previous))


if __name__=='__main__': unittest.main(verbosity=2)
