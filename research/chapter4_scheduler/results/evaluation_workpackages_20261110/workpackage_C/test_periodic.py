"""Artificial arithmetic/interface tests; real workload propagation forbidden."""
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime,timezone
from fractions import Fraction as F
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[4]
sys.path[:0]=[str(OUT),str(REPO/'research/chapter3_experiments')]
import periodic_core as core

NODES=['a','b','c','d']
def platform():return {'node_order':NODES,'heat_capacity_J_per_K':['1']*4,'conductance_W_per_K':[['1' if i==j else '0' for j in range(4)] for i in range(4)],'power_model_temperature_range_degC':['20','100'],'ambient_temperature_degC':'25'}
def segment():return {'start_ms':'0','end_ms':'1000','duration_ms':'1000','local_leakage_slope_W_per_K':{n:'0' for n in NODES}}
def receipt(entry,end,point=False):
    mid=[(F(v[0])+F(v[1]))/2 for v in end];peaks={n:[str(max(F(t),mid[i]))]*2 for i,(n,t) in enumerate(zip(NODES,entry))};mins={n:[str(min(F(t),mid[i]))]*2 for i,(n,t) in enumerate(zip(NODES,entry))}
    violations=[{'node':n,'scene_id':'S','time_s':'1','temperature_degC':peaks[n],'limit_degC':'80'} for n in NODES if F(peaks[n][0])>80] if point else []
    return {'state':'THERMAL_VIOLATION' if violations else 'SAFE','reason':'MOCK_ONLY','complete':True,'covered_until_s':'1','peaks_degC':peaks,'minimum_degC':mins,
        'final_temperature_degC':dict(zip(NODES,end)),'temperature_rise_integrals_Ks':{n:[str((F(t)+mid[i])/2-25)]*2 for i,(n,t) in enumerate(zip(NODES,entry))},
        'energy_J':['1','1'],'energy_components_J':{'baseline':['1','1'],'activity':['0','0'],'external_common':['0','0'],'temperature_correction':['0','0']},'violations':violations}
def review(target,max_rounds=8):
    calls=[]
    def evaluate(entry,label):
        calls.append(label);end=[[str(F(target)+(F(t)-F(target))/2)]*2 for t in entry];return receipt(entry,end,point=True)
    evaluate.segments=[segment()]
    instance={'platform':platform(),'scenarios':[{'id':'S','entry':{'temperature_degC':['50']*4},'maximum_temperature_degC':['80']*4}]}
    with patch.object(core,'fixed_point_guess',return_value=([str(target)]*4,{'role':'MOCK_ONLY'})):
        result=core.review_configuration({},instance,{},'S','1000',evaluate,max_rounds=max_rounds)
    return result,calls

class Tests(unittest.TestCase):
    def test_clip_only_idle_tail_and_keep_original(self):
        old=[dict(segment(),start_ms='0',end_ms='75',duration_ms='75',active_stage_ids=['x']),dict(segment(),start_ms='75',end_ms='400',duration_ms='325',active_stage_ids=[])]
        before=deepcopy(old);new=core.clip_period(old,'90','75');self.assertEqual(new[-1]['end_ms'],'90');self.assertEqual(new[-1]['duration_ms'],'15');self.assertEqual(old,before)
    def test_period_cannot_shorten_busy_schedule(self):
        with self.assertRaises(ValueError):core.clip_period([segment()],'75','87')
    def test_exact_metlzer_contraction(self):
        r=core.contraction(platform(),[segment()],'1000');self.assertEqual(F(r['alpha_per_s']),1);self.assertEqual(F(r['q_rational_upper']),F(1,2))
    def test_noncontractive_feedback_rejected(self):
        s=segment();s['local_leakage_slope_W_per_K']['a']='1'
        with self.assertRaises(ValueError):core.contraction(platform(),[s],'1000')
    def test_negative_slope_rejected_for_energy_order(self):
        s=segment();s['local_leakage_slope_W_per_K']['a']='-1'
        with self.assertRaises(ValueError):core.contraction(platform(),[s],'1000')
    def test_nonmetzler_matrix_rejected(self):
        p=platform();p['conductance_W_per_K'][0][1]=p['conductance_W_per_K'][1][0]='1'
        with self.assertRaises(ValueError):core.contraction(p,[segment()],'1000')
    def test_residual_radius_exact_no_float(self):
        r,b=core.residual_radius(['50']*4,[['49.9','50.2']]*4,'1/2');self.assertEqual(r,F(1,5));self.assertEqual(b,F(2,5))
    def test_box_distance_uses_both_widths(self):self.assertEqual(core.box_distance([['49','51']],[['50','52']]),3)
    def test_means_are_ambient_plus_integral_divided_by_period(self):
        r=receipt(['50']*4,[['40','40']]*4);b=core.combine_paths(r,r,platform(),'1000');self.assertEqual(F(b['mean_by_node_degC']['a'][0]),45)
    def test_incomplete_period_is_not_safe(self):
        r=receipt(['50']*4,[['40','40']]*4);r['complete']=False
        with self.assertRaises(ValueError):core.combine_paths(r,r,platform(),'1000')
    def test_model_range_checked_on_lower_path(self):
        r=receipt(['50']*4,[['40','40']]*4);r['minimum_degC']['a']=['19','19']
        with self.assertRaises(ValueError):core.combine_paths(r,r,platform(),'1000')
    def test_safe_requires_prefix_and_infinite_tail(self):
        r,calls=review(30);self.assertEqual(r['classification'],'SAFE_ALL_ROUNDS');self.assertEqual(r['checked_round_count'],1);self.assertTrue(r['startup_rounds'][0]['tail_model_range_certified']);self.assertFalse(r['periodic_energy_is_diagnostic_only']);self.assertEqual(len(calls),4)
    def test_actual_low_point_certifies_first_unsafe(self):
        r,_=review(90);self.assertEqual(r['classification'],'THERMAL_VIOLATION');self.assertEqual(r['first_unsafe_round'],3);self.assertTrue(r['earlier_rounds_all_safe']);self.assertEqual(r['violation_witness']['global_time_s'],'3');self.assertTrue(r['periodic_energy_is_diagnostic_only'])
    def test_safe_temperatures_but_unknown_future_model_lower_bound(self):
        r,_=review(20,max_rounds=3);self.assertEqual(r['classification'],'UNRESOLVED_MAX_ROUNDS');self.assertIsNone(r['all_rounds_conservative_upper_degC'])
    def test_ordered_interface_inversion_rejected(self):
        lo=receipt(['50']*4,[['40','40']]*4);hi=deepcopy(lo);lo['energy_J']=['2','2']
        with self.assertRaises(ValueError):core.combine_paths(lo,hi,platform(),'1000')

def main():
    stream=io.StringIO();forbidden=[];started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    def deny(*args,**kwargs):forbidden.append('REAL_HEAT_OR_SEARCH');raise AssertionError('NO_REAL_HEAT_OR_SEARCH')
    with ExitStack() as stack:
        for name in ('thermal.evaluate_candidate','thermal.evaluate_piecewise','heft_method.run_heft','heft_method.build_heft_candidate','sa_method.run_sa'):
            stack.enter_context(patch(name,side_effect=deny))
        results=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    record={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-clock,'passed':results.wasSuccessful() and not forbidden,'tests_run':results.testsRun,'forbidden_calls':forbidden,'real_workload_heat_calls':0,'real_scheduling_calls':0,'evidence_kind':'ARTIFICIAL_RATIONAL_ARITHMETIC_AND_INVENTED_PERIOD_MAPS_ONLY','failures':[str(v) for v in results.failures],'errors':[str(v) for v in results.errors]}
    with (OUT/'artificial_checks.json').open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2);f.write('\n')
    (OUT/'artificial_test_output.txt').write_text(stream.getvalue());print(record,flush=True);return not record['passed']

if __name__=='__main__':sys.exit(main())
