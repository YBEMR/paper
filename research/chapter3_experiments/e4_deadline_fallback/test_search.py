"""MOCK search-control regressions; every constructor/evaluator is injected.

The genuine research builder, thermal evaluator and old HANDWRITTEN research
fixture never run here. Real tiny constructors are isolated in test_construction.
"""
import ast
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction as F
import inspect
import unittest
from unittest.mock import patch

from e1_objective import search as old_search
from . import search
from .mock_fixtures import make_toy_fixture


class MockExpired(RuntimeError): pass


class MockBudget:
    def __init__(self, *, expired=False): self.expired, self.checks = expired, 0
    def check(self):
        self.checks += 1
        if self.expired: raise MockExpired("mock deadline")


def fabricated_candidate(instance, **options):
    deployment = options.get("deployment_override", {})
    overrides = options.get("opp_override", {})
    floors = options.get("start_floor", {})
    rank = options.get("opp_rank")
    default = "L" if rank in (1, 2) else "H"
    return {"scenes": {scene["id"]: [{"stage_id": stage["id"],
        "unit": deployment.get(stage["shared_stage_id"], "CPU1"),
        "opp": overrides.get((scene["id"], stage["id"]), default),
        "start_ms": str(floors.get((scene["id"], stage["id"]), "0"))}
        for stage in scene["stage_instances"]] for scene in instance["scenarios"]}}


def construction_receipt(candidate, rank=None):
    return {"candidate": deepcopy(candidate), "opp_rank": rank,
            "status": "COMPLETE_LEGAL_CANDIDATE" if candidate is not None else "CONSTRUCTION_UNRESOLVED",
            "reason": None if candidate is not None else "MOCK_NO_INSERTION"}


def invoke(*, module=search, initial=(False, False, False, False), fallback=True,
           state="SAFE", local=True, budget=None, expire_after_four=False,
           original_error_at=None, fallback_error=None, assess_error=None,
           first_receipt=None, fallback_receipt=None, same_original_candidates=False, observation=None):
    instance = make_toy_fixture("single"); config = {"mock_only": True}
    before, config_before = deepcopy(instance), deepcopy(config)
    trace = []; counts = {"initial": 0, "local": 0, "fallback": 0, "assess": 0}
    budget = budget or MockBudget()
    if observation is not None: observation.update(trace=trace, counts=counts)

    def original(i, b=None, **options):
        assert i is instance and b is budget
        is_initial = "opp_rank" in options
        key = "initial" if is_initial else "local"
        counts[key] += 1; trace.append(("old", deepcopy(options)))
        if is_initial and original_error_at == counts[key]: raise ValueError("mock original failure")
        if is_initial and first_receipt is not None and counts[key] == 1: return deepcopy(first_receipt)
        allowed = initial[counts[key] - 1] if is_initial else local
        opts = {"opp_rank": None} if is_initial and same_original_candidates else options
        candidate = fabricated_candidate(instance, **opts) if allowed else None
        if is_initial and expire_after_four and counts[key] == 4: budget.expired = True
        return construction_receipt(candidate, options.get("opp_rank"))

    def added(i, b=None, **options):
        assert i is instance and b is budget
        counts["fallback"] += 1; trace.append(("deadline", deepcopy(options)))
        if fallback_error: raise fallback_error("mock fallback failure")
        if fallback_receipt is not None: return deepcopy(fallback_receipt)
        return construction_receipt(fabricated_candidate(instance, **options) if fallback else None)

    def assess(candidate, source):
        counts["assess"] += 1; trace.append(("assess", deepcopy(candidate), source))
        if assess_error: raise assess_error("mock evaluator failure")
        if state != "SAFE": return {"state": state, "planning_score_J": None}
        rows = [r for group in candidate["scenes"].values() for r in group]
        score = F(100) - sum((5 if r["opp"] == "L" else 0) + F(r["start_ms"]) for r in rows)
        return {"state": "SAFE", "planning_score_J": [str(score), str(score)]}

    with ExitStack() as stack:
        stack.enter_context(patch.object(module, "build_heft_candidate", original))
        if hasattr(module, "build_deadline_candidate"):
            stack.enter_context(patch.object(module, "build_deadline_candidate", added))
        stack.enter_context(patch.object(module, "explicit_start_sets", return_value=None))
        stack.enter_context(patch.object(module, "require_heuristic_control"))
        result = module.run_search(instance, config, budget, assess, allow_auto_low=True)
    assert instance == before and config == config_before
    return result, trace, counts


def local_tail(function):
    body = ast.parse(inspect.getsource(function)).body[0].body
    at = next(n for n, node in enumerate(body) if isinstance(node, ast.Assign) and
              isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and
              node.value.func.id == "explicit_start_sets")
    return ast.dump(ast.Module(body=body[at:], type_ignores=[]), include_attributes=False)


class DeadlineFallbackSearchTests(unittest.TestCase):
    def test_original_local_pass_ast_is_identical(self):
        self.assertEqual(local_tail(old_search.run_search), local_tail(search.run_search))

    def test_normal_safe_branch_keeps_original_calls_and_acceptance(self):
        old = invoke(module=old_search, initial=(True, True, True, True))
        new = invoke(initial=(True, True, True, True))
        self.assertEqual(old[1:], new[1:])
        for key in ("local_attempts", "local_accepted", "local_base_candidate", "local_base_planning_score_J"):
            self.assertEqual(old[0][key], new[0][key])
        self.assertFalse(new[0]["deadline_fallback"]["triggered"])
        self.assertGreater(new[0]["local_accepted"], 0)

    def test_only_four_no_candidates_enable_one_default_eft_fallback(self):
        result, trace, counts = invoke()
        self.assertEqual(counts["initial"], 4); self.assertEqual(counts["fallback"], 1)
        self.assertEqual([t[1]["opp_rank"] for t in trace if t[0] == "old" and "opp_rank" in t[1]], [None, 0, 1, 2])
        self.assertEqual(next(t[1] for t in trace if t[0] == "deadline"), {"opp_rank": None})
        self.assertEqual(result["initial_complete_legal_candidates"], 0)
        self.assertEqual(result["deadline_fallback"]["attempt_count"], 1)
        self.assertTrue(result["deadline_fallback"]["complete_legal_candidate"])
        self.assertEqual(result["status"], "BOUNDED_SEARCH_COMPLETED")
        self.assertTrue(any(t[0] == "assess" and t[2] == "heft:deadline-ready-fallback" for t in trace))

    def test_one_shot_failed_fallback_does_not_restart(self):
        result, _, counts = invoke(fallback=False)
        self.assertEqual(counts, {"initial": 4, "local": 0, "fallback": 1, "assess": 0})
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")
        self.assertEqual(len(result["construction_attempts"]), 5)

    def test_legal_thermal_violation_is_never_a_no_candidate_trigger(self):
        result, _, counts = invoke(initial=(True, True, True, True), state="THERMAL_VIOLATION")
        self.assertEqual(counts["fallback"], 0); self.assertEqual(result["initial_complete_legal_candidates"], 4)
        self.assertFalse(result["deadline_fallback"]["triggered"])
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")

    def test_legal_numerically_unresolved_candidate_does_not_enable_fallback(self):
        result, _, counts = invoke(initial=(False, True, False, False), state="UNRESOLVED")
        self.assertEqual(counts["fallback"], 0); self.assertEqual(result["initial_complete_legal_candidates"], 1)
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")

    def test_duplicate_legal_candidates_count_before_deduplication(self):
        result, _, counts = invoke(initial=(True, True, True, True), state="UNRESOLVED", same_original_candidates=True)
        self.assertEqual(result["initial_complete_legal_candidates"], 4)
        self.assertEqual(counts["assess"], 1); self.assertEqual(counts["fallback"], 0)
        self.assertEqual(sum(a.get("duplicate_construction", False) for a in result["construction_attempts"]), 3)

    def test_legal_unsafe_fallback_is_not_accepted_or_retried(self):
        result, _, counts = invoke(state="THERMAL_VIOLATION")
        self.assertEqual(counts, {"initial": 4, "local": 0, "fallback": 1, "assess": 1})
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")
        self.assertTrue(result["deadline_fallback"]["complete_legal_candidate"])

    def test_legal_unresolved_fallback_is_not_accepted_or_retried(self):
        result, _, counts = invoke(state="UNRESOLVED")
        self.assertEqual(counts["fallback"], 1); self.assertEqual(counts["local"], 0)
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")

    def test_old_local_priority_can_fail_without_erasing_safe_fallback(self):
        result, _, counts = invoke(local=False)
        self.assertEqual(counts["fallback"], 1); self.assertGreater(counts["local"], 0)
        self.assertEqual(result["local_accepted"], 0)
        self.assertIsNotNone(result["local_base_candidate"])
        self.assertEqual(result["local_base_planning_score_J"], ["100", "100"])

    def test_budget_before_fourth_completion_propagates_without_fallback(self):
        observed = {}
        with self.assertRaises(MockExpired): invoke(expire_after_four=True, observation=observed)
        self.assertEqual(observed["counts"]["initial"], 4)
        self.assertEqual(observed["counts"]["fallback"], 0)

    def test_budget_before_first_construction_propagates(self):
        with self.assertRaises(MockExpired): invoke(budget=MockBudget(expired=True))

    def test_original_constructor_fault_propagates_instead_of_fallback(self):
        observed = {}
        with self.assertRaisesRegex(ValueError, "original failure"): invoke(original_error_at=2, observation=observed)
        self.assertEqual(observed["counts"]["initial"], 2)
        self.assertEqual(observed["counts"]["fallback"], 0)

    def test_fallback_constructor_fault_propagates_without_retry(self):
        with self.assertRaisesRegex(ValueError, "fallback failure"): invoke(fallback_error=ValueError)

    def test_first_legal_evaluator_budget_stop_does_not_enable_fallback(self):
        observed = {}
        with self.assertRaises(MockExpired):
            invoke(initial=(True, True, True, True), assess_error=MockExpired, observation=observed)
        self.assertEqual(observed["counts"]["assess"], 1)
        self.assertEqual(observed["counts"]["fallback"], 0)

    def test_fallback_evaluator_budget_stop_propagates(self):
        with self.assertRaises(MockExpired): invoke(assess_error=MockExpired)

    def test_original_evaluator_numeric_fault_is_not_a_trigger(self):
        with self.assertRaisesRegex(ValueError, "evaluator failure"):
            invoke(initial=(True, True, True, True), assess_error=ValueError)

    def test_complete_status_without_candidate_is_technical(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            invoke(first_receipt={"status": "COMPLETE_LEGAL_CANDIDATE", "candidate": None})

    def test_candidate_with_incomplete_status_is_technical(self):
        candidate = fabricated_candidate(make_toy_fixture("single"))
        with self.assertRaisesRegex(ValueError, "contradictory"):
            invoke(first_receipt={"status": "CONSTRUCTION_UNRESOLVED", "candidate": candidate})

    def test_unknown_constructor_status_is_technical(self):
        with self.assertRaisesRegex(ValueError, "unknown construction status"):
            invoke(first_receipt={"status": "UNRECOGNIZED", "candidate": None})

    def test_fallback_status_contradiction_is_technical(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            invoke(fallback_receipt={"status": "COMPLETE_LEGAL_CANDIDATE", "candidate": None})

    def test_fallback_calls_receive_no_frozen_input_or_candidate_hint(self):
        _, trace, counts = invoke(local=False)
        self.assertEqual(counts["fallback"], 1)
        self.assertEqual([t[1] for t in trace if t[0] == "deadline"], [{"opp_rank": None}])

    def test_local_modifications_continue_through_original_builder_only(self):
        result, trace, counts = invoke()
        self.assertEqual(counts["fallback"], 1)
        self.assertEqual(counts["local"], 2)
        self.assertEqual([t[1] for t in trace if t[0] == "old" and "opp_rank" not in t[1]],
            [{"deployment_override": {"Only": "CPU1"}, "opp_override": {("toy", "toy:iid:Only:r1"): "L"}},
             {"deployment_override": {"Only": "CPU1"}, "opp_override": {("toy", "toy:iid:Only:r1"): "L"},
              "start_floor": {("toy", "toy:iid:Only:r1"): "1"}}])
        self.assertEqual(result["local_accepted"], 2)

    def test_search_inputs_stay_immutable_in_both_branches(self):
        self.assertEqual(invoke(initial=(True, True, True, True))[0]["status"], "BOUNDED_SEARCH_COMPLETED")
        self.assertEqual(invoke()[0]["status"], "BOUNDED_SEARCH_COMPLETED")


if __name__ == "__main__": unittest.main()
