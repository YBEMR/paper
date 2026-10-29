"""Injected filesystem faults; all lifecycle children and workloads are manual fakes."""

from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import persistence as disk, protocol as p, runtime as r
from . import test_runtime as lifecycle


def denied():
    return PermissionError(5, "injected WinError5-like persistence denial")


class PersistenceTests(unittest.TestCase):
    def test_write_once_never_replaces_and_refuses_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            with patch.object(disk.os, "replace", side_effect=AssertionError("no replacement")):
                disk.write_once(path, {"value": 1})
                original = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    disk.write_once(path, {"value": 2})
                self.assertEqual(original, path.read_bytes())

    def test_serialization_failure_leaves_no_empty_final_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            with self.assertRaises(ValueError):
                disk.write_once(path, {"clock": float("nan")})
            self.assertFalse(path.exists())

    def test_snapshots_do_not_touch_prior_open_files(self):
        with tempfile.TemporaryDirectory() as temp:
            log = disk.SnapshotLog(Path(temp) / "progress")
            first = log.append({"step": 1})
            before = first.read_bytes()
            with first.open("rb") as handle, patch.object(disk.os, "replace", side_effect=AssertionError("no replacement")):
                second = log.append({"step": 2})
                self.assertEqual(handle.read(), before)
            self.assertNotEqual(first, second)
            self.assertEqual(disk.read_latest_snapshot(log.directory), {"step": 2})
            with self.assertRaises(FileExistsError):
                disk.SnapshotLog(log.directory)

    def test_truncated_or_tampered_last_snapshot_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            log = disk.SnapshotLog(Path(temp) / "progress")
            log.append({"step": 1})
            last = log.append({"step": 2})
            intact = json.loads(last.read_bytes())
            for bad in ('{"partial":', json.dumps({**intact, "record": {"step": 9}})):
                with self.subTest(bad=bad):
                    last.write_text(bad, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        disk.read_latest_snapshot(log.directory)

    def test_missing_snapshot_sequence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            log = disk.SnapshotLog(Path(temp) / "progress")
            log.append({"step": 1})
            last = log.append({"step": 2})
            last.rename(last.with_name("000003.json"))
            with self.assertRaisesRegex(ValueError, "PROGRESS_SEQUENCE_GAP"):
                disk.read_latest_snapshot(log.directory)

    def test_third_status_failure_keeps_three_complete_and_stops(self):
        def fault(path, value, write):
            if path.parent.name == "status" and path.name == "000003.json":
                raise denied()
            return write(path, value)
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
            self.assertEqual((code, launched), (2, [0, 1, 2]))
            self.assertEqual(result["completed_conditions"], 3)
            self.assertEqual(result["state"], "STOPPED_EXCEPTION")
            self.assertEqual(sum(x["state"] == "NOT_RUN" for x in result["rows"]), 25)
            self.assertEqual(p.read_json(Path(temp) / "out/manual-2/result.json")["state"], "COMPLETE")
            progress = disk.read_latest_snapshot(Path(temp) / "out/status")
            self.assertEqual(progress["state"], "RUNNING")
            self.assertNotIn("summary", progress["rows"][0])

    def test_summary_write_failure_is_not_batch_success(self):
        def fault(path, value, write):
            if path.name == "summary.json":
                raise denied()
            return write(path, value)
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
        self.assertEqual(code, 2)
        self.assertEqual(len(launched), 28)
        self.assertEqual(result["completed_conditions"], 28)
        self.assertEqual(result["state"], "STOPPED_SUMMARY_ERROR")

    def test_terminal_failure_saved_separately_and_primary_never_retried(self):
        attempts = []
        def fault(path, value, write):
            if path.name == "batch_result.json":
                attempts.append(path)
                raise denied()
            return write(path, value)
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
            self.assertTrue((Path(temp) / "out/terminal_failure.json").exists())
            self.assertFalse((Path(temp) / "out/batch_result.json").exists())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(code, 2)
        self.assertEqual(result["state"], "STOPPED_TERMINAL_PERSISTENCE")
        self.assertEqual(result["completed_conditions"], 28)

    def test_terminal_flush_failure_marker_overrides_readable_complete_file(self):
        def fault(path, value, write):
            write(path, value)
            if path.name == "batch_result.json":
                raise denied()  # Simulates an error after primary bytes became readable.
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, _ = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
            self.assertEqual(p.read_json(Path(temp) / "out/batch_result.json")["state"], "COMPLETE")
            self.assertEqual(result["state"], "STOPPED_TERMINAL_PERSISTENCE")
            self.assertEqual(result["execution_state_before_persistence_failure"], "COMPLETE")
        self.assertEqual(code, 2)

    def test_all_terminal_storage_failure_emits_stderr_and_returns_failure(self):
        def fault(path, value, write):
            if path.name in {"batch_result.json", "terminal_failure.json"}:
                raise denied()
            return write(path, value)
        log = io.StringIO()
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp, redirect_stderr(log):
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(len(launched), 28)
        self.assertIn("STOPPED_TERMINAL_PERSISTENCE", log.getvalue())
        self.assertIn("terminal_record_saved", log.getvalue())

    def test_terminal_reader_needs_exit_code_and_never_ignores_bad_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            disk.write_once(base / "batch_result.json", {"state": "COMPLETE"})
            self.assertEqual(disk.read_terminal_record(base, exit_code=0)["state"], "COMPLETE")
            for code in (None, 2, True):
                with self.subTest(exit_code=code), self.assertRaises(ValueError):
                    disk.read_terminal_record(base, exit_code=code)
            failure = base / "terminal_failure.json"
            failure.write_text('{"partial":', encoding="utf-8")
            with self.assertRaises(ValueError):
                disk.read_terminal_record(base, exit_code=0)

    def test_final_write_crossing_batch_deadline_cannot_report_success(self):
        clock = [100.0]
        def fault(path, value, write):
            write(path, value)
            if path.name == "batch_result.json":
                clock[0] = 1901.0
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp, \
             patch.object(r.time, "perf_counter", side_effect=lambda: clock[0]):
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
        self.assertEqual(code, 2)
        self.assertEqual(result["state"], "STOPPED_BATCH_OVERRUN")
        self.assertEqual(result["elapsed_s"], 1801.0)
        self.assertEqual(len(launched), 28)

    def test_secondary_summary_failure_preserves_original_error(self):
        def fault(path, value, write):
            if path.parent.name == "status" and path.name == "000003.json":
                raise PermissionError("first: progress")
            if path.name == "summary.json":
                raise OSError("second: summary")
            return write(path, value)
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, storage_fault=fault)
        self.assertEqual(code, 2)
        self.assertEqual(launched, [0, 1, 2])
        self.assertEqual(result["final_error"]["error"], "first: progress")
        self.assertEqual(result["additional_errors"][0]["error"], "second: summary")

    def test_missing_worker_receipt_retains_latest_progress_counters(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, launched = lifecycle.RuntimeTests()._fake_batch(temp, missing_receipt_index=0)
        self.assertEqual((code, launched), (2, [0]))
        self.assertEqual(result["rows"][0]["counters"]["timetable_constructions"], 1)
        self.assertEqual(result["completed_conditions"], 0)

    def test_worker_progress_denial_stops_before_scheduling(self):
        from .test_condition import manual_case
        call, parent, comparisons = manual_case("S7")
        old = {call["parent_id"]: parent, **comparisons}
        original = disk.write_once
        def fault(path, value):
            if Path(path).parent.name == "progress" and Path(path).name == "000002.json":
                raise denied()
            return original(path, value)
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            directory = Path(temp) / "manual-worker"
            directory.mkdir()
            start = r.time.perf_counter()
            with patch.object(r, "validate_worker_context", return_value=({}, {}, call, directory, start, start+60)), \
                 patch.object(r, "load_evidence", side_effect=lambda inv, name: deepcopy(old[name])), \
                 patch.object(disk, "write_once", side_effect=fault), \
                 patch("research.chapter3_calibration_supplement.condition.evaluate_supplement", side_effect=AssertionError("must not schedule")):
                self.assertEqual(r.worker(temp, temp, 0, "manual-token"), 2)
            receipt = p.read_json(directory / "result.json")
            self.assertEqual(receipt["counters"]["timetable_constructions"], 0)
            self.assertEqual(receipt["error_type"], "PermissionError")

    def test_old_consumed_freeze_is_not_silently_reauthorized(self):
        frozen = p.PACKAGE / "results/frozen_supplement01"
        before = {x.name: p.sha(x) for x in frozen.iterdir() if x.is_file()}
        with self.assertRaisesRegex(ValueError, "FROZEN_SOURCE_DRIFT"):
            p.check_frozen(frozen)
        self.assertEqual(before, {x.name: p.sha(x) for x in frozen.iterdir() if x.is_file()})


if __name__ == "__main__":
    unittest.main()
