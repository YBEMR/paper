"""K152 pure handoff/clock/identity checks; no solver or physical evaluation."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_four_method_comparison as runner


def instance():
    return {'window_ms': '400', 'platform': {'node_order': ['CPU', 'GPU', 'NPU']},
        'scenarios': [{'id': 'A'+other, 'application_pair': ['A', other], 'weight': '1/2',
            'maximum_temperature_degC': ['80', '80', '80'],
            'requests': [{'copy_index': 1}, {'copy_index': 1}],
            'stage_instances': [{'id': owner+'.'+part, 'shared_stage_id': owner+'.'+part}
                for owner in ('A', other) for part in ('pre', 'main', 'post')]}
            for other in ('B', 'C')]}


def values():
    return {'raw': 1}, {'config': 1}, instance()


def identities():
    return dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                    map(runner.canonical, values())))


def declaration():
    from run_neighborhood_diagnostic import opened_stages
    return {**identities(), 'input_identities': identities(),
        'first_opened_by_scene': opened_stages(instance()),
        'linked_opened_by_job': {j['id']: runner.masks(instance(), j['opened_count'])
            for j in runner.jobs() if j.get('opened_count')},
        'scene_spec': runner.scene_spec(instance())}


def check_report(current):
    return {'protocol': runner.CHECK_PROTOCOL, 'passed': True, 'tests_run': 24,
        'errors': 0, 'failures': 0, 'skipped': 0, 'error': None,
        'source_sha256': current, 'source_unchanged': True,
        'blocked_calls': {'mock': 0}, 'research_calls': 0, 'native_calls': 0,
        'physical_models': 0, 'thermal_evaluations': 0}


class Fixture(unittest.TestCase):
    def setUp(self):
        root = runner.REPO/'.runtime/k152_unit_fixtures'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root/'comparison'
        self.out.mkdir()
        (self.out/'claims').mkdir()
        runner.save(self.out/'declaration.json', declaration())
        runner.save(self.out/'ledger.json', {'protocol': runner.PROTOCOL,
            'state': 'DECLARED', 'consumed': 0, 'calls': [], 'reserved_method_budget_s': 0})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runner, 'TARGET', self.out))
        self.stack.enter_context(patch.object(runner, 'GLOBAL_CLAIM', self.root/'single_use.json'))
        self.d = declaration()
        self.entries = {k: Mock(name=k, return_value={})
            for k in ('whole', 'linked', 'heuristic', 'builder', 'session')}

    @staticmethod
    def records(job, result, d, folder, *, input_valid, source_valid, errors=None):
        error = bool(errors) or input_valid is not True or source_valid is not True
        status = 'TECHNICAL_FAILURE_CONFIRMED' if error else result.get('mock_status', 'NORMAL_COMPLETION')
        return {'execution': {'execution_status': status}, 'usable_U_J': result.get('U_J'),
            'context': {'input_identity_valid': input_valid, 'source_identity_valid': source_valid},
            'completion_metrics': {'original_safe_receipt_only': True}}

    def run_fake(self, effect=None, audit=None):
        self.stack.enter_context(patch.object(runner, 'admission', return_value=self.d))
        self.stack.enter_context(patch.object(runner, 'entry_points', return_value=self.entries))
        self.stack.enter_context(patch.object(runner, 'result_records', side_effect=audit or self.records))
        def fake_execute(job, out, d, entries):
            (out/job['id']).mkdir(parents=True, exist_ok=True)
            if isinstance(effect, BaseException): raise effect
            return effect(job, out, d, entries) if effect else ({'U_J': '1'}, {'input_verified': True})
        execute = self.stack.enter_context(patch.object(runner, 'execute', side_effect=fake_execute))
        return runner.run(self.out, execution_authorized=True), execute


class ScopeAndGateTests(Fixture):
    def test_01_exact_four_order_once_300s(self):
        self.assertEqual([j['id'] for j in runner.jobs()],
            ['whole_milp', 'anchor_linked4', 'heft', 'sa101'])
        self.assertEqual((runner.SECONDS, runner.SCENE_SECONDS, runner.CUT), (300, 60, 10))
        r = runner.rules()
        self.assertEqual(r['method_call_limit'], 4)
        self.assertFalse(r['retry_allowed'])
        self.assertFalse(r['extend_budget_allowed'])
        self.assertFalse(r['candidate_cache_or_witness_shared'])
        self.assertTrue(r['no_historical_witness_initialisation'])
        self.assertTrue(r['preeliminate_closed_anchors_linked_second_pass_only'])

    def test_02_linked_four_open_two_closed_full_three_stage_chains(self):
        opened = runner.masks(instance(), 4)
        for other in ('B', 'C'):
            all_ids = {s['id'] for s in instance()['scenarios'][other == 'C']['stage_instances']}
            self.assertEqual(set(opened['A'+other]), {'A.pre', 'A.main', 'A.post', other+'.pre'})
            self.assertEqual(all_ids-set(opened['A'+other]), {other+'.main', other+'.post'})
        for bad in (0, 3, 6):
            with self.assertRaises(ValueError): runner.masks(instance(), bad)
        broken = instance(); broken['scenarios'][0]['stage_instances'].pop()
        with self.assertRaises(ValueError): runner.masks(broken, 4)

    def test_03_output_path_cannot_change_comparison_identity(self):
        self.assertEqual(runner.local(self.out), self.out.resolve())
        for invalid in (self.root/'alternate', runner.REPO.parent/'outside'):
            with self.assertRaises(ValueError): runner.local(invalid)

    def test_04_source_gate_binds_174_inherited_and_four_new_files(self):
        base = runner.read(runner.BASE)['source_sha256']
        extra = {(runner.HERE/n).relative_to(runner.REPO).as_posix(): 'new' for n in runner.NEW}
        current = {**base, **extra}
        with patch.object(runner, 'sources', return_value=current):
            self.assertEqual(runner.source_gate(), current)
            key = next(iter(base)); current[key] = 'changed'
            with self.assertRaises(ValueError): runner.source_gate()
            current[key] = base[key]; current['unexpected.py'] = 'extra'
            with self.assertRaises(ValueError): runner.source_gate()

    def test_05_inherited_gate_and_cutoff_certificate_are_not_optional(self):
        original = runner.read
        base = original(runner.BASE)['source_sha256']
        current = {**base, **{(runner.HERE/n).relative_to(runner.REPO).as_posix(): 'new' for n in runner.NEW}}
        for target, field, wrong in ((runner.METHOD_GATE, 'passed', False),
            (runner.METHOD_GATE, 'count', 79), (runner.CUTOFF_CHECKS, 'adapter_sha256', 'wrong'),
            (runner.CUTOFF_CHECKS, 'source_sha256', {})):
            with self.subTest(field=field, target=target):
                def changed(path, target=target, field=field, wrong=wrong):
                    data = original(path)
                    if Path(path) == target: data[field] = wrong
                    return data
                with patch.object(runner, 'sources', return_value=current), patch.object(runner, 'read', side_effect=changed):
                    with self.assertRaises(ValueError): runner.source_gate()

    def test_06_precheck_requires_matching_source_no_forbidden_calls(self):
        report = check_report({'one.py': 'same'})
        with patch.object(runner, 'read', return_value=report):
            runner.check_gate('mock', {'one.py': 'same'})
            with self.assertRaises(ValueError): runner.check_gate('mock', {'one.py': 'different'})
            for field, wrong in (('skipped', 1), ('research_calls', 1), ('native_calls', 1),
                ('thermal_evaluations', 1), ('source_unchanged', False), ('tests_run', 0)):
                with self.subTest(field=field):
                    saved = report[field]; report[field] = wrong
                    with self.assertRaises(ValueError): runner.check_gate('mock', {'one.py': 'same'})
                    report[field] = saved
            report['blocked_calls']['mock'] = 1
            with self.assertRaises(ValueError): runner.check_gate('mock', {'one.py': 'same'})

    def test_07_prepare_and_admission_bind_input_source_and_protocol(self):
        frozen = self.root/'frozen'
        protocol = self.root/'protocol.md'; protocol.write_text('Frozen K152 fixture.\n', encoding='utf-8')
        shutil.copyfile(runner.PROTOCOL_FILE.with_name('launch_once.py'), self.root/'launch_once.py')
        path = Path(__file__).resolve(); name = path.relative_to(runner.REPO).as_posix()
        current = {name: runner.sha(path)}
        checks = self.root/'checks.json'; runner.save(checks, check_report(current))
        original_read = runner.read
        def read(path):
            if Path(path) == runner.BASE: return {'input_identities': identities()}
            return original_read(path)
        with patch.object(runner, 'TARGET', frozen), patch.object(runner, 'PROTOCOL_FILE', protocol), \
             patch.object(runner, 'source_gate', return_value=current), \
             patch.object(runner, 'fresh_input', return_value=values()), \
             patch('run_minimal_comparison.INPUT_IDENTITIES', identities()), \
             patch.object(runner, 'read', side_effect=read):
            prepared = runner.prepare(frozen, checks)
            self.assertEqual(prepared['research_calls'], 0)
            runner.admission(frozen)
            for item, replacement in ((frozen/'input_config.json', '{"changed":true}'),
                (frozen/'source_snapshot'/name, '# changed\n'), (frozen/'protocol.md', 'changed'),
                (protocol, 'changed source protocol'), (frozen/'precheck.json', '{}')):
                old = item.read_bytes(); item.write_text(replacement, encoding='utf-8')
                with self.subTest(item=item):
                    with self.assertRaises(ValueError): runner.admission(frozen)
                item.write_bytes(old)
            d = original_read(frozen/'declaration.json')
            d['linked_opened_by_job']['anchor_linked4']['AB'].append('B.main')
            runner.save(frozen/'declaration.json', d)
            with self.assertRaises(ValueError): runner.admission(frozen)


class DispatchTests(Fixture):
    def test_08_whole_full_domain_flags_and_continuous_feedback(self):
        runner.execute(runner.jobs()[0], self.out, self.d, self.entries)
        kw = self.entries['whole'].call_args.kwargs
        self.assertEqual((kw['seconds'], kw['feedback_kind']), (300, 'conditional'))
        self.assertIs(kw['model_builder'].func, self.entries['builder'])
        self.assertEqual(kw['model_builder'].keywords,
            {'prefilter_deadlines': True, 'cumulative_precedence': False})
        self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})
        for prohibited in ('shared_deployment', 'opened_by_scene', 'preeliminate_closed_anchors', 'warm_start'):
            self.assertNotIn(prohibited, kw)

    def test_09_linked_second_pass_preelimination_and_independent_copies(self):
        original = deepcopy(self.d)
        runner.execute(runner.jobs()[1], self.out, self.d, self.entries)
        kw = self.entries['linked'].call_args.kwargs
        shared, build = runner.settings()
        self.assertEqual((kw['seconds'], kw['scene_slice_s']), (300, 60))
        self.assertEqual(kw['builder_options'], build)
        self.assertEqual(kw['shared_deployment'], shared)
        self.assertTrue(kw['preeliminate_closed_anchors'])
        self.assertIs(kw['clock'], kw['budget'].clock)
        self.assertEqual(kw['opened_by_scene'], self.d['first_opened_by_scene'])
        self.assertEqual(kw['linked_opened_by_scene'], self.d['linked_opened_by_job']['anchor_linked4'])
        kw['opened_by_scene']['AB'].append('changed')
        kw['linked_opened_by_scene']['AB'].clear()
        kw['shared_deployment']['A.pre'] = 'changed'
        self.assertEqual(self.d, original)
        self.assertNotEqual(runner.settings()[0]['A.pre'], 'changed')

    def test_10_heuristics_same_auto_low_and_single_fixed_seed(self):
        for job in runner.jobs()[2:]:
            runner.execute(job, self.out, self.d, self.entries)
            self.assertEqual(self.entries['heuristic'].call_args.kwargs,
                {'method': job['method'], 'seconds': 300, 'seed': job['seed'], 'allow_auto_low': True})
        self.assertIsNone(runner.jobs()[2]['seed'])
        self.assertEqual(runner.jobs()[3]['seed'], 101)

    def test_11_every_loader_uses_its_own_budget_and_identity(self):
        seen, supplied = [], []
        def entry(loader, folder, **kw):
            budget = kw.get('budget') or Mock()
            if not kw.get('budget'): budget.phase.return_value = nullcontext()
            supplied.append(budget)
            seen.append((loader, loader(budget)))
            return {'mock': True}
        entries = dict(self.entries, whole=entry, linked=entry, heuristic=entry)
        with patch.object(runner, 'fresh_input', side_effect=lambda budget: values()) as fresh, \
             patch('partial_bounds.independent_lower_bound', return_value={'L0_J': '1/2'}) as lower:
            for job in runner.jobs():
                (self.out/job['id']).mkdir()
                result, identity = runner.execute(job, self.out, self.d, entries)
                self.assertTrue(identity['input_verified'])
            self.assertEqual([c.args[0] for c in fresh.call_args_list], supplied)
            lower.assert_called_once_with(seen[0][1][1], None, supplied[0])
        self.assertEqual(len({id(p[0]) for p in seen}), 4)
        self.assertEqual(len({id(b) for b in supplied}), 4)
        self.assertEqual(len({id(p[1][1]) for p in seen}), 4)

    def test_12_every_fresh_raw_config_instance_must_match(self):
        for index in range(3):
            changed = list(values()); changed[index] = {'wrong': index}
            for job in runner.jobs():
                with self.subTest(index=index, method=job['id']):
                    def entry(loader, folder, **kw):
                        budget = kw.get('budget') or Mock()
                        return loader(budget)
                    with patch.object(runner, 'fresh_input', return_value=tuple(changed)):
                        with self.assertRaises(ValueError):
                            runner.execute(job, self.out, self.d,
                                dict(self.entries, whole=entry, linked=entry, heuristic=entry))

    def test_13_unknown_or_modified_job_never_dispatches(self):
        for bad in ({'id': 'unknown', 'method': 'heft'}, dict(runner.jobs()[3], seed=102)):
            with self.assertRaises(ValueError): runner.execute(bad, self.out, self.d, self.entries)
        for key in ('whole', 'linked', 'heuristic'): self.entries[key].assert_not_called()

    def test_14_route_to_method_specific_existing_receipt_audits(self):
        with patch.object(runner, 'cutoff_adapter') as adapter, \
             patch('four_whole_status.result_records', return_value={'whole': True}) as whole, \
             patch('run_heuristic_followup.result_records', return_value={'heuristic': True}) as heuristic:
            adapter.return_value.correct_records.return_value = {'linked': True}
            for job in runner.jobs():
                result = runner.result_records(job, {}, self.d, self.out/job['id'], input_valid=True,
                    source_valid=True, errors=[])
                route = 'whole' if job['method'] == 'milp' else 'linked' if job.get('opened_count') else 'heuristic'
                self.assertEqual(result, {route: True})
            self.assertEqual((whole.call_count, adapter.return_value.correct_records.call_count,
                              heuristic.call_count), (1, 1, 2))


class RunLifecycleTests(Fixture):
    def test_15_consumed_before_dispatch_fixed_order_four_independent_calls(self):
        def inspect(job, out, d, entries):
            self.assertTrue(runner.GLOBAL_CLAIM.exists())
            self.assertTrue((out/'claims'/(job['id']+'.json')).is_file())
            ledger = runner.read(out/'ledger.json')
            self.assertEqual(ledger['consumed'], runner.jobs().index(job)+1)
            self.assertEqual(ledger['calls'][-1]['state'], 'RUNNING')
            return {'U_J': '1'}, {'input_verified': True}
        okay, execute = self.run_fake(inspect)
        self.assertTrue(okay)
        self.assertEqual([c.args[0] for c in execute.call_args_list], runner.jobs())
        ledger = runner.read(self.out/'ledger.json')
        self.assertEqual((ledger['state'], ledger['consumed'], ledger['reserved_method_budget_s']),
                         ('COMPLETED', 4, 1200))

    def test_16_no_authorization_consumes_nothing(self):
        with patch.object(runner.time, 'monotonic', side_effect=AssertionError('No method clock')):
            with self.assertRaises(PermissionError): runner.run(self.out)
        self.assertFalse(runner.GLOBAL_CLAIM.exists())
        self.assertEqual(runner.read(self.out/'ledger.json')['consumed'], 0)

    def test_17_completed_call_cannot_be_replayed_or_rewritten(self):
        self.assertTrue(self.run_fake()[0])
        original = {p.relative_to(self.out): p.read_bytes() for p in self.out.rglob('*.json')}
        with patch.object(runner.time, 'monotonic', side_effect=AssertionError('No replay clock')):
            with self.assertRaises(FileExistsError): runner.run(self.out, execution_authorized=True)
        self.assertEqual(original, {p.relative_to(self.out): p.read_bytes() for p in self.out.rglob('*.json')})

    def test_18_any_prior_claim_or_consumption_refuses_without_retry(self):
        baseline = runner.read(self.out/'ledger.json')
        for state, consumed in (('BLOCKED', 0), ('RUNNING', 0), ('DECLARED', 1)):
            runner.save(self.out/'ledger.json', dict(baseline, state=state, consumed=consumed))
            with self.assertRaises(FileExistsError): runner.run(self.out, execution_authorized=True)
        runner.save(self.out/'ledger.json', baseline)
        runner.save(self.out/'claims/heft.json', {'claimed': True})
        with self.assertRaises(FileExistsError): runner.run(self.out, execution_authorized=True)

    def test_19_normal_deadlines_and_pending_last_requests_continue(self):
        states = ['NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST', 'NORMAL_TIME_LIMIT',
                  'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT']
        def execute(job, *args):
            return {'U_J': '1', 'mock_status': states[runner.jobs().index(job)]}, {'input_verified': True}
        okay, calls = self.run_fake(execute)
        self.assertTrue(okay); self.assertEqual(calls.call_count, 4)
        rows = runner.read(self.out/'ledger.json')['calls']
        self.assertEqual([r['execution']['execution_status'] for r in rows], states)
        self.assertEqual([r['usable_U_J'] for r in rows], ['1']*4)

    def test_20_genuine_fault_stops_future_jobs_preserves_existing_U(self):
        def execute(job, *args):
            return {'U_J': '1', 'mock_status': 'TECHNICAL_FAILURE_CONFIRMED'}, {'input_verified': True}
        okay, calls = self.run_fake(execute)
        self.assertFalse(okay); self.assertEqual(calls.call_count, 1)
        ledger = runner.read(self.out/'ledger.json')
        self.assertEqual((ledger['state'], ledger['consumed']), ('BLOCKED', 1))
        self.assertEqual(ledger['calls'][0]['usable_U_J'], '1')

    def test_21_numeric_or_unknown_status_never_silently_continues(self):
        def execute(job, *args): return {'mock_status': 'NUMERICAL_ANOMALY_OBSERVED'}, {'input_verified': True}
        okay, calls = self.run_fake(execute)
        self.assertFalse(okay); self.assertEqual(calls.call_count, 1)

    def test_22_exception_is_one_consumed_failure_not_an_automatic_retry(self):
        okay, calls = self.run_fake(RuntimeError('injected interface fault'))
        self.assertFalse(okay); self.assertEqual(calls.call_count, 1)
        row = runner.read(self.out/'ledger.json')['calls'][0]
        self.assertTrue(any('injected interface fault' in e for e in row['errors']))
        self.assertEqual(runner.read(self.out/'ledger.json')['reserved_method_budget_s'], 300)

    def test_23_post_call_identity_drift_blocks_without_running_the_next_method(self):
        okay, calls = self.run_fake()
        self.assertTrue(okay)
        # A separate not-yet-started fixture is required; consumed evidence stays immutable.
        extra = self.root/'drift'; extra.mkdir(); (extra/'claims').mkdir()
        runner.save(extra/'ledger.json', {'state': 'DECLARED', 'consumed': 0, 'calls': [], 'reserved_method_budget_s': 0})
        runner.save(extra/'declaration.json', self.d)
        with patch.object(runner, 'TARGET', extra), patch.object(runner, 'GLOBAL_CLAIM', self.root/'drift_claim.json'), \
             patch.object(runner, 'admission', side_effect=[self.d, self.d, ValueError('source drift')]), \
             patch.object(runner, 'execute', return_value=({}, {'input_verified': True})) as called:
            (extra/'whole_milp').mkdir()
            self.assertFalse(runner.run(extra, execution_authorized=True))
            self.assertEqual(called.call_count, 1)
            self.assertFalse(runner.read(extra/'ledger.json')['calls'][0]['source_identity_valid'])

    def test_24_post_audit_exception_does_not_discard_raw_evidence_or_retry(self):
        okay, calls = self.run_fake(audit=RuntimeError('audit failed'))
        self.assertFalse(okay); self.assertEqual(calls.call_count, 1)
        self.assertEqual(runner.read(self.out/'whole_milp/wrapper_raw_result.json')['U_J'], '1')
        self.assertEqual(runner.read(self.out/'ledger.json')['calls'][0]['execution']['execution_status'],
                         'TECHNICAL_FAILURE_CONFIRMED')


class CutoffAdapterRegressionTests(unittest.TestCase):
    def setUp(self):
        from test_execution_status import base_context
        self.adapter = runner.cutoff_adapter()
        self.context = base_context()
        self.context.update(worker_isolation='VERIFIED', completion_verified=False,
            hard_errors=[{'scope': 'AC:round:1', 'reason': None, 'status': 'BUDGET_EXHAUSTED',
                          'technical_state': None, 'error': None}])
        self.original = {'context': self.context,
            'execution': {'execution_status': 'TECHNICAL_FAILURE_CONFIRMED'}, 'usable_U_J': '11/10'}
        self.r = {'budget_exhausted': True, 'reason': 'wall_time_limit',
            'timing': {'limit_s': 300, 'method_elapsed_s': 300.016},
            'condition': {'budget_identity': {'start': '1000'}}}
        self.request = {'cancel_requested': True, 'cancel_published_at_s': 300.016,
            'native_status': 'BUDGET_EXHAUSTED', 'within_budget': False,
            'failure_reasons': ['ROOT_BUDGET_EXHAUSTED']}
        self.python = {'status': 'BUDGET_EXHAUSTED', 'response_may_arrive_later': True,
            'budget_valid': False, 'accepted_for_evaluation': False, 'x': [],
            'publication_read': {'transient_read_errors': {'FileNotFoundError': 1}}}
        self.metadata = {'method_deadline_bound': True, 'absolute_deadline': 1300}

    def classify(self):
        with patch.object(self.adapter.runner, 'result_records', return_value=deepcopy(self.original)), \
             patch.object(self.adapter, '_last_mapping', return_value=(self.request, self.python,
                 self.metadata, {'AC:round:1', 'phase:2:AC:round:1'})):
            return self.adapter.correct_records(runner.jobs()[1], self.r, {}, Path('MOCK'),
                input_valid=True, source_valid=True)

    def test_25_cancel_at_actual_stop_after_300_preserves_only_existing_U(self):
        record = self.classify()
        self.assertTrue(record['cutoff_audit']['applied'])
        self.assertEqual(record['execution']['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertEqual(record['usable_U_J'], '11/10')
        self.assertFalse(record['cutoff_audit']['new_safe_evaluation'])
        self.assertFalse(record['cutoff_audit']['late_candidate_accepted'])

    def test_26_cancel_before_cutoff_or_after_stop_is_not_normalized(self):
        for at in (299.999, 300.017):
            self.request['cancel_published_at_s'] = at
            self.assertFalse(self.classify()['cutoff_audit']['applied'])

    def test_27_late_vector_cannot_be_promoted_by_cutoff_adapter(self):
        self.python['x'] = [1]
        self.assertFalse(self.classify()['cutoff_audit']['applied'])

    def test_28_absolute_deadline_must_be_bound_to_original_root_budget(self):
        for key, value in (('absolute_deadline', 1301), ('method_deadline_bound', False)):
            old = self.metadata[key]; self.metadata[key] = value
            self.assertFalse(self.classify()['cutoff_audit']['applied'])
            self.metadata[key] = old

    def test_29_unrelated_real_error_is_not_removed(self):
        self.original['context']['hard_errors'].append({'scope': 'AB:round:1', 'error': 'real I/O failure'})
        record = self.classify()
        self.assertEqual(record['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertEqual(record['context']['hard_errors'], [{'scope': 'AB:round:1', 'error': 'real I/O failure'}])
        self.assertEqual(record['usable_U_J'], '11/10')

    def test_30_numeric_rejection_prior_incomplete_or_identity_fault_not_excused(self):
        for key, bad in (('observed_numerical_rejection', True), ('prior_requests_complete', False),
            ('current_request_identity_valid', False), ('source_identity_valid', False),
            ('worker_isolation', 'UNKNOWN')):
            with self.subTest(key=key):
                old = self.original['context'][key]; self.original['context'][key] = bad
                self.assertFalse(self.classify()['cutoff_audit']['applied'])
                self.original['context'][key] = old

    def test_31_unknown_failure_reason_or_real_read_error_stays_fault(self):
        self.request['failure_reasons'] = ['UNKNOWN_REASON']
        self.assertFalse(self.classify()['cutoff_audit']['applied'])
        self.request['failure_reasons'] = ['ROOT_BUDGET_EXHAUSTED']
        self.python['publication_read']['transient_read_errors'] = {'PermissionError': 1}
        self.assertFalse(self.classify()['cutoff_audit']['applied'])

    def test_32_current_wrapper_requires_matching_cancel_file(self):
        root = runner.REPO/'.runtime/k152_cancel_fixtures'; root.mkdir(parents=True, exist_ok=True)
        from execution_status import classify_execution
        with tempfile.TemporaryDirectory(dir=root) as name:
            folder = Path(name); (folder/'matlab').mkdir()
            adapter = Mock()
            context = deepcopy(self.context)
            context.update(hard_errors=[], root_deadline_confirmed=True, deadline_causal_trace=True,
                last_request={'state': 'PENDING', 'pending_at_cutoff': True, 'refuses_late_candidate': True,
                    'deadline_causal_trace': True, 'deadline_reasons': ['ROOT_BUDGET_EXHAUSTED']})
            base = {'cutoff_audit': {'applied': True}, 'context': context,
                    'execution': classify_execution(self.r, context), 'usable_U_J': '11/10'}
            adapter.correct_records.side_effect = lambda *a, **kw: deepcopy(base)
            adapter._last_mapping.return_value = (self.request, {'request_number': 4}, self.metadata, {'AC:round:1'})
            cancel = folder/'matlab/request_000004.cancel'
            with patch.object(runner, 'cutoff_adapter', return_value=adapter):
                for text in (None, 'unrelated', 'budget'):
                    if text is not None: cancel.write_text(text, encoding='ascii')
                    record = runner.result_records(runner.jobs()[1], self.r, {}, folder,
                        input_valid=True, source_valid=True)
                    self.assertIs(record['cutoff_audit']['cancel_file_verified'], text == 'budget')
                    expected = 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST' if text == 'budget' else 'TECHNICAL_FAILURE_CONFIRMED'
                    self.assertEqual(record['execution']['execution_status'], expected)
                    self.assertEqual(record['usable_U_J'], '11/10')


if __name__ == '__main__':
    unittest.main()
