"""Join saved static results and check provenance; no model or solver imports."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
read = lambda p: json.loads(p.read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    started = datetime.now(timezone.utc).isoformat()
    plan = read(HERE/'plan.json')
    for group in ['frozen_sources_verified', 'historical_files_sha256']:
        for name, sha in plan[group].items():
            assert digest(REPO/name) == sha, name
    counts = read(HERE/'intervals/summary.json')
    reach = read(HERE/'reachability/result.json')
    small = read(HERE/'reachability/small_domain_results.json')
    numbers = read(HERE/'numerics/statistics.json')
    families = read(HERE/'numerics/row_family_statistics.json')
    build = read(HERE/'numerics/completion.json')
    estimate = read(HERE/'numerics/compact_expression_estimate.json')
    distribution = read(HERE/'reachability/proof_distribution.json')
    rows = list(csv.DictReader((HERE/'intervals/interval_counts.csv').open(encoding='utf-8-sig')))
    supports = list(csv.DictReader((HERE/'reachability/per_interval.csv').open()))
    assert len(rows) == len(supports) == 424
    # Compare by exact scene/interval identity, without recomputing either analysis.
    index = {(r['scenario_id'], int(r['interval_index'])):r for r in rows}
    assert set(index) == {(r['scene'], int(r['interval'])) for r in supports}
    for row in supports:
        old = index[row['scene'], int(row['interval'])]
        assert int(old['joint_state_blocks']) == int(row['blocks_before'])
        assert old['left_ms'] == row['left_ms'] and old['right_ms'] == row['right_ms']
    assert sum(int(r['blocks_before']) for r in supports) == 9798
    assert sum(int(r['proved_unreachable']) for r in supports) == 2938
    assert sum(families[k]['rows'] for k in ['thermal_propagation','complete_energy']) == 97980
    assert sum(families[k]['nnz'] for k in ['thermal_propagation','complete_energy']) == 979800
    assert numbers['conditional_pairs'] == 48990 and numbers['pair_non_gate_mismatch'] == 0
    assert build['static_build_calls'] == 1 and build['matrix_all_equal']
    assert build['new_LP_calls'] == build['new_MILP_calls'] == build['candidate_or_trajectory_evaluations'] == 0
    assert small['all_legal_sets_equal'] and small['legal_schedules_before'] == small['legal_schedules_after'] == 12
    assert distribution['proved_states_by_nonL_domain_count'] == {'3':2712, '2':226}
    totals = estimate['totals']
    assert totals['disaggregated_physical_rows'] == 166246 and totals['extra_copies'] == 77714
    comparison = [dict(candidate='remove_proved_unreachable_joint_states', recommended=True,
        original_electrothermal_rows=97980, potential_electrothermal_rows=68600,
        potential_removed_w=2938, source_copy_variables=0,
        status='Proposal only; no compressed model built; original integer schedule projection justified, binary64 matrix equivalence not yet proved'),
        dict(candidate='disaggregate_continuous_sources_by_state', recommended=False,
        original_electrothermal_rows=97980, potential_electrothermal_rows=166246,
        potential_removed_w=0, source_copy_variables=77714,
        status='Formula estimate using original source coordinates; ideal integer onehot affine equivalence, not an implementation or exported-row equivalence claim')]
    with (HERE/'candidate_comparison.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison[0])); writer.writeheader(); writer.writerows(comparison)
    actual_commands = read(HERE/'numerics/commands.json')
    actual_commands['additional_commands'] = [
        'python3 -B research/chapter3_joint_state_static_20261111/intervals/analyze_intervals.py > research/chapter3_joint_state_static_20261111/intervals/stdout.log 2> research/chapter3_joint_state_static_20261111/intervals/stderr.log',
        'python3 research/chapter3_joint_state_static_20261111/reachability/run_reachability.py freeze > research/chapter3_joint_state_static_20261111/reachability/freeze.stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/freeze.stderr.log',
        'python3 research/chapter3_joint_state_static_20261111/reachability/run_reachability.py > research/chapter3_joint_state_static_20261111/reachability/stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/stderr.log',
        'python3 research/chapter3_joint_state_static_20261111/reachability/validate_small_domain.py > research/chapter3_joint_state_static_20261111/reachability/small_domain.stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/small_domain.stderr.log',
        'python3 research/chapter3_joint_state_static_20261111/seal_results.py > research/chapter3_joint_state_static_20261111/seal.stdout.log 2> research/chapter3_joint_state_static_20261111/seal.stderr.log']
    with (HERE/'executed_commands.json').open('x') as stream: json.dump(actual_commands,stream,indent=2)
    end = datetime.now(timezone.utc).isoformat()
    result = dict(base_commit=plan['base_commit'], master_plan_recorded_start_utc=plan['recorded_start_utc'],
        completed_utc=end, recorded_master_window_s=(datetime.fromisoformat(end)-datetime.fromisoformat(plan['recorded_start_utc'])).total_seconds(),
        initial_preparation_not_fully_timed=True, independent_activities_run_in_parallel=True,
        original_sources_unchanged=len(plan['frozen_sources_verified']), historical_files_unchanged=len(plan['historical_files_sha256']),
        static_model_builds=1, new_LP_calls=0, new_MILP_calls=0, new_thermal_evaluations=0,
        production_source_changes=0, compressed_models_built=0, state_blocks=9798,
        original_electrothermal_rows=97980, proved_unreachable_original_integer_schedule_states=2938,
        remaining_reachability_unknown=6860, potential_physical_row_savings=29380,
        physical_integer_schedule_projection_proof=True, binary64_outer_matrix_equivalence_proof=False,
        independent_small_domain_cases=9, complete_assignments=24, legal_identity_sets_before_after=[12,12],
        sole_recommendation='Remove joint states with exhaustive incompatible active-option support certificates before creating electrothermal rows',
        solver_speedup_tested=False, pushed=False, uploaded=False, merged=False,
        postprocessor_interrupted_then_fixed=True,
        task_time_note='Recorded master window excludes initial untimed source inspections/preparation; scientific activity exact clocks retained in subdirectory receipts')
    with (HERE/'completion_record.json').open('x') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
