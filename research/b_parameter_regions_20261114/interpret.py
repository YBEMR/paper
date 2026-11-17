"""Analytic parameter regions and descriptive summaries; no parameter refitting."""
import csv,itertools,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
cfg=json.loads((ROOT/'design.json').read_text());raw=np.load(OUT/'all_candidate_arrays.npz',allow_pickle=False);temps=raw['temperatures'];actions=json.loads((OUT/'catalogue.json').read_text());ids=[a['id'] for a in actions];policies=json.loads((OUT/'policies.json').read_text());scenarios=cfg['scenarios'];nom=next(i for i,s in enumerate(scenarios) if s['id']==cfg['nominal_id'])

def writecsv(name,records):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def analytic_terms(s):
    t2=.065*s['b2_time_scale'];p2=5*s['b2_power_scale'];enabled=s['sleepcontrast']>0
    wake=.001*s['wake_time_scale'] if enabled else 0
    K=t2*p2-2*.04*4+(s['wake_energy_J'] if enabled else 0)
    d=2*.04-t2-wake;A=.17*s['sleepcontrast'];B=.17*s['leak_scale']*s['sleepcontrast'];beta=.035*s['beta_scale']
    return K,d,A,B,beta

def delta(s,T):
    K,d,A,B,beta=analytic_terms(s)
    return K-d*(A+B*np.exp(beta*(T-40)))

regions=[]
for s in scenarios:
    K,d,A,B,beta=analytic_terms(s);cold=float(delta(s,25));warm=float(delta(s,75))
    if abs(cold-warm)<1e-12:region='temperature_independent_tie' if abs(cold)<1e-12 else 'temperature_independent_S' if cold>0 else 'temperature_independent_Q'
    elif min(cold,warm)>0:region='S_throughout'
    elif max(cold,warm)<0:region='Q_throughout'
    elif cold>0>warm:region='S_to_Q_crossing'
    elif cold<0<warm:region='Q_to_S_crossing'
    else:region='boundary_tie'
    threshold=40+math.log((K/d-A)/B)/beta if d!=0 and B>0 and beta>0 and (K/d-A)/B>0 else None
    regions.append({'scenario_id':s['id'],'family':s['family'],'K_J':K,'awake_time_saved_s':d,'constant_contrast_W':A,'temperature_contrast_at40_W':B,'beta_per_C':beta,'delta_at25_J':cold,'delta_at75_J':warm,'region':region,'threshold_C_if_real':threshold,'threshold_inside_25_75':threshold is not None and 25<=threshold<=75})
writecsv('analytic_regions.csv',regions)

# For fixed T, this four-primitive-variable expression is multi-affine.
# Extrema over the declared independent box occur at its 16 vertices.
corners=[s for s in scenarios if s['family']=='uncertainty_corners']
unc=[]
for T in temps:
    vals=[float(delta(s,T)) for s in corners]
    vals_noisy=[float(delta(s,T+err)) for s in corners for err in [-2,2]]
    nc=next(s for s in scenarios if s['id']==cfg['nominal_id'])
    nominal_delta=float(delta(nc,T))
    # Independent b2 energy perturbation at fixed time: an absolute 1mJ error
    # in b2 energy shifts Q-S by exactly 1mJ because Q uses one extra b2 batch.
    unc.append({'initial_temperature_C':T,'nominal_quasistatic_delta_J':nominal_delta,'exact_box_delta_min_J':min(vals),'exact_box_delta_max_J':max(vals),'box_plus_2C_delta_min_J':min(vals_noisy),'box_plus_2C_delta_max_J':max(vals_noisy),'robust_sign_on_exact_quasistatic_box':('S' if min(vals)>0 else 'Q' if max(vals)<0 else 'UNDETERMINED'),'single_batch2_energy_relative_error_to_erase_nominal_margin_pct':100*abs(nominal_delta)/.325})
writecsv('analytic_uncertainty_envelope.csv',unc)

with (OUT/'scenario_summary.csv').open() as f:rows=list(csv.DictReader(f))
with (OUT/'frozen_policy_transfer.csv').open() as f:tr=list(csv.DictReader(f))
overview={}
for h,label in enumerate(['main_0.4s','common_tail_10.4s']):
    rr=[r for r in rows if r['horizon']==label];positive=[r for r in rr if float(r['oracle_gain_pct'])>1e-7]
    nominal=policies[nom]['horizons'][h]
    overview[label]={'nominal':nominal,'max_oracle_gain_pct':max(float(r['oracle_gain_pct']) for r in rr),'max_oracle_case':max(rr,key=lambda r:float(r['oracle_gain_pct']))['scenario_id'],'max_distribution_free_grid_bound_pct':max(float(r['distribution_free_bound_pct']) for r in rr),'max_two_action_residual_pctpoint':max(float(r['two_action_residual_pctpoint']) for r in rr),'cases':len(rr),'cases_with_common_optimal_action':sum(int(r['common_optimal_count'])>0 for r in rr),'cases_with_SQ_sign_flip':sum(r['SQ_sign_flip']=='True' for r in rr),'cases_oracle_meets_1pct':sum(float(r['oracle_gain_pct'])>=1 for r in rr),'cases_any_temperature_weighting_could_meet_1pct_not_ruled_out_by_bound':sum(float(r['distribution_free_bound_pct'])>=1 for r in rr),'positive_gain_cases':len(positive),'positive_gain_cases_SQ_capture_ge95':sum(float(r['SQ_capture_pct'])>=95 for r in positive),'positive_gain_cases_two_action_capture_ge95':sum(float(r['two_action_capture_pct'])>=95 for r in positive),'all_one_percent_overhead_budgets_negative':all(float(r['oracle_one_percent_overhead_budget_J'])<0 for r in rr)}
    tt=[r for r in tr if r['horizon']==label and r['family']=='uncertainty_corners']
    transfer_summary={}
    for name in ['fixed','SQ','two_action']:
        for offset in ([0.] if name=='fixed' else cfg['observation_offsets_C']):
            subset=[r for r in tt if r['nominal_policy']==name and float(r['observed_temperature_offset_C'])==offset]
            gain=[float(r['gain_vs_true_best_fixed_pct']) for r in subset if r['gain_vs_true_best_fixed_pct']]
            transfer_summary[f'{name}_offset_{offset:g}']={'min_gain_pct':min(gain),'max_gain_pct':max(gain),'negative_cases':sum(v<0 for v in gain),'infeasible_states':sum(int(r['infeasible_states']) for r in subset)}
    overview[label]['local_box_frozen_policy_transfer']=transfer_summary
    nc=[r for r in tr if r['horizon']==label and r['scenario_id']==cfg['nominal_id'] and r['nominal_policy']!='fixed']
    overview[label]['nominal_temperature_offset_results']=[{k:r[k] for k in ['nominal_policy','observed_temperature_offset_C','gain_vs_true_best_fixed_pct']} for r in nc]

# Dynamic sign ambiguity at the very same declared 16 corners (not interval-certified).
ci=[i for i,s in enumerate(scenarios) if s['family']=='uncertainty_corners'];si=ids.index('B-211-100-on');qi=ids.index('B-22-11-on')
amb=[]
for h,label in enumerate(['main_0.4s','common_tail_10.4s']):
    for ti,T in enumerate(temps):
        vals=raw['energy'][ci,h,qi,ti]-raw['energy'][ci,h,si,ti]
        amb.append({'horizon':label,'initial_temperature_C':T,'sampled_corner_min_Q_minus_S_J':float(vals.min()),'sampled_corner_max_Q_minus_S_J':float(vals.max()),'both_signs_among_corners':bool(vals.min()<0<vals.max())})
writecsv('dynamic_corner_sign_envelope.csv',amb)
summary={'evidence_class':'CONDITIONAL_SYNTHETIC_RESULTS_NOT_AGX_CALIBRATION','overview':overview,'quasistatic_nominal_terms':dict(zip(['K_J','d_s','A_W','B_W','beta_per_C'],analytic_terms(scenarios[nom]))),'quasistatic_nominal_threshold_C':regions[nom]['threshold_C_if_real'],'quasistatic_box_sign_ambiguous_temperatures':sum(r['robust_sign_on_exact_quasistatic_box']=='UNDETERMINED' for r in unc),'dynamic_box_sign_ambiguous_temperature_horizon_pairs':sum(r['both_signs_among_corners'] for r in amb),'decision':'NO_COMPLEX_ALGORITHM_INVESTMENT_SUPPORTED_IN_TESTED_MODEL_DOMAIN','boundary':'No conclusion about all possible hardware, all temperatures, all workloads, all continuous parameter values, or unrestricted schedules.'}
(OUT/'interpretation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'quasistatic_nominal_threshold_C':summary['quasistatic_nominal_threshold_C'],'quasistatic_box_ambiguous':summary['quasistatic_box_sign_ambiguous_temperatures'],'dynamic_box_ambiguous':summary['dynamic_box_sign_ambiguous_temperature_horizon_pairs'],'main_transfer':overview['main_0.4s']['local_box_frozen_policy_transfer'],'extended_max_oracle_gain_pct':overview['common_tail_10.4s']['max_oracle_gain_pct']},indent=2))
