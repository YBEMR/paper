"""One newly approved frozen D285 batch. Host bookkeeping only; no retry."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,time
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
def save(name,value):
    with (out/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
command=[sys.executable,'-B',str(root/'work/cplex_ABC_v3/batch.py'),'--workspace',str(root),
    '--plan',str(root/'work/cplex_ABC_v3/plan.json'),'--expected-sha','ff129eb1f340ad067b891542b486ec9c5f0da19c046371eacd167cb9bc75bbd5',
    '--approval',str(out/'approval.json')]
if (root/'work/cplex_ABC_execution_v2').exists():raise RuntimeError('One-use batch output already exists; no retry')
start=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
save('host_launch.json',dict(command=command,host_pid=os.getpid(),start_monotonic=start,started_at_utc=utc,maximum_batch_launches=1))
with (out/'batch.stdout.txt').open('xb') as stdout,(out/'batch.stderr.txt').open('xb') as stderr:
    p=subprocess.Popen(command,cwd=root,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    save('batch_process.json',dict(pid=p.pid,launched_elapsed_s=time.monotonic()-start));code=p.wait()
save('host_receipt.json',dict(exit_code=code,host_wall_s=time.monotonic()-start,started_at_utc=utc,
    ended_at_utc=datetime.now(timezone.utc).isoformat(),launch_count=1,retries=0,
    scope='Host wall accounting only; frozen per-arm receipts determine scientific credit'))
print(json.dumps(dict(exit_code=code,host_wall_s=time.monotonic()-start,output=str(root/'work/cplex_ABC_execution_v2'))))
raise SystemExit(code)
