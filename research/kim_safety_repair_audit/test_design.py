"""Structural checks only; no timing, temperature or energy evaluations."""
import unittest
from collections import Counter

from design import DESIGN, FROZEN, cases, image_ranks, make_scenes
from scene_events import split_workload


class PairedDesignTests(unittest.TestCase):
    def test_complete_preregistered_grid(self):
        grid = cases()
        self.assertEqual(len({c["id"] for c in grid}),12)
        self.assertEqual(sum(c["historic_repeat"] for c in grid),2)
        self.assertEqual({c["ambient"] for c in grid},{25,27.5,30})
        self.assertEqual({(c["order_id"],c["dwell_id"]) for c in grid},
                         {(o,d) for o in ("forward","reverse") for d in ("flat","alternating")})

    def test_old_event_stream_matches_both_regressions(self):
        old = split_workload("10s",25)
        for case in cases():
            if case["historic_repeat"]:
                self.assertEqual(make_scenes(case),old)

    def test_forward_reverse_pair_by_name_and_app(self):
        for dwell in ("flat","alternating"):
            selected = [c for c in cases() if c["dwell_id"] == dwell and c["ambient"] == 25]
            first, second = (make_scenes(c) for c in selected)
            self.assertEqual(first[-1].end_ns,10_040_000_000)
            self.assertEqual(second[-1].end_ns,10_040_000_000)
            def by_scene(scenes):
                return {s.name: list(s.requests) for s in scenes}
            self.assertEqual(by_scene(first),by_scene(second))
            self.assertEqual([s.name for s in first],[s.name for s in second][::-1])
            for batch in (first,second):
                all_jobs = [r for s in batch for r in s.requests]
                self.assertEqual(len({q.id for q in all_jobs}),500)
                self.assertEqual(Counter(q.app for q in all_jobs),Counter({i:125 for i in range(4)}))
                self.assertTrue(all(q.deadline_ns-q.release_ns == 40_000_000 for q in all_jobs))
                allowed = {tuple(edge) for edge in FROZEN["fsm"]["edges"]}
                self.assertTrue(all((x.name,y.name) in allowed for x,y in zip(batch,batch[1:])))
                ranks = image_ranks(batch)
                for app in range(4):
                    self.assertEqual([ranks[r.id] for r in all_jobs if r.app==app],
                                     [1,2]*62+[1])
                self.assertEqual(batch[-1].end_ns-batch[-1].service_end_ns,40_000_000)


if __name__ == "__main__":
    unittest.main()
