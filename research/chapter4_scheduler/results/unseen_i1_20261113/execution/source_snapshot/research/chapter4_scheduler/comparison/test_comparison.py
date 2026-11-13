"""Artificial fixtures only; no workload search or thermal integration."""
from copy import deepcopy
from fractions import Fraction as F
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, FakeClock, changed
from research.chapter4_scheduler.validation.test_sa_adapter import remap
from research.chapter4_scheduler.validation.sa_adapter import SABindings, dispatch_with_sa
from research.chapter4_scheduler.blocking.method import Bindings
from timing import MethodBudget
from thermal import Exhausted
from .core import EvaluationJournal, normalize, canonical_terminal, conditional_statistics, time_to_quality, CLOCK_ORIGIN
from . import run


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock();self.budget=MethodBudget(300,clock=self.clock)
        self.config,self.instance,self.candidate=artificial_input();self.stream=io.StringIO()

    def test_exact_argument_and_return_identity_without_extra_calls(self):
        receipt=object();calls=[]
        def evaluator(i,c,a,b):
            calls.append((i,c,a,b));self.clock.now+=1;return receipt
        journal=EvaluationJournal(evaluator,self.budget,self.stream)
        self.assertIs(journal(self.instance,self.candidate,self.config,self.budget),receipt)
        self.assertIs(calls[0][0],self.instance);self.assertIs(calls[0][1],self.candidate)
        self.assertIs(calls[0][2],self.config);self.assertIs(calls[0][3],self.budget)
        self.assertEqual(len(calls),1);self.assertEqual(journal.attempts[0]["state"],"RETURNED")
        self.assertEqual(json.loads(self.stream.getvalue().splitlines()[0])["candidate"],self.candidate)

    def test_exception_is_counted_and_preserves_original_exception(self):
        failure=Exhausted("MOCK_ONLY")
        def evaluator(*args):raise failure
        journal=EvaluationJournal(evaluator,self.budget,self.stream)
        with self.assertRaises(Exhausted) as caught:journal(self.instance,self.candidate,self.config,self.budget)
        self.assertIs(caught.exception,failure);self.assertEqual(journal.attempts[0]["state"],"INTERRUPTED")
        self.assertEqual(len(self.stream.getvalue().splitlines()),2)

    def test_wrong_budget_stops_before_evaluator(self):
        journal=EvaluationJournal(lambda *args:self.fail("WRONG_ROOT_CALLED"),self.budget)
        with self.assertRaisesRegex(ValueError,"ROOT_CHANGED"):journal(self.instance,self.candidate,self.config,object())
        self.assertEqual(journal.attempts,[])


class CommonLifecycleTests(unittest.TestCase):
    def exercise(self, arm, mode="safe"):
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-main-comparison-") as tmp:
            clock=FakeClock();budget=MethodBudget(300,clock=clock);clock.now+=20
            config,instance,candidate=artificial_input(two_scenes=True)
            count=[]
            def evaluator(i,c,a,b):
                self.assertIs(b,budget)
                if count and mode=="exception":
                    clock.now=1300.1;raise Exhausted("MOCK_ONLY_TIMEOUT")
                count.append(True);clock.now+=1
                r=complete_mock(i,c,a,b)
                if mode=="bad_SAFE":del r["scenes"]["S1"]
                return r
            journal=EvaluationJournal(evaluator,budget)
            def loader(root):self.assertIs(root,budget);clock.now+=2;return deepcopy(config),deepcopy(instance)
            def search(i,c,b,assess,**kwargs):
                assess(candidate,"sa_initial_heft" if arm=="SA" else "MOCK_INITIAL")
                if mode=="exception":assess(changed(candidate,5),"sa_neighbour_delay")
                elif mode=="remap":
                    assess(remap(candidate),"sa_neighbour_mapping")
                else:assess(deepcopy(candidate),"sa_neighbour_delay" if arm=="SA" else "MOCK_CACHE")
                return {"status":"MOCK_INITIALIZER_COMPLETED","initialisation_source":"MOCK_ONLY","stop_reason":"NO_MUTABLE_GENES"}
            bindings=SABindings(search,journal) if arm=="SA" else Bindings(search,journal)
            with patch("research.chapter4_scheduler.blocking.method.candidate_packets",return_value=iter(())):
                result=dispatch_with_sa(arm,loader,Path(tmp)/"method",budget,seed=101 if arm=="SA" else None,bindings=bindings)
            unified=normalize(result,journal)
            return result,unified,journal

    def test_all_three_methods_count_same_actual_boundary_and_cache(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):
                raw,r,journal=self.exercise(arm)
                self.assertEqual(r["counts"]["evaluation_attempts"],1)
                self.assertEqual(r["counts"]["returned_receipts"],1)
                self.assertEqual(r["counts"]["validated_SAFE_receipts"],1)
                self.assertEqual(r["counts"]["cache_hits"],1)
                self.assertEqual(r["timing"]["method_elapsed_s"],23)
                self.assertEqual(r["first_SAFE_at_s"],23);self.assertEqual(r["first_own_final_quality_at_s"],23)
                self.assertEqual(r["timing"]["clock_origin"],CLOCK_ORIGIN)
                self.assertEqual(r["terminal"],"SEARCH_COMPLETED");self.assertEqual(raw["state"],"MOCK_SAFE")

    def test_all_three_methods_keep_prior_SAFE_and_count_interrupted_attempt(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):
                raw,r,journal=self.exercise(arm,"exception")
                self.assertEqual(r["counts"]["evaluation_attempts"],2)
                self.assertEqual(r["counts"]["returned_receipts"],1)
                self.assertEqual(r["counts"]["interrupted_attempts"],1)
                self.assertTrue(r["has_SAFE_archive"]);self.assertEqual(r["terminal"],"BUDGET_EXHAUSTED")

    def test_SA_legal_shared_remap_reaches_original_evaluator(self):
        raw,r,journal=self.exercise("SA","remap")
        self.assertEqual(r["counts"]["evaluation_attempts"],2)
        self.assertEqual(r["counts"]["validated_SAFE_receipts"],2)
        self.assertNotEqual(journal.attempts[0]["candidate_sha256"],journal.attempts[1]["candidate_sha256"])
        self.assertEqual(r["native_search_metadata"]["initialisation_source"],"MOCK_ONLY")

    def test_malformed_SAFE_claim_is_not_counted_as_validated_SAFE(self):
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm):
                raw,r,journal=self.exercise(arm,"bad_SAFE")
                self.assertEqual(r["counts"]["returned_SAFE_claims"],1)
                self.assertEqual(r["counts"]["validated_SAFE_receipts"],0)
                self.assertEqual(r["terminal"],"TECHNICAL_STOP");self.assertFalse(r["normal_stop"])

    def test_accounting_mismatch_is_not_silently_repaired(self):
        raw,r,journal=self.exercise("SA");journal.attempts.append(deepcopy(journal.attempts[0]))
        with self.assertRaisesRegex(ValueError,"ACCOUNTING_MISMATCH"):normalize(raw,journal)


class MetricTests(unittest.TestCase):
    def test_seed_statistics_use_conditional_median_range_and_full_denominator(self):
        r=conditional_statistics(["1","3","2"],5)
        self.assertEqual(r["energy_upper_J_median_among_successes"],"2")
        self.assertEqual(r["energy_upper_J_range_among_successes"],["1","3"])
        self.assertEqual(r["success_rate"],.6)
        self.assertEqual(conditional_statistics([],5)["energy_upper_J_median_among_successes"],None)
        self.assertEqual(conditional_statistics(["1","2"],5)["energy_upper_J_median_among_successes"],"3/2")

    def test_quality_time_uses_complete_upper_threshold_and_formation_time(self):
        rows=[{"accepted_safe":True,"energy":{"lower":"1","upper":"2"},"receipt":{"completed_at_elapsed_s":5}},
              {"accepted_safe":False,"energy":{"upper":"0"},"receipt":{"completed_at_elapsed_s":2}},
              {"accepted_safe":True,"energy":{"lower":"1","upper":"3/2"},"receipt":{"completed_at_elapsed_s":8}}]
        self.assertEqual(time_to_quality({"evaluations":rows},"2"),5)
        self.assertEqual(time_to_quality({"evaluations":rows},"3/2"),8)
        self.assertIsNone(time_to_quality({"evaluations":rows},"1"))

    def test_normal_no_SAFE_not_infeasible_and_numerical_stop_not_timeout(self):
        r={"run_terminal":"UNRESOLVED_STOP","reason":"INITIALIZATION_NOT_COMPLETED","safe_candidate":None,
           "initialization":{"status":"NO_SAFE_CONSTRUCTED_WITNESS"},"evaluations":[{"receipt":{"state":"THERMAL_VIOLATION"}}]}
        self.assertEqual(canonical_terminal(r),"NORMAL_NO_SAFE")
        r["evaluations"][0]["receipt"]["state"]="UNRESOLVED";self.assertEqual(canonical_terminal(r),"TECHNICAL_STOP")
        self.assertEqual(canonical_terminal({"run_terminal":"UNRESOLVED_STOP","reason":"NUMERICAL_UNRESOLVED"}),"NUMERICAL_STOP")

    def test_root_changes_rejected(self):
        clock=FakeClock();budget=MethodBudget(300,clock=clock);root=(budget.start,budget.deadline,budget.seconds,budget.clock)
        run.assert_root(budget,root);budget.deadline+=1
        with self.assertRaisesRegex(ValueError,"ROOT_BUDGET_CHANGED"):run.assert_root(budget,root)

    def test_exact_fourteen_slots_and_seed_case_coverage(self):
        slots=run.slots();self.assertEqual(len(slots),14);self.assertEqual(len({s["id"] for s in slots}),14)
        for case in ("base__R2","base__R5"):
            self.assertEqual(sorted(s["seed"] for s in slots if s["case"]==case and s["arm"]=="SA"),list(range(101,106)))
            self.assertEqual({s["arm"] for s in slots if s["case"]==case},{"HEFT","ON","SA"})


class WorkerTests(unittest.TestCase):
    def test_method_worker_real_binding_identity_path_uses_common_journal_for_all_arms(self):
        """REAL interface checks, but fake search/physics and artificial input."""
        import sa_method,thermal
        from research.chapter4_scheduler.mechanism_check.run import save,sha,digest
        original_budget=MethodBudget
        for arm in ("HEFT","ON","SA"):
            with self.subTest(arm=arm),tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-method-worker-") as tmp:
                clock=FakeClock();out=Path(tmp);slot=next(s for s in run.slots() if s["case"]=="base__R2" and s["arm"]==arm)
                class FixtureBudget(original_budget):
                    def __init__(self,seconds):super().__init__(seconds,clock=clock)
                folder=out/"calls"/slot["id"];folder.mkdir(parents=True)
                config,instance,candidate=artificial_input(two_scenes=True)
                identities={"raw_config_sha256":digest(config),"config_sha256":digest(config),"input_sha256":digest(instance)}
                save(out/"plan.json",{"slots":[slot],"SA_parameters":sa_method.algorithm_parameters(),"input_identities":{"base__R2":identities}})
                save(out/"plan_identity.json",{"plan_sha256":sha(out/"plan.json")})
                save(folder/"claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
                def fresh(case,budget):
                    self.assertEqual(case,"base__R2");clock.now+=2
                    return deepcopy(config),deepcopy(config),deepcopy(instance)
                def evaluator(i,c,a,b):clock.now+=1;return complete_mock(i,c,a,b)
                def search(i,c,b,assess,**kwargs):
                    assess(candidate,"sa_initial_heft" if arm=="SA" else "MOCK_INITIAL")
                    assess(deepcopy(candidate),"MOCK_CACHE")
                    if arm=="SA":
                        self.assertEqual(kwargs["seed"],101)
                        assess(remap(candidate),"sa_neighbour_mapping")
                    return {"status":"BOUNDED_SEARCH_COMPLETED","initialisation_source":"heft",
                            "parameters":sa_method.algorithm_parameters(),"stop_reason":"NO_MUTABLE_GENES"}
                with patch.object(run,"verify"),patch.object(run.time,"monotonic",clock),patch.dict(run.os.environ,run.THREADS), \
                        patch("timing.MethodBudget",FixtureBudget), \
                        patch("p0_batch.run_p0.fresh_input",side_effect=fresh) as loads, \
                        patch("heft_method.run_heft",side_effect=search),patch("sa_method.run_sa",side_effect=search), \
                        patch("thermal.evaluate_candidate",side_effect=evaluator) as physics, \
                        patch("research.chapter4_scheduler.blocking.method.candidate_packets",return_value=iter(())),patch("builtins.print"):
                    failed=run.worker(out,slot["id"])
                    self.assertFalse(failed,run.read(folder/"method_return.json"))
                    self.assertIs(thermal.evaluate_candidate,physics)
                    self.assertEqual(loads.call_count,1)
                r=run.read(folder/"method_return.json");self.assertTrue(r["normal_stop"])
                self.assertEqual(r["counts"]["evaluation_attempts"],2 if arm=="SA" else 1)
                self.assertEqual(r["counts"]["validated_SAFE_receipts"],2 if arm=="SA" else 1)
                self.assertEqual(r["counts"]["cache_hits"],1)
                self.assertEqual(r["timing"]["limit_s"],300)

    def test_fresh_post_clock_label_and_evaluation_phase_are_correct(self):
        import sa_method
        from research.chapter4_scheduler.mechanism_check.run import save,sha
        clock=FakeClock();original_budget=MethodBudget
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-post-clock-") as tmp:
            out=Path(tmp);slot=run.slots()[0];folder=out/"calls"/slot["id"];(folder/"method").mkdir(parents=True)
            config,instance,candidate=artificial_input();budget=original_budget(300,clock=clock)
            raw={"safe_candidate":candidate,"evaluation":complete_mock(instance,candidate,config["accuracy_targets"],budget)}
            for name,value in (("result",raw),("input_instance",instance),("input_config",config)):save(folder/"method"/(name+".json"),value)
            save(out/"plan.json",{"slots":[slot],"SA_parameters":sa_method.algorithm_parameters()})
            save(out/"plan_identity.json",{"plan_sha256":sha(out/"plan.json")})
            save(folder/"post_claim.json",{"slot":slot,"plan_sha256":sha(out/"plan.json")})
            def evaluator(i,c,a,b):clock.now+=2;return complete_mock(i,c,a,b)
            with patch.object(run,"verify"),patch.object(run.time,"monotonic",clock),patch.dict(run.os.environ,run.THREADS), \
                    patch("timing.MethodBudget",side_effect=lambda s:original_budget(s,clock=clock)),patch("thermal.evaluate_candidate",side_effect=evaluator),patch("builtins.print"):
                self.assertFalse(run.worker(out,slot["id"],post=True))
            r=run.read(folder/"post_return.json");self.assertTrue(r["passed"])
            self.assertEqual(r["timing"]["clock_origin"],CLOCK_ORIGIN)
            self.assertEqual(r["timing"]["limit_s"],60)
            self.assertEqual(r["timing"]["phases_exclusive_s"]["complete_post_evaluation"],2)
            self.assertEqual(r["evaluation_attempts"],1)


class BatchTests(unittest.TestCase):
    def exercise(self,mode):
        from research.chapter4_scheduler.mechanism_check.run import save,sha
        with tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-14-batch-") as tmp:
            out=Path(tmp);save(out/"plan.json",{"slots":run.slots(),"budgets":{"calendar_s":9000}})
            save(out/"plan_identity.json",{"plan_sha256":sha(out/"plan.json")})
            def fake(argv,**kwargs):
                phase=argv[4];sid=argv[argv.index("--slot")+1];folder=out/"calls"/sid
                self.assertEqual(kwargs["timeout"],420 if phase=="worker" else 90)
                self.assertTrue(all(kwargs["env"][k]==v for k,v in run.THREADS.items()))
                if mode=="timeout":raise subprocess.TimeoutExpired(argv,420,output=b"MOCK_PARTIAL")
                fail=(mode=="method_fail" and phase=="worker") or (mode=="post_fail" and phase=="post")
                save(folder/("method_return.json" if phase=="worker" else "post_return.json"),
                    {"has_SAFE_archive":mode!="no_safe","normal_stop":not fail,"error":None})
                return SimpleNamespace(returncode=int(fail),stdout="MOCK_ONLY",stderr="")
            with patch.object(run,"verify"),patch.object(run,"resources",return_value={"sufficient":True}), \
                    patch.object(run.subprocess,"run",side_effect=fake) as execute,patch("builtins.print"):
                failed=run.batch(out)
            result=run.read(out/"batch_return.json")
            self.assertEqual(len(result["consumed_method_slots"]),14 if mode in ("success","no_safe") else 1)
            self.assertEqual(execute.call_count,28 if mode=="success" else 14 if mode=="no_safe" else 2 if mode=="post_fail" else 1)
            self.assertEqual(bool(failed),mode not in ("success","no_safe"))
            with patch.object(run,"verify"),self.assertRaises(FileExistsError):run.batch(out)
            if mode=="timeout":self.assertEqual((out/"calls"/run.slots()[0]["id"]/"worker_partial_stdout.log").read_bytes(),b"MOCK_PARTIAL")

    def test_fourteen_fresh_calls_and_posts_once(self):self.exercise("success")
    def test_no_SAFE_retained_without_post_or_replacement(self):self.exercise("no_safe")
    def test_method_failure_halts_later_slots(self):self.exercise("method_fail")
    def test_post_failure_halts_later_slots(self):self.exercise("post_fail")
    def test_watchdog_retains_partial_log_and_never_retries(self):self.exercise("timeout")


if __name__=="__main__":unittest.main()
