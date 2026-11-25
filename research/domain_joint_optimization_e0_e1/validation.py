import copy,itertools,math
import numpy as np
from common import *
from compact import Layout,Illegal,permissions
from master import Master,cp,solver
from model import Problem,transitions,independent_events,Invalid
from heat import integrate,evaluate
from inputs import restore

def fixture(template,kinds,base,edits,controls,boundary,release=None,deadline=None):
    p=copy.copy(template);p.req=[];p.kinds=[];p.options=[]
    for j,typ in enumerate(kinds):
        r=(release or {}).get(j,Q(0));d=(deadline or {}).get(j,Q(220))
        p.req.append(dict(kind=typ,release_tick=math.ceil(r*10),deadline_tick=math.floor(d*10),deadline_ms=d,release_ms=r))
        for stage in ("pre","main","post"):
            name=typ+"."+stage;p.kinds.append(name)
            p.options.append(tuple((u,k) for n,u,k in p.profile if n==name))
    p.n=len(base);p.horizon=5200;p.boundaries=[boundary]
    return p,base,edits,controls

def subjects(p):
    return {
       "mapping_order":fixture(p,"AB",[(0,0,0),(2,9,100),(0,0,900),(1,0,0),(2,9,440),(1,0,920)],
            {1:[(u,k,t) for u,k in [(2,9),(3,2)] for t in (100,440)],
             4:[(u,k,t) for u,k in [(2,9),(3,2)] for t in (100,440)]},[(1,4),(1,-1),(2,-1)],320),
       "switch_boundary_idle":fixture(p,"AB",[(0,0,0),(2,5,300),(0,0,900),(1,0,0),(2,9,478),(1,0,920)],
            {4:[(2,k,t) for k in (0,5,9) for t in (473,477,478,482,483,495)]},[(1,1),(1,4),(1,-1)],475),
       "shared_nested_tie":fixture(p,"ABA",[(0,0,1000),(2,9,1100),(0,0,1900),(1,0,0),(3,2,120),(1,0,1010),
            (1,0,1033),(3,2,1200),(1,0,1950)],{5:[(1,k,t) for k in (0,1) for t in (1000,1010)],
            6:[(1,k,t) for k in (0,1,2) for t in (1021,1025,1028,1032,1033,1040)]},[(0,5),(0,6),(0,2)],1024),
       "rational_release_deadline":fixture(p,"A",[(0,0,151),(2,0,179),(1,0,517)],
            {0:[(0,0,t) for t in (150,151,152)],1:[(2,0,t) for t in (178,179,180)],2:[(1,0,t) for t in (517,518,519)]},
            [(1,1),(0,2)],300,{0:Q(301,20)},{0:Q(1063,20)})}

def masks(keys):
    for bits in itertools.product((False,True),repeat=len(keys)):
        yield frozenset(k for k,b in zip(keys,bits) if b)
def sig(rows,sw):return (tuple(rows),tuple(map(tuple,sw)))
def common_grid(a,b):
    points=sorted(set(a[:,0])|set(b[:,0])|{a[-1,1],b[-1,1]})
    def expand(ev):
        ix=np.searchsorted(ev[:,0],points[:-1],side="right")-1
        return np.column_stack((points[:-1],points[1:],ev[ix,2:]))
    return expand(a),expand(b)

def compare(p,rows,mask,proof=False):
    from diagnostic import physical
    lay=Layout(p,rows);compact=lay.events(mask);ref,sw=independent_events(p,rows,mask)
    assert lay.switches(mask)==sw
    aa,bb=common_grid(compact,ref);assert np.array_equal(aa,bb)
    exact=lay.components(mask)
    oracle=physical(p,(rows,mask))
    for k,v in exact.items():assert v==Q(oracle[{"switch":"switch_J","external":"external_J","activity":"activity_J","base":"base_J"}[k]])
    hold=sum(lay.components(()) .values());assert hold+sum(lay.gap_delta(k,35) for k in mask)==sum(exact.values())
    a=integrate(compact,p.initial,p.G,p.cap,float(p.ta),np.array([],np.int64),True)
    b=evaluate(p,(rows,mask),cert=True)
    assert max(a[0]-a[6],b["E_bounds"][0])<=min(a[0]+a[6],b["E_bounds"][1])
    assert all(max(x,z)<=min(y,w) for x,y,z,w in zip(a[1],a[2],b["peak_lo"],b["peak_hi"]))
    state=("OUT_OF_MODEL" if max(a[1])>100 or min(a[4])<20 else
           "SAFE" if min(a[3])>=20 and max(a[2])<=80 and max(a[2])-max(a[1])<=.001 and a[6]<=1e-6 else
           "HOT" if max(a[1])>80 and max(a[2])<=100 and min(a[3])>=20 and max(a[2])-max(a[1])<=.001 and a[6]<=1e-6 else "UNRESOLVED")
    assert state==b["status"]
    return dict(events=len(aa),switches=len(sw),exact_E35_J=str(sum(exact.values())),
                energy_difference_J=abs(a[0]-b["E_J"]),peak_difference_K=abs(max(a[1])-max(b["peak_lo"])),status=state,energy=b["E_bounds"])

def exhaustive(name,p,base,choices,flags):
    ids=list(choices);theory=math.prod(len(v) for v in choices.values())*2**len(flags)
    assert theory<=50000
    reference={};accepted=0
    for vals in itertools.product(*(choices[i] for i in ids)):
        rs=base.copy()
        for i,r in zip(ids,vals):rs[i]=r
        for low in masks(flags):
            try:_,sw,_=transitions(p,rs,low)
            except Invalid:continue
            accepted+=1;reference[sig(rs,sw)]=1
    master=Master(p,base,ids,3,choices=choices)
    found={};stats=[]
    class Visit(cp.CpSolverSolutionCallback):
        def on_solution_callback(self):
            rs=master.rows(self);lay=Layout(p,rs)
            for low in masks([key for key in flags if key in lay.flex]):
                k=sig(rs,lay.switches(low))
                found[k]=(rs,low)
    sl=solver(30);sl.parameters.enumerate_all_solutions=True
    state=sl.solve(master.m,Visit())
    assert state in (cp.OPTIMAL,cp.INFEASIBLE)
    if set(found)!=set(reference):
        missing=set(reference)-set(found);extra=set(found)-set(reference)
        witness=min(missing or extra,key=lambda x:(sum(a!=b for a,b in zip(x[0],base)),len(x[1]),x))
        save("e0/counterexample.json",dict(fixture=name,missing=bool(missing),witness=witness));raise AssertionError("legal sets differ")
    assert 0<len(found)<=accepted<theory
    for k,(rs,mask) in found.items():
        try:stats.append(compare(p,rs,mask))
        except Exception:
            save("e0/counterexample.json",dict(fixture=name,rows=rs,low=sorted(mask)));raise
    return dict(fixture=name,raw_candidates=theory,original_raw_valid=accepted,oracle_physical=len(reference),
        compact_physical=len(found),set_digest=sha(raw(sorted(reference))),set_equal=True,
        max_energy_error_J=max(x["energy_difference_J"] for x in stats),max_peak_error_K=max(x["peak_difference_K"] for x in stats))

def membership(p,baseline,plan,region,g):
    rows,low=plan;orig=baseline[0];ids=region["ids"]
    if any(a!=b for j,(a,b) in enumerate(zip(rows,orig)) if j not in ids):return False
    lay=Layout(p,rows);nl=lay.normalize(low);fixed,free=permissions(lay,region)
    if not fixed<=nl<=fixed.union(free):return False
    m=Master(p,orig,ids,g,pin={i:rows[i] for i in ids})
    st=solver(8).solve(m.m)
    if st not in (cp.OPTIMAL,cp.FEASIBLE,cp.INFEASIBLE):raise RuntimeError("membership not proved")
    return st!=cp.INFEASIBLE
def e0():
    # Read-only access to the previous exact energy accountant.
    sys.path.append(str(FOLLOW))
    rows=[exhaustive(n,*f) for n,f in subjects(Problem("D1")).items()]
    table("e0/equivalence.csv",rows)
    regions=read("regions.json")["regions"];replays=[]
    for case,hist in [("D1",False),("D2",False),("D3",False),("D1",True),("D2",True)]:
        p=Problem(case);key,pl=archived(case,hist);_,base=archived(case)
        r=restore(regions[case if case!="D3" else "R1"])
        lay=Layout(p,pl[0]);m=compare(p,pl[0],lay.normalize(pl[1]))
        prior=(read(FOLLOW/"results/certificates"/(key+".json"))["continuous"] if hist else
               json.loads(gzip.decompress((OLD/"certificates"/(key+"_continuous.json.gz")).read_bytes()))["metrics"])
        assert prior["status"]==m["status"]=="SAFE" and m["energy"][0]<=prior["E_J"]<=m["energy"][1]
        belongs=[membership(p,base,pl,r,g) for g in range(4)]
        assert hist or all(belongs)
        replays.append(dict(case=case,historical=hist,sha=key,normalized_sha=sha(raw(obj(case,(pl[0],lay.normalize(pl[1]))))),
                            membership=belongs,**m))
    save("e0/replay.json",replays)
    save("e0/gate.json",dict(pass_E0=True,fixtures=len(rows),unique_test_schedules=sum(x["compact_physical"] for x in rows),replays=len(replays)))
