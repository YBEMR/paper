"""Scalar-contract and MOCK_ONLY regressions. No physical core executes."""
import copy,json,unittest
from decimal import localcontext,ROUND_HALF_UP
from fractions import Fraction as F
from pathlib import Path
from h02_pair_preflight.common import ContractError,sha
from h02_pair_preflight.receipts import external_common_energy_interval,safe_receipt
from h02_pair_preflight.tests import test_receipts as old_receipts
from h02_pair_preflight.tests.fixtures import candidate_for,mock_safe_receipt
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet
from h02_pair_b0.exports import verify_final_export

E=F('0.12'); EPS=F(1,10**60)
TRACE=[{'time_s':'1/7'},{'time_s':'2/5'}]
def scalar(lo=E-EPS,hi=E+EPS,trace=TRACE):
    out={'energy_components_J':{'external_common':[str(lo),str(hi)]}}
    if trace is not None: out['trace']=copy.deepcopy(trace)
    return out

def widen_mock(receipt,radius=EPS):
    """Only invented fields; retain global/component and weighted enclosures."""
    scene=receipt['scenes']['AB_offset_0ms']
    scene['energy_components_J']['external_common']=[str(E-radius),str(E+radius)]
    scene['trace']=copy.deepcopy(TRACE)
    value=F(scene['energy_J'][0])
    scene['energy_J']=[str(value-radius),str(value+radius)]
    value=F(receipt['weighted_energy_J'][0])
    receipt['weighted_energy_J']=[str(value-radius/2),str(value+radius/2)]
    receipt['safe_upper_bound_J']=receipt['weighted_energy_J'][1]
    return receipt

class ScalarContract(unittest.TestCase):
    def rejects(self,scene,pattern='.',power='0.30',window='0.4'):
        with self.assertRaisesRegex(ContractError,pattern):external_common_energy_interval(scene,power,window)
    def test_exact_point_without_trace_backward_compatible(self):
        self.assertEqual(external_common_energy_interval(scalar(E,E,None),'0.30','0.4'),(E,E))
    def test_normal_nonterminating_panel_rounding(self):
        self.assertEqual(external_common_energy_interval(scalar(),'0.30','0.4'),(E-EPS,E+EPS))
    def test_tighter_certified_interval_allowed(self):
        self.assertEqual(external_common_energy_interval(scalar(E-EPS/2,E+EPS/2),'0.30','0.4'),(E-EPS/2,E+EPS/2))
    def test_lower_only_rounding_allowed(self):
        self.assertEqual(external_common_energy_interval(scalar(E-EPS,E),'0.30','0.4'),(E-EPS,E))
    def test_upper_only_rounding_allowed(self):
        self.assertEqual(external_common_energy_interval(scalar(E,E+EPS),'0.30','0.4'),(E,E+EPS))
    def test_ambient_decimal_context_does_not_change_contract(self):
        with localcontext() as ctx:
            ctx.prec=6;ctx.rounding=ROUND_HALF_UP
            self.assertEqual(external_common_energy_interval(scalar(),'0.30','0.4'),(E-EPS,E+EPS))
    def test_shifted_below_exact_rejected(self):self.rejects(scalar(E-2*EPS,E-EPS),'EXTERNAL_POWER_ACCOUNTING')
    def test_shifted_above_exact_rejected(self):self.rejects(scalar(E+EPS,E+2*EPS),'EXTERNAL_POWER_ACCOUNTING')
    def test_double_counting_rejected(self):self.rejects(scalar(2*E,2*E,None),'EXTERNAL_POWER_ACCOUNTING')
    def test_omitted_external_energy_rejected(self):self.rejects(scalar(F(0),F(0),None),'EXTERNAL_POWER_ACCOUNTING')
    def test_width_ten_times_rounding_rejected(self):self.rejects(scalar(E-10*EPS,E+10*EPS),'EXTERNAL_ROUNDING_ENCLOSURE')
    def test_containment_alone_is_not_enough(self):self.rejects(scalar(F(0),2*E),'EXTERNAL_ROUNDING_ENCLOSURE')
    def test_global_energy_tolerance_is_not_extra_slack(self):self.rejects(scalar(E-F('1e-7'),E+F('1e-7')),'EXTERNAL_ROUNDING_ENCLOSURE')
    def test_nonpoint_missing_trace_rejected(self):self.rejects(scalar(trace=None),'EXTERNAL_ENERGY_TRACE')
    def test_nonpoint_empty_trace_rejected(self):self.rejects(scalar(trace=[]),'EXTERNAL_ENERGY_TRACE')
    def test_trace_must_be_list(self):self.rejects(scalar(trace={'time_s':'2/5'}),'EXTERNAL_ENERGY_TRACE')
    def test_missing_trace_time_rejected(self):self.rejects(scalar(trace=[{},TRACE[-1]]),'EXTERNAL_ENERGY_TRACE')
    def test_zero_first_end_rejected(self):self.rejects(scalar(trace=[{'time_s':'0'},TRACE[-1]]),'EXTERNAL_ENERGY_TRACE')
    def test_negative_time_rejected(self):self.rejects(scalar(trace=[{'time_s':'-1/7'},TRACE[-1]]),'EXTERNAL_ENERGY_TRACE')
    def test_duplicate_time_rejected(self):self.rejects(scalar(trace=[TRACE[0],TRACE[0],TRACE[1]]),'EXTERNAL_ENERGY_TRACE')
    def test_decreasing_time_rejected(self):self.rejects(scalar(trace=[TRACE[1],TRACE[0]]),'EXTERNAL_ENERGY_TRACE')
    def test_missing_idle_tail_rejected(self):self.rejects(scalar(trace=[TRACE[0]]),'EXTERNAL_ENERGY_TRACE')
    def test_overshooting_window_rejected(self):self.rejects(scalar(trace=[TRACE[0],{'time_s':'0.41'}]),'EXTERNAL_ENERGY_TRACE')
    def test_float_trace_not_exact(self):self.rejects(scalar(trace=[{'time_s':0.1},TRACE[1]]),'NONEXACT_SCALAR')
    def test_bool_trace_not_exact(self):self.rejects(scalar(trace=[{'time_s':True},TRACE[1]]),'NONEXACT_SCALAR')
    def test_nonfinite_trace_rejected(self):self.rejects(scalar(trace=[{'time_s':'NaN'},TRACE[1]]),'INVALID_EXACT_SCALAR')
    def test_zero_power_point_allowed(self):
        self.assertEqual(external_common_energy_interval(scalar(F(0),F(0),None),'0','0.4'),(F(0),F(0)))
    def test_zero_power_padded_interval_rejected(self):self.rejects(scalar(F(0),EPS),'EXTERNAL_ROUNDING_ENCLOSURE',power='0')
    def test_negative_power_rejected(self):self.rejects(scalar(),'EXTERNAL_POWER_OR_WINDOW',power='-0.3')
    def test_zero_window_rejected(self):self.rejects(scalar(),'EXTERNAL_POWER_OR_WINDOW',window='0')
    def test_wrong_milliseconds_to_seconds_rejected(self):self.rejects(scalar(),'EXTERNAL_POWER_ACCOUNTING',window='400')
    def test_negative_endpoint_rejected(self):self.rejects(scalar(-EPS,E),'ENERGY_INTERVAL_ORDER')
    def test_reversed_interval_rejected(self):self.rejects(scalar(E+EPS,E-EPS),'ENERGY_INTERVAL_ORDER')
    def test_float_endpoint_rejected(self):
        s=scalar();s['energy_components_J']['external_common'][0]=0.12;self.rejects(s,'NONEXACT_SCALAR')
    def test_nonfinite_endpoint_rejected(self):
        s=scalar();s['energy_components_J']['external_common'][0]='Infinity';self.rejects(s,'INVALID_EXACT_SCALAR')
    def test_bad_interval_shape_rejected(self):
        s=scalar();s['energy_components_J']['external_common']=['0.12'];self.rejects(s,'ENERGY_INTERVAL_SHAPE')

class MockReceiptIntegration(unittest.TestCase):
    def setUp(self):
        fixture=old_receipts.ReceiptContractTests('test_complete_mock_safe_acceptance');fixture.setUp()
        self.instance=fixture.instance;self.candidate=fixture.candidate;self.accuracy=fixture.accuracy
        self.receipt=widen_mock(fixture.receipt)
    def accept(self):return safe_receipt(self.instance,self.candidate,self.receipt,self.accuracy,120)
    def rejects(self,pattern):
        with self.assertRaisesRegex(ContractError,pattern):self.accept()
    def test_complete_synthetic_nonpoint_receipt(self):
        out=self.accept();self.assertEqual(F(out['lower']),1-EPS/2);self.assertTrue(out['all_scenes_complete'])
        self.assertEqual(self.receipt['evidence_kind'],'MOCK_ONLY');self.assertFalse(self.receipt['formal_experiment_result'])
    def test_too_wide_component_rejected_even_if_global_precision_met(self):
        self.receipt=widen_mock(mock_safe_receipt(self.instance,self.candidate,self.accuracy),F('1e-7'))
        self.rejects('EXTERNAL_ROUNDING_ENCLOSURE')
    def test_scene_precision_not_relaxed(self):
        self.receipt['scenes']['AB_offset_0ms']['energy_J']=['0.9','1.1'];self.rejects('SCENE_ENERGY_PRECISION')
    def test_weighted_precision_not_relaxed(self):
        self.receipt['weighted_energy_J']=['0.9','1.1'];self.receipt['safe_upper_bound_J']='1.1';self.rejects('WEIGHTED_ENERGY_PRECISION')
    def test_thermal_limit_not_relaxed(self):
        self.receipt['scenes']['AB_offset_0ms']['peaks_degC']['NPU0']=['81','81'];self.rejects('CONTINUOUS_THERMAL_BOUNDS')
    def test_temperature_precision_not_relaxed(self):
        self.receipt['scenes']['AB_offset_0ms']['peaks_degC']['NPU0']=['50','50.01'];self.rejects('TEMPERATURE_RANGE_OR_PRECISION')
    def test_deadline_not_relaxed(self):
        self.receipt['completed_at_elapsed_s']=120;self.rejects('LATE_OR_INVALID_SAFE_TIMESTAMP')
    def test_identity_not_relaxed(self):
        self.receipt['evidence_identity']['candidate_sha256']='wrong';self.rejects('RECEIPT_EVIDENCE_IDENTITY')
    def test_scene_coverage_not_relaxed(self):
        del self.receipt['scenes']['AC_offset_0ms'];self.rejects('INCOMPLETE_SCENE_RECEIPT')
    def test_candidate_and_receipt_not_mutated(self):
        before=sha((self.instance,self.candidate,self.receipt,self.accuracy));self.accept()
        self.assertEqual(sha((self.instance,self.candidate,self.receipt,self.accuracy)),before)

class MockFinalExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet=planner_packet(paired_response_input_view('base__R1'),'R')
    def test_nonbest_historical_row_with_rounding_does_not_break_final_identity(self):
        i=self.packet['planner']['instance'];accuracy=self.packet['planner']['config']['accuracy_targets']
        rows=[]
        for offset,energy,source in [(0,'1','best'),(5,'2','nonbest')]:
            cand=candidate_for(i,offset);receipt=mock_safe_receipt(i,cand,accuracy,energy=energy)
            if offset:receipt=widen_mock(receipt)
            rows.append({'candidate':cand,'candidate_sha256':sha(cand),'evaluation':receipt,'source':source,'returned_at_s':2.0,'accepted_safe':True})
        result={'method':'heft','seed':None,'state':'SAFE','problem_id':i['id'],'input_sha256':sha(i),
          'safe_candidate':rows[0]['candidate'],'evaluation':rows[0]['evaluation'],'safe_upper_bound_J':'1',
          'safe_solution_source':'best','evaluations':rows,'timing':{'limit_s':120}}
        before=sha(result);checked=verify_final_export(self.packet,result)
        self.assertEqual(checked['best']['source'],'best');self.assertEqual(sha(result),before)
    def test_mock_post_audit_still_never_claims_research_SAFE(self):
        from h02_pair_b0.tests import test_backends as backend
        backend.BackendWiringTests.setUpClass()
        case=backend.BackendWiringTests('test_mock_safe_never_claims_research_safe');case.setUp()
        case.evaluator.side_effect=lambda i,c,a,b:widen_mock(mock_safe_receipt(i,c,a,formed=b.elapsed+1))
        out=case.run_audit()
        self.assertEqual(out['audit_status'],'TRUE_H_SAFE');self.assertFalse(out['real_safe'])
        self.assertFalse(out['usable_as_research_evidence']);case.bindings.search.assert_not_called()

class ArchivedScalarOnly(unittest.TestCase):
    def test_original_failed_component_only_not_a_new_safe_acceptance(self):
        core=Path(__file__).resolve().parents[2]
        p=core/'results/h02_same_truth_execution01/slot_1/planner_public/method/result.json'
        raw=json.loads(p.read_text(encoding='utf-8'));scene=raw['evaluations'][33]['evaluation']['scenes']['AC_offset_0ms']
        before=sha(scene);value=scene['energy_components_J']['external_common']
        self.assertNotEqual(tuple(map(F,value)),(E,E))
        self.assertEqual(external_common_energy_interval(scene,'0.30','0.4'),tuple(map(F,value)))
        self.assertEqual(sha(scene),before)
        # Only a scalar component was checked: no candidate acceptance or heat replay.

if __name__=='__main__':unittest.main()
