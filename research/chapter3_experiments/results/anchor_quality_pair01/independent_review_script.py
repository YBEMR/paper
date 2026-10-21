"""K151 independent internal post-run audit; no optimizer or search.

Run only once both method calls and the outer launcher are terminal. Stored
evidence is checked using archived JSON/Fraction auditors. The only fresh
physical work is a separate <=60 s full-candidate recheck for each existing
final schedule; it never changes original receipts or budget-internal U.
"""
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
HERE = REPO/'research/chapter3_experiments'
OUT = Path(__file__).resolve().parent
IDS = ('old_linked4', 'anchor_linked4')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def stored_deadline_cause(result, folder):
    """Independently inspect root-cutoff facts, without accepting late data."""
    from math import isfinite
    requests = result['augmented_transport']['requests']
    last, limit = requests[-1], result['timing']['limit_s']
    method_end = result['timing']['method_elapsed_s']
    cancel = last.get('cancel_published_at_s')
    pyfiles = sorted((folder/'matlab').glob('request_*.python.json'))
    python = read(pyfiles[-1])
    prefix = pyfiles[-1].name.removesuffix('.python.json')
    input_data = read(folder/'matlab'/(prefix+'.input.json'))
    def complete(request):
        return (request.get('latched_unresolved') is False and request.get('within_budget') is True
            and not request.get('failure_reasons') and request.get('callback_publications_complete') is True
            and request.get('expected_callback_numbers') == request.get('checked_callback_numbers'))
    numeric = [check.get('report',{}).get('accepted') for request in requests for check in request.get('numerical_checks',[])]
    allowed = {'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED','BUDGET_BEFORE_FINAL_ADMISSION','BUDGET_DURING_ADMISSION_ARCHIVE'}
    facts = {'root_deadline':result.get('reason') == 'wall_time_limit' and result.get('budget_exhausted') is True and limit == 300 and method_end >= limit,
        'actual_cancel_after_cutoff_before_method_return':type(cancel) in (int,float) and isfinite(cancel) and limit <= cancel <= method_end,
        'cancel_recorded':last.get('cancel_requested') is True and 'cancel_error' not in last and (folder/'matlab'/(prefix+'.cancel')).is_file(),
        'only_known_deadline_failures':bool(last.get('failure_reasons')) and set(last['failure_reasons']) <= allowed,
        'all_prior_requests_complete':all(complete(request) for request in requests[:-1]),
        'all_actual_numeric_reports_accepted':bool(numeric) and all(value is True for value in numeric),
        'python_refused_late_candidate':python.get('status') == 'BUDGET_EXHAUSTED' and python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == [] and python.get('response_may_arrive_later') is True,
        'only_transient_missing_response':set((python.get('publication_read') or {}).get('transient_read_errors',{})) <= {'FileNotFoundError'},
        'native_request_bound_to_root_absolute_deadline':input_data.get('method_deadline_bound') is True and type(input_data.get('absolute_deadline')) in (int,float)
            and F(str(input_data['absolute_deadline'])) == F(result['condition']['budget_identity']['start'])+F(result['condition']['budget_identity']['seconds']),
        'last_request_not_admitted':last.get('within_budget') is False and last.get('native_status') == 'BUDGET_EXHAUSTED'}
    return {'passed':all(facts.values()),'checks':facts,'cancel_published_at_s':cancel,'method_elapsed_s':method_end,
        'scope':'unfinished final native request remains unresolved; no late vector or U accepted'}


def removal_audit(stats, condition, instance):
    """Re-derive every stored deletion's original constraint from exact input."""
    scenes = {s['id']:s for s in instance['scenarios']}
    modes = {(shared,m['unit_id'],m['opp_id']):m for shared,values in instance['stage_modes'].items() for m in values}
    failures = []
    for removal in stats['removals']:
        sid, stage_id = removal['scenario_id'], removal['stage_instance_id']
        stage = {s['id']:s for s in scenes[sid]['stage_instances']}
        edges = {tuple(e) for e in scenes[sid]['dependencies']}
        mode = modes[stage[stage_id]['shared_stage_id'],removal['unit_id'],removal['opp_id']]
        start, end = F(removal['start_ms']), F(removal['end_ms'])
        okay = stage_id in condition['opened_by_scene'][sid] and end-start == F(mode['duration_ms']) and mode['domain_id'] == removal['domain_id']
        for reason in removal['reasons']:
            anchor = reason['anchor']; aid = anchor['stage_id']
            warm = condition['warm_options_by_scene'][sid][aid]
            amode = modes[stage[aid]['shared_stage_id'],warm['unit'],warm['opp']]
            astart, aend = F(warm['start_ms']), F(warm['start_ms'])+F(amode['duration_ms'])
            okay &= aid not in condition['opened_by_scene'][sid] and anchor['unit_id'] == warm['unit'] and anchor['opp_id'] == warm['opp'] and anchor['domain_id'] == amode['domain_id'] and F(anchor['start_ms']) == astart and F(anchor['end_ms']) == aend
            overlap = max(start,astart) < min(end,aend)
            derived = []
            if overlap and removal['unit_id'] == warm['unit']:
                derived.append('same_unit_overlap')
            if overlap and mode['domain_id'] == amode['domain_id'] and removal['opp_id'] != warm['opp']:
                derived.append('same_domain_different_opp_overlap')
            if (stage_id,aid) in edges and end > astart:
                derived.append('open_predecessor_finishes_after_closed_start')
            if (aid,stage_id) in edges and start < aend:
                derived.append('open_successor_starts_before_closed_end')
            okay &= bool(derived) and derived == reason['rules']
        okay &= bool(removal['reasons'])
        if not okay:
            failures.append(removal['option_id'])
    return {'passed':not failures and stats['removed'] == len(stats['removals']) == stats['before']-stats['after'],
        'checked_removal_count':len(stats['removals']),'failures':failures,
        'scope':'exact original mode/half-open resource/direct-edge facts; no thermal pruning or search'}


def main():
    ledger = read(OUT/'ledger.json')
    if ledger['state'] not in ('COMPLETED', 'BLOCKED') or not (OUT/'launcher_result.json').is_file():
        raise RuntimeError('Audit waits for terminal method/launcher; never poll or resume research')
    recovering = (OUT/'claims/remaining_recovery.json').is_file()
    if recovering and (not (OUT/'recovery_result.json').is_file() or not (OUT/'recovery_launcher_result.json').is_file()):
        raise RuntimeError('Append-only continuation has not finished; audit performs no intervention')
    for name in ('independent_review.json', 'independent_review.md'):
        if (OUT/name).exists():
            raise FileExistsError('Never overwrite an existing independent review')
    helper_path = HERE/'results/linked_quality_pair01/analysis01/analysis_script.py'
    spec = importlib.util.spec_from_file_location('K151_internal_archived_JSON_auditor', helper_path)
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    h, a = k.h, k.a
    declaration, launcher = read(OUT/'declaration.json'), read(OUT/'launcher_result.json')
    checks = {}
    recovery = read(OUT/'recovery_result.json') if recovering else None
    recovery_claim = read(OUT/'claims/remaining_recovery.json') if recovering else None
    continuation_launcher = read(OUT/'recovery_launcher_result.json') if recovering else None
    if recovering:
        checks['append_only_ledger_exactly_two_unique_calls'] = (ledger['consumed'] == 1 and [c['id'] for c in ledger['calls']] == [IDS[0]]
            and recovery_claim['id'] == IDS[1] and recovery_claim['original_consumed_calls'] == 1
            and recovery_claim['cumulative_consumed_calls_after_claim'] == recovery['cumulative_consumed_calls'] == 2
            and recovery_claim['old_rerun'] is False and recovery['old_rerun'] is False)
        checks['reserved_exactly_600_seconds'] = ledger['reserved_method_budget_s'] == 300 and recovery_claim['method_seconds'] == 300 and recovery['cumulative_reserved_method_budget_s'] == 600
        original_manifest = read(OUT/'recovery_before/original_sha256.json')
        checks['original_twelve_blocked_records_preserved'] = len(original_manifest) == 12 and all(
            sha(HERE/'results/anchor_quality_claim01.json' if name == 'GLOBAL_CLAIM' else OUT/name) == value for name,value in original_manifest.items())
        checks['continuation_completed_without_watchdog'] = continuation_launcher['returncode'] == 0 and continuation_launcher['outer_watchdog_stopped'] is False and continuation_launcher['process_wall_s'] <= 580
        checks['cumulative_active_process_under_900_seconds'] = launcher['process_wall_s']+continuation_launcher['process_wall_s'] <= 900
        bound = read(OUT/'recovery_launcher_claim.json')
        checks['actual_continuation_hard_limit_and_bound_files'] = bound['hard_wall_s'] == 580 and all(sha(HERE/'results/anchor_pair_preparation01'/name) == value for name,value in bound['bindings'].items())
        checks['original_process_stopped_on_preserved_audit_rejection'] = launcher['returncode'] == 1 and launcher['outer_watchdog_stopped'] is False
    else:
        checks['ledger_exactly_two_unique_calls'] = ledger['consumed'] == 2 and [c['id'] for c in ledger['calls']] == list(IDS)
        checks['reserved_exactly_600_seconds'] = ledger['reserved_method_budget_s'] == 600
    checks['two_jobs_four_open_single_toggle'] = declaration['jobs'] == [
        {'id': IDS[0], 'opened_count': 4, 'preeliminate_closed_anchors': False},
        {'id': IDS[1], 'opened_count': 4, 'preeliminate_closed_anchors': True}]
    checks['unchanged_original_grid_window_policy'] = (declaration['window_ms'] == 400
        and declaration['start_grid_ms'] == 5 and declaration['idle_policy'] == 'auto_low_immediate_v1')
    checks['unchanged_budget_solver_rules'] = declaration['per_method_budget_s'] == 300 and declaration['scene_slice_s'] == 60 and declaration['CutMaxIterations'] == 10
    checks['no_retry_or_extension'] = declaration['retry_allowed'] is False and declaration['extend_budget_allowed'] is False
    checks['outer_process_completed_without_watchdog'] = launcher['outer_watchdog_stopped'] is False and launcher['process_wall_s'] <= 900 and (recovering or launcher['returncode'] == 0)
    claim = read(OUT/'launcher_claim.json')
    checks['launcher_prebound_declaration_protocol'] = (claim['declaration_sha256'] == sha(OUT/'declaration.json')
        and claim['protocol_sha256'] == sha(OUT/'protocol.md') and claim['hard_wall_s'] == 900)
    checks['source_current_and_snapshot_174_match'] = len(declaration['source_sha256']) == 174 and all(
        sha(REPO/n) == expected == sha(OUT/'source_snapshot'/n) for n, expected in declaration['source_sha256'].items())
    gate = read(OUT/'precheck.json')
    checks['matching_29_wrapper_checks'] = gate['passed'] is True and gate['tests_run'] == 29 and gate['source_sha256'] == declaration['source_sha256'] and not any(gate['blocked_calls'].values())
    checks['matching_frozen_input_bytes'] = all(sha(OUT/n) == v for n,v in declaration['input_file_sha256'].items())
    jobs, budgets, pids, raw = [], [], [], {}
    for jid in IDS:
        folder = OUT/jid
        result, raw_row = read(folder/'result.json'), read(OUT/'claims'/(jid+'_result.json'))
        row = read(OUT/'corrected_old_record.json') if recovering and jid == IDS[0] else raw_row
        if recovering and jid == IDS[0]:
            checks['original_BLOCKED_status_preserved'] = raw_row['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED' and raw_row['state'] == 'BLOCKED'
            independently_derived = stored_deadline_cause(result,folder)
            checks['old_deadline_cause_independently_verified'] = independently_derived['passed']
            checks['only_three_empty_last_request_budget_hard_records'] = len(raw_row['context']['hard_errors']) == 3 and all(
                isinstance(v,dict) and set(v) == {'scope','reason','status','technical_state','error'}
                and v['status'] == 'BUDGET_EXHAUSTED' and all(v[name] is None for name in ('reason','technical_state','error'))
                and v['scope'] in {'AC_offset_0ms:round:1','phase:2:AC_offset_0ms:round:1'} for v in raw_row['context']['hard_errors'])
            checks['corrected_old_status_does_not_change_U'] = row['usable_U_J'] == raw_row['usable_U_J'] and row['execution']['execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
        instance, config = read(folder/'input_instance.json'), read(folder/'input_config.json')
        raw[jid] = result
        adapted = dict(declaration, old_opened_by_scene=declaration['first_opened_by_scene'],
            new_opened_by_scene=declaration['linked_opened_by_job'][jid],
            linked_opened_by_scene=declaration['linked_opened_by_job'][jid])
        receipt = h.receipt_audit(result, instance, adapted)
        conditions = k.condition_audit(result, instance, adapted)
        updates = h.verified_updates(result, instance)
        warm = h.warm_snapshot_audit(result, instance, updates)
        manifest = read(OUT/'claims'/(jid+'_artifact_sha256.json'))
        artifact_ok = all((folder/n).is_file() and sha(folder/n) == v for n,v in manifest.items())
        checks[jid+'_raw_and_wrapper_result_equal'] = result == read(folder/'wrapper_raw_result.json')
        checks[jid+'_original_input_identity'] = h.digest(instance) == declaration['input_sha256'] and h.digest(config) == declaration['config_sha256']
        checks[jid+'_complete_safe_receipts'] = receipt['all_pass']
        checks[jid+'_condition_and_dual_anchor'] = bool(conditions) and all(v['all_pass'] for v in conditions) and all(v['all_pass'] for v in warm)
        checks[jid+'_all_archived_artifacts_match'] = artifact_ok
        checks[jid+'_usable_U_is_saved_complete_upper'] = row['usable_U_J'] is not None and F(row['usable_U_J']) == F(result['aggregation']['weighted_energy_J'][1])
        checks[jid+'_normal_completion_or_causal_cutoff'] = row['execution']['execution_status'] in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        checks[jid+'_complete_SAFE_within_300s'] = all(0 <= u['at_s'] < 300 for u in updates)
        checks[jid+'_owned_worker_exited'] = row['cleanup']['observed_tree_verified_terminated'] is True
        budget_id = result['condition']['budget_identity']
        budgets.append(budget_id['token'])
        identity = row['cleanup']['process_tree_observation']['root_identity']
        pids.append((identity['pid'], identity['create_time']))
        marker = result['linked_record_contract'].get('closed_anchor_preelimination')
        checks[jid+'_toggle_contract'] = (marker is None if jid == IDS[0] else marker == {
            'enabled': True, 'phase_indices': [2],
            'scope': 'original linked integer schedules retained; all filtering billed before events'})
        model_rows = []
        for phase in result['phases']:
            for sid, scene in phase['scenes'].items():
                if scene.get('model_complete') is not True:
                    continue
                model = scene['model_summary']
                enabled = model['formulation'].get('preeliminate_closed_anchors', False)
                expected = jid == IDS[1] and phase['phase_index'] == 2
                checks[jid+'_phase'+str(phase['phase_index'])+'_'+sid+'_toggle'] = enabled is expected
                stats = model.get('preprocessing', {}).get('closed_anchor_preelimination')
                if expected:
                    checks[jid+'_'+sid+'_filter_identity_complete'] = (stats is not None and stats['complete'] is True
                        and stats['condition_sha256'] == phase['condition_sha256']
                        and stats['warm_candidate_sha256'] == phase['condition']['warm_candidate_sha256']
                        and stats['source_input_sha256'] == declaration['input_sha256'])
                    actual_removals = removal_audit(stats,phase['condition'],instance)
                    checks[jid+'_'+sid+'_all_deleted_options_have_original_constraint_reason'] = actual_removals['passed']
                else:
                    actual_removals = None
                model_rows.append({'phase': phase['phase_index'], 'scene': sid,
                    'enabled': enabled, 'filter': stats,
                    'independent_removal_audit':actual_removals,
                    'variables': model.get('variables'), 'constraints': model.get('constraints')})
        jobs.append({'id': jid, 'U_J': result['safe_upper_bound_J'],
            'energy_interval_J': result['weighted_energy_J'], 'execution': row['execution']['execution_status'],
            'original_wrapper_execution':raw_row['execution']['execution_status'],
            'method_elapsed_s': result['timing']['method_elapsed_s'],
            'cleanup_s': row['cleanup']['cleanup_wall_seconds'],
            'budget_identity': budget_id, 'complete_updates': updates,
            'seed_candidate_sha256': h.digest(result['condition']['seed_candidate']),
            'warm_candidate_sha256': result['linked_record_contract']['closed_anchor_candidate_sha256'],
            'full_receipt_audit': receipt, 'conditions_audit': conditions,
            'warm_snapshot_audit': warm, 'models': model_rows,
            'artifact_count': len(manifest), 'raw_result_sha256': sha(folder/'result.json')})
    checks['method_budget_tokens_distinct'] = len(set(budgets)) == 2
    checks['owned_worker_root_identities_distinct'] = len(set(pids)) == 2
    second_start = recovery_claim['claimed_at_utc'] if recovering else ledger['calls'][1]['started_utc']
    checks['first_call_returned_before_second_started'] = datetime.fromisoformat(ledger['calls'][0]['completed_utc']) <= datetime.fromisoformat(second_start)
    # Full fresh physical checks are separately charged and saved, never fed to
    # either completed method, global claim, wrapper result or ranking U.
    sys.path.insert(0, str(HERE))
    from thermal import Budget, evaluate_candidate
    for job in jobs:
        jid, result = job['id'], raw[job['id']]
        instance = read(OUT/jid/'input_instance.json')
        config = read(OUT/jid/'input_config.json')
        post_file = OUT/(jid+'_post_physical_recheck.json')
        provenance = {'original_result_sha256':job['raw_result_sha256'],
            'input_sha256':h.digest(instance), 'candidate_sha256':h.digest(result['safe_candidate']),
            'accuracy_sha256':h.digest(config['accuracy_targets']),
            'thermal_source_sha256':sha(HERE/'thermal.py'), 'post_budget_seconds':60}
        if post_file.exists():
            post = read(post_file)
            if post.get('post_provenance') != provenance:
                raise ValueError('Previously saved post-check identity mismatch; never rerun physical check')
        else:
            post = evaluate_candidate(instance, result['safe_candidate'], config['accuracy_targets'], Budget(seconds=60))
            post['scope'] = 'post-method recheck of saved final schedule only; no search/repair; not budget-internal U'
            post['post_provenance'] = provenance
            write(post_file, post)
        checks[jid+'_post_full_continuous_safe'] = post['state'] == 'SAFE' and post['rankable_energy'] is True and len(post['scenes']) == len(instance['scenarios'])
        old, fresh = list(map(F,result['weighted_energy_J'])), list(map(F,post['weighted_energy_J'])) if post['weighted_energy_J'] else [F(-1),F(-1)]
        checks[jid+'_post_energy_intervals_overlap'] = max(old[0],fresh[0]) <= min(old[1],fresh[1])
        job['post_recheck'] = {'state':post['state'], 'elapsed_s':post['elapsed_s'],
            'energy_interval_J':post['weighted_energy_J'], 'file':jid+'_post_physical_recheck.json'}
    checks['raw_archives_unchanged_after_physical_checks'] = all(sha(OUT/j['id']/'result.json') == j['raw_result_sha256'] for j in jobs)
    comparison = {'same_seed': jobs[0]['seed_candidate_sha256'] == jobs[1]['seed_candidate_sha256'],
        'same_phase1_warm': jobs[0]['warm_candidate_sha256'] == jobs[1]['warm_candidate_sha256'],
        'new_strictly_better': F(jobs[1]['energy_interval_J'][1]) < F(jobs[0]['energy_interval_J'][0]),
        'old_strictly_better': F(jobs[0]['energy_interval_J'][1]) < F(jobs[1]['energy_interval_J'][0])}
    report = {'stage':'K151', 'review_kind':'internal independent technical audit, not external ChatGPT approval',
        'passed':all(checks.values()), 'checks':checks, 'check_count':len(checks),
        'jobs':jobs, 'comparison':comparison, 'new_research_calls':0,
        'new_optimizer_calls':0, 'new_models':0, 'post_method_physical_rechecks':len(jobs),
        'per_post_recheck_limit_s':60, 'original_records_modified':False,
        'script_sha256':sha(__file__), 'helper_sha256':sha(helper_path),
        'declaration_sha256':sha(OUT/'declaration.json'), 'launcher':launcher,
        'append_only_recovery':recovery, 'continuation_launcher':continuation_launcher,
        'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    if recovering:
        start = read(OUT/'recovery_launcher_claim.json')['created_at_utc']
        report['interruption_calendar_s'] = (datetime.fromisoformat(start)-datetime.fromisoformat(launcher['completed_at_utc'])).total_seconds()
        report['cumulative_active_process_wall_s'] = launcher['process_wall_s']+continuation_launcher['process_wall_s']
    write(OUT/'independent_review.json',report)
    lines=['# K151内部独立复核','',
        f"**{report['check_count']}项核对：{'通过' if report['passed'] else '存在未通过项'}。** 本记录不是外部ChatGPT审批；未启动新搜索、构模或求解。",'',
        '| 方法 | 完整安全U／J | 方法耗时／s | 执行分类 | 事后连续复核／s |',
        '|---|---:|---:|---|---:|']
    for j in jobs:
        lines.append(f"| {j['id']} | {float(F(j['U_J'])):.12f} | {j['method_elapsed_s']:.3f} | {j['execution']} | {j['post_recheck']['elapsed_s']:.3f} |")
    lines += ['',f"两次调用共预留600秒；源码、输入、原预算内完整SAFE及双锚身份均单独核对。两方种子相同：{comparison['same_seed']}；第一遍最终锚相同：{comparison['same_phase1_warm']}。",'',
        f"新版严格改善：{comparison['new_strictly_better']}；旧版严格更低：{comparison['old_strictly_better']}。单次配对仅记录本次质量与求解行为，不形成普遍排名或全域最优证明。",'',
        '预消元仅在新方法第二遍启用，统计绑定同一输入、条件和本次warm；第一遍及旧版未启用。完整参数与自动降L规则保持。', '',
        '两份既成最终方案另以原连续评价器、原误差要求进行事后全场景检查，各独立上限60秒；它们只验证原结果，不生成或回填预算内U。所有原始result与归档hash保留。', '',
        '机器细项及证据定位见[independent_review.json](independent_review.json)。']
    if recovering:
        lines += ['',f"旧方法原BLOCKED及原账本保持；只追加分类校正和未开始的一次新版。实际取消时间300.016秒被继承包装误要求恰等于300秒，并将末请求三份空错误预算状态误作硬故障。独立核对根deadline、拒绝迟到向量、完整前请求、数值门与隔离后，可记正常时间截止、末请求未决，原SAFE不变。",'',
            f"两进程活动时间合{report['cumulative_active_process_wall_s']:.3f}秒，诊断中断{report['interruption_calendar_s']:.3f}秒；不得称900秒内连续完成。恢复只消费尚未开始的新版，旧方法未重跑。"]
    if not report['passed']:
        lines += ['', '未通过：'+str([name for name,ok in checks.items() if not ok])]
    with (OUT/'independent_review.md').open('x',encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    print(json.dumps({'passed':report['passed'],'checks':len(checks),'comparison':comparison,
        'failed':[name for name,ok in checks.items() if not ok]},ensure_ascii=False))


if __name__ == '__main__':
    main()
