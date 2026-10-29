"""Create pending proposal and run only pure mock/state checks."""
import argparse
import io
import json
from pathlib import Path
import sys
import time
import unittest

from .prepare import prepare, save, load, sha, HERE, ROOT
from research.chapter3_formal_input_adapter.run_checks import Guard
from research.chapter3_deadline_reference.run_checks import RecordedResult


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    out = Path(args.output).resolve()
    guard = Guard()
    sys.meta_path.insert(0, guard); sys.addaudithook(guard.audit)
    started = time.monotonic()
    prepare(out)
    plan = load(out/'plan.json')
    from . import test_preparation
    test_preparation.FROZEN = out
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_preparation)
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    unchanged = all(sha(ROOT/name) == h for name, h in plan['source_sha256'].items())
    passed = result.wasSuccessful() and not result.skipped and result.testsRun > 0 and unchanged
    (out/'tests.txt').write_text(log.getvalue(), encoding='utf-8')
    receipt = {'state': 'PASS' if passed else 'FAIL', 'passed': passed,
               'tests': result.testsRun, 'records': result.records,
               'subtests': result.subtest_records, 'sources_unchanged': unchanged,
               'plan_sha256': sha(out/'plan.json'), 'common_input_sha256': sha(out/'common_input.json'),
               'guard_denied': guard.denied, 'elapsed_s': time.monotonic()-started,
               'actual_method_calls': 0, 'model_constructions': 0,
               'thermal_integrations': 0, 'matlab_starts': 0,
               'scope': 'pure protocol mock routing and evidence-state checks; not executable launcher acceptance'}
    save(out/'checks.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('state', 'tests', 'sources_unchanged', 'elapsed_s', 'plan_sha256')}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
