"""B0 dormant backend wiring tested solely with synthetic receipts and mocks.

Only input expansion is real and pure. No scheduling validator, HEFT search,
physical Budget, lower bound, continuous thermal calculation or solver runs.
"""
import builtins
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from h02_pair_b0.backends import (CoreBindings, audit_chain, planner_chain,
    observing_recorder_class, resolve_real_bindings)
from h02_pair_b0.budget import RootClock
from h02_pair_b0.tests.test_budget import FakeClock, FakeBase, FakeBaseExpired
from h02_pair_preflight.common import BASE_SHA, POLICY, encoded, sha, byte_sha, candidate_identity, ContractError
from h02_pair_preflight.paired_response_input_view import paired_response_input_view, planner_packet
from h02_pair_preflight.tests.fixtures import candidate_for, mock_safe_receipt, mock_legal_receipt


class BackendWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pure parameter expansion/project only; cannot produce a research SAFE.
        cls.pair=paired_response_input_view('base__R1',BASE_SHA)

    def setUp(self):
        self.truth=deepcopy(self.pair['truth_H'])
        self.config=self.truth['config']; self.instance=self.truth['instance']
        self.candidate=candidate_for(self.instance)
        self.clock=FakeClock(1000.0); self.root=RootClock(60,clock=self.clock)
        self.token=self.token_for(self.candidate)
        self.validator=Mock(return_value=mock_legal_receipt(self.instance))
        self.evaluator=Mock(side_effect=lambda i,c,a,b:mock_safe_receipt(i,c,a,formed=b.elapsed+1))
        self.bindings=CoreBindings(None,Mock(name='never-searched'),self.evaluator,
            self.validator,FakeBase,FakeBaseExpired,kind='MOCK_ONLY')
        self.snapshots=[]

    def token_for(self,candidate,view='R'):
        raw=encoded(candidate)
        return dict(source_commit_sha=BASE_SHA,truth_H_sha256=sha(self.instance),
            truth_H_config_sha256=sha(self.config),problem_id=self.instance['id'],
            policy_id=POLICY,accuracy_sha256=sha(self.config['accuracy_targets']),
            p1_p2_static_passed=True,planning_top_state='SAFE',
            candidate_json=raw.decode(),candidate_raw_sha256=byte_sha(raw),
            candidate_semantic_sha256=candidate_identity(self.instance,candidate)['candidate_semantic_sha256'],
            plan_formed_at_elapsed_s=1.0,view=view)

    def run_audit(self):
        return audit_chain(self.bindings,self.truth,self.token,self.root,self.snapshots.append)

    def test_mock_safe_never_claims_research_safe(self):
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_SAFE')
        self.assertFalse(out['real_safe'])
        self.assertFalse(out['usable_as_research_evidence'])
        self.assertEqual(out['evidence_kind'],'MOCK_ONLY')
        self.assertTrue(out['audit_consumed'])
        self.assertEqual(len(self.snapshots),1)
        self.bindings.search.assert_not_called()

    def test_post_root_counts_pre_worker_input_handoff_cost(self):
        self.clock.now+=7
        out=self.run_audit()
        budget=self.evaluator.call_args.args[-1]
        self.assertEqual(budget.start,1000)
        self.assertEqual(budget.deadline,1060)
        self.assertEqual(budget.elapsed,7)
        self.assertEqual(out['root']['method_elapsed_s'],7)

    def test_late_return_preserves_mock_receipt_formed_before_60(self):
        def late(i,c,a,b):
            self.clock.now=1061
            return mock_safe_receipt(i,c,a,formed=59.9)
        self.evaluator.side_effect=late
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_SAFE')
        self.assertFalse(out['real_safe'])
        self.assertEqual(out['root']['method_elapsed_s'],61)

    def test_receipt_formed_exactly_at_60_is_unresolved(self):
        self.evaluator.side_effect=lambda i,c,a,b:mock_safe_receipt(i,c,a,formed=60)
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED')
        self.assertEqual(out['reason'],'LATE_OR_INVALID_SAFE_TIMESTAMP')
        self.assertFalse(out['real_safe'])

    def test_expired_root_does_not_call_validator_or_evaluator(self):
        self.clock.now=1060
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED')
        self.assertEqual(out['reason'],'AUDIT_ROOT_EXHAUSTED')
        self.validator.assert_not_called(); self.evaluator.assert_not_called()

    def test_post_root_must_be_declared_60(self):
        self.root=RootClock(120,clock=self.clock)
        with self.assertRaisesRegex(ContractError,'AUDIT_ROOT_NOT_60'):self.run_audit()
        self.validator.assert_not_called()

    def test_wrong_truth_identity_stops_before_core_callbacks(self):
        self.token['truth_H_sha256']='0'*64
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertTrue(out['stop_required'])
        self.validator.assert_not_called();self.evaluator.assert_not_called()

    def test_validator_input_mutation_stops(self):
        def mutate(i,c):
            c['scenes'][next(iter(c['scenes']))][0]['start_ms']='5'
            return mock_legal_receipt(i)
        self.validator.side_effect=mutate
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertIn('VALIDATOR_MUTATED_INPUT',out['reason'])
        self.assertTrue(out['stop_required']);self.evaluator.assert_not_called()

    def test_evaluator_input_mutation_stops(self):
        def mutate(i,c,a,b):
            a['energy_absolute_error_J']='1'
            return mock_safe_receipt(i,c,a)
        self.evaluator.side_effect=mutate
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertIn('EVALUATOR_MUTATED_INPUT',out['reason'])
        self.assertTrue(out['stop_required'])

    def test_technical_unresolved_keeps_stop_distinct(self):
        self.evaluator.side_effect=None
        self.evaluator.return_value={'state':'UNRESOLVED','reason':'NUMERICAL_ERROR'}
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertTrue(out['technical_failure']);self.assertTrue(out['stop_required'])

    def true_overlap_receipt(self):
        scene_id=next(iter(self.candidate['scenes']))
        rows=self.candidate['scenes'][scene_id]
        rows[0]['start_ms']=rows[1]['start_ms']='0'
        self.token=self.token_for(self.candidate)
        return dict(state='INVALID_SCHEDULE',reason='EXECUTION_UNIT_OVERLAP',
            details={'stages':[rows[0]['stage_id'],rows[1]['stage_id']]},
            thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')

    def test_r_bound_exact_overlap_is_monotonicity_anomaly(self):
        self.validator.return_value=self.true_overlap_receipt()
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_INVALID')
        self.assertTrue(out['certificate_checked'])
        self.assertEqual(out['anomaly'],'MONOTONICITY_CONTRACT_ANOMALY')
        self.assertTrue(out['stop_required']);self.evaluator.assert_not_called()

    def test_same_true_overlap_from_h_is_invalid_without_r_anomaly(self):
        self.validator.return_value=self.true_overlap_receipt();self.token['view']='H'
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_INVALID')
        self.assertNotIn('anomaly',out)
        self.assertFalse(out['stop_required'])

    def test_malformed_invalid_is_interface_error_not_r_counterexample(self):
        self.validator.return_value=dict(state='INVALID_SCHEDULE',
            reason='MALFORMED_INPUT_OR_CANDIDATE',details={'error_type':'KeyError'},
            thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertNotIn('anomaly',out);self.assertTrue(out['stop_required'])

    def test_unsupported_policy_is_interface_error(self):
        self.validator.return_value=dict(state='INVALID_SCHEDULE',
            reason='UNSUPPORTED_IDLE_POLICY',details={'message':'unsupported'},
            thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertNotIn('anomaly',out);self.assertTrue(out['stop_required'])

    def test_false_constraint_certificate_is_interface_error(self):
        self.validator.return_value=dict(state='INVALID_SCHEDULE',
            reason='BEFORE_RELEASE',details={'stage':self.candidate['scenes'][next(iter(self.candidate['scenes']))][0]['stage_id']},
            thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
        self.assertFalse(out['certificate_checked']);self.assertNotIn('anomaly',out)

    def test_evaluator_invalid_also_uses_strict_classifier(self):
        legal=self.true_overlap_receipt()
        self.validator.return_value=mock_legal_receipt(self.instance)
        self.evaluator.side_effect=None
        self.evaluator.return_value={'state':'INVALID_SCHEDULE','reason':'EXECUTION_UNIT_OVERLAP','legality':legal}
        out=self.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_INVALID')
        self.assertTrue(out['certificate_checked'])
        self.assertEqual(out['anomaly'],'MONOTONICITY_CONTRACT_ANOMALY')

    def test_observer_finally_preserves_best_even_when_base_raises(self):
        best={'candidate':{'mock':'identity'},'energy':'1'}
        class FakeRecorder:
            def __init__(self):
                self.best=deepcopy(best);self.evaluations=[];self.events=[]
                self.violations=[];self.first_safe_s=1
            def assess(self,candidate,source): raise FakeBaseExpired('mock cutoff')
        snapshots=[];observed=observing_recorder_class(FakeRecorder,snapshots.append)()
        before=deepcopy(observed.best)
        with self.assertRaises(FakeBaseExpired): observed.assess({'mock':'candidate'},'mock')
        self.assertEqual(observed.best,before)
        self.assertEqual(snapshots[0]['best'],before)
        snapshots[0]['best']['energy']='100'
        self.assertEqual(observed.best,before)

    def test_observer_does_not_change_normal_result_or_choice(self):
        class FakeRecorder:
            def __init__(self):
                self.best=None;self.evaluations=[];self.events=[]
                self.violations=[];self.first_safe_s=None
            def assess(self,candidate,source):
                self.best={'candidate':deepcopy(candidate),'source':source}
                return {'state':'UNRESOLVED','evidence_kind':'MOCK_ONLY'}
        observed=observing_recorder_class(FakeRecorder,self.snapshots.append)()
        out=observed.assess({'literal':'mock'},'fixture')
        self.assertEqual(out,{'state':'UNRESOLVED','evidence_kind':'MOCK_ONLY'})
        self.assertEqual(observed.best,self.snapshots[0]['best'])

    def test_validator_receipt_preserved_if_outer_budget_expires(self):
        def late_validator(i,c):
            self.clock.now=self.root.origin+60
            return {'state':'INVALID_SCHEDULE','reason':'MALFORMED_INPUT_OR_CANDIDATE','details':{},'thermal_status':'NOT_EVALUATED','energy_status':'NOT_EVALUATED'}
        self.validator.side_effect=late_validator
        out=audit_chain(self.bindings,self.pair['truth_H'],self.token,self.root)
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED')
        self.assertEqual(out['legality']['reason'],'MALFORMED_INPUT_OR_CANDIDATE')
        self.evaluator.assert_not_called()
    def test_resolver_gate_false_rejects_before_any_core_import(self):
        imports=[];original_import=builtins.__import__
        def guard(name,*args,**kwargs):
            if name in {'heuristic_runner','heft_method','schedules','thermal','timing','partial_bounds'}:
                imports.append(name);raise AssertionError('real core imported')
            return original_import(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=guard):
            with self.assertRaisesRegex(ContractError,'B0_RESEARCH_EXECUTION_NOT_AUTHORIZED'):
                resolve_real_bindings({'research_authorized':False},{'execution_enabled':False})
        self.assertEqual(imports,[])

    def test_mock_planner_uses_public_loader_full_root_and_restores_module(self):
        packet=planner_packet(self.pair,'R');clock=FakeClock(1000)
        root=RootClock(120,clock=clock);clock.now+=11
        original_budget=object();original_recorder=type('OriginalRecorder',(),{});seen={}
        result={'method':'heft','seed':None,'state':'UNRESOLVED',
                'reason':'DECLARED_SEARCH_COMPLETED','safe_candidate':None,'evaluations':[],
                'problem_id':packet['problem_id'],'input_sha256':packet['plan_sha256'],'timing':{'limit_s':120}}
        module=SimpleNamespace(MethodBudget=original_budget,CandidateRecorder=original_recorder)
        def runner(loader,workdir,**kw):
            self.assertEqual(kw['seconds'],120);self.assertIsNone(kw['seed'])
            self.assertTrue(kw['allow_auto_low']);self.assertIs(kw['evaluator'],self.evaluator)
            self.assertIs(kw['search'],self.bindings.search)
            budget=module.MethodBudget(seconds=kw['seconds'],clock=kw['clock'])
            c,i=loader(budget);seen.update(config=c,instance=i,elapsed=budget.elapsed)
            self.assertTrue(all(m['alpha']=='1' for rows in i['stage_modes'].values() for m in rows))
            return deepcopy(result)
        module.execute_heuristic=Mock(side_effect=runner)
        bindings=CoreBindings(module,self.bindings.search,self.evaluator,self.validator,FakeBase,FakeBaseExpired)
        with tempfile.TemporaryDirectory() as tmp:
            out=planner_chain(bindings,packet,root,Path(tmp)/'planner')
        self.assertEqual(seen['elapsed'],11)
        self.assertEqual(seen['instance'],packet['planner']['instance'])
        self.assertIs(module.MethodBudget,original_budget)
        self.assertIs(module.CandidateRecorder,original_recorder)
        self.assertIsNone(out['checked']['best'])
        self.evaluator.assert_not_called();self.bindings.search.assert_not_called()

    def test_mock_planner_restores_module_on_runner_exception(self):
        packet=planner_packet(self.pair,'H');root=RootClock(120,clock=self.clock)
        sentinel_budget=object();sentinel_recorder=type('OriginalRecorder',(),{})
        module=SimpleNamespace(MethodBudget=sentinel_budget,CandidateRecorder=sentinel_recorder,
            execute_heuristic=Mock(side_effect=RuntimeError('synthetic worker exception')))
        bindings=CoreBindings(module,Mock(),Mock(),Mock(),FakeBase,FakeBaseExpired)
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(RuntimeError,'synthetic worker exception'):
            planner_chain(bindings,packet,root,Path(tmp)/'planner')
        self.assertIs(module.MethodBudget,sentinel_budget)
        self.assertIs(module.CandidateRecorder,sentinel_recorder)


if __name__=='__main__':unittest.main()
