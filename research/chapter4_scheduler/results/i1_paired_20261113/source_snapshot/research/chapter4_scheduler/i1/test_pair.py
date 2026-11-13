"""Mock launcher checks. No actual initialization, search or thermal execution."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import inspect
import io
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

from . import pair,run
from .initializer import run_heft_i1
from research.chapter4_scheduler.method import Bindings


class PairTests(unittest.TestCase):
    def cases(self):
        return [{'case_id':c,'root_id':c[:3],'stages_per_scene':12} for c in pair.CASES]

    def test_scope_order_and_frozen_science(self):
        self.assertEqual([(s['case_id'],s['arm']) for s in pair.slots(self.cases())],list(pair.ORDER))
        with self.assertRaises(ValueError):pair.slots(self.cases()+[{'case_id':'U01__n6'}])
        with self.assertRaises(ValueError):pair.dispatch('SA',None,None,None,None)
        frozen=pair.read(pair.OLD/'plan.json')
        self.assertEqual(len(frozen['source_sha256']),510)
        for name,h in frozen['source_sha256'].items():self.assertEqual(pair.sha(pair.REPO/name),h,name)

    def test_dispatch_exact_I1_both_flags_root_and_evaluator(self):
        for arm in ('ON','OFF'):
            root=type('Root',(),{'seconds':300})()
            evaluator,loader=object(),object()
            with patch('research.chapter4_scheduler.blocking.method.execute_reconstruction',return_value='MOCK_ONLY') as call:
                self.assertEqual(pair.dispatch(arm,loader,'folder',root,Bindings(object(),evaluator,'REAL_CORE')),'MOCK_ONLY')
            k=call.call_args.kwargs
            self.assertIs(k['budget'],root);self.assertEqual(k['seconds'],300)
            self.assertIs(k['bindings'].initializer,run_heft_i1)
            self.assertIs(k['bindings'].evaluator,evaluator)
            self.assertEqual(k['bindings'].kind,'REAL_I1')
            self.assertEqual(k['allow_blocking_edges'],arm=='ON')

    def test_OFF_search_cost_not_zeroed(self):
        with patch.object(pair,'ORIGINAL_METRICS',return_value='MOCK_ONLY') as call:
            self.assertEqual(pair.metrics({'mock':True},'OFF'),'MOCK_ONLY')
            call.assert_called_once_with({'mock':True},'ON')

    def test_controller_only_changes_worker_module(self):
        old=inspect.getsource(run.batch).replace('research.chapter4_scheduler.i1.run','research.chapter4_scheduler.i1.pair')
        self.assertEqual(ast.dump(ast.parse(old)),ast.dump(ast.parse(inspect.getsource(pair.batch))))

    def controller(self,technical):
        parent=pair.REPO.parent.resolve();out=parent/('mock_i1_pair_'+uuid.uuid4().hex);out.mkdir()
        try:
            plan={'cases':self.cases(),'slots':pair.slots(self.cases()),'subject_commit':'MOCK_ONLY'}
            pair.save(out/'plan.json',plan)
            def fake(command,**kwargs):
                slot=command[command.index('--slot')+1]
                if not technical:
                    pair.save(out/'calls'/slot/'method_return.json',{'normal_stop':True,'has_SAFE_archive':False,'terminal':'NORMAL_NO_SAFE'})
                return subprocess.CompletedProcess(command,1 if technical else 0,'MOCK_ONLY','')
            with patch.object(pair,'verify'),patch.object(pair.subprocess,'run',side_effect=fake) as launch,redirect_stdout(io.StringIO()):
                self.assertEqual(pair.batch(out),int(technical))
            self.assertEqual(launch.call_count,1 if technical else 4)
            for call in launch.call_args_list:self.assertEqual(call.args[0][3],'research.chapter4_scheduler.i1.pair')
            result=pair.read(out/'batch_return.json')
            self.assertEqual(result['retry_count'],0);self.assertEqual(len(result['slots']),4)
            self.assertEqual(sum(s['status']=='NOT_RUN_TECHNICAL_STOP' for s in result['slots']),3 if technical else 0)
            self.assertEqual(len(pair.read(out/'summary.json')['rows']),4)
        finally:
            assert out.resolve().is_relative_to(parent) and out.name.startswith('mock_i1_pair_')
            shutil.rmtree(out)

    def test_technical_stop_keeps_not_run_rows_no_retry(self):self.controller(True)

    def test_normal_no_SAFE_kept_and_next_planned_calls_continue(self):self.controller(False)

    def test_different_initials_report_difference_without_mechanism_claim(self):
        on={'safe':True,'post_passed':True,'error':None,'energy_upper_J':'8','energy_lower_J':'7'}
        off={**on,'energy_upper_J':'10','energy_lower_J':'9'}
        a={'initial_safe_snapshot':{'candidate':'A','receipt':{'weighted_energy_J':['11','12']}},
           'evaluations':[{'phase':'initialization','candidate_sha256':'A'}],'safe_candidate':'FINAL_A'}
        b=deepcopy(a)
        result=pair.compare_pair(on,off,a,b)
        self.assertTrue(result['comparable_SAFE_pair'])
        self.assertEqual(result['observed_ON_vs_OFF_saving_percent'],20)
        b['initial_safe_snapshot']['candidate']='DIFFERENT'
        result=pair.compare_pair(on,off,a,b)
        self.assertFalse(result['comparable_SAFE_pair'])
        self.assertEqual(result['observed_ON_vs_OFF_saving_percent'],20)


if __name__=='__main__':unittest.main()
