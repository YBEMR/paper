"""K148 zero-research precheck: new wrapper mocks plus exact small oracle.

Only preparation/checking occurs. The research pair is a separate command.
"""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
import unittest
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
HERE = OUT.parents[1]
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))


def main():
    import subprocess
    import scipy.optimize
    import matlab_bridge
    import milp
    import thermal
    import scene_adapter
    import run_five_open_pair as pair
    before = pair.source_gate()
    start = time.monotonic()
    blocked = {}
    capture = io.StringIO()
    result, domain, error = None, None, None

    def reject(label):
        blocked[label] = 0
        def forbidden(*args, **kwargs):
            blocked[label] += 1
            raise AssertionError('Offline K148 check forbids ' + label)
        return forbidden

    try:
        with ExitStack() as stack, redirect_stdout(capture), redirect_stderr(capture):
            for obj, name in [(subprocess, 'Popen'), (scipy.optimize, 'milp'),
                    (scipy.optimize, 'linprog'), (matlab_bridge.MatlabSession, '__init__'),
                    (milp, 'build_model'), (thermal, 'evaluate_candidate'),
                    (thermal, 'evaluate_piecewise'), (scene_adapter, 'evaluate_piecewise')]:
                stack.enter_context(patch.object(obj, name,
                    side_effect=reject(obj.__name__ + '.' + name)))
            suite = unittest.defaultTestLoader.loadTestsFromName('test_five_open_pair')
            result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
            spec = importlib.util.spec_from_file_location('k148_domain_checks', OUT/'domain_checks.py')
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            domain = mod.run_checks()
    except BaseException:
        error = traceback.format_exc()
        capture.write(error)
    after = pair.source_gate()
    passed = bool(result and result.wasSuccessful() and not result.skipped and not error
        and before == after and not any(blocked.values()) and domain and domain.get('state') == 'PASS')
    report = {'protocol': pair.CHECK_PROTOCOL, 'passed': passed,
        'tests_run': result.testsRun if result else 0,
        'errors': len(result.errors) if result else 1,
        'failures': len(result.failures) if result else 0,
        'skipped': len(result.skipped) if result else 0,
        'error': error, 'source_sha256': after, 'source_unchanged': before == after,
        'blocked_calls': blocked, 'research_calls': 0, 'native_calls': 0,
        'physical_models': 0, 'thermal_evaluations': 0,
        'domain_checks': domain,
        'inherited_sources_unchanged': 165, 'source_count': len(after),
        'elapsed_s': time.monotonic() - start,
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'precheck_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'domain_script_sha256': hashlib.sha256((OUT/'domain_checks.py').read_bytes()).hexdigest(),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'new invocation wrapper and exact small structural domain; inherited physical core unchanged'}
    # Never overwrite a failed/successful attempt: each invocation gets a new ID.
    index = 1
    while (OUT/f'attempt{index:02d}').exists():
        index += 1
    attempt = OUT/f'attempt{index:02d}'
    attempt.mkdir()
    (attempt/'unittest.txt').write_bytes(capture.getvalue().encode('utf-8'))
    pair.save(attempt/'checks.json', report)
    for name, digest in after.items():
        target = attempt/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        if pair.sha(target) != digest:
            raise RuntimeError('source changed while archiving')
    for name in ('precheck.py', 'domain_checks.py'):
        shutil.copyfile(OUT/name, attempt/name)
    print(json.dumps({'passed': passed, 'attempt': attempt.relative_to(REPO).as_posix(),
        'tests_run': report['tests_run'], 'errors': report['errors'],
        'failures': report['failures'], 'error': error, 'elapsed_s': report['elapsed_s'],
        'research_calls': 0}, ensure_ascii=False), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
