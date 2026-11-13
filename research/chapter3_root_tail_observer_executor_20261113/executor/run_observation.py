"""Guarded one-shot entry. No automatic authorization creation or retries."""
import time
ENTRY=time.monotonic()
import argparse,os,secrets,subprocess,sys
from pathlib import Path
from guard import read,save,sha,inside,verify_plan,verify_approval,claim_once,ARM
from scope import ScopeLedger
from process_monitor import monitor_owned
PACKAGE=Path(__file__).resolve().parent

def run(workspace,plan_path,approval_path):
    workspace=workspace.resolve();plan_path=plan_path.resolve();approval_path=approval_path.resolve()
    plan=verify_plan(plan_path,workspace,PACKAGE);approval=read(approval_path);verify_approval(approval,sha(plan_path))
    import psutil
    batch=claim_once(workspace,plan,dict(plan_sha256=sha(plan_path),approval_sha256=sha(approval_path),
        parent_pid=os.getpid(),entry_monotonic=ENTRY,no_retry=True))
    save(batch/'approval_consumed.json',approval)
    scope=ScopeLedger(plan['arms'],{ARM:{'model_arm':'C'}})
    while scope.pending():
        arm=scope.pending()[0];folder=batch/arm;folder.mkdir(exist_ok=False)
        token=secrets.token_hex(32);start=ENTRY
        save(folder/'claim.json',dict(arm=arm,plan_sha256=sha(plan_path),approval_sha256=sha(approval_path),
            parent_start_monotonic=start,parent_pid=os.getpid(),parent_create_time=psutil.Process().create_time(),worker_token=token))
        temp=folder/'temp';temp.mkdir()
        argv=[sys.executable,'-B',str(PACKAGE/'run_observation.py'),'_worker','--workspace',str(workspace),
            '--plan',str(plan_path),'--approval',str(approval_path),'--token',token]
        save(folder/'command.json',dict(argv=argv,hidden_window=True))
        receipt=None;monitor=None
        try:
            with (folder/'stdout.log').open('x',encoding='utf-8') as out,(folder/'stderr.log').open('x',encoding='utf-8') as err:
                proc=subprocess.Popen(argv,cwd=PACKAGE,env=dict(os.environ,TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),PYTHONDONTWRITEBYTECODE='1'),
                    stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                monitor=monitor_owned(proc,psutil.Process(proc.pid).create_time(),start,psutil)
            save(folder/'process_monitor.json',monitor)
            receipt=read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
            intact=bool(monitor['returncode']==0 and monitor['complete'] and not monitor['forced_pids'] and receipt)
            controller=dict(completed=intact,process_monitor=monitor,actual_total_wall_s=time.monotonic()-start,retries=0)
        except Exception as e:
            intact=False;controller=dict(completed=False,error=repr(e),cleanup='UNKNOWN',actual_total_wall_s=time.monotonic()-start)
        # Production coordinator uses the persistent ledger, never a stateless current receipt filter.
        scope.consume(arm,receipt,intact)
        save(folder/'controller.json',controller)
    save(batch/'batch.json',dict(scope=scope.snapshot(),actual_total_wall_s=time.monotonic()-ENTRY,
        controller_integrity=intact,scientific_claims_revoked=not intact,retries=0))

def worker(workspace,plan_path,approval_path,token):
    workspace=workspace.resolve();plan_path=plan_path.resolve();approval_path=approval_path.resolve()
    plan=verify_plan(plan_path,workspace,PACKAGE);verify_approval(read(approval_path),sha(plan_path))
    folder=inside(workspace,plan['execution_directory'])/ARM;claim=read(folder/'claim.json')
    if claim['worker_token']!=token or claim['arm']!=ARM or claim['plan_sha256']!=sha(plan_path) or claim['approval_sha256']!=sha(approval_path):
        raise PermissionError('Wrong one-use worker claim')
    import psutil
    if os.getppid()!=claim['parent_pid'] or psutil.Process(claim['parent_pid']).create_time()!=claim['parent_create_time']:
        raise PermissionError('Parent identity drift')
    save(folder/'worker_claim.json',dict(pid=os.getpid(),start_monotonic=claim['parent_start_monotonic']))
    from runtime import Runtime
    from control import execute
    runtime=Runtime(workspace,PACKAGE,plan_path,plan,folder,claim['parent_start_monotonic'])
    result=execute(runtime)
    result.update(actual_native_entry_events=runtime.actual_native_entries,physical_evaluations_attempted=runtime.evaluations,
        model_builds=0,allocation=runtime.allocation,observations_were_executed=True)
    save(folder/'receipt.json',result)
    print(result['terminal_state'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','_worker'])
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--plan',type=Path,default=PACKAGE/'plan.json')
    p.add_argument('--approval',type=Path,required=True);p.add_argument('--token')
    a=p.parse_args()
    if a.command=='run': run(a.workspace,a.plan,a.approval)
    else: worker(a.workspace,a.plan,a.approval,a.token)
