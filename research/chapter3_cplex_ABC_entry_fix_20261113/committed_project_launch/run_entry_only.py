"""Host wall recording for committed-project control-only entry. Not scientific authority."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys,time
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
command=[sys.executable,'-B',str(root/'work/cplex_ABC_v3/batch.py'),'--workspace',str(root),
    '--plan',str(root/'work/cplex_ABC_v3/plan.json'),'--expected-sha','ff129eb1f340ad067b891542b486ec9c5f0da19c046371eacd167cb9bc75bbd5',
    '--approval',str(out/'control_approval.json'),'--entry-only','--control-output',str(root/'work/cplex_ABC_entry_project_v1')]
assert not (root/'work/cplex_ABC_entry_project_v1').exists()
start=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
    p=subprocess.run(command,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
receipt=dict(command=command,exit_code=p.returncode,host_wall_s=time.monotonic()-start,started_at_utc=utc,
    ended_at_utc=datetime.now(timezone.utc).isoformat(),scientific_workers=0,solver_calls=0,
    production_output_absent=not (root/'work/cplex_ABC_execution_v2').exists())
with (out/'host_receipt.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt));raise SystemExit(p.returncode)
