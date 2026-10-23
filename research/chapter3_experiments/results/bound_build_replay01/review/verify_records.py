"""Independent arithmetic/identity cross-check of stored K171 run02, no bound API."""
import ast
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
REPO = HERE.parents[4]
CHECKS = []

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def check(name, passed, context=None):
    CHECKS.append({'name': name, 'passed': bool(passed), 'context': context})

def compatible(candidate, partial):
    lookup = {sid: {r['stage_id']: r for r in rows} for sid, rows in candidate['scenes'].items()}
    return all(all(lookup[sid][stage][field] == value for field, value in fields.items())
        for sid, stages in partial['by_scene'].items() for stage, fields in stages.items())

def expected_partial(instance, condition, phase_index):
    by_scene = {}
    for scene in instance['scenarios']:
        sid = scene['id']
        by_scene[sid] = {}
        for stage in scene['stage_instances']:
            key = stage['id']
            value = {'unit': condition['seed_options_by_scene'][sid][key]['unit']}
            if key not in condition['opened_by_scene'][sid]:
                source = condition['warm_options_by_scene'] if phase_index == 2 else condition['seed_options_by_scene']
                value['opp'] = source[sid][key]['opp']
            by_scene[sid][key] = value
    return {'by_scene': by_scene}

def main():
    started = time.perf_counter()
    paths = [AUDIT / 'run02/results.json', AUDIT / 'timeline/facts.json', AUDIT / 'domain/facts.json',
             AUDIT / 'replay.py', HERE / 'helper_checks_run01.json', HERE / 'helper_function_binding.json']
    source_before = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p) for p in paths}
    run, timeline, domain = (read(p) for p in paths[:3])
    check('root_run_final_passed', run['passed'])
    check('root_checks_all_true', all(run['checks'].values()))
    check('timeline_and_domain_verified', timeline['status'] == 'PASS' and domain['passed'])
    check('domain_503_checks', len(domain['checks']) == 503 and all(c['passed'] for c in domain['checks']))
    check('root_original_frozen_hashes_equal', run['frozen_sha256_before'] == run['frozen_sha256_after'])
    for name, value in run['frozen_sha256_before'].items():
        check('root_frozen_current_hash', sha(REPO / name) == value, name)
    ast_source = ast.parse((AUDIT / 'replay.py').read_bytes())
    tested = read(HERE / 'helper_function_binding.json')
    actual_functions = {n.name: hashlib.sha256(ast.dump(n, include_attributes=False).encode()).hexdigest()
        for n in ast_source.body if isinstance(n, ast.FunctionDef) and n.name in tested['function_AST_sha256']}
    check('final_helpers_AST_equal_17_tested_helpers', actual_functions == tested['function_AST_sha256'])
    check('original_helper_test_passed', read(HERE / 'helper_checks_run01.json')['passed'])
    expected_keys = {f"{c['problem_id']}/phase_{p['phase_index']}/{p['scene_id']}"
        for c in timeline['cases'] for p in c['builds']}
    actual_keys = [r['build_key'] for r in run['records']]
    check('twenty_unique_builds_match_timeline', len(actual_keys) == len(set(actual_keys)) == 20 and set(actual_keys) == expected_keys)
    case_archive = {}
    per_build = []
    total_probe_modes = total_exclusions = total_options = 0
    for case in timeline['cases']:
        instance = read(REPO / case['input_path'])
        result = read(REPO / case['result_path'])
        case_archive[case['problem_id']] = (instance, result, case)
        check('canonical_original_input_identity', canonical(instance) == case['input_sha256'], case['problem_id'])
    for record in run['records']:
        key = record['build_key']
        instance, original, case = case_archive[record['case_id']]
        point = next(p for p in case['builds'] if p['phase_index'] == record['phase_index'] and p['scene_id'] == record['scene_id'])
        d = next(b for b in domain['builds'] if b['build_key'] == key)
        phase = next(p for p in original['phases'] if p['phase_index'] == record['phase_index'])
        condition = phase['condition']
        partial = expected_partial(instance, condition, record['phase_index'])
        check('phase_partial_from_original_two_scene_fixedunit_closedOPP', record['phase_condition'] == d['phase_condition'] == partial, key)
        check('condition_identity_cross_all_records', record['condition_sha256'] == d['condition_sha256'] == point['condition_sha256'] == condition['condition_sha256'], key)
        eligible = []
        for update in case['verified_updates']:
            same = (update['case_id'] == record['case_id']
                and update['input_sha256'] == case['input_sha256']
                and update['call_directory'] == str((REPO / case['result_path']).parent.relative_to(REPO)).replace('\\', '/'))
            ticks = [F(str(update[k])) for k in ('formed_at_s', 'committed_at_s', 'transferred_at_s', 'observer_completed_at_s')]
            valid = (same and update['state'] == 'SAFE' and update['complete_global'] is True
                and update['evidence_verified'] is True and min(ticks) >= 0 and ticks == sorted(ticks)
                and max(ticks) < 300 and max(ticks) < F(str(point['build_started_at_s'])))
            if valid:
                eligible.append(update)
        best = min(eligible, key=lambda u: (F(u['upper_J']), max(F(str(u[k])) for k in ('formed_at_s', 'committed_at_s', 'transferred_at_s', 'observer_completed_at_s'))))
        upper = record['timely_upper']
        check('chosen_U_independently_timely_samecall_minimum',
            best['source_update_index'] == upper['source_update_index'] == point['chosen_update_index']
            and F(best['upper_J']) == F(upper['upper_J']) == F(point['available_safe_upper_bound_J']), key)
        receipt = original['aggregation_attempts'][upper['source_aggregation_index']]
        check('timely_receipt_full_identity', receipt['receipt_sha256'] == upper['receipt_sha256']
            and canonical(receipt['safe_candidate']) == upper['candidate_sha256']
            and F(receipt['safe_upper_bound_J']) == F(upper['upper_J']), key)
        witnesses = [(condition['seed_candidate'], condition['seed_receipt']['safe_upper_bound_J']),
            (condition.get('warm_candidate', condition['seed_candidate']), condition.get('warm_receipt', condition['seed_receipt'])['safe_upper_bound_J']),
            (receipt['safe_candidate'], receipt['safe_upper_bound_J'])]
        base = record['base_bound']
        check('base_bound_identity_and_not_production_or_U', base['input_sha256'] == case['input_sha256']
            and base['condition_sha256'] == canonical(partial) and base['production_search_enabled'] is False
            and base['solver_reported'] is False and base['new_safe_upper_bound'] is False, key)
        base_witness = [F(u) for candidate, u in witnesses if compatible(candidate, partial)]
        check('base_preserves_compatible_original_SAFE_witness', bool(base_witness) and all(F(base['lower_bound_J']) <= u for u in base_witness), key)
        expected_modes = {(row['stage_id'], mode['unit'], mode['opp']): mode
            for row in d['opened_rows'] for mode in row['modes'] if mode['options_nonzero'] > 0}
        observed_modes = {(p['label']['stage_id'], p['label']['unit'], p['label']['opp']): p for p in record['probes']}
        check('exact_actual_open_nonzero_mode_set', expected_modes.keys() == observed_modes.keys()
            and len(observed_modes) == len(record['probes']), key)
        exclusions = 0
        max_margin = None
        for mode_key, probe in observed_modes.items():
            mode = expected_modes[mode_key]
            label = probe['label']
            check('original_columns_and_starts_match_domain', label['remaining_option_count'] == mode['options_nonzero']
                and label['option_columns'] == mode['option_columns'] and label['remaining_starts_ms'] == mode['starts_ms']
                and len(label['option_columns']) == len(label['remaining_starts_ms']) == label['remaining_option_count'], [key, mode_key])
            child = copy.deepcopy(partial)
            child['by_scene'][record['scene_id']][mode_key[0]].update(unit=mode_key[1], opp=mode_key[2])
            b = probe['bound']
            lower = F(b['lower_bound_J'])
            reference = F(upper['upper_J'])
            margin = lower - reference
            max_margin = margin if max_margin is None else max(max_margin, margin)
            check('child_partial_and_bound_identity', probe['partial'] == child
                and b['condition_sha256'] == canonical(child) and b['input_sha256'] == case['input_sha256'], [key, mode_key])
            check('three_complete_bounds_max_not_sum', lower == max(F(b[k]) for k in
                ('legacy_conditioned_lower_bound_J', 'capacity_lower_bound_J', 'forced_residency_lower_bound_J')), [key, mode_key])
            check('exact_strict_result_no_production_token', probe['decision']['excludable'] == (margin > 0)
                and F(probe['decision']['difference_J']) == margin
                and probe['decision']['production_pruning_authorized'] is False
                and probe['comparison']['pruning_authorized'] is False, [key, mode_key])
            for candidate, u in witnesses:
                if compatible(candidate, child):
                    check('compatible_original_witness_never_undercut', lower <= F(u), [key, mode_key])
            x0_rows = d['actual_x0']['candidate']['scenes'][record['scene_id']]
            x0_match = any(r['stage_id'] == mode_key[0] and r['unit'] == mode_key[1] and r['opp'] == mode_key[2] for r in x0_rows)
            check('actual_x0_kept_and_provenance_flags_correct', probe['in_actual_x0'] == x0_match
                and not (x0_match and probe['decision']['excludable']), [key, mode_key])
            exclusions += margin > 0
            total_options += label['remaining_option_count']
        total_probe_modes += len(observed_modes)
        total_exclusions += exclusions
        per_build.append({'build_key': key, 'timely_U_J': upper['upper_J'], 'mode_count': len(observed_modes),
            'excludable_modes': exclusions, 'maximum_LB_minus_U_J': str(max_margin),
            'minimum_U_minus_LB_J': str(-max_margin)})
    check('180_open_modes_zero_exclusions_independent', total_probe_modes == 180 and total_exclusions == 0)
    check('root_summary_matches_independent_counts', run['summary']['builds'] == 20
        and run['summary']['open_mode_instances'] == total_probe_modes
        and run['summary']['excludable_modes'] == total_exclusions
        and run['summary']['excludable_nonzero_option_columns'] == 0)
    after = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p) for p in paths}
    check('replay_facts_and_code_unchanged_during_independent_check', source_before == after)
    payload = {'protocol': 'K171-independent-final-stored-record-arithmetic-v1',
        'checks': CHECKS, 'checks_run': len(CHECKS), 'passed': all(c['passed'] for c in CHECKS),
        'record_sha256_before': source_before, 'record_sha256_after': after,
        'summary': {'builds': len(run['records']), 'open_mode_instances': total_probe_modes,
            'nonzero_open_option_instances': total_options, 'excludable_modes': total_exclusions},
        'per_build': per_build, 'bound_API_calls': 0, 'model_builds': 0,
        'solver_calls': 0, 'thermal_or_candidate_evaluation_calls': 0, 'new_research_calls': 0,
        'wall_s': time.perf_counter() - started}
    with (HERE / 'record_checks_run01.json').open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'passed': payload['passed'], 'checks': len(CHECKS),
        'failures': [c for c in CHECKS if not c['passed']][:5], 'summary': payload['summary']}, ensure_ascii=False))
    assert payload['passed']

if __name__ == '__main__':
    main()
