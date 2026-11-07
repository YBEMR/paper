"""Actual unchanged lifecycle with mock search/evaluator/validator/lower bounds.
No actual HEFT, schedule validation or thermal evaluation is run.
"""
import json,sys,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import Mock,patch
from h02_pair_preflight.common import ContractError,sha,encoded,candidate_identity
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet
from h02_pair_preflight.paired_heuristic_entry import StageARegistry,MockBackend,paired_heuristic_entry,validate_packet
from h02_pair_preflight.truth_H_post_audit import MockAuditBackend,MockBudgetExpired,truth_H_post_audit
from .fixtures import candidate_for,mock_safe_receipt,mock_legal_receipt

class Clock:
    def __init__(self): self.value=0.0
    def __call__(self): return self.value
class AuditBudget:
    def __init__(self,seconds): self.seconds=seconds; self.elapsed=0.0
    def check(self):
        if self.elapsed>=self.seconds: raise MockBudgetExpired()

class Lifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pair=paired_response_input_view('base__R1')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='h02_mock_'); self.addCleanup(self.temp.cleanup)
        self.registry=StageARegistry(Path(self.temp.name)); self.registry.bind_pair(self.pair)
        self.packet=planner_packet(self.pair,'R'); self.clock=Clock(); self.loaded=[]
    def run_mock(self,energies=('1',),formed=None,return_at=None,technical=False,view='R',slot='r0',mutate_result=None,invalid=False,repeat=False,conflict=False):
        self.clock.value=0.0  # each independent method has its own fake origin
        import heuristic_runner as hr
        import partial_bounds
        packet=planner_packet(self.pair,view); n=0
        def evaluator(i,c,a,b):
            nonlocal n
            e=energies[n]; t=formed[n] if formed is not None else float(n+1)
            n+=1; self.clock.value=return_at[n-1] if return_at is not None else t
            return mock_safe_receipt(i,c,a,e,t)
        eval_mock=Mock(side_effect=evaluator)
        def search(i,c,b,assess):
            self.loaded.append((i,c))
            for j in range(len(energies)):
                candidate=candidate_for(i,offset=0 if repeat else 5*j)
                if conflict:
                    for rows in candidate['scenes'].values(): rows[0]['start_ms']=rows[1]['start_ms']='0'
                if invalid:
                    for rows in candidate['scenes'].values():
                        rows[0].update(unit='CPU1',opp='L',start_ms='0')
                        rows[1].update(unit='CPU2',opp='H',start_ms='0')
                assess(candidate,'MOCK_LITERAL_'+str(j))
            if technical: raise MemoryError('MOCK_ONLY')
            return {'local_base_candidate':candidate_for(i,offset=25),'mock_only':True}
        search_mock=Mock(side_effect=search)
        def runner(*args,**kwargs):
            with ExitStack() as stack:
                validate=stack.enter_context(patch.object(hr,'validate_schedule',Mock(side_effect=lambda i,c: {'state':'INVALID_SCHEDULE','reason':'MOCK_CPU_DOMAIN_OPP_CONFLICT'} if invalid else mock_legal_receipt(i))))
                stack.enter_context(patch.object(partial_bounds,'independent_lower_bound',Mock(return_value={'lower_bound_J':'0','mock_only':True})))
                # Default imported evaluator and lower-bound aliases MUST NOT run.
                stack.enter_context(patch.object(hr,'independent_lower_bound',Mock(side_effect=AssertionError('REAL_BOUND_FORBIDDEN'))))
                result=hr.execute_heuristic(*args,**kwargs)
                if mutate_result: mutate_result(result)
                return result
        backend=MockBackend(Mock(side_effect=runner),eval_mock,search_mock,self.clock)
        result=paired_heuristic_entry(packet,backend,self.registry,slot,sha(self.pair['truth_H']['instance']))
        return result,backend
    def token(self,view='R',conflict=False):
        out,_=self.run_mock(view=view,conflict=conflict); self.assertEqual(out['plan_status'],'PLAN_SAFE'); return out['frozen_candidate']
    def audit(self,token,kind='SAFE',formed=1.0,elapsed=1.0,mutate=None,legal_state='SCHEDULE_VALID_THERMAL_UNCHECKED',truth=None):
        b=AuditBudget(60)
        def evaluator(i,c,a,budget):
            budget.elapsed=elapsed
            if kind=='SAFE': r=mock_safe_receipt(i,c,a,formed=formed)
            elif kind=='THERMAL_VIOLATION':
                r={'state':kind,'problem_id':i['id'],'evidence_identity':{'input_sha256':sha(i),'candidate_sha256':sha(c)},'violations':[{'scene_id':i['scenarios'][0]['id'],'node':'NPU0','temperature_degC':['81','81'],'limit_degC':'80','time_s':'1/10','formed_at_elapsed_s':formed}]}
            else: r={'state':kind,'reason':'MOCK_INTERVAL_UNRESOLVED' if kind=='UNRESOLVED' else 'RESOURCE_LIMIT'}
            if mutate: mutate(r,i,c)
            return r
        def legal(i,c):
            if legal_state=='SCHEDULE_VALID_THERMAL_UNCHECKED': return mock_legal_receipt(i)
            stages=next(iter(c['scenes'].values()))
            return {'state':legal_state,'reason':'EXECUTION_UNIT_OVERLAP','details':{'stages':[stages[0]['stage_id'],stages[1]['stage_id']]},'thermal_status':'NOT_EVALUATED','energy_status':'NOT_EVALUATED'}
        backend=MockAuditBackend(Mock(side_effect=legal),Mock(side_effect=evaluator),Mock(return_value=b))
        binding=None if token is None else {k:token[k] for k in ('source_commit_sha','problem_id','truth_H_sha256','policy_id','accuracy_sha256')}
        return truth_H_post_audit(token,truth or deepcopy(self.pair['truth_H']),binding,backend,self.registry),backend
    def test_best_not_last_accepted_SAFE(self):
        out,b=self.run_mock(energies=('1','2'))
        self.assertEqual(out['plan_status'],'PLAN_SAFE'); self.assertEqual(out['raw_method_result']['safe_upper_bound_J'],'1')
        raw=json.loads(out['frozen_candidate']['candidate_json']); self.assertEqual(raw,candidate_for(self.pair['planner_R']['instance']))
    def test_equal_energy_preserves_first(self):
        out,_=self.run_mock(energies=('1','1')); self.assertEqual(json.loads(out['frozen_candidate']['candidate_json']),candidate_for(self.pair['planner_R']['instance']))
    def test_wrong_last_export_rejected(self):
        def change(r):
            row=r['evaluations'][-1]; r.update(safe_candidate=row['candidate'],evaluation=row['evaluation'],safe_upper_bound_J=row['evaluation']['safe_upper_bound_J'])
        out,_=self.run_mock(energies=('1','2'),mutate_result=change); self.assertEqual(out['plan_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertTrue(self.registry.stopped)
    def test_timely_formed_SAFE_preserved_after_return_deadline(self):
        out,_=self.run_mock(formed=(119.9,),return_at=(121,)); self.assertEqual(out['plan_status'],'PLAN_SAFE'); self.assertFalse(out['technical_failure'])
    def test_cutoff_preserves_prior_best(self):
        out,_=self.run_mock(energies=('1','2'),formed=(1.0,120.0),return_at=(1.0,121.0)); self.assertEqual(out['plan_status'],'PLAN_SAFE'); self.assertEqual(out['raw_method_result']['safe_upper_bound_J'],'1')
    def test_deadline_equal_no_SAFE(self):
        out,_=self.run_mock(formed=(120.0,)); self.assertEqual(out['plan_status'],'PLAN_UNRESOLVED'); self.assertIsNone(out['frozen_candidate'])
    def test_invalid_mock_candidate_no_SAFE(self):
        out,b=self.run_mock(invalid=True); self.assertEqual(out['plan_status'],'PLAN_NO_SAFE'); self.assertEqual(b.evaluator.call_count,0)
    def test_technical_failure_keeps_prior_evidence_and_latches_stop(self):
        out,_=self.run_mock(technical=True); self.assertEqual(out['plan_status'],'PLAN_SAFE'); self.assertTrue(self.registry.stopped); self.assertTrue(out['stop_required'])
    def test_directory_reuse_rejected(self):
        self.run_mock()
        with self.assertRaises(ContractError): self.run_mock()
    def test_H_R_loader_and_cache_are_independent(self):
        a,b=self.run_mock(view='R',slot='R'); r=self.loaded[-1]
        c,d=self.run_mock(view='H',slot='H'); h=self.loaded[-1]
        self.assertIsNot(r[0],h[0]); self.assertEqual(b.evaluator.call_count,d.evaluator.call_count,1)
        self.assertNotEqual(a['raw_method_result']['input_sha256'],c['raw_method_result']['input_sha256'])
        self.assertTrue(all(str(m['alpha'])=='1' for rows in r[0]['stage_modes'].values() for m in rows))
        self.assertNotEqual(Path(self.registry.allocated['R']['path']),Path(self.registry.allocated['H']['path']))
    def test_identical_candidate_cache_local_only(self):
        out,b=self.run_mock(energies=('1','2'),repeat=True)
        self.assertEqual(out['raw_method_result']['cache_hits'],1); self.assertEqual(b.evaluator.call_count,1)
    def test_nested_planner_scene_technical_error_latches_stop(self):
        def inject(r): r['search']['last_receipt']={'state':'UNRESOLVED','reason':'NOT_ALL_SCENES_COMPLETE_AND_SAFE','scenes':{'AB':{'state':'UNRESOLVED','reason':'RESOURCE_LIMIT'}}}
        out,_=self.run_mock(mutate_result=inject); self.assertEqual(out['plan_status'],'PLAN_SAFE'); self.assertTrue(out['stop_required'])
    def test_nested_audit_scene_technical_error_stops(self):
        out,_=self.audit(self.token(),kind='UNRESOLVED',mutate=lambda r,i,c:r.update(scenes={'AB':{'state':'UNRESOLVED','reason':'RESOURCE_LIMIT'}}))
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertTrue(out['stop_required'])
    def test_H_violation_plus_scene_numerical_error_preserves_witness_and_stops(self):
        out,_=self.audit(self.token(view='H'),kind='THERMAL_VIOLATION',mutate=lambda r,i,c:r.update(scenes={'AB':{'state':'THERMAL_VIOLATION','reason':'NUMERICAL_ERROR'}}))
        self.assertEqual(out['audit_status'],'TRUE_H_THERMAL_VIOLATION'); self.assertTrue(out['stop_required']); self.assertTrue(out['violations'])
    def test_loader_does_not_capture_truth_or_feedback(self):
        out,b=self.run_mock(); loader=b.runner.call_args.args[0]
        self.assertEqual(len(loader.__closure__),1)
        payload=loader.__closure__[0].cell_contents
        self.assertIsInstance(payload,bytes); self.assertNotIn(b'truth_H',payload); self.assertNotIn(b'H_alpha',payload)
    def test_unbound_packet_denied(self):
        self.registry.bindings.clear()
        with self.assertRaises(ContractError): self.run_mock()
    def test_resigned_changed_packet_denied_by_binding(self):
        p=deepcopy(self.packet); p['planner']['instance']['start_grid_ms']='10'; p['plan_sha256']=sha(p['planner']['instance'])
        from h02_pair_preflight.paired_response_input_view import physical_projection
        p['physical_projection_sha256']=sha(physical_projection(p['planner']['config'],p['planner']['instance']))
        validate_packet(p)
        with self.assertRaisesRegex(ContractError,'UNBOUND'): self.registry.reserve('forged',p,sha(self.pair['truth_H']['instance']))
    def test_true_H_feedback_in_packet_denied(self):
        for field in ('truth_H','audit_receipt'):
            p=deepcopy(self.packet); p[field]={'score':1}
            with self.assertRaises(ContractError): validate_packet(p)
    def test_real_callable_backend_refused(self):
        with self.assertRaises(ContractError): MockBackend(lambda:None,Mock(),Mock(),self.clock).check()
    def test_audit_good_mock_SAFE_once(self):
        token=self.token(); out,b=self.audit(token)
        self.assertEqual(out['audit_status'],'TRUE_H_SAFE'); self.assertFalse(out['real_safe']); self.assertFalse(out['usable_as_research_evidence'])
        self.assertEqual(b.evaluator.call_count,1); again,c=self.audit(token)
        self.assertEqual(again['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertEqual(c.evaluator.call_count,0)
    def test_no_candidate_zero_audit(self):
        out,b=self.audit(None); self.assertEqual(out['reason'],'NO_PLAN_CANDIDATE'); self.assertEqual(b.evaluator.call_count,0)
    def test_audit_exact_cutoff_rejects_SAFE(self):
        out,_=self.audit(self.token(),formed=60.0,elapsed=60.0); self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED')
    def test_audit_timely_receipt_returned_late_preserved(self):
        out,_=self.audit(self.token(),formed=59.9,elapsed=61.0); self.assertEqual(out['audit_status'],'TRUE_H_SAFE')
    def test_R_mock_invalid_triggers_anomaly_and_stop(self):
        out,_=self.audit(self.token(conflict=True),legal_state='INVALID_SCHEDULE'); self.assertEqual(out['anomaly'],'MONOTONICITY_CONTRACT_ANOMALY'); self.assertTrue(self.registry.stopped)
    def test_R_mock_thermal_violation_triggers_anomaly(self):
        out,_=self.audit(self.token(),kind='THERMAL_VIOLATION'); self.assertEqual(out['anomaly'],'MONOTONICITY_CONTRACT_ANOMALY')
    def test_H_mock_invalid_is_not_monotonicity_counterexample(self):
        out,_=self.audit(self.token(view='H',conflict=True),legal_state='INVALID_SCHEDULE'); self.assertEqual(out['audit_status'],'TRUE_H_INVALID'); self.assertNotIn('anomaly',out)
    def test_audit_unresolved_does_not_claim_violation(self):
        out,_=self.audit(self.token(),kind='UNRESOLVED'); self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED'); self.assertFalse(out['stop_required'])
    def test_audit_technical_error_stops(self):
        out,_=self.audit(self.token(),kind='ERROR'); self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertTrue(out['stop_required'])
    def test_audit_missing_scene_rejected_and_consumed(self):
        out,_=self.audit(self.token(),mutate=lambda r,i,c:r['scenes'].pop(next(iter(r['scenes'])))); self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertTrue(out['audit_consumed'])
    def test_wrong_truth_input_rejected_before_call(self):
        t=deepcopy(self.pair['truth_H']); t['instance']['window_ms']='500'; out,b=self.audit(self.token(),truth=t)
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertEqual(b.evaluator.call_count,0)
    def test_wrong_truth_config_rejected_before_call(self):
        t=deepcopy(self.pair['truth_H']); t['config']['platform']['external_common_power_W']='999'; out,b=self.audit(self.token(),truth=t)
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertEqual(b.evaluator.call_count,0)
    def test_mutated_candidate_token_rejected(self):
        t=self.token(); t['candidate_json']=t['candidate_json'].replace('CPU1','CPU2'); out,b=self.audit(t)
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR'); self.assertEqual(b.evaluator.call_count,0)
    def test_mutating_audit_evaluator_rejected(self):
        out,_=self.audit(self.token(),mutate=lambda r,i,c:c['scenes'].clear()); self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
    def test_audit_budget_exception_unresolved_once(self):
        t=self.token(); b=MockAuditBackend(Mock(side_effect=MockBudgetExpired()),Mock(),Mock(return_value=AuditBudget(60)))
        binding={k:t[k] for k in ('source_commit_sha','problem_id','truth_H_sha256','policy_id','accuracy_sha256')}
        out=truth_H_post_audit(t,self.pair['truth_H'],binding,b,self.registry)
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED'); self.assertTrue(out['audit_consumed']); self.assertFalse(out['stop_required'])
    def test_expiry_before_hashing_still_consumes_once(self):
        t=self.token(); budget=AuditBudget(60); budget.elapsed=60
        backend=MockAuditBackend(Mock(),Mock(),Mock(return_value=budget))
        binding={k:t[k] for k in ('source_commit_sha','problem_id','truth_H_sha256','policy_id','accuracy_sha256')}
        out=truth_H_post_audit(t,self.pair['truth_H'],binding,backend,self.registry)
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED'); self.assertTrue(out['audit_consumed'])
        self.assertEqual(backend.validator.call_count,0); self.assertEqual(backend.evaluator.call_count,0)
        again=truth_H_post_audit(t,self.pair['truth_H'],binding,backend,self.registry)
        self.assertEqual(again['audit_status'],'INPUT_OR_INTERFACE_ERROR')
    def test_audit_cannot_feed_back_into_planner(self):
        out,_=self.audit(self.token()); packet=deepcopy(self.packet); packet['audit_receipt']=out
        with self.assertRaises(ContractError): validate_packet(packet)

class CandidateSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.i=paired_response_input_view('base__R1')['truth_H']['instance']
    def reject(self,mutate):
        c=candidate_for(self.i); mutate(c)
        with self.assertRaises((ContractError,KeyError)): candidate_identity(self.i,c)
    def test_extra_predicted_end(self): self.reject(lambda c:next(iter(c['scenes'].values()))[0].__setitem__('end_ms','1'))
    def test_missing_scene(self): self.reject(lambda c:c['scenes'].pop(next(iter(c['scenes']))))
    def test_duplicate_stage(self): self.reject(lambda c:next(iter(c['scenes'].values())).__setitem__(1,deepcopy(next(iter(c['scenes'].values()))[0])))
    def test_unknown_OPP(self): self.reject(lambda c:next(iter(c['scenes'].values()))[0].__setitem__('opp','BAD'))
    def test_float_start(self): self.reject(lambda c:next(iter(c['scenes'].values()))[0].__setitem__('start_ms',5.0))
    def test_bool_start(self): self.reject(lambda c:next(iter(c['scenes'].values()))[0].__setitem__('start_ms',False))
    def test_nongrid_start(self): self.reject(lambda c:next(iter(c['scenes'].values()))[0].__setitem__('start_ms','1/4'))
    def test_A_cross_scene_different_unit(self): self.reject(lambda c:list(c['scenes'].values())[1][0].__setitem__('unit','CPU2'))
