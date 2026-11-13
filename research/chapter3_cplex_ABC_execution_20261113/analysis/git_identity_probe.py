"""Single pure process-control probe. Only git show; no scientific imports or calls."""
from pathlib import Path
import hashlib,json,subprocess,sys,time

if len(sys.argv)>1 and sys.argv[1]=='child':
    if sys.stdin.readline().strip()!='PURE_GIT_CONTROL_GO':raise RuntimeError('Missing controlled GO')
    argv=json.loads(sys.argv[2]);start=time.monotonic()
    result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
    print(json.dumps(dict(returncode=result.returncode,stdout_bytes=len(result.stdout),
        stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),stderr=result.stderr.decode('utf-8',errors='replace'),
        elapsed_s=time.monotonic()-start,scope='Pure git identity read, not a scientific retry')))
else:
    root=Path(__file__).resolve().parents[2];out=Path(__file__).parent/'git_probe';out.mkdir()
    sys.path.insert(0,str(root/'work/cplex_ABC_v2'))
    from windows_job import Job
    argv=['git','-C',str(root/'work/publish_repo'),'show',
        '558a7726eedf82c1578bd3700dc81758aab2c4e5:research/chapter3_cplex_ABC_executor_20261113/executor/plan.json']
    job=Job(3221225472+536870912,active_limit=2);p=None;start=time.monotonic()
    try:
        p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'child',json.dumps(argv)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        job.assign(p)
        stdout,stderr=p.communicate(b'PURE_GIT_CONTROL_GO\n',timeout=8)
        (out/'child.stdout.txt').write_bytes(stdout);(out/'child.stderr.txt').write_bytes(stderr)
        until=time.monotonic()+2
        while job.accounting()['active_processes'] and time.monotonic()<until:time.sleep(.02)
        record=dict(pure_control=True,command=argv,child_exit=p.returncode,job_limits=job.limits(),
            job_accounting=job.accounting(),elapsed_s=time.monotonic()-start,
            scientific_calls=0,CPLEX_imported='cplex' in sys.modules)
    finally:
        if p is not None and p.poll() is None:job.terminate();p.wait(timeout=2)
        job.close()
    with (out/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
    print(stdout.decode(errors='replace'))
