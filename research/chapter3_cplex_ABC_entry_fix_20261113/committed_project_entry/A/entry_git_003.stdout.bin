"""One frozen A/B/C batch. Supervises independent arm controllers; no scientific imports."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,os,secrets,subprocess,sys
from pathlib import Path
from core import read,save,sha,verify,authorize,IntegrityError,error_record,Clock
from identity import verify_commit,require_control_only
from windows_job import Job

ARMS=('A','B','C')
GLOBAL_OUTCOMES={'LICENSE_ERROR','IDENTITY_OR_CORRECTNESS_ERROR','BOUND_CONFLICT','CLEANUP_FAILURE','WORKER_ERROR','WORKER_OUTER_FAILURE'}
GLOBAL_REASONS={'CLEANUP_FAILURE','IDENTITY_DRIFT','BOUND_CONFLICT','CONTROLLER_ERROR','EVIDENCE_INTEGRITY','UNCLASSIFIED_WORKER_ERROR','BATCH_RECEIPT_INVALID'}
def accumulate(blocked,arm,record):
    """Union over all completed arms; a later timeout never erases a previous scope."""
    blocked=set(blocked)
    if not record.get('outer_cleanup_ok',False):
        return blocked|set(ARMS)
    receipt=record.get('receipt') or {};outcome=receipt.get('outcome') or {}
    if outcome.get('stop_scope')=='GLOBAL' or set(outcome.get('reasons',[]))&GLOBAL_REASONS or outcome.get('outcome') in GLOBAL_OUTCOMES:
        return blocked|set(ARMS)
    if outcome.get('outcome')=='REDUCTION_CERTIFICATE_ERROR':
        scope=set(outcome.get('affected_arms',[]))
        # Only independently attributable, closed feature scopes may continue.
        if scope not in ({'B','C'},{'C'}):return blocked|set(ARMS)
        blocked|=scope
    if record.get('supervisor_error'):blocked|=set(ARMS)
    return blocked

def dispatch(launch,persist=lambda *x:None):
    results={};blocked=set()
    for arm in ARMS:
        if arm in blocked:
            results[arm]=dict(skipped=True,reason='CUMULATIVE_STOP_SCOPE',blocked_arms=sorted(blocked))
        else:
            results[arm]=launch(arm)
            blocked=accumulate(blocked,arm,results[arm])
        persist(arm,results[arm],sorted(blocked))
    return dict(arms=results,blocked_arms=sorted(blocked),retries=0)

def read_terminal(folder,exit_code,plan_hash):
    """Administrative read may revoke, never add scientific credit after arm window."""
    folder=Path(folder)
    if not (folder/'controller_receipt.json').exists():
        early=folder.parent/(folder.name+'_entry_unclaimed_failure.json')
        if early.exists():
            detail=read(early)
            if detail.get('plan_sha256')!=plan_hash or detail.get('arm')!=folder.name:raise IntegrityError('Unclaimed entry receipt identity')
            return dict(plan_sha256=plan_hash,entry_error=detail,scientific_worker_started=False,
                outcome=dict(outcome='CONTROL_ENTRY_UNCLAIMED_FAILURE',stop_scope='GLOBAL',reasons=['CONTROL_ENTRY_FAILURE']))
        return dict(outcome=dict(outcome='MISSING_ARM_RECEIPT',stop_scope='GLOBAL',reasons=['BATCH_RECEIPT_INVALID']))
    receipt=read(folder/'controller_receipt.json');completion=read(folder/'controller_completion.json')
    if receipt.get('plan_sha256')!=plan_hash or completion.get('receipt_sha256')!=sha(folder/'controller_receipt.json'):
        raise IntegrityError('Arm terminal identity')
    if not (completion.get('within_method_window') is True and completion.get('after_receipt_and_hash_elapsed_s',600)<600) or (folder/'budget_invalidated.json').exists():
        receipt['outcome']['strict_success']=False;receipt['outcome']['scientific_snapshot_accepted']=False
        receipt['outcome']['reasons'].append('TERMINAL_BUDGET_INVALIDATED')
    # exit 1 is an expected control rejection, not by itself mathematical infeasibility.
    if exit_code not in (0,1):raise IntegrityError('Unexpected arm controller exit')
    if exit_code!=0:
        receipt['outcome']['strict_success']=False;receipt['outcome']['scientific_snapshot_accepted']=False
    return receipt

def launch_arm(arm,root,here,plan_path,plan_hash,plan,batch,approval_path,shared_setup_s=0,entry_only=False):
    actual_start=time.monotonic();t0=actual_start-shared_setup_s;nonce=secrets.token_hex(16)
    save(batch/(arm+'_launch.json'),dict(arm=arm,parent_pid=os.getpid(),start_monotonic=t0,actual_dispatch_monotonic=actual_start,
        shared_setup_charged_s=shared_setup_s,nonce=nonce,plan_sha256=plan_hash))
    argv=[plan['native_runtime']['python'],'-B',str(here/'controller.py'),'--workspace',str(root),
          '--plan',str(plan_path),'--expected-sha',plan_hash,'--approval',str(approval_path),
          '--arm',arm,'--batch',str(batch),'--t0',repr(t0)]
    if entry_only:argv.append("--entry-only")
    p=None;job=None;cleanup=False;errors=[];accounting={};receipt=None;job_limits={}
    try:
        # Outer job owns controller plus worker; nested worker job still enforces 3 GiB.
        job=Job(plan['limits']['job_and_process_hard_commit_bytes']+plan['limits']['parent_private_bytes'],active_limit=2)
        with (batch/(arm+'_controller_stdout.log')).open('xb') as stdout,(batch/(arm+'_controller_stderr.log')).open('xb') as stderr:
            p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,cwd=batch,creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(p);p.stdin.write(('D284_ARM_GO '+nonce+'\n').encode());p.stdin.flush();p.stdin.close()
            try:p.wait(timeout=max(.01,620-(time.monotonic()-t0)))
            except subprocess.TimeoutExpired:
                errors.append(dict(type='OuterDeadline',message='620 second emergency cleanup only; scientific credit ended at 600'))
                job.terminate();p.wait(timeout=2)
            until=time.monotonic()+2
            accounting=job.accounting()
            while accounting['active_processes'] and time.monotonic()<until:
                time.sleep(.02);accounting=job.accounting()
            cleanup=accounting['active_processes']==0
            receipt=read_terminal(batch/arm,p.returncode,plan_hash)
    except BaseException as e:errors.append(error_record(e))
    finally:
        if job:
            try:
                if p is not None and p.poll() is None:job.terminate();p.wait(timeout=2)
                accounting=job.accounting();job_limits=job.limits();cleanup=accounting['active_processes']==0;job.close()
            except BaseException as e:cleanup=False;errors.append(error_record(e))
    elapsed=time.monotonic()-t0
    if receipt and elapsed>=600:
        receipt['outcome']['strict_success']=False;receipt['outcome']['scientific_snapshot_accepted']=False
        receipt['outcome']['reasons'].append('OUTER_CLEANUP_OR_ARCHIVE_EXCEEDED_600')
    return dict(receipt=receipt,outer_cleanup_ok=cleanup,outer_job_accounting=accounting,outer_job_limits=job_limits,
                exit_code=p.returncode if p else None,supervisor_error=errors or None,
                method_elapsed_including_shared_setup_s=elapsed,actual_arm_wall_including_outer_cleanup_s=time.monotonic()-actual_start,
                shared_setup_charged_s=shared_setup_s,
                administrative_postwindow_reads_do_not_upgrade_science=True)

def persist_arm(batch,arm,record,blocked):
    """Dispatch archival is charged too; late writes only revoke the arm's claim."""
    launch=read(batch/(arm+'_launch.json')) if not record.get('skipped') else None
    save(batch/(arm+'_dispatch_receipt.json'),dict(record=record,cumulative_blocked_arms=blocked))
    if launch:
        elapsed=time.monotonic()-launch['start_monotonic']
        save(batch/(arm+'_outer_completion.json'),dict(after_dispatch_archive_elapsed_s=elapsed,within_method_window=elapsed<600))
        if time.monotonic()-launch['start_monotonic']>=600:
            save(batch/(arm+'_outer_budget_invalidated.json'),dict(reason='OUTER_FINAL_WRITE_EXCEEDED_600',scientific_credit=False))
            if record.get('receipt'):
                record['receipt']['outcome'].update(strict_success=False,scientific_snapshot_accepted=False)

def batch_exit_code(result):
    return 1 if result['blocked_arms'] else 0

def main():
    started=ENTRY;clock=Clock(ENTRY)
    a=argparse.ArgumentParser();a.add_argument('--workspace',type=Path,required=True);a.add_argument('--plan',type=Path,required=True)
    a.add_argument('--expected-sha',required=True);a.add_argument('--approval',type=Path,required=True)
    a.add_argument('--entry-only',action='store_true');a.add_argument('--control-output',type=Path);args=a.parse_args()
    root=args.workspace.resolve();here=Path(__file__).resolve().parent;plan_path=args.plan.resolve()
    if sha(plan_path)!=args.expected_sha:raise IntegrityError('Plan identity')
    plan=read(plan_path);approval=read(args.approval)
    if args.entry_only:require_control_only(approval,args.expected_sha)
    else:authorize(approval,args.expected_sha)
    if plan['protocol']!='D285-CPLEX-fresh-ABC-entry-fixed-v1' or not plan['ready_to_request_independent_scientific_authorization']:raise PermissionError('Unready plan')
    if args.entry_only:
        if args.control_output is None:raise PermissionError('Separate control output required')
        batch=args.control_output.resolve();batch.relative_to(root)
        if batch==root/plan['execution_directory']:raise PermissionError('Controls cannot consume scientific output')
    else:
        if args.control_output is not None:raise PermissionError('Unexpected control output')
        batch=root/plan['execution_directory']
    batch.mkdir(exist_ok=False)
    approval_path=batch/('control_approval.json' if args.entry_only else 'approval_consumed.json')
    save(approval_path,approval)
    save(batch/'batch_claim.json',dict(plan_sha256=args.expected_sha,approval_consumed=not args.entry_only,
        entry_only=args.entry_only,maximum_total_solve_calls=0 if args.entry_only else 3,
        maximum_solve_calls_per_arm=0 if args.entry_only else 1,order=list(ARMS),clock_origin=time.monotonic()))
    try:
        verify_commit(root,here,plan,approval,batch,clock,plan_path)
        verify(here,plan['code_hashes']);clock.check(550)
    except BaseException as e:
        save(batch/'batch_entry_failure.json',dict(error=error_record(e),elapsed_s=clock.elapsed,
            scientific_calls=0,scientific_workers_started=0,stop_scope='GLOBAL'))
        result=dict(arms={arm:dict(skipped=True,reason='BATCH_ENTRY_FAILURE') for arm in ARMS},
            blocked_arms=list(ARMS),retries=0,plan_sha256=args.expected_sha,entry_only=args.entry_only,
            scientific_calls=0,actual_batch_wall_s=time.monotonic()-started)
        save(batch/'batch_receipt.json',result);return 1
    setup=time.monotonic()-started
    save(batch/'shared_setup.json',dict(setup_wall_s=setup,charged_identically_to_each_arm=True))
    # All startup, identity reads and raw evidence writes are in the same debit.
    def launch(arm):return launch_arm(arm,root,here,plan_path,args.expected_sha,plan,batch,approval_path,setup,args.entry_only)
    def persist(arm,record,blocked):persist_arm(batch,arm,record,blocked)
    result=dispatch(launch,persist);result.update(actual_batch_wall_s=time.monotonic()-started,plan_sha256=args.expected_sha,
        shared_scientific_results=False,postwindow_administrative_only=True,entry_only=args.entry_only)
    if args.entry_only:result.update(scientific_calls=0,scientific_workers_started=0)
    result['batch_exit_code']=batch_exit_code(result)
    save(batch/'batch_receipt.json',result)
    print(str(batch));return result['batch_exit_code']
if __name__=='__main__':raise SystemExit(main())


