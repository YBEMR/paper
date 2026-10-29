"""Manual and mocked lifecycle checks only. No actual supplement execution."""

import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import shutil
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.run_checks import ScopeGuard, RecordedResult
from .protocol import PACKAGE, REPO, sources, protected, result_path, inventory
from .persistence import write_once as write_json


def historical_supplement_files():
    """Protect the consumed freeze and actual partial run, outside old protected()."""
    from research.chapter3_workload_calibration.runtime import sha
    files = [PACKAGE / "results/supplement_approval01.json"]
    for name in ("frozen_supplement01", "supplement_execution01", "supplement_analysis01"):
        files += [p for p in (PACKAGE / "results" / name).rglob("*") if p.is_file()]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in files}


def check(output):
    out = result_path(output, fresh=True)
    out.mkdir(parents=True)
    previous = tempfile.tempdir
    try:
        return _check(out)
    except (Exception, KeyboardInterrupt) as error:
        detail = {"state": "ERROR", "error": str(error), "traceback": traceback.format_exc(),
                  "supplement_conditions_executed": 0, "formal_algorithm_calls": 0, "thermal_integrations": 0}
        write_json(out / "fatal_error.json", detail)
        if not (out / "checks.json").exists():
            write_json(out / "checks.json", detail)
        print(detail)
        return 1
    finally:
        tempfile.tempdir = previous


def _check(out):
    source_map, before = sources(), protected()
    historical_before = historical_supplement_files()
    for rel in source_map:
        target = out / "sources" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    write_json(out / "source_manifest.json", source_map)
    write_json(out / "protected_before.json", before)
    write_json(out / "historical_supplement_before.json", historical_before)
    scratch = out / "scratch"
    scratch.mkdir()
    tempfile.tempdir = str(scratch)
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    from research.chapter3_deadline_reference import scheduler
    from research.chapter3_workload_calibration import generator, profiles
    counts = {"mapping": 0, "timetables": 0}
    blocked = []

    def manual_only(function, kind):
        def wrapped(data, *args, **kwargs):
            context = data.get("context", {}) if isinstance(data, dict) else {}
            root = data.get("root_family_id", "") if isinstance(data, dict) else ""
            if not context.get("fixture_only") or root.startswith("C"):
                blocked.append({"kind": kind, "root": root})
                raise RuntimeError("MANUAL_ONLY_NO_ACTUAL_SUPPLEMENT")
            counts[kind] += 1
            return function(data, *args, **kwargs)
        return wrapped

    modules = ["research.chapter3_calibration_supplement." + name for name in
               ("test_condition", "test_analysis", "test_runtime", "test_persistence", "test_continuation")]
    modules += ["research.chapter3_calibration_adjustment." + name for name in
                ("test_transforms", "test_window_idle", "test_manifest")]
    modules += ["research.chapter3_deadline_reference.test_reference"]
    log = io.StringIO()
    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(scheduler, "choose_mapping", manual_only(scheduler.choose_mapping, "mapping")))
        stack.enter_context(patch.object(scheduler, "build_timetable", manual_only(scheduler.build_timetable, "timetables")))
        stack.enter_context(patch.object(generator, "build_base", side_effect=RuntimeError("NO_RANDOM_GENERATION")))
        stack.enter_context(patch.object(profiles, "make_profile", side_effect=RuntimeError("NO_RANDOM_PROFILE")))
        with redirect_stdout(log), redirect_stderr(log):
            suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
            result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    inv = inventory()  # Read-only hashes, no time construction.
    after = protected()
    historical_after = historical_supplement_files()
    loaded = [name for name in sys.modules if name.startswith(("research.chapter3_experiments",
              "research.joint_evaluator", "research.v1_evaluator", "research.v2_evaluator"))]
    passed = (result.wasSuccessful() and result.testsRun > 0 and not result.skipped and
              source_map == sources() and before == after and historical_before == historical_after and not blocked and not loaded and
              not guard.denied_events and not guard.denied_imports)
    report = {
        "state": "PASS" if passed else "FAIL", "scope": "MANUAL_AND_MOCKED_EXECUTION_PREPARATION_ONLY",
        "created_utc": datetime.now(timezone.utc).isoformat(), "elapsed_s": time.perf_counter()-started,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skips": len(result.skipped), "test_records": result.records, "subtest_records": result.subtest_records,
        "source_files": source_map, "sources_unchanged": source_map == sources(),
        "protected_file_count": len(before), "protected_unchanged": before == after,
        "historical_supplement_file_count": len(historical_before),
        "historical_supplement_unchanged": historical_before == historical_after,
        "manual_reference_calls": counts, "blocked_workloads": blocked, "prohibited_modules": loaded,
        "denied_events": guard.denied_events, "denied_imports": guard.denied_imports,
        "inventory_hash": inv["manifest_hash"], "planned_conditions": len(inv["calls"]),
        "supplement_conditions_executed": 0, "formal_algorithm_calls": 0, "thermal_integrations": 0,
        "real_worker_processes": 0, "beta_selected": None, "execution_authorized": False,
    }
    write_json(out / "checks.json", report)
    write_json(out / "protected_after.json", after)
    write_json(out / "historical_supplement_after.json", historical_after)
    write_json(out / "failures.json", {
        "failures": [{"test": str(t), "detail": detail} for t, detail in result.failures],
        "errors": [{"test": str(t), "detail": detail} for t, detail in result.errors]})
    (out / "unittest.txt").write_text(log.getvalue(), encoding="utf-8")
    print({k: report[k] for k in ("state", "tests_run", "failures", "errors", "elapsed_s",
                                  "protected_unchanged", "supplement_conditions_executed")})
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    return check(parser.parse_args().output)


if __name__ == "__main__":
    raise SystemExit(main())
