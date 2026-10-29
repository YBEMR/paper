"""Isolated, reproducible adapter tests; no solver or thermal integration.

python -B -m research.chapter3_formal_input_adapter.run_checks --output <new dir>
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def save(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    result = {}
    for directory in ('chapter3_experiments', 'chapter3_deadline_reference',
                      'chapter3_workload_calibration', 'chapter3_calibration_adjustment',
                      'chapter3_calibration_supplement'):
        for p in sorted((HERE.parent / directory).iterdir()):
            if p.is_file() and p.suffix in ('.py', '.json', '.m'):
                result[p.relative_to(ROOT).as_posix()] = digest(p)
    return result


class Guard(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.denied = []

    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split('.')
        if any(p in {'thermal', 'milp', 'matlab', 'gurobipy', 'pulp', 'numpy', 'scipy',
                     'heft_method', 'sa_method', 'linked_method', 'formal_milp',
                     'heuristic_runner', 'matlab_bridge'} for p in parts):
            self.denied.append(fullname)
            raise ImportError('Adapter pure-check scope forbids: '+fullname)

    def audit(self, event, args):
        if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn',
                     'socket.connect', 'socket.getaddrinfo'}:
            self.denied.append(event)
            raise RuntimeError('Adapter pure-check scope forbids: '+event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    allowed = (HERE/'results').resolve()
    if out == allowed or not out.is_relative_to(allowed) or out.exists():
        parser.error('Output must be a new child of this package/results')
    out.mkdir(parents=True)
    before = protected()
    snapshot = out/'sources'
    snapshot.mkdir()
    sources = {}
    for p in sorted(HERE.glob('*.py')):
        shutil.copyfile(p, snapshot/p.name)
        sources[p.relative_to(ROOT).as_posix()] = digest(p)
    save(out/'source_manifest.json', sources)
    from research.chapter3_deadline_reference.run_checks import RecordedResult
    # Old flat modules are imported only for pure option/schedule validation.
    sys.path.insert(0, str(HERE.parent/'chapter3_experiments'))
    guard = Guard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        'research.chapter3_formal_input_adapter.test_adapter')
    result = unittest.TextTestRunner(stream=log, verbosity=2,
                                    resultclass=RecordedResult).run(suite)
    after = protected()
    success = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
    record = {'state': 'PASS' if success and before == after else 'FAIL',
              'passed': bool(success and before == after), 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'records': result.records,
              'subtests': result.subtest_records, 'started_utc': started,
              'elapsed_s': time.monotonic()-clock, 'python': sys.version,
              'python_version': platform.python_version(),
              'source_sha256': sources, 'protected_before': before,
              'protected_after': after, 'protected_unchanged': before == after,
              'guard_denied': guard.denied, 'optimization_calls': 0,
              'thermal_integrations': 0, 'formal_random_families_generated': 0,
              'scope': 'manual adapter correctness only; no physical SAFE result'}
    (out/'tests.txt').write_text(log.getvalue(), encoding='utf-8')
    save(out/'checks.json', record)
    print(json.dumps({k: record[k] for k in ('state', 'tests', 'failures', 'errors',
                      'elapsed_s', 'protected_unchanged')}, ensure_ascii=False))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
