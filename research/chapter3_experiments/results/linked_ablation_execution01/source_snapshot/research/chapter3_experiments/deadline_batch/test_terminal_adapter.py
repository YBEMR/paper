"""Pure stored-record fixtures, never research, solver or thermal evaluation.

All receipt temperatures here are fabricated audit markers.  The first
fixture is an intentionally zero-deadline tiny case, not a proposed input.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT/'p0_batch'), str(ROOT)]
from terminal_adapter import adapt_no_safe_seed, NO_SEED_REASON
from execution_status import classify_execution
from control_policy import with_auto_low_idle
from inputs import load_config
from scene_adapter import canonical_hash, _partial_identity, _receipt_hash, PARTIAL_PROTOCOL
from thermal import _accuracy
from test_partial_deployment import small_case


def save(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=False), encoding='utf-8')


def fixture(folder, *, receipt_kind=None):
    """Make fabricated existing records; do not call a constructor/evaluator."""
    instance, deployment, parts = small_case()
    instance = deepcopy(instance)
    config = with_auto_low_idle(load_config())
    if receipt_kind is None:
        for scene in instance['scenarios']:
            for request in scene['requests']:
                request['deadline_ms'] = request['relative_deadline_ms'] = '0'
    accuracy = _accuracy(config['accuracy_targets'])
    identity = {'full_input_sha256': canonical_hash(instance),
                'config_sha256': canonical_hash(config),
                'shared_deployment_sha256': canonical_hash(deployment),
                'accuracy_sha256': canonical_hash(accuracy)}
    declaration = {'problem_id': instance['id'], 'input_sha256': canonical_hash(instance),
                   'config_sha256': canonical_hash(config)}
    result = {'protocol': 'fixture-linked-seed-audit', 'reason': NO_SEED_REASON,
        'state': 'UNRESOLVED', 'technical_state': 'INTERRUPTED_OR_UNRESOLVED',
        'problem_id': instance['id'], 'identity': identity,
        'shared_deployment': deployment, 'shared_stage_ids': sorted(deployment),
        'original_scene_order': [s['id'] for s in instance['scenarios']],
        'stop_stage': 'fresh_seed_construction', 'budget_exhausted': False,
        'search_failure_latched': False, 'matlab_worker_ready': False,
        'solver_request_attempts': 0, 'session_total_request_count': 0,
        'integer_solver_entered': False, 'event_consumer_detached': True,
        'session_closed_by_neighborhood': False,
        'augmented_transport': {'requests': [], 'latched_unresolved': False, 'failure_reasons': []},
        'phases': [], 'condition': None, 'committed_safe_snapshot': None,
        'global_updates': [], 'rankable_energy': False, 'safe_candidate': None,
        'safe_upper_bound_J': None, 'weighted_energy_J': None, 'aggregation': None,
        'initial_global_safe_upper_bound_J': None,
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'remaining_domain': 'retained', 'timing': {'limit_s': 300, 'method_elapsed_s': 20.},
        'seed_attempts': []}
    domains = instance['platform']['domains']
    opps = {domain: sorted(v['opps'], key=lambda k: (-F(v['opps'][k]['frequency_GHz']), k))
            for domain, v in domains.items()}
    all_rows = [row for part in parts.values() for rows in part['scenes'].values() for row in rows]
    stages = {stage['id']: stage for scene in instance['scenarios'] for stage in scene['stage_instances']}
    full_deployment = {stages[row['stage_id']]['shared_stage_id']: row['unit'] for row in all_rows}
    units = {u['id']: u for u in instance['platform']['units']}
    budget = SimpleNamespace(_scene_adapter_budget_identity={
        'token': 'fixture-one-invocation', 'start': '10.0', 'seconds': '300.0',
        'panel_limit': 100000, 'refinement_limit': 100000})
    for rank in range(1, 4):
        chosen = {d: values[rank-1] for d, values in opps.items()}
        construction = {'rule_version': 'deterministic-initial-schedule-v1',
            'template_rank': rank, 'domain_opps': chosen, 'shared_deployment': full_deployment,
            'thermal_status': 'NOT_EVALUATED', 'energy_status': 'NOT_EVALUATED', 'exclusion': 'NONE'}
        attempt = {'construction': construction, 'schedule_completed_at_s': float(rank),
                   'scene_evaluations': {}, 'state': 'UNRESOLVED', 'aggregation': None}
        if receipt_kind is None:
            scene = instance['scenarios'][0]
            stage = scene['stage_instances'][0]
            mode = next(m for m in instance['stage_modes'][stage['shared_stage_id']]
                        if m['unit_id'] == full_deployment[stage['shared_stage_id']]
                        and m['opp_id'] == chosen[m['domain_id']])
            construction.update(status='CONSTRUCTION_UNRESOLVED', details={
                'reason': 'NO_START_FOUND_BY_FIXED_RULE', 'scenario': scene['id'],
                'stage_id': stage['id'], 'latest_finish_ms': '0', 'earliest_ms': '0',
                'duration_ms': mode['duration_ms'], 'assigned_stage_count': 0})
            attempt['reason'] = 'CONSTRUCTION_UNRESOLVED'
        else:
            candidate = {'scenes': {sid: deepcopy(part['scenes'][sid]) for sid, part in parts.items()}}
            for rows in candidate['scenes'].values():
                for row in rows:
                    row['opp'] = chosen[units[row['unit']]['domain_id']]
            construction.update(status='COMPLETE_LEGAL_CANDIDATE', candidate=candidate)
            scene = instance['scenarios'][0]; sid = scene['id']
            local = {'scenes': {sid: candidate['scenes'][sid]}}
            local_deployment = {stages[row['stage_id']]['shared_stage_id']: row['unit']
                                for row in local['scenes'][sid]}
            violations = ([{'scene_id': sid, 'node': instance['platform']['node_order'][0],
                            'time_s': '0.1', 'temperature_degC': ['81', '81'],
                            'limit_degC': scene['maximum_temperature_degC'][0],
                            'formed_at_elapsed_s': float(rank)+.1}]
                          if receipt_kind == 'violation' else [])
            receipt = {'protocol': PARTIAL_PROTOCOL, 'scenario_id': sid,
                'identity': _partial_identity(instance, deployment, accuracy, budget,
                    scene_id=sid, candidate=local, local_deployment=local_deployment),
                'shared_deployment': deepcopy(deployment), 'shared_stage_ids': sorted(deployment),
                'local_deployment': local_deployment, 'unweighted': True,
                'elapsed_s': float(rank)+.2, 'rankable_energy': False,
                'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'},
                'state': 'THERMAL_VIOLATION' if violations else 'UNRESOLVED',
                'reason': 'POINT_WITNESS' if violations else 'MOCK_HEAT_UNRESOLVED',
                'violations': violations}
            receipt['result'] = {'scene_id': sid, 'state': receipt['state'], 'violations': deepcopy(violations)}
            receipt['receipt_sha256'] = _receipt_hash(receipt)
            attempt.update(scene_evaluations={sid: receipt}, reason=receipt['reason'])
        result['seed_attempts'].append(attempt)
    context = {'input_identity_valid': True, 'source_identity_valid': True,
        'current_request_identity_valid': True, 'cutoff_s': 300,
        'hard_errors': [], 'observed_numerical_rejection': False, 'numerical_checks': [],
        'worker_isolation': 'NOT_APPLICABLE', 'prior_requests_complete': True,
        'completion_verified': False, 'root_deadline_confirmed': False,
        'deadline_causal_trace': False, 'last_request': {'state': 'NONE'},
        'safe_receipt': None, 'thermal_unresolved': False}
    record = {'context': context, 'execution': classify_execution(result, context), 'usable_U_J': None}
    save(folder/'input_config.json', config); save(folder/'input_instance.json', instance)
    return record, result, declaration


class TerminalAdapterTests(unittest.TestCase):
    def setUp(self):
        home = ROOT.parents[1]/'.runtime/deadline_terminal_tests'
        home.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='fixture-', dir=home)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.record, self.result, self.declaration = fixture(self.folder)

    def call(self):
        return adapt_no_safe_seed(self.record, self.result, self.declaration, self.folder)

    def assert_blocked(self):
        out = self.call()
        self.assertFalse(out['no_safe_seed_audit']['applied'], out)
        self.assertEqual(out['execution'], self.record['execution'])
        self.assertEqual(out['context'], self.record['context'])
        self.assertIsNone(out['usable_U_J'])
        return out

    def test_three_clean_fixed_rule_failures_are_normal_completion_without_U(self):
        before = deepcopy((self.record, self.result, self.declaration))
        out = self.call()
        self.assertTrue(out['no_safe_seed_audit']['applied'], out)
        self.assertEqual(out['execution']['execution_status'], 'NORMAL_COMPLETION')
        self.assertIsNone(out['execution']['usable_U_J'])
        self.assertFalse(out['execution']['safe_witness_preserved'])
        self.assertFalse(out['execution']['independently_proven_infeasible'])
        self.assertEqual(before, (self.record, self.result, self.declaration))

    def test_saved_matching_strict_thermal_failures_are_not_SAFE_or_infeasible(self):
        self.record, self.result, self.declaration = fixture(self.folder, receipt_kind='violation')
        out = self.call()
        self.assertTrue(out['no_safe_seed_audit']['applied'], out)
        self.assertEqual(out['no_safe_seed_audit']['saved_point_violation_attempts'], 3)
        self.assertIsNone(out['usable_U_J']); self.assertFalse(out['execution']['independently_proven_infeasible'])

    def test_thermal_unknown_remains_unknown(self):
        self.record, self.result, self.declaration = fixture(self.folder, receipt_kind='unknown')
        out = self.assert_blocked()
        self.assertEqual(out['no_safe_seed_audit']['not_applied_reason'], 'THERMAL_OR_NUMERICAL_UNRESOLVED')

    def test_wrong_N1_reason_is_not_linked_completion(self):
        self.result['reason'] = 'NO_COMPLETE_SAFE_N1_SEED'
        self.assert_blocked()

    def test_reason_alone_missing_attempts_cannot_establish_completion(self):
        self.result['seed_attempts'] = []
        self.assert_blocked()

    def test_missing_or_partial_template_exhaustion_blocks(self):
        self.result['seed_attempts'].pop()
        self.assert_blocked()

    def test_duplicate_template_rank_blocks(self):
        self.result['seed_attempts'][2]['construction']['template_rank'] = 2
        self.assert_blocked()

    def test_wrong_OPP_or_constructor_rule_blocks(self):
        for key, value in [('domain_opps', {}), ('rule_version', 'OTHER_CONSTRUCTOR'), ('exclusion', 'CONFIG_REMOVED')]:
            old = self.result['seed_attempts'][0]['construction'][key]
            self.result['seed_attempts'][0]['construction'][key] = value
            self.assert_blocked()
            self.result['seed_attempts'][0]['construction'][key] = old

    def test_invalid_input_or_internal_structural_rejection_is_not_normal_seed_failure(self):
        self.result['seed_attempts'][0]['construction']['details']['reason'] = 'INDEPENDENT_STRUCTURAL_CHECK_REJECTED'
        self.assert_blocked()

    def test_inherited_fault_numeric_identity_and_unknown_are_preserved(self):
        for key, value in [('hard_errors', ['INTERFACE_ERROR']), ('observed_numerical_rejection', True),
                           ('source_identity_valid', False), ('input_identity_valid', None),
                           ('thermal_unresolved', True), ('worker_isolation', 'UNKNOWN')]:
            old = deepcopy(self.record['context'][key])
            self.record['context'][key] = value
            self.assert_blocked()
            self.record['context'][key] = old

    def test_an_existing_technical_classification_is_never_overridden(self):
        self.record['execution']['execution_status'] = 'TECHNICAL_FAILURE_CONFIRMED'
        self.assert_blocked()

    def test_recorded_native_activity_or_pending_request_blocks(self):
        for key, value in [('matlab_worker_ready', True), ('solver_request_attempts', 1),
                           ('session_total_request_count', 1), ('integer_solver_entered', None),
                           ('event_consumer_detached', False), ('phases', [{'phase_index': 1}])]:
            old = deepcopy(self.result[key]); self.result[key] = value
            self.assert_blocked(); self.result[key] = old

    def test_native_artifact_or_fault_latch_blocks(self):
        native = self.folder/'matlab'; native.mkdir(); (native/'ready.json').write_text('{}')
        self.assert_blocked()
        (native/'ready.json').unlink(); self.result['augmented_transport']['latched_unresolved'] = True
        self.assert_blocked()

    def test_original_model_failure_or_archive_failure_blocks(self):
        for key, value in [('technical_state', 'FAILED'), ('error', 'RESOURCE_LIMIT'),
                           ('cleanup_error', 'ERROR'), ('archive_complete', False),
                           ('search_failure_latched', True)]:
            old = self.result.get(key); self.result[key] = value
            self.assert_blocked()
            if old is None: self.result.pop(key)
            else: self.result[key] = old

    def test_budget_expiry_or_late_attempt_does_not_become_normal_early_completion(self):
        self.result['timing']['method_elapsed_s'] = 300.
        self.assert_blocked()
        self.result['timing']['method_elapsed_s'] = 20.
        self.result['seed_attempts'][2]['schedule_completed_at_s'] = 301.
        self.assert_blocked()

    def test_safe_U_or_proof_or_domain_exclusion_is_never_added(self):
        for key, value in [('safe_upper_bound_J', '1'), ('independently_proven_infeasible', True),
                           ('remaining_domain', 'removed'), ('rankable_energy', True)]:
            old = self.result[key]; self.result[key] = value
            self.assert_blocked(); self.result[key] = old

    def test_stored_input_drift_blocks(self):
        instance = json.loads((self.folder/'input_instance.json').read_text(encoding='utf-8'))
        instance['window_ms'] = '401'; save(self.folder/'input_instance.json', instance)
        self.assert_blocked()

    def test_declared_input_and_problem_identity_drift_blocks(self):
        self.declaration['input_sha256'] = 'other'
        self.assert_blocked()

    def test_forged_receipt_hash_or_non_strict_violation_blocks(self):
        self.record, self.result, self.declaration = fixture(self.folder, receipt_kind='violation')
        receipt = next(iter(self.result['seed_attempts'][0]['scene_evaluations'].values()))
        receipt['receipt_sha256'] = 'wrong'
        self.assert_blocked()
        receipt['violations'][0]['temperature_degC'] = ['79', '81']
        receipt['result']['violations'] = deepcopy(receipt['violations'])
        receipt['receipt_sha256'] = _receipt_hash(receipt)
        self.assert_blocked()

    def test_late_violation_receipt_or_mixed_budget_blocks(self):
        self.record, self.result, self.declaration = fixture(self.folder, receipt_kind='violation')
        receipt = next(iter(self.result['seed_attempts'][1]['scene_evaluations'].values()))
        receipt['identity']['budget']['token'] = 'another-invocation'
        receipt['receipt_sha256'] = _receipt_hash(receipt)
        self.assert_blocked()

    def test_no_candidate_evaluator_or_native_entry_is_called(self):
        with patch('thermal.evaluate_piecewise', side_effect=AssertionError('thermal work forbidden')), \
             patch('initial_schedule.iter_initial_candidates', side_effect=AssertionError('constructor forbidden')), \
             patch('matlab_bridge.MatlabSession', side_effect=AssertionError('native forbidden')):
            out = self.call()
        self.assertTrue(out['no_safe_seed_audit']['applied'], out)


if __name__ == '__main__':
    unittest.main()
