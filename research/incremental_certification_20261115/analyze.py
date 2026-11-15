"""Read-only paired analysis; common SAFE prefix, exact certificate endpoints."""
import argparse,json
from pathlib import Path

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def records(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
def analyze(folder):
    freeze=read(folder/'freeze.json');runs=[];failed=[]
    for plan in freeze['runs']:
        arms={}
        for arm in plan['order']:
            p=folder/f"{plan['call']}__{arm}"
            if not (p/'summary.json').exists():raise RuntimeError('INCOMPLETE_BATCH:'+str(p))
            arms[arm]={'summary':read(p/'summary.json'),'rows':records(p/'receipts.jsonl')}
            if arms[arm]['summary']['failure']:failed.append({'call':plan['call'],'arm':arm,'failure':arms[arm]['summary']['failure']})
            seen={}
            for r in arms[arm]['rows']:
                receipt=r.get('receipt',{})
                for source in receipt.get('reuse_provenance',[]):
                    assert source['source_candidate'] in seen,'FUTURE_OR_CROSS_ROOT_SOURCE'
                    old=seen[source['source_candidate']]
                    assert old['ordinal']<r['ordinal']
                    assert source['source_complete_at_s']==old['receipt']['completed_at_elapsed_s']
                    assert 0<=source['source_complete_at_s']<=r['start_elapsed_s']<=source['reused_at_s']<300
                if r['state']=='SAFE':
                    assert 0<=receipt['completed_at_elapsed_s']<300
                    seen[r['candidate_sha256']]=r
        count=0
        for i in range(min(len(v['rows']) for v in arms.values())):
            rr=[v['rows'][i] for v in arms.values()]
            assert all(r['ordinal']==i+1 and r['candidate_sha256']==plan['candidate_order'][i] for r in rr)
            if any(r['state']!='SAFE' for r in rr):break
            assert len({r['receipt']['semantic_sha256'] for r in rr})==1,'CROSS_ARM_NUMERICAL_DIFFERENCE'
            count+=1
        row={'call':plan['call'],'common_SAFE_prefix':count,'planned':len(plan['candidate_order']),
            'historical_UNRESOLVED':sum(s=='UNRESOLVED' for s in plan['historical_states']),'arms':{}}
        for arm,v in arms.items():
            rr=v['rows'];common=rr[:count];s=v['summary']
            # The next candidate start follows complete previous receipt archival.
            # It includes the next candidate's deepcopy if present; no next physics.
            boundary=rr[count]['start_elapsed_s'] if count<len(rr) else s['method_charged_s']
            cache={k:sum(r.get('cache_delta',{}).get(k,0) for r in common) for k in s['cache_metrics']}
            row['arms'][arm]={'common_charged_s':boundary,'common_source_plus_charged_s':boundary+s['source_load_outside_root_s'],
                'new_panels_common':sum(r['new_panels'] for r in common),'new_extremum_calls_common':sum(r['new_extremum_calls'] for r in common),
                'new_refinements_common':sum(r.get('new_refinements',0) for r in common),
                'outer_legality_common_s':sum(r.get('outer_legality_s',0) for r in common),
                'evaluation_common_s':sum(r.get('evaluation_wall_s',0) for r in common),
                'validation_commit_common_s':sum(r.get('validation_and_commit_s',0) for r in common),
                'cache_common':cache,'full_method_charged_s':s['method_charged_s'],'full_states':s['states'],
                'not_started_count':len(s['not_started']),'full_panels':s['physical_panels'],'peak_rss_bytes':s['memory']['peak_rss_bytes'],
                'full_cache':s['cache_metrics']}
        a=row['arms']['A']['common_charged_s']
        for arm,v in row['arms'].items():
            if arm=='A':continue
            avoided=v['cache_common']['avoided_scene_panels']+v['cache_common']['avoided_prefix_panels']
            assert v['new_panels_common']+avoided==row['arms']['A']['new_panels_common'],'PANEL_COVERAGE_ACCOUNTING'
            assert v['new_extremum_calls_common']+8*avoided==row['arms']['A']['new_extremum_calls_common'],'EXTREMUM_ACCOUNTING'
        row['saving_vs_A']={arm:1-v['common_charged_s']/a for arm,v in row['arms'].items() if arm!='A'}
        runs.append(row)
    arms=sorted(runs[0]['arms']);totals={}
    for arm in arms:
        totals[arm]={key:sum(r['arms'][arm][key] for r in runs) for key in ['common_charged_s','common_source_plus_charged_s','new_panels_common','new_extremum_calls_common','new_refinements_common','evaluation_common_s','validation_commit_common_s','outer_legality_common_s','full_method_charged_s','not_started_count','full_panels']}
        totals[arm]['cache_common']={k:sum(r['arms'][arm]['cache_common'][k] for r in runs) for k in runs[0]['arms'][arm]['cache_common']}
        totals[arm]['peak_rss_max_bytes']=max(r['arms'][arm]['peak_rss_bytes'] for r in runs)
        totals[arm]['full_states']={k:sum(r['arms'][arm]['full_states'][k] for r in runs) for k in runs[0]['arms'][arm]['full_states']}
    saves={arm:1-totals[arm]['common_charged_s']/totals['A']['common_charged_s'] for arm in arms if arm!='A'}
    positive={arm:sum(r['saving_vs_A'][arm]>0 for r in runs) for arm in arms if arm!='A'}
    out={'stage':freeze['stage'],'exact_cross_arm_SAFE':True,'common_SAFE_candidates':sum(r['common_SAFE_prefix'] for r in runs),
        'failures':failed,'runs':runs,'totals':totals,'saving_vs_A':saves,'positive_runs':positive,
        'boundary_note':'Common prefix ends at next-candidate start (includes its deepcopy, no next numerical work), or full method stop if no next record.'}
    if freeze['stage']=='pilot':out['B_gate_pass']=not failed and saves['B']>=0.05 and positive['B']>=3
    (folder/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k not in ['runs','totals']},ensure_ascii=False))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();analyze(a.folder)
