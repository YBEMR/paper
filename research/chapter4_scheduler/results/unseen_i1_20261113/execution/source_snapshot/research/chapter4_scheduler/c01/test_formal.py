"""Formal seven-call protocol tests with artificial algorithms/receipts only."""
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_method import FakeClock,artificial_input,complete_mock,changed
from research.chapter4_scheduler.mechanism_check.run import save,sha,digest
from research.chapter4_scheduler.comparison.core import CLOCK_ORIGIN
from timing import MethodBudget
from . import formal


class PlanTests(unittest.TestCase):
    def plan(self):
        return {"schema":"c01-formal-seven-call-comparison-v1","purpose":"C01_FORMAL_COMPARISON_FIXED_SEVEN_RUNS",
            "formal_comparison":True,"slots":deepcopy(formal.SLOTS),"limits":deepcopy(formal.LIMITS),
            "input_file_sha256":formal.SOURCE_SHA256,"thread_environment":deepcopy(formal.THREADS)}

    def test_exact_seven_slots_and_all_five_seeds(self):
        p=self.plan();formal.validate_plan(p)
        self.assertEqual(len(p["slots"]),7)
        self.assertEqual([s["seed"] for s in p["slots"] if s["arm"]=="SA"],list(range(101,106)))
        self.assertEqual([s["arm"] for s in p["slots"]].count("HEFT"),1)
        self.assertEqual([s["arm"] for s in p["slots"]].count("ON"),1)
        self.assertEqual(p["limits"]["method_s"],300);self.assertEqual(p["limits"]["post_s"],60)

    def test_old_smoke_or_changed_scope_cannot_be_relabelled(self):
        for change in ("schema","purpose","flag","slots","seed","budget","input"):
            p=self.plan()
            if change=="schema":p["schema"]="c01-full-lifecycle-engineering-smoke-v1"
            elif change=="purpose":p["purpose"]="ENGINEERING_ONLY_NOT_FORMAL_COMPARISON"
            elif change=="flag":p["formal_comparison"]=False
            elif change=="slots":p["slots"].append(deepcopy(p["slots"][-1]))
            elif change=="seed":p["slots"][-1]["seed"]=106
            elif change=="budget":p["limits"]["method_s"]=30
            else:p["input_file_sha256"]="wrong"
            with self.subTest(change=change),self.assertRaises(ValueError):formal.validate_plan(p)

    def test_formal_dispatch_uses_original300s_HEFT_not_short_wrapper(self):
        root=object();bindings=object();loader=object()
        with patch("research.chapter4_scheduler.validation.lifecycle.execute_heft",return_value="ORIGINAL") as original, \
                patch("research.chapter4_scheduler.c01.heft_lifecycle.execute_heft",side_effect=AssertionError("NO_SHORT_WRAPPER")):
            self.assertEqual(formal.dispatch("HEFT",loader,Path("MOCK_ONLY"),root,bindings=bindings),"ORIGINAL")
            self.assertIs(original.call_args.kwargs["budget"],root)
            self.assertIs(original.call_args.kwargs["bindings"],bindings)


class WorkerTests(unittest.TestCase):
    def exercise(self,arm,mode="success"):
        import thermal,sa_method
        clock=FakeClock();original_budget=MethodBudget
        class FixtureBudget(original_budget):
            def __init__(self,seconds):super().__init__(seconds,clock=clock)
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-formal-worker-") as tmp:
            out=Path(tmp);slot=next(s for s in formal.SLOTS if s["arm"]==arm);folder=out/"calls"/slot["id"];folder.mkdir(parents=True)
            config,instance,candidate=artificial_input(two_scenes=True)
            save(out/"plan.json",{"slots":[slot],"SA_parameters":sa_method.algorithm_parameters(),"input_sha256":digest(instance),"config_sha256":digest(config)})
            save(out/"plan_identity.json",{"sha256":sha(out/"plan.json")});save(folder/"claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
            calls=[]
            def evaluator(i,c,a,b):
                if calls and mode=="method_failure":raise RuntimeError("MOCK_ONLY_FAILURE")
                calls.append(True);clock.now+=1;return complete_mock(i,c,a,b)
            def loader(b):self.assertEqual(b.seconds,300);clock.now+=1;return deepcopy(config),deepcopy(instance)
            def search(i,c,b,assess,**kwargs):
                self.assertEqual(b.seconds,300)
                assess(candidate,"sa_initial_heft" if arm=="SA" else "heft:eft")
                assess(changed(candidate,5),"sa_neighbour_delay" if arm=="SA" else "heft:energy-pass:one-start-delay")
                if arm=="SA":self.assertEqual(kwargs["seed"],101)
                return {"status":"BOUNDED_SEARCH_COMPLETED","initialisation_source":"MOCK_ONLY","parameters":sa_method.algorithm_parameters(),"stop_reason":"NO_MUTABLE_GENES","counters":{"MOCK_ONLY":True}}
            with patch.object(formal,"verify"),patch.object(formal.time,"monotonic",clock),patch.dict(formal.os.environ,formal.THREADS), \
                    patch("timing.MethodBudget",FixtureBudget),patch.object(formal,"load_c01",side_effect=loader) as loads, \
                    patch("thermal.evaluate_candidate",side_effect=evaluator) as physics,patch("heft_method.run_heft",side_effect=search), \
                    patch("sa_method.run_sa",side_effect=search),patch("research.chapter4_scheduler.blocking.method.candidate_packets",return_value=iter(())),patch("builtins.print"):
                failed=formal.worker(out,slot["id"]);r=formal.read(folder/"method_return.json")
                self.assertEqual(bool(failed),mode=="method_failure",r);self.assertEqual(loads.call_count,1)
                self.assertIs(thermal.evaluate_candidate,physics)
                self.assertTrue(r["formal_comparison_result"])
                self.assertEqual(r["timing"]["limit_s"],300)
                if mode=="success":
                    self.assertEqual(r["counts"]["evaluation_attempts"],2)
                    save(folder/"post_claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
                    self.assertFalse(formal.worker(out,slot["id"],post=True))
                    post=formal.read(folder/"post_return.json");self.assertTrue(post["passed"])
                    self.assertEqual(post["timing"]["limit_s"],60);self.assertEqual(post["timing"]["clock_origin"],CLOCK_ORIGIN)
                    self.assertTrue(post["formal_comparison_result"])
                else:
                    self.assertEqual(r["counts"]["evaluation_attempts"],2);self.assertEqual(r["counts"]["returned_receipts"],1)
                    self.assertTrue(r["has_SAFE_archive"]);self.assertIsNotNone(r["error"])
            return r

    def test_all_three_formal_workers_and_posts_use300_60s_roots(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):self.exercise(arm)

    def test_evaluator_failure_keeps_archive_but_invalidates_formal_success(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):self.exercise(arm,"method_failure")


class BatchTests(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-seven-batch-") as tmp:
            out=Path(tmp);save(out/"plan.json",{"slots":formal.SLOTS});save(out/"plan_identity.json",{"sha256":sha(out/"plan.json")})
            def fake(argv,**kwargs):
                phase=argv[4];slot=argv[argv.index("--slot")+1];folder=out/"calls"/slot
                self.assertEqual(argv[3],"research.chapter4_scheduler.c01.formal")
                self.assertEqual(kwargs["timeout"],420 if phase=="worker" else 90)
                if mode=="timeout":raise subprocess.TimeoutExpired(argv,420,output=b"MOCK_PARTIAL")
                fail=mode=="method_failure" and phase=="worker" or mode=="post_failure" and phase=="post"
                save(folder/("method_return.json" if phase=="worker" else "post_return.json"),{"has_SAFE_archive":mode!="no_safe","normal_stop":not fail,"error":None})
                return SimpleNamespace(returncode=int(fail),stdout="MOCK_ONLY",stderr="")
            with patch.object(formal,"verify"),patch.object(formal,"resources",return_value={"sufficient":True}), \
                    patch.object(formal.subprocess,"run",side_effect=fake) as process,patch("builtins.print"):
                failed=formal.batch(out)
            r=formal.read(out/"batch_return.json")
            self.assertEqual(len(r["consumed_method_slots"]),7 if mode in ("success","no_safe") else 1)
            self.assertEqual(process.call_count,14 if mode=="success" else 7 if mode=="no_safe" else 2 if mode=="post_failure" else 1)
            self.assertEqual(bool(failed),mode not in ("success","no_safe"));self.assertTrue(r["formal_comparison"])
            with patch.object(formal,"verify"),self.assertRaises(FileExistsError):formal.batch(out)
            if mode=="timeout":self.assertEqual((out/"calls"/formal.SLOTS[0]["id"]/"worker_partial_stdout.log").read_bytes(),b"MOCK_PARTIAL")

    def test_seven_methods_and_posts_once(self):self.exercise("success")
    def test_no_SAFE_preserved_without_post_or_replacement(self):self.exercise("no_safe")
    def test_method_failure_halts_future_slots(self):self.exercise("method_failure")
    def test_post_failure_halts_future_slots(self):self.exercise("post_failure")
    def test_watchdog_preserves_partial_logs_and_never_retries(self):self.exercise("timeout")


if __name__=="__main__":unittest.main()
