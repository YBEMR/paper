"""Exact list-decoder shared by the explicitly adapted HEFT and SA baselines.

Decoding is heuristic and not a coverage or infeasibility certificate. Every
complete output still goes through the common continuous thermal evaluator.
"""
from collections import deque
from fractions import Fraction as F

from schedules import validate_schedule
from start_domain import explicit_start_sets


def _check(budget):
    if budget is not None:
        budget.check()


def legal_opp_ids(instance, shared_id, unit):
    return list(dict.fromkeys(m['opp_id'] for m in instance['stage_modes'][shared_id]
                             if m['unit_id'] == unit))


def mode_for(instance, shared_id, unit, opp):
    modes = [m for m in instance['stage_modes'][shared_id]
             if m['unit_id'] == unit and m['opp_id'] == opp]
    if len(modes) != 1:
        raise ValueError('Mode unsupported or ambiguous: '+str((shared_id, unit, opp)))
    return modes[0]


def _index_scene(scene):
    stages = {s['id']: s for s in scene['stage_instances']}
    if len(stages) != len(scene['stage_instances']):
        raise ValueError('duplicate Stage instance')
    pred, succ = {key: [] for key in stages}, {key: [] for key in stages}
    for a, b in scene['dependencies']:
        if a not in stages or b not in stages or a == b:
            raise ValueError('invalid dependency')
        if a not in pred[b]:
            pred[b].append(a); succ[a].append(b)
    return stages, {r['id']: r for r in scene['requests']}, pred, succ


def upward_ranks(instance, budget=None):
    """Average fastest duration per legal execution unit + longest successor."""
    means = {}
    for key, modes in instance['stage_modes'].items():
        _check(budget)
        best = {}
        for mode in modes:
            uid, duration = mode['unit_id'], F(mode['duration_ms'])
            best[uid] = min(best.get(uid, duration), duration)
        means[key] = sum(best.values(), F(0))/len(best)
    result = {}
    for scene in instance['scenarios']:
        stages, _, pred, succ = _index_scene(scene)
        degree = {key: len(pred[key]) for key in stages}
        todo = deque(sorted(key for key in stages if not degree[key]))
        order = []
        while todo:
            _check(budget)
            key = todo.popleft(); order.append(key)
            for following in succ[key]:
                degree[following] -= 1
                if not degree[following]: todo.append(following)
        if len(order) != len(stages):
            raise ValueError('cyclic dependency graph')
        ranks = {}
        for key in reversed(order):
            ranks[key] = means[stages[key]['shared_stage_id']] + max(
                [ranks[following] for following in succ[key]] or [F(0)])
        result[scene['id']] = ranks
    return result


def earliest_placement(instance, scene, stage_id, unit, opp, scheduled,
                       budget=None, minimum_start=0):
    """Insert at the first legal declared start, preserving exact endpoints.

scheduled contains only committed rows of this scene. minimum_start is an
absolute start floor. Pairwise half-open domain conflicts preserve busy locks.
"""
    _check(budget)
    stages, requests, pred, _ = _index_scene(scene)
    if stage_id not in stages or any(key not in scheduled for key in pred[stage_id]):
        return None
    node = stages[stage_id]
    request = requests[node['request_id']]
    mode = mode_for(instance, node['shared_stage_id'], unit, opp)
    duration = F(mode['duration_ms'])
    if duration <= 0: raise ValueError('nonpositive Stage duration')
    units = {u['id']: u for u in instance['platform']['units']}
    domain = units[unit]['domain_id']
    occupied = []
    for key, row in scheduled.items():
        _check(budget)
        if key not in stages: raise ValueError('foreign scheduled Stage')
        previous_mode = mode_for(instance, stages[key]['shared_stage_id'], row['unit'], row['opp'])
        start = F(row['start_ms'])
        occupied.append((start, start+F(previous_mode['duration_ms']), row['unit'],
                         units[row['unit']]['domain_id'], row['opp']))
    earliest = max([F(0), F(minimum_start), F(request['release_ms'])]+
        [F(scheduled[key]['start_ms']) + F(mode_for(instance, stages[key]['shared_stage_id'],
             scheduled[key]['unit'], scheduled[key]['opp'])['duration_ms']) for key in pred[stage_id]])
    window, grid = F(instance['window_ms']), F(instance['start_grid_ms'])
    last = min(window, F(request['deadline_ms']))-duration
    if grid <= 0: raise ValueError('nonpositive grid')
    declared = explicit_start_sets(instance, budget=budget)
    if declared is None:
        first_index, last_index = -((-earliest)//grid), last//grid
        starts = (index*grid for index in range(first_index, last_index+1))
    else:
        starts = (s for s in declared[scene['id']][stage_id] if earliest <= s <= last)
    for start in starts:
        _check(budget)
        end = start+duration
        if all(not (max(start, a) < min(end, b) and
                    (unit == old_unit or domain == old_domain and opp != old_opp))
               for a, b, old_unit, old_domain, old_opp in occupied):
            return {'stage_id': stage_id, 'unit': unit, 'opp': opp, 'start_ms': str(start)}
    return None


def decode_plan(instance, plan, budget=None):
    """Ready-list order, fixed mapping/OPPs, and nonnegative grid-step waits."""
    _check(budget)
    keys = {s['shared_stage_id'] for sc in instance['scenarios'] for s in sc['stage_instances']}
    if set(plan['mapping']) != keys: raise ValueError('incomplete shared deployment')
    expected_scenes = {sc['id'] for sc in instance['scenarios']}
    for field in ('opps', 'priorities', 'delays'):
        if set(plan[field]) != expected_scenes: raise ValueError('incomplete scene genes')
    output = {'scenes': {}}
    grid = F(instance['start_grid_ms'])
    for scene in instance['scenarios']:
        sid = scene['id']
        stages, _, pred, _ = _index_scene(scene)
        priorities = plan['priorities'][sid]
        if len(priorities) != len(stages) or set(priorities) != set(stages):
            raise ValueError('priority permutation must cover Stage instances once')
        if set(plan['opps'][sid]) != set(stages) or set(plan['delays'][sid]) != set(stages):
            raise ValueError('incomplete Stage genes')
        ranks = {key: rank for rank, key in enumerate(priorities)}
        scheduled, remaining = {}, set(stages)
        while remaining:
            _check(budget)
            ready = [key for key in remaining if all(p in scheduled for p in pred[key])]
            if not ready: return None
            key = min(ready, key=lambda k: (ranks[k], k))
            unit, opp = plan['mapping'][stages[key]['shared_stage_id']], plan['opps'][sid][key]
            first = earliest_placement(instance, scene, key, unit, opp, scheduled, budget)
            if first is None: return None
            delay = plan['delays'][sid][key]
            if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
                raise ValueError('delay must be a nonnegative integer number of grid steps')
            row = first if not delay else earliest_placement(instance, scene, key, unit, opp,
                    scheduled, budget, F(first['start_ms'])+delay*grid)
            if row is None: return None
            scheduled[key] = row; remaining.remove(key)
        output['scenes'][sid] = list(scheduled.values())
    checked = validate_schedule(instance, output)
    _check(budget)
    return output if checked['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED' else None


def plan_from_candidate(instance, candidate, budget=None):
    """Recover a decoder plan that exactly retains this complete legal schedule."""
    checked = validate_schedule(instance, candidate)
    _check(budget)
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('cannot encode an illegal schedule')
    plan = {'mapping': {}, 'opps': {}, 'priorities': {}, 'delays': {}}
    grid = F(instance['start_grid_ms'])
    for scene in instance['scenarios']:
        sid = scene['id']; stages, _, _, _ = _index_scene(scene)
        rows = sorted(candidate['scenes'][sid], key=lambda r: (F(r['start_ms']), r['stage_id']))
        plan['opps'][sid], plan['delays'][sid] = {}, {}
        plan['priorities'][sid] = [r['stage_id'] for r in rows]
        previous = {}
        for row in rows:
            _check(budget)
            key = row['stage_id']
            first = earliest_placement(instance, scene, key, row['unit'], row['opp'], previous, budget)
            if first is None: raise ValueError('legal schedule could not be replayed')
            difference = (F(row['start_ms'])-F(first['start_ms']))/grid
            if difference < 0 or difference.denominator != 1:
                raise ValueError('schedule does not have an exact grid-step replay')
            plan['mapping'][stages[key]['shared_stage_id']] = row['unit']
            plan['opps'][sid][key] = row['opp']
            plan['delays'][sid][key] = int(difference)
            previous[key] = row
    return plan
