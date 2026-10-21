"""K148: one fresh linked-4 versus linked-5 pair; no retries or oracle seeds."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BASE = HERE/'results/heft_sa_followup01/declaration.json'
PROTOCOL_FILE = HERE/'results/five_open_preparation01/protocol.md'
TARGET = HERE/'results/linked_five_open_pair01'
GLOBAL_CLAIM = HERE/'results/linked_five_open_claim01.json'
NEW = ('run_five_open_pair.py', 'test_five_open_pair.py')
PROTOCOL = 'K148-fresh-linked4-linked5-quality-pair-v1'
CHECK_PROTOCOL = 'K148-five-open-pair-offline-precheck-v1'
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    pending = path.with_suffix(path.suffix+'.pending')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        stream.write('\n')
    pending.replace(path)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def jobs():
    return [{'id': 'old_linked4', 'opened_count': 4},
            {'id': 'new_linked5', 'opened_count': 5}]


def local(path):
    path = Path(path).resolve()
    path.relative_to(REPO)
    if path != TARGET.resolve():
        raise ValueError('Only the frozen K148 output is allowed')
    return path


def sources():
    paths = list(HERE.glob('*.py'))+[HERE/'config_v01.json', HERE/'solve_model.m',
                                            HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}


def source_gate():
    base = read(BASE)['source_sha256']
    current = sources()
    extra = {(HERE/n).relative_to(REPO).as_posix() for n in NEW}
    if (len(base) != 165 or len(current) != 167 or set(current) != set(base)|extra
            or any(current.get(n) != h for n, h in base.items())):
        raise ValueError('Unchanged inherited 165 sources plus exactly two K148 files required')
    return current


def settings():
    import run_linked_pair as inherited
    return deepcopy(inherited.SHARED), deepcopy(inherited.BUILD_OPTIONS)


def masks(instance, count):
    if count not in (4, 5):
        raise ValueError('Only the predeclared four/five opening is allowed')
    result = {}
    for scene in instance['scenarios']:
        stages = scene['stage_instances']
        ids = [s['id'] for s in stages if s['shared_stage_id'] in
               ('A.pre', 'A.main', 'A.post', 'B.pre', 'C.pre') or
               (count == 5 and s['shared_stage_id'] in ('B.main', 'C.main'))]
        if len(stages) != 6 or len(ids) != count or len(set(ids)) != count:
            raise ValueError('Original two full three-Stage chains required')
        result[scene['id']] = sorted(ids)
    return result


def fresh_input(budget=None):
    from run_neighborhood_diagnostic import fresh_input as inherited
    return inherited(budget)


def entry_points():
    from linked_method import execute_linked_fixed_unit_opp_start
    from matlab_bridge import MatlabSession
    return {'linked': execute_linked_fixed_unit_opp_start, 'session': MatlabSession}


def rules():
    shared, build = settings()
    return {'protocol': PROTOCOL, 'jobs': jobs(), 'method_call_limit': 2,
        'per_method_budget_s': SECONDS, 'scene_slice_s': SCENE_SECONDS,
        'CutMaxIterations': CUT, 'shared_deployment': shared, 'builder_options': build,
        'problem': 'base__R1', 'window_ms': 400, 'start_grid_ms': 5,
        'idle_policy': 'auto_low_immediate_v1', 'retry_allowed': False,
        'extend_budget_allowed': False, 'candidate_cache_or_witness_shared': False,
        'changed_factor': 'second pass opens local B/C.main in addition to A chain and local pre',
        'unit_choices': 'original fresh seed units, unchanged in both passes',
        'closed_choice_anchor': 'last complete first-pass SAFE generation of this invocation only',
        'normal_deadline_can_continue_after_isolation': True,
        'technical_or_unresolved_stops_remaining': True,
        'authorization': 'new direct manual user authorization after autonomous external review was paused; no expired night quota reused',
        'primary_success': 'new complete SAFE energy upper strictly below old complete SAFE energy lower',
        'method_clock': 'one root budget before linked entry input/lazy setup; includes startup, construction, solve and continuous review',
        'post_method_scope': 'stored evidence audit and serialization only; never creates late U',
        'interpretation': 'single quality pair, not statistical or global optimality evidence'}


def check_gate(path, current):
    value = read(path)
    if (value.get('protocol') != CHECK_PROTOCOL or value.get('passed') is not True
            or value.get('source_sha256') != current or value.get('source_unchanged') is not True
            or value.get('errors') != 0 or value.get('failures') != 0
            or value.get('skipped') != 0 or value.get('error') is not None
            or not value.get('tests_run') or not isinstance(value.get('blocked_calls'), dict)
            or not value['blocked_calls'] or any(value['blocked_calls'].values())
            or any(value.get(k) != 0 for k in
                ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations'))):
        raise ValueError('Matching zero-research-call K148 precheck required')
    return value


def scene_spec(instance):
    return {s['id']: {'weight': s['weight'], 'window_s': str(F(instance['window_ms'])/1000),
        'limits': dict(zip(instance['platform']['node_order'], s['maximum_temperature_degC']))}
        for s in instance['scenarios']}


def prepare(out, checks):
    from run_neighborhood_diagnostic import opened_stages
    out = local(out)
    if out.exists() or GLOBAL_CLAIM.exists():
        raise FileExistsError('K148 output or single-use claim already exists')
    current = source_gate()
    check_gate(checks, current)
    raw, config, instance = fresh_input()
    identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                           map(canonical, (raw, config, instance))))
    if identities != read(BASE)['input_identities']:
        raise ValueError('Frozen original input changed')
    out.mkdir(parents=True)
    (out/'claims').mkdir()
    names = ('input_raw.json', 'input_config.json', 'input_instance.json')
    for name, value in zip(names, (raw, config, instance)):
        save(out/name, value)
    for name, digest in current.items():
        destination = out/'source_snapshot'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, destination)
        if sha(destination) != digest:
            raise ValueError('Source changed during snapshot')
    shutil.copyfile(checks, out/'precheck.json')
    shutil.copyfile(PROTOCOL_FILE, out/'protocol.md')
    declaration = {**rules(), **identities, 'input_identities': identities,
        'source_sha256': current, 'baseline_declaration_sha256': sha(BASE),
        'precheck_sha256': sha(out/'precheck.json'), 'scene_spec': scene_spec(instance),
        'protocol_file_sha256': sha(PROTOCOL_FILE),
        'first_opened_by_scene': opened_stages(instance),
        'linked_opened_by_job': {j['id']: masks(instance, j['opened_count']) for j in jobs()},
        'input_file_sha256': {n: sha(out/n) for n in names}, 'declared_at_utc': now()}
    save(out/'declaration.json', declaration)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'state': 'DECLARED', 'consumed': 0,
        'reserved_method_budget_s': 0, 'calls': []})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    admission(out)
    return {'prepared': True, 'source_files': len(current), 'research_calls': 0}


def admission(out):
    from run_neighborhood_diagnostic import opened_stages
    out = local(out)
    declaration, current = read(out/'declaration.json'), source_gate()
    if (any(declaration.get(k) != v for k, v in rules().items())
            or declaration.get('source_sha256') != current
            or declaration.get('baseline_declaration_sha256') != sha(BASE)
            or declaration.get('precheck_sha256') != sha(out/'precheck.json')
            or declaration.get('protocol_file_sha256') != sha(PROTOCOL_FILE)
            or declaration.get('protocol_file_sha256') != sha(out/'protocol.md')):
        raise ValueError('Frozen rule/source/baseline/precheck changed')
    check_gate(out/'precheck.json', current)
    for name, digest in current.items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Frozen source snapshot changed: '+name)
    for name, digest in declaration['input_file_sha256'].items():
        if sha(out/name) != digest:
            raise ValueError('Frozen input bytes changed: '+name)
    identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
        (canonical(read(out/n)) for n in ('input_raw.json', 'input_config.json', 'input_instance.json'))))
    instance = read(out/'input_instance.json')
    if (identities != declaration['input_identities'] or identities != read(BASE)['input_identities']
            or any(declaration[k] != v for k, v in identities.items())
            or declaration['scene_spec'] != scene_spec(instance)
            or declaration['first_opened_by_scene'] != opened_stages(instance)
            or declaration['linked_opened_by_job'] != {j['id']: masks(instance, j['opened_count']) for j in jobs()}):
        raise ValueError('Original input/domain identity changed')
    return declaration


def execute(job, out, declaration, entries):
    entry_started = time.monotonic()
    from timing import MethodBudget
    budget = MethodBudget(float(SECONDS), clock=time.monotonic)
    budget.start, budget.deadline = entry_started, entry_started+SECONDS
    budget.check()
    if job not in jobs():
        raise ValueError('Unknown K148 job')
    identity = {'input_verified': None}
    def loader(budget):
        raw, config, instance = fresh_input(budget)
        actual = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                          map(canonical, (raw, config, instance))))
        identity['input_verified'] = actual == declaration['input_identities']
        if identity['input_verified'] is not True:
            raise ValueError('Billed fresh original input changed')
        if masks(instance, job['opened_count']) != declaration['linked_opened_by_job'][job['id']]:
            raise ValueError('Billed opening changed')
        budget.check()
        return config, instance
    def update(result, record):
        print(json.dumps({'event': 'SAFE_AGGREGATE_UPDATE', 'method': job['id'],
            'phase_index': record.get('phase_index'), 'elapsed_s': record['committed_at_s'],
            'U_J': record['safe_upper_bound_J']}), flush=True)
    shared, build = settings()
    result = entries['linked'](loader, out/job['id'], seconds=SECONDS,
        budget=budget, clock=budget.clock,
        shared_deployment=shared, scene_slice_s=SCENE_SECONDS,
        builder_options=build, session_factory=partial(entries['session'], cut_max_iterations=CUT),
        opened_by_scene=deepcopy(declaration['first_opened_by_scene']),
        linked_opened_by_scene=deepcopy(declaration['linked_opened_by_job'][job['id']]),
        on_global_update=update)
    return result, identity


def aggregate_issues(receipt, candidate, declaration, condition):
    """Audit an existing aggregate and its full original-input scene receipts."""
    from scene_adapter import _receipt_hash
    errors = []
    try:
        spec, identity = declaration['scene_spec'], receipt['identity']
        seed_identity = condition['seed_receipt']['identity']
        if (receipt['state'] != 'SAFE' or receipt['rankable_energy'] is not True
                or receipt['problem_id'] != 'base__R1' or receipt['safe_candidate'] != candidate
                or receipt['receipt_sha256'] != _receipt_hash(receipt)
                or receipt['legality']['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED'
                or set(receipt['scenes']) != set(spec) or set(candidate['scenes']) != set(spec)):
            errors.append('INVALID_COMPLETE_AGGREGATE')
        if (identity['full_input_sha256'] != declaration['input_sha256']
                or identity['candidate_sha256'] != canonical(candidate)
                or identity['budget'] != condition['budget_identity']
                or any(identity[k] != seed_identity[k] for k in
                       ('source_sha256', 'accuracy_sha256', 'control_policy', 'shared_deployment_sha256'))):
            errors.append('AGGREGATE_IDENTITY_MISMATCH')
        stamp = receipt['completed_at_elapsed_s']
        if not finite(stamp) or not 0 <= stamp < SECONDS:
            errors.append('AGGREGATE_OUTSIDE_BUDGET')
        low, high = map(F, receipt['weighted_energy_J'])
        if low < 0 or high < low or F(receipt['safe_upper_bound_J']) != high:
            errors.append('AGGREGATE_ENERGY_INTERVAL_INVALID')
        total_low, total_high = F(0), F(0)
        for sid, definition in spec.items():
            scene = receipt['scenes'][sid]
            physical = scene['result']
            if (scene['receipt_sha256'] != _receipt_hash(scene)
                    or scene['state'] != 'SAFE' or scene['rankable_energy'] is not True
                    or scene['identity']['candidate_sha256'] != canonical({'scenes': {sid: candidate['scenes'][sid]}})
                    or scene['identity']['full_input_sha256'] != declaration['input_sha256']
                    or scene['identity']['budget'] != condition['budget_identity']
                    or physical['state'] != 'SAFE' or physical['complete'] is not True
                    or physical['rankable_energy'] is not True):
                errors.append('INVALID_COMPLETE_SCENE:'+sid)
            window = F(definition['window_s'])
            if F(physical['covered_until_s']) != window or F(physical['trace'][-1]['time_s']) != window:
                errors.append('INCOMPLETE_WINDOW:'+sid)
            if set(physical['peaks_degC']) != set(definition['limits']):
                errors.append('MISSING_THERMAL_NODE:'+sid)
            for node, limit in definition['limits'].items():
                lower, upper = map(F, physical['peaks_degC'][node])
                if upper < lower or upper > F(limit):
                    errors.append('UNSAFE_PEAK_ENCLOSURE:'+sid+':'+node)
            lo, hi = map(F, scene['energy_J'])
            total_low += F(definition['weight'])*lo
            total_high += F(definition['weight'])*hi
        if [total_low, total_high] != [low, high]:
            errors.append('WEIGHTED_ENERGY_MISMATCH')
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        errors.append('MALFORMED_COMPLETE_AGGREGATE')
    return errors


def result_records(job, result, declaration, folder, *, input_valid, source_valid, errors=None):
    """Classify saved evidence. No late decoding, physical evaluation or new U."""
    from completion_metrics import build_completion_metrics
    from execution_status import classify_execution, DEADLINE_REASONS
    from matlab_bridge import cleanup_is_complete
    import run_linked_pair as inherited
    from run_neighborhood_diagnostic import technical_issues
    r = result if isinstance(result, dict) else {}
    hard = list(errors or [])
    condition = r.get('condition') or {}
    identity = r.get('identity') or {}
    input_match = (input_valid is True and identity.get('full_input_sha256') == declaration['input_sha256']
                   and identity.get('config_sha256') == declaration['config_sha256'])
    if input_valid is None and not identity:
        input_match = None
    # Keep every nontransport domain/ledger/anchor check; budget-only transport
    # incompleteness is instead classified below with its causal trace.
    adapted = dict(declaration, old_opened_by_scene=declaration['first_opened_by_scene'],
                   new_opened_by_scene=declaration['linked_opened_by_job'][job['id']])
    domain_issues = inherited.transport_issues(inherited.jobs()[1], r, adapted)
    exempt = {'LATCHED_NUMERICAL_UNRESOLVED', 'REQUEST_ADMISSION_OR_CALLBACK_COVERAGE_UNRESOLVED'}
    hard.extend(v for v in domain_issues if v.get('reason') not in exempt)
    for issue in technical_issues(r):
        if issue.get('reason') != 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED':
            hard.append(issue)
    for phase in r.get('phases') or []:
        hard.extend(v for v in technical_issues({'scenes': phase.get('scenes', {})})
                    if v.get('reason') != 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED')
    cleanup_path = Path(folder)/'matlab/closed.json'
    cleanup = read(cleanup_path) if cleanup_path.is_file() else None
    isolation = ('VERIFIED' if cleanup and cleanup_is_complete(cleanup) else
                 'UNKNOWN' if r.get('matlab_worker_ready') is True else 'NOT_APPLICABLE')
    if cleanup and not cleanup_is_complete(cleanup):
        isolation = 'FAILED'
    safe = None
    aggregate = r.get('aggregation') or {}
    if r.get('safe_upper_bound_J') is not None:
        bad = aggregate_issues(aggregate, r.get('safe_candidate') or {}, declaration, condition)
        if not bad:
            safe = {'verified': True, 'identity_valid': input_match, 'complete': True,
                'formed_at_s': aggregate['completed_at_elapsed_s'], 'energy_upper_J': aggregate['safe_upper_bound_J']}
        else:
            hard.extend(bad)
    requests = (r.get('augmented_transport') or {}).get('requests', [])
    checks = [v for request in requests for v in request.get('numerical_checks', [])]
    numeric = any((v.get('report') or {}).get('accepted') is False for v in checks)
    ambiguous_checks = any(v.get('accepted') is False and (v.get('report') or {}).get('accepted') is not True for v in checks)
    if not numeric and ambiguous_checks:
        numeric = None
    timing = r.get('timing') or {}
    deadline = bool(r.get('budget_exhausted') is True and r.get('reason') == 'wall_time_limit'
                    and timing.get('limit_s') == SECONDS and finite(timing.get('method_elapsed_s'))
                    and timing['method_elapsed_s'] >= SECONDS)
    def complete(request):
        return (request.get('latched_unresolved') is False and request.get('within_budget') is True
            and not request.get('failure_reasons') and request.get('callback_publications_complete') is True
            and request.get('expected_callback_numbers') == request.get('checked_callback_numbers'))
    prior_complete = all(complete(v) for v in requests[:-1])
    last = {'state': 'NONE'}
    causal = deadline
    if requests and not complete(requests[-1]):
        request = requests[-1]
        pyfiles = sorted((Path(folder)/'matlab').glob('request_*.python.json'))
        python = read(pyfiles[-1]) if pyfiles else {}
        poll = python.get('publication_read') or {}
        transient = set((poll.get('transient_read_errors') or {}))
        reasons = request.get('failure_reasons')
        causal = bool(deadline and request.get('cancel_requested') is True
            and request.get('cancel_published_at_s') == SECONDS
            and request.get('native_status') == 'BUDGET_EXHAUSTED'
            and request.get('within_budget') is False
            and python.get('status') == 'BUDGET_EXHAUSTED'
            and python.get('response_may_arrive_later') is True
            and python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == []
            and transient <= {'FileNotFoundError'} and isinstance(reasons, list) and bool(reasons)
            and set(reasons) <= DEADLINE_REASONS)
        last = {'state': 'PENDING', 'pending_at_cutoff': causal,
            'refuses_late_candidate': causal, 'deadline_causal_trace': causal,
            'deadline_reasons': reasons}
    elif requests:
        last = {'state': 'COMPLETE'}
    if not requests and (r.get('augmented_transport') or {}).get('latched_unresolved') is True:
        hard.append('UNEXPLAINED_TRANSPORT_LATCH_WITHOUT_REQUEST')
    context = {'input_identity_valid': input_match, 'source_identity_valid': source_valid,
        'current_request_identity_valid': input_match, 'cutoff_s': SECONDS,
        'hard_errors': hard, 'observed_numerical_rejection': numeric,
        'numerical_checks': checks, 'worker_isolation': isolation,
        'prior_requests_complete': prior_complete, 'completion_verified': not deadline
            and not r.get('search_failure_latched') and bool(r.get('reason') == 'SCENE_SEARCH_SEQUENCE_COMPLETE'),
        'root_deadline_confirmed': deadline, 'deadline_causal_trace': causal,
        'last_request': last, 'safe_receipt': safe, 'thermal_unresolved': False}
    execution = classify_execution(result, context)
    return {'execution': execution, 'usable_U_J': execution['usable_U_J'], 'context': context,
        'completion_metrics': build_completion_metrics(r, uses_matlab=True, seconds=SECONDS),
        'cleanup': cleanup, 'raw_reported_U_J': r.get('safe_upper_bound_J'),
        'phase_quality': inherited.phase_quality(r), 'domain_issues': domain_issues,
        'scope': 'stored evidence only; independent physical recheck is separately archived'}


def run(out, *, execution_authorized=False):
    out = local(out)
    ledger = read(out/'ledger.json')
    if (ledger.get('state') != 'DECLARED' or ledger.get('consumed') != 0
            or ledger.get('calls') or GLOBAL_CLAIM.exists()
            or any((out/'claims'/(j['id']+'.json')).exists() for j in jobs())):
        raise FileExistsError('K148 already claimed/consumed; no retry or restart')
    if execution_authorized is not True:
        raise PermissionError('Explicit execution authorization required')
    declaration = admission(out)
    started_all = time.monotonic()
    imports = time.monotonic()
    entries = entry_points()
    save(out/'runtime_imports.json', {'wall_s': time.monotonic()-imports,
        'scope': 'imports only; no candidates, model, heat or worker'})
    with GLOBAL_CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'declaration_sha256': sha(out/'declaration.json'), 'claimed_utc': now(), 'no_retry': True}, stream)
    okay = True
    for job in jobs():
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'claimed_utc': now(), 'no_retry': True}, stream)
        row = {**job, 'state': 'RUNNING', 'started_utc': now()}
        ledger['calls'].append(row)
        ledger.update(state='RUNNING', consumed=ledger['consumed']+1,
                      reserved_method_budget_s=ledger['reserved_method_budget_s']+SECONDS)
        save(out/'ledger.json', ledger)
        result, identity, errors = None, {'input_verified': None}, []
        started = time.monotonic()
        try:
            result, identity = execute(job, out, declaration, entries)
        except BaseException:
            errors.append(traceback.format_exc())
        returned = time.monotonic()-started
        source_valid = True
        try:
            admission(out)
        except Exception:
            source_valid = False
            errors.append(traceback.format_exc())
        post = time.monotonic()
        if isinstance(result, dict):
            save(out/job['id']/'wrapper_raw_result.json', result)
        try:
            records = result_records(job, result, declaration, out/job['id'],
                input_valid=identity['input_verified'], source_valid=source_valid, errors=errors)
        except Exception:
            errors.append(traceback.format_exc())
            records = {'execution': {'execution_status': 'TECHNICAL_FAILURE_CONFIRMED'},
                       'usable_U_J': None, 'record_errors': errors}
        acceptable = records['execution']['execution_status'] in (
            'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        row.update(state='COMPLETED' if acceptable else 'BLOCKED', completed_utc=now(),
            errors=errors, method_return_inclusive_wall_s=returned,
            source_identity_valid=source_valid, **records)
        save(out/'claims'/(job['id']+'_result.json'), row)
        row['post_method_record_wall_s'] = time.monotonic()-post
        artifacts = {p.relative_to(out/job['id']).as_posix(): sha(p)
                     for p in sorted((out/job['id']).rglob('*')) if p.is_file()}
        save(out/'claims'/(job['id']+'_artifact_sha256.json'), artifacts)
        ledger['state'] = 'RUNNING' if acceptable else 'BLOCKED'
        save(out/'ledger.json', ledger)
        print(json.dumps({'method': job['id'], 'execution_status': records['execution']['execution_status'],
                          'usable_U_J': records.get('usable_U_J')}), flush=True)
        if not acceptable:
            okay = False
            break
    if okay:
        ledger['state'] = 'COMPLETED'
        save(out/'ledger.json', ledger)
    save(out/'wrapper_timing.json', {'wall_s': time.monotonic()-started_all,
        'scope': 'imports, method returns/cleanup, stored-record review and primary archives; no late physical evidence'})
    return okay


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    parser.add_argument('--execution-authorized', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        if args.checks is None:
            parser.error('--prepare requires --checks')
        print(json.dumps(prepare(args.out, args.checks)))
    else:
        raise SystemExit(0 if run(args.out, execution_authorized=args.execution_authorized) else 1)
