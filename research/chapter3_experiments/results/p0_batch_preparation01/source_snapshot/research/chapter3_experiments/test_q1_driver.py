"""Q1 input, structural equivalence and runner contract; no research heat/solve."""
from copy import deepcopy
from fractions import Fraction as F
import itertools
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from inputs import load_config, build_instance, expand_options
from milp import build_model
from q1_case import load_q1, independent_lower_bound, CONFIG_SHA
from q1_reference import assignment_domain
from run_milp_precheck import fixtures, independent_check
from schedules import validate_schedule


class Q1DriverTests(unittest.TestCase):
    def test_main_derivation_preserves_physical_and_service_inputs(self):
        config, q1 = load_q1()
        base = build_instance(config, 'base__R1')
        for key in ('platform', 'window_ms', 'start_grid_ms', 'execution_rules', 'settings'):
            self.assertEqual(q1[key], base[key])
        self.assertEqual(set(q1['stage_modes']), {'A.main', 'B.main', 'C.main'})
        for key, modes in q1['stage_modes'].items():
            self.assertEqual(modes, base['stage_modes'][key])
        self.assertEqual(q1['quality_reference']['source_config_sha256'], CONFIG_SHA)
        for scene, old in zip(q1['scenarios'], base['scenarios']):
            for key in ('id', 'entry', 'weight', 'maximum_temperature_degC'):
                self.assertEqual(scene[key], old[key])
            self.assertEqual(len(scene['stage_instances']), 2)
            self.assertEqual(scene['dependencies'], [])
            for request, original in zip(scene['requests'], old['requests']):
                self.assertEqual({k: v for k, v in request.items() if k != 'stage_instance_ids'},
                                 {k: v for k, v in original.items() if k != 'stage_instance_ids'})
                self.assertEqual(len(request['stage_instance_ids']), 1)

    def test_exact_domain_and_counts_crosscheck(self):
        config, q1 = load_q1()
        dims, identities, counts = assignment_domain(q1)
        self.assertEqual(counts['individual_option_counts'], [16, 12, 16, 12])
        self.assertEqual(counts['joint_assignments_total'], 11520)
        opts = expand_options(q1, config)
        self.assertEqual(len(opts), 84)
        self.assertEqual({F(o['start_ms']) for o in opts}, {F(0), F(45)})
        kept = [o for o in opts if F(o['end_ms']) <= F(o['request_deadline_ms'])]
        self.assertEqual(len(kept), 56)
        # Independent direct product over input mode counts, no temperature.
        raw = {}
        for key, modes in q1['stage_modes'].items():
            raw[key] = {unit: 2*sum(m['unit_id'] == unit for m in modes)
                        for unit in {m['unit_id'] for m in modes}}
        self.assertEqual(sum(n*n for n in raw['A.main'].values()) *
                         sum(raw['B.main'].values())*sum(raw['C.main'].values()), 46656)
        seen = 0
        for rows in itertools.product(*dims):
            shared = {}
            for row, (_, key) in zip(rows, identities):
                if key in shared and shared[key] != row['unit']:
                    break
                shared[key] = row['unit']
            else:
                seen += 1
        self.assertEqual(seen, 11520)

    def test_lower_bound_algebra_derived_without_history(self):
        _, q1 = load_q1()
        bound = independent_lower_bound(q1)
        p = q1['platform']
        self.assertEqual(F(bound['baseline_lower_bound_J']), F('0.598'))
        activity = sum(F(sc['weight'])*sum(min(F(m['activity_energy_J'])
            for m in q1['stage_modes'][s['shared_stage_id']])
            for s in sc['stage_instances']) for sc in q1['scenarios'])
        self.assertEqual(F(bound['lower_bound_J']), F('0.598')+activity)
        changed = deepcopy(q1)
        changed['platform']['domains']['CPU']['local_temperature_slope_W_per_K']['L'] = '-1'
        with self.assertRaises(ValueError): independent_lower_bound(changed)
        changed = deepcopy(q1)
        changed['scenarios'][0]['weight'] = '2'
        with self.assertRaises(ValueError): independent_lower_bound(changed)

    def test_explicit_domain_model_equals_prior_fixture_restriction(self):
        config = load_config()
        instance, starts = fixtures(config)['one_stage_energy']
        original = build_model(instance, config, starts=starts, include_physics=False)
        current = deepcopy(instance)
        current['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                                  'by_scene_stage_ms': starts}
        adapted = build_model(current, config, include_physics=False)
        self.assertEqual(original.names, adapted.names)
        self.assertEqual(original.rows, adapted.rows)
        for key in ('A', 'Aeq'):
            self.assertEqual((original.as_solver_dict()[key] != adapted.as_solver_dict()[key]).nnz, 0)
        for key in ('b', 'beq', 'c', 'lb', 'ub', 'intcon'):
            self.assertTrue(np.array_equal(original.as_solver_dict()[key], adapted.as_solver_dict()[key]), key)

    def test_q1_invalid_grid_inside_but_domain_outside(self):
        _, q1 = load_q1()
        candidate = {'scenes': {sc['id']: [dict(stage_id=s['id'], unit='CPU1', opp='H', start_ms='5')
            for s in sc['stage_instances']] for sc in q1['scenarios']}}
        self.assertEqual(validate_schedule(q1, candidate)['reason'], 'START_OUTSIDE_DECLARED_DOMAIN')

    def test_loader_checkpoints_and_no_historical_read(self):
        class Budget:
            calls = 0
            def check(self): self.calls += 1
        budget = Budget()
        _, instance = load_q1(budget)
        self.assertGreater(budget.calls, 2)
        self.assertFalse(instance['quality_reference']['historical_answers_or_candidates_used'])
        source = Path(__file__).with_name('run_q1_quality.py').read_text(encoding='utf-8')
        self.assertIn('execute_warm(loader, out, seconds=SECONDS)', source)
        self.assertIn("with claim.open('x'", source)
        self.assertIn("with stage_claim.open('x'", source)
        self.assertEqual(__import__('q1_case').SECONDS, 300)


if __name__ == '__main__':
    unittest.main(verbosity=2)
