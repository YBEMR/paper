"""Read-only E2 result accounting; no scheduling, solver or thermal imports."""
from collections import Counter
import csv,hashlib,json
from fractions import Fraction as F
from pathlib import Path
HERE=Path(__file__).resolve().parent;RUN=HERE/'results/e2_res_01'
COMPONENTS=('baseline','activity','external_common','temperature_correction')


def read(p):return json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def save(p,v):Path(p).write_bytes((json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def interval(v):
    a,b=map(F,v);assert a<=b;return a,b

def components(receipt,instance):
    out={k:[F(0),F(0)] for k in COMPONENTS}
    for s in instance['scenarios']:
        for k in out:
            a,b=interval(receipt['scenes'][s['id']]['energy_components_J'][k]);w=F(s['weight'])
            out[k][0]+=w*a;out[k][1]+=w*b
    return {k:list(map(str,v)) for k,v in out.items()}

def main():
    batch=read(RUN/'batch_summary.json');manifest=read(HERE/'evidence/e2_resource_precheck01/frozen_real_manifest.json')
    auth=read(HERE/'authorizations/e2_res_01.json');root=Path(auth['authority_store'])/digest({'authorization_id':auth['authorization_id']})
    assert root.is_dir() and (root/'batch.json').is_file(),'missing canonical persistent ledger'
    ledger_batch=read(root/'batch.json')
    assert ledger_batch['authorization_sha256']==digest(auth) and ledger_batch['scope_sha256']==digest(manifest)
    slots=[];all_stages=[];domain_segments=[];running_evidence=[]
    for ordinal,(problem,objective) in enumerate(manifest['slots'],1):
        item=dict(ordinal=ordinal,problem_id=problem,objective=objective,state='NOT_RUN',post_U_approx_J=None,
                  plan_U_approx_J=None,no_global_optimality_proof=True)
        folder=RUN/f'slot_{ordinal}';ppath=folder/'plan/accepted_result.json'
        if not ppath.exists():slots.append(item);continue
        accepted=read(ppath);plan=accepted['result'];process=accepted.get('process') or {};job=read(folder/'plan/job.json')
        packet=job['packet'];i=packet['instance'];assert i['id']==problem and packet['objective']==objective=='FULL'
        assert digest(i)==manifest['inputs'][problem]['input_sha256'];archive=plan.get('archive',{})
        item.update(state=plan['state'],reason=plan.get('reason'),stop_required=plan.get('stop_required'),
            available_device_classes=i['settings']['available_device_classes'],plan_method_s=plan.get('timing',{}).get('method_elapsed_s'),
            plan_process_s=process.get('method_elapsed_s'),startup_s=process.get('startup_elapsed_s'),
            plan_process_classification=process.get('classification'),plan_reaped=process.get('reaped'),
            first_safe_s=archive.get('first_safe_at_s'),selected_at_s=plan.get('selected_at_s'),
            candidate_attempts=archive.get('candidates'),unique_evaluations=len(archive.get('evaluations',[])),
            cache_hits=archive.get('cache_hits'),score_improvements=len(archive.get('events',[])),
            candidate_states=dict(Counter(r['evaluation']['state'] for r in archive.get('evaluations',[]))),
            coverage_complete=plan.get('coverage_complete',False),independently_proven_optimal=plan.get('independently_proven_optimal',False))
        if plan['state']=='SAFE':
            candidate=plan['safe_candidate'];key=digest(candidate);assert key==plan['selected_candidate_sha256']
            item.update(candidate_sha256=key,planning_score_J=plan['planning_score_J'],
                plan_true_energy_J=plan['evaluation']['weighted_energy_J'],plan_U_approx_J=float(interval(plan['evaluation']['weighted_energy_J'])[1]))
        postpath=folder/'post/accepted_result.json';final=None
        if postpath.exists():
            record=read(postpath);post=record['result'];p=record.get('process') or {}
            item.update(post_state=post['state'],post_reason=post.get('reason'),post_stop_required=post.get('stop_required'),
                post_method_s=post.get('timing',{}).get('method_elapsed_s'),post_process_s=p.get('method_elapsed_s'),
                post_process_classification=p.get('classification'),post_reaped=p.get('reaped'))
            if post['state']=='POST_SAFE':
                assert plan['state']=='SAFE' and post['candidate_sha256']==item['candidate_sha256']
                final=post['evaluation'];a,b=interval(plan['evaluation']['weighted_energy_J']);c,d=interval(final['weighted_energy_J'])
                assert max(a,c)<=min(b,d)
                item.update(state='POST_SAFE',post_true_energy_J=final['weighted_energy_J'],post_U_J=str(d),post_U_approx_J=float(d),
                    weighted_components_J=components(final,i),
                    peak_temperature_upper_degC=str(max(F(v[1]) for s in final['scenes'].values() for v in s['peaks_degC'].values())))
        if final:
            units={u['id']:u for u in i['platform']['units']}
            mapping={}
            for sid,scene in final['legality']['scenes'].items():
                for row in scene['rows']:
                    mapping[row['shared_stage_id']]=row['unit']
                    all_stages.append(dict(ordinal=ordinal,problem_id=problem,scene_id=sid,stage_id=row['stage_id'],
                        shared_stage_id=row['shared_stage_id'],device_class=units[row['unit']]['device_class'],
                        **{k:row[k] for k in ('unit','opp','start_ms','duration_ms','end_ms')}))
                for seg in scene['segments']:
                    domain_segments.append(dict(ordinal=ordinal,problem_id=problem,scene_id=sid,**seg))
            item['shared_mapping']=mapping
            item['stage_device_counts_by_execution']=dict(Counter(row['device_class'] for row in all_stages if row['ordinal']==ordinal))
        slots.append(item)
    comparisons=[]
    for left,right in ((1,2),(1,3),(1,4),(2,4),(3,4)):
        a,b=slots[left-1],slots[right-1]
        pair=dict(subset_slot=left,superset_slot=right,state='NOT_COMPARABLE_WITH_FINAL_POST')
        if a['state']==b['state']=='POST_SAFE':
            a0,a1=interval(a['post_true_energy_J']);b0,b1=interval(b['post_true_energy_J']);delta=(a0-b1,a1-b0)
            ratios=[d/v*100 for d in delta for v in (a0,a1)]
            pair.update(state='COMPARABLE',delta_subset_minus_superset_J=list(map(str,delta)),
                relative_percent=list(map(str,(min(ratios),max(ratios)))),
                relative_percent_approx=float((delta[0]+delta[1])/(a0+a1)*100),
                conclusion='SUPERSET_STRICTLY_LOWER' if b1<a0 else ('SUBSET_STRICTLY_LOWER' if a1<b0 else 'NUMERICALLY_UNRESOLVED'),
                component_delta_subset_minus_superset_J={k:[str(F(a['weighted_components_J'][k][0])-F(b['weighted_components_J'][k][1])),
                    str(F(a['weighted_components_J'][k][1])-F(b['weighted_components_J'][k][0]))] for k in COMPONENTS})
        comparisons.append(pair)
    claims=list(root.glob('*_claim.json'));launches=list(root.glob('*_launch.json'))
    summary=dict(material_passport=dict(type='code_experiment_result',mode='run',status='COMPLETED_READ_ONLY_ACCOUNTING',
        scope='fixed four-node auto-L platform, H R1 full AB/AC three-stage, four mapping availability masks'),
        authorization_id=auth['authorization_id'],source_sha=manifest['source_sha'],manifest_sha256=digest(manifest),
        consumed_plan_calls=sum(read(p)['phase']=='PLAN' for p in claims),consumed_post_calls=sum(read(p)['phase']=='POST' for p in claims),
        launched_plan_calls=sum('plan_launch' in p.name for p in launches),launched_post_calls=sum('post_launch' in p.name for p in launches),
        real_backend_entries=len(list(RUN.rglob('real_backend_entry.json'))),planned_plan_calls=4,retries=batch['retries'],
        planned_max_post_calls=4,formal_SAFE_slots=sum(s['state']=='POST_SAFE' for s in slots),batch_wall_s=batch['wall_s'],
        sum_plan_process_s=sum((s.get('plan_process_s') or 0) for s in slots),sum_post_process_s=sum((s.get('post_process_s') or 0) for s in slots),
        slots=slots,domain_inclusion_comparisons=comparisons,
        interpretation='single-run finite heuristic outcomes, no exact optimality, hardware measurement or statistical-stability claim')
    save(RUN/'analysis.json',summary);save(RUN/'domain_segments.json',domain_segments)
    fields=['ordinal','problem_id','objective','state','post_U_approx_J','plan_U_approx_J','plan_process_s','post_process_s',
            'startup_s','first_safe_s','selected_at_s','candidate_attempts','unique_evaluations','cache_hits','score_improvements',
            'peak_temperature_upper_degC','reason','post_state','post_reason']
    with (RUN/'results.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(slots)
    with (RUN/'schedules.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['ordinal','problem_id','scene_id','stage_id','shared_stage_id','device_class','unit','opp','start_ms','duration_ms','end_ms']
        w=csv.DictWriter(f,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(all_stages)
    print(json.dumps({k:summary[k] for k in ('consumed_plan_calls','consumed_post_calls','formal_SAFE_slots','batch_wall_s','sum_plan_process_s','sum_post_process_s')}))
    for s in slots:print(json.dumps({k:s.get(k) for k in ('ordinal','problem_id','state','post_U_approx_J','first_safe_s','plan_process_s','post_process_s')},ensure_ascii=False))
    for p in comparisons:print(json.dumps({k:p.get(k) for k in ('subset_slot','superset_slot','conclusion','relative_percent_approx')},ensure_ascii=False))

if __name__=='__main__':main()
