"""Post-result subset audit. Reads frozen results; performs NO simulation or fitting."""
import json,csv
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;O=R/'results'
P=json.loads((R/'design.json').read_text());S=json.loads((O/'scenario_summary.json').read_text())
A=np.load(O/'all_candidate_arrays.npz');seq=A['sequences']
one=(seq[:,0]==seq[:,1])|(seq[:,1]==seq[:,2])
assert int(one.sum())==496
nominal=int(np.flatnonzero(np.all(seq==[15,10,10],axis=1))[0]);rows=[]
for s in S:
    sid=s['scenario'];pre=sid+'_hardware__';e=A[pre+'energy'];f=A[pre+'feasible'];indices=np.flatnonzero(one&f);j=int(indices[np.argmin(e[indices])]);best=float(e[j]);oracle=float(e[f].min())
    assert abs(best-oracle)<1e-9
    rows.append({'scenario':sid,'one_switch_catalogue_size':int(one.sum()),'feasible_one_switch':int((one&f).sum()),'best_sequence':seq[j].tolist(),'energy':best,'gain_vs_best_constant_pct':s['catalogue_gain_pct'],'lookahead_gain_vs_one_switch_pct':100*(best-oracle)/best,'nominal_frozen_sequence_feasible':bool(f[nominal]),'nominal_frozen_sequence_energy':float(e[nominal]),'nominal_frozen_regret_pct':float(100*(e[nominal]-best)/best) if f[nominal] else None,'extra_energy_budget_for_1pct_over_one_switch':-.01*best})
g=np.array(P['Genv'])*1.5;gc=P['Gcouple'];leak=np.array(P['leak_coefficient']);K=np.diag(g+gc-leak)+np.array([[0,-gc],[-gc,0]])
pmax=np.array(P['idle_power'])+P['active_base']+np.array(P['dynamic_coefficient']);steady=np.linalg.solve(K,pmax)
# Before any hardware trip, at most one requested-frequency change per job.
# Stable Metzler RC propagator is infinity-norm nonexpansive (positive row dissipation).
impulse_bound=12*P['frequency_transition_energy']/min(P['C']);upper=steady+impulse_bound
assert np.all(np.array(P['scenarios'][0]['initial'])<=steady) and np.all(upper<P['trip'])
gx=P['Genv'][0]+gc-leak[0];lower_eq=pmax[0]/gx;tau=P['C'][0]/gx
t_hit=tau*np.log((lower_eq-.95)/(lower_eq-P['trip'][0]))
out={'status':'POSTHOC_STRUCTURAL_AUDIT_NO_NEW_TRAJECTORIES','selection_rule':'At most one change of template, including all constants; entire 496-member subset, not just observed winners. Chosen after seeing scan; not prospective validation.','rows':rows,'all_scenarios_match_full_catalogue':True,'same_nominal_sequence_feasible_count':sum(x['nominal_frozen_sequence_feasible'] for x in rows),'analytic_bounds':{'strong_cooling_steady_full_busy':steady.tolist(),'pre_first_trip_impulse_bound':impulse_bound,'strong_cooling_upper':upper.tolist(),'nominal_X_continuous_high_lower_equilibrium':lower_eq,'nominal_X_lower_tau':tau,'hot_X_continuous_high_time_to_trip_lower_model':float(t_hit),'hit_scope':'Continuous busy-high X from x=.95 and nonnegative Y, excluding switch pause. Hardware adds sampling/confirmation; not a DAG completion-time proof.'}}
(O/'structural_audit.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
with (O/'structural_audit.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps(out,indent=2))
