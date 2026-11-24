import math
import sys
from fractions import Fraction as Q
from itertools import product
import numpy as np
import sympy as sp
from profiles import CFG, ROOT, IDS, dump, table
from model import Problem, Invalid, construct, event_arrays, independent_events, transitions
from heat import evaluate, integrate


def exact_checks(p):
    G=sp.Matrix(CFG["G"])
    c=sp.diag(*(p.c*v for v in CFG["C"]))
    by_node=[[v for (kind,w,k),v in p.exact.items() if w==u] for u in range(4)]
    beta=[max(max(v[1],v[3]) for v in values) for values in by_node]
    power_min=min(b+s*(t-35) for vals in by_node for v in vals for b,s in (v[:2],v[2:]) for t in (20,100))
    gpu_margin=min(v[2]-v[0]+(v[3]-v[1])*(t-35) for v in by_node[2] for t in (20,100))
    comp=c.inv()*(-G+sp.diag(*beta))
    sums=list(comp*sp.ones(4,1))
    assert all(comp[i,j]>=0 for i in range(4) for j in range(4) if i!=j)
    assert max(sums)<0 and power_min>=0 and gpu_margin>=0
    s=sp.diag(*(next(v[1] for (kind,w,k),v in p.exact.items() if w==u and k==0) for u in range(4)))
    b=sp.Matrix([next(v[0] for (kind,w,k),v in p.exact.items() if w==u and k==0) for u in range(4)])
    entry=(G-s).inv()*(G*sp.ones(4,1)*p.ta+b-s*sp.ones(4,1)*35)
    assert max(abs(float(x)-y) for x,y in zip(entry,p.initial))<1e-12
    return dict(initial_C=list(map(str,entry)),power_min_W=str(power_min),GPU_busy_minus_idle_min_W=str(gpu_margin),
                maximum_slopes_W_K=list(map(str,beta)),comparison_matrix=[list(map(str,comp.row(i))) for i in range(4)],
                comparison_row_sums_per_s=list(map(str,sums)),all_states_stable=True,
                proof="非对角非负，实际矩阵逐元素小于等于公共矩阵，最大行和严格为负；切换为常量热源。")


def analytic_tests(p):
    sys.path.insert(0,str(ROOT.parent/"v1_evaluator"))
    from interval import I,TaylorPanel
    # Decoupled four-node single-node analytic test. Native integration and the
    # historical outward Decimal Taylor kernel independently enclose the same answer.
    dt=Q(1,10); rate=Q(1,2); power=Q(1); T0=30.; ta=25.
    exact=ta+2+(T0-ta-2)*math.exp(-float(rate*dt))
    # Homogeneous offset column exceeds panel norm for a 100-ms step; center at equilibrium.
    old=TaylorPanel([[I.rational(-rate)]],[I(3)],dt).value(dt)[0]+27
    ev=np.array([[0,1000,*[1.]*4,*[0.]*4,*[1.]*4]])
    out=integrate(ev,np.full(4,T0),np.eye(4)*.5,np.ones(4),ta,np.array([],np.int64),True)
    endpoint=out[10][-1,4];rad=out[10][-1,16]
    assert abs(exact-endpoint)<=rad and endpoint-rad<=float(old.lo)<=float(old.hi)<=endpoint+rad
    assert abs(out[0]-.43)<=out[6]
    # Fixed all-low steady solution including temperature-dependent idle energy.
    ev=np.array([[0,1000,*p.idle35,*p.idle_beta,*p.idle35]])
    fixed=integrate(ev,p.initial,p.G,p.cap,float(p.ta),np.array([],np.int64),True)
    steady=(np.sum(p.idle35+p.idle_beta*(p.initial-35))+.3)*.1
    assert max(abs(fixed[10][-1,4:8]-p.initial))<fixed[10][-1,16]
    assert abs(fixed[0]-steady)<=fixed[6]
    return dict(single_exact_C=exact,native_C=endpoint,old_interval_C=old.data(),energy_exact_J=.43,
                fixed_point_energy_J=steady,fixed_point_integral_J=fixed[0])


def run(save):
    details={}
    for case in IDS:
        p=Problem(case)
        table("instances/"+case+".csv",p.req)
        # Holdout materialization only. No holdout scheduling or thermal trajectory.
        details[case]=dict(requests=len(p.req),horizon_tick=p.horizon,**exact_checks(p))
        keys=[(r["stream"],r["release_ms"]) for r in p.req]
        assert len(set(keys))==len(keys)
        assert all(r["release_tick"]>=10*r["release_ms"] and r["release_tick"]-10*r["release_ms"]<1 for r in p.req)
    p=Problem("D0")
    cross=analytic_tests(p)
    low=construct(p,"low")
    cert=evaluate(p,low,cert=True)
    assert cert["status"]=="SAFE" and max(cert["peak_hi"])<=65
    # Replay the first complete physical D0 interval with the old Decimal kernel.
    from interval import I,TaylorPanel
    events,_,_=event_arrays(p,*low)
    first=events[0]
    dt=Q(int(first[1]-first[0]),10000)
    matrix=[[I(0) for _ in range(5)] for _ in range(5)]
    for u in range(4):
        active=next((i for i,(w,k,s) in enumerate(low[0]) if w==u and s==0),None)
        if active is None:
            b,sl=next(v[:2] for (stage,w,k),v in p.exact.items() if w==u and k==0)
        else: b,sl=p.exact[p.kinds[active],u,0][2:]
        for v in range(4):
            matrix[u][v]=I.rational(((sl if u==v else 0)-CFG["G"][u][v])/CFG["C"][u])
        matrix[u][4]=I.rational((b+(p.ta-35)*sl)/(100*CFG["C"][u]))
    initial=[I.rational((Q(t)-p.ta)/100) for t in details["D0"]["initial_C"]]+[I(1)]
    old4=[v*100+p.ta for v in TaylorPanel(matrix,initial,dt).value(dt)[:4]]
    fresh=integrate(events[:1],p.initial,p.G,p.cap,float(p.ta),np.array([],np.int64),True)[10][-1]
    assert all(fresh[4+u]-fresh[16]<=float(v.lo)<=float(v.hi)<=fresh[4+u]+fresh[16] for u,v in enumerate(old4))
    cross["D0_first_interval_old_C"]=[v.data() for v in old4]
    # At a first exit through face T_u=65, each neighboring T_j<=65.
    # A scalar invariant cube is sufficient for all full-low no-switch timelines.
    face=[max(v[2]+30*v[3] for (kind,w,k),v in p.exact.items() if w==u and k==0)-
          sum(CFG["G"][u])*(65-p.ta) for u in range(4)]
    assert max(face)<=0 and max(p.initial)<=65
    low_hash=save(p,low,cert)
    q=Problem("D1"); high=construct(q,"reference_high")
    ev,sw,edges=event_arrays(q,*high)
    verified,sw2=independent_events(q,*high)
    assert np.array_equal(ev,verified) and sw==sw2
    assert all(high[0][i][1] == (9 if high[0][i][0]==2 else 2) for i in range(q.n))
    hrows=[r for r in q.req if r["scene"]==1]
    demand=sum(min(q.dur(3*r["request"]+1,u,0) for u in (2,3)) for r in hrows)
    span=max(r["deadline_ms"] for r in hrows)-min(r["release_ms"] for r in hrows)
    cap=2*span*10
    assert demand>cap
    table("preflight/high_fixed_schedule.csv",[dict(stage=i,unit=u,opp=k,start_tick=t,end_tick=q.finish(i,row))
        for i,row in enumerate(high[0]) for u,k,t in [row]])
    dump("preflight/high_fixed_ledger.json",dict(switches=sw,resource_edges=edges))
    # Deliberately break release/dependency, CPU concurrency, switching and mutual exclusion.
    def rejects(rows):
        for validate in (lambda:transitions(q,rows,()),lambda:independent_events(q,rows,())):
            try: validate()
            except Invalid: continue
            raise AssertionError("invalid mutation accepted")
    rows=high[0].copy();u,k,t=rows[0];rows[0]=(u,k,-1);rejects(rows)
    rows=high[0].copy();u,k,t=rows[1];rows[1]=(u,k,0);rejects(rows)
    # Initial parallel pre stages, homofrequency legal / mixed OPP illegal.
    first=[i for i in range(q.n) if high[0][i][2]==5 and high[0][i][0]<2]
    assert len(first)==2
    i,j=first
    rows=high[0].copy();u,k,t=rows[j];rows[j]=(high[0][i][0],k,t);rejects(rows)
    rows=high[0].copy();rows[j]=(u,1,t);rejects(rows)
    rows=high[0].copy();rows[j]=(u,k,0);rejects(rows)
    early=frozenset((d,-1) for d in (0,1,2))
    t1,s1,_=event_arrays(q,high[0],early)
    t2,s2=independent_events(q,high[0],early)
    assert np.array_equal(t1,t2) and s1==s2
    sw_energy=0.
    for a,b,d,o,f in s1:
        members=(0,1) if d==0 else (d+1,)
        for line in t1[(t1[:,0]>=a)&(t1[:,1]<=b)]:
            sw_energy+=sum(line[2+u]-q.idle[u,o][0] for u in members)*(line[1]-line[0])/10000
    assert abs(sw_energy-len(s1)*.0015)<1e-12
    # Splitting a segment during a switch and during busy operation preserves the integral.
    fixed=evaluate(q,(high[0],early),cert=True)
    q.boundaries=sorted({2,7,*q.boundaries})
    split=evaluate(q,(high[0],early),cert=True)
    assert abs(split["E_J"]-fixed["E_J"])<1e-7
    dump("preflight/checks.json",dict(status="PASS",cases=details,thermal_tests=cross,D0_certificate=low_hash,
         D0_invariant_upper_C=65,D0_face_heat_W=list(map(str,face)),fixed_high_legal=True,
         high_main_min_demand_device_ms=str(Q(demand,10)),high_two_devices_available_ms=str(cap/10),
         high_release_deadline_span_ms=str(span),switch_extra_J=sw_energy,split_energy_difference_J=split["E_J"]-fixed["E_J"],
         illegal_mutations_rejected=5))
