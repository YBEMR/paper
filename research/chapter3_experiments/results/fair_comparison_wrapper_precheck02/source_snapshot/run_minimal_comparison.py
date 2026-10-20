"""K141 preparation for one original-input four-method comparison.

Preparation and mock precheck do not construct a physical model or run a
method. The later run is single-use, four independent 300 s calls, no retries.
"""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
from fractions import Fraction
from functools import partial
import io
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
import unittest
from unittest.mock import patch

import run_linked_pair as linked

HERE, REPO = linked.HERE, linked.REPO
read, save, sha, local, sources, now = (linked.read, linked.save, linked.sha,
    linked.local, linked.sources, linked.now)
PROTOCOL = 'K141-original-autoL-four-method-comparison-preparation-v1'
PRECHECK_PROTOCOL = 'K141-mocked-minimal-comparison-wrapper-precheck-v1'
BASE_DECLARATION = HERE/'results/linked_quality_pair01/declaration.json'
K140_CHECKS = HERE/'results/linked_pair_wrapper_precheck02/checks.json'
K139_CHECKS = linked.METHOD_CHECKS
K127_DECLARATION = HERE/'results/night_k127_run02/declaration.json'
GLOBAL_CLAIM = HERE/'results/minimal_comparison_claim01.json'
WRAPPERS = ('run_minimal_comparison.py', 'test_minimal_comparison.py')
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10
SHARED, BUILD_OPTIONS = deepcopy(linked.SHARED), deepcopy(linked.BUILD_OPTIONS)
INPUT_IDENTITIES = {
    'input_sha256': '989697215b8609cb855b17234ed5d5532d8155c7b382a743de618cfcc8901e27',
    'config_sha256': '15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83',
    'raw_config_sha256': 'd4d6c6c76f0e0adcf3bef128368941a05036ae16cbd301fbf19a887f51e4a387'}


def jobs():
    return [{'id': 'whole_milp', 'method': 'milp', 'feedback_kind': 'conditional'},
            {'id': 'linked_n1', 'method': 'linked_fixed_unit_opp_start'},
            {'id': 'heft', 'method': 'heft'},
            {'id': 'sa101', 'method': 'sa', 'seed': 101}]


def prerequisites():
    return {'K140_declaration': BASE_DECLARATION, 'K140_wrapper_checks': K140_CHECKS,
            'K139_method_checks': K139_CHECKS, 'K127_declaration': K127_DECLARATION}


def method_gate(current):
    base = read(BASE_DECLARATION)
    inherited = base.get('source_sha256', {})
    expected_new = {(HERE/n).relative_to(REPO).as_posix() for n in WRAPPERS}
    if (len(inherited) != 157 or any(current.get(n) != h for n, h in inherited.items())
            or set(current)-set(inherited) != expected_new
            or any(base.get(k) != v for k, v in INPUT_IDENTITIES.items())):
        raise ValueError('Unchanged K140 157-source/input basis plus only two K141 wrappers required')
    # These gates are checked against the matching inherited subset, not the
    # newer 159-source set, and are not advertised as freshly rerun tests.
    linked.method_gate(K139_CHECKS, inherited)
    linked.wrapper_gate(K140_CHECKS, inherited)
    if (sha(K140_CHECKS) != base.get('wrapper_checks_sha256')
            or sha(K139_CHECKS) != base.get('method_checks_sha256')):
        raise ValueError('K140 admitted gate hashes changed')
    older = read(K127_DECLARATION).get('source_sha256', {})
    changed = {n for n, h in older.items() if current.get(n) != h}
    allowed = {'research/chapter3_experiments/'+n for n in
               ('matlab_bridge.py', 'milp.py', 'neighborhood_method.py')}
    if len(older) != 125 or changed != allowed or len(set(older)-changed) != 122:
        raise ValueError('K127 122 unchanged sources and three documented later adaptations required')
    return {'K140_source_count': 157, 'current_source_count': len(current),
        'K127_source_count': 125, 'K127_unchanged_count': 122,
        'K127_changed_sources': sorted(changed), 'old_67_tests_rerun': False,
        'prerequisite_sha256': {k: sha(v) for k, v in prerequisites().items()}}


def wrapper_gate(path, current):
    gate = read(path)
    if (gate.get('protocol') != PRECHECK_PROTOCOL or gate.get('passed') is not True
            or gate.get('tests_run', 0) < 20 or gate.get('errors') != 0
            or gate.get('failures') != 0 or gate.get('error') is not None
            or gate.get('source_sha256') != current or gate.get('source_unchanged') is not True
            or any(gate.get(k) != 0 for k in
                   ('native_calls', 'research_calls', 'physical_models', 'thermal_evaluations'))
            or not gate.get('blocked_calls') or any(gate['blocked_calls'].values())):
        raise ValueError('Matching passing K141 pure-mock wrapper gate required')
    return gate


def rules():
    return {'protocol': PROTOCOL, 'jobs': jobs(), 'method_call_limit': 4,
        'per_method_budget_s': SECONDS, 'scene_slice_s': SCENE_SECONDS,
        'CutMaxIterations': CUT, 'shared_deployment_linked_only': SHARED,
        'builder_options_linked': BUILD_OPTIONS,
        'whole_builder_options': {'prefilter_deadlines': True, 'cumulative_precedence': False},
        'whole_execute_warm_inherited_flags': {k: BUILD_OPTIONS[k] for k in
            ('fix_late_options', 'aggregate_opp_locks', 'relax_auxiliary_integrality', 'strengthen_energy_lower_bounds')},
        'retry_allowed': False, 'extend_budget_allowed': False,
        'technical_fault_stops_remaining_jobs': True,
        'problem': 'base__R1 original full AB/AC three-Stage chains',
        'window_ms': 400, 'start_grid_ms': 5, 'entry_temperature_degC': 50,
        'maximum_temperature_degC': 80, 'idle_policy': 'auto_low_immediate_v1',
        'input_identities': INPUT_IDENTITIES,
        'initialisation': 'each existing entry independently constructs its own billed input/seed/cache; no cross-call candidates or receipts',
        'method_capabilities': 'whole/HEFT/SA retain their existing deployment choices; linked uses original fresh seed units and two declared local passes',
        'thermal_acceptance': 'unchanged complete original scenes/window continuous safety and energy enclosure',
        'SA_scope': 'one fixed seed 101 exploratory observation; no general stochastic ranking',
        'native_MaxTime_semantics': 'cooperative; actual stop delay recorded, no late evidence',
        'clock_semantics': 'existing entries start MethodBudget before fresh input; common entry-module imports before clocks separately measured; linked internal lazy work remains billed',
        'wrapper_clock_semantics': 'method return incl cleanup, then validation and primary serialization; own clock receipt write excluded',
        'proof_scope': 'independent physical L0 separate from solver reported/internal or restricted-domain bounds; no new global proof',
        'preparation_only_this_stage': True,
        'run_requires_separate_execution_authorization': True}


def common_entry_points():
    """Imports only; called once outside method clocks and explicitly timed."""
    from formal_milp import execute_formal_milp
    from linked_method import execute_linked_fixed_unit_opp_start
    from heuristic_runner import execute_heuristic
    from milp import build_model
    from matlab_bridge import MatlabSession
    return dict(whole=execute_formal_milp, linked=execute_linked_fixed_unit_opp_start,
                heuristic=execute_heuristic, builder=build_model, session=MatlabSession)


def prepare(out, checks):
    from run_neighborhood_diagnostic import fresh_input, opened_stages
    from scene_adapter import canonical_hash
    out = local(out)
    if GLOBAL_CLAIM.exists():
        raise FileExistsError('Four-method comparison already claimed')
    current = sources()
    basis = method_gate(current)
    wrapper_gate(checks, current)
    raw, config, instance = fresh_input()
    identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                          map(canonical_hash, (raw, config, instance))))
    if identities != INPUT_IDENTITIES:
        raise ValueError('Original input identities changed')
    imported_at = time.monotonic()
    common_entry_points()
    import_wall = time.monotonic()-imported_at
    out.mkdir(parents=True, exist_ok=False)
    (out/'claims').mkdir()
    for name, value in zip(('input_raw.json', 'input_config.json', 'input_instance.json'),
                           (raw, config, instance)):
        save(out/name, value)
    for name, digest in current.items():
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        if sha(target) != digest:
            raise ValueError('Source changed while preparing')
    shutil.copyfile(checks, out/'wrapper_checks.json')
    declaration = {**rules(), **identities, 'source_sha256': current,
        'old_opened_by_scene': opened_stages(instance),
        'new_opened_by_scene': linked.linked_opened(instance),
        'linked_opened_by_scene': linked.linked_opened(instance),
        'prerequisite_sha256': basis['prerequisite_sha256'],
        'input_file_sha256': {n: sha(out/n) for n in
            ('input_raw.json', 'input_config.json', 'input_instance.json')},
        'wrapper_checks_sha256': sha(out/'wrapper_checks.json'), 'declared_at_utc': now()}
    save(out/'declaration.json', declaration)
    save(out/'source_inheritance.json', basis)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'state': 'DECLARED', 'consumed': 0,
         'method_budget_s_reserved': 0, 'calls': [], 'declared_at_utc': now()})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform(),
        'preparation_common_entry_import_s': import_wall,
        'scope': 'preparation imports/identity freezing only; no physical or research calls'})
    admission(out)
    print(json.dumps({'prepared': True, 'research_calls': 0, 'future_jobs': 4,
                      'per_method_s': SECONDS, 'source_files': len(current)}), flush=True)


def admission(out):
    from run_neighborhood_diagnostic import opened_stages
    from scene_adapter import canonical_hash
    d, current = read(out/'declaration.json'), sources()
    basis = method_gate(current)
    if (any(d.get(k) != v for k, v in rules().items()) or d.get('source_sha256') != current
            or d.get('prerequisite_sha256') != basis['prerequisite_sha256']
            or sha(out/'wrapper_checks.json') != d.get('wrapper_checks_sha256')):
        raise ValueError('Frozen rules/source/prerequisites/wrapper gate changed')
    wrapper_gate(out/'wrapper_checks.json', current)
    for name, digest in current.items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Frozen source snapshot changed: '+name)
    for name, digest in d['input_file_sha256'].items():
        if sha(out/name) != digest:
            raise ValueError('Frozen input bytes changed: '+name)
    for name, key in [('input_raw.json', 'raw_config_sha256'), ('input_config.json', 'config_sha256'),
                      ('input_instance.json', 'input_sha256')]:
        if canonical_hash(read(out/name)) != d.get(key) or d.get(key) != INPUT_IDENTITIES[key]:
            raise ValueError('Frozen input identity changed: '+name)
    instance = read(out/'input_instance.json')
    if (d.get('old_opened_by_scene') != opened_stages(instance)
            or d.get('new_opened_by_scene') != linked.linked_opened(instance)
            or d.get('linked_opened_by_scene') != d.get('new_opened_by_scene')):
        raise ValueError('Frozen linked opening changed')
    return d


def execute(job, out, declaration, entries=None):
    from run_neighborhood_diagnostic import fresh_input, opened_stages
    from scene_adapter import canonical_hash
    from partial_bounds import independent_lower_bound
    if job not in jobs():
        raise ValueError('Unknown frozen method')
    entries = common_entry_points() if entries is None else entries
    lower = {}
    def loader(budget):
        raw, config, instance = fresh_input(budget)
        if (canonical_hash(instance) != declaration['input_sha256']
                or canonical_hash(config) != declaration['config_sha256']
                or canonical_hash(raw) != declaration['raw_config_sha256']
                or opened_stages(instance) != declaration['old_opened_by_scene']):
            raise ValueError('Billed fresh input identity/opening changed')
        if job['method'] == 'milp':
            with budget.phase('comparison_independent_lower_bound'):
                lower['L0'] = independent_lower_bound(instance, None, budget)
        budget.check()
        return config, instance
    folder = out/job['id']
    factory = partial(entries['session'], cut_max_iterations=CUT)
    if job['method'] == 'milp':
        result = entries['whole'](loader, folder, seconds=SECONDS, feedback_kind='conditional',
            model_builder=partial(entries['builder'], prefilter_deadlines=True, cumulative_precedence=False),
            session_factory=factory)
    elif job['method'] == 'linked_fixed_unit_opp_start':
        def update(result, record):
            print(json.dumps({'event': 'SAFE_AGGREGATE_UPDATE', 'method': job['id'],
                'phase_index': record.get('phase_index'), 'elapsed_s': record['committed_at_s'],
                'U_J': record['safe_upper_bound_J']}, ensure_ascii=False), flush=True)
        result = entries['linked'](loader, folder, seconds=SECONDS,
            shared_deployment=deepcopy(SHARED), scene_slice_s=SCENE_SECONDS,
            builder_options=deepcopy(BUILD_OPTIONS), session_factory=factory,
            opened_by_scene=deepcopy(declaration['old_opened_by_scene']),
            linked_opened_by_scene=deepcopy(declaration['new_opened_by_scene']), on_global_update=update)
    else:
        result = entries['heuristic'](loader, folder, method=job['method'], seconds=SECONDS,
                                     seed=job.get('seed'), allow_auto_low=True)
    if lower:
        save(folder/'independent_bounds.json', lower)
    return result


def technical_issues(job, result, declaration):
    from run_night_after_k126 import technical_issues as original_issues
    if not isinstance(result, dict):
        return [{'scope': 'method', 'reason': 'NO_METHOD_RESULT'}]
    issues = original_issues(result)
    if job['method'] == 'linked_fixed_unit_opp_start':
        issues.extend(linked.transport_issues(linked.jobs()[1], result, declaration))
    return issues


def evidence_summary(job, result):
    """Archive existing fields only. Different entry lifecycles stay explicit."""
    result = result if isinstance(result, dict) else {}
    kind = job['method']
    if kind == 'linked_fixed_unit_opp_start':
        energy = result.get('weighted_energy_J')
        first = result.get('first_safe_at_s')
        first_source = 'first_safe_at_s (complete global aggregate)'
        lower = result.get('deployment_bounds')
        candidate_first = legal_first = None
        first_detail = {'complete_global_first_safe_at_s': first,
            'local_scene_first_safe_at_s': {s: v.get('first_safe_at_s') for s, v in result.get('scenes', {}).items()},
            'scope': 'local scene safe times are not a complete first solution'}
    else:
        energy = (result.get('evaluation') or {}).get('weighted_energy_J')
        lower = result.get('independent_lower_bound')
        if kind == 'milp':
            candidates = [result.get('first_initial_safe_s')]
            diagnostic = result.get('solver_diagnostic') or {}
            nested = diagnostic.get('recorder') or diagnostic.get('diagnostic') or {}
            candidates.extend([diagnostic.get('first_safe_receipt_s'), nested.get('first_safe_receipt_s')])
            valid = [v for v in candidates if type(v) in (int, float) and math.isfinite(v) and 0 <= v < SECONDS]
            first = min(valid) if valid else None
            first_source = 'min(recorded initial complete SAFE, recorded complete solver SAFE); missing remains unknown'
            candidate_first = diagnostic.get('first_candidate_received_s')
            legal_first = diagnostic.get('first_legal_candidate_s')
            first_detail = {'initial_complete_first_safe_s': result.get('first_initial_safe_s'),
                            'solver_complete_first_safe_receipt_s': diagnostic.get('first_safe_receipt_s')}
        else:
            first = result.get('first_safe_at_s')
            first_source = 'first_safe_at_s (CandidateRecorder complete evaluation)'
            candidate_first = result.get('first_candidate_at_s')
            legal_first = result.get('first_legal_candidate_at_s')
            first_detail = {'complete_first_safe_at_s': first}
    return {'safe_upper_bound_J': result.get('safe_upper_bound_J'), 'weighted_energy_J': energy,
        'first_complete_safe_at_s': first, 'first_complete_safe_source': first_source,
        'first_candidate_at_s': candidate_first, 'first_legal_candidate_at_s': legal_first,
        'first_safe_detail': first_detail, 'independent_bound_receipt': deepcopy(lower),
        'independently_proven_optimal': result.get('independently_proven_optimal'),
        'independently_proven_infeasible': result.get('independently_proven_infeasible'),
        'coverage_complete': result.get('coverage_complete'), 'solver_reported': deepcopy(result.get('solver_reported')),
        'initial_safe_upper_bound_J': result.get('initial_global_safe_upper_bound_J', result.get('initial_safe_upper_bound_J')),
        'global_updates': deepcopy(result.get('global_updates', [])),
        'heuristic_events': deepcopy(result.get('events', [])),
        'phase_quality': linked.phase_quality(result) if kind == 'linked_fixed_unit_opp_start' else [],
        'safe_U_preserved_even_if_later_technical_issue': True}


def run(out, *, execution_authorized=False):
    from matlab_bridge import cleanup_is_complete
    out = local(out)
    ledger = read(out/'ledger.json')
    if (ledger.get('state') != 'DECLARED' or ledger.get('consumed') != 0
            or ledger.get('calls') != [] or GLOBAL_CLAIM.exists()
            or any((out/'claims'/(j['id']+'.json')).exists() for j in jobs())):
        raise FileExistsError('Already claimed/consumed; no retry/restart/alternate-output run')
    if execution_authorized is not True:
        raise PermissionError('K141 prepares only; a later explicitly authorized execution must opt in')
    d = admission(out)
    started_all = time.monotonic()
    imported = time.monotonic()
    entries = common_entry_points()
    import_wall = time.monotonic()-imported
    save(out/'runtime_common_imports.json', {'common_entry_import_wall_s': import_wall,
        'scope': 'imports only before all MethodBudget clocks; actual internal lazy work remains billed',
        'physical_models': 0, 'thermal_evaluations': 0, 'research_calls': 0})
    with GLOBAL_CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'declaration_sha256': sha(out/'declaration.json'), 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
    okay = True
    for job in jobs():
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
        row = {**job, 'state': 'RUNNING', 'started_at_utc': now(), 'seconds': SECONDS}
        ledger['calls'].append(row)
        ledger.update(state='RUNNING', consumed=ledger['consumed']+1,
                      method_budget_s_reserved=ledger['method_budget_s_reserved']+SECONDS)
        save(out/'ledger.json', ledger)
        print('START '+job['id']+' independent fresh 300 s; no retry', flush=True)
        started = time.monotonic()
        result = error = None
        try:
            result = execute(job, out, d, entries)
        except BaseException:
            error = traceback.format_exc()
        returned = time.monotonic()-started
        try:
            admission(out)
            unchanged = True
        except Exception:
            unchanged = False
            error = (error or '')+'\n'+traceback.format_exc()
        try:
            issues = technical_issues(job, result, d)
        except Exception:
            issues = [{'scope': 'wrapper_validation', 'reason': 'MALFORMED_METHOD_RECEIPT'}]
            error = (error or '')+'\n'+traceback.format_exc()
        cleanup = None
        try:
            closed = out/job['id']/'matlab/closed.json'
            cleanup = read(closed) if closed.is_file() else None
            if isinstance(result, dict) and result.get('matlab_worker_ready') and not cleanup:
                issues.append({'scope': 'cleanup', 'reason': 'MISSING_CLOSED_RECEIPT'})
            if cleanup and not cleanup_is_complete(cleanup):
                issues.append({'scope': 'cleanup', 'reason': 'WORKER_CLEANUP_ANOMALY'})
        except Exception:
            error = (error or '')+'\n'+traceback.format_exc()
        failed = bool(error or issues or not unchanged)
        evidence = result if isinstance(result, dict) else {}
        row.update(state='TECHNICAL_BLOCK' if failed else 'COMPLETED', error=error,
            technical_issues=issues, source_unchanged=unchanged, cleanup=cleanup,
            method_return_inclusive_wall_s=returned, completed_at_utc=now(),
            method_state=evidence.get('state'), reason=evidence.get('reason'),
            method_timing=deepcopy(evidence.get('timing')), **evidence_summary(job, evidence))
        if job['method'] == 'milp' and (out/job['id']/'independent_bounds.json').is_file():
            row['independent_bound_receipt'] = read(out/job['id']/'independent_bounds.json')
        ledger['state'] = 'BLOCKED' if failed else 'RUNNING'
        save(out/'claims'/(job['id']+'_result.json'), row)
        save(out/'ledger.json', ledger)
        timing = linked.timing_components(time.monotonic()-started, result)
        save(out/'claims'/(job['id']+'_wrapper_timing.json'), timing)
        print(json.dumps({k: row.get(k) for k in ('id', 'state', 'reason', 'safe_upper_bound_J')}), flush=True)
        if failed:
            okay = False
            break
    if okay:
        ledger['state'] = 'COMPLETED'
        save(out/'ledger.json', ledger)
    save(out/'wrapper_timing.json', {'common_entry_import_wall_s': import_wall,
        'wrapper_run_through_primary_archives_wall_s': time.monotonic()-started_all,
        'clock_receipt_own_write_included': False,
        'scope': 'imports, method calls/cleanup, validation, primary archives; no post-cutoff new evidence'})
    return okay


def precheck(out):
    import subprocess
    import scipy.optimize
    import matlab_bridge
    import milp
    import scene_adapter
    out = local(out)
    out.mkdir(parents=True, exist_ok=False)
    before = sources()
    started, captured, error, result = time.monotonic(), io.StringIO(), None, None
    # Windows platform metadata can shell out once. Capture before the pure
    # mock guard; none of those discovery processes is a research invocation.
    environment = {'python': sys.version, 'platform': platform.platform()}
    blocked = {}
    def forbidden(name):
        blocked[name] = 0
        def reject(*args, **kwargs):
            blocked[name] += 1
            raise AssertionError('K141 wrapper precheck forbids '+name)
        return reject
    try:
        basis = method_gate(before)
        with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
            for obj, name in ((subprocess, 'Popen'), (scipy.optimize, 'milp'), (scipy.optimize, 'linprog'),
                (matlab_bridge.MatlabSession, '__init__'), (milp, 'build_model'),
                (milp, 'evaluate_model_candidate'), (scene_adapter, 'evaluate_partial_scene'),
                (scene_adapter, 'evaluate_piecewise')):
                stack.enter_context(patch.object(obj, name, side_effect=forbidden(obj.__name__+'.'+name)))
            suite = unittest.defaultTestLoader.loadTestsFromName('test_minimal_comparison')
            result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
    except BaseException:
        error = traceback.format_exc()
        captured.write(error)
    after = sources()
    report = {'protocol': PRECHECK_PROTOCOL,
        'passed': bool(result and result.wasSuccessful() and before == after and not error and not any(blocked.values())),
        'tests_run': result.testsRun if result else 0, 'errors': len(result.errors) if result else 1,
        'failures': len(result.failures) if result else 0, 'source_sha256': after,
        'source_unchanged': before == after, 'native_calls': 0, 'research_calls': 0,
        'physical_models': 0, 'thermal_evaluations': 0, 'blocked_calls': blocked,
        'source_scope': 'K140 157 unchanged; two new K141 wrappers only behavior-tested',
        'elapsed_s': time.monotonic()-started, 'error': error, 'completed_at_utc': now()}
    (out/'unittest.txt').write_text(captured.getvalue(), encoding='utf-8')
    save(out/'checks.json', report)
    save(out/'environment.json', environment)
    for name in WRAPPERS:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE/name, target)
    print(json.dumps({k: report[k] for k in ('passed', 'tests_run', 'errors', 'failures', 'elapsed_s')}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ('precheck', 'prepare', 'run'):
        modes.add_argument('--'+mode, action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    parser.add_argument('--execution-authorized', action='store_true',
                        help='Only use after a separate explicit authorization to execute the frozen comparison')
    args = parser.parse_args()
    if args.precheck:
        raise SystemExit(0 if precheck(args.out) else 1)
    if args.prepare:
        if args.checks is None:
            parser.error('--prepare requires --checks')
        prepare(args.out, args.checks)
    else:
        raise SystemExit(0 if run(args.out, execution_authorized=args.execution_authorized) else 1)
