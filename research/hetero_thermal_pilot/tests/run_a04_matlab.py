"""Run the bounded A04 MATLAB software precheck; no research optimizer."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,time
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',type=Path); ap.add_argument('--matlab',default='F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe'); ap.add_argument('--python',default='F:/Anaconda3/python.exe'); args=ap.parse_args()
    out=(args.output_dir or ROOT/'.runtime_a04'/datetime.now(timezone.utc).strftime('matlab_%Y%m%d_%H%M%S')).resolve()
    if not out.is_relative_to(ROOT): raise SystemExit('Output must remain inside the pilot directory')
    if (out/'execution.json').exists(): raise SystemExit('Do not overwrite an existing execution record')
    out.mkdir(parents=True,exist_ok=True); env=os.environ.copy(); env['MATLAB_PREFDIR']=str(ROOT/'.runtime_matlab_prefs_a04')
    def mp(path):
        text=str(Path(path).resolve()).replace('\\','/')
        if "'" in text: raise ValueError('Unsupported MATLAB path quote')
        return text
    command="addpath('"+mp(ROOT/'matlab')+"'); run_a04_matlab_precheck('"+mp(out)+"','"+mp(args.python)+"');"
    t=time.perf_counter(); started=datetime.now(timezone.utc).isoformat()
    with (out/'console.txt').open('w',encoding='utf-8') as stream:
        try:
            r=subprocess.run([args.matlab,'-batch',command],env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=240)
            code=r.returncode; expired=False
        except subprocess.TimeoutExpired: code=None; expired=True
    files=[*sorted((ROOT/'matlab').glob('*.m')),*sorted((ROOT/'evaluator').glob('*.py')),Path(__file__)]
    record=dict(kind='TEST_ONLY',started_utc=started,elapsed_wall_s=round(time.perf_counter()-t,3),external_timeout_s=240,exit_code=code,timed_out=expired,matlab_batch_command=command,research_optimizer_calls=0,source_hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    (out/'execution.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print((out/'console.txt').read_text(encoding='utf-8')); print('Elapsed including MATLAB startup:',record['elapsed_wall_s'])
    if code!=0 or expired: raise SystemExit(1)
if __name__=='__main__': main()
