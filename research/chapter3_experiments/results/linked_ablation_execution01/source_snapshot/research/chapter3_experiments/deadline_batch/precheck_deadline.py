"""Guarded pure deadline preparation tests, never a research execution."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import io
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch
import prepare_deadline as r


def prior_artifacts():
    names = [r.BASE,
        r.ROOT/'results/p0_execution01/ledger.json',
        r.ROOT/'results/p0_resume01/archive_inventory.json',
        r.ROOT/'results/p0_resume01/ledger.json',
        r.ROOT/'results/p0_resume01/process_terminal.json',
        r.ROOT/'results/p1_execution01/archive_inventory.json',
        r.ROOT/'results/p1_execution01/ledger.json',
        r.ROOT/'results/p1_execution01/worker_terminal.json',
        r.ROOT/'results/p2_execution01/archive_inventory.json',
        r.ROOT/'results/p2_execution01/ledger.json',
        r.ROOT/'results/p2_execution01/worker_terminal.json',
        r.ROOT/'results/p2_execution01/summary.md']
    return {q.relative_to(r.REPO).as_posix(): r.sha(q) for q in names}


def run(out):
    out = Path(out).resolve()
    out.relative_to(r.REPO)
    out.mkdir(parents=True, exist_ok=False)
    before = r.sources()
    prior = prior_artifacts()
    log = io.StringIO()
    error = result = None
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
        'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess', 'seed_generator'), 0)
    def forbidden(key):
        def fail(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden deadline preparation call: '+key)
        return fail
    try:
        import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp
        import thermal, scene_adapter, initial_schedule, scipy.optimize
        with ExitStack() as stack:
            stack.enter_context(patch('platform.platform', return_value='TEST_ONLY_ENV_METADATA'))
            original = tempfile.TemporaryDirectory
            fixture = r.REPO/'.runtime/k162'
            fixture.mkdir(parents=True, exist_ok=True)
            def temp(*args, **kw):
                kw.setdefault('dir', fixture)
                return original(*args, **kw)
            stack.enter_context(patch('tempfile.TemporaryDirectory', side_effect=temp))
            for obj, name, key in (
                    (formal_milp, 'execute_formal_milp', 'whole'),
                    (linked_method, 'execute_linked_fixed_unit_opp_start', 'linked'),
                    (heuristic_runner, 'execute_heuristic', 'heuristic'),
                    (matlab_bridge.MatlabSession, '__init__', 'matlab'),
                    (scipy.optimize, 'milp', 'milp'), (scipy.optimize, 'linprog', 'linprog'),
                    (milp, 'build_model', 'model'), (thermal, 'evaluate_piecewise', 'heat'),
                    (thermal, 'evaluate_candidate', 'candidate_heat'),
                    (scene_adapter, 'evaluate_piecewise', 'scene_heat'),
                    (initial_schedule, 'iter_initial_candidates', 'seed_generator')):
                stack.enter_context(patch.object(obj, name, side_effect=forbidden(key)))
            stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess')))
            with redirect_stdout(log), redirect_stderr(log):
                suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in (
                    'test_deadline', 'test_deadline_boundaries', 'test_terminal_adapter',
                    'test_p0', 'test_four_method_comparison', 'test_four_whole_status',
                    'test_execution_status', 'test_completion_metrics'))
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    except BaseException:
        error = traceback.format_exc()
        log.write(error)
    after = r.sources()
    prior_after = prior_artifacts()
    g = {'protocol': r.PROTOCOL,
         'passed': bool(result and result.wasSuccessful() and not result.skipped
            and error is None and before == after and prior == prior_after and not any(guards.values())),
         'tests_run': result.testsRun if result else 0,
         'errors': len(result.errors) if result else 1,
         'failures': len(result.failures) if result else 0,
         'skipped': len(result.skipped) if result else 0, 'error': error,
         'source_sha256': after, 'source_unchanged': before == after,
         'prior_archives_unchanged': prior == prior_after, 'prior_archive_sha256': prior_after,
         'blocked_calls': guards, **dict.fromkeys(r.COUNTERS, 0)}
    (out/'unittest.txt').write_text(log.getvalue(), encoding='utf-8')
    r.save(out/'checks.json', g)
    print({k: g[k] for k in ('passed', 'tests_run', 'errors', 'failures', 'skipped', 'blocked_calls', 'error')})
    return g['passed']
