"""Pure K192 domain and existing-constructor checks; zero heat/solver calls."""
from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core


class DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((HERE.parents[1] / 'results/whole_long_budget01/method/input_instance.json').read_bytes())
        cls.result = core.produce(cls.original)
        cls.instance = cls.result['instance']

    def test_original_unchanged_and_physical_fields_preserved(self):
        self.assertTrue(core.assert_preserved(self.original, self.instance))
        self.assertEqual(self.original['id'], 'base__R1')
        self.assertEqual(self.original['window_ms'], '400')
        self.assertEqual(self.instance['platform']['node_order'], ['CPU1', 'CPU2', 'GPU0', 'NPU0'])

    def test_all_modes_original_exact_records(self):
        for shared, modes in self.instance['stage_modes'].items():
            self.assertTrue(all(mode in self.original['stage_modes'][shared] for mode in modes))
            self.assertEqual(len(modes), 4 if shared.endswith('.main') else 1)

    def test_shared_A_is_open_and_C_is_in_domain(self):
        self.assertEqual({mode['unit_id'] for mode in self.instance['stage_modes']['A.main']}, {'CPU1', 'NPU0'})
        for shared, unit in core.C_SHARED.items():
            self.assertTrue(any(mode['unit_id'] == unit for mode in self.instance['stage_modes'][shared]))
        self.assertEqual(self.instance['stage_modes']['A.pre'][0]['unit_id'], 'CPU1')
        self.assertEqual(self.instance['stage_modes']['B.pre'][0]['unit_id'], 'CPU2')

    def test_exact_counts(self):
        counts = self.result['counts']
        self.assertEqual(counts['stage_mode_start_options'], 78)
        self.assertEqual(counts['scene_evaluations_for_full_coverage'], 1550)
        self.assertEqual(counts['global_legal_complete_arrangements'], 274500)
        self.assertEqual(counts['by_scene']['AB_offset_0ms']['legal_count_by_shared_A_unit'], {'CPU1': 450, 'NPU0': 650})
        self.assertEqual(counts['by_scene']['AC_offset_0ms']['legal_count_by_shared_A_unit'], {'CPU1': 90, 'NPU0': 360})

    def test_B_wait_starts_are_original_grid(self):
        by = self.instance['start_domain']['by_scene_stage_ms']['AB_offset_0ms']
        self.assertEqual(by['AB_offset_0ms::B_r1::B.main'], ['30', '35', '40', '45', '50'])
        for scene in self.instance['scenarios']:
            for values in self.instance['start_domain']['by_scene_stage_ms'][scene['id']].values():
                self.assertTrue(all((Q(value) / 5).denominator == 1 for value in values))

    def test_C_H_seed_complete_and_common_domain_member(self):
        seed = self.result['C_seed']
        self.assertIsNotNone(seed)
        from schedules import validate_schedule
        self.assertEqual(validate_schedule(self.instance, seed)['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        by = {row['stage_id']: row for row in seed['scenes']['AB_offset_0ms']}
        self.assertEqual(by['AB_offset_0ms::B_r1::B.main']['start_ms'], '40')
        self.assertEqual(by['AB_offset_0ms::A_r1::A.main']['unit'], 'NPU0')
        statuses = [row['status'] for row in self.result['constructor_prechecks']['C_templates']]
        self.assertEqual(statuses, ['COMPLETE_LEGAL_CANDIDATE', 'CONSTRUCTION_UNRESOLVED', 'CONSTRUCTION_UNRESOLVED'])

    def test_HEFT_constructor_respects_same_domain(self):
        heft = self.result['constructor_prechecks']['HEFT_constructor']
        self.assertEqual(heft['status'], 'COMPLETE_LEGAL_CANDIDATE')
        from schedules import validate_schedule
        self.assertEqual(validate_schedule(self.instance, heft['candidate'])['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')

    def test_production_option_catalog_equals_independent_domain(self):
        from inputs import expand_options
        # expand_options uses only the schema equality from config.
        actual = expand_options(self.instance, {'schema_version': self.instance['schema_version']})
        keys = lambda r: (r['scenario_id'], r['stage_instance_id'], r['unit_id'], r['opp_id'], r['start_ms'], r['end_ms'])
        actual_keys = {keys(row) for row in actual}
        expected = set()
        for scene in self.instance['scenarios']:
            for options in core.row_options(self.instance, scene):
                for row in options:
                    expected.add((scene['id'], row['id'], row['unit_id'], row['opp_id'], str(row['start']), str(row['end'])))
        self.assertEqual(actual_keys, expected)
        self.assertEqual(len(actual), 78)

    def test_domain_rejects_mode_coefficient_or_physical_drift(self):
        bad = deepcopy(self.instance)
        bad['stage_modes']['A.main'][0]['duration_ms'] = '1'
        with self.assertRaises(ValueError): core.assert_preserved(self.original, bad)
        bad = deepcopy(self.instance)
        bad['platform']['node_order'][0] = 'OTHER'
        with self.assertRaises(ValueError): core.assert_preserved(self.original, bad)

    def test_common_schedule_rejects_domain_escape(self):
        from schedules import validate_schedule
        bad = deepcopy(self.result['C_seed'])
        bad['scenes']['AB_offset_0ms'][0]['start_ms'] = '5'
        self.assertNotEqual(validate_schedule(self.instance, bad)['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        bad = deepcopy(self.result['C_seed'])
        bad['scenes']['AB_offset_0ms'][0]['unit'] = 'CPU2'
        self.assertNotEqual(validate_schedule(self.instance, bad)['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')

    def test_independent_static_checker_rejects_real_resource_conflict(self):
        scene = self.instance['scenarios'][0]
        rows = deepcopy(self.result['legal_by_scene'][scene['id']][0])
        left = next(row for row in rows if row['shared_stage_id'] == 'A.main')
        right = next(row for row in rows if row['shared_stage_id'] == 'B.main')
        right.update(unit_id=left['unit_id'], domain_id=left['domain_id'], start=left['start'], end=left['end'])
        self.assertFalse(core.is_legal(rows, scene))

    def test_existing_SA_plan_roundtrip_is_same_domain(self):
        from heuristic_common import plan_from_candidate, decode_plan
        seed = self.result['C_seed']
        plan = plan_from_candidate(self.instance, seed)
        rebuilt = decode_plan(self.instance, plan)
        canonical = lambda c: {sid: sorted(rows, key=lambda row: row['stage_id']) for sid, rows in c['scenes'].items()}
        self.assertEqual(canonical(rebuilt), canonical(seed))

    def test_no_solver_or_heat_dependency_imported(self):
        self.assertNotIn('thermal', sys.modules)
        self.assertNotIn('matlab_bridge', sys.modules)
        self.assertNotIn('milp', sys.modules)


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('Native process forbidden in pure check')):
        unittest.main(verbosity=2)
