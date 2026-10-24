"""Independent stored-evidence audit: stdlib + immutable Git reads only.
No imports or execution of scheduling, numerical thermal or old audit modules.
"""
import csv,hashlib,json,subprocess
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,timezone
REF='c6df12309e3bbcdaec284be1e7a131707ca85f69'
PREFIX='research/chapter3_experiments/'
HERE=Path(__file__).resolve().parent
SOURCES={};CACHE={};CHECKS=[]
def raw(path):
    path=PREFIX+path
    if path not in CACHE:
        data=subprocess.check_output(['git','cat-file','blob',REF+':'+path])
        CACHE[path]=data
        SOURCES[path]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
          'git_blob_oid':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
    return CACHE[path]
def read(path):return json.loads(raw(path))
def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(encoded(v)).hexdigest()
def pair(v):return tuple(map(F,v))
def store(v):return [str(x) for x in v]
def check(name,passed,details=None):CHECKS.append({'name':name,'passed':bool(passed),'details':details})
def timely(v,n):return isinstance(v,(float,int)) and not isinstance(v,bool) and 0<=v<n

def audit_slot(k):
    resume='results/response_information_resume01/'
    plan=('results/response_information_execution01/' if k==1 else resume)+f'slot_{k}/planner_public/'
    audit=resume+f'slot_{k}/H_audit_private/'
    method=read(plan+'method/result.json');pj=read(plan+'job.json')
    aj=read(audit+'job.json');ret=read(audit+'worker_return.json');proc=read(audit+'process_receipt.json')
    out=ret['payload'];receipt=out['raw_receipt'];token=aj['token'];truth=aj['truth'];inst=truth['instance'];config=truth['config'];cand=json.loads(token['candidate_json']);accuracy=config['accuracy_targets']
    tag=f'slot{k}'
    check(tag+'_post_job_identity',ret['job_sha256']==sha(aj) and hashlib.sha256(token['candidate_json'].encode()).hexdigest()==token['candidate_raw_sha256'])
    check(tag+'_same_original_candidate',cand==method['safe_candidate'] and sha(cand)==token['candidate_raw_sha256'])
    check(tag+'_same_true_H_identity',inst['response_variant']=='H' and sha(inst)==token['truth_H_sha256'] and sha(config)==token['truth_H_config_sha256'] and receipt['evidence_identity']=={'input_sha256':sha(inst),'candidate_sha256':sha(cand)})
    check(tag+'_original_plan_identity',method['method']=='heft' and method['seed'] is None and pj['packet']['plan_sha256']==sha(pj['packet']['planner']['instance'])==method['input_sha256'])
    accepted=[r for r in method['evaluations'] if r.get('accepted_safe') is True]
    best=min(accepted,key=lambda r:F(r['evaluation']['safe_upper_bound_J']))
    check(tag+'_recorded_final_best',method['safe_candidate']==best['candidate'] and method['evaluation']==best['evaluation'] and method['safe_solution_source']==best['source'])
    check(tag+'_plan_timely_complete',method['reason']=='DECLARED_SEARCH_COMPLETED' and method['timing']['limit_s']==120 and timely(method['timing']['method_elapsed_s'],120) and all(timely(r['evaluation'].get('completed_at_elapsed_s'),120) for r in accepted))
    check(tag+'_post_existing_SAFE_timely',out['evidence_kind']=='REAL_CORE' and out['audit_status']=='TRUE_H_SAFE' and out['real_safe'] and not out['stop_required'] and receipt['state']=='SAFE' and not receipt['violations'] and aj['limit_s']==60 and out['root']['limit_s']==60 and timely(receipt['completed_at_elapsed_s'],60) and proc['returncode']==0 and not proc['watchdog_killed'])
    check(tag+'_post_no_model_or_candidate_repair',receipt['control_policy']=={'idle_policy':'auto_low_immediate_v1','idle_delay_ms':'0'} and receipt['numerical_protocol']=='directed-decimal60-taylor18-scaled100-v1')
    modes={(m['shared_stage_id'],m['unit_id'],m['opp_id']):m for rows in inst['stage_modes'].values() for m in rows}
    total_lo=total_hi=F(0);parts={n:[F(0),F(0)] for n in ('baseline','activity','external_common','temperature_correction')};shared={};max_peak=F(0);min_margin=None;stage_rows={};thermal_details={}
    node_order=inst['platform']['node_order'];valid=list(map(F,inst['platform']['power_model_temperature_range_degC']));window=F(inst['window_ms']);ext=F(inst['platform']['external_common_power_W'])*window/1000
    check(tag+'_scene_and_weight_coverage',set(receipt['scenes'])=={s['id'] for s in inst['scenarios']} and sum(F(s['weight']) for s in inst['scenarios'])==1)
    for scene in inst['scenarios']:
        sid=scene['id'];r=receipt['scenes'][sid];w=F(scene['weight']);stages={s['id']:s for s in scene['stage_instances']};requests={q['id']:q for q in scene['requests']};rows={};legal={x['stage_id']:x for x in receipt['legality']['scenes'][sid]['rows']}
        check(tag+'_'+sid+'_full_window_and_SAFE',r['state']=='SAFE' and r['complete'] and r['rankable_energy'] and r['energy_accuracy_met'] and F(r['covered_until_s'])==window/1000 and not r['violations'])
        check(tag+'_'+sid+'_stage_coverage',{x['stage_id'] for x in cand['scenes'][sid]}==set(stages) and len(cand['scenes'][sid])==len(stages))
        for row in cand['scenes'][sid]:
            st=stages[row['stage_id']];mode=modes[st['shared_stage_id'],row['unit'],row['opp']];req=requests[st['request_id']];start=F(row['start_ms']);end=start+F(mode['duration_ms']);sidrow=row['stage_id']
            check(tag+'_'+sidrow+'_exact_timing',start>=F(req['release_ms']) and end<=F(req['deadline_ms']) and end<=window and (start/F(inst['start_grid_ms'])).denominator==1 and F(legal[sidrow]['start_ms'])==start and F(legal[sidrow]['end_ms'])==end and F(legal[sidrow]['activity_power_W'])==F(mode['activity_power_W']))
            check(tag+'_'+sidrow+'_shared_mapping',st['shared_stage_id'] not in shared or shared[st['shared_stage_id']]==row['unit']);shared[st['shared_stage_id']]=row['unit']
            rows[sidrow]=(start,end,mode);stage_rows[sidrow]=dict(row)
        check(tag+'_'+sid+'_dependencies',all(rows[a][1]<=rows[b][0] for a,b in scene['dependencies']))
        values=list(rows.values())
        for x in range(len(values)):
            for y in range(x):
                a,z,m=values[x];b,t,n=values[y];overlap=max(a,b)<min(z,t)
                check(tag+'_'+sid+f'_resource_{x}_{y}',not overlap or (m['unit_id']!=n['unit_id'] and (m['domain_id']!=n['domain_id'] or m['opp_id']==n['opp_id'])))
        check(tag+'_'+sid+'_request_completion',all(max(rows[x][1] for x in q['stage_instance_ids'])==F(receipt['legality']['scenes'][sid]['request_completion_ms'][q['id']]) for q in requests.values()))
        lo,hi=pair(r['energy_J']);allowed=max(F(accuracy['energy_absolute_error_J']),F(accuracy['energy_relative_error'])*max(0,lo))
        check(tag+'_'+sid+'_scene_energy_precision',0<=lo<=hi and hi-lo<=allowed)
        components={n:pair(v) for n,v in r['energy_components_J'].items()}
        check(tag+'_'+sid+'_components_and_external',set(components)==set(parts) and lo<=sum(v[0] for v in components.values()) and sum(v[1] for v in components.values())<=hi and components['external_common'][0]<=ext<=components['external_common'][1])
        activity=sum((F(m['activity_power_W'])*(end-start)/1000 for start,end,m in rows.values()),F(0))
        check(tag+'_'+sid+'_independent_activity_sum',components['activity'][0]<=activity<=components['activity'][1])
        trace=r['trace'];times=[F(t['time_s']) for t in trace]
        check(tag+'_'+sid+'_trace_full_tail',bool(times) and F(0)<times[0] and all(a<b for a,b in zip(times,times[1:])) and times[-1]==window/1000)
        node_margin={}
        check(tag+'_'+sid+'_thermal_node_coverage',set(r['peaks_degC'])==set(r['minimum_degC'])==set(node_order))
        for ix,node in enumerate(node_order):
            peak=pair(r['peaks_degC'][node]);minimum=pair(r['minimum_degC'][node]);limit=F(scene['maximum_temperature_degC'][ix]);entry=F(scene['entry']['temperature_degC'][ix]);tol=F(accuracy['temperature_enclosure_width_K'])
            check(tag+'_'+sid+'_'+node+'_stored_continuous_bounds',valid[0]<=minimum[0]<=minimum[1]<=valid[1] and valid[0]<=peak[0]<=peak[1]<=min(limit,valid[1]) and peak[1]-peak[0]<=tol and minimum[1]-minimum[0]<=tol and minimum[0]<=entry<=peak[1])
            max_peak=max(max_peak,peak[1]);margin=limit-peak[1];min_margin=margin if min_margin is None else min(min_margin,margin);node_margin[node]=str(margin)
        thermal_details[sid]={'temperature_limit_margins_K':node_margin,'full_window_s':str(window/1000)}
        total_lo+=w*lo;total_hi+=w*hi
        for n,v in components.items():parts[n][0]+=w*v[0];parts[n][1]+=w*v[1]
    elo,ehi=pair(receipt['weighted_energy_J'])
    check(tag+'_weighted_energy_and_certificate',elo<=total_lo<=total_hi<=ehi and F(receipt['safe_upper_bound_J'])==ehi and pair([out['certified_energy']['lower'],out['certified_energy']['upper']])==(elo,ehi) and ehi-elo<=max(F(accuracy['energy_absolute_error_J']),F(accuracy['energy_relative_error'])*max(0,elo)))
    full_plan=None;outside_gap=None
    if k>1:
        pp=read(plan+'process_receipt.json');full_plan=aj['root_origin']-pj['root_origin'];outside_gap=full_plan-pp['process_wall_s_from_root'];check(tag+'_planning_to_post_root_within120',0<=full_plan<120)
    return {'ordinal':k,'problem_id':inst['id'],'view':token['view'],'truth_H_sha256':sha(inst),'truth_H_config_sha256':sha(config),'candidate_sha256':sha(cand),'energy_J':store((elo,ehi)),'energy_float_J':float((elo+ehi)/2),'energy_width_J':str(ehi-elo),'weighted_components_J':{n:store(v) for n,v in parts.items()},'stage_rows':stage_rows,'planning_packet':pj['packet'],'thermal':thermal_details,'maximum_peak_degC':str(max_peak),'minimum_limit_margin_K':str(min_margin),'planning_method_elapsed_s':method['timing']['method_elapsed_s'],'first_core_SAFE_s':method['first_safe_at_s'],'best_formed_s':method['evaluation']['completed_at_elapsed_s'],'post_evidence_formed_s':receipt['completed_at_elapsed_s'],'post_elapsed_s':out['root']['method_elapsed_s'],'full_planning_to_post_root_s':full_plan,'controller_export_gap_after_process_s':outside_gap,'recorded_post_status':out['audit_status']}

def main():
    declaration=read('results/response_information_resume_precheck01/execution_declaration.json')
    snapshot='results/response_information_resume_precheck01/source_snapshot/'
    for path,want in declaration['expected_sha'].items():
        rel=path[len(PREFIX):] if path.startswith(PREFIX) else None
        # Snapshot mirrors full repository paths under source_snapshot/.
        check('frozen_source:'+path,hashlib.sha256(raw(snapshot+path)).hexdigest()==want)
    for path,want in declaration['prior_sha256'].items():check('old_evidence:'+path,hashlib.sha256(raw(path[len(PREFIX):])).hexdigest()==want)
    slots=[audit_slot(k) for k in range(1,5)];pairs=[]
    claim_paths=subprocess.check_output(['git','-c','core.quotePath=false','ls-tree','-r','--name-only',REF,'--',PREFIX+'results/response_information_resume01/ledger'],text=True).splitlines()
    claim_names=sorted(Path(p).name for p in claim_paths if p.endswith('.claim.json'))
    check('only_original_three_plans_four_posts',claim_names==sorted(['slot_2.claim.json','slot_3.claim.json','slot_4.claim.json']+['audit_'+str(k)+'.claim.json' for k in range(1,5)]))
    for k in range(1,5):
        c=read(f'results/response_information_resume01/ledger/audit_{k}.claim.json')
        check(f'audit{k}_single60_claim',c['budget_s']==60)
        if k>1:
            c=read(f'results/response_information_resume01/ledger/slot_{k}.claim.json')
            check(f'plan{k}_single120_claim',c['budget_s']==120)
    old=read('results/response_information_execution01/ledger/slot_1.claim.json')
    check('old_plan120_not_refunded',old['budget_s']==120)
    old_outer=read('results/response_information_execution01_supervision/terminal.json')
    new_outer=read('results/response_information_resume01_supervision/terminal.json')
    check('segmented_calendar_within_original_cap',old_outer['calendar_elapsed_s']+new_outer['calendar_elapsed_s']<1200 and new_outer['calendar_elapsed_s']<1100 and new_outer['returncode']==0 and not new_outer['automatic_retry'])
    def diffs(a,b,path=()):
        if type(a) is not type(b): return [path]
        if isinstance(a,dict):
            if set(a)!=set(b): return [path]
            return [x for key in a for x in diffs(a[key],b[key],path+(key,))]
        if isinstance(a,list):
            if len(a)!=len(b):return [path]
            return [x for n in range(len(a)) for x in diffs(a[n],b[n],path+(n,))]
        return [] if a==b else [path]
    def allowed(path):
        return (path in [('config','defaults','response_variant'),('instance','response_variant'),('instance','settings','response_variant')]
          or (len(path)==6 and path[:2]==('config','stage_catalog') and path[3]=='profiles' and path[5]=='alpha')
          or (len(path)==3 and path[:2]==('instance','catalog_duration_weighted_mean_alpha'))
          or (len(path)==5 and path[:2]==('instance','stage_modes') and path[4] in ('alpha','duration_ms','activity_energy_J')))
    input_differences={}
    for pid in ('base__R1','base__R2'):
        hp=next(s['planning_packet']['planner'] for s in slots if s['problem_id']==pid and s['view']=='H')
        rp=next(s['planning_packet']['planner'] for s in slots if s['problem_id']==pid and s['view']=='R')
        ds=diffs(hp,rp);input_differences[pid]={'difference_count':len(ds),'all_whitelisted':all(allowed(x) for x in ds)}
        check(pid+'_only_whitelisted_response_changes',all(allowed(x) for x in ds))
        ri=rp['instance']; domains=ri['platform']['domains']
        check(pid+'_R_profiles_masked',all(F(v['alpha'])==1 for stage in rp['config']['stage_catalog'] for v in stage['profiles'].values()) and all(F(x)==1 for x in ri['catalog_duration_weighted_mean_alpha'].values()))
        check(pid+'_R_modes_unified_response',all(F(m['alpha'])==1 and F(m['duration_ms'])==F(m['d_ref_ms'])*F(domains[m['domain_id']]['opps'][domains[m['domain_id']]['reference_opp']]['frequency_GHz'])/F(m['frequency_GHz']) for rows in ri['stage_modes'].values() for m in rows))
    for slot in slots:slot.pop('planning_packet')

    for pid in ('base__R1','base__R2'):
        h=next(s for s in slots if s['problem_id']==pid and s['view']=='H');r=next(s for s in slots if s['problem_id']==pid and s['view']=='R');hl,hu=map(F,h['energy_J']);rl,ru=map(F,r['energy_J']);diff=(rl-hu,ru-hl);pct=(100*(1-hu/rl),100*(1-hl/ru));rev=(100*(1-ru/hl),100*(1-rl/hu))
        changes=[{'stage_id':sid,'H':h['stage_rows'][sid],'R':r['stage_rows'][sid]} for sid in h['stage_rows'] if h['stage_rows'][sid]!=r['stage_rows'][sid]]
        check(pid+'_same_true_H',h['truth_H_sha256']==r['truth_H_sha256'] and h['truth_H_config_sha256']==r['truth_H_config_sha256'])
        pairs.append({'problem_id':pid,'strict_winner':'H' if diff[0]>0 else 'R' if diff[1]<0 else 'UNRESOLVED','H_energy_J':h['energy_J'],'R_energy_J':r['energy_J'],'R_minus_H_J':store(diff),'H_saving_relative_to_R_percent':store(pct),'H_saving_relative_to_R_percent_float':list(map(float,pct)),'R_saving_relative_to_H_percent':store(rev),'R_saving_relative_to_H_percent_float':list(map(float,rev)),'weighted_R_minus_H_components_J':{n:store((F(r['weighted_components_J'][n][0])-F(h['weighted_components_J'][n][1]),F(r['weighted_components_J'][n][1])-F(h['weighted_components_J'][n][0]))) for n in h['weighted_components_J']},'changed_stage_rows':len(changes),'device_changes':sum(x['H']['unit']!=x['R']['unit'] for x in changes),'OPP_changes':sum(x['H']['opp']!=x['R']['opp'] for x in changes),'start_changes':sum(F(x['H']['start_ms'])!=F(x['R']['start_ms']) for x in changes),'changes':changes})
    terminal=read('results/response_information_resume01/terminal.json');check('four_existing_post_results',not terminal['stopped'] and len(terminal['slots'])==4)
    check('declared_original_total720',declaration['prior_method_budget_consumed_s']==120 and declaration['budgets']['scientific_total_s']==600 and declaration['cumulative_scientific_budget_s']==720)
    status={'scope':'READ_ONLY_EXISTING_GIT_EVIDENCE_NOT_REINTEGRATED','source_commit_sha':REF,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'passed':all(c['passed'] for c in CHECKS),'check_count':len(CHECKS),'failed_checks':[c for c in CHECKS if not c['passed']],'checks':CHECKS,'slots':slots,'pairs':pairs,'source_blobs':SOURCES,'input_differences':input_differences,'segmented_calendar_s':old_outer['calendar_elapsed_s']+new_outer['calendar_elapsed_s'],'new_research_calls':0,'new_TRUE_H_SAFE':0,'new_optimizer_or_thermal_calls':0,'verification_limit':'Existing thermal enclosure identities/inequalities/accounting checked; no RC reintegration or general kernel proof. Stored SAFE labels are not new research SAFE.'}
    (HERE/'facts.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (HERE/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['problem_id','view','energy_float_J','maximum_peak_degC','minimum_limit_margin_K','planning_method_elapsed_s','post_elapsed_s','recorded_post_status']);writer.writeheader()
        for s in slots:writer.writerow({k:s[k] for k in writer.fieldnames})
    print(json.dumps({'passed':status['passed'],'check_count':len(CHECKS),'failed':status['failed_checks'],'pairs':[{k:v for k,v in p.items() if k in ('problem_id','strict_winner','H_saving_relative_to_R_percent_float','R_saving_relative_to_H_percent_float','changed_stage_rows','device_changes','OPP_changes','start_changes')} for p in pairs],'source_files':len(SOURCES),'new_research_calls':0},ensure_ascii=False))
    return 0 if status['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
