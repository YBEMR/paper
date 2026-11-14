"""Independent adaptive DOP853 integration and catalogue-bound checks."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from model import catalogue,schedule,P

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
cfg=json.loads((ROOT/'design.json').read_text());scenarios=cfg['scenarios'];temps=np.array(cfg['temperatures_C']);actions=catalogue();ids=[a['id'] for a in actions]
data=np.load(OUT/'all_candidate_arrays.npz',allow_pickle=False)
energy,valid=data['energy'],data['feasible']
policies=json.loads((OUT/'policies.json').read_text())
start=time.monotonic();checks=[];pairs=[]

def check(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    assert condition,name

check('shape',energy.shape==(67,2,92,21))
check('finite',np.isfinite(energy).all())
check('accounting',np.max(np.abs(data['components'].sum(axis=-1)-energy))<1e-9)
check('input_freeze',all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==sha for f,sha in json.loads((ROOT/'design_freeze.json').read_text())['files'].items()))
selected={'grid_L1_D1_W1','temperature_independent','grid_L1_D1_W10','grid_L1_D0_W1','grid_L2_D1_W0','OAT_C_scale_0.5','OAT_beta_scale_1.5','box_00','box_15'}
for h in [0,1]:
    ci=max(range(67),key=lambda i:policies[i]['horizons'][h]['oracle_mean_gain_pct']);selected.add(scenarios[ci]['id'])
for ci,s in enumerate(scenarios):
    for h in [0,1]:
        p=policies[ci]['horizons'][h];mat=np.where(valid[ci,h],energy[ci,h],np.inf)
        means=mat.mean(axis=1);oracle=mat.min(axis=0)
        check(f'{ci}/{h}/fixed',abs(means.min()-p['fixed_mean_J'])<1e-10)
        check(f'{ci}/{h}/oracle',abs(oracle.mean()-p['oracle_mean_J'])<1e-10)
        check(f'{ci}/{h}/simple_order',p['oracle_mean_J']<=p['two_action']['mean_J']+1e-10<=p['fixed_mean_J']+2e-10)
        bound=p['distribution_free_bound_pct']/100
        ri=ids.index(p['distribution_free_fixed_id'])
        check(f'{ci}/{h}/distribution_free_pointwise_inequality',np.all((1-bound)*mat[ri]<=oracle+1e-10))
        if s['id'] in ['grid_L1_D1_W1','OAT_beta_scale_1.5']:
            brute=min(float((mat[:,:cut].sum(axis=1)[:,None]+mat[:,cut:].sum(axis=1)[None,:]).min()/len(temps)) for cut in range(len(temps)+1))
            check(f'{ci}/{h}/brute_two_action_threshold',abs(brute-p['two_action']['mean_J'])<1e-10)
    if s['id'] not in selected:continue
    relevant={'B-211-100-on','B-22-11-on','B-1111-0000-on','B-1111-0000-off'}
    for h in [0,1]:
        policy=policies[ci]['horizons'][h]
        relevant.add(policy['fixed_id'])
        relevant.update(ids[i] for i in policy['oracle_indices'])
        relevant.update([policy['two_action']['left_id'],policy['two_action']['right_id']])
    for aid in sorted(relevant):
        ai=ids.index(aid);segs,_=schedule(actions[ai],s)
        for temp in [25.,50.,75.]:
            if time.monotonic()-start>300:raise TimeoutError('Numerical validation budget')
            ti=list(temps).index(temp);z=np.array([temp,temp,0.,0.]);peak=temp;out=[]
            # Construct equations independently from scalar physical parameters.
            gc=P['G_coupling_W_per_K']/s['R_scale'];g0,g1=np.array(P['G_environment_W_per_K'])/s['R_scale']
            c0,c1=np.array(P['C_J_per_K'])*s['C_scale'];l0,l1=np.array(P['leak_at_40C_W'])*s['leak_scale'];beta=P['leak_beta_per_K']*s['beta_scale']
            sleep1=P['awake_base_W'][1]-s['sleepcontrast']*(P['awake_base_W'][1]-P['sleep_base_W'][1]);gate_sleep=1-s['sleepcontrast']*(1-P['sleep_leak_factor'])
            for phase,phase_segs in enumerate([segs,[(.4,10.4,0.,0.,0.)]]):
                for lo,hi,dyn,wake,awake in phase_segs:
                    def rhs(t,x):
                        leak0=l0*np.exp(beta*(x[0]-40));leak1=l1*np.exp(beta*(x[1]-40))*(gate_sleep+(1-gate_sleep)*awake)
                        heat0=P['awake_base_W'][0]+leak0;heat1=sleep1+(P['awake_base_W'][1]-sleep1)*awake+dyn+wake+leak1
                        return [(-g0*(x[0]-s['ambient_C'])-gc*(x[0]-x[1])+heat0)/c0,(-g1*(x[1]-s['ambient_C'])-gc*(x[1]-x[0])+heat1)/c1,heat0+heat1+P['external_base_W'],leak0+leak1]
                    sol=solve_ivp(rhs,(lo,hi),z,method='DOP853',rtol=1e-11,atol=1e-13,max_step=.02 if phase==0 else .1,dense_output=True)
                    assert sol.success
                    sample=np.linspace(lo,hi,max(2,int(np.ceil((hi-lo)/(.0005 if phase==0 else .01)))+1))
                    peak=max(peak,float(sol.sol(sample)[:2].max()));z=sol.y[:,-1]
                out.append((float(z[2]),peak))
            pairs.append({'scenario_id':s['id'],'action_id':aid,'temperature_C':temp,'main_energy_difference_J':out[0][0]-energy[ci,0,ai,ti],'extended_energy_difference_J':out[1][0]-energy[ci,1,ai,ti],'main_peak_difference_C':out[0][1]-data['peak'][ci,0,ai,ti],'extended_peak_difference_C':out[1][1]-data['peak'][ci,1,ai,ti]})
        if len(pairs)%24==0:print(json.dumps({'validated_trajectories':len(pairs),'elapsed_s':round(time.monotonic()-start,2)}),flush=True)
max_e=max(abs(r[k]) for r in pairs for k in ['main_energy_difference_J','extended_energy_difference_J'])
max_t=max(abs(r[k]) for r in pairs for k in ['main_peak_difference_C','extended_peak_difference_C'])
check('adaptive_DOP853_energy_difference_below_1e-7_J',max_e<1e-7)
check('adaptive_DOP853_peak_difference_below_1e-4_C',max_t<1e-4)
zero_ids=[i for i,s in enumerate(scenarios) if s['leak_scale']==0 or s['beta_scale']==0]
check('temperature_independent_controls_energy_constant',all(np.max(np.ptp(energy[i],axis=-1))<1e-9 for i in zero_ids))
result={'status':'PASS_NUMERICAL_ONLY','checks':len(checks),'independent_DOP853_trajectories':len(pairs),'max_energy_difference_J':max_e,'max_sampled_peak_difference_C':max_t,'elapsed_s':time.monotonic()-start,'checks_detail':checks,'trajectories':pairs,'scope':'Numerical integration and finite catalogue only; no hardware validation, continuous thermal safety, or interval robustness certificate.'}
(OUT/'numerical_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['checks_detail','trajectories']}))
