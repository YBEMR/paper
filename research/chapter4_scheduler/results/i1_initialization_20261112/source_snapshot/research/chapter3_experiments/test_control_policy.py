"""Small control-policy correctness fixtures; no method/native/research run.

Exactly one original input is expanded lazily. Actual continuous propagation
is cached: one hand-built auto-L Stage, its legacy counterpart, and the
existing analytic coupled idle-tail peak. Budget-expiry tests either stop
before propagation or inject an already completed synthetic scene receipt.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mpmath as mp

from control_policy import (AUTO_LOW_IMMEDIATE_V1, LEGACY_IDLE_HOLD,
                            require_legacy_control, resolve_idle_policy,
                            with_auto_low_idle)
from inputs import build_instance, load_config
from run_milp_precheck import select_fixture
from run_thermal_precheck import (contains, distance, ode_oracle, physical,
                                  segment)
from schedules import validate_schedule
import thermal
from thermal import Budget, evaluate_candidate, evaluate_piecewise


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LEGACY_BASELINE_COMMIT = 'e086ef4df538c3336f430a3c22198b47548599c9'
_CONFIG = _BASE = _LEGACY_VALIDATOR = None
PRECHECK_RECORDS = {
    'scope': 'unit correctness fixtures only; no scheduling search, solver or research result',
    'fixture_inputs': {}, 'thermal_calls': [],
}


def base_input():
    global _CONFIG, _BASE
    if _BASE is None:
        _CONFIG = load_config()
        _BASE = build_instance(_CONFIG, 'base__R1')
        PRECHECK_RECORDS['single_original_input_expansion'] = {
            'problem_id': 'base__R1', 'count': 1,
            'config_sha256': canonical_hash(_CONFIG),
            'input_sha256': canonical_hash(_BASE)}
    return _BASE


def fixture_candidate(name, assignments, *, auto=True):
    """Select only explicitly listed tasks/starts; never search schedules."""
    base = base_input()
    sid = base['scenarios'][0]['id']
    starts = {shared: [str(start)] for shared, _, _, start in assignments}
    instance, by_stage = select_fixture(base, 'control_'+name,
        {sid: list(starts)}, starts)
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': by_stage}
    by_shared = {st['shared_stage_id']: st['id']
                 for st in instance['scenarios'][0]['stage_instances']}
    candidate = {'scenes': {sid: [
        {'stage_id': by_shared[shared], 'unit': unit, 'opp': opp,
         'start_ms': str(start)} for shared, unit, opp, start in assignments]}}
    output = with_auto_low_idle(instance) if auto else instance
    PRECHECK_RECORDS['fixture_inputs'][name] = {
        'input': deepcopy(output), 'candidate': deepcopy(candidate),
        'source': 'select_fixture plus explicit hand-written assignments'}
    return output, candidate


def checked_segments(case, candidate):
    checked = validate_schedule(case, candidate)
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise AssertionError(checked)
    sid = case['scenarios'][0]['id']
    return checked['scenes'][sid]['segments']


def domain_at(segments, domain, when):
    when = F(when)
    return next(s['domain_opps'][domain] for s in segments
                if F(s['start_ms']) <= when < F(s['end_ms']))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, default=str).encode('utf-8')).hexdigest()


def head_legacy_validator():
    global _LEGACY_VALIDATOR
    if _LEGACY_VALIDATOR is None:
        # Read-only source comparison. No checkout, index or repository write.
        source = subprocess.check_output(['git', 'show',
            LEGACY_BASELINE_COMMIT+':research/chapter3_experiments/schedules.py'], cwd=REPO,
            encoding='utf-8')
        namespace = {'__name__': '_control_test_legacy_schedules',
                     '__file__': str(HERE/'schedules.py')}
        exec(compile(source, LEGACY_BASELINE_COMMIT+':schedules.py', 'exec'), namespace)
        _LEGACY_VALIDATOR = namespace['validate_schedule']
        PRECHECK_RECORDS['legacy_HEAD_schedule_source_sha256'] = hashlib.sha256(
            source.encode('utf-8')).hexdigest()
        PRECHECK_RECORDS['legacy_reference_commit'] = LEGACY_BASELINE_COMMIT
    return _LEGACY_VALIDATOR


def expected_one_stage_segments(instance, candidate):
    """Independent, explicit power table for A.pre/M on CPU1 at 0 ms.

    d=34/3 ms, activity=16/27 W. CPU group baseline is split once between
    CPU1/2; the table is not obtained from the schedule reconstruction.
    """
    nodes = ['CPU1', 'CPU2', 'GPU0', 'NPU0']
    sid = instance['scenarios'][0]['id']
    stage = candidate['scenes'][sid][0]['stage_id']
    table = [
        ('0', '34/3', ['9/20', '9/20', '2/5', '1/4'],
         ['16/27', '0', '0', '0'], ['3/1000', '3/1000', '1/250', '3/1000'],
         {'CPU': 'M', 'GPU': 'L', 'NPU': 'L'}, [stage]),
        ('34/3', '400', ['3/10', '3/10', '2/5', '1/4'],
         ['0', '0', '0', '0'], ['1/500', '1/500', '1/250', '3/1000'],
         {'CPU': 'L', 'GPU': 'L', 'NPU': 'L'}, []),
    ]
    rows = []
    for start, end, baseline, activity, slopes, opps, active in table:
        rows.append({'start_ms': start, 'end_ms': end,
            'duration_ms': str(F(end)-F(start)), 'domain_opps': opps,
            'active_stage_ids': active,
            'baseline_by_power_group_W': {'CPU': '9/10' if opps['CPU']=='M' else '3/5',
                                          'GPU': '2/5', 'NPU': '1/4'},
            'baseline_by_node_W': dict(zip(nodes, baseline)),
            'activity_by_node_W': dict(zip(nodes, activity)),
            'local_leakage_slope_W_per_K': dict(zip(nodes, slopes)),
            'node_power_constant_at_reference_W': {n: str(F(b)+F(q))
                for n,b,q in zip(nodes, baseline, activity)},
            'reference_temperature_degC': '25',
            'external_common_power_W': '3/10', 'external_common_injected_heat_W': '0'})
    return rows


def expire_at(target):
    def hook(event, budget):
        if event == target:
            budget.seconds = -1
    return hook


class ControlPolicyRulesAndTrajectories(unittest.TestCase):
    def test_legacy_default_is_explicitly_preserved(self):
        self.assertEqual(resolve_idle_policy(base_input()), LEGACY_IDLE_HOLD)
        self.assertNotIn('idle_policy', base_input()['execution_rules'])

    def test_adapter_only_changes_rules_and_is_deepcopy_idempotent(self):
        original = deepcopy(base_input())
        converted = with_auto_low_idle(original)
        self.assertEqual(original, base_input())
        self.assertEqual({k:v for k,v in converted.items() if k!='execution_rules'},
                         {k:v for k,v in original.items() if k!='execution_rules'})
        expected = deepcopy(original['execution_rules'])
        expected.update(idle_holds_last_opp=False, idle_policy=AUTO_LOW_IMMEDIATE_V1,
                        idle_delay_ms='0')
        self.assertEqual(converted['execution_rules'], expected)
        again = with_auto_low_idle(converted)
        self.assertEqual(again, converted)
        again['platform']['domains']['CPU']['baseline_W']['L'] = '999'
        self.assertNotEqual(again['platform'], converted['platform'])
        self.assertEqual(resolve_idle_policy(converted), AUTO_LOW_IMMEDIATE_V1)

    def test_unversioned_unknown_and_contradictory_policy_rejected(self):
        for updates in ({'idle_holds_last_opp': False},
                        {'idle_holds_last_opp': False, 'idle_policy': 'unknown', 'idle_delay_ms':'0'},
                        {'idle_policy': AUTO_LOW_IMMEDIATE_V1, 'idle_delay_ms':'0'}):
            with self.subTest(updates=updates):
                case = deepcopy(base_input()); case['execution_rules'].update(updates)
                with self.assertRaises(ValueError): resolve_idle_policy(case)

    def test_nonzero_or_inexact_delay_and_overheads_rejected(self):
        for key,value in [('idle_delay_ms','1'), ('idle_delay_ms',0.0),
                          ('idle_delay_ms',False), ('extra_switch_time_ms','1/10'),
                          ('extra_switch_energy_J','1/1000'), ('preemption',True)]:
            with self.subTest(key=key,value=value):
                case = with_auto_low_idle(base_input()); case['execution_rules'][key] = value
                with self.assertRaises(ValueError): resolve_idle_policy(case)

    def test_low_opp_must_exist_be_legal_and_unique_minimum(self):
        for change in ('missing','tied','higher','zero_voltage','negative_baseline','negative_slope'):
            with self.subTest(change=change):
                case = with_auto_low_idle(base_input()); d = case['platform']['domains']['CPU']
                if change=='missing': del d['opps']['L']
                elif change=='tied': d['opps']['L']['frequency_GHz'] = d['opps']['M']['frequency_GHz']
                elif change=='higher': d['opps']['L']['frequency_GHz'] = '2'
                elif change=='zero_voltage': d['opps']['L']['voltage_V'] = '0'
                elif change=='negative_baseline': d['baseline_W']['L'] = '-1'
                else: d['local_temperature_slope_W_per_K']['L'] = '-1'
                with self.assertRaises(ValueError): resolve_idle_policy(case)

    def test_legacy_complete_checker_matches_unmodified_HEAD_namespace(self):
        arrangements = [[('A.pre','CPU1','M','0')],
            [('A.pre','CPU1','H','0'),('B.pre','CPU2','H','5'),('A.post','CPU1','H','10')],
            [('A.main','NPU0','H','0'),('B.main','NPU0','M','35')]]
        old = head_legacy_validator()
        for index, assignments in enumerate(arrangements):
            with self.subTest(index=index):
                case, candidate = fixture_candidate('legacy_'+str(index), assignments, auto=False)
                self.assertEqual(validate_schedule(case,candidate), old(case,candidate))

    def test_fractional_end_drops_immediately_and_covers_whole_window(self):
        case,candidate = fixture_candidate('fractional', [('A.pre','CPU1','M','0')])
        segments = checked_segments(case,candidate)
        self.assertEqual(segments, expected_one_stage_segments(case,candidate))
        self.assertEqual([(F(s['start_ms']),F(s['end_ms'])) for s in segments],
                         [(F(0),F(34,3)),(F(34,3),F(400))])
        self.assertEqual(domain_at(segments,'CPU',F(34,3)), 'L')

    def test_t0_high_entry_and_never_working_domains_take_low(self):
        case,candidate = fixture_candidate('entry', [('A.pre','CPU1','M','5')])
        case['scenarios'][0]['entry']['domain_opp'] = {'CPU':'H','GPU':'H','NPU':'H'}
        segments = checked_segments(case,candidate)
        self.assertEqual(segments[0]['domain_opps'], {'CPU':'L','GPU':'L','NPU':'L'})
        self.assertEqual(domain_at(segments,'CPU',5), 'M')
        self.assertTrue(all(s['domain_opps']['GPU']=='L' and s['domain_opps']['NPU']=='L'
                            for s in segments))

    def test_cpu_busy_peer_keeps_high_and_accepts_same_high_new_work(self):
        case,candidate = fixture_candidate('parallel', [('A.pre','CPU1','H','0'),
            ('B.pre','CPU2','H','5'),('A.post','CPU1','H','10')])
        segments = checked_segments(case,candidate)
        for t in (0,5,10,15,F(199,10)):
            self.assertEqual(domain_at(segments,'CPU',t),'H')
        self.assertEqual(domain_at(segments,'CPU',20),'L')

    def test_busy_cpu_rejects_different_opp_on_new_peer_work(self):
        case,candidate = fixture_candidate('conflict', [('A.pre','CPU1','H','0'),
            ('B.pre','CPU2','H','5'),('A.post','CPU1','M','10')])
        result = validate_schedule(case,candidate)
        self.assertEqual(result['state'],'INVALID_SCHEDULE')
        self.assertEqual(result['reason'],'FREQUENCY_DOMAIN_CONFLICT')

    def test_same_time_last_end_and_new_middle_has_no_zero_low_segment(self):
        case,candidate = fixture_candidate('tie', [('A.pre','CPU1','H','0'),
                                                  ('A.post','CPU2','M','10')])
        segments = checked_segments(case,candidate)
        self.assertEqual(domain_at(segments,'CPU',10),'M')
        self.assertTrue(all(F(s['duration_ms'])>0 for s in segments))
        self.assertEqual([s['domain_opps']['CPU'] for s in segments],['H','M','L'])

    def test_npu_queue_can_switch_on_exact_end_and_start_boundary(self):
        case,candidate = fixture_candidate('queue', [('A.main','NPU0','H','0'),
                                                    ('B.main','NPU0','M','30')])
        segments = checked_segments(case,candidate)
        self.assertEqual(domain_at(segments,'NPU',0),'H')
        self.assertEqual(domain_at(segments,'NPU',30),'M')
        self.assertEqual(domain_at(segments,'NPU',72),'L')

    def test_npu_queue_gap_is_low_before_later_middle_start(self):
        case,candidate = fixture_candidate('queue_gap', [('A.main','NPU0','H','0'),
                                                        ('B.main','NPU0','M','35')])
        segments = checked_segments(case,candidate)
        self.assertEqual(domain_at(segments,'NPU',30),'L')
        self.assertEqual(domain_at(segments,'NPU',35),'M')
        self.assertEqual(domain_at(segments,'NPU',77),'L')

    def test_external_power_changes_metering_not_heat_reconstruction(self):
        case,candidate = fixture_candidate('external', [('A.pre','CPU1','M','0')])
        before = checked_segments(case,candidate)
        changed = deepcopy(case); changed['platform']['external_common_power_W']='7'
        after = checked_segments(changed,candidate)
        self.assertEqual(changed['platform']['external_common_heat_distribution'],['0']*4)
        for left,right in zip(before,after):
            self.assertEqual(left['external_common_injected_heat_W'],'0')
            self.assertEqual(right['external_common_power_W'],'7')
            self.assertEqual({k:v for k,v in left.items() if k!='external_common_power_W'},
                             {k:v for k,v in right.items() if k!='external_common_power_W'})


class ControlPolicyContinuousAndBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auto,cls.candidate = fixture_candidate('continuous', [('A.pre','CPU1','M','0')])
        cls.legacy = deepcopy(cls.auto)
        cls.legacy['execution_rules'] = deepcopy(base_input()['execution_rules'])
        cls.expected_segments = expected_one_stage_segments(cls.auto,cls.candidate)
        cls.auto_result = evaluate_candidate(cls.auto,cls.candidate, budget=Budget())
        cls.legacy_result = evaluate_candidate(cls.legacy,cls.candidate, budget=Budget())
        sid = cls.auto['scenarios'][0]['id']; cls.sid = sid
        cls.oracle = ode_oracle(cls.auto['platform'],
            cls.auto['scenarios'][0]['entry']['temperature_degC'], cls.expected_segments)
        cls.coupled = physical(['1','1'], [['2','-1'],['-1','2']])
        cls.idle = [segment(cls.coupled,'0','1000',['0','0'],['0','0'],['0','0'])]
        cls.peak_result = evaluate_piecewise(cls.coupled,['25','28'],['25.5','29'],
            cls.idle,'1000',budget=Budget(),scene_id='control_analytic_idle_peak')
        PRECHECK_RECORDS['continuous_one_stage'] = {
            'auto_input': deepcopy(cls.auto), 'legacy_input': deepcopy(cls.legacy),
            'candidate': deepcopy(cls.candidate),
            'independently_handwritten_expected_segments': deepcopy(cls.expected_segments),
            'auto_result': deepcopy(cls.auto_result), 'legacy_result': deepcopy(cls.legacy_result),
            'independent_ODE_oracle': deepcopy(cls.oracle),
            'oracle_role': 'floating cross-check, not an interval error certificate',
            'temperature_comparison_allowance_K': 2e-8,
            'energy_comparison_allowance_J': 2e-10}
        PRECHECK_RECORDS['analytic_idle_peak'] = {
            'platform': deepcopy(cls.coupled), 'initial_temperature_degC': ['25','28'],
            'maximum_temperature_degC': ['25.5','29'], 'window_ms': '1000',
            'segments': deepcopy(cls.idle), 'result': deepcopy(cls.peak_result),
            'analytic_peak_time_s': str(mp.log(3)/2),
            'analytic_peak_temperature_degC': str(mp.mpf(25)+1/mp.sqrt(3)),
            'analytic_final_temperature_N0_degC': str(
                25+mp.mpf('1.5')*(mp.exp(-1)-mp.exp(-3)))}
        PRECHECK_RECORDS['thermal_calls'].extend([
            {'fixture':'continuous_one_stage/auto','real_propagation':True},
            {'fixture':'continuous_one_stage/legacy','real_propagation':True},
            {'fixture':'analytic_idle_peak','real_propagation':True}])

    def test_auto_final_temperature_and_continuous_peaks_match_independent_ode(self):
        self.assertEqual(self.auto_result['state'],'SAFE')
        measured = self.auto_result['scenes'][self.sid]
        self.assertEqual(F(measured['covered_until_s']),F(2,5))
        for node in self.auto['platform']['node_order']:
            self.assertLessEqual(distance(measured['final_temperature_degC'][node],
                self.oracle['final_temperature_degC'][node]),2e-8)
            self.assertLessEqual(distance(measured['peaks_degC'][node],
                self.oracle['peaks_degC'][node]),2e-8)

    def test_auto_correction_and_complete_energy_match_independent_ode(self):
        measured = self.auto_result['scenes'][self.sid]
        self.assertLessEqual(distance(measured['energy_components_J']['temperature_correction'],
            self.oracle['energy_components_J']['temperature_correction']),2e-10)
        self.assertLessEqual(distance(measured['energy_J'],
            self.oracle['energy_direct_integral_J']),2e-10)
        self.assertLessEqual(abs(self.oracle['energy_direct_integral_J']-
            self.oracle['energy_component_sum_J']),2e-10)

    def test_exact_constant_components_and_external_heat_accounting(self):
        measured = self.auto_result['scenes'][self.sid]
        exact = {'baseline':F(2517,5000), 'activity':F(68,10125),
                 'external_common':F(3,25)}
        for name,value in exact.items():
            lo,hi = map(F,measured['energy_components_J'][name])
            self.assertLessEqual(lo,value); self.assertLessEqual(value,hi)
        heat_lo = sum(F(v[0]) for v in measured['node_injected_energy_J'].values())
        heat_hi = sum(F(v[1]) for v in measured['node_injected_energy_J'].values())
        total_lo,total_hi = map(F,measured['energy_J'])
        self.assertLessEqual(max(heat_lo,total_lo-F(3,25)), min(heat_hi,total_hi-F(3,25)))

    def test_auto_receipt_binds_full_input_and_candidate_legacy_gains_no_fields(self):
        self.assertEqual(self.auto_result['control_policy'],
            {'idle_policy':AUTO_LOW_IMMEDIATE_V1,'idle_delay_ms':'0'})
        self.assertEqual(self.auto_result['evidence_identity'],
            {'input_sha256':canonical_hash(self.auto),
             'candidate_sha256':canonical_hash(self.candidate)})
        self.assertNotEqual(canonical_hash(self.auto),canonical_hash(self.legacy))
        self.assertNotIn('control_policy',self.legacy_result)
        self.assertNotIn('evidence_identity',self.legacy_result)

    def test_legacy_same_fixture_holds_middle_tail_and_keeps_full_metering(self):
        self.assertEqual(self.legacy_result['state'],'SAFE')
        checked = validate_schedule(self.legacy,self.candidate)
        self.assertEqual(checked,head_legacy_validator()(self.legacy,self.candidate))
        segments = checked['scenes'][self.sid]['segments']
        self.assertTrue(all(s['domain_opps']['CPU']=='M' for s in segments))
        baseline = self.legacy_result['scenes'][self.sid]['energy_components_J']['baseline']
        self.assertLessEqual(F(baseline[0]),F(31,50))
        self.assertLessEqual(F(31,50),F(baseline[1]))

    def test_existing_coupled_idle_tail_can_have_strict_interior_peak(self):
        result = self.peak_result
        self.assertEqual(result['state'],'THERMAL_VIOLATION')
        self.assertTrue(contains(result['peaks_degC']['N0'],mp.mpf(25)+1/mp.sqrt(3)))
        witness = result['peak_witnesses']['N0']
        self.assertTrue(0<F(witness['time_s'])<1)
        self.assertGreater(F(witness['temperature_degC'][0]),F('25.5'))
        self.assertLess(25+mp.mpf('1.5')*(mp.exp(-1)-mp.exp(-3)),mp.mpf('25.5'))

    def test_expiry_before_first_panel_has_no_prefix_objective(self):
        budget = Budget(hook=expire_at('before_panel'))
        with patch.object(thermal,'Panel',side_effect=AssertionError('No propagation after expiry')):
            result = evaluate_candidate(self.auto,self.candidate,budget=budget)
        PRECHECK_RECORDS['budget_before_panel'] = {
            'input': deepcopy(self.auto), 'candidate': deepcopy(self.candidate),
            'result': deepcopy(result), 'event': 'before_panel'}
        PRECHECK_RECORDS['thermal_calls'].append(
            {'fixture':'budget_before_panel','real_propagation':False,'early_expiry':True})
        self.assertEqual(result['state'],'UNRESOLVED')
        self.assertIsNone(result['weighted_energy_J']); self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(result['scenes'][self.sid]['complete'])

    def test_expiry_after_violation_commit_retains_strict_evidence_without_U(self):
        case = deepcopy(self.auto)
        case['scenarios'][0]['maximum_temperature_degC'][0] = '49'
        budget = Budget(hook=expire_at('after_violation_commit'))
        with patch.object(thermal,'Panel',side_effect=AssertionError('Entry witness needs no propagation')):
            result = evaluate_candidate(case,self.candidate,budget=budget)
        PRECHECK_RECORDS['budget_after_violation_commit'] = {
            'input': deepcopy(case), 'candidate': deepcopy(self.candidate),
            'result': deepcopy(result), 'event': 'after_violation_commit'}
        PRECHECK_RECORDS['thermal_calls'].append(
            {'fixture':'budget_after_violation_commit','real_propagation':False,'early_expiry':True})
        self.assertEqual(result['state'],'THERMAL_VIOLATION')
        self.assertTrue(result['violations'])
        self.assertGreater(F(result['violations'][0]['temperature_degC'][0]),F('49'))
        self.assertIsNone(result['weighted_energy_J']); self.assertIsNone(result['safe_upper_bound_J'])

    def test_expiry_before_aggregate_keeps_scene_SAFE_but_never_global_U(self):
        # Synthetic replay only: tests the aggregation deadline, not a new
        # physical evaluation or cross-Budget receipt reuse API.
        scene = deepcopy(self.auto_result['scenes'][self.sid])
        budget = Budget(hook=expire_at('before_aggregate_commit'))
        with patch.object(thermal,'evaluate_piecewise',return_value=scene) as evaluate:
            result = evaluate_candidate(self.auto,self.candidate,budget=budget)
        PRECHECK_RECORDS['budget_before_aggregate_commit'] = {
            'input': deepcopy(self.auto), 'candidate': deepcopy(self.candidate),
            'result': deepcopy(result), 'event': 'before_aggregate_commit',
            'injected_scene_receipt': deepcopy(scene),
            'scope': 'mocked scene to isolate aggregation deadline; not new physical evidence'}
        PRECHECK_RECORDS['thermal_calls'].append(
            {'fixture':'budget_before_aggregate_commit','real_propagation':False,'mocked_scene':True})
        evaluate.assert_called_once()
        self.assertEqual(result['state'],'UNRESOLVED')
        self.assertEqual(result['scenes'][self.sid]['state'],'SAFE')
        self.assertIsNone(result['weighted_energy_J']); self.assertIsNone(result['safe_upper_bound_J'])


class ControlPolicyLegacyMethodGuards(unittest.TestCase):
    def setUp(self):
        self.auto,self.candidate = fixture_candidate('guard', [('A.pre','CPU1','M','0')])

    def test_helper_allows_legacy_low_level_mocks_but_rejects_auto(self):
        require_legacy_control(base_input(),'test_legacy')
        require_legacy_control({},'test_existing_low_level_mock')
        with self.assertRaises(ValueError): require_legacy_control(self.auto,'test_auto')

    def test_MILP_rejects_mismatched_policy_before_construction(self):
        import milp
        with patch.object(milp,'Model',side_effect=AssertionError('Model must not be built')) as model:
            with self.assertRaises(ValueError): milp.build_model(self.auto,_CONFIG)
            legacy = deepcopy(self.auto)
            legacy['execution_rules'] = deepcopy(base_input()['execution_rules'])
            auto_config = with_auto_low_idle(_CONFIG)
            with self.assertRaises(ValueError): milp.build_model(legacy,auto_config)
            model.assert_not_called()

    def test_HEFT_SA_and_legacy_LB_reject_before_assessment(self):
        from heft_method import run_heft
        from sa_method import run_sa
        from q1_case import independent_lower_bound
        assess = Mock(side_effect=AssertionError('Method must not assess auto-L'))
        with self.assertRaises(ValueError): run_heft(self.auto,_CONFIG,Budget(),assess)
        with self.assertRaises(ValueError): run_sa(self.auto,_CONFIG,Budget(),assess,seed=101)
        with self.assertRaises(ValueError): independent_lower_bound(self.auto)
        assess.assert_not_called()

    def test_legacy_scene_adapter_rejects_auto_policy(self):
        from scene_adapter import validate_fixed_deployment
        with self.assertRaises(ValueError): validate_fixed_deployment(self.auto,{'A.pre':'CPU1'})


if __name__ == '__main__':
    unittest.main()
