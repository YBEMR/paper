"""Real-shaped Model/x0/feedback wiring with explicit handwritten fakes.

These tests never create original Model/Coefficients, solve, or evaluate heat.
Root's runner supplies ctx.check/ctx.rejects and guards scientific entrypoints.
"""
from copy import deepcopy
from types import SimpleNamespace

from ...chapter3_g0.budget import G0Budget, ScopeExhausted
from ...chapter3_g0.contract import derive_deployment, make_scene_view
from ...chapter3_g0.local_domain import make_condition
from ...chapter3_g0.local_model import (_kernel, _manual_model, _digest,
                                      inherited_source_check, build_local_model)
from ...chapter3_g0.tests.fixtures import bundle, FakeClock
from ...chapter3_g0.tests.model_replay import StoredRows
from ...chapter3_g0.tests.test_model import _options
from ..gating import WiringPermit
from .. import model_backend as backend


def _scene(instance, scene_id, *, unweighted=True):
    return make_scene_view(instance, scene_id, unweighted=unweighted)


def _manual_case():
    config, instance, candidate = bundle(4,scene_ids=('X',))
    d0 = derive_deployment(config,instance,candidate)
    condition = make_condition(config,instance,candidate,d0,'X',
        [r['stage_id'] for r in candidate['scenes']['X'][:2]],phase=2)
    options = _options(instance,candidate,'X')
    return config,instance,candidate,condition,options


def test_model_factory_and_options(ctx):
    config,instance,candidate,condition,options = _manual_case()
    clock=FakeClock(); budget=G0Budget(300,clock=clock)
    kernel=_kernel()  # Definitions/old row arithmetic only; not Model.__init__.
    rows=StoredRows(instance['platform'],options,instance['window_ms'],kernel.I)
    calls={'model':0,'options':0}
    expected=_scene(instance,'X')
    for shared,modes in expected['stage_modes'].items():
        expected['stage_modes'][shared]=[m for m in modes if m['unit_id']==condition['d0_all'][shared]]

    def fake_model(view, active_budget, progress=None):
        ctx.check(view==expected and active_budget is budget,'fake Model receives original D0 view/root')
        calls['model']+=1
        return _manual_model(kernel,view,active_budget,progress,rows)

    def fake_expand(view, active_config, *, budget):
        ctx.check(view==expected and active_config==config,'fake expander receives instance W, not config rebuild')
        calls['options']+=1
        budget.check()
        return deepcopy(options)

    deps={'kernel':kernel,'model_factory':fake_model,'expand_options':fake_expand,
          'make_scene_instance':_scene,'resolve_idle_policy':lambda obj:obj['execution_rules']['idle_policy'],
          'auto_low_policy':'auto_low_immediate_v1'}
    model=backend.build(config,instance,condition,budget,dependencies=deps,permit=WiringPermit())
    ctx.check(calls=={'model':1,'options':1},'both wired production-shape seams reached exactly once through fakes')
    ctx.check(model.instance==expected and model.budget is budget,'complete scientific view and same root retained')
    ctx.check(model.preprocessing['wiring_profile']=='SIMULATION' and
              model.preprocessing['manual_origin'] is None,'wiring simulation is distinct from legacy manual row profile')
    ctx.check(model.formulation['relax_auxiliary_integrality'] is True and
              model.formulation['energy_lower_bounds'] is True and
              model.formulation['preeliminate_closed_anchors'] is True,
              'frozen C flags override legacy artificial default switches')
    protected=inherited_source_check()
    ctx.check(protected['numerical_suffix_exact_text'] and protected['numerical_suffix_matches'],
              'all original numerical suffix text remains protected')
    ctx.check(any(r['tag'].startswith('complete_energy') for r in model.rows),
              'handwritten rows exercise complete energy export, not just a mock return flag')
    ctx.rejects(lambda:backend.build(config,instance,condition,budget,permit=WiringPermit()),
                'simulation cannot fall through to original Model or RC factory',exceptions=(PermissionError,))
    broken=dict(deps)
    def wrong_model(view,active_budget,progress=None):
        result=_manual_model(kernel,view,active_budget,progress,rows)
        result.instance['window_ms']='999'
        return result
    broken['model_factory']=wrong_model
    before=calls['options']
    ctx.rejects(lambda:backend.build(config,instance,condition,budget,dependencies=broken,permit=WiringPermit()),
                'factory changes to view are rejected before option processing')
    ctx.check(calls['options']==before,'wrong view did not reach expander')
    return {'fixture_id':'G0-WIRING-MODEL','fake_calls':calls,'row_count':len(model.rows),
            'variable_count':len(model.names),'new_real_models':0,'new_RC_coefficients':0}


class StubBridge:
    """Tests model_backend sequencing; real-profile receipt tests are separate."""
    def __init__(self,budget):
        self.budget=budget; self.accuracy={'test':'EXPLICIT_FAKE'}
        self.calls=[]

    def bind_model_view(self,instance,candidate,raw,*,scope=None):
        self.calls.append('bind')
        wrapped=deepcopy(raw)
        wrapped['g0_context']={'kind':'SIMULATION','root':self.budget.root_identity,
            'input':_digest(instance),'candidate':_digest(candidate)}
        return wrapped

    def validate_model_view(self,instance,candidate,receipt,*,scope=None):
        self.calls.append('validate')
        expected={'input_sha256':_digest(instance),'candidate_sha256':_digest(candidate)}
        if receipt.get('evidence_identity')!=expected:
            raise ValueError('SIMULATION_VIEW_IDENTITY_MISMATCH')
        if receipt.get('g0_context',{}).get('root')!=self.budget.root_identity:
            raise ValueError('SIMULATION_ROOT_MISMATCH')
        return deepcopy(receipt)


def _evaluation_case():
    config,instance,candidate,condition,_=_manual_case()
    view=_scene(instance,'X')
    for shared,modes in view['stage_modes'].items():
        view['stage_modes'][shared]=[m for m in modes if m['unit_id']==condition['d0_all'][shared]]
    clock=FakeClock();budget=G0Budget(300,clock=clock)
    model=SimpleNamespace(instance=view,budget=budget)
    bridge=StubBridge(budget)
    raw={'problem_id':view['id'],'state':'SAFE','rankable_energy':True,
         'completed_at_elapsed_s':0.0,'weighted_energy_J':['1','1'],
         'evidence_identity':{'input_sha256':_digest(view),'candidate_sha256':_digest(candidate)},
         'violations':[]}
    return model,candidate,budget,clock,bridge,raw


def test_prepare_gate_and_x0(ctx):
    model,candidate,budget,clock,bridge,raw=_evaluation_case()
    calls={'evaluate':0,'complete':0,'strict':0,'feedback':0}
    completion={'state':'INITIAL_POINT_REJECTED','x0':None,'reason':'FAKE_NUMERICAL_REJECTION'}
    def evaluate(m,c,a,b):
        ctx.check(m is model and c is candidate and b is budget,'raw model evaluator receives current view/candidate/root')
        calls['evaluate']+=1
        return raw
    def complete(m,c,e,b):
        ctx.check(e is raw and 'g0_context' not in e,'original raw receipt reaches numerical completer unchanged')
        calls['complete']+=1
        return deepcopy(completion)
    deps={'evaluate_model_candidate':evaluate,'complete_initial_point':complete,
          'checked_thermal_witnesses':lambda *args:[], 'add_thermal_feedback':lambda *args:None}
    result=backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit())
    ctx.check(result['state']=='INITIAL_POINT_REJECTED' and result['x0'] is None,
              'numerical rejection permits a bare search result without inventing x0')
    ctx.check(bridge.calls==['bind','validate'] and 'g0_context' not in raw,
              'view provenance is checked before x0 and raw remains intact')
    completion.update(state='INITIAL_POINT_READY',x0=[1.0])
    ready=backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit())
    ctx.check(ready['x0']==[1.0] and ready['state']=='INITIAL_POINT_READY','admitted fake numerical vector retained')
    completion['state']='INITIAL_POINT_REJECTED'
    ctx.rejects(lambda:backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit()),
                'rejected-but-present numerical x0 is an interface failure')
    before=calls['complete']; raw['state']='UNRESOLVED';raw['rankable_energy']=False
    unknown=backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit())
    ctx.check(unknown['x0'] is None and calls['complete']==before,'unresolved view skips x0 completion')
    raw['state']='THERMAL_VIOLATION'
    ctx.rejects(lambda:backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit()),
                'certified anchor versus view violation stops instead of inventing a vector',exceptions=(ArithmeticError,))
    before=calls['evaluate'];clock.advance(300)
    ctx.rejects(lambda:backend.prepare(model,candidate,budget,bridge,dependencies=deps,permit=WiringPermit()),
                'expired root does not start model evaluation',exceptions=(ScopeExhausted,))
    ctx.check(calls['evaluate']==before,'no evaluator work after cutoff')
    return {'fixture_id':'G0-WIRING-X0','calls':calls,'new_real_evaluations':0,'new_real_x0':0}


def test_strict_feedback_gate(ctx):
    model,candidate,budget,clock,bridge,raw=_evaluation_case()
    calls={'strict':0,'add':0}
    raw['state']='THERMAL_VIOLATION';raw['rankable_energy']=False
    raw['violations']=[{'manual_strict':True}]
    wrapped=bridge.bind_model_view(model.instance,candidate,raw)
    def strict(m,c,e):
        calls['strict']+=1
        ctx.check('g0_context' not in e,'strict witness checker receives original model-view shape')
        return e['violations'] if e.get('state')=='THERMAL_VIOLATION' else []
    def add(m,c,e):
        calls['add']+=1
        return {'state':'ADDED','added':True,'kind':'SIMULATION_ROW_ONLY'}
    deps={'evaluate_model_candidate':lambda *args:None,'complete_initial_point':lambda *args:None,
          'checked_thermal_witnesses':strict,'add_thermal_feedback':add}
    result=backend.feedback(model,candidate,wrapped,budget,bridge,dependencies=deps,permit=WiringPermit())
    ctx.check(result['added'] and calls=={'strict':1,'add':1},'strict gate precedes unchanged feedback seam')
    wrapped['state']='SAFE';wrapped['violations']=[]
    result=backend.feedback(model,candidate,wrapped,budget,bridge,dependencies=deps,permit=WiringPermit())
    ctx.check(result['added'] is False and calls['add']==1,'no strict witness means no new feedback row')
    wrong=deepcopy(wrapped);wrong['evidence_identity']['input_sha256']='OTHER_INPUT'
    before=deepcopy(calls)
    ctx.rejects(lambda:backend.feedback(model,candidate,wrong,budget,bridge,dependencies=deps,permit=WiringPermit()),
                'wrong view rejected before strict checker or row add')
    ctx.check(calls==before,'identity conflict causes no numeric feedback work')
    clock.advance(300)
    ctx.rejects(lambda:backend.feedback(model,candidate,wrapped,budget,bridge,dependencies=deps,permit=WiringPermit()),
                'feedback cannot be added after effective deadline',exceptions=(ScopeExhausted,))
    ctx.check(calls==before,'no strict or row work after cutoff')
    return {'fixture_id':'G0-WIRING-FEEDBACK','calls':calls,'new_real_feedback_rows':0}


def test_model_real_permission_closed(ctx):
    ctx.rejects(lambda:backend.build({}, {}, {}, None, permit=None),
                'missing permit cannot initialize original Model',exceptions=(PermissionError,))
    ctx.rejects(lambda:WiringPermit(kind='REAL'),'REAL capability cannot be minted this stage',exceptions=(PermissionError,))
    ctx.rejects(lambda:backend.resolve_build_dependencies(SimpleNamespace(kind='REAL'),None),
                'an arbitrary REAL string/object is not a permit',exceptions=(PermissionError,))
    ctx.rejects(lambda:build_local_model({}, {}, condition={},budget=None,
        manual=True,wiring_permit=WiringPermit(),wiring_dependencies={}),
        'manual and real-shaped wiring profiles cannot be mixed')
    return {'fixture_id':'G0-WIRING-PERMISSION','real_enabled':False}
