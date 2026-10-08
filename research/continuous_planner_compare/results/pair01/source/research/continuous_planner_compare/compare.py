"""K.20: one CP1 paired implementation regression, not a research sweep.

Each method imports the unchanged planner into its own module namespace. Only
the representative provider changes; the search function itself is unchanged.
Both methods get identical instrumentation and separate processes/solver state.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import importlib.util
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'continuous_planner'
sys.path.insert(0,str(OLD))
import planner as p


def earliest(problem,structure):
    """Forward propagation only: no latest or midpoint computation."""
    table={}
    for m,mode in problem['modes'].items():
        rows=p.selected(problem,structure,m)
        d={i:F(o['duration_us']) for i,o in rows.items()}
        edges={(a,s['id']) for s in mode['stages'] for a in s['predecessors']}
        edges|={tuple(e) for e in structure['directions'][m]}
        remaining=set(rows); starts={}
        while remaining:
            ready=sorted(i for i in remaining if not any(a in remaining for a,b in edges if b==i))
            if not ready: raise ValueError('exact_direction_cycle')
            for i in ready:
                starts[i]=max([F(0)]+[starts[a]+d[a] for a,b in edges if b==i])
            remaining.difference_update(ready)
        if any(starts[i]+d[i]>mode['relative_deadline_us'] for i in rows):
            raise ValueError('exact_earliest_deadline')
        table[m]=starts
    if not p.legal(problem,structure,table): raise ValueError('exact_reconstruction_illegal')
    return [('all_E',table)]


def hashes():
    return p.identities() | {str(Path(__file__).relative_to(p.REPO)):p.sha(__file__)}


def snapshot(out):
    out.mkdir(parents=True,exist_ok=False)
    h=hashes()
    for name in h:
        dst=out/'source'/name; dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes((p.REPO/name).read_bytes())
    p.save(out/'manifest.json',dict(files=h,python=sys.version,platform=platform.platform()))
    return h


def setup(method,timing):
    if method not in ['E-only','EML']: raise ValueError('method')
    spec=importlib.util.spec_from_file_location('_paired_'+method.replace('-','_'),OLD/'planner.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    provider=earliest if method=='E-only' else module.representatives
    raw_model=module.Model; raw_evaluations=module.Evaluations
    timing.update(model_s=0.,representative_s=0.,evaluation_s=0.,evaluation_calls=0,representative_calls=0)
    def model(problem):
        start=time.monotonic()
        try: return raw_model(problem)
        finally: timing['model_s']+=time.monotonic()-start
    def representatives(problem,structure):
        start=time.monotonic(); timing['representative_calls']+=1
        try: return provider(problem,structure)
        finally: timing['representative_s']+=time.monotonic()-start
    class ObservedEvaluations(raw_evaluations):
        def evaluate(self,*args,**kwargs):
            start=time.monotonic(); timing['evaluation_calls']+=1
            try: return super().evaluate(*args,**kwargs)
            finally: timing['evaluation_s']+=time.monotonic()-start
    module.Model=model; module.representatives=representatives; module.Evaluations=ObservedEvaluations
    return module


def structure_for(problem,choice,orders):
    dirs={}
    for m in problem['modes']:
        rows=p.selected(problem,{'chosen':choice},m); order=orders[m]
        dirs[m]=[[a,b] for a,b in itertools.combinations(order,2)
                 if p.conflict(problem['platform'],rows[a],rows[b])]
    return dict(chosen=choice,directions=dirs)


def vector(model,st,table):
    v=[F(0)]*len(model.f)
    for (m,i,o),k in model.x.items(): v[k]=int(st['chosen'][m][i]==o)
    for (m,i),k in model.a.items(): v[k]=F(table[m][i])/1000
    for m,i,j,oi,oj,z in model.pairs:
        if st['chosen'][m][i]==oi and st['chosen'][m][j]==oj: v[z]=int([i,j] in st['directions'][m])
    return v


def gate(receipt):
    x=p.read(receipt)
    if x.get('passed') is not True or x.get('hashes')!=hashes(): raise ValueError('paired_precheck_hash_mismatch')


def precheck(out):
    identity=snapshot(out); checks=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    try:
        old=p.read(OLD/'results/precheck05/checks.json')
        check('unchanged_76_check_base',old['passed'] and old['hashes']==p.identities())
        x=p.read(p.DRAFT/'inputs.json'); problem=x['problem']
        # Algebraic reconstruction checks; no thermal parameter variations.
        bymode={}
        for m,mode in problem['modes'].items():
            stages=mode['stages']; ids=[s['id'] for s in stages]; bymode[m]=[]
            for options in itertools.product(*(s['options'] for s in stages)):
                selected={i:o['option_id'] for i,o in zip(ids,options)}
                for order in [ids,[ids[1],ids[0],ids[2]]]: bymode[m].append((selected,order))
        total=0; mismatch=[]; illegal=[]; cert=[]
        for av,bv in itertools.product(bymode['A'],bymode['B']):
            choice={'A':av[0],'B':bv[0]}; st=structure_for(problem,choice,{'A':av[1],'B':bv[1]})
            e=earliest(problem,st); eml=p.representatives(problem,st); total+=1
            if e[0]!=eml[0]: mismatch.append(total)
            if not p.legal(problem,st,e[0][1]): illegal.append(total)
            spans={label:{m:max(t[m][i]+F(o['duration_us']) for i,o in p.selected(problem,st,m).items())
                         for m in problem['modes']} for label,t in eml}
            if not (spans['all_M']['A']+spans['all_M']['B']>14000
                    and spans['all_L']['A']+spans['all_L']['B']==28000): cert.append(total)
        check('earliest_equal_to_original_for_all_576_constructions',total==576 and not mismatch,dict(total=total,mismatch=mismatch))
        check('all_constructed_E_exactly_legal',not illegal)
        check('E455_M_L_deadline_certificate_limit',not cert)
        st=structure_for(problem,x['probes']['reference_options'],{'A':['A0','A1','A2'],'B':['B0','B1','B2']})
        e=earliest(problem,st)
        with patch.object(p,'representatives',side_effect=AssertionError('must not compute M/L')):
            check('E_only_does_not_call_EML_provider',earliest(problem,st)==e)
        bad=deepcopy(st); bad['directions']['A']+=[['A2','A0']]
        try: earliest(problem,bad); rejected=False
        except ValueError as exc: rejected=str(exc)=='exact_direction_cycle'
        check('cycle_rejected',rejected)
        small=deepcopy(problem); small['modes']['A']['relative_deadline_us']=1
        try: earliest(small,st); rejected=False
        except ValueError as exc: rejected=str(exc)=='exact_earliest_deadline'
        check('earliest_deadline_rejected',rejected)
        a=setup('E-only',{}); b=setup('EML',{})
        check('isolated_modules',a is not b and a.search.__globals__ is not b.search.__globals__)
        check('identical_search_bytecode',a.search.__code__.co_code==b.search.__code__.co_code==p.search.__code__.co_code)
        check('EML_representatives_unchanged',b.representatives(problem,st)==p.representatives(problem,st))
        # Tiny actual solver smoke test before the two diagnostic calls.
        clock=p.Clock(60); backend=p.Matlab(out/'solver_precheck',clock)
        try:
            model=p.Model(problem); sol=backend.solve(model,15)
            decoded=model.decode(sol['x'],x['runtime_draft']['integer_decode_tolerance'])
            check('real_MILP_E_reconstruction',earliest(problem,decoded)==p.representatives(problem,decoded)[:1])
            check('R2023b_backend',backend.info['release']=='2023b' and backend.info['license'])
        finally: backend.close()
        # Same exact candidate: real independent evaluator calls, no shared cache.
        ba=p.bundle(problem,x['analysis'],st,a.representatives(problem,st)[0][1])
        bb=p.bundle(problem,x['analysis'],st,b.representatives(problem,st)[0][1])
        ra=a.Evaluations().evaluate(ba,p.Clock(30),20); rb=b.Evaluations().evaluate(bb,p.Clock(30),20)
        p.save(out/'same_E.json',dict(E_only=ra,EML=rb))
        check('same_E_same_identity',ra['binding']==rb['binding'])
        check('same_E_same_safe_energy',ra['status']==rb['status']=='certified_candidate'
              and ra['certified_candidate_energy']==rb['certified_candidate_energy'])
        # Fault tests only: inherited search, deterministic structural responses.
        class Backend:
            def __init__(self): self.calls=0
            def solve(self,model,cap):
                self.calls+=1
                if self.calls>2: return dict(x=[],output={},exitflag=-2)
                chosen=deepcopy(st)
                if self.calls==2: chosen['chosen']['A']['A0']='A0_C0_L'
                chosen=structure_for(problem,chosen['chosen'],{'A':['A0','A1','A2'],'B':['B0','B1','B2']})
                return dict(x=vector(model,chosen,earliest(problem,chosen)[0][1]),output={},exitflag=1)
        for status in ['candidate_violation','unresolved','certified_candidate','input_invalid']:
            mod=setup('E-only',{}); folder=out/('fault_'+status); folder.mkdir()
            answer=deepcopy(ra) if status=='certified_candidate' else dict(status=status,certified_candidate_energy={'status':'unavailable'})
            with patch.object(mod.Evaluations,'evaluate',return_value=answer):
                r=mod.search(problem,x['analysis'],x['protocol'],x['runtime_draft'],folder,p.Clock(30),Backend())
            count=sum(len(s['representatives']) for s in r['structures'])
            check('E_only_control_'+status,count==(1 if status=='input_invalid' else 2))
            check('E_only_never_M_L_'+status,all(i['label']=='all_E' for s in r['structures'] for i in s['representatives']))
            check('original_bounds_'+status,r['L0_J']==F('0.028') and r['infeasibility']=='unproved' and r['optimality']=='unproved')
        clock=p.Clock(30); mod=setup('E-only',{}); folder=out/'fault_interrupt'; folder.mkdir()
        def expired(*args): clock.start-=1000; return dict(status='unresolved',certified_candidate_energy={'status':'unavailable'})
        with patch.object(mod.Evaluations,'evaluate',side_effect=expired):
            r=mod.search(problem,x['analysis'],x['protocol'],x['runtime_draft'],folder,clock,Backend())
        check('partial_structure_kept',r['stop']=='budget_exhausted' and r['structures'][0]['state']=='processing' and r['U_J'] is None)
        # Real inner committed counterexample across outer expiry, E schedule from
        # old 12ms fixture: do not alter the CP1 research input.
        j12=next(c for c in p.read(p.HERE.parent/'joint_evaluator/inputs.json')['cases'] if c['id']=='J12')
        clock=p.Clock(30)
        def hook(point):
            if point=='witness_committed': clock.start-=1000
        rr=a.Evaluations().evaluate(j12,clock,20,hook); p.save(out/'committed_violation.json',rr)
        check('committed_violation_kept',rr['status']=='candidate_violation' and rr['certified_candidate_energy']['status']=='unavailable')
        ev1=a.Evaluations(); ev2=b.Evaluations()
        check('fresh_caches',ev1.cache is not ev2.cache and not ev1.cache and not ev2.cache)
        check('unchanged_original_source_and_input',old['hashes']==p.identities())
    except Exception as exc:
        import traceback
        p.save(out/'exception.json',dict(message=str(exc),traceback=traceback.format_exc()))
        check('completed',False,str(exc))
    check('precheck_source_stable',identity==hashes())
    r=dict(passed=all(c['passed'] for c in checks),count=len(checks),checks=checks,hashes=identity)
    p.save(out/'checks.json',r); print('PRECHECK',sum(c['passed'] for c in checks),'/',len(checks),flush=True)
    return r['passed']


def case(method,out,receipt):
    gate(receipt); snapshot(out)
    clock=p.Clock(120); backend=None; timing={}
    try:
        x=p.read(p.DRAFT/'inputs.json'); mod=setup(method,timing)
        started=clock.elapsed(); backend=p.Matlab(out/'backend',clock)
        timing['backend_startup_s']=clock.elapsed()-started
        r=mod.search(x['problem'],x['analysis'],x['protocol'],x['runtime_draft'],out,clock,backend)
        timing['query_s']=sum(s.get('query_seconds',0) for s in r['structures'])
        timing['search_elapsed_s']=r['elapsed_s']
        p.save(out/'method.json',dict(method=method,representatives=['all_E'] if method=='E-only' else ['all_E','all_M','all_L'],
            timing=timing,environment=backend.info,gate_sha256=p.sha(receipt),input_sha256=p.sha(p.DRAFT/'inputs.json'),
            status='completed_call',interpretation='CP1 implementation regression only; stop at fixed cap'))
        print(method,r['stop'],'evaluations',timing['evaluation_calls'],'elapsed',r['elapsed_s'],flush=True)
    except Exception as exc:
        p.save(out/'blocked.json',dict(message=str(exc),elapsed_s=clock.elapsed()))
        raise
    finally:
        if backend: backend.close()


def paired(out,receipt):
    gate(receipt); snapshot(out)
    for method in ['E-only','EML']:
        # Separate Python/MATLAB processes, input loading, caches and budgets.
        with (out/(method+'.log')).open('x',encoding='utf-8') as log:
            r=subprocess.run([sys.executable,'-B',str(Path(__file__)),'case','--method',method,'--output',str(out/method),
                              '--receipt',str(receipt)],stdout=log,stderr=subprocess.STDOUT)
        if r.returncode:
            p.save(out/'interrupted.json',dict(method=method,returncode=r.returncode)); return False
        print('SAVED',method,flush=True)
    return True


def postcheck(out,pair):
    snapshot(out); x=p.read(p.DRAFT/'inputs.json'); checks=[]; summary={}; records={}
    def check(name,ok): checks.append(dict(name=name,passed=bool(ok)))
    for method in ['E-only','EML']:
        r=p.read(pair/method/'search.json'); meta=p.read(pair/method/'method.json'); records[method]=r
        seen={}; safe=[]; statuses=Counter(); count=0
        for st in r['structures']:
            if 'structure' not in st: continue
            sigma=st['structure']['signature']; seen[sigma]={}
            for item in st['representatives']:
                label=str(st['index'])+'_'+item['label']; result=item['result']; count+=1; statuses[result['status']]+=1
                table={m:{i:F(v) for i,v in row.items()} for m,row in item['table_us'].items()}
                bundle=p.bundle(x['problem'],x['analysis'],st['structure'],table)
                check(method+label+'_exact_valid',p.legal(x['problem'],st['structure'],table))
                check(method+label+'_in_budget',F(item['finished_s'])<=120)
                check(method+label+'_identity',p.joint.binding(bundle)==result.get('binding'))
                seen[sigma][item['label']]=dict(table=table,status=result['status'],energy=result['certified_candidate_energy'])
                if result['status']=='certified_candidate':
                    rr=p.joint.evaluate_bundle(bundle,p.joint.v2.Budget(seconds=20))
                    p.save(out/(method+'_'+label+'.json'),rr)
                    check(method+label+'_full_recheck',rr['status']=='certified_candidate' and rr['certified_candidate_energy']==result['certified_candidate_energy'])
                    safe.append((bundle['id'],result['certified_candidate_energy']['energy_J']))
        records[method+'_seen']=seen
        check(method+'_original_L0',F(r['L0_J'])==p.lower_bound(x['problem']))
        check(method+'_U_evidence',min(F(en[1]) for cid,en in safe)==F(r['U_J']) if safe else r['U_J'] is None)
        check(method+'_sources_bound',p.read(pair/method/'manifest.json')['files']==hashes())
        check(method+'_unsearched_kept',r['optimality']=='unproved' and 'unsearched' in r['coverage'])
        if method=='E-only': check('only_E_called',all(set(v)=={'all_E'} for v in seen.values()))
        best=next((en for cid,en in safe if cid==r['best_candidate']),None)
        summary[method]=dict(structures=len(seen),evaluations=count,statuses=dict(statuses),U_J=r['U_J'],L0_J=r['L0_J'],
            best_energy_J=best,first_safe_s=r['events'][0]['t_s'] if r['events'] else None,stop=r['stop'],timing=meta['timing'])
    common=sorted(set(records['E-only_seen']) & set(records['EML_seen']))
    matched=[]
    for sigma in common:
        a=records['E-only_seen'][sigma].get('all_E'); b=records['EML_seen'][sigma].get('all_E')
        check('matched_'+sigma,a==b)
        matched.append(dict(signature=sigma,same_E=a==b))
    energy_a=summary['E-only']['best_energy_J']; energy_b=summary['EML']['best_energy_J']
    comparison=p.compare(energy_a,energy_b) if energy_a and energy_b else 'no_paired_safe_energy'
    check('old_artifacts_unchanged',p.read(OLD/'results/precheck05/checks.json')['hashes']==p.identities())
    p.save(out/'summary.json',dict(methods=summary,common_structures=matched,comparison=comparison,
        evidence='single CP1 engineering pair, not general scheduling or thermal-energy benefit',
        observation='M/L cannot pass CP1 transition deadlines (E455); no parameter tuning or retry'))
    p.save(out/'checks.json',dict(passed=all(c['passed'] for c in checks),count=len(checks),checks=checks))
    print('POSTCHECK',sum(c['passed'] for c in checks),'/',len(checks),comparison,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['precheck','paired','case','postcheck'])
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--receipt',type=Path)
    parser.add_argument('--method',choices=['E-only','EML']); args=parser.parse_args()
    if args.mode=='precheck': sys.exit(0 if precheck(args.output) else 1)
    elif args.mode=='case': case(args.method,args.output,args.receipt)
    elif args.mode=='paired': sys.exit(0 if paired(args.output,args.receipt) else 1)
    else: postcheck(args.output,args.receipt)
