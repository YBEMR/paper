from pathlib import Path
import argparse,csv,hashlib,json,time,sys,platform,itertools
import numpy as np
from scipy.stats import qmc
from model import KEYS,METRICS,ACTIONS,pack,cycle,initial_states,feasible,sequence

ROOT=Path(__file__).resolve().parent
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
    if isinstance(x,np.integer):return int(x)
    if isinstance(x,np.bool_):return bool(x)
    return x
def savecsv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def fit(E):
    train=[0,2,4];test=[1,3]
    ft=np.mean(E[train],axis=0);fixed=int(np.argmin(ft))
    best=float('inf');rule=(0.,0,0)
    for split in range(4):
        for low,high in itertools.product(range(9),repeat=2):
            chosen=[low if j<split else high for j in range(3)]
            value=float(np.mean([E[s,a] for s,a in zip(train,chosen)]))
            if value<best-1e-12:best=value;rule=(split,low,high)
    split,low,high=rule
    # Threshold is halfway between training STATE INDICES, subsequently mapped to temperatures.
    return fixed,split,low,high

def eval_policy(E,states):
    fixed,split,low,high=fit(E)
    tj=states[[0,2,4],0]
    threshold=-1000. if split==0 else 1000. if split==3 else float((tj[split-1]+tj[split])/2)
    test=[1,3];choice=[low if states[s,0]<threshold else high for s in test]
    F=float(np.mean(E[test,fixed]));T=float(np.mean([E[s,a] for s,a in zip(test,choice)]));O=float(np.mean(np.min(E[test],axis=1)))
    common=np.all(np.isfinite(E),axis=0)
    common_best=int(np.argmin(np.where(common,np.mean(E,axis=0),np.inf)))
    fixed_all=float(np.mean(E[:,common_best]));oracle_all=float(np.mean(np.min(E,axis=1)))
    common_gain=(1-oracle_all/fixed_all)*100 if np.isfinite(fixed_all) else None
    test_fixed_best=float(np.min(np.mean(E[test],axis=0)))
    strict_pairs=[]
    for a,b in itertools.combinations(range(9),2):
        if not np.isfinite(E[[0,4]][:,[a,b]]).all():continue
        d0=E[0,a]-E[0,b];d1=E[4,a]-E[4,b]
        eps0=.001*min(E[0,a],E[0,b]);eps1=.001*min(E[4,a],E[4,b])
        if (d0 < -eps0 and d1 > eps1) or (d0 > eps0 and d1 < -eps1):strict_pairs.append([ACTIONS[a],ACTIONS[b],float(d0),float(d1)])
    return clean(dict(fixed=ACTIONS[fixed],fixed_index=fixed,threshold_C=threshold,below=ACTIONS[low],above=ACTIONS[high],below_index=low,above_index=high,
        fixed_test_J=F,threshold_test_J=T,oracle_test_J=O,best_fixed_test_hindsight_J=test_fixed_best,
        threshold_gain_pct=(1-T/F)*100 if np.isfinite(F) and np.isfinite(T) else None,
        oracle_test_gain_pct=(1-O/F)*100 if np.isfinite(F) else None,
        threshold_oracle_gap_pct=(T/O-1)*100 if np.isfinite(T) and O>0 else None,
        threshold_break_even_J=F-T if np.isfinite(F) and np.isfinite(T) else None,
        fixed_test_feasible=bool(np.isfinite(E[test,fixed]).all()),threshold_test_feasible=bool(all(np.isfinite(E[s,a]) for s,a in zip(test,choice))),
        common_fixed_all=ACTIONS[common_best] if common.any() else None,oracle_all_gain_pct=common_gain,
        argmin_by_state=[ACTIONS[int(np.argmin(row))] if np.isfinite(row).any() else None for row in E],
        candidate_strict_reversal_pairs=strict_pairs))

def main(out):
    started=time.perf_counter();out.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'protocol.json').read_text(encoding='utf-8'))
    freeze=json.loads((ROOT/'freeze.json').read_text(encoding='utf-8'))
    for n,h in freeze['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    base=config['base'];nom=pack(base);states,why=initial_states(nom);assert states is not None,why
    bounds=config['uncertainty']['bounds']; names=list(bounds)
    unit=qmc.LatinHypercube(d=len(names),seed=config['uncertainty']['seed']).random(config['uncertainty']['count'])
    cases=[('nominal',base)]
    for i,u in enumerate(unit):
        d=base.copy()
        for k,v in zip(names,u):
            lo,hi=bounds[k];value=lo+(hi-lo)*v
            if k=='power_scale':d['P_A_W']=base['P_A_W']*value;d['P_B_W']=base['P_B_W']*value
            else:d[k]=value
        cases.append((f'lhs_{i:02d}',d))
    rows=[];policies=[];valid=[];excluded=[];state_rows=[];param_rows=[]
    for cid,d in cases:
        p=pack(d);ss,why=initial_states(p);param_rows.append({'case':cid,**d})
        if ss is None:excluded.append({'case':cid,'reason':why});continue
        valid.append((cid,p,ss))
        for s,st in enumerate(ss):state_rows.append({'case':cid,'state':s,'Tj_C':st[0],'Tp_C':st[1]})
        for th in [False,True]:
            E=np.full((5,9),np.inf)
            for s,st in enumerate(ss):
                for a in range(9):
                    v=cycle(p,*st,a,True,True,th);ok=feasible(v,p,th)
                    if ok:E[s,a]=v[0]
                    rows.append({'case':cid,'state':s,'action':ACTIONS[a],'throttle':int(th),'feasible':int(ok),**dict(zip(METRICS,v))})
            policies.append({'case':cid,'throttle':int(th),**eval_policy(E,ss)})
        if len(valid)%16==0:print('parameter cases',len(valid),flush=True)
    savecsv(out/'parameters.csv',param_rows);savecsv(out/'initial_states.csv',state_rows);savecsv(out/'single_window.csv',rows)
    write(out/'policy_comparison.json',policies);write(out/'excluded_cases.json',excluded)
    print('single-window matrix complete',len(rows),'rows',flush=True)
    abl=[];ab_policy=[]
    for leak,cont,th in itertools.product([False,True],repeat=3):
        E=np.full((5,9),np.inf)
        for s,st in enumerate(states):
            for a in range(9):
                v=cycle(nom,*st,a,leak,cont,th);ok=feasible(v,nom,th)
                if ok:E[s,a]=v[0]
                abl.append({'leak':int(leak),'contention':int(cont),'throttle':int(th),'state':s,'action':ACTIONS[a],'feasible':int(ok),**dict(zip(METRICS,v))})
        ab_policy.append({'leak':int(leak),'contention':int(cont),'throttle':int(th),**eval_policy(E,states)})
    savecsv(out/'ablation.csv',abl);write(out/'ablation_policies.json',ab_policy)
    sensitivity=[]
    for H in config['sensitivity']['tail_horizons_s']:
        p=nom.copy();p[23]=H
        for s in [0,4]:
            for a in range(9):
                v=cycle(p,*states[s],a)
                sensitivity.append({'kind':'tail','value':H,'state':s,'action':ACTIONS[a],**dict(zip(METRICS,v))})
    for k in config['sensitivity']['repeat_counts']:
        p=nom.copy();p[21:25]*=k/1000
        for s in [0,4]:
            for a in range(9):
                v=cycle(p,*states[s],a)
                sensitivity.append({'kind':'repeats','value':k,'state':s,'action':ACTIONS[a],**dict(zip(METRICS,v))})
    savecsv(out/'sensitivity.csv',sensitivity)
    periodic=[];trajectories=[];subset=[v for v in valid if v[0]!='nominal'][:16]
    periods=config['periodic']['periods_s'];n=config['periodic']['cycles']
    for cid,p0,ss in [valid[0]]+subset:
        for period in (periods if cid=='nominal' else [1.5]):
            p=p0.copy();p[23:25]=period
            for th in ([False,True] if cid=='nominal' else [False]):
                pp=next(z for z in policies if z['case']==cid and z['throttle']==int(th))
                jobs=[(0,a,0.,a,a,False) for a in range(9)]
                jobs.append((1,-1,pp['threshold_C'],pp['below_index'],pp['above_index'],False))
                if cid=='nominal':jobs.extend([(2,-1,0.,0,0,False)]+[(0,a,0.,a,a,True) for a in range(9)])
                for pol,a,thr,low,high,reset in jobs:
                    arr=sequence(p,ss[0],pol,thr,low,high,n,reset,th)
                    label=ACTIONS[a] if pol==0 else 'threshold' if pol==1 else 'myopic_enumeration'
                    ok=bool(np.isfinite(arr).all() and (arr[:,23]==1).all())
                    # Completion timestamps can be infinite only when the record is infeasible.
                    record={'case':cid,'period_s':period,'throttle':int(th),'policy':label,'reset':int(reset),'all_cycles_feasible':int(ok),
                            'total_J':float(np.sum(arr[:,4])),'last20_mean_J':float(np.mean(arr[-20:,4])),
                            'end_Tj_C':float(arr[-1,14]),'end_Tp_C':float(arr[-1,15]),
                            'peak_Tj_C':float(np.max(arr[:,12])),'peak_Tp_C':float(np.max(arr[:,13])),
                            'throttle_busy_s':float(np.sum(arr[:,17])),
                            'last_cycle_delta_C':float(np.max(np.abs(arr[-1,14:16]-arr[-2,14:16]))),
                            'action_switches':int(np.sum(arr[1:,3]!=arr[:-1,3]))}
                    periodic.append(record)
                    if cid=='nominal' and period==1.5 and not reset and not th:
                        for row in arr:trajectories.append({'policy':label,'cycle':int(row[0]),'initial_Tj_C':row[1],'initial_Tp_C':row[2],
                            'action':ACTIONS[int(row[3])],'energy_J':row[4],'end_Tj_C':row[14],'end_Tp_C':row[15],'feasible':row[23]})
        print('periodic',cid,flush=True)
    savecsv(out/'periodic.csv',periodic);savecsv(out/'nominal_trajectories.csv',trajectories)
    numerics=[]
    # Independent selection by largest thermal exposure and by every claimed reversal, not by gain magnitude.
    check_ids={'nominal'}
    hot=max(rows,key=lambda x:x['peak_j_C']);check_ids.add(hot['case'])
    for pp in policies:
        if pp['candidate_strict_reversal_pairs']:check_ids.add(pp['case'])
    for cid,p,ss in valid:
        if cid not in check_ids:continue
        for s in [0,4]:
            for a in range(9):
                for th in [False,True]:
                    v=cycle(p,*ss[s],a,True,True,th,.001)
                    v2=cycle(p,*ss[s],a,True,True,th,.0005)
                    v4=cycle(p,*ss[s],a,True,True,th,.00025)
                    numerics.append({'case':cid,'state':s,'action':ACTIONS[a],'throttle':int(th),
                      'E_dt_J':v[0],'E_half_J':v2[0],'E_quarter_J':v4[0],
                      'error_J':abs(v[0]-v4[0]),'error_pct':abs(v[0]-v4[0])/v4[0]*100,
                      'peak_delta_C':abs(v[8]-v4[8]),'feasible_equal':int(feasible(v,p,th)==feasible(v4,p,th))})
    savecsv(out/'numerical_convergence.csv',numerics)
    summary={'experiment':config['experiment_id'],'evidence':config['evidence'],'valid_cases_including_nominal':len(valid),'excluded_count':len(excluded),
       'single_window_rows':len(rows),'ablation_rows':len(abl),'periodic_runs':len(periodic),'periodic_cycles_per_run':n,
       'nominal_states_C':states,'nominal_policies':[x for x in policies if x['case']=='nominal'],
       'sensitivity_summary':{},'numerics_max_error_J':max(x['error_J'] for x in numerics),
       'numerics_max_error_pct':max(x['error_pct'] for x in numerics),
       'numerics_feasibility_flips':sum(1-x['feasible_equal'] for x in numerics),
       'max_heat_balance_error_J':max(abs(x['heat_balance_residual_J']) for x in rows),
       'wall_seconds':time.perf_counter()-started,'python':sys.version,'platform':platform.platform(),
       'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['protocol.json','SOURCES.md','model.py','run_experiment.py']}}
    for th in [0,1]:
        pp=[x for x in policies if x['case']!='nominal' and x['throttle']==th]
        gains=[x['oracle_all_gain_pct'] for x in pp if x['oracle_all_gain_pct'] is not None]
        summary['sensitivity_summary'][str(th)]={'cases':len(pp),'candidate_strict_reversal_cases':sum(bool(x['candidate_strict_reversal_pairs']) for x in pp),
           'argmin_change_cases':sum(len(set(x['argmin_by_state']))>1 for x in pp),
           'oracle_all_gain_max_pct':max(gains) if gains else None,'oracle_all_gain_median_pct':float(np.median(gains)) if gains else None,
           'oracle_all_gain_ge_2pct':sum(x>=2 for x in gains),
           'threshold_test_failure_cases':sum(not x['threshold_test_feasible'] for x in pp),
           'fixed_test_failure_cases':sum(not x['fixed_test_feasible'] for x in pp)}
    write(out/'summary.json',clean(summary));print(json.dumps(clean(summary),ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'results');args=ap.parse_args();main(args.out)
