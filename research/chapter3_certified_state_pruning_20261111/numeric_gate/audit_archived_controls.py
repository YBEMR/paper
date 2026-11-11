"""Exact structural row audit that makes integer-y control determinism explicit."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ARCH=REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'
STATIC=REPO/'research/chapter3_joint_state_static_20261111'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.now(timezone.utc).isoformat()
families={'domain_unique','auto_opp_active_support','unit_opp_aggregate_lock','joint_unique','joint_marginal'}


def save(p,d):
    with p.open('x') as stream:json.dump(d,stream,indent=2);stream.write('\n')


def freeze():
    files=[ARCH/'input_instance.json',ARCH/'execution/on/variable_names.json',ARCH/'execution/on/exported_model.npz',
           STATIC/'reachability/certificates.json',STATIC/'numerics/row_metadata.jsonl']
    save(HERE/'control_plan.json',dict(frozen_utc=now(),source_sha256={str(p.relative_to(REPO)):sha(p) for p in files},
        script_sha256=sha(Path(__file__)),new_model_builds=0,new_solver_calls=0,new_thermal_calls=0,
        scope='Control rows exactly reconstructed from archived state/support catalogues; no model construction'))


def run():
    t=time.monotonic();started=now();plan=read(HERE/'control_plan.json')
    assert sha(Path(__file__))==plan['script_sha256']
    for p,d in plan['source_sha256'].items():assert sha(REPO/p)==d
    names=read(ARCH/'execution/on/variable_names.json');var={name:i for i,name in enumerate(names)}
    matrix=np.load(ARCH/'execution/on/exported_model.npz');a=matrix['A_data'];ind=matrix['A_indices'];ptr=matrix['A_indptr'];rhs=matrix['b']
    instance=read(ARCH/'input_instance.json');assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
    actual=Counter();expected=Counter();counts=Counter();row_records=[]
    def key(tag,coef,b):return (tag,tuple(sorted((int(j),float(c)) for j,c in coef.items() if c)),float(b))
    with (STATIC/'numerics/row_metadata.jsonl').open() as stream:
        for line in stream:
            r=json.loads(line);tag=r['tag'];family=tag.split('/')[0]
            if family not in families:continue
            i=r['row_index'];coef={int(j):float(c) for j,c in zip(ind[ptr[i]:ptr[i+1]],a[ptr[i]:ptr[i+1]])}
            assert all(c in [-1.,1.] for c in coef.values()) and float(rhs[i]) in [-1.,0.,1.]
            assert r['rounding_allowance']=='0'
            actual[key(tag,coef,rhs[i])]+=1;counts[family]+=1
            row_records.append(dict(row_index=i,tag=tag,coefficient_count=len(coef),rhs=float(rhs[i]),all_coefficients_exact_integers=True,rounding_allowance_zero=True))
    def eq(tag,c,b):
        expected[key(tag+'/upper',c,b)]+=1
        expected[key(tag+'/lower',{j:-v for j,v in c.items()},-b)]+=1
    certificates=read(STATIC/'reachability/certificates.json')
    for interval in certificates:
        sid=interval['scene'];l=interval['interval'];domains=interval['domain_order'];support=interval['supports']
        ws={tuple(s['state']):var[f"w:{sid}:{l}:{tuple(s['state'])}"] for s in interval['states']}
        eq('joint_unique',{j:1 for j in ws.values()},1)
        for di,d in enumerate(domains):
            opps=instance['platform']['domains'][d]['opps']
            rhos={opp:var[f'rho:{sid}:{l}:{d}:{opp}'] for opp in opps}
            eq('domain_unique',{j:1 for j in rhos.values()},1)
            unit_opp=defaultdict(list)
            for opp,gs in support[d].items():
                for group in gs:
                    for oid in group['option_ids']:unit_opp[group['unit'],opp].append(var['y:'+oid])
            for opp,rho in rhos.items():
                eq('joint_marginal',{rho:-1,**{j:1 for state,j in ws.items() if state[di]==opp}},0)
                if opp!='L':
                    ys=[var['y:'+oid] for g in support[d].get(opp,[]) for oid in g['option_ids']]
                    expected[key('auto_opp_active_support',{rho:1,**{y:-1 for y in ys}},0)]+=1
            for (unit,opp),ys in unit_opp.items():
                expected[key('unit_opp_aggregate_lock',{rhos[opp]:-1,**{y:1 for y in ys}},0)]+=1
    assert actual==expected,(actual-expected,expected-actual)
    controls=[i for i,name in enumerate(names) if name.startswith(('rho:','w:'))]
    assert all(matrix['lb'][j]==0 and matrix['ub'][j]==1 for j in controls)
    save(HERE/'control_rows.json',row_records)
    result=dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-t,
        exact_rows_by_family=dict(counts),all_semantic_rows_match_archived_catalogue=True,
        rho_and_w_bounds_checked=len(controls),bounds_exact_zero_one=True,
        implication='With exact original integer-y onehot schedules, active locks or no-active auto support determine each rho as onehot; exact nonnegative joint marginals determine unique w. These are exact constraints, not approximate solver acceptance tubes.',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0,environment=dict(python=sys.version,numpy=np.__version__))
    save(HERE/'control_result.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    if sys.argv[1:]==['freeze']:freeze()
    else:run()
