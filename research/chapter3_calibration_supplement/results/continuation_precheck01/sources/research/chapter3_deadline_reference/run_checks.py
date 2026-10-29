"""Reproducible, guarded manual-fixture test entry. No calibration dataset.

From repository root:
  python -B -m research.chapter3_deadline_reference.run_checks --output <new dir>
Output must be a new child of this package's results directory.
"""

import argparse
import hashlib
import importlib.abc
import io
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import unittest
from datetime import datetime, timezone


PACKAGE = Path(__file__).resolve().parent
BLOCKED_TOP = {"numpy", "scipy", "matlab", "milp", "thermal", "schedules",
               "initial_schedule", "chapter3_experiments", "gurobipy", "pulp"}
BLOCKED_PREFIX = ("research.chapter3_experiments", "research.joint_evaluator",
                  "research.v1_evaluator", "research.v2_evaluator")


class ScopeGuard(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.denied_imports = []
        self.denied_events = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED_TOP or any(
                fullname == p or fullname.startswith(p + ".") for p in BLOCKED_PREFIX):
            self.denied_imports.append(fullname)
            raise ImportError("Manual-fixture scope prohibits: " + fullname)
        return None

    def audit(self, event, args):
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn",
                     "socket.connect", "socket.getaddrinfo", "ctypes.dlopen"}:
            self.denied_events.append(event)
            raise RuntimeError("Manual-fixture scope prohibits: " + event)


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.subtest_records = []
        self.starts = {}

    def startTest(self, test):
        self.starts[test.id()] = time.perf_counter()
        super().startTest(test)

    def _record(self, test, state, detail=None):
        self.records.append({"test": test.id(), "state": state,
                             "elapsed_s": time.perf_counter() - self.starts.get(test.id(), time.perf_counter()),
                             "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "SKIP", reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        self.subtest_records.append({"parent_test": test.id(), "subtest": str(subtest),
                                     "state": "PASS" if err is None else "FAIL",
                                     "detail": None if err is None else self._exc_info_to_string(err, test)})

    def stopTest(self, test):
        if not any(record["test"] == test.id() for record in self.records):
            self._record(test, "FAIL", "See subtest_records for failed subtests")
        super().stopTest(test)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _protected_files():
    old = PACKAGE.parent / "chapter3_experiments"
    return {str(p.relative_to(PACKAGE.parent.parent)).replace("\\", "/"): _sha(p)
            for p in sorted(old.glob("*.py")) + [old / "config_v01.json"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    root = (PACKAGE / "results").resolve()
    if output == root or not output.is_relative_to(root):
        parser.error("Output must be a new child of chapter3_deadline_reference/results")
    if output.exists():
        parser.error("Refusing to overwrite a previous test receipt")
    output.mkdir(parents=True)
    before = _protected_files()
    source_dir = output / "sources"
    source_dir.mkdir()
    manifest = {}
    for source in sorted(PACKAGE.glob("*.py")):
        shutil.copy2(source, source_dir / source.name)
        manifest[source.name] = _sha(source)
    _write(output / "source_manifest.json", manifest)
    platform_description = platform.platform()
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "research.chapter3_deadline_reference.test_reference")
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    examples_written = False
    example_error = None
    if result.wasSuccessful() and not result.skipped and result.testsRun:
        try:
            from .fixtures import chain_family
            from .scheduler import build_references
            from .deadlines import diagnose, counts
            from .bounds import lower_bounds
            example = chain_family()
            references = build_references(example)
            diagnostics = diagnose(example, references, betas=["1", "1.3", "1.6", "2"],
                                   reference_topology_id=example["topology_id"])
            _write(output / "manual_example.json", {
                "kind": "HAND_WRITTEN_FIXTURE_NOT_CALIBRATION", "input": example,
                "references": references, "diagnostics": diagnostics,
                "counts": counts(example),
                "time_bounds": lower_bounds(example, references["mapping_record"]["mapping"])})
            examples_written = True
        except Exception as error:
            import traceback
            example_error = {"error": str(error), "traceback": traceback.format_exc()}
    after = _protected_files()
    loaded = sorted(name for name in sys.modules if name.split(".")[0] in BLOCKED_TOP or
                    any(name == p or name.startswith(p + ".") for p in BLOCKED_PREFIX))
    groups = {"g" + str(i): {"tests": 0, "passed": 0} for i in range(1, 9)}
    for record in result.records:
        for group in groups:
            if "test_" + group + "_" in record["test"]:
                groups[group]["tests"] += 1
                groups[group]["passed"] += record["state"] == "PASS"
    groups_complete = all(g["tests"] and g["tests"] == g["passed"] for g in groups.values())
    source_unchanged = all(_sha(PACKAGE / name) == digest for name, digest in manifest.items())
    success = (result.wasSuccessful() and not result.skipped and groups_complete and
               examples_written and not loaded and before == after and source_unchanged and
               not guard.denied_events)
    report = {
        "state": "PASS" if success else "FAIL", "scope": "IMPLEMENTATION_AND_MANUAL_FIXTURES_ONLY",
        "started_utc": started, "elapsed_s": time.perf_counter() - clock,
        "python": sys.version, "platform": platform_description,
        "command": "python -B -m research.chapter3_deadline_reference.run_checks --output <new-directory>",
        "tests_run": result.testsRun, "groups": groups, "test_records": result.records,
        "subtest_records": result.subtest_records,
        "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
        "manual_example_saved": examples_written, "example_error": example_error,
        "source_unchanged_during_run": source_unchanged,
        "protected_sources_unchanged": before == after,
        "protected_sources_before": before, "protected_sources_after": after,
        "prohibited_modules_loaded": loaded, "denied_imports": guard.denied_imports,
        "denied_process_or_network_events": guard.denied_events,
        "random_calibration_families": 0, "formal_method_calls": 0,
        "thermal_integrations": 0, "formal_budget_consumed": False,
    }
    (output / "unittest.txt").write_text(stream.getvalue(), encoding="utf-8")
    _write(output / "checks.json", report)
    print(json.dumps({k: report[k] for k in ("state", "tests_run", "failures", "errors", "skips", "groups",
                                           "protected_sources_unchanged", "elapsed_s")}, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
