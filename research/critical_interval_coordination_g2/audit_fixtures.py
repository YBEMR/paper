"""Independent fixed-domain enumeration of idle policies, physical events and solver optimum."""
from itertools import product,chain
from time import perf_counter
from assets import ROOT,read,write,problem,load,assemble,Layout,Q,git,utc
from model import transitions,independent_events
from fifo import Compact
from feedback import virtual,neighborhood,targets
def main():
    begin=perf_counter();until=begin+80
    p=problem("S16");m=Compact(p)
    base=[row[:2] for row in load(read(ROOT/"witness_gate.json")["witnesses"]["S16"]["plan"])[0][1::3]]
    domain=[3,4];minimum=None;count=0;schedules=set()
    for ops in product(m.ops,repeat=2):
        cfg=list(base)
        for i,op in zip(domain,ops):cfg[i]=op
        rows=assemble(p,cfg);lay=Layout(p,rows);low_list=sorted(lay.flex)
        values=[]
        for mask in product((False,True),repeat=len(low_list)):
            low=frozenset(k for k,on in zip(low_list,mask) if on)
            switches=lay.switches(low);assert switches==transitions(p,rows,low)[1]
            events,sw=independent_events(p,rows,low);assert sw==switches
            reference=sum(lay.components(low).values())
            scalar=((events[:,1]-events[:,0])*(events[:,2:6].sum(axis=1)+.3)).sum()/10000
            assert abs(float(reference)-scalar)<1e-10
            values.append(reference);schedules.add((tuple(rows),low));count+=1
        assert m.joules(m.replay(cfg))==min(values)
        minimum=min(values) if minimum is None else min(minimum,min(values))
    assert count==len(schedules)
    result=m.search(base,set(domain),base,until,101,lambda *args:None)
    assert result["status"]=="EXACT_REFERENCE" and Q(result["best_reference_J"])==minimum
    # Select a feasible tight fixture, then demand an actual post deadline violation.
    origin=assemble(p,base)
    for i,r in enumerate(p.req):r["deadline_tick"]=p.finish(3*i+2,origin[3*i+2])
    m=Compact(p);example=None
    for i in range(m.n):
        if example:break
        for op in m.ops:
            if op==base[i]:continue
            target=((i,op),);v=base.copy();v[i]=op
            if not virtual(m,v)[0]:continue
            ids,h,trace=neighborhood(m,base,target,"Proposed",12,until)
            if any(t["selected"] is not None for t in trace):
                ab,ab_hint,_=neighborhood(m,base,target,"AB",12,until)
                assert len(ids)==len(ab)==12 and h==ab_hint
                example=dict(target=target,trace=trace,ordinary=sorted(ab),proposed=sorted(ids));break
    assert example and perf_counter()<until
    write(ROOT/"finite_gate.json",dict(utc=utc(),status="PASS",freeze=git("rev-parse","HEAD"),
         configuration_leaves=169,physical_schedules=count,exact_reference_J=str(minimum),search=result,
         feedback_fixture=example,elapsed_s=perf_counter()-begin))
if __name__=="__main__":main()
