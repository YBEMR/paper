"""Independent saved-bound check. No planning, thermal simulation or fixes."""
import csv, json, pathlib, sys
from decimal import Decimal as D
import h5py
import numpy as np

p=pathlib.Path(sys.argv[1]);root=pathlib.Path(__file__).resolve().parents[2]
raw=json.loads((root/'research/stage53_design/inputs_v1.json').read_text(encoding='utf8'),parse_float=D)
packages={x['package_id']:x for x in raw['packages']};sysdata=raw['system']
base=sum(D(sysdata[x]) for x in ('idle_cpu_total_W','idle_npu_W','external_W'))*D(sysdata['window_s'])
rows=[]
for i,c in enumerate(raw['cases'],1):
    deadline=D(c['requests'][0]['deadline_s']);infeasible=deadline<D('.005')
    if deadline==D('.006'):
        # Report60 independently checked low-frequency exclusion; temperature
        # does not weaken its no-heat lower bound. Safe output is checked separately.
        expected=D('.038') if c['package_id']=='P_low' else D('.044')
        basis='report60_D6_noheat_lower_bound'
    else:
        modes=packages[c['package_id']]['modes']
        expected=base+sum(min(D(m['duration_s'])*D(m['active_increment_W']) for m in modes if m['stage_type']==s)
                          for req in c['requests'] for s in req['stage_types'])
        basis='independent_Decimal_stage_energy_lower_bound'
    for j in range(1,5):
        with h5py.File(p/f'case{i:02d}_method{j:02d}.mat','r') as a:
            r=a['r'];L=float(r['lower_J'][0,0]);U=float(r['upper_J'][0,0]);trace=r['bound_trace'][:].T
            if infeasible:
                ok=bool(r['grid_infeasible_proved'][0,0]) and np.isinf(L) and np.isinf(U)
                basis='isolated_chain_5ms_exceeds_4ms'
            else:
                units=float(expected*16000)
                finite_l=trace[:,1][np.isfinite(trace[:,1])];finite_u=trace[:,2][np.isfinite(trace[:,2])]
                ok=bool(np.all(finite_l<=units) and np.all(np.diff(finite_l)>=0)
                        and np.all(finite_u>=units) and np.all(np.diff(finite_u)<=0)
                        and abs(L-float(expected))<1e-12 and abs(U-float(expected))<1e-12)
            rows.append([c['case_id'],j,basis,str(expected) if not infeasible else 'infeasible',ok])
with (p/'independent_bound_checks.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.writer(f);w.writerow(['case_id','variant_index','basis','known_lower_J','passed']);w.writerows(rows)
assert all(x[-1] for x in rows),[x for x in rows if not x[-1]]
print(f'Independent bound checks: {len(rows)}/{len(rows)}; saved evidence only')
