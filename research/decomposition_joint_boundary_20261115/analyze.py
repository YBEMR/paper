from pathlib import Path
import csv,json,itertools
import numpy as np
from model import transitions,evaluate_pool,METRICS
ROOT=Path(__file__).resolve().parent
def read(name):
    with (ROOT/'results'/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def save(name,rows):
    with (ROOT/'analysis'/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    (ROOT/'analysis').mkdir(exist_ok=True);rows=read('comparisons.csv');arms=read('arms.csv')
    index={(x['arm'],x['method']):x for x in rows};full=[x for x in rows if x['arm'].endswith('c1l1s1h1')]
    summary=[]
    for method in sorted({x['method'] for x in rows}):
        q=[x for x in rows if x['method']==method];good=[x for x in q if x['feasible']=='True']
        summary.append(dict(method=method,conditions=len(q),failures=len(q)-len(good),
            max_excess_over_joint_pct=max(float(x['excess_over_joint_pct']) for x in good),
            max_joint_saving_pct=max(float(x['joint_saving_pct']) for x in good),
            max_absolute_gap_J=max(float(x['energy_J'])-float(index[x['arm'],'J']['energy_J']) for x in good)))
    save('method_summary.csv',summary)
    heat_pairs=[];state_pairs=[];factor=[]
    for x in rows:
        if x['arm'].endswith('h1'):
            off=index[x['arm'][:-1]+'0',x['method']]
            heat_pairs.append(dict(arm=x['arm'],method=x['method'],same_candidate=x['candidate_id']==off['candidate_id'],
                energy_difference_J=float(x['energy_J'])-float(off['energy_J'])))
        if '_t50_' in x['arm']:
            warm=index[x['arm'].replace('_t50_','_t78_'),x['method']]
            state_pairs.append(dict(arm=x['arm'],method=x['method'],same_candidate=x['candidate_id']==warm['candidate_id']))
    for c,l,s in itertools.product([0,1],repeat=3):
        q=[x for x in rows if x['method']=='NT' and x['arm'].endswith(f'c{c}l{l}s{s}h1')]
        factor.append(dict(coupling=c,leakage=l,shared=s,max_excess_pct=max(float(x['excess_over_joint_pct']) for x in q),
            max_absolute_gap_J=max(float(x['energy_J'])-float(index[x['arm'],'J']['energy_J']) for x in q)))
    save('thermal_constraint_pairs.csv',heat_pairs);save('initial_state_pairs.csv',state_pairs);save('factorial_nt_gap.csv',factor)
    # Refine every unique reported witness, without changing the scientific run.
    cfg=json.loads((ROOT/'protocol.json').read_text());cache={};witness=[];maxE=0.;maxwidth=0.
    for arm in arms:
        label=arm['arm'][:-2]
        if arm['heat_limit']!='1':continue # Same candidates checked below for H=0.
        poolname=arm['pool'];pack=np.load(ROOT/'results'/(poolname+'_pool.npz'))
        unique=sorted({int(x['candidate_id']) for x in rows if x['arm'] in [label+'h0',label+'h1'] and x['candidate_id']})
        c=int(arm['coupling']);l=int(arm['leakage']);s=int(arm['shared']);initial=float(arm['initial_C'])
        if (c,l) not in cache:cache[c,l]=transitions(cfg,c,l,10)
        pool=pack['pool'];res=evaluate_pool(pool[unique],pack['configs'],pack['powers'],s,initial,10,*cache[c,l])
        raw=np.load(ROOT/'results'/(label+'_raw.npz'))['metrics']
        for j,k in enumerate(unique):
            err=abs(res[j,0]-raw[k,0]);width=res[j,6]-res[j,5]
            assert err<1e-8 and width<1e-4 and res[j,6]<=80
            maxE=max(maxE,err);maxwidth=max(maxwidth,width)
            witness.append(dict(arm=label,candidate_id=k,error_from_5ms_J=err,**dict(zip(METRICS,res[j]))))
    save('witnesses_refined.csv',witness)
    output=dict(methods=summary,full_thermal_nt_max_excess_pct=max(float(x['excess_over_joint_pct']) for x in full if x['method']=='NT'),
        selected_all_safe_under_original_80C=all(float(x['peak_bound_C'])<=80 for x in rows if x['candidate_id']),
        heat_limit_changed_candidate=sum(not x['same_candidate'] for x in heat_pairs),
        initial_temperature_changed_candidate=sum(not x['same_candidate'] for x in state_pairs),
        shared_constraint_rejected_candidates=sum(x['candidates']-x['shared_legal'] for x in json.loads((ROOT/'results/summary.json').read_text())['pools']),
        refined_witnesses=len(witness),refined_energy_max_error_J=maxE,refined_peak_max_width_C=maxwidth,
        full_arm_counts=[x for x in arms if x['arm'].endswith('c1l1s1h1')],
        interpretation='No remaining mapping/configuration loss in this finite domain. Shared-frequency collision constraint never excludes a candidate; not a test of the fully active three-way interaction.')
    (ROOT/'analysis/summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k not in ['methods','full_arm_counts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
