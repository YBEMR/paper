"""E3 archived-evidence accounting only; no scientific backend imports."""
from collections import Counter
import csv,hashlib,json
from fractions import Fraction as F
from pathlib import Path
HERE=Path(__file__).resolve().parent;RUN=HERE/'results/e3_deploy_01'
PARTS=('baseline','activity','external_common','temperature_correction')

def read(p):return json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,v):Path(p).write_bytes((json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def interval(v):
    a,b=map(F,v);assert a<=b;return a,b

def weighted_parts(receipt,instance):
    out={k:[F(0),F(0)] for k in PARTS}
    for scene in instance['scenarios']:
        for k in PARTS:
            a,b=interval(receipt['scenes'][scene['id']]['energy_components_J'][k]);w=F(scene['weight'])
            out[k][0]+=w*a;out[k][1]+=w*b
    return {k:list(map(str,v)) for k,v in out.items()}

def canonical_candidate(candidate):
    return {'scenes':{sid:sorted([dict(stage_id=r['stage_id'],unit=r['unit'],opp=r['opp'],start_ms=str(F(r['start_ms'])))
        for r in rows],key=lambda r:r['stage_id']) for sid,rows in candidate['scenes'].items()}}

def main():
    batch=read(RUN/'batch_summary.json');manifest=read(HERE/'evidence/e3_deployment_precheck01/frozen_real_manifest.json')
    auth=read(HERE/'authorizations/e3_deploy_01.json')
    root=Path(auth['authority_store'])/digest({'authorization_id':auth['authorization_id']})
    assert root.is_dir() and (root/'batch.json').is_file(),'canonical ledger missing'
    lb=read(root/'batch.json');assert lb['authorization_sha256']==digest(auth) and lb['scope_sha256']==digest(manifest)
    assert manifest['budgets']==dict(plan_s=300,post_s=60,plan_calls=2,post_calls=2)
    shared_input=read(HERE/'evidence/e3_deployment_precheck01/base__R1.json')['instance']
    original={(s['id'],x['id']):x['shared_stage_id'] for s in shared_input['scenarios'] for x in s['stage_instances']}
    slots=[];stages=[];segments=[];final_receipts={};candidate_views={}
    for n,(pid,objective) in enumerate(manifest['slots'],1):
        folder=RUN/f'slot_{n}';item=dict(ordinal=n,problem_id=pid,arm='SHARED' if n==1 else 'SCENE_LOCAL_A',state='NOT_RUN',
            post_U_approx_J=None,plan_U_approx_J=None,no_global_optimality_proof=True)
        ap=folder/'plan/accepted_result.json'
        if not ap.exists():slots.append(item);continue
        accepted=read(ap);plan=accepted['result'];proc=accepted.get('process') or {};job=read(folder/'plan/job.json');p=job['packet'];i=p['instance']
        assert i['id']==pid and p['objective']==objective=='FULL'
        assert digest(i)==manifest['inputs'][pid]['input_sha256']
        archive=plan.get('archive',{})
        item.update(state=plan['state'],reason=plan.get('reason'),stop_required=plan.get('stop_required'),
            deployment_identity_count=len(i['stage_modes']),catalog_mode_count=sum(len(x) for x in i['stage_modes'].values()),
            plan_process_s=proc.get('method_elapsed_s'),plan_internal_s=plan.get('timing',{}).get('method_elapsed_s'),
            startup_s=proc.get('startup_elapsed_s'),plan_classification=proc.get('classification'),plan_reaped=proc.get('reaped'),
            first_safe_s=archive.get('first_safe_at_s'),selected_at_s=plan.get('selected_at_s'),
            candidate_attempts=archive.get('candidates'),unique_evaluations=len(archive.get('evaluations',[])),cache_hits=archive.get('cache_hits'),
            score_improvements=len(archive.get('events',[])),candidate_states=dict(Counter(x['evaluation']['state'] for x in archive.get('evaluations',[]))),
            coverage_complete=plan.get('coverage_complete',False),independently_proven_optimal=plan.get('independently_proven_optimal',False))
        if plan['state']=='SAFE':
            candidate=plan['safe_candidate'];key=digest(candidate);assert key==plan['selected_candidate_sha256']
            item.update(candidate_sha256=key,planning_score_J=plan['planning_score_J'],plan_true_energy_J=plan['evaluation']['weighted_energy_J'],
                plan_U_approx_J=float(interval(plan['evaluation']['weighted_energy_J'])[1]))
            candidate_views[n]=canonical_candidate(candidate)
        pp=folder/'post/accepted_result.json'
        if pp.exists():
            v=read(pp);post=v['result'];pr=v.get('process') or {}
            item.update(post_state=post['state'],post_reason=post.get('reason'),post_stop_required=post.get('stop_required'),
                post_process_s=pr.get('method_elapsed_s'),post_internal_s=post.get('timing',{}).get('method_elapsed_s'),
                post_classification=pr.get('classification'),post_reaped=pr.get('reaped'))
            if post['state']=='POST_SAFE':
                assert plan['state']=='SAFE' and post['candidate_sha256']==item['candidate_sha256']
                receipt=post['evaluation'];a,b=interval(plan['evaluation']['weighted_energy_J']);c,d=interval(receipt['weighted_energy_J'])
                assert max(a,c)<=min(b,d)
                final_receipts[n]=receipt
                item.update(state='POST_SAFE',post_true_energy_J=receipt['weighted_energy_J'],post_U_J=str(d),post_U_approx_J=float(d),
                    weighted_components_J=weighted_parts(receipt,i),
                    peak_upper_degC=str(max(F(x[1]) for scene in receipt['scenes'].values() for x in scene['peaks_degC'].values())))
                a_units={sid:{} for sid in ('A.pre','A.main','A.post')}
                for sid,scene in receipt['legality']['scenes'].items():
                    for row in scene['rows']:
                        physical_id=original[(sid,row['stage_id'])]
                        stages.append(dict(ordinal=n,arm=item['arm'],scene_id=sid,stage_id=row['stage_id'],physical_stage_id=physical_id,
                            deployment_identity=row['shared_stage_id'],**{k:row[k] for k in ('unit','opp','start_ms','duration_ms','end_ms')}))
                        if physical_id in a_units:a_units[physical_id][sid]=row['unit']
                    for seg in scene['segments']:segments.append(dict(ordinal=n,arm=item['arm'],scene_id=sid,**seg))
                item['A_units_by_stage_and_scene']=a_units
                item['A_stages_with_different_scene_units']=[k for k,v in a_units.items() if len(set(v.values()))>1]
                item['candidate_satisfies_original_A_unit_sharing']=not item['A_stages_with_different_scene_units']
        slots.append(item)
    comparison=dict(state='NOT_COMPARABLE_WITH_FINAL_POST',difference_definition='shared energy minus scene-local energy; percent denominator shared')
    if len(final_receipts)==2:
        s,l=slots;a,b=interval(s['post_true_energy_J']);c,d=interval(l['post_true_energy_J']);delta=(a-d,b-c)
        ratios=[v/w*100 for v in delta for w in (a,b)]
        changes=[]
        left={(x['scene_id'],x['stage_id']):x for x in stages if x['ordinal']==1}
        right={(x['scene_id'],x['stage_id']):x for x in stages if x['ordinal']==2}
        for key in sorted(left):
            fields=[k for k in ('unit','opp','start_ms','end_ms') if left[key][k]!=right[key][k]]
            if fields:changes.append(dict(scene_id=key[0],stage_id=key[1],physical_stage_id=left[key]['physical_stage_id'],
                changed_fields=fields,SHARED={k:left[key][k] for k in ('unit','opp','start_ms','end_ms')},
                SCENE_LOCAL_A={k:right[key][k] for k in ('unit','opp','start_ms','end_ms')}))
        same=candidate_views[1]==candidate_views[2]
        if same:assert max(a,c)<=min(b,d),'same physical candidate contradicts energy intervals'
        part_delta={k:[str(F(s['weighted_components_J'][k][0])-F(l['weighted_components_J'][k][1])),
                       str(F(s['weighted_components_J'][k][1])-F(l['weighted_components_J'][k][0]))] for k in PARTS}
        comparison.update(state='COMPARABLE',conclusion='LOCAL_STRICTLY_LOWER' if d<a else ('SHARED_STRICTLY_LOWER' if b<c else 'NUMERICALLY_UNRESOLVED'),
            delta_shared_minus_local_J=list(map(str,delta)),delta_midpoint_microJ=float(sum(delta)/2*1000000),
            relative_percent=[str(min(ratios)),str(max(ratios))],relative_percent_approx=float(sum(delta)/(a+b)*100),
            same_physical_candidate=same,saved_energy_intervals_identical=s['post_true_energy_J']==l['post_true_energy_J'],
            saved_component_intervals_identical=s['weighted_components_J']==l['weighted_components_J'],
            differing_execution_rows=len(changes),stage_changes=changes,
            same_device_mapping=all(left[k]['unit']==right[k]['unit'] for k in left),
            same_OPPs=all(left[k]['opp']==right[k]['opp'] for k in left),
            local_candidate_satisfies_original_sharing=l['candidate_satisfies_original_A_unit_sharing'],component_delta_shared_minus_local_J=part_delta,
            interpretation='finite deterministic heuristic outputs; not a proof of exact shared-deployment optimum penalty')
    claims=list(root.glob('*_claim.json'));launches=list(root.glob('*_launch.json'))
    summary=dict(material_passport=dict(type='code_experiment_result',mode='run',status='COMPLETED_READ_ONLY_ACCOUNTING',
        scope='same full-chain R1 H/auto-L; shared versus scene-local A concrete-unit deployment only'),
        authorization_id=auth['authorization_id'],source_sha=manifest['source_sha'],manifest_sha256=digest(manifest),
        consumed_plan_calls=sum(read(p)['phase']=='PLAN' for p in claims),consumed_post_calls=sum(read(p)['phase']=='POST' for p in claims),
        launched_plan_calls=sum('plan_launch' in p.name for p in launches),launched_post_calls=sum('post_launch' in p.name for p in launches),
        real_backend_entries=len(list(RUN.rglob('real_backend_entry.json'))),planned_plan_calls=2,planned_max_post_calls=2,
        retries=batch['retries'],post_safe_slots=sum(x['state']=='POST_SAFE' for x in slots),batch_wall_s=batch['wall_s'],
        sum_plan_process_s=sum((x.get('plan_process_s') or 0) for x in slots),sum_post_process_s=sum((x.get('post_process_s') or 0) for x in slots),
        slots=slots,comparison=comparison,no_global_optimality_proof=True)
    save(RUN/'analysis.json',summary);save(RUN/'domain_segments.json',segments)
    fields=['ordinal','arm','problem_id','state','post_U_approx_J','plan_U_approx_J','peak_upper_degC','plan_process_s','post_process_s',
        'first_safe_s','selected_at_s','candidate_attempts','unique_evaluations','cache_hits','score_improvements','deployment_identity_count',
        'candidate_satisfies_original_A_unit_sharing','reason','post_reason']
    with (RUN/'results.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(slots)
    with (RUN/'schedules.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['ordinal','arm','scene_id','stage_id','physical_stage_id','deployment_identity','unit','opp','start_ms','duration_ms','end_ms']
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(stages)
    print(json.dumps({k:summary[k] for k in ('consumed_plan_calls','consumed_post_calls','post_safe_slots','batch_wall_s','sum_plan_process_s','sum_post_process_s')}))
    for x in slots:print(json.dumps({k:x.get(k) for k in ('arm','state','post_U_approx_J','plan_process_s','post_process_s','A_stages_with_different_scene_units')},ensure_ascii=False))
    print(json.dumps({k:comparison.get(k) for k in ('conclusion','relative_percent_approx','same_physical_candidate','differing_execution_rows','same_device_mapping','same_OPPs','local_candidate_satisfies_original_sharing')},ensure_ascii=False))

if __name__=='__main__':main()
