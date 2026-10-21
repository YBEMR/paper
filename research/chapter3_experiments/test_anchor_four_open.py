"""Actual 4-open/2-closed topology on tiny original-response start domains.

All original Stage modes, durations, platform and safety parameters are kept.
Only test task/start selection is reduced. Cartesian checks are performed one
scene at a time with the other scene's warm fixed, avoiding their joint product.
No model, solver or physical trajectory is evaluated; receipts are mock identity
fixtures, not evidence of thermal safety.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import unittest

import anchor_preelimination as propagation
from control_policy import with_auto_low_idle
from run_milp_precheck import candidate_key, independent_check, select_fixture
from test_anchor_preelimination import linked_options, selected_keys
from test_linked_neighborhood import condition_for, oracle_dimensions
from test_neighborhood_milp import base_input, option_key
from thermal import Budget


RECORDS = {'scope': 'two tiny scenes, exact actual four-open/two-closed topology',
           'models': 0, 'solver_calls': 0, 'research_calls': 0,
           'physical_evaluations': 0, 'scenes': {}}


def four_open_fixture():
    base = base_input(); selected, starts = {}, {
        'A.pre': [0, 50], 'A.main': [20, 60], 'A.post': [70, 115]}
    for scene in base['scenarios']:
        local = 'B' if scene['id'].startswith('AB') else 'C'
        selected[scene['id']] = ['A.'+p for p in ('pre', 'main', 'post')] + [
            local+'.'+p for p in ('pre', 'main', 'post')]
        starts.update({local+'.pre': [0, 50], local+'.main': [60],
                       local+'.post': [130]})
    case, by_stage = select_fixture(base, 'anchor_four_open', selected, starts)
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                            'by_scene_stage_ms': by_stage}
    case = with_auto_low_idle(case)
    mapping = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
    candidate, opened = {'scenes': {}}, {}
    for scene in case['scenarios']:
        sid = scene['id']; candidate['scenes'][sid] = []; opened[sid] = []
        for stage in scene['stage_instances']:
            shared = stage['shared_stage_id']
            if shared == 'A.pre': unit, start = 'CPU1', '0'
            elif shared == 'A.main': unit, start = 'NPU0', '20'
            elif shared == 'A.post': unit, start = 'CPU1', '70'
            elif shared.endswith('.pre'): unit, start = 'CPU2', '0'
            elif shared.endswith('.main'):
                unit, start = ('NPU0' if shared.startswith('B.') else 'GPU0'), '60'
            else: unit, start = 'CPU1', '130'
            if shared.startswith('A.') or shared.endswith('.pre'):
                opened[sid].append(stage['id'])
            candidate['scenes'][sid].append({'stage_id': stage['id'], 'unit': unit,
                                             'opp': 'M', 'start_ms': start})
    return case, mapping, deepcopy(candidate), candidate, opened


class FourOpenCartesianTests(unittest.TestCase):
    def test_each_scene_1296_cartesian_preserves_complete_legal_set(self):
        case, mapping, seed, warm, opened = four_open_fixture(); budget = Budget(seconds=600)
        self.assertTrue(independent_check(case, warm)['valid'])
        condition = condition_for(case, mapping, seed, warm, opened, budget)
        original = linked_options(case, condition, budget)
        original = [o for o in original if F(o['end_ms']) <= F(o['request_deadline_ms'])]
        before = deepcopy((case, condition, original))
        kept, stats = propagation.filter_closed_anchor_options(case, condition,
                                                               original, budget=budget)
        keys = {option_key(o) for o in kept}
        self.assertTrue(selected_keys(case, warm) <= keys)
        self.assertEqual(before, (case, condition, original))
        all_dimensions = oracle_dimensions(case, seed, warm, opened)
        for scene in case['scenarios']:
            sid = scene['id']; self.assertEqual(len(opened[sid]), 4)
            self.assertEqual(len(scene['stage_instances']) - len(opened[sid]), 2)
            dimensions = [dim for dim in all_dimensions if dim[0][0] == sid]
            legal_before, legal_after = set(), set(); assignments = 0
            for values in product(*dimensions):
                assignments += 1
                candidate = deepcopy(warm)
                candidate['scenes'][sid] = [deepcopy(row) for _, row, _ in values]
                if independent_check(case, candidate)['valid']:
                    key = candidate_key(candidate); legal_before.add(key)
                    if selected_keys(case, candidate) <= keys:
                        legal_after.add(key)
            self.assertEqual(assignments, 1296)
            self.assertTrue(legal_before); self.assertEqual(legal_before, legal_after)
            original_n = sum(o['scenario_id'] == sid for o in original)
            after_n = sum(o['scenario_id'] == sid for o in kept)
            self.assertLess(after_n, original_n)
            RECORDS['scenes'][sid] = {'opened': 4, 'closed': 2,
                'cartesian_assignments': assignments,
                'legal_before': len(legal_before), 'legal_after': len(legal_after),
                'legal_sets_equal': True, 'options_before': original_n,
                'options_after': after_n, 'warm_preserved': True,
                'other_scene_fixed_only_for_independent_oracle': True}
        RECORDS['stats'] = {k: stats[k] for k in ('before', 'after', 'removed', 'complete')}


if __name__ == '__main__':
    unittest.main(verbosity=2)
