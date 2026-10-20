"""Finite start-domain interface tests; no solver or full thermal evaluation."""

from copy import deepcopy
from fractions import Fraction as F
import unittest

from inputs import expand_options, load_config
from initial_schedule import construct_initial_candidates
from run_milp_precheck import fixtures
from scene_adapter import make_scene_instance
from schedules import validate_schedule
from start_domain import explicit_start_sets


class StartDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixtures = fixtures(cls.config)

    def setUp(self):
        self.instance, self.old_starts = deepcopy(self.fixtures['one_stage_energy'])
        self.sid = self.instance['scenarios'][0]['id']
        self.stage = self.instance['scenarios'][0]['stage_instances'][0]['id']

    def declare(self, values=None, instance=None):
        instance = self.instance if instance is None else instance
        instance['start_domain'] = {
            'version': 1, 'kind': 'explicit_grid_subset', 'by_scene_stage_ms': {
                scene['id']: {stage['id']: list(['0', '45'] if values is None else values)
                              for stage in scene['stage_instances']}
                for scene in instance['scenarios']}}
        return instance['start_domain']

    def candidate(self, start='0'):
        mode = self.instance['stage_modes']['A.pre'][0]
        return {'scenes': {self.sid: [{'stage_id': self.stage, 'unit': mode['unit_id'],
                                     'opp': mode['opp_id'], 'start_ms': start}]}}

    def test_absent_preserves_option_identity(self):
        self.assertIsNone(explicit_start_sets(self.instance))
        original = expand_options(self.instance, self.config)
        self.declare([str(i * 5) for i in range(81)])
        self.assertEqual(original, expand_options(self.instance, self.config))

    def test_exact_sorted_rationals(self):
        self.declare(['45', F(0)])
        self.assertEqual(explicit_start_sets(self.instance),
                         {self.sid: {self.stage: [F(0), F(45)]}})

    def test_expansion_uses_only_domain_and_keeps_all_modes(self):
        self.declare()
        options = expand_options(self.instance, self.config)
        self.assertEqual({o['start_ms'] for o in options}, {'0', '45'})
        self.assertEqual({o['mode_id'] for o in options},
                         {m['mode_id'] for m in self.instance['stage_modes']['A.pre']})
        self.assertEqual(len(options), 2 * len(self.instance['stage_modes']['A.pre']))

    def test_release_filter(self):
        self.declare()
        self.instance['scenarios'][0]['requests'][0]['release_ms'] = '50'
        self.assertEqual(expand_options(self.instance, self.config), [])

    def test_empty_domain_never_expands(self):
        self.declare([])
        self.assertEqual(explicit_start_sets(self.instance)[self.sid][self.stage], [])
        self.assertEqual(expand_options(self.instance, self.config), [])
        self.assertEqual(construct_initial_candidates(self.instance)['candidates'], [])
        checked = validate_schedule(self.instance, self.candidate())
        self.assertEqual(checked['reason'], 'START_OUTSIDE_DECLARED_DOMAIN')

    def test_window_endpoint_has_no_positive_duration_option(self):
        self.declare(['400'])
        self.assertEqual(expand_options(self.instance, self.config), [])

    def test_schedule_rejects_grid_point_outside_domain(self):
        self.assertEqual(validate_schedule(self.instance, self.candidate('5'))['state'],
                         'SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.declare()
        self.assertEqual(validate_schedule(self.instance, self.candidate('5'))['reason'],
                         'START_OUTSIDE_DECLARED_DOMAIN')
        self.assertEqual(validate_schedule(self.instance, self.candidate('45'))['state'],
                         'SCHEDULE_VALID_THERMAL_UNCHECKED')

    def test_initial_constructor_uses_domain_without_legacy_argument(self):
        self.declare(['45'])
        seeds = construct_initial_candidates(self.instance)['candidates']
        self.assertTrue(seeds)
        for seed in seeds:
            self.assertEqual(seed['candidate']['scenes'][self.sid][0]['start_ms'], '45')

    def test_legacy_start_restriction_still_fixture_only(self):
        self.instance['id'] = 'q1__main_only'
        with self.assertRaisesRegex(ValueError, 'fixture-only'):
            construct_initial_candidates(self.instance, starts=self.old_starts)
        self.declare(['45'])
        self.assertTrue(construct_initial_candidates(self.instance)['candidates'])

    def test_legacy_starts_cannot_expand_declared_domain(self):
        self.declare(['45'])
        with self.assertRaisesRegex(ValueError, 'subset'):
            construct_initial_candidates(self.instance, starts=self.old_starts)
        allowed = {self.sid: {self.stage: ['45']}}
        self.assertTrue(construct_initial_candidates(self.instance, starts=allowed)['candidates'])

    def test_scene_projection_cuts_only_domain_scene_map(self):
        instance, _ = deepcopy(self.fixtures['shared_two_scenes'])
        self.declare(instance=instance)
        sid = instance['scenarios'][0]['id']
        projected = make_scene_instance(instance, sid)
        self.assertEqual(set(projected['start_domain']['by_scene_stage_ms']), {sid})
        self.assertEqual(len(instance['start_domain']['by_scene_stage_ms']), 2)
        self.assertEqual(projected['platform'], instance['platform'])
        self.assertEqual(set(explicit_start_sets(projected)), {sid})

    def test_projection_does_not_hide_source_domain_error(self):
        instance, _ = deepcopy(self.fixtures['shared_two_scenes'])
        declaration = self.declare(instance=instance)
        del declaration['by_scene_stage_ms'][instance['scenarios'][1]['id']]
        with self.assertRaises(ValueError):
            make_scene_instance(instance, instance['scenarios'][0]['id'])

    def test_reject_malformed_scalars_and_bounds(self):
        for values in ([0.0], [True], ['1'], ['-5'], ['405'], ['0', '0/2'], [None]):
            with self.subTest(values=values):
                self.declare(values)
                with self.assertRaises((TypeError, ValueError)):
                    explicit_start_sets(self.instance)

    def test_reject_malformed_schema_and_identity(self):
        for variant in ('missing_field', 'extra_field', 'bad_kind', 'bool_version',
                        'unknown_scene', 'missing_stage', 'unknown_stage', 'not_list'):
            with self.subTest(variant=variant):
                declaration = self.declare()
                if variant == 'missing_field':
                    del declaration['kind']
                elif variant == 'extra_field':
                    declaration['fallback'] = 'full_grid'
                elif variant == 'bad_kind':
                    declaration['kind'] = 'continuous'
                elif variant == 'bool_version':
                    declaration['version'] = True
                elif variant == 'unknown_scene':
                    declaration['by_scene_stage_ms']['other'] = {}
                elif variant == 'missing_stage':
                    declaration['by_scene_stage_ms'][self.sid] = {}
                elif variant == 'unknown_stage':
                    declaration['by_scene_stage_ms'][self.sid]['other'] = ['0']
                elif variant == 'not_list':
                    declaration['by_scene_stage_ms'][self.sid][self.stage] = '0'
                with self.assertRaises((TypeError, ValueError)):
                    explicit_start_sets(self.instance)

    def test_budget_is_honoured_during_domain_read(self):
        self.declare()
        class Expired:
            def check(self):
                raise RuntimeError('expired')
        with self.assertRaisesRegex(RuntimeError, 'expired'):
            explicit_start_sets(self.instance, Expired())


if __name__ == '__main__':
    unittest.main(verbosity=2)
