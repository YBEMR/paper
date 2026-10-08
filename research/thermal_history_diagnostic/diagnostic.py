"""K.23 fixed four-plan diagnostic; no optimizer or expected-answer input."""
from copy import deepcopy
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'continuous_planner'))
import planner as cp
joint, v1, v2 = cp.joint, cp.joint.v1, cp.joint.v2
I, Budget = v1.I, v2.Budget
SOURCE = HERE.parent/'continuous_planner_precheck_draft/inputs.json'
SOURCE_SHA = '3432d9225fc78b2e26849417ba139246dcd45288484bd97ca887f46ad6484f36'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_float=D)


def write(path, data):
    cp.save(path, data)


def identities():
    paths = [HERE/'input.json', HERE/'diagnostic.py', HERE/'precheck.py', HERE/'postcheck.py', HERE/'README.md', SOURCE,
             HERE.parent/'continuous_planner/planner.py'] + list(joint.sources().values())
    return {str(p.relative_to(REPO)): cp.sha(p) for p in paths}


def load():
    x = read(HERE/'input.json')
    if cp.sha(SOURCE) != SOURCE_SHA or x['source_sha256'] != SOURCE_SHA:
        raise ValueError('source_hash_changed')
    old = read(SOURCE)
    # Compare typed exact values, not floating-point reserialized estimates.
    if joint.digest(x['problem']) != joint.digest(old['problem']) or joint.digest(x['analysis']) != joint.digest(old['analysis']):
        raise ValueError('source_semantics_changed')
    return x


def candidate(x, aid, bid):
    chosen, table, directions = {}, {}, {}
    for mode, label in [('A', aid), ('B', bid)]:
        spec = x['plans'][label]
        chosen[mode], table[mode] = {}, {}
        for sid, record in spec['stages'].items():
            st = next(s for s in x['problem']['modes'][mode]['stages'] if s['id']==sid)
            matches = [o for o in st['options'] if o['unit']==record['unit'] and o['opp']==record['opp']]
            if len(matches) != 1: raise ValueError('option_identity')
            chosen[mode][sid] = matches[0]['option_id']
            table[mode][sid] = F(record['offset_us'])
        directions[mode] = []
    b = cp.bundle(x['problem'], x['analysis'], dict(chosen=chosen, directions=directions), table)
    b['id'] = aid+bid
    return b


def path_parts(b, path):
    """Expand the original complete 80ms path; clip its valid prefix only afterwards."""
    budget = Budget(seconds=20)
    x = deepcopy(b['candidate']); x['accuracy'] = b['evaluation']['accuracy']
    tr = path['trace']; rows, requests, releases, failure = v1.expand(x, tr, budget)
    if failure: raise ValueError('original_path_deadline')
    segments = v1.power_segments(x, tr, rows, F(tr['window_us']), budget)
    cut = F(tr['switch_requests'][0]['time_us'])
    prefix = []
    for seg in segments:
        if seg['start_us'] >= cut: break
        s = deepcopy(seg); s['end_us'] = min(cut, seg['end_us']); prefix.append(s)
    before = next(s for s in reversed(prefix) if s['end_us']==cut)
    unfinished = [r for r in rows if r['mode']== 'A' and r['start_us']<cut<r['end_us']]
    # The state is BEFORE B's start; its newly selected OPP is not the held entry OPP.
    state = dict(cut_us=cut, held_opps=before['opps'], unfinished=unfinished,
                 old_mode='A', old_phase_us=cut % F(x['fixed_plans']['A']['period_us']),
                 saturated_switch_age_us=min(cut,F(x['fixed_plans']['A']['minimum_switch_interval_us'])),
                 event_instant='after old completion, before B start')
    return x, tr, prefix, state, rows, segments


def prefix_score(b, path):
    start = time.monotonic(); budget = Budget(seconds=20)
    x,tr,prefix,state,rows,segments = path_parts(b,path)
    r = v1.thermal(x['platform'], tr['initial_temperature_C'], prefix, x['accuracy'], budget)
    budget.check()
    if not r['complete'] or r['status']!='safe': raise ValueError('prefix_unresolved')
    return dict(result=r, boundary=state, prefix_role='score_only_not_complete_U1_or_U',
                seconds=time.monotonic()-start)


def b_reference(b, horizon_us):
    start=time.monotonic()
    x = deepcopy(b['candidate']); x['accuracy']=b['evaluation']['accuracy']
    tr = dict(id='B_reference_'+str(horizon_us), initial_mode='B', initial_release_us=0,
              initial_temperature_C=[30,30], initial_opps={'C0':'L','N0':'H'},
              initial_unfinished_work=[], switch_requests=[], window_us=horizon_us)
    budget=Budget(seconds=20); rows, req, rel, failure = v1.expand(x,tr,budget)
    if failure: raise ValueError('B_reference_incomplete')
    segments=v1.power_segments(x,tr,rows,F(horizon_us),budget)
    r=v1.thermal(x['platform'], tr['initial_temperature_C'], segments, x['accuracy'],budget)
    budget.check()
    if not r['complete'] or r['status']!='safe': raise ValueError('B_reference_unresolved')
    g=sensitivity(x['platform'],segments,budget); budget.check()
    return dict(result=r, segments=segments, trace=tr, g_J_per_K=g, seconds=time.monotonic()-start)


def sensitivity(platform, segments, budget):
    """Enclose exact affine energy derivative via homogeneous augmented propagation.

    Constant coordinate is zero. This is not a fit to perturbed trajectories.
    """
    n=len(platform['nodes']); out=[]
    for coordinate in range(n):
        z=[I(int(j==coordinate)) for j in range(n)]+[I(0),I(0)]
        for seg in segments:
            duration=(seg['end_us']-seg['start_us'])/1000000
            matrix=v1.coeff_matrix(platform,seg)
            count=v1.panel_count(matrix,duration); step=duration/count
            for k in range(count):
                budget.panel(); panel=v1.TaylorPanel(matrix,z,step)
                z=panel.value(step); z[-1]=I(0)
        out.append(z[n].data())
    budget.check(); return out


def box(data): return I(*data)
def overlap(a,b): return a.lo<=b.hi and b.lo<=a.hi
def retained(scores):
    best_upper=min(v.hi for v in scores.values())
    return [k for k,v in scores.items() if v.lo<=best_upper]


def score_locals(x):
    out=dict(A={},B={},S_A_J={},S_B_J={},sources=identities())
    for a in ['a0','a1']:
        b=candidate(x,a,'b0'); out['A'][a]={}
        for path in b['evaluation']['paths']:
            out['A'][a][path['trace']['id']]=prefix_score(b,path)
        out['S_A_J'][a]=sum((box(r['result']['energy_J'])/2 for r in out['A'][a].values()),I(0)).data()
    for label in ['b0','b1']:
        b=candidate(x,'a0',label); out['B'][label]={}
        for horizon in [35000,40000]: out['B'][label][str(horizon)]=b_reference(b,horizon)
        out['S_B_J'][label]=sum((box(r['result']['energy_J'])/2 for r in out['B'][label].values()),I(0)).data()
    out['local_retained_A']=retained({k:box(v) for k,v in out['S_A_J'].items()})
    out['local_retained_B']=retained({k:box(v) for k,v in out['S_B_J'].items()})
    out['local_cartesian']=[a+b for a in out['local_retained_A'] for b in out['local_retained_B']]
    return out


def summarize(x,locals_,results):
    out=dict(scope='four fixed combinations, declared two paths; not continuous-domain optimum',
             local_cartesian=locals_['local_cartesian'], rows={}, all_certified=True)
    energies={}
    for label, rec in results.items():
        r=rec['result']; a,b=label[:2],label[2:]
        obj=r['certified_candidate_energy']
        if obj.get('status')!='available':
            out['all_certified']=False; out['rows'][label]={'status':r['status']}; continue
        J=box(obj['energy_J']); energies[label]=J
        residual=J-box(locals_['S_A_J'][a])-box(locals_['S_B_J'][b])
        prediction=I(0); rebuilt=I(0); paths={}
        for tid,horizon in [('F1','35000'),('F2','40000')]:
            pref=locals_['A'][a][tid]['result']; ref=locals_['B'][b][horizon]
            temps=[box(t) for t in pref['end_temperature_C']]
            contribution=sum((box(g)*(t-30) for g,t in zip(ref['g_J_per_K'],temps)),I(0))
            suffix=box(ref['result']['energy_J'])+contribution
            predicted_path=box(pref['energy_J'])+suffix
            actual=box(r['finite_path_energy']['traces'][tid]['thermal']['energy_J'])
            if not overlap(predicted_path,actual): raise ValueError('prefix_suffix_identity')
            prediction=prediction+contribution/2; rebuilt=rebuilt+predicted_path/2
            paths[tid]=dict(actual_J=actual.data(),rebuilt_J=predicted_path.data(),
                            B_actual_J=suffix.data(),history_contribution_J=contribution.data())
        if not overlap(prediction,residual) or not overlap(J,rebuilt): raise ValueError('history_attribution_identity')
        out['rows'][label]=dict(status=r['status'],J_J=J.data(),R_J=residual.data(),
                                R_from_g_J=prediction.data(),rebuilt_J=rebuilt.data(),paths=paths)
    if len(energies)!=4:
        out.update(conclusion='unresolved_or_invalid',joint_retained=[]); return out
    chosen=retained(energies); base=locals_['local_cartesian']
    improved=any(all(energies[k].hi<energies[q].lo for q in base) for k in chosen)
    out.update(joint_retained=chosen,strict_improvement_over_every_local_retained=improved,
               conclusion='strict_choice_improvement' if improved else
                   'choice_unchanged' if chosen==base else 'different_or_unresolved_retained_sets',
               delta_J=(energies['a1b1']-energies['a1b0']-energies['a0b1']+energies['a0b0']).data(),
               conditional_B_retained={a:retained({b:energies[a+b] for b in ['b0','b1']}) for a in ['a0','a1']},
               conditional_A_retained={b:retained({a:energies[a+b] for a in ['a0','a1']}) for b in ['b0','b1']})
    return out


def formal(precheck_folder):
    gate=read(Path(precheck_folder)/'precheck.json')
    state=read(HERE/'state.json')
    if not gate['all_pass'] or gate['sources']!=identities(): raise ValueError('precheck_gate_mismatch')
    if state['phase']!='ready_for_diagnostic' or state['formal_run_count']!=0:
        raise ValueError('stage_not_ready_or_already_run')
    # Claim the one run before evaluating; crash cannot silently retry.
    state.update(phase='diagnostic_running',formal_run_count=1)
    (HERE/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    folder=HERE/'results'/'diagnostic01'; folder_created=False; all_results={}
    try:
        folder.mkdir(parents=True,exist_ok=False); folder_created=True
        x=load(); write(folder/'sources.json',identities()); write(folder/'input_snapshot.json',x)
        locals_=score_locals(x); write(folder/'locals.json',locals_)
        for a,b in [('a0','b0'),('a0','b1'),('a1','b0'),('a1','b1')]:
            bundle=candidate(x,a,b); budget=Budget(seconds=20)
            r=joint.evaluate_bundle(bundle,budget)
            # A late full value never becomes the diagnostic's certified energy.
            if time.monotonic()-budget.start>20:
                r['certified_candidate_energy']={'status':'unavailable'}; r['budget_status']='exhausted'
            rec=dict(bundle=bundle,result=r); all_results[a+b]=rec
            write(folder/(a+b+'.json'),rec)
        summary=summarize(x,locals_,all_results); write(folder/'summary.json',summary)
        state.update(phase='results_ready_for_review',results_folder=str(folder.relative_to(REPO)))
    except BaseException as exc:
        # Update the durable state even when output preparation itself fails.
        # Never write a failure receipt into a pre-existing run directory.
        state.update(phase='diagnostic_failed_review_required',failure_type=type(exc).__name__,failure=str(exc))
        if folder_created:
            try: write(folder/'failure.json',dict(type=type(exc).__name__,message=str(exc)))
            except (OSError,ValueError) as receipt_error: state['failure_receipt_error']=str(receipt_error)
        raise
    finally:
        (HERE/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='frozen': raise SystemExit('usage: diagnostic.py frozen PRECHECK_FOLDER')
    print(json.dumps(formal(sys.argv[2]),ensure_ascii=False,default=v1.encode,indent=2))
