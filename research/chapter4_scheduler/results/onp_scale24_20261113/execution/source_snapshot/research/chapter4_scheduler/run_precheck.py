"""Repeatable, guarded pure checks. No real workload or research call entry."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LEGACY = HERE.parent / "chapter3_experiments"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(LEGACY))
sys.dont_write_bytecode = True


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hashes(paths):
    return {str(p.relative_to(REPO)).replace("\\", "/"):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new evidence directory; must not exist")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError(str(out))
    if not out.is_relative_to(HERE / "results"):
        raise ValueError("precheck artifacts must stay in chapter4_scheduler/results")
    out.mkdir(parents=True)
    own = sorted(HERE.glob("*.py")) + sorted((HERE / "tests").glob("*.py"))
    protected = sorted(LEGACY.glob("*.py")) + [LEGACY / "config_v01.json",
        LEGACY / "h02_pair_preflight/receipts.py", LEGACY / "h02_pair_preflight/common.py",
        HERE.parent / "v1_evaluator/interval.py"]
    before = hashes(own + protected)
    forbidden = []

    def denied(name):
        def call(*args, **kwargs):
            forbidden.append(name)
            raise AssertionError("FORBIDDEN_RESEARCH_OR_EXTERNAL_CALL:" + name)
        return call

    class NoSolverImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in ("milp", "matlab_bridge") or fullname.startswith((
                    "scipy.optimize", "matlab.engine", "gurobipy", "pulp")):
                forbidden.append("import:" + fullname)
                raise AssertionError("FORBIDDEN_SOLVER_IMPORT:" + fullname)
            return None

    guard = NoSolverImports()
    import thermal
    import heft_method
    log = io.StringIO()
    started = time.monotonic()
    sys.meta_path.insert(0, guard)
    try:
        with ExitStack() as stack:
            for target, name in [("thermal.evaluate_candidate", "thermal_candidate"),
                    ("thermal.evaluate_piecewise", "thermal_piecewise"),
                    ("heft_method.run_heft", "real_heft"),
                    ("subprocess.Popen", "subprocess"), ("os.system", "shell"),
                    ("socket.create_connection", "network"), ("socket.socket.connect", "network_socket")]:
                stack.enter_context(patch(target, side_effect=denied(name)))
            suite = unittest.defaultTestLoader.discover(str(HERE / "tests"), pattern="test_*.py")
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    finally:
        sys.meta_path.remove(guard)
    elapsed = time.monotonic() - started
    after = hashes(own + protected)
    passed = result.wasSuccessful() and not forbidden and before == after
    record = {"protocol": "K180-artificial-graph-and-lifecycle-precheck-v1",
        "evidence_kind": "PURE_FIXTURES_AND_MOCK_ONLY", "usable_as_research_evidence": False,
        "passed": passed, "tests_run": result.testsRun,
        "failures": [{"test": str(test), "trace": trace} for test, trace in result.failures],
        "errors": [{"test": str(test), "trace": trace} for test, trace in result.errors],
        "skips": [{"test": str(test), "reason": why} for test, why in result.skipped],
        "wall_s": elapsed, "forbidden_calls": forbidden,
        "source_bytes_unchanged": before == after, "source_sha256": before,
        "new_research_calls": 0, "real_HEFT_calls": 0,
        "new_optimization_calls": 0, "new_thermal_integrations": 0,
        "research_candidate_evaluations": 0,
        "scope": "artificial graph Cartesian checks and invented complete receipts; no P0/P1/P2 candidate generation",
        "prior_development_notes": [
            "Graph agent run 18/19: fixture omitted device_class; fixture corrected then 19/19. Raw first-run log unavailable.",
            "Lifecycle development: system temp WinError5, config fixture missing platform, violation mock missing receipt identity; artificial setup corrected, no research call.",
            "Lifecycle mock exposed late strict-improvement counter and invalid-NaN archival failures; production thin interface corrected and regression tests retained.",
            "Unified precheck run01: 43/44; one assertion expected the former combined timestamp reason, while the stronger split reason was INVALID_SAFE_TIMESTAMP. Only that assertion updated; run01 artifacts retained."]}
    save(out / "checks.json", record)
    (out / "test_output.txt").write_text(log.getvalue(), encoding="utf-8")
    snapshot = out / "source_snapshot"
    for path in own:
        target = snapshot / path.relative_to(HERE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    print(json.dumps({k: record[k] for k in ("passed", "tests_run", "wall_s",
        "forbidden_calls", "source_bytes_unchanged", "new_research_calls")}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
