"""Shared wall-clock budget and immutable execution receipt."""
from pathlib import Path
import datetime,hashlib,json,platform,subprocess,sys,time

ROOT=Path(__file__).resolve().parent

def main():
    before=time.perf_counter()
    prior=0.6928471  # observed stage-1 process/tool wall time, conservative vs arithmetic time
    receipt=dict(start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 prior_stage1_charged_s=prior,total_budget_s=600,commands=[],status='RUNNING',
                 python=sys.version,platform=platform.platform(),
                 code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')})
    dest=ROOT/'run01'
    assert not dest.exists(), 'Never overwrite an earlier run'
    receipt_path=ROOT/'execution_receipt.json'
    assert not receipt_path.exists(), 'Never overwrite an earlier receipt'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    for name in ['experiment.py','verify.py','analyze.py']:
        remaining=600-prior-(time.perf_counter()-before)
        if remaining<=0:receipt['status']='BUDGET_EXHAUSTED';break
        command=[sys.executable,str(ROOT/name),str(dest)]
        log=ROOT/(name.removesuffix('.py')+'_run.log')
        start=time.perf_counter()
        item=dict(command=command,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),remaining_budget_s=remaining)
        with log.open('w',encoding='utf-8') as stream:
            process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
            item['pid']=process.pid
            try:
                code=process.wait(timeout=remaining)
                item['exit_code']=code
            except subprocess.TimeoutExpired:
                print('Scientific wall budget exhausted; stopping current child.',flush=True)
                process.kill();process.wait();item['exit_code']=process.returncode;item['timeout']=True
                receipt['status']='BUDGET_EXHAUSTED'
        item['wall_s']=time.perf_counter()-start;receipt['commands'].append(item)
        receipt['elapsed_scientific_wall_s']=prior+time.perf_counter()-before
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'step':name,**item}),flush=True)
        if item['exit_code']!=0:
            if receipt['status']=='RUNNING':receipt['status']='FAILED'
            break
    else:receipt['status']='COMPLETED'
    receipt['end_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt['elapsed_scientific_wall_s']=prior+time.perf_counter()-before
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2),flush=True)
    return 0 if receipt['status']=='COMPLETED' else 1

if __name__=='__main__':
    sys.exit(main())
