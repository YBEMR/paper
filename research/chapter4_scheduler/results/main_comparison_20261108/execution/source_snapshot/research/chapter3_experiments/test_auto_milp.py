"""K112 finite correctness fixtures, never a research optimization call.

Scheduling projections use an independently filled exact integer vector and
Cartesian legality oracle. One hand-written Stage is continuously evaluated
once for real x0 admission. No solver is started or queried.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import subprocess
import unittest

import numpy as np

import initial_point
import milp
from control_policy import with_auto_low_idle
from inputs import load_config
from matlab_bridge import _prepare
from run_milp_precheck import (candidate_key, canonical_structure_vector,
    exact_row_residuals, independent_assignments, independent_check, select_fixture)
from schedules import validate_schedule
from test_control_policy import base_input, fixture_candidate
from thermal import Budget

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = '2e72ad6c65fcb31aad337f5eaf5515a9f549fee3'
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)
RECORDS = {'scope': 'small projection/physical completion checks; no solver or research run',
           'projection': {}, 'partial': {}, 'physical': {}}
_MODELS = {}
_PHYSICAL = None
_REFERENCE = None


def fixture(name, selected, starts, *, auto=True):
    instance, by_stage = select_fixture(base_input(), 'auto_milp_'+name, selected, starts)
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': by_stage}
    return with_auto_low_idle(instance) if auto else instance


def build(instance, *, physics=False, relax=True, **extra):
    flags = dict(FLAGS, relax_auxiliary_integrality=relax)
    config = load_config()
    if instance['execution_rules'].get('idle_policy'):
        config = with_auto_low_idle(config)
    return milp.build_model(instance, config, include_physics=physics,
                            budget=Budget(seconds=150), **flags, **extra)


def structure_vector(model, candidate):
    """Fill controls by active work, separately from production lifts."""
    x = canonical_structure_vector(model, candidate)
    selected = {(sid, row['stage_id'], row['unit'], row['opp'], F(row['start_ms']))
                for sid, rows in candidate['scenes'].items() for row in rows}
    chosen = [o for o in model.options if (o['scenario_id'], o['stage_instance_id'],
              o['unit_id'], o['opp_id'], F(o['start_ms'])) in selected]
    for sid, meta in model.scenes.items():
        for l, when in enumerate(meta['events'][:-1]):
            state = []
            for domain, data in model.instance['platform']['domains'].items():
                active = [o for o in chosen if o['scenario_id']==sid and
                          o['domain_id']==domain and F(o['start_ms'])/1000 <= when < F(o['end_ms'])/1000]
                # A conflict is rejected by independent lock/mutex rows.
                opp = active[0]['opp_id'] if active else 'L'
                state.append(opp)
                for key in data['opps']:
                    x[meta['rho'][l, domain, key]] = int(key==opp)
            for possible in meta['states'][l]:
                x[meta['joint'][l, possible]] = int(possible==tuple(state))
    return x


def row_accepts(model, vector):
    return all(v <= 0 for v in exact_row_residuals(model, vector)) and all(
        F.from_float(float(lo)) <= F.from_float(float(x)) <= F.from_float(float(hi))
        for lo,x,hi in zip(model.lb,vector,model.ub))


def reference_module():
    global _REFERENCE
    if _REFERENCE is None:
        source = subprocess.check_output(['git','show',REFERENCE+':research/chapter3_experiments/milp.py'],cwd=REPO)
        namespace = {'__name__':'_k112_legacy_milp','__file__':str(HERE/'milp.py')}
        exec(compile(source,REFERENCE+':milp.py','exec'),namespace)
        _REFERENCE = namespace
    return _REFERENCE


def signature(model):
    return {key:getattr(model,key) for key in ('names','lb','ub','integer','logical_binary',
        'c','options','option_vars','shared','rows','scenes','deadline_fixed_options',
        'energy_bound_certificates','bounds')}


def physical_fixture():
    global _PHYSICAL
    if _PHYSICAL is None:
        instance,candidate = fixture_candidate('milp_physical',[('A.pre','CPU1','M','0')])
        model = build(instance,physics=True)
        receipt = milp.evaluate_model_candidate(model,candidate,None,model.budget)
        lift = milp.lift_candidate(model,candidate)
        completed = initial_point.complete_initial_point(model,candidate,receipt,model.budget)
        _PHYSICAL = (instance,candidate,model,receipt,lift,completed)
        RECORDS['physical'] = {'input':instance,'candidate':candidate,'receipt':receipt,
            'model_statistics':model.summary(), 'completion':{
                key:value for key,value in completed.items() if key!='x0'},
            'lift':list(map(float,lift)), 'x0':list(map(float,completed['x0'])) if completed['x0'] is not None else None,
            'events':list(map(str,next(iter(model.scenes.values()))['events']))}
    return _PHYSICAL


class AutoMilpProjection(unittest.TestCase):
    def test_independent_cartesian_projection(self):
        ab = base_input()['scenarios'][0]['id']
        definitions = [
            ('wait',{ab:['A.pre']},{'A.pre':[0,15]}),
            ('parallel',{ab:['A.pre','B.pre']},{'A.pre':[0,15],'B.pre':[0,15]}),
            ('chain',{ab:['A.pre','A.main']},{'A.pre':[0],'A.main':[10,15]}),
            ('npu',{ab:['A.main','B.main']},{'A.main':[0],'B.main':[35]})]
        for name,selected,starts in definitions:
            instance=fixture(name,selected,starts)
            candidates=list(independent_assignments(instance,instance['start_domain']['by_scene_stage_ms']))
            expected={candidate_key(c) for c in candidates if independent_check(instance,c)['valid']}
            for relax in (False,True):
                with self.subTest(fixture=name,auxiliary_continuous=relax):
                    model=build(instance,relax=relax)
                    actual={candidate_key(c) for c in candidates if row_accepts(model,structure_vector(model,c))}
                    self.assertEqual(actual,expected)
                    self.assertTrue(expected)
                    self.assertFalse(any(r['tag'].startswith('idle_hold_') for r in model.rows))
                    self.assertTrue(any(r['tag']=='auto_opp_active_support' for r in model.rows))
                    RECORDS['projection'][name+str(relax)]={'cartesian':len(candidates),'legal':len(expected),
                        'variables':len(model.names),'rows':len(model.rows)}
                    if name=='wait' and relax: _MODELS['wait']=model

    def test_unused_domains_drop_at_entry_and_fractional_end(self):
        instance,candidate=fixture_candidate('entry_and_fraction',[('A.pre','CPU1','M','0')])
        instance['scenarios'][0]['entry']['domain_opp']={'CPU':'H','GPU':'H','NPU':'H'}
        model=build(instance)
        vector=structure_vector(model,candidate)
        self.assertTrue(row_accepts(model,vector))
        sid=instance['scenarios'][0]['id']; meta=model.scenes[sid]
        self.assertIn(F(34,3000),meta['events'])
        for l,left in enumerate(meta['events'][:-1]):
            for domain in ('GPU','NPU'):
                self.assertEqual(vector[meta['rho'][l,domain,'L']],1)
            if left>=F(34,3000): self.assertEqual(vector[meta['rho'][l,'CPU','L']],1)
            self.assertTrue(all(s[1:]==('L','L') for s in meta['states'][l]))
        self.assertEqual(meta['states'][-1],[('L','L','L')])

    def test_no_high_state_without_selected_work(self):
        ab=base_input()['scenarios'][0]['id']
        instance=fixture('wrong_idle',{ab:['A.pre']},{'A.pre':[0,15]})
        model=build(instance)
        stage=instance['scenarios'][0]['stage_instances'][0]['id']
        candidate={'scenes':{ab:[{'stage_id':stage,'unit':'CPU1','opp':'M','start_ms':'15'}]}}
        vector=structure_vector(model,candidate)
        self.assertTrue(row_accepts(model,vector))
        meta=model.scenes[ab]
        for opp in ('L','M','H'): vector[meta['rho'][0,'CPU',opp]]=int(opp=='H')
        for state in meta['states'][0]: vector[meta['joint'][0,state]]=int(state==('H','L','L'))
        residual=exact_row_residuals(model,vector)
        self.assertTrue(any(v>0 and row['tag']=='auto_opp_active_support'
                            for v,row in zip(residual,model.rows)))

    def test_production_lift_matches_independent_controls_at_busy_and_switch_events(self):
        examples=[('busy',[('A.pre','CPU1','H','0'),('B.pre','CPU2','H','0')]),
            ('direct',[('A.pre','CPU1','H','0'),('B.pre','CPU1','M','10')]),
            ('gap',[('A.pre','CPU1','H','0'),('B.pre','CPU1','M','15')]),
            ('queue',[('A.main','NPU0','H','0'),('B.main','NPU0','H','35')])]
        for name,assignments in examples:
            with self.subTest(case=name):
                instance,candidate=fixture_candidate('lift_'+name,assignments)
                model=build(instance)
                lifted=milp.lift_candidate(model,candidate)
                self.assertEqual(list(lifted),structure_vector(model,candidate))
                self.assertTrue(row_accepts(model,lifted))

    def test_default_and_complete_fixed_legacy_rows_unchanged(self):
        instance,candidate=fixture_candidate('legacy_rows',[('A.pre','CPU1','M','0')],auto=False)
        config=load_config()
        for extra in ({},{'fixed_deployment':{'A.pre':'CPU1'},'prefilter_deadlines':True}):
            with self.subTest(extra=extra):
                current=build(instance,**extra)
                previous=reference_module()['build_model'](instance,config,include_physics=False,
                    budget=Budget(seconds=100),**FLAGS,**extra)
                self.assertEqual(signature(current),signature(previous))
        RECORDS['legacy_reference_commit']=REFERENCE


class PartialMilpProjection(unittest.TestCase):
    def test_real_partial_scene_receipts_merge_complete_safe_energy(self):
        from scene_adapter import evaluate_partial_scene, aggregate_partial_scene_receipts
        from thermal import I
        ab,ac=[s['id'] for s in base_input()['scenarios']]
        instance=fixture('real_partial',{ab:['A.pre'],ac:['A.pre']},{'A.pre':[0]})
        candidates={}
        for scene,opp in zip(instance['scenarios'],('M','H')):
            sid=scene['id']; stage=scene['stage_instances'][0]['id']
            candidates[sid]={'scenes':{sid:[{'stage_id':stage,'unit':'CPU1','opp':opp,'start_ms':'0'}]}}
        budget=Budget(seconds=100); condition={'A.pre':'CPU1'}
        receipts={sid:evaluate_partial_scene(instance,sid,condition,c,None,budget)
                  for sid,c in candidates.items()}
        for r in receipts.values(): self.assertEqual(r['state'],'SAFE',r)
        merged=aggregate_partial_scene_receipts(instance,condition,receipts,candidates,None,budget)
        self.assertEqual(merged['state'],'SAFE',merged)
        expected=sum((I(*receipts[s['id']]['energy_J'])*I.rational(F(s['weight']))
                      for s in instance['scenarios']),I(0))
        self.assertEqual(merged['weighted_energy_J'],expected.data())
        self.assertEqual(merged['safe_upper_bound_J'],str(expected.hi))
        self.assertEqual(validate_schedule(instance,merged['safe_candidate'])['state'],
                         'SCHEDULE_VALID_THERMAL_UNCHECKED')
        RECORDS['partial_real']={'input':instance,'fixed_shared_deployment':condition,
                                'candidates':candidates,'receipts':receipts,'merged':merged}

    def test_global_partial_equals_product_of_scene_projections(self):
        ab,ac=[s['id'] for s in base_input()['scenarios']]
        instance=fixture('shared_and_local',{ab:['A.pre','B.main'],ac:['A.pre','C.main']},
                         {'A.pre':[0],'B.main':[20],'C.main':[20]})
        # Named Cartesian fixture reduces modes, never a research input.
        for shared,modes in instance['stage_modes'].items():
            instance['stage_modes'][shared]=[m for m in modes if m['opp_id']==('M' if shared=='A.pre' else 'L')]
        candidates=list(independent_assignments(instance,instance['start_domain']['by_scene_stage_ms']))
        expected={candidate_key(c) for c in candidates if independent_check(instance,c)['valid']}
        union=set()
        for unit in ('CPU1','CPU2'):
            condition={'A.pre':unit}
            model=build(instance,fixed_shared_deployment=condition)
            legal=[c for c in candidates if row_accepts(model,structure_vector(model,c))]
            # Slow L CPU alternatives can violate the unchanged request
            # deadline. Count feasible choices from the independent oracle,
            # never from the unfiltered product of supported devices.
            independently_legal=[]
            for candidate in candidates:
                oracle=independent_check(instance,candidate)
                if oracle['valid'] and oracle['shared_deployment']['A.pre']==unit:
                    independently_legal.append(candidate)
            self.assertEqual(set(map(candidate_key,legal)),set(map(candidate_key,independently_legal)))
            self.assertTrue(legal)
            union.update(map(candidate_key,legal))
            self.assertEqual(model.preprocessing['fixed_shared_deployment'],condition)
            self.assertEqual(model.preprocessing['deployment_scope'],'shared_only')
            local_sets=[]
            for sid,local in ((ab,'B.main'),(ac,'C.main')):
                projected=build(instance,fixed_shared_deployment=condition,fixed_scene_id=sid)
                modes=projected.instance['stage_modes'][local]
                self.assertEqual(modes,instance['stage_modes'][local])
                self.assertEqual(projected.instance['scenarios'][0]['weight'],'1')
                seen={}
                for c in legal:
                    single={'scenes':{sid:c['scenes'][sid]}}
                    if row_accepts(projected,structure_vector(projected,single)):
                        seen[candidate_key(single)]=single
                expected_local={candidate_key({'scenes':{sid:c['scenes'][sid]}}) for c in independently_legal}
                self.assertEqual(set(seen),expected_local)
                local_sets.append(list(seen.values()))
            combined={candidate_key({'scenes':dict(a['scenes'],**b['scenes'])})
                      for a,b in product(*local_sets)}
            self.assertEqual(combined,set(map(candidate_key,legal)))
            RECORDS['partial'][unit]={'local_counts':list(map(len,local_sets)),'global_legal':len(legal),
                'all_candidates':len(candidates),'fixed_shared_deployment':condition}
        self.assertEqual(union,expected)
        RECORDS['partial']['union']={'independent_legal':len(expected),'all_candidates':len(candidates)}

    def test_all_local_modes_and_devices_are_retained(self):
        ab,ac=[s['id'] for s in base_input()['scenarios']]
        instance=fixture('full_catalog',{ab:['A.pre','B.main'],ac:['A.pre','C.main']},
                         {'A.pre':[0],'B.main':[20],'C.main':[20]})
        model=build(instance,fixed_shared_deployment={'A.pre':'CPU1'})
        for local in ('B.main','C.main'):
            self.assertEqual(model.instance['stage_modes'][local],instance['stage_modes'][local])
            self.assertEqual({(o['unit_id'],o['opp_id']) for o in model.options if o['shared_stage_id']==local},
                             {(m['unit_id'],m['opp_id']) for m in instance['stage_modes'][local]})
        self.assertEqual({m['unit_id'] for m in model.instance['stage_modes']['A.pre']},{'CPU1'})

    def test_empty_shared_condition_and_parameter_conflict(self):
        instance,_=fixture_candidate('empty_shared',[('A.pre','CPU1','M','0')])
        sid=instance['scenarios'][0]['id']
        model=build(instance,fixed_shared_deployment={},fixed_scene_id=sid)
        self.assertEqual(model.instance['stage_modes'],instance['stage_modes'])
        with self.assertRaises(ValueError): build(instance,fixed_deployment={},fixed_shared_deployment={})
        with self.assertRaises(ValueError): build(instance,fixed_shared_deployment={'A.pre':'CPU1'})
        with self.assertRaises(ValueError): build(instance,fixed_scene_id=sid)


class AutoMilpPhysical(unittest.TestCase):
    def test_real_safe_receipt_and_both_lifts_numerically_admitted(self):
        instance,candidate,model,receipt,lift,completed=physical_fixture()
        self.assertEqual(receipt['state'],'SAFE')
        self.assertIsNotNone(completed['x0'],completed)
        _prepare(model.as_solver_dict(),x0=lift)
        _prepare(model.as_solver_dict(),x0=completed['x0'])
        self.assertEqual(candidate_key(milp.decode(model,lift)),candidate_key(candidate))
        self.assertEqual(candidate_key(milp.decode(model,completed['x0'])),candidate_key(candidate))
        np.testing.assert_allclose(lift,completed['x0'],rtol=0,atol=2e-12)

    def test_physical_control_and_complete_window_energy(self):
        instance,candidate,model,receipt,lift,completed=physical_fixture()
        sid=instance['scenarios'][0]['id']; meta=model.scenes[sid]
        check=validate_schedule(instance,candidate)
        for l,left in enumerate(meta['events'][:-1]):
            segment=next(s for s in check['scenes'][sid]['segments']
                         if F(s['start_ms'])/1000<=left<F(s['end_ms'])/1000)
            for domain in instance['platform']['domains']:
                for opp in instance['platform']['domains'][domain]['opps']:
                    self.assertEqual(lift[meta['rho'][l,domain,opp]],int(segment['domain_opps'][domain]==opp))
        self.assertEqual(meta['events'][-1],F(2,5))
        energy=sum(lift[j] for j in meta['energy'])
        lo,hi=map(float,receipt['weighted_energy_J'])
        self.assertLessEqual(lo-2e-12,energy)
        self.assertLessEqual(energy,hi+2e-12)
        self.assertTrue(model.energy_bound_certificates)
        self.assertEqual(receipt['safe_upper_bound_J'],receipt['weighted_energy_J'][1])

    def test_exported_energy_lower_bound_certificates_remain_valid(self):
        from run_energy_bound_precheck import expected_certificate, box_certificate_check
        instance,candidate,model,receipt,lift,completed=physical_fixture()
        maxima=[]
        for certificate in model.energy_bound_certificates:
            expected_certificate(model,certificate)
            maxima.extend(map(str,box_certificate_check(model,certificate)))
        self.assertTrue(maxima)
        RECORDS['physical']['energy_bound_box_residual_maxima']=maxima


if __name__=='__main__':
    unittest.main()
