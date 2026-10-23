"""K176 read-only source/archive integrity; no scientific imports or calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RESULTS = REPO / 'research/chapter3_experiments/results'

def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        while b := f.read(1048576): h.update(b)
    return h.hexdigest()
def rel(p): return Path(p).relative_to(REPO).as_posix()
def save(p, obj):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')
def state():
    d = read(RESULTS/'deadline_execution01/declaration.json')
    missing = d['slots'][16:]
    unexpected = [rel(RESULTS/c/'claims'/(s['slot_id']+'.json'))
        for s in missing for c in ('deadline_execution01','deadline_resume01')
        if (RESULTS/c/'claims'/(s['slot_id']+'.json')).exists()]
    p = RESULTS/'whole_native_diagnostic_precheck01/run01/real_preparation'
    k,l = read(p/'declaration.json'),read(p/'ledger.json')
    return {'deadline_consumed':16, 'deadline_unstarted':len(missing),
        'unexpected_claims':unexpected, 'K168_authorized':k['plan']['authorized'],
        'K168_consumed':l['research_calls_consumed'],
        'K168_native_consumed':l['native_requests_consumed'],
        'K168_claim':l['claim'], 'K168_state':l['state']}
def main(after=False):
    start=time.perf_counter(); expected={}; conflicts=[]
    if after:
        old=read(HERE/'before_manifest.json'); expected=old['files_sha256']
    else:
        prior=read(RESULTS/'linked_ablation_execution01/review/before_manifest.json')
        sources=[*prior['groups'].values(),
            read(RESULTS/'linked_release_integration01/review/before_manifest.json')['files_sha256']]
        for group in sources:
            for k,v in group.items():
                if k in expected and expected[k]!=v:conflicts.append(k)
                expected[k]=v
        for folder in ('linked_ablation_execution01','linked_release_preparation01',
                       'linked_release_integration01'):
            for p in sorted((RESULTS/folder).rglob('*')):
                if p.is_file():expected.setdefault(rel(p),sha(p))
        for name in ('linked_release_method.py','linked_release_policy.py','test_linked_release_pure.py'):
            p=RESULTS.parent/name;expected[rel(p)]=sha(p)
    actual={k:sha(REPO/k) if (REPO/k).is_file() else None for k in expected}
    differences=[{'path':k,'expected':v,'actual':actual[k]} for k,v in expected.items() if actual[k]!=v]
    s=state(); okay=(not conflicts and not differences and s['deadline_unstarted']==24
        and not s['unexpected_claims'] and not s['K168_authorized']
        and s['K168_consumed']==s['K168_native_consumed']==0 and s['K168_claim'] is None)
    if after:okay=okay and s==old['state']
    data={'protocol':'K176-old-artifact-'+('after' if after else 'before')+'-v1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(), 'passed':okay,
        'files_sha256':actual, 'expected_hash_conflicts':conflicts, 'differences':differences,
        'state':s,'unique_files_hashed':len(actual),'scientific_calls':0,
        'thermal_integrations':0,'hash_wall_s':time.perf_counter()-start}
    if after:data['before_manifest_sha256']=sha(HERE/'before_manifest.json')
    save(HERE/('after_manifest.json' if after else 'before_manifest.json'),data)
    print(json.dumps({'passed':okay,'files':len(actual),'differences':differences,'state':s}))
    if not okay:raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',action='store_true');main(p.parse_args().after)
