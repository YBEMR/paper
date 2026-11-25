"""Enumerate finite physical schedules both ways, including unseeded time envelopes."""
import itertools
from g1io import *
from full_cp import Full,cp,solver
from thermal_bound import exact_parts,PJ,proof
from model import Invalid
from validation import subjects,masks,sig
from construct import reference,assemble,idle_plan
from math import floor

def history():
    import verify_core as v
    from validation import exhaustive
    import validation
    # Legacy fixture writers are redirected to G1 before exercising them.
    folder=OUT/"preflight"/"legacy"
    v.write=lambda name,data:write(folder/name,data)
    v.table=lambda name,data:table(folder/name,data)
    validation.save=lambda name,data:write(folder/name,data)
    expected={r["fixture"]:r for r in v.csv_rows(E1/"e0/equivalence.csv")}
    for name,args in subjects(problem("D1")).items():
        res=exhaustive(name,*args)
        assert res["set_digest"]==expected[name]["set_digest"]
    v.finite()
    v.interface()
    return dict(E0_E1=len(expected),E2a=read(folder/"validation/finite_gate.json"),rights=15)

def fixtures(p):
    # Unmodified P1 profiles, one A request. Every integer start in a tight
    # deadline window and every mode in the stated miniature domain is enumerated.
    import copy
    mini=copy.copy(p)
    mini.req=[dict(p.req[0],release_tick=0,deadline_tick=447,deadline_ms=Q(447,10))]
    mini.n=3
    mini.options=[((0,0),(1,0)),((3,0),),((0,0),(1,0))]
    mini.kinds=p.kinds[:3]
    mini.horizon=455
    mini.boundaries=[200]
    seed=[(0,0,0),(3,0,28),(1,0,424)]
    yield "tight_all_ticks",mini,seed,None
    # Two requests may swap devices/CPU order and move over 500 ticks.
    p2,seed,_,_=subjects(p)["mapping_order"]
    choices={i:[row] for i,row in enumerate(seed)}
    choices[0]=[(0,0,0),(1,0,37)]
    choices[1]=[(u,k,t) for u,k in [(2,9),(3,2)] for t in (100,440,800)]
    choices[2]=[(0,0,900),(1,1,1300)]
    choices[4]=[(u,k,t) for u,k in [(2,9),(3,2)] for t in (100,440,755)]
    yield "late_move_shared_cpu",p2,seed,choices

def full_check(label,p,rows,choices,method):
    core=Full(p,(rows,frozenset()),method,choices=choices,objective=False)
    oracle=set()
    if choices is None:
        # Derive candidate starts by independent finish-chain simulation.
        def generate(i,partial):
            if i==len(rows):
                yield partial
                return
            start=p.finish(i-1,partial[-1]) if i else p.req[0]["release_tick"]
            for u,k in p.options[i]:
                for t in range(start,p.req[0]["deadline_tick"]-p.dur(i,u,k)+1):
                    yield from generate(i+1,[*partial,(u,k,t)])
        seq=generate(0,[])
    else:
        seq=itertools.product(*(choices[i] for i in range(p.n)))
    for rs in seq:
        try:
            _,sw=independent_events(p,rs,set())
        except Invalid: continue
        # Independent set of meaningful right endpoints; tolerate all redundant bits.
        keys=[(d,i) for d in range(3) for i in [*range(p.n),-1]
              if (i==-1 or common.DOM[rs[i][0]]==d) and any(k>0 and common.DOM[u]==d for u,k,_ in rs)]
        for low in masks(keys):
            try:_,sw=independent_events(p,rs,low)
            except Invalid:continue
            oracle.add(sig(rs,sw))
    seen=set()
    worst=Q(0)
    class Visit(cp.CpSolverSolutionCallback):
        def on_solution_callback(self):
            nonlocal worst
            plan=core.plan(self)
            sw=core.switches(self)
            _,ind=independent_events(p,*plan)
            assert sw==ind
            key=sig(plan[0],sw)
            seen.add(key)
            exact=exact_parts(p,plan,method)
            for k,val in core.parts.items():
                diff=exact[k]-Q(self.value(val),PJ)
                assert diff>=0 and diff<=Q(3*p.horizon+2*p.n,PJ),(k,diff)
            worst=max(worst,sum(exact.values())-Q(self.value(core.total),PJ))
    sl=solver(60)
    sl.parameters.enumerate_all_solutions=True
    st=sl.solve(core.m,Visit())
    assert st==cp.OPTIMAL and oracle==seen and seen,(label,sl.status_name(st),len(oracle),len(seen))
    return dict(fixture=label,method=method,physical=len(seen),digest=sha(raw(sorted(seen))),error_pJ=str(worst*PJ))

def preflight():
    # Import and compile the original thermal kernel within the correctness budget.
    p=problem("S16")
    origin=assemble(p,reference(p,"B0"))
    evaluate(p,idle_plan(p,origin),cert=True)
    data={"legacy":history(),"barriers":{},"full":[]}
    for n in ("S16","S32","S80"):
        prob=problem(n)
        data["barriers"][n]={"C0":proof(prob,(35,)*4,(0,)*4),"C1":proof(prob)}
        assert data["barriers"][n]["C0"]["passed"]
    for label,sub,seed,choices in fixtures(p):
        for method in ("C0","C1"):
            if method=="C1" and not data["barriers"]["S16"]["C1"]["passed"]:continue
            data["full"].append(full_check(label,sub,seed,choices,method))
    write(OUT/"preflight"/"gates.json",data)
