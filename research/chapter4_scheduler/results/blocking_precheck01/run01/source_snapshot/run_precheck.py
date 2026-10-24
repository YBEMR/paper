"""Guarded, repeatable artificial precheck; no research input or backend run."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LEGACY = REPO / "research/chapter3_experiments"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(LEGACY))
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(HERE.parent / "results"):
        raise ValueError("a new chapter4_scheduler/results directory is required")
    own = sorted(HERE.glob("*.py")) + sorted((HERE / "tests").glob("*.py"))
    declaration_path = HERE.parent / "results/resume_execution01/declaration.json"
    declaration = json.loads(declaration_path.read_text("utf-8"))
    expected = {}
    for key in ("source_sha256", "frozen_dependency_sha256", "protected_archive_sha256"):
        expected.update(declaration[key])
    prior_mismatches = [name for name, digest in expected.items() if sha(REPO / name) != digest]
    if prior_mismatches:
        raise ValueError("old frozen source/archive drift: " + repr(prior_mismatches))
    paths = own + [REPO / p for p in expected] + [declaration_path]
    before = {p.relative_to(REPO).as_posix(): sha(p) for p in paths}
    out.mkdir(parents=True)
    forbidden, output = [], io.StringIO()

    def denied(name):
        def call(*args, **kwargs):
            forbidden.append(name)
            raise AssertionError("FORBIDDEN_RESEARCH_OR_EXTERNAL_CALL:" + name)
        return call

    class NoSolverImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.rsplit(".", 1)[-1] in ("milp", "matlab_bridge") or fullname.startswith((
                    "scipy.optimize", "matlab.engine", "gurobipy", "pulp", "cvxpy")):
                forbidden.append("import:" + fullname)
                raise AssertionError("FORBIDDEN_SOLVER_IMPORT:" + fullname)
            return None

    import thermal
    import heft_method
    guard, result, fatal = NoSolverImports(), None, None
    start = time.monotonic()
    sys.meta_path.insert(0, guard)
    try:
        with ExitStack() as stack:
            for target, label in [
                ("thermal.evaluate_candidate", "real_continuous_candidate"),
                ("thermal.evaluate_piecewise", "real_thermal_integration"),
                ("heft_method.run_heft", "real_HEFT"),
                ("heft_method.build_heft_candidate", "real_HEFT_constructor"),
                ("subprocess.Popen", "native_process"), ("os.system", "shell"),
                ("socket.create_connection", "network"), ("socket.socket.connect", "network_socket")]:
                stack.enter_context(patch(target, side_effect=denied(label)))
            suites = unittest.TestSuite()
            for name in (
                "research.chapter4_scheduler.tests.test_graph_core",
                "research.chapter4_scheduler.tests.test_method",
                "research.chapter4_scheduler.blocking.tests.test_core",
                "research.chapter4_scheduler.blocking.tests.test_targets",
                "research.chapter4_scheduler.blocking.tests.test_blocking_method",
            ):
                suites.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suites)
    except BaseException:
        fatal = traceback.format_exc()
    finally:
        sys.meta_path.remove(guard)
    elapsed = time.monotonic() - start
    after = {p.relative_to(REPO).as_posix(): sha(p) for p in paths}
    passed = result is not None and result.wasSuccessful() and not fatal and not forbidden and before == after
    record = {"protocol": "K186-blocking-edge-artificial-precheck-v1",
        "evidence_kind": "PURE_FIXTURES_AND_MOCK_ONLY", "usable_as_research_evidence": False,
        "passed": passed, "tests_run": result.testsRun if result else 0,
        "failures": [{"test": str(t), "trace": trace} for t, trace in result.failures] if result else [],
        "errors": [{"test": str(t), "trace": trace} for t, trace in result.errors] if result else [],
        "fatal": fatal, "wall_s": elapsed, "forbidden_calls": forbidden,
        "source_bytes_unchanged": before == after, "source_sha256": before,
        "prior_frozen_files_verified": len(expected), "prior_frozen_mismatches": prior_mismatches,
        "new_research_calls": 0, "real_HEFT_calls": 0, "new_native_processes": 0,
        "new_optimization_calls": 0, "new_thermal_integrations": 0,
        "research_candidate_evaluations": 0,
        "scope": "artificial expanded schemas, tiny exact Cartesian starts, invented complete receipts; no real cases or historical schedules",
        "old_versions": "original C/HEFT/single/pair source bytes and protected archives unchanged"}
    save(out / "checks.json", record)
    (out / "test_output.txt").write_text(output.getvalue() + (fatal or ""), encoding="utf-8")
    for path in own:
        target = out / "source_snapshot" / path.relative_to(HERE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    print(json.dumps({k: record[k] for k in ("passed", "tests_run", "wall_s",
        "forbidden_calls", "source_bytes_unchanged", "new_research_calls")}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
