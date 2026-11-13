"""Post-stop read-only audit. No optimizer, full model construction or heat evaluation."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,sys,time
root=Path(__file__).resolve().parents[2];here=Path(__file__).parent
sys.path.insert(0,str(root/'work/cplex_ABC_v2'))
from core import read,sha,verify,authorize
from batch import verify_commit
started=time.monotonic()
run=root/'work/cplex_ABC_execution_v1';launch=root/'work/cplex_ABC_D284_launch_v1'
plan_path=root/'work/cplex_ABC_v2/plan.json';plan=read(plan_path);h=sha(plan_path)
batch=read(run/'batch_receipt.json');approval=read(run/'approval_consumed.json');host=read(launch/'host_receipt.json')
authorize(approval,h);verify_commit(root,plan_path.parent,plan,approval)
verify(plan_path.parent,plan['code_hashes'])
checks={}
checks['plan_hash_matches_approved_commit']=h=='bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6'
checks['batch_approval_claimed_once']=read(run/'batch_claim.json')['approval_consumed'] is True and host['launch_count']==1 and host['retries']==0
checks['approval_exact_copy']=sha(run/'approval_consumed.json')==sha(launch/'approval.json')
checks['no_scientific_arm_directory']=all(not (run/a).exists() for a in 'ABC')
checks['B_C_skipped']=all(batch['arms'][a].get('skipped') is True for a in 'BC')
checks['cumulative_global_stop']=batch['blocked_arms']==list('ABC')
a=batch['arms']['A'];checks['A_controller_exit_one']=a['exit_code']==1
checks['owned_processes_cleaned']=a['outer_cleanup_ok'] is True and a['outer_job_accounting']['active_processes']==0
checks['no_retry']=batch['retries']==0
checks['outside_window_no_scientific_upgrade']=not list(run.glob('*budget_invalidated*')) and read(run/'A_outer_completion.json')['within_method_window'] is True
text=(run/'A_controller_stderr.log').read_text()
checks['failure_is_git_identity_read']='CalledProcessError' in text and 'subprocess.check_output' in text and ':research/chapter3_cplex_ABC_executor_20261113/executor/plan.json' in text
source=(plan_path.parent/'controller.py').read_text();tree=ast.parse(source)
function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
positions={}
for x in ast.walk(function):
    if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='check_output':positions['git_show_line']=x.lineno
    if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='run_owned':positions['scientific_worker_launch_line']=x.lineno
checks['source_order_before_worker']=positions['git_show_line']<positions['scientific_worker_launch_line']
p=read(here/'git_probe/child.stdout.txt');q=read(here/'git_direct_probe/child.stdout.txt')
checks['pure_PATH_git_failure_reproduced']=p['returncode']==1 and 'error launching git' in p['stderr']
checks['direct_git_same_limit_identity_pass']=q['returncode']==0 and q['stdout_sha256']==h
for name in ('git_probe','git_direct_probe'):
    r=read(here/name/'receipt.json')
    checks[name+'_control_only_clean']=r['scientific_calls']==0 and r['CPLEX_imported'] is False and r['job_accounting']['active_processes']==0 and r['job_limits']['active_limit']==2
assert all(checks.values()),checks
layers=[]
for arm in 'ABC':
    layers.append(dict(arm=arm,status='PRE_WORKER_GIT_ENTRY_FAILURE' if arm=='A' else 'SKIPPED_GLOBAL_STOP',
        per_arm_full_input_and_model_identity='NOT_REACHED',fresh_builds=0,initializations=0,certifications=0,
        CPLEX_objects=0,solve_calls=0,actual_native_MaxTime_s=None,MIP_start_acceptance='NOT_REACHED',
        root_LP_entered='NOT_REACHED',root_LP_completed='NOT_REACHED',nodes=None,native_lower_bound=None,native_upper_bound=None,gap=None,
        final_native_vector='NONE',original_and_complement_admission='NOT_REACHED',independent_legality='NOT_REACHED',
        complete_AB_AC_SAFE='NOT_REACHED',different_schedule=None,strict_energy_improvement='NOT_ASSESSED',
        initial_energy_interval=None,final_energy_interval=None,independent_optimality_proof='NONE'))
ledger=dict(host_total_wall_s=host['host_wall_s'],batch_wall_s=batch['actual_batch_wall_s'],
    shared_setup_charged_s=a['shared_setup_charged_s'],A_actual_wall_including_cleanup_s=a['actual_arm_wall_including_outer_cleanup_s'],
    A_method_including_shared_setup_s=a['method_elapsed_including_shared_setup_s'],
    A_after_dispatch_archive_s=read(run/'A_outer_completion.json')['after_dispatch_archive_elapsed_s'],
    A_controller_and_git_user_cpu_s=a['outer_job_accounting']['user_cpu_s'],
    A_controller_and_git_kernel_cpu_s=a['outer_job_accounting']['kernel_cpu_s'],
    B_started=False,C_started=False,actual_native_seconds=0,scientific_evaluations=0,
    actual_A_peak_memory='UNKNOWN: pre-worker failure; outer frozen receipt lacks peak memory sample',
    post_stop_git_probe_s=read(here/'git_probe/receipt.json')['elapsed_s'],
    post_stop_direct_git_probe_s=read(here/'git_direct_probe/receipt.json')['elapsed_s'],
    interpretation='Nested method/host costs are not additive; pure post-stop controls are separate and confer no scientific credit')
result=dict(protocol='D284-post-entry-stop-audit-v1',passed=True,checks=checks,source_positions=positions,layers=layers,costs=ledger,
    approved_commit=approval['frozen_commit'],plan_sha256=h,approval_consumed=True,batch_restarted=False,
    scientific_calls=0,full_R1_builds=0,thermal_evaluations=0,
    failure='Execution control entry failed before science, not CPLEX numerical failure or ordinary solver timeout',
    mechanism='PATH resolves to cmd/git.exe launcher; it fails in the frozen two-process Job. Direct mingw64/bin/git.exe succeeds under the same cap with the exact plan hash. Original inner stderr was not persisted; pure-control evidence is separate.',
    limits=['No native feasibility, search, quality or speedup conclusion','Real entry was not resumed using the direct Git path',
        'Original A peak memory and inner Git stderr unavailable; probe readings cannot replace them',
        'The original freeze cannot be approved unchanged again; repair, control acceptance and a new independent approval are required'],
    audit_elapsed_s=time.monotonic()-started,generated_at_utc=datetime.now(timezone.utc).isoformat(),
    evidence_hashes={str(p.relative_to(root)):sha(p) for folder in (run,launch) for p in folder.rglob('*') if p.is_file()})
with (here/'summary.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(passed=True,checks=len(checks),layers=layers,costs=ledger,audit_elapsed_s=result['audit_elapsed_s']),ensure_ascii=False))

