"""Canonical MOCK ONLY constructor tests; no research input or heat calls."""
import ast
from copy import deepcopy
import hashlib
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch

import heft_method
from h02_pair_preflight.common import sha
from schedules import validate_schedule
from . import construction
from .mock_fixtures import (TOY_FIXTURE_NAMES, make_toy_fixture,
                            constructor_fixture_sha256s, is_canonical_constructor_fixture)

CORE = Path(__file__).resolve().parents[1]
HEFT_SHA256 = "0ea5d95222938f430918d0109032a43a3ca3dcc115ffb879da49e79b83fda6a1"


class MockExpired(RuntimeError): pass


class MockBudget:
    def __init__(self, remaining=None): self.remaining, self.checks = remaining, 0
    def check(self):
        self.checks += 1
        if self.remaining is not None and self.checks > self.remaining:
            raise MockExpired("mock root expired")


def _dump(function, *, normalize=False):
    tree = ast.parse(inspect.getsource(function))
    if normalize:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "build_deadline_candidate":
                node.name = "build_heft_candidate"
            if isinstance(node, ast.Name) and node.id == "deadline_ranks":
                node.id = "upward_ranks"
    return ast.dump(tree, include_attributes=False)


def _add_unused(instance):
    modes = deepcopy(instance["stage_modes"]["Long"])
    for mode in modes:
        mode["shared_stage_id"] = "Unused"
        mode["mode_id"] = "Unused@" + mode["unit_id"] + ":" + mode["opp_id"]
    instance["stage_modes"]["Unused"] = modes


class DeadlineConstructionTests(unittest.TestCase):
    def test_original_core_source_is_unchanged(self):
        self.assertEqual(hashlib.sha256((CORE / "heft_method.py").read_bytes()).hexdigest(), HEFT_SHA256)

    def test_private_constructor_ast_changes_only_name_and_priority_call(self):
        self.assertEqual(_dump(heft_method.build_heft_candidate),
                         _dump(construction.build_deadline_candidate, normalize=True))

    def test_fixture_whitelist_has_only_explicit_mock_hashes(self):
        self.assertEqual(len(constructor_fixture_sha256s()), len(TOY_FIXTURE_NAMES))
        for name in TOY_FIXTURE_NAMES:
            instance = make_toy_fixture(name)
            self.assertTrue(is_canonical_constructor_fixture(instance))
            self.assertNotIn("conductance_W_per_K", instance["platform"])
            self.assertNotIn("heat_capacity_J_per_K", instance["platform"])
            self.assertTrue(instance["id"].startswith("MOCK_ONLY_DF_"))
        instance = make_toy_fixture(); instance["window_ms"] = "31"
        self.assertFalse(is_canonical_constructor_fixture(instance))

    def test_deadline_ready_priority_keeps_original_rank_values(self):
        instance = make_toy_fixture()
        old_ranks, old, error = heft_method.upward_ranks(instance)
        ranks, priority, failure = construction.deadline_ranks(instance)
        self.assertIsNone(error); self.assertIsNone(failure)
        self.assertEqual(old, ["Long", "Urgent"])
        self.assertEqual(priority, ["Urgent", "Long"])
        self.assertEqual(ranks, old_ranks)

    def test_ready_requirement_overrides_deadline_order(self):
        instance = make_toy_fixture()
        scene = instance["scenarios"][0]
        by_shared = {s["shared_stage_id"]: s["id"] for s in scene["stage_instances"]}
        scene["dependencies"] = [[by_shared["Long"], by_shared["Urgent"]]]
        ranks, priority, failure = construction.deadline_ranks(instance)
        self.assertIsNone(failure); self.assertEqual(priority, ["Long", "Urgent"])
        self.assertEqual(ranks, heft_method.upward_ranks(instance)[0])

    def test_equal_deadline_uses_original_descending_rank(self):
        instance = make_toy_fixture()
        for request in instance["scenarios"][0]["requests"]: request["deadline_ms"] = "30"
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Long", "Urgent"])

    def test_equal_deadline_and_rank_uses_identity(self):
        instance = make_toy_fixture()
        for request in instance["scenarios"][0]["requests"]: request["deadline_ms"] = "30"
        for mode in instance["stage_modes"]["Urgent"]:
            mode["duration_ms"] = "10" if mode["opp_id"] == "H" else "11"
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Long", "Urgent"])

    def test_uses_absolute_not_relative_deadline(self):
        instance = make_toy_fixture()
        for request in instance["scenarios"][0]["requests"]:
            urgent = request["application"] == "Urgent"
            request.update(release_ms="10" if urgent else "0", deadline_ms="16" if urgent else "15",
                           relative_deadline_ms="6" if urgent else "15")
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Long", "Urgent"])

    def test_earliest_associated_deadline_across_scenes(self):
        instance = make_toy_fixture()
        for request in instance["scenarios"][0]["requests"]: request["deadline_ms"] = "30"
        other = deepcopy(instance["scenarios"][0]); other["id"] = "toy2"
        for request in other["requests"]:
            request["id"] = request["id"].replace("toy:", "toy2:")
            request["stage_instance_ids"] = [s.replace("toy:", "toy2:") for s in request["stage_instance_ids"]]
            if request["application"] == "Urgent": request["deadline_ms"] = "3"
        for stage in other["stage_instances"]:
            stage["id"] = stage["id"].replace("toy:", "toy2:")
            stage["request_id"] = stage["request_id"].replace("toy:", "toy2:")
        instance["scenarios"].append(other)
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Urgent", "Long"])

    def test_earliest_associated_deadline_across_request_copies(self):
        instance = make_toy_fixture(); scene = instance["scenarios"][0]
        for request in scene["requests"]:
            request["deadline_ms"] = "30" if request["application"] == "Urgent" else "10"
        original = next(r for r in scene["requests"] if r["application"] == "Urgent")
        other = deepcopy(original); other["id"] += ":copy2"; other["deadline_ms"] = "5"
        old_stage = next(s for s in scene["stage_instances"] if s["shared_stage_id"] == "Urgent")
        new_stage = deepcopy(old_stage); new_stage["id"] += ":copy2"; new_stage["request_id"] = other["id"]
        other["stage_instance_ids"] = [new_stage["id"]]
        scene["requests"].append(other); scene["stage_instances"].append(new_stage)
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Urgent", "Long"])

    def test_unused_catalog_identity_receives_window_priority(self):
        instance = make_toy_fixture(); _add_unused(instance)
        ranks, priority, failure = construction.deadline_ranks(instance)
        self.assertIsNone(failure); self.assertEqual(set(ranks), {"Long", "Urgent", "Unused"})
        self.assertEqual(priority, ["Urgent", "Long", "Unused"])
        # Unused and referenced-at-window identities legitimately tie by rank/id.
        for mode in instance["stage_modes"]["Unused"]: mode["duration_ms"] = "20"
        self.assertEqual(construction.deadline_ranks(instance)[1], ["Urgent", "Unused", "Long"])

    def test_original_cycle_failure_is_preserved(self):
        instance = make_toy_fixture(); scene = instance["scenarios"][0]
        a, b = [s["id"] for s in scene["stage_instances"]]
        scene["dependencies"] = [[a, b], [b, a]]
        self.assertEqual(construction.deadline_ranks(instance), heft_method.upward_ranks(instance))

    def test_priority_budget_exhaustion_propagates(self):
        with self.assertRaises(MockExpired): construction.deadline_ranks(make_toy_fixture(), MockBudget(0))

    def test_priority_input_is_immutable(self):
        instance = make_toy_fixture(); before = deepcopy(instance)
        construction.deadline_ranks(instance)
        self.assertEqual(instance, before)

    def test_mock_gap_old_constructor_fails_new_constructor_is_legal(self):
        instance = make_toy_fixture(); before = sha(instance)
        old = heft_method.build_heft_candidate(instance, MockBudget())
        new = construction.build_deadline_candidate(instance, MockBudget())
        self.assertIsNone(old["candidate"])
        self.assertEqual(new["status"], "COMPLETE_LEGAL_CANDIDATE")
        checked = validate_schedule(instance, new["candidate"])
        self.assertEqual(checked["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")
        self.assertEqual(checked["thermal_status"], "NOT_EVALUATED")
        rows = {r["shared_stage_id"]: r for r in checked["scenes"]["toy"]["rows"]}
        self.assertEqual(rows["Urgent"]["end_ms"], "2")
        self.assertEqual(rows["Long"]["end_ms"], "12")
        self.assertEqual(sha(instance), before)

    def test_single_stage_mock_keeps_insertion_and_output(self):
        instance = make_toy_fixture("single")
        self.assertEqual(heft_method.build_heft_candidate(instance)["candidate"],
                         construction.build_deadline_candidate(instance)["candidate"])

    def test_mock_two_copies_use_same_unit_and_cover_every_execution(self):
        instance = make_toy_fixture("two_copies")
        built = construction.build_deadline_candidate(instance)
        self.assertEqual(built["status"], "COMPLETE_LEGAL_CANDIDATE")
        rows = built["candidate"]["scenes"]["toy"]
        self.assertEqual(len(rows), 2); self.assertEqual({r["unit"] for r in rows}, {"CPU1"})
        self.assertEqual(len({r["stage_id"] for r in rows}), 2)
        self.assertEqual(validate_schedule(instance, built["candidate"])["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_mock_two_cpu_domain_has_complete_legal_candidate(self):
        instance = make_toy_fixture("two_cpus")
        for function in (heft_method.build_heft_candidate, construction.build_deadline_candidate):
            built = function(instance, MockBudget())
            self.assertEqual(built["status"], "COMPLETE_LEGAL_CANDIDATE")
            self.assertEqual(validate_schedule(instance, built["candidate"])["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_overrides_in_mock_single_stage_are_identical(self):
        instance = make_toy_fixture("single"); sid = instance["scenarios"][0]["stage_instances"][0]["id"]
        options = dict(deployment_override={"Only": "CPU1"}, opp_override={("toy", sid): "L"},
                       start_floor={("toy", sid): "2"})
        old = heft_method.build_heft_candidate(instance, **options)
        new = construction.build_deadline_candidate(instance, **options)
        self.assertEqual(old["candidate"], new["candidate"])
        self.assertEqual(new["candidate"]["scenes"]["toy"][0]["start_ms"], "2")
        self.assertEqual(new["candidate"]["scenes"]["toy"][0]["opp"], "L")

    def test_mock_constructor_budget_exhaustion_propagates(self):
        with self.assertRaises(MockExpired):
            construction.build_deadline_candidate(make_toy_fixture("single"), MockBudget(0))


if __name__ == "__main__": unittest.main()
