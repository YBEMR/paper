"""New-entry mock checks plus unchanged ON-P tests; zero new scientific calls."""
import argparse
import io
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from . import run


def check(out):
    out.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    result = {'passed': False, 'failures': [], 'errors': [], 'real_method_calls': 0,
              'thermal_evaluations': 0, 'new_root_draws': 0, 'real_U05_U06_scale_extensions': 0,
              'manual_static_fixture': 'Separate TEST_ONLY root12-to24; no real heat or method calls'}
    try:
        with patch('thermal.evaluate_candidate', side_effect=AssertionError('NO_REAL_THERMAL')):
            suite = unittest.defaultTestLoader.loadTestsFromNames([
                'research.chapter4_scheduler.onp_scale24.test_entry',
                'research.chapter4_scheduler.onp.test_run',
                'research.chapter4_scheduler.onp.test_onp'])
            log = io.StringIO()
            t = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            (out / 'tests.log').write_text(log.getvalue(), encoding='utf-8')
            result.update(tests_run=t.testsRun, failures=[str(x) for x in t.failures], errors=[str(x) for x in t.errors])
            if not t.wasSuccessful():
                raise AssertionError('ENTRY_CHECKS_FAILED')
        prior = run.read(run.OLD / 'plan.json')
        for n, h in prior['source_sha256'].items():
            assert run.sha(run.REPO / n) == h, n
        result['source_sha256'] = {**prior['source_sha256'], **{
            p.relative_to(run.REPO).as_posix(): run.sha(p) for p in Path(__file__).parent.glob('*.py')}}
        result['prior_frozen_source_files_unchanged'] = len(prior['source_sha256'])
        result['passed'] = True
    except BaseException as e:
        result['errors'].append(repr(e))
        raise
    finally:
        result['wall_s'] = time.monotonic() - began
        run.save(out / 'checks.json', result)
    print({'passed': True, 'tests_run': result['tests_run'], 'wall_s': result['wall_s']})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    check(p.parse_args().out.resolve())
