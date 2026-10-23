"""External energy enclosure regressions; recorded receipts only, no evaluator calls."""
import copy
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path
import unittest

from h02_pair_preflight.common import ContractError, sha
from h02_pair_preflight.receipts import safe_receipt
from h02_pair_preflight.tests.test_receipts import ReceiptContractTests
from h02_pair_b0.exports import verify_final_export

ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / "research/chapter3_experiments/results/response_information_execution01/slot_1/planner_public"


class ExternalIntervalTests(unittest.TestCase):
    def setUp(self):
        f = ReceiptContractTests()
        f.setUp()
        self.i, self.c, self.a, self.r = f.instance, f.candidate, f.accuracy, f.receipt
        self.sid = self.i['scenarios'][0]['id']

    def accept(self):
        return safe_receipt(self.i, self.c, self.r, self.a, 120)

    def outward(self, delta):
        """Widen scene/component/weighted enclosures consistently with exact rationals."""
        scene = self.r['scenes'][self.sid]
        ext = F(self.i['platform']['external_common_power_W']) * F(self.i['window_ms']) / 1000
        scene['energy_components_J']['external_common'] = [str(ext - delta), str(ext + delta)]
        scene['energy_J'] = [str(F(1) - delta), str(F(1) + delta)]
        weight = F(self.i['scenarios'][0]['weight'])
        self.r['weighted_energy_J'] = [str(1 - weight * delta), str(1 + weight * delta)]
        self.r['safe_upper_bound_J'] = self.r['weighted_energy_J'][1]

    def test_exact_point_accepted(self):
        self.assertTrue(self.accept()['all_scenes_complete'])

    def test_narrow_outward_interval_accepted_without_epsilon(self):
        self.outward(F(1, 10**60))
        self.assertTrue(self.accept()['all_scenes_complete'])

    def test_interval_not_containing_exact_energy_rejected(self):
        self.outward(F(1, 10**60))
        self.r['scenes'][self.sid]['energy_components_J']['external_common'] = ['0.1200001', '0.1200002']
        self.r['scenes'][self.sid]['energy_J'] = ['1.0000001', '1.0000002']
        self.r['weighted_energy_J'] = ['1', '1.0000002']
        self.r['safe_upper_bound_J'] = '1.0000002'
        with self.assertRaisesRegex(ContractError, 'EXTERNAL_POWER_ACCOUNTING'):
            self.accept()

    def test_wrong_ledger_rejected_even_after_total_is_rebalanced(self):
        scene = self.r['scenes'][self.sid]
        scene['energy_components_J']['external_common'] = ['0.24', '0.24']
        scene['energy_components_J']['baseline'] = ['0.38', '0.38']
        with self.assertRaisesRegex(ContractError, 'EXTERNAL_POWER_ACCOUNTING'):
            self.accept()

    def test_too_wide_interval_with_matching_totals_is_rejected(self):
        self.outward(F(1, 100))
        with self.assertRaisesRegex(ContractError, 'SCENE_ENERGY_PRECISION'):
            self.accept()

    def test_wide_component_cannot_hide_in_narrow_scene(self):
        self.r['scenes'][self.sid]['energy_components_J']['external_common'] = ['0.11', '0.13']
        with self.assertRaisesRegex(ContractError, 'SCENE_ENERGY_COMPONENT_ENCLOSURE'):
            self.accept()

    def test_valid_external_interval_does_not_bypass_safety_gate(self):
        self.outward(F(1, 10**60))
        self.r['scenes'][self.sid]['peaks_degC']['NPU0'] = ['81', '81']
        with self.assertRaisesRegex(ContractError, 'CONTINUOUS_THERMAL_BOUNDS'):
            self.accept()

    def test_recorded_44_exports_readonly_and_final_best_unchanged(self):
        paths = [OLD / 'job.json', OLD / 'method/result.json', OLD / 'accepted_checkpoint.json']
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        packet = json.loads(paths[0].read_text(encoding='utf8'))['packet']
        result = json.loads(paths[1].read_text(encoding='utf8'))
        checkpoint = json.loads(paths[2].read_text(encoding='utf8'))
        initial = copy.deepcopy(result)
        i, accuracy = packet['planner']['instance'], packet['planner']['config']['accuracy_targets']
        accepted = [r for r in result['evaluations'] if r.get('accepted_safe') is True]
        self.assertEqual(len(accepted), 44)
        for row in accepted:
            with self.subTest(candidate=row['candidate_sha256']):
                self.assertEqual(sha(row['candidate']), row['candidate_sha256'])
                self.assertTrue(safe_receipt(i, row['candidate'], row['evaluation'], accuracy, 120)['all_scenes_complete'])
        checked = verify_final_export(packet, result)
        self.assertEqual(checked['best']['candidate'], result['safe_candidate'])
        self.assertEqual(checked['best']['evaluation'], result['evaluation'])
        self.assertEqual(checked['best']['candidate_sha256'], checkpoint['best']['candidate_sha256'])
        self.assertEqual(checked['best']['candidate_sha256'], 'f3c14d4f6767a5cb584e37643244a0c86b9b995405c7284e31d4765dfa194e41')
        self.assertEqual(checked['best']['evaluation']['safe_upper_bound_J'], '0.881087997280962231831028758232205265027499078298076990362288')
        self.assertEqual(result, initial)
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__ == '__main__':
    unittest.main()
