"""K140: one old-N1/linked-N1 pair, independent fresh 300 s calls.

Only these two wrappers extend the frozen K139 155-source set. Preparation and
mock precheck form no physical evidence. Every research claim is single use.
"""
import argparse
from copy import deepcopy
from functools import partial
from fractions import Fraction
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

import run_augmented_pair as inherited

HERE, REPO = inherited.HERE, inherited.REPO
read, save, sha, local, sources, now, timing_components = (
    inherited.read, inherited.save, inherited.sha, inherited.local,
    inherited.sources, inherited.now, inherited.timing_components)
PROTOCOL = 'K140-old-N1-vs-linked-warm-closed-fixed-unit-pair-v1'
PRECHECK_PROTOCOL = 'K140-mocked-linked-pair-wrapper-precheck-v1'
METHOD_GATE_PROTOCOL = 'K139-linked-subset-dual-anchor-correctness-precheck-v1'
METHOD_CHECKS = HERE/'results/linked_precheck02/checks.json'
GLOBAL_CLAIM = HERE/'results/linked_pair_claim01.json'
WRAPPERS = ('run_linked_pair.py', 'test_linked_pair.py')
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10
SHARED, BUILD_OPTIONS = dict(inherited.SHARED), dict(inherited.BUILD_OPTIONS)
N1_PROTOCOL = 'fixed-unit-local-opp-start-n1-v1'
LINKED_PROTOCOL = 'fixed-unit-linked-opp-start-warm-closed-v1'


def jobs():
    return [{'id': 'old_n1', 'method': 'n1'},
            {'id': 'linked_n1', 'method': 'linked_fixed_unit_opp_start'}]


def method_gate(path, current):
    gate = read(path)
    base = gate.get('source_sha256', {})
    guards = gate.get('blocked_calls', {})
    if (gate.get('protocol') != METHOD_GATE_PROTOCOL or gate.get('passed') is not True
            or gate.get('count') != 66 or gate.get('source_count') != 155 or len(base) != 155
            or gate.get('source_unchanged') is not True or gate.get('source_snapshot_mismatches') != []
            or gate.get('historical_artifact_count') != 1087
            or gate.get('historical_artifacts_unchanged') is not True
            or gate.get('historical_mismatches') != [] or gate.get('error') is not None
            or gate.get('unchanged_inherited_source_count') != 148
            or any(gate.get(k) != 0 for k in ('native_calls', 'research_calls', 'original_scale_models'))
            or set(guards) != {'scipy.optimize.milp', 'scipy.optimize.linprog',
                              'MatlabSession.__init__', 'subprocess.Popen', 'original_scale_build_model'}
            or any(guards.values())
            or sum(m.get('count', 0) for m in gate.get('modules', {}).values()) != 66
            or any(not m.get('passed') or m.get('errors') or m.get('failures') or m.get('skipped')
                   for m in gate.get('modules', {}).values())):
        raise ValueError('Completed K139 66/66, 155-source, 148-inherited, 1087-history zero-guard gate required')
    if any(current.get(name) != digest for name, digest in base.items()):
        raise ValueError('K139 admitted source changed')
    expected = {(HERE/name).relative_to(REPO).as_posix() for name in WRAPPERS}
    if set(current)-set(base) != expected:
        raise ValueError('Only the two separately checked K140 wrappers may extend K139')
    return gate


def historical_manifest():
    manifest = read(METHOD_CHECKS.parent/'parent_baseline.json')['historical_artifact_sha256']
    if len(manifest) != 1087:
        raise ValueError('K139 1087-artifact baseline required')
    return manifest


def check_history(manifest):
    if any(not (REPO/name).is_file() or sha(REPO/name) != digest
           for name, digest in manifest.items()):
        raise ValueError('K139 historical artifact changed')


def wrapper_gate(path, current):
    gate = read(path)
    if (gate.get('protocol') != PRECHECK_PROTOCOL or gate.get('passed') is not True
            or not 22 <= gate.get('tests_run', 0) <= 40
            or gate.get('errors') != 0 or gate.get('failures') != 0 or gate.get('error') is not None
            or gate.get('source_unchanged') is not True or gate.get('source_sha256') != current
            or gate.get('historical_artifacts_unchanged') is not True
            or any(gate.get(k) != 0 for k in ('native_calls', 'research_calls', 'physical_models', 'thermal_evaluations'))
            or any(gate.get('blocked_calls', {'missing': 1}).values())):
        raise ValueError('Passing matching K140 mock wrapper gate required')
    return gate


def rules():
    return {'protocol': PROTOCOL, 'jobs': jobs(), 'method_call_limit': 2,
        'per_method_budget_s': SECONDS, 'scene_slice_s': SCENE_SECONDS,
        'second_pass_scene_cap': 'min(60, remaining_budget/remaining_scenes)',
        'CutMaxIterations': CUT, 'cumulative_precedence': False,
        'shared_deployment': SHARED, 'builder_options': BUILD_OPTIONS,
        'K139_sources_covered': 155, 'K140_wrappers_checked_separately': list(WRAPPERS),
        'retry_allowed': False, 'extend_budget_allowed': False,
        'technical_fault_stops_remaining_jobs': True,
        'native_MaxTime_semantics': 'cooperative limit; record actual duration and stop delay, no hard 60 s promise',
        'initialisation': 'independent billed fresh input and at-most-three-template seed; no historical candidates/cache/oracle',
        'changed_factor': 'within one fresh invocation, N1 then A-chain/local-pre OPP/start with original seed units and last complete first-pass closed choices',
        'problem': 'base__R1 original full AB/AC three-Stage chains',
        'window_ms': 400, 'start_grid_ms': 5, 'entry_temperature_degC': 50,
        'maximum_temperature_degC': 80, 'idle_policy': 'auto_low_immediate_v1',
        'primary_success': 'new complete SAFE energy upper strictly below old complete SAFE energy lower',
        'scope': 'one same-task quality diagnostic; no statistical or global optimality claim',
        'wrapper_clock_semantics': 'method return including cleanup; then validation and primary serialization; own clock receipt write excluded',
        'authorization': 'K140 user continues the declared next step: frozen old N1 and linked version once each at 300 s, same original physical and safety conditions'}


def linked_opened(instance):
    """Declared A-chain/local-pre block, derived from fresh Stage identities only."""
    opened = {}
    for scene in instance['scenarios']:
        stages = scene['stage_instances']
        chosen = [stage['id'] for stage in stages
                  if stage['shared_stage_id'] in ('A.pre', 'A.main', 'A.post')
                  or stage['shared_stage_id'] in ('B.pre', 'C.pre')]
        if (len(stages) != 6 or len(chosen) != 4
                or len(set(chosen)) != 4):
            raise ValueError('Original six-Stage scene with A-chain/local-pre required')
        opened[scene['id']] = sorted(chosen)
    return opened


def prepare(out, checks, method_checks):
    from scene_adapter import canonical_hash
    from run_neighborhood_diagnostic import fresh_input, opened_stages
    out = local(out)
    if GLOBAL_CLAIM.exists():
        raise FileExistsError('K140 pair already claimed; no alternate-output preparation')
    current = sources()
    method_gate(method_checks, current)
    if sha(method_checks) != sha(METHOD_CHECKS):
        raise ValueError('Only the frozen K139 linked final02 gate is admitted')
    wrapper_gate(checks, current)
    historical = historical_manifest()
    check_history(historical)
    raw, config, instance = fresh_input()
    out.mkdir(parents=True, exist_ok=False)
    (out/'claims').mkdir()
    names = ('input_raw.json', 'input_config.json', 'input_instance.json')
    for name, value in zip(names, (raw, config, instance)):
        save(out/name, value)
    for name, digest in current.items():
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        if sha(target) != digest:
            raise ValueError('Source changed while freezing')
    shutil.copyfile(checks, out/'wrapper_checks.json')
    shutil.copyfile(method_checks, out/'method_checks.json')
    declaration = {**rules(), 'source_sha256': current,
        'historical_artifact_sha256': historical,
        'old_opened_by_scene': opened_stages(instance),
        'new_opened_by_scene': linked_opened(instance),
        'linked_opened_by_scene': linked_opened(instance),
        'input_sha256': canonical_hash(instance), 'config_sha256': canonical_hash(config),
        'raw_config_sha256': canonical_hash(raw),
        'input_file_sha256': {name: sha(out/name) for name in names},
        'wrapper_checks_sha256': sha(out/'wrapper_checks.json'),
        'method_checks_sha256': sha(out/'method_checks.json'), 'declared_at_utc': now()}
    save(out/'declaration.json', declaration)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'state': 'DECLARED', 'consumed': 0,
        'method_budget_s_reserved': 0, 'calls': [], 'declared_at_utc': now()})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    admission(out)
    print(json.dumps({'prepared': True, 'calls': 2, 'per_method_s': SECONDS, 'source_files': len(current)}), flush=True)


def admission(out):
    from scene_adapter import canonical_hash
    from run_neighborhood_diagnostic import opened_stages
    d, current = read(out/'declaration.json'), sources()
    if (any(d.get(k) != v for k, v in rules().items()) or d.get('source_sha256') != current
            or sha(out/'wrapper_checks.json') != d.get('wrapper_checks_sha256')
            or sha(out/'method_checks.json') != d.get('method_checks_sha256')
            or sha(out/'method_checks.json') != sha(METHOD_CHECKS)
            or d.get('historical_artifact_sha256') != historical_manifest()):
        raise ValueError('Frozen rule, source, history manifest or gate changed')
    method_gate(out/'method_checks.json', current)
    wrapper_gate(out/'wrapper_checks.json', current)
    check_history(d['historical_artifact_sha256'])
    for name, digest in current.items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Frozen source changed: '+name)
    for name, digest in d['input_file_sha256'].items():
        if sha(out/name) != digest:
            raise ValueError('Frozen input file changed: '+name)
    for name, key in [('input_raw.json', 'raw_config_sha256'), ('input_config.json', 'config_sha256'),
                      ('input_instance.json', 'input_sha256')]:
        if canonical_hash(read(out/name)) != d[key]:
            raise ValueError('Frozen input identity changed')
    instance = read(out/'input_instance.json')
    if (d.get('old_opened_by_scene') != opened_stages(instance)
            or d.get('new_opened_by_scene') != linked_opened(instance)
            or d.get('linked_opened_by_scene') != d.get('new_opened_by_scene')):
        raise ValueError('Frozen first-pass/linked opening does not match original input')
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
            raise ValueError('Billed fresh input identity/opening changed')
        budget.check()
        return config, instance
    def update(result, record):
        print(json.dumps({'event': 'SAFE_AGGREGATE_UPDATE', 'method': job['id'],
            'phase_index': record.get('phase_index', 0 if record['trigger_source'] == 'initial_constructor' else 1),
            'elapsed_s': record['committed_at_s'], 'U_J': record['safe_upper_bound_J'],
            'source': record['trigger_source']}, ensure_ascii=False), flush=True)
    options = dict(shared_deployment=deepcopy(SHARED), seconds=SECONDS,
        scene_slice_s=SCENE_SECONDS, builder_options=deepcopy(BUILD_OPTIONS),
        session_factory=partial(MatlabSession, cut_max_iterations=CUT),
        opened_by_scene=deepcopy(declaration['old_opened_by_scene']), on_global_update=update)
    if job == jobs()[0]:
        from neighborhood_method import execute_n1_neighborhood
        return execute_n1_neighborhood(loader, out/job['id'], **options)
    if job == jobs()[1]:
        from linked_method import execute_linked_fixed_unit_opp_start
        return execute_linked_fixed_unit_opp_start(loader, out/job['id'], linked_opened_by_scene=deepcopy(declaration['new_opened_by_scene']), **options)
    raise ValueError('Unknown frozen method')


def same_domain(actual, expected):
    return (isinstance(actual, dict) and set(actual) == set(expected)
        and all(isinstance(actual[s], list) and len(actual[s]) == len(set(actual[s]))
                and set(actual[s]) == set(expected[s]) for s in expected))


def linked_anchor_issues(result, phases, declaration):
    """Read-only dual-anchor audit, using completed receipts, never re-evaluation."""
    from scene_adapter import canonical_hash
    from neighborhood import _seed_options
    issues = []
    def fail(reason):
        issues.append({'scope': 'linked_anchor', 'reason': reason})
    contract = result.get('linked_record_contract') or {}
    if not same_domain(contract.get('linked_opened_by_scene'), declaration['new_opened_by_scene']):
        fail('DECLARED_LINKED_MASK_MISMATCH')
    second = next((p for p in phases if p.get('phase_index') == 2), None)
    if second is None:
        # A cutoff may happen before the second phase, or even before its
        # condition completes; a frozen anchor can therefore exist alone.
        return issues
    c = second.get('condition') or {}
    if not c:
        fail('MISSING_SECOND_PASS_CONDITION')
        return issues
    updates = [u for u in result.get('global_updates', []) if u.get('phase_index') in (0, 1)]
    if not updates:
        fail('NO_COMPLETE_FIRST_PASS_ANCHOR')
        return issues
    last = updates[-1]
    warm, receipt = c.get('warm_candidate'), c.get('warm_receipt') or {}
    try:
        candidate_hash = canonical_hash(warm)
        options = _seed_options(warm)
        identity = receipt.get('identity') or {}
        seed_identity = (c.get('seed_receipt') or {}).get('identity') or {}
        if (c.get('warm_candidate_sha256') != candidate_hash
                or c.get('warm_receipt_sha256') != receipt.get('receipt_sha256')
                or receipt.get('safe_candidate') != warm or receipt.get('state') != 'SAFE'
                or receipt.get('safe_upper_bound_J') != last.get('safe_upper_bound_J')
                or receipt.get('weighted_energy_J') != last.get('weighted_energy_J')
                or receipt.get('completed_at_elapsed_s') != last.get('committed_at_s')
                or receipt not in result.get('aggregation_attempts', [])
                or c.get('warm_options_by_scene') != options
                or identity.get('full_input_sha256') != declaration['input_sha256']
                or identity.get('candidate_sha256') != candidate_hash
                or identity.get('budget') != c.get('budget_identity')
                or any(identity.get(key) != seed_identity.get(key) for key in
                       ('source_sha256', 'accuracy_sha256', 'control_policy'))
                or any(contract.get(k) != value for k, value in (
                    ('closed_anchor_candidate_sha256', candidate_hash),
                    ('closed_anchor_phase_index', last.get('phase_index')),
                    ('closed_anchor_committed_at_s', last.get('committed_at_s'))))):
            fail('WARM_ANCHOR_IS_NOT_LAST_COMPLETE_FIRST_PASS_GENERATION')
        seeds = c.get('seed_options_by_scene') or {}
        if (set(seeds) != set(options) or any(set(seeds[s]) != set(options[s]) for s in seeds)
                or any(seeds[s][t]['unit'] != options[s][t]['unit'] for s in seeds for t in seeds[s])):
            fail('WARM_ANCHOR_CHANGED_ORIGINAL_SEED_UNIT')
        # Only the committed complete snapshot is a final candidate; latest
        # local scene metadata may legitimately be ahead of that generation.
        snapshot = result.get('committed_safe_snapshot') or {}
        if snapshot.get('phase_index') == 2:
            final = _seed_options(snapshot.get('safe_candidate'))
            if (set(final) != set(seeds) or any(set(final[s]) != set(seeds[s]) for s in seeds)
                    or any(final[s][t]['unit'] != seeds[s][t]['unit']
                        or (t not in declaration['new_opened_by_scene'][s]
                            and final[s][t] != options[s][t]) for s in seeds for t in seeds[s])):
                fail('COMMITTED_SECOND_PASS_CANDIDATE_OUTSIDE_DUAL_ANCHOR_DOMAIN')
    except (KeyError, TypeError, ValueError):
        fail('MALFORMED_DUAL_ANCHOR_RECEIPT')
    return issues


def transport_issues(job, result, declaration):
    """Audit already formed receipts; never evaluate a candidate or heat."""
    if not isinstance(result, dict):
        return []
    issues = []
    def fail(scope, reason):
        issues.append({'scope': scope, 'reason': reason})
    old = declaration['old_opened_by_scene']
    condition = result.get('condition')
    if condition is not None and (condition.get('protocol') != N1_PROTOCOL
            or not same_domain(condition.get('opened_by_scene'), old)
            or condition.get('shared_deployment') != SHARED
            or condition.get('source_input_sha256') != declaration['input_sha256']):
        fail('condition', 'FIRST_PASS_N1_DOMAIN_MISMATCH')
    staged = job == jobs()[1]
    phases = result.get('phases', []) if staged else []
    if staged:
        issues.extend(inherited.transport_issues({'method': 'augmented_fixed_unit_opp_start'}, result))
        if (not isinstance(phases, list) or len(phases) > 2
                or [p.get('phase_index') for p in phases] != list(range(1, len(phases)+1))):
            fail('phases', 'INVALID_PHASE_ORDER')
            phases = []
        budget_stop = result.get('budget_exhausted') is True and result.get('reason') == 'wall_time_limit'
        # K139 also latches non-reusability at an ordinary root deadline.
        # Numerical/context and scene/interface failures remain independently audited.
        if result.get('search_failure_latched') is not False and not budget_stop:
            fail('staged', 'SEARCH_FAILURE_LATCHED')
        for p in phases:
            index = p['phase_index']
            expected = old if index == 1 else declaration['new_opened_by_scene']
            protocol = N1_PROTOCOL if index == 1 else LINKED_PROTOCOL
            c = p.get('condition') or {}
            if (p.get('protocol') != protocol or c.get('protocol') != protocol
                    or not same_domain(p.get('opened_by_scene'), expected)
                    or not same_domain(c.get('opened_by_scene'), expected)
                    or (condition is not None and any(c.get(k) != condition.get(k) for k in
                        ('seed_candidate_sha256', 'seed_options_by_scene', 'shared_deployment', 'source_input_sha256',
                         'seed_receipt', 'seed_receipt_sha256', 'budget_identity')))):
                fail('phase:'+str(index), 'PHASE_MEMBER_DOMAIN_MISMATCH')
            if p.get('failure_latched') is not False and not budget_stop:
                fail('phase:'+str(index), 'PHASE_FAILURE_LATCHED')
            from run_neighborhood_diagnostic import technical_issues
            issues.extend(dict(item, scope='phase:'+str(index)+':'+item['scope'])
                for item in technical_issues({'scenes': p.get('scenes', {})}))
        for i, request in enumerate((result.get('augmented_transport') or {}).get('requests', []), 1):
            numbers = request.get('expected_callback_numbers')
            if (not isinstance(numbers, list) or any(type(n) is not int or n < 1 for n in numbers)
                    or len(numbers) != len(set(numbers))):
                fail('request:'+str(i), 'INVALID_CALLBACK_PUBLICATION_IDENTITY')
        issues.extend(linked_anchor_issues(result, phases, declaration))
    updates = result.get('global_updates') or []
    previous_time, previous_u = -1., None
    for update in updates:
        stamp, upper = update.get('committed_at_s'), update.get('safe_upper_bound_J')
        try:
            numeric = Fraction(str(upper))
            valid = (type(stamp) in (int, float) and math.isfinite(stamp)
                and previous_time <= stamp < SECONDS and (previous_u is None or numeric < previous_u))
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            fail('global_updates', 'INVALID_COMPLETE_UPDATE_CLOCK_OR_UPPER_BOUND')
        if staged and update.get('phase_index') not in [0]+[p['phase_index'] for p in phases]:
            fail('global_updates', 'UPDATE_PHASE_NOT_STARTED')
        if valid:
            previous_time, previous_u = stamp, numeric
    u = result.get('safe_upper_bound_J')
    if u is not None:
        aggregate = result.get('aggregation') or {}
        if (result.get('state') != 'SAFE' or aggregate.get('state') != 'SAFE' or not updates
                or any(result.get(k) != aggregate.get(k) for k in ('safe_candidate', 'safe_upper_bound_J', 'weighted_energy_J'))
                or updates[-1].get('safe_upper_bound_J') != u
                or updates[-1].get('weighted_energy_J') != result.get('weighted_energy_J')):
            fail('global_ledger', 'COMPLETE_SAFE_LEDGER_MISMATCH')
        if staged:
            snapshot = result.get('committed_safe_snapshot') or {}
            if (snapshot.get('aggregation') != aggregate
                    or snapshot.get('scene_receipts') != aggregate.get('scenes')
                    or any(snapshot.get(k) != result.get(k) for k in ('safe_candidate', 'safe_upper_bound_J', 'weighted_energy_J'))
                    or snapshot.get('phase_index') != updates[-1].get('phase_index')
                    or snapshot.get('committed_at_s') != updates[-1].get('committed_at_s')
                    or any(set(snapshot.get(k, {})) != set(old) for k in ('scene_receipts', 'scene_candidates', 'scene_sources'))):
                fail('committed_safe_snapshot', 'COMPLETE_COMMITTED_GENERATION_MISMATCH')
            else:
                candidate_scenes = (snapshot.get('safe_candidate') or {}).get('scenes', {})
                if (set(candidate_scenes) != set(old) or any(
                        (snapshot['scene_candidates'][s].get('scenes') or {}).get(s) != candidate_scenes.get(s)
                        for s in old)):
                    fail('committed_safe_snapshot', 'SCENE_CANDIDATES_DO_NOT_MATCH_COMPLETE_GENERATION')
    elif result.get('state') == 'SAFE' or result.get('committed_safe_snapshot') is not None:
        fail('global_ledger', 'SAFE_WITHOUT_COMPLETE_UPPER_BOUND')
    return issues


def phase_quality(result):
    """Global U only; local objectives never become whole-task quality."""
    rows = []
    phases = (result or {}).get('phases', [])
    if 'phases' not in (result or {}):
        # The unchanged old method has one pass and no phase container.
        phases = [{'phase_index': 1, 'name': 'N1', 'started_at_s': 0.,
            'completed_at_s': ((result or {}).get('timing') or {}).get('method_elapsed_s'),
            'scenes': (result or {}).get('scenes', {})}]
    if not isinstance(phases, list):
        return rows
    for p in phases:
        rows.append({k: deepcopy(p.get(k)) for k in ('phase_index', 'name', 'started_at_s',
            'completed_at_s', 'search_sequence_complete', 'failure_latched')})
        rows[-1]['global_updates'] = [deepcopy(u) for u in result.get('global_updates', [])
                                    if u.get('phase_index', 1) == p['phase_index']]
        rows[-1]['scene_timing_and_solver_records'] = deepcopy(p.get('scenes', {}))
    return rows


def run(out):
    from run_neighborhood_diagnostic import technical_issues
    from matlab_bridge import cleanup_is_complete
    out = local(out)
    ledger = read(out/'ledger.json')
    # Refuse before reading clocks or writing anything, including completed timing.
    if (ledger.get('state') != 'DECLARED' or ledger.get('consumed') != 0
            or ledger.get('calls') != [] or GLOBAL_CLAIM.exists()
            or any((out/'claims'/(j['id']+'.json')).exists() for j in jobs())):
        raise FileExistsError('K140 already consumed/claimed; no restart, retry or alternate-out run')
    d = admission(out)
    pair_started = time.monotonic()
    with GLOBAL_CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'declaration_sha256': sha(out/'declaration.json'), 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
    ok = True
    for job in jobs():
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'claimed_at_utc': now(), 'no_retry': True}, stream, indent=2)
        row = {**job, 'state': 'RUNNING', 'started_at_utc': now(), 'seconds': SECONDS}
        ledger['calls'].append(row)
        ledger['consumed'] += 1
        ledger['method_budget_s_reserved'] += SECONDS
        ledger['state'] = 'RUNNING'
        save(out/'ledger.json', ledger)
        print('START '+job['id']+' fresh 300 s; Cut10/CDFoff; no retry', flush=True)
        started = time.monotonic()
        result = error = None
        try:
            result = execute(job, out, d)
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
            issues = technical_issues(result)+transport_issues(job, result, d)
        except Exception:
            issues = [{'scope': 'wrapper_validation', 'reason': 'MALFORMED_METHOD_RECEIPT'}]
            error = (error or '')+'\n'+traceback.format_exc()
        cleanup = None
        try:
            closed = out/job['id']/'matlab/closed.json'
            cleanup = read(closed) if closed.is_file() else None
        except Exception:
            error = (error or '')+'\n'+traceback.format_exc()
        if isinstance(result, dict) and result.get('matlab_worker_ready') and not cleanup:
            issues.append({'scope': 'cleanup', 'reason': 'MISSING_CLOSED_RECEIPT'})
        if cleanup and not cleanup_is_complete(cleanup):
            issues.append({'scope': 'cleanup', 'reason': 'WORKER_CLEANUP_ANOMALY'})
        failed = bool(error or issues or not unchanged)
        evidence = result if isinstance(result, dict) else {}
        row.update(state='TECHNICAL_BLOCK' if failed else 'COMPLETED', error=error,
            technical_issues=issues, source_unchanged=unchanged, cleanup=cleanup,
            method_return_inclusive_wall_s=returned, completed_at_utc=now(),
            method_state=evidence.get('state'), reason=evidence.get('reason'),
            safe_upper_bound_J=evidence.get('safe_upper_bound_J'),
            weighted_energy_J=evidence.get('weighted_energy_J'),
            initial_safe_upper_bound_J=evidence.get('initial_global_safe_upper_bound_J'),
            global_updates=deepcopy(evidence.get('global_updates', [])),
            phase_quality=phase_quality(evidence), method_timing=evidence.get('timing'),
            safe_U_preserved_even_if_later_technical_issue=True)
        ledger['state'] = 'BLOCKED' if failed else 'RUNNING'
        save(out/'claims'/(job['id']+'_result.json'), row)
        save(out/'ledger.json', ledger)
        timing = timing_components(time.monotonic()-started, result)
        save(out/'claims'/(job['id']+'_wrapper_timing.json'), timing)
        print(json.dumps({k: row.get(k) for k in ('id', 'state', 'reason', 'safe_upper_bound_J')})+' '+json.dumps(timing), flush=True)
        if failed:
            ok = False
            break
    if ok:
        ledger['state'] = 'COMPLETED'
        save(out/'ledger.json', ledger)
    save(out/'wrapper_timing.json', {'wrapper_run_through_primary_archives_wall_s': time.monotonic()-pair_started,
        'clock_receipt_own_write_included': False,
        'scope': 'both method calls/cleanup, validation and primary tail serialization; no new post-cutoff evidence'})
    return ok


def precheck(out):
    from contextlib import ExitStack, redirect_stdout, redirect_stderr
    import subprocess
    import scipy.optimize
    import matlab_bridge
    import milp
    import scene_adapter
    out = local(out)
    out.mkdir(parents=True, exist_ok=False)
    before, historical = sources(), historical_manifest()
    started, captured, error, result = time.monotonic(), io.StringIO(), None, None
    environment = {'python': sys.version, 'platform': platform.platform()}
    blocked = {}
    def forbidden(name):
        blocked[name] = 0
        def reject(*args, **kwargs):
            blocked[name] += 1
            raise AssertionError('Model/heat/optimizer/process forbidden in K140 wrapper precheck: '+name)
        return reject
    try:
        method_gate(METHOD_CHECKS, before)
        check_history(historical)
        with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
            for obj, name in ((subprocess, 'Popen'), (scipy.optimize, 'milp'),
                (scipy.optimize, 'linprog'), (matlab_bridge.MatlabSession, '__init__'),
                (milp, 'build_model'), (milp, 'evaluate_model_candidate'),
                (scene_adapter, 'evaluate_partial_scene'), (scene_adapter, 'evaluate_piecewise')):
                stack.enter_context(patch.object(obj, name, side_effect=forbidden(obj.__name__+'.'+name)))
            suite = unittest.defaultTestLoader.loadTestsFromName('test_linked_pair')
            result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
    except BaseException:
        error = traceback.format_exc()
        captured.write(error)
    after = sources()
    history_ok = True
    try:
        check_history(historical)
    except Exception:
        history_ok = False
        error = (error or '')+'\n'+traceback.format_exc()
    report = {'protocol': PRECHECK_PROTOCOL,
        'passed': bool(result and result.wasSuccessful() and before == after and history_ok and not error and not any(blocked.values())),
        'tests_run': result.testsRun if result else 0, 'errors': len(result.errors) if result else 1,
        'failures': len(result.failures) if result else 0, 'source_sha256': after,
        'source_unchanged': before == after, 'historical_artifacts_unchanged': history_ok,
        'source_scope': 'K139 155 sources unchanged; only two new K140 wrappers behavior tested',
        'native_calls': 0, 'research_calls': 0, 'physical_models': 0, 'thermal_evaluations': 0,
        'blocked_calls': blocked, 'elapsed_s': time.monotonic()-started, 'error': error,
        'completed_at_utc': now(), 'failed_runs_retained': True}
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
