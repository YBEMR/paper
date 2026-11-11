"""Check old state obstructions against exact exported binary64 scheduling rows."""
from collections import defaultdict, Counter
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
import csv
import hashlib
import itertools
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


def save(path,data):
    with path.open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')


def freeze():
    files=[ARCH/'input_instance.json',ARCH/'execution/on/options.json',ARCH/'execution/on/variable_names.json',
           ARCH/'execution/on/exported_model.npz',STATIC/'reachability/certificates.json',STATIC/'numerics/row_metadata.jsonl']
    save(HERE/'dependency_plan.json',dict(frozen_utc=now(),source_sha256={str(p.relative_to(REPO)):sha(p) for p in files},
        script_sha256=sha(Path(__file__)),wall_cap_s=120,
        proof='Sum actual exported dependency-path rows; minimize each Stage group using exact onehot. Endpoints restricted to original witness option groups. Strict positive margin proves no exact binary64-row integer-y point supports that tuple.',
        numeric_tolerance_probe='Additionally report margin minus number_of_path_rows*1e-9, still assuming exact integer choices/onehot; not preservation of near-integer solver acceptance tubes',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0))


def run():
    start=time.monotonic();started=now();plan=read(HERE/'dependency_plan.json')
    assert sha(Path(__file__))==plan['script_sha256']
    for p,h in plan['source_sha256'].items():assert sha(REPO/p)==h,p
    names=read(ARCH/'execution/on/variable_names.json');var={n:i for i,n in enumerate(names)}
    options=read(ARCH/'execution/on/options.json');groups=defaultdict(list);byvar={};byoid={}
    for option in options:
        y=var['y:'+option['option_id']];stage=option['stage_instance_id'];groups[stage].append(y);byvar[y]=option;byoid[option['option_id']]=y
    m=np.load(ARCH/'execution/on/exported_model.npz');a=m['A_data'];ind=m['A_indices'];ptr=m['A_indptr'];rhs=m['b'];intcon=set(map(int,m['intcon']))
    assert set(byvar)<=intcon # this archive uses zero-based exported integer ids
    assert all(m['lb'][y]==0 and m['ub'][y]==1 for y in byvar)
    def row(i):return {int(j):F.from_float(float(c)) for j,c in zip(ind[ptr[i]:ptr[i+1]],a[ptr[i]:ptr[i+1]])}
    instance=read(ARCH/'input_instance.json');edges={tuple(e) for scene in instance['scenarios'] for e in scene['dependencies']}
    dep={};onehot=defaultdict(dict)
    with (STATIC/'numerics/row_metadata.jsonl').open() as stream:
        for line in stream:
            meta=json.loads(line);tag=meta['tag'];i=meta['row_index']
            if tag.split('/')[0] not in ['dependency','stage_unique']:continue
            r=row(i);assert set(r)<=set(byvar)
            stages={byvar[y]['stage_instance_id'] for y in r}
            if tag.startswith('stage_unique'):
                assert len(stages)==1;stage=next(iter(stages));direction=tag.split('/')[1];sign=1 if direction=='upper' else -1
                assert r=={y:F(sign) for y in groups[stage]} and F.from_float(float(rhs[i]))==sign
                onehot[stage][direction]=i
            else:
                before={byvar[y]['stage_instance_id'] for y,c in r.items() if c>0}
                after={byvar[y]['stage_instance_id'] for y,c in r.items() if c<0}
                assert len(before)==len(after)==1
                edge=next(iter(before)),next(iter(after));assert edge in edges and edge not in dep
                dep[edge]=(i,r,F.from_float(float(rhs[i])))
    assert len(dep)==8 and len(onehot)==12 and all(set(v)=={'upper','lower'} for v in onehot.values())
    certificates=read(STATIC/'reachability/certificates.json');cache={};unique_records=[];replay_counts=Counter();failed=[]
    for interval in certificates:
        assert time.monotonic()-start<120
        domains=interval['domain_order'];support=interval['supports']
        for state in interval['states']:
            if state['status']!='PROVED_UNREACHABLE':continue
            choices=[support[d].get(opp,[]) for d,opp in zip(domains,state['state']) if opp!='L']
            tuples=list(itertools.product(*choices));assert len(tuples)==len(state['exhaustive_rejections'])
            for chosen,proof in zip(tuples,state['exhaustive_rejections']):
                assert [[x['stage'],x['unit']] for x in chosen]==proof['witness']
                if proof['reason']=='same_stage_unique':
                    pairs=[(x,y) for x,y in itertools.combinations(chosen,2) if x['stage']==y['stage']]
                    assert pairs
                    x,y=pairs[0];assert set(x['option_ids']).isdisjoint(y['option_ids'])
                    assert all(byoid[oid] in groups[x['stage']] for oid in x['option_ids']+y['option_ids'])
                    replay_counts['same_stage_exact_onehot']+=1
                    continue
                assert proof['reason']=='positive_duration_dependency_path'
                path=proof['path'];first=next(x for x in chosen if x['stage']==path[0]);last=next(x for x in chosen if x['stage']==path[-1])
                restricted={path[0]:tuple(byoid[x] for x in first['option_ids']),path[-1]:tuple(byoid[x] for x in last['option_ids'])}
                key=tuple(path),restricted[path[0]],restricted[path[-1]]
                if key not in cache:
                    total=defaultdict(F);bound=F(0);used=[]
                    for edge in zip(path,path[1:]):
                        i,r,b=dep[edge];used.append(i);bound+=b
                        for y,c in r.items():total[y]+=c
                    # Whole onehot groups not on this path have all-zero coefficients;
                    # enumerate those minima too to make the full-domain relaxation explicit.
                    minimum=F(0);pieces={}
                    for stage,ys in groups.items():
                        selected=restricted.get(stage,ys);assert selected and set(selected)<=set(ys)
                        value=min(total[y] for y in selected);minimum+=value;pieces[stage]=str(value)
                    margin=minimum-bound;tol_margin=margin-F(len(used),10**9)
                    record=dict(path=path,dependency_row_indices=used,first_option_ids=first['option_ids'],last_option_ids=last['option_ids'],
                        stage_minimum_terms=pieces,minimum_lhs_exact=str(minimum),sum_rhs_exact=str(bound),
                        strict_margin_exact=str(margin),strict_margin_float=float(margin),
                        margin_after_path_rows_times_1e_9_exact=str(tol_margin),margin_after_path_rows_times_1e_9_float=float(tol_margin),
                        strict_exclusion=margin>0)
                    cache[key]=record;unique_records.append(record)
                if not cache[key]['strict_exclusion']:failed.append(cache[key])
                replay_counts['dependency_exact_path']+=1
    save(HERE/'dependency_unique_certificates.json',unique_records)
    result=dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-start,
        exact_stage_onehot_groups=len(onehot),exported_dependency_rows=len(dep),
        replayed_obstruction_tuples=dict(replay_counts),unique_dependency_subdomain_checks=len(unique_records),
        strict_exported_path_proofs_passed=not failed,failed_tuple_count=len(failed),
        minimum_strict_margin=min(r['strict_margin_float'] for r in unique_records),
        minimum_after_path_rows_times_1e_9=min(r['margin_after_path_rows_times_1e_9_float'] for r in unique_records),
        all_2938_original_state_certificates_replayed=sum(replay_counts.values())==54440,
        caveat='Assumes original y variables exact 0/1 and exact structural onehot rows. Numeric path tolerance check is separate; it is not a proof about near-integer solver-tolerance tubes. Entire LP relaxation need not be preserved.',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0,environment=dict(python=sys.version,numpy=np.__version__,platform=sys.platform))
    save(HERE/'dependency_result.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    if sys.argv[1:]==['freeze']:freeze()
    else:run()
