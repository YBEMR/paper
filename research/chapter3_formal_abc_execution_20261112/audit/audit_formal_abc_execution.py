"""Post-run read-only audit of already formed evidence. No solver, build or thermal evaluation."""
from pathlib import Path
from fractions import Fraction as F
import json,sys,time,hashlib

ROOT=Path(__file__).resolve().parent.parent
PACKAGE=ROOT/'work/formal_abc_v1'
sys.path.insert(0,str(PACKAGE))
from guard import read,sha,save,verify_plan,verify_approval
from representation import digest
from saved_adapter_base import schedule_key
from budget_policy import ABC_DYNAMIC

def main():
    start=time.monotonic();run=ROOT/'work/formal_abc_execution_v1'
    batch=read(run/'batch.json');plan=verify_plan(PACKAGE/'plan.json',ROOT,PACKAGE)
    verify_approval(read(run/'approval_consumed.json'),sha(PACKAGE/'plan.json'))
    checks=[];arms={};owned=[]
    def check(name,passed,detail=None):checks.append(dict(name=name,passed=bool(passed),detail=detail))
    check('fixed_batch_order',batch['completed']==list('ABC')[:len(batch['completed'])])
    check('no_batch_retry',batch['retries']==0)
    for arm in batch['completed']:
        folder=run/arm;controller=read(folder/'controller.json');claim=read(folder/'claim.json')
        monitor=read(folder/'process_monitor.json') if (folder/'process_monitor.json').exists() else {}
        owned+=monitor.get('observed_identities',[])
        r=read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
        if r is None:
            arms[arm]=dict(state='NO_COMPLETE_RECEIPT',controller=controller);continue
        model=read(folder/'model_summary.json') if (folder/'model_summary.json').exists() else {}
        allocation=read(folder/'publication_allocation.json') if (folder/'publication_allocation.json').exists() else None
        native=r.get('native') or {};validation=r.get('returned_vector_validation') or {}
        timing=read(folder/'timing_after_cleanup.json') if (folder/'timing_after_cleanup.json').exists() else {}
        events=[json.loads(line) for line in (folder/'progress.jsonl').read_text(encoding='utf-8').splitlines()] if (folder/'progress.jsonl').exists() else []
        entries=[e for e in events if e.get('kind')=='solver_entered']
        root=[e for e in events if e.get('values',{}).get('phase')=='rootlp']
        later=[e for e in events if e.get('values',{}).get('phase') in ('heuristics','cutgen','branching')]
        check(arm+'.single_native_request',r['native_request_attempts']<=1 and len(entries)<=1 and r['native_requests_published']<=1)
        check(arm+'.single_fresh_build',r['model_builds']<=1)
        check(arm+'.evaluation_cap',r['physical_evaluations_observed']<=4)
        check(arm+'.no_retry',r['retries']==0)
        check(arm+'.claim_identity',claim['arm']==arm and claim['plan_sha256']==sha(PACKAGE/'plan.json'))
        check(arm+'.event_timestamps',all(0<=e['received_elapsed_s']<550 for e in events))
        check(arm+'.root_evidence_consistent',r['progress']['root_lp_entry_observed']==bool(root) and r['progress']['root_lp_completion_via_later_phase']==bool(later))
        if allocation:
            expected=ABC_DYNAMIC.allocate(allocation['measured_elapsed_s'])
            check(arm+'.frozen_dynamic_allocation',allocation==expected)
        if (folder/'matlab/request_000001.request.json').exists():
            request=read(folder/'matlab/request_000001.request.json')
            check(arm+'.published_native_cap',request['solver_max_time_s']==request['solver_max_time_s_declared']==allocation['native_seconds'])
        if (folder/'initialization.json').exists():
            initial=read(folder/'initialization.json')
            witnesses=[a for a in initial['attempts'] if a.get('evaluation',{}).get('state')=='SAFE']
            check(arm+'.initial_attempt_cap',len(initial['attempts'])<=3)
            if witnesses:
                seed=witnesses[0]['candidate'];ev=witnesses[0]['evaluation']
                check(arm+'.fresh_common_initial_identity',digest(seed)==plan['initial_candidate_identity'])
                check(arm+'.initial_evaluation_identity',ev['evidence_identity']==dict(input_sha256=plan['input_identity'],candidate_sha256=digest(seed)))
        else:seed=None
        returned=r.get('returned_evaluation');initial_eval=r.get('initial_evaluation')
        if returned:
            check(arm+'.returned_evaluation_identity',returned.get('evidence_identity')==dict(input_sha256=plan['input_identity'],candidate_sha256=digest(r['candidate'])))
        if validation.get('state')=='ADMITTED':
            check(arm+'.same_schedule_independently_recomputed',r['same_initial']==(schedule_key(seed)==schedule_key(r['candidate'])))
            check(arm+'.numerical_admission_timely',validation['completed_at_elapsed_s']<600)
        if r['returned_complete_SAFE']:
            check(arm+'.full_SAFE_timely',returned['completed_at_elapsed_s']<600 and len(returned['scenes'])==2 and
                  all(s.get('complete') and s.get('state')=='SAFE' for s in returned['scenes'].values()))
            improved=F(returned['weighted_energy_J'][1])<F(initial_eval['weighted_energy_J'][0]) and r['same_initial'] is False
            check(arm+'.strict_improvement_recomputed',r['strict_energy_improvement']==improved)
        check(arm+'.no_optimality_overclaim',r['independent_optimality_proof'] is False)
        check(arm+'.native_identity_not_overclaimed',not r['evidence_integrity'] or (r.get('identity') or {}).get('state')=='VERIFIED')
        check(arm+'.cleanup_not_overclaimed',not r['lifecycle_integrity'] or (r['cleanup']['complete'] and monitor.get('complete') and not monitor.get('forced_pids')))
        if arm!='C' and (r.get('fault_scope')=='ALL' or not r['cleanup'].get('complete') or r['identity_after'].get('state')!='VERIFIED'):
            check(arm+'.stop_scope_obeyed',batch['completed'][-1]==arm)
        phases=timing.get('phases_exclusive_s',{})
        model_flags=model.get('formulation',{})
        if model:
            check(arm+'.input_model_identity',model['problem_id']=='base__R1' and model['preprocessing']['source_input_sha256']==plan['input_identity'])
            check(arm+'.reduction_switches',bool(model_flags.get('propagate_support'))==(arm!='A') and bool(model_flags.get('prune_joint_states'))==(arm=='C'))
        startup=read(folder/'matlab/session.json') if (folder/'matlab/session.json').exists() else {}
        best=r['progress']['best_consistent_native_bound']
        counts=r['progress']['callback_counter_records']
        final_count=(native.get('output') or {}).get('numfeaspoints')
        done_counts=[c.get('numfeaspoints') for c in counts if c.get('state')=='done']
        arms[arm]=dict(terminal_state=r['terminal_state'],error=r['error'],fault_scope=r['fault_scope'],
            controller_complete=controller['completed'],lifecycle_integrity=r['lifecycle_integrity'],evidence_integrity=r['evidence_integrity'],
            actual_native_calls=r['native_calls_observed'],published_requests=r['native_requests_published'],full_builds=r['model_builds'],
            complete_evaluation_attempts=r['physical_evaluations_observed'],native_MaxTime_s=r['allocated_native_MaxTime_s'],
            publication_elapsed_s=allocation['measured_elapsed_s'] if allocation else None,
            native_entered_elapsed_s=entries[0]['received_elapsed_s'] if entries else None,
            root_LP_entry_elapsed_s=root[0]['received_elapsed_s'] if root else None,
            root_LP_completion_later_phase_elapsed_s=later[0]['received_elapsed_s'] if later else None,
            best_consistent_native_lower_bound=best['value'] if best else None,
            native_bound_conflict=r['native_bound_conflict'],independent_bound_certificate=False,
            native_status=native.get('status'),native_exitflag=native.get('exitflag'),native_output=native.get('output'),
            native_phase_seconds=native.get('phase_seconds'),native_response_elapsed_s=native.get('received_by_adapter_elapsed_s'),
            callback_counter_records=counts,callback_final_count_discrepancy=bool(done_counts and done_counts[-1]!=final_count),
            native_vector_length=len(native.get('x',[])),native_vector_sha256=digest(native['x']) if native.get('x') else None,
            candidate_identity=digest(r['candidate']) if r.get('candidate') else None,
            numerical_admission=validation.get('state','UNKNOWN'),returned_complete_SAFE=r['returned_complete_SAFE'],
            same_initial=r['same_initial'],new_complete_SAFE=r['new_complete_SAFE'],strict_energy_improvement=r['strict_energy_improvement'],
            initial_energy_J=initial_eval.get('weighted_energy_J') if initial_eval else None,
            returned_energy_J=returned.get('weighted_energy_J') if returned else None,
            final_SAFE_completed_at_s=returned.get('completed_at_elapsed_s') if returned else None,
            independent_optimality_proof=False,progress_usable=r['progress_usable'],
            method_elapsed_s=r['method_elapsed_s'],worker_receipt_elapsed_s=r['total_elapsed_s'],
            actual_controller_wall_s=controller['actual_total_wall_s'],
            cleanup_wall_s=(r['cleanup'].get('receipt') or {}).get('cleanup_wall_seconds'),
            startup_wall_s=startup.get('startup_wall_seconds'),phases_exclusive_s=phases,
            unattributed_method_s=timing.get('unattributed_s'),owned_process_monitor=monitor)
    identities=[(p['pid'],p['create_time']) for p in owned]
    check('independent_owned_processes',len(identities)==len(set(identities)))
    import psutil
    states=[]
    for pid,created in identities:
        try:
            p=psutil.Process(pid);alive=p.create_time()==created and p.is_running()
            states.append(dict(pid=pid,create_time=created,original_process_alive=alive))
        except psutil.NoSuchProcess:states.append(dict(pid=pid,create_time=created,original_process_alive=False))
        except psutil.Error as e:states.append(dict(pid=pid,create_time=created,original_process_alive=None,error=repr(e)))
    check('owned_processes_gone',all(s['original_process_alive'] is False for s in states))
    out=ROOT/'work/formal_abc_execution_audit';out.mkdir(exist_ok=False)
    result=dict(plan_sha256=sha(PACKAGE/'plan.json'),execution_base_commit='cbf0257d65c6c3771ef26ad51a96245962ce6f40',
        passed=all(c['passed'] for c in checks),checks=checks,arms=arms,batch=batch,
        postrun_process_check=states,frozen_source_files_verified=len(plan['workspace_files']),frozen_package_files_verified=len(plan['package_files']),
        independent_optimality_or_physical_lower_bound_proof=False,
        audit_wall_s=time.monotonic()-start,audit_new_scientific_calls=0,
        scope='Post-run evidence/identity/timing recomputation only; cannot add late solver or SAFE credit')
    save(out/'audit.json',result)
    print(json.dumps(dict(passed=result['passed'],checks=len(checks),failed=[c for c in checks if not c['passed']],
        arms={a:{k:r.get(k) for k in ['terminal_state','actual_native_calls','native_MaxTime_s','returned_complete_SAFE','same_initial','strict_energy_improvement','actual_controller_wall_s']} for a,r in arms.items()})))

if __name__=='__main__':main()
