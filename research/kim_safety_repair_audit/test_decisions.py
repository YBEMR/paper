"""Small synthetic branch tests for the first-hit budget and one-scene repairs."""
import unittest
from unittest.mock import patch
import numpy as np
import runner


class RepairMechanics(unittest.TestCase):
    def test_neighborhood_changes_exactly_one_scene(self):
        seed=runner.choice("C",0,0.)
        scores={d:np.zeros((4,27)) for d in "AC"}
        ids,_=runner.enumerate_checks("local",seed,scores)
        self.assertEqual(len(set(ids)),104)
        self.assertTrue(all(k>=27**4 for k in ids))
        self.assertTrue(all(sum(x!=0 for x in runner.digits(k%(27**4)))==1 for k in ids))
        scores["C"][0,1:]=np.inf
        other,_=runner.enumerate_checks("local",seed,scores)
        self.assertEqual(len(other),78)

    def test_first_hit_budget_and_full_neighborhood_minimum(self):
        seed=runner.choice("A",0,0.)
        options=(np.array([1,2,3]),np.array([1.,2.,3.]))
        def answer(d,code,sched,kw):
            return (4.-code,"VIOLATION" if code==1 else "SAFE",np.full(4,30.))
        with patch.object(runner,"enumerate_checks",return_value=options), patch.object(runner,"cached_replay",side_effect=answer):
            args=(seed,None,None,None,{"energy_j":1.})
            ranked,_=runner.compare_repair("ranked",*args)
            self.assertEqual((ranked["additional_full_replays"],ranked["first_safe"]["code"]),(2,2))
            local,_=runner.compare_repair("local",*args)
            self.assertEqual((local["additional_full_replays"],local["best_examined"]["code"]),(3,3))
            with patch.object(runner,"RANK_BUDGET",1):
                cap,_=runner.compare_repair("ranked",*args)
                self.assertEqual((cap["stopping_reason"],cap["first_safe"]),("BUDGET",None))
