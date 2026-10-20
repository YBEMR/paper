"""Original-input delegation and evidence transfer; mocked physical receipts.

Real small-domain propagation is kept in the separate persistent gate. No
solver or research candidate is used by these receipt-boundary tests.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

import neighborhood
import neighborhood_adapter as wrapper
from test_neighborhood_condition import mock_condition_fixture
from thermal import Exhausted


class N1AdapterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = mock_condition_fixture()
        self.condition = neighborhood.make_n1_condition(**self.fixture)
        self.instance = self.fixture['instance']
        self.budget = self.fixture['budget']
        self.sid = self.instance['scenarios'][0]['id']
        self.candidate = {'scenes': {self.sid:
            deepcopy(self.fixture['seed_candidate']['scenes'][self.sid])}}
        self.receipt = deepcopy(self.fixture['seed_receipt']['scenes'][self.sid])

    def evaluate(self, **extra):
        return wrapper.evaluate_n1_scene(self.instance, self.condition,
            self.sid, self.candidate, budget=self.budget, **extra)

    def test_original_full_input_and_receipt_are_not_replaced_or_rewritten(self):
        before = deepcopy(self.receipt)
        with patch.object(wrapper, 'evaluate_partial_scene', return_value=self.receipt) as call:
            out = self.evaluate()
        self.assertEqual(out['state'], 'SAFE')  # mock physical energy only
        self.assertIs(call.call_args.args[0], self.instance)
        self.assertEqual(len(call.call_args.args[0]['scenarios']), 2)
        self.assertIs(out['receipt'], self.receipt)
        self.assertEqual(out['receipt'], before)
        self.assertNotIn('safe_upper_bound_J', out)
        self.assertNotIn('weighted_energy_J', out)
        self.assertFalse(out['independently_proven_optimal'])

    def test_fixed_start_change_rejected_before_original_evaluation(self):
        self.candidate['scenes'][self.sid][0]['start_ms'] = '20'
        with patch.object(wrapper, 'evaluate_partial_scene') as call:
            out = self.evaluate()
        call.assert_not_called()
        self.assertEqual(out['state'], 'INVALID_INPUT')
        self.assertIsNone(out['receipt'])

    def test_expired_after_inner_violation_keeps_the_original_evidence(self):
        violation = {'state': 'THERMAL_VIOLATION', 'reason': 'MOCK_POINT_WITNESS',
                     'violations': [{'node': 'CPU1', 'time_s': '1/100'}]}
        def committed(*args):
            self.budget.check = lambda: (_ for _ in ()).throw(Exhausted('test_expired'))
            return violation
        with patch.object(wrapper, 'evaluate_partial_scene', side_effect=committed):
            out = self.evaluate()
        self.assertIs(out['receipt'], violation)
        self.assertEqual(out['state'], 'THERMAL_VIOLATION')
        self.assertFalse(out['rankable_energy'])

    def test_expired_after_committed_SAFE_retains_only_the_existing_local_receipt(self):
        def committed(*args):
            self.budget.check = lambda: (_ for _ in ()).throw(Exhausted('test_expired'))
            return self.receipt
        with patch.object(wrapper, 'evaluate_partial_scene', side_effect=committed):
            out = self.evaluate()
        self.assertEqual(out['state'], 'SAFE')
        self.assertIs(out['receipt'], self.receipt)
        self.assertTrue(out['rankable_energy'])
        self.assertNotIn('weighted_energy_J', out)

    def test_late_SAFE_is_retained_as_raw_evidence_without_safe_acceptance(self):
        self.receipt['completed_at_elapsed_s'] = self.budget.seconds + 1
        with patch.object(wrapper, 'evaluate_partial_scene', return_value=self.receipt):
            out = self.evaluate()
        self.assertIs(out['receipt'], self.receipt)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertFalse(out['rankable_energy'])

    def test_accuracy_change_and_budget_exhaustion_do_not_call_thermal(self):
        with patch.object(wrapper, 'evaluate_partial_scene') as call:
            changed = self.evaluate(accuracy={'energy_absolute_error_J': '0.1'})
            self.assertEqual(changed['state'], 'INVALID_INPUT')
            self.budget.check = lambda: (_ for _ in ()).throw(Exhausted('test_expired'))
            expired = self.evaluate()
        call.assert_not_called()
        self.assertEqual(expired['state'], 'UNRESOLVED')
        self.assertIsNone(expired['receipt'])


if __name__ == '__main__':
    unittest.main()
