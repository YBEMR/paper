"""Finite exact checks precede all performance replay. UNKNOWN is not a proof."""
import itertools,json
from fractions import Fraction as Q
from assets import ROOT,C,read,write
from bounded import CompactModel,graph,options,propagate,legal_assignment
from support import SupportModel,seeded,cp

class Fixture:
    def __init__(self,rows,choices,release=0,last=None):
        self.n=len(rows);self.horizon=3000;self.kinds=list(range(self.n));self.exact={}
        self.req=[dict(release_tick=release,deadline_tick=2000) for _ in range((self.n+2)//3)]
        if last is not None:self.req[-1]["deadline_tick"]=last
        self.choices=choices
        self.options=[]
        for i,(u,k,t) in enumerate(rows):
            levels=choices[i];self.options.append([(u,f) for f in levels])
            for f in levels:self.exact[i,u,f]=(Q(1),0,Q(4 if f==0 else 2),0)
    def dur(self,i,u,k):return self.choices[i][k]
    def finish(self,i,row):return row[2]+self.dur(i,*row[:2])

def cases():
    rows=[(0,0,10),(2,0,22),(0,0,40),(1,0,11),(3,0,22),(1,0,39)]
    ds=[{0:5,1:7},{0:4},{0:3},{0:5,1:6},{0:4},{0:3}]
    yield "shared_overlap_gap_and_exclusion",Fixture(rows,ds),rows,[0,3]
    rows=[(0,0,10),(2,0,70),(3,0,130)]
    yield "zero_envelope_config_and_fixed_edges",Fixture(rows,[{0:4},{0:5,1:6,2:7},{0:4}]),rows,[1]
    for n,i,forward in ((24,0,True),(24,23,False),(27,0,True),(27,26,False)):
        rows=[(2,0,100+10*j) for j in range(n)]
        ds=[({0:10,1:14} if j==i else {0:10}) for j in range(n)]
        yield ("forward" if forward else "reverse")+str(n),Fixture(rows,ds,100 if forward else 0,None if forward else 100+10*n),rows,[i]
    # The terminal boundary alone can force movement, without any changed resource order.
    rows=[(2,0,12),(0,0,35),(3,0,60)]
    p=Fixture(rows,[{0:6},{0:5},{0:6,1:12}],last=68);p.horizon=70
    yield "high_opp_terminal_boundary",p,rows,[2]
    # Baseline starts at zero; a non-low candidate must delay to allow its initial switch.
    rows=[(2,0,0),(0,0,30),(3,0,60)]
    yield "initial_opp_boundary",Fixture(rows,[{0:5,1:6},{0:5},{0:6}]),rows,[0]

def exact(p,rows,ids,model,fixed=None,exclude=None):
    if fixed is not None:
        for i,f in zip(ids,fixed):model.m.add(model.x[i][f]==1)
    if exclude is not None:model.m.add(sum(model.x[i][f] for i,f in zip(ids,exclude))<=len(ids)-1)
    sl=seeded(5,101);status=sl.solve(model.m);name=sl.status_name(status)
    if status==cp.INFEASIBLE:return dict(status=name,value=None)
    if status!=cp.OPTIMAL:raise RuntimeError("unresolved finite-domain verification: "+name)
    plan=model.decode(sl);levels=options(p,rows,ids)
    assert legal_assignment(p,rows,plan,ids,levels,graph(p,rows,levels))
    value=[sl.value(model.gain),sum(a!=b for a,b in zip(rows,plan)),sum(abs(a[2]-b[2]) for a,b in zip(rows,plan))]
    assert sl.value(sum(model.z))==value[1] and sl.value(sum(model.dev))==value[2]
    return dict(status=name,value=value,assignment=plan)

def finite():
    results=[]
    for name,p,rows,ids in cases():
        levels=options(p,rows,ids);edges=graph(p,rows,levels);a,b=propagate(p,rows,levels,edges)
        if name=="zero_envelope_config_and_fixed_edges":
            assert not any(a+b)
            other=rows.copy();other[1]=(2,1,71)
            assert legal_assignment(p,rows,other,ids,levels,edges) and not rows[1][2]-a[1]<=other[1][2]<=rows[1][2]+b[1]
        combos=list(itertools.product(*(levels[i] for i in ids)))
        probes=[(c,None) for c in combos]+[(None,None)]+[(None,c) for c in combos]
        for pin,ban in probes:
            f=SupportModel(p,rows,ids);k=CompactModel(p,rows,ids,levels,edges,a,b)
            old=exact(p,rows,ids,f,pin,ban);new=exact(p,rows,ids,k,pin,ban)
            out=dict(fixture=name,pinned=pin,excluded=ban,full=old,compact=new,early=a,late=b,
                     fixed_rows=rows,frequencies=levels,full_size=[len(f.m.proto.variables),len(f.m.proto.constraints)],
                     compact_size=[len(k.m.proto.variables),len(k.m.proto.constraints)])
            write(ROOT/"validation"/"last_check.json",out)
            if (old["status"],old["value"])!=(new["status"],new["value"]):
                write(ROOT/"validation"/"counterexample.json",out);raise AssertionError("objective or feasibility mismatch")
            if pin==(1,) and name in ("forward27","reverse27"):assert old["status"]=="INFEASIBLE"
            if pin==(1,) and name in ("forward24","reverse24"):assert old["value"][1]==24 and old["value"][2]>0
            if pin==(1,) and name=="zero_envelope_config_and_fixed_edges":assert old["value"][1:]==[1,0]
            results.append(out)
    write(ROOT/"validation"/"finite.json",results)

def run():
    import assets_e2,verify_core,structure
    assets_e2.HERE=verify_core.HERE=ROOT/"regression"
    verify_core.finite();verify_core.replay()
    assert all(read(ROOT/"regression"/"validation"/n)["passed"] for n in ("finite_gate.json","replay_gate.json"))
    finite()
    data=read(C/"samples.json")["structural"]
    actual=[structure.check_case(c) for c in data]
    assert [z["minimum"] for z in actual]==[42,14] and json.loads(json.dumps(actual))==read(C/"structure.json")
    write(ROOT/"validation"/"structure.json",actual)
    write(ROOT/"validation"/"gate.json",dict(passed=True,fixtures=8,probes=len(read(ROOT/"validation"/"finite.json")),structures=[[42,42],[22,14]]))
if __name__=="__main__":run()
