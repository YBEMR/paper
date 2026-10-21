"""Data/mocked K148 protocol checks; never call a solver or physical evaluator."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_five_open_pair as runner


def instance():
    return {'scenarios': [{'id': 'A'+local, 'stage_instances': [
        {'id': who+'.'+part, 'shared_stage_id': who+'.'+part}
        for who in ('A', local) for part in ('pre', 'main', 'post')]}
        for local in ('B', 'C')]}


def declaration():
    return {'input_identities': {'raw_config_sha256': runner.canonical({'raw': 1}),
        'config_sha256': runner.canonical({'config': 1}),
        'input_sha256': runner.canonical(instance())},
        'input_sha256': runner.canonical(instance()),
        'config_sha256': runner.canonical({'config': 1}),
        'first_opened_by_scene': {'AB': ['B.main', 'B.post'], 'AC': ['C.main', 'C.post']},
        'linked_opened_by_job': {j['id']: runner.masks(instance(), j['opened_count']) for j in runner.jobs()}}


def aggregate_fixture():
    from scene_adapter import _receipt_hash
    candidate = {'scenes': {'AB': {'stages': []}}}
    budget = {'token': 'MOCK_ONLY', 'seconds': '300'}
    common = {'full_input_sha256': 'input', 'source_sha256': {'x': 'hash'},
              'accuracy_sha256': 'acc', 'control_policy': 'auto_low_immediate_v1',
              'shared_deployment_sha256': 'shared', 'budget': budget}
    identity = dict(common, candidate_sha256=runner.canonical(candidate))
    physical = {'state': 'SAFE', 'complete': True, 'rankable_energy': True,
        'covered_until_s': '2/5', 'trace': [{'time_s': '2/5'}],
        'peaks_degC': {'CPU': ['50', '51']}}
    scene = {'identity': dict(identity), 'state': 'SAFE', 'rankable_energy': True,
        'result': physical, 'energy_J': ['1', '1']}
    scene['receipt_sha256'] = _receipt_hash(scene)
    aggregate = {'state': 'SAFE', 'rankable_energy': True, 'problem_id': 'base__R1',
        'identity': identity, 'safe_candidate': candidate,
        'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'},
        'scenes': {'AB': scene}, 'weighted_energy_J': ['1', '1'],
        'safe_upper_bound_J': '1', 'completed_at_elapsed_s': 10.0}
    aggregate['receipt_sha256'] = _receipt_hash(aggregate)
    d = {'input_sha256': 'input', 'config_sha256': 'config',
        'first_opened_by_scene': {'AB': []}, 'linked_opened_by_job': {'old_linked4': {'AB': []}},
        'scene_spec': {'AB': {'weight': '1', 'window_s': '2/5', 'limits': {'CPU': '80'}}}}
    condition = {'seed_receipt': {'identity': common}, 'budget_identity': budget}
    return d, candidate, condition, aggregate


class MaskTests(unittest.TestCase):
    def test_exact_four_and_five(self):
        old, new = runner.masks(instance(), 4), runner.masks(instance(), 5)
        self.assertEqual(set(new['AB'])-set(old['AB']), {'B.main'})
        self.assertEqual(set(new['AC'])-set(old['AC']), {'C.main'})
        self.assertNotIn('B.post', new['AB'])
        self.assertNotIn('C.post', new['AC'])

    def test_invalid_count_rejected(self):
        with self.assertRaises(ValueError): runner.masks(instance(), 6)

    def test_nonfull_chain_rejected(self):
        i = instance(); i['scenarios'][0]['stage_instances'].pop()
        with self.assertRaises(ValueError): runner.masks(i, 5)

    def test_duplicate_stage_rejected(self):
        i = instance(); i['scenarios'][0]['stage_instances'][1]['id'] = 'A.pre'
        with self.assertRaises(ValueError): runner.masks(i, 5)

    def test_rules_only_one_changed_factor(self):
        r = runner.rules()
        self.assertEqual(r['method_call_limit'], 2)
        self.assertEqual(r['per_method_budget_s'], 300)
        self.assertFalse(r['candidate_cache_or_witness_shared'])
        self.assertFalse(r['retry_allowed'])
        self.assertFalse(r['extend_budget_allowed'])


class ExecutionTests(unittest.TestCase):
    def test_two_fresh_loaders_budgets_and_masks(self):
        seen = []
        def entry(loader, folder, **kwargs):
            loaded = loader(kwargs['budget'])
            seen.append((kwargs, loaded))
            return {'mock': True}
        d = declaration()
        with patch.object(runner, 'fresh_input', side_effect=lambda budget: ({'raw': 1}, {'config': 1}, instance())):
            for job in runner.jobs():
                r, identity = runner.execute(job, Path('MOCK'), d, {'linked': entry, 'session': object})
                self.assertTrue(identity['input_verified'])
        self.assertIsNot(seen[0][0]['budget'], seen[1][0]['budget'])
        self.assertIsNot(seen[0][1], seen[1][1])
        self.assertEqual(seen[0][0]['opened_by_scene'], seen[1][0]['opened_by_scene'])
        self.assertNotEqual(seen[0][0]['linked_opened_by_scene'], seen[1][0]['linked_opened_by_scene'])
        for kw, _ in seen:
            self.assertEqual(kw['seconds'], 300)
            self.assertEqual(kw['scene_slice_s'], 60)
            self.assertIs(kw['clock'], kw['budget'].clock)
            self.assertEqual(kw['session_factory'].keywords, {'cut_max_iterations': 10})

    def test_fresh_input_identity_failure(self):
        def entry(loader, folder, **kw): return loader(kw['budget'])
        with patch.object(runner, 'fresh_input', return_value=({'wrong': 1}, {}, instance())):
            with self.assertRaises(ValueError):
                runner.execute(runner.jobs()[0], Path('MOCK'), declaration(), {'linked': entry, 'session': object})


class ReceiptTests(unittest.TestCase):
    def test_complete_receipt(self):
        d, c, cond, a = aggregate_fixture()
        self.assertEqual(runner.aggregate_issues(a, c, d, cond), [])

    def test_late_receipt(self):
        d, c, cond, a = aggregate_fixture(); a['completed_at_elapsed_s'] = 300
        self.assertIn('AGGREGATE_OUTSIDE_BUDGET', runner.aggregate_issues(a, c, d, cond))

    def test_bad_candidate_identity(self):
        d, c, cond, a = aggregate_fixture(); a['identity']['candidate_sha256'] = 'wrong'
        self.assertIn('AGGREGATE_IDENTITY_MISMATCH', runner.aggregate_issues(a, c, d, cond))

    def test_bad_receipt_hash(self):
        d, c, cond, a = aggregate_fixture(); a['receipt_sha256'] = 'wrong'
        self.assertIn('INVALID_COMPLETE_AGGREGATE', runner.aggregate_issues(a, c, d, cond))

    def test_missing_idle_tail(self):
        d, c, cond, a = aggregate_fixture(); a['scenes']['AB']['result']['covered_until_s'] = '1/5'
        self.assertIn('INCOMPLETE_WINDOW:AB', runner.aggregate_issues(a, c, d, cond))

    def test_unsafe_temperature(self):
        d, c, cond, a = aggregate_fixture(); a['scenes']['AB']['result']['peaks_degC']['CPU'] = ['79', '81']
        self.assertIn('UNSAFE_PEAK_ENCLOSURE:AB:CPU', runner.aggregate_issues(a, c, d, cond))

    def test_bad_weighted_energy(self):
        d, c, cond, a = aggregate_fixture(); a['weighted_energy_J'] = ['2', '2']
        self.assertIn('WEIGHTED_ENERGY_MISMATCH', runner.aggregate_issues(a, c, d, cond))

    def classify(self, *, pending=False, bad_identity=False, numeric=False, issues=None):
        import run_linked_pair
        d, candidate, condition, aggregate = aggregate_fixture()
        result = {'state': 'SAFE', 'safe_candidate': candidate, 'safe_upper_bound_J': '1',
            'weighted_energy_J': ['1', '1'], 'aggregation': aggregate, 'aggregation_attempts': [],
            'condition': condition, 'identity': {'full_input_sha256': 'wrong' if bad_identity else 'input',
                                             'config_sha256': 'config'},
            'matlab_worker_ready': False, 'reason': 'wall_time_limit' if pending else 'SCENE_SEARCH_SEQUENCE_COMPLETE',
            'budget_exhausted': pending, 'timing': {'limit_s': 300, 'method_elapsed_s': 300.01 if pending else 10},
            'search_failure_latched': False, 'phases': [], 'global_updates': []}
        request = {'latched_unresolved': False, 'within_budget': True, 'failure_reasons': [],
            'callback_publications_complete': True, 'expected_callback_numbers': [], 'checked_callback_numbers': [],
            'numerical_checks': []}
        if pending:
            request.update(latched_unresolved=True, within_budget=False,
                failure_reasons=['BUDGET_BEFORE_FINAL_ADMISSION'], callback_publications_complete=False,
                cancel_requested=True, cancel_published_at_s=300, native_status='BUDGET_EXHAUSTED')
        if numeric: request['numerical_checks'] = [{'report': {'accepted': False}, 'accepted': False}]
        result['augmented_transport'] = {'requests': [request]}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); (folder/'matlab').mkdir()
            if pending:
                runner.save(folder/'matlab/request_000001.python.json', {
                    'status': 'BUDGET_EXHAUSTED', 'response_may_arrive_later': True,
                    'budget_valid': False, 'accepted_for_evaluation': False, 'x': [],
                    'publication_read': {'transient_read_errors': {'FileNotFoundError': 1}}})
            with patch.object(run_linked_pair, 'transport_issues', return_value=issues or []) as audit:
                record = runner.result_records(runner.jobs()[0], result, d, folder,
                    input_valid=True, source_valid=True)
                self.assertEqual(audit.call_args.args[0], run_linked_pair.jobs()[1])
        return record

    def test_normal_completion_preserves_safe(self):
        r = self.classify()
        self.assertEqual(r['execution']['execution_status'], 'NORMAL_COMPLETION')
        self.assertEqual(r['usable_U_J'], '1')

    def test_pending_cutoff_preserves_safe(self):
        r = self.classify(pending=True)
        self.assertEqual(r['execution']['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertEqual(r['usable_U_J'], '1')

    def test_bad_identity_never_rankable(self):
        r = self.classify(pending=True, bad_identity=True)
        self.assertEqual(r['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertIsNone(r['usable_U_J'])

    def test_numerical_failure_not_erased_by_deadline(self):
        r = self.classify(pending=True, numeric=True)
        self.assertEqual(r['execution']['execution_status'], 'NUMERICAL_ANOMALY_OBSERVED')
        self.assertEqual(r['usable_U_J'], '1')

    def test_wrong_warm_anchor_remains_fault(self):
        r = self.classify(pending=True, issues=[{'scope': 'linked_anchor',
                      'reason': 'WARM_ANCHOR_IS_NOT_LAST_COMPLETE_FIRST_PASS_GENERATION'}])
        self.assertEqual(r['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.out = self.repo/'results/pair'
        self.out.mkdir(parents=True); (self.out/'claims').mkdir()
        runner.save(self.out/'declaration.json', {})
        runner.save(self.out/'ledger.json', {'state': 'DECLARED', 'consumed': 0,
            'reserved_method_budget_s': 0, 'calls': []})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close); self.addCleanup(self.temp.cleanup)
        self.stack.enter_context(patch.object(runner, 'REPO', self.repo))
        self.stack.enter_context(patch.object(runner, 'TARGET', self.out))
        self.claim = self.repo/'results/global_claim.json'
        self.stack.enter_context(patch.object(runner, 'GLOBAL_CLAIM', self.claim))
        self.stack.enter_context(patch.object(runner, 'admission', return_value={}))
        self.stack.enter_context(patch.object(runner, 'entry_points', return_value={}))

    def stub(self, job, out, d, entries):
        self.assertTrue(self.claim.is_file())
        self.assertTrue((out/'claims'/(job['id']+'.json')).is_file())
        ledger = runner.read(out/'ledger.json')
        self.assertEqual(ledger['reserved_method_budget_s'], 300*ledger['consumed'])
        self.assertGreater(ledger['consumed'], 0)
        (out/job['id']).mkdir()
        return {'mock': job['id']}, {'input_verified': True}

    def test_claim_consumed_before_both_calls(self):
        with patch.object(runner, 'execute', side_effect=self.stub) as execute, patch.object(runner, 'result_records',
            return_value={'execution': {'execution_status': 'NORMAL_TIME_LIMIT'}, 'usable_U_J': '1'}):
            self.assertTrue(runner.run(self.out, execution_authorized=True))
            self.assertEqual(execute.call_count, 2)
        ledger = runner.read(self.out/'ledger.json')
        self.assertEqual(ledger['consumed'], 2)
        self.assertEqual(ledger['reserved_method_budget_s'], 600)
        with self.assertRaises(FileExistsError): runner.run(self.out, execution_authorized=True)

    def test_real_fault_stops_remaining(self):
        with patch.object(runner, 'execute', side_effect=self.stub) as execute, patch.object(runner, 'result_records',
            return_value={'execution': {'execution_status': 'TECHNICAL_FAILURE_CONFIRMED'}, 'usable_U_J': '1'}):
            self.assertFalse(runner.run(self.out, execution_authorized=True))
            self.assertEqual(execute.call_count, 1)
        self.assertEqual(runner.read(self.out/'ledger.json')['state'], 'BLOCKED')

    def test_no_implicit_authorization(self):
        with self.assertRaises(PermissionError): runner.run(self.out)
        self.assertFalse(self.claim.exists())

    def test_foreign_output_rejected(self):
        with self.assertRaises(ValueError): runner.local(self.repo/'other')

    def test_exception_still_consumed_and_stops(self):
        with patch.object(runner, 'execute', side_effect=RuntimeError('mock fault')) as execute, patch.object(runner, 'result_records',
            return_value={'execution': {'execution_status': 'TECHNICAL_FAILURE_CONFIRMED'}, 'usable_U_J': None}):
            self.assertFalse(runner.run(self.out, execution_authorized=True))
            self.assertEqual(execute.call_count, 1)
        self.assertEqual(runner.read(self.out/'ledger.json')['consumed'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
