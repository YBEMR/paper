"""Pure adapter/bookkeeping tests; no scientific thermal evaluator is called."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import experiment as exp


class FakeKernel:
    def __init__(self, cost, increment=0., violates=False):
        self.cost, self.increment, self.violates = cost, increment, violates

    def batch(self, entries):
        # Deliberately inlet-dependent energy checks that prefixes inherit state.
        return (np.full(len(entries), self.cost)+entries[:, 0]*0.01,
                entries+self.increment,
                np.full(len(entries), 0 if self.violates else 1, dtype=np.int8))


class AdapterTests(unittest.TestCase):
    def test_input_view_restores_even_when_evaluator_raises(self):
        original = exp.events.FROZEN
        view = deepcopy(original)
        view["deployments"] = {"fixture": {}}
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            with exp.deployment_view(view):
                self.assertIs(exp.events.FROZEN, view)
                raise RuntimeError("fixture")
        self.assertIs(exp.events.FROZEN, original)

    def test_catalog_order_must_cover_domain_once_with_historical_controls(self):
        frozen = {"deployments": {key: {} for key in ("A", "C", "D0", "D1")}}
        with patch("catalog.search_order", return_value=["A", "C", "D1", "D0"]):
            self.assertEqual(exp.deployment_order(frozen), ["A", "C", "D1", "D0"])
        with patch("catalog.search_order", return_value=["A", "C", "D0", "D0"]):
            with self.assertRaises(ValueError):
                exp.deployment_order(frozen)

    def test_reference_search_covers_all_codes_without_resetting_state(self):
        tables = []
        for phase in range(4):
            row = [None]*exp.N
            row[0] = FakeKernel(1, increment=1)
            row[2] = FakeKernel(3, increment=2, violates=(phase==2))
            tables.append(row)
        winner, states, energy, depths = exp.joint.joint_search(tables)
        self.assertEqual(depths, [2, 4, 8, 16])
        self.assertEqual(int(np.sum(states!=0)), 16)
        self.assertEqual(int(np.sum(states==1)), 8)
        self.assertEqual(int(np.sum(states==2)), 8)
        self.assertEqual(winner["code"], 0)
        inlet = exp.joint.INITIAL[0]
        self.assertAlmostEqual(winner["predicted_j"], 4+0.01*(4*inlet+6))
        for code in np.flatnonzero(states):
            self.assertTrue(np.isfinite(energy[code]))
        self.assertTrue(np.all(np.isnan(energy[states==0])))

    def test_energy_ties_are_deterministic(self):
        options = [dict(deployment="Z", code=0, predicted_j=1.),
                   dict(deployment="A", code=2, predicted_j=1.+0.5e-9),
                   dict(deployment="A", code=1, predicted_j=1.+0.2e-9)]
        self.assertEqual((exp.choose(options)["deployment"], exp.choose(options)["code"]), ("A", 1))
        self.assertIsNone(exp.choose([]))


if __name__ == "__main__":
    unittest.main()
