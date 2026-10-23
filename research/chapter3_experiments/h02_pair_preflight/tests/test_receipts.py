"""Receipt acceptance tests using invented values; no physical core imports."""
import copy
import unittest
from fractions import Fraction
from h02_pair_preflight.common import ContractError
from h02_pair_preflight.receipts import safe_receipt, thermal_witness
from h02_pair_preflight.tests.fixtures import candidate_for, mock_safe_receipt


class ReceiptContractTests(unittest.TestCase):
    def setUp(self):
        nodes = ['CPU1', 'CPU2', 'GPU0', 'NPU0']
        self.instance = {'id': 'base__R1', 'window_ms': '400',
            'platform': {'external_common_power_W': '0.30', 'node_order': nodes,
                        'power_model_temperature_range_degC': ['20', '100']},
            'scenarios': [{'id': scene, 'weight': '1/2',
                'maximum_temperature_degC': ['80'] * 4,
                'entry': {'temperature_degC': ['50'] * 4},
                'stage_instances': [{'id': scene + '::A.pre', 'shared_stage_id': 'A.pre'}]}
                for scene in ['AB_offset_0ms', 'AC_offset_0ms']]}
        self.accuracy = {'energy_absolute_error_J': '0.000001',
                         'energy_relative_error': '0.000001',
                         'temperature_enclosure_width_K': '0.001'}
        self.candidate = candidate_for(self.instance)
        self.receipt = mock_safe_receipt(self.instance, self.candidate, self.accuracy)
        self.scene = self.receipt['scenes']['AB_offset_0ms']

    def accept(self, receipt=None, seconds=120):
        return safe_receipt(self.instance, self.candidate,
                            self.receipt if receipt is None else receipt,
                            self.accuracy, seconds)

    def rejected(self, expected=None):
        with self.assertRaisesRegex(ContractError, expected or '.'):
            self.accept()

    def test_complete_mock_safe_acceptance(self):
        self.assertEqual(self.accept(), {'lower': '1', 'upper': '1', 'all_scenes_complete': True})
        self.assertEqual(self.receipt['evidence_kind'], 'MOCK_ONLY')

    def test_missing_each_scene(self):
        for sid in self.receipt['scenes']:
            r = copy.deepcopy(self.receipt); del r['scenes'][sid]
            with self.subTest(sid=sid), self.assertRaisesRegex(ContractError, 'INCOMPLETE_SCENE_RECEIPT'):
                self.accept(r)

    def test_extra_scene(self):
        self.receipt['scenes']['AD'] = copy.deepcopy(self.scene)
        self.rejected('INCOMPLETE_SCENE_RECEIPT')

    def test_scene_not_complete_or_not_safe(self):
        for field, value in [('complete', False), ('rankable_energy', False),
                             ('energy_accuracy_met', False), ('state', 'UNRESOLVED')]:
            r = copy.deepcopy(self.receipt); r['scenes']['AB_offset_0ms'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, 'SCENE_NOT_COMPLETE_SAFE'):
                self.accept(r)

    def test_aggregate_not_rankable(self):
        self.receipt['rankable_energy'] = False; self.rejected('NOT_SAFE_RECEIPT')

    def test_upper_bound_mismatch(self):
        self.receipt['safe_upper_bound_J'] = '0.99'; self.rejected('SAFE_UPPER_BOUND_MISMATCH')

    def test_reversed_interval(self):
        self.scene['energy_J'] = ['1.1', '1']; self.rejected('ENERGY_INTERVAL_ORDER')

    def test_negative_interval(self):
        self.scene['energy_J'] = ['-1', '1']; self.rejected('ENERGY_INTERVAL_ORDER')

    def test_energy_interval_shape(self):
        self.scene['energy_J'] = ['1']; self.rejected('ENERGY_INTERVAL_SHAPE')

    def test_energy_interval_precision(self):
        self.scene['energy_J'] = ['0.9', '1.1']; self.rejected('SCENE_ENERGY_PRECISION')

    def test_component_enclosure(self):
        self.scene['energy_components_J']['activity'] = ['0.21', '0.21']
        self.rejected('SCENE_ENERGY_COMPONENT_ENCLOSURE')

    def test_missing_component(self):
        del self.scene['energy_components_J']['activity']; self.rejected('ENERGY_COMPONENTS')

    def test_weighted_energy_respects_scene_weights(self):
        self.receipt['weighted_energy_J'] = ['0.5', '0.5']
        self.receipt['safe_upper_bound_J'] = '0.5'; self.rejected('WEIGHTED_ENERGY_ENCLOSURE')

    def test_weighted_energy_precision(self):
        self.receipt['weighted_energy_J'] = ['0.9', '1.1']
        self.receipt['safe_upper_bound_J'] = '1.1'; self.rejected('WEIGHTED_ENERGY_PRECISION')

    def test_external_energy_once_not_twice(self):
        weighted_external = sum(Fraction(scene['weight']) * Fraction(self.receipt['scenes'][scene['id']]['energy_components_J']['external_common'][0]) for scene in self.instance['scenarios'])
        self.assertEqual(weighted_external, Fraction('0.12'))
        self.assertNotEqual(weighted_external, Fraction('0.24'))
        self.accept()

    def test_wrong_external_energy_rejected_even_with_adjusted_total(self):
        self.scene['energy_components_J']['external_common'] = ['0.24', '0.24']
        self.scene['energy_components_J']['baseline'] = ['0.38', '0.38']
        self.rejected('EXTERNAL_POWER_ACCOUNTING')

    def test_full_tail_required(self):
        self.scene['covered_until_s'] = '0.3'; self.rejected('SCENE_WINDOW_COVERAGE')

    def test_each_node_required(self):
        for key in ['peaks_degC', 'minimum_degC']:
            r = copy.deepcopy(self.receipt); del r['scenes']['AB_offset_0ms'][key]['NPU0']
            with self.subTest(key=key), self.assertRaisesRegex(ContractError, 'TEMPERATURE_NODE_COVERAGE'):
                self.accept(r)

    def test_temperature_over_limit(self):
        self.scene['peaks_degC']['NPU0'] = ['80.1', '80.1']; self.rejected('CONTINUOUS_THERMAL_BOUNDS')

    def test_temperature_outside_model(self):
        self.scene['minimum_degC']['CPU1'] = ['19', '19']; self.rejected('CONTINUOUS_THERMAL_BOUNDS')

    def test_peak_missing_entry(self):
        self.scene['peaks_degC']['CPU1'] = ['49', '49']; self.rejected('TEMPERATURE_RANGE_OR_PRECISION')

    def test_peak_precision(self):
        self.scene['peaks_degC']['CPU1'] = ['50', '50.01']; self.rejected('TEMPERATURE_RANGE_OR_PRECISION')

    def test_deadline_equality_is_late(self):
        self.receipt['completed_at_elapsed_s'] = 120; self.rejected('LATE_OR_INVALID_SAFE_TIMESTAMP')

    def test_invalid_timestamps(self):
        for value in [True, False, float('nan'), float('inf'), -0.1, '1']:
            r = copy.deepcopy(self.receipt); r['completed_at_elapsed_s'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ContractError, 'LATE_OR_INVALID_SAFE_TIMESTAMP'):
                self.accept(r)

    def test_formed_before_deadline_returned_after(self):
        self.receipt['completed_at_elapsed_s'] = 119.99
        self.receipt['returned_at_elapsed_s'] = 121.0
        self.assertTrue(self.accept()['all_scenes_complete'])

    def test_60_second_audit_cutoff(self):
        self.receipt['completed_at_elapsed_s'] = 60
        with self.assertRaisesRegex(ContractError, 'LATE_OR_INVALID_SAFE_TIMESTAMP'):
            self.accept(seconds=60)

    def test_wrong_input_identity(self):
        self.receipt['evidence_identity']['input_sha256'] = 'bad'; self.rejected('RECEIPT_EVIDENCE_IDENTITY')

    def test_wrong_candidate_identity(self):
        self.receipt['evidence_identity']['candidate_sha256'] = 'bad'; self.rejected('RECEIPT_EVIDENCE_IDENTITY')

    def test_wrong_problem_id(self):
        self.receipt['problem_id'] = 'base__R2'; self.rejected('RECEIPT_PROBLEM_ID')

    def test_policy_and_numerical_protocol(self):
        for key, value in [('control_policy', {}), ('numerical_protocol', 'unverified')]:
            r = copy.deepcopy(self.receipt); r[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): self.accept(r)

    def test_technical_error_or_violations_not_safe(self):
        for reason in ['INTERFACE_ERROR', 'INTERNAL_CONSISTENCY_ERROR', 'NUMERICAL_ERROR', 'RESOURCE_LIMIT', 'INVALID_INPUT']:
            r = copy.deepcopy(self.receipt); r['reason'] = reason
            with self.subTest(reason=reason), self.assertRaisesRegex(ContractError, 'SAFE_TECHNICAL_OR_VIOLATION'):
                self.accept(r)
        self.receipt['violations'] = [{'mock_only': True}]
        self.rejected('SAFE_TECHNICAL_OR_VIOLATION')

    def test_legality_requires_all_scenes(self):
        del self.receipt['legality']['scenes']['AC_offset_0ms']; self.rejected('RECEIPT_LEGALITY')

    def violation(self, **updates):
        result = {'scene_id': 'AB_offset_0ms', 'node': 'NPU0', 'time_s': '0.2',
                  'temperature_degC': ['81', '81.001'], 'limit_degC': '80',
                  'formed_at_elapsed_s': 1.0}
        result.update(updates)
        return {'state': 'THERMAL_VIOLATION', 'violations': [result], 'evidence_kind': 'MOCK_ONLY'}

    def test_thermal_witness_valid(self):
        r = self.violation(); self.assertEqual(thermal_witness(self.instance, r, 60), r['violations'])

    def test_thermal_witness_late_returns_none(self):
        self.assertEqual(thermal_witness(self.instance, self.violation(formed_at_elapsed_s=60), 60), [])

    def test_thermal_witness_unresolved_enclosure_not_violation(self):
        with self.assertRaisesRegex(ContractError, 'VIOLATION_NOT_CERTIFIED_IN_MODEL_RANGE'):
            thermal_witness(self.instance, self.violation(temperature_degC=['79.99', '80.01']), 60)

    def test_thermal_witness_model_range(self):
        with self.assertRaisesRegex(ContractError, 'VIOLATION_NOT_CERTIFIED_IN_MODEL_RANGE'):
            thermal_witness(self.instance, self.violation(temperature_degC=['101', '101.1']), 60)

    def test_thermal_witness_wrong_identity_or_limit(self):
        for updates in [{'scene_id': 'UNKNOWN'}, {'node': 'NPU9'}, {'limit_degC': '79'}]:
            with self.subTest(updates=updates), self.assertRaises(ContractError):
                thermal_witness(self.instance, self.violation(**updates), 60)

    def test_thermal_witness_window_and_timestamp(self):
        with self.assertRaisesRegex(ContractError, 'VIOLATION_TIME'):
            thermal_witness(self.instance, self.violation(time_s='0.5'), 60)
        for value in [True, float('nan'), -1]:
            with self.subTest(value=value):
                self.assertEqual(thermal_witness(self.instance, self.violation(formed_at_elapsed_s=value), 60), [])

    def test_nested_technical_error_cannot_be_SAFE(self):
        self.scene['reason']='RESOURCE_LIMIT'
        self.rejected('SAFE_TECHNICAL_OR_VIOLATION')

    def test_minimum_precision_and_peak_consistency(self):
        self.scene['minimum_degC']['CPU1']=['49','50']
        self.rejected('TEMPERATURE_RANGE_OR_PRECISION')

    def test_unresolved_without_witness_retains_no_violation(self):
        self.assertEqual(thermal_witness(self.instance, {'state': 'UNRESOLVED', 'violations': []}, 60), [])


if __name__ == '__main__':
    unittest.main()
