"""Audit only existing paired receipts; new search/thermal integration forbidden."""
from collections import Counter,defaultdict
from contextlib import ExitStack
from datetime import datetime,timezone
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/'research/chapter3_experiments')]
from research.chapter4_scheduler.thermal_pair.run import verify,initialization_diagnostic,SLOTS
from research.chapter4_scheduler.thermal_pair.input import validate_pair
from research.chapter4_scheduler.comparison.core import normalize,EvaluationJournal,CLOCK_ORIGIN
from research.chapter4_scheduler.mechanism_check.run import read,save,digest,sha
from h02_pair_preflight.receipts import safe_receipt,thermal_witness
from schedules import validate_schedule

began=time.monotonic();started=datetime.now(timezone.utc).isoformat();checks=[];records=[];observations={};tokens=[]
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError('READ_ONLY_AUDIT_FORBIDS_NEW_PHYSICS_OR_SEARCH')
def differences(a,b,path=''):
    if type(a)!=type(b):return [path]
    if isinstance(a,dict):
        if set(a)!=set(b):return [path]
        return [v for k in sorted(a) for v in differences(a[k],b[k],path+'/'+k)]
    if isinstance(a,list):
        if len(a)!=len(b):return [path]
        return [v for n,(x,y) in enumerate(zip(a,b)) for v in differences(x,y,path+'/'+str(n))]
    return [] if a==b else [path]
execution=OUT/'execution';plan=read(execution/'plan.json');batch=read(execution/'batch_return.json')
with ExitStack() as stack:
    for target in ('thermal.evaluate_candidate','thermal.evaluate_piecewise','heft_method.run_heft','heft_method.build_heft_candidate','sa_method.run_sa'):
        stack.enter_context(patch(target,side_effect=deny))
    verify(plan,protected=True)
    check('plan hash intact',sha(execution/'plan.json')==read(execution/'plan_identity.json')['sha256'])
    check('exact two method claims',batch['completed'] and not batch['error'] and batch['consumed_method_slots']==[s['id'] for s in SLOTS])
    config50=read(execution/'frozen_inputs/T50/input_config.json');config78=read(execution/'frozen_inputs/T78/input_config.json')
    instance50=read(execution/'frozen_inputs/T50/input_instance.json');instance78=read(execution/'frozen_inputs/T78/input_instance.json')
    config_delta=differences(config50,config78);input_delta=differences(instance50,instance78)
    check('only mirrored default changed',config_delta==['/defaults/initial_temperature_degC'])
    check('only eight scene initial temperatures changed',input_delta==[f'/scenarios/{s}/entry/temperature_degC/{n}' for s in (0,1) for n in range(4)])
    for slot in SLOTS:
        name=slot['id'];folder=execution/'calls'/name;r=read(folder/'method_return.json');raw=read(folder/'method/result.json')
        config=read(folder/'method/input_config.json');instance=read(folder/'method/input_instance.json');expected=plan['inputs'][slot['temperature']]
        check(name+': exact derived input',(digest(config),digest(instance))==(expected['config_sha256'],expected['input_sha256']))
        check(name+': only initial-temperature variation',validate_pair(config,instance,slot['temperature']))
        root=raw['root_context'];tokens.append(root['root_token'])
        check(name+': actual300s fixed root',root['root_seconds']==r['timing']['limit_s']==300 and float(root['root_deadline'])-float(root['root_start'])==300)
        check(name+': independent load and no shared candidate/cache',r['fresh_input_calls']==1 and raw['candidate_or_cache_shared_between_calls'] is False)
        check(name+': raw archive immutable',sha(folder/'method/result.json')==r['raw_result_sha256'])
        journal=EvaluationJournal(deny,object());journal.attempts=r['evaluation_attempts_journal'];normal=normalize(raw,journal)
        check(name+': transparent counts reproduced',all(r[k]==v for k,v in normal.items()))
        check(name+': distinct initialization vs ON result',r['initialization_diagnostic']==initialization_diagnostic(raw))
        events=[json.loads(line) for line in (folder/'method_evaluation_journal.jsonl').read_text().splitlines()]
        physical=[row for row in raw['evaluations'] if not row.get('cache_hit',False)]
        check(name+': all physical journal calls accounted',sum(e['event']=='START' for e in events)==sum(e['event']=='RETURN' for e in events)==len(physical)==r['counts']['evaluation_attempts'])
        phase_states=defaultdict(Counter);violations=[];by_hash={};safe=[]
        for index,row in enumerate(raw['evaluations']):
            receipt=row['receipt'];identity=row['candidate_sha256']
            check(name+': candidate identity '+str(index),digest(row['candidate'])==identity)
            check(name+': evidence identity '+str(index),receipt['evidence_identity']=={'input_sha256':expected['input_sha256'],'candidate_sha256':identity})
            check(name+': full DAG/resource/window legality '+str(index),validate_schedule(instance,row['candidate'])==receipt['legality'])
            if not row.get('cache_hit',False):
                phase_states[row['phase']][receipt['state']]+=1
                by_hash[identity]={'state':receipt['state'],'source':row['source'],'phase':row['phase'],'violations':receipt.get('violations',[]),'energy':receipt.get('weighted_energy_J')}
            if row.get('accepted_safe'):
                check(name+': original complete SAFE gate '+str(index),safe_receipt(instance,row['candidate'],receipt,config['accuracy_targets'],300)==row['energy'])
                check(name+': timely full two-scene coverage '+str(index),0<=receipt['completed_at_elapsed_s']<300 and set(receipt['scenes'])=={'C1','C2'} and all(s['complete'] and F(s['covered_until_s'])==F(23,100) for s in receipt['scenes'].values()))
                safe.append(row)
            elif receipt['state']=='THERMAL_VIOLATION':
                points=thermal_witness(instance,receipt,300)
                check(name+': real timely over-limit point '+str(index),bool(points) and len(points)==len(receipt['violations']))
                check(name+': unsafe energy not rankable '+str(index),not receipt['rankable_energy'] and receipt['weighted_energy_J'] is None)
                violations.append({'candidate_sha256':identity,'source':row['source'],'phase':row['phase'],'reason':receipt['reason'],'point_witnesses':points,
                    'scene_coverage':{sid:{k:v.get(k) for k in ('state','complete','covered_until_s','reason')} for sid,v in receipt['scenes'].items()}})
        observations[slot['temperature']]=by_hash
        initialization=raw.get('initial_safe_snapshot');final=raw.get('evaluation');post=None;peak=None;margin=None
        if final:
            check(name+': own final backed by SAFE history',any(row['candidate_sha256']==digest(raw['safe_candidate']) and row['receipt']==final for row in safe))
            post=read(folder/'post_return.json');receipt=read(folder/'post_receipt.json');energy=safe_receipt(instance,raw['safe_candidate'],receipt,config['accuracy_targets'],60)
            check(name+': complete fresh same-evaluator post',post['passed'] and post['error'] is None and energy==post['energy'] and receipt['completed_at_elapsed_s']<60)
            check(name+': overlapping post energy',max(F(energy['lower']),F(final['weighted_energy_J'][0]))<=min(F(energy['upper']),F(final['weighted_energy_J'][1])))
            check(name+': corrected post root/phase',post['timing']['limit_s']==60 and post['timing']['clock_origin']==CLOCK_ORIGIN and 'complete_post_evaluation' in post['timing']['phases_exclusive_s'])
            peak=max(F(interval[1]) for scene in final['scenes'].values() for interval in scene['peaks_degC'].values());margin=F(80)-peak
            check(name+': final whole-window thermal margin',margin>=0)
        else:check(name+': no safe result is not ON completed',not r['initialization_diagnostic']['ON_search_completed'] and not (folder/'post_claim.json').exists())
        meta=raw.get('initialization') or {};structural=Counter((event.get('state'),event.get('reason')) for event in raw.get('reconstruction_attempts',[]) if event.get('state')!='COMPLETE_LEGAL_CANDIDATE')
        records.append({'slot':slot,'normal_stop':r['normal_stop'],'terminal':r['terminal'],'reason':r['raw_reason'],'initialization_diagnostic':r['initialization_diagnostic'],
            'counts':r['counts'],'phase_physical_states':{k:dict(v) for k,v in phase_states.items()},'thermal_violations':violations,
            'initial_SAFE_candidate_sha256':initialization['candidate_sha256'] if initialization else None,'initial_SAFE_energy':initialization['energy'] if initialization else None,
            'final_candidate_sha256':digest(raw['safe_candidate']) if final else None,'final_energy_interval_J':final['weighted_energy_J'] if final else None,
            'maximum_peak_upper_degC':str(peak) if peak is not None else None,'minimum_limit_margin_K':str(margin) if margin is not None else None,
            'scene_energy_and_peaks':{sid:{k:s[k] for k in ('energy_J','energy_components_J','peaks_degC','violations','covered_until_s')} for sid,s in final['scenes'].items()} if final else None,
            'graph_proposals':len(raw['graph_proposals']),'graph_strict_improvements':raw['graph_strict_improvements'],'reconstruction_attempts':len(raw['reconstruction_attempts']),
            'structural_rejects_not_thermal':[{'state':k[0],'reason':k[1],'count':v} for k,v in structural.items()],
            'HEFT_construction_attempts':[{k:event.get(k) for k in ('status','reason','opp_rank','duplicate_construction')} for event in meta.get('construction_attempts',[])],
            'HEFT_local_nonthermal_construction_failures':dict(Counter(event.get('reason') for event in meta.get('local_attempts',[]) if event.get('construction_status')!='COMPLETE_LEGAL_CANDIDATE')),
            'method_timing':r['timing'],'method_process':read(folder/'worker_command_return.json'),
            'post_timing':post['timing'] if post else None,'post_process':read(folder/'post_command_return.json') if post else None,
            'first_SAFE_s':r['first_SAFE_at_s'],'first_own_final_quality_s':r['first_own_final_quality_at_s'],'post_passed':post.get('passed',False) if post else False})
    check('unique independent caller roots',len(set(tokens))==2)
    for relative,expected in plan['source_sha256'].items():
        if '/results/' not in relative:check('frozen source copy '+relative,sha(execution/'source_snapshot'/relative)==expected)
    check('original common contract frozen unchanged',sha(execution/'original_common_input.json')==plan['input_file_sha256'])
    common=sorted(set(observations['50'])&set(observations['78']))
    matched=[{'candidate_sha256':key,'T50':observations['50'][key],'T78':observations['78'][key]} for key in common]
    states=dict(Counter(a['T50']['state']+' -> '+a['T78']['state'] for a in matched))
audit={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-began,'passed':True,'assertion_count':len(checks),
    'checks':checks,'real_new_search_or_thermal_calls':0,'frozen_source_identities_verified':len(plan['source_sha256']),'protected_existing_files_verified':len(plan['protected_sha256'])}
save(OUT/'audit.json',audit)
save(OUT/'metrics.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':sha(execution/'plan.json'),'batch':batch,'rows':records,
    'only_changed_config_paths':config_delta,'only_changed_instance_paths':input_delta,
    'same_candidate_physical_comparisons':matched,'same_candidate_state_pairs':states,
    'analysis_scope':'Read-only original receipts, no replay. Same evaluator post, not independent implementation. Distinguish inherited HEFT safety filtering from ON incremental result.'})
print(json.dumps({'passed':True,'assertions':len(checks),'rows':len(records),'matched_physical_candidates':len(common),'matched_states':states,'wall_s':audit['wall_s']},ensure_ascii=False),flush=True)
