"""K115 mock admission and one claimed native-only soft-stop interface check.

This entry never runs base__R1 research search or a formal comparison. The
native check uses one small physical model twice, one worker and 180 s total.
"""
import argparse
from datetime import datetime, timezone
import hashlib
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = '1c5fbf2a851244f3689a150db2a7cb79d236ad2b'
CLAIM = HERE/'results/shared_search_native_claim01.json'
NATIVE_SECONDS = 180
SOFT_CAP_SECONDS = 0.000001
MODULES = ('test_shared_search', 'test_partial_slice', 'test_bridge_softcap', 'test_partial_method')
SOURCES = ('shared_search.py', 'test_shared_search.py', 'test_partial_slice.py',
    'test_bridge_softcap.py', 'run_shared_search_precheck.py',
    'partial_method.py', 'partial_bounds.py', 'test_partial_method.py',
    'scene_adapter.py', 'scene_method.py', 'diagnostic_search.py', 'formal_milp.py',
    'initial_point.py', 'initial_schedule.py', 'milp.py', 'milp_coefficients.py',
    'matlab_bridge.py', 'solve_model.m', 'inputs.py', 'start_domain.py', 'schedules.py',
    'thermal.py', 'timing.py', 'build_observer.py', 'control_policy.py', 'config_v01.json',
    'run_milp_precheck.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str,
                                    allow_nan=False)+'\n', encoding='utf-8')


def sources():
    return {p.relative_to(REPO).as_posix(): sha(p)
            for p in [*(HERE/n for n in SOURCES), HERE.parent/'v1_evaluator/interval.py']}


def history():
    baseline = json.loads((HERE/'results/prefilter_protocol01/historical_integrity_before.json').read_text(encoding='utf-8'))
    hashes = baseline['prior_24_archives_sha256']
    if any(sha(HERE/'results/formal_comparison01'/name) != value for name, value in hashes.items()):
        raise ValueError('Historical24 archive changed')
    return hashes


def reused_core():
    """Reuse unchanged expression/numeric modules, not a stale whole gate."""
    path = HERE/'results/partial_method_precheck02/checks.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    allowed = {str(HERE.relative_to(REPO)/n).replace('\\', '/')
               for n in ('partial_method.py', 'matlab_bridge.py', 'solve_model.m')}
    changed = {name: {'old': value, 'current': sha(REPO/name)}
               for name, value in data['source_sha256'].items() if sha(REPO/name) != value}
    if not data['passed'] or set(changed)-allowed:
        raise ValueError('Unexpected core dependency changed')
    if sha(HERE/'config_v01.json') != '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe':
        raise ValueError('Frozen physical input changed')
    return {'path': path.relative_to(REPO).as_posix(), 'sha256': sha(path),
            'scope': 'unchanged expression/numeric modules only; NOT whole old gate current',
            'allowed_modified_modules_newly_tested': changed,
            'unchanged_modules': {n: h for n, h in data['source_sha256'].items() if n not in changed}}


def prepare(out):
    out = out.resolve(); out.relative_to(REPO); out.mkdir(parents=True, exist_ok=False)
    before = sources()
    for name in before:
        dest = out/'source_snapshot'/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO/name, dest)
    return out, before, history(), reused_core()


def run_mock(out):
    started = time.monotonic()
    out, before, old, core = prepare(out)
    save(out/'declaration.json', {'scope': 'mock control flow, algebra and default-path regressions',
        'ceiling_s': 180, 'reference_commit': REFERENCE, 'source_sha256': before,
        'reused_core': core, 'actual_model_builds': 0, 'actual_thermal_evaluations': 0,
        'actual_solver_requests': 0, 'research_calls': 0,
        'native_plan': {'calls': 1, 'budget_s': NATIVE_SECONDS, 'requests': 2,
            'first_cap_s': SOFT_CAP_SECONDS, 'second_cap': None,
            'fixture': 'one original scene/one A.pre, CPU1; actual complete small model',
            'require_actual_soft_time_stop': True, 'natural_convergence_is_not_branch_coverage': True,
            'no_retries': True, 'no_extension': True, 'claim_path': CLAIM.relative_to(REPO).as_posix()}})
    checks, attempts = [], []
    stream = io.StringIO(); outcome = None; error = None
    class Result(unittest.TextTestResult):
        def startTest(self, test):
            if time.monotonic()-started >= 180:
                raise TimeoutError('Mock correctness ceiling')
            super().startTest(test)
        def addSuccess(self, test):
            checks.append({'name': test.id(), 'passed': True}); super().addSuccess(test)
        def addError(self, test, error):
            checks.append({'name': test.id(), 'passed': False, 'kind': 'error'}); super().addError(test, error)
        def addFailure(self, test, error):
            checks.append({'name': test.id(), 'passed': False, 'kind': 'failure'}); super().addFailure(test, error)
        def addSubTest(self, test, subtest, error):
            if error is not None:
                checks.append({'name': subtest.id(), 'passed': False, 'kind': 'subtest'})
            super().addSubTest(test, subtest, error)
    def forbidden(*args, **kwargs):
        attempts.append('actual physical/native operation forbidden')
        raise AssertionError(attempts[-1])
    try:
        suite = unittest.TestLoader().loadTestsFromNames(MODULES)
        with patch('milp.Model.__init__', forbidden), patch('thermal.evaluate_piecewise', forbidden), \
                patch('scene_adapter.evaluate_piecewise', forbidden), patch('matlab_bridge.MatlabSession.__init__', forbidden):
            outcome = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    except Exception:
        error = traceback.format_exc()
    (out/'unit_checks.txt').write_text(stream.getvalue(), encoding='utf-8')
    save(out/'fixture_records.json', {n: getattr(sys.modules.get(n), 'RECORDS', {}) for n in MODULES})
    integrity = {'source_unchanged': sources() == before, 'old24_unchanged': history() == old,
        'unchanged_core_still_matches': reused_core() == core, 'no_actual_physical_or_native': not attempts,
        'correctness_ceiling_respected': time.monotonic()-started < 180}
    checks.extend({'name': n, 'passed': v} for n, v in integrity.items())
    passed = bool(outcome) and outcome.wasSuccessful() and error is None and all(c['passed'] for c in checks)
    report = {'passed': passed, 'count': len(checks), 'unit_test_methods': outcome.testsRun if outcome else 0,
        'checks': checks, 'source_sha256': before, 'runner_error': error, 'actual_attempts': attempts,
        'elapsed_s': time.monotonic()-started, 'reused_core': core, 'historical24_sha256': old}
    save(out/'checks.json', report)
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform(),
        'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'passed': passed, 'checks': len(checks), 'elapsed_s': report['elapsed_s'], 'out': str(out)}), flush=True)
    return passed


def run_native(out, gate_path):
    gate = json.loads(gate_path.read_text(encoding='utf-8'))
    if not gate['passed'] or gate['source_sha256'] != sources():
        raise ValueError('Current source-matched passing gate required')
    if CLAIM.exists():
        raise FileExistsError('K115 native check already consumed; no retry')
    out, before, old, core = prepare(out)
    declaration = {'scope': 'native soft-stop/default-reuse interface only; no new thermal safety evidence',
        'calls': 1, 'budget_s': NATIVE_SECONDS, 'requests': 2, 'first_native_cap_s': SOFT_CAP_SECONDS,
        'second_cap': None, 'require_actual_soft_stop': True, 'retries': False,
        'source_sha256': before, 'gate_sha256': sha(gate_path), 'reused_core': core,
        'recipe': 'fresh small_input inside total budget, first original scene only, shared A.pre=CPU1',
        'parameters_unchanged': True, 'research_calls': 0, 'actual_thermal_evaluations': 0}
    save(out/'declaration.json', declaration)
    with CLAIM.open('x', encoding='utf-8') as file:
        json.dump({'state': 'CLAIMED_NO_RETRY', 'out': out.relative_to(REPO).as_posix(),
            'source_sha256': before, 'gate_sha256': sha(gate_path), 'budget_s': NATIVE_SECONDS}, file, indent=2)
    from test_partial_method import small_input
    from milp import build_model, decode
    from matlab_bridge import MatlabSession
    from scene_method import DEFAULT_BUILDER_OPTIONS
    from schedules import validate_schedule
    from scene_adapter import canonical_hash
    from timing import MethodBudget
    budget = MethodBudget(NATIVE_SECONDS)
    session = None; first = second = None; error = None; legal = None; cleanup_error = None
    try:
        with budget.phase('input_read_and_expansion'):
            config, instance = small_input(budget)
        save(out/'input_config.json', config); save(out/'input_instance.json', instance)
        with budget.phase('model_construction'):
            model = build_model(instance, config, budget=budget,
                fixed_shared_deployment={'A.pre': 'CPU1'}, fixed_scene_id=instance['scenarios'][0]['id'],
                **DEFAULT_BUILDER_OPTIONS)
        save(out/'model_summary.json', model.summary())
        with budget.phase('solver_startup'):
            session = MatlabSession(out/'matlab', total_budget_s=budget.remaining, budget=budget)
        with budget.phase('first_export'):
            payload = model.as_solver_dict()
        first = session.solve(payload, budget=budget, solver_max_time_s=SOFT_CAP_SECONDS)
        save(out/'first_return.json', first)
        if first.get('status') == 'SOLVED' and first.get('budget_valid') and not session.request_blocked:
            budget.check()
            second = session.solve(payload, budget=budget)
            save(out/'second_return.json', second)
            if second.get('accepted_for_evaluation'):
                candidate = decode(model, second['x'])
                legal = validate_schedule(model.instance, candidate)
                save(out/'decoded_candidate.json', candidate)
                save(out/'candidate_legality.json', legal)
    except Exception:
        error = traceback.format_exc()
    finally:
        elapsed = budget.elapsed
        timing = budget.summary(elapsed)
        start_cleanup = time.monotonic()
        if session is not None:
            try:
                session.close()
            except Exception:
                cleanup_error = traceback.format_exc()
        timing['cleanup_s'] = time.monotonic()-start_cleanup
    first, second = first or {}, second or {}
    message = str((first.get('output') or {}).get('message', '')).lower()
    soft_stop = first.get('exitflag') == 0 and ('time' in message or '时间' in message)
    reqs = []
    for prefix in sorted((out/'matlab').glob('request_*.input.json')):
        reqs.append(json.loads(prefix.read_text(encoding='utf-8')))
    checks = {'source_unchanged': sources() == before, 'old24_unchanged': history() == old,
        'no_runtime_error': error is None and cleanup_error is None, 'one_worker_two_requests': session is not None and session.counter == 2,
        'first_entered_and_returned_within_global_budget': first.get('intlinprog_entered') is True and first.get('budget_valid') is True,
        'first_native_MaxTime_positive_and_capped': 0 < first.get('solver_max_time_s_used', -1) <= SOFT_CAP_SECONDS,
        'actual_time_limit_stop_observed': soft_stop,
        'second_default_request_entered_and_returned': second.get('intlinprog_entered') is True and second.get('budget_valid') is True and second.get('status') == 'SOLVED',
        'second_candidate_numerically_admitted': second.get('accepted_for_evaluation') is True,
        'second_candidate_exact_schedule_legal': (legal or {}).get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
        'same_global_response_deadline': len(reqs) == 2 and reqs[0]['absolute_deadline'] == reqs[1]['absolute_deadline'] == budget.deadline,
        'default_has_no_new_native_cap_field': len(reqs) == 2 and 'solver_max_time_s_declared' not in reqs[1],
        'method_within_predeclared_180s': elapsed < NATIVE_SECONDS}
    report = {'passed': all(checks.values()), 'count': len(checks),
        'checks': [{'name': n, 'passed': bool(v)} for n, v in checks.items()],
        'source_sha256': before, 'gate_sha256': sha(gate_path), 'native_method_calls': 1,
        'research_calls': 0, 'actual_thermal_evaluations': 0, 'timing': timing,
        'first_exitflag': first.get('exitflag'), 'first_message': message,
        'second_exitflag': second.get('exitflag'), 'error': error, 'cleanup_error': cleanup_error,
        'scope': 'actual native soft stop and worker reuse only; no SAFE or performance claim'}
    save(out/'verification.json', report)
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'elapsed_s': elapsed,
        'actual_soft_stop': soft_stop, 'out': str(out)}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--gate', type=Path)
    args = parser.parse_args()
    if args.native and args.gate is None:
        parser.error('--native requires --gate')
    raise SystemExit(0 if (run_native(args.out, args.gate) if args.native else run_mock(args.out)) else 1)
