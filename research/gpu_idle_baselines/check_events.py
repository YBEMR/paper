"""Necessary causal/timing checks only, not performance trials or research cases."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'research/gpu_idle_dvfs'),str(ROOT/'research/kim_synthetic_platform_v1')]
import events
from scheduler import Timeline
from online_events import simulate
from controller import Control

def main():
    chains={level:{0:(events.Stage('pre','CPU0',1000,1.),events.Stage('gpu','GPU',duration,2.),events.Stage('post','CPU0',1000,1.))}
            for level,duration in [('L',2000),('H',1000)]}
    req=[events.Request('l0',0,0,40000),events.Request('h0',0,40000,80000),events.Request('h1',0,80000,120000)]
    order=[(q.id,1) for q in req];meta={'l0':(0,'L'),'h0':(2,'H'),'h1':(2,'H')}
    setting=dict(latency_ns=500,energy_j=1e-6)
    runs={}
    for policy in ['reactive','periodic']:
        runs[policy]=simulate(events,Timeline,req,chains,order,meta,124000,policy,setting,100,40000,120000)
        rows,completion,_,audit=runs[policy]
        gpu=[r for r in rows if r.resource=='GPU']
        assert [r.end_ns-r.start_ns for r in gpu]==[2000,1000,1000]
        assert completion['l0']==4000 and completion['h0']==43500
    assert runs['reactive'][1]['h1']==83500 and runs['periodic'][1]['h1']==83000
    plog=runs['periodic'][3]['controller_log']
    for row in plog:
        if row['kind'].startswith('prediction_'):
            sample=plog[row['sample_seq']]
            assert sample['kind']=='ready' and sample['t_ns']<=row['t_ns'] and row['predicted_ns']==sample['t_ns']+40000
    req2=[events.Request('a',0,0,10000),events.Request('b',0,2000,10000)]
    _,_,timeline,audit=simulate(events,Timeline,req2,chains,[('a',1),('b',1)],{'a':(2,'H'),'b':(2,'H')},12000,'reactive',setting,100,40000,10000)
    second=audit['gpu_starts'][1]
    assert second['ready_ns']==3000 and second['start_ns']==3700
    ctrl=Control('periodic',500,1e-6,100,40000,120000,124000)
    ctrl.release(0,'x',0,0,2,'H');assert ctrl.next_prediction(0) is None
    ctrl.ready(1000,'x',1);assert ctrl.next_prediction(1000)['predicted_ns']==41000
    ctrl.release(40000,'y',0,40000,3,'H');assert ctrl.next_prediction(40000) is None
    result=dict(status='PASS',checks=['L/H computation preserved; reactive wake delay is real',
        'periodic warm-up uses only a previous observed ready event',
        'arrival during down-transition pays remaining transition, minimum dwell and wake',
        'new scene clears history and cannot have a preloaded forecast'])
    (HERE/'checks.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(result)
if __name__=='__main__':main()
