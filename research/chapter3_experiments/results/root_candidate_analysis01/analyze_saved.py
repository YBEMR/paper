"""K149: standard-library-only analysis of saved options and native logs.

Does not import planner/evaluator modules, form a matrix, solve, or recompute heat.
The proposed filter is not installed in production code by this script.
"""
from collections import Counter
from fractions import Fraction as F
import csv
import hashlib
from itertools import product
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
RUN = OUT.parent/'linked_five_open_pair01'
inputs_read = {}


def read(path):
    p = Path(path)
    raw = p.read_bytes()
    inputs_read[p.relative_to(REPO).as_posix()] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def conflict(option, anchor):
    overlap = max(option['start'], anchor['start']) < min(option['end'], anchor['end'])
    reasons = []
    if overlap and option['unit'] == anchor['unit']:
        reasons.append('same_unit_overlap')
    if overlap and option['domain'] == anchor['domain'] and option['opp'] != anchor['opp']:
        reasons.append('shared_domain_different_opp_overlap')
    return reasons


def topology(options, instance):
    events = sorted({F(0), F(instance['window_ms'])} |
                    {o[k] for o in options for k in ('start', 'end')})
    domains = instance['platform']['domains']
    states = 0
    for left, right in zip(events, events[1:]):
        assert left < right
        possible = {d: {'L'} for d in domains}
        for o in options:
            if o['start'] <= left < o['end']:
                possible[o['domain']].add(o['opp'])
        states += len(list(product(*(sorted(possible[d]) for d in domains))))
    return {'options': len(options), 'events': len(events), 'intervals': len(events)-1,
            'joint_state_groups': states,
            'conditional_temperature_energy_row_pairs': states*(len(instance['platform']['node_order'])+1)}


def static_scene(job, index, scene, result, instance):
    sid = scene['id']
    stage_shared = {s['id']: s['shared_stage_id'] for s in scene['stage_instances']}
    modes = {(shared, m['unit_id'], m['opp_id']): m
             for shared, values in instance['stage_modes'].items() for m in values}
    grid = F(instance['start_grid_ms'])
    path = RUN/job/'pass_02'/f'scene_{index}'/'augmented_requests'/f'request_{index+1:06d}'
    labels = read(path/'labels.json')
    matrix = read(path/'matrix_identities.json')
    options = []
    for name in labels['names']:
        if not name.startswith('y:'):
            continue
        stage, suffix = name[2:].rsplit('@', 1)
        unit, opp, slot = suffix.split(':')
        assert stage in stage_shared and slot.startswith('g')
        mode = modes[stage_shared[stage], unit, opp]
        start = grid*int(slot[1:])
        options.append({'name': name, 'stage': stage, 'unit': unit, 'opp': opp,
                        'domain': mode['domain_id'], 'start': start,
                        'end': start+F(mode['duration_ms'])})
    phase = result['phases'][1]
    condition = phase['condition']
    opened = set(condition['opened_by_scene'][sid])
    closed = set(stage_shared)-opened
    anchors = [o for o in options if o['stage'] in closed]
    assert len(closed) == 2 and len(anchors) == 2
    assert len({o['stage'] for o in anchors}) == 2
    warm = condition['warm_options_by_scene'][sid]
    for a in anchors:
        w = warm[a['stage']]
        assert (a['unit'], a['opp'], a['start']) == (w['unit'], w['opp'], F(w['start_ms']))
    removed, retained = [], []
    for o in options:
        reasons = [{'anchor_stage': a['stage'], 'reasons': conflict(o, a)}
                   for a in anchors if a['stage'] != o['stage'] and conflict(o, a)]
        if reasons:
            assert o['stage'] in opened
            removed.append({**o, 'certified_conflicts': reasons})
        else:
            retained.append(o)
    before, after = topology(options, instance), topology(retained, instance)
    expected = phase['scenes'][sid]['model_summary']
    assert before['options'] == expected['options']
    assert before['events'] == expected['events_per_scene'][sid]
    assert before['joint_state_groups'] == sum(n.startswith('w:') for n in labels['names'])
    tags = Counter(labels['row_tags'])
    physical_rows = sum(v for k,v in tags.items()
                        if k.startswith(('thermal_propagation/', 'complete_energy/')))
    assert physical_rows == 2*before['conditional_temperature_energy_row_pairs']
    retained_keys = {(o['stage'],o['unit'],o['opp'],o['start']) for o in retained}
    assert all((stage,w['unit'],w['opp'],F(w['start_ms'])) in retained_keys for stage,w in warm.items())
    def serial(o):
        return {k:str(v) if isinstance(v,F) else v for k,v in o.items()}
    by_stage = []
    for stage in stage_shared:
        original = [o for o in options if o['stage']==stage]
        kept = [o for o in retained if o['stage']==stage]
        by_stage.append({'stage':stage,'closed_anchor':stage in closed,
                         'before':len(original),'after':len(kept),'removed':len(original)-len(kept)})
    return {'job':job,'scene':sid,'anchors':list(map(serial,anchors)),
            'before':before,'after_static_filter':after,'by_stage':by_stage,
            'removed_options':list(map(serial,removed)),
            'removed_reason_counts':dict(Counter(reason for o in removed
                for c in o['certified_conflicts'] for reason in c['reasons'])),
            'warm_retained':True,'original_topology_matches_saved_labels_and_rows':True,
            'native_original_dimensions':matrix,
            'scope':'static implications of closed anchors only; predicted topology, no new matrix or timing'}


def main():
    assert not (OUT/'facts.json').exists(), 'Do not overwrite a completed analysis'
    instance = read(RUN/'input_instance.json')
    result = read(RUN/'old_linked4/result.json')
    rows = [static_scene('old_linked4', n, s, result, instance)
            for n,s in enumerate(instance['scenarios'])]
    costs = list(csv.DictReader((RUN/'analysis01/exclusive_costs.csv').open(encoding='utf-8-sig')))
    inputs_read[(RUN/'analysis01/exclusive_costs.csv').relative_to(REPO).as_posix()] = hashlib.sha256(
        (RUN/'analysis01/exclusive_costs.csv').read_bytes()).hexdigest()
    totals = {job:dict() for job in ('old_linked4','new_linked5')}
    for row in costs:
        job,key = row['job'],row['budget_phase']
        totals[job][key] = totals[job].get(key,F(0))+F(row['exclusive_seconds_exact_fraction'])
    source_names = ['milp.py','linked_neighborhood.py','augmented_payload.py','solve_model.m']
    source_hashes = {name:hashlib.sha256((OUT.parents[1]/name).read_bytes()).hexdigest() for name in source_names}
    after = {n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() for n in inputs_read}
    assert after == inputs_read
    facts = {'analysis':'K149-saved-catalog-fixed-anchor-proposal-v1',
        'research_calls':0,'native_calls':0,'lp_calls':0,'model_constructions':0,'heat_evaluations':0,
        'production_changes':0,'source_sha256':source_hashes,'input_sha256':inputs_read,
        'raw_inputs_unchanged':True,'old4_static_scenes':rows,
        'existing_exclusive_cost_totals_s':{j:{k:float(v) for k,v in t.items()} for j,t in totals.items()},
        'interpretation':'Static reduction of individually impossible options, not measured LP speed or energy benefit'}
    (OUT/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'static_counts.csv').open('w',encoding='utf-8',newline='') as stream:
        fields=['scene','metric','before','after_static_filter','removed']
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for row in rows:
            for metric,old in row['before'].items():
                new=row['after_static_filter'][metric]
                writer.writerow({'scene':row['scene'],'metric':metric,'before':old,
                                 'after_static_filter':new,'removed':old-new})
    print(json.dumps([{k:r[k] for k in ('scene','before','after_static_filter','warm_retained')}
                      for r in rows],ensure_ascii=False))


if __name__=='__main__':
    main()
