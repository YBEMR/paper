"""Freeze final SAFE identity with synthetic receipts only."""
import copy,unittest
from h02_pair_preflight.common import ContractError,sha
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet
from h02_pair_preflight.tests.fixtures import candidate_for,mock_safe_receipt
from h02_pair_b0.exports import verify_final_export

class Exports(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.packet=planner_packet(paired_response_input_view('base__R1'),'R')
    def setUp(self):
        i=self.packet['planner']['instance']; c=self.packet['planner']['config']
        a,b=candidate_for(i),candidate_for(i,5)
        rows=[{'source':source,'candidate':cand,'candidate_sha256':sha(cand),'evaluation':mock_safe_receipt(i,cand,c['accuracy_targets'],energy=e,formed=t),'returned_at_s':t,'accepted_safe':True} for cand,e,t,source in [(a,'1',1.0,'first'),(b,'2',2.0,'last')]]
        self.result={'method':'heft','seed':None,'problem_id':i['id'],'input_sha256':sha(i),'state':'SAFE','safe_candidate':a,'evaluation':rows[0]['evaluation'],'safe_upper_bound_J':'1','safe_solution_source':'first','evaluations':rows,'timing':{'limit_s':120}}
    def rejects(self):
        with self.assertRaises((ValueError,KeyError)): verify_final_export(self.packet,self.result)
    def test_best_not_last(self): self.assertEqual(verify_final_export(self.packet,self.result)['best']['source'],'first')
    def test_top_level_UNRESOLVED_with_candidate_rejected(self): self.result['state']='UNRESOLVED'; self.rejects()
    def test_top_level_SAFE_without_candidate_rejected(self): self.result['safe_candidate']=None; self.rejects()
    def test_source_mismatch(self): self.result['safe_solution_source']='last'; self.rejects()
    def test_prediction_upper_mismatch(self): self.result['safe_upper_bound_J']='2'; self.rejects()
    def test_raw_candidate_change(self): self.result['safe_candidate']=candidate_for(self.packet['planner']['instance'],5); self.rejects()
    def test_evaluation_changed(self): self.result['evaluation']=self.result['evaluations'][1]['evaluation']; self.rejects()
    def test_modeled_input_wrong(self): self.result['input_sha256']='wrong'; self.rejects()
    def test_wrong_budget(self): self.result['timing']['limit_s']=119; self.rejects()
    def test_missing_budget(self): self.result.pop('timing'); self.rejects()
    def test_late_safe(self): self.result['evaluation']['completed_at_elapsed_s']=120; self.rejects()
    def test_return_precedes_formation(self): self.result['evaluations'][0]['returned_at_s']=0.0; self.rejects()
    def test_missing_accepted_record(self): self.result['evaluations'][0]['accepted_safe']=False; self.rejects()
    def test_equal_upper_first_tie(self):
        self.result['evaluations'][1]['evaluation']=copy.deepcopy(self.result['evaluations'][0]['evaluation']); self.result['evaluations'][1]['evaluation']['evidence_identity']['candidate_sha256']=self.result['evaluations'][1]['candidate_sha256']
        self.assertEqual(verify_final_export(self.packet,self.result)['best']['source'],'first')
    def test_normal_NO_SAFE_wrong_input_is_not_normal_completion(self):
        self.result.update(state='UNRESOLVED',safe_candidate=None,evaluations=[],reason='DECLARED_SEARCH_COMPLETED',input_sha256='wrong')
        self.rejects()
    def test_normal_NO_SAFE_missing_root_is_interface_failure(self):
        self.result.update(state='UNRESOLVED',safe_candidate=None,evaluations=[],reason='DECLARED_SEARCH_COMPLETED');self.result.pop('timing')
        self.rejects()
    def test_no_SAFE_is_not_infeasible(self):
        self.result.update(state='UNRESOLVED',safe_candidate=None,evaluations=[])
        self.assertIsNone(verify_final_export(self.packet,self.result)['best'])
