"""Regression fixtures for exact preconstruction option support."""
import unittest
from copy import deepcopy
from fractions import Fraction
from itertools import product

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

    def test_fork_join_preserves_every_complete_supported_assignment(self):
        instance = {'scenarios': [
            dict(id='AB', stage_instances=[stage('root', 'A'), stage('left'),
                                          stage('right'), stage('join')],
                 dependencies=[('root', 'left'), ('root', 'right'),
                               ('left', 'join'), ('right', 'join')]),
            dict(id='AC', stage_instances=[stage('copy', 'A')], dependencies=[]),
        ]}
        options = [
            option('AB', 'root', 'CPU1', '0', '2'),
            option('AB', 'root', 'CPU2', '1', '3'),
            option('AB', 'left', 'GPU0', '2', '4'),
            option('AB', 'left', 'GPU0', '3', '5'),
            option('AB', 'left', 'GPU0', '5', '7'),
            option('AB', 'right', 'NPU0', '2', '3'),
            option('AB', 'right', 'NPU0', '3', '5'),
            option('AB', 'right', 'NPU0', '5', '7'),
            option('AB', 'join', 'CPU1', '5', '6'),
            option('AB', 'join', 'CPU1', '7', '8'),
            option('AC', 'copy', 'CPU2', '0', '2', opp='H'),
            option('AC', 'copy', 'CPU2', '5', '7', opp='L'),
        ]
        stage_order = [(scene['id'], item['id'], item['shared_stage_id'])
                       for scene in instance['scenarios'] for item in scene['stage_instances']]

        def complete_assignments(catalog):
            domains = [[(index, row) for index, row in enumerate(options)
                        if row in catalog and (row['scenario_id'], row['stage_instance_id']) == (sid, name)]
                       for sid, name, _ in stage_order]
            legal = set()
            for assignment in product(*domains):
                selected = {(sid, name): row for (sid, name, _), (_, row) in zip(stage_order, assignment)}
                deployment = {}
                compatible = True
                for (_, _, shared), (_, row) in zip(stage_order, assignment):
                    compatible &= deployment.setdefault(shared, row['unit_id']) == row['unit_id']
                for scene in instance['scenarios']:
                    for before, after in scene['dependencies']:
                        compatible &= (Fraction(selected[scene['id'], before]['end_ms'])
                                       <= Fraction(selected[scene['id'], after]['start_ms']))
                if compatible:
                    legal.add(tuple(index for index, _ in assignment))
            return legal

        kept, stats = propagate_local_options(instance, options, budget=Budget())
        baseline = complete_assignments(options)
        self.assertTrue(baseline)
        self.assertLess(len(kept), len(options))
        self.assertEqual(complete_assignments(kept), baseline)
        self.assertGreater(stats['removed_by_rule']['shared_unit'], 0)
        self.assertGreater(stats['removed_by_rule']['precedence_forward'], 0)

    def test_repeated_shared_copies_keep_independent_frequency_and_start(self):
        instance = {'scenarios': [dict(id='AB', stage_instances=[stage('copy1', 'A'), stage('copy2', 'A')],
                                       dependencies=[])]}
        first = option('AB', 'copy1', 'CPU2', '0', '5', opp='H')
        second = option('AB', 'copy2', 'CPU2', '10', '20', opp='L')
        unsupported = option('AB', 'copy1', 'CPU1', '0', '5', opp='H')
        kept, _ = propagate_local_options(instance, [unsupported, first, second], budget=Budget())
        self.assertEqual(kept, [first, second])

    def test_zero_weight_scene_still_requires_shared_device_support(self):
        instance = {'scenarios': [
            dict(id='AB', weight='1', stage_instances=[stage('pre')], dependencies=[]),
            dict(id='AC', weight='0', stage_instances=[stage('pre')], dependencies=[]),
        ]}
        wrong = option('AB', 'pre', 'CPU1', '0', '5')
        first = option('AB', 'pre', 'CPU2', '0', '5')
        second = option('AC', 'pre', 'CPU2', '10', '15')
        kept, _ = propagate_local_options(instance, [wrong, first, second], budget=Budget())
        self.assertEqual(kept, [first, second])

    def test_fixed_point_is_idempotent_without_mutating_original_inputs(self):
        instance = {'scenarios': [dict(id='AB', stage_instances=[stage('pre'), stage('main')],
                                       dependencies=[('pre', 'main')])]}
        options = [option('AB', 'pre', 'CPU1', '0', '5'),
                   option('AB', 'main', 'NPU0', '0', '5'),
                   option('AB', 'main', 'NPU0', '5', '10')]
        original_instance, original_options = deepcopy(instance), deepcopy(options)
        kept, _ = propagate_local_options(instance, options, budget=Budget())
        again, stats = propagate_local_options(instance, kept, budget=Budget())
        self.assertEqual(instance, original_instance)
        self.assertEqual(options, original_options)
        self.assertEqual(again, kept)
        self.assertEqual(sum(stats['removed_by_rule'].values()), 0)
        self.assertEqual(stats['passes'], 1)

    def test_cancellation_does_not_publish_a_partial_domain_or_mutate_input(self):
        class CancelledBudget:
            checks = 0

            def check(self):
                self.checks += 1
                if self.checks == 4:
                    raise RuntimeError('cancelled')

        instance = {'scenarios': [dict(id='AB', stage_instances=[stage('pre'), stage('main')],
                                       dependencies=[('pre', 'main')])]}
        options = [option('AB', 'pre', 'CPU1', '0', '5'),
                   option('AB', 'main', 'NPU0', '0', '5'),
                   option('AB', 'main', 'NPU0', '5', '10')]
        original_instance, original_options = deepcopy(instance), deepcopy(options)
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            propagate_local_options(instance, options, budget=CancelledBudget())
        self.assertEqual(instance, original_instance)
        self.assertEqual(options, original_options)


if __name__ == '__main__':
    unittest.main()
