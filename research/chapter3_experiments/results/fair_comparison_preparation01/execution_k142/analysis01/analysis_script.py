"""K142 saved-evidence audit. No production import, optimizer or physical replay.

Run only after the frozen four-method controller is terminal. All quality
values must come from budget-valid complete SAFE receipts already on disk.
"""
import argparse
from collections import Counter
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
HELPER = REPO/'research/chapter3_experiments/results/linked_quality_pair01/analysis01/analysis_script.py'
spec = importlib.util.spec_from_file_location('saved_k140_audit_only', HELPER)
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)
h, a, b = k.h, k.a, k.b
read, save, digest, interval = k.read, k.save, k.digest, k.interval
EXPECTED = ('whole_milp', 'linked_n1', 'heft', 'sa101')


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def raw_hashes(root, paths=None):
    if paths is not None:
        return {rel: sha(root/rel) for rel in paths}
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
        if p.is_file() and 'execution_k142' not in p.relative_to(root).parts}


def exact_schedule(candidate, instance):
    """Recheck finite-domain/resource/deadline relations with Fractions only."""
    checks, rows = [], []
    shared = {}
    scenes = {s['id']: s for s in instance['scenarios']}
    checks.append(set(candidate.get('scenes', {})) == set(scenes))
    for sid, scene in scenes.items():
        items = candidate.get('scenes', {}).get(sid, [])
        stages = {s['id']: s for s in scene['stage_instances']}
        requests = {r['id']: r for r in scene['requests']}
        checks += [len(items) == len(stages), {i['stage_id'] for i in items} == set(stages)]
        intervals = {}
        for item in items:
            stage = stages[item['stage_id']]
            mode = next((m for m in instance['stage_modes'][stage['shared_stage_id']]
                if m['unit_id'] == item['unit'] and m['opp_id'] == item['opp']), None)
            checks.append(mode is not None)
            if mode is None:
                continue
            start, duration = F(item['start_ms']), F(mode['duration_ms'])
            end = start + duration
            request = requests[stage['request_id']]
            checks += [start >= F(request['release_ms']), end <= F(request['deadline_ms']),
                start >= 0, (start/F(instance['start_grid_ms'])).denominator == 1,
                end <= F(instance['window_ms'])]
            prior = shared.setdefault(stage['shared_stage_id'], item['unit'])
            checks.append(prior == item['unit'])
            intervals[item['stage_id']] = (start, end, mode)
            rows.append({'scene': sid, 'stage_id': item['stage_id'], 'shared_stage_id': stage['shared_stage_id'],
                'unit': item['unit'], 'opp': item['opp'], 'start_ms': str(start), 'duration_ms': str(duration),
                'end_ms': str(end), 'deadline_ms': request['deadline_ms'],
                'activity_energy_J': mode['activity_energy_J']})
        for before, after in scene['dependencies']:
            checks.append(before in intervals and after in intervals and intervals[before][1] <= intervals[after][0])
        values = list(intervals.values())
        for i, (s1, e1, m1) in enumerate(values):
            for s2, e2, m2 in values[i+1:]:
                overlap = max(s1, s2) < min(e1, e2)
                checks.append(not overlap or m1['unit_id'] != m2['unit_id'])
                checks.append(not overlap or m1['domain_id'] != m2['domain_id'] or m1['opp_id'] == m2['opp_id'])
    return {'all_pass': bool(checks) and all(checks), 'checks': len(checks), 'rows': rows,
        'shared_deployment': shared, 'scope': 'exact rational nonthermal finite-domain audit; thermal conclusions use saved continuous enclosures only'}


def energy_components(receipt, instance, method):
    components = {}
    thermal = []
    for scene in instance['scenarios']:
        local = receipt['scenes'][scene['id']]
        if method == 'n1':
            local = local['result']
        weight = F(scene['weight'])
        for name, raw in local['energy_components_J'].items():
            lo, hi = interval(raw)
            current = components.setdefault(name, [F(0), F(0)])
            current[0] += weight*lo
            current[1] += weight*hi
        for node in instance['platform']['node_order']:
            thermal.append({'scene': scene['id'], 'node': node,
                'peak_degC': local['peaks_degC'][node], 'minimum_degC': local['minimum_degC'][node],
                'covered_until_s': local['covered_until_s'], 'complete': local['complete'],
                'last_trace_time_s': local['trace'][-1]['time_s'], 'energy_J': local['energy_J'],
                'continuous_enclosure_source': 'saved full-window physical receipt; no sampled or replayed trajectory'})
    return {name: [str(v) for v in values] for name,values in components.items()}, thermal


def whole_native(result, folder, jid):
    solved = result.get('solver_diagnostic') or result
    pseudo = {'scenes': {'whole_original_domain': {'solver_result': solved,
        'solver_bound_scope': 'solver-reported original-domain relaxation; not independently certified'}}}
    rows = b.native_records(pseudo, jid, folder)
    for row in rows:
        row['phase_index'] = None
    return rows


def normalized_declaration(declaration):
    normalized = dict(declaration)
    normalized['shared_deployment'] = declaration['shared_deployment_linked_only']
    normalized['linked_opened_by_scene'] = declaration['new_opened_by_scene']
    return normalized


def analyze_job(root, job, row, declaration):
    jid, method = job['id'], job['method']
    folder = root/jid
    if not (folder/'result.json').is_file():
        return {'id': jid, 'ledger': row, 'state': 'NO_SAVED_RESULT', 'result_present': False,
            'final_SAFE_receipt_verified': False}, [], [], [], [], []
    instance, config, result = (read(folder/name) for name in ('input_instance.json','input_config.json','result.json'))
    a.require(digest(instance) == declaration['input_sha256'], jid+' input identity differs')
    a.require(digest(config) == declaration['config_sha256'], jid+' config identity differs')
    a.require(F(instance['window_ms']) == 400 and F(instance['start_grid_ms']) == 5, 'window/grid differs')
    a.require(instance['execution_rules']['idle_policy'] == 'auto_low_immediate_v1', 'idle policy differs')
    a.require(result['timing']['limit_s'] == 300, 'budget differs')
    if method == 'linked_fixed_unit_opp_start':
        report, native, phases, costs, changes = h.job_audit(root, normalized_declaration(declaration), row)
        report['linked_record_contract'] = result.get('linked_record_contract')
        report['linked_budget_boundary'] = result.get('linked_budget_boundary')
        report['failure_boundary'] = k.failure_boundary(result)
        report.pop('staged_budget_boundary', None)
        verifier_method = 'n1'
    else:
        adapted = {'input_identities': {'base': {'instance_sha256': declaration['input_sha256']}}}
        report = a.analyze_job(root, {**job, 'condition': 'base'}, row, adapted)
        report.update(id=jid, result_present=True, state=result.get('state'))
        report['wrapper_timing'] = read(root/'claims'/f'{jid}_wrapper_timing.json')
        report['method_return_inclusive_wall_s'] = row.get('method_return_inclusive_wall_s')
        native = whole_native(result, folder, jid) if method == 'milp' else []
        phases, costs, changes = [], [], []
        verifier_method = method
    report['reported_first_complete_SAFE_s'] = row.get('first_complete_safe_at_s')
    report['reported_first_complete_SAFE_source'] = row.get('first_complete_safe_source')
    report['first_SAFE_time_matches_earliest_saved_receipt'] = (
        report.get('first_SAFE_s') == row.get('first_complete_safe_at_s'))
    # First-time reporting follows the immutable earliest complete receipt;
    # missing or different recorder summaries remain explicit diagnostics.
    report['first_SAFE_s_source'] = 'earliest budget-valid complete saved original SAFE receipt'
    report['first_candidate_at_s'] = row.get('first_candidate_at_s')
    report['first_legal_candidate_at_s'] = row.get('first_legal_candidate_at_s')
    schedule, thermal = [], []
    if report.get('final_SAFE_receipt_verified'):
        audit = exact_schedule(result['safe_candidate'], instance)
        report['exact_saved_schedule_audit'] = audit
        a.require(audit['all_pass'], jid+' exact saved schedule failed')
        schedule = [{'job': jid, **r} for r in audit['rows']]
        final = result['aggregation'] if verifier_method == 'n1' else result['evaluation']
        components, thermal = energy_components(final, instance, verifier_method)
        report['weighted_energy_components_J'] = components
        report['final_continuous_thermal_enclosures'] = thermal
        scene_quality = []
        for scene in instance['scenarios']:
            sid = scene['id']
            physical = final['scenes'][sid]
            if verifier_method == 'n1': physical = physical['result']
            items = [r for r in audit['rows'] if r['scene'] == sid]
            scene_quality.append({'job':jid,'scene':sid,'weight':scene['weight'],
                'energy_J':physical['energy_J'],'energy_components_J':physical['energy_components_J'],
                'OPP_counts':dict(Counter(r['opp'] for r in items)),
                'stage_OPP':{r['shared_stage_id']:r['opp'] for r in items},
                'stage_unit':{r['shared_stage_id']:r['unit'] for r in items},
                'scope':'best retained complete SAFE at method deadline; not a proven optimal candidate'})
        report['best_retained_SAFE_scene_quality'] = scene_quality
        report['best_retained_SAFE_shared_A_deployment'] = {
            stage:unit for stage,unit in audit['shared_deployment'].items() if stage.startswith('A.')}
        weights = {s['id']: F(s['weight']) for s in instance['scenarios']}
        activity = sum((weights[r['scene']]*F(r['activity_energy_J']) for r in audit['rows']), F(0))
        activity_enclosure = interval(components['activity'])
        report['independent_activity_energy_double_count'] = {'exact_J':str(activity),
            'receipt_interval_J':components['activity'],
            'all_pass':activity_enclosure[0] <= activity <= activity_enclosure[1],
            'scope':'sum of original mode activity energy times original scene weights; no thermal integration'}
        a.require(report['independent_activity_energy_double_count']['all_pass'], jid+' activity energy differs')
    report['native_call_times'] = native
    report['reported_U_raw'] = result.get('safe_upper_bound_J')
    if not report.get('final_SAFE_receipt_verified'):
        report['final_U_J'] = None
        report['final_energy_J'] = None
        report['unaccepted_reported_L0_gap'] = report.get('L0_gap')
        report['L0_gap'] = None
    report['model_summary'] = result.get('model_summary')
    report['model_construction'] = result.get('model_construction')
    report['preprocessing'] = result.get('preprocessing')
    report['method_events'] = result.get('events')
    report['solver_attempts_raw'] = result.get('solver_request_attempts')
    report['iteration_count_raw'] = result.get('iterations')
    report['method_domain_scope'] = ('fresh-seed fixed devices; declared two OPP/start subsets'
        if verifier_method == 'n1' else 'original legal shared and scene-local device choices')
    report['single_run_ranking_only'] = True
    report['SA_single_seed_exploratory'] = method == 'sa'
    return report, native, phases, costs, schedule, [{'job':jid,**r} for r in thermal]


def plot(out, calls):
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10,5), layout='constrained')
    for call in calls:
        points = call.get('updates') or []
        end = min(300, (call.get('timing') or {}).get('method_elapsed_s', 300))
        if points:
            xs = [v['at_s'] for v in points]
            ys = [float(F(v['energy_J'][1])) for v in points]
            ax.step(xs+[max(xs[-1],end)], ys+[ys[-1]], where='post', label=call['id']+' SAFE U')
            ax.scatter(xs,ys,s=13)
        lower = (call.get('independent_bounds') or {}).get('L0')
        if lower and not call.get('independent_bound_errors'):
            ax.plot([lower['formed_at_s'],end], [float(F(lower['lower_bound_J']))]*2,
                linestyle=':', alpha=.55, label=call['id']+' independent L0')
    ax.set(xlim=(0,300), xlabel='Complete method elapsed time (s)', ylabel='Weighted system energy (J)')
    ax.grid(alpha=.2)
    if any(c.get('updates') for c in calls): ax.legend(fontsize=8)
    fig.savefig(out/'energy_bounds.png',dpi=180)
    fig.savefig(out/'energy_bounds.pdf')
    plt.close(fig)


def main(root, out):
    declaration, ledger = read(root/'declaration.json'), read(root/'ledger.json')
    a.require(ledger['state'] not in ('RUNNING','DECLARED','PREPARED'), 'controller not terminal')
    a.require(all(r['state'] not in ('RUNNING','DECLARED') for r in ledger['calls']), 'call not terminal')
    a.require(tuple(j['id'] for j in declaration['jobs']) == EXPECTED, 'frozen order changed')
    a.require(not (out/'facts.json').exists(), 'do not overwrite prior derived audit')
    a.require(ledger['consumed'] <= 4 and len(ledger['calls']) == ledger['consumed'], 'call accounting changed')
    before = raw_hashes(root)
    sources = h.source_audit(root, declaration)
    a.require(sources['all_match'] and sources['count'] == 159, 'frozen 159 sources differ')
    a.require(digest(read(root/'input_instance.json')) == declaration['input_sha256'], 'frozen instance differs')
    a.require(digest(read(root/'input_config.json')) == declaration['config_sha256'], 'frozen config differs')
    a.require(digest(read(root/'input_raw.json')) == declaration['raw_config_sha256'], 'frozen raw differs')
    a.require(sha(root/'protocol.md') == read(root/'phase_context.json')['protocol_sha256'], 'protocol changed')
    a.require(sha(root/'launcher.py') == read(root/'phase_context.json')['launcher_sha256'], 'launcher changed')
    by_id = {r['id']:r for r in ledger['calls']}
    calls, native, phases, costs, schedules, thermal = [], [], [], [], [], []
    for job in declaration['jobs']:
        if job['id'] not in by_id:
            calls.append({'id':job['id'],'state':'NOT_RUN','result_present':False,'final_SAFE_receipt_verified':False})
            continue
        try:
            report, nr, pr, cr, sr, tr = analyze_job(root, job, by_id[job['id']], declaration)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            report = {'id':job['id'],'ledger':by_id[job['id']],'state':'SAVED_AUDIT_BLOCKED',
                'audit_error':f'{type(exc).__name__}: {exc}', 'final_SAFE_receipt_verified':False}
            nr,pr,cr,sr,tr = [],[],[],[],[]
        calls.append(report); native += nr; phases += pr; costs += cr; schedules += sr; thermal += tr
    by_call = {c['id']:c for c in calls}
    pairwise = []
    for left in calls:
        for right in calls:
            if left['id'] == right['id']: continue
            le = interval(left['final_energy_J']) if left.get('final_energy_J') and left.get('final_SAFE_receipt_verified') else None
            re = interval(right['final_energy_J']) if right.get('final_energy_J') and right.get('final_SAFE_receipt_verified') else None
            pairwise.append({'lower_energy_method':left['id'],'comparison_method':right['id'],
                'both_full_SAFE_verified':bool(le and re), 'strictly_lower_energy':bool(le and re and le[1] < re[0]),
                'conservative_saving_J':str(re[0]-le[1]) if le and re else None,
                'conservative_saving_percent':float((re[0]-le[1])/re[0]*100) if le and re and re[0] > 0 else None})
    after = raw_hashes(root, before)
    a.require(before == after, 'raw archive changed during saved analysis')
    out.mkdir(parents=True,exist_ok=True)
    facts = {'protocol':'K142-stored-four-method-complete-safety-audit-v1', 'declaration_protocol':declaration['protocol'],
        'ledger':ledger, 'calls':calls, 'pairwise_strict_interval_comparison':pairwise,
        'all_four_calls_executed_once':ledger['consumed'] == 4 and tuple(r['id'] for r in ledger['calls']) == EXPECTED,
        'all_four_comparison_valid':ledger['consumed'] == 4 and all(c.get('final_SAFE_receipt_verified') and
            c.get('ledger',{}).get('state') == 'COMPLETED' and not c.get('audit_error') for c in calls),
        'all_saved_SAFE_consistent':all(c.get('ledger',{}).get('method_state') != 'SAFE'
            or c.get('final_SAFE_receipt_verified') for c in calls),
        'method_elapsed_total_s':sum((c.get('timing') or {}).get('method_elapsed_s',0) for c in calls),
        'method_return_inclusive_wall_total_s':sum(c.get('method_return_inclusive_wall_s') or 0 for c in calls),
        'native_call_times':native,'linked_phase_attribution':phases,'linked_phase_exclusive_costs':costs,
        'final_schedule_rows':schedules,'thermal_enclosures':thermal,'frozen_sources':sources,
        'raw_hashes_before':before,'raw_hashes_after':after,'raw_archives_unchanged':True,
        'helper_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in (HELPER,k.HELPER,h.HELPER,b.HELPER)},
        'launcher_timing':read(root/'launcher_timing.json') if (root/'launcher_timing.json').is_file() else None,
        'wrapper_timing':read(root/'wrapper_timing.json') if (root/'wrapper_timing.json').is_file() else None,
        'new_native_model_decode_heat_calls':0,'historical_candidate_or_U_used':False,
        'scope':'one fixed original baseline; SA101 one seed; linked fixed devices versus free baseline devices; not same coverage or statistical ranking; no new physical validation'}
    save(out/'facts.json', facts)
    h.write_csv(out/'comparison.csv',[{'job':c['id'],'state':c.get('state'),'ledger_state':c.get('ledger',{}).get('state'),
        'verified_SAFE':c.get('final_SAFE_receipt_verified'),'energy_J':c.get('final_energy_J'),'U_J':c.get('final_U_J'),
        'first_SAFE_s':c.get('first_SAFE_s'),'method_s':(c.get('timing') or {}).get('method_elapsed_s'),
        'L0_gap':c.get('L0_gap'),'feedback_records':c.get('feedback_records'),'feedback_rows':c.get('feedback_rows'),
        'timely_violations':c.get('timely_distinct_saved_violation_receipts'),'reason':c.get('reason'),
        'audit_error':c.get('audit_error')} for c in calls])
    h.write_csv(out/'energy_updates.csv',[{'job':c['id'],**p} for c in calls for p in c.get('updates',[])])
    for name, rows in [('pairwise_energy',pairwise),('native_timing',native),('linked_phase_attribution',phases),
        ('linked_phase_costs',costs),('complete_final_schedule',schedules),('continuous_thermal_enclosures',thermal)]:
        h.write_csv(out/(name+'.csv'),rows)
    h.write_csv(out/'best_SAFE_scene_energy_and_OPP.csv',[r for c in calls
        for r in c.get('best_retained_SAFE_scene_quality',[])])
    h.write_csv(out/'best_SAFE_shared_A_deployment.csv',[{'job':c['id'],**c.get('best_retained_SAFE_shared_A_deployment',{})}
        for c in calls if c.get('final_SAFE_receipt_verified')])
    save(out/'complete_final_candidates.json',{c['id']:read(root/c['id']/'result.json').get('safe_candidate')
        for c in calls if c.get('final_SAFE_receipt_verified')})
    plot(out,calls)
    lines = ['# K142：冻结原基准四方法存档核查','',
        f'实际消费 {ledger["consumed"]}/4 次，控制器状态 {ledger["state"]}；四方法对照'+('完成。' if facts['all_four_comparison_valid'] else '未完成，不能形成四法排名；已经核实的完整安全输出保留。'),'',
        '| 方法 | 完整SAFE能量/J | 首SAFE/s | 方法耗时/s | 热反馈行 | 方法／调用状态 |',
        '|---|---:|---:|---:|---:|---|']
    for c in calls:
        lines.append(f'| {c["id"]} | {h.numeric_text(c.get("final_U_J"))} | {h.numeric_text(c.get("first_SAFE_s"),3)} | {h.numeric_text((c.get("timing") or {}).get("method_elapsed_s"),3)} | {c.get("feedback_rows","NA")} | {c.get("state")}／{c.get("ledger",{}).get("state","NOT_RUN")} |')
    lines += ['', '| 方法 | 共享A.pre | 共享A.main | 共享A.post |', '|---|---|---|---|']
    for c in calls:
        shared = c.get('best_retained_SAFE_shared_A_deployment',{})
        lines.append(f'| {c["id"]} | {shared.get("A.pre","NA")} | {shared.get("A.main","NA")} | {shared.get("A.post","NA")} |')
    lines += ['', '| 方法/场景 | 能量/J | 基准/J | 活动/J | 公共/J | 温度修正/J | 各Stage工作点 |',
        '|---|---:|---:|---:|---:|---:|---|']
    for c in calls:
        for row in c.get('best_retained_SAFE_scene_quality',[]):
            parts = row['energy_components_J']
            values = [h.numeric_text(parts[name][1]) for name in ('baseline','activity','external_common','temperature_correction')]
            opps = '；'.join(stage+'='+opp for stage,opp in row['stage_OPP'].items())
            lines.append(f'| {c["id"]}/{row["scene"]} | {h.numeric_text(row["energy_J"][1])} | '+ ' | '.join(values)+f' | {opps} |')
    lines += ['', '能量比较仅使用预算内完整原输入SAFE区间，严格优劣条件为较优方案上端小于对照下端；L0差距与solver-reported界分列。所有源代码、输入、协议、原始结果的哈希已核对；分析没有执行新的候选解码、热计算或优化。',
        '联动版固定本次fresh seed设备，其余三方法保留原合法设备自由度；本次比较预算内可用输出，不宣称等覆盖、全局最优、随机稳定排名或普遍性能。',
        '[能量与独立L0曲线](energy_bounds.png)。完整时间表、峰温包络、阶段归因、原生停止延迟及原始异常分别保存在本目录CSV和facts.json。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    own = Path(__file__).resolve()
    if own != (out/'analysis_script.py').resolve(): (out/'analysis_script.py').write_bytes(own.read_bytes())
    print(json.dumps({'consumed':ledger['consumed'],'valid':facts['all_four_comparison_valid'],
        'calls':[{key:c.get(key) for key in ('id','state','final_U_J','first_SAFE_s','audit_error')} for c in calls]},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=REPO/'research/chapter3_experiments/results/fair_comparison_preparation01')
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    main(root,(args.out or root/'execution_k142/analysis01').resolve())
