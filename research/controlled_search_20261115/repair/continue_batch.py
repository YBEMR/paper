"""User-authorized remaining eleven slots; never rerun the completed A root."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from support import read,save,sha,verify_sources

def prepare():
    old=read(root/'execution/freeze.json');status=read(root/'execution/batch_summary.json')
    assert len(status['returns'])==1 and status['returns'][0]['slot']['id']=='01_U07__n24_A'
    assert status['returns'][0]['exit_code']==1 and status['stop_reason']=='01_U07__n24_A:PROCESS_FAILURE'
    evidence=read(root/'repair/recovered_A_evidence.json');assert evidence['final_SAFE_contract_valid']
    fix=read(root/'repair/memory_probe.json');assert fix['status']=='PASS'
    assert sha(root/'versions/v1/support.py')==old['code_sha256']['support.py']==fix['original_sha256']
    assert sha(root/'support.py')==fix['corrected_sha256']
    for name,h in old['code_sha256'].items():
        if name!='support.py':assert sha(root/name)==h,name
    verify_sources();folder=root/'continuation';folder.mkdir(exist_ok=False)
    plan=dict(old);plan.update(created_local=time.strftime('%Y-%m-%dT%H:%M:%S%z'),slots=old['slots'][1:],
      code_sha256={name:sha(root/name) for name in old['code_sha256']},
      prior_freeze_sha256=sha(root/'execution/freeze.json'),recovered_A_sha256=sha(root/'repair/recovered_A_evidence.json'),
      continuation_launcher_sha256=sha(Path(__file__)),memory_fix_sha256=sha(root/'repair/memory_signature.patch'),
      authorization='User explicitly selected: 修复后继续剩余11槽（推荐）. Keep original A and missing telemetry; no rerun or expansion.',
      scope='Only the eleven original NOT_STARTED slots; unchanged 300-second roots/180-second I1 admission.')
    save(folder/'freeze.json',plan);print(json.dumps({'prepared_remaining':11,'freeze_sha256':sha(folder/'freeze.json')}))
def run():
    folder=root/'continuation';plan=read(folder/'freeze.json');old=read(root/'execution/freeze.json')
    assert plan['slots']==old['slots'][1:] and len(plan['slots'])==11
    assert sha(Path(__file__))==plan['continuation_launcher_sha256']
    for name,h in plan['code_sha256'].items():assert sha(root/name)==h,name
    verify_sources();seen={}
    for row in read(root/'repair/recovered_A_numerical_calls.json'):
        if row['state']=='SAFE':seen[('U07__n24',row['candidate_sha256'])]=row['semantic_sha256']
    env=dict(os.environ,**plan['thread_environment'],PYTHONUTF8='1',PYTHONIOENCODING='utf-8');stop=None;returns=[]
    with (folder/'events.jsonl').open('x',encoding='utf-8') as stream:
        def event(x):stream.write(json.dumps(x)+'\n');stream.flush();print(json.dumps(x),flush=True)
        for slot in plan['slots']:
            if stop:event({'event':'NOT_STARTED','slot':slot,'reason':stop});continue
            for name,h in plan['code_sha256'].items():assert sha(root/name)==h,name
            target=folder/slot['id'];event({'event':'START','slot':slot,'time':time.strftime('%Y-%m-%dT%H:%M:%S%z')});started=time.perf_counter()
            argv=[sys.executable,'-B','-X','utf8',str(root/'worker.py'),'--case',slot['case'],'--arm',slot['arm'],'--out',str(target),'--freeze',str(folder/'freeze.json')]
            with (folder/(slot['id']+'.log')).open('x',encoding='utf-8') as log:
                p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env)
                try:code=p.wait(timeout=330)
                except subprocess.TimeoutExpired:
                    event({'event':'SUPERVISOR_LIMIT_STOPPING','slot':slot,'seconds':330});p.kill();p.wait();code=-1
            record={'event':'RETURN','slot':slot,'exit_code':code,'process_wall_s':time.perf_counter()-started};event(record);returns.append(record)
            if code:stop=slot['id']+':PROCESS_FAILURE';continue
            s=read(target/'summary.json')
            if not s['normal_stop'] or not s['root_unchanged']:stop=slot['id']+':NONNORMAL';continue
            for row in read(target/'numerical_calls.json'):
                if row['state']!='SAFE':continue
                key=(slot['case'],row['candidate_sha256']);previous=seen.get(key)
                if previous and previous!=row['semantic_sha256']:stop=slot['id']+':COMMON_CANDIDATE_DIFFERENCE';break
                seen[key]=row['semantic_sha256']
        event({'event':'BATCH_COMPLETE' if not stop else 'BATCH_STOPPED','stop_reason':stop,'returned':len(returns)})
    save(folder/'batch_summary.json',{'stop_reason':stop,'returns':returns,'retry_count':0,'all_11_returned':len(returns)==11,
      'prior_search_calls':1,'total_search_calls':1+len(returns)})
    if stop:raise SystemExit(2)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);a=p.parse_args();(prepare if a.action=='prepare' else run)()
