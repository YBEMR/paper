"""K119: one independent 10/1 cut-pass pair, fixed shared A, no retry.

--precheck exercises only transport/entry/lifecycle fixtures. --prepare freezes
the current source identity. --run consumes one stage claim for both calls.
Each method owns a fresh 300 s budget before input, one new worker, and the
unchanged AB/AC 60 s cooperative slices. Cleanup is separately reported.
"""
import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = 'K119-fixed-shared-A-cut10-cut1-independent-pair-v1'
PROBLEM = 'base__R1'
SETTINGS = (10, 1)
SECONDS = 300
SLICE_SECONDS = 60
SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
CLAIM = HERE/'results/cut_pair_diagnostic_claim01.json'
BASELINE = HERE/'results/shared_search_diagnostic01/declaration.json'
READ_FIX = HERE/'results/request_read_native01/verification.json'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
CHANGED_TRANSPORT = {'research/chapter3_experiments/matlab_bridge.py',
                     'research/chapter3_experiments/solve_model.m'}
EXTRA_SOURCES = ('run_cut_pair_diagnostic.py', 'test_cut_pair_entry.py',
                 'test_bridge_cut_iterations.py', 'summarize_cut_pair.py',
                 'test_summarize_cut_pair.py')
TESTS = ('test_bridge_cut_iterations', 'test_cut_pair_entry',
         'test_summarize_cut_pair', 'test_bridge_softcap', 'test_partial_slice',
         'test_partial_method.PartialMethodLifecycle.test_single_budget_session_and_callback_updates_before_return',
         'test_partial_method.PartialMethodLifecycle.test_callback_violation_cancel_return_then_feedback',
         'test_partial_method.PartialMethodLifecycle.test_late_original_recheck_retains_initial_global_safe',
         'test_partial_method.PartialMethodLifecycle.test_callback_safe_survives_late_native_final',
         'test_partial_method.PartialMethodLifecycle.test_retained_SAFE_cannot_hide_technical_or_numerical_failure')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _workspace_path(path):
    resolved = Path(path).resolve()
    resolved.relative_to(REPO)
    return resolved


def collect_sources():
    """Reuse unchanged math/physical modules, not the stale whole-worker gate."""
    baseline = read(BASELINE)['source_sha256']
    stale = [name for name, expected in baseline.items()
             if name not in CHANGED_TRANSPORT and sha(REPO/name) != expected]
    if stale or sha(HERE/'config_v01.json') != CONFIG_SHA:
        raise ValueError('Original mathematical/input source changed: '+str(stale))
    names = set(baseline) | {f'research/chapter3_experiments/{n}' for n in EXTRA_SOURCES}
    return {name: sha(REPO/name) for name in sorted(names)}


def precheck(out):
    """No real model, thermal trajectory or MATLAB call is made here."""
    out = _workspace_path(out)
    out.mkdir(parents=True, exist_ok=False)
    before = collect_sources()
    temp_root = REPO/'.runtime/k119_precheck_tmp'
    temp_root.mkdir(parents=True, exist_ok=True)
    old_temp = tempfile.tempdir
    tempfile.tempdir = str(temp_root)
    text = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
        result = unittest.TextTestRunner(stream=text, verbosity=2).run(suite)
    finally:
        tempfile.tempdir = old_temp
    (out/'unittest.txt').write_text(text.getvalue(), encoding='utf-8')
    after = collect_sources()
    passed = result.wasSuccessful() and before == after
    report = {'protocol': PROTOCOL, 'passed': passed, 'count': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'source_unchanged': before == after, 'source_sha256': after,
        'test_targets': list(TESTS), 'scope': 'option/transport/entry/lifecycle mocks only',
        'new_real_model_LP_heat_MATLAB_or_research_calls': 0,
        'old_whole_worker_gate_claimed_current': False,
        'read_fix_report_sha256': sha(READ_FIX),
        'read_fix_original_passed_false_and_shutdown_limit_retained': True,
        'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'checks.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return passed


def admission(checks):
    sources = collect_sources()
    receipt = read(checks)
    if not receipt.get('passed') or receipt.get('source_sha256') != sources:
        raise ValueError('Necessary targeted checks missing/stale/failed')
    if receipt.get('read_fix_report_sha256') != sha(READ_FIX):
        raise ValueError('Historical K117 record changed')
    if CLAIM.exists():
        raise FileExistsError('K119 pair already consumed; no retry')
    return sources


def prepare(out, checks):
    out = _workspace_path(out)
    sources = admission(checks)
    out.mkdir(parents=True, exist_ok=False)
    for name in sources:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO/name, target)
    declaration = {'protocol': PROTOCOL, 'state': 'DECLARED_NOT_RUN',
        'problem_id': PROBLEM, 'settings_in_order': list(SETTINGS),
        'research_calls': 2, 'per_call_budget_s': SECONDS,
        'per_call_scene_slice_s': SLICE_SECONDS, 'shared_deployment': SHARED,
        'analysis_scope': 'fixed_shared_deployment_not_global16',
        'input_recipe': 'fresh load_config/build_instance(base__R1)/explicit autoL inside each budget',
        'physical_parameter_override': False, 'starts_override': None,
        'window_ms': 400, 'start_grid_ms': 5,
        'initial_temperature_degC': 50, 'temperature_limit_degC': 80,
        'local_mapping_OPP_start_choices_remain_free': True,
        'new_worker_models_initialisation_and_caches_each_call': True,
        'CutGeneration': 'basic', 'all_other_solver_options': 'unchanged current R2023b path',
        'retry_allowed': False, 'budget_extension_allowed': False,
        'formal_comparison': False, 'historical_K116_is_control': False,
        'source_sha256': sources,
        'checks_path': Path(checks).resolve().relative_to(REPO).as_posix(),
        'checks_sha256': sha(checks), 'K117_read_fix_report_sha256': sha(READ_FIX),
        'K117_original_failed_gate_and_shutdown_limit_retained': True,
        'billed': 'fresh input, bounds, construction, init, worker startup, export, solve, callbacks, continuous recheck, feedback and live logs',
        'separately_reported': 'imports/source snapshots; cleanup; completed-evidence serialization and read-only analysis',
        'authorization': 'user 继续下一步吧 after K118 explicit 10/1 fixed-condition pair proposal',
        'declared_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'declaration.json', declaration)
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    print(json.dumps({'prepared': True, 'source_count': len(sources),
                      'research_calls': 0, 'out': str(out)}), flush=True)


def _execute_one(out, value):
    from control_policy import with_auto_low_idle
    from inputs import build_instance, load_config
    from matlab_bridge import MatlabSession
    from partial_method import execute_shared_deployment

    def loader(budget):
        raw = load_config()
        instance = build_instance(raw, PROBLEM, budget=budget)
        return with_auto_low_idle(raw), with_auto_low_idle(instance)

    return execute_shared_deployment(loader, out/'invocation',
        shared_deployment=dict(SHARED), seconds=SECONDS, scene_slice_s=SLICE_SECONDS,
        session_factory=partial(MatlabSession, cut_max_iterations=value))


def run(out):
    from matlab_bridge import NUMERICAL_CONSISTENCY_UNRESOLVED

    out = _workspace_path(out)
    declaration = read(out/'declaration.json')
    checks = REPO/declaration['checks_path']
    sources = admission(checks)
    if (declaration.get('protocol') != PROTOCOL or declaration['source_sha256'] != sources
            or declaration['checks_sha256'] != sha(checks)
            or declaration['settings_in_order'] != list(SETTINGS)
            or declaration['per_call_budget_s'] != SECONDS
            or declaration['per_call_scene_slice_s'] != SLICE_SECONDS
            or declaration['shared_deployment'] != SHARED):
        raise ValueError('Frozen protocol/source/rule mismatch')
    for name, expected in sources.items():
        if sha(out/'source_snapshot'/name) != expected:
            raise ValueError('Frozen snapshot changed: '+name)
    if any((out/f'call_{value}').exists() for value in SETTINGS):
        raise FileExistsError('Existing call output: no overwrite/retry')
    with CLAIM.open('x', encoding='utf-8') as f:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'state': 'CLAIMED_NO_RETRY', 'declaration_sha256': sha(out/'declaration.json'),
            'settings': list(SETTINGS), 'per_call_budget_s': SECONDS,
            'claimed_at_utc': datetime.now(timezone.utc).isoformat()}, f, indent=2)
    report = {'protocol': PROTOCOL, 'analysis_scope': 'fixed_shared_deployment_not_global16',
        'state': 'RUNNING', 'declaration_sha256': sha(out/'declaration.json'),
        'source_sha256': sources, 'shared_deployment': SHARED,
        'per_call_budget_s': SECONDS, 'scene_slice_s': SLICE_SECONDS, 'calls': [],
        'scope': 'only pre-cutoff method evidence; no post-cutoff evaluation/search/aggregation'}
    save(out/'run_record.json', report)
    stop = False
    for value in SETTINGS:
        if stop:
            report['calls'].append({'cut_max_iterations': value, 'state': 'NOT_RUN_AFTER_TECHNICAL_FAILURE'})
            break
        call = out/f'call_{value}'
        call.mkdir(exist_ok=False)
        print(f'START K119 CutMaxIterations={value}; {SECONDS}s total, {SLICE_SECONDS}s scenes', flush=True)
        began = time.monotonic()
        result = error = None
        try:
            result = _execute_one(call, value)
        except BaseException:
            error = traceback.format_exc()
        wall = time.monotonic()-began
        cleanup_status = None
        cleanup_metadata_error = None
        closed_path = call/'invocation/matlab/closed.json'
        if closed_path.exists():
            try:
                cleanup_status = read(closed_path)
            except (OSError, ValueError) as exc:
                cleanup_metadata_error = f'{type(exc).__name__}: {exc}'
        unchanged = all(sha(REPO/name) == expected for name, expected in sources.items())
        record = {'cut_max_iterations': value, 'relative_path': call.name,
            'state': 'RETURNED' if error is None else 'INVOCATION_EXCEPTION',
            'error': error, 'wrapper_call_wall_s': wall, 'source_unchanged': unchanged,
            'method_state': None if result is None else result.get('state'),
            'method_reason': None if result is None else result.get('reason'),
            'cleanup_error': None if result is None else result.get('cleanup_error'),
            'cleanup_status': cleanup_status,
            'cleanup_metadata_error': cleanup_metadata_error,
            'safe_upper_bound_J': None if result is None else result.get('safe_upper_bound_J'),
            'method_timing': None if result is None else result.get('timing')}
        save(call/'run_record.json', record)
        report['calls'].append(record)
        technical = {'INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
                     'INVALID_INPUT_OR_INTERFACE', NUMERICAL_CONSISTENCY_UNRESOLVED}
        stop = (error is not None or not unchanged or record['cleanup_error'] is not None
                or cleanup_metadata_error is not None
                or (isinstance(cleanup_status, dict) and cleanup_status.get('cleanup_pending_pid') is not None)
                or record['method_reason'] in technical)
        save(out/'run_record.json', report)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    report['state'] = 'STOPPED_TECHNICAL_FAILURE' if stop else 'PAIR_COMPLETED'
    report['research_calls_consumed'] = sum(x['state'] != 'NOT_RUN_AFTER_TECHNICAL_FAILURE' for x in report['calls'])
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    save(out/'run_record.json', report)
    return not stop


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--precheck', action='store_true')
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    args = parser.parse_args()
    if args.precheck:
        raise SystemExit(0 if precheck(args.out) else 1)
    elif args.prepare:
        if args.checks is None:
            parser.error('--prepare requires --checks')
        prepare(args.out, args.checks)
    else:
        raise SystemExit(0 if run(args.out) else 1)
