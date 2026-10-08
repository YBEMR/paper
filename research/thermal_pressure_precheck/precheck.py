"""Run implementation fixtures only; never execute the four U1 diagnostics."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import argparse
import platform
import time
import traceback
import adapter as a


def run(destination, contract_only=False):
    destination.mkdir(parents=True, exist_ok=False)  # Retain earlier failures.
    before = a.identities()
    checks, artifacts = [], {}
    def check(name, ok, details=None):
        checks.append(dict(name=name, passed=bool(ok), details=details))
    def attempt(name, fn):
        try:
            fn()
        except Exception:
            check(name, False, traceback.format_exc())

    def static():
        x = a.load()
        check('approved_overrides_only', True)
        rows = [o for m in x['problem']['modes'].values() for s in m['stages'] for o in s['options']]
        check('14_legal_responses_2_NPU_rows', len(rows)==14 and sum(o['unit']=='N0' for o in rows)==2)
        p = x['problem']['platform']; g = [[F(v) for v in row] for row in p['G_W_per_K']]
        check('passive_G_exact_determinant', g[0][0]*g[1][1]-g[0][1]**2 == F(2075,1000000))
        for lam, determinant in [(F(2,1000), F(1829,1000000)), (F(1,1000), F(1847,1000000))]:
            check('stable_leakage_'+str(lam), (g[0][0]-lam)*(g[1][1]-F(2,1000))-g[0][1]**2==determinant)
        expected = {'a_c':(5000,F(85,10000)), 'a_n':(3500,F(65,10000)),
                    'b_c':(3750,F(625,100000)), 'b_n':(3000,F(425,100000))}
        boundaries = {}
        for aa, bb in [('a_c','b_c'),('a_c','b_n'),('a_n','b_c'),('a_n','b_n')]:
            b = a.bundle(x,aa,bb); ident=aa+bb
            a.joint.validate_bundle(b,a.v2.Budget(seconds=20))
            for mode,label in [('A',aa),('B',bb)]:
                plan=b['candidate']['fixed_plans'][mode]
                energy=sum(F(s['duration_us'])*F(s['activity_increment_W'])/1000000 for s in plan['stages'])
                check(ident+'_'+label+'_span_activity', (a.v2.span(plan),energy)==expected[label])
            proof=a.proof_only(b); artifacts[ident+'_certificate']=proof
            check(ident+'_certificate_status',proof['status']==('sustained_safe' if ident=='a_cb_c' else 'unresolved'))
            check(ident+'_deadline',proof['deadline']['status']=='pass')
            check(ident+'_Cartesian_coverage',proof['thermal_certificate']['expected_count']==(4 if ident=='a_cb_c' else 8)
                  and proof['thermal_certificate']['coverage_complete'])
            check(ident+'_no_replay',proof['witness'] is None)
            for path in b['evaluation']['paths']:
                _,tr,_,state,_,_=a.old.path_parts(b,path)
                key=tr['id']; boundaries.setdefault(key,[]).append(state)
                check(ident+'_'+key+'_aligned',not state['unfinished'] and state['held_opps']=={'C0':'L','N0':'H'})
            for mode in ['A','B']:
                path=a.single_mode_path(b,mode)
                a.validate_probe(b,path)
                rows,requests,releases,failure=a.v1.expand(b['candidate'],path['trace'],a.v2.Budget(seconds=20))
                check(ident+'_'+mode+'_probe_entry',path['entry_state']['actual_mode']==mode and not failure)
                check(ident+'_'+mode+'_probe_releases',len(releases)==4 and max(F(r['release_us']) for r in requests)==60000)
                if ident=='a_cb_c' and mode=='B':
                    bad=deepcopy(path); bad['entry_state']['actual_mode']='A'
                    try: a.validate_probe(b,bad)
                    except a.v1.Invalid: check('mismatched_B_entry_rejected',True)
                    else: check('mismatched_B_entry_rejected',False)
        check('all_nonthermal_boundaries_equal',all(all(a.joint.digest(v)==a.joint.digest(vs[0]) for v in vs) for vs in boundaries.values()))
        b=a.bundle(x,'a_c','b_c'); c=a.joint.safety_input(b)
        c['fragment_superset'].pop()
        r=a.v2.verify(c,b['candidate']['semantics'])
        check('missing_fragment_is_unresolved',r['status']=='unresolved' and r['thermal_certificate']['reason']=='fragment_coverage_missing')
        b=a.bundle(x,'a_c','b_c'); c=a.joint.safety_input(b)
        extra=deepcopy(c['fragment_superset'][0]); extra['activity_W']['N0']=1; c['fragment_superset'].append(extra)
        r=a.v2.verify(c,b['candidate']['semantics'])
        check('extra_NPU_activity_not_ignored',r['status']=='unresolved')
        def stop(_):
            raise a.v1.Exhausted('injected_budget_expiry')
        r=a.v2.verify(a.joint.safety_input(b),b['candidate']['semantics'],a.v2.Budget(seconds=20,hook=stop))
        check('zero_budget_not_certificate',r['status']=='unresolved')

    def statuses():
        r=dict(input_status='valid',execution_status='valid',rankable_energy=True,
               thermal=dict(status='safe',complete=True,precision_met=True,energy_J=['1','1']))
        check('finite_safety_not_sustained',a.finite_evidence(r)['sustained_safety']=='not_inferred')
        check('certified_complete_aggregate',a.aggregate([r,r],[F(1,2),F(1,2)],'sustained_safe')['energy_J']==['1.0','1.0'])
        for kind in ['unresolved','violation','incomplete','deadline','imprecise']:
            bad=deepcopy(r); bad['rankable_energy']=False
            if kind in ['unresolved','violation']: bad['thermal']['status']=kind
            if kind=='violation': bad['thermal']['known_violations']=[{'node':'NPU','lower_temperature_C':'81'}]
            if kind=='incomplete': bad['thermal']['complete']=False
            if kind=='imprecise': bad['thermal']['precision_met']=False
            if kind=='deadline': bad.update(execution_status='deadline_violation',failure={'deadline_us':14000})
            check(kind+'_not_safe_score','safe_energy_J' not in a.finite_evidence(bad))
            check(kind+'_not_aggregate',a.aggregate([r,bad],[F(1,2),F(1,2)],'sustained_safe')['status']=='not_aggregable')
        check('unresolved_certificate_not_U',a.aggregate([r],[1],'unresolved')['status']=='not_aggregable')
        late=deepcopy(r); late['rankable_energy']=False; late['thermal'].update(complete=False,status='violation',known_violations=[{'node':'NPU','lower_temperature_C':'81'}])
        out=a.finite_evidence(late)
        check('committed_violation_survives_incomplete',out['status']=='violation' and bool(out['known_violations']) and 'diagnostic_energy_J' not in out)

    def numerical():
        # Independent one-node analytic fixture uses the fast NPU coefficients;
        # it is not an A/B schedule or a research counterexample.
        p=dict(nodes=['N'],C_J_per_K=[D('.00002')],G_W_per_K=[[D('.020')]],
               ambient_C=25,leak_reference_C=25,valid_temperature_C=[0,100],
               temperature_limit_C=[80],external_power_W=D('.5'))
        seg=dict(start_us=F(0),end_us=F(1250),base_W=[D('.3')],leak_W_per_K=[D('.002')],activity_W=[F(1)])
        acc=a.load()['problem']['evaluation']['accuracy']
        budget=a.v2.Budget(seconds=20)
        started=time.monotonic(); r=a.thermal(p,[30],[seg],acc,budget)
        artifacts['fast_scalar']=dict(result=r,elapsed_s=time.monotonic()-started,panels=budget.panels)
        check('fast_scalar_complete_precision',r['complete'] and r['precision_met'])
        if not r['complete']: return
        with localcontext() as ctx:
            ctx.prec=70
            t=D('.00125'); k=D(900); steady=D('1.3')/D('.018'); initial=D(5)
            end=D(25)+steady+(initial-steady)*(-k*t).exp()
            integral=steady*t+(initial-steady)*(1-(-k*t).exp())/k
            energy=D('1.8')*t+D('.002')*integral
            # 70-digit Decimal exp is a cross-check, not the source of the interval guarantee.
            check('fast_scalar_analytic_T',D(r['end_temperature_C'][0][0])<=end<=D(r['end_temperature_C'][0][1]))
            check('fast_scalar_analytic_E',D(r['energy_J'][0])<=energy<=D(r['energy_J'][1]))
        check('energy_double_count',a.v1.I(*r['energy_J']).lo <= sum(D(r[k][0]) for k in ['external_J','leakage_J'])+sum(D(v[0]) for k in ['base_by_node_J','activity_by_node_J'] for v in r[k]) <= a.v1.I(*r['energy_J']).hi)
        # Coupled idle fixture exercises stiffness and a full 80 ms tail, with no Stage schedule.
        pp=a.load()['problem']['platform']
        ss=dict(start_us=F(0),end_us=F(80000),base_W=[D('.2'),D('.3')],
                leak_W_per_K=[D('.002'),D('.002')],activity_W=[F(0),F(0)])
        budget=a.v2.Budget(seconds=20); start=time.monotonic()
        rr=a.thermal(pp,[30,30],[ss],acc,budget)
        artifacts['coupled_idle_80ms']=dict(result=rr,elapsed_s=time.monotonic()-start,panels=budget.panels)
        check('coupled_idle_80ms_complete_precision',rr['complete'] and rr['precision_met'],rr.get('reason'))
        # Deterministic interruption after a committed initially unsafe point.
        class Stop(a.v2.Budget):
            def panel(self):
                raise a.v1.Exhausted('injected_before_first_panel')
        rr=a.thermal(p,[81],[seg],acc,Stop(seconds=20))
        check('actual_thermal_interruption_retains_violation',rr['status']=='violation' and bool(rr['known_violations']) and 'energy_J' not in rr)

    sections=[('static',static),('status_contract',statuses)]
    if not contract_only: sections.append(('numerical',numerical))
    for name,fn in sections: attempt(name,fn)
    check('input_source_hashes_unchanged',a.identities()==before)
    out=dict(stage='K.28',scope='TP-1 necessary prechecks only; no four-combination energy diagnostic',
             passed=all(c['passed'] for c in checks),formal_ready=False,
             executed_sections=[name for name,_ in sections], checks=checks,artifacts=artifacts,
             hashes=before,python=platform.python_version(),platform=platform.platform())
    a.old.write(destination/'result.json',out)
    print(f"{sum(c['passed'] for c in checks)}/{len(checks)} passed; {destination}")
    for c in checks:
        if not c['passed']: print(c['name'],c['details'])
    return out['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',required=True)
    parser.add_argument('--contract-only',action='store_true')
    args=parser.parse_args(); raise SystemExit(0 if run(Path(args.out),args.contract_only) else 1)
