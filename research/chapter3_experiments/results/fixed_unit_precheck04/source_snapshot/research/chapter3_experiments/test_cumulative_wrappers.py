"""Builder-flag routing only; deliberately stop before building any MILP.

Input expansion and receipt identities are real. Builders and outer condition
executors below are protocol doubles, never physical/optimization evidence.
No mock SAFE, thermal evaluation, native session or solver call is produced.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from inputs import build_instance, load_config
from partial_method import execute_shared_deployment
from run_milp_precheck import select_fixture
from scene_adapter import canonical_hash
from scene_method import DEFAULT_BUILDER_OPTIONS, execute_fixed_deployment
from shared_search import execute_shared_search


REPO = Path(__file__).resolve().parents[2]
EXPECTED_DEFAULTS = {
    'fix_late_options': True,
    'aggregate_opp_locks': True,
    'relax_auxiliary_integrality': True,
    'strengthen_energy_lower_bounds': True,
    'prefilter_deadlines': True,
}
STOP = 'MOCK_STOP_BEFORE_MODEL_CONSTRUCTION'


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def mock_bound(instance, mapping, budget):
    """Identity-bearing protocol double; never used to report any SAFE/gap."""
    return {'scope': ('original_full_domain' if mapping is None
                      else 'fixed_shared_deployment'),
            'input_sha256': canonical_hash(instance),
            'shared_deployment': deepcopy(mapping),
            'lower_bound_J': '0', 'solver_reported': False,
            'test_scope': 'mock routing only; not a physical bound certificate'}


class CumulativeWrapperRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        base = build_instance(config, 'base__R1')
        first, second = [scene['id'] for scene in base['scenarios']]
        instance, starts = select_fixture(base, 'cumulative_wrapper_routing',
            {first: ['A.pre'], second: ['A.pre']}, {'A.pre': [0]})
        instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                                   'by_scene_stage_ms': starts}
        cls.config, cls.instance = config, instance

    def setUp(self):
        home = REPO / '.runtime' / 'cumulative_wrappers_unit'
        home.mkdir(parents=True, exist_ok=True)
        self.home = home.resolve()
        self.temp = tempfile.TemporaryDirectory(prefix='unit_', dir=home)
        self.path = Path(self.temp.name).resolve()
        self.path.relative_to(self.home)

    def tearDown(self):
        self.path.relative_to(self.home)
        self.temp.cleanup()

    def loader(self, budget):
        return deepcopy(self.config), deepcopy(self.instance)

    def run_wrapper(self, kind, folder, *, options_marker=None, supplied=False):
        """Capture kwargs after real identity checks, then deliberately stop."""
        calls = []

        def stop_builder(instance, config, **kwargs):
            self.assertEqual(instance, self.instance)
            self.assertEqual(config, self.config)
            calls.append(dict(kwargs))
            raise RuntimeError(STOP)

        session = Mock(side_effect=AssertionError('native session must not start'))
        physical = Mock(side_effect=AssertionError('thermal evaluation forbidden'))
        common = {'seconds': 60, 'clock': Clock(), 'model_builder': stop_builder,
                  'session_factory': session, 'scene_evaluator': physical}
        if supplied:
            common['builder_options'] = options_marker
        if kind == 'partial':
            initial = Mock(side_effect=AssertionError('initialization forbidden'))
            result = execute_shared_deployment(self.loader, folder,
                shared_deployment={'A.pre': 'CPU1'}, initial_preparer=initial,
                bounds_provider=lambda instance, fixed, budget: {
                    'L0': mock_bound(instance, None, budget),
                    'L_a': mock_bound(instance, fixed, budget)}, **common)
            initial.assert_not_called()
        else:
            result = execute_fixed_deployment(self.loader, folder,
                fixed_deployment={'A.pre': 'CPU1'}, **common)
        session.assert_not_called()
        physical.assert_not_called()
        saved = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['state'], 'UNRESOLVED')
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertFalse(result['integer_solver_entered'])
        self.assertEqual(result['solver_request_attempts'], 0)
        return result, saved, calls

    def assert_routed(self, kind, value=None, *, supplied=False):
        options = ({'cumulative_precedence': value} if supplied else None)
        before = deepcopy(options)
        result, saved, calls = self.run_wrapper(kind, self.path / kind,
                                               options_marker=options, supplied=supplied)
        expected = dict(EXPECTED_DEFAULTS)
        if supplied:
            expected['cumulative_precedence'] = value
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertEqual(result['stop_stage'], 'model_construction')
        self.assertEqual(result['error'], 'RuntimeError: ' + STOP)
        self.assertEqual(result['builder_options'], expected)
        self.assertEqual(saved['builder_options'], expected)
        ordinary = {'starts', 'budget', 'progress', 'fixed_scene_id',
                    'fixed_shared_deployment' if kind == 'partial' else 'fixed_deployment'}
        self.assertEqual({key: value for key, value in calls[0].items()
                          if key not in ordinary}, expected)
        self.assertEqual(set(calls[0]), ordinary | set(expected))
        self.assertEqual(result['identity']['full_input_sha256'], canonical_hash(self.instance))
        self.assertEqual(options, before)
        self.assertEqual(DEFAULT_BUILDER_OPTIONS, EXPECTED_DEFAULTS)

    def test_defaults_still_have_exactly_five_original_keys(self):
        self.assertEqual(DEFAULT_BUILDER_OPTIONS, EXPECTED_DEFAULTS)
        self.assertNotIn('cumulative_precedence', DEFAULT_BUILDER_OPTIONS)

    def test_partial_default_does_not_inject_false_or_new_result_key(self):
        self.assert_routed('partial')

    def test_partial_explicit_false_reaches_builder_and_archive(self):
        self.assert_routed('partial', False, supplied=True)

    def test_partial_explicit_true_reaches_builder_and_archive(self):
        self.assert_routed('partial', True, supplied=True)

    def test_scene_default_does_not_inject_false_or_new_result_key(self):
        self.assert_routed('scene')

    def test_scene_explicit_false_reaches_builder_and_archive(self):
        self.assert_routed('scene', False, supplied=True)

    def test_scene_explicit_true_reaches_builder_and_archive(self):
        self.assert_routed('scene', True, supplied=True)

    def test_empty_options_preserve_legacy_flag_archive(self):
        for kind in ('partial', 'scene'):
            with self.subTest(kind=kind):
                result, saved, calls = self.run_wrapper(kind, self.path / kind,
                    options_marker={}, supplied=True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['builder_options'], EXPECTED_DEFAULTS)
                self.assertEqual(saved['builder_options'], EXPECTED_DEFAULTS)
                self.assertNotIn('cumulative_precedence', calls[0])

    def test_unknown_flags_rejected_before_builder(self):
        for kind in ('partial', 'scene'):
            with self.subTest(kind=kind):
                result, saved, calls = self.run_wrapper(kind, self.path / kind,
                    options_marker={'cumulative_precedence_typo': True}, supplied=True)
                self.assertEqual(calls, [])
                self.assertEqual(result['reason'], 'INVALID_INPUT_OR_INTERFACE')
                self.assertEqual(result['stop_stage'], 'identity_and_scope_validation')
                self.assertNotIn('builder_options', saved)

    def test_nonbool_new_and_existing_flags_rejected_before_builder(self):
        for kind in ('partial', 'scene'):
            for flag in ('cumulative_precedence', 'prefilter_deadlines'):
                for index, invalid in enumerate((0, 1, None, 'true', [], {})):
                    with self.subTest(kind=kind, flag=flag, invalid=repr(invalid)):
                        folder = self.path / ('%s_%s_%d' % (kind, flag, index))
                        result, saved, calls = self.run_wrapper(kind, folder,
                            options_marker={flag: invalid}, supplied=True)
                        self.assertEqual(calls, [])
                        self.assertEqual(result['reason'], 'INVALID_INPUT_OR_INTERFACE')
                        self.assertNotIn('builder_options', saved)

    def test_outer_condition_options_preserved_across_all_conditions(self):
        for label, opts in (('default', {}), ('false', {'builder_options': {
                'cumulative_precedence': False}}), ('true', {'builder_options': {
                'cumulative_precedence': True}})):
            with self.subTest(label=label):
                seen, budgets = [], []
                original = deepcopy(opts)

                def condition(loader, folder, **kwargs):
                    budget = kwargs['budget']
                    config, instance = loader(budget)
                    self.assertEqual(config, self.config)
                    self.assertEqual(instance, self.instance)
                    self.assertEqual(kwargs['bounds_receipt']['L_a']['shared_deployment'],
                                     kwargs['shared_deployment'])
                    budgets.append(id(budget))
                    seen.append(deepcopy(kwargs.get('builder_options')))
                    self.assertEqual('builder_options' in kwargs, bool(opts))
                    folder = Path(folder)
                    folder.mkdir()
                    result = {'state': 'UNRESOLVED', 'reason': 'MOCK_ROUTING_ONLY',
                              'shared_deployment': deepcopy(kwargs['shared_deployment']),
                              'scenes': {}, 'violations': [], 'worker_reusable': True,
                              'builder_options': deepcopy(kwargs.get('builder_options'))}
                    (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                    return result

                session = Mock(side_effect=AssertionError('native session forbidden'))
                result = execute_shared_search(self.loader, self.path / label, seconds=60,
                    clock=Clock(), condition_executor=condition, session_factory=session,
                    bound_provider=mock_bound, condition_options=opts)
                self.assertEqual(result['reason'], 'FIRST_PASS_COMPLETED_REMAINING_DOMAIN_UNRESOLVED')
                self.assertEqual(result['visited_condition_count'], 2)
                self.assertEqual(seen, [opts.get('builder_options')] * 2)
                self.assertEqual(len(set(budgets)), 1)
                self.assertEqual(opts, original)
                self.assertEqual(result['state'], 'UNRESOLVED')
                self.assertIsNone(result['safe_upper_bound_J'])
                self.assertFalse(result['independently_proven_optimal'])
                session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
