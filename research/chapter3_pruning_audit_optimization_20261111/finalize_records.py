"""Seal already completed evidence. No model, thermal, or solver calls."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    master = read(HERE/'master_plan.json')
    for name, expected in master['history_sha256'].items():
        assert sha(REPO/name) == expected, name
    old = ast.parse((HERE/'milp.py.before.txt').read_text())
    new = ast.parse((REPO/'research/chapter3_experiments/milp.py').read_text())
    for name in ['Model','build_model','add_energy_lower_bound']:
        before = next(n for n in old.body if getattr(n,'name',None)==name)
        after = next(n for n in new.body if getattr(n,'name',None)==name)
        assert ast.dump(before) == ast.dump(after), name
    pair = HERE/'static_pair'
    plan = read(pair/'plan.json')
    for label, sources in plan['source_sha256'].items():
        for name, expected in sources.items():
            assert sha(pair/'frozen'/label/name) == expected
            if label=='optimized': assert sha(REPO/name) == expected
    accepted = read(pair/'acceptance.json')
    for name, expected in {**accepted['source_sha256'],**accepted['evidence_sha256']}.items():
        assert sha(REPO/name) == expected, name
    compare = read(pair/'comparison.json')
    assert all(compare['on_arrays_byte_identical'].values())
    assert all(compare['old_on_matches_historical_archive'].values())
    assert all(compare['off_matches_historical_archive'].values())
    assert compare['on_names_equal'] and compare['same_options_events_objective_bounds_integer_indices']
    assert compare['deleted_state_name_set_equals_frozen_prediction'] and compare['deleted_states']==2938
    assert compare['gate_proof_results_exactly_equal'] and compare['represented_gate_rows']==29380
    assert compare['energy_cuts_exact_and_unchanged']
    test = read(HERE/'validation/acceptance_summary.json')
    assert test['passed']
    completed = read(HERE/'validation/completion.json')
    assert completed['final_tests']==21 and completed['cumulative_thermal_calls']==60
    assert completed['cumulative_test_wall_s'] <= 240
    replay = read(HERE/'safety_review/replay_result.json')
    assert replay['all_old_new_per_state_exact_scalar_certificates_equal'] and replay['cold_start']
    assert replay['deleted_states']==2938 and replay['full_model_builds']==0
    records = {}
    for arm in ['old_on','optimized_on','off']:
        result=read(pair/'execution'/arm/'result.json')
        receipt=read(pair/f'{arm}.command_receipt.json')
        assert result['success'] and not result['forbidden_attempts']
        assert result['solver_calls']==result['candidate_thermal_calls']==0
        assert receipt['returncode']==0 and not receipt['watchdog_expired']
        records[arm]=dict(build_s=result['build_s'],export_s=result['export_s'],
            build_plus_export_s=result['build_plus_export_s'],worker_s=result['worker_elapsed_s'],
            command_wall_s=receipt['wall_s'],peak_RSS_after_export_bytes=result['peak_memory']['after_export']['bytes'])
    stats=compare['optimized_cache_statistics']
    assert stats['misses']==284 and stats['hits']==2654 and stats['strict_rows_evaluated']==2840
    old_gate=next(r['gate_off_audit_s'] for r in compare['rows'] if r['arm']=='old_on')
    new_gate=next(r['gate_off_audit_s'] for r in compare['rows'] if r['arm']=='optimized_on')
    record=dict(completed_utc=datetime.now(timezone.utc).isoformat(),base_commit=master['base_commit'],
        master_recorded_utc=master['record_created_utc'],initial_preparation_not_fully_timed=True,
        history_files_unchanged=len(master['history_sha256']),
        source_sha256={name:sha(REPO/name) for name in [
            'research/chapter3_experiments/milp.py','research/chapter3_experiments/joint_state_support.py',
            'research/chapter3_experiments/test_joint_audit_cache.py']},
        Model_build_model_energy_generator_AST_unchanged=True,
        revisions=dict(rev1_accepted=False,rev1_reason='Actual kernel context rebinding identity omission; corrected before performance',rev2_accepted=True),
        final_tests=21,cumulative_real_candidate_thermal_calls=60,cumulative_test_wall_s=completed['cumulative_test_wall_s'],
        baseline_receipts_reused_in_rev2=12,helper_replay_contexts=1,helper_replay_full_model_builds=0,
        full_R1_static_builds=3,LP_MILP_solve_calls=0,full_R1_candidate_thermal_calls=0,
        static_batch_start_utc=read(pair/'batch_claim.json')['started_utc'],
        static_batch_end_utc=read(pair/'batch_completed.json')['ended_utc'],
        full_matrices_and_BigM_outer_metadata_unchanged_between_ON=True,
        removed_state_identities_unchanged=2938,states=6860,variables=16919,rows=94958,nonzeros=990904,
        represented_gate_rows=29380,freshly_certified_unique_template_rows=2840,
        audit_reduction_percent=100*(1-new_gate/old_gate),
        build_export_reduction_percent=100*(1-records['optimized_on']['build_plus_export_s']/records['old_on']['build_plus_export_s']),
        optimized_ON_over_OFF_percent=100*(records['optimized_on']['build_plus_export_s']/records['off']['build_plus_export_s']-1),
        costs=records,freeze_preparation_wall_s=None,freeze_preparation_note='No independent wall-clock instrument; not included in algorithm build+export',
        statistical_significance_tested=False,MILP_performance_tested=False,
        formal_MILP_proposal_only=True,matlab_available_on_PATH=False,
        pushed=False,uploaded=False,merged=False,performance_retries=0)
    with (HERE/'completion_record.json').open('x') as stream:json.dump(record,stream,ensure_ascii=False,indent=2)
    print(json.dumps(record,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
