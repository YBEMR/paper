"""K176 stored-evidence gate. No solver, decoder, policy replay or thermal imports."""
from copy import deepcopy
from decimal import Decimal, Context, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
LIMIT=300
DEADLINE_REASONS={'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED','BUDGET_BEFORE_FINAL_ADMISSION',
    'BUDGET_DURING_ADMISSION_ARCHIVE','ROOT_BUDGET_EXHAUSTED','BUDGET_DURING_CANDIDATE_EVALUATION'}
BAD={'INTERFACE_ERROR','RESOURCE_LIMIT','SOLVER_INTERFACE_ERROR','INVALID_INPUT_OR_INTERFACE',
    'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED','NUMERICAL_CANDIDATE_ANOMALY','INITIALISATION_ERROR'}
NORMAL={'NORMAL_COMPLETION','NORMAL_TIME_LIMIT','NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def receipt_hash(v):return canonical({k:x for k,x in v.items() if k!='receipt_sha256'})
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def interval(v):
    if not isinstance(v,list) or len(v)!=2:raise ValueError('two-sided interval required')
    a,b=map(F,v)
    if not 0<=a<=b:raise ValueError('invalid nonnegative interval')
    return a,b
def case_spec(d,s):
    rows=[c for c in d['cases'] if c['common']['case_id']==s['case_id']]
    if len(rows)!=1:raise ValueError('case identity')
    return rows[0]

def schedule_audit(instance,candidate):
    """Exact label/time legality and per-request slack; no temperature work."""
    errors=[];margins=[];shared={};prepared={}
    try:
        scenes={s['id']:s for s in instance['scenarios']}
        if set(candidate['scenes'])!=set(scenes):raise ValueError('scene coverage')
        grid,window=F(instance['start_grid_ms']),F(instance['window_ms'])
        for sid,scene in scenes.items():
            copies={s['id']:s for s in scene['stage_instances']};rows=candidate['scenes'][sid]
            if len(rows)!=len(copies) or {r['stage_id'] for r in rows}!=set(copies):raise ValueError('stage coverage')
            requests={r['id']:r for r in scene['requests']};activities={}
            for r in rows:
                stage=copies[r['stage_id']]
                modes=[m for m in instance['stage_modes'][stage['shared_stage_id']] if m['unit_id']==r['unit'] and m['opp_id']==r['opp']]
                if len(modes)!=1:raise ValueError('mode identity')
                m=modes[0];start=F(r['start_ms']);end=start+F(m['duration_ms']);req=requests[stage['request_id']]
                if start<max(F(0),F(req['release_ms'])) or start/grid!=(start//grid) or end>window:errors.append('START_WINDOW:'+sid+':'+r['stage_id'])
                identity=stage['shared_stage_id']
                if identity in shared and shared[identity]!=r['unit']:errors.append('SHARED_DEPLOYMENT:'+identity)
                shared[identity]=r['unit']
                activities[r['stage_id']]={'start':start,'end':end,'unit':r['unit'],'opp':r['opp'],'domain':m['domain_id'],'request':stage['request_id']}
            for a,b in scene['dependencies']:
                if activities[a]['end']>activities[b]['start']:errors.append('DEPENDENCY:'+sid+':'+a+'->'+b)
            items=list(activities.items())
            for i,(ak,a) in enumerate(items):
                for bk,b in items[i+1:]:
                    if max(a['start'],b['start'])<min(a['end'],b['end']):
                        if a['unit']==b['unit']:errors.append('RESOURCE:'+sid+':'+ak+':'+bk)
                        if a['domain']==b['domain'] and a['opp']!=b['opp']:errors.append('DOMAIN_OPP:'+sid+':'+ak+':'+bk)
            for rid,req in requests.items():
                finish=max(a['end'] for a in activities.values() if a['request']==rid)
                slack=F(req['deadline_ms'])-finish
                margins.append({'scene_id':sid,'request_id':rid,'completion_ms':str(finish),'deadline_ms':str(F(req['deadline_ms'])),'slack_ms':str(slack)})
                if slack<0:errors.append('DEADLINE:'+sid+':'+rid)
            prepared[sid]=activities
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as e:errors.append('MALFORMED_SCHEDULE:'+str(e))
    return {'passed':not errors,'errors':errors,'request_slack':margins,
        'minimum_deadline_slack_ms':str(min(F(r['slack_ms']) for r in margins)) if margins else None,
        'new_candidate_generated':False,'thermal_evaluation_performed':False}

def _outward_weighted(receipt,instance):
    down,up=Context(prec=60,rounding=ROUND_FLOOR),Context(prec=60,rounding=ROUND_CEILING)
    lo=hi=Decimal(0);elo=ehi=F(0)
    for s in instance['scenarios']:
        sid=s['id'];a,b=interval(receipt['scenes'][sid]['energy_J']);w=F(s['weight'])
        if w<0:raise ValueError('negative weight')
        elo+=w*a;ehi+=w*b
        wl=down.divide(Decimal(w.numerator),Decimal(w.denominator));wh=up.divide(Decimal(w.numerator),Decimal(w.denominator))
        al,ah=map(Decimal,receipt['scenes'][sid]['energy_J'])
        pairs=[(x,y) for x in (al,ah) for y in (wl,wh)]
        lo=down.add(lo,min(down.multiply(x,y) for x,y in pairs));hi=up.add(hi,max(up.multiply(x,y) for x,y in pairs))
    stored=interval(receipt['weighted_energy_J'])
    return stored==(F(lo),F(hi)) and stored[0]<=elo<=ehi<=stored[1]

def aggregate_issues(receipt,candidate,instance,config,common,budget,sources):
    errors=[]
    try:
        if receipt['state']!='SAFE' or receipt['rankable_energy'] is not True or receipt['safe_candidate']!=candidate or receipt['receipt_sha256']!=receipt_hash(receipt):errors.append('AGGREGATE_STRUCTURE')
        identity=receipt['identity'];expected_sources={Path(k).name:v for k,v in sources.items() if Path(k).name in {'scene_adapter.py','schedules.py','thermal.py','start_domain.py','interval.py','control_policy.py'}}
        expect={'full_input_sha256':common['input_sha256'],'candidate_sha256':canonical(candidate),
            'budget':budget,'source_sha256':expected_sources,'accuracy_sha256':canonical(config['accuracy_targets']),
            'control_policy':common['control_policy'],'platform_sha256':canonical(instance['platform']),
            'execution_rules_sha256':canonical(instance['execution_rules']),
            'shared_deployment_sha256':canonical(common['shared_deployment'])}
        if any(identity.get(k)!=v for k,v in expect.items()):errors.append('AGGREGATE_IDENTITY')
        if receipt['problem_id']!=instance['id'] or receipt['legality']['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED':errors.append('AGGREGATE_LEGALITY')
        stamp=receipt['completed_at_elapsed_s']
        if not finite(stamp) or not 0<=stamp<LIMIT:errors.append('AGGREGATE_LATE')
        if F(receipt['safe_upper_bound_J'])!=interval(receipt['weighted_energy_J'])[1]:errors.append('AGGREGATE_U')
        if set(receipt['scenes'])!={s['id'] for s in instance['scenarios']}:errors.append('AGGREGATE_SCENES')
        for scene in instance['scenarios']:
            sid=scene['id'];r=receipt['scenes'][sid];p=r['result'];si=r['identity'];local={'scenes':{sid:candidate['scenes'][sid]}}
            if (r['state']!='SAFE' or r['rankable_energy'] is not True or r['receipt_sha256']!=receipt_hash(r)
                or r['scenario_id']!=sid or r['legality']['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED'
                or p['state']!='SAFE' or p['complete'] is not True or p['rankable_energy'] is not True):errors.append('SCENE_STRUCTURE:'+sid)
            for k in ('full_input_sha256','budget','source_sha256','accuracy_sha256','control_policy','platform_sha256','execution_rules_sha256','shared_deployment_sha256'):
                if si.get(k)!=expect[k]:errors.append('SCENE_IDENTITY:'+sid+':'+k)
            if si.get('candidate_sha256')!=canonical(local) or si.get('scenario_sha256')!=canonical(scene) or si.get('entry_sha256')!=canonical(scene['entry']):errors.append('SCENE_CANDIDATE_ENTRY:'+sid)
            if not finite(r['completed_at_elapsed_s']) or not 0<=r['completed_at_elapsed_s']<=stamp<LIMIT:errors.append('SCENE_LATE:'+sid)
            window=F(instance['window_ms'])/1000
            if F(p['covered_until_s'])!=window or F(p['trace'][-1]['time_s'])!=window:errors.append('SCENE_COVERAGE:'+sid)
            limits=dict(zip(instance['platform']['node_order'],scene['maximum_temperature_degC']))
            if set(p['peaks_degC'])!=set(limits):errors.append('SCENE_NODES:'+sid)
            for node,limit in limits.items():
                a,b=map(F,p['peaks_degC'][node])
                if a>b or b>F(limit):errors.append('SCENE_PEAK:'+sid+':'+node)
            if interval(r['energy_J'])!=interval(p['energy_J']) or F(r['safe_upper_bound_J'])!=interval(r['energy_J'])[1]:errors.append('SCENE_ENERGY:'+sid)
        if not _outward_weighted(receipt,instance):errors.append('OUTWARD_WEIGHTED_ENERGY')
    except (KeyError,TypeError,ValueError,IndexError,ZeroDivisionError) as e:errors.append('MALFORMED_AGGREGATE:'+str(e))
    return errors

def _has_error(v):
    if isinstance(v,dict):
        return any(((k in ('error','errors') or k.endswith(('_error','_errors')) or 'pending' in k) and x not in (None,False,'',[],{})) or _has_error(x) for k,x in v.items())
    return isinstance(v,list) and any(_has_error(x) for x in v)
def cleanup_ok(r):
    if not isinstance(r,dict) or _has_error(r):return False
    code=r.get('returncode')
    if type(code) is not int:return False
    if 'cleanup_status' not in r:return code==0
    v=r.get('process_tree_verification') or {};ids=v.get('identities');n=r.get('observed_tree_identity_count')
    if not isinstance(ids,list) or type(n) is not int or n<=0 or n!=len(ids) or any(r.get(k) is not True for k in ('observed_tree_verified_terminated','observed_tree_capture_complete')) or v.get('capture_complete') is not True or v.get('verified_terminated') is not True:return False
    if any(type(x.get('pid')) is not int or x['pid']<=0 or not finite(x.get('create_time')) or x['create_time']<=0 or x.get('state') not in ('EXITED','PID_REUSED_ORIGINAL_EXITED') for x in ids):return False
    return ((r.get('cleanup_status')=='graceful_closed' and code==0 and r.get('force_requested') is False) or (r.get('cleanup_status')=='forced_closed' and r.get('force_requested') is True and r.get('force_termination_succeeded') is True and (r.get('own_process_tree_kill_returncode')==0 or r.get('own_process_kill_succeeded') is True)))

def phase_records(result):
    return result.get('phases') or [{'phase_index':1,'name':'N1','started_at_s':0,'completed_at_s':result.get('timing',{}).get('method_elapsed_s'),'scenes':result.get('scenes',{})}]

def _terminal(result,folder):
    """Only a final root-cancelled request may remain incomplete."""
    errors=[];numeric=[];pending=False;rounds=[]
    deadline=(result.get('reason')=='wall_time_limit' and result.get('budget_exhausted') is True and result.get('timing',{}).get('limit_s')==300 and finite(result.get('timing',{}).get('method_elapsed_s')) and result['timing']['method_elapsed_s']>=300)
    if result.get('error') or result.get('cleanup_error'):errors.append('METHOD_ERROR')
    for p in phase_records(result):
        for sid,s in p.get('scenes',{}).items():
            solved=s.get('solver_result') or {}
            if solved.get('reason') in BAD or solved.get('error'):errors.append('SCENE_TECHNICAL:'+sid)
            if solved.get('reason') in ('EVALUATION_UNRESOLVED','FEEDBACK_UNRESOLVED') and not deadline:errors.append('SCENE_EVALUATION_UNRESOLVED:'+sid)
            rounds.extend(solved.get('rounds',[]))
    for r in rounds:
        if (r.get('numerical_consistency') or {}).get('state')=='NUMERICAL_ADMISSION_STATUS_CONFLICT':numeric.append('NUMERICAL_ADMISSION_STATUS_CONFLICT')
        if r.get('status') in ('ERROR','WORKER_EXITED') or r.get('error'):errors.append('NATIVE_TECHNICAL')
    for request in (result.get('augmented_transport') or {}).get('requests',[]):
        for c in request.get('numerical_checks',[]):
            if (c.get('report') or {}).get('accepted') is False:numeric.append('ORIGINAL_NUMERICAL_REPORT_REJECTED')
        incomplete=(request.get('latched_unresolved') is not False or request.get('callback_publications_complete') is not True or request.get('expected_callback_numbers')!=request.get('checked_callback_numbers'))
        if incomplete and not (deadline and request.get('cancel_requested') is True and set(request.get('failure_reasons') or [])<=DEADLINE_REASONS):errors.append('AUGMENTED_COVERAGE_UNRESOLVED')
    invalid=[(i,r) for i,r in enumerate(rounds) if r.get('status')!='SOLVED' or r.get('budget_valid') is not True]
    if invalid:
        if len(invalid)!=1 or invalid[0][0]!=len(rounds)-1 or not deadline:errors.append('EARLIER_OR_UNEXPLAINED_REQUEST_UNRESOLVED')
        else:
            r=invalid[0][1];number=r.get('request_number')
            try:
                py=read(Path(folder)/'method/matlab'/f'request_{number:06d}.python.json')
                inp=read(Path(folder)/'method/matlab'/f'request_{number:06d}.input.json')
                bid=result['condition']['budget_identity']
                okay=(py.get('request_number')==number and inp.get('request_number')==number
                    and py.get('status')=='BUDGET_EXHAUSTED' and py.get('budget_valid') is False
                    and py.get('accepted_for_evaluation') is False and py.get('x')==[]
                    and inp.get('method_deadline_bound') is True and F(str(inp['absolute_deadline']))==F(bid['start'])+300
                    and set((py.get('publication_read') or {}).get('transient_read_errors') or {})<={'FileNotFoundError'})
                if not okay:errors.append('ROOT_CANCEL_EVIDENCE_INCOMPLETE')
                else:pending=True
            except (OSError,KeyError,TypeError,ValueError):errors.append('ROOT_CANCEL_ARCHIVE_MISSING')
    if numeric:return 'NUMERICAL_ANOMALY_OBSERVED',errors,numeric,pending
    if errors:return 'TECHNICAL_OR_COVERAGE_UNRESOLVED',errors,numeric,pending
    if deadline:return ('NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST' if pending else 'NORMAL_TIME_LIMIT'),errors,numeric,pending
    if result.get('reason')=='SCENE_SEARCH_SEQUENCE_COMPLETE' and not result.get('search_failure_latched'):
        return 'NORMAL_COMPLETION',errors,numeric,pending
    return 'METHOD_STATUS_UNRESOLVED',errors,numeric,pending

def _condition_issues(result,common,variant):
    errors=[];condition=result.get('condition') or {};phases=phase_records(result)
    try:
        if condition['source_input_sha256']!=common['input_sha256'] or condition['shared_deployment']!=common['shared_deployment'] or condition['opened_by_scene']!=common['first_opened_by_scene']:errors.append('FIRST_DOMAIN_IDENTITY')
        if condition['condition_sha256']!=canonical({k:v for k,v in condition.items() if k!='condition_sha256'}):errors.append('CONDITION_HASH')
        if condition['seed_candidate_sha256']!=canonical(condition['seed_candidate']) or condition['seed_receipt_sha256']!=condition['seed_receipt']['receipt_sha256']:errors.append('SEED_HASH')
        if variant=='A' and result.get('phases'):errors.append('A_UNEXPECTED_PHASE2_CONTAINER')
        if variant!='A':
            if [p['phase_index'] for p in phases] not in ([1],[1,2]):errors.append('PHASE_ORDER')
            for p in phases:
                c=p['condition'];expected=common['first_opened_by_scene'] if p['phase_index']==1 else (result['conditional_release']['selection']['opened_by_scene'] if variant=='conditional_release' else common['second_opened_by_scene'])
                if c['opened_by_scene']!=expected or c['seed_candidate_sha256']!=condition['seed_candidate_sha256'] or c['seed_options_by_scene']!=condition['seed_options_by_scene'] or c['budget_identity']!=condition['budget_identity']:errors.append('PHASE_DOMAIN_OR_SEED')
                if c['condition_sha256']!=canonical({k:v for k,v in c.items() if k!='condition_sha256'}):errors.append('PHASE_CONDITION_HASH')
                for scene in p.get('scenes',{}).values():
                    if scene.get('model_complete'):
                        enabled=scene.get('model_summary',{}).get('formulation',{}).get('preeliminate_closed_anchors',False)
                        if enabled is not (variant in ('C','conditional_release') and p['phase_index']==2):errors.append('ANCHOR_TOGGLE')
                if p['phase_index']==2:
                    for sid,scene in p.get('scenes',{}).items():
                        if not scene.get('model_complete'):continue
                        pre=(scene.get('preprocessing') or {}).get('closed_anchor_preelimination') or (scene.get('model_summary',{}).get('preprocessing') or {}).get('closed_anchor_preelimination')
                        if pre is None:errors.append('REFILTER_EVIDENCE_MISSING:'+sid);continue
                        if (pre.get('complete') is not True or pre.get('passes')!=1 or pre.get('condition_sha256')!=c['condition_sha256'] or pre.get('warm_candidate_sha256')!=c['warm_candidate_sha256']):errors.append('REFILTER_BINDING:'+sid)
                        expected_closed=set(c['warm_options_by_scene'][sid])-set(c['opened_by_scene'][sid])
                        if {r['stage_id'] for r in pre.get('anchors_by_scene',{}).get(sid,[])}!=expected_closed:errors.append('REFILTER_CLOSED_MASK:'+sid)
            if len(phases)==2:
                c=phases[1]['condition'];contract=result['linked_record_contract']
                candidates=[a for a in result['aggregation_attempts'] if a.get('receipt_sha256')==c['warm_receipt_sha256']]
                updates=[u for u in result['global_updates'] if u.get('phase_index') in (0,1)]
                if len(candidates)!=1 or c['warm_candidate']!=candidates[0]['safe_candidate'] or c['warm_receipt']!=candidates[0] or c['warm_candidate_sha256']!=canonical(c['warm_candidate']) or not updates or F(updates[-1]['safe_upper_bound_J'])!=F(c['warm_receipt']['safe_upper_bound_J']) or contract['closed_anchor_candidate_sha256']!=c['warm_candidate_sha256']:errors.append('PHASE1_COMPLETE_ANCHOR')
    except (KeyError,TypeError,ValueError):errors.append('CONDITION_OR_ANCHOR_MALFORMED')
    if variant=='conditional_release':errors.extend(_release_issues(result,common))
    elif variant!='C' or 'conditional_release' in result:errors.append('UNEXPECTED_RELEASE_VARIANT')
    return errors

def _release_issues(result,common):
    """Check root-billed receipt and final condition use exactly the frozen S1.

    This checks stored provenance only. It never runs the selector again or
    generates a new schedule/energy result outside the method budget.
    """
    errors=[]
    try:
        q=result['conditional_release'];contract=result['linked_record_contract']
        if (q['maximum_added_stages_per_scene']!=1 or q['added_search_passes']!=0
                or q['policy_changes_physical_evaluation'] is not False):errors.append('RELEASE_SCOPE')
        phases=result.get('phases') or []
        if len(phases)<2:
            # No second pass is also legitimate at a normal root deadline.
            if q.get('selection_state') not in ('NOT_ENTERED','FROZEN_BEFORE_SELECTION','SELECTED_ONCE','FINAL_CONDITION_BOUND'):
                errors.append('RELEASE_PREPARATION_STATE')
            return errors
        c=phases[1]['condition'];base=q['baseline_condition'];selected=q['selection']
        frozen=q['frozen_first_pass_safe_snapshot'];rec=selected['receipt']
        if q['selection_state']!='FINAL_CONDITION_BOUND':errors.append('RELEASE_NOT_BOUND')
        if base['opened_by_scene']!=common['second_opened_by_scene'] or contract['baseline_linked_opened_by_scene']!=common['second_opened_by_scene']:
            errors.append('RELEASE_BASELINE_MASK')
        if base['condition_sha256']!=canonical({k:v for k,v in base.items() if k!='condition_sha256'}):errors.append('RELEASE_BASELINE_HASH')
        for k in ('source_input_sha256','shared_deployment','seed_candidate','seed_receipt','seed_candidate_sha256','seed_receipt_sha256','seed_options_by_scene','warm_candidate','warm_receipt','warm_candidate_sha256','warm_receipt_sha256','warm_options_by_scene','budget_identity','accuracy'):
            if base[k]!=c[k]:errors.append('RELEASE_BASELINE_FINAL:'+k)
        if (frozen['safe_candidate']!=c['warm_candidate'] or frozen['aggregation']!=c['warm_receipt']
                or frozen['candidate_sha256']!=c['warm_candidate_sha256'] or frozen['receipt_sha256']!=c['warm_receipt_sha256']
                or frozen['safe_upper_bound_J']!=c['warm_receipt']['safe_upper_bound_J']):errors.append('RELEASE_FROZEN_S1')
        expected={'baseline_condition_sha256':base['condition_sha256'],'frozen_candidate_sha256':c['warm_candidate_sha256'],
            'frozen_receipt_sha256':c['warm_receipt_sha256'],'final_condition_sha256':c['condition_sha256'],
            'opened_by_scene':c['opened_by_scene'],'receipt_sha256':canonical(rec)}
        if any(selected.get(k)!=v for k,v in expected.items()):errors.append('RELEASE_SELECTION_BINDING')
        expected_receipt={'protocol':'k174-one-closed-stage-opp-start-release-v1',
            'rule':'slower-cheaper-closed-retiming-with-open-conflict-v1','source_input_sha256':common['input_sha256'],
            'baseline_condition_sha256':base['condition_sha256'],'seed_candidate_sha256':base['seed_candidate_sha256'],
            'S1_candidate_sha256':c['warm_candidate_sha256'],'S1_receipt_sha256':c['warm_receipt_sha256'],
            'budget_identity':c['budget_identity'],'base_opened_by_scene':common['second_opened_by_scene'],
            'opened_by_scene':c['opened_by_scene'],'rule_source_sha256':sha(REPO/'research/chapter3_experiments/linked_release_policy.py')}
        if any(rec.get(k)!=v for k,v in expected_receipt.items()) or rec.get('selection_sha256')!=canonical({k:v for k,v in rec.items() if k!='selection_sha256'}):errors.append('RELEASE_RECEIPT_IDENTITY')
        old=base['opened_by_scene'];new=selected['opened_by_scene']
        if set(old)!=set(new) or set(rec['scenes'])!=set(old) or contract['linked_opened_by_scene']!=new:errors.append('RELEASE_SCENE_MASKS')
        for sid,values in new.items():
            original=set(old[sid]);chosen=set(values);record=rec['scenes'][sid]
            if len(values)!=len(chosen) or not original<=chosen or len(chosen-original)>1 or not chosen<set(c['warm_options_by_scene'][sid]):errors.append('RELEASE_MASK_SUPERSET:'+sid)
            if record['opened']!=values or ({record['selected']} if record['selected'] else set())!=chosen-original:errors.append('RELEASE_SELECTED_STAGE:'+sid)
        stamps=[q['selection_started_at_s'],rec['started_at_s'],rec['completed_at_s'],q['selection_completed_at_s']]
        if (any(not finite(x) for x in stamps) or stamps!=sorted(stamps)
                or not 0<=stamps[0]<=stamps[-1]<300 or frozen['committed_at_s']>stamps[0]
                or c['warm_receipt']['completed_at_elapsed_s']>stamps[0]):errors.append('RELEASE_BUDGET_OR_ORDER')
        boundary=result['linked_budget_boundary']
        if boundary.get('identical_budget_forwarded_to_both_passes') is not True or boundary.get('anchor_capture_freeze_selection_validation_and_observer_billed') is not True:errors.append('RELEASE_BUDGET_BOUNDARY')
        pre=contract['closed_anchor_preelimination']
        if pre['enabled'] is not True or pre['phase_indices']!=[2]:errors.append('RELEASE_REFILTER_DECLARATION')
    except (KeyError,TypeError,ValueError,IndexError) as e:errors.append('RELEASE_METADATA_MALFORMED:'+str(e))
    return errors

def audit_slot(folder,slot,declaration):
    """Fail closed on identity/faults; preserve existing U separately from post eligibility."""
    folder=Path(folder);hard=[];safe_issues=[];r={};safe=None;classification='AUDIT_UNRESOLVED'
    out={'protocol':'K176-method-stored-audit-v1','slot_id':slot['slot_id'],'passed':False,'can_continue':False,
        'eligible_for_post':False,'classification':classification,'reported_U_J':None,'usable_U_J':None,
        'comparison_eligible_U_J':None,'new_U':False,'new_physical_evaluation':False}
    try:
        spec=case_spec(declaration,slot);common=spec['common'];variant=slot['variant']
        r=read(folder/'result.json');raw=read(folder/'wrapper_raw_result.json');wi=read(folder/'worker_identity.json');wr=read(folder/'worker_return.json')
        config=read(folder/'input_config.json');instance=read(folder/'input_instance.json')
        if r!=raw:hard.append('ROOT_RESULT_RAW_MISMATCH')
        if canonical(instance)!=common['input_sha256'] or canonical(config)!=common['config_sha256']:hard.append('FRESH_INPUT_IDENTITY')
        if wr.get('passed') is not True or any(wi.get(k) is not True for k in ('input_verified','source_verified','environment_verified')) or wi.get('fresh_input_calls')!=1:hard.append('WORKER_IDENTITY_UNVERIFIED')
        if wi.get('not_scientific') is not False or wr.get('not_scientific') is not False or wr.get('scientific_call_started') is not True:hard.append('FAKE_OR_NOT_STARTED_WORKER')
        for k,v in (('slot_id',slot['slot_id']),('case_id',slot['case_id']),('variant',variant)):
            if wi.get(k)!=v or wr.get(k)!=v:hard.append('WORKER_SLOT:'+k)
        for key,name in [('result_sha256','result.json'),('wrapper_raw_result_sha256','wrapper_raw_result.json'),('identity_sha256','worker_identity.json')]:
            if wr.get(key)!=sha(folder/name):hard.append('WORKER_RETURN_HASH:'+key)
        declaration_path=folder.parent.parent/'declaration.json'
        if wi.get('declaration_sha256')!=wr.get('declaration_sha256') or wi.get('declaration_sha256')!=sha(declaration_path):hard.append('WORKER_DECLARATION_HASH')
        if wi.get('recipe_sha256')!=canonical(spec['recipes'][variant]):hard.append('WORKER_RECIPE_HASH')
        if any(sha(REPO/name)!=digest for name,digest in declaration['source_sha256'].items()):hard.append('SOURCE_DRIFT')
        condition=r.get('condition') or {};bid=condition.get('budget_identity')
        if bid!=wi.get('budget_identity') or F(bid['seconds'])!=300 or F(bid['start'])!=F(str(wi['worker_root_start_s'])) or F(str(wi['worker_root_deadline_s']))!=F(bid['start'])+300:hard.append('ROOT_BUDGET_IDENTITY')
        if r.get('identity',{}).get('full_input_sha256')!=common['input_sha256'] or r.get('identity',{}).get('config_sha256')!=common['config_sha256']:hard.append('METHOD_INPUT_IDENTITY')
        if r.get('timing',{}).get('limit_s')!=300 or wi.get('limit_s')!=300:hard.append('ROOT_LIMIT_CHANGED')
        wanted_protocol=('fresh-seed-n1-then-conditional-release-linked-opp-start-v1' if variant=='conditional_release' else 'fresh-seed-n1-then-linked-opp-start-warm-closed-complement-live-scenes-v1')
        if variant not in ('C','conditional_release') or r.get('protocol')!=wanted_protocol or r.get('scene_slice_s')!=60:hard.append('METHOD_VARIANT_OR_CAP_MISMATCH')
        hard.extend(_condition_issues(r,common,variant))
        closure=read(folder/'method/matlab/closed.json') if (folder/'method/matlab/closed.json').is_file() else None
        if r.get('matlab_worker_ready') is True and not cleanup_ok(closure):hard.append('MATLAB_ISOLATION_UNVERIFIED')
        classification,terminal_errors,numeric,pending=_terminal(r,folder)
        hard.extend(terminal_errors)
        out.update(reported_U_J=r.get('safe_upper_bound_J'),raw_reason=r.get('reason'),
            classification=classification,numerical_issues=numeric,pending_last_request=pending,
            worker_isolation='VERIFIED' if cleanup_ok(closure) else 'NOT_APPLICABLE' if not r.get('matlab_worker_ready') else 'UNRESOLVED')
        if r.get('safe_upper_bound_J') is not None:
            safe_issues=aggregate_issues(r.get('aggregation') or {},r.get('safe_candidate') or {},instance,config,common,bid,declaration.get('scientific_source_sha256',declaration['source_sha256']))
            legality=schedule_audit(instance,r.get('safe_candidate') or {})
            if not legality['passed']:safe_issues.extend(legality['errors'])
            if any(r.get(k)!=r['aggregation'].get(k) for k in ('safe_candidate','safe_upper_bound_J','weighted_energy_J')):safe_issues.append('TOP_SAFE_LEDGER_MISMATCH')
            if not safe_issues:safe=r['safe_upper_bound_J']
            out['current_schedule_audit']=legality
        elif r.get('state')=='SAFE':hard.append('SAFE_STATE_WITHOUT_U')
        seed=condition.get('seed_candidate');seedrec=condition.get('seed_receipt')
        if seed and seedrec:
            issues=aggregate_issues(seedrec,seed,instance,config,common,bid,declaration.get('scientific_source_sha256',declaration['source_sha256']))
            if issues:hard.extend('SEED_'+x for x in issues)
            out['initial_seed']={'candidate_sha256':canonical(seed),'source_sha256':seedrec.get('identity',{}).get('source_sha256'),
                'U_J':seedrec.get('safe_upper_bound_J'),'energy_J':seedrec.get('weighted_energy_J'),
                'formed_at_s':seedrec.get('completed_at_elapsed_s'),'budget_token':bid.get('token'),'complete_safe_verified':not issues}
        else:hard.append('NO_COMPLETE_FRESH_SAFE_SEED')
        for p in r.get('phases') or []:
            if p.get('phase_index')==2:
                c=p.get('condition') or {}
                hard.extend('WARM_'+v for v in aggregate_issues(c.get('warm_receipt') or {},c.get('warm_candidate') or {},instance,config,common,bid,declaration.get('scientific_source_sha256',declaration['source_sha256'])))
        if safe is not None:
            updates=r.get('global_updates') or []
            if not updates or updates[-1].get('safe_upper_bound_J')!=safe or updates[-1].get('weighted_energy_J')!=r.get('weighted_energy_J'):hard.append('GLOBAL_UPDATE_LEDGER')
            if variant!='A':
                snap=r.get('committed_safe_snapshot') or {}
                if snap.get('aggregation')!=r.get('aggregation') or snap.get('safe_candidate')!=r.get('safe_candidate') or snap.get('safe_upper_bound_J')!=safe:hard.append('COMPLETE_SNAPSHOT_LEDGER')
        out['phase_quality']=[{'phase_index':p['phase_index'],'name':p.get('name'),'started_at_s':p.get('started_at_s'),
            'completed_at_s':p.get('completed_at_s'),'global_updates':[u for u in r.get('global_updates',[]) if u.get('phase_index',1)==p['phase_index']],
            'condition_sha256':p.get('condition_sha256'),'closed_anchor_candidate_sha256':p.get('condition',{}).get('warm_candidate_sha256')} for p in phase_records(r)]
        out['timing']=r.get('timing') or {}
        out['usable_U_J']=safe
        normal=classification in NORMAL and not hard and not safe_issues
        out.update(passed=normal,can_continue=normal,eligible_for_post=normal and safe is not None,
            normal_terminal=classification in NORMAL,hard_errors=hard,aggregate_issues=safe_issues,
            result_sha256=sha(folder/'result.json'),raw_result_sha256=sha(folder/'wrapper_raw_result.json'),
            input_sha256=common['input_sha256'],config_sha256=common['config_sha256'],
            candidate_sha256=canonical(r['safe_candidate']) if safe is not None else None)
        if hard:out['classification']='TECHNICAL_OR_IDENTITY_FAILURE'
    except (OSError,KeyError,TypeError,ValueError,IndexError,ZeroDivisionError) as e:
        out.update(hard_errors=hard+['AUDIT_EXCEPTION:'+type(e).__name__+':'+str(e)],aggregate_issues=safe_issues)
    return out

def audit_post(folder,slot,declaration,method_audit=None):
    folder=Path(folder);issues=[]
    try:
        method_audit=method_audit or read(folder/'audit.json')
        if method_audit.get('eligible_for_post') is not True:raise ValueError('method not post eligible')
        p=read(folder/'post_return.json');claim=read(folder/'postcheck.claim.json');r=read(folder/'postcheck.json')
        old=read(folder/'result.json');instance=read(folder/'input_instance.json');config=read(folder/'input_config.json')
        expected={'slot_id':slot['slot_id'],'raw_result_sha256':sha(folder/'wrapper_raw_result.json'),
            'input_sha256':canonical(instance),'candidate_sha256':canonical(old['safe_candidate']),
            'accuracy_sha256':canonical(config['accuracy_targets']),'declaration_source_sha256':declaration['source_sha256']}
        if any(p.get(k)!=v or claim.get(k)!=v for k,v in expected.items()):issues.append('POST_IDENTITY')
        if p.get('passed') is not True or p.get('new_U') is not False or p.get('no_search_or_repair') is not True or p.get('evaluation_calls')!=1 or p.get('not_scientific') is not False or p.get('post_seconds')!=60 or not finite(p.get('evaluation_elapsed_s')) or not 0<=p['evaluation_elapsed_s']<=60:issues.append('POST_TIME_OR_SCOPE')
        if p.get('postcheck_sha256')!=sha(folder/'postcheck.json') or p.get('method_audit_sha256')!=sha(folder/'audit.json'):issues.append('POST_FILE_BINDING')
        if r.get('state')!='SAFE' or r.get('rankable_energy') is not True or set(r.get('scenes',{}))!=set(old['safe_candidate']['scenes']):issues.append('POST_NOT_FULL_SAFE')
        for scene in instance['scenarios']:
            q=r['scenes'][scene['id']];window=F(instance['window_ms'])/1000
            if q.get('complete') is not True or q.get('state')!='SAFE' or F(q['covered_until_s'])!=window or F(q['trace'][-1]['time_s'])!=window:issues.append('POST_WINDOW')
            limits=dict(zip(instance['platform']['node_order'],scene['maximum_temperature_degC']))
            if set(q.get('peaks_degC',{}))!=set(limits):issues.append('POST_THERMAL_NODES')
            for node,limit in limits.items():
                low,high=map(F,q['peaks_degC'][node])
                if low>high or high>F(limit):issues.append('POST_PEAK_UNSAFE')
        a,b=interval(old['weighted_energy_J']);c,d=interval(r['weighted_energy_J'])
        if max(a,c)>min(b,d):issues.append('POST_ENERGY_NOT_REPRODUCED')
        if method_audit['usable_U_J']!=old['safe_upper_bound_J']:issues.append('POST_REPLACED_U')
        return {'passed':not issues,'issues':issues,'new_U':False,'comparison_eligible_U_J':method_audit['usable_U_J'] if not issues else None,'postcheck_sha256':sha(folder/'postcheck.json')}
    except (OSError,KeyError,TypeError,ValueError,IndexError,ZeroDivisionError) as e:
        return {'passed':False,'issues':['POST_AUDIT_EXCEPTION:'+str(e)],'new_U':False,'comparison_eligible_U_J':None}
