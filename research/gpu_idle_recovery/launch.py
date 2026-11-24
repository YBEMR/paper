"""Four independent processes, each killed at 120 s without retry."""
from pathlib import Path
import os,json,subprocess,sys,time,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
cfg=json.loads((HERE/'config.json').read_bytes())
spent=0.
if '--resume-import-fault' in sys.argv:
    src=(HERE/'raw'/cfg['cases'][0]).resolve();dst=(HERE/'startup_fault').resolve()
    assert src.is_relative_to(HERE.resolve()) and dst.is_relative_to(HERE.resolve()) and not dst.exists()
    receipt=json.loads((src/'receipt.json').read_bytes())
    assert receipt['returncode']==1 and receipt['wall_s']<5 and len(list((HERE/'raw').iterdir()))==1
    assert 'ImportError' in (src/'console.txt').read_text() and not list(src.glob('*.gz'))
    spent=receipt['wall_s'];src.rename(dst)
    (HERE/'environment.json').rename(HERE/'startup_environment.json')
else:assert not (HERE/'raw').exists(),'No overwrite/repeated batch'
assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT).strip()
(HERE/'raw').mkdir(exist_ok=True)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMBA_NUM_THREADS='1')
environment=dict(execution_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),python=sys.version,threads=1)
(HERE/'environment.json').write_bytes((json.dumps(environment,indent=2)+'\n').encode())
for case in cfg['cases']:
    out=HERE/'raw'/case;out.mkdir();prior=spent if case==cfg['cases'][0] else 0.
    start=time.perf_counter()-prior;env['RECOVERY_START']=str(start)
    with (out/'console.txt').open('wb') as log:
        proc=subprocess.Popen([sys.executable,'-B','-X','utf8',str(HERE/'worker.py'),case],cwd=ROOT,env=env,stdout=log,stderr=log)
        hard=False
        try:proc.wait(timeout=max(.001,cfg['budget_s']-(time.perf_counter()-start)))
        except subprocess.TimeoutExpired:hard=True;proc.kill();proc.wait()
    receipt=dict(case=case,wall_s=time.perf_counter()-start,prior_failed_initialization_s=prior,returncode=proc.returncode,hard_timeout=hard,
        files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.is_file()})
    (out/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print(case,receipt['wall_s'],proc.returncode,hard,flush=True)
    if proc.returncode and not hard:raise SystemExit(proc.returncode)
