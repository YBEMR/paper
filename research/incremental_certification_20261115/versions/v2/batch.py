"""Serial fresh-process replay; fixed order, fail closed, no automatic retry."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
from replay import REL

def main(cache,out,stage):
    here=Path(__file__).resolve().parent;calls=sorted(p.name for p in (cache/REL/'execution/calls').iterdir() if (p/'method/result.json').exists())
    if stage=='formal':
        assert json.loads((out.parent/'pilot/analysis.json').read_text())['B_gate_pass'],'B_GATE_NOT_PASSED'
        assert json.loads((here/'tests_v2/prefix_correctness_final.json').read_text())['status']=='PASS','C_CORRECTNESS_NOT_PASSED'
        assert json.loads((here/'tests_v2/root_stop_final.json').read_text())['status']=='PASS','ROOT_STOP_NOT_PASSED'
    assert len(calls)==16
    selected=[calls[i] for i in [0,4,8,12]] if stage=='pilot' else calls
    orders=['AB','BA','AB','BA'] if stage=='pilot' else ['ABC','BCA','CAB','ACB','CBA','BAC']
    out.mkdir(parents=True,exist_ok=False)
    manifest={'stage':stage,'created_local':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'root_seconds':300,'supervisor_seconds':330,
      'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in here.iterdir() if p.suffix in ['.py','.md','.json']},'runs':[]}
    for i,call in enumerate(selected):
        data=json.loads((cache/REL/'execution/calls'/call/'method/result.json').read_text(encoding='utf-8'))
        rows=[e for e in data['evaluations'] if not e.get('cache_hit',False)]
        manifest['runs'].append({'call':call,'order':orders[i%len(orders)],'candidate_order':[e['candidate_sha256'] for e in rows],
            'historical_states':[e['receipt']['state'] for e in rows],
            'archive_sha256':hashlib.sha256((cache/REL/'execution/calls'/call/'method/result.json').read_bytes()).hexdigest()})
    (out/'freeze.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    with (out/'events.jsonl').open('w',encoding='utf-8') as log:
        def event(x):log.write(json.dumps(x)+'\n');log.flush();print(json.dumps(x),flush=True)
        for run in manifest['runs']:
            for arm in run['order']:
                target=out/f"{run['call']}__{arm}";started=time.perf_counter()
                event({'event':'START','call':run['call'],'arm':arm,'time':time.strftime('%Y-%m-%dT%H:%M:%S%z')})
                with (out/f"{run['call']}__{arm}.log").open('w',encoding='utf-8') as stdout:
                    proc=subprocess.Popen([sys.executable,'-X','utf8',str(here/'replay.py'),'--cache',str(cache),'--call',run['call'],'--arm',arm,'--out',str(target)],stdout=stdout,stderr=subprocess.STDOUT)
                    try:code=proc.wait(timeout=330)
                    except subprocess.TimeoutExpired:
                        proc.kill();proc.wait();event({'event':'SUPERVISOR_TIMEOUT','call':run['call'],'arm':arm,'wall_s':time.perf_counter()-started});raise SystemExit(3)
                event({'event':'RETURN','call':run['call'],'arm':arm,'exit_code':code,'process_wall_s':time.perf_counter()-started})
                if code:raise SystemExit(code)
        event({'event':'BATCH_COMPLETE','stage':stage})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--stage',choices=['pilot','formal'],required=True)
    a=p.parse_args();main(a.cache.resolve(),a.out.resolve(),a.stage)
