"""K138 stored-result audit. Never imports production, decodes, evaluates heat or solves.

Run only after the pair ledger is terminal. All U values come from already saved
complete original-input SAFE receipts. Staged local scene metadata is diagnostic,
not a replacement for committed_safe_snapshot. The archived JSON-only K127/K135
checkers are the only imported project helpers. Historical HEFT is not read.
"""
from collections import Counter, defaultdict
import argparse
import csv
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents
            if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
HELPER = REPO/'research/chapter3_experiments/results/augmented_quality_pair01/analysis02/analysis_script.py'
spec = importlib.util.spec_from_file_location('saved_k135_json_audit', HELPER)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
a = b.a
read, digest, interval, save, numeric_text = b.read, b.digest, b.interval, b.save, b.numeric_text
EXPECTED = ('old_n1', 'staged_n1_all')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (list, dict)) else value for key, value in row.items()})


def raw_hashes(root, paths=None):
    if paths is not None:
        return {rel: sha(root/rel) for rel in paths}
    return {path.relative_to(root).as_posix(): sha(path)
        for path in sorted(root.rglob('*')) if path.is_file()
        and 'source_snapshot' not in path.relative_to(root).parts
        and not any(part.startswith('analysis') for part in path.relative_to(root).parts)}


def source_audit(root, declaration):
    rows = []
    for rel, expected in declaration['source_sha256'].items():
        current, snapshot = REPO/rel, root/'source_snapshot'/rel
        rows.append({'path': rel, 'expected_sha256': expected,
            'current_sha256': sha(current) if current.is_file() else None,
            'snapshot_sha256': sha(snapshot) if snapshot.is_file() else None})
    return {'count': len(rows), 'all_match': all(row['expected_sha256'] == row['current_sha256']
        == row['snapshot_sha256'] for row in rows), 'files': rows}


def source_identity_checks(identity, instance, condition, declaration, *, scene=None):
    checks = {'full_input': identity.get('full_input_sha256') == digest(instance),
        'platform': identity.get('platform_sha256') == digest(instance['platform']),
        'execution_rules': identity.get('execution_rules_sha256') == digest(instance['execution_rules']),
        'control_policy': identity.get('control_policy') == instance['execution_rules']['idle_policy'],
        'shared_deployment': identity.get('shared_deployment_sha256') == digest(condition['shared_deployment']),
        'accuracy': identity.get('accuracy_sha256') == digest(condition['accuracy']),
        'budget': identity.get('budget') == condition.get('budget_identity')}
    expected_sources = {Path(rel).name: value for rel, value in declaration['source_sha256'].items()}
    sources = identity.get('source_sha256') or {}
    required_sources = {'scene_adapter.py', 'schedules.py', 'thermal.py', 'start_domain.py', 'interval.py', 'control_policy.py'}
    checks['evaluator_sources'] = set(sources) == required_sources and all(expected_sources.get(name) == value
        for name, value in sources.items())
    if scene is not None:
        checks.update(scene_id=identity.get('scenario_id') == scene['id'],
            scene=identity.get('scenario_sha256') == digest(scene),
            entry=identity.get('entry_sha256') == digest(scene['entry']))
    return checks


def originals(result):
    """Immutable stored original-input receipts with their provenance, no cache replay."""
    rows = []
    for i, attempt in enumerate(result.get('seed_attempts', [])):
        for sid, receipt in attempt.get('scene_evaluations', {}).items():
            rows.append((sid, receipt, f'seed_attempts/{i}/scene_evaluations/{sid}'))
    for sid, scene in result.get('scenes', {}).items():
        for i, item in enumerate(scene.get('original_scene_evaluations', [])):
            receipt = item.get('receipt')
            if isinstance(receipt, dict):
                rows.append((sid, receipt, f'scenes/{sid}/original_scene_evaluations/{i}/receipt'))
    for pi, phase in enumerate(result.get('phases', [])):
        for sid, scene in phase.get('scenes', {}).items():
            for i, item in enumerate(scene.get('original_scene_evaluations', [])):
                receipt = item.get('receipt')
                if isinstance(receipt, dict):
                    rows.append((sid, receipt, f'phases/{pi}/scenes/{sid}/original_scene_evaluations/{i}/receipt'))
    for sid, receipt in (result.get('committed_safe_snapshot') or {}).get('scene_receipts', {}).items():
        rows.append((sid, receipt, f'committed_safe_snapshot/scene_receipts/{sid}'))
    return rows


def receipt_audit(result, instance, declaration):
    condition = result.get('condition') or {}
    final = result.get('aggregation') or {}
    candidate = result.get('safe_candidate')
    limit = result['timing']['limit_s']
    report = {'final_full_SAFE_verified': False, 'checks': {}, 'scenes': {}, 'errors': []}
    if not condition or result.get('state') != 'SAFE' or candidate is None:
        report['errors'].append('No complete final SAFE/condition available')
        return report
    try:
        energy = a.full_safe(final, candidate, instance, limit, 'n1', result)
        report['final_full_SAFE_verified'] = True
        report['final_energy_J'] = list(map(str, energy))
        report['checks'].update(source_identity_checks(final['identity'], instance, condition, declaration))
        report['checks']['result_U'] = F(result['safe_upper_bound_J']) == energy[1]
        report['checks']['weights_sum_exactly_one'] = sum(F(s['weight']) for s in instance['scenarios']) == 1
        report['checks']['complete_400ms_window'] = F(instance['window_ms']) == 400
        report['checks']['one_300s_budget'] = F(limit) == 300 and F(condition['budget_identity']['seconds']) == 300
        report['checks']['independent_fresh_call_no_shared_candidate_cache'] = result.get('candidate_and_cache_shared_between_calls') is False
        seed = condition['seed_candidate']
        report['checks']['all_final_units_anchored_to_original_fresh_seed'] = all(
            {item['stage_id']: item['unit'] for item in candidate['scenes'][sid]} ==
            {item['stage_id']: item['unit'] for item in rows} for sid, rows in seed['scenes'].items())
        origin_rows = originals(result)
        for scene in instance['scenarios']:
            sid = scene['id']; local = final['scenes'][sid]
            checks = source_identity_checks(local['identity'], instance, condition, declaration, scene=scene)
            provenance = [path for saved_sid, saved, path in origin_rows
                          if saved_sid == sid and saved == local]
            checks['original_receipt_present_in_retained_original_archive'] = bool(provenance)
            local_candidate = {'scenes': {sid: candidate['scenes'][sid]}}
            checks['candidate_hash'] = local['identity']['candidate_sha256'] == digest(local_candidate)
            checks['local_deployment_hash'] = local['identity'].get('local_deployment_sha256') == digest(local.get('local_deployment'))
            checks['same_budget_as_complete_final'] = local['identity']['budget'] == final['identity']['budget']
            checks['no_post_budget_receipt'] = a.timely(local.get('completed_at_elapsed_s'), limit)
            report['scenes'][sid] = {'checks': checks, 'all_pass': all(checks.values()),
                'original_receipt_sha256': local.get('receipt_sha256'), 'original_provenance': provenance,
                'primary_original_archive_provenance_present': any(not p.startswith('committed_safe_snapshot/') for p in provenance),
                'candidate_sha256': digest(local_candidate), 'weight': scene['weight'],
                'covered_until_s': local['result']['covered_until_s'],
                'energy_J': local['result']['energy_J'],
                'energy_components_J': local['result']['energy_components_J'],
                'conservation_energy_J': local['result']['conservation_energy_J'],
                'peaks_degC': local['result']['peaks_degC'], 'minimum_degC': local['result']['minimum_degC'],
                'completed_at_elapsed_s': local['completed_at_elapsed_s']}
        snap = result.get('committed_safe_snapshot')
        if snap is not None:
            checks = {'candidate_matches_final': snap.get('safe_candidate') == candidate,
                'aggregation_matches_final': snap.get('aggregation') == final,
                'U_matches_final': snap.get('safe_upper_bound_J') == result.get('safe_upper_bound_J'),
                'energy_matches_final': snap.get('weighted_energy_J') == result.get('weighted_energy_J'),
                'timestamp_matches_final': snap.get('committed_at_s') == final.get('completed_at_elapsed_s'),
                'scene_receipts_match_final': snap.get('scene_receipts') == final.get('scenes'),
                'scene_candidates_match_final': all(snap.get('scene_candidates', {}).get(sid) ==
                    {'scenes': {sid: rows}} for sid, rows in candidate['scenes'].items())}
            report['committed_snapshot'] = {'checks': checks, 'all_pass': all(checks.values()),
                'phase_index': snap.get('phase_index'), 'candidate_sha256': digest(snap.get('safe_candidate'))}
            report['checks']['complete_snapshot_consistent'] = all(checks.values())
        report['all_pass'] = (all(report['checks'].values()) and
                              all(row['all_pass'] for row in report['scenes'].values()))
    except (KeyError, ValueError, TypeError) as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
        report['all_pass'] = False
    return report


def condition_audit(result, instance, declaration):
    conditions = [(0, result.get('condition'))]
    conditions += [(p['phase_index'], p.get('condition')) for p in result.get('phases', [])]
    first = result.get('condition') or {}
    expected_sources = {Path(rel).name: value for rel, value in declaration['source_sha256'].items()}
    rows = []
    for index, cond in conditions:
        if not cond:
            continue
        hashed = {key: value for key, value in cond.items() if key != 'condition_sha256'}
        checks = {'hash': cond.get('condition_sha256') == digest(hashed),
            'original_input': cond.get('source_input_sha256') == digest(instance),
            'fresh_seed_unchanged': cond.get('seed_candidate') == first.get('seed_candidate'),
            'fresh_seed_receipt_unchanged': cond.get('seed_receipt') == first.get('seed_receipt'),
            'seed_candidate_hash': cond.get('seed_candidate_sha256') == digest(cond.get('seed_candidate')),
            'budget_unchanged': cond.get('budget_identity') == first.get('budget_identity'),
            'shared_A_deployment_unchanged': cond.get('shared_deployment') == first.get('shared_deployment'),
            'shared_A_deployment_matches_declaration': cond.get('shared_deployment') == declaration.get('shared_deployment')}
        src = 'fixed_unit_neighborhood.py' if index == 2 else 'neighborhood.py'
        checks['condition_source'] = cond.get('condition_source_sha256') == expected_sources.get(src)
        if index == 2:
            checks['every_original_Stage_opened'] = cond.get('opened_by_scene') == {
                scene['id']: sorted(s['id'] for s in scene['stage_instances']) for scene in instance['scenarios']}
            deps = cond.get('condition_dependency_sha256') or {}
            checks['condition_dependencies'] = bool(deps) and all(expected_sources.get(key) == value for key, value in deps.items())
        rows.append({'phase_index': index, 'protocol': cond.get('protocol'), 'checks': checks,
            'all_pass': all(checks.values()), 'condition_sha256': cond.get('condition_sha256'),
            'seed_candidate_sha256': cond.get('seed_candidate_sha256'),
            'opened_by_scene': cond.get('opened_by_scene'), 'seed_options_by_scene': cond.get('seed_options_by_scene')})
    return rows


def verified_updates(result, instance):
    """Use only committed global_updates, each matched to a saved full SAFE receipt."""
    available = []
    for candidate, receipt, source in a.full_evaluations(result, 'n1'):
        if receipt.get('state') == 'SAFE':
            energy = a.full_safe(receipt, candidate, instance, result['timing']['limit_s'], 'n1', result)
            available.append((candidate, receipt, source, list(map(str, energy))))
    updates, previous = [], None
    for i, update in enumerate(result.get('global_updates', [])):
        matching = [(c, r, s, e) for c, r, s, e in available
            if r.get('completed_at_elapsed_s') == update.get('committed_at_s')
            and r.get('weighted_energy_J') == update.get('weighted_energy_J')
            and r.get('safe_upper_bound_J') == update.get('safe_upper_bound_J')]
        a.require(bool(matching), f'global_updates/{i} lacks matching complete SAFE')
        candidate, receipt, _, energy = matching[0]
        a.require(previous is None or F(energy[1]) < F(previous), 'global U does not strictly decrease')
        phase = update.get('phase_index')
        if phase is None:
            phase = 0 if update.get('trigger_source') == 'initial_constructor' else 1
        a.require(phase in (0, 1, 2), 'unknown update phase')
        point = {'at_s': update['committed_at_s'], 'phase_index': phase,
            'source': update.get('trigger_source'), 'trigger_scene': update.get('trigger_scene'),
            'energy_J': energy, 'candidate_sha256': digest(candidate),
            'receipt_sha256': receipt['receipt_sha256'], 'global_update_index': i,
            'transferred_at_s': update.get('transferred_at_s'),
            'source_path': f'result.json#/global_updates/{i}'}
        updates.append(point); previous = energy[1]
    if result.get('state') == 'SAFE':
        a.require(bool(updates), 'SAFE lacks committed global update')
        a.require(updates[-1]['candidate_sha256'] == digest(result['safe_candidate']), 'global update/final candidate differ')
        a.require(F(updates[-1]['energy_J'][1]) == F(result['safe_upper_bound_J']), 'global update/final U differ')
    return updates


def windows(result):
    end = F(str(result['timing']['method_elapsed_s']))
    phases = result.get('phases') or []
    if not phases:
        starts = [F(str(row['start_s'])) for row in result['timing'].get('phase_records', [])
                  if row['phase'] == 'model_construction']
        start = min(starts) if starts else end
        return [{'slot': 'initial_and_condition', 'phase_index': 0, 'start': F(0), 'end': start,
                 'clock_source': 'root origin to first model_construction; old method has no phase record'},
                {'slot': 'phase1_N1', 'phase_index': 1, 'start': start, 'end': end,
                 'clock_source': 'first model_construction to method return; inferred old method interval'}]
    rows, cursor = [], F(0)
    for phase in phases:
        index = phase['phase_index']; start = F(str(phase['started_at_s']))
        stop = F(str(phase.get('completed_at_s', float(end))))
        a.require(cursor <= start <= stop <= end + F('0.001'), 'phase intervals overlap or exceed method clock')
        if start > cursor:
            slot = 'initial_and_condition' if index == 1 else 'phase2_setup_before_phase_record'
            rows.append({'slot': slot, 'phase_index': 0 if index == 1 else None,
                'start': cursor, 'end': start, 'clock_source': 'timestamp gap outside saved phase interval'})
        rows.append({'slot': 'phase1_N1' if index == 1 else 'phase2_all_open',
            'phase_index': index, 'start': start, 'end': min(stop, end),
            'clock_source': f'result.json#/phases/{index-1}/started_at_s,completed_at_s'})
        cursor = min(stop, end)
    if cursor < end:
        rows.append({'slot': 'method_tail_after_last_phase', 'phase_index': None,
            'start': cursor, 'end': end, 'clock_source': 'timestamp gap after saved phase interval'})
    return rows


def clock_audit(result, jid):
    """Split nested budget records at every timestamp; charge deepest active frame once."""
    timing = result['timing']; end = F(str(timing['method_elapsed_s']))
    slots = windows(result); frames = timing.get('phase_records', [])
    cuts = {F(0), end}
    parsed = []
    for index, row in enumerate(frames):
        start, stop = F(str(row['start_s'])), F(str(row['end_s']))
        a.require(start <= stop, 'negative stored budget phase')
        start, stop = max(F(0), start), min(end, stop)
        if start < stop:
            parsed.append((start, stop, row.get('depth', 0), index, row['phase']))
            cuts.update((start, stop))
    for row in slots:
        cuts.update((row['start'], row['end']))
    cost = defaultdict(F); collisions = []
    cuts = sorted(cuts)
    for start, stop in zip(cuts, cuts[1:]):
        if stop <= start:
            continue
        active = [frame for frame in parsed if frame[0] <= start and stop <= frame[1]]
        if active:
            depth = max(frame[2] for frame in active)
            deepest = [frame for frame in active if frame[2] == depth]
            if len(deepest) != 1:
                collisions.append({'start_s': str(start), 'end_s': str(stop),
                    'same_depth_active_frames': [frame[3] for frame in deepest]})
            name = max(deepest, key=lambda frame: (frame[0], frame[3]))[4]
        else:
            name = 'unattributed'
        slot = next((row['slot'] for row in slots if row['start'] <= start and stop <= row['end']), 'outside_defined_intervals')
        cost[(slot, name)] += stop-start
    rows = [{'job': jid, 'slot': slot, 'budget_phase': name, 'exclusive_s': float(value),
        'exclusive_seconds_exact_fraction': str(value), 'fraction_of_full_method': str(value/end) if end else None}
        for (slot, name), value in sorted(cost.items())]
    totals = {row['slot']: float(row['end']-row['start']) for row in slots}
    actual = defaultdict(F)
    for (slot, name), value in cost.items():
        actual[name] += value
    differences = {name: float(actual[name]-F(str(saved)))
        for name, saved in timing.get('phases_exclusive_s', {}).items()}
    return {'intervals': [{**row, 'start': float(row['start']), 'end': float(row['end']),
                'elapsed_s': float(row['end']-row['start'])} for row in slots],
        'interval_totals_s': totals, 'exclusive_costs': rows, 'same_depth_collisions': collisions,
        'total_exclusive_s': float(sum(cost.values(), F(0))),
        'exclusive_sum_matches_method_elapsed': sum(cost.values(), F(0)) == end,
        'maximum_difference_from_saved_named_exclusive_s': max(map(abs, differences.values()), default=0),
        'differences_from_saved_named_exclusive_s': differences,
        'scope': 'root clock fractions partitioned once by timestamps and deepest active frame; phase2 setup remains outside phase2 record'}, rows


def phase_report(result, jid, updates, clocks):
    rows = []
    for index in (1, 2) if jid == 'staged_n1_all' else (1,):
        marker = next((row for row in clocks['intervals'] if row['phase_index'] == index), None)
        prior = [point for point in updates if point['phase_index'] < index]
        own = [point for point in updates if point['phase_index'] == index]
        before = prior[-1] if prior else None
        after = own[-1] if own else before
        before_e, after_e = (interval(before['energy_J']) if before else None,
                             interval(after['energy_J']) if after else None)
        strict = bool(before_e and after_e and after_e[1] < before_e[0])
        row = {'job': jid, 'phase_index': index, 'phase_name': 'N1' if index == 1 else 'all_stage_opp_start',
            'entered': marker is not None, 'started_at_s': marker['start'] if marker else None,
            'completed_at_s': marker['end'] if marker else None,
            'recorded_interval_elapsed_s': marker['elapsed_s'] if marker else None,
            'starting_complete_energy_J': before['energy_J'] if before else None,
            'starting_complete_U_J': str(before_e[1]) if before_e else None,
            'final_complete_energy_J': after['energy_J'] if after else None,
            'final_complete_U_J': str(after_e[1]) if after_e else None,
            'committed_U_decrease_count': len(own), 'strict_energy_improvement_vs_own_before_interval': strict,
            'U_decrease_J': str(before_e[1]-after_e[1]) if before_e and after_e else None,
            'strict_saving_vs_before_lower_fraction': str((before_e[0]-after_e[1])/before_e[0])
                if before_e and after_e and before_e[0] > 0 else None,
            'pre_record_phase2_setup_s': clocks['interval_totals_s'].get('phase2_setup_before_phase_record', 0.) if index == 2 else None,
            'scope': 'complete globally committed SAFE U; never one-scene local or solver objective'}
        rows.append(row)
    return rows


def phase_scene_records(result, jid):
    if result.get('phases'):
        for phase in result['phases']:
            for sid, scene in phase.get('scenes', {}).items():
                yield phase['phase_index'], sid, scene
    else:
        for sid, scene in result.get('scenes', {}).items():
            yield 1, sid, scene


def warm_snapshot_audit(result, instance, updates):
    """Match second-pass x0 source to the complete generation at its snapshot timestamp."""
    if not result.get('phases'):
        return []
    candidates = {digest(candidate): candidate for candidate, receipt, _ in a.full_evaluations(result, 'n1')
                  if receipt.get('state') == 'SAFE'}
    frames = sorted((frame for frame in result['timing'].get('phase_records', [])
                     if frame['phase'] == 'committed_warm_snapshot'), key=lambda row: row['start_s'])
    second = next((phase for phase in result['phases'] if phase['phase_index'] == 2), {})
    rows = []
    for i, scene in enumerate(instance['scenarios']):
        sid = scene['id']; local = second.get('scenes', {}).get(sid) or {}
        initial = local.get('initialisation')
        if initial is None:
            continue
        frame = frames[i] if i < len(frames) else None
        earlier = [point for point in updates if frame is not None and point['at_s'] <= frame['start_s']]
        latest = earlier[-1] if earlier else None
        warm_hash = initial.get('snapshot_candidate_sha256')
        warm = candidates.get(warm_hash)
        checks = {'snapshot_timestamp_recorded': frame is not None,
            'latest_complete_generation_hash': latest is not None and latest['candidate_sha256'] == warm_hash,
            'retained_complete_candidate_found': warm is not None,
            'local_x0_candidate_matches_complete_generation': warm is not None and initial.get('candidate') ==
                {'scenes': {sid: warm['scenes'][sid]}},
            'source_is_complete_commit': initial.get('source') == 'last_committed_full_aggregate'}
        rows.append({'phase_index': 2, 'scene': sid, 'checks': checks, 'all_pass': all(checks.values()),
            'snapshot_candidate_sha256': warm_hash, 'snapshot_start_s': None if frame is None else frame['start_s'],
            'snapshot_end_s': None if frame is None else frame['end_s'],
            'latest_complete_update_index': None if latest is None else latest['global_update_index']})
    return rows


def native_and_models(result, jid, folder):
    native, models, bounds, feedback = [], [], [], []
    for index, sid, scene in phase_scene_records(result, jid):
        local = {'scenes': {sid: scene}}
        for row in b.native_records(local, jid, folder):
            row['phase_index'] = index
            row['scope'] = 'solver-reported conditional scene diagnostics; never complete U or original-domain proof'
            native.append(row)
        models.append({'phase_index': index, 'scene': sid, 'model_complete': scene.get('model_complete'),
            'model_completed_at_s': scene.get('model_completed_at_s'), 'model_summary': scene.get('model_summary'),
            'preprocessing': scene.get('preprocessing'), 'initialisation': scene.get('initialisation'),
            'initial_checkpoint': scene.get('initial_checkpoint'), 'x0_injected': scene.get('x0_injected'),
            'bare_MILP_fallback': scene.get('bare_MILP_fallback'),
            'scene_slice_s': scene.get('scene_slice_s'), 'search_started_at_s': scene.get('search_started_at_s'),
            'search_returned_at_s': scene.get('search_returned_at_s'), 'reason': scene.get('reason'),
            'worker_admission': scene.get('worker_admission')})
        for record in scene.get('solver_reported_bounds', []):
            bounds.append({'phase_index': index, 'scene': sid, 'solver_reported_only': True, 'record': record})
        for record in (scene.get('solver_result') or {}).get('feedback', []):
            feedback.append({'phase_index': index, 'scene': sid, 'record': record})
    return native, models, bounds, feedback


def augmented_audit(folder, result):
    report = b.augmented_records(folder, result)
    if report is None:
        return None
    terminal = {row['request_index']: row for row in result['augmented_transport'].get('requests', [])}
    for row in report['requests']:
        rel = row.get('archive_relative_path')
        stored = read(folder/rel) if rel else None
        final = terminal[row['request_index']]
        saved_checks = (stored or {}).get('numerical_checks', [])
        final_checks = final.get('numerical_checks', [])
        same_except_checks = stored is not None and {k:v for k,v in stored.items() if k != 'numerical_checks'} == {
            k:v for k,v in final.items() if k != 'numerical_checks'}
        prefix = same_except_checks and saved_checks == final_checks[:len(saved_checks)]
        row['admission_archive_saved_numerical_check_count'] = len(saved_checks) if stored is not None else None
        row['terminal_result_numerical_check_count'] = len(final_checks)
        row['saved_admission_is_exact_earlier_numerical_check_prefix'] = prefix
        row['terminal_only_additional_checks'] = [{key: check.get(key) for key in
            ('source', 'started_at_s', 'completed_at_s', 'accepted', 'within_budget', 'reason')}
            for check in final_checks[len(saved_checks):]] if prefix else None
        row['archive_consistency_scope'] = 'byte/JSON equality or exact saved prefix identified; no archive rewritten'
    return report


def job_audit(root, declaration, row):
    jid = row['id']; folder = root/jid
    if not (folder/'result.json').is_file() or not (folder/'input_instance.json').is_file():
        return {'id': jid, 'ledger': row, 'state': 'MISSING_SAVED_RESULT', 'result_present': False}, [], [], [], []
    result, instance = read(folder/'result.json'), read(folder/'input_instance.json')
    a.require(digest(instance) == declaration['input_sha256'], jid+' frozen input mismatch')
    config = read(folder/'input_config.json')
    a.require(digest(config) == declaration['config_sha256'], jid+' frozen config mismatch')
    a.require((result.get('condition') or {}).get('accuracy', config['accuracy_targets']) == config['accuracy_targets'],
              jid+' condition accuracy differs from frozen config')
    adapted = {'input_identities': {'base': {'instance_sha256': declaration['input_sha256']}}}
    report = a.analyze_job(root, {'id': jid, 'method': 'n1', 'condition': 'base'}, row, adapted)
    receipt = receipt_audit(result, instance, declaration)
    conditions = condition_audit(result, instance, declaration)
    updates = verified_updates(result, instance)
    clocks, costs = clock_audit(result, jid)
    phases = phase_report(result, jid, updates, clocks)
    warm = warm_snapshot_audit(result, instance, updates)
    native, models, bounds, feedback = native_and_models(result, jid, folder)
    wrapper_file = root/'claims'/f'{jid}_wrapper_timing.json'
    complete_safe = bool(report['final_SAFE_receipt_verified'] and receipt.get('all_pass')
                         and all(item['all_pass'] for item in conditions) and all(item['all_pass'] for item in warm))
    report.update(id=jid, result_present=True, state=result.get('state'), method=row.get('method'),
        final_SAFE_receipt_verified=complete_safe, committed_receipt_audit=receipt, conditions_audit=conditions,
        seed_candidate_sha256=digest((result.get('condition') or {}).get('seed_candidate')),
        seed_receipt_sha256=(result.get('condition') or {}).get('seed_receipt_sha256'),
        config_sha256=digest(config),
        final_U_J=result.get('safe_upper_bound_J') if complete_safe else None,
        final_energy_J=receipt.get('final_energy_J') if complete_safe else None,
        first_SAFE_s=min((point['at_s'] for point in updates), default=None), updates=updates,
        phase_attribution=phases, clock_attribution=clocks, phase_model_and_initialisation_records=models,
        phase_warm_snapshot_audit=warm,
        native_call_times=native, solver_reported_bounds=bounds, feedback_log=feedback,
        feedback_records=len(feedback), feedback_rows=sum(item['record'].get('rows_added', 0) for item in feedback),
        distinct_saved_full_SAFE_candidates=len({digest(candidate) for candidate, receipt, _ in a.full_evaluations(result, 'n1')
                                                if receipt.get('state') == 'SAFE'}),
        components_J=b.components(result, instance) if result.get('aggregation') else {},
        original_weights={s['id']: s['weight'] for s in instance['scenarios']},
        input_scene_stage_counts={s['id']: len(s['stage_instances']) for s in instance['scenarios']},
        original_receipt_cache_hits_by_scene={sid: scene.get('original_receipt_cache_hits') for sid, scene in result.get('scenes', {}).items()},
        latest_local_scene_metadata_is_not_the_committed_global_ledger=bool(result.get('phases')),
        committed_safe_snapshot_phase_index=(result.get('committed_safe_snapshot') or {}).get('phase_index'),
        search_failure_latched=result.get('search_failure_latched'), worker_reusable=result.get('worker_reusable'),
        staged_budget_boundary=result.get('staged_budget_boundary'),
        augmented_transport_saved_audit=augmented_audit(folder, result),
        wrapper_timing=read(wrapper_file) if wrapper_file.is_file() else None,
        archive_timing=read(folder/'archive_timing.json') if (folder/'archive_timing.json').is_file() else None,
        method_return_inclusive_wall_s=row.get('method_return_inclusive_wall_s'),
        technical_state=result.get('technical_state'), stop_stage=result.get('stop_stage'), stop_scene=result.get('stop_scene'),
        candidate_and_cache_shared_between_calls=result.get('candidate_and_cache_shared_between_calls'),
        source_paths={'complete_U': f'{jid}/result.json#/aggregation',
            'staged_final_generation': f'{jid}/result.json#/committed_safe_snapshot' if result.get('phases') else None,
            'phase_updates': f'{jid}/result.json#/global_updates',
            'phase_models_native': f'{jid}/result.json#/phases' if result.get('phases') else f'{jid}/result.json#/scenes',
            'clock': f'{jid}/result.json#/timing/phase_records'},
        scope_note='stored JSON only; one original fresh seed per call; fixed execution units, scene-specific OPP/start; no global optimization proof')
    report['feedback_action_counts'] = dict(Counter(action.get('type', 'UNKNOWN') for item in feedback
        for action in item['record'].get('actions', [])))
    return report, native, phases, costs, b.changes(result, jid)


def plot(out, jobs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    for job, color in zip(jobs, ('#24689d', '#d4771b')):
        points = job.get('updates') or []
        end = min(300., (job.get('timing') or {}).get('method_elapsed_s', 300.))
        if points:
            x = [point['at_s'] for point in points]; y = [float(F(point['energy_J'][1])) for point in points]
            ax.step(x+[max(x[-1], end)], y+[y[-1]], where='post', color=color, label=job['id']+' complete SAFE U')
            ax.scatter(x, y, color=color, s=15)
        lower = (job.get('independent_bounds') or {}).get('L0')
        if lower and not job.get('independent_bound_errors'):
            ax.plot([lower['formed_at_s'], end], [float(F(lower['lower_bound_J']))]*2,
                linestyle=':', color=color, alpha=.7, label=job['id']+' independent L0')
        for phase in job.get('phase_attribution', []):
            if phase['phase_index'] == 2 and phase['entered']:
                ax.axvline(phase['started_at_s'], linestyle='--', linewidth=.8, color=color, alpha=.6,
                    label='phase 2 record starts (setup precedes this)')
    ax.set(xlim=(0, 300), xlabel='Full method elapsed time, all preparation included (s)',
        ylabel='Original weighted system energy (J)')
    ax.grid(alpha=.2)
    if any(job.get('updates') for job in jobs):
        ax.legend(fontsize=7)
    fig.savefig(out/'energy_bounds.png', dpi=180)
    plt.close(fig)


def main(root, out, refresh=False):
    a.require(not out.exists() or refresh, 'never overwrite an analysis without explicit refresh authorization')
    previous = read(out/'facts.json') if out.exists() else None
    ledger, declaration = read(root/'ledger.json'), read(root/'declaration.json')
    a.require(ledger.get('state') not in ('RUNNING', 'PREPARED', 'DECLARED'), 'pair ledger not terminal')
    rows = ledger.get('calls') or []
    a.require(all(row.get('state') not in ('RUNNING', 'PREPARED', 'DECLARED') for row in rows), 'call not terminal')
    before = raw_hashes(root, previous['raw_hashes_before'] if previous is not None else None)
    if previous is not None:
        a.require(before == previous['raw_hashes_before'], 'original research archives changed before derived-output refresh')
    frozen = source_audit(root, declaration)
    jobs, native, phases, costs, changes = [], [], [], [], []
    by_id = {row['id']: row for row in rows}
    for jid in EXPECTED:
        if jid not in by_id:
            jobs.append({'id': jid, 'state': 'NOT_RUN', 'result_present': False,
                'final_SAFE_receipt_verified': False, 'reason': 'missing terminal call; no historical result substituted'})
            continue
        try:
            report, nr, pr, cr, sr = job_audit(root, declaration, by_id[jid])
        except (OSError, KeyError, TypeError, ValueError) as error:
            report = {'id': jid, 'ledger': by_id[jid], 'state': 'SAVED_AUDIT_BLOCKED',
                'result_present': (root/jid/'result.json').is_file(), 'final_SAFE_receipt_verified': False,
                'audit_error': f'{type(error).__name__}: {error}',
                'reason': 'stored result audit could not complete; no heat re-evaluation or substitute result'}
            nr, pr, cr, sr = [], [], [], []
        jobs.append(report); native += nr; phases += pr; costs += cr; changes += sr
    old, new = jobs
    old_e = interval(old['final_energy_J']) if old.get('final_energy_J') else None
    new_e = interval(new['final_energy_J']) if new.get('final_energy_J') else None
    normal = (ledger.get('consumed') == 2 and [row['id'] for row in rows] == list(EXPECTED)
        and all(row.get('state') == 'COMPLETED' for row in rows)
        and all(job.get('result_present') and not job.get('audit_error') for job in jobs))
    same_seed = bool(old.get('seed_candidate_sha256') and
        old.get('seed_candidate_sha256') == new.get('seed_candidate_sha256') and
        old.get('initial_energy_J') == new.get('initial_energy_J'))
    strict = bool(normal and old_e and new_e and new_e[1] < old_e[0])
    comparison = {'stage': 'K138', 'quality_pair_completed': normal,
        'same_task_pair_comparison_valid': normal and all(job.get('final_SAFE_receipt_verified') for job in jobs),
        'single_pair_not_statistical_ranking': True, 'identical_fresh_seed_candidate_and_energy': same_seed,
        'strict_new_improvement_over_old_observed': strict,
        'strict_criterion': 'new complete SAFE energy upper < old complete SAFE energy lower',
        'old_interval_J': old.get('final_energy_J'), 'new_interval_J': new.get('final_energy_J'),
        'signed_relative_new_minus_old_using_safe_uppers': str((new_e[1]-old_e[1])/old_e[1]) if old_e and new_e else None,
        'strict_saving_vs_old_lower_fraction': str((old_e[0]-new_e[1])/old_e[0]) if old_e and new_e else None,
        'strict_saving_vs_old_lower_J': str(old_e[0]-new_e[1]) if old_e and new_e else None,
        'strict_saving_vs_old_lower_microjoule_decimal': float((old_e[0]-new_e[1])*1000000) if old_e and new_e else None,
        'strict_saving_vs_old_lower_percent_decimal': float((old_e[0]-new_e[1])/old_e[0]*100) if old_e and new_e else None,
        'consumed_method_calls': ledger.get('consumed'), 'declared_call_limit': declaration.get('method_call_limit'),
        'method_elapsed_sum_s': sum(job.get('timing', {}).get('method_elapsed_s', 0.) for job in jobs),
        'cleanup_elapsed_sum_s': sum((job.get('ledger', {}).get('cleanup') or {}).get('cleanup_wall_seconds', 0.) for job in jobs),
        'all_unchanged_execution_units': not any(row['unit_changed'] for row in changes),
        'all_final_complete_SAFE_receipts_consistent': all(job.get('final_SAFE_receipt_verified') for job in jobs),
        'no_new_thermal_decode_model_or_solver_calls': True, 'no_historical_HEFT_read': True,
        'old_final_not_injected_into_new_call': 'not an experiment input; fresh seed equality and per-phase seed identity checked',
        'no_global_optimality_claim': True,
        'comparison_scope': 'combined search opening/order and remaining-budget use; no single-factor attribution'}
    wrapper_times = [b.wrapper_wall(job) for job in jobs]
    comparison['wrapper_elapsed_sum_s'] = sum(wrapper_times) if all(v is not None for v in wrapper_times) else None
    by_method_stage = {jid: {(row['scene'], row['stage_id']): row for row in changes if row['job'] == jid} for jid in EXPECTED}
    pair_changes = []
    for key, old_row in by_method_stage['old_n1'].items():
        new_row = by_method_stage['staged_n1_all'].get(key)
        if new_row is not None and any(old_row[field] != new_row[field] for field in ('unit', 'final_opp', 'final_start_ms')):
            pair_changes.append({'scene': key[0], 'stage_id': key[1],
                'old_unit': old_row['unit'], 'new_unit': new_row['unit'],
                'old_opp': old_row['final_opp'], 'new_opp': new_row['final_opp'],
                'old_start_ms': old_row['final_start_ms'], 'new_start_ms': new_row['final_start_ms']})
    comparison['final_pair_stage_differences'] = pair_changes
    after = raw_hashes(root, before)
    a.require(before == after, 'raw saved artifacts changed during analysis')
    a.require(frozen['all_match'], 'current/source snapshot mismatch')
    facts = {'analysis': 'K138-stored-pair-complete-ledger-phase-audit-v1', 'protocol': declaration['protocol'],
        'scope': 'stored original-input SAFE receipt identity, interval accounting, timestamps and immutable event audit only',
        'helpers': [{'path': HELPER.relative_to(REPO).as_posix(), 'sha256': sha(HELPER)},
                    {'path': b.HELPER.relative_to(REPO).as_posix(), 'sha256': sha(b.HELPER)}],
        'declaration_sha256': sha(root/'declaration.json'), 'ledger': ledger, 'calls': jobs,
        'comparison': comparison, 'phase_attribution': phases, 'native_call_times': native,
        'stage_changes': changes, 'phase_exclusive_costs': costs,
        'external_launcher_timing_records': b.launcher_records(root),
        'raw_hashes_before': before, 'raw_hashes_after': after, 'raw_unchanged': before == after,
        'frozen_sources': frozen, 'new_research_native_thermal_decode_model_calls': 0,
        'evidence_boundary': 'No post-budget forced U or bound; no native objective treated as complete SAFE; no historical seed or quality result used'}
    out.mkdir(parents=True, exist_ok=refresh)
    save(out/'facts.json', facts)
    write_csv(out/'comparison.csv', [{'job': job['id'], 'ledger_state': job.get('ledger', {}).get('state', job.get('state')),
        'complete_SAFE_audit': job.get('final_SAFE_receipt_verified'), 'initial_energy_J': job.get('initial_energy_J'),
        'final_energy_J': job.get('final_energy_J'), 'U_J': job.get('final_U_J'), 'first_SAFE_s': job.get('first_SAFE_s'),
        'method_s': job.get('timing', {}).get('method_elapsed_s'), 'technical_state': job.get('technical_state'),
        'reason': job.get('reason'), 'latch': job.get('search_failure_latched')} for job in jobs])
    write_csv(out/'phase_attribution.csv', phases, ['job', 'phase_index', 'phase_name', 'entered', 'started_at_s',
        'completed_at_s', 'recorded_interval_elapsed_s', 'starting_complete_energy_J', 'starting_complete_U_J',
        'final_complete_energy_J', 'final_complete_U_J', 'committed_U_decrease_count',
        'strict_energy_improvement_vs_own_before_interval', 'U_decrease_J', 'strict_saving_vs_before_lower_fraction',
        'pre_record_phase2_setup_s', 'scope'])
    write_csv(out/'energy_updates.csv', [dict(job=job['id'], **point,
        energy_lower_J=point['energy_J'][0], U_J=point['energy_J'][1]) for job in jobs for point in job.get('updates', [])],
        ['job', 'at_s', 'phase_index', 'source', 'trigger_scene', 'energy_J', 'candidate_sha256', 'receipt_sha256',
         'global_update_index', 'transferred_at_s', 'source_path', 'energy_lower_J', 'U_J'])
    nf = ['job', 'phase_index', 'scene', 'round', 'request_number', 'status', 'exitflag', 'intlinprog_entered',
        'budget_valid', 'accepted_for_evaluation', 'MaxTime_used_s', 'actual_intlinprog_call_s',
        'stop_delay_over_MaxTime_s', 'actual_call_within_MaxTime', 'callback_count', 'nonempty_callback_count',
        'final_vector_present', 'rootlp_callback_observed', 'first_rootlp_native_elapsed_s',
        'first_rootlp_event_number', 'rootlp_numfeaspoints', 'rootlp_numnodes', 'final_numfeaspoints', 'final_numnodes']
    write_csv(out/'native_timing.csv', [{key: row.get(key) for key in nf} for row in native], nf)
    write_csv(out/'stage_changes.csv', changes, ['job', 'scene', 'stage_id', 'unit', 'seed_unit', 'seed_opp',
        'final_opp', 'seed_start_ms', 'final_start_ms', 'unit_changed', 'opp_changed', 'start_changed', 'changed'])
    write_csv(out/'phase_costs.csv', costs, ['job', 'slot', 'budget_phase', 'exclusive_s',
        'exclusive_seconds_exact_fraction', 'fraction_of_full_method'])
    plot(out, jobs)
    lines = ['# K138：旧N1与两遍版本的存档配对分析', '',
        f"正常完成配对：{normal}；新版严格低于旧版：{strict}。仅改善{comparison['strict_saving_vs_old_lower_microjoule_decimal']:.9f}微焦耳（{comparison['strict_saving_vs_old_lower_percent_decimal']:.12f}%），全部来自第一遍N1；第二遍完整U更新0，不能归为第二遍收益或稳定优势。" if old_e and new_e else
        f"正常完成配对：{normal}；无法依据两个完整SAFE区间比较。",
        '严格判据为新版完整安全能量上端＜旧版完整安全能量下端；量级与判据分别报告。',
        '', '| 方法 | 初始完整U/J | 最终完整安全U/J | 首SAFE/s | 全方法/s | 技术状态 |',
        '|---|---|---:|---:|---:|---|']
    for job in jobs:
        lines.append(f"| {job['id']} | {numeric_text(job['initial_energy_J'][1]) if job.get('initial_energy_J') else 'NA'} | {numeric_text(job.get('final_U_J'))} | {numeric_text(job.get('first_SAFE_s'),3)} | {numeric_text(job.get('timing',{}).get('method_elapsed_s'),3)} | {job.get('ledger',{}).get('state',job.get('state'))} |")
    lines += ['', '| 方法/阶段 | 自身阶段前完整U/J | 阶段后完整U/J | 严格改善 | 阶段记录区间/s | 记录前第二遍准备/s |',
        '|---|---:|---:|---|---:|---:|']
    for row in phases:
        lines.append(f"| {row['job']}/{row['phase_index']} | {numeric_text(row['starting_complete_U_J'])} | {numeric_text(row['final_complete_U_J'])} | {row['strict_energy_improvement_vs_own_before_interval']} | {numeric_text(row['recorded_interval_elapsed_s'],3)} | {numeric_text(row['pre_record_phase2_setup_s'],3)} |")
    lines += ['', f"两调用fresh种子及初始完整能量一致：{same_seed}；最终完整SAFE回执及原输入身份核对通过：{comparison['all_final_complete_SAFE_receipts_consistent']}。",
        '新旧最终安排只在AB场景B.post起点不同：145→150 ms；执行单元、OPP及其他安排相同。微降来自新版第一遍AB的round1:final（80.328 s），最终完整U在第一遍AC聚合形成（142.297 s）。' if pair_changes else '最终安排的逐Stage对照见facts.json。',
        '阶段U仅从global_updates匹配完整SAFE聚合；新版最终安排以committed_safe_snapshot与aggregation一致性为准。scenes可能保留尚未进入完整账本的局部代，不能用作最终U。',
        '全方法300秒包含初始种子、导入／适配、模型、x0、两遍切换、增广准备、求解、回调及复核。阶段记录区间没有涵盖其开始前的第二遍setup；该时间单列。phase_costs.csv按记录时间戳及最深活动帧进行一次性独占分摊，命名预算帧的壁钟不直接相加。',
        'native_timing.csv分列MaxTime、实际intlinprog调用与停止延迟。合作式片段时限不是硬实时停止保证；完整U仍须在单一根截止前形成。回调非空向量取不可变event文件，缺失事件不填0。',
        '第二遍AB的admission.json保存3条数值门，终态result保存4条：原3条完全相同，另有209.235→209.250 s的round1:final接纳门仅在终态result。其余请求字段一致，AC档案完全一致；未修改原档案，也不将该第二遍附加归档差异当成SAFE或质量收益。',
        '完整回执核对400 ms全窗口、所有节点温峰／最低温区间、功率适用域、分项守恒、精确场景权重、来源／预算／候选哈希及种子固定执行单元。缓存命中只复用原回执，最终场景回执须能追溯到种子或原输入评价存档。未重新计算热轨迹。',
        '独立L0与局部求解器自报bound/gap分列；未形成全局最优、无解、统计稳定性或单因素归因结论。单次两遍组织同时改变开放顺序和余量利用。',
        f"源码／快照{frozen['count']}项一致；原始存档分析前后哈希一致。缺失／阻塞调用保留原状态，不以历史HEFT或预算后补算填补。",
        '[完整安全U与独立L0](energy_bounds.png)。详细模型规模、初始点、回调、增广门、锁存及各阶段时间见facts.json。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=REPO/'research/chapter3_experiments/results/staged_quality_pair01')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--refresh-existing-analysis', action='store_true',
                        help='Only with explicit authorization: replace derived analysis files while checking original raw hashes')
    args = parser.parse_args()
    root = args.run.resolve()
    main(root, (args.out or root/'analysis01').resolve(), args.refresh_existing_analysis)
