"""One archived, guarded manual precheck; never construct calibration identities."""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import sys
import time
import unittest

from research.chapter3_deadline_reference.run_checks import ScopeGuard, RecordedResult
from .runtime import fresh_output, snapshot, protected_files, source_files, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = fresh_output(args.output)
    sources = snapshot(out)
    before = protected_files()
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    modules = ["research.chapter3_workload_calibration." + n for n in
               ("test_profiles", "test_topology", "test_generator", "test_execution")]
    modules += ["research.chapter3_deadline_reference.test_reference"]
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    log = io.StringIO()
    started = time.perf_counter()
    with redirect_stdout(log):
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    elapsed = time.perf_counter() - started
    after = protected_files()
    passed = result.wasSuccessful() and not result.skipped and before == after and source_files() == sources
    passed = passed and not guard.denied_events
    report = {"state": "PASS" if passed else "FAIL", "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "MANUAL_FIXTURES_AND_MOCK_LAUNCH_ONLY", "elapsed_s": elapsed,
              "python": sys.version, "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
              "test_records": result.records, "subtest_records": result.subtest_records,
              "source_files": sources, "protected_sources_before": before, "protected_sources_after": after,
              "protected_sources_unchanged": before == after, "denied_imports": guard.denied_imports,
              "denied_events": guard.denied_events, "calibration_roots_generated": 0,
              "formal_method_calls": 0, "thermal_integrations": 0}
    (out / "unittest.txt").write_text(log.getvalue(), encoding="utf-8")
    write_json(out / "checks.json", report)
    print({k: report[k] for k in ("state", "tests_run", "failures", "errors", "elapsed_s")})
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
