"""Execution-scope negative tests. Never execute a thermal precheck."""
from copy import deepcopy
from pathlib import Path
import json
import unittest

from .semantic_precheck import validate_plan


class PlanTests(unittest.TestCase):
    def plan(self):
        return {'schema': 'formal-input-semantic-precheck-v1', 'beta': '13/10',
                'maximum_temperature_C': '80', 'total_real_thermal_seconds': 120,
                'batch_wall_seconds': 300, 'optimization_calls': 0, 'MATLAB_starts': 0,
                'formal_result': False, 'no_formal_initialization': True,
                'real_thermal_slots': [
                    {'id': 'new_C01_S1_2', 'seconds': 60, 'expected': 'SAFE'},
                    {'id': 'old_P2_negative', 'seconds': 60, 'expected': 'THERMAL_VIOLATION'}]}

    def test_declared_small_precheck_scope_is_accepted(self):
        validate_plan(self.plan())

    def test_budget_and_optimization_scope_drift_is_rejected(self):
        for key, value in [('total_real_thermal_seconds', 121), ('batch_wall_seconds', 301),
                           ('optimization_calls', 1), ('MATLAB_starts', 1),
                           ('maximum_temperature_C', '79'), ('beta', '2')]:
            with self.subTest(field=key):
                p = self.plan(); p[key] = value
                with self.assertRaises(ValueError): validate_plan(p)

    def test_extra_reordered_or_extended_slots_are_rejected(self):
        for change in ('extra', 'reorder', 'longer', 'replacement'):
            with self.subTest(change=change):
                p = self.plan()
                if change == 'extra': p['real_thermal_slots'].append(deepcopy(p['real_thermal_slots'][0]))
                if change == 'reorder': p['real_thermal_slots'].reverse()
                if change == 'longer': p['real_thermal_slots'][0]['seconds'] = 61
                if change == 'replacement': p['real_thermal_slots'][0]['id'] = 'other_input'
                with self.assertRaises(ValueError): validate_plan(p)
