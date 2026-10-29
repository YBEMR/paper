"""Pure small fixtures: never C01--C24 and never a time/thermal scheduler."""

from copy import deepcopy
import unittest

from .topology import TopologyError, make_topology, validate_graph, _degree_capacity


def fixture_settings():
    return {"algorithm_version": "layered-forward-v1", "layer_rule": "ceil_sqrt_balanced",
            "output_rule": "all_last_layer", "edge_target_multiplier": "3/2",
            "edge_target_rounding": "half_up", "edge_cap_rule": "max_bipartite_degree_capacity",
            "max_indegree": 3, "max_outdegree": 3, "max_attempts": 64,
            "small_two_node_rule": "chain", "branch_rule": "first_diamond_then_tail_chain",
            "reject_total_reachability_order": True, "reject_branch_template": True}


class TopologyTests(unittest.TestCase):
    def graph(self, n, kind):
        return make_topology([f"n{i:02}" for i in range(n)], kind,
                             key="MANUAL_FIXTURE_topology", settings=fixture_settings())

    def test_settings_are_all_explicit(self):
        for field in fixture_settings():
            with self.subTest(field=field):
                settings = fixture_settings()
                del settings[field]
                with self.assertRaises(TopologyError):
                    make_topology(["a", "b"], "serial", key="manual", settings=settings)

    def test_two_node_random_exception_is_recorded(self):
        result = self.graph(2, "layered")
        self.assertEqual(result["edges"], [["n00", "n01"]])
        self.assertEqual(result["trace"]["small_graph_exception"], "TWO_NODE_CHAIN")

    def test_four_node_diamond_is_real_branch(self):
        result = self.graph(4, "branch_join")
        self.assertEqual(result["edges"], [["n00", "n01"], ["n00", "n02"],
                                            ["n01", "n03"], ["n02", "n03"]])
        self.assertIn(["n01", "n02"], result["trace"]["validation"]["incomparable_pairs"])

    def test_branch_growth_preserves_prefix_edges(self):
        graphs = [self.graph(n, "branch_join") for n in (2, 4, 8, 16)]
        for smaller, bigger in zip(graphs, graphs[1:]):
            self.assertLessEqual({tuple(e) for e in smaller["edges"]},
                                 {tuple(e) for e in bigger["edges"]})

    def test_serial_growth_and_output(self):
        result = self.graph(8, "serial")
        self.assertEqual(len(result["edges"]), 7)
        self.assertEqual(result["required_outputs"], ["n07"])
        self.assertEqual(result["trace"]["validation"]["incomparable_pairs"], [])

    def test_four_node_capacity_cap_is_explicit(self):
        result = self.graph(4, "layered")
        self.assertEqual(result["trace"]["layer_widths"], [2, 2])
        self.assertEqual(result["trace"]["raw_edge_target"], 5)
        self.assertEqual(result["trace"]["degree_layer_capacity"], 4)
        self.assertEqual(result["trace"]["edge_target"], 4)
        self.assertTrue(result["trace"]["capacity_capped"])
        self.assertEqual(len(result["edges"]), 4)
        self.assertEqual(len(result["required_outputs"]), 2)

    def test_eight_node_target_and_reproducibility(self):
        one = self.graph(8, "layered")
        self.assertEqual(one, self.graph(8, "layered"))
        self.assertEqual(one["trace"]["layer_widths"], [3, 3, 2])
        self.assertEqual(one["trace"]["raw_edge_target"], 11)
        self.assertEqual(len(one["edges"]), 11)
        self.assertTrue(one["trace"]["validation"]["incomparable_pairs"])

    def test_sixteen_node_degree_bound(self):
        result = self.graph(16, "layered")
        self.assertEqual(len(result["edges"]), 23)
        check = result["trace"]["validation"]
        self.assertLessEqual(check["maximum_indegree"], 3)
        self.assertLessEqual(check["maximum_outdegree"], 3)

    def test_bounded_failure_retains_every_attempt(self):
        settings = fixture_settings()
        settings.update(edge_target_multiplier="1/10", max_attempts=3)
        with self.assertRaises(TopologyError) as caught:
            make_topology(["a", "b", "c", "d"], "layered", key="manual", settings=settings)
        self.assertEqual(caught.exception.code, "BOUNDED_TOPOLOGY_ATTEMPTS_EXHAUSTED")
        attempts = caught.exception.details["trace"]["attempts"]
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all(row["state"] == "REJECTED" for row in attempts))

    def test_original_settings_are_not_mutated(self):
        settings = fixture_settings()
        before = deepcopy(settings)
        make_topology(["a", "b", "c", "d"], "layered", key="manual", settings=settings)
        self.assertEqual(before, settings)

    def test_invalid_nodes_and_undeclared_three_node_case(self):
        for nodes in (["a", "a"], ["a"], ["a", "b", "c"]):
            with self.subTest(nodes=nodes), self.assertRaises(TopologyError):
                make_topology(nodes, "layered", key="manual", settings=fixture_settings())

    def test_capacity_matches_exhaustive_four_node_edge_subsets(self):
        nodes = ["a", "b", "c", "d"]
        candidates = [(left, right) for left in nodes[:2] for right in nodes[2:]]
        for bound in (1, 2, 3):
            maximum = 0
            for mask in range(1 << len(candidates)):
                selected = [e for i, e in enumerate(candidates) if mask & (1 << i)]
                if all(sum(e[0] == node for e in selected) <= bound and
                       sum(e[1] == node for e in selected) <= bound for node in nodes):
                    maximum = max(maximum, len(selected))
            self.assertEqual(_degree_capacity(nodes, candidates, bound, bound), maximum)

    def test_validator_rejects_shortcut_chain(self):
        with self.assertRaises(TopologyError) as caught:
            validate_graph(["a", "b", "c", "d"],
                           [["a", "b"], ["b", "c"], ["c", "d"], ["a", "c"]], ["d"],
                           max_indegree=3, max_outdegree=3, layers=None,
                           require_nonchain=True, forbidden_edges=None)
        self.assertEqual(caught.exception.code, "REACHABILITY_IS_TOTAL_ORDER")

    def test_validator_rejects_cycle_missing_output_and_isolate(self):
        fixtures = [(["a", "b"], [["a", "b"], ["b", "a"]], ["b"]),
                    (["a", "b", "c"], [["a", "b"], ["a", "c"]], ["b"]),
                    (["a", "b", "c"], [["a", "b"]], ["b", "c"])]
        for nodes, edges, outputs in fixtures:
            with self.subTest(edges=edges), self.assertRaises(TopologyError):
                validate_graph(nodes, edges, outputs, max_indegree=3, max_outdegree=3,
                               layers=None, require_nonchain=False, forbidden_edges=None)

    def test_validator_rejects_backward_layers_and_exact_branch(self):
        for layers, forbidden in (([["b"], ["a"]], None),
                                  (None, [["a", "b"]])):
            with self.subTest(layers=layers), self.assertRaises(TopologyError):
                validate_graph(["a", "b"], [["a", "b"]], ["b"],
                               max_indegree=3, max_outdegree=3, layers=layers,
                               require_nonchain=False, forbidden_edges=forbidden)


if __name__ == "__main__":
    unittest.main()
