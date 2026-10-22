"""Exact A03 scheduling/accounting adapter. No search, repair or cache."""
from fractions import Fraction as F
from pathlib import Path
import hashlib, json
from .certified_segments import Budget, Exhausted, evaluate_piecewise
ROOT=Path(__file__).resolve().parents[1]

class ScheduleError(ValueError): pass

def q(v):
    if isinstance(v,bool) or not isinstance(v,(int,str,F)): raise ScheduleError('Exact integer/decimal/rational required')
    try: return F(v)
    except (ValueError,ZeroDivisionError): raise ScheduleError('Invalid exact scalar')

def parse_json(raw):
    return json.loads(raw.decode('utf-8'),parse_float=F,parse_constant=lambda s:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def read_json(path): return parse_json(Path(path).read_bytes())

def load_frozen(path=None):
    path=Path(path) if path else ROOT/'inputs/a03_minimal_v1.json'
    manifest=read_json(ROOT/'inputs/a03_manifest.json'); raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    if digest!=manifest['input_sha256']: raise ValueError('A03_FROZEN_INPUT_HASH_MISMATCH')
    x=parse_json(raw)
    if x['schema']!='htp.a03.v1': raise ValueError('A03_SCHEMA_MISMATCH')
    return x,digest

def indexes(x):
    return ({u['id']:u for u in x['execution_units']},{d['id']:d for d in x['frequency_domains']},
            {s['id']:s for s in x['workload']['stages']},{m['id']:m for m in x['mode_table']})

def prepare_schedule(x,schedule,budget):
    budget.check(); units,domains,stages,modes=indexes(x); entries=schedule['entries']
    ids=[e['stage_id'] for e in entries]
    if len(ids)!=len(set(ids)) or set(ids)!=set(stages): raise ScheduleError('EXACT_STAGE_COVERAGE_REQUIRED')
    requests={r['id']:r for r in x['workload']['requests']}; selected={}; intervals={}
    W=q(x['workload']['window_s'])
    for e in entries:
        budget.check(); sid=e['stage_id']; mid=e['mode_id']
        if mid not in modes or modes[mid]['stage_id']!=sid: raise ScheduleError('ILLEGAL_STAGE_MODE')
        m=modes[mid]; a=q(e['start_s']); b=a+q(m['duration_s']); r=requests[stages[sid]['request_id']]
        if a<q(r['release_s']): raise ScheduleError('RELEASE_VIOLATION')
        if b>q(r['absolute_deadline_s']): raise ScheduleError('REQUEST_DEADLINE_VIOLATION')
        if b>W: raise ScheduleError('WINDOW_VIOLATION')
        selected[sid]=m; intervals[sid]=(a,b)
    for sid,(a,b) in intervals.items():
        budget.check()
        if any(intervals[p][1]>a for p in stages[sid]['predecessors']): raise ScheduleError('DEPENDENCY_VIOLATION')
        for other,(c,d) in intervals.items():
            if sid>=other or max(a,c)>=min(b,d): continue
            m,n=selected[sid],selected[other]
            if m['unit_id']==n['unit_id']: raise ScheduleError('EXECUTION_UNIT_OVERLAP')
            if m['domain_id']==n['domain_id'] and m['opp_id']!=n['opp_id']: raise ScheduleError('SHARED_DOMAIN_OPP_CONFLICT')
    completion={r: max(intervals[s][1] for s in item['terminal_stage_ids']) for r,item in requests.items()}
    events=sorted({F(0),W,*[v for pair in intervals.values() for v in pair]})
    nodes=x['thermal']['node_order']; segments=[]
    for a,b in zip(events,events[1:]):
        budget.check(); active=[sid for sid,(c,d) in intervals.items() if c<=a<d]
        base={n:F(0) for n in nodes}; activity={n:F(0) for n in nodes}; leak={n:F(0) for n in nodes}; ks={}; sources={}
        for dom in domains.values():
            running={selected[s]['opp_id'] for s in active if selected[s]['domain_id']==dom['id']}
            if len(running)>1: raise ScheduleError('SHARED_DOMAIN_OPP_CONFLICT')
            k=next(iter(running)) if running else dom['opps'][0]['id']; ks[dom['id']]=k
            opp=next(o for o in dom['opps'] if o['id']==k)
            for unit in dom['unit_ids']:
                node=units[unit]['thermal_node']; base[node]+=q(opp['baseline_per_unit_W']); leak[node]+=q(opp['local_leakage_W_per_K'])
        U=x['shared_system']; base[U['node']]+=q(U['baseline_W']); leak[U['node']]+=q(U['leakage_W_per_K'])
        for sid in active:
            m=selected[sid]; node=units[m['unit_id']]['thermal_node']; local=q(m['local_activity_W']); shared=q(m['shared_activity_W'])
            activity[node]+=local; activity[U['node']]+=shared
            sources[sid]=dict(local_node=node,local_W=local,shared_node=U['node'],shared_W=shared)
        segments.append(dict(start_ms=a*1000,end_ms=b*1000,duration_ms=(b-a)*1000,
            baseline_by_node_W=base,activity_by_node_W=activity,local_leakage_slope_W_per_K=leak,
            node_power_constant_at_reference_W={n:base[n]+activity[n] for n in nodes},baseline_by_power_group_W=dict(base),
            external_common_power_W=0,external_common_injected_heat_W=0,reference_temperature_degC=x['thermal']['reference_temperature_degC'],
            active_stage_ids=active,domain_opps=ks,activity_sources=sources))
    return segments,completion,intervals

def clean(value):
    if isinstance(value,F): return str(value)
    if isinstance(value,dict): return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [clean(v) for v in value]
    return value

def evaluate_schedule(x,schedule,budget=None):
    budget=budget if budget is not None else Budget(); out=dict(state='UNRESOLVED',rankable_energy=False,complete=False,energy_J=None,violations=[])
    try:
        segments,completion,intervals=prepare_schedule(x,schedule,budget)
        t=dict(x['thermal']); t['external_common_power_W']=0
        req=x['evaluation_request']; accuracy=dict(temperature_enclosure_width_K=q(req['temperature_extrema_abs_width_K']),energy_absolute_error_J=q(req['energy_interval_abs_width_J']),energy_relative_error=q(req['energy_interval_rel_width']))
        result=evaluate_piecewise(t,t['initial_temperature_degC'],t['limit_temperature_degC'],segments,q(x['workload']['window_s'])*1000,accuracy,budget,schedule.get('id','schedule'))
        out.update(result,schedule_legal=True,request_completion_s=completion,stage_intervals_s=intervals,power_segments=segments,accuracy_requested=accuracy)
        out['technical_issue']=out.get('reason') in ('INTERNAL_CONSISTENCY_ERROR','NUMERICAL_ERROR','RESOURCE_LIMIT')
    except Exhausted as error:
        out.update(reason=str(error),budget_exhausted=True)
    except ScheduleError as error:
        out.update(state='INVALID_SCHEDULE',schedule_legal=False,reason=str(error))
    except (KeyError,TypeError,ValueError) as error:
        out.update(state='INVALID_INPUT',reason=str(error))
    out.update(elapsed_s=budget.elapsed,panels=budget.panels,refinements=budget.refinements,coverage_scope='One declared initial state, one complete schedule, full finite window; not long-run or optimality proof')
    return clean(out)

def evaluate_frozen(schedule_file=None,fixture_id=None,seconds=60,input_file=None):
    budget=Budget(seconds=seconds); digest=None
    try:
        x,digest=load_frozen(input_file); budget.check()
        if (schedule_file is None)==(fixture_id is None): raise ValueError('Exactly one schedule file or fixture ID required')
        if fixture_id is not None:
            hits=[f for f in x['schedule_fixtures'] if f['id']==fixture_id]
            if len(hits)!=1: raise ValueError('Unknown fixture')
            schedule=hits[0]; schedule_bytes=json.dumps(clean(schedule),sort_keys=True,separators=(',',':')).encode('utf-8')
        else:
            schedule_bytes=Path(schedule_file).read_bytes(); schedule=parse_json(schedule_bytes)
        result=evaluate_schedule(x,schedule,budget)
        result.update(input_sha256=digest,schedule_sha256=hashlib.sha256(schedule_bytes).hexdigest(),fixture_id=fixture_id,kind='TEST_ONLY' if fixture_id else 'FULL_SCHEDULE_EVALUATION',research_optimizer_calls=0)
        return result
    except Exhausted as error:
        return dict(state='UNRESOLVED',reason=str(error),complete=False,rankable_energy=False,energy_J=None,violations=[],budget_exhausted=True,input_sha256=digest,fixture_id=fixture_id,schedule_sha256=None,elapsed_s=budget.elapsed)
    except (OSError,ValueError,KeyError) as error:
        return dict(state='INVALID_INPUT',reason=str(error),complete=False,rankable_energy=False,energy_J=None,elapsed_s=budget.elapsed)
