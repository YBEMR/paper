"""Necessary L/M/H event test, no thermal performance pilot."""
import sys,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'research/kim_synthetic_platform_v1'))
import events
from control import Control,Timeline
from online_events import simulate
requests=[events.Request('a',0,0,40000000),events.Request('b',0,40000000,80000000)]
chains={0:{0:[events.Stage('gpu','GPU',1000000,2.)]},1:{0:[events.Stage('gpu','GPU',1200000,1.)]}}
rows,done,timeline,audit=simulate(events,Timeline,requests,chains,[('a',0),('b',0)],{'a':(0,'H'),'b':(1,'M')},100000000,'reactive',dict(latency_ns=100000,energy_j=1e-5),100000,40000000,80000000)
assert rows[0].start_ns==200000 and rows[1].start_ns==40100000
assert rows[0].end_ns-rows[0].start_ns==1000000 and rows[1].activity_w==1.
assert [s['target'] for s in timeline.switches]==['H','L','M','L']
c=Control('reactive',100000,1e-5,100000,40000000,80000000,100000000)
assert c.choose(1000000,'M',True,None,0,0)==(None,None,None)
assert c.choose(1000000,'M',False,'M',0,0)==(None,None,None)
result=dict(status='PASS',checks=['preserved M/H compute','nonzero restoration stall','idle M to L','no midstage switch'],scope='two toy requests only; formal four regressions paid inside budgets')
(HERE/'checks.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(result)
