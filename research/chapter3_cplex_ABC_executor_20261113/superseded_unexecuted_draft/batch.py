"""One frozen A/B/C batch. Supervises independent arm controllers; no scientific imports."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,os,secrets,subprocess,sys
from pathlib import Path
from core import read,save,sha,verify,authorize,IntegrityError,error_record
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

def launch_arm(arm,root,here,plan_path,plan_hash,plan,batch,approval_path,shared_setup_s=0):
    actual_start=time.monotonic();t0=actual_start-shared_setup_s;nonce=secrets.token_hex(16)
    save(batch/(arm+'_launch.json'),dict(arm=arm,parent_pid=os.getpid(),start_monotonic=t0,actual_dispatch_monotonic=actual_start,
        shared_setup_charged_s=shared_setup_s,nonce=nonce,plan_sha256=plan_hash))
    argv=[plan['native_runtime']['python'],'-B',str(here/'controller.py'),'--workspace',str(root),
          '--plan',str(plan_path),'--expected-sha',plan_hash,'--approval',str(approval_path),
          '--arm',arm,'--batch',str(batch),'--t0',repr(t0)]
    p=None;job=None;cleanup=False;errors=[];accounting={};receipt=None
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
                accounting=job.accounting();cleanup=accounting['active_processes']==0;job.close()
            except BaseException as e:cleanup=False;errors.append(error_record(e))
    elapsed=time.monotonic()-t0
    if receipt and elapsed>=600:
        receipt['outcome']['strict_success']=False;receipt['outcome']['scientific_snapshot_accepted']=False
        receipt['outcome']['reasons'].append('OUTER_CLEANUP_OR_ARCHIVE_EXCEEDED_600')
    return dict(receipt=receipt,outer_cleanup_ok=cleanup,outer_job_accounting=accounting,
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

def verify_commit(root,here,plan,approval):
    for name in ['plan.json']+list(plan['code_hashes']):
        raw=subprocess.check_output(['git','-C',str(root/'work/publish_repo'),'show',
            approval['frozen_commit']+':'+plan['repository_package']+'/'+name],stderr=subprocess.PIPE)
        if hashlib.sha256(raw).hexdigest()!=sha(here/name):raise IntegrityError('Approved source mismatch: '+name)

def main():
    started=ENTRY
    a=argparse.ArgumentParser();a.add_argument('--workspace',type=Path,required=True);a.add_argument('--plan',type=Path,required=True)
    a.add_argument('--expected-sha',required=True);a.add_argument('--approval',type=Path,required=True);args=a.parse_args()
    root=args.workspace.resolve();here=Path(__file__).resolve().parent;plan_path=args.plan.resolve()
    if sha(plan_path)!=args.expected_sha:raise IntegrityError('Plan identity')
    plan=read(plan_path);approval=read(args.approval);authorize(approval,args.expected_sha)
    if plan['protocol']!='D284-CPLEX-fresh-ABC-executor-v1' or not plan['ready_to_request_independent_scientific_authorization']:raise PermissionError('Unready plan')
    verify_commit(root,here,plan,approval)
    verify(here,plan['code_hashes'])
    batch=root/plan['execution_directory'];batch.mkdir(exist_ok=False)
    save(batch/'approval_consumed.json',approval)
    save(batch/'batch_claim.json',dict(plan_sha256=args.expected_sha,approval_consumed=True,maximum_total_solve_calls=3,
        maximum_solve_calls_per_arm=1,order=list(ARMS),clock_origin=time.monotonic(),setup_wall_s=time.monotonic()-started))
    setup=time.monotonic()-started
    # Same measured launcher setup debit for every group; no free common setup.
    # It is charged three times conservatively, never pooled or reused as science.
    def launch(arm):return launch_arm(arm,root,here,plan_path,args.expected_sha,plan,batch,batch/'approval_consumed.json',setup)
    def persist(arm,record,blocked):persist_arm(batch,arm,record,blocked)
    result=dispatch(launch,persist);result.update(actual_batch_wall_s=time.monotonic()-started,plan_sha256=args.expected_sha,
        shared_scientific_results=False,postwindow_administrative_only=True)
    save(batch/'batch_receipt.json',result)
    print(str(batch))
if __name__=='__main__':main()

