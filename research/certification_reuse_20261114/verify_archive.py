"""Static source identity and derived CSV consistency; never evaluate a schedule."""
import argparse, ast, csv, hashlib, json
from pathlib import Path

def read(path): return json.loads(path.read_text(encoding='utf-8'))

def main(cache):
    here=Path(__file__).resolve().parent; checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition: raise AssertionError(name)
    manifest=read(here/'source_manifest.json')
    for item in manifest['sources']:
        data=(cache/item['path']).read_bytes()
        check('source/'+item['path'],hashlib.sha256(data).hexdigest()==item['sha256'] and
              hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['sha'])
    check('protocol_identity',hashlib.sha256((here/'PROTOCOL.md').read_bytes()).hexdigest()==read(here/'protocol_freeze.json')['sha256'])
    for path in sorted(here.glob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'));check('syntax/'+path.name,True)
    res=here/'results';s=read(res/'summary.json')
    with (res/'candidates.csv').open(encoding='utf-8',newline='') as f: cs=list(csv.DictReader(f))
    with (res/'scene_pairs.csv').open(encoding='utf-8',newline='') as f: ps=list(csv.DictReader(f))
    with (res/'runs.csv').open(encoding='utf-8',newline='') as f: rs=list(csv.DictReader(f))
    check('complete_population',len(cs)==855 and len(ps)==3356 and len(rs)==16)
    check('safe_and_unresolved_retained',sum(r['state']=='SAFE' for r in cs)==845 and sum(r['state']=='UNRESOLVED' for r in cs)==10)
    check('no_existing_hash_hits',s['actual_full_hash_cache_hits']==0 and all(r['cache_hits']=='0' for r in rs))
    for a in s['aggregates']:
        cc=[r for r in cs if a['phase']=='all' or r['phase']==a['phase']]
        check('aggregate_population/'+a['phase'],len(cc)==a['evaluations'])
        for key in ['segments','panel_attempts','committed_panels','uncommitted_panel_attempts','refinements','whole_scene_panels','extra_incumbent_prefix_panels']:
            check('aggregate/'+a['phase']+'/'+key,sum(int(r[key]) for r in cc)==a[key])
    check('panel_attempts_not_repeated_cumulative_sum',sum(int(r['attempted_panels']) for r in rs)==79796 and sum(int(r['committed_panels']) for r in cs)==79787)
    check('all_search_parents_single_scene',all(r['incumbent_changed_scenes']=='1' for r in cs if r['phase']=='refinement'))
    check('retained_zero_reuse',s['incumbent_coverage'][0]['zero_reusable_panel_candidates']==40)
    check('no_scientific_calls_or_claimed_speedup',s['new_scientific_calls']==0 and s['wall_speedup'] is None and s['thermal_subphase_timings'] is None)
    for key in ['thermal.py','interval.py','method.py','graph_core.py']:
        item=next(x for x in manifest['sources'] if x['path']=={'thermal.py':'research/chapter3_experiments/thermal.py','interval.py':'research/v1_evaluator/interval.py','method.py':'research/chapter4_scheduler/method.py','graph_core.py':'research/chapter4_scheduler/graph_core.py'}[key])
        check('runtime_snapshot_matches/'+key,item['runtime_snapshot_git_blob']==item['sha'])
    output={'status':'PASS_STATIC_ARCHIVE_CHECKS','checks':len(checks),'detail':checks,'new_scientific_calls':0,
            'not_certified':'No new incremental evaluator, runtime speedup, or independent thermal proof was tested.'}
    (here/'verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':output['status'],'checks':len(checks)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);main(p.parse_args().cache)
