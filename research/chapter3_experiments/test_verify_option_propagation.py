"""Keep legacy and current R1 inputs distinct at the diagnostic entry."""
import json
import unittest
from unittest.mock import patch

from thermal import Budget
from verify_option_propagation import archived, r1_input


class InputProfileTests(unittest.TestCase):
    def test_current_profile_is_the_complete_auto_low_problem(self):
        config, instance = r1_input(Budget(), 'auto-low')
        self.assertEqual(instance['execution_rules']['idle_policy'], 'auto_low_immediate_v1')
        self.assertEqual(config['execution_rules']['idle_policy'], 'auto_low_immediate_v1')
        self.assertEqual(instance['settings']['deadline_beta'], '1.3')
        self.assertEqual(instance['settings']['initial_temperature_degC'], '50')
        self.assertEqual(sum(len(s['stage_instances']) for s in instance['scenarios']), 12)

    def test_default_entry_retains_the_original_hold_last_reproduction(self):
        _, legacy = r1_input(Budget())
        _, current = r1_input(Budget(), 'auto-low')
        self.assertTrue(legacy['execution_rules']['idle_holds_last_opp'])
        self.assertFalse(current['execution_rules']['idle_holds_last_opp'])

    def test_auto_low_input_drift_is_rejected_before_building(self):
        def altered(path):
            raw = archived(path)
            if path.endswith('input_instance.json'):
                data = json.loads(raw)
                data['settings']['deadline_beta'] = '1.0'
                return json.dumps(data).encode()
            return raw

        with patch('verify_option_propagation.archived', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'input identity'):
                r1_input(Budget(), 'auto-low')


if __name__ == '__main__':
    unittest.main()
