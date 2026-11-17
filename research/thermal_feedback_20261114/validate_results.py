"""Independent scalar recurrence and prescribed time-grid convergence checks."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import hashlib,json,time,math
from pathlib import Path
import numpy as np
import model
from model import P,simulate,ALL_SEQUENCES
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';started=time.monotonic();limit=started+P['validation_budget_seconds'];model.DEADLINE=limit
raw=np.load(OUT/'all_candidate_arrays.npz',allow_pickle=False);methods=json.loads((OUT/'selected_methods.json').read_text());checks=[];convergence=[];scalar_results=[];trace=[]
def check(name,val):checks.append({'name':name,'passed':bool(val)});assert val,name
def budget():
    if time.monotonic()>limit:raise TimeoutError('Prescribed validation budget exceeded')
def scalar(s,seq,dt=.02):
    """No calls to vectorized scheduling, RC matrix or control helpers."""
    C=[v*s['c_scale'] for v in P['C']];g=[v*s['g_scale'] for v in P['Genv']];gc=P['Gcouple']*s['coupling_scale'];x=s['initial'][:];E=0.;cap=[False,False];hot=[0,0];cool=[0,0];freq=[.5,.5];request=[.5,.5];stall=[0.,0.];active=[None,None];jobs=[];trips=[0,0]
    for rep in range(3):
        templ=P['templates'][seq[rep]]
        for kind in range(4):
            dev=templ['map'][kind];jobs.append({'arrival':8.*rep,'deadline':8.*(rep+1),'device':dev,'freq':templ['frequency'][dev],'type':kind,'remaining':P['work'][kind],'start':None,'finish':None,'previous':len(jobs)-1 if kind in [1,3] else None})
    sample=round(.1/dt);nup=1+round(s['trip_confirm']/.1);ndown=1+round(s['release_confirm']/.1)
    for step in range(round(34/dt)):
        if step%200==0:budget()
        t=step*dt
        if step%sample==0:
            for dev in [0,1]:
                hot[dev]=hot[dev]+1 if not cap[dev] and x[dev]>=P['trip'][dev] else 0
                cool[dev]=cool[dev]+1 if cap[dev] and x[dev]<=P['release'][dev] else 0
                if not cap[dev] and hot[dev]>=nup:cap[dev]=True;trips[dev]+=1
                elif cap[dev] and cool[dev]>=ndown:cap[dev]=False
        if t<24:
            for dev in [0,1]:
                if active[dev] is None:
                    for j,job in enumerate(jobs):
                        if job['device']!=dev or job['start'] is not None or job['arrival']>t+1e-9:continue
                        if job['previous'] is not None and jobs[job['previous']]['finish'] is None:continue
                        active[dev]=j;job['start']=t;request[dev]=job['freq'];break
        else:active=[None,None]
        for dev in [0,1]:
            target=min(request[dev],.5 if cap[dev] else 1.)
            if abs(target-freq[dev])>1e-12:
                freq[dev]=target;stall[dev]=t+.02;E+=.002;x[dev]+=.002/C[dev]
        powers=P['idle_power'][:]
        for dev in [0,1]:
            j=active[dev]
            if j is None or stall[dev]>t+1e-9:continue
            job=jobs[j];speed=P['rates'][dev][job['type']]*freq[dev];fraction=min(1.,job['remaining']/(dt*speed));job['remaining']=max(0.,job['remaining']-dt*speed)
            powers[dev]+=fraction*(P['active_base'][dev]+P['dynamic_coefficient'][dev]*freq[dev]**3)
            if job['remaining']<=1e-10:job['finish']=t+dt*fraction;active[dev]=None
        def rhs(a,b):
            heat=[powers[0]+P['leak_coefficient'][0]*a,powers[1]+P['leak_coefficient'][1]*b]
            return [(-g[0]*a-gc*(a-b)+heat[0])/C[0],(-g[1]*b-gc*(b-a)+heat[1])/C[1],sum(heat)+P['external_power']]
        k1=rhs(*x);k2=rhs(x[0]+dt*k1[0]/2,x[1]+dt*k1[1]/2);k3=rhs(x[0]+dt*k2[0]/2,x[1]+dt*k2[1]/2);k4=rhs(x[0]+dt*k3[0],x[1]+dt*k3[1]);x=[x[i]+dt*(k1[i]+2*k2[i]+2*k3[i]+k4[i])/6 for i in [0,1]];E+=dt*(k1[2]+2*k2[2]+2*k3[2]+k4[2])/6
    return {'energy':E,'feasible':all(j['finish'] is not None and j['finish']<=j['deadline']+1e-9 for j in jobs),'finish':[j['finish'] for j in jobs],'trips':trips}

for name,sha in json.loads((ROOT/'design_freeze.json').read_text())['files'].items():check('freeze/'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha)
for s in P['scenarios']:
    sid=s['id'];key=sid+'__';hw=sid+'_hardware__';energy=raw[hw+'energy'];feasible=raw[hw+'feasible'];rows=[r for r in methods if r['scenario']==sid];oracle=next(x for x in rows if x['method']=='catalogue_best')
    check(sid+'/finite',np.isfinite(energy).all());check(sid+'/balance',np.max(abs(raw[hw+'components'].sum(axis=1)-energy))<1e-9)
    check(sid+'/true_catalogue_min',abs(float(energy[feasible].min())-oracle['energy'])<1e-9)
    check(sid+'/all_feasible_complete',np.all(raw[hw+'completed'][feasible]==12))
    check(sid+'/precedence',all(all(x['finish'][i] is None or x['finish'][i-1]<=x['start'][i]+1e-9 for i in [1,3,5,7,9,11]) for x in rows))
    seqs=sorted({tuple(x['sequence_indices']) for x in rows if x['method']!='reactive_threshold'});lookup={seq:i for i,seq in enumerate(seqs)}
    refined={}
    for dt in [.01,.005]:
        budget();r=simulate(s,seqs,dt=dt,prefix=False,trace=(sid in ['nominal','hot','cold','g_scale_1.5'] and dt==.005));reactseq=next(x['sequence_indices'] for x in rows if x['method']=='reactive_threshold');rr=simulate(s,[reactseq],dt=dt,reactive=True,prefix=False)
        for row in rows:
            selected=rr if row['method']=='reactive_threshold' else r;i=0 if selected is rr else lookup[tuple(row['sequence_indices'])]
            convergence.append({'scenario':sid,'method':row['method'],'dt':dt,'original_energy':row['energy'],'refined_energy':float(selected['energy'][i]),'relative_energy_difference_pct':100*(selected['energy'][i]-row['energy'])/row['energy'],'original_feasible':row['feasible'],'refined_feasible':bool(selected['feasible'][i]),'deadline_misses':int(selected['deadline_misses'][i])})
        if dt==.005:
            refined=r
            if sid in ['nominal','hot','cold','g_scale_1.5']:trace.append({'scenario':sid,'sequences':[list(x) for x in seqs],'samples':r['trace']})
    if sid in ['nominal','hot','g_scale_1.5','c_scale_1.3']:
        for seq in sorted({tuple(oracle['sequence_indices']),tuple(next(x['sequence_indices'] for x in rows if x['method']=='cold_fixed_plus_hardware'))}):
            result=scalar(s,seq);ind=int(np.flatnonzero(np.all(ALL_SEQUENCES==seq,axis=1))[0]);diff=result['energy']-energy[ind]
            scalar_results.append({'scenario':sid,'sequence':list(seq),'energy_difference':diff,'feasible_match':bool(result['feasible']==feasible[ind])});check(sid+'/scalar/'+str(seq),abs(diff)<1e-6 and result['feasible']==feasible[ind])
    print(json.dumps({'validated':sid,'elapsed_s':round(time.monotonic()-started,2)}),flush=True)

# Refinement is a scientific sensitivity result, not an assert that hides failures.
feasibility_changes=[r for r in convergence if r['original_feasible']!=r['refined_feasible']]
fine_gains=[]
for s in P['scenarios']:
    rr=[r for r in convergence if r['scenario']==s['id'] and r['dt']==.005];simple=[r for r in rr if r['method'] in ['cold_fixed_plus_hardware','safe_low_fixed','reactive_threshold','best_thermal_fixed'] and r['refined_feasible']];a=next(r for r in rr if r['method']=='two_period_lookahead')
    gain=100*(min(r['refined_energy'] for r in simple)-a['refined_energy'])/min(r['refined_energy'] for r in simple) if simple and a['refined_feasible'] else None
    fine_gains.append({'scenario':s['id'],'refined_selected_policy_gain_pct':gain,'scope':'Re-evaluated selected policies only; full catalogue not reoptimized on the finer grid.'})
result={'status':'PASS_NUMERIC_WITH_REFINEMENT_LIMITATIONS' if feasibility_changes else 'PASS_NUMERIC_AND_SELECTED_FEASIBILITY_CONVERGENCE','checks':len(checks),'checks_detail':checks,'independent_scalar_trajectories':scalar_results,'max_scalar_energy_error':max(abs(r['energy_difference']) for r in scalar_results),'convergence':convergence,'selected_feasibility_changes':feasibility_changes,'max_selected_energy_difference_pct':max(abs(r['relative_energy_difference_pct']) for r in convergence),'fine_grid_selected_gains':fine_gains,'elapsed_s':time.monotonic()-started,'scope':'Independent recurrence + selected-policy resolution check; no continuous-time/global-catalogue optimality or hardware validity certification.'}
(OUT/'numerical_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');(OUT/'selected_traces.json').write_text(json.dumps(trace,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['status','checks','max_scalar_energy_error','max_selected_energy_difference_pct','elapsed_s']}));print('feasibility_changes',len(feasibility_changes))
