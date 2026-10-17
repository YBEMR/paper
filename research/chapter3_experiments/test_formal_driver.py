"""Formal-batch identity and saved-evidence checks, without research calls.

The only input construction below is an existing one-Stage correctness fixture.
Controller tests replace subprocess workers; no MATLAB or physical evaluation
is called, and no historical optimum is read.
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_formal_comparison as driver
from inputs import load_config
from run_milp_precheck import fixtures


HERE = Path(__file__).resolve().parent


class DriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixture, starts = deepcopy(fixtures(cls.config)['one_stage_energy'])
        cls.fixture['start_domain'] = {
            'version': 1, 'kind': 'explicit_grid_subset',
            'by_scene_stage_ms': starts}
        cls.proposed = driver.manifest()

    def temporary(self):
        root = HERE.parents[1]/'.runtime'/'formal_correctness'
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def safe_result(self):
        instance = deepcopy(self.fixture)
        candidate = {'scenes': {
            scene['id']: [dict(stage_id=stage['id'], unit='CPU1', opp='H', start_ms='0')
                          for stage in scene['stage_instances']]
            for scene in instance['scenarios']}}
        result = {
            'state': 'SAFE', 'reason': 'CORRECTNESS_FIXTURE',
            'safe_candidate': candidate, 'safe_upper_bound_J': '2',
            'evaluation': {
                'problem_id': instance['id'], 'state': 'SAFE', 'rankable_energy': True,
                'weighted_energy_J': ['1', '2'],
                'completed_at_elapsed_s': 1,
                'scenes': {scene['id']: {
                    'state': 'SAFE', 'complete': True,
                    'covered_until_s': str(F(instance['window_ms'])/1000)}
                    for scene in instance['scenarios']}},
            'timing': {'limit_s': 300, 'method_elapsed_s': 2}}
        return instance, result

    def gate_records(self, root):
        root = Path(root)
        fingerprint = driver.canonical_hash(self.proposed)
        gate = {'passed': True, 'count': 1,
                'checks': [{'name': 'fixture', 'passed': True}],
                'source_sha256': {'fixture.py': 'known-source'},
                'manifest_sha256': fingerprint}
        approval = {'approved': True, 'manifest_sha256': fingerprint,
                    'user_confirmation_text': 'TEST ONLY: simulated concrete approval'}
        gate_path = root/'precheck.json'; approval_path = root/'approval.json'
        driver.save(gate_path, gate); driver.save(approval_path, approval)
        return gate_path, approval_path, gate, approval

    def test_manifest_has_fifteen_problems_and_115_unique_calls(self):
        proposed = self.proposed
        self.assertEqual(proposed['problems'], 15)
        self.assertEqual(proposed['calls'], 115)
        self.assertEqual(len(proposed['jobs']), 115)
        self.assertEqual(len({j['call_id'] for j in proposed['jobs']}), 115)
        self.assertEqual(proposed['maximum_method_seconds'], 115*300)
        self.assertEqual({j['seconds'] for j in proposed['jobs']}, {300})

    def test_first_technical_case_contains_exactly_eight_calls(self):
        jobs = self.proposed['jobs']
        self.assertEqual([j['problem_id'] for j in jobs[:8]], ['base__R1']*8)
        self.assertEqual([j['method'] for j in jobs[:8]],
                         ['milp', 'heft', 'sa', 'sa', 'sa', 'sa', 'sa', 'assignment'])
        self.assertNotEqual(jobs[8]['problem_id'], 'base__R1')

    def test_seed_and_assignment_scope_are_exact(self):
        jobs = self.proposed['jobs']
        expected = {condition+'__R'+str(sample)
                    for condition in ('base', 'initial_78', 'response_R')
                    for sample in range(1, 6)}
        self.assertEqual({j['problem_id'] for j in jobs}, expected)
        self.assertEqual(Counter(j['method'] for j in jobs),
                         {'milp': 15, 'heft': 15, 'sa': 75, 'assignment': 10})
        for problem in expected:
            self.assertEqual([j['seed'] for j in jobs
                              if j['problem_id']==problem and j['method']=='sa'],
                             [101, 102, 103, 104, 105])
        self.assertFalse(any(j['problem_id'].startswith('response_R__')
                             for j in jobs if j['method']=='assignment'))
        self.assertFalse(any('q1' in j['call_id'].lower() for j in jobs))

    def test_gate_accepts_only_current_complete_record_and_actual_approval(self):
        with self.temporary() as temp:
            gate_path, approval_path, _, _ = self.gate_records(temp)
            with patch.object(driver, 'signature', return_value={'fixture.py': 'known-source'}):
                self.assertEqual(driver.validate_gate(gate_path, approval_path), self.proposed)

    def test_gate_rejects_failed_missing_and_partial_checks(self):
        with self.temporary() as temp:
            gate_path, approval_path, original, _ = self.gate_records(temp)
            variants = []
            for key, value in [('passed', False), ('checks', []), ('count', 2)]:
                record = deepcopy(original); record[key] = value; variants.append(record)
            record = deepcopy(original); record['checks'][0]['passed'] = False; variants.append(record)
            with patch.object(driver, 'signature', return_value={'fixture.py': 'known-source'}):
                for record in variants:
                    with self.subTest(record=record):
                        driver.save(gate_path, record)
                        with self.assertRaisesRegex(ValueError, 'passing precheck'):
                            driver.validate_gate(gate_path, approval_path)

    def test_gate_rejects_stale_source_identity(self):
        with self.temporary() as temp:
            gate_path, approval_path, _, _ = self.gate_records(temp)
            with patch.object(driver, 'signature', return_value={'fixture.py': 'new-source'}):
                with self.assertRaisesRegex(ValueError, 'passing precheck'):
                    driver.validate_gate(gate_path, approval_path)

    def test_gate_rejects_stale_manifest_or_approval_manifest(self):
        with self.temporary() as temp:
            gate_path, approval_path, gate, approval = self.gate_records(temp)
            with patch.object(driver, 'signature', return_value={'fixture.py': 'known-source'}):
                for target, original in [(gate_path, gate), (approval_path, approval)]:
                    with self.subTest(target=target.name):
                        record = deepcopy(original); record['manifest_sha256'] = 'old-manifest'
                        driver.save(target, record)
                        with self.assertRaises(ValueError): driver.validate_gate(gate_path, approval_path)
                        driver.save(target, original)

    def test_gate_rejects_example_approval_and_absent_user_confirmation(self):
        with self.temporary() as temp:
            gate_path, approval_path, _, approval = self.gate_records(temp)
            variants = []
            for key, value in [('approved', False), ('approved', 1),
                               ('user_confirmation_text', None),
                               ('user_confirmation_text', '   ')]:
                record = deepcopy(approval); record[key] = value; variants.append(record)
            with patch.object(driver, 'signature', return_value={'fixture.py': 'known-source'}):
                for record in variants:
                    with self.subTest(record=record):
                        driver.save(approval_path, record)
                        with self.assertRaisesRegex(ValueError, 'approval'):
                            driver.validate_gate(gate_path, approval_path)

    def test_safe_receipt_requires_legal_schedule_and_complete_window(self):
        instance, result = self.safe_result()
        self.assertTrue(driver.technical_check(result, instance, 300)['passed'])
        sid = instance['scenarios'][0]['id']
        for mutation in ('illegal_start', 'missing_scene', 'short_window', 'incomplete', 'scene_unknown'):
            with self.subTest(mutation=mutation):
                changed = deepcopy(result)
                if mutation=='illegal_start': changed['safe_candidate']['scenes'][sid][0]['start_ms'] = '-5'
                elif mutation=='missing_scene': changed['evaluation']['scenes'].pop(sid)
                elif mutation=='short_window': changed['evaluation']['scenes'][sid]['covered_until_s'] = '1/1000'
                elif mutation=='incomplete': changed['evaluation']['scenes'][sid]['complete'] = False
                else: changed['evaluation']['scenes'][sid]['state'] = 'UNRESOLVED'
                self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])

    def test_safe_energy_and_in_budget_commit_are_required(self):
        instance, result = self.safe_result()
        for value in (300, 301, -1, True, None, '1'):
            with self.subTest(formed=value):
                changed = deepcopy(result); changed['evaluation']['completed_at_elapsed_s'] = value
                self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])
        changed = deepcopy(result); changed['safe_upper_bound_J'] = '3'
        self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])
        changed = deepcopy(result); changed['evaluation']['rankable_energy'] = False
        self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])

    def test_unresolved_without_safe_is_technically_valid_not_infeasible(self):
        instance, _ = self.safe_result()
        result = {'state': 'UNRESOLVED', 'reason': 'BUDGET', 'safe_upper_bound_J': None,
                  'independently_proven_infeasible': False,
                  'timing': {'limit_s': 300, 'method_elapsed_s': 301}}
        self.assertTrue(driver.technical_check(result, instance, 300)['passed'])
        result['safe_upper_bound_J'] = '2'
        self.assertFalse(driver.technical_check(result, instance, 300)['passed'])

    def test_interface_error_and_changed_time_limit_are_technical_failures(self):
        instance, result = self.safe_result()
        for reason in ('INTERFACE_ERROR', 'INTERFACE_OR_CONSISTENCY_ERROR'):
            changed = deepcopy(result); changed['reason'] = reason
            self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])
        changed = deepcopy(result); changed['timing']['limit_s'] = 301
        self.assertFalse(driver.technical_check(changed, instance, 300)['passed'])

    def test_technical_check_binds_call_input_and_safe_candidate(self):
        instance, result = self.safe_result()
        identity = driver.canonical_hash(instance)
        job = {'call_id': 'fixture__heft', 'problem_id': instance['id'],
               'method': 'heft', 'seed': None, 'seconds': 300}
        result.update({key: job[key] for key in ('call_id', 'problem_id', 'method', 'seed')})
        result.update(input_sha256=identity, safe_evidence_binding={
            'input_sha256': identity,
            'candidate_sha256': driver.canonical_hash(result['safe_candidate'])})
        self.assertTrue(driver.technical_check(result, instance, 300, job, identity)['passed'])
        for field, value in [('call_id', 'wrong-call'), ('problem_id', 'wrong-input'),
                             ('method', 'sa'), ('seed', 101), ('input_sha256', 'changed')]:
            with self.subTest(field=field):
                changed = deepcopy(result); changed[field] = value
                self.assertFalse(driver.technical_check(changed, instance, 300, job, identity)['passed'])
        changed = deepcopy(result); changed['evaluation']['problem_id'] = 'different-fixture'
        self.assertFalse(driver.technical_check(changed, instance, 300, job, identity)['passed'])
        changed = deepcopy(result); changed['safe_evidence_binding']['candidate_sha256'] = 'changed'
        self.assertFalse(driver.technical_check(changed, instance, 300, job, identity)['passed'])
        self.assertFalse(driver.technical_check(result, instance, 300, job, 'changed')['passed'])

    def test_worker_rejects_changed_source_before_loading_research_input(self):
        with self.temporary() as temp:
            declaration = Path(temp)/'declaration.json'
            driver.save(declaration, {'source_sha256': {'x': 'old'}, 'manifest': self.proposed})
            with patch.object(driver, 'signature', return_value={'x': 'new'}), \
                 patch.object(driver, 'load_config') as loader:
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    driver.worker(self.proposed['jobs'][0], Path(temp)/'call', declaration)
                loader.assert_not_called()

    def test_worker_rejects_unknown_job_before_loading_research_input(self):
        with self.temporary() as temp:
            declaration = Path(temp)/'declaration.json'
            driver.save(declaration, {'source_sha256': {'x': 'same'}, 'manifest': self.proposed})
            changed = deepcopy(self.proposed['jobs'][0]); changed['seconds'] = 600
            with patch.object(driver, 'signature', return_value={'x': 'same'}), \
                 patch.object(driver, 'load_config') as loader:
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    driver.worker(changed, Path(temp)/'call', declaration)
                loader.assert_not_called()

    def test_approval_claim_is_single_use_across_different_outputs(self):
        with self.temporary() as temp:
            root = Path(temp); _, approval_path, _, _ = self.gate_records(root)
            driver.claim_approval(approval_path, self.proposed, root/'first')
            used = list(root.glob('*.used.json'))
            self.assertEqual(len(used), 1)
            before = used[0].read_bytes()
            with self.assertRaises((FileExistsError, ValueError)):
                driver.claim_approval(approval_path, self.proposed, root/'second')
            self.assertEqual(used[0].read_bytes(), before)

    def test_run_stops_after_first_technical_error_without_retry(self):
        with self.temporary() as temp:
            root = Path(temp); gate_path, approval_path, _, _ = self.gate_records(root)
            proposed = deepcopy(self.proposed)
            proposed['jobs'] = proposed['jobs'][:2]
            out = root/'batch'; subprocess_calls = []

            def fake_worker(command, **kwargs):
                subprocess_calls.append(command)
                call_out = Path(command[command.index('--out')+1]); call_out.mkdir()
                driver.save(call_out/'input_instance.json', self.fixture)
                driver.save(call_out/'result.json', {
                    'state': 'UNRESOLVED', 'reason': 'INTERFACE_ERROR',
                    'source_signature_unchanged': True,
                    'timing': {'limit_s': 300, 'method_elapsed_s': 1}})
                return SimpleNamespace(returncode=0)

            with patch.object(driver, 'validate_gate', return_value=proposed), \
                 patch.object(driver, 'signature', return_value={'x': 'same'}), \
                 patch.object(driver, 'source_paths', return_value={}), \
                 patch.object(driver.subprocess, 'run', side_effect=fake_worker):
                driver.run(gate_path, approval_path, out)
            self.assertEqual(len(subprocess_calls), 1)
            self.assertEqual(json.loads((out/'stop.json').read_text(encoding='utf-8'))['reason'],
                             'TECHNICAL_CHECK_FAILED')
            self.assertEqual(len(json.loads((out/'calls.json').read_text(encoding='utf-8'))), 1)
            self.assertFalse((out/(proposed['jobs'][1]['call_id']+'.claim.json')).exists())

    def test_run_rejects_unapproved_gate_before_any_output_or_worker(self):
        with self.temporary() as temp:
            out = Path(temp)/'batch'
            with patch.object(driver, 'validate_gate', side_effect=ValueError('not approved')), \
                 patch.object(driver.subprocess, 'run') as native:
                with self.assertRaisesRegex(ValueError, 'not approved'):
                    driver.run('not-read-gate.json', 'not-read-approval.json', out)
                native.assert_not_called()
            self.assertFalse(out.exists())

    def test_source_change_before_first_call_stops_with_empty_saved_summary(self):
        with self.temporary() as temp:
            root = Path(temp); gate_path, approval_path, _, _ = self.gate_records(root)
            out = root/'batch'
            with patch.object(driver, 'validate_gate', return_value=self.proposed), \
                 patch.object(driver, 'signature', side_effect=[{'x': 'old'}, {'x': 'new'}, {'x': 'new'}]), \
                 patch.object(driver, 'source_paths', return_value={}), \
                 patch.object(driver.subprocess, 'run') as native:
                driver.run(gate_path, approval_path, out)
                native.assert_not_called()
            self.assertEqual(json.loads((out/'calls.json').read_text(encoding='utf-8')), [])
            self.assertEqual(json.loads((out/'stop.json').read_text(encoding='utf-8'))['reason'],
                             'SOURCE_CHANGED')
            summary = json.loads((out/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['calls_completed'], 0)

    def test_prepare_creates_only_an_unapproved_example(self):
        with self.temporary() as temp:
            out = Path(temp)/'proposal'
            with patch.object(driver, 'signature', return_value={'x': 'same'}): driver.prepare(out)
            approval = json.loads((out/'approval_record_example.json').read_text(encoding='utf-8'))
            self.assertIs(approval['approved'], False)
            self.assertIsNone(approval['user_confirmation_text'])
            self.assertEqual(approval['manifest_sha256'], driver.canonical_hash(self.proposed))
            self.assertFalse(list(out.glob('*.used.json')))

    def test_atomic_publication_preserves_existing_evidence_if_replace_fails(self):
        with self.temporary() as temp:
            target=Path(temp)/'result.json'
            original=b'{"state":"SAFE","old_receipt":true}\n'
            target.write_bytes(original)
            replacement={'state':'SAFE','call_id':'fixture_only'}
            with patch.object(Path,'replace',side_effect=OSError(22,'injected publication failure')):
                with self.assertRaises(OSError): driver.save(target,replacement)
            self.assertEqual(target.read_bytes(),original)
            pending=list(Path(temp).glob('.result.json.pending-*'))
            self.assertEqual(len(pending),1)
            self.assertEqual(json.loads(pending[0].read_text(encoding='utf-8')),replacement)

    def test_atomic_publication_replaces_only_after_complete_serialization(self):
        with self.temporary() as temp:
            target=Path(temp)/'result.json'
            driver.save(target,{'old':True})
            before=target.read_bytes()
            with self.assertRaises(ValueError): driver.save(target,{'invalid':float('nan')})
            self.assertEqual(target.read_bytes(),before)
            self.assertFalse(list(Path(temp).glob('.result.json.pending-*')))
            driver.save(target,{'complete':['new','receipt']})
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'complete':['new','receipt']})
            self.assertFalse(list(Path(temp).glob('.result.json.pending-*')))


if __name__=='__main__': unittest.main(verbosity=2)
