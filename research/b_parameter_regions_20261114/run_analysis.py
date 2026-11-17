"""Bounded deterministic sensitivity experiment; no post-result parameter search."""
import csv,hashlib,json,platform,time
from pathlib import Path
import numpy as np
from model import catalogue,evaluate

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
CFG=json.loads((ROOT/'design.json').read_text());TEMPS=np.array(CFG['temperatures_C']);ACTIONS=catalogue();IDS=[a['id'] for a in ACTIONS]
TIE=CFG['tie_J'];NT=len(TEMPS)

def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def writecsv(name,records):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def threshold_actions(policy,offset=0.):
    return np.where(TEMPS+offset<policy['threshold_C'],policy['left_index'],policy['right_index'])

def policy_dict(cut,left,right,mean):
    threshold=float(TEMPS[0]-100) if cut==0 else float(TEMPS[-1]+100) if cut==NT else float((TEMPS[cut-1]+TEMPS[cut])/2)
    return dict(cut_index=cut,threshold_C=threshold,left_index=int(left),right_index=int(right),left_id=IDS[left],right_id=IDS[right],mean_J=float(mean),constant=(cut in [0,NT] or left==right))

def solve_policies(e,f):
    m=np.where(f,e,np.inf)
    means=m.mean(axis=1);fixed=int(np.argmin(means));ef=float(means[fixed])
    assert np.isfinite(ef),'No all-temperature feasible fixed policy'
    oracle=m.min(axis=0);bestidx=m.argmin(axis=0);eo=float(oracle.mean())
    bestsq=None
    for mode in ['on','off']:
        s=IDS.index('B-211-100-'+mode);q=IDS.index('B-22-11-'+mode)
        for cut in range(NT+1):
            for left,right in [(s,q),(q,s)]:
                value=(m[left,:cut].sum()+m[right,cut:].sum())/NT
                if bestsq is None or value<bestsq['mean_J']-1e-14:bestsq=policy_dict(cut,left,right,value)
    prefix=np.concatenate([np.zeros((len(IDS),1)),np.cumsum(m,axis=1)],axis=1)
    suffix=np.concatenate([np.cumsum(m[:,::-1],axis=1)[:,::-1],np.zeros((len(IDS),1))],axis=1)
    besttwo=None
    for cut in range(NT+1):
        left=int(prefix[:,cut].argmin());right=int(suffix[:,cut].argmin())
        value=(prefix[left,cut]+suffix[right,cut])/NT
        if besttwo is None or value<besttwo['mean_J']-1e-14:besttwo=policy_dict(cut,left,right,value)
    regret=np.where(f,(e-oracle[None,:])/e,np.inf)
    rb=regret.max(axis=1);robust_fixed=int(rb.argmin())
    common=np.where(np.all(m<=oracle[None,:]+TIE,axis=1))[0]
    potential=ef-eo
    return {'fixed_index':fixed,'fixed_id':IDS[fixed],'fixed_mean_J':ef,'oracle_mean_J':eo,'oracle_indices':bestidx.tolist(),'oracle_mean_gain_pct':100*potential/ef,'common_optimal_ids':[IDS[i] for i in common],'SQ':bestsq,'two_action':besttwo,'SQ_gain_pct':100*(ef-bestsq['mean_J'])/ef,'SQ_capture_pct':100*(ef-bestsq['mean_J'])/potential if potential>TIE else None,'two_action_gain_pct':100*(ef-besttwo['mean_J'])/ef,'two_action_capture_pct':100*(ef-besttwo['mean_J'])/potential if potential>TIE else None,'two_action_residual_pctpoint':100*(besttwo['mean_J']-eo)/ef,'SQ_residual_pctpoint':100*(bestsq['mean_J']-eo)/ef,'distribution_free_bound_pct':100*float(rb[robust_fixed]),'distribution_free_fixed_id':IDS[robust_fixed],'oracle_one_percent_overhead_budget_J':.99*ef-eo,'SQ_one_percent_overhead_budget_J':.99*ef-bestsq['mean_J'],'two_action_one_percent_overhead_budget_J':.99*ef-besttwo['mean_J']}

def main():
    start=time.monotonic();allresults=[];policies=[];summary_rows=[];temp_rows=[];action_rows=[]
    for ci,s in enumerate(CFG['scenarios']):
        if time.monotonic()-start>CFG['hard_scan_seconds']:raise TimeoutError('Frozen scan budget reached; completed files retained')
        r=evaluate(s,TEMPS,main_step=CFG['main_step_s'],tail_step=CFG['tail_step_s'])
        allresults.append(r)
        case_policies=[]
        for h,horizon in enumerate(['main_0.4s','common_tail_10.4s']):
            e,f=r['energy'][h],r['feasible'][h];p=solve_policies(e,f);case_policies.append(p)
            sq_s=IDS.index('B-211-100-on');sq_q=IDS.index('B-22-11-on');delta=e[sq_q]-e[sq_s]
            row={'scenario_id':s['id'],'family':s['family'],'horizon':horizon,**{k:v for k,v in s.items() if k not in ['id','family']},'fixed_id':p['fixed_id'],'fixed_mean_J':p['fixed_mean_J'],'oracle_mean_J':p['oracle_mean_J'],'oracle_gain_pct':p['oracle_mean_gain_pct'],'SQ_gain_pct':p['SQ_gain_pct'],'SQ_capture_pct':p['SQ_capture_pct'],'SQ_threshold_C':p['SQ']['threshold_C'],'SQ_left':p['SQ']['left_id'],'SQ_right':p['SQ']['right_id'],'two_action_gain_pct':p['two_action_gain_pct'],'two_action_capture_pct':p['two_action_capture_pct'],'two_action_threshold_C':p['two_action']['threshold_C'],'two_action_left':p['two_action']['left_id'],'two_action_right':p['two_action']['right_id'],'two_action_residual_pctpoint':p['two_action_residual_pctpoint'],'SQ_residual_pctpoint':p['SQ_residual_pctpoint'],'distribution_free_bound_pct':p['distribution_free_bound_pct'],'oracle_one_percent_overhead_budget_J':p['oracle_one_percent_overhead_budget_J'],'SQ_one_percent_overhead_budget_J':p['SQ_one_percent_overhead_budget_J'],'two_action_one_percent_overhead_budget_J':p['two_action_one_percent_overhead_budget_J'],'common_optimal_count':len(p['common_optimal_ids']),'SQ_delta_min_J':float(delta.min()),'SQ_delta_max_J':float(delta.max()),'SQ_sign_flip':bool(delta.min()<-TIE and delta.max()>TIE),'infeasible_action_states':int((~f).sum()),'accounting_error_J':r['accounting_error_J']}
            summary_rows.append(row)
            for ti,T in enumerate(TEMPS):
                oi=p['oracle_indices'][ti];si=int(threshold_actions(p['SQ'])[ti]);bi=int(threshold_actions(p['two_action'])[ti])
                temp_rows.append({'scenario_id':s['id'],'horizon':horizon,'initial_GPU_C':T,'initial_CPU_C':T,'fixed_id':p['fixed_id'],'fixed_J':float(e[p['fixed_index'],ti]),'oracle_id':IDS[oi],'oracle_J':float(e[oi,ti]),'SQ_id':IDS[si],'SQ_J':float(e[si,ti]),'two_action_id':IDS[bi],'two_action_J':float(e[bi,ti]),'immediate_DPM_on_J':float(e[IDS.index('B-1111-0000-on'),ti]),'immediate_DPM_off_J':float(e[IDS.index('B-1111-0000-off'),ti]),'S_J':float(e[sq_s,ti]),'Q_J':float(e[sq_q,ti]),'Q_minus_S_J':float(delta[ti]),'oracle_peak_C':float(r['peak'][h,oi,ti]),'oracle_base_J':float(r['components'][h,oi,ti,0]),'oracle_dynamic_J':float(r['components'][h,oi,ti,1]),'oracle_leak_J':float(r['components'][h,oi,ti,2]),'oracle_wake_J':float(r['components'][h,oi,ti,3])})
            for ai,a in enumerate(ACTIONS):
                action_rows.append({'scenario_id':s['id'],'horizon':horizon,'action_id':a['id'],'feasible_temperatures':int(f[ai].sum()),'mean_J_if_all_feasible':float(e[ai].mean()) if f[ai].all() else None,'min_J':float(e[ai].min()),'max_J':float(e[ai].max())})
        policies.append({'scenario_id':s['id'],'horizons':case_policies})
        if ci%5==0 or ci==66:print(json.dumps({'completed':ci+1,'total':67,'elapsed_s':round(time.monotonic()-start,2)}),flush=True)
    energy=np.stack([r['energy'] for r in allresults]);feasible=np.stack([r['feasible'] for r in allresults]);peak=np.stack([r['peak'] for r in allresults]);components=np.stack([r['components'] for r in allresults])
    np.savez_compressed(OUT/'all_candidate_arrays.npz',energy=energy,feasible=feasible,peak=peak,components=components,temperatures=TEMPS)
    writecsv('scenario_summary.csv',summary_rows);writecsv('temperature_results.csv',temp_rows);writecsv('all_action_aggregates.csv',action_rows)
    dump('policies.json',policies);dump('catalogue.json',ACTIONS)

    # Frozen nominal policy deployment to declared unknown-parameter scenarios.
    ni=next(i for i,s in enumerate(CFG['scenarios']) if s['id']==CFG['nominal_id'])
    transfer=[]
    for ci,s in enumerate(CFG['scenarios']):
        if s['family'] not in ['uncertainty_corners','one_at_a_time'] and ci!=ni:continue
        for h,horizon in enumerate(['main_0.4s','common_tail_10.4s']):
            base=policies[ci]['horizons'][h]['fixed_mean_J'];nomp=policies[ni]['horizons'][h]
            for name in ['fixed','SQ','two_action']:
                for offset in ([0.] if name=='fixed' else CFG['observation_offsets_C']):
                    inds=np.full(NT,nomp['fixed_index']) if name=='fixed' else threshold_actions(nomp[name],offset)
                    good=feasible[ci,h,inds,np.arange(NT)]
                    actual=float(energy[ci,h,inds,np.arange(NT)].mean()) if good.all() else None
                    transfer.append({'scenario_id':s['id'],'family':s['family'],'horizon':horizon,'nominal_policy':name,'observed_temperature_offset_C':offset,'infeasible_states':int((~good).sum()),'actual_mean_J':actual,'true_parameter_best_fixed_J':base,'gain_vs_true_best_fixed_pct':100*(base-actual)/base if actual is not None else None})
    writecsv('frozen_policy_transfer.csv',transfer)
    nominal=CFG['scenarios'][ni]
    rf=evaluate(nominal,TEMPS,main_step=CFG['main_step_s'],tail_step=CFG['tail_step_s'],cpu_fixed=40.)
    np.savez_compressed(OUT/'cpu_fixed40_arrays.npz',**{k:rf[k] for k in ['energy','feasible','peak','components']})
    dump('cpu_fixed40_policy_summary.json',[solve_policies(rf['energy'][h],rf['feasible'][h]) for h in [0,1]])
    # Reproducibility metadata excludes wall time from scientific summaries.
    env={'python':platform.python_version(),'numpy':np.__version__,'elapsed_s':time.monotonic()-start,'case_count':67,'temperature_count':NT,'action_count':len(ACTIONS),'main_candidate_state_evaluations':67*NT*len(ACTIONS),'additional_cpu_fixed_state_evaluations':NT*len(ACTIONS),'max_accounting_error_J':max(r['accounting_error_J'] for r in allresults),'status':'COMPLETE','files_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['PROTOCOL.md','design.json','nominal_synthetic_parameters.json','model.py','run_analysis.py']}}
    dump('run_environment.json',env)
    print(json.dumps(env),flush=True)

if __name__=='__main__':main()
