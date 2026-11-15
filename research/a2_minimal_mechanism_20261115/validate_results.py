"""Post-run numerical checks; no parameter retuning or new optimization domain."""
from pathlib import Path
import argparse, csv, json, hashlib, importlib.metadata
import numpy as np
from model import pack, cycle, sequence, initial_states, ACTIONS

ROOT = Path(__file__).resolve().parent

def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

def main(replay=None):
    out = ROOT/'results'
    params = {x['case']: pack({k: float(v) for k,v in x.items() if k!='case'})
              for x in read_csv(out/'parameters.csv')}
    policies = json.loads((out/'policy_comparison.json').read_text(encoding='utf-8'))
    affected = sorted({x['case'] for x in policies if len(set(x['argmin_by_state']))>1})
    numerical = []; diagnostic = []; ablations = []
    # These IDs are selected after inspecting argmin changes, for diagnosis only.
    for cid in affected:
        p = params[cid]; states, _ = initial_states(p)
        for s, st in enumerate(states):
            for a in range(9):
                v = cycle(p,*st,a,True,True,False,.001)
                fine = cycle(p,*st,a,True,True,False,.00025)
                no_leak_feedback = cycle(p,*st,a,False,True,False,.001)
                numerical.append(dict(case=cid,state=s,action=ACTIONS[a],E_J=v[0],E_quarter_J=fine[0],error_J=abs(v[0]-fine[0])))
                ablations.append(dict(case=cid,state=s,action=ACTIONS[a],temperature_independent_leak_J=no_leak_feedback[0]))
        pp = next(x for x in policies if x['case']==cid and x['throttle']==0)
        for a in range(10):
            arr = sequence(p, states[0], 0 if a<9 else 1, pp['threshold_C'],
                           a if a<9 else pp['below_index'], a if a<9 else pp['above_index'], 240)
            diagnostic.append(dict(case=cid,policy=ACTIONS[a] if a<9 else 'threshold',
                total_J=float(arr[:,4].sum()),all_feasible=bool(np.isfinite(arr).all() and (arr[:,23]==1).all()),
                action_switches=int((arr[1:,3]!=arr[:-1,3]).sum()),peak_Tj_C=float(arr[:,12].max()),
                throttle_busy_s=float(arr[:,17].sum()),last_cycle_delta_C=float(abs(arr[-1,14:16]-arr[-2,14:16]).max())))
    write_csv(out/'posthoc_convergence.csv', numerical)
    write_csv(out/'posthoc_periodic.csv', diagnostic)
    write_csv(out/'posthoc_leakage_ablation.csv', ablations)
    max_error = max(x['error_J'] for x in numerical)
    assert max_error < 1e-8
    # Artificial boundary UNIT TEST: not an admitted initial state, no evidence claim.
    p = params['nominal']
    active = cycle(p,87.,70.,0,True,True,True)
    inactive = cycle(p,87.,70.,0,True,True,False)
    assert active[13]>0 and max(active[6:8])>max(inactive[6:8])
    raw = read_csv(out/'single_window.csv')
    for pp in policies:
        records=[x for x in raw if x['case']==pp['case'] and int(x['throttle'])==pp['throttle']]
        E=np.array([[float(next(x['energy_J'] for x in records if int(x['state'])==s and x['action']==a)) for a in ACTIONS] for s in range(5)])
        assert all(int(x['feasible']) for x in records)
        oracle=float(np.min(E[[1,3]],axis=1).mean())
        fixed=float(E[[1,3],pp['fixed_index']].mean())
        assert abs(oracle-pp['oracle_test_J'])<1e-10 and abs(fixed-pp['fixed_test_J'])<1e-10
    tested=[x for x in policies if x['case']!='nominal' and x['throttle']==0]
    overhead=[]
    for cost in [0.,1e-5,1e-4,1e-3]:
        for label in ['threshold','oracle']:
            gains=[(1-(x[f'{label}_test_J']+cost)/x['fixed_test_J'])*100 for x in tested]
            overhead.append(dict(policy=label,incremental_overhead_J=cost,max_net_gain_pct=max(gains),min_net_gain_pct=min(gains)))
    write_csv(out/'overhead_sensitivity.csv',overhead)
    replay_checks=[]
    if replay:
        # Only original-run outputs; excludes this post-hoc validation's files.
        names=['parameters.csv','initial_states.csv','single_window.csv','policy_comparison.json','excluded_cases.json',
               'ablation.csv','ablation_policies.json','sensitivity.csv','periodic.csv','nominal_trajectories.csv','numerical_convergence.csv']
        for name in names:
            same=(out/name).read_bytes()==(replay/name).read_bytes()
            assert same, name
            replay_checks.append(dict(file=name,byte_identical=same,sha256=hashlib.sha256((out/name).read_bytes()).hexdigest()))
        a=json.loads((out/'summary.json').read_text()); b=json.loads((replay/'summary.json').read_text())
        a.pop('wall_seconds'); b.pop('wall_seconds'); assert a==b
        replay_checks.append(dict(file='summary.json',identical_except_wall_seconds=True))
    result=dict(status='PASS',scope='Computational validation only; no hardware calibration',
        affected_case_selection='post-hoc: every case whose best action varies across initial states',
        affected_cases=affected,posthoc_max_numerical_error_J=max_error,
        posthoc_periodic_runs=len(diagnostic),posthoc_periodic_cycles=240,
        artificial_throttle_boundary_unit_test=dict(initial_Tj_C=87,initial_Tp_C=70,throttle_busy_s=float(active[13]),
            finish_throttled_s=float(max(active[6:8])),finish_fixed_s=float(max(inactive[6:8])),scientific_evidence=False),
        max_heldout_oracle_gain_pct=max(x['oracle_test_gain_pct'] for x in tested),
        max_heldout_threshold_gain_pct=max(x['threshold_gain_pct'] for x in tested),
        min_heldout_threshold_gain_pct=min(x['threshold_gain_pct'] for x in tested),
        replay=replay_checks,versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','numba','matplotlib']})
    (ROOT/'validation_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['replay','versions']},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--replay',type=Path); args=ap.parse_args(); main(args.replay)
