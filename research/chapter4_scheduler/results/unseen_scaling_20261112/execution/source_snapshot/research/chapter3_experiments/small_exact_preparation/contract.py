"""K193 preparation only: static coverage and exact-rational envelope fixtures.

There is deliberately no evaluator, MATLAB or optimization execution entry.
Record states below presume identity/timestamp admission, specified separately
in the protocol; this reducer does not authenticate physical receipts.
"""
from fractions import Fraction as Q
from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent
ROOT = PRODUCTION.parents[1]
sys.path[:0] = [str(PRODUCTION / 'small_domain_precheck/domain'), str(PRODUCTION)]
import core
from inputs import expand_options
from schedules import validate_schedule

INPUT = PRODUCTION / 'results/small_full_chain_precheck02/restricted_input.json'
CONFIG = PRODUCTION / 'results/whole_long_budget01/method/input_config.json'
EPSILON = Q(1, 1000000)
GROUPS = [('AB_offset_0ms', 'CPU1'), ('AB_offset_0ms', 'NPU0'),
          ('AC_offset_0ms', 'CPU1'), ('AC_offset_0ms', 'NPU0')]
EXPECTED_GROUP_COUNTS = [450, 650, 90, 360]


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical_candidate(candidate):
    return json.dumps(candidate, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def candidate_of(scene_id, rows):
    return {'scenes': {scene_id: [{'stage_id': row['id'], 'unit': row['unit_id'],
        'opp': row['opp_id'], 'start_ms': str(row['start'])}
        for row in sorted(rows, key=lambda row: row['id'])]}}


def make_manifest(instance, config):
    """Exactly enumerate static legality; retain full candidates, no energy."""
    legal, counts = core.enumerate_legal(instance)
    expected = set()
    for scene in instance['scenarios']:
        for choices in core.row_options(instance, scene):
            for row in choices:
                expected.add((scene['id'], row['id'], row['unit_id'], row['opp_id'], str(row['start']), str(row['end'])))
    actual = expand_options(instance, config)
    actual = {(r['scenario_id'], r['stage_instance_id'], r['unit_id'], r['opp_id'], r['start_ms'], r['end_ms']) for r in actual}
    if expected != actual or len(actual) != 78:
        raise ValueError('Whole option catalog differs from independent finite domain')
    queues = {}
    for scene in instance['scenarios']:
        sid = scene['id']
        # A one-scene structural view, preserving all physical nodes and modes.
        from copy import deepcopy
        view = deepcopy(instance)
        view['scenarios'] = [deepcopy(scene)]
        view['scenarios'][0]['weight'] = '1'
        view['start_domain']['by_scene_stage_ms'] = {sid: deepcopy(instance['start_domain']['by_scene_stage_ms'][sid])}
        for rows in legal[sid]:
            candidate = candidate_of(sid, rows)
            check = validate_schedule(view, candidate)
            if check['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
                raise ValueError('Independent static schedule rejected by common checker')
            unit = next(row for row in rows if row['shared_stage_id'] == 'A.main')['unit_id']
            canonical = tuple((r['id'], r['unit_id'], r['opp_id'], r['start']) for r in sorted(rows, key=lambda r: r['id']))
            queues.setdefault((sid, unit), []).append((canonical, candidate))
    for key in queues:
        queues[key].sort(key=lambda pair: pair[0])
    if [len(queues[k]) for k in GROUPS] != EXPECTED_GROUP_COUNTS:
        raise ValueError('Frozen group count changed')
    manifest, ids = [], set()
    for index in range(max(map(len, queues.values()))):
        for sid, unit in GROUPS:
            queue = queues[(sid, unit)]
            if index >= len(queue):
                continue
            candidate = queue[index][1]
            identity = sha256(canonical_candidate(candidate).encode('utf-8')).hexdigest()
            if identity in ids:
                raise ValueError('Duplicate canonical scene schedule')
            ids.add(identity)
            manifest.append({'ordinal': len(manifest)+1, 'id': identity,
                'scene_id': sid, 'shared_A_device': unit, 'group_ordinal': index+1,
                'candidate': candidate})
    if len(manifest) != 1550 or counts['global_legal_complete_arrangements'] != 274500:
        raise ValueError('Coverage count differs from K192')
    return manifest, counts


def min_bound(values):
    """None means positive infinity, including an empty minimum."""
    finite = [v for v in values if v is not None]
    return min(finite) if finite else None


def pair_mean(left, right):
    return None if left is None or right is None else (left+right)/2


def envelope(manifest, records, epsilon=EPSILON):
    """Exact arithmetic over admitted fixture records, no physics evaluation.

    A SAFE is [lo,hi], VIOLATION is [infinity,infinity], and every missing or
    unresolved record is [0,infinity]. No prefix or diagnostic energy is used.
    """
    domain = {row['id']: row for row in manifest}
    if len(domain) != len(manifest):
        raise ValueError('Duplicate manifest identity')
    group_counts = Counter((row['scene_id'], row['shared_A_device']) for row in manifest)
    if len(manifest) != 1550 or group_counts != dict(zip(GROUPS, EXPECTED_GROUP_COUNTS)):
        raise ValueError('Incomplete frozen coverage manifest')
    if not set(records) <= set(domain):
        raise ValueError('Record outside frozen manifest')
    groups = {key: [] for key in GROUPS}
    for row in manifest:
        record = records.get(row['id'], {'state': 'NOT_STARTED'})
        state = record['state']
        low, high = Q(0), None
        if state == 'SAFE':
            low, high = map(Q, record['energy_J'])
            if low < 0 or high < low:
                raise ValueError('Invalid admitted SAFE energy interval')
        elif state == 'VIOLATION':
            low, high = None, None
        elif state not in {'UNRESOLVED', 'TIMEOUT', 'NOT_STARTED', 'TECHNICAL_UNRESOLVED'}:
            raise ValueError('Unknown result state')
        groups[(row['scene_id'], row['shared_A_device'])].append((low, high, row['id']))
    group_bounds = {}
    for key, entries in groups.items():
        low = min_bound([r[0] for r in entries])
        high = min_bound([r[1] for r in entries])
        witness = next((r[2] for r in entries if high is not None and r[1] == high), None)
        group_bounds[key] = {'lower': low, 'upper': high, 'SAFE_witness_id': witness}
    per_device = {}
    for unit in ['CPU1', 'NPU0']:
        a, c = (group_bounds[(sid, unit)] for sid in ['AB_offset_0ms', 'AC_offset_0ms'])
        per_device[unit] = {'lower': pair_mean(a['lower'], c['lower']),
                            'upper': pair_mean(a['upper'], c['upper'])}
    lower = min_bound([v['lower'] for v in per_device.values()])
    upper = min_bound([v['upper'] for v in per_device.values()])
    gap = None if lower is None or upper is None else upper-lower
    if gap is not None and gap < 0:
        raise ValueError('Contradictory admitted energy bounds')
    state = ('FINITE_DOMAIN_INFEASIBLE' if lower is None else
             'NO_COMPLETE_SAFE_WITNESS' if upper is None else
             'FINITE_DOMAIN_EPSILON_OPTIMAL' if gap <= epsilon else 'SAFE_UPPER_WITH_GAP')
    return {'state': state, 'lower': lower, 'upper': upper, 'gap': gap,
            'groups': group_bounds, 'per_device': per_device, 'unique_optimum_proven': False}
