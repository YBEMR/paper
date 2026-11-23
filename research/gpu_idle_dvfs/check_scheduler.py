"""Three small timing invariants only; no new research workload or performance pilot."""
import sys
from model import ROOT,save,HERE
sys.path.insert(0,str(ROOT/'research/kim_synthetic_platform_v1'))
import events
from scheduler import Timeline,dispatch,predictive_calendar


def main():
    chain=(events.Stage('pre','CPU0',1000,1.),events.Stage('gpu','GPU',1000,2.),events.Stage('post','CPU0',1000,1.))
    chains={'L':{0:chain},'H':{0:chain}}
    req=[events.Request('a',0,0,10000),events.Request('b',0,20000,30000)]
    original,original_completion=events._dispatch(req,{0:chain})
    order=[(r.request,r.stage_index) for r in original if r.resource=='GPU']
    high=Timeline(40000);high.changes=[(0,'H')]
    rows,completion,_=dispatch(events,req,chains,order,40000,calendar=high)
    assert rows==original and completion==original_completion
    _,slow,_=dispatch(events,req,chains,order,40000,simple=(500,1e-6,100))
    assert slow['a']==original_completion['a']+500 and slow['b']==original_completion['b']+500
    forecast=predictive_calendar(original,40000,500,1e-6,100)
    pred,pred_completion,_=dispatch(events,req,chains,order,40000,calendar=forecast)
    assert pred==original and pred_completion==original_completion
    result=dict(status='PASS',checks=['fixed GPU order and original dispatcher identity',
        'reactive wake latency appears in both request completion times','predictive wake hides transitions before actual GPU ready times'])
    save(HERE/'scheduler_checks.json',result);print(result)


if __name__=='__main__':main()
