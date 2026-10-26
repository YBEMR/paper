"""Receipt-shape and lifecycle fixtures only: zero thermal/solver calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from admission import admit, scene_view, validate_schedule

ACCURACY = {'temperature_enclosure_width_K': '0.001',
            'energy_absolute_error_J': '0.000001', 'energy_relative_error': '0.000001'}


class ReceiptAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = HERE.parent / 'results/small_full_chain_precheck02'
        cls.instance = json.loads((fixture/'restricted_input.json').read_text(encoding='utf-8'))
        full = json.loads((fixture/'witness_candidate.json').read_text(encoding='utf-8'))
        cls.sid = 'AB_offset_0ms'
        cls.entry = {'scene_id': cls.sid, 'shared_A_device': 'NPU0',
                     'candidate': {'scenes': {cls.sid: full['scenes'][cls.sid]}}}
        cls.checked = validate_schedule(scene_view(cls.instance, cls.sid), cls.entry['candidate'])
        assert cls.checked['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED'

    def receipt(self):
        nodes = self.instance['platform']['node_order']
        scene = {'scene_id': self.sid, 'state': 'SAFE', 'reason': 'COMPLETE_CONTINUOUS_ENCLOSURE',
                 'complete': True, 'rankable_energy': True, 'energy_accuracy_met': True,
                 'energy_J': ['1', '1'], 'covered_until_s': '2/5',
                 'completed_at_elapsed_s': 1.0, 'elapsed_s': 1.0, 'violations': [],
                 'peaks_degC': {n: ['55', '55'] for n in nodes},
                 'minimum_degC': {n: ['45', '45'] for n in nodes},
                 'final_temperature_degC': {n: ['48', '48'] for n in nodes},
                 'energy_components_J': {'baseline': ['.4', '.4'], 'activity': ['.3', '.3'],
                                         'external_common': ['.1', '.1'], 'temperature_correction': ['.2', '.2']},
                 'node_injected_energy_J': {n: ['.225', '.225'] for n in nodes},
                 'conservation_energy_J': ['1', '1']}
        return {'state': 'SAFE', 'reason': 'ALL_SCENES_COMPLETE_AND_SAFE',
                'problem_id': self.instance['id'], 'legality': deepcopy(self.checked),
                'numerical_protocol': 'directed-decimal60-taylor18-scaled100-v1',
                'scenes': {self.sid: scene}, 'violations': [], 'weighted_energy_J': ['1', '1']}

    def evaluate(self, raw, **kwargs):
        return admit(self.instance, self.entry, raw, kwargs.get('start', 100.0),
                     kwargs.get('call', 110.0), kwargs.get('root', 200.0), ACCURACY)

    def violation(self, raw, formed=1.0):
        scene = raw['scenes'][self.sid]
        witness = {'scene_id': self.sid, 'node': 'CPU1', 'time_s': '1/20',
                   'temperature_degC': ['81', '81.0001'], 'limit_degC': '80',
                   'formed_at_elapsed_s': formed}
        scene.update(state='THERMAL_VIOLATION', reason='wall_time_limit',
                     complete=False, rankable_energy=False, violations=[witness])
        raw.update(state='THERMAL_VIOLATION', reason='wall_time_limit', violations=[deepcopy(witness)])
        return witness

    def test_normal_complete_safe(self):
        out = self.evaluate(self.receipt())
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(out['energy_J'], ['1', '1'])
        self.assertFalse(out['technical_stop'])

    def test_late_outer_timeout_keeps_inner_timely_complete(self):
        raw = self.receipt()
        raw.update(state='UNRESOLVED', reason='wall_time_limit', weighted_energy_J=None,
                   rankable_energy=False, elapsed_s=11.0)
        self.assertEqual(self.evaluate(raw)['state'], 'SAFE')

    def test_completion_at_deadline_is_not_timely(self):
        raw = self.receipt()
        raw['scenes'][self.sid]['completed_at_elapsed_s'] = 10.0
        self.assertEqual(self.evaluate(raw)['state'], 'UNRESOLVED')
        self.assertIsNone(self.evaluate(raw)['energy_J'])

    def test_root_deadline_wins_over_call(self):
        raw = self.receipt()
        raw['scenes'][self.sid]['completed_at_elapsed_s'] = 3.0
        self.assertEqual(self.evaluate(raw, root=102.0)['state'], 'UNRESOLVED')

    def test_timely_violation_survives_outer_timeout(self):
        raw = self.receipt()
        self.violation(raw)
        raw['state'] = 'UNRESOLVED'
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'VIOLATION')
        self.assertEqual(len(out['timely_violations']), 1)
        self.assertFalse(out['technical_stop'])
        self.assertIsNone(out['energy_J'])

    def test_technical_after_point_keeps_witness_and_stops(self):
        raw = self.receipt()
        self.violation(raw)
        raw['scenes'][self.sid]['reason'] = 'NUMERICAL_ERROR'
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'VIOLATION')
        self.assertTrue(out['technical_stop'])

    def test_late_point_does_not_establish_violation(self):
        raw = self.receipt()
        self.violation(raw, 10.0)
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertEqual(out['late_violation_count'], 1)
        self.assertFalse(out['timely_violations'])

    def test_non_strict_point_rejected(self):
        raw = self.receipt()
        self.violation(raw)
        for v in [raw['violations'][0], raw['scenes'][self.sid]['violations'][0]]:
            v['temperature_degC'] = ['80', '80.0001']
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_point_outside_model_range_rejected(self):
        raw = self.receipt()
        self.violation(raw)
        for v in [raw['violations'][0], raw['scenes'][self.sid]['violations'][0]]:
            v['temperature_degC'] = ['101', '102']
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_invalid_scene_point_rejected(self):
        raw = self.receipt()
        self.violation(raw)
        for v in [raw['violations'][0], raw['scenes'][self.sid]['violations'][0]]:
            v['scene_id'] = 'other'
        self.assertEqual(self.evaluate(raw)['state'], 'TECHNICAL_UNRESOLVED')

    def test_identity_and_legality_drift_rejected(self):
        for field, value in [('problem_id', 'other'), ('legality', {}), ('numerical_protocol', 'other')]:
            raw = self.receipt()
            raw[field] = value
            self.assertEqual(self.evaluate(raw)['state'], 'TECHNICAL_UNRESOLVED')

    def test_prefix_energy_never_usable(self):
        raw = self.receipt()
        raw['scenes'][self.sid].update(state='UNRESOLVED', reason='wall_time_limit', complete=False,
                                      rankable_energy=False, covered_until_s='1/10')
        raw.update(state='UNRESOLVED', reason='wall_time_limit')
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertIsNone(out['energy_J'])

    def test_safe_prefix_claim_is_technical(self):
        raw = self.receipt()
        raw['scenes'][self.sid]['covered_until_s'] = '1/10'
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_node_coverage_and_limit_guard(self):
        mutations = [('peaks_degC', 'CPU1', ['81', '81']),
                     ('minimum_degC', 'CPU1', ['19', '19']),
                     ('final_temperature_degC', 'CPU1', ['60', '60'])]
        for field, node, value in mutations:
            raw = self.receipt()
            raw['scenes'][self.sid][field][node] = value
            self.assertTrue(self.evaluate(raw)['technical_stop'])
        raw = self.receipt()
        del raw['scenes'][self.sid]['peaks_degC']['GPU0']
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_energy_width_and_conservation_guard(self):
        mutations = [('energy_J', ['1', '1.01']), ('conservation_energy_J', ['2', '2'])]
        for field, value in mutations:
            raw = self.receipt()
            raw['scenes'][self.sid][field] = value
            self.assertTrue(self.evaluate(raw)['technical_stop'])
        raw = self.receipt()
        raw['scenes'][self.sid]['node_injected_energy_J']['CPU1'] = ['1', '1']
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_normal_unresolved_reasons_continue(self):
        for reason in ['wall_time_limit', 'panel_limit', 'peak_refinement_limit',
                       'ENERGY_ERROR_TARGET', 'TEMPERATURE_LIMIT_UNRESOLVED', 'POWER_MODEL_RANGE_UNRESOLVED']:
            raw = self.receipt()
            raw['scenes'][self.sid].update(state='UNRESOLVED', reason=reason, complete=False,
                                          rankable_energy=False, covered_until_s='1/10')
            raw.update(state='UNRESOLVED', reason='NOT_ALL_SCENES_COMPLETE_AND_SAFE')
            out = self.evaluate(raw)
            self.assertEqual(out['state'], 'UNRESOLVED')
            self.assertFalse(out['technical_stop'])

    def test_technical_reasons_stop(self):
        for reason in ['RESOURCE_LIMIT', 'INTERNAL_CONSISTENCY_ERROR', 'NUMERICAL_ERROR']:
            raw = self.receipt()
            raw['scenes'][self.sid].update(state='UNRESOLVED', reason=reason)
            out = self.evaluate(raw)
            self.assertEqual(out['state'], 'TECHNICAL_UNRESOLVED')
            self.assertTrue(out['technical_stop'])

    def test_missing_scene_timeout_continues(self):
        raw = self.receipt()
        raw.update(state='UNRESOLVED', reason='wall_time_limit', scenes={})
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertFalse(out['technical_stop'])

    def test_timeout_before_legality_commit_is_not_technical(self):
        raw = self.receipt()
        raw.update(state='UNRESOLVED', reason='wall_time_limit', scenes={})
        del raw['legality']
        out = self.evaluate(raw)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertFalse(out['technical_stop'])
        self.assertIsNone(out['energy_J'])

    def test_malformed_receipt_and_scene_are_technical(self):
        self.assertTrue(self.evaluate(None)['technical_stop'])
        raw = self.receipt()
        raw['scenes'][self.sid] = []
        self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_negative_or_nonfinite_clock_rejected(self):
        for formed in [-1.0, float('nan'), float('inf')]:
            raw = self.receipt()
            raw['scenes'][self.sid]['completed_at_elapsed_s'] = formed
            self.assertTrue(self.evaluate(raw)['technical_stop'])

    def test_shape_checks_do_not_call_thermal_or_optimization(self):
        import admission
        self.assertFalse(any(name in admission.__dict__ for name in (
            'evaluate_candidate', 'evaluate_piecewise', 'linprog', 'milp', 'MatlabSession')))
        self.assertEqual(self.evaluate(self.receipt())['state'], 'SAFE')


if __name__ == '__main__':
    unittest.main()
