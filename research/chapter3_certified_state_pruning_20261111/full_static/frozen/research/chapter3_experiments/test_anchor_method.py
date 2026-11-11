"""K150 default-off dispatch and freshly rebuilt tiny physical warm echo.

The fake worker only returns the current model's freshly completed x0; it
does not optimize. All original continuous/numeric admission gates run.
"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch

import linked_method
import test_linked_method as inherited


RECORDS = {'scope': 'tiny physical warm reconstruction and mock method dispatch',
           'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0}


class AnchorMethodTests(unittest.TestCase):
    def test_only_second_pass_receives_flag_under_same_root_budget(self):
        harness = inherited.LinkedHarness()
        built = []
        original = harness.builder

        def builder(instance, config, **kwargs):
            built.append((kwargs['neighborhood_condition']['protocol'],
                          kwargs.pop('preeliminate_closed_anchors', None)))
            return original(instance, config, **kwargs)

        harness.builder = builder
        folder = Path(__file__).resolve().parents[2]/'.runtime'/('anchor_dispatch_'+uuid4().hex)
        result = harness.run(folder, preeliminate_closed_anchors=True)
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertEqual(len(built), 4)
        self.assertEqual([value for _, value in built], [None, None, True, True])
        self.assertEqual(len(set(harness.budgets)), 1)
        self.assertEqual(result['linked_record_contract']['closed_anchor_preelimination']['phase_indices'], [2])
        RECORDS['dispatch'] = {'build_flags': built, 'same_budget': True,
                               'status': result['state']}

    def test_new_events_warm_numeric_complement_and_complete_continuous_safety(self):
        probe = inherited.LinkedMethodTests('test_true_tiny_complete_thermal_model_echo_and_phase0_anchor')
        execute = linked_method.execute_linked_fixed_unit_opp_start
        observed = []

        def enabled(*args, **kwargs):
            original = kwargs['model_builder']

            def builder(instance, config, **options):
                model = original(instance, config, **options)
                if options.get('preeliminate_closed_anchors'):
                    condition = model.neighborhood_condition
                    sid = model.instance['scenarios'][0]['id']
                    choices = condition['warm_candidate']['scenes'][sid]
                    events = set(model.scenes[sid]['events'])
                    from fractions import Fraction as F
                    self.assertIn(F(0), events)
                    self.assertIn(F(model.instance['window_ms'])/1000, events)
                    for row in choices:
                        mode = next(o for o in model.options if
                            o['stage_instance_id'] == row['stage_id'] and o['unit_id'] == row['unit']
                            and o['opp_id'] == row['opp'] and F(o['start_ms']) == F(row['start_ms']))
                        self.assertIn(F(mode['start_ms'])/1000, events)
                        self.assertIn(F(mode['end_ms'])/1000, events)
                    observed.append(model.summary())
                return model

            kwargs['model_builder'] = builder
            kwargs['preeliminate_closed_anchors'] = True
            return execute(*args, **kwargs)

        probe.setUp()
        try:
            with patch.object(linked_method, 'execute_linked_fixed_unit_opp_start', side_effect=enabled):
                probe.test_true_tiny_complete_thermal_model_echo_and_phase0_anchor()
        finally:
            probe.tearDown()
        self.assertEqual(len(observed), 2)
        self.assertGreater(sum(m['preprocessing']['closed_anchor_preelimination']['removed'] for m in observed), 0)
        details = deepcopy(inherited.RECORDS['physical_tiny'])
        self.assertEqual(len(details['calls']), 4)
        self.assertTrue(all(call['x0_admitted'] for call in details['calls']))
        self.assertEqual(len(details['result']['augmented_transport']['requests']), 2)
        RECORDS['physical_tiny'] = details
        RECORDS['filtered_second_pass_summaries'] = observed

    def test_bad_flag_rejected_before_input(self):
        def loader(budget):
            self.fail('Invalid flag must fail before loading input')
        for value in (None, 0, 1, 'yes'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                linked_method.execute_linked_fixed_unit_opp_start(loader, Path('unused'),
                    shared_deployment={}, opened_by_scene={}, linked_opened_by_scene={},
                    preeliminate_closed_anchors=value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
