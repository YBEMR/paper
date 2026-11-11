"""Read saved evidence and seal this round; no scientific execution."""
import ast
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    plan = read(HERE/'master_plan.json')
    for name, expected in plan['history_sha256'].items():
        assert sha(REPO/name) == expected, name
    before = ast.parse((HERE/'milp_before.py.txt').read_text())
    after = ast.parse((REPO/'research/chapter3_experiments/milp.py').read_text())
    for name in ['Model', 'add_energy_lower_bound']:
        old = next(node for node in before.body if getattr(node, 'name', None) == name)
        new = next(node for node in after.body if getattr(node, 'name', None) == name)
        assert ast.dump(old) == ast.dump(new), name
    full = HERE/'full_static'
    frozen = read(full/'plan.json')
    for name, expected in frozen['frozen_sources_sha256'].items():
        assert sha(REPO/name) == expected == sha(full/'frozen'/name)
    acceptance = read(full/'acceptance.json')
    for name, expected in acceptance['evidence_sha256'].items():
        assert sha(REPO/name) == expected, name
    test = read(HERE/'validation/execution/results.json')
    legacy = read(HERE/'validation/old_structural_regression/results.json')
    assert test['passed'] and test['tests_run'] == 7 and test['thermal_calls'] == 24
    assert legacy['passed'] and legacy['tests_run'] == 8
    compare = read(full/'comparison.json')
    assert all(compare['off_archive_arrays_byte_equal'].values())
    assert compare['surviving_non_cut_row_multiset_exact']
    assert compare['options_equal'] and compare['events_equal']
    assert all(compare['shared_variable_vectors_byte_equal'].values())
    audit = read(full/'pruning_audit_summary.json')
    assert audit['gate_off_rows_checked'] == 29380 and F(audit['gate_off_minimum_slack_exact']) > 0
    assert audit['all_recorded_dependency_margins_exceed_1e_9_per_row']
    rows = []
    for variant in ['off', 'on']:
        result = read(full/'execution'/variant/'result.json')
        receipt = read(full/f'{variant}.command_receipt.json')
        assert result['success'] and not result['forbidden_attempts']
        assert result['solver_calls'] == result['candidate_thermal_calls'] == 0
        assert result['energy_certificates_checked'] == 424
        assert receipt['returncode'] == 0 and not receipt['watchdog_expired']
        rows.append(dict(variant=variant, options=result['model_summary']['options'],
            state_blocks=sum(result['joint_state_blocks'].values()), variables=result['variables'],
            rows=result['rows'], nonzeros=result['nonzeros'], build_s=result['build_s'],
            export_s=result['export_s'], energy_certificate_check_s=result['energy_certificate_check_s'],
            worker_elapsed_s=result['worker_elapsed_s'], command_wall_s=receipt['wall_s'],
            started_utc=result['started_utc'], ended_utc=result['ended_utc']))
    assert rows[0]['state_blocks']-rows[1]['state_blocks'] == 2938
    assert rows[0]['rows']-rows[1]['rows'] == 29380
    with (HERE/'static_pair_summary.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result = dict(completed_utc=datetime.now(timezone.utc).isoformat(),
        base_commits=[plan['prior_formal_commit'],plan['base_commit']],
        first_scientific_activity_recorded_utc=read(HERE/'numeric_gate/gate_zero_result.json')['started_utc'],
        initial_preparation_not_fully_timed=True, master_recorded_utc=plan['recorded_utc'],
        full_static_batch_start_utc=read(full/'batch_claim.json')['started_utc'],
        full_static_batch_end_utc=read(full/'batch_completed.json')['ended_utc'],
        protected_history_files_unchanged=len(plan['history_sha256']),
        old_Model_and_energy_cut_generator_AST_unchanged=True,
        frozen_runtime_sources=217, formal_source_sha256={name:sha(REPO/name) for name in [
            'research/chapter3_experiments/milp.py','research/chapter3_experiments/joint_state_support.py',
            'research/chapter3_experiments/test_joint_state_support.py']},
        new_tests=7, old_structural_regressions=8, test_fixture_model_attempts=5,
        fixture_expected_fail_closed_attempts=1, full_R1_static_builds=2,
        new_LP_or_MILP_solve_calls=0, full_R1_thermal_calls=0,
        small_domain_candidate_thermal_calls=24, all_small_domain_physical_scientific_fields_equal=True,
        full_original_R1_initializations=0, removed_states=2938, removed_electrothermal_rows=29380,
        removed_nonzeros=320242, exact_binary64_integer_y_projection_evidence_passed=True,
        unchanged_LP_projection_claim=False, solver_tolerance_tube_claim=False,
        construction_speedup_observed=False, solver_speedup_tested=False,
        full_pair_retries=0, pushed=False, uploaded=False, merged=False,
        postprocessing_note='One temporary read-only summary KeyError was corrected; no model/compare/solver retry')
    with (HERE/'completion_record.json').open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
