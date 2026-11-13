"""Read-only committed-project entry audit; no native/scientific execution."""
from pathlib import Path
import json,hashlib,time
root=Path(__file__).resolve().parents[2];here=Path(__file__).parent
run=root/'work/cplex_ABC_entry_project_v1';package=root/'work/cplex_ABC_v3'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=read(package/'plan.json');batch=read(run/'batch_receipt.json')
checks={};costs={};started=time.monotonic()
checks['plan_hash']=sha(package/'plan.json')=='ff129eb1f340ad067b891542b486ec9c5f0da19c046371eacd167cb9bc75bbd5'
checks['frozen_source_unchanged']=all(sha(package/k)==v for k,v in plan['code_hashes'].items())
checks['no_production_directory']=not (root/plan['execution_directory']).exists()
checks['control_approval_not_science']=read(run/'control_approval.json')['decision']=='CONTROL_ONLY'
checks['scientific_approval_not_consumed']=read(run/'batch_claim.json')['approval_consumed'] is False
checks['all_groups_completed_without_blocking']=batch['blocked_arms']==[] and batch['batch_exit_code']==0
for a in 'ABC':
    out=run/a;r=batch['arms'][a];receipt=read(out/'controller_receipt.json');s=read(out/'entry_git_summary.json')
    checks[a+'_true_entry_only']=receipt['entry_only'] is True and receipt['scientific_worker_started'] is False and receipt['outcome']['outcome']=='CONTROL_ENTRY_ONLY_VERIFIED'
    checks[a+'_all_22_Git_reads']=s['passed'] is True and len(s['checks'])==1+len(plan['code_hashes'])==22
    checks[a+'_raw_bytes_identity']=all(sha(out/x['stdout_file'])==x['stdout_sha256']==x['expected_blob_sha256'] and sha(out/x['stderr_file'])==x['stderr_sha256'] and x['returncode']==0 and x['returned_elapsed_s']<550 for x in s['checks'])
    checks[a+'_receipt_hashes']=all(sha(out/k)==v for k,v in receipt['evidence_hashes'].items())
    checks[a+'_no_scientific_worker_artifacts']=not any((out/x).exists() for x in ('claim.json','owned_process.json','runtime.json','native_response.json','model_summary.json','initialization.json'))
    checks[a+'_unchanged_Job_limits']=r['outer_job_limits']['active_limit']==2 and r['outer_job_limits']['job_memory']==3758096384
    checks[a+'_clean']=r['outer_cleanup_ok'] is True and r['outer_job_accounting']['active_processes']==0 and r['exit_code']==0
    checks[a+'_in_window']=read(run/(a+'_outer_completion.json'))['within_method_window'] is True and not (run/(a+'_outer_budget_invalidated.json')).exists()
    costs[a]=dict(method_s=r['method_elapsed_including_shared_setup_s'],actual_wall_s=r['actual_arm_wall_including_outer_cleanup_s'],
        shared_startup_charged_s=r['shared_setup_charged_s'],peak_outer_commit_MiB=r['outer_job_limits']['peak_job_memory']/1048576)
assert all(checks.values()),checks
result=dict(passed=True,checks=checks,source_commit='e3b1c1414d5d4de367ccab72c3b73e8787b2a9da',plan_sha256=sha(package/'plan.json'),
    costs=costs,batch_wall_s=batch['actual_batch_wall_s'],audit_wall_s=time.monotonic()-started,
    scientific_workers=0,CPLEX_objects=0,full_builds=0,solver_calls=0,thermal_evaluations=0,
    ready_to_request_independent_ABC_authorization=True,execution_authorized=False,
    limits='Entry/identity/control acceptance only; no new model, CPLEX environment or performance acceptance')
with (here/'audit.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(dict(passed=True,checks=len(checks),costs=costs)))

