"""K126 saved-record verification only: no new solve, decode or trajectory."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO/'research/chapter3_experiments'))
from summarize_cut_pair import _hash, _read, _saved_safe


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    assert not (HERE/'verification.json').exists(), 'Do not overwrite an earlier verification'
    raw_paths = [p for p in RUN.rglob('*') if p.is_file() and not p.is_relative_to(HERE)]
    before = {p.relative_to(RUN).as_posix(): sha(p) for p in raw_paths}
    declared = _read(RUN/'declaration.json')
    call = RUN/'call_n1/invocation'
    method, report = _read(call/'result.json'), _read(RUN/'run_record.json')
    instance, config = _read(call/'input_instance.json'), _read(call/'input_config.json')
    facts = _read(HERE/'facts.json')
    checks = {}
    assert declared['research_calls'] == report['research_calls_consumed'] == 1
    assert declared['total_budget_s'] == method['timing']['limit_s'] == 300
    assert method['scene_slice_s'] == 60 and not declared['retry_allowed']
    assert report['state'] == 'CALL_COMPLETED' and report['source_unchanged']
    checks['one_claim_one_completed_call_no_retry'] = True
    for path, digest in declared['source_sha256'].items():
        assert sha(REPO/path) == sha(RUN/'source_snapshot'/path) == digest
    assert report['source_sha256_before'] == report['source_sha256_after'] == declared['source_sha256']
    assert len(declared['source_sha256']) == 54
    checks['all_54_source_and_snapshot_identities_match'] = True
    assert _hash(instance) == declared['original_instance_sha256']
    assert _hash(config) == declared['original_config_sha256']
    assert F(instance['window_ms']) == 400 and F(instance['start_grid_ms']) == 5
    assert all(len(s['stage_instances']) == 6 for s in instance['scenarios'])
    checks['original_full_chain_input_matches_declaration'] = True
    aggregates = method['aggregation_attempts']
    assert len(aggregates) == 3 and all(_saved_safe(a, instance, method['shared_deployment'], 300) for a in aggregates)
    assert method['aggregation'] == aggregates[-1]
    assert F(method['weighted_energy_J'][1]) < F(method['initial_global_weighted_energy_J'][0])
    assert method['strict_improvement_over_initial_certified'] is True
    checks['three_complete_timely_SAFE_aggregates_and_strict_improvement'] = True
    condition = method['condition']
    assert condition['condition_sha256'] == _hash({k:v for k,v in condition.items() if k != 'condition_sha256'})
    assert condition['source_input_sha256'] == _hash(instance)
    for sid, rows in method['safe_candidate']['scenes'].items():
        seed = {r['stage_id']: r for r in condition['seed_candidate']['scenes'][sid]}
        for row in rows:
            original = seed[row['stage_id']]
            assert row['unit'] == original['unit']
            if row['stage_id'] not in declared['opened_by_scene'][sid]:
                assert row['opp'] == original['opp'] and F(row['start_ms']) == F(original['start_ms'])
    checks['fixed_devices_and_closed_exact_choices_preserved'] = True
    assert method['timing']['method_elapsed_s'] < 300
    assert all(x['committed_at_s'] < 300 for x in method['global_updates'])
    assert report['cleanup_status']['returncode'] == 0 and not report['technical_issues']
    checks['method_cutoff_and_cleanup_valid'] = True
    assert method['integer_solver_entered'] is True
    assert len(facts['call']['requests']) == 2
    assert all(r['budget_valid'] and r['native_options']['CutMaxIterations'] == 10 for r in facts['call']['requests'])
    assert facts['call']['feedback_records'] == 0 and not method['violations']
    assert sum(s['distinct_new_decoded_arrangements'] for s in facts['scenes']) == 2
    assert all(r['solver_reported_only'] and not r['independently_certified']
        and r['scope'] == 'seed_defined_N1_fixed_shared_deployment_unweighted_scene'
        for s in facts['scenes'] for r in s['solver_reported_bounds'])
    assert not method['independently_proven_optimal'] and not method['independently_proven_infeasible']
    checks['native_progress_thermal_and_bound_scopes_separate'] = True
    after = {p.relative_to(RUN).as_posix(): sha(p) for p in raw_paths}
    assert before == after
    checks['read_only_archive_unchanged'] = True
    out = {'passed': True, 'count': len(checks), 'checks': checks,
        'source_sha256': sha(__file__), 'scope': 'saved records only; no new solve/trajectory/decode',
        'raw_archive_sha256': after}
    (HERE/'verification.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'checks': len(checks), 'raw_files_unchanged': len(after)}))


if __name__ == '__main__':
    run()
