"""Independent Radau integration of eight full-window + continuation cases."""
import json, pathlib
import numpy as np
from scipy.integrate import solve_ivp
import screen as m

root=pathlib.Path(__file__).parent
rows=[json.loads(x) for x in (root/'results/all_candidates.jsonl').read_text().splitlines()]
ref={(r['id'],r['state']):r for r in rows if r['variant']=='full'}
actions={a['id']:a for a in list(m.a_actions())+list(m.b_actions())}
out=[]
for aid in ['A-10-0-6','A-10-1-6','B-211-100','B-22-11']:
    for state in ['cool','warm']:
        a=actions[aid]
        segs,_=m.schedule(a,'full')
        segs.append(m.segment(m.H,m.H+m.P['continuation_s'],awake=(1,1 if a['direction']=='A' else 0)))
        z=np.r_[m.P['initial_states_C'][state],0.]
        for s in segs:
            def rhs(t,z):
                heat,energy=m.rates(s,z[:2],'full')
                return np.r_[(-m.G@(z[:2]-m.TA)+heat)/m.C,energy.sum()]
            sol=solve_ivp(rhs,(s['start'],s['end']),z,method='Radau',rtol=1e-11,atol=1e-13,max_step=.05)
            assert sol.success
            z=sol.y[:,-1]
        out.append(dict(id=aid,state=state,radau_energy_J=float(z[2]),difference_J=float(z[2]-ref[aid,state]['extended_energy_J'])))
assert max(abs(r['difference_J']) for r in out)<1e-8
(root/'results/tail_validation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
