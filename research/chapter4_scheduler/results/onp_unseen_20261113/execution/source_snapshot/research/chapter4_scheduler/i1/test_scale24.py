"""New entry checks. Only a separate TEST root is structurally generated."""
import ast
from contextlib import redirect_stdout
import inspect
import io
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

from . import scale24 as unseen, unseen as pair, scale24_inputs as new_inputs
from .initializer import run_heft_i1
from research.chapter4_scheduler.method import Bindings


class Scale24Tests(unittest.TestCase):
    def setUp(self):
        self.parent=unseen.REPO.parent.resolve()
        self.folder=self.parent/('mock_unseen_'+uuid.uuid4().hex);self.folder.mkdir()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        assert self.folder.resolve().is_relative_to(self.parent) and self.folder.name.startswith('mock_unseen_')
        shutil.rmtree(self.folder)

    def cases(self):
        return [{'case_id':c,'root_id':c[:3],'stages_per_scene':24} for c in unseen.CASES]

    def test_fixed_roots_and_exact_six_slots(self):
        p=new_inputs.fixed_plan()
        self.assertEqual(p['roots'],[{'root_id':r,'seed':s} for r,s in new_inputs.ROOTS])
        self.assertEqual(p['scales'],[24]);self.assertEqual(p['namespace'],'ch4-independent-i1-v1')
        self.assertEqual([(s['case_id'],s['arm']) for s in unseen.slots(self.cases())],list(unseen.ORDER))
        self.assertEqual([s['arm'] for s in unseen.slots(self.cases())],['HEFT','OFF','ON','ON','OFF','HEFT'])
        with self.assertRaises(ValueError):unseen.dispatch('SA',None,None,None,None)

    def test_515_existing_sources_unchanged(self):
        old=unseen.read(unseen.OLD/'plan.json')
        self.assertEqual(len(old['source_sha256']),515)
        for name,h in old['source_sha256'].items():self.assertEqual(unseen.sha(unseen.REPO/name),h,name)

    def test_separate_manual_root12_to24_static_preserves_lineage(self):
        from research.chapter3_workload_calibration.profiles import load_catalog
        p=new_inputs.fixed_plan();p['namespace']='ch4-scale24-input-manual-check'
        config=unseen.read(new_inputs.original.SOURCE_CONFIG)
        with patch('thermal.evaluate_candidate',side_effect=AssertionError('THERMAL_FORBIDDEN')),patch('heft_method.run_heft',side_effect=AssertionError('HEFT_FORBIDDEN')):
            from .new_inputs import construct as construct12
            catalog=load_catalog(new_inputs.original.SOURCE_CONFIG)
            _,parent=construct12(catalog,config,'TEST_SCALE24_ONLY',1,p)
            adapted,e=new_inputs.construct(catalog,config,'TEST_SCALE24_ONLY',1,p,parent)
            with self.assertRaisesRegex(ValueError,'PARENT_LINEAGE_MISMATCH'):
                new_inputs.construct(catalog,config,'WRONG_PARENT_ROOT',1,p,parent)
        self.assertEqual(e['metrics']['stages_per_scene'],[24,24])
        self.assertEqual(e['two_scene_evidence']['counters']['thermal_evaluations'],0)
        self.assertEqual(e['static_check']['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertIsNone(e['adaptation_receipt']['formal_initial_solution'])
        self.assertIsNone(e['adaptation_receipt']['fixed_deployment'])
        self.assertEqual(e['two_scene_evidence']['workload']['time_contract']['derivation']['axis'],'S2')
        self.assertTrue(e['lineage']['existing_profiles_and_edges_preserved'])
        self.assertEqual(e['lineage']['parent_scale'],12)
        self.assertEqual(e['metrics']['shared_stage_identities'],32)
        self.assertEqual(e['metrics']['identities_present_in_both_scenes'],16)
        old=parent['two_scene_evidence']['workload'];new=e['two_scene_evidence']['workload']
        for sid,v in old['physical_profiles'].items():self.assertEqual(new['physical_profiles'][sid],v)
        for app,v in old['applications'].items():self.assertTrue(set(map(tuple,v['edges']))<=set(map(tuple,new['applications'][app]['edges'])))

    def test_input_plan_precedes_mock_draws_and_no_overwrite(self):
        out=self.folder/'generation';seen=[]
        def fake(catalog,config,root,seed,plan,parent):
            self.assertEqual(unseen.read(out/'input_plan.json'),plan)
            seen.append((root,seed))
            return {'config':{'MOCK_ONLY':True},'instance':{'MOCK_ONLY':True}}, {'metrics':{'MOCK_ONLY':True}}
        with patch.object(new_inputs,'construct',side_effect=fake):
            result=new_inputs.build_inputs(out)
            with self.assertRaises(FileExistsError):new_inputs.build_inputs(out)
        self.assertEqual(seen,list(new_inputs.ROOTS));self.assertEqual(len(result['cases']),2)
        self.assertEqual(result['counters']['HEFT_ON_OFF_SA_calls'],0)

    def test_all_three_arms_exact_I1_and_same_root(self):
        for arm in ('HEFT','OFF','ON'):
            root=type('Root',(),{'seconds':300})();evaluator=object()
            with patch('research.chapter4_scheduler.validation.lifecycle.execute_heft',return_value='MOCK_ONLY') as heft,patch('research.chapter4_scheduler.blocking.method.execute_reconstruction',return_value='MOCK_ONLY') as graph:
                self.assertEqual(unseen.dispatch(arm,object(),'folder',root,Bindings(object(),evaluator,'REAL_CORE')),'MOCK_ONLY')
            selected=heft if arm=='HEFT' else graph
            self.assertEqual(selected.call_count,1)
            self.assertEqual((graph if arm=='HEFT' else heft).call_count,0)
            k=selected.call_args.kwargs
            self.assertIs(k['budget'],root);self.assertIs(k['bindings'].initializer,run_heft_i1)
            self.assertIs(k['bindings'].evaluator,evaluator);self.assertEqual(k['bindings'].kind,'REAL_I1')
            if arm!='HEFT':self.assertEqual(k['allow_blocking_edges'],arm=='ON')

    def test_controller_only_changes_module(self):
        old=inspect.getsource(pair.batch).replace('research.chapter4_scheduler.i1.unseen','research.chapter4_scheduler.i1.scale24')
        self.assertEqual(ast.dump(ast.parse(old)),ast.dump(ast.parse(inspect.getsource(unseen.batch))))

    def controller(self,technical):
        out=self.folder/'batch';out.mkdir()
        plan={'cases':self.cases(),'slots':unseen.slots(self.cases()),'subject_commit':'MOCK_ONLY'}
        unseen.save(out/'plan.json',plan)
        def fake(command,**kwargs):
            slot=command[command.index('--slot')+1]
            if not technical:unseen.save(out/'calls'/slot/'method_return.json',{'normal_stop':True,'has_SAFE_archive':False,'terminal':'NORMAL_NO_SAFE'})
            return subprocess.CompletedProcess(command,int(technical),'MOCK_ONLY','')
        with patch.object(unseen,'verify'),patch.object(unseen.subprocess,'run',side_effect=fake) as launch,redirect_stdout(io.StringIO()):
            self.assertEqual(unseen.batch(out),int(technical))
        self.assertEqual(launch.call_count,1 if technical else 6)
        self.assertTrue(all(c.args[0][3]=='research.chapter4_scheduler.i1.scale24' for c in launch.call_args_list))
        b=unseen.read(out/'batch_return.json');s=unseen.read(out/'summary.json')
        self.assertEqual(b['retry_count'],0);self.assertEqual(len(b['slots']),6);self.assertEqual(len(s['rows']),6)
        self.assertEqual(sum(x['status']=='NOT_RUN_TECHNICAL_STOP' for x in b['slots']),5 if technical else 0)
        self.assertEqual(len(s['three_arm_comparisons']),2)

    def test_normal_no_SAFE_keeps_six_slots(self):self.controller(False)
    def test_technical_failure_stops_without_retry(self):self.controller(True)

    def test_search_metrics_omit_only_HEFT(self):
        with patch.object(unseen,'ORIGINAL_METRICS',return_value='MOCK_ONLY') as f:
            for arm in ('HEFT','ON','OFF'):unseen.metrics({},arm)
        self.assertEqual([c.args[1] for c in f.call_args_list],['HEFT','ON','ON'])


    def test_generation_failure_retained_without_second_root_or_retry(self):
        out=self.folder/'failed_generation'
        with patch.object(new_inputs,'construct',side_effect=RuntimeError('MOCK_GENERATION_FAILURE')) as gen:
            with self.assertRaisesRegex(RuntimeError,'MOCK_GENERATION_FAILURE'):new_inputs.build_inputs(out)
        self.assertEqual(gen.call_count,1)
        r=unseen.read(out/'generation_failure.json')
        self.assertEqual(r['retry_count'],0);self.assertEqual(r['replacement_count'],0)
        self.assertEqual(r['case_id'],'U03__n24');self.assertFalse((out/'U04__n24').exists())

    def test_saved_parent_identity_verified(self):
        p=new_inputs.fixed_plan()
        e,c=new_inputs.load_parent('U03',2026111303,p)
        self.assertEqual(c['case_id'],'U03__n12')
        self.assertEqual(e['unprojected_eight_scene_bundle']['provenance']['scale'],12)
        p['parent_manifest_sha256']='WRONG'
        with self.assertRaisesRegex(ValueError,'PARENT_IDENTITY_DRIFT'):new_inputs.load_parent('U03',2026111303,p)


if __name__=='__main__':unittest.main()
