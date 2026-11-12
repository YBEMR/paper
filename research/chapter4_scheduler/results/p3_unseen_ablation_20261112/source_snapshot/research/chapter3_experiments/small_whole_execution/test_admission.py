"""Synthetic-only K195 stored admission tests; no science module imports."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission


def receipt(upper='1', stamp=20):
    return {'state': 'SAFE', 'rankable_energy': True,
        'completed_at_elapsed_s': stamp,
        'weighted_energy_J': ['0.999', upper], 'safe_upper_bound_J': upper,
        'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'},
        'scenes': {'AB': {'complete': True}, 'AC': {'complete': True}}}


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {'scenes': {'AB': [{'mock': 1}], 'AC': [{'mock': 2}]}}
        self.result = {'state': 'SAFE', 'safe_candidate': deepcopy(self.candidate),
            'evaluation': receipt(), 'safe_upper_bound_J': '1',
            'safe_solution_source': 'initial_constructor'}
        self.spec = {'scene_spec': {'AB': {}, 'AC': {}}}
        self.status = 'NORMAL_COMPLETION'
        self.calls = []

    def original(self, result, spec, folder, **kwargs):
        self.calls.append((deepcopy(result), deepcopy(spec), folder, deepcopy(kwargs)))
        return {'execution': {'execution_status': self.status}, 'usable_U_J': '1'}

    def validator(self, candidate):
        self.assertEqual(candidate, self.candidate)
        return {'state': 'COMPLETE_STRUCTURAL_DOMAIN_MEMBER'}

    def method(self, **kwargs):
        values = dict(input_valid=True, source_valid=True, errors=[],
            original_audit=self.original, candidate_validator=self.validator)
        values.update(kwargs)
        return admission.method_records(self.result, self.spec, 'fake-folder', **values)

    def post(self, fresh=None, **kwargs):
        values = dict(receipt_issues=lambda *args: [],
            exact_enclosure=lambda *args: {'accepted': True},
            legality={'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'})
        values.update(kwargs)
        return admission.post_records(self.result, fresh or receipt(stamp=2),
            self.candidate, self.spec, **values)

    def test_normal_complete_safe_domain_is_post_eligible(self):
        result = self.method()
        self.assertTrue(result['post_eligible'])
        self.assertEqual(result['comparison_eligible_U_J'], '1')
        self.assertEqual(self.calls[0][3], dict(input_valid=True, source_valid=True, errors=[]))

    def test_all_normal_statuses_preserve_completed_safe(self):
        for state in admission.NORMAL:
            self.status = state
            self.assertTrue(self.method()['post_eligible'])

    def test_numeric_anomaly_retains_old_evidence_but_blocks_post_and_ranking(self):
        self.status = 'NUMERICAL_ANOMALY_OBSERVED'
        result = self.method()
        self.assertEqual(result['usable_U_J'], '1')
        self.assertIsNotNone(result['retained_safe_evidence'])
        self.assertFalse(result['retained_safe_evidence']['normal_ranking_eligible'])
        self.assertFalse(result['post_eligible'])
        self.assertIsNone(result['comparison_eligible_U_J'])

    def test_technical_failure_cannot_be_converted_to_normal(self):
        self.status = 'TECHNICAL_FAILURE_CONFIRMED'
        result = self.method()
        self.assertEqual(result['usable_U_J'], '1')
        self.assertFalse(result['normal_terminal'])
        self.assertFalse(result['post_eligible'])

    def test_domain_rejected_blocks_reuse(self):
        result = self.method(candidate_validator=lambda _: {'passed': False})
        self.assertFalse(result['domain_valid'])
        self.assertIsNone(result['usable_U_J'])

    def test_validator_exception_fails_closed(self):
        def fail(_):
            raise ValueError('wrong sparse start')
        result = self.method(candidate_validator=fail)
        self.assertFalse(result['domain_valid'])
        self.assertFalse(result['post_eligible'])

    def test_validator_unknown_success_shape_fails_closed(self):
        self.assertFalse(self.method(candidate_validator=lambda _: True)['domain_valid'])

    def test_initial_and_accepted_native_candidates_are_checked(self):
        self.result['initialisation'] = {'witness': {'candidate': {'bad': 'initial'},
            'evaluation': {'state': 'SAFE'}}}
        result = self.method(candidate_validator=lambda c: {'passed': c == self.candidate})
        self.assertFalse(result['domain_valid'])
        self.assertEqual(len(result['domain_checks']), 2)

    def test_duplicate_final_and_native_candidate_only_checked_once(self):
        self.result['diagnostic'] = {'evaluations': [{'accepted_safe': True,
            'candidate': deepcopy(self.candidate)}]}
        self.assertEqual(len(self.method()['domain_checks']), 1)

    def test_missing_input_source_proof_blocks_post(self):
        for key in ('input_valid', 'source_valid'):
            for value in (None, False):
                result = self.method(**{key: value})
                self.assertFalse(result['post_eligible'])
                self.assertIsNone(result['usable_U_J'])

    def test_supplied_errors_do_not_allow_normal_ranking(self):
        self.assertFalse(self.method(errors=['technical'])['post_eligible'])

    def test_no_safe_is_not_an_error_or_post_eligible(self):
        self.result = {'state': 'UNRESOLVED'}
        result = self.method(original_audit=lambda *a, **k: {
            'execution': {'execution_status': 'NORMAL_TIME_LIMIT'}, 'usable_U_J': None})
        self.assertIsNone(result['domain_valid'])
        self.assertTrue(result['normal_terminal'])
        self.assertFalse(result['post_eligible'])

    def test_original_audit_exception_does_not_retry(self):
        calls = []
        def fail(*args, **kwargs):
            calls.append(1)
            raise RuntimeError('audit source drift')
        result = self.method(original_audit=fail)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result['usable_U_J'])
        self.assertFalse(result['post_eligible'])

    def test_mismatching_final_u_ledger_blocks_post(self):
        self.result['safe_upper_bound_J'] = '2'
        self.assertFalse(self.method()['post_eligible'])

    def test_post_same_complete_candidate_passes_without_replacing_u(self):
        result = self.post()
        self.assertTrue(result['passed'], result)
        self.assertFalse(result['new_U'])
        self.assertEqual(result['old_U_J_unchanged'], '1')

    def test_post_boundary_or_late_completion_rejected(self):
        for stamp in (60, 60.1, -1, None, True, float('nan')):
            self.assertFalse(self.post(receipt(stamp=stamp))['passed'])

    def test_post_candidate_change_rejected(self):
        other = {'scenes': {'AB': [], 'AC': []}}
        result = admission.post_records(self.result, receipt(stamp=2), other, self.spec,
            receipt_issues=lambda *args: [], exact_enclosure=lambda *args: {'accepted': True},
            legality={'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'})
        self.assertFalse(result['passed'])
        self.assertIn('POST_CANDIDATE_CHANGED', result['issues'])

    def test_post_scene_coverage_mismatch_rejected(self):
        fresh = receipt(stamp=2)
        fresh['scenes'].pop('AC')
        self.assertFalse(self.post(fresh)['passed'])

    def test_post_non_safe_prefix_or_incomplete_scene_cannot_be_admitted(self):
        for field, value in (('state', 'UNRESOLVED'), ('rankable_energy', False)):
            fresh = receipt(stamp=2)
            fresh[field] = value
            self.assertFalse(self.post(fresh)['passed'])
        fresh = receipt(stamp=2)
        fresh['scenes']['AB']['complete'] = False
        self.assertFalse(self.post(fresh)['passed'])

    def test_post_invalid_legality_or_receipt_rejected(self):
        self.assertFalse(self.post(legality={'state': 'INVALID_SCHEDULE'})['passed'])
        self.assertFalse(self.post(receipt_issues=lambda *a: ['SCENE_NOT_COMPLETE_SAFE'])['passed'])

    def test_post_not_original_outward_weighted_interval_rejected(self):
        self.assertFalse(self.post(exact_enclosure=lambda *a: {'accepted': False})['passed'])

    def test_post_disjoint_energy_rejected(self):
        fresh = receipt(upper='2', stamp=2)
        fresh['weighted_energy_J'] = ['1.5', '2']
        self.assertFalse(self.post(fresh)['passed'])

    def test_post_overlap_need_not_have_identical_endpoints(self):
        fresh = receipt(upper='1.001', stamp=2)
        self.assertTrue(self.post(fresh)['passed'])

    def test_post_receipt_upper_ledger_must_match(self):
        fresh = receipt(stamp=2)
        fresh['safe_upper_bound_J'] = '2'
        self.assertFalse(self.post(fresh)['passed'])

    def test_post_wrong_budget_or_callback_error_fails_closed(self):
        self.assertFalse(self.post(seconds=61)['passed'])
        def fail(*args):
            raise RuntimeError('no original enclosure')
        self.assertFalse(self.post(exact_enclosure=fail)['passed'])

    def test_all_checks_leave_arguments_unchanged(self):
        fresh = receipt(stamp=2)
        before = deepcopy((self.result, self.candidate, self.spec, fresh))
        self.method()
        self.post(fresh)
        self.assertEqual(before, (self.result, self.candidate, self.spec, fresh))


if __name__ == '__main__':
    unittest.main(verbosity=2)
