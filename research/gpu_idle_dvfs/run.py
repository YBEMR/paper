"""One frozen deterministic batch, 78 full replays, no automatic retries."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:
    os.environ[key]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/'config.json').read_bytes())
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_freeze():
    for name,value in read(HERE/'execution_manifest.json').items():assert hashfile(ROOT/name)==value,name

def execute():
    began=perf_counter();verify_freeze()
    import numpy as np
    from dataclasses import asdict
    from model import prepare,build_policy,certify,save,WINDOW,DEP
    from scheduler import Timeline,dispatch
    import platform,importlib.metadata
    env=dict(execution_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             python=sys.version,platform=platform.platform(),
             versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','numba','psutil']},
             frozen_manifest_sha256=hashfile(HERE/'execution_manifest.json'),threads=1)
    save(HERE/'environment.json',env)
    results=[];regression=[]
    for load in CFG['loads']:
        begin=perf_counter()
        ev,stages,chains,requests,reference,original_completion,order=prepare(load)
        events=sys.modules['events']
        high=Timeline(WINDOW);high.changes=[(0,'H')]
        highrows,highcompletion,_=dispatch(events,requests,chains,order,WINDOW,calendar=high)
        assert len(requests)==500
        save(HERE/'raw'/f'{load}_input.json.gz',dict(stages=stages,request_sha=ev.identity,
            requests=[asdict(q) for q in requests],baseline_rows=[asdict(r) for r in reference],
            high_rows=[asdict(r) for r in highrows],gpu_order=order,prepare_s=perf_counter()-begin))
        for setting in CFG['settings']:
            strategies=CFG['strategies']+(['ideal_fixed_busy'] if setting['id']=='ideal' else [])
            for strategy in strategies:
                plan_start=perf_counter()
                rows,completion,timeline=build_policy(ev,chains,requests,order,strategy,setting,reference,highrows)
                plan_s=perf_counter()-plan_start
                if strategy=='ideal_fixed_busy' or (strategy=='kim' and setting['id']=='ideal'):
                    assert rows==reference and completion==original_completion
                for ambient in CFG['ambient_c']:
                    t=perf_counter();case=f'{load}_{ambient}C'
                    dest=HERE/'raw'/case;dest.mkdir(exist_ok=True)
                    proof,times,temps=certify(ev,requests,rows,completion,timeline,ambient)
                    physics_s=perf_counter()-t
                    p=proof['physical'];old=read(ROOT/'research/kim_gap_diagnostics/inputs'/f'{case}_kim.json.gz')['physical']
                    if strategy=='kim' and setting['id']=='ideal':
                        energy_error=abs(p['energy_J']-old['energy_j'])
                        peak_error=float(np.max(np.abs(np.array(p['peak_upper_c'])-old['peak_upper_c'])))
                        final_error=float(np.max(np.abs(np.array(p['final_c'])-old['final_c'])))
                        assert energy_error<=1e-7 and peak_error<=1e-6 and final_error<=1e-7
                        assert p['min_slack_ms']==old['min_slack_ms'] and p['SAFE']
                        regression.append(dict(case_id=case,status='PASS',energy_error_j=energy_error,
                                               peak_error_c=peak_error,final_error_c=final_error))
                    name=f"{setting['id']}_{strategy}"
                    proof.update(case_id=case,load=load,ambient_c=ambient,strategy=strategy,setting=setting,
                                 deployment=DEP,stages=stages,request_sha=ev.identity,planning_s=plan_s,physics_s=physics_s)
                    save(dest/(name+'.json.gz'),proof)
                    np.savez_compressed(dest/(name+'_trace.npz'),time_s=times,temperature_c=temps)
                    result=dict(case_id=case,setting=setting['id'],strategy=strategy,
                        latency_us=setting['latency_ns']/1000,switch_microjoules=setting['energy_j']*1e6,
                        **p,planning_s=plan_s,physics_s=physics_s,physics_and_archive_s=perf_counter()-t,
                        proof=str((dest/(name+'.json.gz')).relative_to(HERE)).replace('\\','/'))
                    results.append(result)
                    print(case,setting['id'],strategy,'SAFE' if p['SAFE'] else p['thermal_status']+' / deadline='+str(p['deadline_ok']),
                          round(p['energy_J'],6),round(max(p['peak_upper_c']),4),round(p['min_slack_ms'],6),flush=True)
    assert len(results)==CFG['expected_physical_runs'] and len(regression)==6
    save(HERE/'results.json',results);save(HERE/'regression.json',dict(status='PASS',cases=regression))
    save(HERE/'batch_result.json',dict(status='completed',replays=len(results),elapsed_s=perf_counter()-began,
        regression_count=len(regression),new_search_calls=0,retries=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    if args.worker:return execute()
    verify_freeze()
    assert not (HERE/'raw').exists(),'No overwrite or repeated batch'
    assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).strip()
    (HERE/'raw').mkdir()
    start=perf_counter()
    with (HERE/'console.txt').open('w',encoding='utf-8',newline='\n') as out:
        p=subprocess.Popen([sys.executable,'-B','-X','utf8',str(HERE/'run.py'),'--worker'],stdout=out,stderr=out,cwd=ROOT)
        try:p.wait(timeout=CFG['batch_timeout_s']);status='completed' if p.returncode==0 else 'fault'
        except subprocess.TimeoutExpired:p.kill();p.wait();status='timeout'
    receipt=dict(status=status,returncode=p.returncode,total_wall_s=perf_counter()-start,
        files={str(f.relative_to(HERE)).replace('\\','/'):hashfile(f) for f in sorted((HERE/'raw').rglob('*')) if f.is_file()})
    (HERE/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print(status,'wall',receipt['total_wall_s'])
    if p.returncode:raise SystemExit(p.returncode)

if __name__=='__main__':main()
