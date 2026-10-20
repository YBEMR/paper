"""New wrapper mocks only: no method, physical model, optimizer or heat call."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4
import unittest

import run_heuristic_followup as w

class DummyBudget:
    def check(self):pass

class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.folder=w.REPO/'.runtime/k144_wrapper_fixtures'/uuid4().hex
        self.folder.mkdir(parents=True);self.out=self.folder/'followup'
        self.raw={'kind':'mock raw'};self.config={'kind':'mock config'}
        self.instance={'id':'base__R1','window_ms':'400','start_grid_ms':'5',
            'platform':{'node_order':['CPU1']},
            'scenarios':[{'id':sid,'weight':'1/2','maximum_temperature_degC':['80']} for sid in ('AB','AC')]}
        self.ids=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(w.canonical,(self.raw,self.config,self.instance))))
        self.source=self.folder/'source.py';self.source.write_text('# fixture only\n',encoding='utf-8')
        self.current={self.source.relative_to(w.REPO).as_posix():w.sha(self.source)}
        self.base=self.folder/'base.json';self.plan=self.folder/'plan.json';self.gate=self.folder/'checks.json'
        w.save(self.base,{'input_identities':self.ids,'source_sha256':self.current})
        w.save(self.plan,{'method_order':w.jobs(),'per_method_root_budget_s':300,'input_identities':self.ids})
        w.save(self.gate,{'protocol':w.CHECK_PROTOCOL,'passed':True,'source_sha256':self.current,
            'source_unchanged':True,'errors':0,'failures':0,'skipped':0,'error':None,'tests_run':1,
            'blocked_calls':{'mock':0},'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0})
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.real_source_gate=w.source_gate;self.real_sources=w.sources
        for name,value in [('TARGET',self.out),('GLOBAL_CLAIM',self.folder/'claim.json'),('BASE',self.base),('PLAN',self.plan)]:
            self.stack.enter_context(patch.object(w,name,value))
        self.stack.enter_context(patch.object(w,'source_gate',return_value=self.current))
        self.stack.enter_context(patch.object(w,'sources',return_value=self.current))
        self.fresh=self.stack.enter_context(patch.object(w,'fresh_input',side_effect=lambda *a:deepcopy((self.raw,self.config,self.instance))))
        self.entry=Mock(side_effect=self.fake_method)
        self.entries=self.stack.enter_context(patch.object(w,'entry_points',return_value={'heuristic':self.entry}))

    def prepared(self):
        w.prepare(self.out,self.gate)
        return w.read(self.out/'declaration.json')

    def safe(self,*,reason='DECLARED_SEARCH_COMPLETED',elapsed=20.):
        candidate={'scenes':{sid:[{'stage_id':sid+'.stage','unit':'CPU1','opp':'L','start_ms':'0'}] for sid in ('AB','AC')}}
        evaluation={'state':'SAFE','rankable_energy':True,'problem_id':'base__R1',
            'legality':{'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'},'completed_at_elapsed_s':2.,
            'weighted_energy_J':['1','1.000001'],'safe_upper_bound_J':'1.000001',
            'scenes':{sid:{'state':'SAFE','rankable_energy':True,'complete':True,'covered_until_s':'2/5',
                'trace':[{'time_s':'2/5'}],'peaks_degC':{'CPU1':['50','50']}} for sid in ('AB','AC')}}
        row={'source':'mock seed','candidate':candidate,'candidate_sha256':w.canonical(candidate),
            'evaluation':evaluation,'accepted_safe':True,'returned_at_s':2.}
        return {'state':'SAFE','reason':reason,'input_sha256':self.ids['input_sha256'],
            'safe_candidate':candidate,'safe_upper_bound_J':'1.000001','evaluation':evaluation,
            'evaluations':[row],'events':[],'violations':[], 'budget_exhausted':elapsed>=300,
            'timing':{'limit_s':300.,'method_elapsed_s':elapsed,'phase_records':[],
                'deadline_overshoot_s':max(0.,elapsed-300),'cleanup_s':0.}}

    def fake_method(self,loader,folder,**kwargs):
        loader(DummyBudget())
        self.assertEqual(kwargs['seconds'],300);self.assertTrue(kwargs['allow_auto_low'])
        return self.safe()

    def status(self,r,d=None,**kwargs):
        d=d or {'scene_spec':w.scene_spec(self.instance),'input_sha256':self.ids['input_sha256']}
        return w.result_records(r,d,input_valid=True,source_valid=True,**kwargs)

    def test_01_prepare_and_admission_preserve_original_domain(self):
        d=self.prepared();self.assertEqual(w.admission(self.out),d)
        self.assertEqual(d['jobs'],w.jobs());self.assertEqual(d['per_method_budget_s'],300)
        self.assertEqual(w.read(self.out/'ledger.json')['consumed'],0)
        self.assertFalse(w.GLOBAL_CLAIM.exists());self.assertFalse(list((self.out/'claims').iterdir()))

    def test_02_execution_needs_explicit_separate_authorization(self):
        self.prepared()
        with self.assertRaises(PermissionError):w.run(self.out)
        self.entry.assert_not_called();self.assertFalse(w.GLOBAL_CLAIM.exists())

    def test_03_two_mock_methods_independent_fresh_and_original_arguments(self):
        self.prepared();self.assertTrue(w.run(self.out,execution_authorized=True))
        self.assertEqual(self.entry.call_count,2)
        self.assertEqual([c.kwargs['method'] for c in self.entry.call_args_list],['heft','sa'])
        self.assertEqual([c.kwargs['seed'] for c in self.entry.call_args_list],[None,101])
        self.assertEqual(self.fresh.call_count,3)
        for call in self.entry.call_args_list:
            self.assertEqual(set(call.kwargs),{'method','seed','seconds','allow_auto_low'})
            self.assertNotIn('shared_deployment',call.kwargs)
        self.assertEqual(w.read(self.out/'ledger.json')['consumed'],2)

    def test_04_normal_deadline_does_not_stop_next_mock_method(self):
        self.prepared()
        def effect(loader,folder,**kw):loader(DummyBudget());return self.safe(reason='wall_time_limit',elapsed=300.01)
        self.entry.side_effect=effect
        self.assertTrue(w.run(self.out,execution_authorized=True))
        rows=w.read(self.out/'ledger.json')['calls']
        self.assertEqual([r['execution']['execution_status'] for r in rows],['NORMAL_TIME_LIMIT']*2)
        self.assertTrue(all(r['usable_U_J']=='1.000001' for r in rows))

    def test_05_real_resource_failure_stops_remaining_even_with_deadline(self):
        self.prepared()
        def effect(loader,folder,**kw):loader(DummyBudget());return self.safe(reason='RESOURCE_LIMIT',elapsed=300.01)
        self.entry.side_effect=effect
        self.assertFalse(w.run(self.out,execution_authorized=True));self.assertEqual(self.entry.call_count,1)
        row=w.read(self.out/'ledger.json')['calls'][0]
        self.assertEqual(row['execution']['execution_status'],'TECHNICAL_FAILURE_CONFIRMED')
        self.assertEqual(row['usable_U_J'],'1.000001')
        self.assertFalse((self.out/'claims/sa101.json').exists())

    def test_06_consumed_batch_cannot_restart(self):
        self.prepared();self.assertTrue(w.run(self.out,execution_authorized=True))
        count=self.entry.call_count
        with self.assertRaises(FileExistsError):w.run(self.out,execution_authorized=True)
        self.assertEqual(self.entry.call_count,count)

    def test_07_input_corruption_rejected_before_call(self):
        self.prepared();w.save(self.out/'input_instance.json',{'changed':True})
        with self.assertRaises(ValueError):w.run(self.out,execution_authorized=True)
        self.entry.assert_not_called();self.assertFalse(w.GLOBAL_CLAIM.exists())

    def test_08_precheck_and_snapshot_bytes_bind_admission(self):
        self.prepared();w.save(self.out/'precheck.json',{'changed':True})
        with self.assertRaises(ValueError):w.admission(self.out)

    def test_09_no_alternate_output_or_reprepare(self):
        self.prepared()
        with self.assertRaises(FileExistsError):w.prepare(self.out,self.gate)
        with self.assertRaises(ValueError):w.prepare(self.folder/'other',self.gate)

    def test_10_incomplete_or_missing_tail_is_not_usable_SAFE(self):
        for mutate in ('complete','tail','node','peak'):
            r=self.safe();scene=r['evaluation']['scenes']['AB']
            if mutate=='complete':scene['complete']=False
            if mutate=='tail':scene['trace'][-1]['time_s']='1/5'
            if mutate=='node':scene['peaks_degC']={}
            if mutate=='peak':scene['peaks_degC']['CPU1']=['81','81']
            rec=self.status(r)
            self.assertIsNone(rec['usable_U_J']);self.assertEqual(rec['execution']['execution_status'],'TECHNICAL_FAILURE_CONFIRMED')

    def test_11_missing_scene_or_zero_weight_scene_still_needed(self):
        r=self.safe();del r['evaluation']['scenes']['AC']
        self.assertIsNone(self.status(r)['usable_U_J'])

    def test_12_candidate_hash_binds_every_complete_record(self):
        r=self.safe();r['evaluations'][0]['candidate_sha256']='corrupted'
        rec=self.status(r);self.assertIsNone(rec['usable_U_J'])
        self.assertIsNone(rec['completion_metrics']['first_complete_SAFE_at_s'])

    def test_13_late_claimed_SAFE_never_becomes_usable(self):
        r=self.safe();r['evaluation']['completed_at_elapsed_s']=300.
        self.assertIsNone(self.status(r)['usable_U_J'])

    def test_14_incomplete_last_candidate_retains_previous_complete_SAFE(self):
        r=self.safe(reason='wall_time_limit',elapsed=300.)
        r['evaluations'].append({'source':'interrupted','candidate':{'scenes':{}},'accepted_safe':False,
            'evaluation':{'state':'UNRESOLVED','reason':'wall_time_limit','budget_exhausted':True},'returned_at_s':300.})
        rec=self.status(r)
        self.assertEqual(rec['execution']['execution_status'],'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertEqual(rec['usable_U_J'],'1.000001');self.assertEqual(len(rec['unresolved_evaluation_records']),1)

    def test_15_old_unresolved_observation_kept_without_erasing_valid_SAFE(self):
        r=self.safe();r['evaluations'].insert(0,{'source':'old undecided','accepted_safe':False,
            'evaluation':{'state':'UNRESOLVED','reason':'TEMPERATURE_LIMIT_UNRESOLVED'}})
        rec=self.status(r);self.assertEqual(rec['usable_U_J'],'1.000001')
        self.assertEqual(rec['execution']['execution_status'],'NORMAL_COMPLETION')
        self.assertEqual(len(rec['unresolved_evaluation_records']),1)

    def test_16_real_numeric_error_in_earlier_scene_not_erased(self):
        r=self.safe(reason='wall_time_limit',elapsed=300.)
        r['evaluations'].insert(0,{'accepted_safe':False,'evaluation':{'state':'UNRESOLVED',
            'scenes':{'AB':{'state':'UNRESOLVED','reason':'NUMERICAL_ERROR'}}}})
        self.assertEqual(self.status(r)['execution']['execution_status'],'NUMERICAL_ANOMALY_OBSERVED')

    def test_17_valid_violation_before_deadline_survives(self):
        r=self.safe(reason='wall_time_limit',elapsed=300.)
        r['violations']=[{'formed_at_elapsed_s':299.,'scene_id':'AB','node':'CPU1',
            'time_s':'1/5','temperature_degC':['81','82'],'limit_degC':'80'}]
        self.assertTrue(self.status(r)['execution']['known_violation_preserved'])

    def test_18_source_identity_failure_withholds_rankable_U(self):
        d={'scene_spec':w.scene_spec(self.instance),'input_sha256':self.ids['input_sha256']}
        rec=w.result_records(self.safe(),d,input_valid=True,source_valid=False)
        self.assertIsNone(rec['usable_U_J']);self.assertEqual(rec['raw_reported_U_J'],'1.000001')

    def test_19_missing_SAFE_is_not_infeasibility(self):
        r=self.safe(reason='wall_time_limit',elapsed=300.)
        r.update(state='UNRESOLVED',safe_candidate=None,safe_upper_bound_J=None,evaluation=None,evaluations=[])
        rec=self.status(r)
        self.assertEqual(rec['execution']['execution_status'],'NORMAL_TIME_LIMIT')
        self.assertFalse(rec['execution']['independently_proven_infeasible']);self.assertIsNone(rec['usable_U_J'])

    def test_20_source_gate_inherits159_and_only_six_additions(self):
        with patch.object(w,'BASE',w.HERE/'results/fair_comparison_preparation01/declaration.json'),patch.object(w,'sources',self.real_sources):
            self.assertEqual(len(self.real_source_gate()),165)
        with patch.object(w,'source_gate',side_effect=ValueError('changed source')):
            with self.assertRaises(ValueError):w.prepare(self.out,self.gate)

if __name__=='__main__':unittest.main()
