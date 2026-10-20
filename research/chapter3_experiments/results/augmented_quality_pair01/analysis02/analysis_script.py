"""K135 post-run JSON audit. No production import, planning, decode, heat or solver.

The only imported helper is the archived K127 JSON/Fraction receipt checker.
Run only after both frozen calls have terminal ledger entries. This script
does not create, improve, or replay any physical witness.
"""
from collections import Counter
import argparse
import csv
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents
            if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
HELPER = REPO/'research/chapter3_experiments/results/night_k127_run02/analysis01/analysis_script.py'
spec = importlib.util.spec_from_file_location('saved_k127_receipt_audit', HELPER)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
read, digest, interval = a.read, a.digest, a.interval


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def csv_file(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def numeric_text(value, digits=12):
    return 'NA' if value is None else f'{float(F(value)):.{digits}f}'


def wrapper_wall(report):
    """Prefer the K135 external wrapper clock; missing is never zero."""
    timing = report.get('wrapper_timing') or {}
    value = timing.get('wrapper_call_and_primary_archive_wall_s')
    if value is None:
        value = (report.get('ledger') or {}).get('wrapper_wall_s')
    return value


def launcher_records(root):
    return {path.name: read(path) for path in sorted(root.glob('*timing*.json'))}


def vector_nonempty(value):
    """Publication presence, not validity: scalar 0 is a nonempty candidate."""
    if value is None:
        return False
    if isinstance(value, (list, tuple, dict, str, bytes)):
        return len(value) != 0
    return True


def immutable_callback_records(folder, request_number):
    if not isinstance(request_number, int) or isinstance(request_number, bool):
        return {'state': 'UNKNOWN_REQUEST_ID', 'files': [], 'read_errors': [], 'callbacks': []}
    paths = sorted(folder.rglob(f'request_{request_number:06d}.event_*.json'))
    callbacks, errors = [], []
    for path in paths:
        try:
            event = read(path)
            if not isinstance(event, dict):
                raise ValueError('event is not an object')
            if event.get('kind') == 'callback':
                callbacks.append({'file': path.relative_to(folder).as_posix(),
                    'sha256': sha(path), 'event_number': event.get('event_number'),
                    'state': event.get('state'), 'request_wall_seconds': event.get('request_wall_seconds'),
                    'values': event.get('values'), 'nonempty_vector': vector_nonempty(event.get('x'))})
        except (OSError, ValueError, TypeError) as error:
            errors.append({'file': path.relative_to(folder).as_posix(),
                           'error': f'{type(error).__name__}: {error}'})
    return {'state': ('IMMUTABLE_EVENTS_READ' if paths and not errors else
                      'PARTIAL_EVENT_READ' if paths else 'NO_EVENT_FILES_UNKNOWN'),
        'files': [path.relative_to(folder).as_posix() for path in paths],
        'read_errors': errors, 'callbacks': callbacks}


def incomplete_analysis(root, out, ledger, declaration, missing):
    """A failed first call does not manufacture a second call or pair ranking."""
    assert not out.exists(), 'never overwrite a prior analysis'
    by_id = {row['id']: row for row in ledger.get('calls', [])}
    reports, table = [], []
    for jid in ('old_n1', 'augmented_all_opp_start'):
        row = by_id.get(jid)
        entry = {'id': jid, 'ledger': row, 'state': 'NOT_RUN' if row is None else row.get('state'),
            'result_present': (root/jid/'result.json').exists(), 'complete_SAFE_audit': None,
            'reason': 'not executed after preceding stop' if row is None else row.get('error')}
        wrapper_file = root/'claims'/f'{jid}_wrapper_timing.json'
        entry['wrapper_timing'] = read(wrapper_file) if wrapper_file.exists() else None
        if row is not None and entry['result_present'] and (root/jid/'input_instance.json').exists():
            try:
                adapted = {'input_identities': {'base': {'instance_sha256': declaration['input_sha256']}}}
                verified = a.analyze_job(root, {'id': jid, 'method': 'n1', 'condition': 'base'}, row, adapted)
                entry['saved_result_audit'] = verified
                entry['complete_SAFE_audit'] = verified['final_SAFE_receipt_verified']
                entry['U_J'] = verified['final_U_J'] if verified['final_SAFE_receipt_verified'] else None
                entry['first_SAFE_s'] = verified['first_SAFE_s']
                entry['reason'] = verified.get('reason') or entry['reason']
            except (KeyError, TypeError, ValueError, OSError) as error:
                entry['saved_result_audit_error'] = f'{type(error).__name__}: {error}'
        elif row is not None and not entry['result_present']:
            entry['reason'] = 'terminal call has no saved result; ' + str(entry['reason'])
        reports.append(entry)
        table.append({key: entry.get(key) for key in
            ('id', 'state', 'result_present', 'complete_SAFE_audit', 'U_J', 'first_SAFE_s', 'reason')})
    wrappers = [wrapper_wall(entry) for entry in reports if entry['ledger'] is not None]
    facts = {'analysis': 'K135-incomplete-read-only-analysis-v1', 'quality_pair_completed': False,
        'supersedes_analysis01': {'reason': 'callback_count_schema_correction',
            'original_analysis01_preserved': True},
        'comparison_or_performance_ranking_valid': False, 'missing_or_incomplete': missing,
        'ledger': ledger, 'calls': reports, 'consumed_method_calls': ledger.get('consumed'),
        'wrapper_elapsed_s': sum(wrappers) if wrappers and all(value is not None for value in wrappers) else None,
        'external_launcher_timing_records': launcher_records(root),
        'new_solver_thermal_decode_calls': 0, 'historical_results_not_used_to_fill_missing_call': True}
    out.mkdir()
    save(out/'facts.json', facts)
    csv_file(out/'comparison.csv', table,
        ['id', 'state', 'result_present', 'complete_SAFE_audit', 'U_J', 'first_SAFE_s', 'reason'])
    lines = ['# K135：配对未完成，保留已消费调用与已有证据', '',
        '**未完成正常双方法配对，不能进行质量排名。** 未执行的方法标为NOT_RUN；缺失结果不以历史结果、局部结果或预算后补算填补。', '',
        '| 方法 | 状态 | 结果存在 | 完整SAFE回执核对 | 可保留U/J | 原因 |',
        '|---|---|---|---|---:|---|']
    for item in table:
        lines.append(f"| {item['id']} | {item['state']} | {item['result_present']} | {item['complete_SAFE_audit']} | {numeric_text(item.get('U_J'))} | {item['reason']} |")
    lines += ['', f"实际消费{ledger.get('consumed')}次方法调用；包装钟合{numeric_text(facts['wrapper_elapsed_s'], 3)}秒。独立launcher总钟另存于facts.json，不与方法预算、清理或包装尾成本混合。",
        '可读的终态结果只核已有完整回执与身份，不生成新热轨迹、候选、U或界。缺项和技术故障保持，未补跑。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'quality_pair_completed': False, 'missing': missing,
        'consumed': ledger.get('consumed'), 'out': str(out)}, ensure_ascii=False, indent=2))


def components(result, instance):
    receipt = result.get('aggregation') or {}
    values = {}
    for scene in instance['scenarios']:
        local = receipt.get('scenes', {}).get(scene['id'], {}).get('result', {})
        for key, energy in local.get('energy_components_J', {}).items():
            bounds = interval(energy)
            row = values.setdefault(key, [F(0), F(0)])
            for i in range(2):
                row[i] += F(scene['weight'])*bounds[i]
    return {key: list(map(str, row)) for key, row in values.items()}


def changes(result, jid):
    seed = (result.get('condition') or {}).get('seed_candidate')
    final = result.get('safe_candidate')
    if not seed or not final:
        return []
    rows = []
    for sid, current in final['scenes'].items():
        old = {item['stage_id']: item for item in seed['scenes'][sid]}
        for item in current:
            before = old[item['stage_id']]
            row = {'job': jid, 'scene': sid, 'stage_id': item['stage_id'],
                'unit': item['unit'], 'seed_unit': before['unit'],
                'seed_opp': before['opp'], 'final_opp': item['opp'],
                'seed_start_ms': before['start_ms'], 'final_start_ms': item['start_ms'],
                'unit_changed': item['unit'] != before['unit'],
                'opp_changed': item['opp'] != before['opp'],
                'start_changed': F(item['start_ms']) != F(before['start_ms'])}
            row['changed'] = any(row[key] for key in ('unit_changed', 'opp_changed', 'start_changed'))
            rows.append(row)
    return rows


def native_records(result, jid, folder):
    records = []
    for sid, scene in result.get('scenes', {}).items():
        for i, row in enumerate((scene.get('solver_result') or {}).get('rounds', []), 1):
            phases = row.get('phase_seconds') or {}
            used = row.get('solver_max_time_s_used')
            actual = phases.get('intlinprog_call')
            raw_events = immutable_callback_records(folder, row.get('request_number'))
            callbacks = raw_events['callbacks']
            summary_callbacks = row.get('callbacks') or []
            raw_numbers = [item.get('event_number') for item in callbacks]
            summary_numbers = [item.get('event_number') for item in summary_callbacks]
            known = raw_events['state'] == 'IMMUTABLE_EVENTS_READ'
            complete = known and sorted(raw_numbers) == sorted(summary_numbers)
            rootlp = next((item for item in callbacks
                if isinstance(item.get('values'), dict) and item['values'].get('phase') == 'rootlp'), None)
            root_values = (rootlp or {}).get('values') or {}
            native_output = row.get('output') or {}
            records.append({'job': jid, 'scene': sid, 'round': i,
                'request_number': row.get('request_number'),
                'status': row.get('status'), 'exitflag': row.get('exitflag'),
                'intlinprog_entered': row.get('intlinprog_entered'),
                'budget_valid': row.get('budget_valid'),
                'accepted_for_evaluation': row.get('accepted_for_evaluation'),
                'MaxTime_used_s': used, 'actual_intlinprog_call_s': actual,
                'stop_delay_over_MaxTime_s': None if used is None or actual is None
                    else max(0., actual-used),
                'actual_call_within_MaxTime': None if used is None or actual is None else actual <= used,
                'native_phase_seconds': phases,
                'native_output_solver_reported_only': row.get('output'),
                'bound_scope': scene.get('solver_bound_scope') or
                    ('old_N1_one_scene_conditional' if jid == 'old_n1' else
                     'seed_fixed_units_all_stage_opp_start_one_scene_conditional'),
                'numerical_consistency': row.get('numerical_consistency'),
                'callback_count': len(callbacks) if known else None,
                'native_summary_callback_count': len(summary_callbacks),
                'nonempty_callback_count': sum(item['nonempty_vector'] for item in callbacks) if known else None,
                'callback_count_origin': 'immutable request event files; response callback summaries omit x',
                'immutable_callback_publications_match_response_numbers': complete,
                'immutable_event_audit': raw_events,
                'rootlp_callback_observed': bool(rootlp) if known else None,
                'first_rootlp_native_elapsed_s': root_values.get('time'),
                'first_rootlp_event_number': (rootlp or {}).get('event_number'),
                'first_rootlp_request_wall_s': (rootlp or {}).get('request_wall_seconds'),
                'rootlp_numfeaspoints': root_values.get('numfeaspoints'),
                'rootlp_numnodes': root_values.get('numnodes'),
                'final_numfeaspoints': native_output.get('numfeaspoints'),
                'final_numnodes': native_output.get('numnodes'),
                'rootlp_timing_scope': 'native self-reported elapsed; absent callback is unknown completion, not zero time',
                'final_vector_present': vector_nonempty(row.get('x')),
                'initial_point': row.get('initial_point'),
                'augmented_admission': row.get('augmented_admission')})
    return records


def augmented_records(root, result):
    """Summarize saved gates; do not recompute arrays or validate new candidates."""
    transport = result.get('augmented_transport')
    if transport is None:
        return None
    report = {key: value for key, value in transport.items() if key != 'requests'}
    requests = []
    files = sorted(root.rglob('admission.json'))
    by_index = {read(path)['request_index']: path for path in files}
    for receipt in transport.get('requests', []):
        index = receipt['request_index']
        path = by_index.get(index)
        stored = read(path) if path else None
        mapping_path = None if path is None else path.parent/'mapping.json'
        mapping = read(mapping_path) if mapping_path and mapping_path.exists() else {}
        checks = receipt.get('numerical_checks', [])
        selected = mapping.get('exact_row_selection') or {}
        retained = selected.get('retained_nonrepresentable_physical_rows', [])
        condensed = []
        for item in checks:
            gate = item.get('report') or {}
            condensed.append({key: item.get(key) for key in
                ('source', 'started_at_s', 'completed_at_s', 'within_budget', 'accepted', 'reason')}
                | {'original': gate.get('original'), 'augmented': gate.get('augmented'),
                   'link_max_abs_residual': gate.get('link_max_abs_residual'),
                   'constraint_tolerance': gate.get('constraint_tolerance'),
                   'integer_tolerance': gate.get('integer_tolerance'),
                   'report_accepted': gate.get('accepted'), 'report_reasons': gate.get('reasons'),
                   'objective_check': item.get('objective_check')})
        requests.append({'request_index': index,
            'archive_relative_path': None if path is None else path.relative_to(root).as_posix(),
            'archive_matches_result_receipt': stored == receipt,
            'failure_reasons': receipt.get('failure_reasons'),
            'latched_unresolved': receipt.get('latched_unresolved'),
            'callback_publications_complete': receipt.get('callback_publications_complete'),
            'expected_callback_numbers': receipt.get('expected_callback_numbers'),
            'checked_callback_numbers': receipt.get('checked_callback_numbers'),
            'events': receipt.get('events'), 'checks': condensed,
            'original_n': mapping.get('original_n'), 'augmented_n': mapping.get('augmented_n'),
            'new_continuous_variables': mapping.get('new_variables'),
            'physical_rows_rewritten': mapping.get('physical_rows_rewritten'),
            'physical_rows_retained_original': len(retained),
            'retained_original_row_indices': [item['row'] for item in retained],
            'all_retained_rows_marked_bitwise': all(
                item.get('original_expression_retained_bitwise') is True for item in retained),
            'all_stored_numerical_gates_accepted': all(item.get('accepted') is True for item in checks),
            'original_numerical_gate_maxima': {key: max((
                (item.get('report') or {}).get('original', {}).get(key, 0) for item in checks), default=None)
                for key in ('inequality_violation', 'equality_violation', 'lower_bound_violation',
                            'upper_bound_violation', 'integer_violation')},
            'scope': 'stored transport/gate consistency only; not independent matrix recomputation or SAFE'})
    report['requests'] = requests
    report['archived_request_count'] = len(files)
    return report


def analyze(root, out):
    ledger, declaration = read(root/'ledger.json'), read(root/'declaration.json')
    rows = ledger['calls']
    assert all(row['state'] not in ('RUNNING', 'DECLARED', 'PREPARED') for row in rows), 'unfinished calls'
    assert ledger['state'] not in ('RUNNING', 'PREPARED'), 'unfinished paired ledger'
    expected = ['old_n1', 'augmented_all_opp_start']
    missing = {'consumed': ledger.get('consumed'), 'observed_ids': [row['id'] for row in rows],
        'missing_result_ids': [jid for jid in expected if not (root/jid/'result.json').exists()]}
    if ledger.get('consumed') != 2 or [row['id'] for row in rows] != expected or missing['missing_result_ids']:
        incomplete_analysis(root, out, ledger, declaration, missing)
        return
    assert not out.exists(), 'never overwrite a prior analysis'
    raw_hashes = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*')
        if path.is_file() and 'source_snapshot' not in path.parts
        and not any(part.startswith('analysis') for part in path.parts)
        and path.suffix in ('.json', '.jsonl', '.txt', '.log')}
    jobs, raw, stage_rows, natives = [], {}, [], []
    for row in rows:
        jid = row['id']; folder = root/jid
        result, instance = read(folder/'result.json'), read(folder/'input_instance.json')
        raw[jid] = result
        job = {'id': jid, 'method': 'n1', 'condition': 'base'}
        adapted = {'input_identities': {'base': {'instance_sha256': declaration['input_sha256']}}}
        report = a.analyze_job(root, job, row, adapted)
        report['job']['method'] = row['method']
        report['condition_sha256'] = report.pop('N1_condition_sha256')
        report['method_completed_without_technical_block'] = row['state'] == 'COMPLETED'
        report['scope_note'] = 'Same fresh seed-fixed devices; old local suffix vs all-Stage OPP/start. Neither is global search.'
        report['input_scene_stage_counts'] = {s['id']: len(s['stage_instances']) for s in instance['scenarios']}
        report['original_weights'] = {s['id']: s['weight'] for s in instance['scenarios']}
        report['components_J'] = components(result, instance)
        report['seed_candidate_sha256'] = digest(result['condition']['seed_candidate'])
        report['distinct_saved_full_SAFE_candidates'] = len({digest(c) for c, r, _ in
            a.full_evaluations(result, 'n1') if r.get('state') == 'SAFE'})
        report['post_initialisation_strict_U_updates'] = [point for point in report['updates']
            if point['source'] != 'initial_constructor'
            and report['initial_energy_J'] and F(point['energy_J'][1]) < F(report['initial_energy_J'][0])]
        report['augmented_transport_saved_audit'] = augmented_records(folder, result)
        report['archive_timing'] = read(folder/'archive_timing.json') if (folder/'archive_timing.json').exists() else None
        wrapper_file = root/'claims'/f'{jid}_wrapper_timing.json'
        report['wrapper_timing'] = read(wrapper_file) if wrapper_file.exists() else None
        report['method_return_inclusive_wall_s'] = row.get('method_return_inclusive_wall_s')
        report['scene_search_metrics'] = {sid: {
            'search_started_at_s': scene.get('search_started_at_s'),
            'search_returned_at_s': scene.get('search_returned_at_s'),
            'model_view_evaluation_records': len(scene.get('model_view_evaluations') or []),
            'original_input_evaluation_records': len(scene.get('original_scene_evaluations') or []),
            'original_receipt_cache_hits': scene.get('original_receipt_cache_hits'),
            'model_summary': scene.get('model_summary'),
            'reason': scene.get('reason')}
            for sid, scene in result.get('scenes', {}).items()}
        jobs.append(report)
        stage_rows.extend(changes(result, jid)); natives.extend(native_records(result, jid, folder))
    old, new = jobs
    old_e = interval(old['final_energy_J']) if old['final_energy_J'] else None
    new_e = interval(new['final_energy_J']) if new['final_energy_J'] else None
    same_seed = (old['seed_candidate_sha256'] == new['seed_candidate_sha256']
                 and old['initial_energy_J'] == new['initial_energy_J'])
    complete = all(job['method_completed_without_technical_block'] for job in jobs)
    old_in_new = bool(same_seed and raw['old_n1'].get('safe_candidate') and all(
        item['unit'] == next(seed['unit'] for seed in raw['augmented_all_opp_start']['condition']['seed_candidate']['scenes'][sid]
                           if seed['stage_id'] == item['stage_id'])
        and item['stage_id'] in raw['augmented_all_opp_start']['condition']['opened_by_scene'][sid]
        for sid, items in raw['old_n1']['safe_candidate']['scenes'].items() for item in items))
    wrappers = [wrapper_wall(job) for job in jobs]
    comparison = {'stage': 'K135', 'identical_fresh_seed_candidate_and_energy': same_seed,
        'quality_pair_completed': complete, 'single_pair_not_statistical_ranking': True,
        'strict_new_improvement_over_old_observed': bool(old_e and new_e and new_e[1] < old_e[0]),
        'strict_old_improvement_over_new_observed': bool(old_e and new_e and old_e[1] < new_e[0]),
        'old_interval_J': old.get('final_energy_J'), 'new_interval_J': new.get('final_energy_J'),
        'signed_relative_new_minus_old_using_safe_uppers': None if not old_e or not new_e
            else str((new_e[1]-old_e[1])/old_e[1]),
        'new_strict_saving_vs_old_lower_fraction': None if not old_e or not new_e
            else str((old_e[0]-new_e[1])/old_e[0]),
        'old_SAFE_candidate_inside_new_fixed_unit_domain_static': old_in_new,
        'new_research_calls': len(rows), 'reserved_method_budget_s': 600,
        'method_elapsed_s': sum(job['timing']['method_elapsed_s'] for job in jobs),
        'wrapper_elapsed_s': sum(wrappers) if all(value is not None for value in wrappers) else None,
        'wrapper_clock_source': 'claims/<id>_wrapper_timing.json:wrapper_call_and_primary_archive_wall_s; legacy ledger only if present',
        'external_launcher_timing_records': launcher_records(root),
        'cleanup_elapsed_s': sum((job['ledger'].get('cleanup') or {}).get('cleanup_wall_seconds', 0) for job in jobs),
        'posthoc_physical_work_or_search': False,
        'all_final_SAFE_receipts_consistent': all(job['raw_state'] != 'SAFE' or job['final_SAFE_receipt_verified'] for job in jobs),
        'all_unchanged_execution_units': not any(row['unit_changed'] for row in stage_rows),
        'no_global_optimality_claim': True}
    # Historical quality background is read only after the two terminal calls.
    historical = root.parent/'night_k127_run02/base_heft/result.json'
    hr, hi = read(historical), read(historical.parent/'input_instance.json')
    assert digest(hi) == declaration['input_sha256']
    he = a.full_safe(hr['evaluation'], hr['safe_candidate'], hi, hr['timing']['limit_s'], 'heft', hr)
    comparison['HEFT_historical_only'] = {'result_sha256': sha(historical), 'energy_J': list(map(str, he)),
        'old_signed_relative_U_gap': None if old_e is None else str((old_e[1]-he[1])/he[1]),
        'new_signed_relative_U_gap': None if new_e is None else str((new_e[1]-he[1])/he[1]),
        'not_concurrent_timing': True, 'not_optimality_gap': True, 'not_method_initialization': True}
    frozen = {name: sha(root/'source_snapshot'/name) == value and sha(REPO/name) == value
              for name, value in declaration['source_sha256'].items()}
    assert all(frozen.values()), 'frozen source changed'
    assert all(sha(root/rel) == value for rel, value in raw_hashes.items()), 'raw archive changed'
    facts = {'protocol': declaration['protocol'], 'analysis': 'K135-read-only-frozen-quality-pair-v2',
        'supersedes_analysis01': {'reason': 'callback_count_schema_correction',
            'original_analysis01_preserved': True,
            'correction': 'nonempty callback count comes from immutable event x, not x-free response summaries; root LP times and native point/node counts added'},
        'inherited_receipt_checker': {'path': HELPER.relative_to(REPO).as_posix(), 'sha256': sha(HELPER)},
        'scope': 'stored receipt/clock/identity audit; no schedule decode, thermal replay or search',
        'calls': jobs, 'comparison': comparison, 'stage_changes': stage_rows, 'native_call_times': natives,
        'raw_hashes_before': raw_hashes, 'raw_unchanged': True,
        'frozen_source_count': len(frozen), 'all_frozen_current_and_snapshot_sources_match': True}
    out.mkdir()
    save(out/'facts.json', facts)
    csv_file(out/'comparison.csv', [dict(job=job['job']['id'], ledger_state=job['ledger']['state'],
        U_J=job['final_U_J'], first_SAFE_s=job['first_SAFE_s'], method_s=job['timing']['method_elapsed_s'],
        feedback=job['feedback_records'], strict_vs_seed=job['strict_improvement_over_this_call_seed'],
        complete_SAFE_audit=job['final_SAFE_receipt_verified']) for job in jobs],
        ['job', 'ledger_state', 'U_J', 'first_SAFE_s', 'method_s', 'feedback', 'strict_vs_seed', 'complete_SAFE_audit'])
    csv_file(out/'stage_changes.csv', stage_rows, ['job', 'scene', 'stage_id', 'unit', 'seed_unit', 'seed_opp',
        'final_opp', 'seed_start_ms', 'final_start_ms', 'unit_changed', 'opp_changed', 'start_changed', 'changed'])
    csv_file(out/'phase_costs.csv', [dict(job=job['job']['id'], phase=phase, exclusive_s=value)
        for job in jobs for phase, value in job['timing'].get('phases_exclusive_s', {}).items()],
        ['job', 'phase', 'exclusive_s'])
    csv_file(out/'energy_updates.csv', [dict(job=job['job']['id'], at_s=point['at_s'], source=point['source'],
        energy_lower_J=point['energy_J'][0], U_J=point['energy_J'][1], candidate_sha256=point['candidate_sha256'])
        for job in jobs for point in job['updates']],
        ['job', 'at_s', 'source', 'energy_lower_J', 'U_J', 'candidate_sha256'])
    timing_fields = ['job', 'scene', 'round', 'request_number', 'status', 'exitflag',
        'intlinprog_entered', 'budget_valid', 'accepted_for_evaluation', 'MaxTime_used_s',
        'actual_intlinprog_call_s', 'stop_delay_over_MaxTime_s', 'actual_call_within_MaxTime',
        'callback_count', 'nonempty_callback_count', 'final_vector_present',
        'rootlp_callback_observed', 'first_rootlp_native_elapsed_s', 'first_rootlp_event_number',
        'rootlp_numfeaspoints', 'rootlp_numnodes', 'final_numfeaspoints', 'final_numnodes']
    csv_file(out/'native_timing.csv', [{key: item.get(key) for key in timing_fields} for item in natives], timing_fields)
    plot(out, jobs)
    lines = ['# K135：原基准旧N1与增广新版的独立质量配对', '',
        '材料：两次已终止调用的只读存档分析。原base__R1完整AB／AC三Stage链、400 ms窗口、5 ms启动域、auto-L与完整连续热标准不变；各一次300秒上限，scene60秒为合作式限额。', '',
        '**本版analysis02替代analysis01的回调计数口径：** response的callbacks摘要不含x，非空向量须从不可变event文件统计，标量0也计非空发布。analysis01原样保留，能量结果没有追改。rootlp时间及节点／可行点数量只按原生自报登记，缺少rootlp事件不填0或推断完成。', '',
        '| 方法 | 技术状态 | 完整安全U/J | 首SAFE/s | 方法耗时/s | 初始化外严格改善 |',
        '|---|---|---:|---:|---:|---|']
    for job in jobs:
        first = 'NA' if job['first_SAFE_s'] is None else f"{job['first_SAFE_s']:.3f}"
        lines.append(f"| {job['job']['id']} | {job['ledger']['state']} | {numeric_text(job['final_U_J'])} | {first} | {job['timing']['method_elapsed_s']:.3f} | {bool(job['post_initialisation_strict_U_updates'])} |")
    lines += ['', f"**新版严格低于旧N1：{comparison['strict_new_improvement_over_old_observed']}；质量配对正常完成：{complete}。** 严格比较使用新版能量上端＜旧版能量下端；不以近似打印值或求解器内部gap替代。",
        f"两调用fresh种子候选和完整初始能量一致：{same_seed}；完整SAFE回执一致性通过：{comparison['all_final_SAFE_receipts_consistent']}。",
        '', f"K127 HEFT历史安全U={numeric_text(he[1])} J，仅作事后质量背景，不作同期速度、最优差距或免费初始化。",
        '', '每份被报告为SAFE的安排均核对原输入全场景、完整窗口、连续峰温区间、功率适用范围、分项守恒、精确场景权重及预算内形成时刻。此处只核已有回执，不重算热；接纳失败、超时、技术故障与已有SAFE分列。',
        '工作点／起点实际变化见stage_changes.csv。共享A具体unit与场景内A工作点／时序分层；本次设备均固定于各自fresh种子，没有部署重选。',
        '独立L0与安全U分列；单场景局部内部bound／gap只原样保存，不聚合成全域证明。没有独立最优或无解结论。连续热反馈、严格热违规与初始化筛查分别计数，0次也保留。',
        '', f"两次方法耗时合{comparison['method_elapsed_s']:.3f}秒，包装合{numeric_text(comparison['wrapper_elapsed_s'], 3)}秒，清理合{comparison['cleanup_elapsed_s']:.3f}秒。独立launcher总钟另存，不与包装钟混称。原生MaxTime实际停止延迟见facts.json；合作式60秒不写成硬实时截止，所有U仍受单一300秒证据截止约束。",
        f"当前源码与快照{len(frozen)}项匹配；原档案未改。[安全U与独立L0](energy_bounds.png)。详细分项、矩阵门、映射保留行、内部状态和时间见facts.json。", '',
        '本轮没有补跑、调温限、增加邻域、使用历史候选或恢复115次正式批次。单次结果不支持统计稳定性或普遍加速主张。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


def plot(out, jobs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.6, 4.8), layout='constrained')
    for job, color in zip(jobs, ('#2864a0', '#d87b20')):
        points = job['updates']; end = min(300., job['timing']['method_elapsed_s'])
        if points:
            x = [point['at_s'] for point in points]
            y = [float(F(point['energy_J'][1])) for point in points]
            ax.step(x+[max(x[-1], end)], y+[y[-1]], where='post', color=color, label=job['job']['id']+' SAFE U')
            ax.scatter(x, y, color=color, s=13)
        lower = job['independent_bounds'].get('L0')
        if lower and not job['independent_bound_errors']:
            ax.plot([lower['formed_at_s'], end], [float(F(lower['lower_bound_J']))]*2,
                    linestyle=':', color=color, alpha=.65, label=job['job']['id']+' independent L0')
    ax.set(xlim=(0, 300), xlabel='Billed method elapsed time (s)', ylabel='Weighted system energy (J)')
    ax.grid(alpha=.2); ax.legend(fontsize=7)
    fig.savefig(out/'energy_bounds.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=REPO/'research/chapter3_experiments/results/augmented_quality_pair01')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    analyze(root, (args.out or root/'analysis02').resolve())
