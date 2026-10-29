"""Data-only launch-contract/state tests, never actual method execution."""
from copy import deepcopy
from pathlib import Path
import unittest

from .prepare import (load, validate_common_input, validate_plan, mock_dispatch,
                      canonical, METHODS)
from research.chapter3_experiments.execution_status import classify_execution

FROZEN = None


def context(*, deadline=False, safe=False, pending=False):
    out = {'input_identity_valid': True, 'source_identity_valid': True,
           'current_request_identity_valid': True, 'cutoff_s': 300,
           'hard_errors': [], 'observed_numerical_rejection': False,
           'worker_isolation': 'NOT_APPLICABLE', 'prior_requests_complete': True,
           'completion_verified': not deadline, 'root_deadline_confirmed': deadline,
           'deadline_causal_trace': deadline, 'last_request': {'state': 'NONE'}}
    if safe:
        out['safe_receipt'] = {'verified': True, 'identity_valid': True,
            'complete': True, 'formed_at_s': 30, 'energy_upper_J': '1'}
    if pending:
        out['last_request'] = {'state': 'PENDING', 'pending_at_cutoff': True,
            'refuses_late_candidate': True, 'deadline_causal_trace': True,
            'deadline_reasons': ['ROOT_BUDGET_EXHAUSTED']}
    return out


class PreparationTests(unittest.TestCase):
    def plan(self): return load(FROZEN/'plan.json')
    def common(self): return load(FROZEN/'common_input.json')

    def test_common_scientific_input_and_scope(self):
        validate_common_input(self.common()); validate_plan(self.plan())
        i = self.common()['instance']
        self.assertEqual(len(i['stage_modes']), 8)
        self.assertEqual(sum(len(s['stage_instances']) for s in i['scenarios']), 12)

    def test_no_reference_candidate_or_energy_channel(self):
        for key in ('candidate', 'reference', 'safe_upper_bound_J', 'fixed_deployment'):
            v = self.common(); v['instance'][key] = {'example': 'forbidden'}
            v['provenance']['instance_sha256'] = canonical(v['instance'])
            with self.subTest(key=key), self.assertRaises(ValueError): validate_common_input(v)

    def test_input_content_drift_rejected(self):
        v = self.common(); v['instance']['stage_modes']['L1.s0001'][0]['duration_ms'] = '1'
        with self.assertRaises(ValueError): validate_common_input(v)

    def test_three_mock_routes_use_one_input_and_independent_seeds(self):
        p = self.plan(); records = []
        for j in p['jobs']:
            mock_dispatch(p, j, lambda job, evidence: records.append((job, evidence)))
        self.assertEqual([j['id'] for j, _ in records], list(METHODS))
        self.assertEqual({e['input_sha256'] for _, e in records}, {p['common_input_sha256']})
        self.assertTrue(all(e['simulation_only'] and not e['initial_solution_imported']
                            and not e['cache_shared_between_methods'] for _, e in records))

    def test_extra_C_or_duplicate_job_rejected(self):
        for j in ({'id': 'linked_C'}, self.plan()['jobs'][0]):
            p = self.plan(); p['jobs'].append(j)
            with self.assertRaises(ValueError): validate_plan(p)

    def test_budget_seed_input_and_flags_drift_rejected(self):
        mutations = [('method_seconds', 301), ('seed', 102), ('input_sha256', 'other')]
        for k, v in mutations:
            p = self.plan(); p['jobs'][2][k] = v
            with self.subTest(key=k), self.assertRaises(ValueError): validate_plan(p)
        p = self.plan(); p['jobs'][0]['builder_flags']['prefilter_deadlines'] = False
        with self.assertRaises(ValueError): validate_plan(p)

    def test_no_authorized_execution_switch(self):
        p = self.plan(); self.assertFalse(p['execution_authorized'])
        p['execution_authorized'] = True
        with self.assertRaises(ValueError): validate_plan(p)

    def test_construction_deadline_is_not_native_timeout(self):
        raw = {'model_complete': False, 'stop_stage': 'model_construction',
               'integer_solver_entered': False, 'budget_exhausted': True}
        r = classify_execution(raw, context(deadline=True))
        self.assertEqual(r['execution_status'], 'NORMAL_TIME_LIMIT')
        self.assertFalse(raw['integer_solver_entered'])
        self.assertFalse(r['independently_proven_infeasible'])

    def test_construction_memory_fault_remains_technical(self):
        c = context(); c['hard_errors'] = ['MemoryError in model_construction']
        r = classify_execution({'model_complete': False}, c)
        self.assertEqual(r['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_no_initial_SAFE_is_not_infeasibility(self):
        raw = {'integer_solver_entered': False, 'initialisation': {
            'state': 'UNRESOLVED', 'reason': 'NO_SAFE_INITIAL_WITNESS'}}
        r = classify_execution(raw, context())
        self.assertIsNone(r['usable_U_J']); self.assertFalse(r['independently_proven_infeasible'])
        self.assertEqual(raw['initialisation']['reason'], 'NO_SAFE_INITIAL_WITNESS')

    def test_SAFE_with_x0_rejection_preserved_and_marked_numeric(self):
        c = context(safe=True); c['observed_numerical_rejection'] = True
        r = classify_execution({'integer_solver_entered': False,
            'initialisation': {'state': 'SAFE_POINT_REJECTED'}}, c)
        self.assertTrue(r['safe_witness_preserved'])
        self.assertEqual(r['execution_status'], 'NUMERICAL_ANOMALY_OBSERVED')

    def test_native_deadline_without_SAFE_is_normal_unresolved(self):
        r = classify_execution({'integer_solver_entered': True}, context(deadline=True, pending=True))
        self.assertEqual(r['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertFalse(r['safe_witness_preserved'])

    def test_native_deadline_retains_prior_SAFE_not_last_candidate(self):
        r = classify_execution({'integer_solver_entered': True}, context(deadline=True, pending=True, safe=True))
        self.assertTrue(r['safe_witness_preserved']); self.assertEqual(r['usable_U_J'], '1')
        self.assertFalse(r['new_or_late_candidate_accepted'])

    def test_late_SAFE_never_accepted(self):
        c = context(deadline=True, pending=True, safe=True)
        c['safe_receipt']['formed_at_s'] = 300
        self.assertFalse(classify_execution({}, c)['safe_witness_preserved'])

    def test_fault_with_SAFE_is_not_normal_deadline(self):
        c = context(deadline=True, safe=True); c['hard_errors'] = ['payload corrupt']
        r = classify_execution({}, c)
        self.assertTrue(r['safe_witness_preserved'])
        self.assertEqual(r['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_cleanup_unverified_is_unresolved_and_not_reusable(self):
        c = context(); c['worker_isolation'] = 'UNKNOWN'
        r = classify_execution({}, c)
        self.assertEqual(r['execution_status'], 'STATUS_UNRESOLVED')
        self.assertFalse(r['worker_may_be_reused'])

    def test_static_counts_are_bounds_not_measured_cost(self):
        s = self.plan()['static_case']
        self.assertEqual((s['Y'], s['K']), (3167, 2406))
        self.assertEqual(s['variables_bounds'], [56131, 118687])
        self.assertEqual(s['rows_bounds'], [142869, 797301])
