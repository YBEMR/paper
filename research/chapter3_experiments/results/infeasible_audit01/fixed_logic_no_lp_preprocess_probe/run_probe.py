"""Single-use fixed-logic feasibility diagnostic; no scheduling search or thermal evaluation."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ORIGINAL = REPO / 'research/chapter3_experiments/results/formal_comparison02/response_R__R2__milp/matlab'
MATLAB = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe')

def dump(path, value):
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    begin=time.monotonic(); deadline=begin+120
    wall_deadline=time.time()+120
    with (HERE/'single_use_claim.json').open('x',encoding='utf-8') as stream:
        json.dump({'pid':os.getpid(),'started_unix':time.time(),'budget_seconds':120},stream)
    declared=json.loads((HERE/'predeclaration.json').read_text(encoding='utf-8'))
    actual={name:sha(ORIGINAL/name) for name in declared['original_sha256']}
    if actual!=declared['original_sha256']:
        raise RuntimeError('Original input hash mismatch; no native call')
    prior=Path(declared['prior_fixed_logic_probe'])
    prior_actual={name:sha(prior/name) for name in declared['prior_artifact_sha256']}
    if prior_actual!=declared['prior_artifact_sha256']:
        raise RuntimeError('Prior fixed-logic artifact hash mismatch; no native call')
    env=os.environ.copy()
    prefs=REPO/'.runtime/matlab_prefs'
    prefs.mkdir(exist_ok=True,parents=True)
    env['MATLAB_PREFDIR']=str(prefs)
    env['MATLAB_LOG_DIR']=str(HERE)
    folder=str(HERE).replace('\\','/').replace("'","''")
    original=str(ORIGINAL).replace('\\','/').replace("'","''")
    active=str(REPO/'research/chapter3_experiments').replace('\\','/').replace("'","''")
    command=f"addpath('{active}');addpath('{folder}');run_fixed_logic_no_lp_probe('{folder}','{original}',{wall_deadline:.6f})"
    result={'budget_seconds':120,'formal_experiment':False,'retry_performed':False,
            'original_sha256_before':actual,'matlab_prefdir':str(prefs)}
    with (HERE/'matlab_stdout.log').open('wb') as stdout, (HERE/'matlab_stderr.log').open('wb') as stderr:
        process=subprocess.Popen([str(MATLAB),'-nosplash','-nodesktop','-batch',command],
            cwd=REPO,env=env,stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result['process_pid']=process.pid
        try:
            result['process_exit_code']=process.wait(timeout=max(0,deadline-time.monotonic()))
            result['outer_deadline_expired']=False
        except subprocess.TimeoutExpired:
            result['outer_deadline_expired']=True
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=10)
            result['process_exit_code']=process.poll()
    result['outer_wall_seconds']=time.monotonic()-begin
    result['result_visible_at_return']=(HERE/'result.json').is_file()
    result['result_formed_before_deadline']=result['result_visible_at_return'] and time.monotonic()<=deadline
    # Hash recheck and metadata serialization are post-diagnostic audit only.
    result['original_sha256_after']={name:sha(ORIGINAL/name) for name in declared['original_sha256']}
    result['original_files_unchanged']=result['original_sha256_after']==actual
    dump(HERE/'driver_result.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    main()
