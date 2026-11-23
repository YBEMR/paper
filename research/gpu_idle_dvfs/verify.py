"""Verify archived timelines and certificates; no search or thermal replay."""
from bisect import bisect_right
from collections import defaultdict
import gzip,json,hashlib,sys
from pathlib import Path
import numpy as np
from run import HERE,ROOT,CFG,verify_freeze,read
sys.path.insert(0,str(ROOT/'research/kim_synthetic_platform_v1'))
from profiles import build_chains
from workloads import FROZEN


def main():
    verify_freeze()
    receipt=read(HERE/'receipt.json');assert receipt['status']=='completed' and receipt['total_wall_s']<=900
    for name,value in receipt['files'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==value,name
    results=read(HERE/'results.json');assert len(results)==78
    platform=read(ROOT/'research/kim_synthetic_platform_v1/platform.json')
    count=0;stage_count=0;switch_count=0;temperature_pairs={}
    for result in results:
        p=read(HERE/result['proof']);phy=p['physical'];inp=read(HERE/'raw'/f"{p['load']}_input.json.gz")
        assert p['deployment']=='X4139374' and p['stages']==inp['stages'] and p['request_sha']==inp['request_sha']
        jobs={q['id']:q for q in inp['requests']};rows=p['rows'];ledger={r['request_id']:r for r in p['completions']}
        assert len(jobs)==len(ledger)==phy['required']==phy['completed']==500
        binding=dict(applications=FROZEN['applications'],deployments={'fixed':dict(stages=inp['stages'])})
        chains={level:build_chains(platform,binding,'fixed','L'+level+'L') for level in ['L','H']}
        assert [[r['request'],r['stage_index']] for r in rows if r['resource']=='GPU']==inp['gpu_order']
        grouped=defaultdict(list);by_job=defaultdict(list)
        spans=p['clock_spans'];starts=[s[0] for s in spans]
        assert spans[0][0]==0 and spans[-1][1]==CFG['window_ns']
        assert all(a[1]==b[0] for a,b in zip(spans,spans[1:]))
        for row in rows:
            grouped[row['resource']].append(row);by_job[row['request']].append(row)
            level='L'
            if row['resource']=='GPU':
                i=bisect_right(starts,row['start_ns'])-1;a,b,level=spans[i]
                assert level in ['L','H'] and row['end_ns']<=b,'GPU clock changed within computation'
                if p['strategy'] in ['simple','predictive']:assert level=='H'
            stage=chains[level][jobs[row['request']]['app']][row['stage_index']]
            assert (stage.resource,stage.name,stage.duration_ns,stage.activity_w)==(row['resource'],row['stage'],row['end_ns']-row['start_ns'],row['activity_w'])
        for group in grouped.values():
            group.sort(key=lambda r:r['start_ns'])
            assert all(a['end_ns']<=b['start_ns'] for a,b in zip(group,group[1:]))
        for rid,q in jobs.items():
            chain=sorted(by_job[rid],key=lambda r:r['stage_index'])
            assert [r['stage_index'] for r in chain]==list(range(len(chains['L'][q['app']])))
            assert chain[0]['start_ns']>=q['release_ns']
            assert all(a['end_ns']<=b['start_ns'] for a,b in zip(chain,chain[1:]))
            record=ledger[rid]
            assert record['completion_ns']==chain[-1]['end_ns']
            assert record['release_ns']==q['release_ns'] and record['deadline_ns']==q['deadline_ns']
            assert record['slack_ns']==q['deadline_ns']-record['completion_ns']
        assert phy['min_slack_ms']==min(x['slack_ns'] for x in ledger.values())/1e6
        assert phy['deadline_ok']==all(x['slack_ns']>=0 for x in ledger.values())
        assert phy['SAFE']==(phy['deadline_ok'] and max(phy['peak_upper_c'])<=80)
        previous=[30.]*4;total=0.
        for block,span in zip(p['thermal_blocks'],spans,strict=True):
            assert [block['start_ns'],block['end_ns'],block['mode']]==span
            assert block['entry_c']==previous;previous=block['final_c'];total+=block['energy_j']
        assert previous==phy['final_c'] and abs(total-phy['energy_J'])<1e-8
        assert abs(phy['energy_J']-sum([phy['common_J'],phy['transfer_J'],sum(phy['idle_J']),sum(phy['activity_J']),sum(phy['leakage_J'])]))<1e-8
        for sw in p['switches']:
            assert sw['end_ns']-sw['start_ns']==p['setting']['latency_ns']
            assert sw['energy_j']==p['setting']['energy_j']
            assert not any(max(r['start_ns'],sw['start_ns'])<min(r['end_ns'],sw['end_ns']) for r in grouped['GPU'])
        assert abs(sum(sw['energy_j'] for sw in p['switches'])-phy['switch_energy_j'])<1e-10
        path=HERE/result['proof'].replace('.json.gz','_trace.npz')
        with np.load(path,allow_pickle=False) as trace:
            t,T=trace['time_s'],trace['temperature_c']
            assert t.shape==(len(T),) and T.shape[1]==4 and np.min(np.diff(t))>=-1e-9
            assert t[0]==0 and abs(t[-1]-10.04)<1e-8 and np.all(T[0]==30.)
            assert np.max(np.abs(T[-1]-phy['final_c']))<1e-8
            assert np.all(np.max(T,axis=0)<=np.array(phy['peak_upper_c'])+1e-8)
        if p['strategy']=='ideal_fixed_busy' or (p['strategy']=='kim' and p['setting']['id']=='ideal'):
            assert rows==inp['baseline_rows']
        if p['strategy']=='predictive':assert rows==inp['high_rows']
        key=p['load'],p['setting']['id'],p['strategy']
        signature=hashlib.sha256(json.dumps([rows,p['switches'],spans],sort_keys=True).encode()).hexdigest()
        if key in temperature_pairs:assert temperature_pairs[key]==signature,'Control depends on ambient temperature'
        temperature_pairs[key]=signature
        assert all(result[k]==v for k,v in phy.items())
        count+=len(ledger);stage_count+=len(rows);switch_count+=len(p['switches'])
    reg=read(HERE/'regression.json');assert reg['status']=='PASS' and len(reg['cases'])==6
    out=dict(status='PASS',full_replays=len(results),safe_replays=sum(r['SAFE'] for r in results),request_completions=count,
             stage_rows=stage_count,transition_records=switch_count,regression_cases=6,
             same_decisions_at_both_temperatures=True,scope='offline archive, timing, profiles, inheritance, certificates; no new physical evaluation')
    (HERE/'verification.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(out)


if __name__=='__main__':main()
