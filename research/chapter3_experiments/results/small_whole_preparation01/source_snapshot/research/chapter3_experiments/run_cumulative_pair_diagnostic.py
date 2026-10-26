"""K122: one fresh cumulative-precedence off/on pair; no retry.

K121's completed targeted checks admit the unchanged 39-source implementation.
Only the two new entry files are additionally tested here. Each invocation
owns fresh input, models, initialization, worker and caches, with a 300-second
method budget and 60-second AB/AC cooperative slices. Both use cut limit 10.
"""
import argparse
from contextlib import redirect_stdout
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
PROTOCOL = 'K122-fixed-shared-A-cumulative-off-on-independent-pair-v1'
PROBLEM = 'base__R1'
SETTINGS = (False, True)
SECONDS = 300
SLICE_SECONDS = 60
CUT_MAX_ITERATIONS = 10
SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
CLAIM = HERE / 'results/cumulative_pair_diagnostic_claim01.json'
K121_GATE = HERE / 'results/cumulative_precedence_precheck02'
K121_FILES = ('checks.json', 'default_matrix_identity.json',
              'archived_rows.json', 'independent_review.json', 'unittest.txt')
READ_FIX = HERE / 'results/request_read_native01/verification.json'
EXTRA_SOURCES = ('run_cumulative_pair_diagnostic.py', 'test_cumulative_pair_entry.py')
TESTS = ('test_cumulative_pair_entry',)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _workspace_path(path):
    resolved = Path(path).resolve()
    resolved.relative_to(REPO)
    return resolved


def _k121_evidence():
    checks = read(K121_GATE / 'checks.json')
    if (checks.get('protocol') != 'cumulative-precedence-integration-precheck-v1'
            or checks.get('passed') is not True
            or checks.get('source_unchanged') is not True
            or checks.get('tests_run') != 62 or checks.get('failures') != 0
            or checks.get('errors') != 0 or checks.get('error') is not None
            or checks.get('new_LP_MILP_native_thermal_trajectory_or_research_calls') != 0
            or len(checks.get('source_sha256', {})) != 39):
        raise ValueError('K121 precheck02 is missing, failed or not the completed 39-source gate')
    for name in ('default_matrix_identity.json', 'archived_rows.json', 'independent_review.json'):
        receipt = read(K121_GATE / name)
        if receipt.get('passed') is not True:
            raise ValueError('K121 evidence failed: ' + name)
        if name == 'independent_review.json' and receipt.get('source_sha256') != checks['source_sha256']:
            raise ValueError('K121 independent review source identity mismatch')
    return {name: sha(K121_GATE / name) for name in K121_FILES}


def collect_sources():
    """Exact K121 source equality, without invoking a previous stage's gate."""
    _k121_evidence()
    baseline = read(K121_GATE / 'checks.json')['source_sha256']
    stale = [name for name, digest in baseline.items()
             if sha(_workspace_path(REPO / name)) != digest]
    if stale:
        raise ValueError('K121 admitted source changed: ' + str(stale))
    names = set(baseline) | {'research/chapter3_experiments/' + name for name in EXTRA_SOURCES}
    return {name: sha(_workspace_path(REPO / name)) for name in sorted(names)}


def precheck(out):
    """Entry mocks only; no new model, LP, trajectory, MATLAB or research call."""
    out = _workspace_path(out)
    out.mkdir(parents=True, exist_ok=False)
    before = collect_sources()
    gate_before = _k121_evidence()
    read_fix_before = sha(READ_FIX)
    temp_root = REPO / '.runtime/k122_precheck_tmp'
    temp_root.mkdir(parents=True, exist_ok=True)
    old_temp = tempfile.tempdir
    tempfile.tempdir = str(temp_root)
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    finally:
        tempfile.tempdir = old_temp
    (out / 'unittest.txt').write_text(output.getvalue(), encoding='utf-8')
    after = collect_sources()
    gate_after = _k121_evidence()
    passed = (result.wasSuccessful() and before == after and gate_before == gate_after
              and read_fix_before == sha(READ_FIX))
    report = {'protocol': PROTOCOL, 'passed': passed, 'count': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'source_unchanged': before == after, 'source_sha256': after,
        'test_targets': list(TESTS), 'test_execution_count': 1,
        'scope': 'new off/on entry mocks only; completed K121 gate is reused without rerun',
        'K121_gate_path': K121_GATE.relative_to(REPO).as_posix(),
        'K121_evidence_sha256': gate_after, 'K121_39_sources_exactly_matched': True,
        'new_real_model_LP_heat_MATLAB_or_research_calls': 0,
        'old_whole_worker_gate_claimed_current': False,
        'read_fix_report_sha256': sha(READ_FIX),
        'K117_original_passed_false_and_shutdown_limit_retained': True,
        'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out / 'checks.json', report)
    print(json.dumps({'passed': passed, 'count': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'source_count': len(after), 'new_research_calls': 0}, ensure_ascii=False), flush=True)
    return passed


def admission(checks):
    sources = collect_sources()
    receipt = read(checks)
    if (receipt.get('protocol') != PROTOCOL or receipt.get('passed') is not True
            or receipt.get('source_unchanged') is not True
            or receipt.get('source_sha256') != sources
            or receipt.get('test_targets') != list(TESTS)
            or receipt.get('failures') != 0 or receipt.get('errors') != 0):
        raise ValueError('Necessary K122 entry checks missing/stale/failed')
    if receipt.get('K121_evidence_sha256') != _k121_evidence():
        raise ValueError('Completed K121 gate evidence changed')
    if receipt.get('read_fix_report_sha256') != sha(READ_FIX):
        raise ValueError('Historical K117 record changed')
    if CLAIM.exists():
        raise FileExistsError('K122 off/on pair already consumed; no retry')
    return sources


def _frozen_rules():
    return {'protocol': PROTOCOL, 'problem_id': PROBLEM,
        'settings_in_order': list(SETTINGS), 'call_names_in_order': ['call_off', 'call_on'],
        'research_calls': 2, 'per_call_budget_s': SECONDS,
        'per_call_scene_slice_s': SLICE_SECONDS, 'shared_deployment': dict(SHARED),
        'analysis_scope': 'fixed_shared_deployment_not_global16',
        'input_recipe': 'fresh load_config/build_instance(base__R1)/explicit autoL inside each budget',
        'physical_parameter_override': False, 'starts_override': None,
        'window_ms': 400, 'start_grid_ms': 5,
        'initial_temperature_degC': 50, 'temperature_limit_degC': 80,
        'local_mapping_OPP_start_choices_remain_free': True,
        'new_worker_models_initialisation_and_caches_each_call': True,
        'only_varied_factor': 'builder_options.cumulative_precedence False then True',
        'CutMaxIterations': CUT_MAX_ITERATIONS, 'CutGeneration': 'basic',
        'all_other_solver_options': 'unchanged current R2023b path',
        'retry_allowed': False, 'budget_extension_allowed': False,
        'formal_comparison': False, 'historical_K119_is_control': False,
        'K121_62_checks_rerun': False, 'old_whole_worker_gate_claimed_current': False,
        'K117_original_failed_gate_and_shutdown_limit_retained': True,
        'billed': 'fresh input, bounds, construction, init, worker startup, export, solve, callbacks, continuous recheck, feedback and live logs',
        'separately_reported': 'imports/source snapshots; cleanup; completed-evidence serialization and read-only analysis',
        'authorization': 'user 继续 after K121 proposed the fixed-condition cumulative off/on pair'}


def prepare(out, checks):
    out = _workspace_path(out)
    sources = admission(checks)
    out.mkdir(parents=True, exist_ok=False)
    for name in sources:
        target = out / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, target)
    evidence = out / 'precheck_evidence'
    evidence.mkdir()
    (evidence / 'K121').mkdir()
    for name in K121_FILES:
        shutil.copy2(K121_GATE / name, evidence / 'K121' / name)
    shutil.copy2(READ_FIX, evidence / 'K117_verification.json')
    shutil.copy2(checks, evidence / 'targeted_checks.json')
    declaration = {**_frozen_rules(), 'state': 'DECLARED_NOT_RUN',
        'source_sha256': sources, 'checks_path': _workspace_path(checks).relative_to(REPO).as_posix(),
        'checks_sha256': sha(checks),
        'K121_gate_path': K121_GATE.relative_to(REPO).as_posix(),
        'K121_evidence_sha256': _k121_evidence(), 'K117_read_fix_report_sha256': sha(READ_FIX),
        'declared_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out / 'declaration.json', declaration)
    save(out / 'environment.json', {'python': sys.version, 'platform': platform.platform()})
    print(json.dumps({'prepared': True, 'source_count': len(sources),
                      'research_calls': 0, 'out': str(out)}), flush=True)


def _execute_one(out, enabled):
    if type(enabled) is not bool:
        raise ValueError('cumulative precedence setting must be a strict bool')
    from control_policy import with_auto_low_idle
    from inputs import build_instance, load_config
    from matlab_bridge import MatlabSession
    from partial_method import execute_shared_deployment

    def loader(budget):
        raw = load_config()
        instance = build_instance(raw, PROBLEM, budget=budget)
        return with_auto_low_idle(raw), with_auto_low_idle(instance)

    return execute_shared_deployment(loader, out / 'invocation',
        shared_deployment=dict(SHARED), seconds=SECONDS, scene_slice_s=SLICE_SECONDS,
        builder_options={'cumulative_precedence': enabled},
        session_factory=partial(MatlabSession, cut_max_iterations=CUT_MAX_ITERATIONS))


def _technical_issues(result):
    """A retained SAFE never hides errors in any scene/native response."""
    bad = {'INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
           'INVALID_INPUT_OR_INTERFACE', 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED',
           'NUMERICAL_CANDIDATE_ANOMALY', 'INITIALISATION_ERROR'}
    issues = []

    def inspect(record, scope):
        if not isinstance(record, dict):
            issues.append({'scope': scope, 'reason': 'NONMAPPING_RECEIPT'})
            return
        if record.get('reason') in bad or record.get('error') or record.get('cleanup_error'):
            issues.append({'scope': scope, 'reason': record.get('reason'),
                           'error': record.get('error') or record.get('cleanup_error')})
        if record.get('status') in ('ERROR', 'WORKER_EXITED'):
            issues.append({'scope': scope, 'reason': record['status']})
        if (record.get('numerical_consistency') or {}).get('state') == 'NUMERICAL_ADMISSION_STATUS_CONFLICT':
            issues.append({'scope': scope, 'reason': 'NUMERICAL_ADMISSION_STATUS_CONFLICT'})

    inspect(result, 'method')
    if isinstance(result, dict):
        for sid, scene in result.get('scenes', {}).items():
            inspect(scene, sid)
            solved = scene.get('solver_result') or {}
            inspect(solved, sid + ':solver')
            for number, response in enumerate(solved.get('rounds', []), 1):
                inspect(response, sid + ':native:' + str(number))
    return issues


def run(out):
    out = _workspace_path(out)
    declaration = read(out / 'declaration.json')
    checks = _workspace_path(REPO / declaration['checks_path'])
    sources = admission(checks)
    rules_match = all(json.dumps(declaration.get(key), sort_keys=True)
                      == json.dumps(value, sort_keys=True) for key, value in _frozen_rules().items())
    if (not rules_match or declaration.get('source_sha256') != sources
            or declaration.get('checks_sha256') != sha(checks)
            or declaration.get('K121_evidence_sha256') != _k121_evidence()
            or declaration.get('K117_read_fix_report_sha256') != sha(READ_FIX)):
        raise ValueError('Frozen protocol/source/rule mismatch')
    for name, expected in sources.items():
        if sha(out / 'source_snapshot' / name) != expected:
            raise ValueError('Frozen snapshot changed: ' + name)
    evidence = out / 'precheck_evidence'
    for name, expected in declaration['K121_evidence_sha256'].items():
        if sha(evidence / 'K121' / name) != expected:
            raise ValueError('Frozen K121 evidence changed: ' + name)
    if (sha(evidence / 'K117_verification.json') != sha(READ_FIX)
            or sha(evidence / 'targeted_checks.json') != sha(checks)):
        raise ValueError('Frozen entry/historical evidence changed')
    if any((out / name).exists() for name in ('call_off', 'call_on')):
        raise FileExistsError('Existing call output: no overwrite/retry')
    with CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'state': 'CLAIMED_NO_RETRY', 'declaration_sha256': sha(out / 'declaration.json'),
            'settings': list(SETTINGS), 'per_call_budget_s': SECONDS,
            'claimed_at_utc': datetime.now(timezone.utc).isoformat()}, stream, indent=2)
    report = {'protocol': PROTOCOL, 'analysis_scope': 'fixed_shared_deployment_not_global16',
        'state': 'RUNNING', 'declaration_sha256': sha(out / 'declaration.json'),
        'source_sha256': sources, 'shared_deployment': dict(SHARED),
        'K121_evidence_sha256': declaration['K121_evidence_sha256'],
        'K117_read_fix_report_sha256': sha(READ_FIX),
        'K117_original_failed_gate_and_shutdown_limit_retained': True,
        'per_call_budget_s': SECONDS, 'scene_slice_s': SLICE_SECONDS,
        'cut_max_iterations': CUT_MAX_ITERATIONS, 'calls': [],
        'scope': 'only pre-cutoff method evidence; no post-cutoff evaluation/search/aggregation'}
    save(out / 'run_record.json', report)
    stop = False
    for enabled in SETTINGS:
        label = 'on' if enabled else 'off'
        if stop:
            report['calls'].append({'cumulative_precedence': enabled,
                                    'state': 'NOT_RUN_AFTER_TECHNICAL_FAILURE'})
            break
        call = out / ('call_' + label)
        call.mkdir(exist_ok=False)
        print(f'START K122 cumulative={label}, CutMaxIterations=10; {SECONDS}s total, {SLICE_SECONDS}s scenes', flush=True)
        began = time.monotonic()
        result = error = None
        try:
            result = _execute_one(call, enabled)
        except BaseException:
            error = traceback.format_exc()
        wall = time.monotonic() - began
        cleanup_status = cleanup_metadata_error = None
        closed_path = call / 'invocation/matlab/closed.json'
        if closed_path.exists():
            try:
                cleanup_status = read(closed_path)
                if not isinstance(cleanup_status, dict):
                    cleanup_metadata_error = 'Native cleanup receipt is not a mapping'
            except (OSError, ValueError) as exc:
                cleanup_metadata_error = f'{type(exc).__name__}: {exc}'
        elif isinstance(result, dict) and (result.get('matlab_worker_ready')
                                         or result.get('solver_request_attempts', 0)):
            cleanup_metadata_error = 'Native worker used but cleanup receipt missing'
        source_error = None
        try:
            unchanged = (collect_sources() == sources
                and _k121_evidence() == declaration['K121_evidence_sha256']
                and sha(READ_FIX) == declaration['K117_read_fix_report_sha256'])
        except (OSError, ValueError) as exc:
            unchanged = False
            source_error = f'{type(exc).__name__}: {exc}'
        method = result if isinstance(result, dict) else {}
        issues = _technical_issues(result)
        record = {'cumulative_precedence': enabled, 'cut_max_iterations': CUT_MAX_ITERATIONS,
            'relative_path': call.name, 'state': 'RETURNED' if error is None else 'INVOCATION_EXCEPTION',
            'error': error, 'wrapper_call_wall_s': wall, 'source_unchanged': unchanged,
            'source_check_error': source_error, 'technical_issues': issues,
            'method_state': method.get('state'), 'method_reason': method.get('reason'),
            'cleanup_error': method.get('cleanup_error'), 'cleanup_status': cleanup_status,
            'cleanup_metadata_error': cleanup_metadata_error,
            'safe_upper_bound_J': method.get('safe_upper_bound_J'),
            'method_timing': method.get('timing')}
        save(call / 'run_record.json', record)
        report['calls'].append(record)
        cleanup_failed = (isinstance(cleanup_status, dict) and (
            cleanup_status.get('cleanup_pending_pid') is not None
            or bool(cleanup_status.get('error') or cleanup_status.get('cleanup_error'))
            or cleanup_status.get('returncode') not in (None, 0)))
        stop = (error is not None or not unchanged or bool(issues)
                or cleanup_metadata_error is not None or cleanup_failed)
        save(out / 'run_record.json', report)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    report['state'] = 'STOPPED_TECHNICAL_FAILURE' if stop else 'PAIR_COMPLETED'
    report['research_calls_consumed'] = sum(
        item['state'] != 'NOT_RUN_AFTER_TECHNICAL_FAILURE' for item in report['calls'])
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    save(out / 'run_record.json', report)
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
