"""Exactly 18 new physical replays; all comparison baselines are reused archives."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:
    os.environ[key]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from time import perf_counter
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OLD=ROOT/'research/gpu_idle_dvfs'
CFG=json.loads((HERE/'config.json').read_bytes())
def read(path):return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify_freeze():
    for name,value in read(HERE/'execution_manifest.json').items():assert sha(ROOT/name)==value,name

def execute():
    start=perf_counter();verify_freeze()
    import numpy as np
    from dataclasses import asdict
    from preserve import prepare,plan,certify,save,DEP
    import platform,importlib.metadata
    save(HERE/'environment.json',dict(execution_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=sys.version,platform=platform.platform(),threads=1,
        versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','numba']},manifest_sha256=sha(HERE/'execution_manifest.json')))
    assert CFG['settings']==[s for s in read(OLD/'config.json')['settings'] if s['id']!='ideal']
    results=[];checks=[]
    for load in CFG['loads']:
        t=perf_counter();ev,stages,chains,requests,reference,old_completion,order=prepare(load)
        previous=read(OLD/'raw'/f'{load}_input.json.gz')
        assert stages==previous['stages'] and ev.identity==previous['request_sha']
        assert [asdict(q) for q in requests]==previous['requests'] and [asdict(r) for r in reference]==previous['baseline_rows']
        prepare_s=perf_counter()-t
        checks.append(dict(load=load,requests=500,stages_and_timing='identical_to_archived_Kim',prepare_s=prepare_s))
        for setting in CFG['settings']:
            t=perf_counter();rows,completion,calendar=plan(ev,chains,requests,reference,order,setting,CFG['dwell_ns'])
            assert completion==old_completion
            plan_s=perf_counter()-t
            for ambient in CFG['ambient_c']:
                t=perf_counter();case=f'{load}_{ambient}C';dest=HERE/'raw'/case;dest.mkdir(exist_ok=True)
                proof,times,temperatures=certify(ev,requests,rows,completion,calendar,ambient)
                physics_s=perf_counter()-t;p=proof['physical']
                proof.update(case_id=case,load=load,ambient_c=ambient,deployment=DEP,stages=stages,request_sha=ev.identity,
                             strategy='preserve_kim_busy',setting=setting,planning_s=plan_s,physics_s=physics_s)
                save(dest/(setting['id']+'.json.gz'),proof)
                np.savez_compressed(dest/(setting['id']+'_trace.npz'),time_s=times,temperature_c=temperatures)
                result=dict(case_id=case,setting=setting['id'],strategy='preserve_kim_busy',**p,
                            planning_s=plan_s,physics_s=physics_s,physics_and_archive_s=perf_counter()-t,
                            proof=str((dest/(setting['id']+'.json.gz')).relative_to(HERE)).replace('\\','/'))
                results.append(result)
                print(case,setting['id'],'SAFE' if p['SAFE'] else 'FAIL',round(p['energy_J'],6),
                      round(max(p['peak_upper_c']),6),p['min_slack_ms'],flush=True)
    assert len(results)==18
    save(HERE/'results.json',results);save(HERE/'regression.json',dict(status='PASS',cases=checks,
        all_18_complete_stage_timelines_equal_original_Kim=True))
    save(HERE/'batch_result.json',dict(status='completed',replays=18,elapsed_s=perf_counter()-start,retries=0,new_baseline_replays=0))

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');args=p.parse_args()
    if args.worker:return execute()
    verify_freeze();assert not (HERE/'raw').exists(),'No repeated batch or overwrite'
    assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).strip()
    (HERE/'raw').mkdir();start=perf_counter()
    with (HERE/'console.txt').open('wb') as output:
        child=subprocess.Popen([sys.executable,'-B','-X','utf8',str(HERE/'run_preserve.py'),'--worker'],stdout=output,stderr=output,cwd=ROOT)
        try:child.wait(timeout=CFG['batch_timeout_s']);status='completed' if child.returncode==0 else 'fault'
        except subprocess.TimeoutExpired:child.kill();child.wait();status='timeout'
    receipt=dict(status=status,returncode=child.returncode,total_wall_s=perf_counter()-start,
        files={str(f.relative_to(HERE)).replace('\\','/'):sha(f) for f in sorted((HERE/'raw').rglob('*')) if f.is_file()})
    (HERE/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print(status,receipt['total_wall_s'])
    if child.returncode:raise SystemExit(child.returncode)
if __name__=='__main__':main()
