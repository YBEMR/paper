"""K135: one fresh old-N1/live-complement quality pair, 300 s per method.

Preparation freezes inputs and source only. The wrapper precheck uses mocks,
not a model, optimizer or thermal evaluator. Consumed calls are never retried.
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
import time
import traceback
import unittest
from unittest.mock import patch

import run_fixed_unit_pair as inherited

HERE, REPO = inherited.HERE, inherited.REPO
PROTOCOL = 'K135-old-N1-vs-live-complement-fixed-unit-all-opp-start-v1'
PRECHECK_PROTOCOL = 'K135-mocked-quality-pair-wrapper-precheck-v1'
METHOD_GATE_PROTOCOL = 'K134-augmented-fixed-unit-method-integration-precheck-v1'
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10
SHARED = dict(inherited.SHARED)
WRAPPERS = ('run_augmented_pair.py', 'test_augmented_pair.py')
GLOBAL_CLAIM = HERE/'results/augmented_pair_claim01.json'
BUILD_OPTIONS = {'fix_late_options': True, 'aggregate_opp_locks': True,
    'relax_auxiliary_integrality': True, 'strengthen_energy_lower_bounds': True,
    'prefilter_deadlines': True, 'cumulative_precedence': False}

read, save, sha, local, sources, now = (inherited.read, inherited.save,
    inherited.sha, inherited.local, inherited.sources, inherited.now)


def jobs():
    return [{'id': 'old_n1', 'method': 'n1'},
            {'id': 'augmented_all_opp_start', 'method': 'augmented_fixed_unit_opp_start'}]


def method_gate(path, current):
    gate = read(path)
    baseline = gate.get('source_sha256', {})
    if (gate.get('protocol') != METHOD_GATE_PROTOCOL or gate.get('passed') is not True
            or gate.get('count') != 60 or len(baseline) != 142
            or gate.get('source_unchanged') is not True
            or gate.get('historical_artifacts_unchanged') is not True
            or gate.get('error') is not None
            or any(gate.get(k) != 0 for k in ('native_calls', 'research_calls', 'original_scale_models'))
            or sum(x.get('count', 0) for x in gate.get('modules', {}).values()) != 60
            or any(not x.get('passed') or x.get('errors') or x.get('failures')
                   for x in gate.get('modules', {}).values())):
        raise ValueError('Matching completed K134 60/60 and 142-source gate required')
    mismatch = [name for name, digest in baseline.items() if current.get(name) != digest]
    if mismatch:
        raise ValueError('K134 admitted source changed: '+repr(mismatch))
    extra = set(current)-set(baseline)
    expected = {(HERE/name).relative_to(REPO).as_posix() for name in WRAPPERS}
    if extra != expected:
        raise ValueError('Only the two separately checked K135 wrappers may extend K134 sources')
    return gate


def wrapper_gate(path, current):
    gate = read(path)
    if (gate.get('protocol') != PRECHECK_PROTOCOL or gate.get('passed') is not True
            or gate.get('tests_run', 0) < 14 or gate.get('errors') != 0
            or gate.get('failures') != 0 or gate.get('source_unchanged') is not True
            or gate.get('source_sha256') != current or gate.get('error') is not None
            or gate.get('native_calls') != 0 or gate.get('research_calls') != 0
            or gate.get('physical_models') != 0 or gate.get('thermal_evaluations') != 0):
        raise ValueError('Matching passing K135 mock wrapper precheck required')
    return gate


def prepare(out, checks, method_checks):
    from scene_adapter import canonical_hash
    from run_neighborhood_diagnostic import opened_stages, fresh_input
    out = local(out)
    current = sources()
    method_gate(method_checks, current)
    wrapper_gate(checks, current)
    raw, config, instance = fresh_input()
    old_opened = opened_stages(instance)
    out.mkdir(parents=True, exist_ok=False)
    (out/'claims').mkdir()
    for name, value in [('input_raw.json', raw), ('input_config.json', config),
                        ('input_instance.json', instance)]:
        save(out/name, value)
    for name, digest in current.items():
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        if sha(target) != digest:
            raise ValueError('Source changed during preparation')
    shutil.copyfile(checks, out/'wrapper_checks.json')
    shutil.copyfile(method_checks, out/'method_checks.json')
    declaration = {'protocol': PROTOCOL, 'jobs': jobs(), 'method_call_limit': 2,
        'per_method_budget_s': SECONDS, 'scene_slice_s': SCENE_SECONDS,
        'CutMaxIterations': CUT, 'cumulative_precedence': False,
        'shared_deployment': SHARED, 'builder_options': BUILD_OPTIONS,
        'source_sha256': current, 'K134_sources_covered': 142,
        'K135_wrappers_checked_separately': list(WRAPPERS),
        'old_opened_by_scene': old_opened,
        'new_opened_by_scene': {s['id']: [i['id'] for i in s['stage_instances']]
                                for s in instance['scenarios']},
        'input_sha256': canonical_hash(instance), 'config_sha256': canonical_hash(config),
        'raw_config_sha256': canonical_hash(raw),
        'input_file_sha256': {name: sha(out/name) for name in
            ('input_raw.json', 'input_config.json', 'input_instance.json')},
        'wrapper_checks_sha256': sha(out/'wrapper_checks.json'),
        'method_checks_sha256': sha(out/'method_checks.json'),
        'problem': 'base__R1 original full AB/AC three-Stage chains',
        'window_ms': 400, 'start_grid_ms': 5, 'entry_temperature_degC': 50,
        'maximum_temperature_degC': 80, 'idle_policy': 'auto_low_immediate_v1',
        'candidate_transport_new_only': 'exact selected-row complement; original-prefix numerical admission',
        'changed_factor': 'all Stage OPP/start open at fresh-seed fixed units, plus validated numerical transport',
        'initialisation': 'independent fresh at-most-three-template constructor per invocation; no historical seed/cache',
        'primary_success': 'new complete SAFE energy upper strictly below old complete SAFE energy lower',
        'scope': 'one same-task quality diagnostic; no global optimization or statistical ranking claim',
        'retry_allowed': False, 'extend_budget_allowed': False,
        'technical_fault_stops_remaining_jobs': True, 'new_temperature_conditions': 0,
        'budget_semantics': 'each existing method owns one 300 s MethodBudget; scene MaxTime uses remaining budget and 60 s slice; no restart replenishes time',
        'wrapper_clock_semantics': 'external wrapper clock includes method return, cleanup, validation and primary tail serialization; clock receipt own write excluded and external launcher reported separately',
        'authorization': 'user 继续吧 after K134 proposed old/new one 300 s each quality pair',
        'declared_at_utc': now()}
    save(out/'declaration.json', declaration)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'state': 'DECLARED',
        'consumed': 0, 'method_budget_s_reserved': 0, 'calls': [], 'declared_at_utc': now()})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    admission(out)
    print(json.dumps({'prepared': True, 'calls': 2, 'per_method_s': SECONDS,
                      'source_files': len(current)}), flush=True)


def admission(out):
    from scene_adapter import canonical_hash
    d = read(out/'declaration.json')
    current = sources()
    if (d['protocol'] != PROTOCOL or d['jobs'] != jobs() or d['method_call_limit'] != 2
            or d['per_method_budget_s'] != SECONDS or d['scene_slice_s'] != SCENE_SECONDS
            or d['CutMaxIterations'] != CUT or d['builder_options'] != BUILD_OPTIONS
            or d['shared_deployment'] != SHARED or d['cumulative_precedence'] is not False
            or d['source_sha256'] != current or d['retry_allowed'] is not False
            or d['extend_budget_allowed'] is not False
            or sha(out/'wrapper_checks.json') != d['wrapper_checks_sha256']
            or sha(out/'method_checks.json') != d['method_checks_sha256']):
        raise ValueError('Frozen rules, source or gates changed')
    method_gate(out/'method_checks.json', current)
    wrapper_gate(out/'wrapper_checks.json', current)
    for name, digest in current.items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Frozen source snapshot changed: '+name)
    for name, digest in d['input_file_sha256'].items():
        if sha(out/name) != digest:
            raise ValueError('Frozen input file changed: '+name)
    for name, key in [('input_instance.json', 'input_sha256'),
                      ('input_config.json', 'config_sha256'), ('input_raw.json', 'raw_config_sha256')]:
        if canonical_hash(read(out/name)) != d[key]:
            raise ValueError('Frozen input identity changed')
    return d


def execute(job, out, declaration):
    from scene_adapter import canonical_hash
    from run_neighborhood_diagnostic import fresh_input, opened_stages
    from matlab_bridge import MatlabSession
    def loader(budget):
        raw, config, instance = fresh_input(budget)
        if (canonical_hash(instance) != declaration['input_sha256']
                or canonical_hash(config) != declaration['config_sha256']
                or canonical_hash(raw) != declaration['raw_config_sha256']
                or opened_stages(instance) != declaration['old_opened_by_scene']):
            raise ValueError('Billed fresh original input changed')
        budget.check()
        return config, instance
    def update(result, record):
        print(json.dumps({'event': 'SAFE_AGGREGATE_UPDATE', 'method': job['id'],
            'elapsed_s': record['committed_at_s'], 'U_J': record['safe_upper_bound_J'],
            'source': record['trigger_source']}, ensure_ascii=False), flush=True)
    options = dict(shared_deployment=dict(SHARED), seconds=SECONDS,
        scene_slice_s=SCENE_SECONDS, builder_options={'cumulative_precedence': False},
        session_factory=partial(MatlabSession, cut_max_iterations=CUT),
        on_global_update=update)
    if job['method'] == 'n1':
        from neighborhood_method import execute_n1_neighborhood
        return execute_n1_neighborhood(loader, out/job['id'],
            opened_by_scene=declaration['old_opened_by_scene'], **options)
    if job['method'] == 'augmented_fixed_unit_opp_start':
        from fixed_unit_method import execute_augmented_fixed_unit_opp_start
        return execute_augmented_fixed_unit_opp_start(loader, out/job['id'], **options)
    raise ValueError('Unknown frozen method')


def timing_components(elapsed, result):
    timing = (result or {}).get('timing') or {}
    method = timing.get('method_elapsed_excluding_cleanup_s', timing.get('method_elapsed_s'))
    cleanup = timing.get('cleanup_s')
    known = isinstance(method, (int, float)) and isinstance(cleanup, (int, float))
    return {'wrapper_call_and_primary_archive_wall_s': elapsed,
        'method_stop_elapsed_s': method, 'cleanup_s': cleanup,
        'unattributed_wrapper_archive_overhead_s': (max(0., elapsed-method-cleanup) if known else None),
        'includes_method_tail_serialization_and_wrapper_validation_and_primary_archives': True,
        'overhead_is_not_solver_time': True,
        'clock_receipt_own_serialization_included': False}


def transport_issues(job, result):
    if job['method'] != 'augmented_fixed_unit_opp_start' or not isinstance(result, dict):
        return []
    summary = result.get('augmented_transport')
    if not isinstance(summary, dict):
        return [{'scope': 'augmented_transport', 'reason': 'MISSING_TRANSPORT_RECEIPT'}]
    issues = []
    if summary.get('latched_unresolved') is not False or summary.get('failure_reasons'):
        issues.append({'scope': 'augmented_transport', 'reason': 'LATCHED_NUMERICAL_UNRESOLVED',
                       'failure_reasons': summary.get('failure_reasons')})
    for i, request in enumerate(summary.get('requests', []), 1):
        if (request.get('latched_unresolved') is not False or request.get('failure_reasons')
                or request.get('callback_publications_complete') is not True
                or request.get('expected_callback_numbers') != request.get('checked_callback_numbers')):
            issues.append({'scope': 'augmented_request:'+str(i),
                           'reason': 'REQUEST_ADMISSION_OR_CALLBACK_COVERAGE_UNRESOLVED'})
    return issues


def run(out):
    from run_neighborhood_diagnostic import technical_issues
    from matlab_bridge import cleanup_is_complete
    pair_started = time.monotonic()
    out = local(out)
    d = admission(out)
    ledger = read(out/'ledger.json')
    if ledger.get('state') == 'BLOCKED':
        raise FileExistsError('Technical failure blocked this pair; consumed calls cannot retry')
    claim_identity = {'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
                      'declaration_sha256': sha(out/'declaration.json')}
    if GLOBAL_CLAIM.exists():
        old = read(GLOBAL_CLAIM)
        if any(old.get(k) != v for k, v in claim_identity.items()) or not ledger['calls']:
            raise FileExistsError('This one-pair protocol was already claimed; no alternate-out retry')
    else:
        with GLOBAL_CLAIM.open('x', encoding='utf-8') as stream:
            json.dump({**claim_identity, 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
    ok = True
    for job in jobs():
        previous = next((r for r in ledger['calls'] if r['id'] == job['id']), None)
        if previous:
            if previous['state'] == 'COMPLETED':
                continue
            raise FileExistsError('Consumed unsettled/failed call cannot restart: '+job['id'])
        if ledger['consumed'] >= 2:
            raise ValueError('Two-call cap consumed')
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
        row = {**job, 'state': 'RUNNING', 'started_at_utc': now(), 'seconds': SECONDS}
        ledger['calls'].append(row)
        ledger['consumed'] += 1
        ledger['method_budget_s_reserved'] += SECONDS
        ledger['state'] = 'RUNNING'
        save(out/'ledger.json', ledger)
        print('START '+job['id']+' fresh 300 s, scene 60 s, Cut10/CDFoff; no retry', flush=True)
        started = time.monotonic()
        result = error = None
        try:
            result = execute(job, out, d)
        except BaseException:
            error = traceback.format_exc()
        method_return = time.monotonic()-started
        try:
            admission(out)
            unchanged = True
        except Exception:
            unchanged = False
            error = (error or '')+'\n'+traceback.format_exc()
        issues = technical_issues(result)+transport_issues(job, result)
        if isinstance(result, dict) and result.get('condition') is not None:
            actual = result['condition']['opened_by_scene']
            expected = d['old_opened_by_scene'] if job['method'] == 'n1' else d['new_opened_by_scene']
            if {k: sorted(v) for k,v in actual.items()} != {k: sorted(v) for k,v in expected.items()}:
                issues.append({'scope': 'search_domain', 'reason': 'OPENED_DOMAIN_MISMATCH'})
        closed = out/job['id']/'matlab/closed.json'
        cleanup = None
        try:
            cleanup = read(closed) if closed.is_file() else None
        except Exception:
            error = (error or '')+'\n'+traceback.format_exc()
        if isinstance(result, dict) and result.get('matlab_worker_ready') and not cleanup:
            issues.append({'scope': 'cleanup', 'reason': 'MISSING_CLOSED_RECEIPT'})
        if cleanup and not cleanup_is_complete(cleanup):
            issues.append({'scope': 'cleanup', 'reason': 'WORKER_CLEANUP_ANOMALY'})
        failed = bool(error or issues or not unchanged)
        row.update(state='TECHNICAL_BLOCK' if failed else 'COMPLETED', error=error,
            technical_issues=issues, source_unchanged=unchanged, cleanup=cleanup,
            method_return_inclusive_wall_s=method_return, completed_at_utc=now(),
            method_state=(result or {}).get('state'), reason=(result or {}).get('reason'),
            safe_upper_bound_J=(result or {}).get('safe_upper_bound_J'),
            initial_safe_upper_bound_J=(result or {}).get('initial_global_safe_upper_bound_J'),
            method_timing=(result or {}).get('timing'),
            safe_U_preserved_even_if_later_technical_issue=True)
        if failed:
            ledger['state'] = 'BLOCKED'
        save(out/'claims'/(job['id']+'_result.json'), row)
        save(out/'ledger.json', ledger)
        # Read time only after method's own tail, validation and primary JSON
        # writes. This clock receipt's own write is excluded explicitly.
        timing = timing_components(time.monotonic()-started, result)
        save(out/'claims'/(job['id']+'_wrapper_timing.json'), timing)
        print(json.dumps({k: row.get(k) for k in ('id','state','method_state','reason','safe_upper_bound_J')})
              + ' '+json.dumps(timing), flush=True)
        if failed:
            ok = False
            break
    if ok:
        ledger['state'] = 'COMPLETED'
        save(out/'ledger.json', ledger)
    save(out/'wrapper_timing.json', {'wrapper_run_through_primary_archives_wall_s': time.monotonic()-pair_started,
        'clock_receipt_own_write_included': False,
        'scope': 'includes both method calls/cleanup, validation and primary tail serialization; no new evidence in post-cutoff archives'})
    return ok


def precheck(out):
    out = local(out)
    out.mkdir(parents=True, exist_ok=False)
    before = sources()
    started = time.monotonic()
    environment = {'python': sys.version, 'platform': platform.platform()}
    captured = io.StringIO()
    error = None
    result = None
    def forbidden(*args, **kwargs):
        raise AssertionError('Model, thermal, optimizer or subprocess forbidden in wrapper precheck')
    try:
        import subprocess
        import scipy.optimize
        import matlab_bridge
        import milp
        import scene_adapter
        from contextlib import ExitStack, redirect_stdout, redirect_stderr
        with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
            for obj, name in ((subprocess, 'Popen'), (scipy.optimize, 'milp'),
                (scipy.optimize, 'linprog'), (matlab_bridge.MatlabSession, '__init__'),
                (milp, 'build_model'), (milp, 'evaluate_model_candidate'),
                (scene_adapter, 'evaluate_partial_scene')):
                stack.enter_context(patch.object(obj, name, side_effect=forbidden))
            suite = unittest.defaultTestLoader.loadTestsFromName('test_augmented_pair')
            result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
    except BaseException:
        error = traceback.format_exc()
        captured.write(error)
    after = sources()
    report = {'protocol': PRECHECK_PROTOCOL, 'passed': bool(result and result.wasSuccessful()
              and before == after and error is None),
        'tests_run': result.testsRun if result else 0,
        'errors': len(result.errors) if result else 1,
        'failures': len(result.failures) if result else 0,
        'source_sha256': after, 'source_unchanged': before == after,
        'source_scope': 'all current source identities; behavior tests only the two K135 wrappers, K134 remains a separate 60-check gate',
        'native_calls': 0, 'research_calls': 0, 'physical_models': 0,
        'thermal_evaluations': 0, 'elapsed_s': time.monotonic()-started, 'error': error}
    (out/'unittest.txt').write_text(captured.getvalue(), encoding='utf-8')
    save(out/'checks.json', report)
    save(out/'environment.json', environment)
    for name in WRAPPERS:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE/name, target)
    print(json.dumps({k: report[k] for k in ('passed','tests_run','errors','failures','elapsed_s')}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--precheck', action='store_true')
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    parser.add_argument('--method-checks', type=Path)
    args = parser.parse_args()
    if args.precheck:
        raise SystemExit(0 if precheck(args.out) else 1)
    if args.prepare:
        if args.checks is None or args.method_checks is None:
            parser.error('--prepare requires --checks and --method-checks')
        prepare(args.out, args.checks, args.method_checks)
    else:
        raise SystemExit(0 if run(args.out) else 1)
