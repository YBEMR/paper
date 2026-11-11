"""One frozen test batch, 240 seconds total; no retry/full-R1 or solver entry."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
now=lambda:datetime.now(timezone.utc).isoformat()
start=time.monotonic();started=now();records=[]
commands=[['python3','-B','research/chapter3_experiments/test_joint_state_support.py','run','--output',str((HERE/'execution').relative_to(REPO))],
          ['python3','-B','research/chapter3_experiments/test_option_support_structural.py','--output',str((HERE/'old_structural_regression').relative_to(REPO))]]
with (HERE/'launch_claim.json').open('x') as f:json.dump(dict(started_utc=started,total_budget_s=240,commands=commands),f,indent=2)
success=True
for ordinal,command in enumerate(commands):
    t=time.monotonic();at=now();remaining=240-(t-start)
    with (HERE/f'command_{ordinal}.stdout.log').open('xb') as out,(HERE/f'command_{ordinal}.stderr.log').open('xb') as err:
        p=subprocess.Popen(command,cwd=REPO,stdout=out,stderr=err)
        try:rc=p.wait(timeout=max(0,remaining));expired=False
        except subprocess.TimeoutExpired:p.kill();rc=p.wait();expired=True
    records.append(dict(argv=command,started_utc=at,ended_utc=now(),wall_s=time.monotonic()-t,returncode=rc,watchdog_expired=expired))
    if rc or expired:success=False;break
with (HERE/'command_receipts.json').open('x') as f:json.dump(dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-start,records=records,passed=success),f,indent=2)
print(json.dumps(records,indent=2))
raise SystemExit(0 if success else 1)
