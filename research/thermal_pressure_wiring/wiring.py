"""K.30: isolated complete-path, local-score and counterexample wiring."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from types import FunctionType, SimpleNamespace
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'thermal_pressure_numerics'))
import scaled as s
a=s.a
I=a.v1.I


def clone(fn, **overrides):
    return FunctionType(fn.__code__,dict(fn.__globals__,**overrides),fn.__name__,fn.__defaults__)


# The old evaluator and its globally imported thermal function remain untouched.
evaluate_trace=clone(a.v1.evaluate_trace,thermal=s.thermal)


def identities():
    out=s.identities()
    for p in [HERE/'wiring.py',HERE/'precheck.py',HERE/'PROTOCOL.md']:
        out[str(p.relative_to(a.old.REPO))]=a.cp.sha(p)
    return out


def binding(b):
    return dict(a.joint.binding(b),wired_sources=identities())


assemble=clone(a.joint.assemble,binding=binding)
_v1=SimpleNamespace(**dict(vars(a.v1),evaluate_trace=evaluate_trace))
_joint=clone(a.joint.evaluate_bundle,v1=_v1,binding=binding,assemble=assemble)


def evaluate_bundle(b,budget=None):
    budget=budget or a.v2.Budget(seconds=20)
    # Finite counterexample probes have explicit entry binding below.
    # Do not call the legacy V2 replay, which chooses the first entry block.
    if b['safety'].get('witness_requests') or b['safety'].get('thermal_witness'):
        raise ValueError('use_explicit_probe_entry_not_legacy_replay')
    return _joint(b,budget)


def evaluate_probe(b,path,budget=None):
    budget=budget or a.v2.Budget(seconds=20)
    out=dict(status='unresolved',scope='finite_counterexample_probe_not_U1',binding=None)
    try:
        single=deepcopy(b);single['evaluation']['paths']=[path];single['evaluation']['weights']=[1]
        out['membership']=a.joint.validate_bundle(single,budget)
        out['binding']=binding(b);out['path']=deepcopy(path)
        x=deepcopy(b['candidate']);x['accuracy']=b['evaluation']['accuracy']
        r=evaluate_trace(x,path['trace'],budget)
        # Transfer only committed counterexamples BEFORE the receiving budget check.
        evidence=a.finite_evidence(r)
        if evidence['status']=='violation':
            out.update(status='violation',known_violations=evidence['known_violations'],deadline_failure=evidence['deadline_failure'])
        budget.checkpoint('probe_returned')
        out.update(status=evidence['status'],result=r)
    except a.v1.Exhausted as exc:
        out.update(budget_status='exhausted',reason=str(exc))
    except (a.v1.Invalid,ValueError,KeyError,TypeError) as exc:
        out.update(status='invalid',reason=str(exc))
    except (MemoryError,ArithmeticError) as exc:
        out.update(reason=type(exc).__name__,numerical_or_resource_status='unresolved')
    out['elapsed_s']=time.monotonic()-budget.start
    return out


def prefix_parts(b,path,budget):
    a.joint.validate_bundle(b,budget)
    x=deepcopy(b['candidate']);x['accuracy']=b['evaluation']['accuracy']
    tr=path['trace']
    if path not in b['evaluation']['paths']:raise ValueError('prefix_path_not_bound')
    rows,req,releases,failure=a.v1.expand(x,tr,budget)
    if failure:raise ValueError('prefix_source_path_deadline_failure')
    cut=F(tr['switch_requests'][0]['time_us'])
    segments=a.v1.power_segments(x,tr,rows,F(tr['window_us']),budget)
    prefix=[]
    for seg in segments:
        if seg['start_us']>=cut:break
        part=deepcopy(seg);part['end_us']=min(cut,part['end_us']);prefix.append(part)
    state=dict(cut_us=cut,held_opps=prefix[-1]['opps'],
               unfinished=[r for r in rows if r['mode']=='A' and r['start_us']<cut<r['end_us']],
               event_instant='after old completion, before B start')
    return x,tr,prefix,state


def sensitivity(platform,segments,budget):
    n=len(platform['nodes']);out=[];cache={}
    for coordinate in range(n):
        z=[I(int(j==coordinate)) for j in range(n)]+[I(0),I(0)]
        for seg in segments:
            budget.check()
            matrix=a.v1.coeff_matrix(platform,seg)
            duration=(F(seg['end_us'])-F(seg['start_us']))/1000000
            count=s.panel_count(matrix,duration);step=duration/count
            for _ in range(count):
                budget.panel();panel=s.ScaledPanel(matrix,z,step,cache)
                next_z=panel.value(step);next_z[-1]=I(0)
                budget.check();z=next_z
        out.append(z[n].data())
    budget.check();return out


def reference_path(b,horizon_us):
    entry=next(deepcopy(e) for e in b['safety']['initial_states']
               if e['actual_mode']=='B' and e['held_opps']=={'C0':'L','N0':'H'})
    entry['temperature_box_C']=[[30,30],[30,30]]
    trace=dict(id='B_reference_'+str(horizon_us),initial_mode='B',initial_release_us=0,
               initial_temperature_C=[30,30],initial_opps={'C0':'L','N0':'H'},initial_unfinished_work=[],
               switch_requests=[],window_us=horizon_us)
    return dict(entry_state=entry,trace=trace)


def local_score(b,kind,path=None,horizon_us=None,budget=None):
    budget=budget or a.v2.Budget(seconds=20)
    out=dict(status='unresolved',kind=kind,role='local_reference_only_not_U1_or_sustained_certificate')
    try:
        budget.checkpoint('local_start')
        out['binding']=binding(b)
        if kind=='A_prefix':
            x,tr,segments,boundary=prefix_parts(b,path,budget)
            out.update(boundary=boundary,source_trace_id=tr['id'])
        elif kind=='B_reference':
            ref=reference_path(b,horizon_us)
            single=deepcopy(b);single['evaluation']['paths']=[ref];single['evaluation']['weights']=[1]
            a.joint.validate_bundle(single,budget)
            x=deepcopy(b['candidate']);x['accuracy']=b['evaluation']['accuracy'];tr=ref['trace']
            rows,_,_,failure=a.v1.expand(x,tr,budget)
            if failure:raise ValueError('reference_deadline_failure')
            segments=a.v1.power_segments(x,tr,rows,F(horizon_us),budget)
            out['reference_path']=ref;out['reference_schedule']=rows
        else:raise ValueError('unknown_score_kind')
        r=s.thermal(x['platform'],tr['initial_temperature_C'],segments,x['accuracy'],budget)
        # A reference violation does not exclude the full configuration.
        if r.get('known_violations'):
            out.update(status='reference_violation',known_violations=deepcopy(r['known_violations']))
        budget.checkpoint('local_thermal_returned')
        if kind=='B_reference':g=sensitivity(x['platform'],segments,budget)
        else:g=None
        budget.checkpoint('local_before_commit')
        out['thermal']=r
        if g is not None:out['g_J_per_K']=g
        if r.get('complete') and 'energy_J' in r:
            out['diagnostic_energy_J']=r['energy_J']
        if r.get('complete') and r.get('precision_met') and r['status']=='safe':
            out.update(status='safe_reference',score_J=r['energy_J'])
    except a.v1.Exhausted as exc:
        out.update(budget_status='exhausted',reason=str(exc))
    except (a.v1.Invalid,KeyError,ValueError,TypeError) as exc:
        out.update(status='invalid',reason=str(exc))
    except (MemoryError,ArithmeticError) as exc:
        out.update(reason=type(exc).__name__,numerical_or_resource_status='unresolved')
    out['elapsed_s']=time.monotonic()-budget.start
    return out


def combine_scores(records,weights):
    if len(records)!=len(weights) or not records or sum(map(F,weights))!=1 or any(F(w)<0 for w in weights):
        raise ValueError('score_weight_contract')
    if any(r['status']!='safe_reference' or 'score_J' not in r for r in records):
        return dict(status='unavailable',parts=[r['status'] for r in records])
    if (any(r.get('binding')!=records[0].get('binding') for r in records)
        or records[0].get('binding') is None
        or len({r.get('kind') for r in records})!=1
        or records[0].get('kind') not in ['A_prefix','B_reference']):
        return dict(status='identity_mismatch')
    value=sum((I(*r['score_J'])*I.rational(F(w)) for r,w in zip(records,weights)),I(0))
    return dict(status='available',score_J=value.data(),scope='local_score_not_complete_candidate_energy')


def attribution(prefix,reference,full,trace_id):
    actual=full.get('finite_path_energy',{}).get('traces',{}).get(trace_id,{})
    if any(r.get('status')!='safe_reference' for r in [prefix,reference]) or not actual.get('rankable_energy'):
        return dict(status='unavailable')
    if prefix.get('binding')!=full.get('binding') or reference.get('binding')!=full.get('binding'):
        return dict(status='identity_mismatch')
    boundary=prefix['boundary'];ref=reference['reference_path']['trace'];cut=F(boundary['cut_us'])
    if (prefix.get('source_trace_id')!=trace_id or boundary['unfinished']
        or boundary['held_opps']!=ref['initial_opps']):
        return dict(status='nonthermal_boundary_mismatch')
    def key(row,shift):
        return tuple(row[k] for k in ['stage','unit','opp'])+(F(row['start_us'])-shift,F(row['end_us'])-shift)
    suffix=[key(row,cut) for row in actual['schedule'] if row['mode']=='B']
    reference_rows=[key(row,F(0)) for row in reference['reference_schedule']]
    end=F(actual['thermal']['covered_until_us'])
    if suffix!=reference_rows or end-cut!=F(ref['window_us']):
        return dict(status='suffix_timing_mismatch')
    temp=[I(*v) for v in prefix['thermal']['end_temperature_C']]
    correction=sum((I(*g)*(t-30) for g,t in zip(reference['g_J_per_K'],temp)),I(0))
    predicted=I(*prefix['score_J'])+I(*reference['score_J'])+correction
    actual_energy=I(*actual['thermal']['energy_J'])
    return dict(status='consistent' if a.old.overlap(predicted,actual_energy) else 'inconsistent',
                history_J=correction.data(),predicted_J=predicted.data(),actual_J=actual_energy.data())
