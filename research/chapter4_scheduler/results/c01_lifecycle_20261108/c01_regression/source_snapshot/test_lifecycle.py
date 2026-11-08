"""Artificial whole-lifecycle/worker contracts; no real scheduling or heat."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_method import artificial_input,complete_mock,FakeClock,changed
from research.chapter4_scheduler.validation.lifecycle import execute_heft as previous_heft
from research.chapter4_scheduler.blocking.method import Bindings
from research.chapter4_scheduler.comparison.core import CLOCK_ORIGIN
from timing import MethodBudget
from thermal import Exhausted
from .heft_lifecycle import execute_heft
from . import entry


def without_call_token(value):
    if isinstance(value,dict):return {k:without_call_token(v) for k,v in value.items() if k!="root_token"}
    if isinstance(value,list):return [without_call_token(v) for v in value]
    return value


class HeftBudgetBridgeTests(unittest.TestCase):
    def exercise(self,execute,seconds=300,mode="complete"):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-HEFT-lifecycle-") as tmp:
            clock=FakeClock();budget=MethodBudget(seconds,clock=clock);clock.now+=.25
            config,instance,candidate=artificial_input();seen=[]
            def loader(active):self.assertIs(active,budget);clock.now+=.25;return deepcopy(config),deepcopy(instance)
            def evaluator(i,c,a,b):
                self.assertIs(b,budget);seen.append(deepcopy(c));clock.now+=.5
                return complete_mock(i,c,a,b,interval=("10","10") if len(seen)==1 else ("9","9"))
            def initializer(i,c,b,assess,**kwargs):
                self.assertIs(b,budget)
                if mode=="no_safe":return {"status":"NO_SAFE_CONSTRUCTED_WITNESS"}
                assess(candidate,"heft:eft")
                if mode=="technical":raise RuntimeError("MOCK_ONLY_HEFT_FAILURE")
                assess(changed(candidate,5),"heft:energy-pass:one-start-delay")
                if mode=="expiry":clock.now=1000+seconds+.01
                return {"status":"BOUNDED_SEARCH_COMPLETED","local_attempts":[{"MOCK_ONLY":True}]}
            result=execute(loader,Path(tmp)/"method",bindings=Bindings(initializer,evaluator),budget=budget)
            return result,seen

    def test_original300s_behavior_matches_complete_lifecycle(self):
        for mode in ("complete","expiry","technical","no_safe"):
            with self.subTest(mode=mode):
                old,old_trace=self.exercise(previous_heft,mode=mode);new,new_trace=self.exercise(execute_heft,mode=mode)
                self.assertEqual(old_trace,new_trace);self.assertEqual(without_call_token(old),without_call_token(new))

    def test_short_real_root_not_disguised_as300s(self):
        r,_=self.exercise(execute_heft,seconds=5)
        self.assertEqual(r["root_context"]["root_seconds"],5)
        self.assertEqual(float(r["root_context"]["root_deadline"])-float(r["root_context"]["root_start"]),5)
        self.assertEqual(r["timing"]["limit_s"],5);self.assertEqual(r["safe_upper_bound_J"],"9")

    def test_short_expiry_retains_timely_SAFE_and_sets_budget_flag(self):
        r,_=self.exercise(execute_heft,seconds=5,mode="expiry")
        self.assertEqual(r["run_terminal"],"BUDGET_EXHAUSTED");self.assertTrue(r["budget_exhausted"])
        self.assertEqual(r["safe_upper_bound_J"],"9");self.assertIsNone(r["initial_safe_snapshot"])

    def test_deadline_or_cap_drift_refused_before_loader(self):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-bad-cap-") as tmp:
            for seconds,drift in ((301,False),(5,True),(True,False)):
                budget=MethodBudget(seconds,clock=FakeClock())
                if drift:budget.deadline+=1
                with self.subTest(seconds=seconds,drift=drift),self.assertRaises(ValueError):
                    execute_heft(lambda b:self.fail("BAD_ROOT_LOADER"),Path(tmp)/str(seconds),bindings=object(),budget=budget)

    def test_late_SAFE_cannot_replace_valid_archive_on_short_root(self):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-late-") as tmp:
            clock=FakeClock();budget=MethodBudget(5,clock=clock);config,instance,candidate=artificial_input();calls=[]
            def evaluator(i,c,a,b):
                if calls:
                    clock.now=1005.01;return complete_mock(i,c,a,b,interval=("1","1"),formed=5.001)
                calls.append(True);clock.now=1001;return complete_mock(i,c,a,b)
            def search(i,c,b,assess,**kwargs):
                assess(candidate,"heft:eft");assess(changed(candidate,5),"heft:energy-pass:one-start-delay")
            r=execute_heft(lambda b:(config,instance),Path(tmp)/"method",bindings=Bindings(search,evaluator),budget=budget)
            self.assertEqual(r["run_terminal"],"BUDGET_EXHAUSTED");self.assertEqual(r["safe_upper_bound_J"],"10")


class DispatchTests(unittest.TestCase):
    def test_each_path_uses_same_caller_root_and_original_short_root_APIs(self):
        from . import dispatch as module
        budget=SimpleNamespace(seconds=30);loader=object();folder=Path("MOCK_ONLY");bindings=object()
        with patch.object(module,"execute_heft",return_value="HEFT") as heft:
            self.assertEqual(module.dispatch("HEFT",loader,folder,budget,bindings=bindings),"HEFT")
            self.assertIs(heft.call_args.kwargs["budget"],budget)
        with patch("research.chapter4_scheduler.blocking.method.execute_reconstruction",return_value="ON") as on:
            self.assertEqual(module.dispatch("ON",loader,folder,budget,bindings=bindings),"ON")
            self.assertEqual(on.call_args.kwargs["seconds"],30);self.assertTrue(on.call_args.kwargs["allow_blocking_edges"])
        with patch("research.chapter4_scheduler.validation.sa_adapter.execute_sa",return_value="SA") as sa:
            self.assertEqual(module.dispatch("SA",loader,folder,budget,seed=101,bindings=bindings),"SA")
            self.assertEqual(sa.call_args.kwargs["seed"],101)
        for arm in ("OFF","other"):
            with self.assertRaises(ValueError):module.dispatch(arm,loader,folder,budget)
        with self.assertRaises(ValueError):module.dispatch("ON",loader,folder,budget,seed=101)


class WorkerTests(unittest.TestCase):
    def exercise(self,arm,mode="complete"):
        import sa_method,thermal
        from research.chapter4_scheduler.mechanism_check.run import save,sha,digest
        original_budget=MethodBudget;clock=FakeClock()
        class FixtureBudget(original_budget):
            def __init__(self,seconds):super().__init__(seconds,clock=clock)
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-full-worker-") as tmp:
            out=Path(tmp);slot=next(s for s in entry.SLOTS if s["arm"]==arm);folder=out/"calls"/slot["id"];folder.mkdir(parents=True)
            config,instance,candidate=artificial_input(two_scenes=True)
            save(out/"plan.json",{"slots":[slot],"SA_parameters":sa_method.algorithm_parameters(),"input_sha256":digest(instance),"config_sha256":digest(config)})
            save(out/"plan_identity.json",{"sha256":sha(out/"plan.json")});save(folder/"claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
            calls=[]
            def evaluator(i,c,a,b):
                if calls and mode=="exception":raise RuntimeError("MOCK_ONLY_EVALUATION_FAILURE")
                calls.append(True);clock.now+=1;return complete_mock(i,c,a,b)
            def loader(b):
                self.assertEqual(b.seconds,30);clock.now+=1;return deepcopy(config),deepcopy(instance)
            def search(i,c,b,assess,**kwargs):
                self.assertEqual(b.seconds,30);assess(candidate,"sa_initial_heft" if arm=="SA" else "heft:eft")
                assess(changed(candidate,5),"sa_neighbour_delay" if arm=="SA" else "heft:energy-pass:one-start-delay")
                if arm=="SA":self.assertEqual(kwargs["seed"],101)
                return {"status":"BOUNDED_SEARCH_COMPLETED","initialisation_source":"MOCK_ONLY","parameters":sa_method.algorithm_parameters(),"stop_reason":"NO_MUTABLE_GENES","counters":{"MOCK_ONLY":True}}
            with patch.object(entry,"verify"),patch.object(entry.time,"monotonic",clock),patch.dict(entry.os.environ,entry.THREADS), \
                    patch("timing.MethodBudget",FixtureBudget),patch.object(entry,"load_c01",side_effect=loader) as loads, \
                    patch("thermal.evaluate_candidate",side_effect=evaluator) as physics,patch("heft_method.run_heft",side_effect=search), \
                    patch("sa_method.run_sa",side_effect=search),patch("research.chapter4_scheduler.blocking.method.candidate_packets",return_value=iter(())),patch("builtins.print"):
                failed=entry.worker(out,slot["id"])
                returned=entry.read(folder/"method_return.json")
                self.assertEqual(bool(failed),mode=="exception",returned)
                self.assertIs(thermal.evaluate_candidate,physics);self.assertEqual(loads.call_count,1)
                self.assertFalse((folder/"input_raw_config.json").exists());self.assertTrue((folder/"common_input_identity.json").exists())
                if mode!="exception":
                    save(folder/"post_claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
                    self.assertFalse(entry.worker(out,slot["id"],post=True))
                    post=entry.read(folder/"post_return.json");self.assertTrue(post["passed"])
                    self.assertEqual(post["timing"]["limit_s"],10);self.assertEqual(post["timing"]["clock_origin"],CLOCK_ORIGIN)
            return returned

    def test_all_three_actual_lifecycle_workers_and_post_use_same_semantics(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):
                r=self.exercise(arm)
                self.assertEqual(r["counts"]["evaluation_attempts"],2);self.assertEqual(r["counts"]["validated_SAFE_receipts"],2)
                self.assertEqual(r["timing"]["limit_s"],30);self.assertEqual(r["timing"]["method_elapsed_s"],3)
                self.assertFalse(r["formal_comparison_result"]);self.assertTrue(r["normal_stop"])

    def test_interrupted_evaluation_attempt_keeps_prior_SAFE_but_stops_path(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):
                r=self.exercise(arm,"exception")
                self.assertEqual(r["counts"]["evaluation_attempts"],2);self.assertEqual(r["counts"]["returned_receipts"],1)
                self.assertEqual(r["counts"]["validated_SAFE_receipts"],1);self.assertTrue(r["has_SAFE_archive"])
                self.assertIsNotNone(r["error"]);self.assertFalse(r["normal_stop"])


class PlanAndBatchTests(unittest.TestCase):
    def test_only_three_short_engineering_paths_can_be_declared(self):
        plan={"schema":"c01-full-lifecycle-engineering-smoke-v1","purpose":"ENGINEERING_ONLY_NOT_FORMAL_COMPARISON",
            "formal_comparison":False,"slots":deepcopy(entry.SLOTS),"limits":deepcopy(entry.LIMITS),
            "input_file_sha256":entry.SOURCE_SHA256,"thread_environment":deepcopy(entry.THREADS)}
        entry.validate_plan(plan)
        for change in ("formal","seed","budget","input"):
            bad=deepcopy(plan)
            if change=="formal":bad["formal_comparison"]=True
            elif change=="seed":bad["slots"][-1]["seed"]=102
            elif change=="budget":bad["limits"]["method_s"]=300
            else:bad["input_file_sha256"]="changed"
            with self.subTest(change=change),self.assertRaises(ValueError):entry.validate_plan(bad)

    def test_coverage_records_observed_paths_without_claiming_full_completion(self):
        c=entry.coverage({"evaluations":[],"timing":{"phase_records":[{"phase":"activity_saving_targets"}]},"initialization":{"status":"BOUNDED_SEARCH_COMPLETED"},"initial_safe_snapshot":{}},"ON")
        self.assertTrue(c["complete_enhanced_HEFT_initialization"]);self.assertTrue(c["ON_target_phase_entered"])
        self.assertEqual(c["ON_graph_physical_evaluations"],0)

    def exercise_batch(self,mode):
        from research.chapter4_scheduler.mechanism_check.run import save,sha
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-three-batch-") as tmp:
            out=Path(tmp);save(out/"plan.json",{"slots":entry.SLOTS});save(out/"plan_identity.json",{"sha256":sha(out/"plan.json")})
            def fake(argv,**kwargs):
                phase=argv[4];slot=argv[argv.index("--slot")+1];folder=out/"calls"/slot
                self.assertEqual(kwargs["timeout"],45 if phase=="worker" else 20)
                if mode=="timeout":raise __import__('subprocess').TimeoutExpired(argv,45,output=b"MOCK_PARTIAL")
                failure=mode=="method_fail" and phase=="worker" or mode=="post_fail" and phase=="post"
                save(folder/("method_return.json" if phase=="worker" else "post_return.json"),{"has_SAFE_archive":mode!="no_safe","normal_stop":not failure,"error":None})
                return SimpleNamespace(returncode=int(failure),stdout="MOCK_ONLY",stderr="")
            with patch.object(entry,"verify"),patch.object(entry,"resources",return_value={"sufficient":True}),patch.object(entry.subprocess,"run",side_effect=fake) as process,patch("builtins.print"):
                failed=entry.batch(out)
            r=entry.read(out/"batch_return.json")
            self.assertEqual(len(r["consumed_method_slots"]),3 if mode in ("success","no_safe") else 1)
            self.assertEqual(process.call_count,6 if mode=="success" else 3 if mode=="no_safe" else 2 if mode=="post_fail" else 1)
            self.assertEqual(bool(failed),mode not in ("success","no_safe"))
            with patch.object(entry,"verify"),self.assertRaises(FileExistsError):entry.batch(out)
            if mode=="timeout":self.assertEqual((out/"calls"/entry.SLOTS[0]["id"]/"worker_partial_stdout.log").read_bytes(),b"MOCK_PARTIAL")

    def test_three_methods_three_posts_once(self):self.exercise_batch("success")
    def test_no_SAFE_is_retained_without_post_or_retry(self):self.exercise_batch("no_safe")
    def test_method_failure_halts_later_paths(self):self.exercise_batch("method_fail")
    def test_post_failure_halts_later_paths(self):self.exercise_batch("post_fail")
    def test_watchdog_preserves_partial_log_and_never_retries(self):self.exercise_batch("timeout")


if __name__=="__main__":unittest.main()
