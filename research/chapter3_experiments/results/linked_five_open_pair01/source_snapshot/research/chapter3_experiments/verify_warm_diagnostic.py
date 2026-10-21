"""Archive-only audit of one completed warm-start diagnostic.

No planner, decoder, numerical row admission, thermal evaluator or solver is
imported or executed. Existing in-budget receipts alone supply safety/U.
Native publications found after the call are listed as raw evidence only.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FORMULATION = dict(fix_late_options=True, aggregate_opp_locks=True,
                   relax_auxiliary_integrality=True, energy_lower_bounds=True)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def candidate_key(candidate):
    """Compare already decoded schedules; this performs no vector decoding."""
    return tuple((sid, tuple(sorted((row['stage_id'], row['unit'], row['opp'],
                                    F(row['start_ms'])) for row in rows)))
                 for sid, rows in sorted(candidate['scenes'].items()))


def existing_path(value):
    path = Path(str(value).replace('\\', '/'))
    return path if path.is_absolute() else REPO/path


def receipt_checks(instance, candidate, evaluation, limit):
    """Check receipt identity/completeness, without repeating its analysis."""
    checks = {}
    stamp = evaluation.get('completed_at_elapsed_s')
    checks['SAFE_and_in_budget'] = (evaluation.get('state') == 'SAFE'
        and evaluation.get('rankable_energy') is True
        and stamp is not None and 0 <= stamp < limit)
    checks['matching_identity'] = evaluation.get('evidence_identity') == {
        'input_sha256': identity(instance), 'candidate_sha256': identity(candidate)}
    interval = evaluation.get('weighted_energy_J')
    checks['complete_energy_interval'] = (isinstance(interval, list) and len(interval) == 2
        and F(interval[0]) <= F(interval[1])
        and evaluation.get('safe_upper_bound_J') is not None
        and F(evaluation['safe_upper_bound_J']) == F(interval[1]))
    scenes = evaluation.get('scenes', {})
    expected = {scene['id'] for scene in instance['scenarios']}
    checks['all_scenes_and_window_complete'] = (set(scenes) == expected
        and all(scene.get('state') == 'SAFE' and scene.get('complete') is True
                and scene.get('rankable_energy') is True
                and F(scene.get('covered_until_s', '-1')) == F(instance['window_ms'])/1000
                for scene in scenes.values()))
    return checks


def summarise(result, instance, input_records=()):
    """Pure extraction/checking; valid absence of solver candidates is allowed."""
    limit = result['timing']['limit_s']
    diagnostic = result.get('diagnostic', {})
    initial = result.get('initialisation') or {}
    seed = initial.get('witness')
    seed_candidate = seed.get('candidate') if seed else None
    seed_eval = seed.get('evaluation') if seed else None
    checks, timeline = [], []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})

    if seed:
        for name, passed in receipt_checks(instance, seed_candidate, seed_eval, limit).items():
            check('initial_receipt/'+name, passed)
        check('initial_U_matches_receipt', result.get('initial_safe_upper_bound_J')
              == seed_eval.get('safe_upper_bound_J'))
        check('initial_time_matches_receipt', result.get('first_initial_safe_s')
              == seed_eval.get('completed_at_elapsed_s'))
        timeline.append({'method_elapsed_s': seed_eval['completed_at_elapsed_s'],
                         'kind': 'initial_SAFE', 'evidence': 'independent complete receipt',
                         'safe_U_J': seed_eval.get('safe_upper_bound_J'), 'same_as_seed': True})
    else:
        check('no_initial_witness_has_no_initial_U', result.get('initial_safe_upper_bound_J') is None)

    progress = diagnostic.get('solver_progress', [])
    observed = []
    for row in progress:
        stamp = row.get('method_elapsed_s')
        check('solver_event_time/'+str(len(observed)), stamp is not None and 0 <= stamp < limit)
        values = row.get('values', {})
        event = {'method_elapsed_s': stamp, 'kind': row.get('kind'),
                 'request': row.get('request'), 'phase': values.get('phase'),
                 'evidence': 'solver-reported',
                 'solver_lowerbound_J': values.get('lowerbound'),
                 'solver_fval_J': values.get('fval'),
                 'solver_relativegap': values.get('relativegap'),
                 'solver_numfeaspoints': values.get('numfeaspoints')}
        observed.append(event)
        timeline.append(event)
    entries = [row['method_elapsed_s'] for row in progress
               if row.get('kind') == 'solver_entered' and row.get('method_elapsed_s') is not None
               and 0 <= row['method_elapsed_s'] < limit]
    entry = min(entries) if entries else None
    check('solver_entry_time_matches_receipt', diagnostic.get('solver_entered_received_s') == entry)

    for row in diagnostic.get('decode_records', []):
        if row.get('within_budget'):
            check('decode_receipt_time/'+row['source'], 0 <= row['completed_at_s'] < limit)
        timeline.append({'method_elapsed_s': row.get('completed_at_s'), 'kind': 'candidate_decode',
                         'source': row.get('source'), 'decode_state': row.get('state'),
                         'evidence': 'existing legality receipt',
                         'within_budget': row.get('within_budget')})

    evaluations, safe_records = [], []
    for index, row in enumerate(diagnostic.get('evaluations', [])):
        candidate, evaluation = row['candidate'], row['evaluation']
        same = bool(seed_candidate is not None and candidate_key(candidate) == candidate_key(seed_candidate))
        good = bool(row.get('accepted_safe'))
        if good:
            for name, passed in receipt_checks(instance, candidate, evaluation, limit).items():
                check(f'solver_SAFE_receipt/{index}/'+name, passed)
            safe_records.append(row)
        item = {'source': row.get('source'), 'state': evaluation.get('state'),
                'accepted_safe': good, 'same_modes_and_starts_as_seed': same,
                'safe_U_J': evaluation.get('safe_upper_bound_J') if good else None,
                'completed_at_s': evaluation.get('completed_at_elapsed_s'),
                'candidate_identity': evaluation.get('evidence_identity', {}).get('candidate_sha256')}
        evaluations.append(item)
        timeline.append({'method_elapsed_s': evaluation.get('completed_at_elapsed_s',
                                                          row.get('evaluation_returned_at_s')),
                         'kind': 'solver_candidate_SAFE' if good else 'candidate_evaluation',
                         'source': row.get('source'), 'evidence': 'independent complete receipt' if good
                                                                else 'existing incomplete/violation receipt',
                         'safe_U_J': item['safe_U_J'], 'same_as_seed': same,
                         'evaluation_state': evaluation.get('state')})
    callback_seed = [row for row in evaluations if row['accepted_safe']
                     and row['same_modes_and_starts_as_seed'] and ':event' in (row['source'] or '')]
    seed_observed = bool(entry is not None and callback_seed)
    solver_best = min(safe_records, key=lambda row: F(row['evaluation']['safe_upper_bound_J'])) if safe_records else None
    solver_U = solver_best['evaluation']['safe_upper_bound_J'] if solver_best else None
    initial_U = seed_eval.get('safe_upper_bound_J') if seed else None
    improved = bool(initial_U is not None and solver_U is not None and F(solver_U) < F(initial_U))
    separated = bool(seed and solver_best and
        F(solver_best['evaluation']['weighted_energy_J'][1]) < F(seed_eval['weighted_energy_J'][0]))
    check('solver_U_matches_independent_receipts', result.get('milp_safe_upper_bound_J') == solver_U)
    check('improvement_flag_matches_U', result.get('milp_improved_initial_upper_bound', False) == improved)
    check('strict_separation_flag_matches_intervals',
          result.get('strict_energy_improvement_certified', False) == separated)
    check('first_solver_SAFE_time_matches_receipts', diagnostic.get('first_safe_receipt_s') ==
          min((row['evaluation']['completed_at_elapsed_s'] for row in safe_records), default=None))
    check('first_solver_legal_time_matches_receipts', diagnostic.get('first_legal_candidate_s') ==
          min((row['completed_at_s'] for row in diagnostic.get('decode_records', [])
               if row.get('state') == 'LEGAL' and row.get('within_budget')), default=None))
    available = ([('initial_constructor', seed_candidate, seed_eval)] if seed else [])
    if solver_best:
        available.append(('MILP_candidate', solver_best['candidate'], solver_best['evaluation']))
    best = min(available, key=lambda item: F(item[2]['safe_upper_bound_J'])) if available else None
    check('final_U_is_best_formed_receipt', result.get('safe_upper_bound_J') ==
          (best[2]['safe_upper_bound_J'] if best else None))
    check('final_source_is_best_formed_receipt', result.get('safe_solution_source') == (best[0] if best else None))
    if best:
        for name, passed in receipt_checks(instance, result['safe_candidate'], result['evaluation'], limit).items():
            check('final_receipt/'+name, passed)
        check('final_schedule_matches_best_receipt', candidate_key(result['safe_candidate']) == candidate_key(best[1]))
    check('no_independent_optimality_or_infeasibility_claim',
          result.get('independently_proven_optimal') is False
          and result.get('independently_proven_infeasible') is False)
    transport = any(row.get('initial_point', {}).get('provided') is True for row in input_records)
    summary = {key: result.get(key) for key in ('problem_id', 'state', 'reason', 'safe_upper_bound_J',
        'budget_exhausted', 'model_complete', 'matrix_complete', 'solver_request_attempts',
        'integer_solver_entered', 'safe_solution_source', 'initial_safe_upper_bound_J',
        'milp_safe_upper_bound_J', 'first_initial_safe_s')}
    summary.update(first_solver_integer_candidate_s=diagnostic.get('first_candidate_received_s'),
        first_solver_legal_candidate_s=diagnostic.get('first_legal_candidate_s'),
        first_solver_independent_SAFE_s=diagnostic.get('first_safe_receipt_s'),
        in_budget_solver_entry_s=entry, transport_x0_provided=transport,
        seed_incumbent_observed=seed_observed,
        seed_incumbent_observed_at_s=min((row['completed_at_s'] for row in callback_seed), default=None)
                                         if seed_observed else None,
        seed_observation_scope='in-budget callback candidate independently SAFE; same modes/starts; transport alone insufficient',
        independent_solver_evaluations=evaluations, accepted_solver_SAFE_receipts=len(safe_records),
        callback_arrangement_comparisons=[row for row in evaluations if ':event' in (row['source'] or '')],
        first_integer_candidate_scope='solver-proposed vector receipt; LEGAL and SAFE are separately checked',
        candidate_receipts=diagnostic.get('candidate_receipts', 0),
        duplicate_receipts=diagnostic.get('duplicate_receipts', 0),
        milp_really_lowered_safe_U=improved, strict_energy_intervals_separated=separated,
        solver_reported_progress=observed,
        independent_optimality=False, independently_proven_infeasible=False,
        method_elapsed_s=result['timing']['method_elapsed_s'],
        limit_s=limit, phases_exclusive_s=result['timing'].get('phases_exclusive_s'),
        formal_comparison=False,
        postprocess_scope='existing completed receipts only; no solve/decode/row/thermal recheck',
        observations_scope='one diagnostic; no causal speedup or timing stability claim')
    timeline.sort(key=lambda row: float('inf') if row.get('method_elapsed_s') is None else row['method_elapsed_s'])
    return summary, checks, timeline


def verify(folder, prior):
    folder, prior = Path(folder).resolve(), Path(prior).resolve()
    result, instance = read(folder/'result.json'), read(folder/'input_instance.json')
    integrity, prerequisites = read(folder/'source_integrity.json'), read(folder/'prerequisites.json')
    inputs = [read(path) for path in sorted((folder/'matlab').glob('*.input.json'))]
    summary, checks, timeline = summarise(result, instance, inputs)

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})

    check('one_original_900_second_call', result['problem_id'] == 'base__R1'
          and result['timing']['limit_s'] == 900 and result.get('formal_comparison') is False)
    check('source_before_after_identical', integrity.get('unchanged') is True
          and integrity['before'] == integrity['after'])
    for name, sha in integrity['after'].items():
        check('archived_source/'+name, digest(folder/'source_snapshot'/name) == sha)
    same_config = read(folder/'input_config.json') == read(prior/'input_config.json')
    same_instance = instance == read(prior/'input_instance.json')
    check('K88_input_config_identical', same_config)
    check('K88_input_instance_identical', same_instance)
    old = read(prior/'result.json')['model_summary']
    current = result['model_summary']
    feedback_rows = sum(row.get('rows_added', 0) for row in result.get('feedback', []))
    late_feedback_rows = sum(row.get('rows_added', 0) for row in result.get('late_feedback_diagnostics', []))
    static = ('variables', 'binary_variables', 'options', 'logical_binary_variables',
              'deadline_fixed_options', 'coefficient_sets', 'events_per_scene', 'formulation')
    for field in static:
        check('K88_model/'+field, current[field] == old[field])
    check('K88_initial_rows_plus_archived_feedback', current['rows'] == old['rows']+feedback_rows+late_feedback_rows)
    check('same_requested_formulation', current['formulation'] == FORMULATION)
    checkpoint = read(folder/'initial_receipt_checkpoint.json')
    check('initial_checkpoint_matches_final_initialisation', checkpoint.get('initialisation') == result.get('initialisation'))
    check('initial_checkpoint_published_in_budget', 0 <= checkpoint['publication_started_at_s'] < 900)
    claim_path = existing_path(integrity['original_claim'])
    claim = read(claim_path)
    check('exclusive_claim_targets_this_call', existing_path(claim['out']).resolve() == folder
          and claim['seconds'] == 900 and claim['retries'] == 0
          and claim['problem_id'] == 'base__R1' and claim['historical_candidate_input'] is False
          and claim['formal_comparison'] is False and claim['source_sha256'] == integrity['before'])
    matching = [path for path in folder.parent.glob('*/original_warm_run_claim.json')
                if existing_path(read(path)['out']).resolve() == folder]
    check('exactly_one_original_claim', len(matching) == 1 and matching[0].resolve() == claim_path.resolve())
    for label, records in prerequisites.items():
        for index, record in enumerate(records if isinstance(records, list) else [records]):
            path = existing_path(record['path'])
            precheck = read(path)
            check(f'prerequisite/{label}/{index}/archive_hash', digest(path) == record['sha256'])
            rows = precheck.get('checks', [])
            check(f'prerequisite/{label}/{index}/all_passed', bool(rows) and all(
                row.get('passed') is True if 'passed' in row else row.get('status') == 'PASS' for row in rows))
    raw_native = []
    for path in sorted((folder/'matlab').glob('*.response.json')):
        raw = read(path)
        raw_native.append({'file': path.name, 'sha256': digest(path), 'status': raw.get('status'),
            'exitflag': raw.get('exitflag'), 'fval': raw.get('fval'), 'output': raw.get('output'),
            'initial_point': raw.get('initial_point'), 'intlinprog_entered': raw.get('intlinprog_entered'),
            'acceptance': 'raw archive only; not newly accepted budgeted evidence'})
    raw_events = []
    for path in sorted((folder/'matlab').glob('*.event_*.json')):
        row = read(path)
        raw_events.append({'file': path.name, 'sha256': digest(path), 'kind': row.get('kind'),
                           'event_number': row.get('event_number'), 'values': row.get('values'),
                           'contains_vector': bool(row.get('x')),
                           'acceptance': 'raw native; acceptance only via recorded in-budget receipt'})
    summary.update(raw_native=raw_native, raw_native_events=raw_events,
                   input_identical_to_K88=same_config and same_instance,
                   source_unchanged_during_run=integrity.get('unchanged'),
                   initial_model_rows=old['rows'], final_model_rows=current['rows'],
                   feedback_rows_added=feedback_rows, late_feedback_rows_archival_only=late_feedback_rows,
                   original_case_calls=1,
                   analysis_source_sha256=digest(__file__))
    verification = {'passed': all(row['passed'] for row in checks), 'count': len(checks),
                    'checks': checks, 'scope': summary['postprocess_scope'],
                    'analysis_source_sha256': summary['analysis_source_sha256']}
    write(folder/'verification.json', verification)
    write(folder/'diagnostic_summary.json', summary)
    fields = sorted({key for row in timeline for key in row})
    with (folder/'timeline.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(timeline)
    return verification, summary


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', required=True, type=Path)
    parser.add_argument('--prior-dir', type=Path, default=HERE/'results/base_long_diagnostic04')
    args = parser.parse_args()
    verification, summary = verify(args.result_dir, args.prior_dir)
    print(json.dumps({'passed': verification['passed'], 'count': verification['count'],
                      'summary': {key: summary.get(key) for key in ('initial_safe_upper_bound_J',
                          'milp_safe_upper_bound_J', 'transport_x0_provided',
                          'seed_incumbent_observed', 'safe_solution_source')}}, ensure_ascii=False))
    raise SystemExit(0 if verification['passed'] else 1)
