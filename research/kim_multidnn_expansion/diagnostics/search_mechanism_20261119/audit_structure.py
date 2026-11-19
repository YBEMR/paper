"""Static exact-input classes plus bounded E0 checks; never call a search."""
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
import numpy as np
from scipy.linalg import expm

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT/'research/kim_scene_dvfs_admission'))
import scene_events as events
from profiles import build_chains
sys.path.insert(0, str(ROOT/'research/kim_safety_repair_audit'))
from design import make_scenes, cases
frozen = json.loads((EXP/'expanded_input.json').read_text(encoding='utf-8'))
events.FROZEN = frozen
start = perf_counter()
def read(p):
    return json.loads(p.read_text(encoding='utf-8'))
def key(obj):
    return json.dumps(obj, sort_keys=True, separators=(',',':'))
def write(name,obj):
    (HERE/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

chains = {(d,o):build_chains(events.PLATFORM,frozen,d,o)
          for d in frozen['deployments'] for o in events.OPPS}
summaries, maps, positivity, e0 = [], [], [], []
scheduling_calls = thermal_calls = 0
for case in [c for c in cases() if c['ambient']==25]:
    scenes = make_scenes(case)
    old = read(EXP/'raw/expanded'/case['id']/'result.json')
    observed = old['completed_deployments']
    with (EXP/'raw/expanded'/case['id']/'local.csv').open(encoding='utf-8',newline='') as stream:
        local = {(r['deployment'],int(r['scene']),r['opp']):r for r in csv.DictReader(stream)}
    for index, scene in enumerate(scenes):
        active = sorted(set(q.app for q in scene.requests))
        full_groups, seen_groups, feasible_groups = {}, {}, {}
        for d in frozen['deployments']:
            for o in events.OPPS:
                signature = key(dict(requests=[asdict(q) for q in scene.requests],
                    window_ns=scene.duration_ns, service_end_local_ns=scene.service_end_ns-scene.start_ns,
                    active_chains={a:[asdict(s) for s in chains[d,o][a]] for a in active},
                    thermal_kwargs=events.thermal_kwargs(events.PLATFORM,o,25,True,'base')))
                digest = hashlib.sha256(signature.encode()).hexdigest()
                full_groups.setdefault(digest,[]).append((d,o))
                if d in observed:
                    seen_groups.setdefault(digest,[]).append((d,o))
                    if local[d,index,o]['deadline_ok']=='True':
                        feasible_groups.setdefault(digest,[]).append((d,o))
        row = dict(case=case['id'],index=index,scene=scene.name,active_apps=active,
            full_actions=len(frozen['deployments'])*27,full_exact_classes=len(full_groups),
            observed_actions=len(observed)*27,observed_exact_classes=len(seen_groups),
            observed_feasible_actions=sum(len(g) for g in feasible_groups.values()),
            observed_feasible_exact_classes=len(feasible_groups))
        summaries.append(row)
        maps.append(dict(case=case['id'],index=index,scene=scene.name,
                         full_groups=full_groups,observed_feasible_groups=feasible_groups))
        # One identical-input pair per scene, only in forward_flat (8 schedules).
        if case['id']=='forward_flat_25C':
            pair = next(g[:2] for g in feasible_groups.values()
                        if len(g)>1 and g[0][1]=='LLL') if any(
                            len(g)>1 and g[0][1]=='LLL' for g in feasible_groups.values()) else next(
                            g[:2] for g in feasible_groups.values() if len(g)>1)
            schedules = [events.time_scene(events.PLATFORM,scene,d,o) for d,o in pair]
            scheduling_calls += 2
            a,b = schedules
            assert a.rows==b.rows and a.completions_ns==b.completions_ns
            for field in ('start_ns','duration_ns','active_w','transfer_w'):
                assert np.array_equal(getattr(a,field),getattr(b,field)), field
            assert a.deadline_feasible==b.deadline_feasible
            e0.append(dict(scene=scene.name,pair=pair,rows=len(a.rows),
                           events=len(a.duration_ns),bitwise_equal=True))
            # Only first scene: identical trajectories + ordered hotter entry.
            if index==0:
                kw=events.thermal_kwargs(events.PLATFORM,pair[0][1],25,True,'base')
                cold=events.evaluate_thermal(a.duration_ns*1e-9,a.active_w,transfer_W=a.transfer_w,**kw)
                equal=events.evaluate_thermal(b.duration_ns*1e-9,b.active_w,transfer_W=b.transfer_w,**kw)
                hotkw=dict(kw,initial_C=(np.array(kw['initial_C'])+np.array([1.,2.,3.,4.])).tolist())
                hot=events.evaluate_thermal(a.duration_ns*1e-9,a.active_w,transfer_W=a.transfer_w,**hotkw)
                thermal_calls+=3
                assert cold==equal
                assert hot['energy_J']>=cold['energy_J']
                assert np.all(np.array(hot['final_C'])>=np.array(cold['final_C']))
                e0[-1]['thermal_equal']=True
                e0[-1]['hotter_entry_energy_difference_j']=hot['energy_J']-cold['energy_J']
        for opp in events.OPPS:
            kw=events.thermal_kwargs(events.PLATFORM,opp,25,True,'base')
            C=np.asarray(kw['capacity_J_K'])
            S=np.asarray(kw['slope_W_K'])
            G=np.asarray(kw['conductance_W_K'])
            A=(np.diag(S)-G)/C[:,None]
            off=A.copy()
            np.fill_diagonal(off,0)
            assert np.min(off)>=0 and np.min(S)>=0
            h=scene.duration_ns*1e-9
            F=expm(A*h)
            # Integral exp(A*t) = solve(A,F-I); stable A is invertible.
            w=S@np.linalg.solve(A,F-np.eye(4))
            assert np.min(F)>=-1e-12 and np.min(w)>=-1e-12
            positivity.append(dict(case=case['id'],index=index,opp=opp,
                min_F=float(F.min()),min_w=float(w.min()),max_eigenvalue=float(np.linalg.eigvals(A).real.max())))
    print(json.dumps([r for r in summaries if r['case']==case['id']]),flush=True)

# Count only observed nonidentical saved SAFE prefixes, same fixed deployment/boundary.
dominance_pairs=[]
eligible_pairs=0
for case in [c for c in cases() if c['ambient']==25]:
    rows=read(EXP/'raw/expanded'/case['id']/'deployments.json')
    for row in rows:
        choices=[row[k] for k in ('independent','joint') if row[k] is not None]
        if len(choices)!=2:
            continue
        for depth in (1,2,3):
            a,b=choices
            if a['opps'][:depth]==b['opps'][:depth]:
                continue
            prefix=[x['physical']['scene_rows'][:depth] for x in choices]
            if any(len(rs)!=depth or any(r['thermal_status']!='SAFE' for r in rs) for rs in prefix):
                continue
            eligible_pairs+=1
            states=[(sum(r['energy_j'] for r in rs),np.array(rs[-1]['final_c'])) for rs in prefix]
            for u,v in ((0,1),(1,0)):
                eu,tu=states[u]
                ev,tv=states[v]
                if eu<=ev and np.all(tu<=tv):
                    dominance_pairs.append(dict(case=case['id'],deployment=row['deployment'],depth=depth,
                        dominating=choices[u]['opps'][:depth],dominated=choices[v]['opps'][:depth],
                        energy_advantage_j=ev-eu,temperature_advantage_c=(tv-tu).tolist()))
write('equivalence_counts.json',summaries)
write('equivalence_classes.json',maps)
write('monotonicity_e0.json',dict(positivity=positivity,e0=e0,
    saved_distinct_safe_prefix_pairs=eligible_pairs,saved_dominance_pairs=dominance_pairs,
    scheduling_calls=scheduling_calls,thermal_integrations=thermal_calls,
    full_search_calls=0,wall_s=perf_counter()-start))
print(json.dumps(dict(PASS=True,scheduling_calls=scheduling_calls,thermal_integrations=thermal_calls,
    distinct_saved_safe_prefix_pairs=eligible_pairs,dominance_pairs=len(dominance_pairs),
    wall_s=perf_counter()-start)),flush=True)
