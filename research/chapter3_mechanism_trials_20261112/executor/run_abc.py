"""One newly authorized finite mechanism batch; isolated fresh workers, no automatic retry."""
import time
ENTRY=time.monotonic()
import argparse,os,secrets,subprocess,sys
from pathlib import Path
from guard import read,save,sha,inside,verify_plan,verify_approval,claim_once
from control import execute,next_arms
from process_monitor import monitor_owned
PACKAGE=Path(__file__).resolve().parent

def run(workspace,plan_path,approval_path):
    workspace=workspace.resolve();plan_path=plan_path.resolve();approval_path=approval_path.resolve()
    plan=verify_plan(plan_path,workspace,PACKAGE)
    approval=read(approval_path);verify_approval(approval,sha(plan_path))
    import psutil
    batch=claim_once(workspace,plan,dict(plan_sha256=sha(plan_path),approval_sha256=sha(approval_path),
        parent_pid=os.getpid(),entry_monotonic=ENTRY,arms=plan['arms'],no_retry=True))
    save(batch/'approval_consumed.json',approval)
    completed=[];pending=list(plan['arms']);receipts=[]
    while pending:
        arm=pending[0];start=time.monotonic();folder=batch/arm;folder.mkdir(exist_ok=False)
        token=secrets.token_hex(32)
        save(folder/'claim.json',dict(arm=arm,plan_sha256=sha(plan_path),approval_sha256=sha(approval_path),
            parent_start_monotonic=start,parent_pid=os.getpid(),parent_create_time=psutil.Process().create_time(),worker_token=token))
        temp=folder/'temp';temp.mkdir()
        env=dict(os.environ,TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),PYTHONDONTWRITEBYTECODE='1')
        argv=[sys.executable,'-B',str(PACKAGE/'run_abc.py'),'_worker','--workspace',str(workspace),
              '--plan',str(plan_path),'--approval',str(approval_path),'--arm',arm,'--token',token]
        save(folder/'command.json',dict(argv=argv,cwd=str(PACKAGE),hidden_window=True))
        monitor=None;receipt=None
        try:
            with (folder/'stdout.log').open('x',encoding='utf-8') as out,(folder/'stderr.log').open('x',encoding='utf-8') as err:
                proc=subprocess.Popen(argv,cwd=PACKAGE,env=env,stdout=out,stderr=err,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                created=psutil.Process(proc.pid).create_time()
                monitor=monitor_owned(proc,created,start,psutil)
            save(folder/'process_monitor.json',monitor)
            receipt=read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
            intact=bool(monitor['returncode']==0 and monitor['complete'] and not monitor['forced_pids'] and receipt)
            controller=dict(arm=arm,completed=intact,actual_total_wall_s=time.monotonic()-start,
                receipt_present=receipt is not None,process_monitor=monitor,retries=0)
        except Exception as e:
            controller=dict(arm=arm,completed=False,error=repr(e),process_cleanup='UNKNOWN',
                actual_total_wall_s=time.monotonic()-start,retries=0)
            intact=False
        save(folder/'controller.json',controller);receipts.append(controller);completed.append(arm)
        pending=next_arms(plan['arms'],completed,receipt,plan['trials']) if intact else []
    save(batch/'batch.json',dict(completed=completed,not_started=[a for a in plan['arms'] if a not in completed],
        controllers=receipts,actual_batch_wall_s=time.monotonic()-ENTRY,
        per_arm_wall_sum_s=sum(r['actual_total_wall_s'] for r in receipts),
        retries=0,scientific_results_require_per_arm_layered_evidence=True))

def worker(workspace,plan_path,approval_path,arm,token):
    workspace=workspace.resolve();plan_path=plan_path.resolve();approval_path=approval_path.resolve()
    plan=verify_plan(plan_path,workspace,PACKAGE);verify_approval(read(approval_path),sha(plan_path))
    folder=inside(workspace,plan['execution_directory'])/arm;claim=read(folder/'claim.json')
    if claim['arm']!=arm or claim['worker_token']!=token or claim['plan_sha256']!=sha(plan_path) or claim['approval_sha256']!=sha(approval_path):
        raise PermissionError('Worker does not match its one-use claim')
    import psutil
    parent=psutil.Process(claim['parent_pid'])
    if parent.create_time()!=claim['parent_create_time'] or os.getppid()!=claim['parent_pid']:raise PermissionError('Parent identity drift')
    save(folder/'worker_claim.json',dict(pid=os.getpid(),start_monotonic=claim['parent_start_monotonic']))
    from runtime import Runtime
    runtime=Runtime(workspace,PACKAGE,plan_path,plan,folder,claim['parent_start_monotonic'],arm=arm)
    result=execute(runtime)
    published=(folder/'matlab/request_000001.request.json').exists()
    result.update(model_arm=runtime.model_arm,predeclared_Heuristics=runtime.trial['Heuristics'],model_builds=runtime.model_builds,physical_evaluations_observed=runtime.evaluations,
        actual_native_entry_events=runtime.actual_native_entries,
        allocated_native_MaxTime_s=(runtime.allocation or {}).get('native_seconds'),
        native_calls_observed=(1 if runtime.actual_native_entries or (result['native'] or {}).get('intlinprog_entered') is True
                               else (0 if not published else None)),native_requests_published=int(published))
    from layers import layers
    save(folder/'layered_scientific_evidence.json',layers(runtime,result))
    save(folder/'receipt.json',result)
    print(result['terminal_state'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','_worker'])
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--plan',type=Path,default=PACKAGE/'plan.json')
    p.add_argument('--approval',type=Path,required=True);p.add_argument('--arm',choices=['C_repeat','B_repeat','C_noheur']);p.add_argument('--token')
    a=p.parse_args()
    if a.command=='run':run(a.workspace,a.plan,a.approval)
    else:worker(a.workspace,a.plan,a.approval,a.arm,a.token)
