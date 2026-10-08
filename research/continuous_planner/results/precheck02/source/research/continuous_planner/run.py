"""Reproducible diagnostic checks and one frozen CP1 prototype run."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import itertools
import json
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch
import planner as p


def snapshot(out):
    out.mkdir(parents=True,exist_ok=False)
    hashes=p.identities(); (out/'source').mkdir()
    for name in hashes:
        src=p.REPO/name
        dest=out/'source'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(src.read_bytes())
    p.save(out/'manifest.json',dict(files=hashes,python=sys.version,platform=platform.platform()))
    return hashes


def reference_structure(problem,chosen):
    # Test-only fixture constructor, independent of the production MILP decoder.
    dirs={m:[] for m in problem['modes']}
    for m,mode in problem['modes'].items():
        rows=p.selected(problem,{'chosen':chosen},m)
        for a,b in itertools.combinations(rows,2):
            if p.conflict(problem['platform'],rows[a],rows[b]): dirs[m].append([a,b])
    return dict(chosen=chosen,directions=dirs)


def assignment(model,structure,table):
    v=[F(0)]*len(model.f)
    for (m,i,o),k in model.x.items(): v[k]=int(structure['chosen'][m][i]==o)
    for (m,i),k in model.a.items(): v[k]=F(table[m][i])/1000
    for m,i,j,oi,oj,z in model.pairs:
        if structure['chosen'][m][i]==oi and structure['chosen'][m][j]==oj:
            v[z]=int([i,j] in structure['directions'][m])
    return v


def matrix_accepts(model,v):
    dot=lambda row:sum(c*v[k] for k,c in row.items())
    return (all(a<=x<=b for x,a,b in zip(v,model.lb,model.ub))
        and all(dot(row)<=rhs for row,rhs in zip(model.A,model.b))
        and all(dot(row)==rhs for row,rhs in zip(model.Aeq,model.beq)))


def precheck(out):
    hashes=snapshot(out); data=p.read(p.DRAFT/'inputs.json'); problem=data['problem']; checks=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    try:
        for line in (p.DRAFT/'SHA256SUMS.txt').read_text().splitlines():
            h,n=line.split(maxsplit=1); check('frozen_'+n,p.sha(p.DRAFT/n)==h)
        deps=p.read(p.DRAFT/'DEPENDENCIES_SHA256.json')
        check('old_dependencies_unchanged',all(p.sha(p.REPO/n)==h for n,h in deps.items()))
        model=p.Model(problem)
        check('continuous_start_variables',all(k not in model.integer for k in model.a.values()))
        check('14_options_retained',len(model.x)==14)
        check('independent_L0',p.lower_bound(problem)==F(28,1000))
        clock=p.Clock(180); backend=p.Matlab(out/'backend',clock)
        try:
            check('R2023b_license',backend.info['license'] and backend.info['release']=='2023b',backend.info)
            sol=backend.solve(model,15)
            structure=model.decode(sol['x'],'1e-6')
            reps=p.representatives(problem,structure)
            check('real_solver_exact_reconstruction',bool(reps) and all(p.legal(problem,structure,t) for _,t in reps))
            check('solver_objective_28mJ',abs(F(sol['fval'])-28)<F(1,1000000))
            unused=[z for m,i,j,oi,oj,z in model.pairs if structure['chosen'][m][i]!=oi or structure['chosen'][m][j]!=oj]
            altered=list(sol['x']); altered[unused[0]]=1-round(F(altered[unused[0]]))
            check('inactive_direction_signature_invariant',model.decode(altered,'1e-6')['signature']==structure['signature'])
            v=assignment(model,structure,reps[0][1]); check('exact_matrix_reconstructed',matrix_accepts(model,v))
            model.exclude_query(structure)
            check('query_cut_blocks_structure',not matrix_accepts(model,v))
            v[unused[0]]=1-v[unused[0]]
            check('query_cut_ignores_inactive_bit',not matrix_accepts(model,v))
            sol2=backend.solve(model,15); s2=model.decode(sol2['x'],'1e-6')
            check('query_cut_retains_other_structure',s2['signature']!=structure['signature'])
            # Real MILP forcing checks live only here, never in the prototype.
            for key in model.x:
                forced=p.Model(problem); k=forced.x[key]; forced.row({k:1},1,True)
                r=backend.solve(forced,15); s=forced.decode(r['x'],'1e-6')
                check('force_option_'+key[-1],s['chosen'][key[0]][key[1]]==key[2] and bool(p.representatives(problem,s)))
            for direction in (0,1):
                forced=p.Model(problem)
                pair=next(t for t in forced.pairs if t[0:3]==('A','A0','A1'))
                m,i,j,oi,oj,z=pair
                for k,val in [(forced.x[m,i,oi],1),(forced.x[m,j,oj],1),(z,direction)]: forced.row({k:1},val,True)
                r=backend.solve(forced,15); s=forced.decode(r['x'],'1e-6')
                check('force_both_orders_'+str(direction),([i,j] if direction else [j,i]) in s['directions'][m])
        finally: backend.close()
        # Exhaustive independent small scheduling domain vs exact inequalities.
        tiny=deepcopy(problem); tiny['modes']={'A':deepcopy(problem['modes']['A'])}
        tiny['modes']['A']['stages']=tiny['modes']['A']['stages'][:2]
        tiny['modes']['A']['relative_deadline_us']=6000
        tiny['evaluation']=deepcopy(problem['evaluation'])
        for path in tiny['evaluation']['paths']: path['trace']['switch_requests']=[]
        tm=p.Model(tiny); total=0; mismatch=[]
        s0,s1=tiny['modes']['A']['stages']
        for o0,o1,t0,t1 in itertools.product(s0['options'],s1['options'],[0,1000,1500,3000,4500],[0,1000,1500,3000,4500]):
            table={'A':{'A0':F(t0),'A1':F(t1)}}; opts={'A':{'A0':o0['option_id'],'A1':o1['option_id']}}
            # Independent physical definition: actual intervals and actual OPP.
            ends=[F(t0)+F(o0['duration_us']),F(t1)+F(o1['duration_us'])]
            overlap=max(t0,t1)<min(ends)
            physical=all(e<=6000 for e in ends) and not (overlap and o0['unit']==o1['unit'])
            accepted=False
            for direction in (0,1):
                dirs=[] if o0['unit']!=o1['unit'] else ([['A0','A1']] if direction else [['A1','A0']])
                st=dict(chosen=opts,directions={'A':dirs})
                accepted |= matrix_accepts(tm,assignment(tm,st,table))
            total+=1
            if accepted!=physical: mismatch.append([o0['option_id'],o1['option_id'],t0,t1])
        check('small_domain_matrix_bijection',not mismatch,dict(assignments=total,mismatches=mismatch))
        # Separate shared-domain scheduling probes, not new thermal platform data.
        dom=deepcopy(problem); dom['platform']['units']['C1']=deepcopy(dom['platform']['units']['C0'])
        dom['platform']['opps']['C1']=deepcopy(dom['platform']['opps']['C0'])
        a=dict(unit='C0',opp='H'); b=dict(unit='C1',opp='H')
        check('shared_domain_same_frequency_no_conflict',not p.conflict(dom['platform'],a,b))
        b['opp']='L'; check('shared_domain_different_frequency_conflict',p.conflict(dom['platform'],a,b))
        check('CPU_NPU_parallel',not p.conflict(dom['platform'],a,dict(unit='N0',opp='H')))
        check('NPU_exclusive',p.conflict(dom['platform'],dict(unit='N0',opp='H'),dict(unit='N0',opp='H')))
        bad=list(sol2['x']); bad[0]=F(1,10)
        try: model.decode(bad,'1e-6'); ok=False
        except ValueError: ok=True
        check('noninteger_rejected',ok)
        # Runtime evaluations before expected-result comparison.
        ref=reference_structure(problem,data['probes']['reference_options'])
        reps=p.representatives(problem,ref); actual={}; bundles={}; cache=p.Evaluations()
        for label,table in reps:
            b=p.bundle(problem,data['analysis'],ref,table); bundles[label]=b
            actual[label]=cache.evaluate(b,p.Clock(30),20)
            p.save(out/(label+'.json'),actual[label])
        narrow=deepcopy(bundles['all_E']); narrow['safety']['certificate_box_C']=data['analysis']['narrow_box_probe_C']
        nr=cache.evaluate(narrow,p.Clock(30),20); p.save(out/'narrow.json',nr)
        expected=p.read(p.DRAFT/'expected.json')
        check('reference_exact_E_M_L',all([table[m][st['id']] for st in problem['modes'][m]['stages']]==expected['representatives_us'][label[-1]][m]
              for label,table in reps for m in problem['modes']))
        check('only_three_global_representatives',len(reps)==3)
        for label,state in [('all_E','certified_candidate'),('all_M','candidate_violation'),('all_L','candidate_violation')]:
            check(label+'_runtime',actual[label]['status']==state,actual[label]['status'])
        energy=actual['all_E'].get('certified_candidate_energy',{}).get('energy_J')
        check('reference_energy_coarse_bound',energy and F(117,1000)<=F(energy[0])<=F(energy[1])<=F('0.12788'),energy)
        check('M_counterexample_1500us',actual['all_M'].get('sustained_safety',{}).get('witness',{}).get('failure',{}).get('lateness_us')==1500)
        check('L_prefix_not_aggregated',actual['all_L'].get('finite_path_energy',{}).get('aggregate',{}).get('status')=='not_aggregatable')
        check('narrow_box_unresolved',nr['status']=='unresolved')
        check('proof_change_not_candidate_change',p.joint.binding(narrow)['candidate_sha256']==p.joint.binding(bundles['all_E'])['candidate_sha256'])
        check('proof_change_cache_miss',cache.hits==0)
        hit=cache.evaluate(bundles['all_E'],p.Clock(30),20)
        check('exact_cache_hit',cache.hits==1 and hit==actual['all_E'])
        check('overlap_not_strict_ranking',p.compare(['1','3'],['2','4'])=='overlap_or_tie')
        shifted=deepcopy(reps[0][1])
        for m in shifted:
            for i in shifted[m]: shifted[m][i]+=F(1,3)
        b=p.bundle(problem,data['analysis'],ref,shifted)
        clock=p.Clock(30); p.joint.validate_bundle(b,p.joint.v2.Budget())
        check('fractional_continuous_offset_accepted',b['candidate']['fixed_plans']['A']['stages'][0]['offset_us']==F(1,3))
        exact=deepcopy(tiny); exact['modes']['A']['stages'][1]['predecessors']=['A0']
        for st in exact['modes']['A']['stages']: st['options']=[st['options'][0]]
        exact['modes']['A']['relative_deadline_us']=3500
        st=reference_structure(exact,{'A':{'A0':'A0_C0_H','A1':'A1_C0_H'}})
        check('equal_representatives_dedup',len(p.representatives(exact,st))==1)
        # Real inner evaluator, only expiry injected at the evidence boundary.
        clock=p.Clock(30)
        def expires_at_witness(name):
            if name=='witness_committed': clock.start-=1000
        rr=p.Evaluations().evaluate(bundles['all_M'],clock,20,expires_at_witness)
        p.save(out/'late_violation.json',rr)
        check('committed_violation_survives_outer_expiry',rr['status']=='candidate_violation' and rr['certified_candidate_energy']['status']=='unavailable')
        clock=p.Clock(30); real=p.joint.evaluate_bundle
        def late_safe(*args):
            r=real(*args); clock.start-=1000; return r
        with patch.object(p.joint,'evaluate_bundle',side_effect=late_safe):
            rr=p.Evaluations().evaluate(bundles['all_E'],clock,20)
        p.save(out/'late_safe.json',rr)
        check('late_safe_not_accepted',rr['status']=='unresolved' and rr['certified_candidate_energy']['status']=='unavailable')
        # Outer search faults with real representative construction and controlled
        # evaluator returns. No fake result is used in prototype or safe-output data.
        class FakeBackend:
            def __init__(self): self.calls=0
            def solve(self,model,cap):
                self.calls+=1
                if self.calls>1: raise MemoryError('injected_backend_resource')
                values=assignment(model,ref,reps[0][1])
                return dict(x=values,exitflag=1,fval=37,output={})
        clock=p.Clock(30); fb=FakeBackend(); fault=out/'fault_resource'; fault.mkdir()
        with patch.object(p.Evaluations,'evaluate',return_value=actual['all_E']):
            r=p.search(problem,data['analysis'],data['protocol'],data['runtime_draft'],fault,clock,fb)
        check('resource_preserves_U_and_L0',r['U_J'] is not None and r['L0_J']==F(28,1000) and r['optimality']=='unproved')
        check('safe_first_does_not_stop_other_representatives',len(r['structures'][0]['representatives'])==3)
        clock=p.Clock(30); fault=out/'fault_interrupt'; fault.mkdir()
        def expire(*args): clock.start-=1000; return dict(status='unresolved',certified_candidate_energy={'status':'unavailable'})
        with patch.object(p.Evaluations,'evaluate',side_effect=expire):
            r=p.search(problem,data['analysis'],data['protocol'],data['runtime_draft'],fault,clock,FakeBackend())
        check('interrupted_parent_retained',r['structures'][0]['state']=='processing' and r['stop']=='budget_exhausted' and r['U_J'] is None)
        check('no_silent_fallback_or_full_coverage',r['infeasibility']=='unproved' and 'unsearched' in r['coverage'])
        check('production_no_expected_or_probes_access',all(token not in (p.HERE/'planner.py').read_text() for token in ["['probes']","['reference_options']","representatives_us"]))
    except Exception as exc:
        import traceback
        p.save(out/'exception.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()))
        check('runtime_completed',False,str(exc))
    check('source_input_unchanged_during_precheck',hashes==p.identities())
    result=dict(passed=all(x['passed'] for x in checks),count=len(checks),checks=checks,hashes=hashes)
    p.save(out/'checks.json',result)
    print('SUMMARY',sum(c['passed'] for c in checks),'/',len(checks),flush=True)
    return result['passed']


def prototype(out,receipt):
    checked=p.read(receipt)
    if not checked['passed'] or checked['hashes']!=p.identities(): raise ValueError('precheck_gate_mismatch')
    snapshot(out)
    clock=p.Clock(120)  # Starts before loading/expanding input and MATLAB startup.
    data=p.read(p.DRAFT/'inputs.json'); backend=None
    try:
        backend=p.Matlab(out/'backend',clock)
        r=p.search(data['problem'],data['analysis'],data['protocol'],data['runtime_draft'],out,clock,backend)
        print('PROTOTYPE',r['stop'],'U=',r['U_J'],'structures=',len(r['structures']),flush=True)
    except Exception as exc:
        p.save(out/'blocked.json',dict(reason=str(exc),elapsed_s=clock.elapsed()))
        raise
    finally:
        if backend: backend.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['precheck','prototype'])
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--receipt',type=Path)
    a=parser.parse_args()
    if a.mode=='precheck': sys.exit(0 if precheck(a.output) else 1)
    else: prototype(a.output,a.receipt)
