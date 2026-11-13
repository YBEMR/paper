"""K126: one fresh base__R1 N1 quality diagnostic, 300 s total; no retry.

--prepare only freezes the admitted K125 sources, original input and rules.
--run consumes one global claim and invokes the existing N1 method once.
No original-scale solver, model or thermal evaluation runs during preparation.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
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
PROTOCOL = 'K126-one-fresh-base-R1-N1-quality-diagnostic-v1'
PROBLEM = 'base__R1'
SECONDS = 300
SLICE_SECONDS = 60
CUT_MAX_ITERATIONS = 10
SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
CLAIM = HERE / 'results/neighborhood_diagnostic_claim01.json'
K125 = HERE / 'results/neighborhood_method_precheck02'
GATE_FILES = ('checks.json', 'physical_checks.json', 'source_sha256.json',
              'independent_review.md', 'unittest.txt')
READ_FIX = HERE / 'results/request_read_native01/verification.json'
ENTRY = 'research/chapter3_experiments/run_neighborhood_diagnostic.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str) + '\n', encoding='utf-8')


def workspace_path(path):
    path = Path(path).resolve()
    path.relative_to(REPO)
    return path


def gate_evidence():
    checks = read(K125 / 'checks.json')
    if (checks.get('protocol') != 'K125-n1-method-lifecycle-precheck-v1'
            or checks.get('passed') is not True or checks.get('source_unchanged') is not True
            or checks.get('tests_run') != 45 or checks.get('failures') != 0
            or checks.get('errors') != 0 or checks.get('error') is not None
            or len(checks.get('source_sha256', {})) != 53
            or checks.get('physical_lifecycle_completed') is not True
            or any(checks.get(key) != 0 for key in
                   ('optimizer_calls', 'native_calls', 'research_calls'))):
        raise ValueError('Completed K125 45/45, 53-source gate is missing or failed')
    if (read(K125 / 'source_sha256.json') != checks['source_sha256']
            or read(K125 / 'physical_checks.json').get('passed') is not True):
        raise ValueError('K125 source manifest or physical lifecycle evidence mismatch')
    if read(READ_FIX).get('passed') is not False:
        raise ValueError('Historical K117 failed record must remain failed')
    return {name: sha(K125 / name) for name in GATE_FILES}


def collect_sources():
    gate_evidence()
    baseline = read(K125 / 'checks.json')['source_sha256']
    changed = [name for name, digest in baseline.items()
               if sha(workspace_path(REPO / name)) != digest]
    if changed:
        raise ValueError('K125 admitted source changed: ' + str(changed))
    return {name: sha(workspace_path(REPO / name)) for name in sorted(set(baseline) | {ENTRY})}


def opened_stages(instance):
    """Bind explicit catalog IDs to the original scene/request instance IDs."""
    expected = {('A', 'B'): ('B.main', 'B.post'),
                ('A', 'C'): ('C.main', 'C.post')}
    opened = {}
    seen = set()
    for scene in instance['scenarios']:
        pair = tuple(scene['application_pair'])
        if pair not in expected or pair in seen:
            raise ValueError('Expected exactly the original AB and AC scenes')
        seen.add(pair)
        stages = scene['stage_instances']
        if (len(stages) != 6 or len(scene['requests']) != 2
                or any(request['copy_index'] != 1 for request in scene['requests'])):
            raise ValueError('N1 diagnostic requires the original full three-Stage R1 chains')
        selected = []
        for shared_id in expected[pair]:
            matching = [stage for stage in stages if stage['shared_stage_id'] == shared_id]
            if len(matching) != 1:
                raise ValueError('Missing/duplicate exact Stage identity: ' + shared_id)
            selected.append(matching[0]['id'])
        opened[scene['id']] = selected
    if seen != set(expected):
        raise ValueError('Original AB/AC scene coverage is incomplete')
    return opened


def fresh_input(budget=None):
    from control_policy import with_auto_low_idle
    from inputs import build_instance, load_config
    raw = load_config()
    instance = build_instance(raw, PROBLEM, budget=budget)
    config, instance = with_auto_low_idle(raw), with_auto_low_idle(instance)
    if (instance['id'] != PROBLEM or Fraction(instance['window_ms']) != 400
            or Fraction(instance['start_grid_ms']) != 5
            or any(any(Fraction(value) != 50 for value in scene['entry']['temperature_degC'])
                   or any(Fraction(value) != 80 for value in scene['maximum_temperature_degC'])
                   for scene in instance['scenarios'])):
        raise ValueError('Original base__R1 window/grid/temperature settings changed')
    return raw, config, instance


def frozen_rules():
    return {'protocol': PROTOCOL, 'problem_id': PROBLEM, 'research_calls': 1,
        'method': 'execute_n1_neighborhood', 'total_budget_s': SECONDS,
        'scene_slice_s': SLICE_SECONDS, 'shared_deployment': SHARED,
        'all_execution_units_fixed_to_this_calls_fresh_seed': True,
        'opened_catalog_stage_ids_by_application_pair': {
            'AB': ['B.main', 'B.post'], 'AC': ['C.main', 'C.post']},
        'closed_stages_keep_seed_OPP_and_exact_start': True,
        'opened_stages_keep_original_OPP_and_5ms_start_choices': True,
        'cumulative_precedence': False, 'CutMaxIterations': CUT_MAX_ITERATIONS,
        'CutGeneration': 'basic', 'window_ms': 400, 'start_grid_ms': 5,
        'initial_temperature_degC': 50, 'temperature_limit_degC': 80,
        'idle_policy': 'auto_low_immediate_v1',
        'physical_parameter_override': False, 'starts_override': None,
        'single_fresh_worker': True, 'old_candidates_or_heat_receipts_reused': False,
        'comparison_reference': 'this invocation fresh complete SAFE seed only',
        'formal_comparison': False, 'global_deployment_search': False,
        'retry_allowed': False, 'budget_extension_allowed': False,
        'K125_completed_gate_reused_without_rerun': True,
        'K117_original_failed_gate_and_shutdown_limit_retained': True,
        'billed': 'fresh input, L0/La, seed construction and complete original-input evaluation, '
                  'N1 condition, models/x0, startup, export, solver, callbacks, continuous '
                  'recheck, feedback, aggregate updates and live logs',
        'separately_reported': 'imports and declaration snapshots; cleanup; completed-evidence '
                               'serialization and read-only analysis',
        'authorization': 'user 开始吧 after K125 proposed one 300s N1 diagnosis with 60s scene slices'}


def prepare(out):
    from scene_adapter import canonical_hash
    out = workspace_path(out)
    sources, evidence = collect_sources(), gate_evidence()
    raw, config, instance = fresh_input()
    opened = opened_stages(instance)
    out.mkdir(parents=True, exist_ok=False)
    for name in sources:
        target = out / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, target)
    (out / 'precheck_evidence').mkdir()
    for name in GATE_FILES:
        shutil.copy2(K125 / name, out / 'precheck_evidence' / name)
    shutil.copy2(READ_FIX, out / 'precheck_evidence/K117_verification.json')
    snapshots = {'input_raw_config.json': raw, 'input_config.json': config,
                 'input_instance.json': instance}
    for name, value in snapshots.items():
        save(out / name, value)
    declaration = {**frozen_rules(), 'state': 'DECLARED_NOT_RUN',
        'source_sha256': sources, 'K125_evidence_sha256': evidence,
        'K117_read_fix_report_sha256': sha(READ_FIX),
        'input_snapshot_sha256': {name: sha(out / name) for name in snapshots},
        'original_config_sha256': canonical_hash(config),
        'original_instance_sha256': canonical_hash(instance),
        'opened_by_scene': opened, 'declared_at_utc': datetime.now(timezone.utc).isoformat()}
    if sources != collect_sources() or evidence != gate_evidence():
        raise ValueError('Source/evidence changed during preparation')
    save(out / 'declaration.json', declaration)
    save(out / 'environment.json', {'python': sys.version, 'platform': platform.platform()})
    print(json.dumps({'prepared': True, 'source_count': len(sources),
        'opened_by_scene': opened, 'research_calls': 0, 'out': str(out)}, ensure_ascii=False), flush=True)


def admission(out):
    from scene_adapter import canonical_hash
    declaration = read(out / 'declaration.json')
    sources = collect_sources()
    if (any(declaration.get(key) != value for key, value in frozen_rules().items())
            or declaration.get('source_sha256') != sources
            or declaration.get('K125_evidence_sha256') != gate_evidence()
            or declaration.get('K117_read_fix_report_sha256') != sha(READ_FIX)):
        raise ValueError('Frozen rule/source/evidence mismatch')
    for name, expected in sources.items():
        if sha(out / 'source_snapshot' / name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    for name, expected in declaration['K125_evidence_sha256'].items():
        if sha(out / 'precheck_evidence' / name) != expected:
            raise ValueError('Frozen K125 evidence changed: ' + name)
    if sha(out / 'precheck_evidence/K117_verification.json') != sha(READ_FIX):
        raise ValueError('Frozen K117 evidence changed')
    for name, expected in declaration['input_snapshot_sha256'].items():
        if sha(out / name) != expected:
            raise ValueError('Frozen input changed: ' + name)
    instance, config = read(out / 'input_instance.json'), read(out / 'input_config.json')
    if (canonical_hash(config) != declaration['original_config_sha256']
            or canonical_hash(instance) != declaration['original_instance_sha256']
            or opened_stages(instance) != declaration['opened_by_scene']):
        raise ValueError('Frozen input identity/opened Stage mismatch')
    if CLAIM.exists() or (out / 'call_n1').exists():
        raise FileExistsError('K126 diagnostic already consumed or call directory exists; no retry')
    return declaration, sources


def technical_issues(result):
    issues = []
    if not isinstance(result, dict):
        return [{'scope': 'method', 'reason': 'NO_METHOD_RESULT'}]
    records = [('method', result)]
    for sid, scene in result.get('scenes', {}).items():
        records.append((sid, scene))
        solved = scene.get('solver_result') or {}
        records.append((sid + ':solver', solved))
        records.extend((sid + ':round:' + str(i), item)
                       for i, item in enumerate(solved.get('rounds', []), 1))
    bad = {'INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
        'INVALID_INPUT_OR_INTERFACE', 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED',
        'NUMERICAL_CANDIDATE_ANOMALY', 'INITIALISATION_ERROR'}
    for scope, record in records:
        if (record.get('error') or record.get('cleanup_error') or record.get('reason') in bad
                or record.get('status') in ('ERROR', 'WORKER_EXITED')
                or record.get('technical_state') in ('FAILED', 'TECHNICAL_FAILURE')
                or (record.get('numerical_consistency') or {}).get('state')
                   == 'NUMERICAL_ADMISSION_STATUS_CONFLICT'):
            issues.append({'scope': scope, 'reason': record.get('reason'),
                'status': record.get('status'), 'technical_state': record.get('technical_state'),
                'error': record.get('error') or record.get('cleanup_error')})
    return issues


def run(out):
    from matlab_bridge import MatlabSession
    from neighborhood_method import execute_n1_neighborhood
    from scene_adapter import canonical_hash
    out = workspace_path(out)
    declaration, sources = admission(out)
    with CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'state': 'CLAIMED_NO_RETRY',
            'out': out.relative_to(REPO).as_posix(), 'total_budget_s': SECONDS,
            'declaration_sha256': sha(out / 'declaration.json'),
            'claimed_at_utc': datetime.now(timezone.utc).isoformat()}, stream, indent=2)
    call = out / 'call_n1'
    call.mkdir(exist_ok=False)
    record = {'protocol': PROTOCOL, 'state': 'RUNNING', 'research_calls_consumed': 1,
        'declaration_sha256': sha(out / 'declaration.json'), 'source_sha256_before': sources,
        'total_budget_s': SECONDS, 'scene_slice_s': SLICE_SECONDS,
        'K117_original_failed_gate_and_shutdown_limit_retained': True,
        'scope': 'fixed shared A, seed-defined N1; evidence formed before one absolute cutoff only'}
    save(out / 'run_record.json', record)

    def loader(budget):
        raw, config, instance = fresh_input(budget)
        if (canonical_hash(config) != declaration['original_config_sha256']
                or canonical_hash(instance) != declaration['original_instance_sha256']
                or opened_stages(instance) != declaration['opened_by_scene']):
            raise ValueError('Fresh billed input differs from declaration')
        budget.check()
        return config, instance

    def report_update(result, update):
        print(json.dumps({'event': 'SAFE_AGGREGATE_UPDATE',
            'elapsed_s': update['committed_at_s'], 'source': update['trigger_source'],
            'U_J': update['safe_upper_bound_J']}, ensure_ascii=False), flush=True)

    print('START K126: one fresh N1 call; 300 s total, 60 s scene slices, CDF off, Cut10', flush=True)
    began = time.monotonic()
    result = error = None
    try:
        result = execute_n1_neighborhood(loader, call / 'invocation',
            shared_deployment=dict(SHARED), opened_by_scene=declaration['opened_by_scene'],
            seconds=SECONDS, scene_slice_s=SLICE_SECONDS,
            builder_options={'cumulative_precedence': False},
            session_factory=partial(MatlabSession, cut_max_iterations=CUT_MAX_ITERATIONS),
            on_global_update=report_update)
    except BaseException:
        error = traceback.format_exc()
    record['wrapper_call_wall_s'] = time.monotonic() - began
    cleanup, cleanup_error = None, None
    closed = call / 'invocation/matlab/closed.json'
    if closed.exists():
        try:
            cleanup = read(closed)
            if not isinstance(cleanup, dict):
                raise ValueError('Native cleanup receipt is not a mapping')
        except (OSError, ValueError) as exc:
            cleanup_error = f'{type(exc).__name__}: {exc}'
    elif isinstance(result, dict) and (result.get('matlab_worker_ready')
                                      or result.get('solver_request_attempts', 0)):
        cleanup_error = 'Native worker used but cleanup receipt missing'
    after, source_error = None, None
    try:
        after = collect_sources()
        unchanged = (after == sources and gate_evidence() == declaration['K125_evidence_sha256']
            and sha(READ_FIX) == declaration['K117_read_fix_report_sha256'])
    except (OSError, ValueError) as exc:
        unchanged, source_error = False, f'{type(exc).__name__}: {exc}'
    issues = technical_issues(result)
    cleanup_failed = isinstance(cleanup, dict) and (
        cleanup.get('cleanup_pending_pid') is not None or cleanup.get('error')
        or cleanup.get('cleanup_error') or cleanup.get('returncode') not in (None, 0))
    method = result if isinstance(result, dict) else {}
    failed = bool(error or not unchanged or issues or cleanup_error or cleanup_failed)
    record.update(state='STOPPED_TECHNICAL_FAILURE' if failed else 'CALL_COMPLETED',
        error=error, source_unchanged=unchanged, source_sha256_after=after,
        source_check_error=source_error, technical_issues=issues, cleanup_status=cleanup,
        cleanup_metadata_error=cleanup_error, method_state=method.get('state'),
        method_reason=method.get('reason'), method_technical_state=method.get('technical_state'),
        initial_global_safe_upper_bound_J=method.get('initial_global_safe_upper_bound_J'),
        safe_upper_bound_J=method.get('safe_upper_bound_J'),
        inner_MILP_improved_initial_upper_bound=method.get('inner_MILP_improved_initial_upper_bound'),
        strict_improvement_over_initial_certified=method.get('strict_improvement_over_initial_certified'),
        method_timing=method.get('timing'), finished_at_utc=datetime.now(timezone.utc).isoformat())
    save(call / 'run_record.json', record)
    save(out / 'run_record.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return not failed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.out)
    else:
        raise SystemExit(0 if run(args.out) else 1)
