"""Pure algebra checks for independent full/conditional energy bounds.

The hand-written power panels are algebraic relaxations, not RC solutions,
SAFE schedules, heat evaluations or method-performance observations.
"""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from control_policy import AUTO_LOW_IMMEDIATE_V1, LEGACY_IDLE_HOLD, with_auto_low_idle
import partial_bounds as bounds


PRECHECK_RECORDS = {'scope':'unit-test algebra only; zero heat/model/solver calls'}


def algebra_instance(*, auto=True):
    """A complete hand-sized physical declaration, independent of old answers."""
    units = [dict(id=u,domain_id=d,power_group_id=d,thermal_node_id=u)
             for u,d in [('CPU1','CPU'),('CPU2','CPU'),('NPU0','NPU')]]
    opps = {'L':{'frequency_GHz':'1','voltage_V':'1'},
            'H':{'frequency_GHz':'2','voltage_V':'1'}}
    domains = {
        'CPU':{'unit_ids':['CPU1','CPU2'],'opps':deepcopy(opps),
               'baseline_W':{'L':'2','H':'4'},
               'local_temperature_slope_W_per_K':{'L':'1/10','H':'1/5'},
               'baseline_heat_distribution':['1/2','1/2','0']},
        'NPU':{'unit_ids':['NPU0'],'opps':deepcopy(opps),
               'baseline_W':{'L':'1','H':'3'},
               'local_temperature_slope_W_per_K':{'L':'1/20','H':'1/10'},
               'baseline_heat_distribution':['0','0','1']}}
    platform = {'node_order':['CPU1','CPU2','NPU0'],'units':units,'domains':domains,
        'heat_capacity_J_per_K':['1','1','1'],
        'conductance_W_per_K':[['1','0','0'],['0','1','0'],['0','0','1']],
        'ambient_temperature_degC':'25','reference_temperature_degC':'25',
        'power_model_temperature_range_degC':['20','100'],
        'external_common_power_W':'1/2','external_common_heat_distribution':['0','0','0']}
    rules = dict(preemption=False,migration=False,in_stage_opp_change=False,
        switch_only_when_domain_empty=True,idle_holds_last_opp=True,
        interval_convention='[start,end)')
    for field in ('extra_transfer_time_ms','extra_switch_time_ms','extra_handoff_time_ms',
                  'extra_transfer_energy_J','extra_switch_energy_J','extra_handoff_energy_J'):
        rules[field] = '0'
    by_unit = {unit['id']:unit for unit in units}

    def mode(stage,unit,opp,duration,power):
        domain = by_unit[unit]['domain_id']
        return {'shared_stage_id':stage,'unit_id':unit,'opp_id':opp,
                'domain_id':domain,'power_group_id':domain,'thermal_node_id':unit,
                **opps[opp],'duration_ms':duration,'activity_power_W':power,
                'activity_energy_J':str(F(duration)*F(power)/1000)}

    modes = {
        'A':[mode('A','CPU1','L','100','2'),mode('A','CPU1','H','50','8'),
             mode('A','NPU0','L','200','1/2'),mode('A','NPU0','H','100','2')],
        'B':[mode('B','CPU2','L','100','1'),mode('B','CPU2','H','50','3')],
        'C':[mode('C','NPU0','L','100','1/4'),mode('C','NPU0','H','50','1')]}
    scenes = []
    for sid,local,weight in [('AB','B','1/4'),('AC','C','3/4')]:
        stages,requests = [],[]
        for stage in ['A',local]:
            iid,rid = sid+'.'+stage,sid+'.request.'+stage
            stages.append({'id':iid,'shared_stage_id':stage,'request_id':rid})
            requests.append({'id':rid,'stage_instance_ids':[iid],
                             'release_ms':'0','deadline_ms':'1000'})
        scenes.append({'id':sid,'weight':weight,'stage_instances':stages,
            'requests':requests,'dependencies':[],
            'entry':{'temperature_degC':['25','25','25'],
                     'domain_opp':{'CPU':'L','NPU':'L'},'unfinished_work':[]},
            'maximum_temperature_degC':['80','80','80']})
    instance = {'window_ms':'1000','start_grid_ms':'1','execution_rules':rules,
                'platform':platform,'stage_modes':modes,'scenarios':scenes}
    return with_auto_low_idle(instance) if auto else instance


# All local temperatures are the declared Tmin. These panels deliberately do
# not assert the thermal differential equation; they attain a relaxed bound.
MANUAL_GLOBAL = {
    'AB':[('0','200',{'CPU':'L','NPU':'L'},['0','0','1/2']),
          ('200','300',{'CPU':'L','NPU':'L'},['0','1','0']),
          ('300','1000',{'CPU':'L','NPU':'L'},['0','0','0'])],
    'AC':[('0','200',{'CPU':'L','NPU':'L'},['0','0','1/2']),
          ('200','300',{'CPU':'L','NPU':'L'},['0','0','1/4']),
          ('300','1000',{'CPU':'L','NPU':'L'},['0','0','0'])]}
MANUAL_CPU_CONDITION = {
    'AB':[('0','100',{'CPU':'L','NPU':'L'},['2','0','0']),
          ('100','200',{'CPU':'L','NPU':'L'},['0','1','0']),
          ('200','1000',{'CPU':'L','NPU':'L'},['0','0','0'])],
    'AC':[('0','100',{'CPU':'L','NPU':'L'},['2','0','0']),
          ('100','200',{'CPU':'L','NPU':'L'},['0','0','1/4']),
          ('200','1000',{'CPU':'L','NPU':'L'},['0','0','0'])]}


def panel_integral(instance,panels,temperature='20'):
    """Hand sum of baseline-once + local slopes + active q + external power."""
    platform = instance['platform']; out = {}
    for sid,rows in panels.items():
        energy,covered = F(0),F(0)
        for start,end,opps,activity in rows:
            assert F(start) == covered and F(end) > F(start)
            power = F(platform['external_common_power_W'])+sum(map(F,activity))
            for domain_id,domain in platform['domains'].items():
                opp = opps[domain_id]
                power += F(domain['baseline_W'][opp])
                power += len(domain['unit_ids'])*F(
                    domain['local_temperature_slope_W_per_K'][opp])*(
                    F(temperature)-F(platform['reference_temperature_degC']))
            energy += power*(F(end)-F(start))/1000
            covered = F(end)
        assert covered == F(instance['window_ms'])
        out[sid] = energy
    return sum((F(scene['weight'])*out[scene['id']] for scene in instance['scenarios']),F(0))


class AlgebraDeadline(RuntimeError):
    pass


class AlgebraBudget:
    def __init__(self):
        self.seconds,self.now,self.checks = 10,1,0

    @property
    def elapsed(self):
        return self.now

    def check(self):
        self.checks += 1
        if self.now >= self.seconds:
            raise AlgebraDeadline('same absolute algebra cutoff')


class IndependentPartialBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        instance = algebra_instance()
        PRECHECK_RECORDS.update(instance=deepcopy(instance),
            L0=bounds.independent_lower_bound(instance),
            L_a=bounds.independent_lower_bound(instance,{'A':'CPU1'}),
            manual_global_panels=deepcopy(MANUAL_GLOBAL),
            manual_conditional_panels=deepcopy(MANUAL_CPU_CONDITION),
            manual_global_energy_J=str(panel_integral(instance,MANUAL_GLOBAL)),
            manual_conditional_energy_J=str(panel_integral(instance,MANUAL_CPU_CONDITION)),
            manual_temperature_degC='20',manual_RC_solution_claimed=False)

    def test_exact_original_components_charge_each_domain_baseline_once(self):
        result = bounds.independent_lower_bound(algebra_instance())
        self.assertEqual(result['domain_power_floors_W'],{'CPU':'1','NPU':'3/4'})
        self.assertEqual(result['baseline_lower_bound_J'],'9/4')
        self.assertEqual(result['scene_activity_lower_bounds_J'],{'AB':'1/5','AC':'1/8'})
        self.assertEqual(result['activity_lower_bound_J'],'23/160')
        self.assertEqual(result['lower_bound_J'],'383/160')
        self.assertEqual(result['stage_instance_activity_minima_J']['AB'],
                         {'AB.A':'1/10','AB.B':'1/10'})

    def test_only_H_unit_filter_changes_conditional_activity(self):
        case = algebra_instance()
        original = bounds.independent_lower_bound(case)
        cpu = bounds.independent_lower_bound(case,{'A':'CPU1'})
        npu = bounds.independent_lower_bound(case,{'A':'NPU0'})
        self.assertEqual(cpu['lower_bound_J'],'399/160')
        self.assertEqual(cpu['baseline_lower_bound_J'],original['baseline_lower_bound_J'])
        self.assertEqual(npu['lower_bound_J'],original['lower_bound_J'])
        self.assertEqual(cpu['stage_instance_activity_minima_J']['AB']['AB.B'],'1/10')
        self.assertEqual(cpu['stage_instance_activity_minima_J']['AC']['AC.C'],'1/40')

    def test_domain_floor_minimizes_across_all_OPPs_even_with_auto_idle_L(self):
        case = algebra_instance(); cpu = case['platform']['domains']['CPU']
        cpu['baseline_W']['H'] = '3'
        cpu['local_temperature_slope_W_per_K']['H'] = '1/4'
        result = bounds.independent_lower_bound(case)
        # H gives 3 + 2*(1/4)*(20-25)=1/2 W, below L's 1 W.
        # It remains a pointwise relaxation, not a proposed all-H idle trace.
        self.assertEqual(result['domain_power_floors_W']['CPU'],'1/2')
        self.assertEqual(F(result['lower_bound_J']),F(383,160)-F(1,2))

    def test_scope_and_identity_do_not_claim_solver_or_feasibility_evidence(self):
        case = algebra_instance(); both = bounds.get_deployment_bounds(case,{'A':'CPU1'})
        full,conditional = both['L0'],both['L_a']
        self.assertEqual(full['scope'],'original_full_domain')
        self.assertEqual(conditional['scope'],'fixed_shared_deployment')
        self.assertTrue(full['is_global_lower_bound']); self.assertFalse(conditional['is_global_lower_bound'])
        self.assertEqual(full['shared_stage_ids'],['A'])
        self.assertIsNone(full['shared_deployment']); self.assertIsNone(full['shared_deployment_sha256'])
        self.assertEqual(conditional['shared_deployment'],{'A':'CPU1'})
        self.assertEqual(full['input_sha256'],conditional['input_sha256'])
        for result in both.values():
            for key in ('solver_reported','used_as_new_MILP_row',
                        'independently_proven_optimal','independently_proven_infeasible'):
                self.assertIs(result[key],False)
            self.assertNotIn('safe_upper_bound_J',result)

    def test_hand_written_panel_integrals_attain_algebraic_relaxations(self):
        case = algebra_instance()
        self.assertEqual(panel_integral(case,MANUAL_GLOBAL),F(383,160))
        self.assertEqual(panel_integral(case,MANUAL_CPU_CONDITION),F(399,160))
        self.assertEqual(F(bounds.independent_lower_bound(case)['lower_bound_J']),
                         panel_integral(case,MANUAL_GLOBAL))
        self.assertEqual(F(bounds.independent_lower_bound(case,{'A':'CPU1'})['lower_bound_J']),
                         panel_integral(case,MANUAL_CPU_CONDITION))
        # A different OPP and higher allowed temperature raise the hand sum;
        # none of these algebraic paths is used as a SAFE upper bound.
        higher = deepcopy(MANUAL_GLOBAL)
        for rows in higher.values():
            for _,_,opps,_ in rows: opps['CPU'] = 'H'
        self.assertGreater(panel_integral(case,higher,temperature='30'),F(383,160))

    def test_each_request_copy_is_charged_even_for_same_shared_identity(self):
        case = algebra_instance(); scene = case['scenarios'][0]
        stage = deepcopy(scene['stage_instances'][0]); stage.update(id='AB.A.copy',request_id='AB.copy')
        scene['stage_instances'].append(stage)
        scene['requests'].append({'id':'AB.copy','stage_instance_ids':['AB.A.copy'],
                                  'release_ms':'0','deadline_ms':'1000'})
        full = bounds.independent_lower_bound(case)
        fixed = bounds.independent_lower_bound(case,{'A':'CPU1'})
        self.assertEqual(full['shared_stage_ids'],['A'])
        self.assertEqual(F(full['lower_bound_J']),F(383,160)+F(1,40))
        self.assertEqual(F(fixed['lower_bound_J']),F(399,160)+F(1,20))

    def test_zero_weight_scene_remains_validated_but_weighted_once(self):
        case = algebra_instance()
        case['scenarios'][0]['weight'] = '1'; case['scenarios'][1]['weight'] = '0'
        self.assertEqual(bounds.independent_lower_bound(case)['lower_bound_J'],'49/20')
        case['stage_modes']['C'][0]['activity_power_W'] = '-1'
        with self.assertRaises(ValueError): bounds.independent_lower_bound(case)

    def test_genuine_single_scene_has_H_empty_and_explicit_empty_condition(self):
        case = algebra_instance(); case['scenarios'] = case['scenarios'][:1]
        case['scenarios'][0]['weight'] = '1'
        full = bounds.independent_lower_bound(case); fixed = bounds.independent_lower_bound(case,{})
        self.assertEqual(full['shared_stage_ids'],[])
        self.assertEqual(full['lower_bound_J'],fixed['lower_bound_J'])
        self.assertIsNone(full['shared_deployment']); self.assertEqual(fixed['shared_deployment'],{})
        self.assertFalse(fixed['is_global_lower_bound'])

    def test_unused_device_domain_and_its_floor_are_retained(self):
        case = algebra_instance(); platform = case['platform']
        platform['node_order'].append('GPU0')
        platform['units'].append(dict(id='GPU0',domain_id='GPU',power_group_id='GPU',thermal_node_id='GPU0'))
        for domain in platform['domains'].values(): domain['baseline_heat_distribution'].append('0')
        platform['domains']['GPU'] = {'unit_ids':['GPU0'],
            'opps':deepcopy(platform['domains']['CPU']['opps']),
            'baseline_W':{'L':'2','H':'3'},
            'local_temperature_slope_W_per_K':{'L':'0','H':'0'},
            'baseline_heat_distribution':['0','0','0','1']}
        platform['heat_capacity_J_per_K'].append('1')
        for row in platform['conductance_W_per_K']: row.append('0')
        platform['conductance_W_per_K'].append(['0','0','0','1'])
        platform['external_common_heat_distribution'].append('0')
        for scene in case['scenarios']:
            scene['entry']['temperature_degC'].append('25'); scene['entry']['domain_opp']['GPU'] = 'L'
            scene['maximum_temperature_degC'].append('80')
        result = bounds.independent_lower_bound(case)
        self.assertEqual(result['domain_power_floors_W']['GPU'],'2')
        self.assertEqual(F(result['lower_bound_J']),F(383,160)+2)

    def test_redundant_activity_energy_is_never_trusted(self):
        case = algebra_instance(); expected = bounds.independent_lower_bound(case)
        for modes in case['stage_modes'].values():
            for i,mode in enumerate(modes): mode['activity_energy_J'] = ['nonsense','-999','999'][i%3]
        result = bounds.independent_lower_bound(case)
        self.assertEqual(result['lower_bound_J'],expected['lower_bound_J'])
        self.assertNotEqual(result['input_sha256'],expected['input_sha256'])
        case['stage_modes']['A'][2]['activity_power_W'] = '3/5'
        self.assertEqual(F(bounds.independent_lower_bound(case)['lower_bound_J']),F(383,160)+F(1,50))

    def test_control_policies_share_valid_algebra_but_keep_distinct_identities(self):
        legacy = algebra_instance(auto=False); auto = with_auto_low_idle(legacy)
        old,new = bounds.independent_lower_bound(legacy),bounds.independent_lower_bound(auto)
        self.assertEqual(old['lower_bound_J'],new['lower_bound_J'])
        self.assertEqual(old['control_policy'],LEGACY_IDLE_HOLD)
        self.assertEqual(new['control_policy'],AUTO_LOW_IMMEDIATE_V1)
        self.assertNotEqual(old['input_sha256'],new['input_sha256'])

    def test_invalid_a_never_becomes_an_infeasibility_certificate(self):
        for mapping in ({},{'A':'CPU2'},{'A':'CPU1','B':'CPU2'},[]):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValueError):
                    bounds.independent_lower_bound(algebra_instance(),mapping)

    def test_rejects_invalid_signs_weights_locality_and_nonexact_parameters(self):
        mutations = [
            lambda c:c['stage_modes']['A'][0].update(activity_power_W='-1'),
            lambda c:c['stage_modes']['A'][0].update(duration_ms='0'),
            lambda c:c['stage_modes']['A'][0].update(thermal_node_id='CPU2'),
            lambda c:c['stage_modes']['A'][0].update(power_group_id='NPU'),
            lambda c:c['stage_modes']['A'][0].update(frequency_GHz='3'),
            lambda c:c['stage_modes']['A'][0].update(duration_ms=0.5),
            lambda c:c['platform']['domains']['CPU']['local_temperature_slope_W_per_K'].update(H='-1'),
            lambda c:c['platform']['domains']['CPU'].update(baseline_heat_distribution=['1','1','0']),
            lambda c:c['scenarios'][0].update(weight='-1/4'),
            lambda c:c['scenarios'][0].update(weight='1/3'),
            lambda c:c['execution_rules'].update(extra_switch_energy_J='1')]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                case = algebra_instance(); change(case)
                with self.assertRaises(ValueError): bounds.independent_lower_bound(case)

    def test_rejects_invalid_thermal_range_structure_or_entry(self):
        mutations = [
            lambda c:c['platform'].update(power_model_temperature_range_degC=['100','20']),
            lambda c:c['platform'].update(heat_capacity_J_per_K=['0','1','1']),
            lambda c:c['platform'].update(conductance_W_per_K=[['1','1','0'],['0','1','0'],['0','0','1']]),
            lambda c:c['platform'].update(external_common_heat_distribution=['1','0','0']),
            lambda c:c['scenarios'][0]['entry'].update(temperature_degC=['19','25','25']),
            lambda c:c['scenarios'][0]['entry'].update(unfinished_work=['pending'])]
        for index,change in enumerate(mutations):
            with self.subTest(change=index):
                case = algebra_instance(); change(case)
                with self.assertRaises(ValueError): bounds.independent_lower_bound(case)

    def test_budget_is_shared_without_reset_and_records_formation(self):
        case = algebra_instance(); budget = AlgebraBudget()
        with patch.object(bounds,'independent_lower_bound',wraps=bounds.independent_lower_bound) as calls:
            result = bounds.get_deployment_bounds(case,{'A':'CPU1'},budget)
        self.assertEqual(len(calls.call_args_list),2)
        self.assertIs(calls.call_args_list[0].args[2],budget)
        self.assertIs(calls.call_args_list[1].args[2],budget)
        self.assertGreater(budget.checks,2)
        self.assertEqual(result['L0']['formed_at_s'],1)
        self.assertEqual(result['L_a']['formed_at_s'],1)

    def test_expired_budget_rejects_before_any_identity_work(self):
        budget = AlgebraBudget(); budget.now = budget.seconds
        with patch.object(bounds,'canonical_hash',side_effect=AssertionError('late identity')) as identity:
            with self.assertRaises(AlgebraDeadline):
                bounds.independent_lower_bound(algebra_instance(),budget=budget)
        identity.assert_not_called()

    def test_expiry_during_identity_cannot_return_late_bound(self):
        case = algebra_instance(); budget = AlgebraBudget(); canonical = bounds.canonical_hash
        def expire(value):
            budget.now = budget.seconds
            return canonical(value)
        with patch.object(bounds,'canonical_hash',side_effect=expire):
            with self.assertRaises(AlgebraDeadline):
                bounds.independent_lower_bound(case,budget=budget)

    def test_inputs_and_condition_are_not_mutated(self):
        case = algebra_instance(); mapping = {'A':'CPU1'}; original = deepcopy(case)
        result = bounds.independent_lower_bound(case,mapping)
        self.assertEqual(case,original); self.assertEqual(mapping,{'A':'CPU1'})
        result['shared_deployment']['A'] = 'NPU0'
        self.assertEqual(mapping,{'A':'CPU1'})


if __name__ == '__main__':
    unittest.main()
