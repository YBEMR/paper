"""Manual end-to-end control paths, no optimizer or physical propagation."""
from copy import deepcopy
from fractions import Fraction as F
import importlib
from types import SimpleNamespace
from unittest.mock import patch

from .fixtures import bundle, FakeClock
from .manual_backend import ManualLedger, schedules
from ..budget import G0Budget, ScopeExhausted, MethodBudget
from ..contract import canonical_hash, validate_inputs, derive_deployment
from ..method import ManualBackend, run_g0, make_model_view


def backend_for(config, instance, anchor, clock, *, init_delay=0, init_safe=True,
                action='improve', idle_after=999, init_finish_before_safe=False):
    ledger=ManualLedger(config,instance,clock)
    calls=[]
    idle_calls=[0]

    def initializer(inst, cfg, budget, assess):
        calls.append('initializer')
        if init_finish_before_safe:
            clock.advance(init_delay); budget.check()
        if init_safe:
            assess(deepcopy(anchor),'fake-heft:seed')
        if not init_finish_before_safe:
            clock.advance(init_delay); budget.check()
        return {'status':'BOUNDED_SEARCH_COMPLETED','evidence_kind':'MANUAL_FIXTURE'}

    def build(cfg, inst, condition, budget):
        calls.append(('build',condition['phase'],condition['scene_id']))
        if action=='memory':
            raise MemoryError('MANUAL_MEMORY_FAILURE')
        budget.check()
        return SimpleNamespace(instance=make_model_view(inst,condition['scene_id'],condition['d0_all']),
                               condition=condition)

    def prepare(model, candidate, budget):
        calls.append(('prepare',model.condition['phase'],model.condition['scene_id']))
        return dict(evaluation=ledger.view(model.instance,candidate,budget),x0=None,
                    state='INITIAL_POINT_REJECTED',reason='MANUAL_VECTOR_REJECTION')

    def search(model,x0,budget,emit):
        condition=model.condition
        calls.append(('search',condition['phase'],condition['scene_id']))
        if action=='timeout':
            clock.advance(budget.remaining+0.01); budget.check()
        if action=='numerical':
            raise ArithmeticError('MANUAL_NUMERICAL_CONFLICT')
        if action=='interface':
            raise ValueError('MANUAL_INTERFACE_CONFLICT')
        if action in ('unresolved','none'):
            return {'state':'UNRESOLVED','evidence_kind':'MANUAL_FIXTURE'}
        sid=condition['scene_id']
        candidate={'scenes':{sid:deepcopy(condition['anchor']['scenes'][sid])}}
        if action=='improve':
            opened=set(condition['open_ids'])
            for row in candidate['scenes'][sid]:
                if row['stage_id'] in opened:
                    row['opp']='L'
        if action=='violation':
            ledger.status_by_scene[sid]='THERMAL_VIOLATION'
        view=ledger.view(model.instance,candidate,budget)
        result=emit(candidate,view)
        return {'state':result.get('state'),'evidence_kind':'MANUAL_FIXTURE'}

    def idle():
        idle_calls[0]+=1
        return idle_calls[0] <= idle_after

    backend=ManualBackend(initializer,build,prepare,search,idle,ledger.deps(),ledger.sources())
    return backend,ledger,calls


def execute(*, n=6, seconds=300, **kwargs):
    config,instance,anchor=bundle(n)
    clock=FakeClock()
    backend,ledger,calls=backend_for(config,instance,anchor,clock,**kwargs)
    with ledger.patched():
        result=run_g0(lambda:(config,instance),backend,seconds=seconds,clock=clock,manual=True)
    return result,calls,ledger


def A08_extra(ctx):
    result,calls,_=execute(action='unresolved')
    ctx.check(result['failure'] is None and result['S1'] is not None,'complete S1 across both scenes')
    marks=[e['kind'] for e in result['events']]
    ctx.check(marks.index('S1_FROZEN') < marks.index('B2_ALL_DECLARED'),'S1 precedes atomic B2 declaration')
    ctx.check(all(r['declared'] and r['model_completed'] and r['solver_entered']
                  and not r['complete_updates'] for p in result['stages'].values() for r in p),
              'declared/built/entered/improved are separate lifecycle states')
    return {'lifecycle_events':marks,'final_source':result['final']['source']}


def A09_extra(ctx):
    import research.chapter3_g0.method as method
    original=method.select_block
    def interrupted(*args,**kwargs):
        block=original(*args,**kwargs)
        if kwargs.get('phase')==2:
            kwargs['budget'].clock.advance(kwargs['budget'].remaining)
            kwargs['budget'].check()
        return block
    with patch.object(method,'select_block',interrupted):
        result,calls,_=execute(action='none')
    ctx.check(not result['blocks']['2'] and not result['stages']['2'],'no partial B2 publication/model')
    ctx.check(result['S1'] is not None and result['final'] is not None,'S1 retained after selection cutoff')
    return {'b2_published':False,'reason':result['reason']}


def A22(ctx):
    config,instance,anchor=bundle(4,scene_ids=('X',),shape='independent')
    anchor['scenes']['X'][0]['start_ms']='0'
    anchor['scenes']['X'][1]['start_ms']='0'  # CPU1/2 at common H, not two baselines
    clock=FakeClock(); budget=G0Budget(300,clock=clock); ledger=ManualLedger(config,instance,clock)
    with ledger.patched():
        archive,bridge=ledger.setup(budget)
        receipt=bridge.assess(anchor)
    ctx.check(receipt['state']=='SAFE','manual full-window receipt')
    fake=next(c for c in ledger.calls if c['kind']=='FAKE_PHYSICAL_LEDGER')
    segments=fake['segments']; window=F(instance['window_ms'])
    ctx.check(segments[0]['start_ms']=='0' and F(segments[-1]['end_ms'])==window,'0-W including idle tail')
    ctx.check(all(F(a['end_ms'])==F(b['start_ms']) for a,b in zip(segments,segments[1:])),
              'no gaps or double-counted waiting intervals')
    first=segments[0]
    cpu=instance['platform']['domains']['CPU']['baseline_W']['H']
    ctx.check(first['baseline_by_power_group_W']['CPU']==cpu,'CPU baseline exactly once for two active cores')
    terms=receipt['scenes']['X']['result']['manual_terms_J']
    energy=sum(map(F,terms.values()))
    ctx.check(F(receipt['safe_upper_bound_J'])==energy,'baseline/activity/external/temperature arithmetic exact')
    ctx.check(F(terms['temperature_correction'])>0 and F(terms['external'])>0,'local temperature term and common power retained')
    ctx.check(all(c.get('thermal_propagation') is False for c in ledger.calls if c['kind']=='FAKE_PHYSICAL_LEDGER'),
              'ledger is not new thermal integration')
    return {'fixture_id':'MANUAL-A22-FOUR-NODE-LEDGER','terms_J':terms,'segments':segments,
            'energy_J':str(energy),'new_thermal_integrations':0}


def A23(ctx):
    clock=FakeClock(); budget=G0Budget(300,clock=clock)
    ctx.check(isinstance(budget,MethodBudget),'actual legacy MethodBudget subclass')
    original=(budget.start,budget.seconds,budget.deadline,budget.root_identity)
    with budget.scope('phase1',150,kind='phase'):
        with budget.scope('slot',20,kind='slot') as token:
            clock.advance(19)
            ctx.check(budget.accept_formed(19,scope=token),'strictly before cutoff accepted')
            clock.advance(1)
            ctx.check(not budget.accept_formed(20,scope=token),'exact deadline rejected')
            ctx.rejects(budget.check,'slot cutoff classified',exceptions=(ScopeExhausted,))
            ctx.check(budget.accept_formed(19,scope=token),'timely formation may return late before seal')
        ctx.check(not budget.accept_formed(19,scope=token),'sealed callback rejected')
    ctx.check((budget.start,budget.seconds,budget.deadline,budget.root_identity)==original,'one immutable root/token')
    with budget.scope('phase2',300):
        clock.advance(281)
        ctx.rejects(budget.check,'root cutoff',exceptions=(ScopeExhausted,))
    return {'fixture_id':'MANUAL-A23-CUTOFF','root_seconds':300,'scope_records':budget.scope_records}


def A24(ctx):
    safe,calls,_=execute(init_delay=151,action='none')
    ctx.check(safe['S0'] is not None and safe['S1']['candidate']==safe['S0']['candidate'],
              'initialization SAFE inherited after T/2')
    ctx.check(not safe['blocks']['1'] and bool(safe['blocks']['2']),'no declared B1; B2 uses complement of empty')
    ctx.check(not any(isinstance(c,tuple) and c[0]=='build' and c[1]==1 for c in calls),'no phase1 local model')
    empty,ecalls,_=execute(init_delay=151,init_safe=False,action='none')
    ctx.check(empty['final'] is None and not any(isinstance(c,tuple) for c in ecalls),'no SAFE no local MILP')
    ctx.check(empty['reason']=='NO_COMPLETE_SAFE_INITIALIZATION','no SAFE is not infeasibility proof')
    return {'fixture_id':'MANUAL-A24-INITIALIZER-CUTOFF','safe_stages':safe['stages'],
            'no_safe_reason':empty['reason']}


def A26(ctx):
    config,instance,anchor=bundle(4); clock=FakeClock();budget=G0Budget(300,clock=clock)
    ledger=ManualLedger(config,instance,clock)
    with ledger.patched():
        archive,bridge=ledger.setup(budget)
        with budget.scope('phase1',150) as token:
            receipt=bridge.assess(anchor,scope=token)
            archive.freeze('S0')
        frozen=archive.freeze('S1')
        ctx.check(not archive.commit(anchor,receipt,source='late_callback',scope=token),'sealed old callback cannot commit')
        ctx.check(archive.frozen('S1')==frozen,'frozen full-scene S1 unaffected')
    ctx.check(set(frozen['candidate']['scenes'])=={'X','Y'},'S1 retains all scenes including unvisited')
    return {'fixture_id':'MANUAL-A26-SEALED-CALLBACK','late_commit_accepted':False}


def A27(ctx):
    output={}
    for action in ['timeout','memory','numerical','interface']:
        result,calls,_=execute(action=action)
        ctx.check(result['final'] is not None,action+': previous SAFE retained')
        if action=='timeout':
            ctx.check(result['failure'] is None,'normal cutoff is not technical fault')
            ctx.check(any(r['status'].endswith('CUTOFF') for rs in result['stages'].values() for r in rs),'cutoff terminal recorded')
        else:
            ctx.check(result['failure']['kind']=='TECHNICAL_FAILURE',action+': actual failure classified')
        output[action]={'reason':result['reason'],'failure':result['failure'],'stopped_s':result['stopped_s']}
    result,_,_=execute(action='none',idle_after=1)
    ctx.check(result['failure']['kind']=='CLEANUP_FAILURE' and result['final'] is not None,'cleanup unknown stops but retains SAFE')
    return {'fixture_id':'MANUAL-A27-FAILURE-RETENTION','outcomes':output}


def A29(ctx):
    result,_,_=execute(action='improve')
    ctx.check(result['failure'] is None,'manual complete lifecycle with two phases')
    ctx.check(result['S0'] is not None and result['S1'] is not None and result['final'] is not None,'all three anchors')
    u0,u1,uf=[F(result[key]['U_J']) for key in ('S0','S1','final')]
    ctx.check(uf<=u1<=u0,'archive energy nonincreasing; costs attributed to separate phases')
    ctx.check(result['first_legal_s'] is not None and result['first_safe_s'] is not None,'first legal/SAFE timestamps')
    ctx.check(all(r['warm_start']['state']=='INITIAL_POINT_REJECTED' for rs in result['stages'].values() for r in rs),
              'rejected numerical x0 does not erase inherited SAFE')
    return {'fixture_id':'MANUAL-A29-PHASE-ATTRIBUTION','U_S0_J':str(u0),'U_S1_J':str(u1),
            'U_final_J':str(uf),'result':result}


def A30(ctx):
    config,instance,anchor=bundle()
    for field in ('reference_timetable','reference_deployment','historical_SAFE','external_heft_result','thermal_cache'):
        bad=deepcopy(instance);bad['extra']={field:{'answer':'do not read'}}
        ctx.rejects(lambda:validate_inputs(config,bad),field+' rejected')
    ctx.check(all('reference' not in k.lower() for k in anchor),'handwritten candidate no reference payload')
    return {'fixture_id':'MANUAL-A30-REFERENCE-ISOLATION','rejected_fields':5}


def A31(ctx):
    config,instance,anchor=bundle(2)
    for key in ('window_ms',):
        bad=deepcopy(instance);bad.pop(key)
        ctx.rejects(lambda:validate_inputs(config,bad),'missing window not defaulted',exceptions=(ValueError,KeyError))
    bad=deepcopy(instance);bad['scenarios'][0]['requests'][0].pop('deadline_ms')
    ctx.rejects(lambda:validate_inputs(config,bad),'missing deadline not beta default',exceptions=(ValueError,KeyError))
    bad=deepcopy(instance)
    bad['start_domain']={'version':1,'kind':'explicit_grid_subset','by_scene_stage_ms':{
        s['id']:{i['id']:[] for i in s['stage_instances']} for s in bad['scenarios']}}
    validate_inputs(config,bad)
    ctx.rejects(lambda:derive_deployment(config,bad,anchor),'empty start sets do not become full grid')
    return {'fixture_id':'MANUAL-A31-EXPLICIT-INPUT','empty_domain_retained':True}


def A32(ctx):
    import research.chapter3_g0 as package
    from ..receipts import production_dependencies
    from ..local_model import build_local_model
    ctx.check(package.REAL_EXECUTION_ENABLED is False,'package real execution switch false')
    ctx.rejects(production_dependencies,'real evaluator dependency gate',exceptions=(RuntimeError,))
    ctx.rejects(lambda:run_g0(None,None,seconds=300,clock=FakeClock(),manual=False),
                'real coordinator entry blocked',exceptions=(PermissionError,))
    ctx.rejects(lambda:build_local_model({}, {}, condition={},budget=None,manual=False),
                'real model entry blocked',exceptions=(RuntimeError,PermissionError,ValueError))
    return {'fixture_id':'MANUAL-A32-REAL-ENTRY-DISABLED','real_enabled':False}
