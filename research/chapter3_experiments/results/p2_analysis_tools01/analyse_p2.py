"""Stored-record P2 analysis only; no scientific imports or new evaluations.

Run only after a process_terminal.json exists. A stopped batch is reportable;
unstarted slots remain explicit. Outputs must use a new directory.
"""
import argparse
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ROOT = HERE.parents[1]
DEFAULT_CAMPAIGN = ROOT/'results/p2_execution01'
P0_FACTS = ROOT/'results/p0_resume01/analysis01/facts.json'
NORMAL = {'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def scalar(value):
    if value is None or value == []:
        return None
    try:
        return float(F(str(value)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lo, hi = map(F, value)
        return (lo, hi) if lo <= hi else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def exact_pair(pair):
    return list(map(str, pair)) if pair is not None else None


def strictly_lower(pair_a, pair_b):
    a, b = interval(pair_a), interval(pair_b)
    return None if a is None or b is None else a[1] < b[0]


def walk(value, path='$'):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from walk(item, path+'.'+key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk(item, f'{path}[{i}]')


def saved_feedback(raw):
    """Authoritative distinct search invocations; final scenes are aliases."""
    sequences = [('$.feedback', raw.get('feedback') or [])]
    for i, phase in enumerate(raw.get('phases') or []):
        for scene, item in (phase.get('scenes') or {}).items():
            sequences.append((f'$.phases[{i}].scenes.{scene}.solver_result.feedback',
                              (item.get('solver_result') or {}).get('feedback') or []))
    return [{'source': f'{path}[{i}]', 'value': value}
            for path, values in sequences for i, value in enumerate(values)]


def evaluation_records(raw):
    """Deduplicate repeated stored full/scene-subproblem evaluator objects.

    These are saved records, NOT a reconstructed count of all thermal calls.
    """
    found = {}
    for path, value in walk(raw):
        if {'problem_id', 'scenes', 'numerical_protocol', 'state'} <= value.keys():
            key = canonical(value)
            if key not in found:
                found[key] = {'sha256': key, 'source': path, 'state': value['state'],
                    'reason': value.get('reason'), 'violations': value.get('violations') or [],
                    'completed_at_elapsed_s': value.get('completed_at_elapsed_s'),
                    'covered_scenes': sorted(value.get('scenes') or {})}
    return list(found.values())


def bounds_records(raw):
    records = []
    for path, value in walk(raw):
        if value.get('solver_reported_only') is True:
            records.append({'source': path, 'evidence': 'solver-reported only', 'value': value})
        elif value.get('kind') == 'callback' and isinstance(value.get('values'), dict):
            records.append({'source': path, 'evidence': 'solver-reported only', 'value': value})
    return records


def choose_L0(raw, folder, read):
    value = raw.get('independent_lower_bound')
    if not isinstance(value, dict):
        value = (raw.get('deployment_bounds') or {}).get('L0')
    if not isinstance(value, dict) and (folder/'independent_bounds.json').is_file():
        value = read(folder/'independent_bounds.json').get('L0')
    if (isinstance(value, dict) and value.get('is_global_lower_bound') is True
            and value.get('scope') == 'original_full_domain' and value.get('solver_reported') is False):
        return value
    return None


def scene_data(evaluation):
    rows = {}
    for scene, value in (evaluation.get('scenes') or {}).items():
        physical = value.get('result', value)
        rows[scene] = physical
    return rows


def weighted_components(evaluation, instance):
    scenes = scene_data(evaluation)
    if not scenes or set(scenes) != {s['id'] for s in instance.get('scenarios', [])}:
        return None
    result = {}
    for definition in instance['scenarios']:
        value = scenes[definition['id']]
        if value.get('complete') is not True or value.get('state') != 'SAFE':
            return None
        components = value.get('energy_components_J') or {}
        if not components:
            return None
        for key, pair in components.items():
            pair = interval(pair)
            if pair is None:
                return None
            weight = F(definition['weight'])
            old = result.setdefault(key, [F(0), F(0)])
            old[0] += weight*pair[0]; old[1] += weight*pair[1]
    return {key: exact_pair(value) for key, value in result.items()}


def phase_energies(raw, metrics):
    updates = raw.get('global_updates') or []
    initial = metrics.get('initial_complete_SAFE_energy_interval_J')
    prior = interval(initial)
    answer = []
    for phase in metrics.get('phases') or []:
        if phase.get('kind') != 'method_phase':
            continue
        idx = phase.get('phase_index')
        entry = interval(phase.get('baseline_complete_energy_interval_J')) or prior
        eligible = [u for u in updates if u.get('phase_index') == idx
                    and interval(u.get('weighted_energy_J')) is not None]
        final = interval(eligible[-1]['weighted_energy_J']) if eligible else entry
        answer.append({**phase, 'entry_complete_energy_interval_J': exact_pair(entry),
            'end_complete_energy_interval_J': exact_pair(final),
            'complete_updates_this_phase': len(eligible),
            'strict_energy_reduction_from_entry': None if entry is None or final is None else final[1] < entry[0],
            'upper_bound_reduction_J': None if entry is None or final is None else float(entry[1]-final[1])})
        prior = final
    return answer


def summary_row(slot, record, raw, folder, instance, read):
    evidence = record.get('records') or {}
    metrics = evidence.get('completion_metrics') or {}
    execution = evidence.get('execution') or {}
    evaluation = raw.get('aggregation') if slot['method'] == 'linked_fixed_unit_opp_start' else raw.get('evaluation')
    evaluation = evaluation or {}
    energy = interval(evaluation.get('weighted_energy_J'))
    usable = evidence.get('usable_U_J')
    usable_f = None if usable is None else F(usable)
    safe_receipt = (evidence.get('context') or {}).get('safe_receipt') or {}
    rankable = (usable_f is not None and energy is not None and usable_f == energy[1]
                and evaluation.get('state') == 'SAFE' and evaluation.get('rankable_energy') is True
                and safe_receipt.get('verified') is True)
    lower = choose_L0(raw, folder, read)
    L0 = None if lower is None else F(lower['lower_bound_J'])
    saved = evaluation_records(raw)
    feedback = saved_feedback(raw)
    phases = phase_energies(raw, metrics)
    return {'ordinal': slot['ordinal'], 'problem_id': slot['problem_id'], 'method': slot['id'],
        'method_kind': slot['method'], 'seed': slot.get('seed'), 'slot_state': record.get('state', 'NOT_STARTED'),
        'execution_status': execution.get('execution_status', 'NO_STORED_METHOD_RETURN'),
        'usable_U_exact_J': usable, 'safe_U_J': scalar(usable) if rankable else None,
        'safe_energy_interval_J': exact_pair(energy) if rankable else None,
        'rankable_original_receipt': rankable, 'stored_safe_receipt_verified': safe_receipt.get('verified'),
        'comparison_usable': rankable and (record.get('postcheck') or {}).get('passed') is True
                             and execution.get('execution_status') in NORMAL,
        'post_passed': (record.get('postcheck') or {}).get('passed'),
        'post_state': (record.get('postcheck') or {}).get('state'),
        'post_new_U': (record.get('postcheck') or {}).get('new_U'),
        'post_evaluator_s': (record.get('postcheck') or {}).get('elapsed_s'),
        'first_SAFE_s': metrics.get('first_complete_SAFE_at_s'),
        'first_strict_improvement_s': metrics.get('first_strict_improvement_at_s'),
        'first_strict_improvement_status': metrics.get('strict_improvement_status'),
        'method_root_s': metrics.get('root_stop_at_s'),
        'deadline_overshoot_s': metrics.get('deadline_overshoot_s'),
        'return_inclusive_s': record.get('method_return_inclusive_wall_s'),
        'matlab_startup_s': (metrics.get('matlab_startup') or {}).get('wall_s'),
        'matlab_startup_status': (metrics.get('matlab_startup') or {}).get('status'),
        'initial_safe_energy_interval_J': metrics.get('initial_complete_SAFE_energy_interval_J'),
        'certified_L0_J': None if L0 is None else float(L0),
        'certified_L0_exact_J': None if L0 is None else str(L0),
        'certified_L0_source': lower,
        'L0_above_U_anomaly': None if L0 is None or usable_f is None else L0 > usable_f,
        'certified_gap_fraction': None if L0 is None or not rankable or usable_f <= 0 else float((usable_f-L0)/usable_f),
        'independently_proven_optimal': execution.get('independently_proven_optimal') is True,
        'independently_proven_infeasible': execution.get('independently_proven_infeasible') is True,
        'safe_curve': deepcopy_json(metrics.get('complete_SAFE_receipts') or []),
        'method_phases': phases, 'scene_slices': metrics.get('scene_slices') or [],
        'accounting_phases': metrics.get('phases') or [],
        'native_requests': metrics.get('native_requests') or [],
        'feedback_saved_rows': len(feedback), 'feedback_records': feedback,
        'unique_stored_evaluation_records': len(saved),
        'thermal_violation_saved_records': sum(v['state'] == 'THERMAL_VIOLATION' for v in saved),
        'thermal_unresolved_saved_records': sum(v['state'] == 'UNRESOLVED' for v in saved),
        'evaluation_record_index': saved, 'solver_reported_records': bounds_records(raw),
        'weighted_energy_components_J': weighted_components(evaluation, instance) if rankable else None,
        'final_scene_data': {sid: {k: value.get(k) for k in ('state', 'complete', 'energy_J',
            'energy_components_J', 'peaks_degC', 'minimum_degC', 'final_temperature_degC',
            'violations', 'covered_until_s')} for sid, value in scene_data(evaluation).items()} if rankable else {},
        'candidate_sha256': canonical(raw['safe_candidate']) if rankable and raw.get('safe_candidate') else None,
        'safe_candidate': raw.get('safe_candidate') if rankable else None,
        'original_raw_state': raw.get('state'), 'original_raw_reason': raw.get('reason'),
        'source_folder': folder.relative_to(REPO).as_posix(),
        'errors': record.get('errors') or []}


def deepcopy_json(value):
    return json.loads(json.dumps(value))


def cohorts(rows):
    result = []
    for problem in sorted({r['problem_id'] for r in rows}):
        group = [r for r in rows if r['problem_id'] == problem]
        by_method = {r['method']: r for r in group}
        sa = [r['safe_U_J'] for r in group if r['method_kind'] == 'sa'
              and r.get('comparison_usable') is True and r['safe_U_J'] is not None]
        linked = by_method.get('anchor_linked4', {}); heft = by_method.get('heft', {})
        lu = linked.get('safe_U_J') if linked.get('comparison_usable') is True else None
        hu = heft.get('safe_U_J') if heft.get('comparison_usable') is True else None
        result.append({'problem_id': problem, 'declared_slots': len(group),
            'observed_calls': sum(r['slot_state'] != 'NOT_STARTED' for r in group),
            'safe_calls': sum(r['rankable_original_receipt'] for r in group),
            'post_verified_SAFE_calls': sum(r['rankable_original_receipt'] and r['post_passed'] is True for r in group),
            'linked_vs_HEFT_reduction_fraction': None if lu is None or hu is None or hu <= 0 else (hu-lu)/hu,
            'linked_strictly_lower_than_HEFT': strictly_lower(linked.get('safe_energy_interval_J'), heft.get('safe_energy_interval_J'))
                if lu is not None and hu is not None else None,
            'SA_safe_n': len(sa), 'SA_declared_n': sum(r['method_kind'] == 'sa' for r in group),
            'SA_median_J': statistics.median(sa) if sa else None,
            'SA_mean_J': statistics.mean(sa) if sa else None,
            'SA_min_J_descriptive_only': min(sa) if sa else None,
            'SA_max_J': max(sa) if sa else None,
            'SA_sample_stdev_J': statistics.stdev(sa) if len(sa) > 1 else None})
    return result


def collect(campaign, *, expected_sources=224):
    campaign = Path(campaign).resolve(); campaign.relative_to(REPO)
    source_hashes = {}
    def read(path):
        path = Path(path)
        source_hashes[path.relative_to(REPO).as_posix()] = sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    if not (campaign/'process_terminal.json').is_file():
        raise RuntimeError('No terminal process record; analysis refuses an active/unstarted batch')
    terminal = read(campaign/'process_terminal.json')
    declaration = read(campaign/'declaration.json'); ledger = read(campaign/'ledger.json')
    if len(declaration.get('source_sha256', {})) != expected_sources:
        raise ValueError('Unexpected frozen scientific/execution source count')
    verified = all(sha(REPO/name) == digest == sha(campaign/'source_snapshot'/name)
                   for name, digest in declaration['source_sha256'].items())
    if not verified:
        raise ValueError('Frozen/current source mismatch; do not analyze under a changed implementation')
    rows = []; receipts = {r['slot_id']: r for r in ledger.get('calls', [])}
    for slot in declaration['slots']:
        folder = campaign/'calls'/slot['problem_id']/slot['id']
        immutable = campaign/'claims'/(slot['slot_id']+'_result.json')
        returned = campaign/'claims'/(slot['slot_id']+'_method_return.json')
        record = (read(immutable) if immutable.is_file() else read(returned)
                  if returned.is_file() else receipts.get(slot['slot_id'], {}))
        claimed = campaign/'claims'/(slot['slot_id']+'.json')
        if not record and claimed.is_file():
            record = {**read(claimed), 'state': 'CLAIMED_NO_STORED_METHOD_RETURN'}
        raw_path = folder/'wrapper_raw_result.json'
        raw = read(raw_path) if raw_path.is_file() else {}
        instance = read(campaign/'inputs'/slot['problem_id']/'instance.json')
        row = summary_row(slot, record, raw, folder, instance, read)
        row['record_source'] = (immutable if immutable.is_file() else returned
            if returned.is_file() else campaign/'ledger.json').relative_to(REPO).as_posix()
        rows.append(row)
    for row in rows:
        heft = next((v for v in rows if v['problem_id'] == row['problem_id'] and v['method'] == 'heft'), None)
        valid = (row['comparison_usable'] and heft is not None and heft['comparison_usable']
                 and row['safe_U_J'] is not None and heft['safe_U_J'] is not None and heft['safe_U_J'] > 0)
        row['normalised_to_HEFT'] = row['safe_U_J']/heft['safe_U_J'] if valid else None
        row['strictly_lower_than_HEFT'] = strictly_lower(row['safe_energy_interval_J'], heft['safe_energy_interval_J']) if valid else None
    prior = read(P0_FACTS)
    old = {(r['problem_id'], r['method']): r for r in prior['rows']}
    comparisons = []
    for row in rows:
        previous = old.get((row['problem_id'].replace('initial_78__', 'base__'), row['method']))
        if not previous:
            continue
        p0 = previous.get('safe_U_J') if previous.get('comparison_usable') is True else None
        p2 = row['safe_U_J'] if row.get('comparison_usable') is True else None
        comparisons.append({'sample': row['problem_id'].split('__')[-1], 'method': row['method'],
            'P0_problem_id': previous['problem_id'], 'P2_problem_id': row['problem_id'],
            'P0_safe_U_J': p0, 'P2_safe_U_J': p2,
            'P2_minus_P0_U_J': None if p0 is None or p2 is None else p2-p0,
            'P0_method_root_s': previous.get('method_root_s'), 'P2_method_root_s': row['method_root_s'],
            'P0_first_SAFE_s': previous.get('first_SAFE_s'), 'P2_first_SAFE_s': row['first_SAFE_s'],
            'P0_feedback_saved_rows': previous.get('feedback_saved_rows'),
            'P2_feedback_saved_rows': row['feedback_saved_rows'],
            'scope': 'separate true initial-temperature inputs, not one uninterrupted cohort or fixed-schedule counterfactual'})
    facts = {'protocol': 'K161-P2-terminal-stored-record-analysis-v1', 'campaign': campaign.relative_to(REPO).as_posix(),
        'process_terminal': terminal, 'ledger_state': ledger.get('state'),
        'declared_slots': len(declaration['slots']),
        'consumed_total': (terminal.get('worker_terminal') or {}).get('consumed_total', ledger.get('consumed_total')),
        'ledger_consumed_total': ledger.get('consumed_total'),
        'reserved_total_method_s': ledger.get('reserved_total_method_s'),
        'frozen_source_count': len(declaration['source_sha256']), 'frozen_sources_verified': verified,
        'cohorts': cohorts(rows), 'rows': rows,
        'execution_status_counts': dict(Counter(r['execution_status'] for r in rows)),
        'method_root_sum_s': sum(r['method_root_s'] for r in rows if r['method_root_s'] is not None),
        'safe_original_receipts': sum(r['rankable_original_receipt'] for r in rows),
        'post_verified_safe_receipts': sum(r['rankable_original_receipt'] and r['post_passed'] is True for r in rows),
        'comparison_usable_calls': sum(r['comparison_usable'] for r in rows),
        'bound_anomalies': [r['problem_id']+'__'+r['method'] for r in rows if r['L0_above_U_anomaly'] is True],
        'P0_P2_separate_conditions': comparisons, 'source_sha256': source_hashes,
        'analysis_script_sha256': sha(Path(__file__)), 'new_scientific_evaluations': 0,
        'scope': 'read saved records only; raw usable U remains authoritative, post never replaces U; no proof upgrade'}
    return facts


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text('', encoding='utf-8'); return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def figures(out, facts):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'whole_milp': '#555555', 'anchor_linked4': '#1f77b4', 'heft': '#ff7f0e',
              'sa101': '#2ca02c', 'sa102': '#9467bd', 'sa103': '#8c564b', 'sa104': '#e377c2', 'sa105': '#17becf'}
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.5), constrained_layout=True)
    for ax, cohort in zip(axes, facts['cohorts']):
        group = [r for r in facts['rows'] if r['problem_id'] == cohort['problem_id']]
        for row in group:
            curve = [(x.get('completed_at_s'), scalar(x.get('safe_upper_bound_J'))) for x in row['safe_curve']]
            curve = [(t, u) for t, u in curve if t is not None and u is not None and t < 300]
            if curve:
                t, u = zip(*curve)
                stop = min(300, row['method_root_s'] if row['method_root_s'] is not None else t[-1])
                ax.step([*t, max(t[-1], stop)], [*u, u[-1]], where='post',
                        label=row['method'], color=colors[row['method']], alpha=.85, linewidth=1.2)
        lowers = sorted({r['certified_L0_J'] for r in group if r['certified_L0_J'] is not None})
        for i, lower in enumerate(lowers): ax.axhline(lower, color='black', ls='--', linewidth=.8, label='independent L0' if i == 0 else None)
        ax.set(title=cohort['problem_id'].split('__')[-1], xlabel='Method time (s)', ylabel='Safe system energy (J)', xlim=(0, 300))
        ax.grid(alpha=.2)
    legend = {}
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        legend.update(zip(labels, handles))
    if legend: fig.legend(list(legend.values()), list(legend), loc='lower center',
                          bbox_to_anchor=(.5, -.06), ncol=9, fontsize=8)
    fig.savefig(out/'safe_energy_and_independent_bound.png', dpi=180, bbox_inches='tight'); plt.close(fig)


def markdown(facts):
    def num(v, digits=9): return '—' if v is None else f'{v:.{digits}f}'
    out = ['# K161：P2原H响应高初温结果（存档提取）', '',
        f"状态：{facts['process_terminal'].get('state')}；消费{facts['consumed_total']}/{facts['declared_slots']}次。",
        '', '| 输入 | 整体MILP/J | 联动/J | HEFT/J | SA安全中位数/J | 原预算内安全输出 |',
        '|---|---:|---:|---:|---:|---:|']
    for c in facts['cohorts']:
        by = {r['method']: r for r in facts['rows'] if r['problem_id'] == c['problem_id']}
        out.append('|'+c['problem_id']+'|'+num(by.get('whole_milp', {}).get('safe_U_J'))+'|'
            +num(by.get('anchor_linked4', {}).get('safe_U_J'))+'|'+num(by.get('heft', {}).get('safe_U_J'))+'|'
            +num(c['SA_median_J'])+f"（{c['SA_safe_n']}/{c['SA_declared_n']}）|{c['safe_calls']}/{c['declared_slots']}|")
    out += ['', f"方法根时钟合{facts['method_root_sum_s']:.3f}秒；原预算内安全回执{facts['safe_original_receipts']}份，事后复核通过{facts['post_verified_safe_receipts']}份。",
        '', 'U只取原方法回执；post不补搜索、修复或替换U。未运行、无U、未决、故障分别保留，不填零能量。',
        '', 'SA逐种子及安全分布分列，最小值仅描述分布，不作为一次同预算竞争者。',
        '', 'P0/P2是50°C/78°C两个真实初温条件，原H响应与80°C温限保持；跨条件能量差不是同一固定安排的因果复算。',
        '', '热违规记录与反馈分别保存；有反馈不自动证明净求解收益。内部界保留原作用域，不能与独立全域L0合并或作为独立最优证书。',
        '', '来源、各阶段和原生界记录、SA逐次、节点峰温及能耗组成见facts.json和CSV；本工具新求解/热评价0次。', '']
    return '\n'.join(out)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--campaign', type=Path, default=DEFAULT_CAMPAIGN)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--no-plots', action='store_true')
    args = cli.parse_args(argv)
    facts = collect(args.campaign)  # Refuse active batches before creating any output.
    out = args.out.resolve(); out.relative_to(REPO); out.mkdir(parents=True, exist_ok=False)
    (out/'facts.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    scalar_keys = ['ordinal', 'problem_id', 'method', 'seed', 'slot_state', 'execution_status', 'safe_U_J',
        'usable_U_exact_J', 'rankable_original_receipt', 'comparison_usable', 'normalised_to_HEFT',
        'strictly_lower_than_HEFT', 'post_passed', 'post_state', 'first_SAFE_s',
        'first_strict_improvement_s', 'method_root_s', 'return_inclusive_s', 'matlab_startup_s',
        'certified_L0_J', 'certified_gap_fraction', 'L0_above_U_anomaly', 'feedback_saved_rows',
        'thermal_violation_saved_records', 'thermal_unresolved_saved_records', 'independently_proven_optimal',
        'independently_proven_infeasible', 'source_folder', 'record_source']
    write_csv(out/'results40.csv', ({k: r.get(k) for k in scalar_keys} for r in facts['rows']))
    write_csv(out/'cohorts.csv', facts['cohorts'])
    write_csv(out/'P0_P2_separate_conditions.csv', facts['P0_P2_separate_conditions'])
    write_csv(out/'phases.csv', ({'problem_id': r['problem_id'], 'method': r['method'], **p}
        for r in facts['rows'] for p in r['method_phases']))
    write_csv(out/'scene_energy.csv', ({'problem_id': r['problem_id'], 'method': r['method'], 'scene': sid,
        'energy_J': s.get('energy_J'), 'energy_components_J': s.get('energy_components_J')}
        for r in facts['rows'] for sid, s in r['final_scene_data'].items()))
    write_csv(out/'scene_peak_temperature.csv', ({'problem_id': r['problem_id'], 'method': r['method'],
        'scene': sid, 'node': node, 'peak_lo_degC': pair[0], 'peak_hi_degC': pair[1]}
        for r in facts['rows'] for sid, s in r['final_scene_data'].items()
        for node, pair in (s.get('peaks_degC') or {}).items()))
    (out/'summary.md').write_text(markdown(facts), encoding='utf-8')
    if not args.no_plots: figures(out, facts)
    print({'analysis_complete': True, 'declared': facts['declared_slots'], 'consumed': facts['consumed_total'],
           'safe_original_receipts': facts['safe_original_receipts'], 'new_scientific_evaluations': 0})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
