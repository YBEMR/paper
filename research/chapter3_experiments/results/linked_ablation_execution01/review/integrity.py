"""K173 old-source/archive baseline; standard-library hashing only."""
import argparse
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
RESULTS=ROOT/'results'

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rel(p):return Path(p).relative_to(REPO).as_posix()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        while b:=f.read(1048576):h.update(b)
    return h.hexdigest()
def state():
    d=read(RESULTS/'deadline_execution01/declaration.json')
    missing=d['slots'][16:]; unexpected=[]
    for s in missing:
        for camp in ('deadline_execution01','deadline_resume01'):
            p=RESULTS/camp/'claims'/(s['slot_id']+'.json')
            if p.exists():unexpected.append(rel(p))
    p=RESULTS/'whole_native_diagnostic_precheck01/run01/real_preparation'
    k,l=read(p/'declaration.json'),read(p/'ledger.json')
    return {'deadline_consumed':16,'deadline_unstarted':len(missing),'unexpected_claims':unexpected,
        'K168_authorized':k['plan']['authorized'],'K168_consumed':l['research_calls_consumed'],
        'K168_native_consumed':l['native_requests_consumed'],'K168_claim':l['claim'],'K168_state':l['state']}
def save(name,o):
    with (HERE/name).open('x',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False,indent=2);f.write('\n')
def main(after=False):
    start=time.perf_counter();cache={};diff=[]
    def get(k):
        if k not in cache:cache[k]=sha(REPO/k) if (REPO/k).is_file() else None
        return cache[k]
    if not after:
        p=RESULTS/'linked_ablation_preparation01/review/before_manifest.json';old=read(p)
        groups={**old['groups'],**old['frozen_directory_scopes']}
        for group,m in groups.items():
            diff.extend({'group':group,'path':k,'expected':v,'actual':get(k)} for k,v in m.items() if get(k)!=v)
        folder=RESULTS/'linked_ablation_preparation01'
        groups['K172_all_preparation_artifacts']={rel(f):get(rel(f)) for f in sorted(folder.rglob('*')) if f.is_file()}
        snapshot={g:{k:get(k) for k in m} for g,m in groups.items()}
        s=state();okay=not diff and s['deadline_unstarted']==24 and not s['unexpected_claims'] and not s['K168_authorized'] and s['K168_consumed']==s['K168_native_consumed']==0 and s['K168_claim'] is None
        save('before_manifest.json',{'protocol':'K173-old-artifact-before-v1','groups':snapshot,
            'previous_K172_before_sha256':sha(p),'differences':diff,'state':s,'unique_files_hashed':len(cache),
            'old_scientific_source_count':253,'new_execution_directory_excluded':True,
            'new_scientific_calls':0,'hash_wall_s':time.perf_counter()-start,'passed':okay})
    else:
        old=read(HERE/'before_manifest.json')
        for group,m in old['groups'].items():
            diff.extend({'group':group,'path':k,'expected':v,'actual':get(k)} for k,v in m.items() if get(k)!=v)
        s=state();okay=not diff and s==old['state']
        save('after_manifest.json',{'protocol':'K173-old-artifact-after-v1','before_manifest_sha256':sha(HERE/'before_manifest.json'),
            'differences':diff,'state':s,'unique_files_rehashed':len(cache),'new_scientific_calls':0,
            'hash_wall_s':time.perf_counter()-start,'passed':okay})
    print(json.dumps({'passed':okay,'files':len(cache),'differences':len(diff),'state':s},ensure_ascii=False))
    assert okay
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',action='store_true');main(p.parse_args().after)
