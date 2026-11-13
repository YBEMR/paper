"""Pure fake lifecycle checks; no native process, archived MAT, solver or heat.

Scratch files stay under this workspace's .runtime, never the default TEMP.
The real core transformation is covered separately by test_core.py; here the
worker seam receives a tiny hand-authored payload and fully mocked core API.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("k189_runner_under_pure_test", HERE / "run_once.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
SCRATCH = HERE.parents[2] / ".runtime/k189_runner_pure_tests"


class Clock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class PureRunnerTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="fake_", dir=SCRATCH)
        self.folder = Path(self.temp.name)
        self.native_guard = patch.object(runner.subprocess, "Popen", side_effect=AssertionError("NATIVE_PROCESS_FORBIDDEN"))
        self.native_popen = self.native_guard.start()

    def tearDown(self):
        self.native_guard.stop()
        self.temp.cleanup()

    def make_worker(self, *, solve_seconds=20, exitflag=1, returned_vector=None,
                    budget_valid=True, options_drift=False, startup_failure=False,
                    environment_drift=False, verify_failure=False, cleanup_failure=False,
                    cleanup_complete=True):
        clock = Clock()
        actual_budget_class = runner.RootBudget
        budget = actual_budget_class(300, clock=clock)
        out = self.folder / "out"
        runner.write_new(out / "declaration.json", {"mock_declaration_only": True})
        runner.write_new(out / "launch.claim.json", {
            "declaration_sha256": runner.sha(out / "declaration.json"), "mock_only": True})
        environment = {"version": "MOCK_VERSION", "release": "MOCK_RELEASE", "intlinprog_path": "MOCK_NO_NATIVE"}
        options = {"AbsoluteGapTolerance": 0, "RelativeGapTolerance": 0,
                   "ConstraintTolerance": 1e-9, "IntegerTolerance": 1e-6, "MaxTime": 299}
        declaration = {"original_ready": environment, "original_options": options,
                       "original_python_environment": {"mock_only": True}}
        original_key = (runner.OLD / "method/matlab/request_000001.mat").relative_to(runner.REPO).as_posix()
        declaration["source_files"] = {original_key: {"sha256": "MOCK_ORIGINAL_MAT_SHA"}}
        host = {"token_is_appcontainer": False, "matlab_processes": [],
                "physical_available_bytes": 8 * 1024**3, "commit_available_bytes": 8 * 1024**3,
                "disk_free_bytes": 8 * 1024**3, "mock_only": True}
        original = {"c": [2.0, 3.0], "A": [[1.0, 0.0]], "b": [1.0],
                    "Aeq": [], "beq": [], "lb": [0.0, -2.0], "ub": [1.0, 2.0],
                    "intcon": [0], "x0": [1.0, 0.5]}
        fixed = deepcopy(original)
        fixed["lb"][0] = fixed["ub"][0] = original["x0"][0]
        calls = {"load": [], "fix": [], "identity": [], "verify": [], "sessions": [], "solve": [], "close": 0}

        def load(path):
            calls["load"].append(str(path))
            clock.advance(1)
            payload = fixed if Path(path) == out / "matlab/request_000001.mat" else original
            return payload, {"mock_only": True, "new_model_built": False, "sha256": "MOCK_ORIGINAL_MAT_SHA"}

        def fix(payload):
            self.assertIs(payload, original)
            calls["fix"].append(payload)
            return fixed, {"mock_only": True, "only_actual_intcon_bounds_fixed": True}

        def identity(a, b):
            self.assertIs(a, original)
            self.assertIs(b, fixed)
            self.assertEqual({k: v for k, v in a.items() if k not in ("lb", "ub")},
                             {k: v for k, v in b.items() if k not in ("lb", "ub")})
            self.assertEqual(b["lb"], [1.0, -2.0])
            self.assertEqual(b["ub"], [1.0, 2.0])
            calls["identity"].append(True)
            return {"passed": True, "mock_only": True}

        def verify(vector, a, b, objective=None, *, require_objective=True):
            self.assertIs(a, original)
            self.assertIs(b, fixed)
            calls["verify"].append({"vector": list(vector), "objective": objective,
                                    "require_objective": require_objective, "at_s": budget.elapsed})
            clock.advance(.25)
            accepted = vector == original["x0"] and (not verify_failure or not require_objective)
            return {"accepted": accepted, "mock_only": True, "physical_safety_claim": False}

        core = SimpleNamespace(load_original_mat=Mock(side_effect=load),
            fix_actual_intcon=Mock(side_effect=fix),
            assert_only_fixed_integer_bounds_changed=Mock(side_effect=identity),
            verify_vector=Mock(side_effect=verify))

        class StartupError(RuntimeError):
            pass

        outer = self

        class FakeSession:
            def __init__(self, folder, **kwargs):
                if startup_failure:
                    error = StartupError("MOCK_CONSTRUCTOR_FAILURE")
                    error.matlab_cleanup = {"mock_only": True, "cleanup_status": "MOCK_CONSTRUCTOR_CLEANED"}
                    raise error
                self.environment = dict(environment)
                if environment_drift:
                    self.environment["release"] = "MOCK_DRIFT"
                self.counter = 0
                self.event_consumer = None
                self.cleanup = None
                self.budget = kwargs["budget"]
                self.kwargs = kwargs
                outer.assertIs(self.budget, budget)
                outer.assertEqual(kwargs["cut_max_iterations"], 10)
                outer.assertGreater(kwargs["total_budget_s"], 0)
                outer.assertLessEqual(kwargs["total_budget_s"], 300)
                calls["sessions"].append(self)
                clock.advance(2)

            def solve(self, payload, *, remaining_s, budget, x0):
                outer.assertIs(payload, fixed)
                outer.assertIs(budget, self.budget)
                outer.assertIs(x0, original["x0"])
                outer.assertEqual(payload["c"], original["c"])
                outer.assertEqual(payload["intcon"], original["intcon"])
                outer.assertEqual(payload["x0"], original["x0"])
                outer.assertEqual(remaining_s, budget.remaining)
                self.counter += 1
                calls["solve"].append({"payload": deepcopy(payload), "x0": list(x0),
                                       "remaining_s": remaining_s, "budget": budget})
                transport = out / "matlab/request_000001.mat"
                transport.parent.mkdir(parents=True, exist_ok=True)
                with transport.open("xb") as stream:
                    stream.write(b"MOCK_TRANSPORT_MARKER_ONLY_NOT_A_MAT_FILE")
                clock.advance(solve_seconds)
                native_options = dict(options, MaxTime=max(0, remaining_s - .5))
                if options_drift:
                    native_options["ConstraintTolerance"] = 1e-8
                return {"status": "SOLVED", "budget_valid": budget_valid, "exitflag": exitflag,
                        "x": list(original["x0"] if returned_vector is None else returned_vector),
                        "fval": 3.5, "options": native_options, "mock_only": True}

            def close(self):
                calls["close"] += 1
                clock.advance(.5)
                if cleanup_failure:
                    raise RuntimeError("MOCK_CLOSE_FAILURE")
                self.cleanup = {"mock_only": True, "observed_tree_verified_terminated": cleanup_complete,
                                "cleanup_status": "MOCK_CLOSED"}

        def cleanup_is_complete(receipt):
            if not isinstance(receipt, dict) or not receipt.get("mock_only"):
                return False
            return receipt.get("observed_tree_verified_terminated",
                               receipt.get("cleanup_status") == "MOCK_CONSTRUCTOR_CLEANED") is True

        bridge = SimpleNamespace(MatlabSession=FakeSession,
                                 cleanup_is_complete=Mock(side_effect=cleanup_is_complete))
        return SimpleNamespace(clock=clock, budget=budget, out=out, declaration=declaration,
            host=host, original=original, fixed=fixed, calls=calls, core=core, bridge=bridge)

    def run_worker(self, fixture):
        with patch.object(runner, "OUT", fixture.out), \
             patch.object(runner, "RootBudget", side_effect=lambda: fixture.budget), \
             patch.object(runner, "admission", return_value=fixture.declaration), \
             patch.object(runner, "context", return_value=fixture.host), \
             patch.object(runner, "check_python_environment", return_value={"mock_only": True, "passed": True}), \
             patch.object(runner, "bind_bridge", return_value=fixture.bridge) as bind, \
             patch.dict(sys.modules, {"core": fixture.core}):
            status = runner.worker()
        self.assertEqual(self.native_popen.call_count, 0)
        return status, runner.read(fixture.out / "method_return.json"), bind.call_count

    def test_root_budget_uses_one_absolute_deadline_and_clamps_remaining(self):
        clock = Clock(20)
        root = runner.RootBudget(300, clock=clock)
        self.assertEqual((root.start, root.deadline, root.remaining), (20, 320, 300))
        clock.advance(299)
        root.check()
        self.assertEqual(root.remaining, 1)
        clock.advance(1)
        with self.assertRaises(TimeoutError):
            root.check()
        clock.advance(9)
        self.assertEqual(root.remaining, 0)
        self.assertEqual(root.deadline, 320)

    def test_root_budget_phase_records_on_exception(self):
        clock = Clock()
        root = runner.RootBudget(clock=clock)
        with self.assertRaisesRegex(ValueError, "MOCK"):
            with root.phase("mock_phase"):
                clock.advance(2.5)
                raise ValueError("MOCK")
        self.assertEqual(root.records, [{"phase": "mock_phase", "start_s": 0, "end_s": 2.5}])

    def test_write_new_is_exclusive_and_preserves_original_bytes(self):
        path = self.folder / "receipt.json"
        runner.write_new(path, {"mock": "first"})
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            runner.write_new(path, {"mock": "second"})
        self.assertEqual(path.read_bytes(), original)

    def test_classify_numeric_success_is_not_safe_claim(self):
        self.assertEqual(runner.classify({"budget_valid": True, "status": "SOLVED", "exitflag": 1, "x": [1]},
                                         {"accepted": True}, True, True), "FIXED_CONFIGURATION_NUMERICALLY_ADMITTED")

    def test_classify_budget_dominates_x_and_native_status(self):
        for within, valid in ((False, True), (True, False), (False, False)):
            self.assertEqual(runner.classify({"budget_valid": valid, "status": "SOLVED", "exitflag": 1, "x": [1]},
                {"accepted": True}, within, True), "UNRESOLVED_BUDGET_OR_LATE")

    def test_classify_minus_two_is_admission_status_conflict(self):
        self.assertEqual(runner.classify({"budget_valid": True, "status": "SOLVED", "exitflag": -2, "x": []},
                                         None, True, True), "NUMERICAL_ADMISSION_STATUS_CONFLICT")

    def test_classify_nonempty_vector_required_even_numfeaspoints_positive(self):
        self.assertEqual(runner.classify({"budget_valid": True, "status": "SOLVED", "exitflag": 0,
                                         "x": [], "output": {"numfeaspoints": 99}}, None, True, True),
                         "UNRESOLVED_EMPTY_NATIVE_VECTOR")

    def test_classify_options_drift_and_rejected_vector(self):
        native = {"budget_valid": True, "status": "SOLVED", "exitflag": 1, "x": [1]}
        self.assertEqual(runner.classify(native, {"accepted": True}, True, False), "NATIVE_OPTIONS_DRIFT")
        self.assertEqual(runner.classify(native, {"accepted": False}, True, True), "NUMERICAL_VECTOR_REJECTED")

    def test_worker_uses_one_solve_same_root_original_c_intcon_x0_and_cleanup(self):
        fixture = self.make_worker()
        status, report, binds = self.run_worker(fixture)
        self.assertEqual((status, binds, len(fixture.calls["solve"]), fixture.calls["close"]), (0, 1, 1, 1))
        self.assertEqual(report["request_attempts"], 1)
        self.assertEqual(report["state"], "FIXED_CONFIGURATION_NUMERICALLY_ADMITTED")
        self.assertTrue(report["options_match_except_time"])
        self.assertTrue(report["cleanup"]["observed_tree_verified_terminated"])
        self.assertTrue(report["lifecycle_complete"])
        self.assertEqual(len(fixture.calls["verify"]), 2)
        self.assertEqual(len(fixture.calls["load"]), 2)
        self.assertTrue((fixture.out / "transport_identity.json").is_file())
        self.assertFalse(fixture.calls["verify"][0]["require_objective"])
        self.assertTrue(fixture.calls["verify"][1]["require_objective"])
        self.assertEqual((report["new_safe_or_U"], report["thermal_integrations"], report["complete_candidate_evaluations"]), (False, 0, 0))
        self.assertGreater(report["wall_including_cleanup_s"], report["method_elapsed_s"])

    def test_worker_late_native_x_is_not_numerically_admitted(self):
        fixture = self.make_worker(solve_seconds=301)
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 0)
        self.assertEqual(report["state"], "UNRESOLVED_BUDGET_OR_LATE")
        self.assertIsNone(report["numeric"])
        self.assertIsNone(report["numeric_admission_completed_s"])
        self.assertEqual(len(fixture.calls["verify"]), 1)
        self.assertEqual((len(fixture.calls["solve"]), fixture.calls["close"]), (1, 1))

    def test_worker_budget_invalid_native_x_is_not_admitted(self):
        fixture = self.make_worker(budget_valid=False)
        _, report, _ = self.run_worker(fixture)
        self.assertEqual(report["state"], "UNRESOLVED_BUDGET_OR_LATE")
        self.assertIsNone(report["numeric"])
        self.assertEqual(len(fixture.calls["verify"]), 1)

    def test_worker_minus_two_conflict_no_retry(self):
        fixture = self.make_worker(exitflag=-2, returned_vector=[])
        _, report, _ = self.run_worker(fixture)
        self.assertEqual(report["state"], "NUMERICAL_ADMISSION_STATUS_CONFLICT")
        self.assertEqual((len(fixture.calls["solve"]), fixture.calls["close"]), (1, 1))
        self.assertIsNone(report["numeric"])

    def test_worker_drifted_options_block_verification_of_returned_vector(self):
        fixture = self.make_worker(options_drift=True)
        _, report, _ = self.run_worker(fixture)
        self.assertEqual(report["state"], "NATIVE_OPTIONS_DRIFT")
        self.assertIsNone(report["numeric"])
        self.assertEqual(len(fixture.calls["verify"]), 1)

    def test_worker_numerical_rejection_preserves_raw_without_safe_claim(self):
        fixture = self.make_worker(verify_failure=True)
        _, report, _ = self.run_worker(fixture)
        self.assertEqual(report["state"], "NUMERICAL_VECTOR_REJECTED")
        self.assertFalse(report["numeric"]["accepted"])
        self.assertEqual(report["result"]["x"], fixture.original["x0"])
        self.assertFalse(report["new_safe_or_U"])

    def test_worker_constructor_failure_archives_exception_cleanup(self):
        fixture = self.make_worker(startup_failure=True)
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report["state"], "TECHNICAL_FAILURE")
        self.assertEqual(report["cleanup"]["cleanup_status"], "MOCK_CONSTRUCTOR_CLEANED")
        self.assertEqual(report["request_attempts"], 0)
        self.assertEqual(fixture.calls["solve"], [])
        self.assertFalse((fixture.out / "request.claim.json").exists())
        self.assertTrue(report["source_preserved"])

    def test_worker_environment_mismatch_closes_before_any_request(self):
        fixture = self.make_worker(environment_drift=True)
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report["state"], "TECHNICAL_FAILURE")
        self.assertEqual((fixture.calls["solve"], fixture.calls["close"]), ([], 1))
        self.assertEqual(report["request_attempts"], 0)

    def test_worker_cleanup_error_is_recorded_and_never_retries(self):
        fixture = self.make_worker(cleanup_failure=True)
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertIn("CLEANUP_ERROR", [row["type"] for row in report["errors"]])
        self.assertEqual((len(fixture.calls["solve"]), fixture.calls["close"]), (1, 1))

    def test_worker_unresolved_cleanup_preserves_numeric_receipt_but_fails_lifecycle(self):
        fixture = self.make_worker(cleanup_complete=False)
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report["state"], "FIXED_CONFIGURATION_NUMERICALLY_ADMITTED")
        self.assertTrue(report["numeric"]["accepted"])
        self.assertFalse(report["lifecycle_complete"])
        self.assertIn("CLEANUP_UNRESOLVED", [row["type"] for row in report["errors"]])
        self.assertEqual((len(fixture.calls["solve"]), fixture.calls["close"]), (1, 1))
        self.assertFalse(report["new_safe_or_U"])

    def test_worker_original_payload_hash_drift_stops_before_native(self):
        fixture = self.make_worker()
        key = next(iter(fixture.declaration["source_files"]))
        fixture.declaration["source_files"][key]["sha256"] = "MOCK_DIFFERENT_HASH"
        status, report, _ = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report["state"], "TECHNICAL_FAILURE")
        self.assertEqual(fixture.calls["sessions"], [])
        self.assertEqual(fixture.calls["solve"], [])
        self.assertEqual(report["request_attempts"], 0)

    def test_inspect_owned_distinguishes_alive_reused_exited_and_unresolved(self):
        class Gone(Exception):
            pass
        class Denied(Exception):
            pass
        def process(pid):
            if pid == 3:
                raise Gone()
            if pid == 4:
                raise Denied()
            return SimpleNamespace(create_time=lambda: 10 if pid == 1 else 99)
        fake = SimpleNamespace(Process=Mock(side_effect=process), NoSuchProcess=Gone, AccessDenied=Denied)
        with patch.dict(sys.modules, {"psutil": fake}):
            rows = runner.inspect_owned({(1, 10): True, (2, 10): True, (3, 10): True, (4, 10): True})
        self.assertEqual([row["state"] for row in rows],
                         ["ALIVE", "PID_REUSED_ORIGINAL_EXITED", "EXITED", "UNRESOLVED_ACCESS"])

    def test_stop_owned_never_kills_a_reused_pid(self):
        class Gone(Exception):
            pass
        class Denied(Exception):
            pass
        alive = SimpleNamespace(create_time=lambda: 10, kill=Mock())
        reused = SimpleNamespace(create_time=lambda: 99, kill=Mock())
        fake = SimpleNamespace(Process=Mock(side_effect=lambda pid: alive if pid == 1 else reused),
                               NoSuchProcess=Gone, AccessDenied=Denied)
        with patch.dict(sys.modules, {"psutil": fake}), patch.object(runner.time, "monotonic", return_value=0):
            actions = runner.stop_owned({(1, 10): True, (2, 10): True}, deadline=10)
        self.assertEqual(alive.kill.call_count, 1)
        self.assertEqual(reused.kill.call_count, 0)
        self.assertEqual([row["pid"] for row in actions], [1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
