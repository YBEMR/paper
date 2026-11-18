"""Analytical toy schedules; no frozen deployment or energy comparison is run."""
import random
import unittest

import numpy as np

from events import PRIORITY, RESOURCES, Request, Stage, simulate


class EventChecks(unittest.TestCase):
    def test_idle_window_including_scene_boundary(self):
        out = simulate([], {}, 25, (0, 12, 25))
        np.testing.assert_array_equal(out.start_ns, (0, 12))
        np.testing.assert_array_equal(out.duration_ns, (12, 13))
        self.assertEqual(out.rows, [])
        self.assertTrue(out.deadline_feasible)
        self.assertFalse(out.active_w.any())
        self.assertFalse(out.transfer_w.any())
        self.assertEqual(out.idle_ns["CPU7"], 25)
        self.assertIsNone(out.min_slack_ns)

    def test_chain_transfer_and_equality_deadline(self):
        chain = [Stage("pre", "CPU0", 2, 1.5), Stage("boundary", "XFER", 1, 0.5),
                 Stage("inference", "GPU", 5, 2), Stage("output", "CPU0", 3, 1)]
        out = simulate([Request("r0", 0, 4, 15)], {0: chain}, 20, (8,))
        self.assertEqual([(r.start_ns, r.end_ns) for r in out.rows],
                         [(4,6), (6,7), (7,12), (12,15)])
        self.assertEqual(out.min_slack_ns, 0)
        self.assertTrue(out.deadline_feasible)
        self.assertEqual(out.completions_ns, {"r0":15})
        self.assertEqual(out.max_response_ns, 11)
        self.assertEqual(out.busy_ns["GPU"], 5)
        self.assertEqual(out.idle_ns["CPU0"], 15)
        np.testing.assert_allclose(out.duration_ns @ out.active_w, (6,10,0,0))
        self.assertAlmostEqual(out.duration_ns @ out.transfer_w, 0.5)

    def test_two_dlas_overlap_and_contention_on_each_is_exclusive(self):
        jobs = (Request("j0",0,0,30), Request("j1",1,0,30), Request("j2",2,0,30))
        chains = {0:[Stage("a","DLA0",4,1)], 1:[Stage("b","DLA1",7,2)],
                  2:[Stage("c","DLA0",3,3)]}
        out = simulate(jobs, chains, 40)
        self.assertEqual(out.completions_ns, {"j0":4,"j1":7,"j2":7})
        np.testing.assert_array_equal(out.active_w[0], [0,0,1,2])
        self.assertEqual((out.busy_ns["DLA0"], out.busy_ns["DLA1"]), (7,7))
        self.assertEqual(out.rows[-1].start_ns, 4)

    def test_same_time_arrivals_and_successors_compete_before_dispatch(self):
        # Newly released job has the higher app priority but older request
        # release wins the same-ready-time tie under the frozen accelerator rule.
        jobs = [Request("early",1,0,20), Request("new",0,3,20)]
        chains = {1:[Stage("p","CPU1",3,1), Stage("g","GPU",4,1)],
                  0:[Stage("g","GPU",2,1)]}
        out = simulate(jobs, chains, 25)
        self.assertEqual(out.completions_ns, {"early":7, "new":9})
        # Same ready and release time: priority order is 0,3,1,2.
        apps = (2,1,3,0)
        out = simulate([Request(str(i),i,0,9) for i in apps],
                       {i:[Stage("g","GPU",1,1)] for i in apps}, 10)
        self.assertEqual([row.request for row in out.rows], ["0","3","1","2"])

    def test_backlog_deadline_miss_and_drain_past_tail(self):
        jobs = [Request("old", 0, 0, 3), Request("new", 0, 3, 6)]
        out = simulate(jobs, {0:[Stage("g","GPU",5,2)]}, 7, (3,6))
        self.assertFalse(out.deadline_feasible)
        self.assertEqual(out.completions_ns, {"old":5, "new":10})
        self.assertEqual(out.last_completion_ns, 10)
        self.assertEqual(out.late_ids, ("old","new"))
        self.assertEqual(out.unfinished_ids, ("new",))
        self.assertEqual(out.min_slack_ns, -4)
        self.assertEqual(out.max_tardiness_ns, 4)
        self.assertEqual(out.stages_touching_after_window, 1)
        self.assertEqual(out.busy_ns["GPU"], 7)
        self.assertEqual(list(out.start_ns), [0,3,5,6])
        self.assertEqual(out.duration_ns @ out.active_w[:,1], 14)

    def test_two_cpu_cores_and_one_copy_engine(self):
        chains = {i:[Stage("pre",f"CPU{i}",2,1.5),Stage("handoff","XFER",2,1)]
                  for i in (0,1)}
        jobs = [Request(str(i),i,0,10) for i in (0,1)]
        out = simulate(jobs,chains,10)
        self.assertEqual(out.active_w[0,0], 3)
        self.assertEqual(out.completions_ns, {"0":4, "1":6})
        self.assertEqual(out.transfer_w.max(), 1)
        self.assertEqual(out.busy_ns["XFER"], 4)

    def test_reject_malformed_inputs(self):
        one = Request("r",0,0,3)
        good = {0:[Stage("g","GPU",2,1)]}
        for jobs, chains, bounds in [
            ([one,one],good,()), ([Request("r",0,1,0)],good,()), ([one],good,(9,)),
            ([one],{0:[Stage("wrong","CPU1",2,1)]},()), ([one],{0:[Stage("g","GPU",0,1)]},()),
            ([one],{0:[Stage("g","GPU",2,-1)]},()),
        ]:
            with self.subTest(chains=chains,jobs=jobs), self.assertRaises(ValueError):
                simulate(jobs,chains,5,bounds)

    def test_event_results_match_independent_integer_tick_oracle(self):
        # Small integer workloads allow direct unit-step execution with no
        # finish-event heap or window activity builder.
        rng = random.Random(371)
        for iteration in range(12):
            apps = (0,1,2)
            chains = {a:[Stage("pre",f"CPU{a}",rng.randint(1,3),1),
                         Stage("transfer","XFER",rng.randint(1,3),0.5),
                         Stage("run",rng.choice(("DLA0","DLA1","GPU")),rng.randint(1,4),2)]
                      for a in apps}
            jobs = [Request(f"j{i}",rng.choice(apps),rng.randint(0,8),22) for i in range(8)]
            out = simulate(jobs,chains,24,(5,15))
            positions = [0]*len(jobs)
            ready_times = [r.release_ns for r in jobs]
            active = {}
            complete = {}
            busy = dict.fromkeys(RESOURCES,0)
            for t in range(100):
                for unit, (i, finish) in list(active.items()):
                    if t == finish:
                        del active[unit]
                        positions[i] += 1
                        ready_times[i] = t
                        if positions[i] == len(chains[jobs[i].app]):
                            complete[jobs[i].id] = t
                executing = {i for i, _ in active.values()}
                for unit in RESOURCES:
                    if unit in active:
                        continue
                    options = []
                    for i, job in enumerate(jobs):
                        pos = positions[i]
                        if i in executing or ready_times[i] > t or pos == len(chains[job.app]):
                            continue
                        stage = chains[job.app][pos]
                        if stage.resource == unit:
                            options.append((ready_times[i], job.release_ns, PRIORITY[job.app],
                                            pos, job.id, i))
                    if options:
                        i = min(options)[-1]
                        duration = chains[jobs[i].app][positions[i]].duration_ns
                        active[unit] = (i,t + duration)
                        executing.add(i)
                if t < 24:
                    for unit in active:
                        busy[unit] += 1
                if len(complete) == len(jobs):
                    break
            with self.subTest(iteration=iteration):
                self.assertEqual(out.completions_ns, complete)
                self.assertEqual(out.busy_ns,busy)


if __name__ == "__main__":
    unittest.main()
