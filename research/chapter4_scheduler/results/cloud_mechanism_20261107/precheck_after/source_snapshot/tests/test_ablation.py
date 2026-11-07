"""Artificial switch isolation checks; no scientific backends or input."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from research.chapter4_scheduler.blocking import method
from research.chapter4_scheduler.blocking.tests.test_blocking_method import crossing_input
from research.chapter4_scheduler.tests.test_graph_core import Budget


class BlockingAblationTests(TestCase):
    def collect(self, enabled):
        _, instance, incumbent = crossing_input()
        before = deepcopy((instance, incumbent))
        diagnostics, bases = [], []
        reconstruct = method.core.reconstruct
        def observed(*args, **kwargs):
            if kwargs.get("extra_resource_edge") is None:
                bases.append((args[2], deepcopy(args[3:]), kwargs["orientation"], kwargs["template"]))
            return reconstruct(*args, **kwargs)
        with patch.object(method.core, "reconstruct", side_effect=observed), \
                patch.object(method, "energy_targets", wraps=method.energy_targets) as targets:
            packets = list(method.candidate_packets(instance, incumbent, Budget(100000),
                diagnostics=diagnostics, **({} if enabled is None else {"allow_blocking_edges": enabled})))
        self.assertEqual((instance, incumbent), before)
        self.assertEqual(targets.call_count, 1)
        return packets, diagnostics, bases

    def test_default_and_explicit_enabled_are_identical(self):
        self.assertEqual(self.collect(None), self.collect(True))

    def test_switch_preserves_base_skeleton_generation_and_order(self):
        on, on_d, on_b = self.collect(True)
        off, off_d, off_b = self.collect(False)
        self.assertEqual(on_b, off_b)
        self.assertEqual([d for d in on_d if d["extra_resource_edge"] is None], off_d)
        self.assertTrue(any(p["additional_reversed_edges"] for p in on))
        self.assertFalse(any(p["additional_reversed_edges"] for p in off))
        common = {method.digest(p["candidate"]) for p in off}
        self.assertEqual([method.digest(p["candidate"]) for p in on
                          if method.digest(p["candidate"]) in common],
                         [method.digest(p["candidate"]) for p in off])

    def test_disabled_switch_never_requests_an_extra_edge(self):
        _, instance, incumbent = crossing_input()
        with patch.object(method.core, "blocking_edges", side_effect=AssertionError("OFF_MUST_NOT_REPAIR")):
            list(method.candidate_packets(instance, incumbent, Budget(100000), allow_blocking_edges=False))

    def test_non_boolean_switch_rejected(self):
        _, instance, incumbent = crossing_input()
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                list(method.candidate_packets(instance, incumbent, Budget(100000), allow_blocking_edges=value))
