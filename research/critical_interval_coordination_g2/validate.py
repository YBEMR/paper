"""Exact small domains, queue equivalence and archived FIFO replay. No research search."""
import gzip, itertools, json, time, copy, traceback, sys
from assets import ROOT,G1,problem,load,assess,read,write,assemble,idle_plan,Layout,git,utc,Q
from fifo import Compact
from model import transitions, independent_events, event_arrays, Invalid
import numpy as np

def check(m,cfg):
    p=m.p;rows=assemble(p,cfg);s=m.replay(cfg)
    physical=all(p.finish(3*i+2,rows[3*i+2])<=r["deadline_tick"] for i,r in enumerate(p.req))
    assert (s is not None)==physical
    if not physical:return False
    plan=idle_plan(p,rows);layout=Layout(p,rows)
    expected=sum(layout.components(plan[1]).values())
    assert expected==m.joules(s)
    for a in (0,1):
        actual=tuple((p.finish(3*i+1,rows[3*i+1]),i) for i,op in enumerate(cfg) if op[0]==a+2)
        assert s.events[a]==actual
    for low in {frozenset(),plan[1]}:
        _,sw,_=transitions(p,rows,low)
        assert sw==layout.switches(low)==independent_events(p,rows,low)[1]
    return True

def gate():
    receipt=ROOT/"model_gate.json"
    with receipt.open("x") as f:f.write("{}")
    start=time.perf_counter();data=dict(utc=utc(),freeze=git("rev-parse","HEAD"),fixtures=[],replays={})
    try:
        gate=read(ROOT/"witness_gate.json");assert gate["status"]=="PASS"
        r=problem("S16");w=load(gate["witnesses"]["S16"]["plan"])[0];base=[x[:2] for x in w[1::3]]
        for tight in (False,True):
            p=copy.deepcopy(r)
            if tight:
                # Put every post exactly at its witness finish; this includes queue interactions.
                for i,req in enumerate(p.req):req["deadline_tick"]=p.finish(3*i+2,w[3*i+2])
            m=Compact(p);valid=0;invalid=0
            for first,second in itertools.product(m.ops,repeat=2):
                cfg=base.copy();cfg[3]=first;cfg[4]=second
                if check(m,cfg):valid+=1
                else:invalid+=1
            data["fixtures"].append(dict(tight=tight,valid=valid,invalid=invalid))
        assert invalid and valid
        # Exhaust all two-device event patterns in a near-overlap window, including equal ticks, both ID orders.
        import itertools as it
        tests=0
        for ends in it.product(range(11,40),range(11,40)):
            for ids in ((0,1),(1,0)):
                events=sorted(zip(ends,ids));finish=0
                for k,(e,i) in enumerate(events):
                    q=(11,13);finish=max(finish,e)+q[i]
                    alt=max([e+q[i]]+[v+q[j]+q[i] for v,j in events[:k]])
                    assert finish==alt
                    tests+=1
        data["event_cases"]=tests
        refs=[json.loads(l) for l in (G1/"results/references.jsonl").read_bytes().splitlines()]
        for case in ("S16","S32","S80","D1","D2","D3"):
            p=problem(case);m=Compact(p)
            keys={r["plan"] for r in refs if r["case"]==case and r["status"]=="SAFE"}
            keys.add(read(G1/"results/seeds"/(case+".json"))["plan"])
            for l in (G1/"results/suffix.jsonl").read_bytes().splitlines():
                if case=="D3":keys.add(json.loads(l)["plan"])
            for key in sorted(keys):
                o=json.loads(gzip.decompress((G1/"results/plans"/(key+".json.gz")).read_bytes()))
                rows=list(map(tuple,o["rows"]));cfg=[x[:2] for x in rows[1::3]]
                assert assemble(p,cfg)==rows and check(m,cfg)
                low=frozenset(map(tuple,o["low"]));arch=read(G1/"results/certificates"/(key+".json"))
                lay=Layout(p,rows)
                assert lay.switches(low)==list(map(tuple,arch["switches"]))
                assert sum(lay.components(low).values())==Q(arch["exact_E35_J"])
            data["replays"][case]=len(keys)
        data["status"]="PASS"
    except BaseException:
        data.update(status="STOP",error=traceback.format_exc());raise
    finally:
        data.update(end=utc(),elapsed_s=time.perf_counter()-start);write(receipt,data)
if __name__=="__main__":gate()
