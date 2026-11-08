"""K193 pure proof/lifecycle requirements; no evaluator or optimizer calls."""
from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract as c


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = json.loads(c.INPUT.read_bytes())
        cls.config = json.loads(c.CONFIG.read_bytes())
        cls.manifest, cls.counts = c.make_manifest(cls.instance, cls.config)

    def test_full_coverage_unique_and_reproducible_order(self):
        self.assertEqual(len(self.manifest), 1550)
        self.assertEqual(len({row['id'] for row in self.manifest}), 1550)
        self.assertEqual([r['ordinal'] for r in self.manifest], list(range(1, 1551)))
        self.assertEqual([(r['scene_id'], r['shared_A_device']) for r in self.manifest[:4]], c.GROUPS)
        self.assertEqual(self.counts['global_legal_complete_arrangements'], 274500)

    def test_all_rows_are_full_six_Stage_scene_schedules(self):
        for row in self.manifest:
            self.assertEqual(set(row['candidate']['scenes']), {row['scene_id']})
            self.assertEqual(len(row['candidate']['scenes'][row['scene_id']]), 6)

    def test_missing_or_unresolved_energy_cannot_produce_upper(self):
        records = {row['id']: {'state': 'TIMEOUT', 'energy_J': ['999','1000']} for row in self.manifest}
        result = c.envelope(self.manifest, records)
        self.assertEqual(result['lower'], 0)
        self.assertIsNone(result['upper'])

    def test_safe_pair_must_share_device_before_aggregation(self):
        rows = self.manifest[:4]
        records = {rows[0]['id']: {'state':'SAFE','energy_J':['2','2']},
                   rows[3]['id']: {'state':'SAFE','energy_J':['1','1']}}
        self.assertIsNone(c.envelope(self.manifest, records)['upper'])
        records[rows[2]['id']] = {'state':'SAFE','energy_J':['4','4']}
        result = c.envelope(self.manifest, records)
        self.assertEqual(result['upper'], 3)  # original weights applied exactly once
        self.assertEqual(result['lower'], 0)  # unvisited options retained

    def test_all_safe_intervals_give_epsilon_not_unique_optimum(self):
        records = {r['id']: {'state':'SAFE','energy_J':['1','10000001/10000000']} for r in self.manifest}
        result = c.envelope(self.manifest, records)
        self.assertEqual(result['state'], 'FINITE_DOMAIN_EPSILON_OPTIMAL')
        self.assertEqual(result['gap'], Q(1, 10000000))
        self.assertFalse(result['unique_optimum_proven'])

    def test_unsafe_excludes_only_one_schedule(self):
        records = {self.manifest[0]['id']: {'state':'VIOLATION'}}
        result = c.envelope(self.manifest, records)
        self.assertEqual(result['lower'], 0)
        self.assertEqual(result['state'], 'NO_COMPLETE_SAFE_WITNESS')

    def test_only_exhaustive_valid_violations_can_prove_no_safe(self):
        records = {r['id']: {'state':'VIOLATION'} for r in self.manifest}
        self.assertEqual(c.envelope(self.manifest, records)['state'], 'FINITE_DOMAIN_INFEASIBLE')
        records.pop(self.manifest[0]['id'])
        records.pop(self.manifest[2]['id'])
        self.assertEqual(c.envelope(self.manifest, records)['lower'], 0)

    def test_unknown_id_state_and_invalid_SAFE_interval_rejected(self):
        with self.assertRaises(ValueError): c.envelope(self.manifest, {'not_in_domain': {'state':'SAFE'}})
        with self.assertRaises(ValueError): c.envelope(self.manifest, {self.manifest[0]['id']: {'state':'INFEASIBLE_FROM_TIMEOUT'}})
        with self.assertRaises(ValueError): c.envelope(self.manifest, {self.manifest[0]['id']: {'state':'SAFE','energy_J':['2','1']}})

    def test_duplicate_manifest_is_not_coverage(self):
        bad = deepcopy(self.manifest)
        bad[-1] = deepcopy(bad[0])
        with self.assertRaises(ValueError): c.envelope(bad, {})
        with self.assertRaises(ValueError): c.envelope(self.manifest[:-1], {})

    def test_no_thermal_or_MATLAB_module_imported(self):
        self.assertNotIn('thermal', sys.modules)
        self.assertNotIn('matlab_bridge', sys.modules)


if __name__ == '__main__':
    unittest.main(verbosity=2)
