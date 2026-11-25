"""Independent old-builder enumeration, independent quantization, and fixed assignment tests."""
import itertools,math
from assets_e2 import *
from reference_objective import Core,Access,PJ,SW,error_bound
from master import solver,cp
from model import Invalid
from validation import subjects,masks,sig,common_grid
sys.path.append(str(FOLLOW))
from diagnostic import physical

def integer_parts(p,rows,sw):
    tickrate={(d,k):round(v[0]*PJ/10000) for (d,k),v in p.domain_idle.items()}
    dwell=0
    for d in range(3):
        t=f=0
        for end,k in [(b,new) for a,b,h,old,new in sw if h==d]+[(p.horizon,0)]:
            dwell+=(end-t)*tickrate[d,f];t=end;f=k
    add=0
    for i,(u,k,s) in enumerate(rows):
        b,_,v,_=p.exact[p.kinds[i],u,k]
        add+=round((v-b)*p.dur(i,u,k)*PJ/10000)
    return dict(activity=add,base=dwell,switch=SW*len(sw),external=p.horizon*30_000_000)

def check(p,plan,parts,sw,oracle=False):
    rs,low=plan;lay=Layout(p,rs)
    _,original,_=transitions(p,rs,low)
    assert sw==original==lay.switches(low)
    exact=lay.components(low);integer=integer_parts(p,rs,original)
    assert parts==integer,(parts,integer)
    if oracle:
        independent=physical(p,plan)
        assert all(v==Q(independent[k+"_J"]) for k,v in exact.items())
    diff=abs(Q(sum(parts.values()),PJ)-sum(exact.values()))
    assert diff<=error_bound(p)
    return exact,diff

def fixtures():
    orig=subjects(Problem("D1"));alltests=orig.copy()
    p,b,c,f=orig["switch_boundary_idle"]
    alltests["same_activity_gap_controls"]=(p,b,{4:[(2,9,483),(2,9,495)]},f)
    p,b,c,f=orig["shared_nested_tie"]
    alltests["cpu_union_length"]=(p,b,{5:[(1,0,1000),(1,0,1035)],6:[(1,0,1060)]},[])
    p,b,c,f=orig["mapping_order"]
    alltests["two_domains_migration"]=(p,b,{1:[(2,9,100),(3,2,100)]},[(1,4),(1,-1),(2,-1)])
    p,b,c,f=orig["switch_boundary_idle"]
    alltests["new_fixed_neighbor_gap"]=(p,b,{1:[(2,5,285),(2,5,300),(2,5,310)]},[(1,4),(1,-1)])
    return alltests

def finite():
    expected={z["fixture"]:z for z in csv_rows(E1/"e0/equivalence.csv")}
    summary=[]
    for name,(p,b,c,flags) in fixtures().items():
        count=math.prod(map(len,c.values()))*2**len(flags);assert count<=50000
        oracle={};ids=list(c)
        for selected in itertools.product(*(c[i] for i in ids)):
            rows=b.copy()
            for i,v in zip(ids,selected):rows[i]=v
            for low in masks(flags):
                try:_,sw,_=transitions(p,rows,low)
                except Invalid:continue
                oracle[sig(rows,sw)]=True
        core=Core(p,(b,set()),ids,3,choices=c,flags=flags,objective=False)
        found={};evidence=[];samples=[]
        class Visit(cp.CpSolverSolutionCallback):
            def on_solution_callback(self):
                plan=core.plan(self);sw=core.switches(self);parts={k:self.value(v) for k,v in core.parts.items()}
                inst=sig(plan[0],sw)
                try:
                    exact,err=check(p,plan,parts,sw,True)
                    for d,seq in enumerate(Layout(p,plan[0]).work):
                        front=0
                        for s,e,k,i in [*seq,(p.horizon,p.horizon,0,-1)]:
                            n,pre,old,bit,f,gap,h,count=core.states[d,i]
                            assert [self.value(v) for v in (pre,f,gap,h)]==[front,max(front,e),max(0,s-front),max(front,e)-max(front,s)]
                            front=max(front,e)
                except Exception:
                    write("validation/counterexample.json",dict(test=name,plan=obj(p.case,plan),parts=parts,switches=sw));raise
                found[inst]=(sum(parts.values()),sum(exact.values()))
                evidence.append(dict(id=sha(raw(inst)),integer=parts,exact={k:str(v) for k,v in exact.items()},error_J=str(err)))
                samples.append((plan,sw,exact))
        sl=solver(80);sl.parameters.enumerate_all_solutions=True;st=sl.solve(core.m,Visit())
        assert st==cp.OPTIMAL
        if found.keys()!=oracle.keys():
            delta=set(found)^set(oracle);item=min(delta,key=lambda x:(sum(a!=z for a,z in zip(x[0],b)),len(x[1]),x))
            write("validation/counterexample.json",dict(test=name,missing=item not in found,schedule=item));raise ValueError("legal sets differ")
        digest=sha(raw(sorted(oracle)));assert found and len(evidence)==len(found)
        if name in expected:assert expected[name]["set_digest"]==digest and int(expected[name]["compact_physical"])==len(found)
        def busy_cpu(rs):
            times=set()
            for i,(u,k,s) in enumerate(rs):
                if u<2:times.update(range(s,p.finish(i,rs[i])))
            return len(times)
        if name=="same_activity_gap_controls":
            assert len({x["activity"] for a,b0,x in samples})==1 and len({sum(x.values()) for a,b0,x in samples})>1
        if name=="cpu_union_length":assert len({busy_cpu(a[0]) for a,sw,x in samples})>1
        if name=="two_domains_migration":
            left=next(sw for (rs,lo),sw,x in samples if rs[1][0]==2 and not lo)
            right=next(sw for (rs,lo),sw,x in samples if rs[1][0]==3 and not lo)
            assert {v[2] for v in set(left)^set(right)}=={1,2}
        if name=="new_fixed_neighbor_gap":
            assert len({Layout(p,rs).gaps[1,4][0] for (rs,lo),_,_ in samples})>1
        core.m.minimize(core.total);opt=solver(40);assert opt.solve(core.m)==cp.OPTIMAL
        key=sig(core.plan(opt)[0],core.switches(opt));pi,qi=found[key]
        int_min=min(a for a,q in found.values());qmin=min(q for a,q in found.values())
        assert pi==int_min
        # Exhaustion resolves every rounded tie even if CP picks a different rational minimizer.
        tied={q for a,q in found.values() if a==int_min}
        write("validation/finite/"+name+".json",dict(physical=evidence,rational_minimizers=[sha(raw(k)) for k,v in found.items() if v[1]==qmin],
              cp_winner=sha(raw(key)),rounded_min_rational_values=sorted(map(str,tied))))
        summary.append(dict(fixture=name,theory=count,oracle=len(oracle),CP=len(found),hash=digest,
                 integer_optimum_pJ=int_min,CP_winner_exact_J=str(qi),exact_optimum_J=str(qmin),same_optimum=qi==qmin,
                 max_abs_error_J=float(max(Q(x["error_J"]) for x in evidence)),epsilon_J=float(error_bound(p))))
        table("validation/finite.csv",summary)
    write("validation/finite_gate.json",dict(passed=True,original=sum(x["CP"] for x in summary[:4]),additional=sum(x["CP"] for x in summary[4:])))

def fix(core,plan,seconds=12):
    rows,low=plan
    for var,value in core.assignment(plan):core.m.add(var==value)
    sl=solver(seconds);status=sl.solve(core.m)
    if status in (cp.OPTIMAL,cp.FEASIBLE):
        if core.plan(sl)!=(rows,frozenset(low)):return "OUTSIDE_FIXED_STATE",None
        return "ACCEPT",({k:sl.value(v) for k,v in core.parts.items()},core.switches(sl))
    if status==cp.INFEASIBLE:return "REJECT",None
    raise RuntimeError("fixed replay incomplete: "+sl.status_name(status))

def interface():
    cases=fixtures();p,b,c,flags=cases["mapping_order"];ids=list(c)
    # Genuine fixture witnesses; 100 and 440 can swap, and both accelerators support a migration.
    def test(label,rs,rights,ok,low=(),shape=None):
        w=Core(p,(b,set()),ids,3,choices=c,flags=flags,access=rights,pin={i:rs[i] for i in ids})
        status,_=fix(w,(rs,frozenset(low)));assert (status=="ACCEPT")==ok,(label,status)
        tests.append(dict(mode=label,expected=ok,status=status))
    def rights(sf,st,*,maps=None,order=None,insert=None,gaps=None,cap=None):
        return Access(set(sf),set(st),maps or {},order,insert,gaps,cap)
    tests=[];rev=b.copy();rev[1]=(2,9,440);rev[4]=(2,9,100)
    mig=b.copy();mig[1]=(3,2,100);both=mig.copy();both[4]=(3,2,440)
    allmap={i:{2,3} for i in ids}
    test("time_only_accept_swap",rev,rights([],ids),True)
    test("time_only_reject_mapping",mig,rights([],ids,maps=allmap),False)
    test("fixed_start_reject_swap",rev,rights([],[]),False)
    test("one_config_plus_coordination",mig,rights(ids,ids,maps=allmap,cap=1),True)
    test("one_config_reject_two",both,rights(ids,ids,maps=allmap,cap=1),False)
    test("multiple_configs",both,rights(ids,ids,maps=allmap,cap=2),True)
    test("fixed_order",rev,rights(ids,ids,order=set()),False)
    test("unreleased_pair",rev,rights(ids,ids,order={(2,1,3)}),False)
    test("released_pair",rev,rights(ids,ids,order={(2,1,4)}),True)
    test("selected_mapping",mig,rights([1],ids,maps={1:{2,3}}),True)
    test("other_mapping_locked",both,rights([1],ids,maps={1:{2,3}}),False)
    revmig=b.copy();revmig[1]=(3,2,440);revmig[4]=(3,2,100)
    test("target_insertion_locked",revmig,rights(ids,ids,maps=allmap,insert=set()),False)
    test("target_insertion_open",revmig,rights(ids,ids,maps=allmap,insert={(3,1,4)}),True)
    test("gap_unlocked",b,rights([],ids,gaps={(1,-1)}),True,[(1,-1)])
    test("gap_locked",b,rights([],ids,gaps=set()),False,[(1,-1)])
    table("validation/permissions.csv",tests)

def replay():
    records=[];traces={};sources=csv_rows(E1/"e1/endpoint_membership.csv");matrix={}
    for z in sources:
        name=z["region"];key=z["sha"]
        if name not in matrix:matrix[name]=region(name)
        p,base,r=matrix[name];plan=decode(json.loads(gzip.decompress((E1/"e1/plans"/(key+".json.gz")).read_bytes())))
        if key not in traces:
            k,m=certify(p,plan);assert k==key
            old=read(E1/"e1/certificates"/(key+".json"))["metrics"]
            assert all(m[j]==old[j] for j in ("E_bounds","peak_lo","peak_hi","status")) and m["status"]=="SAFE"
            with np.load(HERE/"certificates"/(key+".npz")) as data:
                ref=data["events"][:,:14]
            a,b0=common_grid(Layout(p,plan[0]).events(plan[1]),ref);assert np.array_equal(a,b0)
            traces[key]=m
        for g in range(4):
            expect=z["P"+str(g)]=="True"
            cached=next((x for x in records if x["region"]==name and x["sha"]==key and x["group"]==g),None)
            if cached:records.append(dict(cached,origin=z["origin"]));continue
            c=Core(p,base,r["ids"],g,region=r,pin={i:plan[0][i] for i in r["ids"]})
            status,out=fix(c,plan)
            if (status=="ACCEPT")!=expect:
                write("validation/counterexample.json",dict(region=name,sha=key,group=g,expected=expect,status=status))
                raise ValueError("replay membership differs")
            if expect:
                parts,sw=out;exact,err=check(p,plan,parts,sw,True)
            records.append(dict(region=name,origin=z["origin"],sha=key,group=g,expected=expect,status=status,
                       integer_pJ=sum(parts.values()) if expect else "",exact_J=str(sum(exact.values())) if expect else "",
                       peak_hi=max(traces[key]["peak_hi"]),E_bounds=traces[key]["E_bounds"]))
        table("validation/replay.csv",records)
    interface()
    write("validation/replay_gate.json",dict(passed=True,unique=len(traces),memberships=len(records),permissions=15))
