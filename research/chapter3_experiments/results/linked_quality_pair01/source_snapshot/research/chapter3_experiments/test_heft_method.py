"""Small structural and fake-receipt checks; no research run or heat simulation."""

from copy import deepcopy
from fractions import Fraction as F
import unittest

from heft_method import build_heft_candidate, run_heft, upward_ranks
from inputs import load_config
from run_milp_precheck import fixtures
from schedules import validate_schedule
from thermal import Exhausted


class CountingBudget:
    def __init__(self, limit=None):
        self.calls, self.limit = 0, limit

    def check(self):
        self.calls += 1
        if self.limit is not None and self.calls >= self.limit:
            raise Exhausted("injected-budget")


class HeftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixtures = fixtures(cls.config)

    def fixture(self, name="one_stage_energy"):
        return deepcopy(self.fixtures[name][0])

    def assert_legal(self, instance, candidate):
        self.assertEqual(validate_schedule(instance, candidate)["state"],
                         "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_rank_mean_fastest_per_unit_not_frequency_count(self):
        instance = self.fixture()
        modes = instance["stage_modes"]["A.pre"]
        expected = sum(min(F(mode["duration_ms"]) for mode in modes
                           if mode["unit_id"] == unit)
                       for unit in {mode["unit_id"] for mode in modes}) / 2
        instance["stage_modes"]["A.pre"].append({**deepcopy(modes[-1]), "duration_ms": "100000"})
        ranks, priority, error = upward_ranks(instance)
        self.assertIsNone(error)
        self.assertEqual(ranks["A.pre"], expected)
        self.assertEqual(priority, ["A.pre"])

    def test_rank_dependency_and_exact_insertion(self):
        instance = self.fixture("chain_fractional")
        for mode in instance["stage_modes"]["A.pre"]:
            mode["duration_ms"] = "21/2"
        result = build_heft_candidate(instance)
        self.assertEqual(result["shared_priority"], ["A.pre", "A.main"])
        rows = result["candidate"]["scenes"][instance["scenarios"][0]["id"]]
        by_shared = {row["stage_id"].split("::")[-1]: row for row in rows}
        self.assertEqual(by_shared["A.pre"]["start_ms"], "0")
        self.assertEqual(by_shared["A.main"]["start_ms"], "15")
        self.assert_legal(instance, result["candidate"])

    def test_shared_unit_chosen_once_across_scenes(self):
        instance = self.fixture("shared_two_scenes")
        candidate = build_heft_candidate(instance)["candidate"]
        self.assertEqual(len({row["unit"] for rows in candidate["scenes"].values()
                              for row in rows}), 1)
        self.assert_legal(instance, candidate)

    def test_repeated_requests_share_unit_and_use_deadline_order(self):
        instance = self.fixture()
        scene = instance["scenarios"][0]
        first = scene["requests"][0]
        second = deepcopy(first)
        second["id"] += "_early"
        second["deadline_ms"] = "12"
        original_stage = scene["stage_instances"][0]
        duplicate = deepcopy(original_stage)
        duplicate["id"] += "_early"
        duplicate["request_id"] = second["id"]
        second["stage_instance_ids"] = [duplicate["id"]]
        scene["requests"].append(second)
        scene["stage_instances"].append(duplicate)
        candidate = build_heft_candidate(instance,
            deployment_override={"A.pre": "CPU1"}, opp_rank=0)["candidate"]
        rows = {row["stage_id"]: row for row in candidate["scenes"][scene["id"]]}
        self.assertEqual(rows[duplicate["id"]]["start_ms"], "0")
        self.assertGreater(F(rows[original_stage["id"]]["start_ms"]), 0)
        self.assert_legal(instance, candidate)

    def test_branch_and_join_are_not_hardcoded_as_chain(self):
        instance = self.fixture("parallel_cpu")
        scene = instance["scenarios"][0]
        request = scene["requests"][0]
        original = deepcopy(scene["stage_instances"][0])
        stage_by_shared = {stage["shared_stage_id"]: stage for stage in scene["stage_instances"]}
        for shared in ("X", "Y"):
            stage = {**deepcopy(original), "id": original["id"] + shared,
                     "shared_stage_id": shared}
            scene["stage_instances"].append(stage)
            instance["stage_modes"][shared] = [{**deepcopy(mode), "shared_stage_id": shared,
                                               "mode_id": mode["mode_id"] + shared}
                                              for mode in instance["stage_modes"]["A.pre"]]
            stage_by_shared[shared] = stage
        scene["requests"] = [request]
        for stage in scene["stage_instances"]:
            stage["request_id"] = request["id"]
        request["stage_instance_ids"] = [stage["id"] for stage in scene["stage_instances"]]
        scene["dependencies"] = [[stage_by_shared[a]["id"], stage_by_shared[b]["id"]]
                                 for a, b in (("A.pre", "B.pre"), ("A.pre", "X"),
                                              ("B.pre", "Y"), ("X", "Y"))]
        candidate = build_heft_candidate(instance, opp_rank=0,
            deployment_override={"A.pre": "CPU1", "B.pre": "CPU2", "X": "CPU1", "Y": "CPU1"})["candidate"]
        self.assertIsNotNone(candidate)
        self.assert_legal(instance, candidate)

    def test_same_domain_same_opp_parallel_cpu(self):
        instance = self.fixture("parallel_cpu")
        candidate = build_heft_candidate(instance,
            deployment_override={"A.pre": "CPU1", "B.pre": "CPU2"}, opp_rank=0)["candidate"]
        self.assertEqual({row["start_ms"] for rows in candidate["scenes"].values()
                          for row in rows}, {"0"})
        self.assert_legal(instance, candidate)

    def test_different_opp_same_domain_waits_until_empty(self):
        instance = self.fixture("parallel_cpu")
        scene = instance["scenarios"][0]
        by_shared = {stage["shared_stage_id"]: stage["id"] for stage in scene["stage_instances"]}
        candidate = build_heft_candidate(instance,
            deployment_override={"A.pre": "CPU1", "B.pre": "CPU2"},
            opp_override={(scene["id"], by_shared["A.pre"]): "H",
                          (scene["id"], by_shared["B.pre"]): "L"})["candidate"]
        rows = candidate["scenes"][scene["id"]]
        self.assertEqual(len({row["start_ms"] for row in rows}), 2)
        self.assert_legal(instance, candidate)

    def test_npu_queue_is_serialized(self):
        instance = self.fixture("accelerator_queue")
        candidate = build_heft_candidate(instance,
            deployment_override={"A.main": "NPU0", "B.main": "NPU0"})["candidate"]
        rows = next(iter(candidate["scenes"].values()))
        self.assertEqual(len({row["start_ms"] for row in rows}), 2)
        self.assert_legal(instance, candidate)

    def test_idle_gap_insertion_does_not_append_every_stage(self):
        instance = self.fixture("parallel_cpu")
        scene = instance["scenarios"][0]
        by_app = {request["application"]: request for request in scene["requests"]}
        # Make the first-ranked B execute in the future; lower-ranked A may
        # still be inserted at zero in the same CPU's earlier idle interval.
        by_app["B"]["release_ms"] = "40"
        for mode in instance["stage_modes"]["B.pre"]:
            mode["duration_ms"] = "30"
        candidate = build_heft_candidate(instance,
            deployment_override={"A.pre": "CPU1", "B.pre": "CPU1"}, opp_rank=0)["candidate"]
        rows = {row["stage_id"].split("::")[-1]: row
                for row in next(iter(candidate["scenes"].values()))}
        self.assertEqual(rows["B.pre"]["start_ms"], "40")
        self.assertEqual(rows["A.pre"]["start_ms"], "0")
        self.assert_legal(instance, candidate)

    def test_explicit_domain_waiting_is_preserved(self):
        instance = self.fixture()
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {scene["id"]: {stage["id"]: ["45"]
                for stage in scene["stage_instances"]} for scene in instance["scenarios"]}}
        candidate = build_heft_candidate(instance)["candidate"]
        self.assertEqual(next(iter(candidate["scenes"].values()))[0]["start_ms"], "45")
        self.assert_legal(instance, candidate)

    def test_empty_start_domain_is_unresolved_not_infeasible(self):
        instance = self.fixture()
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {scene["id"]: {stage["id"]: []
                for stage in scene["stage_instances"]} for scene in instance["scenarios"]}}
        result = build_heft_candidate(instance)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "CONSTRUCTION_UNRESOLVED")
        self.assertEqual(result["optimality_status"], "NOT_PROVED")

    def test_shared_union_cycle_is_constructor_limitation(self):
        instance = self.fixture("chain_fractional")
        extra = deepcopy(instance["scenarios"][0])
        extra["id"] = "reverse"
        extra["dependencies"] = [list(reversed(edge)) for edge in extra["dependencies"]]
        instance["scenarios"].append(extra)
        result = build_heft_candidate(instance)
        self.assertEqual(result["reason"], "SHARED_IDENTITY_DEPENDENCY_CYCLE")
        self.assertIsNone(result["candidate"])

    def test_fallback_and_energy_pass_use_common_assess(self):
        instance = self.fixture()
        checked = []
        def assess(candidate, source):
            self.assert_legal(instance, candidate)
            checked.append((deepcopy(candidate), source))
            opp = next(iter(candidate["scenes"].values()))[0]["opp"]
            if opp == "H":
                return {"state": "THERMAL_VIOLATION"}
            cost = "2" if opp == "M" else "1"
            return {"state": "SAFE", "weighted_energy_J": [cost, cost],
                    "safe_upper_bound_J": cost}
        result = run_heft(instance, self.config, CountingBudget(), assess)
        self.assertEqual(result["status"], "BOUNDED_SEARCH_COMPLETED")
        self.assertTrue(any(source == "heft:fallback-opp-rank-1" for _, source in checked))
        self.assertEqual(result["local_base_energy_J"], ["1", "1"])
        self.assertGreaterEqual(result["local_accepted"], 1)

    def test_overlapping_intervals_do_not_force_energy_descent(self):
        instance = self.fixture()
        counter = []
        def assess(candidate, source):
            counter.append(source)
            return {"state": "SAFE", "weighted_energy_J": ["1", "2"],
                    "safe_upper_bound_J": "2"}
        result = run_heft(instance, self.config, CountingBudget(), assess)
        self.assertEqual(result["local_accepted"], 0)
        self.assertGreater(len(counter), 1)

    def test_no_safe_attempt_does_not_claim_infeasible(self):
        result = run_heft(self.fixture(), self.config, CountingBudget(),
                          lambda candidate, source: {"state": "UNRESOLVED"})
        self.assertEqual(result["status"], "NO_SAFE_CONSTRUCTED_WITNESS")
        self.assertEqual(result["infeasibility_status"], "NOT_PROVED")

    def test_budget_interrupt_is_not_swallowed(self):
        with self.assertRaises(Exhausted):
            build_heft_candidate(self.fixture(), CountingBudget(4))

    def test_deterministic_ties_and_no_input_mutation(self):
        instance = self.fixture("parallel_cpu")
        original = deepcopy(instance)
        self.assertEqual(build_heft_candidate(instance), build_heft_candidate(instance))
        self.assertEqual(instance, original)

    def test_bad_opp_rank_is_rejected(self):
        for rank in (-1, 3, True, "0"):
            with self.subTest(rank=rank), self.assertRaises(ValueError):
                build_heft_candidate(self.fixture(), opp_rank=rank)


if __name__ == "__main__":
    unittest.main(verbosity=2)
