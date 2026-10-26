"""Synthetic JSON and mock-module checks; no scientific entry is imported."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import read_audit as reader


def safe(formed=100, energy='1'):
    return {'state': 'SAFE', 'rankable_energy': True,
            'completed_at_elapsed_s': formed, 'weighted_energy_J': [energy, energy],
            'safe_upper_bound_J': energy}


class AuditAdapterTests(unittest.TestCase):
    def modules(self, fail=False):
        whole, heuristic = types.ModuleType('audit_whole'), types.ModuleType('audit_heuristic')
        whole.SECONDS = heuristic.SECONDS = 300
        def records(result, declaration, folder, **kwargs):
            self.assertEqual((whole.SECONDS, heuristic.SECONDS), (3600, 3600))
            self.assertEqual(result, {'sentinel': True})
            self.assertEqual(declaration, {'input': 'bound'})
            self.assertEqual(folder, Path('unopened-mock-folder'))
            self.assertEqual(kwargs, dict(input_valid=True, source_valid=False, errors=['drift']))
            if fail:
                raise RuntimeError('mock failure')
            return {'execution': {'execution_status': 'MOCK_TECHNICAL_FAILURE'}}
        whole.result_records = records
        return whole, heuristic

    def invoke(self):
        return reader.audit_result({'sentinel': True}, {'input': 'bound'}, 'unopened-mock-folder',
            input_valid=True, source_valid=False, errors=['drift'])

    def test_adapter_changes_only_two_cutoffs_and_passes_all_arguments(self):
        whole, heuristic = self.modules()
        with patch.dict('sys.modules', audit_whole=whole, audit_heuristic=heuristic):
            self.assertEqual(self.invoke()['execution']['execution_status'], 'MOCK_TECHNICAL_FAILURE')
        self.assertEqual((whole.SECONDS, heuristic.SECONDS), (300, 300))

    def test_original_module_globals_restored_after_failure(self):
        whole, heuristic = self.modules(fail=True)
        with patch.dict('sys.modules', audit_whole=whole, audit_heuristic=heuristic):
            with self.assertRaises(RuntimeError):
                self.invoke()
        self.assertEqual((whole.SECONDS, heuristic.SECONDS), (300, 300))

    def test_only_declared_3600_cutoff_is_accepted(self):
        for value in (300, 3601, True, float('nan')):
            with self.assertRaises(ValueError):
                reader.audit_result({}, {}, '.', input_valid=True, source_valid=True, seconds=value)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[3]/'.runtime')
        self.folder = Path(self.tmp.name)
        self.write('method_budget_identity.json', dict(start=1000, deadline=4600,
                                                      limit_s=3600, clock='monotonic'))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        (self.folder/name).write_text(json.dumps(value), encoding='utf-8')

    def rows(self, name, values, partial=''):
        (self.folder/name).write_text(''.join(json.dumps(v)+'\n' for v in values)+partial,
                                      encoding='utf-8')

    def read(self, cutoff=300, observed=1301):
        return reader.read_checkpoint(self.folder, cutoff, observed)

    def initial(self, formed=100, energy='1', completed=150):
        self.write('initial_receipt_checkpoint.json', {
            'publication_started_at_s': completed,
            'initialisation': {'completed_at_s': completed,
                'attempts': [{'schedule_completed_at_s': formed-1}],
                'witness': {'candidate': {'mock': 'initial'}, 'evaluation': safe(formed, energy)}}})

    def event(self, stamp=250, formed=240, energy='0.9', accepted=True):
        return {'event': 'candidate_evaluated', 'source': 'request_000001:event3',
                'evaluation_returned_at_s': stamp, 'accepted_safe': accepted,
                'candidate': {'mock': 'solver'}, 'evaluation': safe(formed, energy)}

    def test_future_and_boundary_records_are_excluded(self):
        rows = [{'event': 'candidate_received', 'method_elapsed_s': 100},
                self.event(), self.event(300, 299, '0.8'), self.event(400, 390, '0.7')]
        self.rows('diagnostic_events.jsonl', rows)
        result = self.read()
        self.assertEqual(result['raw_events'], rows[:2])
        self.assertEqual(result['raw_events_excluded'], 2)
        self.assertEqual(result['counts']['solver_candidate_receipts'], 1)
        self.assertEqual(result['counts']['solver_safe_receipts'], 1)
        self.assertEqual(result['best_safe_receipt_as_reported']['safe_upper_bound_J'], '0.9')

    def test_early_observation_cannot_see_future_receipts(self):
        self.rows('diagnostic_events.jsonl', [self.event(250, 240)])
        result = self.read(observed=1200)
        self.assertFalse(result['checkpoint_reached'])
        self.assertEqual(result['raw_events'], [])

    def test_initial_and_solver_safe_are_distinct(self):
        self.initial()
        self.rows('diagnostic_events.jsonl', [self.event()])
        result = self.read()
        self.assertEqual(result['counts']['initial_safe_receipts'], 1)
        self.assertEqual(result['counts']['solver_safe_receipts'], 1)
        self.assertEqual(result['best_safe_receipt_as_reported']['source'], 'request_000001:event3')
        self.assertFalse(result['best_safe_receipt_as_reported']['independently_validated_by_reader'])

    def test_formed_initial_safe_survives_later_x0_completion(self):
        self.initial(formed=100, completed=500)
        result = self.read()
        self.assertEqual(result['initial_safe_receipt']['formed_at_s'], 100)
        self.assertNotIn('publication_started_at_s', result['initial_safe_receipt'])
        self.assertNotIn('completed_at_s', result['initial_safe_receipt'])

    def test_future_initial_safe_is_not_backfilled(self):
        self.initial(formed=350)
        self.assertIsNone(self.read()['initial_safe_receipt'])

    def test_unaccepted_or_prefix_energy_cannot_become_safe(self):
        not_accepted = self.event(accepted=False)
        prefix = self.event()
        prefix['evaluation']['rankable_energy'] = False
        self.rows('diagnostic_events.jsonl', [not_accepted, prefix])
        self.assertIsNone(self.read()['best_safe_receipt_as_reported'])

    def test_mismatched_energy_upper_is_not_safe(self):
        row = self.event()
        row['evaluation']['safe_upper_bound_J'] = '0.8'
        self.rows('diagnostic_events.jsonl', [row])
        self.assertEqual(self.read()['counts']['solver_safe_receipts'], 0)

    def test_raw_counts_do_not_turn_duplicates_into_new_candidates(self):
        rows = [{'event': 'candidate_received', 'method_elapsed_s': 20},
                {'event': 'candidate_decoded', 'decode': {'state': 'LEGAL', 'completed_at_s': 21}},
                {'event': 'duplicate_receipt_reused', 'method_elapsed_s': 22},
                {'event': 'invalid_candidate', 'method_elapsed_s': 25}]
        self.rows('diagnostic_events.jsonl', rows)
        count = self.read()['counts']
        self.assertEqual((count['solver_candidate_receipts'], count['legal_decodes'],
                          count['duplicate_receipts'], count['invalid_decodes']), (1, 1, 1, 1))
        self.assertEqual(count['solver_candidate_evaluations'], 0)

    def test_native_bound_uses_received_root_time_and_preserves_missing_gap(self):
        rows = [{'event': 'worker_event_received', 'kind': 'solver_entered',
                 'method_elapsed_s': 80, 'request': 'request_000001'},
                {'event': 'worker_event_received', 'kind': 'callback', 'method_elapsed_s': 200,
                 'request': 'request_000001', 'values': {'lowerbound': 0.5}},
                {'event': 'worker_event_received', 'kind': 'callback', 'method_elapsed_s': 350,
                 'request': 'request_000001', 'values': {'lowerbound': 0.8}}]
        self.rows('diagnostic_events.jsonl', rows)
        result = self.read()
        self.assertEqual(result['solver_entered_received_s'], 80)
        self.assertEqual(result['latest_solver_reported_bound']['lowerbound'], 0.5)
        self.assertIsNone(result['latest_solver_reported_bound']['relativegap'])
        self.assertFalse(result['latest_solver_reported_bound']['independently_certified'])

    def test_partial_log_line_is_not_a_complete_record(self):
        self.rows('diagnostic_events.jsonl', [{'event': 'candidate_received', 'method_elapsed_s': 20}],
                  partial='{"event": "candidate_evaluated"')
        result = self.read()
        self.assertEqual(result['ignored_partial_lines'], 1)
        self.assertEqual(len(result['raw_events']), 1)

    def test_missing_and_invalid_root_do_not_produce_scientific_evidence(self):
        (self.folder/'method_budget_identity.json').unlink()
        self.assertEqual(self.read()['state'], 'ROOT_IDENTITY_NOT_AVAILABLE')
        self.write('method_budget_identity.json', dict(start=1000, deadline=1300,
                                                      limit_s=300, clock='monotonic'))
        self.assertEqual(self.read()['state'], 'INVALID_ROOT_IDENTITY')

    def test_observation_before_method_is_explicit(self):
        self.assertEqual(self.read(observed=900)['state'], 'OBSERVATION_PRECEDES_METHOD')

    def test_build_progress_is_filtered_by_its_root_time(self):
        first = {'method_elapsed_seconds': 30, 'current_stage': 'options'}
        future = {'method_elapsed_seconds': 350, 'current_stage': 'complete'}
        self.rows('build_progress.jsonl', [first, future])
        self.assertEqual(self.read()['latest_build_progress'], first)

    def test_reader_never_writes_or_mutates_existing_files(self):
        self.initial()
        self.rows('diagnostic_events.jsonl', [self.event()])
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.read()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})

    def test_invalid_checkpoint_arguments_rejected(self):
        for value in (0, -1, 3601, True, float('inf')):
            with self.assertRaises(ValueError):
                self.read(cutoff=value)
        with self.assertRaises(ValueError):
            self.read(observed=float('nan'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
