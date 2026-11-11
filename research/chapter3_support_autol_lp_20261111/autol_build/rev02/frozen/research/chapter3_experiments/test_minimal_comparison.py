"""K141 wrapper-only mocks. No optimizer, physical model, heat or subprocess."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from unittest.mock import Mock, patch
from uuid import uuid4
import unittest

import run_minimal_comparison as comparison
import test_linked_pair as linked_fixtures


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.folder = comparison.REPO/'.runtime/k141_wrapper_fixtures'/uuid4().hex
        self.folder.mkdir(parents=True)
        self.out = self.folder/'comparison'
        self.out.mkdir()
        (self.out/'claims').mkdir()
        comparison.save(self.out/'declaration.json', {'protocol': comparison.PROTOCOL})
        comparison.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0,
            'calls': [], 'method_budget_s_reserved': 0})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(comparison, 'GLOBAL_CLAIM', self.folder/'global_claim.json'))
        self.fixture = linked_fixtures.PairTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.d = deepcopy(self.fixture.d)
        self.entries = {k: Mock(name=k, return_value={}) for k in
                        ('whole', 'linked', 'heuristic', 'builder', 'session')}

    def safe(self, job):
        if job['method'] == 'linked_fixed_unit_opp_start':
            return self.fixture.safe(staged=True)
        receipt = self.fixture.aggregate(self.fixture.candidate(), '1', 20.)
        return {'state': 'SAFE', 'safe_candidate': receipt['safe_candidate'],
            'safe_upper_bound_J': '1', 'evaluation': receipt, 'reason': 'wall_time_limit',
            'first_initial_safe_s': 20. if job['method'] == 'milp' else None,
            'first_safe_at_s': 20. if job['method'] != 'milp' else None,
            'timing': {'method_elapsed_s': 300., 'cleanup_s': 2.}}

    def run_fake(self, effect=None):
        self.stack.enter_context(patch.object(comparison, 'admission', return_value=self.d))
        self.stack.enter_context(patch.object(comparison, 'common_entry_points', return_value=self.entries))
        called = self.stack.enter_context(patch.object(comparison, 'execute', side_effect=effect or
            (lambda job, out, d, entries: self.safe(job))))
        return comparison.run(self.out, execution_authorized=True), called

    def report(self, current):
        return {'protocol': comparison.PRECHECK_PROTOCOL, 'passed': True, 'tests_run': 25,
            'errors': 0, 'failures': 0, 'error': None, 'source_unchanged': True,
            'source_sha256': current, 'native_calls': 0, 'research_calls': 0,
            'physical_models': 0, 'thermal_evaluations': 0, 'blocked_calls': {'mock': 0}}

    def test_01_fixed_job_order_and_scope(self):
        self.assertEqual([j['id'] for j in comparison.jobs()], ['whole_milp', 'linked_n1', 'heft', 'sa101'])
        self.assertEqual(comparison.jobs()[-1]['seed'], 101)
        self.assertEqual((comparison.SECONDS, comparison.SCENE_SECONDS, comparison.CUT), (300, 60, 10))
        r = comparison.rules()
        self.assertFalse(r['retry_allowed'])
        self.assertFalse(r['extend_budget_allowed'])
        self.assertTrue(r['run_requires_separate_execution_authorization'])
        self.assertEqual(r['method_call_limit'], 4)

    def test_02_159_source_gate_and_122_inherited_sources(self):
        current = comparison.sources()
        gate = comparison.method_gate(current)
        self.assertEqual((gate['current_source_count'], gate['K140_source_count'],
                          gate['K127_unchanged_count']), (159, 157, 122))
        changed = deepcopy(current)
        changed[next(iter(comparison.read(comparison.BASE_DECLARATION)['source_sha256']))] = 'changed'
        self.assertRaises(ValueError, comparison.method_gate, changed)
        self.assertRaises(ValueError, comparison.method_gate, {**current, 'another.py': 'x'})

    def test_03_old_gate_hash_and_baseline_identity_must_match(self):
        original = comparison.read
        def mutate(path):
            value = original(path)
            if path == comparison.BASE_DECLARATION:
                value['wrapper_checks_sha256'] = 'changed'
            return value
        with patch.object(comparison, 'read', side_effect=mutate):
            self.assertRaises(ValueError, comparison.method_gate, comparison.sources())

    def test_04_wrapper_gate_requires_source_and_zero_forbidden(self):
        report = self.report({'source': 'same'})
        with patch.object(comparison, 'read', return_value=report):
            comparison.wrapper_gate('mock', {'source': 'same'})
            self.assertRaises(ValueError, comparison.wrapper_gate, 'mock', {'source': 'different'})
            report['blocked_calls']['mock'] = 1
            self.assertRaises(ValueError, comparison.wrapper_gate, 'mock', {'source': 'same'})

    def test_05_whole_dispatch_exact_flags_and_conditional_feedback(self):
        comparison.execute(comparison.jobs()[0], self.out, self.d, self.entries)
        kw = self.entries['whole'].call_args.kwargs
        self.assertEqual(kw['seconds'], 300)
        self.assertEqual(kw['feedback_kind'], 'conditional')
        self.assertEqual(kw['model_builder'].func, self.entries['builder'])
        self.assertEqual(kw['model_builder'].keywords, {'prefilter_deadlines': True, 'cumulative_precedence': False})
        self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})
        self.assertNotIn('shared_deployment', kw)
        self.assertNotIn('opened_by_scene', kw)

    def test_06_linked_dispatch_dual_anchor_masks_and_copied_options(self):
        original = deepcopy(self.d)
        comparison.execute(comparison.jobs()[1], self.out, self.d, self.entries)
        kw = self.entries['linked'].call_args.kwargs
        self.assertEqual(kw['shared_deployment'], comparison.SHARED)
        self.assertEqual(kw['opened_by_scene'], self.d['old_opened_by_scene'])
        self.assertEqual(kw['linked_opened_by_scene'], self.d['new_opened_by_scene'])
        self.assertEqual(kw['builder_options'], comparison.BUILD_OPTIONS)
        self.assertEqual((kw['seconds'], kw['scene_slice_s']), (300, 60))
        kw['opened_by_scene']['AB'].append('different')
        kw['shared_deployment']['A.pre'] = 'different'
        self.assertEqual(self.d, original)
        self.assertEqual(comparison.SHARED['A.pre'], 'CPU1')

    def test_07_heuristic_dispatch_no_free_fixed_deployment_or_seed(self):
        for job in comparison.jobs()[2:]:
            comparison.execute(job, self.out, self.d, self.entries)
            kw = self.entries['heuristic'].call_args.kwargs
            self.assertEqual(kw, dict(method=job['method'], seconds=300,
                seed=job.get('seed'), allow_auto_low=True))
            self.assertNotIn('shared_deployment', kw)
            self.assertNotIn('builder_options', kw)

    def test_08_billed_loaders_are_fresh_and_own_each_budget(self):
        budgets, loaders = [], []
        with patch('run_neighborhood_diagnostic.fresh_input', return_value=('raw', 'config', 'instance')) as fresh, \
             patch('run_neighborhood_diagnostic.opened_stages', return_value=self.d['old_opened_by_scene']), \
             patch('scene_adapter.canonical_hash', side_effect=lambda x: x), \
             patch('partial_bounds.independent_lower_bound', return_value={'L0': 'exact'}) as lower:
            for job in comparison.jobs():
                comparison.execute(job, self.out, self.d, self.entries)
                route = 'whole' if job['method'] == 'milp' else 'linked' if job['method'].startswith('linked') else 'heuristic'
                loaders.append(self.entries[route].call_args.args[0])
                budget = Mock()
                budget.phase.return_value = nullcontext()
                budgets.append(budget)
            for loader, budget in zip(loaders, budgets):
                self.assertEqual(loader(budget), ('config', 'instance'))
        self.assertEqual([c.args for c in fresh.call_args_list], [(b,) for b in budgets])
        lower.assert_called_once_with('instance', None, budgets[0])
        budgets[0].phase.assert_called_once_with('comparison_independent_lower_bound')
        self.assertEqual(len(set(map(id, loaders))), 4)
        for budget in budgets:
            budget.check.assert_called_once()

    def test_09_loader_rejects_every_input_and_opening_mismatch(self):
        for values, opened in [(('bad', 'config', 'instance'), self.d['old_opened_by_scene']),
            (('raw', 'bad', 'instance'), self.d['old_opened_by_scene']),
            (('raw', 'config', 'bad'), self.d['old_opened_by_scene']),
            (('raw', 'config', 'instance'), {'AB': ['bad']})]:
            with patch('run_neighborhood_diagnostic.fresh_input', return_value=values), \
                 patch('run_neighborhood_diagnostic.opened_stages', return_value=opened), \
                 patch('scene_adapter.canonical_hash', side_effect=lambda x: x):
                comparison.execute(comparison.jobs()[1], self.out, self.d, self.entries)
                self.assertRaises(ValueError, self.entries['linked'].call_args.args[0], Mock())

    def test_10_unknown_job_rejected_before_routes(self):
        self.assertRaises(ValueError, comparison.execute, {'id': 'unknown', 'method': 'heft'},
                          self.out, self.d, self.entries)
        self.entries['heuristic'].assert_not_called()

    def test_11_claims_consumed_before_each_call_and_order_fixed(self):
        def check(job, out, d, entries):
            self.assertTrue(comparison.GLOBAL_CLAIM.exists())
            self.assertTrue((out/'claims'/(job['id']+'.json')).is_file())
            ledger = comparison.read(out/'ledger.json')
            self.assertEqual(ledger['calls'][-1]['state'], 'RUNNING')
            self.assertEqual(ledger['consumed'], comparison.jobs().index(job)+1)
            return self.safe(job)
        okay, call = self.run_fake(check)
        self.assertTrue(okay)
        self.assertEqual([c.args[0] for c in call.call_args_list], comparison.jobs())
        ledger = comparison.read(self.out/'ledger.json')
        self.assertEqual((ledger['state'], ledger['consumed'], ledger['method_budget_s_reserved']),
                          ('COMPLETED', 4, 1200))

    def test_12_completed_run_refuses_before_clocks_or_rewrite(self):
        self.assertTrue(self.run_fake()[0])
        before = {p.name: p.read_bytes() for p in self.out.glob('*.json')}
        with patch.object(comparison.time, 'monotonic', side_effect=AssertionError('No clock on replay')):
            self.assertRaises(FileExistsError, comparison.run, self.out, execution_authorized=True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.glob('*.json')})

    def test_13_claim_or_blocked_or_running_refuses(self):
        for state in ('BLOCKED', 'RUNNING'):
            comparison.save(self.out/'ledger.json', {'state': state, 'consumed': 0, 'calls': []})
            self.assertRaises(FileExistsError, comparison.run, self.out, execution_authorized=True)
        comparison.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0, 'calls': []})
        comparison.save(self.out/'claims/heft.json', {'claimed': True})
        self.assertRaises(FileExistsError, comparison.run, self.out, execution_authorized=True)

    def test_14_alternate_output_cannot_bypass_global_claim(self):
        self.assertTrue(self.run_fake()[0])
        other = self.folder/'another'
        other.mkdir()
        comparison.save(other/'ledger.json', {'state': 'DECLARED', 'consumed': 0, 'calls': []})
        self.assertRaises(FileExistsError, comparison.run, other, execution_authorized=True)

    def test_15_no_execution_without_separate_explicit_opt_in(self):
        with patch.object(comparison.time, 'monotonic', side_effect=AssertionError('No method clock')):
            self.assertRaises(PermissionError, comparison.run, self.out)
        self.assertFalse(comparison.GLOBAL_CLAIM.exists())
        self.assertEqual(comparison.read(self.out/'ledger.json')['consumed'], 0)

    def test_16_interface_fault_stops_remaining_and_keeps_existing_U(self):
        def fail(job, out, d, entries):
            value = self.safe(job)
            value.update(reason='INTERFACE_ERROR', error='injected')
            return value
        okay, call = self.run_fake(fail)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)
        ledger = comparison.read(self.out/'ledger.json')
        self.assertEqual((ledger['state'], ledger['consumed']), ('BLOCKED', 1))
        self.assertEqual(ledger['calls'][0]['safe_upper_bound_J'], '1')

    def test_17_exception_consumes_without_retry(self):
        okay, call = self.run_fake(RuntimeError('injected'))
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)
        self.assertIn('injected', comparison.read(self.out/'ledger.json')['calls'][0]['error'])

    def test_18_whole_native_numerical_and_status_faults_kept(self):
        for row in [{'status': 'ERROR'}, {'status': 'WORKER_EXITED'},
                    {'numerical_consistency': {'state': 'NUMERICAL_ADMISSION_STATUS_CONFLICT'}}]:
            value = self.safe(comparison.jobs()[0])
            value['rounds'] = [row]
            self.assertTrue(comparison.technical_issues(comparison.jobs()[0], value, self.d))

    def test_19_linked_transport_uses_known_K140_job_identity(self):
        value = self.safe(comparison.jobs()[1])
        self.assertEqual(comparison.technical_issues(comparison.jobs()[1], value, self.d), [])
        value['augmented_transport']['latched_unresolved'] = True
        self.assertTrue(comparison.technical_issues(comparison.jobs()[1], value, self.d))

    def test_20_normal_deadline_not_a_technical_failure(self):
        self.assertTrue(self.run_fake()[0])
        ledger = comparison.read(self.out/'ledger.json')
        self.assertEqual([r['state'] for r in ledger['calls']], ['COMPLETED']*4)
        self.assertTrue(all(r['reason'] == 'wall_time_limit' for r in ledger['calls']))

    def test_21_first_complete_safe_times_keep_different_lifecycles(self):
        whole, linked, heft, sa = comparison.jobs()
        value = self.safe(whole)
        value.update(first_safe_at_s=1., first_initial_safe_s=20.,
                     solver_diagnostic={'diagnostic': {'first_safe_receipt_s': 25.,
                         'first_candidate_received_s': 23., 'first_legal_candidate_s': 24.}})
        self.assertEqual(comparison.evidence_summary(whole, value)['first_complete_safe_at_s'], 20.)
        self.assertEqual(comparison.evidence_summary(whole, value)['first_candidate_at_s'], 23.)
        self.assertEqual(comparison.evidence_summary(whole, value)['first_legal_candidate_at_s'], 24.)
        value['first_initial_safe_s'] = None
        self.assertEqual(comparison.evidence_summary(whole, value)['first_complete_safe_at_s'], 25.)
        value['solver_diagnostic']['diagnostic']['first_safe_receipt_s'] = 301.
        self.assertIsNone(comparison.evidence_summary(whole, value)['first_complete_safe_at_s'])
        value['diagnostic'] = {'first_safe_receipt_s': 26.}
        self.assertEqual(comparison.evidence_summary(whole, value)['first_complete_safe_at_s'], 26.)
        for job in (linked, heft, sa):
            value = self.safe(job)
            value['first_safe_at_s'] = 29.
            self.assertEqual(comparison.evidence_summary(job, value)['first_complete_safe_at_s'], 29.)

    def test_22_local_first_safe_and_solver_fval_not_global_quality(self):
        job = comparison.jobs()[1]
        value = self.safe(job)
        value['first_safe_at_s'] = 20.
        value['scenes'] = {'AB': {'first_safe_at_s': 1., 'solver_result': {'fval': -999}}}
        summary = comparison.evidence_summary(job, value)
        self.assertEqual(summary['first_complete_safe_at_s'], 20.)
        self.assertEqual(summary['safe_upper_bound_J'], '1')
        self.assertEqual(summary['first_safe_detail']['local_scene_first_safe_at_s'], {'AB': 1.})

    def test_23_common_imports_external_clock_and_cleanup_not_relabelled(self):
        okay, call = self.run_fake()
        self.assertTrue(okay)
        imported = comparison.read(self.out/'runtime_common_imports.json')
        self.assertEqual(imported['research_calls'], 0)
        self.assertIn('actual internal lazy work remains billed', imported['scope'])
        wrapper = comparison.read(self.out/'wrapper_timing.json')
        self.assertGreaterEqual(wrapper['wrapper_run_through_primary_archives_wall_s'],
                                wrapper['common_entry_import_wall_s'])
        for job in comparison.jobs():
            clock = comparison.read(self.out/'claims'/(job['id']+'_wrapper_timing.json'))
            self.assertEqual(clock['method_stop_elapsed_s'], 300.)
            self.assertEqual(clock['cleanup_s'], 2. if job['id'] != 'linked_n1' else 5.)
            self.assertTrue(clock['includes_method_tail_serialization_and_wrapper_validation_and_primary_archives'])

    def test_24_cleanup_anomaly_stops_after_formed_safe_U(self):
        def fail(job, out, d, entries):
            folder = out/job['id']/'matlab'
            folder.mkdir(parents=True)
            comparison.save(folder/'closed.json', {'cleanup_pending_pid': 123, 'returncode': None})
            return self.safe(job)
        okay, call = self.run_fake(fail)
        self.assertFalse(okay)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(comparison.read(self.out/'ledger.json')['calls'][0]['safe_upper_bound_J'], '1')

    def test_25_prepare_and_admission_bind_input_source_rules(self):
        from scene_adapter import canonical_hash
        current = comparison.sources()
        checks = self.folder/'wrapper_checks.json'
        comparison.save(checks, self.report(current))
        values = ({'raw': 'fixture'}, {'config': 'fixture'}, {'instance': 'fixture'})
        identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                              map(canonical_hash, values)))
        basis = {'prerequisite_sha256': {'mock': 'sha'}}
        frozen = self.folder/'frozen'
        with patch.object(comparison, 'INPUT_IDENTITIES', identities), \
             patch.object(comparison, 'method_gate', return_value=basis), \
             patch.object(comparison, 'common_entry_points', return_value=self.entries), \
             patch('run_neighborhood_diagnostic.fresh_input', return_value=values), \
             patch('run_neighborhood_diagnostic.opened_stages', return_value=self.d['old_opened_by_scene']), \
             patch.object(comparison.linked, 'linked_opened', return_value=self.d['new_opened_by_scene']):
            comparison.prepare(frozen, checks)
            self.assertEqual(len(comparison.admission(frozen)['source_sha256']), 159)
            comparison.save(frozen/'input_config.json', {'changed': True})
            self.assertRaises(ValueError, comparison.admission, frozen)
            comparison.save(frozen/'input_config.json', values[1])
            declaration = comparison.read(frozen/'declaration.json')
            declaration['per_method_budget_s'] = 600
            comparison.save(frozen/'declaration.json', declaration)
            self.assertRaises(ValueError, comparison.admission, frozen)


if __name__ == '__main__':
    unittest.main()
