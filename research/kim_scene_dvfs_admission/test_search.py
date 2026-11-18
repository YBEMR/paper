"""Toy search oracles using tiny action spaces; no target workload is executed."""
from itertools import product
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import run
from joint_thermal import SAFE, VIOLATION, UNRESOLVED


class ToyAction:
    def __init__(self, transition):
        self.transition = transition

    def batch(self, entries):
        result = [self.transition(float(t[0])) for t in entries]
        costs, exits, states = zip(*result)
        return np.asarray(costs), np.repeat(np.asarray(exits)[:, None], 4, axis=1), np.asarray(states)


def schedules(tables):
    return [[SimpleNamespace(deadline_feasible=k is not None, requests=(0,), min_slack_ns=1)
             for k in table] for table in tables]


class ToySearchTests(unittest.TestCase):
    def test_reset_and_continuous_decisions(self):
        # Two consecutive hot stages breach the limit. Cool resets the toy
        # state, so the cheapest safe four-stage schedule alternates.
        hot = ToyAction(lambda t: (1., t+2., SAFE if t+2. <= 33. else VIOLATION))
        cool = ToyAction(lambda t: (3., 30., SAFE))
        tables = [[hot, cool] for _ in range(4)]
        with patch.multiple(run, N=2, SIZE=16, OPPS=["HOT", "COOL"], INITIAL=np.full(4, 30.)):
            fixed, feasible, _, _ = run.fixed_selection(tables)
            local, costs, _ = run.local_selection(tables, schedules(tables), 25, "toy")
            joint, states, energies, prefix = run.joint_search(tables)
            self.assertEqual((fixed["code"], feasible, fixed["predicted_j"]), (15, 1, 12.))
            self.assertEqual((local["code"], local["predicted_j"], states[0]), (0, 4., 2))
            self.assertEqual((joint["code"], joint["predicted_j"]), (5, 8.))
            self.assertEqual(joint["opps"], ["HOT", "COOL", "HOT", "COOL"])
            self.assertEqual(prefix, [2, 4, 8, 16])
            diagnostics = run.compare_sets(costs, states, energies)
            self.assertEqual((diagnostics["both_feasible"], diagnostics["reset_only"]), (8, 8))
            self.assertEqual(diagnostics["both_feasible_lowest_reset_score"]["code"], 5)

    def test_cartesian_codes_and_failure_precedence(self):
        def action(scene, i):
            if (scene, i) == (1, 2):
                return None
            state = {(0, 2): VIOLATION, (2, 1): UNRESOLVED}.get((scene, i), SAFE)
            return ToyAction(lambda t: ((scene+1)*(i+1) + t, t+i, state))
        tables = [[action(scene, i) for i in range(3)] for scene in range(4)]
        names = ["low", "mid", "high"]
        with patch.multiple(run, N=3, SIZE=81, OPPS=names, INITIAL=np.zeros(4)):
            _, status, energy, prefixes = run.joint_search(tables)
            self.assertEqual(prefixes, [3, 6, 18, 54])
            for index, actions in enumerate(product(range(3), repeat=4)):
                self.assertEqual(run.decode(index), [names[i] for i in actions])
                if actions[1] == 2:
                    self.assertEqual(status[index], 0)
                    self.assertTrue(np.isnan(energy[index]))
                    continue
                expected = 2 if actions[0] == 2 else (3 if actions[2] == 1 else 1)
                cost = sum((scene+1)*(i+1)+sum(actions[:scene]) for scene, i in enumerate(actions))
                self.assertEqual((status[index], energy[index]), (expected, cost))

    def test_no_choices_and_energy_ties(self):
        noop = ToyAction(lambda t: (0., t, SAFE))
        tables = [[noop, noop], [None, None], [noop, noop], [noop, noop]]
        with patch.multiple(run, N=2, SIZE=16, OPPS=["a","b"], INITIAL=np.zeros(4)):
            local, _, _ = run.local_selection(tables, schedules(tables), 25, "toy")
            self.assertIsNone(local)
            self.assertIsNone(run.fixed_selection(tables)[0])
            joint, states, energy, prefixes = run.joint_search(tables)
            self.assertIsNone(joint)
            self.assertEqual(prefixes, [2, 0, 0, 0])
            self.assertTrue(np.all(states == 0) and np.all(np.isnan(energy)))
            # Within tolerance, choose the earliest code even when encountered last.
            tie = run.pick(np.array([5, 3, 1]), np.array([1., 1.+2*run.EPS, 1.+run.EPS/2]))
            self.assertEqual(tie["code"], 1)


if __name__ == "__main__":
    unittest.main()
