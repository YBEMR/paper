"""K140 wrapper-only mocks: no models, heat evaluation, optimizer or process."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from unittest.mock import Mock, patch
from uuid import uuid4
import unittest

import run_linked_pair as pair


class PairTests(unittest.TestCase):
    def setUp(self):
        self.folder = pair.REPO/'.runtime/k140_wrapper_fixtures'/uuid4().hex
        self.folder.mkdir(parents=True)
        self.out = self.folder/'pair'
        self.out.mkdir()
        (self.out/'claims').mkdir()
        pair.save(self.out/'declaration.json', {'protocol': pair.PROTOCOL})
        pair.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0,
            'calls': [], 'method_budget_s_reserved': 0})
        self.d = {'input_sha256': 'instance', 'config_sha256': 'config',
            'raw_config_sha256': 'raw', 'old_opened_by_scene': {'AB': ['b'], 'AC': ['c']},
            'new_opened_by_scene': {'AB': ['a'], 'AC': ['a']},
            'linked_opened_by_scene': {'AB': ['a'], 'AC': ['a']}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(pair, 'GLOBAL_CLAIM', self.folder/'global_claim.json'))

    def condition(self, second=False):
        from scene_adapter import canonical_hash
        from neighborhood import _seed_options
        candidate = self.candidate()
        receipt = self.aggregate(candidate, '11/10', 10.)
        c = {'protocol': pair.LINKED_PROTOCOL if second else pair.N1_PROTOCOL,
            'opened_by_scene': deepcopy(self.d['new_opened_by_scene' if second else 'old_opened_by_scene']),
            'shared_deployment': deepcopy(pair.SHARED), 'source_input_sha256': 'instance',
            'seed_candidate_sha256': canonical_hash(candidate), 'seed_options_by_scene': _seed_options(candidate),
            'seed_receipt': {'fresh': 'receipt', 'identity': {'source_sha256': {'thermal': 'same'},
                'accuracy_sha256': 'same', 'control_policy': 'auto-L'}}, 'seed_receipt_sha256': 'receipt-hash',
            'budget_identity': {'token': 'this-invocation'}}
        if second:
            c.update(warm_candidate=candidate, warm_receipt=receipt,
                warm_candidate_sha256=canonical_hash(candidate),
                warm_receipt_sha256=receipt['receipt_sha256'], warm_options_by_scene=_seed_options(candidate))
        return c

    def candidate(self):
        return {'scenes': {s: [{'stage_id': stage, 'unit': 'CPU1', 'opp': 'L', 'start_ms': '0'}
                              for stage in ('a', 'b' if s == 'AB' else 'c')]
                           for s in ('AB', 'AC')}}

    def aggregate(self, candidate, upper, stamp):
        from scene_adapter import canonical_hash
        return {'state': 'SAFE', 'safe_candidate': deepcopy(candidate),
            'weighted_energy_J': ['0.9' if upper == '1' else '1.05', upper],
            'safe_upper_bound_J': upper, 'scenes': {'AB': {}, 'AC': {}},
            'completed_at_elapsed_s': stamp, 'receipt_sha256': 'warm-receipt' if stamp == 10. else 'final-receipt',
            'identity': {'full_input_sha256': 'instance', 'candidate_sha256': canonical_hash(candidate),
                'budget': {'token': 'this-invocation'}, 'source_sha256': {'thermal': 'same'},
                'accuracy_sha256': 'same', 'control_policy': 'auto-L'}}

    def safe(self, staged=False):
        from scene_adapter import canonical_hash
        candidate = self.candidate()
        aggregate = self.aggregate(candidate, '1', 20.)
        update = {'safe_upper_bound_J': '1', 'weighted_energy_J': ['0.9', '1'],
            'committed_at_s': 20., 'trigger_source': 'solver_callback'}
        result = {**deepcopy(aggregate), 'aggregation': deepcopy(aggregate),
            'reason': 'wall_time_limit', 'budget_exhausted': True,
            'condition': self.condition(), 'global_updates': [update],
            'timing': {'method_elapsed_s': 300., 'cleanup_s': 5.}}
        if staged:
            update['phase_index'] = 2
            warm = self.aggregate(candidate, '11/10', 10.)
            result['global_updates'] = [{'safe_upper_bound_J': '11/10',
                'weighted_energy_J': ['1.05', '11/10'], 'committed_at_s': 10.,
                'trigger_source': 'solver_callback', 'phase_index': 1}, update]
            result['aggregation_attempts'] = [deepcopy(warm), deepcopy(aggregate)]
            result['phases'] = [{'phase_index': i, 'name': 'N1' if i == 1 else 'linked_opp_start_warm_closed',
                'protocol': pair.N1_PROTOCOL if i == 1 else pair.LINKED_PROTOCOL,
                'condition': self.condition(i == 2),
                'opened_by_scene': deepcopy(self.d['old_opened_by_scene' if i == 1 else 'new_opened_by_scene']),
                'failure_latched': False, 'started_at_s': 5. if i == 1 else 15.,
                'completed_at_s': 10. if i == 1 else 300., 'scenes': {}}
                for i in (1, 2)]
            result['search_failure_latched'] = False
            result['augmented_transport'] = {'latched_unresolved': False, 'failure_reasons': [], 'requests': []}
            result['linked_record_contract'] = {
                'linked_opened_by_scene': deepcopy(self.d['new_opened_by_scene']),
                'closed_anchor_candidate_sha256': canonical_hash(candidate),
                'closed_anchor_phase_index': 1, 'closed_anchor_committed_at_s': 10.}
            result['committed_safe_snapshot'] = {**deepcopy(aggregate), 'aggregation': deepcopy(aggregate),
                'phase_index': 2, 'committed_at_s': 20.,
                'scene_receipts': {'AB': {}, 'AC': {}},
                'scene_candidates': {s: {'scenes': {s: deepcopy(candidate['scenes'][s])}} for s in ('AB', 'AC')},
                'scene_sources': {'AB': 'mock', 'AC': 'mock'}}
        return result

    def run_fake(self, side_effect=None):
        call = self.stack.enter_context(patch.object(pair, 'execute', side_effect=side_effect or
            (lambda job, out, d: self.safe(staged=job['id'] != 'old_n1'))))
        self.stack.enter_context(patch.object(pair, 'admission', return_value=self.d))
        return pair.run(self.out), call

    def report(self, current):
        return {'protocol': pair.PRECHECK_PROTOCOL, 'passed': True, 'tests_run': 22,
            'errors': 0, 'failures': 0, 'error': None, 'source_unchanged': True,
            'source_sha256': current, 'historical_artifacts_unchanged': True,
            'native_calls': 0, 'research_calls': 0, 'physical_models': 0,
            'thermal_evaluations': 0, 'blocked_calls': {'mock': 0}}

    def test_01_order_frozen_budget_and_shared_domain(self):
        self.assertEqual([j['id'] for j in pair.jobs()], ['old_n1', 'linked_n1'])
        self.assertEqual((pair.SECONDS, pair.SCENE_SECONDS, pair.CUT), (300, 60, 10))
        self.assertEqual(pair.SHARED, {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'})
        self.assertFalse(pair.rules()['retry_allowed'])
        self.assertFalse(pair.rules()['extend_budget_allowed'])
        self.assertEqual(pair.rules()['second_pass_scene_cap'], 'min(60, remaining_budget/remaining_scenes)')

    def test_02_reuse_155_gate_and_only_two_extras(self):
        gate = pair.read(pair.METHOD_CHECKS)
        current = {**gate['source_sha256'], **{(pair.HERE/n).relative_to(pair.REPO).as_posix(): 'wrapper' for n in pair.WRAPPERS}}
        with patch.object(pair, 'read', return_value=gate):
            pair.method_gate('mock', current)
            changed = dict(current)
            changed[next(iter(gate['source_sha256']))] = 'changed'
            self.assertRaises(ValueError, pair.method_gate, 'mock', changed)
            self.assertRaises(ValueError, pair.method_gate, 'mock', {**current, 'extra.py': 'x'})
        for field, value in [('count', 65), ('historical_artifact_count', 1086), ('source_unchanged', False)]:
            bad = deepcopy(gate)
            bad[field] = value
            with self.subTest(field=field), patch.object(pair, 'read', return_value=bad):
                self.assertRaises(ValueError, pair.method_gate, 'mock', current)
        bad = deepcopy(gate)
        bad['unchanged_inherited_source_count'] = 1
        with patch.object(pair, 'read', return_value=bad):
            self.assertRaises(ValueError, pair.method_gate, 'mock', current)
        bad = deepcopy(gate)
        bad['blocked_calls']['subprocess.Popen'] = 1
        with patch.object(pair, 'read', return_value=bad):
            self.assertRaises(ValueError, pair.method_gate, 'mock', current)

    def test_03_wrapper_gate_binds_current_identities(self):
        report = self.report({'source': 'sha'})
        with patch.object(pair, 'read', return_value=report):
            pair.wrapper_gate('mock', {'source': 'sha'})
            self.assertRaises(ValueError, pair.wrapper_gate, 'mock', {'source': 'changed'})
        report['blocked_calls']['mock'] = 1
        with patch.object(pair, 'read', return_value=report):
            self.assertRaises(ValueError, pair.wrapper_gate, 'mock', {'source': 'sha'})

    def test_04_routes_share_only_copied_options_and_explicit_N1_opening(self):
        original = deepcopy(self.d)
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as old, \
             patch('linked_method.execute_linked_fixed_unit_opp_start', return_value={}) as staged:
            pair.execute(pair.jobs()[0], self.out, self.d)
            old_kw = old.call_args.kwargs
            old_kw['opened_by_scene']['AB'].append('mutated')
            old_kw['shared_deployment']['A.pre'] = 'mutated'
            old_kw['builder_options']['cumulative_precedence'] = True
            pair.execute(pair.jobs()[1], self.out, self.d)
        kw = staged.call_args.kwargs
        self.assertEqual(kw['seconds'], 300)
        self.assertEqual(kw['scene_slice_s'], 60)
        self.assertEqual(kw['builder_options'], pair.BUILD_OPTIONS)
        self.assertEqual(kw['shared_deployment'], pair.SHARED)
        self.assertEqual(kw['opened_by_scene'], original['old_opened_by_scene'])
        self.assertEqual(kw['linked_opened_by_scene'], original['new_opened_by_scene'])
        self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})
        self.assertEqual(self.d, original)
        self.assertRaises(ValueError, pair.execute, {'id': 'x', 'method': 'unknown'}, self.out, self.d)

    def test_05_each_method_owns_fresh_billed_loader(self):
        budget1, budget2 = Mock(), Mock()
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as old, \
             patch('linked_method.execute_linked_fixed_unit_opp_start', return_value={}) as staged, \
             patch('run_neighborhood_diagnostic.fresh_input', return_value=('raw', 'config', 'instance')) as fresh, \
             patch('run_neighborhood_diagnostic.opened_stages', return_value=self.d['old_opened_by_scene']), \
             patch('scene_adapter.canonical_hash', side_effect=lambda value: value):
            pair.execute(pair.jobs()[0], self.out, self.d)
            pair.execute(pair.jobs()[1], self.out, self.d)
            self.assertEqual(old.call_args.args[0](budget1), ('config', 'instance'))
            self.assertEqual(staged.call_args.args[0](budget2), ('config', 'instance'))
        self.assertEqual([c.args for c in fresh.call_args_list], [(budget1,), (budget2,)])
        budget1.check.assert_called_once()
        budget2.check.assert_called_once()

    def test_06_fresh_loader_rejects_every_frozen_identity_mismatch(self):
        for values, opened in [(('changed', 'config', 'instance'), self.d['old_opened_by_scene']),
            (('raw', 'changed', 'instance'), self.d['old_opened_by_scene']),
            (('raw', 'config', 'changed'), self.d['old_opened_by_scene']),
            (('raw', 'config', 'instance'), {'AB': ['different']})]:
            with self.subTest(values=values, opened=opened), \
                 patch('linked_method.execute_linked_fixed_unit_opp_start', return_value={}) as method, \
                 patch('run_neighborhood_diagnostic.fresh_input', return_value=values), \
                 patch('run_neighborhood_diagnostic.opened_stages', return_value=opened), \
                 patch('scene_adapter.canonical_hash', side_effect=lambda value: value):
                pair.execute(pair.jobs()[1], self.out, self.d)
                self.assertRaises(ValueError, method.call_args.args[0], Mock())

    def test_07_prepare_admission_freezes_files_rules_and_hashes(self):
        current = pair.sources()
        checks = self.folder/'wrapper_gate.json'
        pair.save(checks, self.report(current))
        frozen = self.folder/'frozen'
        instance = {'scenarios': [{'id': 'AB', 'stage_instances': [{'id': 'a'}, {'id': 'b'}]}]}
        with patch.object(pair, 'historical_manifest', return_value={}), \
             patch('run_neighborhood_diagnostic.fresh_input', return_value=({'raw': 1}, {'config': 1}, instance)), \
             patch('run_neighborhood_diagnostic.opened_stages', return_value={'AB': ['b']}), \
             patch.object(pair, 'linked_opened', return_value={'AB': ['a']}):
            pair.prepare(frozen, checks, pair.METHOD_CHECKS)
            d = pair.admission(frozen)
            self.assertEqual(len(d['source_sha256']), 157)
            pair.save(frozen/'input_config.json', {'changed': 1})
            self.assertRaises(ValueError, pair.admission, frozen)
            pair.save(frozen/'input_config.json', {'config': 1})
            original = pair.read(frozen/'declaration.json')
            mutated = deepcopy(original)
            mutated['per_method_budget_s'] = 600
            pair.save(frozen/'declaration.json', mutated)
            self.assertRaises(ValueError, pair.admission, frozen)
            pair.save(frozen/'declaration.json', original)
            pair.admission(frozen)

    def test_08_global_and_per_job_claim_consumed_before_calls(self):
        def verify(job, out, declaration):
            self.assertTrue(pair.GLOBAL_CLAIM.exists())
            self.assertTrue((out/'claims'/(job['id']+'.json')).exists())
            ledger = pair.read(out/'ledger.json')
            self.assertEqual(ledger['calls'][-1]['state'], 'RUNNING')
            self.assertEqual(ledger['consumed'], 1 if job['id'] == 'old_n1' else 2)
            return self.safe(staged=job['id'] != 'old_n1')
        okay, call = self.run_fake(verify)
        self.assertTrue(okay)
        self.assertEqual(call.call_count, 2)
        ledger = pair.read(self.out/'ledger.json')
        self.assertEqual((ledger['consumed'], ledger['method_budget_s_reserved']), (2, 600))

    def test_09_completed_run_refuses_without_clock_or_receipt_rewrite(self):
        self.assertTrue(self.run_fake()[0])
        before = {p.name: p.read_bytes() for p in self.out.glob('*.json')}
        with patch.object(pair.time, 'monotonic', side_effect=AssertionError('No repeated clock')):
            self.assertRaises(FileExistsError, pair.run, self.out)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.glob('*.json')})

    def test_10_running_blocked_or_preexisting_job_claim_refuses(self):
        for state in ('RUNNING', 'BLOCKED'):
            pair.save(self.out/'ledger.json', {'state': state, 'consumed': 0, 'calls': []})
            self.assertRaises(FileExistsError, pair.run, self.out)
        pair.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0, 'calls': []})
        pair.save(self.out/'claims/old_n1.json', {'claimed': True})
        self.assertRaises(FileExistsError, pair.run, self.out)

    def test_11_alternate_output_cannot_bypass_global_claim(self):
        self.run_fake()
        other = self.folder/'other'
        other.mkdir()
        pair.save(other/'ledger.json', {'state': 'DECLARED', 'consumed': 0, 'calls': []})
        self.assertRaises(FileExistsError, pair.run, other)

    def test_12_exception_consumes_call_and_stops_remaining_job(self):
        def broken(*args):
            raise RuntimeError('mock interface fault')
        okay, call = self.run_fake(broken)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(pair.read(self.out/'ledger.json')['consumed'], 1)
        self.assertRaises(FileExistsError, pair.run, self.out)

    def test_13_old_technical_fault_stops_and_preserves_SAFE(self):
        result = self.safe()
        result['technical_state'] = 'FAILED'
        okay, call = self.run_fake(lambda *args: result)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)
        row = pair.read(self.out/'ledger.json')['calls'][0]
        self.assertEqual(row['safe_upper_bound_J'], '1')
        self.assertTrue(row['safe_U_preserved_even_if_later_technical_issue'])

    def test_14_staged_transport_fault_and_publication_coverage(self):
        job = pair.jobs()[1]
        for change in ('missing', 'context', 'publication'):
            result = self.safe(staged=True)
            if change == 'missing':
                result.pop('augmented_transport')
            elif change == 'context':
                result['augmented_transport']['latched_unresolved'] = True
            else:
                result['augmented_transport']['requests'] = [{'latched_unresolved': False,
                    'failure_reasons': [], 'callback_publications_complete': False,
                    'expected_callback_numbers': [1, 2], 'checked_callback_numbers': [1]}]
            self.assertTrue(pair.transport_issues(job, result, self.d))
        def failure(job, *args):
            result = self.safe(staged=job['id'] != 'old_n1')
            if job['id'] != 'old_n1':
                result['augmented_transport']['failure_reasons'] = ['mock numeric fault']
            return result
        okay, call = self.run_fake(failure)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(pair.read(self.out/'ledger.json')['calls'][1]['safe_upper_bound_J'], '1')

    def test_15_cleanup_missing_or_incomplete_stops_remaining_job(self):
        def broken(job, out, d):
            result = self.safe()
            result['matlab_worker_ready'] = True
            folder = out/job['id']/'matlab'
            folder.mkdir(parents=True)
            pair.save(folder/'closed.json', {'cleanup_status': 'pending', 'returncode': None})
            return result
        okay, call = self.run_fake(broken)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)

    def test_16_post_call_source_change_stops(self):
        call = self.stack.enter_context(patch.object(pair, 'execute', return_value=self.safe()))
        self.stack.enter_context(patch.object(pair, 'admission', side_effect=[self.d, self.d, ValueError('changed')]))
        self.assertFalse(pair.run(self.out))
        self.assertEqual(call.call_count, 1)

    def test_17_wrong_first_second_domain_order_seed_and_latch_rejected(self):
        def wrong_first(r): r['condition']['opened_by_scene'] = self.d['new_opened_by_scene']
        def wrong_second(r): r['phases'][1]['condition']['opened_by_scene'] = self.d['old_opened_by_scene']
        def wrong_protocol(r): r['phases'][1]['protocol'] = pair.N1_PROTOCOL
        def wrong_seed(r): r['phases'][1]['condition']['seed_candidate_sha256'] = 'historical'
        def wrong_order(r): r['phases'].reverse()
        def latch(r): r.update(search_failure_latched=True, budget_exhausted=False, reason='SCENE_SEARCH_SEQUENCE_COMPLETE')
        for change in (wrong_first, wrong_second, wrong_protocol, wrong_seed, wrong_order, latch):
            result = self.safe(staged=True)
            change(result)
            self.assertTrue(pair.transport_issues(pair.jobs()[1], result, self.d), change.__name__)

    def test_18_budget_stop_without_second_pass_or_with_timeout_latch_is_normal(self):
        result = self.safe(staged=True)
        result['phases'] = result['phases'][:1]
        result['phases'][0]['failure_latched'] = True
        result['search_failure_latched'] = True
        result['global_updates'][-1]['phase_index'] = 1
        result['committed_safe_snapshot']['phase_index'] = 1
        self.assertFalse(pair.transport_issues(pair.jobs()[1], result, self.d))
        result['phases'][0]['scenes'] = {'AB': {'technical_state': 'FAILED'}}
        self.assertTrue(pair.transport_issues(pair.jobs()[1], result, self.d))
        result['phases'] = []
        result['condition'] = None
        result['global_updates'] = result['global_updates'][-1:]
        result['global_updates'][-1]['phase_index'] = 0
        result['committed_safe_snapshot']['phase_index'] = 0
        self.assertFalse(pair.transport_issues(pair.jobs()[1], result, self.d))

    def test_19_complete_ledger_snapshot_update_phase_and_cutoff_coherence(self):
        def u(r): r['aggregation']['safe_upper_bound_J'] = '2'
        def candidate(r): r['committed_safe_snapshot']['safe_candidate'] = {'scenes': {}}
        def scene(r): r['committed_safe_snapshot']['scene_candidates']['AB']['scenes']['AB'] = ['stale']
        def receipt(r): r['committed_safe_snapshot']['scene_receipts']['AB'] = {'stale': True}
        def budget(r): r['phases'][1]['condition']['budget_identity'] = {'token': 'other-invocation'}
        def phase(r): r['global_updates'][0]['phase_index'] = 3
        def clock(r): r['global_updates'][0]['committed_at_s'] = 300.
        for change in (u, candidate, scene, receipt, budget, phase, clock):
            result = self.safe(staged=True)
            change(result)
            self.assertTrue(pair.transport_issues(pair.jobs()[1], result, self.d), change.__name__)

    def test_20_observer_logs_actual_complete_U_and_phase(self):
        captured = io.StringIO()
        with patch('linked_method.execute_linked_fixed_unit_opp_start', return_value={}) as method:
            pair.execute(pair.jobs()[1], self.out, self.d)
            with redirect_stdout(captured):
                method.call_args.kwargs['on_global_update']({}, {'phase_index': 2,
                    'committed_at_s': 123.5, 'safe_upper_bound_J': '7.25', 'trigger_source': 'callback'})
        row = json.loads(captured.getvalue())
        self.assertEqual((row['phase_index'], row['elapsed_s'], row['U_J']), (2, 123.5, '7.25'))

    def test_21_external_clock_includes_validation_primary_tail_separates_cleanup(self):
        clock = [0.]
        real_save = pair.save
        def archive(path, value):
            real_save(path, value)
            clock[0] += 2.
        def call(job, *args):
            clock[0] += 10.
            return self.safe(staged=job['id'] != 'old_n1')
        self.stack.enter_context(patch.object(pair.time, 'monotonic', side_effect=lambda: clock[0]))
        self.stack.enter_context(patch.object(pair, 'save', side_effect=archive))
        self.assertTrue(self.run_fake(call)[0])
        timing = pair.read(self.out/'claims/old_n1_wrapper_timing.json')
        self.assertEqual(timing['wrapper_call_and_primary_archive_wall_s'], 14.)
        self.assertFalse(timing['clock_receipt_own_serialization_included'])
        actual = pair.timing_components(311., {'timing': {
            'method_elapsed_excluding_cleanup_s': 299., 'cleanup_s': 5.}})
        self.assertEqual((actual['method_stop_elapsed_s'], actual['cleanup_s'],
            actual['unattributed_wrapper_archive_overhead_s']), (299., 5., 7.))

    def test_22_phase_quality_keeps_actual_global_updates_and_unclipped_native_timing(self):
        result = self.safe(staged=True)
        result['phases'][1]['scenes'] = {'AB': {'search_started_at_s': 15.,
            'search_returned_at_s': 83., 'scene_slice_s': 60.,
            'solver_result': {'elapsed_s': 68., 'objective': 0.01}}}
        rows = pair.phase_quality(result)
        self.assertEqual(rows[1]['global_updates'][0]['safe_upper_bound_J'], '1')
        self.assertEqual(rows[1]['global_updates'][0]['committed_at_s'], 20.)
        self.assertEqual(rows[1]['scene_timing_and_solver_records']['AB']['solver_result']['elapsed_s'], 68.)
        rows[1]['global_updates'][0]['safe_upper_bound_J'] = 'mutated'
        self.assertEqual(result['global_updates'][-1]['safe_upper_bound_J'], '1')
        old = pair.phase_quality(self.safe())
        self.assertEqual(old[0]['name'], 'N1')
        self.assertEqual(old[0]['completed_at_s'], 300.)

    def test_23_warm_anchor_matches_last_complete_first_pass_not_seed_or_local(self):
        result = self.safe(staged=True)
        self.assertFalse(pair.transport_issues(pair.jobs()[1], result, self.d))
        for change in ('time', 'receipt', 'hash', 'phase', 'budget', 'source', 'candidate_identity'):
            bad = deepcopy(result)
            condition = bad['phases'][1]['condition']
            if change == 'time': condition['warm_receipt']['completed_at_elapsed_s'] = 9.
            elif change == 'receipt': bad['aggregation_attempts'] = []
            elif change == 'hash': condition['warm_candidate_sha256'] = 'historical'
            elif change == 'phase': bad['linked_record_contract']['closed_anchor_phase_index'] = 0
            elif change == 'budget': condition['warm_receipt']['identity']['budget'] = {'token': 'other'}
            elif change == 'source': condition['warm_receipt']['identity']['source_sha256'] = {'thermal': 'changed'}
            else: condition['warm_receipt']['identity']['candidate_sha256'] = 'other'
            with self.subTest(change=change):
                self.assertTrue(pair.linked_anchor_issues(bad, bad['phases'], self.d))

    def test_24_closed_choices_and_all_units_are_checked_in_complete_snapshot(self):
        for field, value in (('opp', 'H'), ('start_ms', '5'), ('unit', 'CPU2')):
            result = self.safe(staged=True)
            result['committed_safe_snapshot']['safe_candidate']['scenes']['AB'][1][field] = value
            self.assertTrue(pair.linked_anchor_issues(result, result['phases'], self.d))
        result = self.safe(staged=True)
        result['committed_safe_snapshot']['safe_candidate']['scenes']['AB'][0]['opp'] = 'H'
        self.assertFalse(pair.linked_anchor_issues(result, result['phases'], self.d))

    def test_25_latest_uncommitted_scene_does_not_replace_warm_generation(self):
        result = self.safe(staged=True)
        result['scenes'] = {'AB': {'latest_local_candidate': {'not': 'complete generation'}}}
        self.assertFalse(pair.transport_issues(pair.jobs()[1], result, self.d))
        result['linked_record_contract']['linked_opened_by_scene']['AB'] = ['b']
        self.assertTrue(pair.transport_issues(pair.jobs()[1], result, self.d))

    def test_26_mask_derived_only_from_fresh_stage_labels(self):
        instance = {'scenarios': [{'id': 'AB', 'stage_instances': [
            {'id': 'AB:'+label, 'shared_stage_id': label}
            for label in ('A.pre', 'A.main', 'A.post', 'B.pre', 'B.main', 'B.post')]}]}
        self.assertEqual(pair.linked_opened(instance), {'AB': ['AB:A.main', 'AB:A.post', 'AB:A.pre', 'AB:B.pre']})
        instance['scenarios'][0]['stage_instances'].pop()
        self.assertRaises(ValueError, pair.linked_opened, instance)

    def test_27_checkpoint_prefix_can_precede_final_transport_summary(self):
        result = self.safe(staged=True)
        result['augmented_transport']['requests'] = [{'latched_unresolved': False,
            'failure_reasons': [], 'callback_publications_complete': True,
            'expected_callback_numbers': [1], 'checked_callback_numbers': [1],
            'checkpoint_numeric_gate_count': 1, 'terminal_numeric_gate_count': 2}]
        self.assertFalse(pair.transport_issues(pair.jobs()[1], result, self.d))
        result['augmented_transport']['requests'][0]['failure_reasons'] = ['terminal gate rejected']
        self.assertTrue(pair.transport_issues(pair.jobs()[1], result, self.d))

    def test_28_linked_mask_copied_and_not_forwarded_to_old_N1(self):
        original = deepcopy(self.d)
        with patch('neighborhood_method.execute_n1_neighborhood', return_value={}) as old, \
             patch('linked_method.execute_linked_fixed_unit_opp_start', return_value={}) as linked:
            pair.execute(pair.jobs()[0], self.out, self.d)
            pair.execute(pair.jobs()[1], self.out, self.d)
            self.assertNotIn('linked_opened_by_scene', old.call_args.kwargs)
            linked.call_args.kwargs['linked_opened_by_scene']['AB'].append('changed')
        self.assertEqual(self.d, original)


if __name__ == '__main__':
    unittest.main()
