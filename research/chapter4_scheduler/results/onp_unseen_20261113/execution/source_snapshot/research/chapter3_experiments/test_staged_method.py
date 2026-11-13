"""K137 two-pass lifecycle checks, with fake workers and one tiny real model.

Fabricated H/M/L energies below are control-flow markers. The sole physical
fixture uses the inherited small_case unchanged and only echoes its freshly
completed initial points. Neither fixture is optimization or quality evidence.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

import augmented_method
import fixed_unit_neighborhood as fixed_condition
import fixed_unit_neighborhood_adapter as fixed_adapter
import matlab_bridge
import milp
import neighborhood
import neighborhood_adapter
import partial_method
import scene_adapter
import staged_method
from control_policy import with_auto_low_idle
from inputs import load_config
from test_neighborhood_method import Harness
from test_partial_deployment import small_case


REPO = Path(__file__).resolve().parents[2]
RECORDS = {'scope': 'K137 bounded correctness only; no optimizer or quality evidence',
           'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0}


def write(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=False), encoding='utf-8')


class StagedHarness(Harness):
    """Real domain/receipt/aggregation and complement gates; fabricated physics."""
    def __init__(self, **options):
        super().__init__(**options)
        self.conditions, self.built, self.completions, self.calls = [], [], [], []
        self.aggregate_calls = 0
        self.last_stage2_vector = None
        self.contexts = []

    def condition_factory(self, *args, **kwargs):
        result = super().condition_factory(*args, **kwargs)
        self.conditions.append(result)
        return result

    def second_condition_factory(self, *args, **kwargs):
        budget = kwargs['budget']; self.budgets.append(id(budget)); self.clock.tick()
        self.trace.append(('second_condition', self.clock.now))
        result = fixed_condition.make_fixed_unit_condition(*args, **kwargs)
        if self.options.get('stale_condition'):
            result['budget_identity']['token']='a_stale_other_invocation_token'
            result['condition_sha256']=neighborhood._condition_hash(result)
        self.condition = result; self.conditions.append(result)
        if self.options.get('expire_transition'): self.clock.tick(400)
        return result

    def builder(self, instance, config, **kwargs):
        budget = kwargs['budget']; sid = kwargs['fixed_scene_id']
        condition = kwargs['neighborhood_condition']
        phase = 1 if condition['protocol'] == neighborhood.PROTOCOL else 2
        self.budgets.append(id(budget)); self.clock.tick()
        self.assert_original(instance)
        validator=(neighborhood.validate_n1_condition if phase==1
                   else fixed_condition.validate_fixed_unit_condition)
        validator(instance,condition,budget=budget,
                  shared_deployment=kwargs['fixed_shared_deployment'])
        serial = len(self.built)+1
        # Equal dimension, different column meanings in the last scene. This
        # makes replayed vectors and complement maps observable, independently
        # of a length check.
        gate, choice = (0, 1) if serial == 4 else (1, 0)
        names = ['']*3
        names[gate] = 'w:fixture_gate_'+sid+'_phase_'+str(phase)
        names[choice] = 'z:fixture_choice_'+sid+'_phase_'+str(phase)
        names[2] = 'fixture:model_generation_'+str(serial)
        row = {'coef': {choice: 1., gate: 1000.}, 'rhs': 1001.,
               'tag': 'thermal_propagation/fixture_'+str(serial)}
        view = scene_adapter.make_scene_instance(instance, sid)
        for shared, unit in kwargs['fixed_shared_deployment'].items():
            if shared in view['stage_modes']:
                view['stage_modes'][shared] = [m for m in view['stage_modes'][shared]
                                                if m['unit_id'] == unit]
        model = SimpleNamespace(instance=view, budget=budget, names=names, rows=[row],
            phase=phase, serial=serial, gate=gate, choice=choice, scenes={sid: {}},
            neighborhood_condition=deepcopy(condition),
            formulation={'fixed_device_neighborhood': True},
            preprocessing={'source_input_sha256': milp._digest(instance),
                'fixed_shared_deployment': deepcopy(self.mapping),
                'neighborhood_condition_sha256': condition['condition_sha256']})
        model.summary = lambda: {'problem_id': view['id'], 'variables':3, 'rows':1,
            'fixture_generation':serial, 'neighborhood':{'condition_sha256':condition['condition_sha256']}}
        def payload():
            budget.check()
            low = np.zeros(3); high = np.ones(3)
            low[2] = high[2] = serial
            objective = np.zeros(3); objective[choice] = 1.
            return {'c':objective, 'A':sparse.csr_matrix([[row['coef'].get(j,0.) for j in range(3)]]),
                'b':np.array([row['rhs']]), 'Aeq':sparse.csr_matrix((0,3)), 'beq':np.empty(0),
                'lb':low, 'ub':high, 'intcon':np.array([choice])}
        model.as_solver_dict = payload
        self.built.append(model); self.models[sid] = model
        self.trace.append(('model', sid, phase, serial, self.clock.now))
        return model

    def completer(self, model, proposal, evaluation, budget):
        self.budgets.append(id(budget)); self.clock.tick()
        assert evaluation['evidence_identity'] == {
            'input_sha256':milp._digest(model.instance), 'candidate_sha256':milp._digest(proposal)}
        model.base_candidate = deepcopy(proposal)
        point = np.zeros(3); point[model.gate] = 1.; point[2] = model.serial
        self.completions.append({'phase':model.phase, 'sid':next(iter(proposal['scenes'])),
            'candidate':deepcopy(proposal), 'generation':model.serial, 'x0':point.tolist()})
        if model.phase == 2 and self.options.get('reject_second_x0'):
            return {'state':'INITIAL_POINT_REJECTED', 'reason':'MOCK_X0_REJECTED', 'x0':None}
        checked = matlab_bridge._prepare(model.as_solver_dict(), x0=point)
        assert checked['x0_validation']['accepted_numerically']
        return {'state':'INITIAL_POINT_READY', 'reason':'INITIAL_POINT_READY', 'x0':point}

    def proposed(self, model, number):
        out = deepcopy(model.base_candidate)
        if not number: return out
        sid = next(iter(out['scenes']))
        local = next(row for row in out['scenes'][sid] if 'A.pre' not in row['stage_id'])
        local.update(opp='M' if model.phase == 1 else 'L', start_ms='15')
        if model.phase == 2 and self.options.get('worse_second'):
            return deepcopy(self.seed_parts[sid])
        if model.phase == 2 and self.options.get('shared_change'):
            a = next(row for row in out['scenes'][sid] if 'A.pre' in row['stage_id'])
            # Only AB changes A; AC keeps its original A. Scene OPP choices
            # must remain independent despite the common execution unit.
            if sid == next(iter(self.seed_parts)): a['opp'] = 'M'
        return out

    def decoder(self, model, vector):
        assert len(vector) == 3
        assert vector[2] == model.serial, 'stale same-size model vector'
        return self.proposed(model, int(round(vector[model.choice])))

    def recorder(self, *args, **kwargs):
        return partial_method.PartialRecorder(*args, decoder=self.decoder, **kwargs)

    def context_factory(self, **kwargs):
        owner = self
        class Context(augmented_method.AugmentedMethodContext):
            def recorder_factory(self, *args, **kw):
                return super().recorder_factory(*args, decoder=owner.decoder, **kw)
        context = Context(**kwargs); self.contexts.append(context)
        return context

    def second_scene_evaluator(self, instance, condition, sid, proposal, *, budget, accuracy=None):
        self.budgets.append(id(budget)); self.clock.tick(); self.assert_original(instance)
        with patch.object(scene_adapter, 'evaluate_piecewise', side_effect=self.physical):
            return fixed_adapter.evaluate_fixed_unit_scene(instance, condition, sid, proposal,
                                                          budget=budget, accuracy=accuracy)

    def aggregator(self, *args, **kwargs):
        self.aggregate_calls += 1
        result = super().aggregator(*args, **kwargs)
        if self.aggregate_calls == 3 and self.options.get('uncommitted_local'):
            return {'state':'UNRESOLVED', 'rankable_energy':False,
                    'reason':'MOCK_AFTER_LOCAL_STORE_BEFORE_FULL_COMMIT'}
        if self.aggregate_calls == 3 and self.options.get('aggregate_error'):
            raise OSError('MOCK_AGGREGATE_INTERRUPTION_AFTER_LOCAL_STORE')
        return result

    def session_factory(self, workdir, **kwargs):
        owner = self
        class Session:
            def __init__(self):
                self.workdir=Path(workdir); self.workdir.mkdir(parents=True)
                self.budget=kwargs['budget']; self.event_consumer=None; self.counter=0
                self.closed=self.request_blocked=False
                owner.budgets.append(id(self.budget)); owner.sessions.append(self); owner.clock.tick()
            def solve(self, payload, *, remaining_s, budget, x0=None, **request):
                assert budget is self.budget
                model = owner.built[-1] if len(payload['c']) == 4 else owner.built[self.counter]
                self.counter += 1; owner.budgets.append(id(budget))
                prefix=self.workdir/('request_%03d'%self.counter)
                vector=np.zeros(3); vector[model.gate]=1.; vector[model.choice]=1.; vector[2]=model.serial
                if model.phase == 2: vector=np.append(vector, 0.)
                if model.phase == 2 and owner.options.get('stale_vector') and owner.last_stage2_vector is not None:
                    vector=np.asarray(owner.last_stage2_vector)
                if model.phase == 2 and owner.options.get('no_second_candidate'): vector=np.empty(0)
                if model.phase == 2 and owner.options.get('expire_second_candidate'): owner.clock.tick(400)
                call={'phase':model.phase,'sid':model.instance['scenarios'][0]['id'],
                    'generation':model.serial,'remaining_s':remaining_s,'budget_remaining_s':budget.remaining,
                    'solver_max_time_s':request.get('solver_max_time_s'),
                    'at_s':budget.elapsed,'x0':None if x0 is None else np.asarray(x0).tolist(),
                    'vector':vector.tolist(),'payload_dimension':len(payload['c'])}
                owner.calls.append(call); owner.trace.append(('request',model.phase,call['sid']))
                events=[{'kind':'solver_entered','event_number':1}]
                callbacks=[]
                if vector.size:
                    event={'kind':'callback','event_number':2,'x':vector.tolist(),
                        'values':{'fval':float(payload['c'] @ vector)}}
                    events.append(event); callbacks=[event]
                owner.inside=True
                for event in events:
                    owner.clock.tick()
                    write(Path(str(prefix)+'.event_%06d.json'%event['event_number']),event)
                    if self.event_consumer: self.event_consumer(prefix)
                owner.inside=False; owner.clock.tick()
                if model.phase == 2 and vector.size: owner.last_stage2_vector=vector.tolist()
                if (owner.options.get('fault_first') and model.phase == 1 or
                        owner.options.get('fault_second') and model.phase == 2):
                    raise RuntimeError('MOCK_WORKER_FAULT_NO_RESTART')
                if owner.options.get('expire_before_transition') and self.counter == 2: owner.clock.tick(400)
                if owner.options.get('hidden_blocked') and model.phase == 1:self.request_blocked=True
                return {'status':'SOLVED','x':vector.tolist(),'exitflag':1,
                    'fval':float(payload['c'] @ vector) if vector.size else None,
                    'budget_valid':budget.remaining>0, 'accepted_for_evaluation':budget.remaining>0,
                    'intlinprog_entered':True,'output':{},'callbacks':callbacks}
            def close(self):
                self.event_consumer=None; self.closed=True; owner.clock.tick(2)
        return Session()

    def run(self, directory, *, seconds=300, **extra):
        _, _, parts=small_case()
        opened={sid:[row['stage_id'] for row in part['scenes'][sid] if 'A.pre' not in row['stage_id']]
                for sid,part in parts.items()}
        return staged_method.execute_staged_fixed_unit_opp_start(self.loader,directory,
            shared_deployment={'A.pre':'CPU1'},opened_by_scene=opened,seconds=seconds,
            clock=self.clock,seed_iterator=self.seed_iterator,seed_scene_evaluator=self.seed_scene_evaluator,
            condition_factory=self.condition_factory,second_condition_factory=self.second_condition_factory,
            n1_scene_evaluator=self.n1_scene_evaluator,second_scene_evaluator=self.second_scene_evaluator,
            model_builder=self.builder,initial_completer=self.completer,model_evaluator=self.evaluator,
            aggregator=self.aggregator,recorder_factory=self.recorder,session_factory=self.session_factory,
            augmented_context_factory=self.context_factory,feedback_adder=self.feedback,**extra)


class StagedMethodTests(unittest.TestCase):
    def setUp(self):
        root=REPO/'.runtime/staged_method_correctness'; root.mkdir(parents=True,exist_ok=True)
        self.path=root/('case_'+uuid4().hex); self.path.mkdir()

    def run_fixture(self, **options):
        h=StagedHarness(**options); result=h.run(self.path/uuid4().hex)
        self.assertEqual(result['state'],'SAFE',result.get('error',result))
        self.assertEqual(result['safe_upper_bound_J'],result['aggregation']['safe_upper_bound_J'])
        self.assertEqual(result['safe_candidate'],result['aggregation']['safe_candidate'])
        return h,result

    def test_one_loader_seed_session_budget_declared_two_pass_order_and_residual_cap(self):
        h,out=self.run_fixture()
        self.assertEqual(len(h.seed_views),1); self.assertEqual(len(h.sessions),1)
        self.assertEqual(len(set(h.budgets)),1)
        self.assertEqual([(p['phase_index'],p['name']) for p in out['phases']],
                         [(1,'N1'),(2,'all_stage_opp_start')])
        sids=out['original_scene_order']
        self.assertEqual([(c['phase'],c['sid']) for c in h.calls],[(p,s) for p in (1,2) for s in sids])
        self.assertEqual(len(h.built),4)
        for call in h.calls[:2]: self.assertEqual(call['solver_max_time_s'],60)
        for index,call in enumerate(h.calls[2:]):
            self.assertLessEqual(call['solver_max_time_s'],min(60,call['budget_remaining_s']/(2-index))+1e-8)
        self.assertTrue(all(c['remaining_s']<=300-c['at_s']+1e-8 for c in h.calls))
        self.assertEqual(h.instance,h.input_before)
        RECORDS['one_invocation_two_passes']={'result':out,'calls':h.calls,'completions':h.completions}
        # Force R/k below the 60 s cap. The fixture clock does not advance
        # between allocation and native solve, so this checks the allocation
        # itself, rather than merely accepting any value below 60 seconds.
        limited=StagedHarness(); limited_out=limited.run(self.path/uuid4().hex,seconds=100)
        self.assertEqual(limited_out['state'],'SAFE',limited_out.get('error',limited_out))
        self.assertEqual(limited_out['timing']['limit_s'],100)
        self.assertEqual(limited.primary_budget.seconds,100)
        self.assertEqual(set(limited.budgets),{id(limited.primary_budget)})
        self.assertEqual(len(limited.seed_views),1);self.assertEqual(len(limited.sessions),1)
        self.assertEqual([(c['phase'],c['sid']) for c in limited.calls],
                         [(p,s) for p in (1,2) for s in sids])
        first_second=limited.calls[2]
        self.assertLess(first_second['solver_max_time_s'],60)
        self.assertAlmostEqual(first_second['solver_max_time_s'],
                               first_second['budget_remaining_s']/2,places=10)
        self.assertTrue(all(c['remaining_s']<=100-c['at_s']+1e-8 for c in limited.calls))
        RECORDS['residual_budget_dominates']={'result':limited_out,'calls':limited.calls,
            'completions':limited.completions,'budget_limit_s':limited.primary_budget.seconds,
            'one_root_budget':len(set(limited.budgets))==1}

    def test_own_improvement_re_lifted_through_new_model_not_old_vector(self):
        h,out=self.run_fixture()
        self.assertEqual([h._local_opp(c['candidate'],c['sid']) for c in h.completions],['H','H','M','M'])
        for call,completion in zip(h.calls,h.completions):
            self.assertEqual(call['x0'][:3],completion['x0'])
            self.assertEqual(len(call['x0']),3 if call['phase']==1 else 4)
        self.assertEqual(len({tuple(c['x0']) for c in h.completions}),4)
        self.assertTrue(all(c['seed_candidate']==h.conditions[0]['seed_candidate'] for c in h.conditions))
        self.assertEqual(Fraction(out['safe_upper_bound_J']),6)
        values=[Fraction(r['safe_upper_bound_J']) for r in out['global_updates']]
        self.assertEqual(values,sorted(values,reverse=True))
        self.assertEqual(out['committed_safe_snapshot']['safe_candidate'],out['safe_candidate'])

    def test_no_or_worse_second_candidate_preserves_first_complete_U(self):
        for option in ('no_second_candidate','worse_second'):
            with self.subTest(option=option):
                h,out=self.run_fixture(**{option:True})
                self.assertEqual(Fraction(out['safe_upper_bound_J']),8)
                self.assertEqual(len(h.calls),4)
                self.assertTrue(all(h._local_opp({'scenes':{sid:rows}},sid)=='M'
                                    for sid,rows in out['safe_candidate']['scenes'].items()))

    def test_second_x0_rejection_uses_bare_current_domain_and_keeps_U(self):
        h,out=self.run_fixture(reject_second_x0=True,no_second_candidate=True)
        self.assertEqual(Fraction(out['safe_upper_bound_J']),8)
        self.assertTrue(all(call['x0'] is None for call in h.calls[2:]))
        self.assertTrue(all(c['payload_dimension']==4 for c in h.calls[2:]))
        self.assertTrue(all(r['bare_MILP_fallback'] for r in out['phases'][1]['scenes'].values()))

    def test_worker_fault_preserves_committed_U_and_cannot_restart_next_phase(self):
        for option,count in (('fault_first',1),('fault_second',3),('hidden_blocked',1)):
            with self.subTest(option=option):
                h,out=self.run_fixture(**{option:True})
                self.assertEqual(len(h.calls),count)
                self.assertTrue(out['search_failure_latched'])
                self.assertEqual(len(h.sessions),1)
                self.assertLess(Fraction(out['safe_upper_bound_J']),10)
                if option=='hidden_blocked':
                    self.assertEqual(out['reason'],'SOLVER_INTERFACE_ERROR')
                    self.assertEqual(out['technical_state'],'FAILED')

    def test_local_store_without_full_commit_is_not_second_pass_warm(self):
        h,out=self.run_fixture(uncommitted_local=True,no_second_candidate=True)
        self.assertEqual(Fraction(out['safe_upper_bound_J']),9)
        second=[c for c in h.completions if c['phase']==2]
        self.assertEqual([h._local_opp(c['candidate'],c['sid']) for c in second],['M','H'])
        self.assertTrue(any(r['state']=='UNRESOLVED' for r in out['aggregation_attempts']))
        self.assertTrue(all(r['initialisation']['source']=='last_committed_full_aggregate'
                            for r in out['phases'][1]['scenes'].values()))
        RECORDS['partial_local_store_not_warm']={'result':out,'completions':h.completions}

    def test_exception_after_local_store_latches_and_blocks_phase_transition(self):
        h,out=self.run_fixture(aggregate_error=True)
        self.assertEqual(len(h.calls),2)
        self.assertEqual(len(h.conditions),1)
        self.assertEqual(Fraction(out['safe_upper_bound_J']),9)
        self.assertTrue(out['search_failure_latched'])

    def test_expiry_before_transition_never_builds_second_pass(self):
        h,out=self.run_fixture(expire_before_transition=True)
        self.assertTrue(out['budget_exhausted'])
        self.assertEqual(len(h.conditions),1); self.assertEqual(len(h.built),2)
        self.assertEqual(Fraction(out['safe_upper_bound_J']),8)

    def test_expiry_during_transition_cannot_start_new_model_or_request(self):
        h,out=self.run_fixture(expire_transition=True)
        self.assertTrue(out['budget_exhausted'])
        self.assertEqual(len(h.conditions),2); self.assertEqual(len(h.built),2)
        self.assertEqual(len(h.calls),2); self.assertEqual(Fraction(out['safe_upper_bound_J']),8)

    def test_late_second_candidate_cannot_manufacture_U(self):
        h,out=self.run_fixture(expire_second_candidate=True)
        self.assertTrue(out['budget_exhausted'])
        self.assertEqual(Fraction(out['safe_upper_bound_J']),8)
        self.assertTrue(all(r['committed_at_s']<300 for r in out['global_updates']))

    def test_old_condition_replay_is_rejected_before_second_model(self):
        h,out=self.run_fixture(stale_condition=True)
        self.assertEqual(len(h.built),2); self.assertEqual(len(h.calls),2)
        self.assertEqual(Fraction(out['safe_upper_bound_J']),8)
        self.assertTrue(out['search_failure_latched'])

    def test_same_dimension_old_vector_rejected_by_new_original_rows(self):
        h,out=self.run_fixture(stale_vector=True)
        self.assertEqual(len(h.calls),4)
        self.assertEqual(len(h.calls[2]['vector']),len(h.calls[3]['vector']))
        self.assertEqual(h.calls[2]['vector'],h.calls[3]['vector'])
        self.assertTrue(h.contexts[0].failed)
        self.assertTrue(out['search_failure_latched'])
        self.assertEqual(Fraction(out['safe_upper_bound_J']),7)
        self.assertTrue(h.contexts[0].summary()['requests'][-1]['latched_unresolved'])

    def test_old_complement_mapping_replay_rejects_new_x0_and_latches(self):
        original=augmented_method.build_live_augmented_payload; previous=[]
        def stale_mapping(payload,labels):
            augmented,mapping=original(payload,labels)
            if previous: mapping=deepcopy(previous[0])
            else: previous.append(deepcopy(mapping))
            return augmented,mapping
        with patch.object(augmented_method,'build_live_augmented_payload',side_effect=stale_mapping):
            h,out=self.run_fixture(no_second_candidate=True)
        self.assertEqual(len(h.calls),3)
        self.assertTrue(h.contexts[0].failed)
        self.assertTrue(out['search_failure_latched'])
        self.assertEqual(Fraction(out['safe_upper_bound_J']),8)

    def test_shared_A_unit_fixed_with_independent_scene_OPP_and_start_domain(self):
        h,out=self.run_fixture(shared_change=True)
        a=[next(r for r in rows if 'A.pre' in r['stage_id']) for rows in out['safe_candidate']['scenes'].values()]
        self.assertEqual({r['unit'] for r in a},{'CPU1'})
        self.assertEqual({r['opp'] for r in a},{'M','H'})
        old,new=h.conditions
        for sid,rows in new['seed_options_by_scene'].items():
            for stage,seed in rows.items():
                self.assertEqual(seed,old['seed_options_by_scene'][sid][stage])
                self.assertIn(stage,new['opened_by_scene'][sid])
                self.assertTrue(neighborhood._member(new,sid,stage,seed['unit'],'M','20'))
                self.assertFalse(neighborhood._member(new,sid,stage,'CPU999','M','20'))
        self.assertTrue(all('A.pre' not in stage for rows in old['opened_by_scene'].values() for stage in rows))

    def test_old_default_domain_and_owned_protocol_cannot_be_relabelled(self):
        old=Harness(closed_opp_escape=True); out=old.run(self.path/'old_default')
        self.assertEqual(Fraction(out['safe_upper_bound_J']),10)
        self.assertNotIn('staged',out['protocol']); self.assertNotIn('phases',out)
        called=[]
        def loader(budget): called.append(True); raise AssertionError('invalid override must fail before load')
        for override in ({'_second_phase':{}},{'_method_identity':{}},{'membership_checker':lambda *a:None}):
            with self.subTest(override=tuple(override)),self.assertRaises(ValueError):
                staged_method.execute_staged_fixed_unit_opp_start(loader,self.path/uuid4().hex,
                    shared_deployment={'A.pre':'CPU1'},opened_by_scene={},**override)
        for cap in (None,True,0,-1,60.01,float('inf'),float('nan')):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                staged_method.execute_staged_fixed_unit_opp_start(loader,self.path/uuid4().hex,
                    shared_deployment={'A.pre':'CPU1'},opened_by_scene={},scene_slice_s=cap)
        self.assertFalse(called)

    def test_true_tiny_two_scene_four_request_lifecycle_rebuilds_transport_and_x0(self):
        config=with_auto_low_idle(load_config()); instance,shared,parts=small_case()
        before=scene_adapter.canonical_hash(instance)
        opened={sid:[r['stage_id'] for r in c['scenes'][sid] if 'A.pre' not in r['stage_id']]
                for sid,c in parts.items()}
        models,calls,sessions,loads=[],[],[],[]
        def loader(budget):
            budget.check(); loads.append(id(budget)); return deepcopy(config),deepcopy(instance)
        def builder(original,cfg,**kwargs):
            model=milp.build_model(original,cfg,**kwargs); models.append(model); return model
        class Echo:
            def __init__(self,workdir,*,total_budget_s,budget):
                self.workdir=Path(workdir); self.workdir.mkdir(); self.budget=budget
                self.counter=0; self.event_consumer=None; self.closed=self.request_blocked=False
                sessions.append(self)
            def solve(self,payload,*,remaining_s,budget,x0=None,**kwargs):
                budget.check(); assert budget is self.budget and x0 is not None
                prepared=matlab_bridge._prepare(payload,x0=x0)
                assert prepared['x0_validation']['accepted_numerically']
                self.counter+=1; vector=np.asarray(x0).reshape(-1).tolist()
                prefix=self.workdir/('request_%03d'%self.counter)
                fval=float(payload['c'] @ np.asarray(vector))
                event={'kind':'callback','event_number':2,'x':vector,'values':{'fval':fval}}
                for item in ({'kind':'solver_entered','event_number':1},event):
                    write(Path(str(prefix)+'.event_%06d.json'%item['event_number']),item)
                    if self.event_consumer:self.event_consumer(prefix)
                calls.append({'budget_id':id(budget),'dimension':len(vector),
                    'original_n':len(models[self.counter-1].names),
                    'condition_sha256':models[self.counter-1].neighborhood_condition['condition_sha256'],
                    'x0_sha256':scene_adapter.canonical_hash(vector),'x0':vector,'x0_admitted':True})
                return {'status':'SOLVED','x':vector,'fval':fval,'exitflag':1,
                    'budget_valid':budget.remaining>0,'accepted_for_evaluation':budget.remaining>0,
                    'intlinprog_entered':True,'output':{},'callbacks':[event]}
            def close(self):self.event_consumer=None;self.closed=True
        out=staged_method.execute_staged_fixed_unit_opp_start(loader,self.path/'real_tiny',
            shared_deployment=shared,opened_by_scene=opened,seconds=300,
            model_builder=builder,session_factory=Echo)
        self.assertEqual(out['state'],'SAFE',out.get('error',out))
        self.assertEqual(out['reason'],'SCENE_SEARCH_SEQUENCE_COMPLETE',out.get('error',out))
        self.assertEqual(len(calls),4);self.assertEqual(len(models),4);self.assertEqual(len(sessions),1)
        self.assertEqual(len(loads),1);self.assertEqual(len({r['budget_id'] for r in calls}|set(loads)),1)
        self.assertTrue(all(c['dimension']==c['original_n'] for c in calls[:2]))
        self.assertTrue(all(c['dimension']>c['original_n'] for c in calls[2:]))
        self.assertNotEqual(calls[0]['condition_sha256'],calls[2]['condition_sha256'])
        self.assertTrue(sessions[0].closed)
        self.assertEqual(out['weighted_energy_J'],out['initial_global_weighted_energy_J'])
        self.assertFalse(out['strict_improvement_over_initial_certified'])
        self.assertFalse(out['independently_proven_optimal']);self.assertFalse(out['independently_proven_infeasible'])
        self.assertEqual(scene_adapter.canonical_hash(instance),before)
        transport=out['augmented_transport'];self.assertEqual(len(transport['requests']),2)
        self.assertFalse(transport['latched_unresolved'])
        self.assertNotEqual(transport['requests'][0]['label_sha256'],transport['requests'][1]['label_sha256'])
        for item in transport['requests']:
            self.assertTrue(item['callback_publications_complete'])
            self.assertTrue(any(c['source']=='request_initial_point' and c['accepted'] for c in item['numerical_checks']))
        RECORDS['real_tiny_two_pass_echo']={'input':instance,'config':config,'result':out,'calls':calls,
            'model_summaries':[m.summary() for m in models],
            'native_calls':0,'research_calls':0,'original_scale_models':0}


if __name__=='__main__':
    unittest.main(verbosity=2)
