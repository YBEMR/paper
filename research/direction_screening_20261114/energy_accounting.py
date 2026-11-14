"""Post-run accounting only: partition every full-model main-window joule by device phase."""
import csv
import json
import numpy as np
from scipy.integrate import solve_ivp
import screen as s

PHASES = ['compute', 'awake_idle', 'sleep', 'wake']
COMPONENTS = ['base', 'dynamic', 'leakage', 'switching']


def account(action, initial):
    segs, _ = s.schedule(action, 'full')
    z = np.r_[initial, np.zeros(16)]
    for seg in segs:
        awake = np.array(seg['awake'])
        base = s.SLEEP + (s.BASE-s.SLEEP)*awake
        gate = s.P['sleep_leak_factor'] + (1-s.P['sleep_leak_factor'])*awake
        dyn, sw = np.array(seg['dynamic']), np.array(seg['switch'])
        phases = [3 if sw[i] else 0 if dyn[i] else 2 if not awake[i] else 1 for i in range(2)]
        def rhs(t, y):
            leak = s.L*np.exp(s.BETA*(y[:2]-40))*gate
            heat = base+dyn+leak+sw
            accum = np.zeros((4,4))
            for i in range(2):
                accum[phases[i]] += [base[i],dyn[i],leak[i],sw[i]]
            return np.r_[(-s.G@(y[:2]-s.TA)+heat)/s.C,accum.ravel()]
        sol = solve_ivp(rhs,(seg['start'],seg['end']),z,method='DOP853',rtol=1e-9,atol=1e-11,max_step=.01)
        assert sol.success
        z = sol.y[:,-1]
    data = {f'{phase}_{comp}_J':float(z[2+4*i+j]) for i,phase in enumerate(PHASES) for j,comp in enumerate(COMPONENTS)}
    data.update({f'{phase}_total_J':sum(data[f'{phase}_{c}_J'] for c in COMPONENTS) for phase in PHASES})
    data['external_J'] = s.P['external_base_W']*s.H
    data['accounted_total_J'] = sum(data[f'{p}_total_J'] for p in PHASES)+data['external_J']
    return data


if __name__ == '__main__':
    raw = [json.loads(x) for x in (s.ROOT/'results/all_candidates.jsonl').read_text().splitlines()]
    actions = {x['id']:x for x in json.loads((s.ROOT/'results/actions.json').read_text())}
    rows = []
    for r in raw:
        if r['variant'] != 'full': continue
        x = dict(id=r['id'],direction=r['direction'],state=r['state'],**account(actions[r['id']],s.P['initial_states_C'][r['state']]))
        x['difference_from_original_J'] = x['accounted_total_J']-r['energy_J']
        rows.append(x)
    error = max(abs(x['difference_from_original_J']) for x in rows)
    assert error < 1e-8
    with (s.ROOT/'results/energy_accounting.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (s.ROOT/'results/energy_accounting_check.json').write_text(json.dumps(dict(rows=len(rows),max_abs_total_difference_J=error,description='Post-run disjoint device-phase accounting; same full model and parameters, no new conditions.'),indent=2),encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),max_abs_total_difference_J=error)))
