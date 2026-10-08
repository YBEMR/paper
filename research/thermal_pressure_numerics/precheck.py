"""Targeted numerical fixtures; no A/B energy diagnosis or parameter search."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import argparse
import json
import platform
import time
import traceback
import scaled as s
a=s.a


def run(dest):
    dest.mkdir(parents=True,exist_ok=False)
    records=[]; artifacts={}; hashes=s.identities()
    def check(name,ok,detail=None): records.append(dict(name=name,passed=bool(ok),detail=detail))
    def contains(bounds,point): return D(bounds[0])<=point<=D(bounds[1])
    def overlap(x,y): return max(D(x[0]),D(y[0]))<=min(D(x[1]),D(y[1]))
    def timed(name,p,initial,segments,acc,legacy=False,budget=None):
        budget=budget or a.v2.Budget(seconds=20)
        start=time.monotonic()
        r=(a.thermal if legacy else s.thermal)(p,initial,segments,acc,budget)
        artifacts[name]=dict(result=r,elapsed_s=time.monotonic()-start,panels=budget.panels,refinements=budget.refinements)
        return r
    def section(name,fn):
        try: fn()
        except Exception: check(name,False,traceback.format_exc())
    x=a.load(); p=x['problem']['platform']; acc=x['problem']['evaluation']['accuracy']
    idle=dict(start_us=F(0),end_us=F(80000),base_W=[D('.2'),D('.3')],leak_W_per_K=[D('.002'),D('.002')],activity_W=[F(0),F(0)])

    def algebra():
        m=a.v1.coeff_matrix(p,idle); mm=s.transform(m); ds=s.scales(4)
        # Independent exact rational coefficients of this affine system.
        exact=[[F(-103,20),F(1,4),F(0),F(10)],
               [F(250),F(-900),F(0),F(15000)],
               [F(1,500),F(1,500),F(0),F(0)], [F(0)]*4]
        check('similarity_exact_coefficients',all(F(mm[i][j].lo)<=exact[i][j]*ds[j]/ds[i]<=F(mm[i][j].hi) for i in range(4) for j in range(4)))
        check('idle_step_count_416',s.panel_count(m,F(8,100))==416)
        check('original_globals_unmodified',a.v1.thermal.__globals__['TaylorPanel'] is not s.ScaledPanel)
        z=[s.I(5),s.I(5),s.I(0),s.I(1)]; h=F(1,100000)
        pp=s.ScaledPanel(m,z,h)
        check('initial_coordinates_restored',all(v.lo<=q.lo<=q.hi<=v.hi for v,q in zip(pp.value(0),z)))
        old=a.v1.TaylorPanel(m,z,h)
        check('short_panel_endpoint_overlap',all(overlap(v.data(),w.data()) for v,w in zip(pp.value(h),old.value(h))))
        check('short_panel_image_overlap',all(overlap(v.data(),w.data()) for v,w in zip(pp.value(0,h),old.value(0,h))))

    def coupled():
        r=timed('coupled_idle_80ms',p,[30,30],[idle],acc)
        check('coupled_complete_precision',r['complete'] and r['precision_met'],r.get('reason'))
        if not r['complete']: return
        check('coupled_safe',r['status']=='safe')
        # Independent closed form: exp(A t) via the two eigenvalues; integral
        # = steady*t + A^-1(exp(A t)-I)(theta0-steady).
        with localcontext() as ctx:
            ctx.prec=75
            mat=[[D('-5.15'),D('.25')],[D(250),D(-900)]]
            forcing=[D(10),D(15000)]; det=mat[0][0]*mat[1][1]-mat[0][1]*mat[1][0]
            def solve(v): return [(mat[1][1]*v[0]-mat[0][1]*v[1])/det,(-mat[1][0]*v[0]+mat[0][0]*v[1])/det]
            steady=solve([-v for v in forcing]); v=[D(5)-z for z in steady]; t=D('.08')
            trace=mat[0][0]+mat[1][1]; gap=((mat[0][0]-mat[1][1])**2+4*mat[0][1]*mat[1][0]).sqrt()
            l1=(trace+gap)/2; l2=(trace-gap)/2; e2=(l2*t).exp(); coef=((l1*t).exp()-e2)/gap
            ev=[e2*v[i]+coef*(sum(mat[i][j]*v[j] for j in range(2))-l2*v[i]) for i in range(2)]
            ends=[D(25)+steady[i]+ev[i] for i in range(2)]
            corr=solve([ev[i]-v[i] for i in range(2)])
            integrals=[steady[i]*t+corr[i] for i in range(2)]
            energy=D(1)*t+D('.002')*sum(integrals)
            check('coupled_analytic_endpoint',all(contains(b,z) for b,z in zip(r['end_temperature_C'],ends)))
            check('coupled_analytic_energy',contains(r['energy_J'],energy))
        short=deepcopy(idle); short['end_us']=F(1250)
        old=timed('legacy_coupled_1250us',p,[30,30],[short],acc,legacy=True)
        new=timed('scaled_coupled_1250us',p,[30,30],[short],acc)
        check('legacy_new_complete',old['complete'] and new['complete'])
        if old['complete'] and new['complete']:
            for key in ['peak_C','end_temperature_C']:
                check('legacy_new_'+key,all(overlap(v,w) for v,w in zip(old[key],new[key])))
            check('legacy_new_energy',overlap(old['energy_J'],new['energy_J']))
        # Same unchanged idle coefficients, additional numerical boundary only.
        seg1=deepcopy(idle);seg1['end_us']=F(40000)
        seg2=deepcopy(idle);seg2['start_us']=F(40000)
        rr=timed('split_idle_80ms',p,[30,30],[seg1,seg2],acc)
        check('split_complete',rr['complete'] and rr['precision_met'])
        if rr['complete']:
            check('split_invariance_energy',overlap(rr['energy_J'],r['energy_J']))
            check('split_invariance_temperature',all(overlap(v,w) for v,w in zip(rr['end_temperature_C'],r['end_temperature_C'])))

    def interior():
        pp=dict(nodes=['X','Y'],C_J_per_K=[1,1],G_W_per_K=[[2,-1],[-1,2]],ambient_C=25,leak_reference_C=25,valid_temperature_C=[0,100],temperature_limit_C=[80,80],external_power_W=0)
        seg=dict(start_us=F(0),end_us=F(1000000),base_W=[0,0],leak_W_per_K=[0,0],activity_W=[F(0),F(0)])
        r=timed('interior_peak',pp,[55,25],[seg],acc)
        check('interior_complete',r['complete'] and r['precision_met'])
        if r['complete']:
            with localcontext() as ctx:
                ctx.prec=75
                peak=D(25)+D(10)/D(3).sqrt()
                check('internal_peak_analytic',contains(r['peak_C'][1],peak))
                check('peak_exceeds_endpoints',D(r['peak_C'][1][0])>D(r['end_temperature_C'][1][1]))
        # Same fixture with a limit below its internal peak; endpoints alone
        # would pass at Y. This is a precheck fixture, not a TP-1 parameter change.
        pp['temperature_limit_C']=[80,30]
        r=timed('interior_violation',pp,[55,25],[seg],acc)
        check('internal_violation_detected',r['status']=='violation' and any(v['node']=='Y' for v in r['known_violations']))

    def interrupted():
        class Stop(a.v2.Budget):
            def panel(self): raise a.v1.Exhausted('injected_budget_expiry')
        r=timed('interrupted_initial_violation',p,[30,81],[idle],acc,budget=Stop(seconds=20))
        check('committed_violation_retained',r['status']=='violation' and not r['complete'] and 'energy_J' not in r and bool(r['known_violations']))
        r=timed('interrupted_no_witness',p,[30,30],[idle],acc,budget=Stop(seconds=20))
        check('interruption_unresolved_no_energy',r['status']=='unresolved' and not r['complete'] and 'energy_J' not in r)

    def changed_fragments():
        # Synthetic pulse then idle/workpoint change. No mode, request, or U1.
        pulse=deepcopy(idle);pulse['end_us']=F(1250);pulse['activity_W']=[F(0),F(1)]
        tail=deepcopy(idle);tail['start_us']=F(1250);tail['base_W'][0]=D('.15');tail['leak_W_per_K'][0]=D('.001')
        r=timed('pulse_changed_OPP_tail',p,[30,30],[pulse,tail],acc)
        check('changed_fragments_complete',r['complete'] and r['precision_met'])
        if not r['complete']: return
        with localcontext() as ctx:
            ctx.prec=75
            temps=[D(30),D(30)]; energy=D(0)
            for seg in [pulse,tail]:
                cv=p['C_J_per_K'];g=p['G_W_per_K'];lam=seg['leak_W_per_K']
                mat=[[(-g[i][j]+(lam[i] if i==j else 0))/cv[i] for j in range(2)] for i in range(2)]
                forcing=[(seg['base_W'][i]+D(seg['activity_W'][i].numerator)/D(seg['activity_W'][i].denominator))/cv[i] for i in range(2)]
                det=mat[0][0]*mat[1][1]-mat[0][1]*mat[1][0]
                def solve(v):return [(mat[1][1]*v[0]-mat[0][1]*v[1])/det,(-mat[1][0]*v[0]+mat[0][0]*v[1])/det]
                steady=solve([-v for v in forcing]);v=[temps[i]-25-steady[i] for i in range(2)]
                t=D((seg['end_us']-seg['start_us']).numerator)/D((seg['end_us']-seg['start_us']).denominator)/1000000
                trace=mat[0][0]+mat[1][1];gap=((mat[0][0]-mat[1][1])**2+4*mat[0][1]*mat[1][0]).sqrt()
                l1=(trace+gap)/2;l2=(trace-gap)/2;e2=(l2*t).exp();coef=((l1*t).exp()-e2)/gap
                ev=[e2*v[i]+coef*(sum(mat[i][j]*v[j] for j in range(2))-l2*v[i]) for i in range(2)]
                corr=solve([ev[i]-v[i] for i in range(2)])
                integral=[steady[i]*t+corr[i] for i in range(2)]
                energy+=(sum(seg['base_W'])+sum(D(q.numerator)/D(q.denominator) for q in seg['activity_W'])+p['external_power_W'])*t+sum(lam[i]*integral[i] for i in range(2))
                temps=[25+steady[i]+ev[i] for i in range(2)]
            check('changed_fragments_analytic_T',all(contains(b,v) for b,v in zip(r['end_temperature_C'],temps)))
            check('changed_fragments_analytic_E',contains(r['energy_J'],energy))
        bounds=r['activity_by_node_J'][1]
        check('activity_energy_encloses_exact',contains(bounds,D('.00125')) and D(bounds[1])-D(bounds[0])<=D(acc['energy_enclosure_width_J']))
        # Per-call state-free cache; different h and matrices have different keys.
        cache={}; state=[s.I(5),s.I(5),s.I(0),s.I(1)]; h=F(1,100000)
        one=s.ScaledPanel(a.v1.coeff_matrix(p,pulse),state,h,cache);v=one.value(h)
        count=len(cache)
        changed=s.ScaledPanel(a.v1.coeff_matrix(p,tail),state,h,cache);changed.value(h)
        check('cache_matrix_identity',len(cache)>count)
        count=len(cache);s.ScaledPanel(a.v1.coeff_matrix(p,pulse),state,2*h,cache).value(2*h)
        check('cache_duration_identity',len(cache)>count)
        count=len(cache); state2=[s.I(7),s.I(8),s.I(0),s.I(1)]
        reused=s.ScaledPanel(a.v1.coeff_matrix(p,pulse),state2,h,cache).value(h)
        check('cache_reuses_operator_not_state',len(cache)==count and reused[0].lo>v[0].hi)

    for name,fn in [('algebra',algebra),('coupled',coupled),('interior',interior),('interruption',interrupted),('changed_fragments',changed_fragments)]: section(name,fn)
    check('hashes_unchanged',hashes==s.identities())
    out=dict(stage='K.29',passed=all(r['passed'] for r in records),checks=records,artifacts=artifacts,hashes=hashes,
             python=platform.python_version(),scope='numerical fixtures only',formal_diagnostic_runs=0)
    a.old.write(dest/'result.json',out)
    print(f"{sum(r['passed'] for r in records)}/{len(records)} passed")
    for r in records:
        if not r['passed']: print(r['name'],r['detail'])
    for k,v in artifacts.items(): print(k,v['elapsed_s'],v['panels'],v['result']['status'])
    return out['passed']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    raise SystemExit(0 if run(Path(args.out)) else 1)
