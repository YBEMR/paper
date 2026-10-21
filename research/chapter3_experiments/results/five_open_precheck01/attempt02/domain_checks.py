"""Exact small-domain check for opening the local main Stage.

This is a four-Stage-per-scene structural analogue: A.pre plus local
pre/main/post, with mocked SAFE identity receipts. It does not establish the
production six-Stage 4/5 mask identities (the invocation-wrapper tests do).
No MILP model, optimizer, MATLAB process or physical thermal evaluation runs.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys


SOURCE_DIR = Path(__file__).resolve().parents[2]
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import linked_neighborhood as linked
from inputs import expand_options, load_config
from run_milp_precheck import independent_check
from schedules import validate_schedule
from test_linked_neighborhood import condition_for, fixture
from thermal import Budget


def _require(value, message):
    if not value:
        raise AssertionError(message)


def _row_key(row):
    return (row['stage_id'], row['unit'], row['opp'], str(Fraction(row['start_ms'])))


def _dimensions(case, sid, seed, warm, opened):
    """Independent original-mode/start Cartesian dimensions, exact arithmetic."""
    scene = next(scene for scene in case['scenarios'] if scene['id'] == sid)
    initial = {row['stage_id']: row for row in seed['scenes'][sid]}
    anchor = {row['stage_id']: row for row in warm['scenes'][sid]}
    requests = {request['id']: request for request in scene['requests']}
    dimensions = []
    for stage in scene['stage_instances']:
        stage_id = stage['id']
        choices = []
        for mode in case['stage_modes'][stage['shared_stage_id']]:
            if mode['unit_id'] != initial[stage_id]['unit']:
                continue
            for raw_start in case['start_domain']['by_scene_stage_ms'][sid][stage_id]:
                start = Fraction(raw_start)
                end = start + Fraction(mode['duration_ms'])
                if start < Fraction(requests[stage['request_id']]['release_ms']):
                    continue
                if end > Fraction(case['window_ms']):
                    continue
                if stage_id not in opened[sid] and (
                        mode['opp_id'] != anchor[stage_id]['opp'] or
                        start != Fraction(anchor[stage_id]['start_ms'])):
                    continue
                choices.append({'stage_id': stage_id, 'unit': mode['unit_id'],
                                'opp': mode['opp_id'], 'start_ms': str(start)})
        dimensions.append(choices)
    return dimensions


def _expect_rejected(case, condition, candidate, budget, description):
    try:
        linked.check_linked_candidate(case, condition, candidate, budget=budget)
    except ValueError:
        return
    raise AssertionError('candidate unexpectedly accepted: ' + description)


def run_checks():
    case, mapping, seed, warm, old_opened = fixture()
    original = deepcopy(case)
    budget = Budget(seconds=3600)
    new_opened = deepcopy(old_opened)
    for scene in case['scenarios']:
        sid = scene['id']
        new_opened[sid] += [stage['id'] for stage in scene['stage_instances']
                            if stage['shared_stage_id'].endswith('.main')]
        _require(len(scene['stage_instances']) == 4, 'fixture must have four Stages')
        _require(len(old_opened[sid]) == 2 and len(new_opened[sid]) == 3,
                 'fixture must be the explicit 2/3-open structural analogue')
    conditions = {
        'old': condition_for(case, mapping, seed, warm, old_opened, budget),
        'new': condition_for(case, mapping, seed, warm, new_opened, budget),
    }
    opened_map = {'old': old_opened, 'new': new_opened}
    originals = expand_options(case, load_config(), budget=budget)
    outcomes, fractional_witness = {}, None
    for label, condition in conditions.items():
        projected, stats = linked.filter_linked_options(case, condition, originals,
                                                       budget=budget)
        _require(stats['complete'], label + ': incomplete option filtering')
        by_scene = {}
        for scene in case['scenarios']:
            sid = scene['id']
            dimensions = _dimensions(case, sid, seed, warm, opened_map[label])
            expected_options = {_row_key(row) for choices in dimensions for row in choices}
            actual_options = {(option['stage_instance_id'], option['unit_id'],
                               option['opp_id'], str(Fraction(option['start_ms'])))
                              for option in projected if option['scenario_id'] == sid}
            _require(expected_options == actual_options,
                     label + '/' + sid + ': filtered option projection differs')
            legal, production, inspected = set(), set(), 0
            for selected in product(*dimensions):
                inspected += 1
                candidate = deepcopy(warm)
                candidate['scenes'][sid] = list(selected)
                key = tuple(sorted(_row_key(row) for row in selected))
                independent = independent_check(case, candidate)
                if independent['valid']:
                    legal.add(key)
                local = {'scenes': {sid: list(selected)}}
                try:
                    linked.check_linked_candidate(case, condition, local,
                                                  budget=budget, scene_id=sid)
                except ValueError:
                    accepted = False
                else:
                    accepted = True
                    production.add(key)
                _require(accepted == independent['valid'],
                         label + '/' + sid + ': production/oracle legality differs')
                if independent['valid'] and fractional_witness is None:
                    for stage_id, row in independent['scenes'][sid]['rows'].items():
                        if row['end'].denominator != 1:
                            checked = validate_schedule(case, candidate)
                            actual = next(item for item in checked['scenes'][sid]['rows']
                                          if item['stage_id'] == stage_id)
                            _require(Fraction(actual['end_ms']) == row['end'],
                                     'production rounded a noninteger end')
                            fractional_witness = {'scene': sid, 'stage': stage_id,
                                'start_ms': str(row['start']),
                                'duration_ms': str(row['mode']['duration_ms']),
                                'end_ms': str(row['end'])}
            _require(legal == production and bool(legal),
                     label + '/' + sid + ': empty or unequal legal projection')
            by_scene[sid] = {'cartesian_assignments': inspected,
                            'legal_keys': legal, 'legal_assignments': len(legal),
                            'option_count': len(expected_options)}
        outcomes[label] = by_scene
        linked.check_linked_candidate(case, condition, warm, budget=budget)

    added = {}
    for scene in case['scenarios']:
        sid = scene['id']
        old, new = outcomes['old'][sid]['legal_keys'], outcomes['new'][sid]['legal_keys']
        _require(old <= new, sid + ': opening main lost old legal schedules')
        additions = new - old
        _require(bool(additions), sid + ': no newly legal main choice in this fixture')
        main_id = next(stage['id'] for stage in scene['stage_instances']
                       if stage['shared_stage_id'].endswith('.main'))
        anchor_main = next(row for row in warm['scenes'][sid] if row['stage_id'] == main_id)
        _require(any(next(row for row in key if row[0] == main_id) != _row_key(anchor_main)
                     for key in additions), sid + ': main did not actually gain a choice')
        added[sid] = len(additions)

    condition = conditions['new']
    sid = case['scenarios'][0]['id']
    changed_post = deepcopy(warm)
    post = next(row for row in changed_post['scenes'][sid] if '.post' in row['stage_id'])
    post['opp'] = 'H' if post['opp'] != 'H' else 'L'
    _require(not linked._member(condition, sid, post['stage_id'], post['unit'],
                                post['opp'], post['start_ms']), 'closed post OPP escaped')
    _expect_rejected(case, condition, changed_post, budget, 'closed post OPP')
    changed_start = deepcopy(warm)
    post = next(row for row in changed_start['scenes'][sid] if '.post' in row['stage_id'])
    post['start_ms'] = str(Fraction(post['start_ms']) + Fraction(case['start_grid_ms']))
    _require(not linked._member(condition, sid, post['stage_id'], post['unit'],
                                post['opp'], post['start_ms']), 'closed post start escaped')
    _expect_rejected(case, condition, changed_start, budget, 'closed post start')
    changed_unit = deepcopy(warm)
    row = next(row for row in changed_unit['scenes'][sid] if 'A.pre' in row['stage_id'])
    row['unit'] = 'CPU2'
    _require(not linked._member(condition, sid, row['stage_id'], row['unit'],
                                row['opp'], row['start_ms']), 'seed-fixed device escaped')
    _expect_rejected(case, condition, changed_unit, budget, 'seed-fixed device')
    _require(fractional_witness is not None, 'no fractional-end witness checked')
    _require(case == original, 'input fixture was modified')

    # All cross-scene shared choices here are already fixed to identical seed
    # units. No cross-scene timing constraint remains; complete legal counts
    # are consequently products of these exhaustive per-scene projections.
    counts = {}
    for label, by_scene in outcomes.items():
        full_count = 1
        for item in by_scene.values():
            full_count *= item['legal_assignments']
        counts[label] = {'by_scene': {sid: {key: value for key, value in item.items()
                                          if key != 'legal_keys'}
                                     for sid, item in by_scene.items()},
                         'complete_legal_count_by_fixed_device_factorization': full_count}
    return {'state': 'PASS', 'scope': 'four-Stage-per-scene 2/3-open analogue; '
            'production six-Stage 4/5 masks require separate wrapper checks',
            'checks': {'independent_cartesian_projection_equal': True,
                'old_legal_domain_subset_of_new': True, 'warm_retained_in_both': True,
                'new_legal_main_choices': added, 'closed_post_opp_rejected': True,
                'closed_post_exact_start_rejected': True, 'seed_units_fixed': True,
                'input_unchanged': True, 'exact_fractional_end': fractional_witness},
            'counts': counts, 'condition_sha256': {label: value['condition_sha256']
                for label, value in conditions.items()},
            'native_calls': 0, 'research_calls': 0, 'milp_models': 0,
            'physical_thermal_evaluations': 0,
            'receipt_scope': 'mock SAFE receipts test identities only; no physical safety claim'}


if __name__ == '__main__':
    print(json.dumps(run_checks(), ensure_ascii=False, indent=2, allow_nan=False))
