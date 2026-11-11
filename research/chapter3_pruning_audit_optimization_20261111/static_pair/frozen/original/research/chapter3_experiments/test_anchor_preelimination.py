"""Independent K150 small-domain anchor propagation checks.

The Cartesian oracle enumerates original legal option choices and calls the
pre-existing exact task/resource checker. SAFE receipts are identity-only mocks;
structural matrices omit physical constraints. No solver, MATLAB worker,
historical result, original-scale model or physical SAFE evidence is used.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import anchor_preelimination as propagation
import linked_neighborhood as linked
import milp
from control_policy import with_auto_low_idle
from inputs import expand_options, load_config
from run_milp_precheck import candidate_key, independent_check, select_fixture
from test_auto_milp import row_accepts, structure_vector
from test_linked_neighborhood import (condition_for, fixture, oracle_candidates)
from test_neighborhood_milp import (assert_solver_bytes_equal, base_input,
                                    option_key)
from thermal import Budget, Exhausted


RECORDS = {'scope': 'independent small Cartesian and structural correctness only',
           'solver_calls': 0, 'research_calls': 0, 'original_scale_models': 0,
           'physical_evaluations': 0, 'checks': {}}


def linked_options(case, condition, budget):
    options = expand_options(case, with_auto_low_idle(load_config()), budget=budget)
    return linked.filter_linked_options(case, condition, options, budget=budget)[0]


def selected_keys(case, candidate):
    """Option keys reconstructed from original modes, never filter metadata."""
    by_scene = {s['id']: s for s in case['scenarios']}
    out = set()
    for sid, rows in candidate['scenes'].items():
        stages = {s['id']: s for s in by_scene[sid]['stage_instances']}
        for row in rows:
            modes = case['stage_modes'][stages[row['stage_id']]['shared_stage_id']]
            mode = next(m for m in modes if (m['unit_id'], m['opp_id']) ==
                        (row['unit'], row['opp']))
            start = F(row['start_ms'])
            out.add((sid, row['stage_id'], row['unit'], row['opp'], start,
                     start + F(mode['duration_ms'])))
    return out


def small_fixture(*, closed='A.pre', same_unit=False):
    """Three Stage test-only domain; exact 3/2-ms duration is intentional.

    Test parameters do not alter production inputs. The original legality
    oracle sees precisely these same test parameters and direct edges.
    """
    base = base_input(); sid = base['scenarios'][0]['id']
    starts = {'A.pre': ['0', '3/2', '2', '5', '15/2'],
              'B.pre': ['0', '3/2', '2', '7/2', '5', '15/2'],
              'B.main': ['0', '3/2', '2', '5', '15/2', '10']}
    case, by_stage = select_fixture(base, 'anchor_boundaries',
        {sid: ['A.pre', 'B.pre', 'B.main']}, starts)
    case['start_grid_ms'] = '1/2'
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                            'by_scene_stage_ms': by_stage}
    assigned = {'A.pre': 'CPU1', 'B.pre': 'CPU1' if same_unit else 'CPU2',
                'B.main': 'NPU0'}
    durations = {'A.pre': '2', 'B.pre': '3/2', 'B.main': '2'}
    for shared, modes in case['stage_modes'].items():
        case['stage_modes'][shared] = [m for m in modes
                                      if m['unit_id'] == assigned[shared]]
        for mode in case['stage_modes'][shared]:
            mode['duration_ms'] = durations[shared]
            mode['activity_energy_J'] = str(F(mode['activity_power_W']) *
                                            F(mode['duration_ms']) / 1000)
    case = with_auto_low_idle(case)
    rows = []; opened = {sid: []}
    for stage in case['scenarios'][0]['stage_instances']:
        shared = stage['shared_stage_id']
        start = '5' if shared == 'B.main' else (
            '2' if same_unit and shared == 'B.pre' else '0')
        rows.append({'stage_id': stage['id'], 'unit': assigned[shared],
                     'opp': 'M', 'start_ms': start})
        if shared != closed:
            opened[sid].append(stage['id'])
    warm = {'scenes': {sid: rows}}
    return case, {}, deepcopy(warm), warm, opened


def structural_model(case, mapping, condition, budget, **extra):
    return milp.build_model(case, with_auto_low_idle(load_config()),
        include_physics=False, fixed_shared_deployment=mapping,
        neighborhood_condition=condition, budget=budget, **extra)


class AnchorIndependentTests(unittest.TestCase):
    def prepare(self, definition=None):
        case, mapping, seed, warm, opened = definition or fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, warm, opened, budget)
        options = linked_options(case, condition, budget)
        return case, mapping, seed, warm, opened, budget, condition, options

    def filter(self, prepared, options=None, **kwargs):
        case, _, _, _, _, budget, condition, original = prepared
        return propagation.filter_closed_anchor_options(case, condition,
            original if options is None else options, budget=budget, **kwargs)

    def test_original_cartesian_legal_set_equals_after_filter_and_models(self):
        data = self.prepare(); case, mapping, seed, warm, opened, budget, condition, options = data
        before = deepcopy((case, condition, options)); kept, stats = self.filter(data)
        old = structural_model(case, mapping, condition, budget)
        new = structural_model(case, mapping, condition, budget,
                               preeliminate_closed_anchors=True)
        retained = {option_key(o) for o in kept}
        self.assertEqual({option_key(o) for o in new.options}, retained)
        legal_before, legal_after, accepted_old, accepted_new = set(), set(), set(), set()
        assignments = 0
        for candidate in oracle_candidates(case, seed, warm, opened):
            assignments += 1; key = candidate_key(candidate)
            represented = selected_keys(case, candidate) <= retained
            valid = independent_check(case, candidate)['valid']
            if valid:
                legal_before.add(key)
                if represented: legal_after.add(key)
            if row_accepts(old, structure_vector(old, candidate)):
                accepted_old.add(key)
            if represented and row_accepts(new, structure_vector(new, candidate)):
                accepted_new.add(key)
        self.assertTrue(legal_before)
        self.assertEqual(legal_before, legal_after)
        self.assertEqual(legal_before, accepted_old)
        self.assertEqual(legal_before, accepted_new)
        self.assertTrue(selected_keys(case, warm) <= retained)
        self.assertEqual(before, (case, condition, options))
        self.assertTrue(stats['complete']); self.assertGreater(stats['removed'], 0)
        self.assertEqual(stats['condition_sha256'], condition['condition_sha256'])
        RECORDS['checks']['original_cartesian'] = {'assignments': assignments,
            'complete_legal_schedules': len(legal_before), 'before_options': len(options),
            'after_options': len(kept), 'legal_set_equal': True,
            'both_structural_matrix_projections_equal_oracle': True,
            'warm_preserved': True, 'models': 2, 'include_physics': False}

    def test_half_open_fractional_boundary_same_frequency_and_independent_domain(self):
        data = self.prepare(small_fixture()); case = data[0]
        kept, _ = self.filter(data); keys = {option_key(o) for o in kept}
        sid = case['scenarios'][0]['id']
        stages = {s['shared_stage_id']: s['id'] for s in case['scenarios'][0]['stage_instances']}
        def survives(shared, opp, start):
            return any(k[1] == stages[shared] and k[3] == opp and k[4] == F(start) for k in keys)
        # Closed A.pre is CPU1/M [0,2); CPU2/M may overlap on the same domain.
        self.assertTrue(survives('B.pre', 'M', '0'))
        self.assertFalse(survives('B.pre', 'H', '0'))
        self.assertFalse(survives('B.pre', 'L', '3/2'))
        self.assertTrue(survives('B.pre', 'L', '2'))  # touching is legal
        self.assertTrue(survives('B.main', 'H', '0'))  # independent NPU domain
        # Open B.pre warm [0,3/2) is not an anchor: it must not remove B.main/0.
        self.assertTrue(survives('B.main', 'M', '0'))
        self.assertTrue(any(F(o['end_ms']).denominator != 1 for o in kept))
        RECORDS['checks']['boundaries'] = {'same_frequency_CPU_concurrency': True,
            'different_frequency_overlap_removed': True, 'half_open_touch_retained': True,
            'fractional_ends_exact': True, 'independent_domain_retained': True,
            'open_warm_not_an_anchor': True, 'scene': sid}

    def test_same_unit_overlap_removed_but_exact_touch_retained(self):
        data = self.prepare(small_fixture(same_unit=True))
        kept, _ = self.filter(data)
        stage = next(s['id'] for s in data[0]['scenarios'][0]['stage_instances']
                     if s['shared_stage_id'] == 'B.pre')
        starts = {F(o['start_ms']) for o in kept if o['stage_instance_id'] == stage}
        self.assertNotIn(F(0), starts); self.assertNotIn(F('3/2'), starts)
        self.assertIn(F(2), starts)

    def test_both_direct_dependency_directions_preserve_equality(self):
        checks = []
        for closed in ('B.main', 'B.pre'):
            data = self.prepare(small_fixture(closed=closed))
            case, _, seed, warm, opened, _, _, original = data
            kept, stats = self.filter(data); keys = {option_key(o) for o in kept}
            legal_before, legal_after = set(), set()
            for candidate in oracle_candidates(case, seed, warm, opened):
                if independent_check(case, candidate)['valid']:
                    legal_before.add(candidate_key(candidate))
                    if selected_keys(case, candidate) <= keys:
                        legal_after.add(candidate_key(candidate))
            self.assertTrue(legal_before); self.assertEqual(legal_before, legal_after)
            if closed == 'B.pre':
                # Its exact finish is 3/2; successor start 3/2 must survive.
                self.assertTrue(any(o['shared_stage_id'] == 'B.main' and
                    F(o['start_ms']) == F('3/2') for o in kept))
                self.assertFalse(any(o['shared_stage_id'] == 'B.main' and
                    F(o['start_ms']) == 0 for o in kept))
            else:
                self.assertFalse(any(o['shared_stage_id'] == 'B.pre' and
                    F(o['end_ms']) > 5 for o in kept))
                self.assertTrue(any(o['shared_stage_id'] == 'B.pre' and
                    F(o['end_ms']) == 5 for o in kept))
            checks.append({'closed': closed, 'before': len(original), 'after': len(kept),
                           'legal': len(legal_before), 'equal': True})
        RECORDS['checks']['direct_dependency'] = checks

    def test_scene_subset_order_object_identity_and_no_cross_scene_pruning(self):
        data = self.prepare(); kept, stats = self.filter(data)
        self.assertEqual(stats['before'], len(data[-1]))
        self.assertEqual(stats['after'], len(kept))
        self.assertEqual(stats['removed'], len(data[-1]) - len(kept))
        positions = {id(o): index for index, o in enumerate(data[-1])}
        indices = [positions[id(o)] for o in kept]
        self.assertEqual(indices, sorted(indices))
        for scene in data[0]['scenarios']:
            sid = scene['id']; only = [o for o in data[-1] if o['scenario_id'] == sid]
            one, _ = self.filter(data, only, scene_ids=[sid])
            self.assertEqual({option_key(o) for o in one},
                             {option_key(o) for o in kept if o['scenario_id'] == sid})
        with self.assertRaises(ValueError):
            self.filter(data, scene_ids=['unknown'])

    def test_missing_closed_anchor_rejected_but_empty_open_set_is_recorded(self):
        data = self.prepare(small_fixture())
        case, mapping, _, _, opened, budget, condition, original = data
        sid = case['scenarios'][0]['id']
        target = opened[sid][0]
        missing_open = [o for o in original if o['stage_instance_id'] != target]
        kept, stats = self.filter(data, missing_open)
        self.assertTrue(stats['complete'])
        self.assertIn({'scenario_id': sid, 'stage_instance_id': target},
                      stats['empty_open_stage_option_sets'])
        closed = next(s['id'] for s in case['scenarios'][0]['stage_instances']
                      if s['id'] not in opened[sid])
        with self.assertRaises(ValueError):
            self.filter(data, [o for o in original if o['stage_instance_id'] != closed])
        # Controlled missing-open injection verifies that the model keeps the
        # one-hot contradiction instead of silently dropping that Stage.
        expanded = expand_options(case, load_config(), budget=budget)
        with patch.object(milp, 'expand_options', return_value=[o for o in expanded
                            if o['stage_instance_id'] != target]):
            model = structural_model(case, mapping, condition, budget,
                                     preeliminate_closed_anchors=True)
        self.assertTrue(any(not row['coef'] and row['rhs'] == -1
                            for row in model.rows if row['tag'] == 'stage_unique/lower'))
        self.assertEqual({option_key(o) for o in model.options},
                         {option_key(o) for o in kept})
        RECORDS['checks']['empty_sets'] = {'missing_closed_rejected': True,
            'missing_open_recorded': True, 'stage_unique_contradiction_retained': True,
            'injection_is_not_a_physical_infeasibility_certificate': True}

    def test_same_shared_stage_repeated_request_uses_instance_identity(self):
        case, mapping, seed, warm, opened = small_fixture()
        scene = case['scenarios'][0]; sid = scene['id']
        original = next(s for s in scene['stage_instances'] if s['shared_stage_id'] == 'B.pre')
        repeated = deepcopy(original); repeated['id'] += '_copy'; repeated['request_id'] += '_copy'
        scene['stage_instances'].append(repeated)
        request = deepcopy(next(r for r in scene['requests'] if r['id'] == original['request_id']))
        request['id'] = repeated['request_id']; request['stage_instance_ids'] = [repeated['id']]
        scene['requests'].append(request)
        case['start_domain']['by_scene_stage_ms'][sid][repeated['id']] = ['0', '2', '5']
        for candidate in (seed, warm):
            candidate['scenes'][sid].append({'stage_id': repeated['id'], 'unit': 'CPU2',
                                            'opp': 'M', 'start_ms': '5'})
        opened[sid] = [repeated['id']]
        data = self.prepare((case, mapping, seed, warm, opened)); kept, _ = self.filter(data)
        values = {(o['stage_instance_id'], F(o['start_ms'])) for o in kept}
        self.assertIn((original['id'], F(0)), values)
        self.assertIn((repeated['id'], F(2)), values)
        self.assertNotIn((repeated['id'], F(0)), values)
        self.assertNotIn((original['id'], F(5)), values)
        RECORDS['checks']['repeated_request'] = {'same_shared_stage': 'B.pre',
            'closed_original_not_confused_with_open_copy': True}

    def test_forged_end_domain_mode_and_unknown_identity_are_rejected(self):
        data = self.prepare(small_fixture()); before = deepcopy(data[-1])
        changes = [('end_ms', '999'), ('domain_id', 'NPU'),
                   ('duration_ms', '999'), ('stage_instance_id', 'unknown'),
                   ('scenario_id', 'unknown')]
        for field, value in changes:
            modified = deepcopy(data[-1]); modified[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.filter(data, modified)
        self.assertEqual(data[-1], before)

    def test_budget_interrupt_returns_no_complete_partial_result(self):
        data = self.prepare(); before = deepcopy((data[0], data[6], data[-1]))
        calls = 0; loop_entered = False
        original_hash = propagation.canonical_hash
        def detect_option_loop(value):
            nonlocal loop_entered
            if value is data[-1]:
                loop_entered = True
            return original_hash(value)
        def expire():
            nonlocal calls
            if loop_entered:
                calls += 1
            if calls >= 4:
                raise Exhausted('independent injected expiry')
        # Mid-operation failure cannot return a misleading complete filter.
        with patch.object(propagation, 'canonical_hash', side_effect=detect_option_loop), \
                patch.object(data[5], 'check', side_effect=expire):
            with self.assertRaises(Exhausted):
                self.filter(data)
        self.assertTrue(loop_entered); self.assertEqual(calls, 4)
        self.assertEqual(before, (data[0], data[6], data[-1]))
        RECORDS['checks']['interrupt'] = {'injected_check_calls': calls,
            'after_option_loop_started': True,
            'raises_instead_of_returning_complete': True, 'input_unchanged': True}

    def test_default_off_is_byte_identical_and_flag_rejects_unscoped_use(self):
        data = self.prepare(small_fixture()); case, mapping, _, _, _, budget, condition, _ = data
        self.assertIs(inspect.signature(milp.build_model).parameters[
            'preeliminate_closed_anchors'].default, False)
        omitted = structural_model(case, mapping, condition, budget)
        explicit = structural_model(case, mapping, condition, budget,
                                    preeliminate_closed_anchors=False)
        assert_solver_bytes_equal(self, omitted, explicit)
        for name in ('names', 'rows', 'options', 'option_vars', 'shared', 'scenes',
                     'c', 'lb', 'ub', 'bounds', 'integer', 'logical_binary', 'formulation'):
            self.assertEqual(getattr(omitted, name), getattr(explicit, name), name)
        self.assertEqual(omitted.summary(), explicit.summary())
        with self.assertRaises(ValueError):
            milp.build_model(case, with_auto_low_idle(load_config()),
                include_physics=False, budget=budget, fixed_shared_deployment=mapping,
                preeliminate_closed_anchors=True)
        for invalid in (None, 1, 'true'):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                structural_model(case, mapping, condition, budget,
                                 preeliminate_closed_anchors=invalid)
        RECORDS['checks']['default_off'] = {'eight_solver_arrays_byte_equal': True,
            'metadata_equal': True, 'unscoped_enable_rejected': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--records')
    args, remaining = parser.parse_known_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AnchorIndependentTests))
    RECORDS['result'] = {'tests': result.testsRun, 'failures': len(result.failures),
                         'errors': len(result.errors), 'passed': result.wasSuccessful()}
    if args.records:
        target = Path(args.records)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(RECORDS, stream, ensure_ascii=False, indent=2)
    sys.exit(0 if result.wasSuccessful() else 1)
