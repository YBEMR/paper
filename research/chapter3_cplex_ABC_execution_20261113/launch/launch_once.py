"""Single authorized frozen D284 batch launch; host accounting only."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,time
root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
def save(name,value):
    with (out/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
command=[r'F:/Anaconda3/python.exe','-B',str(root/'work/cplex_ABC_v2/batch.py'),'--workspace',str(root),
    '--plan',str(root/'work/cplex_ABC_v2/plan.json'),'--expected-sha','bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6',
    '--approval',str(out/'approval.json')]
if (root/'work/cplex_ABC_execution_v1').exists():raise RuntimeError('One-use scientific directory already exists; no retry')
start=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
save('host_launch.json',dict(command=command,host_pid=os.getpid(),start_monotonic=start,started_at_utc=utc,maximum_batch_launches=1))
with (out/'batch.stdout.txt').open('xb') as so,(out/'batch.stderr.txt').open('xb') as se:
    p=subprocess.Popen(command,cwd=root,stdout=so,stderr=se,creationflags=subprocess.CREATE_NO_WINDOW)
    save('batch_process.json',dict(pid=p.pid,launched_elapsed_s=time.monotonic()-start))
    code=p.wait()
save('host_receipt.json',dict(exit_code=code,host_wall_s=time.monotonic()-start,started_at_utc=utc,
    ended_at_utc=datetime.now(timezone.utc).isoformat(),launch_count=1,retries=0,
    scope='Host wall and launch bookkeeping; scientific credit governed exclusively by frozen per-arm receipts'))
print(json.dumps(dict(exit_code=code,host_wall_s=time.monotonic()-start,output=str(root/'work/cplex_ABC_execution_v1'))))
sys.exit(code)

