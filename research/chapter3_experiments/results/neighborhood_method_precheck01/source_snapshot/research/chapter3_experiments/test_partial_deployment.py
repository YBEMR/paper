"""Partial shared-deployment interfaces, using mock physical receipts only.

One original input is expanded for task/identity fixtures. No model, solver,
thermal integration, method search or research result is produced here.
"""
from copy import deepcopy
from fractions import Fraction as F
from math import prod
import unittest
from unittest.mock import patch

from control_policy import with_auto_low_idle
from inputs import build_instance, load_config
from run_milp_precheck import select_fixture
from schedules import validate_schedule
from thermal import Budget
import scene_adapter as adapter


PRECHECK_RECORDS = {'scope': 'mocked scene-receipt interface checks only; no thermal propagation'}
_BASE = None


def base_input():
    global _BASE
    if _BASE is None:
        _BASE = build_instance(load_config(), 'base__R1')
    return _BASE


def small_case(*, auto=True, weights=None):
    base = base_input(); ab,ac = [s['id'] for s in base['scenarios']]
    case,starts = select_fixture(base,'partial_deployment',
        {ab:['A.pre','B.pre'],ac:['A.pre','C.pre']},
        {'A.pre':[0,20],'B.pre':[0,15,20],'C.pre':[0,15,20]})
    case['start_domain'] = {'version':1,'kind':'explicit_grid_subset',
                            'by_scene_stage_ms':starts}
    if auto: case = with_auto_low_idle(case)
    if weights is not None:
        for scene,weight in zip(case['scenarios'],weights): scene['weight'] = str(weight)
    candidates = {}
    for scene in case['scenarios']:
        sid = scene['id']; rows = []
        for stage in scene['stage_instances']:
            shared = stage['shared_stage_id']
            unit,start = ('CPU1','0') if shared=='A.pre' else (
                ('CPU2','0') if shared=='B.pre' else ('CPU1','15'))
            rows.append({'stage_id':stage['id'],'unit':unit,'opp':'H','start_ms':start})
        candidates[sid] = {'scenes':{sid:rows}}
    return case,{'A.pre':'CPU1'},candidates


def fake_physical(platform, entry, limits, segments, window, accuracy, budget, *, scene_id):
    """Explicitly fabricated interface energy; never physical evidence."""
    value = '1' if scene_id.startswith('AB') else '3'
    return {'scene_id':scene_id,'state':'SAFE','reason':'MOCK_COMPLETE_SCENE',
        'complete':True,'rankable_energy':True,'violations':[],
        'energy_J':[value,value],'energy_accuracy_met':True,
        'covered_until_s':str(F(window)/1000),
        'completed_at_elapsed_s':budget.elapsed}


def matching_receipts(case, mapping, candidates, budget, accuracy=None):
    with patch.object(adapter,'evaluate_piecewise',side_effect=fake_physical):
        return {sid:adapter.evaluate_partial_scene(case,sid,mapping,candidate,accuracy,budget)
                for sid,candidate in candidates.items()}


def assert_no_U(test, result):
    test.assertNotEqual(result['state'],'SAFE')
    test.assertFalse(result['rankable_energy'])
    test.assertIsNone(result['safe_upper_bound_J'])
    test.assertIsNone(result['weighted_energy_J'])
    test.assertFalse(result['independently_proven_infeasible'])


class PartialDeploymentInterfaces(unittest.TestCase):
    def test_H_counts_distinct_scenes_and_current_support_product_is_sixteen(self):
        base = base_input()
        shared = adapter.shared_deployment_ids(base)
        self.assertEqual(shared,['A.main','A.post','A.pre'])
        self.assertEqual(prod(len({m['unit_id'] for m in base['stage_modes'][s]})
                              for s in shared),16)

    def test_H_empty_accepts_empty_mapping_for_one_scene(self):
        case,_,_ = small_case()
        case['scenarios'] = case['scenarios'][:1]
        sid = case['scenarios'][0]['id']
        case['start_domain']['by_scene_stage_ms'] = {sid:case['start_domain']['by_scene_stage_ms'][sid]}
        self.assertEqual(adapter.shared_deployment_ids(case),[])
        self.assertEqual(adapter.validate_shared_deployment(case,{}),{})

    def test_a_must_cover_exactly_H_and_supported_specific_units(self):
        case,_,_ = small_case()
        for mapping in ({},{'A.pre':'CPU1','B.pre':'CPU2'},
                        {'A.pre':'NPU0'},{'A.pre':'CPU999'},{'A.pre':1}):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValueError): adapter.validate_shared_deployment(case,mapping)
        self.assertEqual(adapter.validate_shared_deployment(case,{'A.pre':'CPU2'}),{'A.pre':'CPU2'})

    def test_shared_condition_validation_does_not_mutate_original(self):
        case,mapping,_ = small_case(); before = deepcopy(case)
        normalized = adapter.validate_shared_deployment(case,mapping)
        normalized['A.pre'] = 'CPU2'
        self.assertEqual(case,before); self.assertEqual(mapping,{'A.pre':'CPU1'})

    def test_local_mappings_remain_free_under_same_a(self):
        case,mapping,candidates = small_case(); budget = Budget()
        ab = case['scenarios'][0]['id']
        alternate = deepcopy(candidates[ab])
        local = next(r for r in alternate['scenes'][ab] if 'B.pre' in r['stage_id'])
        local.update(unit='CPU1',start_ms='15')
        with patch.object(adapter,'evaluate_piecewise',side_effect=fake_physical):
            first = adapter.evaluate_partial_scene(case,ab,mapping,candidates[ab],budget=budget)
            second = adapter.evaluate_partial_scene(case,ab,mapping,alternate,budget=budget)
        self.assertEqual(first['state'],'SAFE'); self.assertEqual(second['state'],'SAFE')
        self.assertEqual(first['shared_deployment'],second['shared_deployment'])
        self.assertNotEqual(first['local_deployment'],second['local_deployment'])
        self.assertNotEqual(first['identity']['local_deployment_sha256'],
                            second['identity']['local_deployment_sha256'])

    def test_outer_a_mismatch_never_invokes_physical_evaluation(self):
        case,_,candidates = small_case(); sid = case['scenarios'][0]['id']
        with patch.object(adapter,'evaluate_piecewise',side_effect=AssertionError('No physical call')) as physical:
            result = adapter.evaluate_partial_scene(case,sid,{'A.pre':'CPU2'},candidates[sid])
        physical.assert_not_called()
        self.assertEqual(result['state'],'INVALID_SCHEDULE')
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(result['independently_proven_infeasible'])

    def test_same_scene_request_copies_do_not_enter_H_but_mapping_must_agree(self):
        base = base_input(); sid = base['scenarios'][0]['id']
        case,starts = select_fixture(base,'partial_copies',{sid:['A.pre']},{'A.pre':[0,20]})
        scene = case['scenarios'][0]; first = scene['stage_instances'][0]
        extra = deepcopy(first); extra['id'] += '_copy'; extra['request_id'] += '_copy'
        req = deepcopy(scene['requests'][0]); req['id'] = extra['request_id']
        req['stage_instance_ids'] = [extra['id']]
        scene['stage_instances'].append(extra); scene['requests'].append(req)
        starts[sid][extra['id']] = ['0','20']
        case['start_domain'] = {'version':1,'kind':'explicit_grid_subset','by_scene_stage_ms':starts}
        case = with_auto_low_idle(case)
        self.assertEqual(adapter.shared_deployment_ids(case),[])
        self.assertEqual(adapter.validate_shared_deployment(case,{}),{})
        good = {'scenes':{sid:[{'stage_id':st['id'],'unit':'CPU1','opp':'H','start_ms':str(t)}
                                 for st,t in [(first,0),(extra,20)]]}}
        bad = deepcopy(good); bad['scenes'][sid][1]['unit'] = 'CPU2'
        with patch.object(adapter,'evaluate_piecewise',side_effect=fake_physical) as physical:
            accepted = adapter.evaluate_partial_scene(case,sid,{},good)
            rejected = adapter.evaluate_partial_scene(case,sid,{},bad)
        self.assertEqual(accepted['state'],'SAFE')
        self.assertEqual(rejected['state'],'INVALID_SCHEDULE')
        self.assertEqual(physical.call_count,1)

    def test_identity_binds_full_input_rules_local_solution_sources_and_budget(self):
        case,mapping,candidates = small_case(); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget)
        for receipt in receipts.values():
            identity = receipt['identity']
            for field in ('full_input_sha256','shared_deployment_sha256','local_deployment_sha256',
                          'candidate_sha256','execution_rules_sha256','accuracy_sha256','budget'):
                self.assertIn(field,identity)
            self.assertIn('control_policy.py',identity['source_sha256'])
            self.assertEqual(receipt['shared_stage_ids'],['A.pre'])
            self.assertIsNone(receipt['certified_lower_bound_J'])

    def test_all_scene_SAFE_aggregates_original_weights_once_and_rechecks_full_input(self):
        case,mapping,candidates = small_case(weights=['1/4','3/4']); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget)
        with patch.object(adapter,'validate_schedule',wraps=validate_schedule) as validate:
            result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
        self.assertEqual(result['state'],'SAFE'); self.assertEqual(list(map(F,result['weighted_energy_J'])),[F(5,2)]*2)
        validate.assert_called_once()
        self.assertEqual(set(validate.call_args.args[1]['scenes']),set(candidates))
        self.assertEqual(result['merged_deployment'],{'A.pre':'CPU1','B.pre':'CPU2','C.pre':'CPU1'})
        self.assertFalse(result['independently_proven_optimal'])
        PRECHECK_RECORDS['mock_weighted_merge'] = {'input':case,'shared_deployment':mapping,
            'candidates':candidates,'receipts':receipts,'aggregation':result}

    def test_new_partial_protocol_supports_both_declared_control_policies(self):
        for auto in (False,True):
            with self.subTest(auto=auto):
                case,mapping,candidates = small_case(auto=auto); budget = Budget()
                receipts = matching_receipts(case,mapping,candidates,budget)
                result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
                self.assertEqual(result['state'],'SAFE')
                self.assertEqual(result['protocol'],adapter.PARTIAL_PROTOCOL)

    def test_missing_zero_weight_scene_still_blocks_global_U(self):
        case,mapping,candidates = small_case(weights=['1','0']); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget)
        receipts.pop(case['scenarios'][1]['id'])
        result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
        assert_no_U(self,result)

    def test_receipts_cannot_cross_budget_objects(self):
        case,mapping,candidates = small_case(); first = Budget()
        receipts = matching_receipts(case,mapping,candidates,first)
        result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=Budget())
        assert_no_U(self,result); self.assertTrue(result['receipt_errors'])

    def test_changed_candidate_outer_condition_policy_or_precision_rejects_cache_mix(self):
        case,mapping,candidates = small_case(); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget)
        for kind in ('candidate','condition','policy','precision'):
            with self.subTest(kind=kind):
                original,mapping2,candidates2 = deepcopy(case),deepcopy(mapping),deepcopy(candidates)
                accuracy = None
                if kind=='candidate':
                    sid = next(iter(candidates2)); candidates2[sid]['scenes'][sid][0]['start_ms']='20'
                elif kind=='condition': mapping2['A.pre']='CPU2'
                elif kind=='policy': original['execution_rules']=deepcopy(base_input()['execution_rules'])
                else: accuracy={'energy_absolute_error_J':'1/10000000'}
                result = adapter.aggregate_partial_scene_receipts(original,mapping2,receipts,candidates2,accuracy,budget)
                assert_no_U(self,result)

    def test_source_or_payload_tampering_is_not_a_matching_receipt(self):
        case,mapping,candidates = small_case(); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget)
        with patch.object(adapter,'_source_identity',return_value={'changed':'source'}):
            result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
        assert_no_U(self,result)
        modified = deepcopy(receipts); modified[next(iter(modified))]['energy_J']=['0','0']
        result = adapter.aggregate_partial_scene_receipts(case,mapping,modified,candidates,budget=budget)
        assert_no_U(self,result)

    def test_unresolved_scene_is_not_exclusion_or_global_U(self):
        case,mapping,candidates = small_case(); budget = Budget()
        def unresolved(*args,**kwargs):
            return {'state':'UNRESOLVED','reason':'MOCK_TIMEOUT','complete':False,'violations':[]}
        sid = next(iter(candidates))
        with patch.object(adapter,'evaluate_piecewise',side_effect=unresolved):
            receipt = adapter.evaluate_partial_scene(case,sid,mapping,candidates[sid],budget=budget)
        result = adapter.aggregate_partial_scene_receipts(case,mapping,{sid:receipt},candidates,budget=budget)
        assert_no_U(self,result)
        self.assertEqual(receipt['deployment_feasibility'],'NOT_DECIDED')

    def test_expired_scene_SAFE_receipts_remain_visible_but_add_no_global_U(self):
        case,mapping,candidates = small_case(); budget = Budget()
        receipts = matching_receipts(case,mapping,candidates,budget); budget.seconds=-1
        result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
        assert_no_U(self,result); self.assertEqual(set(result['scenes']),set(candidates))

    def test_committed_violation_survives_outer_expiry_and_missing_other_scene(self):
        case,mapping,candidates = small_case(); budget = Budget(); sid = next(iter(candidates))
        def violation(*args,**kwargs):
            witness = {'scene_id':sid,'node':'CPU1','time_s':'0',
                'temperature_degC':['81','81'],'limit_degC':'80',
                'formed_at_elapsed_s':budget.elapsed}
            budget.seconds=-1
            return {'state':'THERMAL_VIOLATION','reason':'MOCK_POINT_WITNESS',
                    'complete':False,'violations':[witness]}
        with patch.object(adapter,'evaluate_piecewise',side_effect=violation):
            receipt = adapter.evaluate_partial_scene(case,sid,mapping,candidates[sid],budget=budget)
        result = adapter.aggregate_partial_scene_receipts(case,mapping,{sid:receipt},
            {sid:candidates[sid]},budget=budget)
        self.assertEqual(result['state'],'THERMAL_VIOLATION'); self.assertTrue(result['violations'])
        self.assertIsNone(result['safe_upper_bound_J']); self.assertFalse(result['independently_proven_infeasible'])

    def test_late_physical_SAFE_is_not_new_local_or_global_U(self):
        case,mapping,candidates = small_case(); budget = Budget(); sid = next(iter(candidates))
        def late(*args,**kwargs):
            result = fake_physical(*args,**kwargs); result['completed_at_elapsed_s']=budget.seconds+1
            return result
        with patch.object(adapter,'evaluate_piecewise',side_effect=late):
            receipt = adapter.evaluate_partial_scene(case,sid,mapping,candidates[sid],budget=budget)
        self.assertEqual(receipt['state'],'UNRESOLVED'); self.assertIsNone(receipt['safe_upper_bound_J'])

    def test_expiry_at_aggregate_commit_retains_scenes_but_no_new_U(self):
        case,mapping,candidates = small_case()
        def hook(event,budget):
            if event=='before_partial_aggregate_commit': budget.seconds=-1
        budget = Budget(hook=hook); receipts = matching_receipts(case,mapping,candidates,budget)
        result = adapter.aggregate_partial_scene_receipts(case,mapping,receipts,candidates,budget=budget)
        assert_no_U(self,result); self.assertEqual(set(result['scenes']),set(candidates))

    def test_legacy_fixed_API_keeps_full_mapping_and_old_protocol(self):
        case,_,candidates = small_case(auto=False); budget=Budget(); sid=next(iter(candidates))
        full={'A.pre':'CPU1','B.pre':'CPU2','C.pre':'CPU1'}
        with patch.object(adapter,'evaluate_piecewise',side_effect=fake_physical):
            receipt=adapter.evaluate_scene(case,sid,full,candidates[sid],budget=budget)
        self.assertEqual(receipt['protocol'],adapter.PROTOCOL)
        self.assertEqual(receipt['state'],'SAFE')
        self.assertNotIn('local_deployment',receipt)
        with self.assertRaises(ValueError): adapter.validate_fixed_deployment(case,{'A.pre':'CPU1'})
        with self.assertRaises(ValueError): adapter.validate_fixed_deployment(with_auto_low_idle(case),full)


if __name__ == '__main__':
    unittest.main()
