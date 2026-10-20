"""K128 saved-mode algebra only: no scheduler, thermal or solver imports."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'RESEARCH_BRIEF.md').is_file())
OLD = ROOT/'research/chapter3_experiments/results/night_k127_run02'
FILES = [OLD/'base_n1/input_instance.json', OLD/'base_n1/result.json',
         OLD/'base_heft/input_instance.json', OLD/'base_heft/result.json']

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def run(out):
    out=out.resolve(); out.relative_to(ROOT)
    if out.exists(): raise FileExistsError(out)
    before={p.relative_to(ROOT).as_posix():sha(p) for p in FILES}
    instance,n1,heft_input,heft=map(read,FILES)
    assert canonical(instance)==canonical(heft_input)
    condition=n1['condition']
    seed=condition['seed_candidate']['scenes']; final=n1['safe_candidate']['scenes']
    across=defaultdict(set)
    for scene in instance['scenarios']:
        for stage in scene['stage_instances']: across[stage['shared_stage_id']].add(scene['id'])
    shared={key for key,scenes in across.items() if len(scenes)>1}
    weights={s['id']:F(s['weight']) for s in instance['scenarios']}
    assert sum(weights.values())==1
    totals={key:F(0) for key in ['current_N1_min','current_selected','release_shared_OPP_min',
                                'release_all_OPP_min','fixed_closed','opened_min']}
    rows=[]
    for scene in instance['scenarios']:
        sid=scene['id']; w=weights[sid]
        initial={r['stage_id']:r for r in seed[sid]}
        selected={r['stage_id']:r for r in final[sid]}
        opened=set(condition['opened_by_scene'][sid])
        for stage in scene['stage_instances']:
            iid,key=stage['id'],stage['shared_stage_id']; chosen=selected[iid]; anchor=initial[iid]
            assert chosen['unit']==anchor['unit']
            modes=[(i,m) for i,m in enumerate(instance['stage_modes'][key]) if m['unit_id']==anchor['unit']]
            energies={m['opp_id']:F(m['activity_power_W'])*F(m['duration_ms'])/1000 for i,m in modes}
            assert all(energies[m['opp_id']]==F(m['activity_energy_J']) for i,m in modes)
            minimum=min(energies.values()); locked=energies[anchor['opp']]
            old=minimum if iid in opened else locked
            shared_free=minimum if key in shared or iid in opened else locked
            totals['current_N1_min']+=w*old
            totals['current_selected']+=w*energies[chosen['opp']]
            totals['release_shared_OPP_min']+=w*shared_free
            totals['release_all_OPP_min']+=w*minimum
            totals['opened_min' if iid in opened else 'fixed_closed']+=w*(minimum if iid in opened else locked)
            if iid in opened: assert energies[chosen['opp']]==minimum
            rows.append({'scene':sid,'stage':key,'stage_instance':iid,'weight':str(w),
                'unit':anchor['unit'],'old_open':iid in opened,'cross_scene_shared':key in shared,
                'seed_opp':anchor['opp'],'selected_opp':chosen['opp'],
                'energies_by_OPP_J':{k:str(v) for k,v in energies.items()},
                'minimum_J':str(minimum),'minimum_OPPs':[k for k,v in energies.items() if v==minimum],
                'mode_JSON_pointers':[f'/stage_modes/{key}/{i}' for i,m in modes if energies[m['opp_id']]==minimum]})
    assert totals['current_selected']==totals['current_N1_min']
    activity=[F(0),F(0)]; parts={}
    for scene in instance['scenarios']:
        w=weights[scene['id']]
        receipt=n1['aggregation']['scenes'][scene['id']]['result']
        for j,v in enumerate(receipt['energy_components_J']['activity']): activity[j]+=w*F(v)
    assert activity[0]<=totals['current_selected']<=activity[1]
    cpu_equal={}
    for key,modes in instance['stage_modes'].items():
        cpu={unit:{m['opp_id']:(m['duration_ms'],m['activity_power_W']) for m in modes if m['unit_id']==unit}
             for unit in ('CPU1','CPU2')}
        if cpu['CPU1'] and cpu['CPU2']: cpu_equal[key]=cpu['CPU1']==cpu['CPU2']
    assert all(cpu_equal.values())
    after={p.relative_to(ROOT).as_posix():sha(p) for p in FILES}
    assert before==after
    decl=read(OLD/'declaration.json')
    assert all(sha(ROOT/p)==v for p,v in decl['source_sha256'].items())
    report={'stage':'K128','verification_status':'ANALYZED',
        'scope':'exact arithmetic on saved mode table and accepted receipts; no new arrangement',
        'source_sha256':before,'source_unchanged':before==after,'production_sources_unchanged':len(decl['source_sha256']),
        'canonical_input_sha256':canonical(instance),'shared_stage_ids':sorted(shared),
        'totals_J':{k:str(v) for k,v in totals.items()},
        'shared_OPP_optimistic_activity_reduction_J':str(totals['current_N1_min']-totals['release_shared_OPP_min']),
        'all_OPP_optimistic_activity_reduction_J':str(totals['current_N1_min']-totals['release_all_OPP_min']),
        'saved_actual_activity_interval_J':[str(v) for v in activity],
        'CPU_labels_same_OPP_duration_activity_equal':cpu_equal,'stage_rows':rows,
        'exclusions':['not a total-energy lower-bound certificate','not a schedulability or thermal witness',
                      'does not prove minimum activity choices are jointly feasible','does not predict solver runtime'],
        'new_model_thermal_solver_or_research_calls':0,
        'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    out.mkdir(parents=True)
    (out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    (out/'activity_facts.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stage':'K128','totals_J':{k:float(v) for k,v in totals.items()},
                      'old_sources_unchanged':len(decl['source_sha256']),'new_research_calls':0},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
