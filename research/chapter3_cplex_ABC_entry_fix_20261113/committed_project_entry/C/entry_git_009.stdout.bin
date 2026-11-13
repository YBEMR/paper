"""Freeze source identities after pure controls; no model or solver entry."""
import argparse,copy,sys
from pathlib import Path
from core import read,save,sha,verify
from environment import snapshot

def main():
    a=argparse.ArgumentParser();a.add_argument('--workspace',type=Path,required=True);a.add_argument('--controls',type=Path,required=True);args=a.parse_args()
    root=args.workspace.resolve();here=Path(__file__).resolve().parent;controls=args.controls.resolve()
    prior_path=root/'work/cplex_C_solve_v2/plan.json';prior=read(prior_path)
    formal=read(root/'work/formal_abc_v1/plan.json');tests=read(controls/'results.json')
    code={p.name:sha(p) for p in sorted(here.glob('*.py'))}
    assert tests['passed'] and not tests['CPLEX_imported'] and not tests['original_science_imported']
    assert tests['optimization_calls']==tests['full_R1_builds']==tests['thermal_evaluations']==0
    assert tests['code_hashes']==code,'Final source must pass controls'
    plan={k:copy.deepcopy(prior[k]) for k in ('runtime_hashes','evaluation_source_hashes','native_runtime','parameter_baseline',
        'parameter_overrides','parameter_rule','matrix_admission','observation','candidate_policy','layered_acceptance',
        'strict_success','historical_common_energy_J','environment','bound_objective_consistency_tolerance','scene_ids','limits')}
    plan.update(protocol='D285-CPLEX-fresh-ABC-entry-fixed-v1',status='FROZEN_AWAITING_INDEPENDENT_APPROVAL',
        base_commit='5bc1adeab10de8b8a19dea18aa088ebcbef7276f',D283_plan_sha256=sha(prior_path),supersedes_consumed_D284_plan_sha256='bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6',
        execution_authorized=False,ready_to_execute=False,ready_to_request_independent_scientific_authorization=True,
        repository_package='research/chapter3_cplex_ABC_entry_fix_20261113/executor',execution_directory='work/cplex_ABC_execution_v2',
        code_hashes=code,environment=snapshot(),arms=['A','B','C'],order='A then B then C; no automatic retry',
        baseline_flags=formal['baseline_flags'],arm_switches=formal['arm_switches'],input_identity=formal['input_identity'],
        initial_candidate_identity=formal['initial_candidate_identity'],
        input_hashes={p:sha(root/p) for p in ('work/stable_expression/full/input_instance.json','work/stable_expression/full/input_config.json')},
        scope=dict(instance='complete auto-L R1',stages=12,original_modes=66,grid_ms=5,window_ms=400,
            expression='split_constant_v1 complementary gate; exact projected binary64 coefficients certified anew per arm',
            physical_equations_precision_objective='unchanged',integer_domain='only proven lossless reductions',
            matrix_source='fresh construction only; no saved matrix import'),
        initialization=dict(rule='iter_initial_candidates(instance,budget,max_attempts=3); first complete SAFE; complete_initial_point',
            cross_arm_shared_cache_or_result=False,initial_schedule_hash_is_check_only=True,
            D283_improved_schedule_is_not_warm_start=True,native_start='all continuous and integer values; check_feasibility effort=1; no fallback or repair'),
        calls=dict(maximum_solve_per_arm=1,maximum_solve_total=3,maximum_build_per_arm=1,
            maximum_initial_candidates_per_arm=3,maximum_complete_evaluations_per_arm=4,maximum_final_evaluations_per_arm=1,retries=0),
        budget=dict(per_arm_total_s=600,native_response_cutoff_s=550,scientific_seal_s=590,
            allocation='floor(min(540,max(0,600-t-10-50))); call only if >=30',
            clock_origin='parent monotonic before per-arm claim/startup minus identical measured shared launcher setup debit',
            all_scientific_preparation_charged=True,group_budget_pooling=False,three_method_windows_max_s=1800,
            emergency_cleanup_s=620,outer_cleanup_wait_s=2,administrative_batch_overhead='launcher setup fully debited identically to all three groups (conservative triple charging); outer arm cleanup/receipt/archive charged; final comparative report is administrative only, separately timed and cannot upgrade science',
            phase_accounting='outer phase intervals partition work; nested science phases explain preparation, never add twice'),
        stop_rules=dict(ordinary='timeout, no vector, preparation budget/initial point rejection, resource limit and final candidate rejection: end arm, continue independent groups after cleanup',
            feature='independently diagnosed support certificate failure blocks B/C; joint replay failure blocks C; cumulative set union',
            global_stop='source/input/initial identity drift, unknown correctness/controller error, license failure, bound conflict, evidence integrity or cleanup failure: stop remaining groups',
            retries=0,late_evidence='can revoke only; never new scientific credit',missing_root='UNKNOWN, not failure inferred from silence'),
        fairness=dict(same_solver_version=True,same_complete_parameter_baseline=True,same_expression=True,same_initial_rule=True,
            independent_build_init_certification_native_readback_evaluation=True,
            compare='end-to-end feasible quality and valid bounds; record allocation/preparation/native time separately',
            prohibits_historical_intlinprog_or_D283_saved_C_as_speedup_control=True,
            single_batch_limit='descriptive R1 evidence, not statistical repeatability or universal scaling claim'),
        controls=dict(path=controls.relative_to(root).as_posix(),results_sha256=sha(controls/'results.json'),tests_run=tests['tests_run']),
        unknowns=['Fresh A/B/C CPLEX preparation and peak memory not measured this turn',
            '600 seconds does not guarantee all groups reach or complete root LP',
            'Native bounds/gap are solver reports, not independent exact optimality certificates',
            'OS scheduling/cleanup is bounded by watchdog policy, not a hard real-time guarantee'],
        approval_schema=dict(protocol='D285-CPLEX-fresh-ABC-approval-v1',decision='APPROVE',plan_sha256='this plan hash',
            maximum_solve_calls=3,maximum_solve_calls_per_arm=1,arms=['A','B','C'],total_window_s=600,response_cutoff_s=550,
            retries=0,scope='FRESH_FULL_R1_CPLEX_ABC_ONCE',approval_id='unique new user approval',user_message_reference='actual independent new authorization',
            frozen_commit='40 hex commit containing plan and executor'))
    git_path=Path('F:/Git/Git/mingw64/bin/git.exe')
    plan['control_git']=dict(path=git_path.as_posix(),sha256=sha(git_path),PATH_fallback=False,
        per_read_max_seconds=5,deadline='min(5,550-elapsed); same absolute method clock')
    plan['runtime_hashes'][git_path.as_posix()]=sha(git_path)
    plan['control_entry']=dict(mode='--entry-only requires CONTROL_ONLY approval with zero scientific workers and calls',
        separate_output_required=True,stops_before_worker_creation=True,actual_controller_and_Job_tested=True,
        raw_stdout_stderr_and_returncode_archived=True,entry_failure_global_stop=True,global_batch_failure_exit_code=1)
    plan['unchanged_scientific_source_hashes']={}
    for name in ('science.py','representation.py','reduction_replay.py','worker.py','native.py','native_adapter.py','transport_contract.py','windows_job.py'):
        assert (here/name).read_bytes()==(root/'work/cplex_ABC_v2'/name).read_bytes()
        plan['unchanged_scientific_source_hashes'][name]=sha(here/name)
    plan['native_runtime']['entitlement']='User-confirmed academic Studio; complete C optimization entry succeeded in D283; no license change; future entry errors stop batch'
    plan['evaluation_source_hashes']['work/stable_expression/complement_gate.py']=sha(root/'work/stable_expression/complement_gate.py')
    verify(root,plan['input_hashes']);verify(root,plan['evaluation_source_hashes']);verify(Path('/'),plan['runtime_hashes'])
    assert plan['parameter_baseline']==prior['parameter_baseline'] and plan['parameter_overrides']==prior['parameter_overrides']
    assert plan['limits']==prior['limits']
    save(here/'plan.json',plan);save(here/'plan.identity.json',dict(sha256=sha(here/'plan.json'),execution_authorized=False))
    print(sha(here/'plan.json'))
if __name__=='__main__':main()

