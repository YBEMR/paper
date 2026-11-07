"""Artificial lifecycle/dispatch/batch contracts; no real research calls."""
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, FakeClock
from research.chapter4_scheduler.blocking.method import Bindings
from timing import MethodBudget
from .lifecycle import execute_heft
from . import run as launcher


class HeftLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir="/tmp",prefix="mock-sixslot-heft-");self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)/"method";self.clock=FakeClock();self.budget=MethodBudget(300,clock=self.clock)
        self.config,self.instance,self.candidate=artificial_input()

    def execute(self,*,mode="complete",bad_receipt=False):
        roots=[]
        def loader(budget):
            roots.append(budget);self.clock.now+=2
            return deepcopy(self.config),deepcopy(self.instance)
        def evaluator(instance,candidate,accuracy,budget):
            roots.append(budget);self.clock.now+=1
            receipt=complete_mock(instance,candidate,accuracy,budget)
            if bad_receipt:next(iter(receipt["scenes"].values()))["complete"]=False
            return receipt
        def initializer(instance,config,budget,assess,*,allow_auto_low):
            self.assertTrue(allow_auto_low);roots.append(budget);self.clock.now+=3
            if mode=="no_safe":return {"status":"NO_SAFE_CONSTRUCTED_WITNESS"}
            assess(deepcopy(self.candidate),"MOCK_ONLY:initial")
            if mode=="timeout":self.clock.now=1300.1
            return {"status":"MOCK_INITIALIZER_COMPLETED" if mode!="unfinished" else "MOCK_INTERRUPTED"}
        with patch("research.chapter4_scheduler.blocking.method.candidate_packets",side_effect=AssertionError("NO_GRAPH_FOR_HEFT")):
            result=execute_heft(loader,self.folder,bindings=Bindings(initializer,evaluator),budget=self.budget)
        self.assertTrue(all(root is self.budget for root in roots))
        self.assertFalse(result["usable_as_research_evidence"])
        self.assertNotEqual(result["state"],"SAFE")
        self.assertEqual(launcher.read(self.folder/"result.json"),result)
        return result

    def test_original_initializer_and_complete_recorder_share_caller_root(self):
        self.clock.now+=20
        result=self.execute()
        self.assertEqual(result["state"],"MOCK_SAFE");self.assertEqual(result["run_terminal"],"SEARCH_COMPLETED")
        self.assertEqual(result["timing"]["method_elapsed_s"],26)
        self.assertEqual(result["root_context"]["root_start"],"1000.0")
        self.assertEqual(result["root_context"]["root_deadline"],"1300.0")
        self.assertEqual(result["safe_candidate"],result["initial_safe_snapshot"]["candidate"])
        self.assertEqual(len(result["evaluations"]),1)

    def test_timeout_retains_timely_complete_safe_without_initial_freeze(self):
        result=self.execute(mode="timeout")
        self.assertEqual(result["state"],"MOCK_SAFE");self.assertEqual(result["run_terminal"],"BUDGET_EXHAUSTED")
        self.assertIsNone(result["initial_safe_snapshot"])

    def test_no_safe_is_explicit_normal_no_safe(self):
        result=self.execute(mode="no_safe")
        self.assertIsNone(result["safe_candidate"]);self.assertEqual(result["run_terminal"],"NORMAL_NO_SAFE")
        self.assertTrue(launcher.normal_outcome(result))

    def test_unfinished_initializer_does_not_claim_completion(self):
        result=self.execute(mode="unfinished")
        self.assertEqual(result["state"],"MOCK_SAFE");self.assertEqual(result["run_terminal"],"UNRESOLVED_STOP")
        self.assertIsNone(result["initial_safe_snapshot"]);self.assertFalse(launcher.normal_outcome(result))

    def test_incomplete_receipt_cannot_become_safe(self):
        result=self.execute(bad_receipt=True)
        self.assertIsNone(result["safe_candidate"]);self.assertEqual(result["run_terminal"],"TECHNICAL_STOP")


class DispatchTests(unittest.TestCase):
    def test_original_graph_no_safe_with_only_validated_thermal_witnesses_is_normal(self):
        r={"run_terminal":"UNRESOLVED_STOP","reason":"INITIALIZATION_NOT_COMPLETED",
            "initialization":{"status":"NO_SAFE_CONSTRUCTED_WITNESS"},"safe_candidate":None,
            "evaluations":[{"receipt":{"state":"THERMAL_VIOLATION"}}]}
        self.assertTrue(launcher.normal_outcome(r))
        r["evaluations"][0]["receipt"]["state"]="UNRESOLVED"
        self.assertFalse(launcher.normal_outcome(r))

    def test_only_arm_and_blocking_flag_differ_on_common_root(self):
        root=object();bindings=object();loader=object();folder=Path("MOCK_ONLY")
        for arm in ("HEFT","OFF","ON"):
            with self.subTest(arm=arm),patch("research.chapter4_scheduler.validation.lifecycle.execute_heft",return_value="HEFT") as heft, \
                    patch("research.chapter4_scheduler.blocking.method.execute_reconstruction",return_value="GRAPH") as graph:
                self.assertEqual(launcher.dispatch(arm,loader,folder,root,bindings),"HEFT" if arm=="HEFT" else "GRAPH")
                active=heft if arm=="HEFT" else graph
                self.assertIs(active.call_args.kwargs["budget"],root)
                self.assertIs(active.call_args.kwargs["bindings"],bindings)
                if arm!="HEFT":
                    self.assertEqual(active.call_args.kwargs["seconds"],300)
                    self.assertIs(active.call_args.kwargs["allow_blocking_edges"],arm=="ON")
                (graph if arm=="HEFT" else heft).assert_not_called()


class BatchTests(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-sixslot-batch-") as tmp:
            out=Path(tmp);slots=[{"id":str(i),"case":c,"arm":a} for i,(c,a) in enumerate(launcher.ORDER)]
            launcher.save(out/"plan.json",{"slots":slots,"budgets":{"calendar_s":3600}})
            def fake(cmd,**kwargs):
                slot=cmd[cmd.index("--slot")+1];phase=cmd[4];folder=out/"calls"/slot
                self.assertEqual(kwargs["timeout"],420 if phase=="worker" else 70)
                if mode=="timeout":raise subprocess.TimeoutExpired(cmd,420,output=b"MOCK_ONLY_PARTIAL")
                if phase=="worker":launcher.save(folder/"method_return.json",{"safe":mode!="no_safe"})
                code=int(mode=="worker_failure" and phase=="worker" or mode=="post_failure" and phase=="post")
                return SimpleNamespace(returncode=code,stdout="MOCK_ONLY",stderr="")
            with patch.object(launcher,"verify"),patch.object(launcher,"resources",return_value={}), \
                    patch.object(launcher.subprocess,"run",side_effect=fake) as process,patch("builtins.print"):
                failed=launcher.batch(out)
            result=launcher.read(out/"batch_return.json")
            expected=6 if mode in ("success","no_safe") else 1
            self.assertEqual(len(result["consumed_method_slots"]),expected)
            self.assertEqual(bool(failed),mode not in ("success","no_safe"))
            self.assertEqual(process.call_count,12 if mode=="success" else 6 if mode=="no_safe" else 2 if mode=="post_failure" else 1)
            if mode not in ("success","no_safe"):self.assertFalse((out/"calls/1").exists())
            if mode=="timeout":self.assertEqual((out/"calls/0/worker_partial_stdout.log").read_bytes(),b"MOCK_ONLY_PARTIAL")
            with patch.object(launcher,"verify"),patch.object(launcher,"resources",return_value={}),self.assertRaises(FileExistsError):
                launcher.batch(out)

    def test_six_fresh_methods_and_six_posts_once(self):self.exercise("success")
    def test_normal_no_safe_is_retained_without_post_or_free_retry(self):self.exercise("no_safe")
    def test_worker_failure_stops_next_slot(self):self.exercise("worker_failure")
    def test_post_failure_stops_next_slot(self):self.exercise("post_failure")
    def test_timeout_retains_partial_log_and_stops_without_retry(self):self.exercise("timeout")


if __name__=="__main__":unittest.main()
