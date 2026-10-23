"""Bounded K127 night protocol: one heat pair, then four exploratory methods.

One immutable declaration, irreversible per-call claims and a shared night
deadline prevent retries or budget replenishment. No invocation runs on import.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction as F
from functools import partial
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
START_UTC = datetime.fromisoformat('2026-10-19T14:50:19+00:00')
DEADLINE_UTC = min(START_UTC+timedelta(hours=6),
                  datetime.fromisoformat('2026-10-19T23:00:00+00:00'))
SECONDS = 300
PROTOCOL = 'K127-bounded-night-autoL-evidence-20261019-v1'
BASE = HERE/'results/neighborhood_diagnostic01/call_n1/invocation/result.json'
K125_GATE = HERE/'results/neighborhood_method_precheck02/checks.json'
SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p = Path(p)
    pending = p.with_suffix(p.suffix+'.pending')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        stream.write('\n')
    pending.replace(p)


def utc_now():
    return datetime.now(timezone.utc)


def remaining_night():
    return (DEADLINE_UTC-utc_now()).total_seconds()


def workspace(p):
    p = Path(p).resolve()
    p.relative_to(REPO)
    return p


def make_input(condition, budget=None):
    from inputs import load_config, build_instance
    from control_policy import with_auto_low_idle
    raw = load_config()
    if condition == 'heat52':
        raw['conditions'].append({'id': 'night_limit52', 'group': 'K127_declared_thermal_pressure',
                                 'overrides': {'maximum_temperature_degC': '52'}})
        problem = 'night_limit52__R1'
    elif condition == 'base':
        problem = 'base__R1'
    else:
        raise ValueError('Undeclared condition')
    instance = build_instance(raw, problem, budget=budget)
    config, instance = with_auto_low_idle(raw), with_auto_low_idle(instance)
    if F(instance['window_ms']) != 400 or F(instance['start_grid_ms']) != 5:
        raise ValueError('Original window/start domain changed')
    return config, instance


def jobs():
    return [
        {'id': 'heat52_conditional', 'phase': 'heat', 'condition': 'heat52', 'method': 'milp', 'feedback_kind': 'conditional'},
        {'id': 'heat52_assignment', 'phase': 'heat', 'condition': 'heat52', 'method': 'milp', 'feedback_kind': 'assignment'},
        {'id': 'base_milp', 'phase': 'comparison', 'condition': 'base', 'method': 'milp', 'feedback_kind': 'conditional'},
        {'id': 'base_n1', 'phase': 'comparison', 'condition': 'base', 'method': 'n1'},
        {'id': 'base_heft', 'phase': 'comparison', 'condition': 'base', 'method': 'heft'},
        {'id': 'base_sa101', 'phase': 'comparison', 'condition': 'base', 'method': 'sa', 'seed': 101},
    ]


def heat_basis():
    """Algebra on archived continuous enclosures, not new propagation."""
    old = read(BASE)
    seed = next(a['aggregation'] for a in old['seed_attempts'] if a['state'] == 'SAFE')
    final = old['aggregation']
    by_scene = {}
    for sid in seed['scenes']:
        a = seed['scenes'][sid]['result']
        b = final['scenes'][sid]['result']
        assert a['complete'] and b['complete']
        assert F(a['covered_until_s']) == F(b['covered_until_s']) == F('2/5')
        assert any(F(v[0]) > 52 for v in a['peaks_degC'].values())
        assert all(F(v[1]) < 52 for v in b['peaks_degC'].values())
        by_scene[sid] = {'seed_peaks_degC': a['peaks_degC'],
            'final_peaks_degC': b['peaks_degC'], 'seed_peak_witnesses': a.get('peak_witnesses'),
            'complete_window_s': '2/5', 'seed_violates_52': True, 'final_safe_below_52': True}
    return {'source_path': BASE.relative_to(REPO).as_posix(), 'source_sha256': sha(BASE),
        'chosen_limit_degC': '52', 'entry_degC': '50', 'power_valid_range_degC': ['20', '100'],
        'selection': 'single integer 52 in saved final-safe/seed-violating peak gap; frozen before new calls',
        'only_temperature_limit_changes': True, 'new_trajectory_evaluations': 0,
        'injected_into_method_as_seed_or_cache': False,
        'scope': 'trajectory-assisted abstract pressure case, not measured hardware or feedback-trigger guarantee',
        'scenes': by_scene}


def source_paths():
    paths = list(HERE.glob('*.py'))+[HERE/'config_v01.json', HERE/'solve_model.m',
                                   HERE.parent/'v1_evaluator/interval.py']
    return sorted(p.relative_to(REPO).as_posix() for p in paths)


def precheck_matches(checks, files):
    return (set(checks['source_sha256']) <= set(files)
        and all(sha(REPO/p) == digest for p, digest in checks['source_sha256'].items()))


def prepare(out, checks):
    from scene_adapter import canonical_hash
    out = workspace(out)
    if remaining_night() < 360:
        raise TimeoutError('Night cutoff too close to start work')
    check = read(checks)
    if (check.get('passed') is not True or not check['capabilities']['formal']
            or any(v.get('errors', 0) or v.get('failures', 0) for v in check['modules'].values())):
        raise ValueError('Whole-model auto-L checks not passed')
    baseline = read(K125_GATE)
    if not baseline['passed'] or any(sha(REPO/p) != h for p,h in baseline['source_sha256'].items()):
        raise ValueError('Unchanged K125 N1 basis does not match')
    files = source_paths()
    sources = {p: sha(REPO/p) for p in files}
    if not precheck_matches(check, files):
        raise ValueError('New targeted precheck is stale')
    basis = heat_basis()
    out.mkdir(parents=True, exist_ok=False)
    (out/'claims').mkdir()
    (out/'inputs').mkdir()
    for name, digest in sources.items():
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        assert sha(target) == digest
    save(out/'heat_basis.json', basis)
    identities = {}
    for condition in ('heat52', 'base'):
        config, instance = make_input(condition)
        save(out/'inputs'/(condition+'_config.json'), config)
        save(out/'inputs'/(condition+'_instance.json'), instance)
        identities[condition] = {'config_sha256': canonical_hash(config), 'instance_sha256': canonical_hash(instance)}
    shutil.copyfile(checks, out/'targeted_checks.json')
    from run_neighborhood_diagnostic import opened_stages
    opened = opened_stages(read(out/'inputs/base_instance.json'))
    declaration = {'protocol': PROTOCOL, 'started_at_utc': START_UTC.isoformat(),
        'deadline_utc': DEADLINE_UTC.isoformat(), 'wall_limit_hours': 6,
        'user_latest_stop_beijing': '2026-10-20T07:00:00+08:00',
        'maximum_research_method_calls': 8, 'planned_method_calls': len(jobs()),
        'planned_new_thermal_conditions': 1, 'maximum_thermal_conditions': 2,
        'per_method_budget_s': 300, 'heat_call_limit': 4, 'comparison_call_limit': 4,
        'jobs': jobs(), 'source_sha256': sources, 'input_identities': identities,
        'targeted_checks_sha256': sha(checks), 'capabilities': check['capabilities'],
        'K125_basis_sha256': sha(K125_GATE), 'heat_basis_sha256': sha(out/'heat_basis.json'),
        'model_flags': {'fix_late_options': True, 'aggregate_opp_locks': True,
            'relax_auxiliary_integrality': True, 'strengthen_energy_lower_bounds': True,
            'prefilter_deadlines': True, 'cumulative_precedence': False},
        'CutMaxIterations': 10, 'n1_scene_slice_s': 60, 'n1_shared_deployment': SHARED,
        'n1_opened': ['B.main', 'B.post', 'C.main', 'C.post'],
        'n1_opened_by_scene': opened,
        'feedback_difference': 'conditional point rows with existing repeated-assignment fallback vs complete violated-scene assignment deletion only',
        'feedback_primary_domain': 'whole original legal mode/start domain, no fixed shared A',
        'comparison_scope': 'same original problem/output/budget/safety; N1 search subset and other heuristic coverage explicitly differ',
        'SA_scope': 'one fixed seed 101, exploratory only', 'retry_allowed': False,
        'extend_budget_or_tune_conditions_allowed': False, 'old_hold_results_reused': False,
        'archived_K126_candidates_supplied_to_methods': False,
        'authorization': 'user bounded overnight instruction after K126, 2026-10-19',
        'declared_at_utc': utc_now().isoformat()}
    save(out/'declaration.json', declaration)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'phase': 'DECLARED', 'consumed': 0,
        'method_limit_s_consumed': 0, 'calls': [], 'started_at_utc': START_UTC.isoformat(),
        'deadline_utc': DEADLINE_UTC.isoformat(), 'declared_jobs': [j['id'] for j in jobs()]})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    print(json.dumps({'prepared': True, 'source_files': len(sources), 'jobs': len(jobs()),
        'deadline_utc': DEADLINE_UTC.isoformat(), 'remaining_night_s': remaining_night()}), flush=True)


def admitted(out):
    from scene_adapter import canonical_hash
    declaration = read(out/'declaration.json')
    if declaration['protocol'] != PROTOCOL or declaration['jobs'] != jobs():
        raise ValueError('Protocol/job mismatch')
    if declaration['deadline_utc'] != DEADLINE_UTC.isoformat():
        raise ValueError('Night deadline cannot be changed')
    for p, h in declaration['source_sha256'].items():
        if sha(REPO/p) != h or sha(out/'source_snapshot'/p) != h:
            raise ValueError('Frozen source changed: '+p)
    if sha(out/'targeted_checks.json') != declaration['targeted_checks_sha256']:
        raise ValueError('Frozen necessary checks changed')
    if sha(out/'heat_basis.json') != declaration['heat_basis_sha256']:
        raise ValueError('Thermal selection basis changed')
    for condition, identity in declaration['input_identities'].items():
        if (canonical_hash(read(out/'inputs'/(condition+'_instance.json'))) != identity['instance_sha256']
                or canonical_hash(read(out/'inputs'/(condition+'_config.json'))) != identity['config_sha256']):
            raise ValueError('Frozen input snapshot changed: '+condition)
    return declaration


def execute_job(job, out, declaration):
    from scene_adapter import canonical_hash
    from partial_bounds import independent_lower_bound
    from matlab_bridge import MatlabSession
    from milp import build_model
    lower = {}
    def loader(budget):
        config, instance = make_input(job['condition'], budget)
        identity = declaration['input_identities'][job['condition']]
        if (canonical_hash(config) != identity['config_sha256']
                or canonical_hash(instance) != identity['instance_sha256']):
            raise ValueError('Fresh billed input differs from frozen condition')
        # N1/heuristic wrappers compute their own existing bounds. The whole
        # method has no L0 field, so add only this independent billed receipt.
        if job['method'] == 'milp':
            with budget.phase('night_independent_lower_bound'):
                lower['L0'] = independent_lower_bound(instance, None, budget)
        budget.check()
        return config, instance
    folder = out/job['id']
    session_factory = partial(MatlabSession, cut_max_iterations=10)
    if job['method'] == 'milp':
        from formal_milp import execute_formal_milp
        # execute_warm supplies the original four FLAGS; prefilter and CDF
        # remain explicit here, identical across the two feedback variants.
        result = execute_formal_milp(loader, folder, seconds=SECONDS,
            feedback_kind=job['feedback_kind'],
            model_builder=partial(build_model, prefilter_deadlines=True, cumulative_precedence=False),
            session_factory=session_factory)
    elif job['method'] == 'n1':
        from neighborhood_method import execute_n1_neighborhood
        # Only predeclared stage identities; fresh input remains billed.
        opened = declaration['n1_opened_by_scene']
        result = execute_n1_neighborhood(loader, folder, shared_deployment=dict(SHARED),
            opened_by_scene=opened, seconds=SECONDS, scene_slice_s=60,
            builder_options={'cumulative_precedence': False}, session_factory=session_factory)
    else:
        from heuristic_runner import execute_heuristic
        result = execute_heuristic(loader, folder, method=job['method'],
            seconds=SECONDS, seed=job.get('seed'), allow_auto_low=True)
    if lower:
        save(folder/'independent_bounds.json', lower)
    return result


def technical_issues(result):
    from run_neighborhood_diagnostic import technical_issues as inspect_n1
    issues = inspect_n1(result)
    for row in result.get('rounds', []):
        if row.get('status') in ('ERROR', 'WORKER_EXITED') or row.get('error_identifier'):
            issues.append({'scope': 'whole_native', 'reason': row.get('status'),
                           'error': row.get('error_message')})
        if (row.get('numerical_consistency') or {}).get('state') == 'NUMERICAL_ADMISSION_STATUS_CONFLICT':
            issues.append({'scope': 'whole_native', 'reason': 'NUMERICAL_ADMISSION_STATUS_CONFLICT'})
    return issues


def run_phase(out, phase):
    out = workspace(out)
    declaration = admitted(out)
    ledger = read(out/'ledger.json')
    if phase == 'comparison' and ledger.get('heat_phase_state') != 'COMPLETED':
        raise ValueError('Heat phase not complete or technically blocked')
    phase_jobs = [j for j in jobs() if j['phase'] == phase]
    for job in phase_jobs:
        previous = next((c for c in ledger['calls'] if c['id'] == job['id']), None)
        if previous is not None:
            if previous['state'] in ('COMPLETED', 'SKIPPED_NOT_ADAPTED'):
                continue  # resume only unconsumed later jobs; never rerun
            raise FileExistsError('Unsettled/failed consumed call blocks retries: '+job['id'])
        if remaining_night() < 360 or ledger['consumed'] >= 8:
            ledger[phase+'_phase_state'] = 'STOPPED_GLOBAL_LIMIT'
            save(out/'ledger.json', ledger)
            return False
        if job['method'] in ('heft', 'sa') and not declaration['capabilities'].get('auto_heuristics'):
            ledger['calls'].append({**job, 'state': 'SKIPPED_NOT_ADAPTED', 'consumed': False})
            save(out/'ledger.json', ledger)
            continue
        admitted(out)
        claim = out/'claims'/(job['id']+'.json')
        with claim.open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'state': 'CLAIMED_NO_RETRY',
                'claimed_at_utc': utc_now().isoformat()}, stream, indent=2)
        row = {**job, 'state': 'RUNNING', 'consumed': True, 'seconds': SECONDS,
            'started_at_utc': utc_now().isoformat()}
        ledger['calls'].append(row)
        ledger['consumed'] += 1
        ledger['method_limit_s_consumed'] += SECONDS
        ledger['phase'] = phase
        save(out/'ledger.json', ledger)
        print('START '+job['id']+' total=300s no retry', flush=True)
        start = time.monotonic()
        result = error = None
        try:
            result = execute_job(job, out, declaration)
        except BaseException:
            error = traceback.format_exc()
        row['wrapper_wall_s'] = time.monotonic()-start
        row['error'] = error
        unchanged = True
        try:
            admitted(out)
        except Exception as exc:
            unchanged = False
            row['source_error'] = repr(exc)
        issues = technical_issues(result) if isinstance(result, dict) else [{'reason': 'NO_RESULT'}]
        closed = out/job['id']/'matlab/closed.json'
        cleanup = None
        if closed.exists():
            try:
                cleanup = read(closed)
            except (ValueError, OSError) as exc:
                issues.append({'scope': 'cleanup', 'error': repr(exc)})
        elif isinstance(result, dict) and result.get('matlab_worker_ready'):
            issues.append({'scope': 'cleanup', 'reason': 'MISSING_CLEANUP_RECEIPT'})
        cleanup_bad = bool(cleanup and (cleanup.get('cleanup_pending_pid') is not None
            or cleanup.get('error') or cleanup.get('cleanup_error')
            or cleanup.get('returncode') not in (None, 0)))
        failed = bool(error or issues or not unchanged or cleanup_bad)
        row.update(state='TECHNICAL_BLOCK' if failed else 'COMPLETED', source_unchanged=unchanged,
            technical_issues=issues, cleanup=cleanup, completed_at_utc=utc_now().isoformat(),
            method_state=(result or {}).get('state'), method_reason=(result or {}).get('reason'),
            safe_upper_bound_J=(result or {}).get('safe_upper_bound_J'), timing=(result or {}).get('timing'))
        save(out/'claims'/(job['id']+'_result.json'), row)
        save(out/'ledger.json', ledger)
        print(json.dumps({k: row.get(k) for k in ('id', 'state', 'method_state', 'method_reason',
            'safe_upper_bound_J', 'wrapper_wall_s')}, ensure_ascii=False), flush=True)
        if failed:
            ledger[phase+'_phase_state'] = 'BLOCKED'
            save(out/'ledger.json', ledger)
            return False
    ledger[phase+'_phase_state'] = 'COMPLETED'
    save(out/'ledger.json', ledger)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--run-phase', choices=('heat', 'comparison'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    args = parser.parse_args()
    if args.prepare:
        if args.checks is None:
            parser.error('--prepare requires --checks')
        prepare(args.out, args.checks)
    else:
        raise SystemExit(0 if run_phase(args.out, args.run_phase) else 1)
