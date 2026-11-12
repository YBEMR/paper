"""Read-only audit of the consumed ON slot. No imports from scientific execution code."""
from pathlib import Path
import hashlib
import json
import sys


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def main(workspace,out):
    workspace=Path(workspace).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    package=workspace/'work/on_diagnostic';run=workspace/'work/on_diagnostic_execution_20261112'
    plan=read(package/'plan.json');receipt=read(run/'receipt.json');controller=read(run/'controller.json')
    timing=read(run/'timing_after_cleanup.json');initial=read(run/'initial_complete_evaluation.json')
    closed=read(run/'matlab/closed.json');ready=read(run/'matlab/ready.json')
    expected='fcbf4dfcfbbd0a4033bd8676b5e8c57b836a15bd8729eb5121b0ebf8b32d208b'
    checks={}
    checks['approved_frozen_plan']=sha(package/'plan.json')==expected==read(run/'claim.json')['plan_sha256']
    approval=read(run/'approval_consumed.json')
    checks['approval_exact_scope']=bool(approval['approved'] is True and approval['plan_sha256']==expected
        and approval['approved_subject_commit']=='7b723b13bae842eed95b33a6f5f2e1aea0775096'
        and approval['maximum_native_calls']==1 and approval['total_window_s']==300 and approval['native_MaxTime_s']==240
        and approval['retries']==0 and approval['arm']=='ON')
    checks['approval_bytes_match']=sha(run/'approval_consumed.json')==sha(workspace/'work/on_diagnostic_approval_20261112.json')==read(run/'claim.json')['approval_sha256']
    checks['frozen_sources_unchanged']=all(sha(workspace/name)==h for name,h in plan['workspace_files'].items())
    checks['frozen_executor_unchanged']=all(sha(package/name)==h for name,h in plan['package_files'].items())
    checks['once_only_claim_present']=(run/'claim.json').is_file() and (run/'worker_claim.json').is_file()
    checks['native_not_requested']=receipt['native_request_attempts']==0 and receipt['native_calls_observed']==0 and receipt['actual_native_entry_events']==0
    request_files=[p.name for p in (run/'matlab').glob('request_*')]
    checks['no_native_publications']=not request_files and receipt['native'] is None and not (run/'progress.jsonl').exists()
    checks['expected_stop']=receipt['terminal_state']=='INSUFFICIENT_FIXED_CAP_RESERVE_NO_CALL' and receipt['error'] is None
    remaining=plan['total_window_s']-receipt['method_elapsed_s']
    checks['fixed_cap_does_not_fit']=remaining<plan['native_MaxTime_s'] and remaining<plan['native_MaxTime_s']+10
    checks['initial_complete_SAFE']=bool(initial['state']=='SAFE' and initial['rankable_energy']
        and len(initial['scenes'])==2 and all(s['complete'] and s['state']=='SAFE' for s in initial['scenes'].values()))
    baseline=read(workspace/'work/stable_expression/entry_runs/off1/initial_evaluation.json')
    checks['initial_energy_matches_prior_OFF']=initial['weighted_energy_J']==baseline['weighted_energy_J']
    checks['single_complete_initial_evaluation']=receipt['physical_evaluations_observed']==receipt['physical_evaluation_attempts']==1
    checks['no_returned_evaluation']=receipt['returned_evaluation'] is None and receipt['candidate'] is None
    checks['original_MATLAB_ready']=ready['status']=='READY' and ready['release']=='2023b' and ready['license_checkout'] is True
    checks['graceful_cleanup']=closed['observed_tree_verified_terminated'] is True and closed['cleanup_status']=='graceful_closed'
    checks['controller_complete']=controller['state']=='COMPLETED' and controller['returncode']==0 and controller['process_monitor']['complete'] is True
    checks['no_forced_process_cleanup']=not controller['process_monitor']['forced_pids'] and not controller['process_monitor']['watchdog_expired']
    checks['cost_arithmetic']=abs(sum(timing['phases_exclusive_s'].values())+timing['unattributed_s']-receipt['method_elapsed_s'])<1e-9
    checks['no_extra_work']=receipt['retries']==receipt['formal_ABC_runs']==receipt['model_builds']==0
    checks['no_progress_claim']=receipt['progress_usable'] is False and controller['progress_usable'] is False
    result=dict(passed=all(checks.values()),checks=checks,approved_subject_commit='7b723b13bae842eed95b33a6f5f2e1aea0775096',
        plan_sha256=expected,approval_sha256=sha(run/'approval_consumed.json'),
        native_optimization_calls=0,native_request_attempts=0,complete_physical_evaluations=1,
        new_model_builds=0,new_algebraic_transforms=0,retries=0,formal_ABC_runs=0,
        execution_slot_consumed=True,unused_native_call_not_reusable_under_this_plan=True,
        classification='AUTHORIZED_EXECUTION_STOPPED_BEFORE_NATIVE_REQUEST',
        stop_reason=receipt['terminal_state'],
        costs=dict(method_elapsed_s=receipt['method_elapsed_s'],worker_total_s=receipt['total_elapsed_s'],controller_total_s=controller['wall_s'],
                   phases_exclusive_s=timing['phases_exclusive_s'],unattributed_s=timing['unattributed_s'],
                   remaining_at_stop_s=remaining,required_before_native_request_s=250,
                   cleanup_s=closed['cleanup_wall_seconds'],
                   other_post_method_worker_overhead_s=receipt['total_elapsed_s']-receipt['method_elapsed_s']-closed['cleanup_wall_seconds'],
                   solver_time_s=None),
        initial=dict(state=initial['state'],completed_at_elapsed_s=initial['completed_at_elapsed_s'],weighted_energy_J=initial['weighted_energy_J'],
                     candidate_identity=plan['initial_candidate_identity'],is_solver_candidate=False),
        progress=dict(root_LP='NOT_RUN',integer_candidate='NOT_RUN',finite_lower_bound='NOT_RUN',solver_exitflag=None,
                      new_SAFE_schedule='NO_SOLVER_RESULT',energy_improvement='NOT_MEASURED'),
        uncertainty=dict(startup_65_844s_cause='UNKNOWN_NO_PHASE_BREAKDOWN',
                         native_ON_numerical_behavior='UNKNOWN_NOT_TESTED',
                         complement_gate_solver_benefit='UNVERIFIED',
                         reason_for_receipt_integrity_NOT_ESTABLISHED='Native model transport/options identity is absent because no request was sent; no observed source mismatch.',
                         meaning_of_controller_COMPLETED='Controller and cleanup finished normally; this is not solver success.'),
        interpretation='This slot measures preparation/startup failure to fit the fixed cap, not ON numerical failure or lack of solver progress. No OFF/ON performance comparison is valid.',
        audit_scientific_calls=dict(native=0,physical_evaluation=0,model_build=0),
        source_files_verified=len(plan['workspace_files']))
    evidence=[run/name for name in ['approval_consumed.json','claim.json','command.json','controller.json',
        'initial_complete_evaluation.json','process_monitor.json','receipt.json','saved_input_admission.json',
        'stderr.log','stdout.log','timing_after_cleanup.json','worker_claim.json','matlab/closed.json',
        'matlab/matlab.log','matlab/ready.json','matlab/session.json','matlab/stop']]
    bindings={p.relative_to(workspace).as_posix():sha(p) for p in evidence}
    bindings[(package/'plan.json').relative_to(workspace).as_posix()]=sha(package/'plan.json')
    save(out/'source_bindings.json',bindings)
    result['evidence_bindings_sha256']=sha(out/'source_bindings.json')
    save(out/'audit.json',result)
    if not result['passed']:raise RuntimeError('Saved run audit failed')
    print(json.dumps({'passed':True,'checks':len(checks),'native_calls':0,'complete_initial_evaluations':1,'remaining_at_stop_s':remaining,'audit_source_files':len(bindings)},ensure_ascii=False))


if __name__=='__main__':main(sys.argv[1],sys.argv[2])
