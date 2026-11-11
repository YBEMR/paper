"""Finite necessary-support certificates only. Never imports a solver/thermal kernel."""
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
from itertools import product, combinations
import ast
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ARCH=REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'
CAP=4096
TOTAL_CAP=2000000
UTC=timezone.utc
now=lambda:datetime.now(UTC).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def save(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def paths(scene):
    successors={s['id']:[] for s in scene['stage_instances']}
    for a,b in scene['dependencies']:successors[a].append(b)
    result={}
    for a in successors:
        queue=[(a,[a])];seen={a}
        for at,path in queue:
            for b in successors[at]:
                if b not in seen:seen.add(b);queue.append((b,path+[b]));result[a,b]=path+[b]
    return result

def support_groups(scene,options,left,right,domains):
    shared={s['id']:s['shared_stage_id'] for s in scene['stage_instances']}
    grouped={d:{} for d in domains}
    for o in options:
        if o['scenario_id']!=scene['id'] or not (F(o['start_ms'])<=left and right<=F(o['end_ms'])):continue
        key=(o['stage_instance_id'],o['unit_id'])
        grouped[o['domain_id']].setdefault(o['opp_id'],{}).setdefault(key,[]).append(o['option_id'])
    return {d:{opp:[dict(stage=k[0],unit=k[1],shared=shared[k[0]],option_ids=ids)
                   for k,ids in sorted(groups.items())] for opp,groups in opps.items()}
            for d,opps in grouped.items()}

def conflict(a,b,dependency_paths):
    if a['stage']==b['stage']:return {'reason':'same_stage_unique','stages':[a['stage'],b['stage']]}
    if (a['stage'],b['stage']) in dependency_paths:return {'reason':'positive_duration_dependency_path','path':dependency_paths[a['stage'],b['stage']]}
    if (b['stage'],a['stage']) in dependency_paths:return {'reason':'positive_duration_dependency_path','path':dependency_paths[b['stage'],a['stage']]}
    if a['unit']==b['unit']:return {'reason':'unit_mutex','unit':a['unit']}
    if a['shared']==b['shared'] and a['unit']!=b['unit']:return {'reason':'shared_device_equality','shared':a['shared'],'units':[a['unit'],b['unit']]}
    return None

def classify(state,domains,support,dependency_paths):
    required=[(d,o) for d,o in zip(domains,state) if o!='L']
    choices=[support[d].get(o,[]) for d,o in required]
    size=1
    for rows in choices:size*=len(rows)
    if size>CAP:return dict(status='UNKNOWN_CAP',support_product=size)
    exclusions=[]
    for chosen in product(*choices):
        rejected=None
        for a,b in combinations(chosen,2):
            rejected=conflict(a,b,dependency_paths)
            if rejected:break
        if rejected is None:return dict(status='UNKNOWN_SUPPORT_EXISTS',support_product=size,
             compatible_witness=[dict(stage=x['stage'],unit=x['unit']) for x in chosen])
        exclusions.append(dict(witness=[[x['stage'],x['unit']] for x in chosen],**rejected))
    return dict(status='PROVED_UNREACHABLE',required_domains=[[d,o] for d,o in required],
                support_product=size,exhaustive_rejections=exclusions)

def independently_replay(proof,state,domains,support,scene):
    """Exhaustively check each recorded obstruction directly, not by classify/conflict."""
    choices=[support[d].get(o,[]) for d,o in zip(domains,state) if o!='L']
    tuples=list(product(*choices));assert len(tuples)==proof['support_product']
    assert len(proof['exhaustive_rejections'])==len(tuples)
    edges={tuple(e) for e in scene['dependencies']}
    for chosen,record in zip(tuples,proof['exhaustive_rejections']):
        assert [[x['stage'],x['unit']] for x in chosen]==record['witness']
        if record['reason']=='positive_duration_dependency_path':
            path=record['path'];assert len(path)>=2
            assert all((a,b) in edges for a,b in zip(path,path[1:]))
            assert path[0] in [x['stage'] for x in chosen] and path[-1] in [x['stage'] for x in chosen]
        elif record['reason']=='same_stage_unique':assert len({x['stage'] for x in chosen})<len(chosen)
        elif record['reason']=='unit_mutex':assert sum(x['unit']==record['unit'] for x in chosen)>=2
        elif record['reason']=='shared_device_equality':
            assert len({x['unit'] for x in chosen if x['shared']==record['shared']})>=2
        else:raise AssertionError('unknown proof rule')
    return True

def freeze():
    names=['plan.json','input_instance.json','input_config.json','execution/on/options.json','execution/on/variable_names.json','execution/on/result.json']
    records={str((ARCH/n).relative_to(REPO)):sha(ARCH/n) for n in names}
    commit='7631a16d420fbd8711af1e6cb2f35bc03cf9700d'
    for path,dig in records.items():
        b=subprocess.check_output(['git','show',commit+':'+path],cwd='/workspace/paper_publish_autol_lp_20261111')
        assert hashlib.sha256(b).hexdigest()==dig,path
    save('plan.json',dict(frozen_utc=now(),commit=commit,input_sha256=records,script_sha256=sha(Path(__file__)),
        per_state_group_product_cap=CAP,total_candidate_group_product_cap=TOTAL_CAP,
        wall_cap_seconds=90,scientific_solver_calls=0,new_thermal_calls=0,
        scope='Local finite necessary-support classification, not complete actual-R1 schedule search; survivors unknown'))

def main():
    start=time.monotonic();started=now();plan=read(HERE/'plan.json')
    assert sha(Path(__file__))==plan['script_sha256']
    for path,dig in plan['input_sha256'].items():assert sha(REPO/path)==dig
    instance=read(ARCH/'input_instance.json');options=read(ARCH/'execution/on/options.json')
    assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
    domains=list(instance['platform']['domains']);records=[];summaries=[];products=0;certificates=0
    w_names=read(ARCH/'execution/on/variable_names.json')
    archived={}
    for name in w_names:
        if name.startswith('w:'):
            _,sid,l,state=name.split(':',3);archived.setdefault((sid,int(l)),set()).add(tuple(ast.literal_eval(state)))
    for scene in instance['scenarios']:
        sid=scene['id'];local=[o for o in options if o['scenario_id']==sid]
        events=sorted({F(0),F(instance['window_ms'])}|{F(o[k]) for o in local for k in ['start_ms','end_ms']})
        dependency_paths=paths(scene)
        for l,(left,right) in enumerate(zip(events,events[1:])):
            assert time.monotonic()-start<90
            support=support_groups(scene,options,left,right,domains)
            states=list(product(*(sorted({'L'}|set(support[d])) for d in domains)))
            assert set(states)==archived[sid,l]
            result=[]
            for state in states:
                p=classify(state,domains,support,dependency_paths);products+=p['support_product']
                assert products<=TOTAL_CAP
                if p['status']=='PROVED_UNREACHABLE':
                    assert independently_replay(p,state,domains,support,scene);certificates+=1
                result.append(dict(state=state,**p))
            count=Counter(r['status'] for r in result)
            summaries.append(dict(scene=sid,interval=l,left_ms=str(left),right_ms=str(right),
                blocks_before=len(states),proved_unreachable=count['PROVED_UNREACHABLE'],
                unknown_support_exists=count['UNKNOWN_SUPPORT_EXISTS'],unknown_cap=count['UNKNOWN_CAP']))
            records.append(dict(scene=sid,interval=l,left_ms=str(left),right_ms=str(right),domain_order=domains,
                supports=support,states=result))
    totals={k:sum(r[k] for r in summaries) for k in ['blocks_before','proved_unreachable','unknown_support_exists','unknown_cap']}
    assert totals['blocks_before']==9798
    save('certificates.json',records)
    with (HERE/'per_interval.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    per_scene={s['id']:{k:sum(r[k] for r in summaries if r['scene']==s['id']) for k in totals} for s in instance['scenarios']}
    save('result.json',dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-start,totals=totals,
        per_scene=per_scene,group_products_considered=products,proofs_independently_replayed=certificates,
        variables_potentially_removable=totals['proved_unreachable'],electrothermal_rows_potentially_removable=10*totals['proved_unreachable'],
        solver_calls=0,model_builds=0,thermal_calls=0,original_complete_schedule_searches=0,
        caveat='Only necessary local witness conditions used. No structural/thermal sufficiency or global reachability claimed for survivors. Full numerical MILP LP relaxation need not be preserved.',
        environment=dict(python=sys.version,platform=sys.platform)))
    print(json.dumps(dict(totals=totals,per_scene=per_scene,products=products,wall_s=time.monotonic()-start),indent=2))

if __name__=='__main__':
    if sys.argv[1:] == ['freeze']:freeze()
    else:main()
