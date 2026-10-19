"""Targeted K127 auto-L interface checks; never starts a native optimizer."""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

import scipy.optimize
import matlab_bridge

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TARGETS = ('test_night_formal_auto', 'test_formal_milp',
           'test_auto_heuristic', 'test_heft_method', 'test_sa_method')
NAMES = ('auto_heuristic_policy.py', 'heft_method.py', 'sa_method.py',
    'heuristic_runner.py', 'heuristic_common.py', 'formal_milp.py', 'method_runner.py',
    'run_warm_diagnostic.py', 'initial_point.py', 'initial_schedule.py', 'milp.py',
    'matlab_bridge.py', 'control_policy.py', 'thermal.py', 'timing.py',
    'partial_bounds.py', 'scene_adapter.py', 'schedules.py', 'inputs.py',
    'config_v01.json', 'run_night_precheck.py', 'run_night_after_k126.py')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def identity():
    files = [HERE/p for p in NAMES]+[HERE/(name+'.py') for name in TARGETS]
    return {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run(out):
    out = Path(out).resolve()
    out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    before = identity()
    for name in before:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    captured = io.StringIO()
    started, results, error = time.monotonic(), {}, None
    old_temp = tempfile.tempdir
    temp = REPO/'.runtime/k127_precheck'
    temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp)
    def forbidden(*args, **kwargs):
        raise AssertionError('Real optimizer/native launch is outside this small-domain check')
    try:
        with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
            for owner, name in ((scipy.optimize, 'linprog'), (scipy.optimize, 'milp'),
                                (matlab_bridge.MatlabSession, '__init__')):
                stack.enter_context(patch.object(owner, name, side_effect=forbidden))
            for name in TARGETS:
                suite = unittest.defaultTestLoader.loadTestsFromName(name)
                result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
                results[name] = {'passed': result.wasSuccessful(), 'count': result.testsRun,
                    'failures': len(result.failures), 'errors': len(result.errors)}
    except Exception:
        error = traceback.format_exc()
        captured.write(error)
    finally:
        tempfile.tempdir = old_temp
    (out/'unittest.txt').write_bytes(captured.getvalue().encode('utf-8'))
    after = identity()
    capabilities = {'formal': all(results.get(p, {}).get('passed') is True
        for p in TARGETS[:2]), 'auto_heuristics': all(results.get(p, {}).get('passed') is True
        for p in TARGETS[2:])}
    if before != after or error is not None:
        capabilities = dict.fromkeys(capabilities, False)
    details = {}
    for name, attr in (('test_night_formal_auto', 'RECORDS'), ('test_auto_heuristic', 'PHYSICAL_RECORDS')):
        details[name] = getattr(sys.modules.get(name), attr, {})
    save(out/'physical_and_boundary_records.json', details)
    report = {'protocol': 'K127-targeted-auto-L-precheck-v1',
        'passed': all(capabilities.values()), 'capabilities': capabilities,
        'count': sum(r['count'] for r in results.values()), 'modules': results,
        'source_sha256': after, 'source_unchanged': before == after,
        'native_or_research_calls': 0, 'original_size_models': 0,
        'mock_native_is_not_optimization_evidence': True,
        'exploratory_test_note': 'formal test development first hit Windows temporary-directory access errors; '
            'inherited-ACL .runtime unique directories used without changing ACL; development traces are not research results',
        'elapsed_s': time.monotonic()-started, 'error': error,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'environment': {'python': sys.version, 'platform': platform.platform()}}
    save(out/'checks.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'capabilities', 'count', 'error', 'elapsed_s')}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
