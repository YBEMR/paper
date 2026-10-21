"""K148 terminal stored-evidence analysis; no solver, decode or heat recomputation.

Reuses the previously reviewed K140/K138 JSON/Fraction receipt audit helpers.
Do not execute until the new pair has ended. Does not overwrite prior analysis.
"""
from collections import Counter
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path


REPO = next(p for p in Path(__file__).resolve().parents
            if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
HELPER = REPO/'research/chapter3_experiments/results/linked_quality_pair01/analysis01/analysis_script.py'
spec = importlib.util.spec_from_file_location('K148_existing_K140_JSON_audit', HELPER)
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)
h, a, b = k.h, k.a, k.b
read, save, digest, interval = k.read, k.save, k.digest, k.interval
EXPECTED = ('old_linked4', 'new_linked5')


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_summary(row):
    """Never duplicate the multi-MB ledger/contexts/raw result in facts."""
    fields = ('id', 'opened_count', 'state', 'started_utc', 'completed_utc',
              'method_return_inclusive_wall_s', 'post_method_record_wall_s',
              'usable_U_J', 'raw_reported_U_J', 'source_identity_valid', 'errors')
    out = {name: row.get(name) for name in fields}
    out['execution'] = row.get('execution')
    return out


def old_history():
    original = REPO/'research/chapter3_experiments/results/fair_comparison_preparation01'
    manifest = read(REPO/'research/chapter3_experiments/results/budget_end_review01/audit.json')['raw_artifact_sha256']
    require(len(manifest) == 301, 'Expected immutable K142 original 301 artifacts')
    actual = {name: sha(original/name) for name in manifest}
    require(actual == manifest, 'K142 original artifacts differ from immutable K143 manifest')
    return original, manifest


def phase_report(result, jid, updates, clocks):
    rows = k.phase_report(result, 'linked_n1', updates, clocks)
    for row in rows:
        row['job'] = jid
        row['phase_name'] = ('N1_local_main_post' if row['phase_index'] == 1 else
                             'linked_4_open_2_closed' if jid == 'old_linked4' else
                             'linked_5_open_1_closed')
    return rows


def native_compact(rows):
    wanted = ('job', 'scene', 'phase_index', 'round', 'request_number', 'status', 'exitflag',
        'intlinprog_entered', 'budget_valid', 'accepted_for_evaluation', 'MaxTime_used_s',
        'actual_intlinprog_call_s', 'stop_delay_over_MaxTime_s', 'actual_call_within_MaxTime',
        'callback_count', 'native_summary_callback_count', 'nonempty_callback_count',
        'rootlp_callback_observed', 'first_rootlp_native_elapsed_s', 'first_rootlp_request_wall_s',
        'rootlp_numfeaspoints', 'rootlp_numnodes', 'final_numfeaspoints', 'final_numnodes',
        'final_vector_present', 'bound_scope', 'scope')
    return [{key: row.get(key) for key in wanted} for row in rows]


def schedule_rows(result, jid):
    rows = []
    for sid, scene in (result.get('aggregation') or {}).get('legality', {}).get('scenes', {}).items():
        for row in scene.get('rows', []):
            rows.append({'job': jid, 'scene': sid, **row})
    return rows


def compare_schedules(rows):
    old = {(r['scene'], r['stage_id']): r for r in rows if r['job'] == EXPECTED[0]}
    new = {(r['scene'], r['stage_id']): r for r in rows if r['job'] == EXPECTED[1]}
    result = []
    for key in sorted(set(old)|set(new)):
        one, two = old.get(key, {}), new.get(key, {})
        row = {'scene': key[0], 'stage_id': key[1],
            'both_present': bool(one and two)}
        for field in ('unit', 'opp', 'start_ms', 'end_ms', 'duration_ms', 'activity_power_W'):
            row['old_'+field], row['new_'+field] = one.get(field), two.get(field)
        row['unit_changed'] = one.get('unit') != two.get('unit')
        row['opp_changed'] = one.get('opp') != two.get('opp')
        row['start_changed'] = bool(one and two and F(one['start_ms']) != F(two['start_ms']))
        result.append(row)
    return result


def component_rows(jobs):
    result = []
    for job in jobs:
        for component, values in job.get('components_J', {}).items():
            result.append({'job': job['id'], 'component': component,
                           'lower_J': values[0], 'upper_J': values[1]})
    return result


def model_rows(result, jid):
    rows = []
    for phase in result.get('phases', []):
        for sid, scene in phase.get('scenes', {}).items():
            model = scene.get('model_summary') or {}
            rows.append({'job': jid, 'phase_index': phase['phase_index'], 'scene': sid,
                'model_complete': scene.get('model_complete'),
                'model_completed_at_s': scene.get('model_completed_at_s'),
                'model_summary': model, 'x0_injected': scene.get('x0_injected'),
                'scene_slice_s': scene.get('scene_slice_s'),
                'search_started_at_s': scene.get('search_started_at_s'),
                'search_returned_at_s': scene.get('search_returned_at_s'),
                'reason': scene.get('reason')})
    return rows


def audit_job(jid, row, declaration):
    folder = ROOT/jid
    result = read(folder/'result.json')
    instance, config = read(folder/'input_instance.json'), read(folder/'input_config.json')
    require(digest(instance) == declaration['input_sha256'], jid+' original instance mismatch')
    require(digest(config) == declaration['config_sha256'], jid+' original config mismatch')
    require(result == read(folder/'wrapper_raw_result.json'), jid+' wrapper raw/result mismatch')
    require((result.get('condition') or {}).get('accuracy', config['accuracy_targets']) == config['accuracy_targets'],
            jid+' accuracy mismatch')
    adapted = dict(declaration,
        old_opened_by_scene=declaration['first_opened_by_scene'],
        linked_opened_by_scene=declaration['linked_opened_by_job'][jid],
        new_opened_by_scene=declaration['linked_opened_by_job'][jid])
    receipt = h.receipt_audit(result, instance, adapted)
    conditions = k.condition_audit(result, instance, adapted)
    updates = h.verified_updates(result, instance)
    clocks, costs = h.clock_audit(result, jid)
    phases = phase_report(result, jid, updates, clocks)
    warm = h.warm_snapshot_audit(result, instance, updates)
    native, models, bounds, feedback = h.native_and_models(result, jid, folder)
    complete = bool(receipt.get('all_pass') and conditions
        and all(v['all_pass'] for v in conditions) and all(v['all_pass'] for v in warm))
    execution = row.get('execution') or {}
    if complete:
        require(F(row['usable_U_J']) == interval(receipt['final_energy_J'])[1], jid+' usable U mismatch')
    else:
        require(row.get('usable_U_J') is None, jid+' wrapper admits an independently unverified SAFE')
    result_artifacts = read(ROOT/'claims'/(jid+'_artifact_sha256.json'))
    artifact_mismatches = [name for name, expected in result_artifacts.items()
        if not (folder/name).is_file() or sha(folder/name) != expected]
    require(not artifact_mismatches, jid+' method artifact archive hash mismatch')
    metrics = row.get('completion_metrics') or {}
    for phase in phases:
        saved = next((p for p in metrics.get('phases', [])
                      if p.get('phase_index') == phase['phase_index']), {})
        phase.update(root_remaining_at_entry_s=saved.get('root_remaining_at_entry_s'),
                     root_remaining_at_end_s=saved.get('root_remaining_at_end_s'),
                     first_strict_improvement_at_s=saved.get('first_strict_improvement_at_s'),
                     first_strict_improvement_after_entry_s=saved.get('first_strict_improvement_after_entry_s'))
    components = b.components(result, instance) if complete else {}
    report = {'id': jid, 'wrapper_record': safe_summary(row),
        'result_present': True, 'result_state': result.get('state'), 'reason': result.get('reason'),
        'final_SAFE_receipt_verified': complete,
        'final_energy_J': receipt.get('final_energy_J') if complete else None,
        'final_U_J': result.get('safe_upper_bound_J') if complete else None,
        'initial_energy_J': result.get('initial_global_weighted_energy_J'),
        'seed_candidate_sha256': digest((result.get('condition') or {}).get('seed_candidate')),
        'seed_budget_token': ((result.get('condition') or {}).get('budget_identity') or {}).get('token'),
        'committed_receipt_audit': receipt, 'conditions_audit': conditions,
        'complete_updates': updates, 'phase_warm_snapshot_audit': warm,
        'completion_metrics': metrics, 'phase_attribution': phases,
        'clock_attribution': clocks, 'components_J': components,
        'feedback_records': len(feedback),
        'feedback_rows': sum(v['record'].get('rows_added', 0) for v in feedback),
        'feedback_action_counts': dict(Counter(action.get('type', 'UNKNOWN') for v in feedback
                                             for action in v['record'].get('actions', []))),
        'model_records': model_rows(result, jid),
        'independent_bounds': result.get('deployment_bounds'),
        'independently_proven_optimal': result.get('independently_proven_optimal'),
        'independently_proven_infeasible': result.get('independently_proven_infeasible'),
        'cleanup': {name: (row.get('cleanup') or {}).get(name) for name in
            ('cleanup_status', 'returncode', 'observed_tree_verified_terminated', 'cleanup_wall_seconds')},
        'artifact_hash_count': len(result_artifacts), 'artifact_hashes_match': not artifact_mismatches,
        'saved_bound_record_count': len(bounds), 'failure_boundary': k.failure_boundary(result),
        'last_request': execution.get('last_request'), 'execution_status': execution.get('execution_status'),
        'scope': 'read-only original receipt and provenance audit, not independent thermal recomputation'}
    return report, native_compact(native), phases, costs, schedule_rows(result, jid)


def plot(jobs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), layout='constrained')
    for job, color in zip(jobs, ('#31658b', '#d37c29')):
        points = job.get('complete_updates') or []
        if points:
            xs = [p['at_s'] for p in points]
            ys = [float(F(p['energy_J'][1])) for p in points]
            axes[0].step(xs+[300.0], ys+[ys[-1]], where='post', color=color, label=job['id'])
            axes[0].scatter(xs, ys, color=color, s=17)
        for phase in job.get('phase_attribution') or []:
            if phase['phase_index'] == 2 and phase['entered']:
                axes[0].axvline(phase['started_at_s'], color=color, alpha=.6, linestyle='--', linewidth=.8)
        values = job.get('components_J', {})
        bottom = 0.
        for component, bounds in sorted(values.items()):
            val = (float(F(bounds[0]))+float(F(bounds[1])))/2
            axes[1].bar(job['id'], val, bottom=bottom, label=component if job['id']==EXPECTED[0] else None)
            bottom += val
    axes[0].set(xlim=(0, 300), xlabel='Full method time (s)', ylabel='Complete SAFE energy U (J)')
    axes[1].set(ylabel='Weighted complete system energy (J)')
    axes[0].grid(alpha=.2)
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7)
    fig.savefig(OUT/'energy_progress_and_components.png', dpi=170)
    plt.close(fig)


def text_energy(values):
    return 'NA' if not values else f'{float(F(values[1])):.12f}'


def summary(facts):
    comparison, jobs = facts['comparison'], facts['jobs']
    lines = ['# K.148：4开2闭与5开1闭的单次质量配对', '',
        f"**配对证据有效：{comparison['valid_quality_pair']}；新版严格改善：{comparison['strict_new_improvement']}。**", '',
        '| 方法 | 完整安全能量／J | 首个完整SAFE／s | 首次严格改善／s | 方法返回墙钟／s | 执行分类 |',
        '|---|---:|---:|---:|---:|---|']
    for job in jobs:
        metrics, wrapper = job.get('completion_metrics') or {}, job.get('wrapper_record') or {}
        lines.append(f"| {job['id']} | {text_energy(job.get('final_energy_J'))} | "
            f"{metrics.get('first_complete_SAFE_at_s')} | {metrics.get('first_strict_improvement_at_s')} | "
            f"{wrapper.get('method_return_inclusive_wall_s')} | {job.get('execution_status', 'NOT_RUN')} |")
    if facts.get('post_audit_recovery'):
        lines += ['', '**本轮出现过包装器事后审计故障。** 旧版已完成的安全能量包络向外舍入5e−61 J，'
            '原包装器错误要求与精确加权端点完全相等，先记BLOCKED。只读独立复核确认完整SAFE后，'
            '以包容关系和原60位向外运算的精确复现纠正审计；原故障记录不改，旧版未重跑。'
            '新版按修订记录只执行尚未消费的一次调用。以下是故障修复后完成的同预算配对，不能称为无故障首轮完整流程。']
    if comparison.get('strict_saving_vs_old_lower_percent') is not None:
        lines += ['', f"新版相对旧版的保守能量差为{comparison['strict_saving_vs_old_lower_percent']:.9f}%；"
                      '正值表示新版较低，按新区间上端与旧区间下端计算。']
    lines += ['', '| 方法／阶段 | 进入 | 起止／s | 完整能量起点→终点／J | 本阶段严格改善 |',
              '|---|---|---|---|---|']
    for row in facts['phases']:
        lines.append(f"| {row['job']}／{row['phase_index']} | {row['entered']} | "
            f"{row['started_at_s']}—{row['completed_at_s']} | "
            f"{text_energy(row.get('starting_complete_energy_J'))}→{text_energy(row.get('final_complete_energy_J'))} | "
            f"{row['strict_energy_improvement_vs_own_before_interval']} |")
    lines += ['', '两方法均独立读取原完整AB／AC三Stage输入、创建自身seed和MATLAB会话。唯一搜索域改动为第二遍多开放B／C.main，具体设备保持自身seed；其他参数、auto-L、400 ms窗口、5 ms起点和连续安全标准不变。', '',
        '完整安全结论来自预算内已生成的全部场景、完整窗口和连续峰温包络回执，本分析只核对其来源、哈希、区间及聚合关系；不补算热轨迹、不制造预算后的U。正常截止的末请求未决与此前完整SAFE分列。', '',
        '阶段耗时见phase_timing.csv，互斥时间归属见exclusive_costs.csv，原生求解及内部状态见native.csv，时间表及跨方法差异见schedules.csv、schedule_differences.csv，账面能量组成见energy_components.csv。内部界仅为局部／solver-reported，不作原问题全域证明。', '',
        f"两边同fresh seed选择：{comparison['same_fresh_seed_choices']}；预算token相互独立：{comparison['separate_budget_tokens']}。"
        '独立调用的首遍warm和实际剩余预算可能不同，不能把全部结果差异直接归为多开一个Stage；一次配对不支持稳定性或普遍排名。', '',
        f"实际调用消费{facts['consumed_calls']}次；原165源码、167快照、输入和K142原301工件均核对。"
        '分析前后原始工件哈希保持相同，未补跑、未延长预算。']
    (OUT/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def main():
    require(not (OUT/'facts.json').exists(), 'Never overwrite completed analysis')
    ledger, declaration = read(ROOT/'ledger.json'), read(ROOT/'declaration.json')
    rows = ledger.get('calls') or []
    require(ledger.get('state') not in ('RUNNING', 'DECLARED', 'PREPARED'), 'Pair is still running')
    require(all(r.get('state') not in ('RUNNING', 'DECLARED', 'PREPARED') for r in rows), 'Method still running')
    require([r['id'] for r in rows] == list(EXPECTED[:len(rows)]), 'Unexpected method order')
    before = h.raw_hashes(ROOT)
    history_root, history = old_history()
    frozen = h.source_audit(ROOT, declaration)
    require(frozen['all_match'] and frozen['count'] == 167, 'Frozen167 current/snapshot mismatch')
    base = read(REPO/'research/chapter3_experiments/results/heft_sa_followup01/declaration.json')
    inherited = base['source_sha256']
    require(len(inherited) == 165 and all(declaration['source_sha256'].get(p) == v for p,v in inherited.items()),
            'Inherited165 changed')
    require(all(sha(ROOT/n) == value for n,value in declaration['input_file_sha256'].items()), 'Frozen input byte mismatch')
    require({name: digest(read(ROOT/file)) for name,file in (
        ('raw_config_sha256','input_raw.json'), ('config_sha256','input_config.json'), ('input_sha256','input_instance.json'))}
        == declaration['input_identities'] == base['input_identities'], 'Frozen original input mismatch')
    jobs, native, phases, costs, schedules = [], [], [], [], []
    by_id = {r['id']: r for r in rows}
    recovery = None
    if (ROOT/'corrected_old_record.json').is_file():
        corrected = read(ROOT/'corrected_old_record.json')
        require(corrected.get('original_claim_sha256') == sha(ROOT/'claims/old_linked4_result.json'),
                'Corrected old audit does not bind immutable original claim')
        require((ROOT/'recovery_before/ledger.json').is_file(), 'Original blocked ledger snapshot missing')
        old_snapshot = read(ROOT/'recovery_before/ledger.json')
        require(old_snapshot.get('consumed') == 1 and old_snapshot.get('state') == 'BLOCKED',
                'Recovery snapshot is not original one-consumed blocked state')
        require(sha(ROOT/'recovery_before/old_linked4_result.json') == sha(ROOT/'claims/old_linked4_result.json')
                and old_snapshot['calls'][0] == by_id.get('old_linked4'),
                'Original old blocked claim or ledger row was modified')
        recovery = {'protocol': corrected.get('source_revision_protocol'),
            'original_old_execution_status': (by_id['old_linked4'].get('execution') or {}).get('execution_status'),
            'corrected_old_execution_status': (corrected.get('execution') or {}).get('execution_status'),
            'original_old_claim_sha256': sha(ROOT/'claims/old_linked4_result.json'),
            'corrected_old_record_sha256': sha(ROOT/'corrected_old_record.json'),
            'original_blocked_ledger_sha256': sha(ROOT/'recovery_before/ledger.json'),
            'recovery_result': read(ROOT/'recovery_result.json'),
            'not_a_fault_free_initial_pair': True, 'old_call_not_repeated': True}
        by_id['old_linked4'] = {**by_id['old_linked4'], **corrected}
    for jid in EXPECTED:
        if jid not in by_id:
            jobs.append({'id': jid, 'result_present': False, 'final_SAFE_receipt_verified': False,
                         'execution_status': 'NOT_RUN'})
            continue
        try:
            report, nr, pr, cr, sr = audit_job(jid, by_id[jid], declaration)
        except (OSError, KeyError, TypeError, ValueError) as error:
            report = {'id': jid, 'final_SAFE_receipt_verified': False, 'audit_error': f'{type(error).__name__}: {error}',
                      'wrapper_record': safe_summary(by_id[jid]), 'execution_status': (by_id[jid].get('execution') or {}).get('execution_status')}
            nr, pr, cr, sr = [], [], [], []
        jobs.append(report); native += nr; phases += pr; costs += cr; schedules += sr
    if recovery:
        jobs[0]['original_wrapper_record'] = safe_summary(read(ROOT/'claims/old_linked4_result.json'))
        jobs[0]['original_execution_status'] = recovery['original_old_execution_status']
        jobs[0]['execution_status_correction_scope'] = 'read-only post-audit recovery; original claim unchanged'
    old, new = jobs
    normal = {'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}
    valid = bool(len(rows)==2 and ledger.get('consumed')==2 and
                 all(v.get('final_SAFE_receipt_verified') and v.get('execution_status') in normal for v in jobs))
    old_e = interval(old['final_energy_J']) if old.get('final_energy_J') else None
    new_e = interval(new['final_energy_J']) if new.get('final_energy_J') else None
    difference = old_e[0]-new_e[1] if old_e and new_e else None
    comparison = {'valid_quality_pair': valid,
        'strict_new_improvement': bool(valid and difference is not None and difference > 0),
        'strict_criterion': 'new complete energy upper < old complete energy lower',
        'old_energy_J': old.get('final_energy_J'), 'new_energy_J': new.get('final_energy_J'),
        'old_lower_minus_new_upper_J': None if difference is None else str(difference),
        'strict_saving_vs_old_lower_percent': float(difference/old_e[0]*100) if difference is not None and old_e[0]>0 else None,
        'same_fresh_seed_choices': bool(old.get('seed_candidate_sha256') and old.get('seed_candidate_sha256') == new.get('seed_candidate_sha256')),
        'separate_budget_tokens': bool(old.get('seed_budget_token') and new.get('seed_budget_token')
                                       and old['seed_budget_token'] != new['seed_budget_token']),
        'post_audit_recovery_used': bool(recovery), 'fault_free_initial_pair': not bool(recovery),
        'no_global_optimality_or_statistical_ranking': True}
    facts = {'stage': 'K148', 'analysis': 'terminal-read-only-K140-K138-receipt-audit-v1',
        'new_research_calls': 0, 'new_solver_calls': 0, 'new_heat_evaluations': 0,
        'new_candidate_decodes': 0, 'consumed_calls': ledger.get('consumed'),
        'reserved_method_budget_s': ledger.get('reserved_method_budget_s'),
        'pair_ledger_state_raw': ledger.get('state'), 'declaration_sha256': sha(ROOT/'declaration.json'),
        'analysis_source_sha256': sha(__file__), 'helper_sha256': sha(HELPER),
        'source_count': frozen['count'], 'source_current_and_snapshot_match': frozen['all_match'],
        'inherited165_unchanged': True, 'K142_original301_unchanged': True,
        'input_identities': declaration['input_identities'],
        'comparison': comparison, 'jobs': jobs, 'native_records': native, 'phases': phases,
        'post_audit_recovery': recovery,
        'model_records': [v for job in jobs for v in job.get('model_records', [])],
        'raw_hashes_before': before,
        'scope': 'only saved, already terminal evidence; no search or physical reevaluation'}
    h.write_csv(OUT/'comparison.csv', [{**job.get('wrapper_record', {}), 'id': job['id'],
        'complete_SAFE_verified': job.get('final_SAFE_receipt_verified'),
        'final_energy_J': job.get('final_energy_J'), 'audit_error': job.get('audit_error')}
        for job in jobs])
    h.write_csv(OUT/'phase_timing.csv', phases)
    h.write_csv(OUT/'exclusive_costs.csv', costs)
    h.write_csv(OUT/'native.csv', native)
    h.write_csv(OUT/'schedules.csv', schedules)
    h.write_csv(OUT/'schedule_differences.csv', compare_schedules(schedules))
    h.write_csv(OUT/'energy_components.csv', component_rows(jobs))
    h.write_csv(OUT/'models.csv', facts['model_records'])
    plot(jobs)
    after = h.raw_hashes(ROOT, before)
    require(before == after, 'Raw experiment artifacts changed during analysis')
    require({name: sha(history_root/name) for name in history} == history, 'Old301 changed during analysis')
    require(h.source_audit(ROOT, declaration)['all_match'], 'Source/snapshot changed during analysis')
    facts['raw_hashes_after'] = after
    facts['raw_artifacts_unchanged'] = True
    save(OUT/'facts.json', facts)
    summary(facts)
    print(json.dumps({'valid_quality_pair': valid, 'strict_new_improvement': comparison['strict_new_improvement'],
        'consumed_calls': ledger.get('consumed'), 'old_energy_J': old.get('final_energy_J'),
        'new_energy_J': new.get('final_energy_J'), 'audit_errors': [v.get('audit_error') for v in jobs]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
