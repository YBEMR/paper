"""Counterfactual pure Git read under unchanged two-process Job. Never launches science."""
from pathlib import Path
import hashlib,json,subprocess,sys,time
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent/'git_direct_probe';out.mkdir()
sys.path.insert(0,str(root/'work/cplex_ABC_v2'))
from windows_job import Job
git=Path('F:/Git/Git/mingw64/bin/git.exe')
argv=[str(git),'-C',str(root/'work/publish_repo'),'show',
    '558a7726eedf82c1578bd3700dc81758aab2c4e5:research/chapter3_cplex_ABC_executor_20261113/executor/plan.json']
job=Job(3221225472+536870912,active_limit=2);p=None;start=time.monotonic()
try:
    p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).parent/'git_identity_probe.py'),'child',json.dumps(argv)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    job.assign(p);stdout,stderr=p.communicate(b'PURE_GIT_CONTROL_GO\n',timeout=8)
    (out/'child.stdout.txt').write_bytes(stdout);(out/'child.stderr.txt').write_bytes(stderr)
    until=time.monotonic()+2
    while job.accounting()['active_processes'] and time.monotonic()<until:time.sleep(.02)
    record=dict(pure_control=True,command=argv,child_exit=p.returncode,job_limits=job.limits(),
        job_accounting=job.accounting(),elapsed_s=time.monotonic()-start,scientific_calls=0,CPLEX_imported='cplex' in sys.modules,
        executable_sha256=hashlib.sha256(git.read_bytes()).hexdigest(),
        expected_stdout_sha256='bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6',
        scope='Only an isolated git show; frozen executor and scientific run are unchanged and not restarted')
finally:
    if p is not None and p.poll() is None:job.terminate();p.wait(timeout=2)
    job.close()
with (out/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
print(stdout.decode(errors='replace'))
