"""Archive hand-authored fixture tests and a NOT_AUTHORIZED supplement list.

No 28-condition runner is supplied. All timetable construction is guarded to
manual inputs; prior calibration archives are read only for provenance hashes.
"""

import argparse
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.run_checks import ScopeGuard, RecordedResult
from .manifest import make_manifest, validate_manifest, PINS


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_files():
    paths = list(PACKAGE.glob("*.py"))
    for name in ("chapter3_deadline_reference", "chapter3_workload_calibration"):
        paths += list((REPO / "research" / name).glob("*.py"))
    paths += [REPO / "research/chapter3_experiments/config_v01.json"]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}


def protected_files():
    """Entire old calibration/reference artifacts, plus original production source."""
    paths = []
    for name in ("chapter3_deadline_reference", "chapter3_workload_calibration"):
        paths += [p for p in (REPO / "research" / name).rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts]
    production = REPO / "research/chapter3_experiments"
    paths += list(production.glob("*.py")) + list(production.glob("*.m")) + [production / "config_v01.json"]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(set(paths))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    allowed = (PACKAGE / "results").resolve()
    if out == allowed or not out.is_relative_to(allowed) or out.exists():
        parser.error("Use a new child directory of chapter3_calibration_adjustment/results")
    out.mkdir(parents=True)
    sources = source_files()
    before = protected_files()
    for rel in sources:
        target = out / "sources" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    write_json(out / "source_manifest.json", sources)
    write_json(out / "protected_before.json", before)
    scratch = out / "scratch"
    scratch.mkdir()
    previous_temp = tempfile.tempdir
    tempfile.tempdir = str(scratch)
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    from research.chapter3_deadline_reference import scheduler
    from research.chapter3_workload_calibration import generator, profiles
    manual_calls = {"mapping": 0, "timetables": 0}
    blocked_workloads = []

    def manual_wrapper(function, kind):
        def guarded(data, *pos, **kw):
            root = data.get("root_family_id", "") if isinstance(data, dict) else ""
            context = data.get("context", {}) if isinstance(data, dict) else {}
            if not context.get("fixture_only") or root.startswith("C") or context.get("namespace") == "ch3-calibration-v1":
                blocked_workloads.append({"operation": kind, "root_family_id": root})
                raise RuntimeError("MANUAL_INPUTS_ONLY")
            manual_calls[kind] += 1
            return function(data, *pos, **kw)
        return guarded

    log = io.StringIO()
    started = time.perf_counter()
    modules = ["research.chapter3_calibration_adjustment." + n for n in
               ("test_transforms", "test_window_idle", "test_manifest")]
    modules += ["research.chapter3_deadline_reference.test_reference"]
    example_error = None
    with ExitStack() as stack:
        stack.enter_context(patch.object(scheduler, "choose_mapping", manual_wrapper(scheduler.choose_mapping, "mapping")))
        stack.enter_context(patch.object(scheduler, "build_timetable", manual_wrapper(scheduler.build_timetable, "timetables")))
        stack.enter_context(patch.object(generator, "build_base", side_effect=RuntimeError("NO_RANDOM_TASK_GENERATION")))
        stack.enter_context(patch.object(profiles, "make_profile", side_effect=RuntimeError("NO_RANDOM_PROFILE_GENERATION")))
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        with redirect_stdout(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
        if result.wasSuccessful() and not result.skipped:
            try:
                from .artifacts import manual_example
                example = manual_example()
                write_json(out / "manual_example.json", example)
                write_json(out / "idle_certificate.json", example["idle_certificate"])
            except Exception as error:
                import traceback
                example_error = {"type": type(error).__name__, "message": str(error),
                                 "traceback": traceback.format_exc()}
    manifest_error = None
    try:
        manifest = make_manifest(REPO)
        validate_manifest(manifest, REPO)
        write_json(out / "supplement_manifest.json", manifest)
    except Exception as error:
        manifest_error = {"type": type(error).__name__, "message": str(error)}
    after = protected_files()
    loaded = sorted(name for name in sys.modules if name == "thermal" or
                    name.startswith(("research.chapter3_experiments", "research.joint_evaluator",
                                     "research.v1_evaluator", "research.v2_evaluator")))
    passed = (result.wasSuccessful() and result.testsRun > 0 and not result.skipped and
              sources == source_files() and before == after and not loaded and
              not guard.denied_imports and not guard.denied_events and not blocked_workloads and
              manifest_error is None and example_error is None and (out / "manual_example.json").is_file())
    report = {"state": "PASS" if passed else "FAIL", "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "IMPLEMENTATION_AND_MANUAL_FIXTURES_ONLY", "python": sys.version,
              "elapsed_s": time.perf_counter() - started, "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
              "test_records": result.records, "subtest_records": result.subtest_records,
              "source_files": sources, "sources_unchanged_during_tests": sources == source_files(),
              "protected_file_count": len(before), "protected_unchanged": before == after,
              "manual_reference_calls": manual_calls, "blocked_workloads": blocked_workloads,
              "denied_imports": guard.denied_imports, "denied_events": guard.denied_events,
              "prohibited_modules_loaded": loaded, "manifest_error": manifest_error, "example_error": example_error,
              "pinned_archives": PINS, "new_calibration_roots": 0, "supplement_conditions_executed": 0,
              "supplement_timetables_constructed": 0, "formal_algorithm_calls": 0,
              "thermal_integrations": 0, "beta_selected": None, "execution_authorized": False}
    write_json(out / "protected_after.json", after)
    write_json(out / "checks.json", report)
    write_json(out / "failures.json", {"failures": [{"test": str(t), "detail": d} for t, d in result.failures],
               "errors": [{"test": str(t), "detail": d} for t, d in result.errors],
               "failed_records": [r for r in result.records if r["state"] != "PASS"],
               "manifest_error": manifest_error, "example_error": example_error})
    (out / "unittest.txt").write_text(log.getvalue(), encoding="utf-8")
    tempfile.tempdir = previous_temp
    print(json.dumps({k: report[k] for k in ("state", "tests_run", "failures", "errors", "elapsed_s",
                                            "protected_unchanged", "supplement_conditions_executed")}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
