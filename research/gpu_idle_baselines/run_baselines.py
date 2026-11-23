"""One frozen batch: 36 new full certificates; Kim/Oracle are archived comparators."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:
    os.environ[key]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from time import perf_counter
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OLD=ROOT/'research/gpu_idle_dvfs';ORACLE=ROOT/'research/gpu_idle_preserve'
CFG=json.loads((HERE/'config.json').read_bytes())
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_freeze():
    for name,h in read(HERE/'execution_manifest.json').items():assert sha(ROOT/name)==h,name

def execute():
    begin=perf_counter();verify_freeze()
    import numpy as np
    from dataclasses import asdict
    import platform,importlib.metadata
    sys.path.insert(0,str(OLD))
    from model import prepare,certify,save,WINDOW,DEP,BASE_OPPS
    from scheduler import Timeline
    from online_events import simulate
    save(HERE/'environment.json',dict(execution_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=sys.version,platform=platform.platform(),threads=1,versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','numba']},
        manifest_sha256=sha(HERE/'execution_manifest.json')))
    assert CFG['settings']==read(ORACLE/'config.json')['settings']
    results=[];input_checks=[]
    for load in CFG['loads']:
        t=perf_counter();ev,stages,chains,requests,reference,old_completion,order=prepare(load)
        inp=read(OLD/'raw'/f'{load}_input.json.gz')
        assert ev.identity==inp['request_sha'] and stages==inp['stages']
        assert [asdict(q) for q in requests]==inp['requests'] and [asdict(r) for r in reference]==inp['baseline_rows']
        meta={q.id:(j,BASE_OPPS[j][1]) for j,scene in enumerate(ev.scenes) for q in scene.requests}
        features={(r.request,r.stage_index):(r.stage,r.resource,r.end_ns-r.start_ns,r.activity_w) for r in reference}
        input_checks.append(dict(load=load,status='PASS',request_sha=ev.identity,prepare_s=perf_counter()-t))
        for setting in CFG['settings']:
            for strategy in CFG['strategies']:
                t=perf_counter()
                rows,completion,timeline,audit=simulate(sys.modules['events'],Timeline,requests,chains,order,meta,WINDOW,
                    strategy,setting,CFG['dwell_ns'],CFG['period_ns'],CFG['service_end_ns'])
                plan_s=perf_counter()-t
                assert {(r.request,r.stage_index):(r.stage,r.resource,r.end_ns-r.start_ns,r.activity_w) for r in rows}==features
                for ambient in CFG['ambient_c']:
                    case=f'{load}_{ambient}C';dest=HERE/'raw'/case;dest.mkdir(exist_ok=True);t=perf_counter()
                    proof,times,temperatures=certify(ev,requests,rows,completion,timeline,ambient)
                    physics_s=perf_counter()-t;p=proof['physical'];name=setting['id']+'_'+strategy
                    proof.update(case_id=case,load=load,ambient_c=ambient,deployment=DEP,stages=stages,request_sha=ev.identity,
                        strategy=strategy,setting=setting,planning_s=plan_s,physics_s=physics_s)
                    save(dest/(name+'.json.gz'),proof);save(dest/(name+'_control.json.gz'),audit)
                    np.savez_compressed(dest/(name+'_trace.npz'),time_s=times,temperature_c=temperatures)
                    result=dict(case_id=case,setting=setting['id'],strategy=strategy,**p,planning_s=plan_s,physics_s=physics_s,
                        physics_and_archive_s=perf_counter()-t,proof=str((dest/(name+'.json.gz')).relative_to(HERE)).replace('\\','/'))
                    results.append(result)
                    print(case,setting['id'],strategy,'SAFE' if p['SAFE'] else 'FAIL',round(p['energy_J'],6),
                          round(max(p['peak_upper_c']),6),p['min_slack_ms'],flush=True)
    assert len(results)==36
    save(HERE/'results.json',results);save(HERE/'input_checks.json',input_checks)
    save(HERE/'batch_result.json',dict(status='completed',new_replays=36,elapsed_s=perf_counter()-begin,new_baseline_replays=0,retries=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');a=parser.parse_args()
    if a.worker:return execute()
    verify_freeze();assert not (HERE/'raw').exists(),'No repeated batch or overwrite'
    assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).strip()
    (HERE/'raw').mkdir();start=perf_counter()
    with (HERE/'console.txt').open('wb') as out:
        proc=subprocess.Popen([sys.executable,'-B','-X','utf8',str(HERE/'run_baselines.py'),'--worker'],stdout=out,stderr=out,cwd=ROOT)
        try:proc.wait(timeout=CFG['batch_timeout_s']);status='completed' if proc.returncode==0 else 'fault'
        except subprocess.TimeoutExpired:proc.kill();proc.wait();status='timeout'
    receipt=dict(status=status,returncode=proc.returncode,total_wall_s=perf_counter()-start,
        files={f.relative_to(HERE).as_posix():sha(f) for f in sorted((HERE/'raw').rglob('*')) if f.is_file()})
    (HERE/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print(status,receipt['total_wall_s'])
    if proc.returncode:raise SystemExit(proc.returncode)
if __name__=='__main__':main()
