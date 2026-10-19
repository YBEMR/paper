"""Read archived JSON only. No production imports, model, solver or thermal work."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json

ROOT = Path.cwd()  # Execute from the project root; no production imports.
BASE = ROOT / 'research/chapter3_experiments/results/cumulative_pair_diagnostic01/call_off/invocation'
I = json.loads((BASE / 'input_instance.json').read_text(encoding='utf-8'))
W, G = F(I['window_ms']), F(I['start_grid_ms'])
U = {u['id']: u for u in I['platform']['units']}
OUT = {'scope': 'read-only exact static option/event arithmetic; no candidate thermal or SAFE judgment',
       'input_sha256': hashlib.sha256((BASE / 'input_instance.json').read_bytes()).hexdigest(),
       'arithmetic': 'fractions.Fraction; true duration/end retained; start grid unchanged',
       'scenes': []}

def compatible(a, b):
    if max(a['start'], b['start']) >= min(a['end'], b['end']):
        return True
    return a['unit'] != b['unit'] and (a['domain'] != b['domain'] or a['opp'] == b['opp'])

def option(row, mode, start):
    return {'stage': row['id'], 'shared': row['shared_stage_id'], 'unit': mode['unit_id'],
            'domain': mode['domain_id'], 'opp': mode['opp_id'], 'start': start,
            'end': start + F(mode['duration_ms'])}

for ix, scene in enumerate(I['scenarios']):
    D = json.loads((BASE / f'initial_scene_{ix:03d}.json').read_text(encoding='utf-8'))
    sid = scene['id']
    rows = D['witness']['evaluation']['legality']['scenes'][sid]['rows']
    byid = {r['stage_id']: r for r in rows}
    req = {r['id']: r for r in scene['requests']}
    pred = {r['id']: [] for r in scene['stage_instances']}
    succ = {r['id']: [] for r in scene['stage_instances']}
    for a, b in scene['dependencies']:
        pred[b].append(a); succ[a].append(b)
    current = {}
    report_rows = []
    for row in scene['stage_instances']:
        r = byid[row['id']]
        current[row['id']] = {'stage': row['id'], 'shared': row['shared_stage_id'],
            'unit': r['unit'], 'domain': r['domain_id'], 'opp': r['opp'],
            'start': F(r['start_ms']), 'end': F(r['end_ms'])}
        complete = max(F(byid[x]['end_ms']) for x in req[row['request_id']]['stage_instance_ids'])
        report_rows.append({**r, 'predecessors': pred[row['id']], 'successors': succ[row['id']],
            'gap_after_predecessor_ms': [str(F(r['start_ms'])-F(byid[p]['end_ms'])) for p in pred[row['id']]],
            'gap_before_successor_ms': [str(F(byid[s]['start_ms'])-F(r['end_ms'])) for s in succ[row['id']]],
            'request_completion_ms': str(complete),
            'request_slack_ms': str(F(req[row['request_id']]['deadline_ms'])-complete)})
    local_app = scene['application_pair'][1]
    suffix = {local_app+'.main', local_app+'.post'}
    variants = []
    for name in ('shared_A_only_full', 'N1_all_devices_fixed_all_OPP_starts',
                 'N1_local_suffix_fixed_devices', 'N2_local_suffix_free_devices'):
        opts = []; fixed = []; perstage = {}
        for row in scene['stage_instances']:
            sh = row['shared_stage_id']; cur = current[row['id']]
            fixed_row = name in ('N1_local_suffix_fixed_devices', 'N2_local_suffix_free_devices') and sh not in suffix
            if fixed_row:
                local = [dict(cur)]; fixed.append(dict(cur))
            else:
                modes = I['stage_modes'][sh]
                if name in ('N1_all_devices_fixed_all_OPP_starts', 'N1_local_suffix_fixed_devices') or sh.startswith('A.'):
                    modes = [m for m in modes if m['unit_id'] == cur['unit']]
                release = F(req[row['request_id']]['release_ms'])
                deadline = min(W, F(req[row['request_id']]['deadline_ms']))
                local = [option(row,m,k*G) for m in modes for k in range(int(W//G)+1)
                         if k*G >= release and k*G+F(m['duration_ms']) <= deadline]
            opts.extend(local)
            perstage[sh] = len(local)
        ev = sorted({F(0), W}|{o['start'] for o in opts}|{o['end'] for o in opts})
        necessary = []
        for o in opts:
            if all(compatible(o,f) for f in fixed if o['stage'] != f['stage']) and all(
                o['start'] >= current[p]['end'] for p in pred[o['stage']] if any(f['stage']==p for f in fixed)) and all(
                o['end'] <= current[s]['start'] for s in succ[o['stage']] if any(f['stage']==s for f in fixed)):
                necessary.append(o)
        nev = sorted({F(0), W}|{o['start'] for o in necessary}|{o['end'] for o in necessary})
        variants.append({'name':name,'scope':'static local options, not complete model size or feasible-schedule count',
            'deadline_filtered_options':len(opts), 'per_stage':perstage,
            'events':len(ev), 'intervals':len(ev)-1,
            'after_only_fixed_work_compatibility':{'options':len(necessary),'events':len(nev),'intervals':len(nev)-1},
            'all_nodes_retained':I['platform']['node_order'], 'global_bound_claim':False})
    # One hand-derived low-OPP suffix illustration per scene. Structural arithmetic only.
    main_row = next(r for r in scene['stage_instances'] if r['shared_stage_id']==local_app+'.main')
    post_row = next(r for r in scene['stage_instances'] if r['shared_stage_id']==local_app+'.post')
    illustration = {key:dict(value) for key,value in current.items()}
    changes=[]; activity_delta=F(0)
    for row in [main_row,post_row]:
        cur=current[row['id']]
        mode=next(m for m in I['stage_modes'][row['shared_stage_id']] if m['unit_id']==cur['unit'] and m['opp_id']=='L')
        start=cur['start'] if row==main_row else -((-illustration[main_row['id']]['end'])//G)*G
        illustration[row['id']]=option(row,mode,start)
        oldmode=next(m for m in I['stage_modes'][row['shared_stage_id']] if m['unit_id']==cur['unit'] and m['opp_id']==cur['opp'])
        activity_delta+=F(mode['activity_energy_J'])-F(oldmode['activity_energy_J'])
        changes.append({'shared_stage_id':row['shared_stage_id'],'unit':cur['unit'],'opp':'L','start_ms':str(start),
                        'end_ms':str(start+F(mode['duration_ms']))})
    vals=list(illustration.values())
    structure_ok=(all(compatible(a,b) for j,a in enumerate(vals) for b in vals[j+1:]) and
                  all(illustration[a]['end']<=illustration[b]['start'] for a,b in scene['dependencies']) and
                  all(F(req[row['request_id']]['release_ms'])<=illustration[row['id']]['start'] and
                      illustration[row['id']]['end']<=F(req[row['request_id']]['deadline_ms'])
                      for row in scene['stage_instances']))
    OUT['scenes'].append({'scene_id':sid,'stage_rows':report_rows,'static_counts':variants,
        'suffix_illustration':{'changes':changes,'exact_structural_arithmetic_satisfied':structure_ok,
             'activity_energy_delta_J':str(activity_delta), 'thermal_evaluation_performed':False,
             'system_energy_claim':None,'SAFE_claim':False}})

(ROOT/'.runtime').mkdir(exist_ok=True)
(ROOT/'.runtime/k123_neighborhood_audit.json').write_text(json.dumps(OUT,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for scene in OUT['scenes']:
    print(scene['scene_id'])
    for v in scene['static_counts']:
        print(v['name'],v['deadline_filtered_options'],v['events'],v['after_only_fixed_work_compatibility'])
    print(scene['suffix_illustration'])
