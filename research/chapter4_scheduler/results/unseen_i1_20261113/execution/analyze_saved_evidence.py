"""Read-only receipt and mechanism analysis; no scientific imports or reruns."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

REPO=next(p for a in Path(__file__).resolve().parents for p in (a,a/'paper') if (p/'research/chapter4_scheduler/i1').is_dir())
OUT=REPO/'research/chapter4_scheduler/results/unseen_i1_20261113/execution'
PREVIOUS=REPO/'research/chapter4_scheduler/results/i1_paired_20261113'
GENERATED=OUT.parent/'input_generation'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def init_semantics(raw):
    m=raw.get('initialization') or {}
    result={k:m.get(k) for k in ('rule_version','status','stop_reason','fallback_used','active_priority',
        'quality_stages_completed','local_accepted','local_base_candidate','local_base_energy_J','first_SAFE_energy_J')}
    for label in ('construction_attempts','local_attempts'):
        result[label]=[{k:v for k,v in e.items() if k!='admitted_at_s'} for e in m.get(label,[])]
    return result


def main():
    plan,summary,batch=[read(OUT/n) for n in ('plan.json','summary.json','batch_return.json')]
    checks,details,raws={},[],{}
    def check(name,condition):checks[name]=bool(condition)
    check('six slots retained',len(plan['slots'])==len(summary['rows'])==len(batch['slots'])==6)
    check('no retry and identity intact',batch['retry_count']==0 and batch['frozen_identity_unchanged'])
    check('all frozen sources',all(sha(REPO/n)==sha(OUT/'source_snapshot'/n)==h for n,h in plan['source_sha256'].items()))
    previous=read(PREVIOUS/'plan.json')
    check('all512 prior sources unchanged',len(previous['source_sha256'])==512 and all(sha(REPO/n)==h for n,h in previous['source_sha256'].items()))
    check('only4 config instance files',len(plan['input_file_sha256'])==4 and all(n.endswith(('/instance.json','/config.json')) for n in plan['input_file_sha256']))
    check('all frozen inputs',all(sha(OUT/n)==h for n,h in plan['input_file_sha256'].items()))
    for slot in plan['slots']:
        key=slot['id'];folder=OUT/'calls'/key
        if not (folder/'method/result.json').exists():
            details.append({'id':key,'status':'NO_RAW_RESULT','batch_stop':batch['stop_reason']});continue
        raw,ret=read(folder/'method/result.json'),read(folder/'method_return.json');raws[key]=raw
        ins,cfg=read(folder/'method/input_instance.json'),read(folder/'method/input_config.json')
        check(key+':input',{'instance_sha256':digest(ins),'config_sha256':digest(cfg)}==plan['input_identities'][slot['case_id']] and ret['fresh_input_calls']==1)
        check(key+':I1 and ON OFF flag',raw['initialization_version']=='I1' and raw['evidence_kind']=='REAL_I1' and (slot['arm']=='HEFT' or raw['blocking_edge_adjustment_enabled']==(slot['arm']=='ON')))
        check(key+':root300',raw['timing']['limit_s']==300)
        check(key+':raw hash',sha(folder/'method/result.json')==ret['raw_result_sha256'])
        physical=[e for e in raw['evaluations'] if not e.get('cache_hit')]
        calls=[j for j in ret['evaluation_attempts_journal'] if j['state']=='RETURNED']
        check(key+':evaluation accounting',[e['candidate_sha256'] for e in physical]==[j['candidate_sha256'] for j in calls])
        safe=[e for e in physical if e.get('accepted_safe')]
        check(key+':complete timely SAFE',all(e['receipt']['state']=='SAFE' and e['receipt']['completed_at_elapsed_s']<=300
            and set(e['receipt']['scenes'])=={s['id'] for s in ins['scenarios']}
            and all(s['complete'] and F(s['covered_until_s'])==F(ins['window_ms'])/1000 for s in e['receipt']['scenes'].values()) for e in safe))
        meta=raw.get('initialization') or {}
        initial_physical=[e for e in physical if e['phase']=='initialization']
        check(key+':initial evaluation admission',all(e['evaluation_admitted_at_s']<180 for e in initial_physical))
        check(key+':initial construction admission',all(e['admitted_at_s']<180 for e in meta.get('construction_attempts',[])+meta.get('local_attempts',[])))
        check(key+':no initializer delay stage',not any(e['kind']=='one-start-delay' for e in meta.get('local_attempts',[])))
        steps=[];initial=raw.get('initial_safe_snapshot')
        if initial:
            current=initial;receipts={e['candidate_sha256']:e for e in raw['evaluations'] if e.get('accepted_safe')}
            for j,p in enumerate(raw.get('graph_proposals',[])):
                check(key+f':proposal base {j}',p['base_candidate_sha256']==current['candidate_sha256'])
                extra=p.get('additional_reversed_edges',[])
                check(key+f':edge count {j}',len(extra)<=1 and (slot['arm']=='ON' or not extra))
                if not p['strict_accepted']:continue
                new=receipts[p['candidate_sha256']]
                old_lo,old_hi=map(F,current['receipt']['weighted_energy_J']);new_lo,new_hi=map(F,new['receipt']['weighted_energy_J'])
                check(key+f':strict acceptance {j}',new_hi<old_lo)
                changes=[];fixed=True
                for sid,rs in new['candidate']['scenes'].items():
                    before={r['stage_id']:r for r in current['candidate']['scenes'][sid]}
                    for r in rs:
                        fixed=fixed and r['unit']==before[r['stage_id']]['unit']
                        if r!=before[r['stage_id']]:changes.append({'scene':sid,'before':before[r['stage_id']],'after':r})
                check(key+f':fixed deployment {j}',fixed)
                steps.append({'accepted_step':len(steps)+1,'proposal_index':j,'has_additional_edge':bool(extra),
                    'additional_reversed_edges':extra,'target':p.get('energy_target'),'selected_stages':p['selected_stages'],
                    'orientation':p['orientation'],'template':p['template'],'base_deadline_violations':p.get('base_deadline_violations'),
                    'base_blocking_traces':p.get('base_blocking_traces'),'old_energy_upper_J':str(old_hi),'new_energy_upper_J':str(new_hi),
                    'step_upper_difference_J':str(old_hi-new_hi),'candidate_sha256':new['candidate_sha256'],'changes':changes})
                current=new
            check(key+':steps agree with final',len(steps)==raw.get('graph_strict_improvements',0) and current['candidate']==raw['safe_candidate'])
        graph=raw.get('reconstruction_attempts',[])
        if slot['arm']=='OFF':check(key+':OFF no extra edge',not any(d.get('extra_resource_edge') for d in graph))
        post=read(folder/'post_return.json') if (folder/'post_return.json').exists() else None
        if post:
            check(key+':single successful post',post.get('passed') and len(post['evaluation_attempts_journal'])==1 and post['timing']['limit_s']==60)
            lo,hi=map(F,raw['evaluation']['weighted_energy_J'])
            check(key+':post interval overlap',max(lo,F(post['energy']['lower']))<=min(hi,F(post['energy']['upper'])))
        extra_graph=[d for d in graph if d.get('extra_resource_edge')]
        costs={phase:sum(j['returned_at_s']-j['started_at_s'] for e,j in zip(physical,calls) if e['phase']==phase) for phase in ('initialization','refinement')}
        durations=[j['returned_at_s']-j['started_at_s'] for j in calls]
        phase_costs={}
        for phase in ('initialization','refinement'):
            ds=[j['returned_at_s']-j['started_at_s'] for e,j in zip(physical,calls) if e['phase']==phase]
            phase_costs[phase]={'returned_count':len(ds),'sum_s':sum(ds),'mean_s':sum(ds)/len(ds) if ds else None,'max_s':max(ds) if ds else None}
        interruptions=[j for j in ret['evaluation_attempts_journal'] if j['state']!='RETURNED']
        construction=[{k:e.get(k) for k in ('opp_rank','priority_policy','status','reason','failed_shared_stage','assessment_state','admitted_at_s')} for e in meta.get('construction_attempts',[])]
        details.append({'id':key,
            'initialization_semantics_sha256':digest(init_semantics(raw)),'first_SAFE_energy_J':meta.get('first_SAFE_energy_J'),
            'accepted_steps':steps,'graph_states':dict(Counter(d['state'] for d in graph)),
            'graph_reasons':dict(Counter(d.get('reason') for d in graph if d.get('reason'))),
            'extra_graph_states':dict(Counter(d['state'] for d in extra_graph)),
            'extra_graph_reasons':dict(Counter(d.get('reason') for d in extra_graph if d.get('reason'))),
            'extra_accepted_step_difference_J':str(sum((F(s['step_upper_difference_J']) for s in steps if s['has_additional_edge']),F(0))),
            'ordinary_accepted_step_difference_J':str(sum((F(s['step_upper_difference_J']) for s in steps if not s['has_additional_edge']),F(0))),
            'complete_evaluation_cost_s':costs,'returned_evaluation_statistics':phase_costs,
            'all_returned_evaluation_mean_s':sum(durations)/len(durations) if durations else None,
            'all_returned_evaluation_max_s':max(durations) if durations else None,
            'returned_evaluation_share_of_method_percent':100*sum(durations)/ret['timing']['method_elapsed_s'],
            'interrupted_evaluation_journal':interruptions,
            'initialization_construction_attempts':construction,
            'initial_local_attempt_counts':dict(Counter(e['kind'] for e in meta.get('local_attempts',[]))),
            'initial_local_accept_count':meta.get('local_accepted'),
            'quality_stages_completed':meta.get('quality_stages_completed'),
            'initial_fallback_attempts':sum(e.get('priority_policy')=='deadline_scarcity' for e in meta.get('construction_attempts',[])),
            'initial_construction_states':dict(Counter(e['status'] for e in meta.get('construction_attempts',[]))),
            'admission_stop':meta.get('admission_stop'),
            'initial_evaluations_crossing180':sum(e['returned_at_s']>=180 for e in initial_physical),
            'post_process_wall_s':read(folder/'post_command_return.json')['wall_s'] if post else None})
    pairs=[]
    for c in summary['comparisons']:
        arms={s['arm']:s for s in plan['slots'] if s['case_id']==c['case_id']}
        if any(s['id'] not in raws for s in arms.values()):pairs.append({**c,'audit_status':'MISSING_RAW'});continue
        on,off=raws[arms['ON']['id']],raws[arms['OFF']['id']]
        pairs.append({**c,'same_initialization_semantics':init_semantics(on)==init_semantics(off),
            'both_searches_completed':all(r['run_terminal']=='SEARCH_COMPLETED' for r in (on,off)),
            'ON_OFF_net_upper_difference_J':str(F(off['evaluation']['weighted_energy_J'][1])-F(on['evaluation']['weighted_energy_J'][1])) if c['both_final_SAFE_post_passed'] else None})
    manifest=read(GENERATED/'inputs_manifest.json')
    check('generation manifest identity',sha(GENERATED/'inputs_manifest.json')==plan['generation_manifest_sha256'])
    check('generation before algorithm without screening',manifest['counters']=={'parameter_roots':2,'mapping_constructions':2,'H_timetable_constructions':2,'scene_schedules':4,'thermal_evaluations':0,'HEFT_ON_OFF_SA_calls':0,'retries':0,'replacements':0})
    generation=[]
    for case in manifest['cases']:
        for kind in ('config','instance','generation_evidence'):
            check(case['case_id']+':generated '+kind,sha(GENERATED/case[kind+'_path'])==case[kind+'_sha256'])
        e=read(GENERATED/case['generation_evidence_path']);prov=e['unprojected_eight_scene_bundle']['provenance']
        check(case['case_id']+':new root provenance',prov['namespace']=='ch4-independent-i1-v1' and prov['root_id']==case['root_id'] and prov['seed']==case['seed'] and prov['scale']==12)
        check(case['case_id']+':static not reference injection',e['static_check']['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED' and e['static_check']['thermal_evaluations']==0 and e['adaptation_receipt']['formal_initial_solution'] is None and e['adaptation_receipt']['fixed_deployment'] is None)
        generation.append({'case_id':case['case_id'],'seed':case['seed'],'namespace':prov['namespace'],'static_state':e['static_check']['state'],'metrics':case['metrics']})
    triple_audit=[]
    for triple in summary['three_arm_comparisons']:
        members=[raws[r['id']] for r in summary['rows'] if r['case_id']==triple['case_id'] and r['id'] in raws]
        triple_audit.append({**triple,'all3_same_initialization_semantics':len(members)==3 and all(init_semantics(r)==init_semantics(members[0]) for r in members)})
    result={'passed':all(checks.values()),'checks':checks,'checks_passed':sum(checks.values()),'details':details,'pairs':pairs,'three_arm_comparisons':triple_audit,'generation':generation,
        'scope':'Read-only archived receipt/trajectory analysis; no scientific rerun, no same-evaluator independence claim.'}
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'failed':[k for k,v in checks.items() if not v],'pairs':pairs,'three_arm_comparisons':triple_audit},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
