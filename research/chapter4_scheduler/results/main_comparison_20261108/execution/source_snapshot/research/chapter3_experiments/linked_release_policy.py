"""K174 bounded, exact-arithmetic neighborhood selection; no solve/thermal work.

Called only after the original linked-condition SAFE validation. The checks
below bind that condition to the current root; they do not replace physical
evaluation or certify a new schedule. Core rule is unchanged from K174.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

PROTOCOL = 'k174-one-closed-stage-opp-start-release-v1'
RULE = 'slower-cheaper-closed-retiming-with-open-conflict-v1'


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _check(budget):
    if budget is not None:
        budget.check()


def _candidate_options(candidate):
    result = {}
    for sid, rows in candidate['scenes'].items():
        result[sid] = {r['stage_id']: {'unit': r['unit'], 'opp': r['opp'],
            'start_ms': str(F(r['start_ms']))} for r in rows}
        if len(result[sid]) != len(rows):
            raise ValueError('Duplicate candidate Stage')
    return result


def _binding(instance, condition, budget):
    budget.check()
    if condition.get('protocol') != 'fixed-unit-linked-opp-start-warm-closed-v1':
        raise ValueError('Release selection requires an original linked condition')
    if condition.get('condition_sha256') != canonical({k: v for k, v in condition.items()
            if k != 'condition_sha256'}):
        raise ValueError('Changed baseline condition')
    input_hash = canonical(instance)
    if input_hash != condition['source_input_sha256']:
        raise ValueError('Wrong original full input')
    identity = getattr(budget, '_scene_adapter_budget_identity', None)
    if not identity or identity != condition['budget_identity']:
        raise ValueError('Wrong invocation root budget')
    seed = _candidate_options(condition['seed_candidate'])
    warm = _candidate_options(condition['warm_candidate'])
    if seed != condition['seed_options_by_scene'] or warm != condition['warm_options_by_scene']:
        raise ValueError('Candidate option identities changed')
    scenes = {s['id']: s for s in instance['scenarios']}
    if len(scenes) != len(instance['scenarios']) or set(scenes) != set(warm) or set(seed) != set(warm):
        raise ValueError('Scene identities changed')
    for label, options in (('seed', seed), ('warm', warm)):
        candidate = condition[label+'_candidate']; receipt = condition[label+'_receipt']
        budget.check()
        formed = receipt.get('completed_at_elapsed_s')
        if (canonical(candidate) != condition[label+'_candidate_sha256']
                or receipt.get('safe_candidate') != candidate
                or receipt.get('state') != 'SAFE' or receipt.get('rankable_energy') is not True
                or receipt.get('receipt_sha256') != condition[label+'_receipt_sha256']
                or receipt.get('receipt_sha256') != canonical({k: v for k, v in receipt.items() if k != 'receipt_sha256'})
                or receipt.get('identity', {}).get('budget') != identity
                or isinstance(formed, bool) or not isinstance(formed, (int, float))
                or not math.isfinite(formed) or not 0 <= formed < budget.seconds
                or formed > budget.elapsed):
            raise ValueError('Requires current-call complete SAFE evidence')
        for sid, scene in scenes.items():
            budget.check()
            expected = {s['id'] for s in scene['stage_instances']}
            if set(options[sid]) != expected or set(seed[sid]) != expected:
                raise ValueError('Incomplete Stage identity')
            if any(seed[sid][k]['unit'] != warm[sid][k]['unit'] for k in expected):
                raise ValueError('Release may not change any seed unit')
    for sid, values in condition['opened_by_scene'].items():
        if not values or len(values) != len(set(values)) or not set(values) < set(warm[sid]):
            raise ValueError('Invalid original second-phase mask')
    if set(condition['opened_by_scene']) != set(scenes):
        raise ValueError('Incomplete second-phase masks')
    binding = {'protocol': PROTOCOL, 'rule': RULE, 'source_input_sha256': input_hash,
        'baseline_condition_sha256': condition['condition_sha256'],
        'seed_candidate_sha256': condition['seed_candidate_sha256'],
        'S1_candidate_sha256': condition['warm_candidate_sha256'],
        'S1_receipt_sha256': condition['warm_receipt_sha256'],
        'budget_identity': deepcopy(identity),
        'rule_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    budget.check()
    return binding


def select_release(instance, baseline_condition, *, budget):
    """Append at most one closed Stage per scene; selection work is root-billed."""
    budget.check()
    started = budget.elapsed
    binding = _binding(instance, baseline_condition, budget)
    old = deepcopy(baseline_condition['opened_by_scene'])
    records = {}
    for scene in instance['scenarios']:
        budget.check()
        sid = scene['id']
        records[sid] = select_scene(instance, scene,
            baseline_condition['warm_options_by_scene'][sid], old[sid], budget=budget)
    new = {sid: records[sid]['opened'] for sid in old}
    budget.check()
    receipt = dict(binding, base_opened_by_scene=old, opened_by_scene=new,
        scenes=records, started_at_s=started, completed_at_s=budget.elapsed,
        scope='neighborhood selection only; no feasible schedule, energy bound or new SAFE U')
    receipt['selection_sha256'] = canonical(receipt)
    result = {'opened_by_scene': deepcopy(new), 'receipt': receipt}
    validate_selection(instance, baseline_condition, result, budget=budget)
    return result


def validate_selection(instance, baseline_condition, selection, *, budget):
    """Reject stale/mutated identities or masks; no re-selection or clock reset."""
    binding = _binding(instance, baseline_condition, budget)
    if not isinstance(selection, dict) or set(selection) != {'opened_by_scene', 'receipt'}:
        raise ValueError('Invalid release selection')
    receipt = selection['receipt']
    if any(receipt.get(k) != v for k, v in binding.items()):
        raise ValueError('Wrong release anchor, input, source or budget')
    if receipt.get('selection_sha256') != canonical({k: v for k, v in receipt.items() if k != 'selection_sha256'}):
        raise ValueError('Changed release selection receipt')
    old = baseline_condition['opened_by_scene']; new = selection['opened_by_scene']
    if receipt.get('base_opened_by_scene') != old or receipt.get('opened_by_scene') != new or set(new) != set(old) or set(receipt['scenes']) != set(old):
        raise ValueError('Release masks do not match baseline or receipt')
    for sid, values in new.items():
        budget.check()
        original = set(old[sid]); chosen = set(values)
        if len(values) != len(chosen) or not original <= chosen or len(chosen-original) > 1 or not chosen < set(baseline_condition['warm_options_by_scene'][sid]):
            raise ValueError('Release must append at most one and keep a closed Stage')
        record = receipt['scenes'][sid]
        if record['opened'] != values or ({record['selected']} if record['selected'] else set()) != chosen-original:
            raise ValueError('Released Stage identity mismatch')
    a, b = receipt.get('started_at_s'), receipt.get('completed_at_s')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (a, b)) or not 0 <= a <= b < budget.seconds or b > budget.elapsed:
        raise ValueError('Selection did not complete inside the original root')
    budget.check()
    return deepcopy(selection)


# K174 core, with cooperative root checks at loop boundaries.
def conflict(a, b, edges):
    overlap = max(F(a['start_ms']), F(b['start_ms'])) < min(F(a['end_ms']), F(b['end_ms']))
    reasons = []
    if overlap and a['unit_id'] == b['unit_id']:
        reasons.append('same_unit')
    if overlap and a['domain_id'] == b['domain_id'] and (a['opp_id'] != b['opp_id']):
        reasons.append('same_domain_different_opp')
    if (a['stage_id'], b['stage_id']) in edges and F(a['end_ms']) > F(b['start_ms']):
        reasons.append('predecessor')
    if (b['stage_id'], a['stage_id']) in edges and F(b['end_ms']) > F(a['start_ms']):
        reasons.append('successor')
    return reasons

def view(instance, scene, warm, opened, *, budget=None):
    _check(budget)
    stages = {s['id']: s for s in scene['stage_instances']}
    if len(stages) != len(scene['stage_instances']) or set(warm) != set(stages):
        raise ValueError('Stage identity mismatch')
    if not set(opened) < set(stages) or not opened or len(opened) != len(set(opened)):
        raise ValueError('Need nonempty proper mask')
    requests = {r['id']: r for r in scene['requests']}
    edges = {tuple(x) for x in scene['dependencies']}
    if any((len(e) != 2 or not set(e) <= set(stages) for e in edges)):
        raise ValueError('Unknown edge')
    catalog = {}
    anchors = {}
    minimum = {}
    for k, s in stages.items():
        _check(budget)
        choices = {m['opp_id']: m for m in instance['stage_modes'][s['shared_stage_id']] if m['unit_id'] == warm[k]['unit']}
        if len(choices) != sum((m['unit_id'] == warm[k]['unit'] for m in instance['stage_modes'][s['shared_stage_id']])):
            raise ValueError('Ambiguous mode')
        for m in choices.values():
            _check(budget)
            if F(m['duration_ms']) <= 0 or F(m['activity_energy_J']) != F(m['activity_power_W']) * F(m['duration_ms']) / 1000:
                raise ValueError('Invalid physical mode ledger')
        m = choices[warm[k]['opp']]
        start = F(warm[k]['start_ms'])
        if start < 0 or start % F(instance['start_grid_ms']):
            raise ValueError('Anchor outside grid')
        catalog[k] = choices
        minimum[k] = min((F(m['duration_ms']) for m in choices.values()))
        anchors[k] = {'stage_id': k, 'unit_id': m['unit_id'], 'domain_id': m['domain_id'], 'opp_id': m['opp_id'], 'start_ms': str(start), 'end_ms': str(start + F(m['duration_ms']))}
    order = []
    pending = set(stages)
    while pending:
        _check(budget)
        ready = sorted((k for k in pending if not any((v == k and u in pending for u, v in edges))))
        if not ready:
            raise ValueError('Cyclic DAG')
        order += ready
        pending -= set(ready)
    earliest = {}
    latest_finish = {}
    for k in order:
        _check(budget)
        req = requests[stages[k]['request_id']]
        earliest[k] = max([F(req['release_ms'])] + [earliest[u] + minimum[u] for u, v in edges if v == k])
    for k in reversed(order):
        _check(budget)
        req = requests[stages[k]['request_id']]
        latest_finish[k] = min([F(instance['window_ms']), F(req['deadline_ms'])] + [latest_finish[v] - minimum[v] for u, v in edges if u == k])
    return (stages, edges, catalog, anchors, earliest, latest_finish)

def select_scene(instance, scene, warm, opened, *, budget=None):
    _check(budget)
    stages, edges, modes, anchors, earliest, latest = view(instance, scene, warm, opened, budget=budget)
    closed = sorted(set(stages) - set(opened))
    triggers = []
    rejected = []
    if len(closed) <= 1:
        return {'selected': None, 'opened': sorted(opened), 'triggers': [], 'reason': 'keep_one_closed_stage'}
    if F(scene['weight']) <= 0:
        return {'selected': None, 'opened': sorted(opened), 'triggers': [], 'reason': 'no_positive_objective_weight'}
    for j in closed:
        _check(budget)
        current = modes[j][warm[j]['opp']]
        for opp, m in sorted(modes[j].items()):
            _check(budget)
            saving = F(current['activity_energy_J']) - F(m['activity_energy_J'])
            if saving <= 0 or F(m['duration_ms']) <= F(current['duration_ms']):
                continue
            d = F(m['duration_ms'])
            oldstart = F(warm[j]['start_ms'])
            upper = min([latest[j]] + [F(anchors[v]['start_ms']) for u, v in edges if u == j and v in closed and (v != j)])
            lower = max([earliest[j]] + [F(anchors[u]['end_ms']) for u, v in edges if v == j and u in closed and (u != j)])
            if oldstart + d <= upper:
                continue
            grid = F(instance['start_grid_ms'])
            first = max(0, -(-lower // grid))
            last = (upper - d) // grid
            labels = []
            for n in range(first, last + 1):
                _check(budget)
                start = n * grid
                row = {'stage_id': j, 'unit_id': m['unit_id'], 'domain_id': m['domain_id'], 'opp_id': opp, 'start_ms': str(start), 'end_ms': str(start + d)}
                if any((conflict(row, anchors[k], edges) for k in closed if k != j)):
                    continue
                blockers = {k: conflict(row, anchors[k], set()) for k in sorted(opened)}
                blockers = {k: v for k, v in blockers.items() if v}
                labels.append({'label': row, 'open_anchor_resource_conflicts': blockers})
            if not labels or any((not x['open_anchor_resource_conflicts'] for x in labels)):
                rejected.append({'stage_id': j, 'opp': opp, 'reason': 'no_labels_or_unblocked_retiming_exists', 'necessary_label_count': len(labels)})
                continue
            triggers.append({'stage_id': j, 'target_opp': opp, 'unit_id': m['unit_id'], 'old_start_ms': str(oldstart), 'old_activity_energy_J': current['activity_energy_J'], 'new_activity_energy_J': m['activity_energy_J'], 'activity_saving_proxy_J': str(saving), 'weighted_proxy_J': str(F(scene['weight']) * saving), 'earliest_ms': str(lower), 'latest_start_ms': str(upper - d), 'last_grid_start_ms': str(last * grid), 'old_start_new_end_ms': str(oldstart + d), 'latest_finish_ms': str(upper), 'necessary_labels': labels})
    triggers.sort(key=lambda t: (-F(t['weighted_proxy_J']), t['stage_id'], t['target_opp']))
    selected = triggers[0]['stage_id'] if triggers else None
    return {'selected': selected, 'opened': sorted(set(opened) | ({selected} if selected else set())), 'triggers': triggers, 'rejected': rejected, 'reason': 'triggered' if selected else 'no_trigger'}
