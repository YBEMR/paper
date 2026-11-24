"""Four independent processes, each killed at 120 s without retry."""
from pathlib import Path
import os,json,subprocess,sys,time,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
cfg=json.loads((HERE/'config.json').read_bytes())
assert not (HERE/'raw').exists(),'No overwrite/repeated batch'
assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT).strip()
(HERE/'raw').mkdir()
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMBA_NUM_THREADS='1')
environment=dict(execution_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),python=sys.version,threads=1)
(HERE/'environment.json').write_bytes((json.dumps(environment,indent=2)+'\n').encode())
for case in cfg['cases']:
    out=HERE/'raw'/case;out.mkdir();start=time.perf_counter();env['RECOVERY_START']=str(start)
    with (out/'console.txt').open('wb') as log:
        proc=subprocess.Popen([sys.executable,'-B','-X','utf8',str(HERE/'worker.py'),case],cwd=ROOT,env=env,stdout=log,stderr=log)
        hard=False
        try:proc.wait(timeout=max(.001,cfg['budget_s']-(time.perf_counter()-start)))
        except subprocess.TimeoutExpired:hard=True;proc.kill();proc.wait()
    receipt=dict(case=case,wall_s=time.perf_counter()-start,returncode=proc.returncode,hard_timeout=hard,
        files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.is_file()})
    (out/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print(case,receipt['wall_s'],proc.returncode,hard,flush=True)
    if proc.returncode and not hard:raise SystemExit(proc.returncode)
