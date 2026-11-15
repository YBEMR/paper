"""Post-run read-only evidence/source audit; no numerical evaluator imports."""
import hashlib,json,shutil,sys
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def digest(x):return sha(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main(root,cache):
    source=read(root/'source_manifest.json');verified=[];copies=[]
    for row in source['sources']:
        data=(cache/row['path']).read_bytes();git=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        assert len(data)==row['bytes'] and sha(data)==row['sha256'] and git==row['git_blob'],row['path']
        verified.append(row['path'])
        if '/execution/frozen_inputs/' in row['path']:
            rel='inputs/'+row['path'].split('/execution/frozen_inputs/')[1];p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(data);copies.append({'path':rel,'source_path':row['path'],'sha256':row['sha256'],'git_blob':git})
    freeze=read(root/'formal_v2/freeze.json');code={k:v for k,v in freeze['sources'].items() if k.endswith('.py')}
    for k,v in code.items():assert sha((root/k).read_bytes())==v,k
    count=0;oldstates={};rawbase=cache/'research/chapter4_scheduler/results/onp_new24_20261113/execution'
    for p in sorted((rawbase/'calls').glob('*/method/result.json')):
        raw=read(p)
        for e in raw['evaluations']:
            if e.get('cache_hit',False):continue
            assert digest(e['candidate'])==e['candidate_sha256'];count+=1
            state=e['receipt']['state'];oldstates[state]=oldstates.get(state,0)+1
    runs=[]
    for plan in freeze['runs']:
        for arm in plan['order']:
            summary=read(root/'formal_v2'/f"{plan['call']}__{arm}"/'summary.json')
            assert not summary['failure']
            assert summary['root_seconds']==300
            assert summary['prototype_sources']==code
            assert sum(summary['states'].values())+len(summary['not_started'])==summary['planned_candidates']
            runs.append({'call':plan['call'],'arm':arm,'cpu_s':summary['cpu_s'],'wall_s':summary['wall_total_s'],
              'peak_rss_bytes':summary['memory']['peak_rss_bytes'],'panels':summary['physical_panels'],'refinements':summary['refinements'],
              'states':summary['states'],'not_started':len(summary['not_started'])})
    assert count==855 and len(runs)==48
    resources=[]
    for folder in ['pilot','formal','formal_v2']:
        events=[json.loads(x) for x in (root/folder/'events.jsonl').read_text().splitlines()]
        returned=[x for x in events if x['event']=='RETURN']
        resources.append({'stage':folder,'successful_replay_processes':sum(x['exit_code']==0 for x in returned),
          'nonzero_exit_processes':sum(x['exit_code']!=0 for x in returned),
          'all_process_wall_s':sum(x['process_wall_s'] for x in returned),
          'note':'formal v1 includes one intentional pre-bootstrap control stop; excluded from final performance.' if folder=='formal' else ''})
    result={'status':'PASS','frozen_sources_byte_identical':len(verified),'archived_candidate_payload_hashes':count,
      'historical_states':oldstates,'formal_v2_frozen_code_files':code,'formal_v2_runs_same_frozen_code':len(runs),
      'input_copies':copies,'runs':runs,'resources':resources,
      'scope':'Read-only source/certificate audit and byte-identical copies of eight frozen parameter files; zero scientific calls.'}
    (root/'results').mkdir(exist_ok=True);(root/'results/post_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['runs','input_copies','formal_v2_frozen_code_files']},ensure_ascii=False))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
