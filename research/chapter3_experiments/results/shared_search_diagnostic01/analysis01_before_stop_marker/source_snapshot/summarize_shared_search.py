"""Read-only summary of one completed shared_search archive.

Imports only the standard library; matplotlib is loaded lazily for plotting.
No project module, model builder, heat evaluator, solver or old answer is used.
The audit checks stored identities/evidence, and never creates another U.
"""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil


SEARCH_PROTOCOL = 'shared-deployment-first-pass-global-budget-v1'
PARTIAL_PROTOCOL = 'partial-shared-deployment-unweighted-scene-v1'
VALID_LEGALITY = 'SCHEDULE_VALID_THERMAL_UNCHECKED'


def _load(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _q(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,Fraction)):
        raise ValueError('Nonexact saved energy scalar')
    return Fraction(value)


def _energy(value):
    if not isinstance(value,list) or len(value) != 2:
        raise ValueError('Missing saved energy interval')
    lo,hi = map(_q,value)
    if lo > hi:
        raise ValueError('Reversed saved energy interval')
    return lo,hi


def _time(value,limit):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value) and 0 <= value < limit)


def _inside(root,name):
    """Reject archive paths that escape their declared parent, including links."""
    if not isinstance(name,str) or not name or Path(name).is_absolute():
        raise ValueError('Archive path must be relative')
    path = (root/name).resolve()
    path.relative_to(root.resolve())
    return path


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _cell(value):
    return _json(value) if isinstance(value,(dict,list)) else '' if value is None else value


def _csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows({key:_cell(row.get(key)) for key in fields} for row in rows)


def _source_audit(run,declaration):
    declared = declaration.get('source_sha256')
    errors,files = [],{}
    if not isinstance(declared,dict) or not declared:
        return {},['MISSING_DECLARED_SOURCE_IDENTITY'],{}
    by_name = {}
    for name,digest in declared.items():
        try:
            path = _inside(run/'source_snapshot',name)
            actual = _sha(path)
            valid = isinstance(digest,str) and actual == digest
            files[name] = {'expected_sha256':digest,'actual_sha256':actual,'matches':valid}
            if not valid: errors.append('SOURCE_MISMATCH: '+name)
            by_name.setdefault(Path(name).name,[]).append(digest)
        except (OSError,ValueError,TypeError) as error:
            files[str(name)] = {'matches':False,'error':str(error)}
            errors.append('SOURCE_UNAVAILABLE: '+str(name))
    return by_name,errors,files


def _sources_match(identity,by_name):
    saved = identity.get('source_sha256')
    if not isinstance(saved,dict) or not saved:
        return False
    return all(isinstance(digest,str) and by_name.get(name) == [digest]
               for name,digest in saved.items())


def _shared_ids(instance):
    counts = {}
    for scene in instance['scenarios']:
        for stage in {row['shared_stage_id'] for row in scene['stage_instances']}:
            counts[stage] = counts.get(stage,0)+1
    return sorted(stage for stage,count in counts.items() if count > 1)


def _local_map(scene,rows):
    stages = {stage['id']:stage for stage in scene['stage_instances']}
    if (not isinstance(rows,list) or len(rows) != len(stages)
            or {row['stage_id'] for row in rows} != set(stages)):
        raise ValueError('Candidate does not cover the original Stage instances once')
    deployment = {}
    for row in rows:
        shared = stages[row['stage_id']]['shared_stage_id']; unit = row['unit']
        if shared in deployment and deployment[shared] != unit:
            raise ValueError('Same-scene request copies have different deployments')
        deployment[shared] = unit
    return deployment


def _identity_errors(identity,ctx,fixed,candidate,local,scene=None):
    errors = []
    expected = {'protocol':PARTIAL_PROTOCOL,'full_input_sha256':ctx['input_hash'],
        'shared_stage_ids':ctx['H'],'shared_deployment_sha256':_hash(fixed),
        'platform_sha256':_hash(ctx['instance']['platform']),
        'execution_rules_sha256':_hash(ctx['instance']['execution_rules']),
        'control_policy':ctx['policy'],'candidate_sha256':_hash(candidate),
        'local_deployment_sha256':_hash(local)}
    if scene is not None:
        expected.update(scenario_id=scene['id'],scenario_sha256=_hash(scene),
                        entry_sha256=_hash(scene['entry']))
    for key,value in expected.items():
        if identity.get(key) != value: errors.append('IDENTITY_'+key)
    if identity.get('accuracy_sha256') != ctx['accuracy_hash']: errors.append('ACCURACY_IDENTITY_MISMATCH')
    if not _sources_match(identity,ctx['source_by_name']): errors.append('RECEIPT_SOURCE_MISMATCH')
    budget = identity.get('budget')
    try:
        if not isinstance(budget,dict) or not budget.get('token') or float(budget['seconds']) != ctx['limit']:
            errors.append('BUDGET_IDENTITY_MISMATCH')
    except (KeyError,ValueError,TypeError):
        errors.append('BUDGET_IDENTITY_MISMATCH')
    return errors


def _audit_aggregate(aggregation,ctx,fixed):
    """Check saved payloads/identities; no schedule or physical reevaluation."""
    errors = []
    try:
        if not isinstance(aggregation,dict): raise ValueError('MISSING_AGGREGATE')
        if (aggregation.get('protocol') != PARTIAL_PROTOCOL or aggregation.get('state') != 'SAFE'
                or aggregation.get('rankable_energy') is not True):
            errors.append('NOT_SAVED_COMPLETE_SAFE_AGGREGATE')
        if aggregation.get('violations') or aggregation.get('receipt_errors'):
            errors.append('AGGREGATE_HAS_VIOLATION_OR_RECEIPT_ERRORS')
        if aggregation.get('shared_deployment') != fixed or set(fixed) != set(ctx['H']):
            errors.append('SHARED_CONDITION_MISMATCH')
        if aggregation.get('shared_stage_ids') != ctx['H']: errors.append('SHARED_SET_MISMATCH')
        if aggregation.get('receipt_sha256') != _hash({key:value for key,value in aggregation.items()
                                                     if key != 'receipt_sha256'}):
            errors.append('AGGREGATE_PAYLOAD_HASH_MISMATCH')
        formed = aggregation.get('completed_at_elapsed_s')
        if not _time(formed,ctx['limit']): errors.append('LATE_OR_MISSING_AGGREGATE_TIME')
        interval = aggregation.get('weighted_energy_J'); _,hi = _energy(interval)
        if _q(aggregation.get('safe_upper_bound_J')) != hi: errors.append('AGGREGATE_UPPER_MISMATCH')
        candidate = aggregation['safe_candidate']
        if set(candidate['scenes']) != set(ctx['scenes']): errors.append('INCOMPLETE_ORIGINAL_SCENE_CANDIDATE')
        receipts = aggregation['scenes']; checked = aggregation['legality']
        if set(receipts) != set(ctx['scenes']): errors.append('MISSING_ORIGINAL_SCENE_RECEIPT')
        if checked.get('state') != VALID_LEGALITY: errors.append('MISSING_SAVED_FULL_INPUT_LEGALITY')
        merged = {}; local_maps = {}
        for sid,scene in ctx['scenes'].items():
            local = _local_map(scene,candidate['scenes'][sid]); local_maps[sid] = local
            for shared,unit in local.items():
                if shared in merged and merged[shared] != unit:
                    errors.append('CROSS_SCENE_DEPLOYMENT_MISMATCH')
                merged[shared] = unit
        if aggregation.get('merged_deployment') != merged or checked.get('shared_deployment') != merged:
            errors.append('MERGED_DEPLOYMENT_MISMATCH')
        if any(merged.get(stage) != unit for stage,unit in fixed.items()):
            errors.append('CANDIDATE_DOES_NOT_SATISFY_SHARED_CONDITION')
        identity = aggregation.get('identity') or {}
        errors.extend(_identity_errors(identity,ctx,fixed,candidate,merged))
        for sid,scene in ctx['scenes'].items():
            receipt = receipts[sid]; physical = receipt.get('result') or {}
            local_candidate = {'scenes':{sid:candidate['scenes'][sid]}}
            if (receipt.get('protocol') != PARTIAL_PROTOCOL or receipt.get('state') != 'SAFE'
                    or receipt.get('rankable_energy') is not True or receipt.get('unweighted') is not True
                    or receipt.get('scenario_id') != sid or receipt.get('violations')):
                errors.append(sid+':NOT_COMPLETE_SAFE_SCENE')
            if receipt.get('receipt_sha256') != _hash({k:v for k,v in receipt.items() if k != 'receipt_sha256'}):
                errors.append(sid+':SCENE_PAYLOAD_HASH_MISMATCH')
            if (receipt.get('shared_deployment') != fixed or receipt.get('local_deployment') != local_maps[sid]
                    or receipt.get('shared_stage_ids') != ctx['H']):
                errors.append(sid+':SCENE_DEPLOYMENT_MISMATCH')
            inner_identity = receipt.get('identity') or {}
            errors.extend(sid+':'+error for error in _identity_errors(
                inner_identity,ctx,fixed,local_candidate,local_maps[sid],scene))
            if (inner_identity.get('budget') != identity.get('budget')
                    or inner_identity.get('accuracy_sha256') != identity.get('accuracy_sha256')):
                errors.append(sid+':SCENE_AGGREGATE_IDENTITY_MISMATCH')
            scene_time,physical_time = receipt.get('completed_at_elapsed_s'),physical.get('completed_at_elapsed_s')
            if (not _time(scene_time,ctx['limit']) or not _time(physical_time,ctx['limit'])
                    or (isinstance(formed,(int,float)) and isinstance(scene_time,(int,float)) and scene_time > formed)
                    or (isinstance(scene_time,(int,float)) and isinstance(physical_time,(int,float)) and physical_time > scene_time)):
                errors.append(sid+':LATE_OR_REVERSED_SCENE_TIME')
            _,scene_hi = _energy(receipt.get('energy_J'))
            if (physical.get('state') != 'SAFE' or physical.get('complete') is not True
                    or physical.get('rankable_energy') is not True or physical.get('energy_accuracy_met') is not True
                    or physical.get('scene_id') != sid or physical.get('energy_J') != receipt.get('energy_J')
                    or physical.get('violations') or _q(receipt.get('safe_upper_bound_J')) != scene_hi
                    or _q(physical.get('covered_until_s')) != _q(ctx['instance']['window_ms'])/1000):
                errors.append(sid+':INCONSISTENT_COMPLETE_PHYSICAL_RECEIPT')
            legality = receipt.get('legality') or {}
            if (legality.get('state') != VALID_LEGALITY
                    or (legality.get('scenes') or {}).get(sid) != (checked.get('scenes') or {}).get(sid)):
                errors.append(sid+':LOCAL_AND_FULL_LEGALITY_RECORD_MISMATCH')
        if ctx['archive_errors']: errors.append('ARCHIVE_PREREQUISITE_FAILED')
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as error:
        errors.append(str(error))
    return {'valid':not errors,'errors':sorted(set(errors)),
            'formed_at_s':aggregation.get('completed_at_elapsed_s') if isinstance(aggregation,dict) else None}


def _matching_aggregate(records,fixed,energy,formed):
    for record in records:
        if (record.get('shared_deployment') == fixed and record.get('weighted_energy_J') == energy
                and record.get('completed_at_elapsed_s') == formed):
            return record
    return None


def _issues(record):
    found = []
    bad = {'INTERFACE_ERROR','RESOURCE_LIMIT','SOLVER_INTERFACE_ERROR','INVALID_INPUT_OR_INTERFACE',
           'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED','NUMERICAL_CANDIDATE_ANOMALY','INITIALISATION_ERROR'}
    def numerical_bad(value):
        state = str((value or {}).get('state','')) if isinstance(value,dict) else ''
        return any(word in state for word in ('CONFLICT','UNRESOLVED','ANOMALY','REJECTED'))
    for key in ('error','cleanup_error','technical_issues','startup_cleanup'):
        if record.get(key): found.append({key:record[key]})
    if record.get('reason') in bad: found.append({'reason':record['reason']})
    if numerical_bad(record.get('numerical_consistency')):
        found.append({'numerical_consistency':record['numerical_consistency']})
    for sid,scene in record.get('scenes',{}).items():
        if not isinstance(scene,dict): continue
        for key in ('error','numerical_consistency'):
            if scene.get(key) and (key == 'error' or numerical_bad(scene[key])):
                found.append({'scene':sid,key:scene[key]})
        solved = scene.get('solver_result') or {}
        for key in ('error','numerical_consistency'):
            if solved.get(key) and (key == 'error' or numerical_bad(solved[key])):
                found.append({'scene':sid,key:solved[key]})
        if solved.get('reason') in bad: found.append({'scene':sid,'reason':solved['reason']})
        for index,returned in enumerate(solved.get('rounds',[]),1):
            if (returned.get('error') or returned.get('status') in ('ERROR','WORKER_EXITED')
                    or numerical_bad(returned.get('numerical_consistency'))):
                found.append({'scene':sid,'round':index,'status':returned.get('status'),
                    'error':returned.get('error'),'numerical_consistency':returned.get('numerical_consistency')})
    return found


def initial_pool_comparison(final_hi,initial_intervals,*,complete=True):
    """Compare saved intervals, without selecting a best true-energy seed."""
    intervals = [_energy(interval) for interval in initial_intervals]
    lower = min((lo for lo,_ in intervals),default=None)
    upper = min((hi for _,hi in intervals),default=None)
    strict = bool(complete and lower is not None and final_hi is not None and _q(final_hi) < lower)
    return {'min_initial_lower_J':None if lower is None else str(lower),
            'min_initial_upper_J':None if upper is None else str(upper),
            'final_hi_below_all_initial_lomin':strict}


def select_plot_records(timeline,limit):
    """The graph has no authority to promote rejected or late saved records."""
    updates = [row for row in timeline if row.get('kind') == 'global_U'
               and row.get('audit_valid') is True and _time(row.get('formed_at_s'),limit)
               and _time(row.get('committed_at_s'),limit)]
    initial = [row for row in timeline if row.get('kind') == 'initial_baseline'
               and row.get('audit_valid') is True and _time(row.get('formed_at_s'),limit)]
    return {'U':sorted(updates,key=lambda row:row['committed_at_s']),
            'initial_reference':sorted(initial,key=lambda row:row['formed_at_s'])}


def attribution_axes(updates):
    """Separate the saved initializer/inner source from the change of a."""
    axes = {source:{'same_a':0,'changed_a':0} for source in ('initial_constructor','inner_MILP')}
    for row in updates:
        axes[row['source']]['changed_a' if row['condition_changed'] else 'same_a'] += 1
    return axes


def _plot(out,timeline,L0,limit):
    import matplotlib
    matplotlib.use('Agg',force=True)
    import matplotlib.pyplot as plt
    fig,ax = plt.subplots(figsize=(7.2,4.2),layout='constrained')
    selected = select_plot_records(timeline,limit)
    valid_U,initial = selected['U'],selected['initial_reference']
    if valid_U:
        xs = [row['committed_at_s'] for row in valid_U]
        ys = [float(_q(row['energy_hi_J'])) for row in valid_U]
        ax.step(xs+[limit],ys+[ys[-1]],where='post',color='#1764a0',label='Saved global safe U(t)',linewidth=1.7)
        for source,marker in [('initial_constructor','o'),('inner_MILP','^')]:
            points = [row for row in valid_U if row['source'] == source]
            if points:
                ax.scatter([row['committed_at_s'] for row in points],
                    [float(_q(row['energy_hi_J'])) for row in points],s=30,marker=marker,
                    color='#1764a0',zorder=4,label='U source: '+source)
    else:
        ax.text(.5,.62,'No audited saved global U',ha='center',va='center',transform=ax.transAxes)
    if initial:
        xs,ys,best = [],[],None
        for row in initial:
            value = _q(row['energy_hi_J']); best = value if best is None else min(best,value)
            xs.append(row['formed_at_s']); ys.append(float(best))
        ax.step(xs+[limit],ys+[ys[-1]],where='post',color='#bc6c19',linestyle='--',
                label='Best completed initializer upper (reference)',linewidth=1.5)
    if L0 is not None:
        ax.plot([L0['formed_at_s'],limit],[float(_q(L0['lower_bound_J']))]*2,
                color='#444444',linestyle=':',label='Independent original-domain L0',linewidth=1.7)
    ax.set(xlabel='Elapsed time in the one method budget (s)',ylabel='Energy (J)',
           xlim=(0,limit),title='One shared-deployment search diagnostic')
    ax.grid(alpha=.23); handles,_ = ax.get_legend_handles_labels()
    if handles: ax.legend(fontsize=8,loc='best')
    fig.savefig(out/'global_bounds.png',dpi=220)
    fig.savefig(out/'global_bounds.pdf')
    plt.close(fig)


def summarize(result_dir,out_dir):
    """Summarize an archive; out_dir must not exist. Return the audit dict.

    result_dir contains declaration.json/source_snapshot and, normally,
    invocation/result.json. Only explicitly referenced saved files are read.
    File/source/identity failures are reported and suppress plotted U; they
    never trigger evaluation, repair, another method call or a replacement U.
    """
    run,out = Path(result_dir).resolve(),Path(out_dir).resolve()
    if out.exists(): raise FileExistsError('Summary output already exists: '+str(out))
    if run == out or run.is_relative_to(out): raise ValueError('Output cannot contain the input archive')
    declaration = _load(run/'declaration.json')
    invocation = run/'invocation' if (run/'invocation/result.json').is_file() else run
    result = _load(invocation/'result.json')
    if result.get('protocol') != SEARCH_PROTOCOL or not result.get('timing') or not result.get('reason'):
        raise ValueError('Not a completed shared_search result archive')
    instance,config = _load(invocation/'input_instance.json'),_load(invocation/'input_config.json')
    source_by_name,archive_errors,source_files = _source_audit(run,declaration)
    limit = declaration.get('budget_s',result.get('global_budget_s'))
    if (isinstance(limit,bool) or not isinstance(limit,(int,float))
            or not math.isfinite(limit) or limit <= 0): raise ValueError('Invalid declared budget')
    limit = float(limit); identity = result.get('identity') or {}; input_hash = _hash(instance)
    if result.get('global_budget_s') != limit: archive_errors.append('DECLARED_RESULT_BUDGET_MISMATCH')
    if result['timing'].get('limit_s') != limit: archive_errors.append('TIMING_BUDGET_MISMATCH')
    if identity.get('full_input_sha256') != input_hash: archive_errors.append('ORIGINAL_INPUT_HASH_MISMATCH')
    if identity.get('config_sha256') != _hash(config): archive_errors.append('CONFIG_HASH_MISMATCH')
    rules = instance['execution_rules']
    policy = ('legacy_idle_holds_last_opp' if rules.get('idle_holds_last_opp') is True
              else rules.get('idle_policy'))
    if identity.get('control_policy') != policy: archive_errors.append('CONTROL_POLICY_IDENTITY_MISMATCH')
    if config.get('execution_rules') != rules: archive_errors.append('CONFIG_INSTANCE_RULES_MISMATCH')
    if declaration.get('problem_id') not in (None,result.get('problem_id')):
        archive_errors.append('DECLARED_PROBLEM_MISMATCH')
    if instance.get('id') != result.get('problem_id'): archive_errors.append('SAVED_PROBLEM_MISMATCH')
    weights = [_q(scene['weight']) for scene in instance['scenarios']]
    if any(weight < 0 for weight in weights) or sum(weights) != 1:
        archive_errors.append('ORIGINAL_WEIGHT_MISMATCH')
    scenes = {scene['id']:scene for scene in instance['scenarios']}
    if len(scenes) != len(instance['scenarios']): archive_errors.append('DUPLICATE_ORIGINAL_SCENE')
    ctx = dict(instance=instance,scenes=scenes,input_hash=input_hash,policy=identity.get('control_policy'),
               accuracy_hash=_hash(config['accuracy_targets']),
               H=_shared_ids(instance),source_by_name=source_by_name,limit=limit,archive_errors=archive_errors)
    conditions,result_records,all_aggregates,condition_errors = [],{},[],[]
    for item in result.get('conditions',[]):
        index = item['index']; saved = {}; load_error = None
        if item.get('result_file'):
            try:
                file = _inside(invocation,item['result_file'])
                saved = _load(file)
            except (OSError,ValueError,TypeError) as error: load_error = str(error)
        elif item.get('visited'): load_error = 'VISITED_WITHOUT_RESULT_FILE'
        result_records[index] = saved
        aggregates = list(saved.get('aggregation_attempts',[]))
        if isinstance(saved.get('aggregation'),dict): aggregates.append(saved['aggregation'])
        all_aggregates.extend(aggregates)
        local_errors = []
        if load_error: local_errors.append(load_error)
        if saved:
            if saved.get('shared_deployment') != item['shared_deployment']: local_errors.append('CONDITION_MAPPING_MISMATCH')
            local_identity = saved.get('identity') or {}
            if local_identity.get('full_input_sha256') != input_hash: local_errors.append('CONDITION_INPUT_MISMATCH')
            if saved.get('control_policy') != ctx['policy']: local_errors.append('CONDITION_POLICY_MISMATCH')
        scene_records = saved.get('scenes') or item.get('scenes') or {}
        final_audit = _audit_aggregate(saved.get('aggregation'),ctx,item['shared_deployment']) if saved.get('safe_upper_bound_J') is not None else None
        if final_audit and not final_audit['valid']: local_errors.extend(final_audit['errors'])
        feedback = [entry for scene in scene_records.values()
                    for entry in (scene.get('solver_result') or {}).get('feedback',[])]
        native = {sid:[{'status':entry.get('status'),'exitflag':entry.get('exitflag'),
                      'budget_valid':entry.get('budget_valid'),'output':entry.get('output'),
                      'numerical_consistency':entry.get('numerical_consistency')}
                     for entry in (scene.get('solver_result') or {}).get('rounds',[])]
                  for sid,scene in scene_records.items()}
        issues = _issues(saved)
        if issues or local_errors: condition_errors.append({'index':index,'archive_errors':local_errors,'technical_or_numerical':issues})
        conditions.append({'index':index,'shared_deployment':item['shared_deployment'],
            'visited':item.get('visited',False),'state':item.get('state'),'reason':item.get('reason'),
            'result_file':item.get('result_file'),'saved_result_present':bool(saved),
            'visit_started_at_s':item.get('visit_started_at_s'),'visit_returned_at_s':item.get('visit_returned_at_s'),
            'L_a_J':(item.get('L_a') or {}).get('lower_bound_J'),
            'initial_energy_J':item.get('initial_energy_J'),
            'initial_upper_bound_J':item.get('initial_upper_bound_J'),
            'final_upper_bound_J':saved.get('safe_upper_bound_J',item.get('safe_upper_bound_J')),
            'final_energy_J':saved.get('weighted_energy_J',item.get('weighted_energy_J')),
            'saved_safe_solution_source':saved.get('safe_solution_source'),
            'inner_upper_bound_improved_initial':saved.get('inner_MILP_improved_initial_upper_bound'),
            'strict_inner_improvement_over_initial_certified':saved.get('strict_improvement_over_initial_certified'),
            'first_safe_at_s':saved.get('first_safe_at_s'),
            'scene_states':{sid:{'state':r.get('state'),'reason':r.get('reason'),
                'model_complete':r.get('model_complete'),'best_source':r.get('best_source'),
                'x0_injected':r.get('x0_injected'),'first_safe_at_s':r.get('first_safe_at_s'),
                'initialisation_state':(r.get('initialisation') or {}).get('state'),
                'initialisation_reason':(r.get('initialisation') or {}).get('reason'),
                'search_started_at_s':r.get('search_started_at_s'),
                'search_returned_at_s':r.get('search_returned_at_s')}
                for sid,r in scene_records.items()},
            'feedback_records':len(feedback),'feedback_rows':sum(r.get('rows_added',0) for r in feedback),
            'violations_saved':len(saved.get('violations',[])),
            'solver_reported_scene_bounds':{sid:r.get('solver_reported_bounds',[]) for sid,r in scene_records.items()},
            'native_status_and_output':native,'stop_stage':saved.get('stop_stage'),
            'stop_scene':saved.get('stop_scene'),'technical_numerical_issues':issues,
            'archive_errors':local_errors,'final_receipt_audit_valid':None if final_audit is None else final_audit['valid']})
    if isinstance(result.get('aggregation'),dict): all_aggregates.append(result['aggregation'])
    timeline,previous_upper,previous_fixed,previous_interval,previous_time = [],None,None,None,None
    for index,update in enumerate(result.get('global_updates',[])):
        errors = []; fixed = update.get('shared_deployment'); energy = update.get('energy_J')
        formed,committed = update.get('aggregate_formed_at_s'),update.get('committed_at_s')
        aggregate = _matching_aggregate(all_aggregates,fixed,energy,formed)
        audit = _audit_aggregate(aggregate,ctx,fixed or {})
        errors.extend(audit['errors'])
        try:
            lo,hi = _energy(energy)
            if _q(update.get('safe_upper_bound_J')) != hi: errors.append('UPDATE_UPPER_MISMATCH')
            if previous_upper is not None and hi >= previous_upper: errors.append('NONDECREASING_GLOBAL_UPDATE')
        except (ValueError,TypeError,ZeroDivisionError) as error:
            errors.append(str(error)); lo = hi = None
        if not _time(committed,limit) or not _time(formed,limit): errors.append('LATE_GLOBAL_U_TIME')
        elif formed > committed: errors.append('AGGREGATE_AFTER_GLOBAL_COMMIT')
        if previous_time is not None and _time(committed,limit) and committed < previous_time:
            errors.append('REVERSED_GLOBAL_COMMIT_TIMES')
        sources = update.get('scene_sources') or {}
        source = 'initial_constructor' if sources and all(v == 'initial_constructor' for v in sources.values()) else 'inner_MILP'
        if set(sources) != set(scenes) or update.get('source') != source: errors.append('SOURCE_ATTRIBUTION_MISMATCH')
        changed = previous_fixed is not None and fixed != previous_fixed
        if update.get('condition_changed') is not changed: errors.append('CONDITION_CHANGE_AXIS_MISMATCH')
        if hi is not None:
            improved = previous_upper is not None and hi < previous_upper
            strict = previous_interval is not None and hi < previous_interval[0]
            if update.get('upper_bound_improved') is not improved: errors.append('UPPER_IMPROVEMENT_FLAG_MISMATCH')
            if update.get('strict_energy_improvement_certified') is not strict: errors.append('STRICT_IMPROVEMENT_FLAG_MISMATCH')
        valid = not errors
        if valid:
            previous_upper,previous_fixed,previous_interval,previous_time = hi,fixed,(lo,hi),committed
        timeline.append({'kind':'global_U','record_index':index,'condition_index':update.get('condition_index'),
            'formed_at_s':formed,'committed_at_s':committed,'source':update.get('source'),
            'scene_sources':sources,'condition_changed':update.get('condition_changed'),
            'shared_deployment':fixed,'energy_lo_J':None if lo is None else str(lo),
            'energy_hi_J':None if hi is None else str(hi),'audit_valid':valid,'audit_errors':errors,
            'saved_upper_bound_improved':update.get('upper_bound_improved'),
            'saved_strict_energy_improvement_certified':update.get('strict_energy_improvement_certified')})
    for index,baseline in enumerate(result.get('initial_baselines',[])):
        fixed,energy,formed = baseline.get('shared_deployment'),baseline.get('energy_J'),baseline.get('formed_at_s')
        aggregate = _matching_aggregate(all_aggregates,fixed,energy,formed)
        audit = _audit_aggregate(aggregate,ctx,fixed or {}); errors = audit['errors'][:]
        try:
            lo,hi = _energy(energy)
            if _q(baseline.get('upper_bound_J')) != hi: errors.append('INITIAL_UPPER_MISMATCH')
        except (ValueError,TypeError,ZeroDivisionError) as error:
            errors.append(str(error)); lo = hi = None
        matching_sources = [u.get('scene_sources') or {} for record in result_records.values()
            for u in record.get('global_updates',[]) if u.get('weighted_energy_J') == energy
            and u.get('committed_at_s') == formed and record.get('shared_deployment') == fixed]
        matching_sources.extend(u.get('scene_sources') or {} for u in result.get('global_updates',[])
            if u.get('energy_J') == energy and u.get('aggregate_formed_at_s') == formed
            and u.get('shared_deployment') == fixed)
        if not any(set(s) == set(scenes) and all(v == 'initial_constructor' for v in s.values()) for s in matching_sources):
            errors.append('MISSING_ALL_INITIAL_SCENE_SOURCE_RECORD')
        condition_index = next((c['index'] for c in conditions if c['shared_deployment'] == fixed),None)
        timeline.append({'kind':'initial_baseline','record_index':index,'condition_index':condition_index,
            'formed_at_s':formed,'committed_at_s':baseline.get('transferred_at_s'),
            'transfer_after_cutoff':isinstance(baseline.get('transferred_at_s'),(int,float)) and baseline['transferred_at_s'] >= limit,
            'source':'initial_constructor','shared_deployment':fixed,
            'energy_lo_J':None if lo is None else str(lo),'energy_hi_J':None if hi is None else str(hi),
            'audit_valid':not errors,'audit_errors':errors})
    L0 = result.get('L0'); L0_errors = []
    if isinstance(L0,dict):
        try:
            _q(L0['lower_bound_J'])
            if (L0.get('scope') != 'original_full_domain' or L0.get('solver_reported') is not False
                    or L0.get('used_as_new_MILP_row') is not False or L0.get('input_sha256') != input_hash
                    or not _time(L0.get('formed_at_s'),limit)): L0_errors.append('L0_SCOPE_IDENTITY_OR_TIME_MISMATCH')
        except (KeyError,ValueError,TypeError,ZeroDivisionError): L0_errors.append('MALFORMED_L0')
    else: L0_errors.append('MISSING_L0')
    if archive_errors: L0_errors.append('ARCHIVE_PREREQUISITE_FAILED')
    if L0_errors: L0 = None
    else:
        timeline.append({'kind':'independent_L0','formed_at_s':L0['formed_at_s'],
            'source':'independent_original_domain','energy_lo_J':L0['lower_bound_J'],
            'audit_valid':True,'audit_errors':[]})
    final_audit = _audit_aggregate(result.get('aggregation'),ctx,result.get('best_shared_deployment') or {}) if result.get('safe_upper_bound_J') is not None else {'valid':False,'errors':['NO_SAVED_GLOBAL_U']}
    final_updates = [row for row in timeline if row['kind'] == 'global_U' and row['audit_valid']]
    if result.get('safe_upper_bound_J') is not None:
        if (not final_updates or final_updates[-1]['energy_hi_J'] != str(_q(result['safe_upper_bound_J']))
                or result.get('state') != 'SAFE' or result.get('rankable_energy') is not True
                or final_updates[-1]['shared_deployment'] != result.get('best_shared_deployment')
                or result.get('safe_candidate') != (result.get('aggregation') or {}).get('safe_candidate')
                or result.get('weighted_energy_J') != (result.get('aggregation') or {}).get('weighted_energy_J')):
            final_audit['valid'] = False; final_audit['errors'].append('FINAL_U_CANDIDATE_OR_TIMELINE_MISMATCH')
    initial_rows = [row for row in timeline if row['kind'] == 'initial_baseline' and row['audit_valid']]
    pool_complete = len(initial_rows) == len(result.get('initial_baselines',[]))
    final_hi = _q(result['safe_upper_bound_J']) if final_audit['valid'] else None
    pool_comparison = initial_pool_comparison(final_hi,
        [[row['energy_lo_J'],row['energy_hi_J']] for row in initial_rows],complete=pool_complete)
    strict_pool = pool_comparison['final_hi_below_all_initial_lomin']
    pool_min_hi = None if pool_comparison['min_initial_upper_J'] is None else _q(pool_comparison['min_initial_upper_J'])
    gap = None
    if final_hi is not None and L0 is not None:
        lower = _q(L0['lower_bound_J']); difference = final_hi-lower
        gap = {'L0_J':str(lower),'saved_U_J':str(final_hi),'absolute_gap_J':str(difference),
               'relative_gap':str(difference/final_hi) if final_hi > 0 else None,'consistent':difference >= 0,
               'scope':'original_full_domain','solver_reported':False,'postprocess_arithmetic_only':True}
    axes = attribution_axes(final_updates)
    checks = {'scope':'read-only archive consistency audit; no new evaluation/search/U',
        'source_file_count':len(source_files),'source_files':source_files,
        'source_identity_matches':not any(not entry.get('matches') for entry in source_files.values()) and bool(source_files),
        'archive_errors':archive_errors,'condition_errors':condition_errors,'final_U_audit':final_audit,
        'L0_errors':L0_errors,'L0_gap':gap,'saved_independent_gaps':result.get('independent_gaps'),
        'initial_pool':{'saved_count':len(result.get('initial_baselines',[])),'audited_count':len(initial_rows),
            'all_saved_baselines_audited':pool_complete,**pool_comparison,
            'saved_strict_flag':result.get('strict_improvement_over_best_initial_certified'),
            'saved_strict_flag_matches_audit':result.get('strict_improvement_over_best_initial_certified') is strict_pool},
        'attribution_axes':axes,'saved_global_updates':len(result.get('global_updates',[])),
        'audited_global_updates':len(final_updates),'nominal_conditions':len(conditions),
        'visited_conditions':sum(bool(row['visited']) for row in conditions),
        'unvisited_conditions':sum(not row['visited'] for row in conditions),
        'technical_numerical_issues':_issues(result),'global_budget_s':limit,
        'postprocessor':{'sha256':_sha(Path(__file__)),'method_source_freeze_member':False,
            'copied_source':'source_snapshot/summarize_shared_search.py'},
        'outputs':['summary.md','per_condition.csv','global_timeline.csv','global_bounds.png','global_bounds.pdf','checks.json']}
    # No output is created until the complete saved evidence has been read.
    out.mkdir(parents=True,exist_ok=False)
    (out/'source_snapshot').mkdir()
    shutil.copyfile(Path(__file__),out/'source_snapshot/summarize_shared_search.py')
    condition_fields = list(conditions[0]) if conditions else ['index','visited','state','reason','result_file']
    _csv(out/'per_condition.csv',conditions,condition_fields)
    timeline_fields = ['kind','record_index','condition_index','formed_at_s','committed_at_s','transfer_after_cutoff','source',
        'scene_sources','condition_changed','shared_deployment','energy_lo_J','energy_hi_J',
        'saved_upper_bound_improved','saved_strict_energy_improvement_certified','audit_valid','audit_errors']
    _csv(out/'global_timeline.csv',timeline,timeline_fields)
    _plot(out,timeline,L0,limit)
    _write_summary(out,result,declaration,checks,conditions,final_updates,final_hi,pool_min_hi,L0)
    (out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return checks


def _number(value):
    return '—' if value is None else format(float(_q(value)),'.9g')


def _write_summary(out,result,declaration,checks,conditions,updates,final_hi,best_initial,L0):
    strict = checks['initial_pool']['final_hi_below_all_initial_lomin']
    if final_hi is None:
        lead = '本次档案未提供审计通过的全局安全上界；保存状态与未决原因见下表。'
    elif not checks['initial_pool']['all_saved_baselines_audited']:
        lead = '已保存全局安全方案；初始化池存在未通过审计的记录，节能比较保留未决。'
    elif strict:
        lead = '已保存的全局安全上界严格低于本次全部已成初始化回执的能量下端。'
    elif best_initial is not None and final_hi < best_initial:
        lead = '已保存的全局安全上界低于最佳已成初始化上界，但区间尚不足以证明严格优于整个初始化池。'
    else:
        lead = '已保存全局安全方案；未证实相对最佳已成初始化池的严格节能改善。'
    gap = checks['L0_gap'] or {}; pool = checks['initial_pool']; axes = checks['attribution_axes']
    lines = [lead,'',
        '| 项目 | 保存值 / 审计 |','|---|---|',
        f"| 原问题 / 策略 | {result.get('problem_id')} / {(result.get('identity') or {}).get('control_policy')} |",
        f"| 方法预算 / scene soft slice | {checks['global_budget_s']:g} s / {result.get('scene_slice_s')} s |",
        f"| 状态 / 停止原因 | {result.get('state')} / {result.get('reason')} |",
        f"| 方法耗时 / 清理 | {(result.get('timing') or {}).get('method_elapsed_s')} s / {(result.get('timing') or {}).get('cleanup_s')} s |",
        f"| 最终已保存 U（J） | {_number(final_hi)}；回执审计 {checks['final_U_audit']['valid']} |",
        f"| 首次全局 SAFE / 全局 U 更新 | {result.get('first_safe_at_s')} s / {len(updates)} 条通过审计 |",
        f"| 独立原域 L0（J） | {_number(None if L0 is None else L0['lower_bound_J'])} |",
        f"| U−L0 / 相对 gap | {_number(gap.get('absolute_gap_J'))} J / {_number(gap.get('relative_gap'))} |",
        f"| 已成初始化池 | 保存 {pool['saved_count']}；审计 {pool['audited_count']}；最小上端 {_number(pool['min_initial_upper_J'])} J；所有初始化下端的最小值 {_number(pool['min_initial_lower_J'])} J |",
        f"| 严格池比较 final_hi < all_initial_lomin | {strict} |",
        f"| 名义条件 / 已访问 / 未访问 | {checks['nominal_conditions']} / {checks['visited_conditions']} / {checks['unvisited_conditions']} |",
        f"| 源冻结身份 | {checks['source_file_count']} 项，快照匹配 {checks['source_identity_matches']}；后处理脚本另存 SHA |",'',
        '全局 U 更新按两个独立轴归因：',
        '', '| 保存来源 | 同一 a（含首个 U） | 切换 a |','|---|---:|---:|',
        f"| 初始化构造器 | {axes['initial_constructor']['same_a']} | {axes['initial_constructor']['changed_a']} |",
        f"| 含 inner MILP 场景回执 | {axes['inner_MILP']['same_a']} | {axes['inner_MILP']['changed_a']} |",'',
        '换 a 后的初始化改善归初始化/外层访问；inner 来源表示至少一个场景采用后续 MILP 回执。上界下降与严格能量区间分离分别保存在 CSV；同条件 inner 对其初始化的比较见 per_condition.csv。', '',
        '| 条件 | 访问 | 保存状态 / 原因 | 初始 U（J） | 最终 U（J） | inner 严格改善 |',
        '|---:|---|---|---:|---:|---|']
    for row in conditions:
        lines.append(f"| {row['index']} | {row['visited']} | {row['state']} / {row['reason']} | {_number(row['initial_upper_bound_J'])} | {_number(row['final_upper_bound_J'])} | {row['strict_inner_improvement_over_initial_certified']} |")
    feedback_records = sum(row['feedback_records'] for row in conditions)
    feedback_rows = sum(row['feedback_rows'] for row in conditions)
    lines += ['',f'保存热反馈 {feedback_records} 条、约束行 {feedback_rows} 行；仅说明触发/处理记录，不构成反馈优势消融。',
        '所有原场景（包括零权重）须有匹配 SAFE 回执才有全局 U。图中初始化曲线只引用已成回执，可能在传递越过预算后才归档；它不是新增搜索上界。图中 U 只用原存且提交、聚合均严格早于方法截止时刻的更新。',
        '逐场景 solver-reported 内部界、节点/原生状态、x0 与反馈分列在 per_condition.csv，不合成独立原域下界，也不作跨方法节点等价解释。',
        '未访问/覆盖不足、模型未成、数值接纳冲突、原生请求未返回及技术失败仍是未决。单候选失败不排除部署；遍历名义条件不等于证明最优。本次单问题诊断不推断总体胜率。', '',
        f"归档审计问题：{_json(checks['archive_errors'])}；条件技术/数值/归档问题：{len(checks['condition_errors'])} 组；最终 U 审计：{_json(checks['final_U_audit'])}。细项见 checks.json。",'',
        '本汇总只读已保存 JSON 与冻结源快照；未调用构模、连续热评价或求解，未读取历史参考答案，未补造预算内数据或新 U。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path,help='completed driver archive directory')
    parser.add_argument('--out',required=True,type=Path,help='new, nonexistent summary directory')
    args = parser.parse_args(argv)
    checks = summarize(args.run,args.out)
    print(json.dumps({'out':str(args.out.resolve()),'final_U_audit':checks['final_U_audit'],
        'source_file_count':checks['source_file_count'],'visited_conditions':checks['visited_conditions']},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
