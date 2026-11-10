"""Regression fixtures for exact preconstruction option support."""
import unittest

from option_propagation import propagate_local_options
from thermal import Budget


def stage(name, shared=None):
    return {'id': name, 'shared_stage_id': shared or name}


def option(scene, name, unit, start, end, opp='L'):
    return dict(scenario_id=scene, stage_instance_id=name, unit_id=unit,
                opp_id=opp, start_ms=start, end_ms=end)


class PropagationTests(unittest.TestCase):
    def test_shared_device_loss_propagates_to_successor_on_next_pass(self):
        instance = {'scenarios': [
            dict(id='AB', stage_instances=[stage('pre'), stage('main')],
                 dependencies=[('pre', 'main')]),
            dict(id='AC', stage_instances=[stage('pre')], dependencies=[]),
        ]}
        impossible_unit = option('AB', 'pre', 'CPU1', '0', '5')
        pre_ab = option('AB', 'pre', 'CPU2', '0', '21/2')
        pre_ac = option('AC', 'pre', 'CPU2', '5', '20', opp='H')
        impossible_start = option('AB', 'main', 'NPU0', '10', '12')
        main = option('AB', 'main', 'NPU0', '15', '25')
        options = [impossible_unit, main, pre_ac, impossible_start, pre_ab]
        kept, stats = propagate_local_options(instance, options, budget=Budget())
        self.assertEqual(kept, [main, pre_ac, pre_ab])
        self.assertEqual(stats['passes'], 3)
        self.assertEqual(stats['removed_by_rule'],
                         {'precedence_forward': 1, 'precedence_backward': 0, 'shared_unit': 1})

    def test_backward_bound_is_inclusive_and_exact(self):
        instance = {'scenarios': [dict(id='AB', stage_instances=[stage('pre'), stage('main')],
                                       dependencies=[('pre', 'main')])]}
        late = option('AB', 'pre', 'CPU1', '0', '31/3')
        on_time = option('AB', 'pre', 'CPU2', '0', '10')
        main = option('AB', 'main', 'NPU0', '10', '15')
        kept, stats = propagate_local_options(instance, [late, on_time, main], budget=Budget())
        self.assertEqual(kept, [on_time, main])
        self.assertEqual(stats['removed_by_rule']['precedence_backward'], 1)

    def test_no_shared_support_preserves_empty_required_stage_domains(self):
        instance = {'scenarios': [dict(id='AB', stage_instances=[stage('copy1', 'A'), stage('copy2', 'A')],
                                       dependencies=[])]}
        options = [option('AB', 'copy1', 'CPU1', '0', '5'),
                   option('AB', 'copy2', 'CPU2', '5', '10')]
        kept, stats = propagate_local_options(instance, options, budget=Budget())
        self.assertEqual(kept, [])
        self.assertEqual(stats['empty_stage_domains'], [('AB', 'copy1'), ('AB', 'copy2')])


if __name__ == '__main__':
    unittest.main()
