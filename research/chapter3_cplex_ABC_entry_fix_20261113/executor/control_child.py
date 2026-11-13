"""Tiny process-control fixture; no model, CPLEX import or evaluator."""
import json,os,sys,time
from pathlib import Path
from core import save
mode=sys.argv[1]
if not sys.stdin.readline().startswith('D283_GO '):raise RuntimeError('No protected GO')
if mode=='normal':print('ARTIFICIAL ordinary child',flush=True)
elif mode=='timeout':
    print('ARTIFICIAL waiting child',flush=True);time.sleep(4)
elif mode=='memory':
    blocks=[]
    try:
        while True:blocks.append(bytearray(8*1024*1024))
    except MemoryError as e:
        blocks.clear()
        os.write(2,b'ARTIFICIAL original MemoryError at hard Job limit\n')
        save(Path.cwd()/'memory_exception.json',dict(type=type(e).__name__,message=str(e),scope='synthetic Python memory control, not CPLEX'))
elif mode=='child_blocked':
    import subprocess
    try:
        p=subprocess.run([sys.executable,'-c','print("should not be admitted")'],capture_output=True,timeout=2)
        save(Path.cwd()/'spawn_result.json',dict(returncode=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode()))
        if p.returncode==0:raise RuntimeError('Second process unexpectedly admitted')
    except OSError as e:save(Path.cwd()/'spawn_result.json',dict(type=type(e).__name__,message=str(e)))
elif mode=='response':
    save(Path.cwd()/'native_response.json',dict(plan_sha256='control-plan',vector=None,scope='ARTIFICIAL no candidate'))
    stop=time.monotonic()+2
    while not (Path.cwd()/'response_ack.json').exists() and time.monotonic()<stop:time.sleep(.01)
    acknowledgment=json.loads((Path.cwd()/'response_ack.json').read_text())
    save(Path.cwd()/'child_ack_seen.json',acknowledgment)
else:raise ValueError(mode)
