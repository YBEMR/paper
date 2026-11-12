"""Post-run read-only audit. Reads persisted receipts and file bytes; no science imports."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import math
import os

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUN=ROOT/'work/on_budget_candidate_A420_execution_v1'
PACKAGE=ROOT/'work/budget_protocol_v2/candidate_on'
SUBJECT='aa1dde93be928d82de17ccf775f789e80d60cc75'
PLAN_HASH='b141fef4ce1cd2a7daf22ae5b1188d6d3b30cc31c5229c83c8b140628aed3bac'


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def optional(p):return read(p) if p.exists() else None
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(p,v):
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def safe(v):return bool(v and v['state']=='SAFE' and v['rankable_energy'] and v['completed_at_elapsed_s']<420
    and len(v['scenes'])==2 and all(s['complete'] and s['state']=='SAFE' for s in v['scenes'].values()))


def main():
    out=HERE/'audit';out.mkdir(exist_ok=False)
    plan=read(PACKAGE/'plan.json');receipt=read(RUN/'receipt.json');controller=read(RUN/'controller.json')
    claim=read(RUN/'claim.json');approval=read(RUN/'approval_consumed.json')
    native=optional(RUN/'native_receipt.json');raw=optional(RUN/'matlab/request_000001.response.json')
    timing=read(RUN/'timing_after_cleanup.json');closed=read(RUN/'matlab/closed.json')
    session=read(RUN/'matlab/session.json');ready=read(RUN/'matlab/ready.json')
    initial=read(RUN/'initial_complete_evaluation.json');returned=optional(RUN/'returned_complete_evaluation.json')
    admission=read(RUN/'saved_input_admission.json');allocation=optional(RUN/'publication_allocation.json')
    events=[json.loads(line) for line in (RUN/'progress.jsonl').read_text(encoding='utf-8').splitlines()] if (RUN/'progress.jsonl').exists() else []
    timely=[e for e in events if 0<=e['received_elapsed_s']<370]
    entered=[e for e in timely if e.get('kind')=='solver_entered']
    roots=[e for e in timely if e.get('values',{}).get('phase')=='rootlp']
    later=[e for e in timely if e.get('values',{}).get('phase') in ('heuristics','cutgen','branching')]
    bounds=[e for e in timely if finite(e.get('values',{}).get('lowerbound'))]
    vectors=[e for e in timely if isinstance(e.get('x'),list) and e['x']]
    requests=sorted((RUN/'matlab').glob('request_*.request.json'))
    checks=dict(plan_and_claim_identity=sha(PACKAGE/'plan.json')==PLAN_HASH==claim['plan_sha256'],
        approval_scope=approval['approved'] is True and approval['approved_subject_commit']==SUBJECT
            and approval['plan_sha256']==PLAN_HASH and approval['total_window_s']==420
            and approval['native_MaxTime_s']==240 and approval['solver_response_cutoff_s']==370
            and approval['maximum_native_calls']==1 and approval['retries']==0,
        approval_bytes=sha(RUN/'approval_consumed.json')==claim['approval_sha256']==sha(ROOT/'work/on_budget_A420_approval_20261112.json'),
        frozen_sources_unchanged=all(sha(ROOT/n)==h for n,h in plan['workspace_files'].items()),
        frozen_executor_unchanged=all(sha(PACKAGE/n)==h for n,h in plan['package_files'].items()),
        single_consumed_slot=(RUN/'worker_claim.json').exists() and (ROOT/'work/on_diagnostic_execution_20261112/claim.json').exists(),
        exactly_one_request=len(requests)==1 and receipt['native_request_attempts']==1,
        exactly_one_observed_native_entry=len(entered)==1 and receipt['native_calls_observed']==1,
        unchanged_native_options=bool(raw and raw.get('options')==plan['native_options']),
        published_with_full_reserve=bool(allocation and allocation['can_submit'] and allocation['native_seconds']==240
            and allocation['measured_elapsed_s']<=120),
        exact_native_240_from_entry=bool(entered and entered[0]['solver_time_allocation']['native_MaxTime_used']==240),
        original_R2023b_ready=ready['status']=='READY' and ready['release']=='2023b' and ready['license_checkout'] is True,
        identity_checked=receipt['identity']['state']=='VERIFIED' and receipt['identity_after']['state']=='VERIFIED',
        no_late_progress_credit=len(events)==len(timely),
        initial_complete_SAFE_in_window=safe(initial),
        evaluator_count_within_scope=receipt['physical_evaluations_observed']==receipt['physical_evaluation_attempts']<=2,
        returned_SAFE_claim_supported=receipt['returned_complete_SAFE']==safe(returned),
        no_extra_work=receipt['retries']==receipt['formal_ABC_runs']==receipt['model_builds']==0,
        native_response_budget_observed=bool(native and native['budget_valid'] and native['solver_response_complete_at_monotonic']<claim['parent_start_monotonic']+370),
        method_stopped_within_window=receipt['method_elapsed_s']<420,
        lifecycle_and_evidence_verified=receipt['lifecycle_integrity']==receipt['evidence_integrity']=='VERIFIED',
        graceful_cleanup=closed['cleanup_status']=='graceful_closed' and closed['observed_tree_verified_terminated'] is True,
        controller_completed=controller['state']=='COMPLETED' and controller['returncode']==0 and controller['process_monitor']['complete'],
        no_forced_cleanup=not controller['process_monitor']['forced_pids'] and not controller['process_monitor']['watchdog_expired'],
        timing_conservation=abs(sum(timing['phases_exclusive_s'].values())+timing['unattributed_s']-receipt['method_elapsed_s'])<1e-8,
        progress_flags_agree=controller['progress_usable']==receipt['progress_usable'])
    output=(raw or {}).get('output',{})
    result=dict(approved_subject_commit=SUBJECT,plan_sha256=PLAN_HASH,approval_sha256=sha(RUN/'approval_consumed.json'),
        passed=all(checks.values()),checks=checks,source_files_verified=len(plan['workspace_files']),
        execution_slot_consumed=True,authorization_reusable=False,stop_state=receipt['terminal_state'],
        matlab_sessions=1,native_request_attempts=receipt['native_request_attempts'],native_calls_observed=receipt['native_calls_observed'],
        physical_evaluation_attempts=receipt['physical_evaluations_observed'],complete_initial_SAFE=safe(initial),
        returned_complete_SAFE=safe(returned),new_complete_SAFE=receipt['new_complete_SAFE'],strict_energy_improvement=receipt['strict_energy_improvement'],
        model_builds=0,new_transforms=0,additional_LP_calls=0,formal_ABC_runs=0,retries=0,
        native=dict(status=(raw or {}).get('status'),exitflag=(raw or {}).get('exitflag'),
            output=output,final_vector_length=len((raw or {}).get('x',[])),fval=(raw or {}).get('fval'),
            warning_identifier=(raw or {}).get('solver_warning_identifier'),warning_message=(raw or {}).get('solver_warning_message'),
            error_identifier=(raw or {}).get('error_identifier'),error_message=(raw or {}).get('error_message'),
            actual_MaxTime=(raw or {}).get('options',{}).get('MaxTime')),
        progress=dict(intlinprog_entry_elapsed_s=[e['received_elapsed_s'] for e in entered],
            rootlp_entry_events=len(roots),later_phase_events=len(later),root_LP_completion='OBSERVED' if later else 'UNKNOWN_NOT_OBSERVED',
            finite_native_bound_events=len(bounds),callback_vector_events=len(vectors),
            callback_counter_observations=[dict(event=e.get('event_number'),state=e.get('state'),
                received_elapsed_s=e['received_elapsed_s'],phase=e.get('values',{}).get('phase'),
                numfeaspoints=e.get('values',{}).get('numfeaspoints'),vector_length=len(e.get('x',[])))
                for e in timely if e.get('kind')=='callback'],
            frozen_progress_metrics=receipt['progress'],progress_usable=controller['progress_usable'],
            independently_certified_lower_bound=False),
        initial=dict(is_native_candidate=False,candidate_identity=plan['initial_candidate_identity'],
            completed_at_elapsed_s=initial['completed_at_elapsed_s'],weighted_energy_J=initial['weighted_energy_J'],
            scene_energies_J={name:s['energy_J'] for name,s in initial['scenes'].items()},
            numerical_admission=admission,not_an_exact_feasibility_certificate=True),
        costs=dict(method_elapsed_s=receipt['method_elapsed_s'],worker_total_s=receipt['total_elapsed_s'],
            controller_total_s=controller['wall_s'],phases_exclusive_s=timing['phases_exclusive_s'],
            unattributed_s=timing['unattributed_s'],matlab_phase_seconds=(raw or {}).get('phase_seconds'),
            startup_wall_s=session.get('startup_wall_seconds'),startup_observer=read(RUN/'startup_timing_observer.json'),
            publication_elapsed_s=(allocation or {}).get('measured_elapsed_s'),
            response_complete_elapsed_s=(native or {}).get('solver_response_complete_at_monotonic',claim['parent_start_monotonic'])-claim['parent_start_monotonic'],
            cleanup_s=closed['cleanup_wall_seconds'],
            other_post_method_worker_s=receipt['total_elapsed_s']-receipt['method_elapsed_s']-closed['cleanup_wall_seconds'],
            controller_overhead_s=controller['wall_s']-receipt['total_elapsed_s']),
        audit_scientific_calls=dict(native_MILP_LP=0,complete_physical_evaluation=0,model_build=0),
        comparison_scope='Saved ON entry diagnosis only; no historical OFF/new ON speedup comparison.',
        next_action='STOP_NO_RETRY_NO_AUTOMATIC_ABC')
    bindings={}
    for folder,dirs,files in os.walk(RUN):
        dirs[:]=[d for d in dirs if d not in ('temp','isolated_preferences','__pycache__')]
        for name in files:
            p=Path(folder)/name;bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    for p in (PACKAGE/'plan.json',PACKAGE/'plan.identity.json',HERE/'prelaunch_identity.json',ROOT/'work/on_budget_A420_approval_20261112.json'):
        bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    save(out/'source_bindings.json',dict(sorted(bindings.items())))
    result['source_bindings_sha256']=sha(out/'source_bindings.json')
    save(out/'audit.json',result)
    print(json.dumps(dict(passed=result['passed'],checks=len(checks),stop_state=result['stop_state'],
        native=result['native'],progress=result['progress'],costs=result['costs']),ensure_ascii=False))


if __name__=='__main__':main()
