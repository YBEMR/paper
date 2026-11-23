"""Offline physical-record and causal-information audit. No extra physical runs."""
from bisect import bisect_right
from collections import defaultdict,Counter
import json
import numpy as np
from run_baselines import HERE,OLD,CFG,read,sha,verify_freeze

def main():
    verify_freeze();receipt=read(HERE/'receipt.json')
    assert receipt['status']=='completed' and receipt['total_wall_s']<=CFG['batch_timeout_s']
    for name,value in receipt['files'].items():assert sha(HERE/name)==value,name
    results=read(HERE/'results.json');assert len(results)==36
    counts=Counter();decisions={};maximum_activity_error=0.
    for result in results:
        p=read(HERE/result['proof']);phy=p['physical']
        audit=read(HERE/result['proof'].replace('.json.gz','_control.json.gz'))
        baseline=read(OLD/'raw'/p['case_id']/'ideal_kim.json.gz')
        assert p['deployment']==baseline['deployment']=='X4139374'
        assert p['stages']==baseline['stages'] and p['request_sha']==baseline['request_sha']
        rows=p['rows'];oldrows=baseline['rows'];by_key={(r['request'],r['stage_index']):r for r in rows}
        old_key={(r['request'],r['stage_index']):r for r in oldrows}
        assert len(rows)==len(oldrows)==len(by_key) and set(by_key)==set(old_key)
        for key,r in by_key.items():
            b=old_key[key]
            assert (r['stage'],r['resource'],r['end_ns']-r['start_ns'],r['activity_w'])==(b['stage'],b['resource'],b['end_ns']-b['start_ns'],b['activity_w'])
        gpu=[r for r in rows if r['resource']=='GPU']
        assert [(r['request'],r['stage_index']) for r in gpu]==[(r['request'],r['stage_index']) for r in oldrows if r['resource']=='GPU']
        spans=p['clock_spans'];starts=[x[0] for x in spans];oldspans=baseline['clock_spans'];oldstarts=[x[0] for x in oldspans]
        assert spans[0][0]==0 and spans[-1][1]==CFG['window_ns'] and all(a[1]==b[0] for a,b in zip(spans,spans[1:]))
        for r in gpu:
            _,end,mode=spans[bisect_right(starts,r['start_ns'])-1];b=old_key[r['request'],r['stage_index']]
            required=oldspans[bisect_right(oldstarts,b['start_ns'])-1][2]
            assert mode==required and r['end_ns']<=end
        resources=defaultdict(list);job_rows=defaultdict(list)
        for r in rows:resources[r['resource']].append(r);job_rows[r['request']].append(r)
        for rr in resources.values():
            rr.sort(key=lambda r:r['start_ns']);assert all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
        old_jobs={q['request_id']:q for q in baseline['completions']};ledger={q['request_id']:q for q in p['completions']}
        assert len(ledger)==phy['required']==phy['completed']==500 and ledger.keys()==old_jobs.keys()
        for rid,job in ledger.items():
            rr=sorted(job_rows[rid],key=lambda r:r['stage_index']);old=old_jobs[rid]
            assert all(job[k]==old[k] for k in ['app_id','release_ns','deadline_ns'])
            assert rr[0]['start_ns']>=job['release_ns'] and all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
            assert rr[-1]['end_ns']==job['completion_ns'] and job['slack_ns']==job['deadline_ns']-job['completion_ns']
        assert phy['min_slack_ms']==min(q['slack_ns'] for q in ledger.values())/1e6
        assert phy['deadline_ok']==all(q['slack_ns']>=0 for q in ledger.values())
        assert phy['SAFE']==(phy['deadline_ok'] and max(phy['peak_upper_c'])<=80)
        previous=[30.]*4;energy=0.
        for block,span in zip(p['thermal_blocks'],spans,strict=True):
            assert [block['start_ns'],block['end_ns'],block['mode']]==span and block['entry_c']==previous
            previous=block['final_c'];energy+=block['energy_j']
        assert previous==phy['final_c'] and abs(energy-phy['energy_J'])<1e-8
        assert abs(phy['energy_J']-sum([phy['common_J'],phy['transfer_J'],sum(phy['idle_J']),sum(phy['activity_J']),sum(phy['leakage_J'])]))<1e-8
        activity_error=abs(sum(phy['activity_J'])-phy['switch_energy_j']-sum(baseline['physical']['activity_J']))
        maximum_activity_error=max(maximum_activity_error,activity_error);assert activity_error<1e-8
        for sw in p['switches']:
            assert sw['end_ns']-sw['start_ns']==p['setting']['latency_ns'] and sw['energy_j']==p['setting']['energy_j']
            assert not any(max(r['start_ns'],sw['start_ns'])<min(r['end_ns'],sw['end_ns']) for r in gpu)
        assert abs(sum(sw['energy_j'] for sw in p['switches'])-phy['switch_energy_j'])<1e-10
        with np.load(HERE/result['proof'].replace('.json.gz','_trace.npz'),allow_pickle=False) as trace:
            t,T=trace['time_s'],trace['temperature_c']
            assert T.shape==(len(t),4) and np.min(np.diff(t))>=-1e-9 and t[0]==0 and abs(t[-1]-10.04)<1e-8
            assert np.all(T[0]==30.) and np.max(np.abs(T[-1]-phy['final_c']))<1e-8
            assert np.all(np.max(T,axis=0)<=np.array(phy['peak_upper_c'])+1e-8)
        # Independently reconstruct the observed information available to each forecast.
        log=audit['controller_log'];released={};live={};scene=None;seen_ready={};transitions=[];gpu_started=[]
        assert all(a['t_ns']<=b['t_ns'] for a,b in zip(log,log[1:]))
        for seq,event in enumerate(log):
            assert event['seq']==seq;now=event['t_ns'];kind=event['kind']
            if kind=='scene_reset':scene=event['scene'];live.clear()
            elif kind=='release':
                rid=event['rid'];assert rid not in released
                assert now==event['release_ns']==ledger[rid]['release_ns'] and event['app']==ledger[rid]['app_id']
                released[rid]=event
            elif kind=='ready':
                rid=event['rid'];stage=event['stage'];assert rid in released
                assert event['release_ns']==released[rid]['release_ns'] and event['scene']==released[rid]['scene']
                ready_at=by_key[rid,stage-1]['end_ns'] if stage else ledger[rid]['release_ns']
                assert now==ready_at and event['offset_ns']==now-event['release_ns'];seen_ready[rid,stage]=now
            elif kind=='forecast':
                assert p['strategy']=='periodic';sample=log[event['sample_seq']]
                assert sample['kind']=='ready' and sample['seq']<seq and sample['t_ns']==now==event['sample_time_ns']
                assert sample['rid']==event['sample_rid'] and sample['required']=='H' and sample['scene']==event['scene']==scene
                assert (sample['app'],sample['stage'])==(event['app'],event['stage'])
                assert event['predicted_ns']==now+CFG['period_ns']
                assert event['next_release_ns']==sample['release_ns']+CFG['period_ns']<CFG['service_end_ns']
                assert not event['used'];live[event['app'],event['stage']]=[event['sample_seq'],False]
                counts['forecasts']+=1
            elif kind in ['prediction_wake','prediction_keep_H','forecast_expired']:
                key=(event['app'],event['stage']);assert key in live and live[key]==[event['sample_seq'],False]
                sample=log[event['sample_seq']];assert sample['t_ns']<=now and event['predicted_ns']==sample['t_ns']+CFG['period_ns']
                if kind=='forecast_expired':assert event['predicted_ns']<now
                assert event['used'];live[key][1]=True;counts[kind]+=1
            elif kind=='transition_start':
                transitions.append(event)
                if event['reason']=='periodic_prediction':
                    assert p['strategy']=='periodic' and event['head'] is None and event['target']=='H'
                    assert log[seq-1]['kind']=='prediction_wake' and log[seq-1]['t_ns']==now
                elif event['reason']=='actual_ready':
                    assert event['head'] is not None and seen_ready[tuple(event['head'])]<=now
            elif kind=='gpu_start':
                r=by_key[event['rid'],event['stage']];assert now==r['start_ns'] and event['ready_ns']==seen_ready[event['rid'],event['stage']]
                gpu_started.append({k:event[k] for k in ['rid','stage','ready_ns','required']}|{'start_ns':now})
        assert len(released)==500 and gpu_started==audit['gpu_starts']
        assert len(transitions)==len(p['switches'])
        for event,sw in zip(transitions,p['switches'],strict=True):
            assert event['t_ns']==sw['start_ns'] and event['source']==sw['source'] and event['target']==sw['target']
        for stall in audit['stall_segments']:
            assert seen_ready[stall['rid'],stall['stage']]<=stall['start_ns']<stall['end_ns']<=by_key[stall['rid'],stall['stage']]['start_ns']
            assert not any(max(r['start_ns'],stall['start_ns'])<min(r['end_ns'],stall['end_ns']) for r in gpu)
        key=p['load'],p['setting']['id'],p['strategy'];signature=(rows,spans,p['switches'],audit)
        if key in decisions:assert decisions[key]==signature
        decisions[key]=signature
        assert all(result[k]==v for k,v in phy.items())
        counts['new_replays']+=1;counts['SAFE']+=int(phy['SAFE']);counts['request_completions']+=500
        counts['stage_rows']+=len(rows);counts['switches']+=len(p['switches'])
    report=dict(status='PASS',counts=dict(counts),max_compute_activity_error_j=maximum_activity_error,
        causal_prediction_samples_verified=True,same_control_at_both_temperatures=True,
        scope='frozen sources, raw receipts, stages, causal observations, deadlines and continuous thermal certificate consistency; no reruns')
    (HERE/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(report)
if __name__=='__main__':main()
