"""One predeclared serial batch: four roots, three arms, no retries."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from support import HERE,INPUTS,read,save,sha,paths,verify_sources

ORDER=[(case,arm) for case,arms in [('U07__n24','ABC'),('U08__n24','BCA'),('U09__n24','CAB'),('U10__n24','ACB')] for arm in arms]
def prepare(out):
    paths();from runtime import digest
    assert not out.exists();verify_sources()
    checks=read(HERE/'tests/interface.json');assert checks['status']=='PASS'
    code={p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.glob('*.py'))}
    code.update({p.relative_to(HERE).as_posix():sha(p) for p in sorted((HERE/'reuse').glob('*')) if p.is_file()})
    inputs={case:{name:digest(read(HERE/'frozen'/INPUTS/case/(name+'.json'))) for name in ['instance','config']} for case,_ in ORDER}
    out.mkdir(parents=True)
    freeze={'protocol':'SIC20261115-fixed-ONP-ABC-4x300-v1','created_local':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
      'slots':[{'id':f'{i:02d}_{case}_{arm}','case':case,'arm':arm} for i,(case,arm) in enumerate(ORDER,1)],
      'root_seconds':300,'initialization_admission_seconds':180,'supervisor_seconds':330,
      'code_sha256':code,'inputs':inputs,'sources_manifest_sha256':sha(HERE/'sources.json'),
      'interface_checks_sha256':sha(HERE/'tests/interface.json'),'protocol_sha256':sha(HERE/'PROTOCOL.md'),
      'thread_environment':{k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},
      'scope':'User authorized exactly 12 fresh ON-P calls; no MILP, new cases, retries or post-root numerical reevaluation.'}
    save(out/'freeze.json',freeze);print(json.dumps({'prepared':True,'slots':12,'freeze_sha256':sha(out/'freeze.json')}))
def batch(out):
    plan=read(out/'freeze.json');assert [(s['case'],s['arm']) for s in plan['slots']]==ORDER
    for name,h in plan['code_sha256'].items():assert sha(HERE/name)==h,name
    assert sha(HERE/'sources.json')==plan['sources_manifest_sha256'] and sha(HERE/'tests/interface.json')==plan['interface_checks_sha256']
    assert sha(HERE/'PROTOCOL.md')==plan['protocol_sha256'];verify_sources()
    env=dict(os.environ,**plan['thread_environment'],PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    seen={};stop=None;returns=[]
    with (out/'events.jsonl').open('x',encoding='utf-8') as stream:
        def event(x):stream.write(json.dumps(x)+'\n');stream.flush();print(json.dumps(x),flush=True)
        for slot in plan['slots']:
            if stop:event({'event':'NOT_STARTED','slot':slot,'reason':stop});continue
            target=out/slot['id'];event({'event':'START','slot':slot,'time':time.strftime('%Y-%m-%dT%H:%M:%S%z')});start=time.perf_counter()
            argv=[sys.executable,'-B','-X','utf8',str(HERE/'worker.py'),'--case',slot['case'],'--arm',slot['arm'],'--out',str(target),'--freeze',str(out/'freeze.json')]
            with (out/(slot['id']+'.log')).open('x',encoding='utf-8') as log:
                proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env)
                try:code=proc.wait(timeout=330)
                except subprocess.TimeoutExpired:
                    event({'event':'SUPERVISOR_LIMIT_STOPPING','slot':slot,'seconds':330});proc.kill();proc.wait();code=-1
            record={'event':'RETURN','slot':slot,'exit_code':code,'process_wall_s':time.perf_counter()-start};event(record);returns.append(record)
            if code:stop=slot['id']+':PROCESS_FAILURE';continue
            result=read(target/'summary.json')
            if not result['normal_stop'] or not result['root_unchanged']:stop=slot['id']+':NONNORMAL';continue
            for row in read(target/'numerical_calls.json'):
                if row['state']!='SAFE':continue
                key=(slot['case'],row['candidate_sha256']);old=seen.get(key)
                if old and old!=row['semantic_sha256']:stop=slot['id']+':COMMON_CANDIDATE_DIFFERENCE';break
                seen[key]=row['semantic_sha256']
        event({'event':'BATCH_COMPLETE' if stop is None else 'BATCH_STOPPED','stop_reason':stop,'returned':len(returns)})
    save(out/'batch_summary.json',{'stop_reason':stop,'returns':returns,'retry_count':0,'all_12_returned':len(returns)==12})
    if stop:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    (prepare if a.action=='prepare' else batch)(a.out.resolve())
