"""Guarded synthetic tests for the proposed eight-slot launch chain."""
import argparse
from contextlib import ExitStack
import importlib.abc
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'research/chapter3_experiments'))
sys.dont_write_bytecode = True
from research.chapter4_scheduler.execution import protocol as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    p._output(out)
    if out.exists():
        raise FileExistsError('Never overwrite a pure check run')
    out.mkdir(parents=True)
    before = p.make_declaration()
    forbidden = []
    def denied(name):
        def call(*a, **k):
            forbidden.append(name)
            raise AssertionError('FORBIDDEN_REAL_RESEARCH_OR_PROCESS:' + name)
        return call
    class NoOptimizer(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in ('milp', 'matlab_bridge') or fullname.startswith((
                    'scipy.optimize', 'matlab.engine', 'gurobipy', 'pulp')):
                forbidden.append('import:' + fullname)
                raise AssertionError('FORBIDDEN_OPTIMIZER_IMPORT:' + fullname)
            return None
    import thermal
    import heft_method
    log = io.StringIO(); guard = NoOptimizer(); started = time.monotonic()
    sys.meta_path.insert(0, guard)
    result = None
    try:
        with ExitStack() as stack:
            for name in ('thermal.evaluate_candidate', 'thermal.evaluate_piecewise',
                    'heft_method.run_heft', 'subprocess.Popen', 'os.system',
                    'socket.create_connection', 'socket.socket.connect'):
                stack.enter_context(patch(name, side_effect=denied(name)))
            suite = unittest.TestSuite([
                unittest.defaultTestLoader.discover(str(HERE.parent / 'tests'), pattern='test_*.py'),
                unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py')])
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    finally:
        sys.meta_path.remove(guard)
    after = p.make_declaration()
    unchanged = before['source_sha256'] == after['source_sha256']
    protected = p.verify_files(before)
    passed = result is not None and result.wasSuccessful() and not forbidden and unchanged and protected
    report = dict(protocol='K181-guarded-execution-precheck-v1', passed=passed,
        evidence_kind='ARTIFICIAL_INPUTS_AND_INERT_BACKENDS_ONLY',
        usable_as_research_evidence=False, tests_run=0 if result is None else result.testsRun,
        failures=[] if result is None else [dict(test=str(t), trace=s) for t, s in result.failures],
        errors=[] if result is None else [dict(test=str(t), trace=s) for t, s in result.errors],
        skips=[] if result is None else [dict(test=str(t), reason=s) for t, s in result.skipped],
        wall_s=time.monotonic()-started, forbidden_calls=forbidden,
        source_bytes_unchanged=unchanged, protected_archive_unchanged=protected,
        source_sha256=before['source_sha256'],
        new_research_calls=0, real_HEFT_calls=0, new_optimization_calls=0,
        new_thermal_integrations=0, research_candidate_evaluations=0,
        execution_enabled=False, authorized=False)
    p.write_new(out / 'checks.json', report)
    (out / 'test_output.txt').write_text(log.getvalue(), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'tests_run', 'wall_s',
        'forbidden_calls', 'source_bytes_unchanged', 'protected_archive_unchanged', 'new_research_calls')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
