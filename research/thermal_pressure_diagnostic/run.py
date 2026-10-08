"""One-shot TP-1 diagnostic. Historical inputs and evaluators are read-only."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import argparse
import json
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'thermal_pressure_wiring'))
import wiring as w
a=w.a
ORDER=[('a_c','b_c'),('a_c','b_n'),('a_n','b_c'),('a_n','b_n')]


def identities():
    out=w.identities()
    for name in ['run.py','precheck.py','PROTOCOL.md','postcheck.py']:
        p=HERE/name;out[str(p.relative_to(a.old.REPO))]=a.cp.sha(p)
    return out


def tasks():
    out=[]
    for aa,bb in ORDER:
        for path,h in [('F1',35000),('F2',40000)]:
            out.extend([dict(a=aa,b=bb,kind='A_prefix',path=path),dict(a=aa,b=bb,kind='B_reference',path=path,horizon=h)])
    out.extend(dict(a=aa,b=bb,kind='full') for aa,bb in ORDER)
    out.extend(dict(a=aa,b=bb,kind='probe',mode=mode) for aa,bb in ORDER for mode in ['A','B'])
    return out


def violations(result):
    """Private evaluator receipts only, never raw inputs or local scores."""
    evidence=[]
    def visit(v,path):
        if isinstance(v,dict):
            if v.get('known_violations'):evidence.append(dict(at=path,thermal=deepcopy(v['known_violations'])))
            if v.get('execution_status')=='deadline_violation' and v.get('failure'):evidence.append(dict(at=path,deadline=deepcopy(v['failure'])))
            if v.get('deadline_failure'):evidence.append(dict(at=path,deadline=deepcopy(v['deadline_failure'])))
            if v.get('committed_evidence'):evidence.extend(deepcopy(v['committed_evidence']))
            for k,item in v.items():
                if k not in ['known_violations','failure','deadline_failure','committed_evidence','binding']:
                    visit(item,path+'/'+k)
        elif isinstance(v,list):
            for i,item in enumerate(v):visit(item,path+'/'+str(i))
    visit(result,'result');return evidence


def late_guard(result,kind,elapsed):
    if elapsed<=20:return result
    ev=violations(result)
    status=('reference_violation' if kind in ['A_prefix','B_reference'] else 'candidate_violation') if ev else 'unresolved'
    kept=dict(status=status,budget_status='exhausted',reason='outer_wall_clock_limit',
                committed_evidence=ev,source_binding=result.get('binding'),certified_candidate_energy={'status':'unavailable'})
    # Private joint outputs carry only already-received safety receipts; keep
    # them for conflict detection, never to restore a late objective value.
    if kind=='full':
        for key in ['safety_receipt','sustained_safety']:
            if result.get(key) is not None:kept[key]=deepcopy(result[key])
        proof=kept.get('sustained_safety') or (kept.get('safety_receipt') or {}).get('result',{})
        if result.get('status')=='evidence_conflict' or (proof.get('status')=='sustained_safe' and ev):
            kept['status']='evidence_conflict'
    return kept


def invoke(task):
    budget=a.v2.Budget(seconds=20);b=None
    try:
        x=a.load();b=a.bundle(x,task['a'],task['b'])
        if task['kind']=='full':r=w.evaluate_bundle(b,budget)
        elif task['kind']=='probe':r=w.evaluate_probe(b,a.single_mode_path(b,task['mode']),budget)
        elif task['kind']=='A_prefix':
            path=next(p for p in b['evaluation']['paths'] if p['trace']['id']==task['path'])
            r=w.local_score(b,'A_prefix',path=path,budget=budget)
        else:r=w.local_score(b,'B_reference',horizon_us=task['horizon'],budget=budget)
    except (a.v1.Exhausted,MemoryError,ArithmeticError) as exc:
        r=dict(status='unresolved',reason=type(exc).__name__+': '+str(exc))
    elapsed=time.monotonic()-budget.start
    return dict(task=task,bundle=b,result=late_guard(r,task['kind'],elapsed),evaluation_elapsed_s=elapsed,budget_s=20)


def classify(full,probes):
    proof=full.get('sustained_safety') or (full.get('safety_receipt') or {}).get('result',{})
    bad=violations(full)+[e for p in probes for e in violations(p)]
    safe=proof.get('status')=='sustained_safe'
    if full.get('status')=='evidence_conflict' or (safe and bad):return dict(status='evidence_conflict',evidence=bad)
    if bad:return dict(status='excluded_by_counterexample',evidence=bad)
    obj=full.get('certified_candidate_energy',{})
    if safe and obj.get('status')=='available':return dict(status='certified',energy_J=obj['energy_J'])
    return dict(status='unresolved',reason='no_complete_safe_U_or_no_sustained_certificate')


def hull(values):
    return w.I(min(v.lo for v in values),max(v.hi for v in values))


def summarize(records):
    indexed={}
    for rec in records:
        t=rec['task'];key=t['a']+t['b'];indexed.setdefault(key,dict(local={},probes={},full={}))
        if t['kind']=='full':indexed[key]['full']=rec['result']
        elif t['kind']=='probe':indexed[key]['probes'][t['mode']]=rec['result']
        else:indexed[key]['local'][t['kind']+'_'+t['path']]=rec['result']
    out=dict(scope='four fixed TP-1 combinations only',rows={},local_scores={},local_choice_status='unresolved',attribution={})
    candidates={}
    for aa,bb in ORDER:
        key=aa+bb;row=indexed[key]
        out['rows'][key]=classify(row['full'],list(row['probes'].values()))
        if out['rows'][key]['status']=='certified':candidates[key]=w.I(*out['rows'][key]['energy_J'])
        scores={}
        for kind in ['A_prefix','B_reference']:
            scores[kind]=w.combine_scores([row['local'][kind+'_'+p] for p in ['F1','F2']],[F(1,2),F(1,2)])
        out['local_scores'][key]=scores
        out['attribution'][key]={p:w.attribution(row['local']['A_prefix_'+p],row['local']['B_reference_'+p],row['full'],p) for p in ['F1','F2']}
    unresolved=[k for k,r in out['rows'].items() if r['status'] in ['unresolved','evidence_conflict']]
    retained=a.old.retained(candidates) if candidates else []
    out.update(safe_retained=retained,unresolved_candidates=unresolved,
               four_point_optimality='unresolved' if unresolved else 'no_safe_candidate' if not candidates else 'strict_unique' if len(retained)==1 else 'interval_retained_set')
    mode_scores={}
    for label in ['a_c','a_n','b_c','b_n']:
        kind='A_prefix' if label.startswith('a') else 'B_reference'
        vals=[out['local_scores'][aa+bb][kind] for aa,bb in ORDER if label in [aa,bb]]
        if all(v['status']=='available' for v in vals):
            boxes=[w.I(*v['score_J']) for v in vals]
            if all(a.old.overlap(boxes[0],z) for z in boxes):mode_scores[label]=hull(boxes)
    out['available_mode_scores_J']={k:v.data() for k,v in mode_scores.items()}
    if len(mode_scores)==4:
        ra=a.old.retained({k:v for k,v in mode_scores.items() if k.startswith('a')})
        rb=a.old.retained({k:v for k,v in mode_scores.items() if k.startswith('b')})
        local=[aa+bb for aa in ra for bb in rb]
        order=sorted([aa+bb for aa,bb in ORDER],key=lambda key:((mode_scores[key[:3]]+mode_scores[key[3:]]).hi,(mode_scores[key[:3]]+mode_scores[key[3:]]).lo,key))
        first=next((key for key in order if out['rows'][key]['status']=='certified'),None)
        out.update(local_choice_status='available',local_retained=local,simple_refill_order=order,simple_refill_first_certified=first,
                   refill_scope='posthoc policy replay, not independent performance run')
    else:out['local_choice_reason']='some reference scores unavailable; no full local ordering inferred'
    return out


def check_gate(gate,ready,state):
    if not gate.get('passed') or gate.get('hashes')!=identities():raise ValueError('runner_precheck_mismatch')
    old=a.old.read(HERE.parent/'thermal_pressure_wiring/precheck02/result.json')
    if not old['passed'] or old['hashes']!=w.identities():raise ValueError('wiring_precheck_mismatch')
    if ready.get('hashes')!=identities() or ready.get('review_passed') is not True:raise ValueError('review_not_bound')
    review=Path(ready['review_path'])
    if a.cp.sha(review)!=ready['review_sha256']:raise ValueError('review_changed')
    if state.get('phase')!='ready' or state.get('formal_run_count')!=0:raise ValueError('not_ready_or_already_run')


def save_state(path,state):
    """Only this mutable control file is replaced; evidence stays create-only."""
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(state,handle,ensure_ascii=False,indent=2);handle.write('\n')
    temporary.replace(path)


def claim(folder,state_path,state):
    folder.mkdir(parents=True,exist_ok=False)
    state.update(phase='running',formal_run_count=1)
    save_state(state_path,state)


def formal():
    state_path=HERE/'state.json';state=a.old.read(state_path)
    gate=a.old.read(HERE/'precheck04/result.json');ready=a.old.read(HERE/'ready02.json')
    check_gate(gate,ready,state)
    folder=HERE/'results/diagnostic01';claim(folder,state_path,state)
    records=[]
    try:
        a.old.write(folder/'input_snapshot.json',a.load());a.old.write(folder/'hashes.json',identities())
        for i,task in enumerate(tasks()):
            rec=invoke(task);a.old.write(folder/f'{i:02d}.json',rec);records.append(rec)
            print(i+1,task,rec['result']['status'],round(rec['evaluation_elapsed_s'],3),flush=True)
        if identities()!=gate['hashes']:raise ValueError('runtime_sources_changed')
        summary=summarize(records);a.old.write(folder/'summary.json',summary)
        state.update(phase='results_awaiting_review',completed_calls=len(records))
    except BaseException as exc:
        state.update(phase='failed_no_automatic_retry',error=type(exc).__name__+': '+str(exc),completed_calls=len(records))
        raise
    finally:save_state(state_path,state)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['frozen']);p.parse_args();formal()
