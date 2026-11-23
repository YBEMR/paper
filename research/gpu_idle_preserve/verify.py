"""Archive-only verification of fixed compute timing, transitions and full SAFE certificates."""
from bisect import bisect_right
import json
import numpy as np
from run_preserve import HERE,OLD,CFG,read,sha,verify_freeze


def main():
    verify_freeze()
    receipt=read(HERE/'receipt.json');assert receipt['status']=='completed' and receipt['total_wall_s']<=300
    for name,value in receipt['files'].items():assert sha(HERE/name)==value,name
    results=read(HERE/'results.json');assert len(results)==18
    decisions={};counts=dict(replays=0,SAFE=0,request_completions=0,stage_rows=0,switches=0)
    max_compute_error=0.
    for result in results:
        proof=read(HERE/result['proof']);p=proof['physical']
        base=read(OLD/'raw'/proof['case_id']/'ideal_kim.json.gz')
        matched=read(OLD/'raw'/proof['case_id']/(proof['setting']['id']+'_kim.json.gz'))
        assert proof['deployment']==base['deployment']=='X4139374'
        for key in ['stages','request_sha','rows','completions']:
            assert proof[key]==base[key],(result['case_id'],key)
        assert len(proof['completions'])==p['required']==p['completed']==500
        spans=proof['clock_spans'];starts=[x[0] for x in spans]
        oldspans=base['clock_spans'];oldstarts=[x[0] for x in oldspans]
        assert spans[0][0]==0 and spans[-1][1]==CFG['window_ns']
        assert all(a[1]==b[0] for a,b in zip(spans,spans[1:]))
        gpu=[r for r in proof['rows'] if r['resource']=='GPU']
        for r in gpu:
            _,end,mode=spans[bisect_right(starts,r['start_ns'])-1]
            oldmode=oldspans[bisect_right(oldstarts,r['start_ns'])-1][2]
            assert mode==oldmode and mode in ['L','H'] and r['end_ns']<=end
        for switch in proof['switches']:
            assert switch['end_ns']-switch['start_ns']==proof['setting']['latency_ns']
            assert switch['energy_j']==proof['setting']['energy_j']
            assert not any(max(r['start_ns'],switch['start_ns'])<min(r['end_ns'],switch['end_ns']) for r in gpu)
        assert abs(sum(x['energy_j'] for x in proof['switches'])-p['switch_energy_j'])<1e-10
        compute_error=abs(sum(p['activity_J'])-p['switch_energy_j']-sum(base['physical']['activity_J']))
        max_compute_error=max(max_compute_error,compute_error);assert compute_error<1e-8
        previous=[30.]*4;energy=0.
        for block,span in zip(proof['thermal_blocks'],spans,strict=True):
            assert [block['start_ns'],block['end_ns'],block['mode']]==span
            assert block['entry_c']==previous;previous=block['final_c'];energy+=block['energy_j']
        assert previous==p['final_c'] and abs(energy-p['energy_J'])<1e-8
        assert abs(p['energy_J']-sum([p['common_J'],p['transfer_J'],sum(p['idle_J']),sum(p['activity_J']),sum(p['leakage_J'])]))<1e-8
        assert p['min_slack_ms']==min(q['deadline_ns']-q['completion_ns'] for q in proof['completions'])/1e6
        assert p['deadline_ok']==all(q['slack_ns']>=0 for q in proof['completions'])
        assert p['SAFE']==(p['deadline_ok'] and max(p['peak_upper_c'])<=80)
        with np.load(HERE/result['proof'].replace('.json.gz','_trace.npz'),allow_pickle=False) as trace:
            t,T=trace['time_s'],trace['temperature_c']
            assert t[0]==0 and abs(t[-1]-10.04)<1e-8 and T.shape==(len(t),4)
            assert np.min(np.diff(t))>=-1e-9 and np.all(T[0]==30.)
            assert np.max(np.abs(T[-1]-p['final_c']))<1e-8
            assert np.all(np.max(T,axis=0)<=np.array(p['peak_upper_c'])+1e-8)
        assert matched['setting']==proof['setting'] and matched['request_sha']==proof['request_sha']
        key=proof['load'],proof['setting']['id']
        decision=(proof['rows'],spans,proof['switches'])
        if key in decisions:assert decisions[key]==decision
        decisions[key]=decision
        assert all(result[k]==v for k,v in p.items())
        counts['replays']+=1;counts['SAFE']+=int(p['SAFE']);counts['request_completions']+=500
        counts['stage_rows']+=len(proof['rows']);counts['switches']+=len(proof['switches'])
    output=dict(status='PASS',counts=counts,max_compute_activity_error_j=max_compute_error,
        all_stage_frequencies_and_timings_equal_Kim=True,same_decisions_at_both_temperatures=True,
        scope='archived records and inherited baseline certificates; no extra physical replay')
    (HERE/'verification.json').write_bytes((json.dumps(output,indent=2)+'\n').encode());print(output)

if __name__=='__main__':main()
