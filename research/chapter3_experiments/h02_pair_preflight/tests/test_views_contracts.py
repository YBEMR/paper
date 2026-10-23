"""Exact inputs and injected negative contracts; no scheduling/thermal calls."""
import unittest
from copy import deepcopy
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,pair_audit,planner_packet,physical_projection,fresh_H
from h02_pair_preflight.contracts import static_monotonicity_contract
from h02_pair_preflight.common import candidate_identity,raw_candidate,sha,encoded,ContractError
from h02_pair_preflight.paired_heuristic_entry import StageARegistry,validate_packet
from .fixtures import candidate_for

class ViewsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pairs={p:paired_response_input_view(p) for p in ('base__R1','base__R2')}
    def pair(self): return deepcopy(self.pairs['base__R1'])
    def test_both_cases_static_formulas(self):
        for p in self.pairs.values():
            self.assertTrue(p['audit']['passed'])
            self.assertTrue(static_monotonicity_contract(p['truth_H']['config'],p['truth_H']['instance'],p['planner_R']['instance'])['passed'])
            self.assertEqual(len(p['audit']['mode_diff']),66)
    def test_independent_copies(self):
        p=self.pair(); p['planner_R']['instance']['scenarios'][0]['weight']='1'
        self.assertEqual(p['truth_H'],p['planner_H'])
        self.assertEqual(p['truth_H']['instance']['scenarios'][0]['weight'],'1/2')
    def test_R_payload_has_only_masked_alphas(self):
        packet=planner_packet(self.pair(),'R'); validate_packet(packet)
        self.assertNotIn('truth_H',packet); self.assertNotIn('audit',packet)
        self.assertNotIn('H_alpha',str(packet)); self.assertEqual(packet['problem_id'],'base__R1')
    def test_global_R_constructor_trap_rejected(self):
        from inputs import build_instance
        c=self.pair()['planner_R']['config']
        with self.assertRaisesRegex(ValueError,'Duplicate effective condition'): build_instance(c,'base__R1')
    def test_candidate_raw_semantic_identity(self):
        i=self.pair()['truth_H']['instance']; a=candidate_for(i); b=deepcopy(a)
        for rows in b['scenes'].values():
            rows.reverse()
            for row in rows: row['start_ms']=str(row['start_ms'])+'/1'
        aa,bb=candidate_identity(i,a),candidate_identity(i,b)
        self.assertNotEqual(aa['candidate_raw_sha256'],bb['candidate_raw_sha256'])
        self.assertEqual(aa['candidate_semantic_sha256'],bb['candidate_semantic_sha256'])
    def test_duplicate_JSON_keys_rejected(self):
        with self.assertRaises(ContractError): raw_candidate(b'{"scenes":{},"scenes":{}}')
    def test_JSON_floats_and_NaN_rejected(self):
        for v in (b'{"x":0.0}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(ContractError): raw_candidate(v)

# Separate tests preserve a readable rejection receipt for each injected drift.
def make_drift(name,mutation):
    def test(self):
        p=self.pair(); mutation(p)
        with self.assertRaises((ValueError,KeyError)):
            pair_audit(p['planner_H']['config'],p['planner_H']['instance'],p['planner_R']['config'],p['planner_R']['instance'])
    test.__name__='test_reject_'+name; return test

def first_mode(p): return next(iter(p['planner_R']['instance']['stage_modes'].values()))[0]
def first_profile(p): return next(iter(p['planner_R']['config']['stage_catalog'][0]['profiles'].values()))
DRIFTS={
 'R_config_H_alpha':lambda p:first_profile(p).__setitem__('alpha','1/2'),
 'R_mode_H_alpha':lambda p:first_mode(p).__setitem__('alpha','1/2'),
 'R_mean_H_alpha':lambda p:p['planner_R']['instance']['catalog_duration_weighted_mean_alpha'].__setitem__('CPU','1/2'),
 'R_activity_power':lambda p:first_mode(p).__setitem__('activity_power_W','999'),
 'R_duration_formula':lambda p:first_mode(p).__setitem__('duration_ms','999'),
 'R_energy_formula':lambda p:first_mode(p).__setitem__('activity_energy_J','999'),
 'mode_missing':lambda p:next(iter(p['planner_R']['instance']['stage_modes'].values())).pop(),
 'mode_duplicate':lambda p:next(iter(p['planner_R']['instance']['stage_modes'].values())).append(deepcopy(first_mode(p))),
 'mode_order':lambda p:next(iter(p['planner_R']['instance']['stage_modes'].values())).reverse(),
 'stage_support_missing':lambda p:p['planner_R']['instance']['stage_modes'].pop(next(iter(p['planner_R']['instance']['stage_modes']))),
 'grid_changed':lambda p:p['planner_R']['instance'].__setitem__('start_grid_ms','10'),
 'deadline_changed':lambda p:p['planner_R']['instance']['scenarios'][0]['requests'][0].__setitem__('deadline_ms','200'),
 'thermal_matrix_changed':lambda p:p['planner_R']['instance']['platform']['conductance_W_per_K'][0].__setitem__(0,'999'),
 'baseline_changed':lambda p:p['planner_R']['instance']['platform']['domains']['CPU']['baseline_W'].__setitem__('L','0'),
 'extra_feedback_field':lambda p:p['planner_R']['config'].__setitem__('truth_H_feedback',{'score':'1'}),
 'case_identity':lambda p:p['planner_R']['instance'].__setitem__('id','response_R__R1'),
}
for name,mutation in DRIFTS.items(): setattr(ViewsContracts,'test_reject_'+name,make_drift(name,mutation))

def make_premise(name,mutate):
    def test(self):
        p=self.pair(); c,h,r=p['truth_H']['config'],p['truth_H']['instance'],p['planner_R']['instance']
        mutate(c,h,r)
        # Synchronize physical records to defeat a mere H/R-equality check.
        h['platform']=deepcopy(c['platform']); r['platform']=deepcopy(c['platform'])
        h['execution_rules']=deepcopy(c['execution_rules']); r['execution_rules']=deepcopy(c['execution_rules'])
        with self.assertRaises(ValueError): static_monotonicity_contract(c,h,r)
    return test
PREMISES={
 'negative_C':lambda c,h,r:c['platform']['heat_capacity_J_per_K'].__setitem__(0,'0'),
 'nonpassive_G':lambda c,h,r:c['platform']['conductance_W_per_K'][0].__setitem__(1,'1/100'),
 'nongrounded_G':lambda c,h,r:c['platform']['conductance_W_per_K'][0].__setitem__(0,'0'),
 'baseline_not_monotone':lambda c,h,r:c['platform']['domains']['CPU']['baseline_W'].__setitem__('L','2'),
 'lambda_not_monotone':lambda c,h,r:c['platform']['domains']['CPU']['local_temperature_slope_W_per_K'].__setitem__('L','1'),
 'negative_heat_split':lambda c,h,r:c['platform']['domains']['CPU']['baseline_heat_distribution'].__setitem__(0,'-1/2'),
 'ambient_reference_mismatch':lambda c,h,r:c['platform'].__setitem__('reference_temperature_degC','30'),
 'H_alpha_outside_unit':lambda c,h,r:next(iter(c['stage_catalog'][0]['profiles'].values())).__setitem__('alpha','2'),
 'idle_delay':lambda c,h,r:c['execution_rules'].__setitem__('idle_delay_ms','1'),
 'nonzero_switch_cost':lambda c,h,r:c['execution_rules'].__setitem__('extra_switch_energy_J','1'),
 'external_heat_injection':lambda c,h,r:c['platform']['external_common_heat_distribution'].__setitem__(0,'1'),
 'different_initial':lambda c,h,r:h['scenarios'][0]['entry']['temperature_degC'].__setitem__(0,'24'),
}
for name,mutation in PREMISES.items(): setattr(ViewsContracts,'test_premise_'+name,make_premise(name,mutation))
