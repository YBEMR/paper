"""H04 regression against the actual thin functions using Mock only."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from h02_pair_preflight.common import sha
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet
from h02_pair_preflight.paired_heuristic_entry import StageARegistry,MockBackend,paired_heuristic_entry
from h02_pair_preflight.truth_H_post_audit import MockAuditBackend,MockBudgetExpired,truth_H_post_audit
from h02_pair_preflight.tests.fixtures import candidate_for,mock_safe_receipt
class Budget:
    def __init__(self): self.elapsed=0.0; self.seconds=60
    def check(self):
        if self.elapsed>=self.seconds: raise MockBudgetExpired()
class ThinIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pair=paired_response_input_view('base__R1')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='h02_B0_thin_mock_'); self.addCleanup(self.temp.cleanup)
        self.registry=StageARegistry(Path(self.temp.name)); self.registry.bind_pair(self.pair)
        self.packet=planner_packet(self.pair,'R'); self.budget=Budget()
    def plan(self,mutate=None):
        i=self.packet['planner']['instance'];c=self.packet['planner']['config'];cand=candidate_for(i)
        for rows in cand['scenes'].values(): rows[1]['start_ms']='0' # explicit synthetic overlap, not a real R SAFE
        receipt=mock_safe_receipt(i,cand,c['accuracy_targets'])
        row={'candidate':cand,'candidate_sha256':sha(cand),'source':'MOCK','evaluation':receipt,'accepted_safe':True,'returned_at_s':1.0}
        result={'method':'heft','seed':None,'state':'SAFE','problem_id':i['id'],'input_sha256':sha(i),'safe_candidate':cand,'safe_upper_bound_J':'1','evaluation':receipt,'safe_solution_source':'MOCK','evaluations':[row],'timing':{'limit_s':120},'reason':'DECLARED_SEARCH_COMPLETED'}
        if mutate: mutate(result)
        return paired_heuristic_entry(self.packet,MockBackend(Mock(return_value=result),Mock(),Mock(),lambda:1),self.registry,'slot',sha(self.pair['truth_H']['instance']))
    def audit(self,reason):
        planned=self.plan(); token=planned['frozen_candidate'];rows=next(iter(__import__('json').loads(token['candidate_json'])['scenes'].values()))
        legal={'state':'INVALID_SCHEDULE','reason':reason,'details':{'stages':[rows[0]['stage_id'],rows[1]['stage_id']]} if reason=='EXECUTION_UNIT_OVERLAP' else {},'thermal_status':'NOT_EVALUATED','energy_status':'NOT_EVALUATED'}
        backend=MockAuditBackend(Mock(return_value=legal),Mock(side_effect=AssertionError('NO_HEAT_AFTER_INVALID')),Mock(return_value=self.budget))
        binding={k:token[k] for k in ('source_commit_sha','problem_id','truth_H_sha256','policy_id','accuracy_sha256')}
        return truth_H_post_audit(token,self.pair['truth_H'],binding,backend,self.registry)
    def test_MALFORMED_INPUT_OR_CANDIDATE_is_technical_not_math_counterexample(self):
        out=self.audit('MALFORMED_INPUT_OR_CANDIDATE');self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR');self.assertTrue(out['stop_required']);self.assertNotIn('anomaly',out)
    def test_UNSUPPORTED_IDLE_POLICY_is_technical_not_math_counterexample(self):
        out=self.audit('UNSUPPORTED_IDLE_POLICY');self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR');self.assertTrue(out['stop_required']);self.assertNotIn('anomaly',out)
    def test_unknown_reason_fails_closed(self):
        out=self.audit('NEW_UNREVIEWED_REASON');self.assertEqual(out['audit_status'],'INPUT_OR_INTERFACE_ERROR')
    def test_actual_overlap_certificate_triggers_R_contract_anomaly(self):
        out=self.audit('EXECUTION_UNIT_OVERLAP');self.assertEqual(out['audit_status'],'TRUE_H_INVALID');self.assertEqual(out['anomaly'],'MONOTONICITY_CONTRACT_ANOMALY')
    def test_classification_crossing_60_cannot_add_new_invalid_proof(self):
        from h02_pair_b0.classification import classify_invalid_schedule
        def late(*a):
            value=classify_invalid_schedule(*a);self.budget.elapsed=60;return value
        with patch('h02_pair_b0.classification.classify_invalid_schedule',side_effect=late):out=self.audit('EXECUTION_UNIT_OVERLAP')
        self.assertEqual(out['audit_status'],'TRUE_H_UNRESOLVED');self.assertNotIn('anomaly',out);self.assertTrue(out['audit_consumed'])
    def test_thin_plan_rejects_NONSAFE_top_level(self):
        out=self.plan(lambda r:r.update(state='UNRESOLVED'));self.assertEqual(out['plan_status'],'INPUT_OR_INTERFACE_ERROR')
    def test_thin_plan_rejects_source_mismatch(self):
        out=self.plan(lambda r:r.update(safe_solution_source='other'));self.assertEqual(out['plan_status'],'INPUT_OR_INTERFACE_ERROR')
