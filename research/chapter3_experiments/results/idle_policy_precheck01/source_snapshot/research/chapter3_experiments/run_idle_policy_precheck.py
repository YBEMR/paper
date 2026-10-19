"""K111 evaluator-only correctness gate; no MILP, MATLAB or research methods.

Run the new small-fixture policy tests and the two affected legacy heuristic
unit suites. Existing main scripts and frozen research calls are never run.
The 180 s ceiling bounds this correctness phase, not a performance comparison.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
SOURCE_NAMES = (
    'control_policy.py', 'schedules.py', 'thermal.py', 'milp.py',
    'initial_point.py', 'scene_adapter.py', 'q1_case.py', 'heuristic_runner.py',
    'heft_method.py', 'sa_method.py', 'heuristic_common.py', 'initial_schedule.py',
    'inputs.py', 'start_domain.py', 'timing.py', 'matlab_bridge.py',
    'milp_coefficients.py', 'run_precheck.py', 'run_milp_precheck.py',
    'run_thermal_precheck.py', 'test_heft_method.py', 'test_sa_method.py',
    'test_control_policy.py', 'run_idle_policy_precheck.py', 'config_v01.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               default=str, allow_nan=False)+'\n', encoding='utf-8')


def numerical_definitions(source):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
            and node.name != 'evaluate_candidate'}


def run(out, seconds=180):
    out = out.resolve()
    out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    files = [HERE/name for name in SOURCE_NAMES]
    files.append(HERE.parent/'v1_evaluator/interval.py')
    before = {str(path.relative_to(REPO)).replace('\\', '/'): sha(path)
              for path in files}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO).decode().strip()
    baseline = {}
    for name in ('schedules.py', 'thermal.py'):
        raw = subprocess.check_output(['git', 'show', head+':research/chapter3_experiments/'+name], cwd=REPO)
        dest = out/'baseline_snapshot'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        baseline[name] = raw.decode('utf-8')
    for path in files:
        dest = out/'source_snapshot'/path.relative_to(REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    historical_path = HERE/'results/prefilter_protocol01/historical_integrity_before.json'
    historical = json.loads(historical_path.read_text(encoding='utf-8'))['prior_24_archives_sha256']
    old_results = HERE/'results/formal_comparison01'
    if any(sha(old_results/name) != value for name, value in historical.items()):
        raise ValueError('Historical research archives changed before precheck')
    save(out/'declaration.json', {
        'scope': 'small correctness fixtures only; no research case or native solver',
        'declared_correctness_ceiling_s': seconds, 'baseline_commit': head,
        'source_sha256': before, 'research_method_calls': 0,
        'native_solver_calls': 0, 'model_builds_permitted': 0,
        'physical_fixture_calls_ceiling': 6, 'independent_ODE_oracles_ceiling': 1,
        'legacy_research_config_sha256': CONFIG_SHA})
    modules = ['test_control_policy', 'test_heft_method', 'test_sa_method']
    records, stream = [], io.StringIO()

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            if time.monotonic()-start >= seconds:
                raise TimeoutError('Correctness-phase deadline; no extra tests')
            super().startTest(test)

        def addSuccess(self, test):
            records.append({'name': test.id(), 'passed': True})
            super().addSuccess(test)

        def addFailure(self, test, error):
            records.append({'name': test.id(), 'passed': False, 'kind': 'failure'})
            super().addFailure(test, error)

        def addError(self, test, error):
            records.append({'name': test.id(), 'passed': False, 'kind': 'error'})
            super().addError(test, error)

        def addSubTest(self, test, subtest, error):
            if error is not None:
                records.append({'name': subtest.id(), 'passed': False, 'kind': 'subtest'})
            super().addSubTest(test, subtest, error)

    native_attempts, model_attempts = [], []

    def forbidden_native(*args, **kwargs):
        native_attempts.append('attempted')
        raise AssertionError('Native solver startup forbidden in evaluator precheck')

    def forbidden_model(*args, **kwargs):
        model_attempts.append('attempted')
        raise AssertionError('MILP model construction forbidden in evaluator precheck')

    error, test_result = None, None
    try:
        suite = unittest.TestLoader().loadTestsFromNames(modules)
        with patch('matlab_bridge.MatlabSession.__init__', forbidden_native), \
                patch('milp.Model.__init__', forbidden_model):
            test_result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    except Exception as exc:
        error = type(exc).__name__+': '+str(exc)
    (out/'unit_checks.txt').write_text(stream.getvalue(), encoding='utf-8')
    module = sys.modules.get('test_control_policy')
    save(out/'fixture_records.json', getattr(module, 'PRECHECK_RECORDS', {}))
    integrity = {
        'source_unchanged_during_run': all(sha(REPO/name) == value for name, value in before.items()),
        'legacy_config_unchanged': sha(HERE/'config_v01.json') == CONFIG_SHA,
        'thermal_numerical_definitions_unchanged': numerical_definitions(baseline['thermal.py']) ==
            numerical_definitions((HERE/'thermal.py').read_text(encoding='utf-8')),
        'historical24_unchanged': all(sha(old_results/name) == value for name, value in historical.items()),
        'no_native_startup': not native_attempts,
        'no_model_construction': not model_attempts,
        'correctness_ceiling_respected': time.monotonic()-start < seconds}
    records.extend({'name': name, 'passed': value} for name, value in integrity.items())
    passed = (bool(records) and not error and test_result is not None and
              test_result.wasSuccessful() and all(item['passed'] for item in records))
    summary = {'passed': passed, 'count': len(records), 'checks': records,
        'unit_tests_recorded': len(records)-len(integrity), 'runner_error': error,
        'source_sha256': before, 'baseline_commit': head,
        'original_historical24_sha256': historical,
        'elapsed_s': time.monotonic()-start, 'native_solver_calls': 0,
        'research_method_calls': 0, 'model_builds': 0,
        'scope': 'evaluator/control correctness only; no energy benefit or method readiness claim'}
    save(out/'checks.json', summary)
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform(),
        'checked_at_utc': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'passed': passed, 'checks': len(records),
                      'elapsed_s': summary['elapsed_s'], 'out': str(out)}), flush=True)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
