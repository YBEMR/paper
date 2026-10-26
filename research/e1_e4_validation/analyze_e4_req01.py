"""Read-only E4 request-count result accounting; no scheduling, solver or thermal imports."""
from collections import Counter
import csv,hashlib,json
from fractions import Fraction as F
from pathlib import Path
HERE=Path(__file__).resolve().parent;RUN=HERE/'results/e4_req_01'
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
    batch=read(RUN/'batch_summary.json');manifest=read(HERE/'evidence/e4_requests_precheck01/frozen_real_manifest.json')
    auth=read(HERE/'authorizations/e4_req_01.json');root=Path(auth['authority_store'])/digest({'authorization_id':auth['authorization_id']})
    assert root.is_dir() and (root/'batch.json').is_file(),'missing canonical persistent ledger'
    ledger_batch=read(root/'batch.json')
    assert ledger_batch['authorization_sha256']==digest(auth) and ledger_batch['scope_sha256']==digest(manifest)
    slots=[];all_stages=[];domain_segments=[];request_rows=[]
    for ordinal,(problem,objective) in enumerate(manifest['slots'],1):
        item=dict(ordinal=ordinal,problem_id=problem,objective=objective,state='NOT_RUN',post_U_approx_J=None,
                  plan_U_approx_J=None,no_global_optimality_proof=True)
        frozen=read(HERE/f'evidence/e4_requests_precheck01/{problem}.json')['instance']
        weighted_count=sum((F(scene['weight'])*len(scene['requests']) for scene in frozen['scenarios']),F(0))
        item.update(requests_per_application=frozen['settings']['requests_per_application'],
            weighted_requests_per_window=str(weighted_count),
            raw_requests_across_scenarios=sum(len(scene['requests']) for scene in frozen['scenarios']),
            stage_executions_across_scenarios=sum(len(scene['stage_instances']) for scene in frozen['scenarios']))
        folder=RUN/f'slot_{ordinal}';ppath=folder/'plan/accepted_result.json'
        if not ppath.exists():slots.append(item);continue
        accepted=read(ppath);plan=accepted['result'];process=accepted.get('process') or {}
        if not (folder/'plan/job.json').exists():
            item.update(state=plan['state'],reason=plan.get('reason'),stop_required=plan.get('stop_required'),plan_process_s=process.get('method_elapsed_s'))
            slots.append(item);continue
        job=read(folder/'plan/job.json')
        packet=job['packet'];i=packet['instance'];assert i['id']==problem and packet['objective']==objective=='FULL'
        assert digest(i)==manifest['inputs'][problem]['input_sha256'];archive=plan.get('archive',{})
        item.update(state=plan['state'],reason=plan.get('reason'),stop_required=plan.get('stop_required'),
            deadline_beta=i['settings']['deadline_beta'],plan_method_s=plan.get('timing',{}).get('method_elapsed_s'),
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
                item['per_request_energy_J']=[str(c/weighted_count),str(d/weighted_count)]
                item['per_request_U_approx_J']=float(d/weighted_count)
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
            for scene in i['scenarios']:
                for req in scene['requests']:
                    completion=final['legality']['scenes'][scene['id']]['request_completion_ms'][req['id']]
                    slack=F(req['deadline_ms'])-F(completion)
                    assert slack>=0
                    request_rows.append(dict(ordinal=ordinal,beta=i['settings']['deadline_beta'],scene_id=scene['id'],
                        request_id=req['id'],application=req['application'],release_ms=req['release_ms'],deadline_ms=req['deadline_ms'],
                        completion_ms=completion,slack_ms=str(slack)))
            item['min_deadline_slack_ms']=str(min(F(x['slack_ms']) for x in request_rows if x['ordinal']==ordinal))
            item['stage_OPP_counts_by_execution']=dict(Counter(row['opp'] for row in all_stages if row['ordinal']==ordinal))
            item['shared_mapping']=mapping
            item['stage_device_counts_by_execution']=dict(Counter(row['device_class'] for row in all_stages if row['ordinal']==ordinal))
        slots.append(item)
    comparison=dict(state='NOT_COMPARABLE_WITH_FINAL_POST',
        scope='different request counts; no feasible-domain-inclusion or algorithm-ranking claim')
    if all(x['state']=='POST_SAFE' for x in slots):
        one,two=slots;a0,a1=interval(one['post_true_energy_J']);b0,b1=interval(two['post_true_energy_J'])
        p0,p1=interval(one['per_request_energy_J']);q0,q1=interval(two['per_request_energy_J'])
        delta=(p0-q1,p1-q0);ratios=[d/v*100 for d in delta for v in (p0,p1)]
        comparison.update(state='COMPARABLE',
            total_energy_delta_double_minus_single_J=list(map(str,(b0-a1,b1-a0))),
            total_energy_ratio_double_over_single=list(map(str,(b0/a1,b1/a0))),
            per_request_delta_single_minus_double_J=list(map(str,delta)),
            per_request_reduction_percent=list(map(str,(min(ratios),max(ratios)))),
            per_request_reduction_percent_approx=float(sum(delta)/(p0+p1)*100),
            conclusion='DOUBLE_PER_REQUEST_STRICTLY_LOWER' if q1<p0 else ('SINGLE_PER_REQUEST_STRICTLY_LOWER' if p1<q0 else 'NUMERICALLY_UNRESOLVED'),
            weighted_request_count=[one['weighted_requests_per_window'],two['weighted_requests_per_window']],
            shared_mapping_unchanged=one['shared_mapping']==two['shared_mapping'],
            caveat='fixed-window common/baseline amortization may lower per-request energy; not by itself better optimization')
    claims=list(root.glob('*_claim.json'));launches=list(root.glob('*_launch.json'))
    summary=dict(material_passport=dict(type='code_experiment_result',mode='run',status='COMPLETED_READ_ONLY_ACCOUNTING',
        scope='same R1 full-chain fixed platform H/auto-L, one vs two requests per application at release zero, unchanged individual deadlines'),
        authorization_id=auth['authorization_id'],source_sha=manifest['source_sha'],manifest_sha256=digest(manifest),
        consumed_plan_calls=sum(read(p)['phase']=='PLAN' for p in claims),consumed_post_calls=sum(read(p)['phase']=='POST' for p in claims),
        launched_plan_calls=sum('plan_launch' in p.name for p in launches),launched_post_calls=sum('post_launch' in p.name for p in launches),
        real_backend_entries=len(list(RUN.rglob('real_backend_entry.json'))),planned_plan_calls=2,retries=batch['retries'],
        planned_max_post_calls=2,formal_SAFE_slots=sum(s['state']=='POST_SAFE' for s in slots),batch_wall_s=batch['wall_s'],
        sum_plan_process_s=sum((s.get('plan_process_s') or 0) for s in slots),sum_post_process_s=sum((s.get('post_process_s') or 0) for s in slots),
        slots=slots,request_count_comparison=comparison,
        interpretation='single-run finite heuristic outcomes, no exact optimality, hardware measurement or statistical-stability claim')
    save(RUN/'analysis.json',summary);save(RUN/'domain_segments.json',domain_segments);save(RUN/'request_deadlines.json',request_rows)
    fields=['ordinal','problem_id','objective','deadline_beta','requests_per_application','weighted_requests_per_window','per_request_U_approx_J','min_deadline_slack_ms','state','post_U_approx_J','plan_U_approx_J','plan_process_s','post_process_s',
            'startup_s','first_safe_s','selected_at_s','candidate_attempts','unique_evaluations','cache_hits','score_improvements',
            'peak_temperature_upper_degC','reason','post_state','post_reason']
    with (RUN/'results.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(slots)
    with (RUN/'schedules.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['ordinal','problem_id','scene_id','stage_id','shared_stage_id','device_class','unit','opp','start_ms','duration_ms','end_ms']
        w=csv.DictWriter(f,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(all_stages)
    print(json.dumps({k:summary[k] for k in ('consumed_plan_calls','consumed_post_calls','formal_SAFE_slots','batch_wall_s','sum_plan_process_s','sum_post_process_s')}))
    for s in slots:print(json.dumps({k:s.get(k) for k in ('ordinal','problem_id','state','post_U_approx_J','first_safe_s','plan_process_s','post_process_s')},ensure_ascii=False))
    print(json.dumps({k:comparison.get(k) for k in ('state','conclusion','per_request_reduction_percent_approx')},ensure_ascii=False))

if __name__=='__main__':main()
