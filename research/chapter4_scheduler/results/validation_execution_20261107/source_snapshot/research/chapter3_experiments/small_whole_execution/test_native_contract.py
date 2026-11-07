"""K195 native-record fixtures only: no process, MATLAB, solve or heat."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_contract as nc


class NativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proposal = json.loads((HERE.parent / 'results/small_exact_protocol01/protocol_proposal.json').read_text(encoding='utf-8'))
        cls.reference = proposal['whole_proposal']['native_options_reference']['options_except_MaxTime']

    def ready(self):
        return dict(status='READY', release='2023b', license_checkout=True,
                    license_test=1, intlinprog_path='F:/fixture/intlinprog.m')

    def records(self):
        request = dict(remaining_s=290.0, cut_max_iterations=10)
        response = dict(status='SOLVED', options=dict(deepcopy(self.reference), MaxTime=280.0),
                        cut_max_iterations_declared=10,
                        cut_max_iterations_actual_effective=10)
        return request, response

    def test_ready_original_identity(self):
        self.assertTrue(nc.validate_ready(self.ready())['passed'])

    def test_ready_release_drift_rejected(self):
        ready = self.ready(); ready['release'] = '2024a'
        with self.assertRaises(ValueError): nc.validate_ready(ready)

    def test_not_ready_rejected(self):
        ready = self.ready(); ready['status'] = 'TOOLBOX_UNAVAILABLE'
        with self.assertRaises(ValueError): nc.validate_ready(ready)

    def test_checkout_missing_rejected(self):
        ready = self.ready(); ready['license_checkout'] = False
        with self.assertRaises(ValueError): nc.validate_ready(ready)

    def test_empty_solver_path_rejected(self):
        ready = self.ready(); ready['intlinprog_path'] = ''
        with self.assertRaises(ValueError): nc.validate_ready(ready)

    def test_license_test_boolean_rejected(self):
        ready = self.ready(); ready['license_test'] = True
        with self.assertRaises(ValueError): nc.validate_ready(ready)

    def test_original_options_accepted(self):
        request, response = self.records()
        result = nc.validate_request_response(request, response, self.reference)
        self.assertTrue(result['passed']); self.assertEqual(result['MaxTime'], 280)

    def test_normal_cutoff_status_not_success_claim(self):
        request, response = self.records(); response['status'] = 'BUDGET_EXHAUSTED_BEFORE_SOLVER'
        self.assertTrue(nc.validate_request_response(request, response, self.reference)['passed'])

    def test_tolerance_drift_rejected(self):
        request, response = self.records(); response['options']['ConstraintTolerance'] = 1e-8
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_hidden_preprocess_drift_rejected(self):
        request, response = self.records(); response['options']['LPPreprocess'] = 'basic'
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_added_option_rejected(self):
        request, response = self.records(); response['options']['NewOption'] = 0
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_missing_readback_rejected(self):
        request, response = self.records(); response.pop('options')
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_null_preserves_original_inf_json(self):
        request, response = self.records()
        self.assertIsNone(response['options']['ObjectiveCutOff'])
        nc.validate_request_response(request, response, self.reference)
        response['options']['ObjectiveCutOff'] = 1e300
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_zero_maxtime_rejected(self):
        request, response = self.records(); response['options']['MaxTime'] = 0
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_nonfinite_maxtime_rejected(self):
        for value in (float('nan'), float('inf'), True):
            request, response = self.records(); response['options']['MaxTime'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                nc.validate_request_response(request, response, self.reference)

    def test_maxtime_exceeds_remaining_rejected(self):
        request, response = self.records(); response['options']['MaxTime'] = 291
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_remaining_exceeds_root_rejected(self):
        request, response = self.records(); request['remaining_s'] = 301
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_declared_solver_cap_rejected(self):
        request, response = self.records()
        with self.assertRaises(ValueError):
            nc.validate_request_response(request, response, self.reference, solver_max_time_s=200)

    def test_evidence_solver_cap_rejected(self):
        for which in ('request', 'response'):
            request, response = self.records()
            (request if which == 'request' else response)['solver_max_time_s_declared'] = 200
            with self.subTest(which=which), self.assertRaises(ValueError):
                nc.validate_request_response(request, response, self.reference)

    def test_bridge_cut_constant_rejected(self):
        request, response = self.records()
        with self.assertRaises(ValueError):
            nc.validate_request_response(request, response, self.reference, cut_max_iterations=9)

    def test_native_cut_drift_rejected(self):
        request, response = self.records(); response['cut_max_iterations_actual_effective'] = 9
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)

    def test_root_budget_constant_rejected(self):
        request, response = self.records()
        with self.assertRaises(ValueError):
            nc.validate_request_response(request, response, self.reference, method_seconds=301)

    def test_original_zero_not_boolean(self):
        request, response = self.records(); response['options']['AbsoluteGapTolerance'] = False
        with self.assertRaises(ValueError): nc.validate_request_response(request, response, self.reference)


if __name__ == '__main__':
    unittest.main(verbosity=2)
