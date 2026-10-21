"""K152 independent internal audit, to be run only after four-method termination.

Stored JSON and exact-rational legality checks do not create new search evidence.
Each existing final SAFE may receive at most one separate 60 s full continuous
recheck. Exclusive preclaims make a crash non-retryable; completed rechecks are
reused only with identical provenance. No solver or model is invoked here.
"""
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
HERE = REPO/'research/chapter3_experiments'
OUT = HERE/'results/four_method_comparison01'
IDS = ('whole_milp', 'anchor_linked4', 'heft', 'sa101')
NORMAL = {'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def legal(candidate, instance):
    """Original exact legality, independently rederived without planner imports."""
    checks = {}
    scenes = {s['id']: s for s in instance['scenarios']}
    got = candidate.get('scenes', {})
    checks['all_original_scenes'] = set(got) == set(scenes)
    units = {u['id']: u for u in instance['platform']['units']}
    grid, window = F(instance['start_grid_ms']), F(instance['window_ms'])
    shared_units, rows_out = {}, []
    try:
        for sid, scene in scenes.items():
            requests = {r['id']: r for r in scene['requests']}
            stages = {s['id']: s for s in scene['stage_instances']}
            items = got[sid]
            choices = {r['stage_id']: r for r in items}
            checks[sid+'/unique_full_stages'] = len(choices) == len(items) == len(stages) and set(choices) == set(stages)
            intervals = {}
            for stage_id, st in stages.items():
                row = choices[stage_id]
                selected = [m for m in instance['stage_modes'][st['shared_stage_id']]
                    if m['unit_id'] == row['unit'] and m['opp_id'] == row['opp']]
                checks[sid+'/'+stage_id+'/one_legal_mode'] = len(selected) == 1
                mode = selected[0]
                start = F(row['start_ms']); end = start+F(mode['duration_ms'])
                request = requests[st['request_id']]
                checks[sid+'/'+stage_id+'/grid_release_deadline_window'] = (start >= 0
                    and (start/grid).denominator == 1 and start >= F(request['release_ms'])
                    and end <= F(request['deadline_ms']) and end <= window and end > start)
                explicit = instance.get('start_domain')
                if explicit:
                    checks[sid+'/'+stage_id+'/declared_start'] = start in map(F, explicit['by_scene_stage_ms'][sid][stage_id])
                previous = shared_units.setdefault(st['shared_stage_id'], row['unit'])
                checks[sid+'/'+stage_id+'/shared_deployment'] = previous == row['unit']
                intervals[stage_id] = {'start': start, 'end': end, 'unit': row['unit'],
                    'opp': row['opp'], 'domain': units[row['unit']]['domain_id']}
            for left, right in scene['dependencies']:
                checks[sid+'/dependency/'+left+'->'+right] = intervals[left]['end'] <= intervals[right]['start']
            names = sorted(intervals)
            for index, left in enumerate(names):
                a = intervals[left]
                for right in names[index+1:]:
                    b = intervals[right]
                    overlap = max(a['start'],b['start']) < min(a['end'],b['end'])
                    checks[sid+'/resource/'+left+'|'+right] = not overlap or (a['unit'] != b['unit']
                        and (a['domain'] != b['domain'] or a['opp'] == b['opp']))
            rows_out.append({'scene': sid, 'stages': len(intervals), 'shared_units': dict(shared_units)})
    except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError) as error:
        checks['well_formed'] = False
        rows_out.append({'error':type(error).__name__+': '+str(error)})
    return {'passed':bool(checks) and all(checks.values()), 'checks':checks, 'scenes':rows_out}


def receipt_audit(receipt, candidate, instance):
    """Verify complete original-window stored SAFE and exact aggregate enclosure."""
    checks = {}
    try:
        checks['complete_safe'] = receipt['state'] == 'SAFE' and receipt['rankable_energy'] is True
        checks['in_root_budget'] = finite(receipt['completed_at_elapsed_s']) and 0 <= receipt['completed_at_elapsed_s'] < 300
        scenes = {s['id']:s for s in instance['scenarios']}
        checks['scene_coverage'] = set(receipt['scenes']) == set(candidate['scenes']) == set(scenes)
        low, high = map(F, receipt['weighted_energy_J'])
        checks['valid_system_energy'] = 0 <= low <= high and F(receipt['safe_upper_bound_J']) == high
        sums = [F(0), F(0)]
        for sid, scene in scenes.items():
            local = receipt['scenes'][sid]
            physical = local.get('result', local)
            checks[sid+'/safe_complete'] = (local['state'] == physical['state'] == 'SAFE'
                and local['rankable_energy'] is True and physical['rankable_energy'] is True and physical['complete'] is True)
            window = F(instance['window_ms'])/1000
            checks[sid+'/full_window_and_tail'] = F(physical['covered_until_s']) == window and F(physical['trace'][-1]['time_s']) == window
            nodes = instance['platform']['node_order']
            checks[sid+'/all_thermal_nodes'] = set(physical['peaks_degC']) == set(nodes)
            for node, limit in zip(nodes, scene['maximum_temperature_degC']):
                lo, hi = map(F,physical['peaks_degC'][node])
                checks[sid+'/peak/'+node] = lo <= hi <= F(limit)
            values = physical['energy_J']
            lo, hi = map(F,values)
            checks[sid+'/valid_energy'] = 0 <= lo <= hi
            weight = F(scene['weight'])
            checks[sid+'/nonnegative_weight'] = weight >= 0
            sums[0] += weight*lo; sums[1] += weight*hi
        checks['exact_weighted_sum_enclosed'] = low <= sums[0] <= sums[1] <= high
        checks['weights_sum_one'] = sum(F(s['weight']) for s in scenes.values()) == 1
        identity = receipt.get('evidence_identity')
        if identity is not None:
            checks['original_full_evidence_identity'] = identity == {'input_sha256':digest(instance), 'candidate_sha256':digest(candidate)}
    except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError) as error:
        checks['well_formed'] = False
        return {'passed':False,'checks':checks,'error':type(error).__name__+': '+str(error)}
    return {'passed':all(checks.values()),'checks':checks}


def matched_current_receipt(result, kind, receipt, candidate):
    matches = []
    if kind == 'milp':
        witness = (result.get('initialisation') or {}).get('witness') or {}
        if witness.get('evaluation') == receipt and witness.get('candidate') == candidate:
            matches.append('initialisation.witness')
        for name, diag in [('diagnostic',result.get('diagnostic')),('solver_diagnostic',(result.get('solver_diagnostic') or {}).get('diagnostic'))]:
            for index,row in enumerate((diag or {}).get('evaluations',[])):
                if row.get('accepted_safe') is True and row.get('evaluation') == receipt and row.get('candidate') == candidate:
                    matches.append(name+'.evaluations/'+str(index))
    elif kind == 'linked_fixed_unit_opp_start':
        snapshot = result.get('committed_safe_snapshot') or {}
        if snapshot.get('aggregation') == receipt and snapshot.get('safe_candidate') == candidate:
            matches.append('committed_safe_snapshot')
        for index,row in enumerate(result.get('aggregation_attempts',[])):
            if row == receipt and row.get('safe_candidate') == candidate:
                matches.append('aggregation_attempts/'+str(index))
    else:
        for index,row in enumerate(result.get('evaluations',[])):
            if (row.get('accepted_safe') is True and row.get('evaluation') == receipt
                    and row.get('candidate') == candidate and row.get('candidate_sha256') == digest(candidate)):
                matches.append('evaluations/'+str(index))
    return matches


def removal_audit(stats, condition, instance):
    """Reprove every eliminated option from original hard constraints and warm."""
    scenes = {s['id']:s for s in instance['scenarios']}
    modes = {(shared,m['unit_id'],m['opp_id']):m for shared,values in instance['stage_modes'].items() for m in values}
    failures = []
    for removal in stats['removals']:
        sid, stage_id = removal['scenario_id'], removal['stage_instance_id']
        stages = {s['id']:s for s in scenes[sid]['stage_instances']}
        edges = {tuple(e) for e in scenes[sid]['dependencies']}
        mode = modes[stages[stage_id]['shared_stage_id'],removal['unit_id'],removal['opp_id']]
        start,end = F(removal['start_ms']),F(removal['end_ms'])
        okay = stage_id in condition['opened_by_scene'][sid] and end-start == F(mode['duration_ms']) and mode['domain_id'] == removal['domain_id']
        for reason in removal['reasons']:
            anchor = reason['anchor']; aid = anchor['stage_id']
            warm = condition['warm_options_by_scene'][sid][aid]
            amode = modes[stages[aid]['shared_stage_id'],warm['unit'],warm['opp']]
            astart,aend = F(warm['start_ms']),F(warm['start_ms'])+F(amode['duration_ms'])
            okay &= (aid not in condition['opened_by_scene'][sid] and anchor['unit_id'] == warm['unit']
                and anchor['opp_id'] == warm['opp'] and anchor['domain_id'] == amode['domain_id']
                and F(anchor['start_ms']) == astart and F(anchor['end_ms']) == aend)
            overlap = max(start,astart) < min(end,aend)
            derived = []
            if overlap and removal['unit_id'] == warm['unit']:derived.append('same_unit_overlap')
            if overlap and mode['domain_id'] == amode['domain_id'] and removal['opp_id'] != warm['opp']:derived.append('same_domain_different_opp_overlap')
            if (stage_id,aid) in edges and end > astart:derived.append('open_predecessor_finishes_after_closed_start')
            if (aid,stage_id) in edges and start < aend:derived.append('open_successor_starts_before_closed_end')
            okay &= bool(derived) and derived == reason['rules']
        okay &= bool(removal['reasons'])
        if not okay:failures.append(removal['option_id'])
    return {'passed':not failures and stats['removed'] == len(stats['removals']) == stats['before']-stats['after'],
        'checked_removal_count':len(stats['removals']),'failures':failures}


def linked_audit(result,instance,declaration):
    helper = HERE/'results/linked_quality_pair01/analysis01/analysis_script.py'
    spec=importlib.util.spec_from_file_location('K152_prior_JSON_only_linked_auditor',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    adapted=dict(declaration,shared_deployment=declaration['shared_deployment_linked_only'],
        old_opened_by_scene=declaration['first_opened_by_scene'],
        new_opened_by_scene=declaration['linked_opened_by_job']['anchor_linked4'],
        linked_opened_by_scene=declaration['linked_opened_by_job']['anchor_linked4'])
    full=module.h.receipt_audit(result,instance,adapted)
    conditions=module.condition_audit(result,instance,adapted)
    updates=module.h.verified_updates(result,instance)
    warm=module.h.warm_snapshot_audit(result,instance,updates)
    rows=[];checks={
        'complete_original_receipt_identity':full['all_pass'],
        'both_anchor_conditions':bool(conditions) and all(v['all_pass'] for v in conditions),
        'warm_snapshot':bool(warm) and all(v['all_pass'] for v in warm),
        'only_second_pass_toggle':(result.get('linked_record_contract') or {}).get('closed_anchor_preelimination') == {
            'enabled':True,'phase_indices':[2],
            'scope':'original linked integer schedules retained; all filtering billed before events'}}
    for phase in result.get('phases',[]):
        for sid,scene in phase.get('scenes',{}).items():
            if scene.get('model_complete') is not True:continue
            summary=scene['model_summary'];expected=phase['phase_index'] == 2
            prefix='phase'+str(phase['phase_index'])+'/'+sid
            checks[prefix+'/toggle'] = summary['formulation'].get('preeliminate_closed_anchors',False) is expected
            stats=(summary.get('preprocessing') or {}).get('closed_anchor_preelimination')
            if expected:
                checks[prefix+'/filter_identity'] = (stats is not None and stats['complete'] is True
                    and stats['condition_sha256'] == phase['condition_sha256']
                    and stats['warm_candidate_sha256'] == phase['condition']['warm_candidate_sha256']
                    and stats['source_input_sha256'] == declaration['input_sha256'])
                audit=removal_audit(stats,phase['condition'],instance)
                checks[prefix+'/every_removal_original_hard_constraint'] = audit['passed']
                rows.append({'phase':phase['phase_index'],'scene':sid,'audit':audit})
            else:checks[prefix+'/no_filter'] = stats is None
    return {'passed':all(checks.values()),'checks':checks,'conditions':conditions,'warm':warm,
        'removal_audits':rows,'helper_sha256':sha(helper)}


def postcheck_once(jid,result,instance,config):
    """A saved SAFE has at most one external recheck; never a new internal U."""
    from thermal import Budget,evaluate_candidate
    receipt=result['aggregation'] if jid == 'anchor_linked4' else result['evaluation']
    provenance={'original_result_sha256':sha(OUT/jid/'result.json'),
        'input_sha256':digest(instance),'candidate_sha256':digest(result['safe_candidate']),
        'accuracy_sha256':digest(config['accuracy_targets']),'thermal_source_sha256':sha(HERE/'thermal.py'),
        'interval_source_sha256':sha(HERE.parent/'v1_evaluator/interval.py'),'post_budget_seconds':60}
    target=OUT/(jid+'_post_physical_recheck.json');claim=OUT/(jid+'_post_physical_recheck.claim.json')
    if target.exists():
        post=read(target)
        if post.get('post_provenance') != provenance or not claim.is_file() or read(claim).get('post_provenance') != provenance:
            raise ValueError('Stored post-check provenance mismatch; no re-evaluation allowed')
    else:
        write_new(claim,{'claimed_utc':datetime.now(timezone.utc).isoformat(),
            'post_provenance':provenance,'no_retry':True})
        post=evaluate_candidate(instance,result['safe_candidate'],config['accuracy_targets'],Budget(seconds=60))
        post.update(post_provenance=provenance,scope='post-method fixed-final-schedule verification only; no search, repair or budget-internal U replacement')
        write_new(target,post)
    old=tuple(map(F,receipt['weighted_energy_J']))
    fresh=tuple(map(F,post['weighted_energy_J'])) if post.get('weighted_energy_J') else (F(-1),F(-1))
    checks={'post_complete_safe':post.get('state') == 'SAFE' and post.get('rankable_energy') is True
        and set(post.get('scenes',{})) == set(result['safe_candidate']['scenes']),
        'post_energy_intervals_overlap':max(old[0],fresh[0]) <= min(old[1],fresh[1]),
        'post_receipt_full_window':all(s.get('complete') is True and F(s['covered_until_s']) == F(instance['window_ms'])/1000
            for s in post.get('scenes',{}).values()),'original_result_unchanged':sha(OUT/jid/'result.json') == provenance['original_result_sha256']}
    return {'passed':all(checks.values()),'checks':checks,'file':target.name,
        'elapsed_s':post.get('elapsed_s'),'energy_interval_J':post.get('weighted_energy_J'),'provenance':provenance}


def main():
    ledger=read(OUT/'ledger.json')
    launcher_path=OUT/'launcher_result.json'
    if ledger.get('state') not in ('COMPLETED','BLOCKED') or not launcher_path.is_file() or any(c.get('state') == 'RUNNING' for c in ledger.get('calls',[])):
        raise RuntimeError('Only terminal research/launcher evidence may be audited; no polling/resume')
    if (OUT/'independent_review.json').exists() or (OUT/'independent_review.md').exists():
        raise FileExistsError('Independent review is append-only; do not overwrite')
    sys.path.insert(0,str(HERE))
    import run_four_method_comparison as runner
    d,launcher=read(OUT/'declaration.json'),read(launcher_path)
    checks={};jobs=[];roots=[]
    consumed = ledger.get('consumed')
    actual_ids = [c['id'] for c in ledger.get('calls',[])]
    checks['ledger_once_only_declared_prefix'] = (type(consumed) is int and 0 <= consumed <= 4
        and len(actual_ids) == consumed and actual_ids == list(IDS[:consumed]))
    checks['reserved_300_per_consumed_call_at_most_1200'] = (type(consumed) is int
        and ledger.get('reserved_method_budget_s') == consumed*300 <= 1200)
    checks['completed_four_or_explicit_blocked_prefix'] = ((ledger['state'] == 'COMPLETED' and consumed == 4)
        or (ledger['state'] == 'BLOCKED' and bool(actual_ids)))
    checks['launcher_terminal_without_watchdog'] = (launcher.get('returncode') == (0 if ledger['state'] == 'COMPLETED' else 1)
        and launcher.get('outer_watchdog_stopped') is False and launcher.get('process_wall_s',1801) <= 1800)
    bound=read(OUT/'launcher_claim.json')
    checks['launcher_bound_protocol_and_declaration'] = (bound.get('hard_wall_s') == 1800
        and bound.get('declaration_sha256') == sha(OUT/'declaration.json') and bound.get('protocol_sha256') == sha(OUT/'protocol.md')
        and bound.get('script_sha256') == sha(Path(__file__).parent/'launch_once.py'))
    global_claim=read(runner.GLOBAL_CLAIM)
    checks['global_once_claim_bound'] = global_claim.get('no_retry') is True and global_claim.get('declaration_sha256') == sha(OUT/'declaration.json') and global_claim.get('out') == OUT.relative_to(REPO).as_posix()
    checks['exact_four_dispatch_jobs'] = d['jobs'] == runner.jobs()
    checks['original_rules_and_budgets'] = (d['per_method_budget_s'] == 300 and d['method_call_limit'] == 4 and d['scene_slice_s'] == 60 and d['CutMaxIterations'] == 10
        and d['window_ms'] == 400 and d['start_grid_ms'] == 5 and d['entry_temperature_degC'] == 50 and d['maximum_temperature_degC'] == 80
        and d['idle_policy'] == 'auto_low_immediate_v1' and d['retry_allowed'] is False and d['extend_budget_allowed'] is False)
    checks['178_sources_current_and_snapshot'] = len(d['source_sha256']) == 178 and all(sha(REPO/n) == value == sha(OUT/'source_snapshot'/n) for n,value in d['source_sha256'].items())
    checks['extra_dependencies_bound'] = all(sha(REPO/n) == value for n,value in d['dependency_sha256'].items())
    gate=read(OUT/'precheck.json')
    checks['matching_passing_zero_call_precheck'] = (gate['passed'] is True and gate['source_sha256'] == d['source_sha256']
        and gate['source_unchanged'] is True and not any(gate['blocked_calls'].values()) and gate['errors'] == gate['failures'] == gate['skipped'] == 0
        and all(gate[k] == 0 for k in ('research_calls','native_calls','physical_models','thermal_evaluations')) and sha(OUT/'precheck.json') == d['precheck_sha256'])
    checks['frozen_input_bytes'] = all(sha(OUT/n) == value for n,value in d['input_file_sha256'].items())
    for name,key in [('input_raw.json','raw_config_sha256'),('input_config.json','config_sha256'),('input_instance.json','input_sha256')]:
        checks['frozen_canonical/'+name] = digest(read(OUT/name)) == d[key]
    manifest=read(runner.BASE)
    checks['original_K151_input_identity_retained'] = d['input_identities'] == manifest['input_identities']
    before={}
    for index,job in enumerate(d['jobs']):
        jid=job['id'];folder=OUT/jid;rowpath=OUT/'claims'/(jid+'_result.json')
        if not folder.is_dir() or not rowpath.is_file():
            checks[jid+'/unstarted_after_explicit_block'] = (ledger['state'] == 'BLOCKED'
                and jid not in actual_ids and not (OUT/'claims'/(jid+'.json')).exists() and not folder.exists())
            jobs.append({'id':jid,'state':'NOT_RUN','post_recheck':None});continue
        row=read(rowpath)
        if not (folder/'result.json').is_file():
            checks[jid+'/missing_method_result_explicitly_failed'] = (row['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED'
                and row.get('usable_U_J') is None and row.get('state') == 'BLOCKED')
            jobs.append({'id':jid,'execution':row['execution'],'U_J':None,'state':'NO_METHOD_RESULT',
                'post_recheck':None,'raw_wrapper_errors':row.get('errors')});continue
        result=read(folder/'result.json')
        if not (folder/'input_instance.json').is_file() or not (folder/'input_config.json').is_file():
            checks[jid+'/missing_input_not_used_as_safe_evidence'] = (result.get('safe_upper_bound_J') is None
                and row.get('usable_U_J') is None and row['execution']['execution_status'] not in NORMAL)
            jobs.append({'id':jid,'execution':row['execution'],'U_J':None,'state':'INPUT_NOT_ARCHIVED',
                'method_elapsed_s':(result.get('timing') or {}).get('method_elapsed_s'),'post_recheck':None,
                'raw_wrapper_errors':row.get('errors')});continue
        instance,config=read(folder/'input_instance.json'),read(folder/'input_config.json')
        before[jid]=sha(folder/'result.json')
        claim=read(OUT/'claims'/(jid+'.json'))
        checks[jid+'/once_claim'] = all(claim.get(k) == v for k,v in job.items()) and claim.get('seconds') == 300 and claim.get('no_retry') is True
        checks[jid+'/original_independent_input'] = digest(instance) == d['input_sha256'] and digest(config) == d['config_sha256']
        checks[jid+'/one_root_budget'] = result['timing']['limit_s'] == 300 and finite(result['timing']['method_elapsed_s'])
        checks[jid+'/raw_result_preserved'] = result == read(folder/'wrapper_raw_result.json')
        checks[jid+'/no_shared_candidate_cache'] = result.get('candidate_and_cache_shared_between_calls') is False
        artifacts=read(OUT/'claims'/(jid+'_artifact_sha256.json'))
        checks[jid+'/all_recorded_artifacts_preserved'] = all(sha(folder/n) == h for n,h in artifacts.items())
        recalculated=runner.result_records(job,result,d,folder,input_valid=True,source_valid=True,errors=row.get('errors'))
        checks[jid+'/execution_classification_reproduced'] = recalculated['execution'] == row['execution'] and recalculated['usable_U_J'] == row['usable_U_J']
        checks[jid+'/execution_status_preserved_without_forcing_success'] = row['execution']['execution_status'] in (
            NORMAL | {'TECHNICAL_FAILURE_CONFIRMED','NUMERICAL_ANOMALY_OBSERVED','STATUS_UNRESOLVED'})
        if index:
            previous=ledger['calls'][index-1]
            checks[jid+'/sequential_after_previous_return'] = datetime.fromisoformat(previous['completed_utc']) <= datetime.fromisoformat(row['started_utc'])
        if job['method'] in ('milp','linked_fixed_unit_opp_start'):
            cleanup=read(folder/'matlab/closed.json') if (folder/'matlab/closed.json').is_file() else {}
            checks[jid+'/owned_worker_isolated'] = cleanup.get('observed_tree_verified_terminated') is True
            root=(cleanup.get('process_tree_observation') or {}).get('root_identity') or {}
            roots.append((root.get('pid'),root.get('create_time')))
        else:
            checks[jid+'/no_native_worker'] = not (folder/'matlab').exists()
            checks[jid+'/fixed_seed'] = result.get('seed') == (101 if jid == 'sa101' else None)
            checks[jid+'/autoL_opt_in'] = result.get('auto_low_opt_in') is True
        extra={}
        if jid == 'whole_milp':
            summary=result.get('model_summary') or {};form=summary.get('formulation') or {}
            checks[jid+'/no_fixed_deployment_or_neighborhood'] = not any(form.get(k,False) for k in ('fixed_deployment','fixed_shared_deployment','fixed_device_neighborhood','preeliminate_closed_anchors'))
        elif jid == 'anchor_linked4' and result.get('safe_upper_bound_J') is not None:
            extra=linked_audit(result,instance,d)
            checks[jid+'/linked_identity_anchors_and_removals'] = extra['passed']
        output={'id':jid,'execution':row['execution'],'U_J':row.get('usable_U_J'),
            'method_elapsed_s':result['timing']['method_elapsed_s'],'extra_audit':extra,
            'completion_metrics':row.get('completion_metrics'),'post_recheck':None}
        if result.get('safe_upper_bound_J') is not None:
            receipt=result['aggregation'] if jid == 'anchor_linked4' else result['evaluation']
            candidate=result['safe_candidate']
            la=legal(candidate,instance);ra=receipt_audit(receipt,candidate,instance)
            matches=matched_current_receipt(result,job['method'],receipt,candidate)
            checks[jid+'/independent_exact_legality'] = la['passed']
            checks[jid+'/full_original_window_SAFE_receipt'] = ra['passed']
            checks[jid+'/accepted_current_call_provenance'] = bool(matches)
            checks[jid+'/usable_U_exactly_original_complete_upper'] = row['usable_U_J'] is not None and F(row['usable_U_J']) == F(result['safe_upper_bound_J']) == F(receipt['weighted_energy_J'][1])
            output.update(legality_audit=la,receipt_audit=ra,accepted_current_sources=matches,energy_interval_J=receipt['weighted_energy_J'])
            if la['passed'] and ra['passed'] and matches:
                output['post_recheck']=postcheck_once(jid,result,instance,config)
                checks[jid+'/postcheck_passed'] = output['post_recheck']['passed']
        else:
            checks[jid+'/no_U_without_SAFE'] = row.get('usable_U_J') is None
        jobs.append(output)
    checks['separate_recorded_native_workers'] = len(set(roots)) == len(roots) and all(None not in r for r in roots)
    checks['original_results_unchanged_after_postchecks'] = all(sha(OUT/jid/'result.json') == value for jid,value in before.items())
    report={'stage':'K152','review_kind':'internal independent technical audit; not external ChatGPT/主线⑥ approval',
        'passed':all(checks.values()),'checks':checks,'check_count':len(checks),'jobs':jobs,
        'new_research_calls':0,'new_optimizer_calls':0,'new_models':0,
        'post_method_physical_rechecks':sum(j.get('post_recheck') is not None for j in jobs),
        'per_post_recheck_limit_s':60,'original_records_modified':False,
        'planned_method_calls':4,'actual_consumed_calls':consumed,
        'four_methods_completed':ledger['state'] == 'COMPLETED' and consumed == 4,
        'final_SAFE_outputs':sum(j.get('post_recheck') is not None for j in jobs),
        'script_sha256':sha(__file__),'declaration_sha256':sha(OUT/'declaration.json'),
        'launcher':launcher,'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    write_new(OUT/'independent_review.json',report)
    lines=['# K152内部独立审查','',f"**{len(checks)}项核对：{'通过' if report['passed'] else '存在未通过项'}。** 本记录不是外部⑥审批。",'',
        '| 方法 | 原预算内安全U／J | 方法耗时／s | 执行状态 | 事后复核／s |','|---|---:|---:|---|---:|']
    for j in jobs:
        u='—' if j.get('U_J') is None else f"{float(F(j['U_J'])):.12f}"
        elapsed='—' if j.get('method_elapsed_s') is None else f"{j['method_elapsed_s']:.3f}"
        post=j.get('post_recheck') or {};post_s='—' if post.get('elapsed_s') is None else f"{post['elapsed_s']:.3f}"
        lines.append(f"| {j['id']} | {u} | {elapsed} | {(j.get('execution') or {}).get('execution_status',j.get('state'))} | {post_s} |")
    lines += ['',f"本轮计划4种方法各一次300秒，最多预留1200研究秒；实际消费{consumed}次／{ledger.get('reserved_method_budget_s')}秒。无安全方案或技术阻断按原记录报告，不把四法均SAFE作为审计通过条件。源与输入、原预算内完整SAFE、执行截止及预消元原约束来源分别核查。",
        '','事后连续复核仅针对已经完成的最终方案，每方独立上限60秒、最多一次；独占预声明和来源hash阻止重复计算。它不参与搜索，不替换预算内U。',
        '','整体MILP、联动局部搜索与启发式覆盖不同；求解器内部界不升级为全域证明。单次SA101不建立随机算法的一般排名。',
        '','逐项证据见[independent_review.json](independent_review.json)。']
    if not report['passed']:lines += ['','未通过项：'+str([n for n,v in checks.items() if not v])]
    with (OUT/'independent_review.md').open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
    print(json.dumps({'passed':report['passed'],'checks':len(checks),'failed':[n for n,v in checks.items() if not v]},ensure_ascii=False))
    return report['passed']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
