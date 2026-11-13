"""Artificial SA recording tests. Invented receipts are never experiment data."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, FakeClock
from timing import MethodBudget
from thermal import Exhausted
from research.chapter4_scheduler.blocking import method as old
from . import sa_adapter as adapter


def remap(candidate, unit="CPU2", *, all_scenes=True):
    result=deepcopy(candidate)
    for n,rows in enumerate(result["scenes"].values()):
        if n and not all_scenes:break
        next(r for r in rows if r["stage_id"]=="x")["unit"]=unit
    return result


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock();self.budget=MethodBudget(300,clock=self.clock)
        self.config,self.instance,self.candidate=artificial_input(two_scenes=True)
        self.energy=("10","10")
        def evaluate(i,c,a,b):
            self.clock.now+=1
            return complete_mock(i,c,a,b,interval=self.energy)
        self.evaluator=Mock(side_effect=evaluate)
        self.bindings=adapter.SABindings(Mock(),self.evaluator)
        self.rec=adapter.SARecorder(self.instance,self.config,self.budget,self.bindings,adapter.source_identity())

    def test_old_frozen_graph_rejects_legal_remap_but_SA_recorder_allows_it(self):
        graph=old.CompleteRecorder(self.instance,self.config,self.budget,self.bindings,old.source_identity())
        graph.assess(self.candidate,"mock:init");graph.freeze_initial()
        with self.assertRaisesRegex(old.SearchStop,"FIXED_DEPLOYMENT_DRIFT"):
            graph.assess(remap(self.candidate),"mock:remap")
        self.rec.assess(self.candidate,"sa_initial_heft")
        self.energy=("11","11")
        receipt=self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        self.assertEqual(receipt["state"],"SAFE");self.assertEqual(receipt["weighted_energy_J"],["11","11"])
        self.assertEqual(self.rec.best["candidate"],self.candidate)
        self.assertIsNone(self.rec.current)
        self.assertFalse(self.rec.rows[-1]["best_archive_replaced"])

    def test_shared_mapping_requires_consistent_change_in_every_scene(self):
        self.rec.assess(self.candidate,"sa_initial_heft")
        with self.assertRaisesRegex(old.SearchStop,"PROPOSED_CANDIDATE_NOT_LEGAL"):
            self.rec.assess(remap(self.candidate,all_scenes=False),"sa_neighbour_mapping")
        self.assertEqual(self.evaluator.call_count,1)

    def test_better_remapped_candidate_replaces_best_without_locking_device(self):
        self.rec.assess(self.candidate,"sa_initial_heft");self.energy=("9","9")
        mapped=remap(self.candidate)
        self.rec.assess(mapped,"sa_neighbour_mapping")
        self.assertEqual(self.rec.best["candidate"],mapped)
        self.assertEqual(self.rec.initial["candidate"],self.candidate)
        self.assertIsNotNone(self.rec.first_strict_best_improvement_s)
        self.assertIsNone(self.rec.current)

    def test_overlapping_lower_upper_can_improve_archive_without_strict_descent(self):
        self.energy=("10","11");self.rec.assess(self.candidate,"sa_initial_heft")
        self.energy=("10","21/2");self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        self.assertEqual(self.rec.best["energy"]["upper"],"21/2")
        self.assertIsNone(self.rec.first_strict_best_improvement_s)

    def test_graph_freeze_is_explicitly_forbidden_for_SA(self):
        with self.assertRaisesRegex(old.SearchStop,"SA_DEPLOYMENT_MUST_NOT_BE_FROZEN"):self.rec.freeze_initial()
        self.assertIsNone(self.rec.current)

    def test_safe_cache_is_call_local_and_mapping_is_part_of_key(self):
        self.rec.assess(self.candidate,"sa_initial_heft");self.rec.assess(deepcopy(self.candidate),"sa_neighbour_delay")
        self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        other=adapter.SARecorder(self.instance,self.config,self.budget,self.bindings,adapter.source_identity())
        other.assess(self.candidate,"sa_initial_heft")
        self.assertEqual(self.evaluator.call_count,3);self.assertEqual(self.rec.cache_hits,1)
        self.assertNotEqual(self.rec.context["root_token"],other.context["root_token"])

    def test_complete_thermal_violation_is_returned_without_safe_objective_and_cached(self):
        self.rec.assess(self.candidate,"sa_initial_heft")
        def violation(i,c,a,b):
            self.clock.now+=1;r=complete_mock(i,c,a,b)
            r.update(state="THERMAL_VIOLATION",rankable_energy=False,weighted_energy_J=None,safe_upper_bound_J=None,
                violations=[{"scene_id":"S0","node":"c1","time_s":"1/100","temperature_degC":["81","82"],
                    "limit_degC":"80","formed_at_elapsed_s":b.elapsed}])
            return r
        self.evaluator.side_effect=violation
        trial=remap(self.candidate)
        receipt=self.rec.assess(trial,"sa_neighbour_mapping")
        self.assertIsNone(receipt["weighted_energy_J"]);self.assertEqual(receipt["state"],"THERMAL_VIOLATION")
        self.rec.assess(trial,"sa_neighbour_mapping")
        self.assertEqual(self.evaluator.call_count,2);self.assertEqual(self.rec.cache_hits,1)
        self.assertEqual(self.rec.best["candidate"],self.candidate)

    def test_zero_weight_scene_still_requires_complete_SAFE(self):
        self.instance["scenarios"][0]["weight"]="1";self.instance["scenarios"][1]["weight"]="0"
        self.rec=adapter.SARecorder(self.instance,self.config,self.budget,self.bindings,adapter.source_identity())
        def incomplete(i,c,a,b):
            r=complete_mock(i,c,a,b);del r["scenes"]["S1"];return r
        self.evaluator.side_effect=incomplete
        with self.assertRaises(Exception):self.rec.assess(self.candidate,"sa_initial_heft")
        self.assertIsNone(self.rec.best)

    def test_wrong_receipt_identity_rejected(self):
        def bad(i,c,a,b):
            r=complete_mock(i,c,a,b);r["evidence_identity"]["candidate_sha256"]="0"*64;return r
        self.evaluator.side_effect=bad
        with self.assertRaisesRegex(old.SearchStop,"RECEIPT_INPUT_OR_CANDIDATE_IDENTITY"):
            self.rec.assess(self.candidate,"sa_initial_heft")
        self.assertIsNone(self.rec.best)

    def test_evaluator_argument_mutation_rejected(self):
        def bad(i,c,a,b):
            r=complete_mock(i,c,a,b);i["id"]="mutated";return r
        self.evaluator.side_effect=bad
        with self.assertRaisesRegex(old.SearchStop,"EVALUATOR_ARGUMENT_MUTATION"):
            self.rec.assess(self.candidate,"sa_initial_heft")
        self.assertIsNone(self.rec.best)

    def test_timely_improved_SAFE_survives_late_transfer(self):
        self.rec.assess(self.candidate,"sa_initial_heft")
        def late(i,c,a,b):
            self.clock.now=1299.9;r=complete_mock(i,c,a,b,interval=("9","9"),formed=299.9)
            self.clock.now=1300.1;return r
        self.evaluator.side_effect=late
        with self.assertRaises(Exhausted):self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        self.assertEqual(self.rec.best["energy"]["upper"],"9")

    def test_SAFE_formed_after_deadline_never_replaces_old(self):
        self.rec.assess(self.candidate,"sa_initial_heft")
        def late(i,c,a,b):
            self.clock.now=1300.2;return complete_mock(i,c,a,b,interval=("9","9"),formed=300.1)
        self.evaluator.side_effect=late
        with self.assertRaisesRegex(old.SearchStop,"SAFE_FORMED_AFTER_DEADLINE"):
            self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        self.assertEqual(self.rec.best["candidate"],self.candidate)

    def test_numerical_unresolved_stops_without_invented_penalty(self):
        self.rec.assess(self.candidate,"sa_initial_heft")
        def unresolved(i,c,a,b):
            r=complete_mock(i,c,a,b);r.update(state="UNRESOLVED",rankable_energy=False,weighted_energy_J=None,safe_upper_bound_J=None);return r
        self.evaluator.side_effect=unresolved
        with self.assertRaisesRegex(old.SearchStop,"NUMERICAL_UNRESOLVED"):
            self.rec.assess(remap(self.candidate),"sa_neighbour_mapping")
        self.assertEqual(self.rec.best["candidate"],self.candidate)

    def test_root_clock_or_input_drift_rejected(self):
        for change in ("clock","deadline","input"):
            clock=FakeClock();budget=MethodBudget(300,clock=clock);config,instance,candidate=artificial_input()
            rec=adapter.SARecorder(instance,config,budget,self.bindings,adapter.source_identity())
            if change=="clock":budget.clock=lambda:clock.now
            elif change=="deadline":budget.deadline+=1
            else:instance["id"]="drift"
            with self.subTest(change=change),self.assertRaisesRegex(old.SearchStop,"SA_CALL_CONTEXT_DRIFT"):
                rec.assess(candidate,"sa_initial_heft")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-sa-lifecycle-");self.addCleanup(self.tmp.cleanup)
        self.clock=FakeClock();self.budget=MethodBudget(300,clock=self.clock)
        self.config,self.instance,self.candidate=artificial_input()

    def execute(self, search, *, seed=101, evaluator=None, budget=None):
        def loader(root):
            self.assertIs(root,self.budget if budget is None else budget);self.clock.now+=2
            return deepcopy(self.config),deepcopy(self.instance)
        if evaluator is None:
            def evaluator(i,c,a,b):
                self.clock.now+=1;return complete_mock(i,c,a,b)
        return adapter.execute_sa(loader,Path(self.tmp.name)/"method",seed=seed,budget=self.budget if budget is None else budget,
            bindings=adapter.SABindings(search,evaluator))

    def test_seed_and_original_caller_root_forwarded_without_reset(self):
        self.clock.now+=20
        def search(i,c,b,assess,*,seed,allow_auto_low):
            self.assertIs(b,self.budget);self.assertEqual(b.elapsed,22);self.assertEqual(seed,103);self.assertTrue(allow_auto_low)
            assess(self.candidate,"sa_initial_heft");return {"initialisation_source":"MOCK_ONLY","stop_reason":"NO_MUTABLE_GENES"}
        r=self.execute(search,seed=103)
        self.assertEqual(r["timing"]["method_elapsed_s"],23);self.assertEqual(r["state"],"MOCK_SAFE")
        self.assertFalse(r["usable_as_research_evidence"]);self.assertFalse(r["formal_comparison_result"])

    def test_invalid_seeds_and_budget_cap_rejected_before_loader(self):
        for seed in (True,1.0,None,"101"):
            with self.subTest(seed=seed),self.assertRaises(ValueError):self.execute(Mock(),seed=seed)
        with self.assertRaises(ValueError):self.execute(Mock(),budget=MethodBudget(301,clock=self.clock))

    def test_search_failure_preserves_prior_safe_and_failed_request(self):
        def search(i,c,b,assess,**kwargs):
            assess(self.candidate,"sa_initial_heft");raise RuntimeError("MOCK_ONLY_SEARCH_FAILURE")
        r=self.execute(search)
        self.assertEqual(r["state"],"MOCK_SAFE");self.assertEqual(r["run_terminal"],"TECHNICAL_STOP")
        self.assertIn("MOCK_ONLY_SEARCH_FAILURE",r["error"])

    def test_normal_no_SAFE_is_explicit_unresolved_not_infeasible(self):
        r=self.execute(lambda *args,**kwargs:{"initialisation_source":None,"stop_reason":"NO_MUTABLE_GENES"})
        self.assertIsNone(r["safe_candidate"]);self.assertEqual(r["run_terminal"],"SEARCH_COMPLETED")
        self.assertFalse(r["independently_proven_infeasible"])

    def test_evaluator_exception_keeps_request_and_old_safe(self):
        calls=[]
        def evaluator(i,c,a,b):
            if calls:raise RuntimeError("MOCK_EVALUATOR_FAILURE")
            calls.append(True);self.clock.now+=1;return complete_mock(i,c,a,b)
        def search(i,c,b,assess,**kwargs):
            assess(self.candidate,"sa_initial_heft");assess(remap(self.candidate),"sa_neighbour_mapping")
        r=self.execute(search,evaluator=evaluator)
        self.assertEqual(r["state"],"MOCK_SAFE");self.assertEqual(len(r["candidate_requests"]),2)
        self.assertEqual(r["candidate_requests"][-1]["state"],"INTERRUPTED_OR_REJECTED")
        self.assertEqual(r["full_evaluator_calls"],2)
        self.assertEqual(r["returned_evaluator_receipts"],1)
        self.assertEqual(r["evaluator_attempts"][-1]["state"],"INTERRUPTED")

    def test_new_dispatch_routes_SA_without_enabling_old_batch(self):
        with patch.object(adapter,"execute_sa",return_value="MOCK_ONLY") as sa:
            self.assertEqual(adapter.dispatch_with_sa("SA",object(),Path("MOCK"),self.budget,seed=105),"MOCK_ONLY")
            self.assertEqual(sa.call_args.kwargs["seed"],105)
        for arm in ("HEFT","OFF","ON"):
            with patch("research.chapter4_scheduler.validation.run.dispatch",return_value="LEGACY") as legacy:
                self.assertEqual(adapter.dispatch_with_sa(arm,object(),Path("MOCK"),self.budget,bindings=object()),"LEGACY")
                self.assertEqual(legacy.call_args.args[0],arm)
        with self.assertRaises(ValueError):adapter.dispatch_with_sa("HEFT",object(),Path("MOCK"),self.budget,seed=101)


class OriginalSADifferentialTests(unittest.TestCase):
    def test_original_SA_candidates_RNG_metadata_and_uphill_acceptance_match(self):
        """Two seeds, invented receipts; original SA body and RNG are used."""
        import sa_method
        for seed in (101,102):
            with self.subTest(seed=seed),tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-SA-differential-") as tmp:
                config,instance,candidate=artificial_input()
                outcomes=[]
                for adapted in (False,True):
                    clock=FakeClock();budget=MethodBudget(300,clock=clock);seen=[];energies=("10","10.001","9.9","10.002")
                    def evaluator(i,c,a,b):
                        seen.append(old.digest(c))
                        if len(seen)>len(energies):
                            clock.now=1300.1;raise Exhausted("MOCK_TIME_LIMIT")
                        clock.now+=1
                        return complete_mock(i,c,a,b,interval=(energies[len(seen)-1],)*2)
                    from heuristic_runner import CandidateRecorder
                    reference=CandidateRecorder(instance,config["accuracy_targets"],budget,evaluator=evaluator)
                    with patch("heft_method.build_heft_candidate",return_value={"candidate":deepcopy(candidate)}):
                        if adapted:
                            result=adapter.execute_sa(lambda root:(deepcopy(config),deepcopy(instance)),Path(tmp)/"adapted",
                                seed=seed,budget=budget,bindings=adapter.SABindings(sa_method.run_sa,evaluator))
                            meta=result["search"]
                            self.assertEqual(result["safe_upper_bound_J"],"99/10")
                            self.assertIsNone(result.get("error"))
                        else:meta=sa_method.run_sa(instance,config,budget,reference.assess,seed=seed,allow_auto_low=True)
                    outcomes.append((seen,meta))
                self.assertEqual(outcomes[0],outcomes[1])
                self.assertGreaterEqual(outcomes[1][1]["counters"].get("accepted_uphill_midpoint",0),1)


if __name__=="__main__":unittest.main()
