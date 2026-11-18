"""Toy round trips for the event-only archive, including past-window draining."""
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive import Ledger, iter_schedules
from events import Request, Stage, simulate


class ArchiveChecks(unittest.TestCase):
    def test_lossless_timeline_and_corruption(self):
        jobs = [Request("first", 0, 0, 7), Request("other", 1, 0, 7), Request("second", 0, 1, 8)]
        chains = {
            0: [Stage("pre", "CPU0", 1, 0.31), Stage("infer", "GPU", 9, 2.77),
                Stage("push", "XFER", 1, 0.1)],
            1: [Stage("pre", "CPU1", 1, 0.31), Stage("infer", "DLA1", 3, 1.15)],
        }
        result = simulate(jobs, chains, 8)
        self.assertTrue(result.unfinished_ids)
        store = Ledger()
        store.add("toy", jobs, result)
        with self.assertRaises(ValueError):
            store.add("toy", jobs, result)
        with TemporaryDirectory() as folder:
            first = store.save(folder)
            (name, decoded), = iter_schedules(folder)
            self.assertEqual(name, "toy")
            self.assertEqual(decoded["window_ns"], 8)
            self.assertEqual(decoded["rows"], [asdict(r) for r in result.rows])
            self.assertEqual(decoded["requests"], [dict(asdict(r), completion_ns=result.completions_ns[r.id])
                                                   for r in jobs])
            second = store.save(folder)
            self.assertEqual(first, second)
            path = Path(folder) / "ledger" / first["shards"][0]["name"]
            path.write_bytes(path.read_bytes()[:-1] + b"!")
            with self.assertRaises(ValueError):
                list(iter_schedules(folder))

    def test_empty_workload(self):
        store = Ledger()
        store.add("empty", [], simulate([], {}, 100))
        with TemporaryDirectory() as folder:
            store.save(folder)
            self.assertEqual(list(iter_schedules(folder)),
                             [("empty", dict(window_ns=100, requests=[], rows=[]))])


if __name__ == "__main__":
    unittest.main()
