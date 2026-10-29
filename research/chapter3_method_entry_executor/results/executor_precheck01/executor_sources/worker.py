"""One isolated method/post worker. Production imports are lazy and gated.

Importing this module performs no input reads, model construction, search,
thermal integration, subprocess creation or authorization consumption.
"""
from copy import deepcopy
from fractions import Fraction as F
from functools import partial
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = ROOT / 'research/chapter3_experiments'


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str, allow_nan=False).encode()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _save(path, value):
    from .common import save
    save(Path(path), value)


def _finite_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _minimum(*values):
    finite = [v for v in values if _finite_time(v)]
    return min(finite) if finite else None


def _timely(cutoff, *values):
    return _minimum(*[v for v in values if _finite_time(v) and v < cutoff])


def _cleanup(raw, method_dir):
    needed = bool(raw.get('matlab_worker_ready') or raw.get('startup_cleanup'))
    if not needed:
        return {'required': False, 'receipt': None, 'verified': True}
    receipt = raw.get('startup_cleanup')
    path = Path(method_dir)/'matlab/closed.json' if method_dir is not None else None
    if path is not None and path.is_file():
        try:
            receipt = _load(path)
        except Exception as error:
            return {'required': True, 'receipt': deepcopy(receipt), 'verified': None,
                    'read_error': type(error).__name__+': '+str(error)}
    if not isinstance(receipt, dict):
        return {'required': True, 'receipt': receipt, 'verified': None}
    errors = [key for key, value in receipt.items()
              if value and ('error' in key.lower() or key.startswith('cleanup_pending'))]
    verified = (receipt.get('cleanup_status') in ('graceful_closed', 'forced_closed')
                and receipt.get('observed_tree_verified_terminated') is True and not errors)
    return {'required': True, 'receipt': deepcopy(receipt), 'verified': bool(verified),
            'error_fields': errors}


def normalize_result(raw, job, instance, *, input_sha256, plan_sha256,
                     input_verified=True, method_dir=None):
    """Consume already formed evidence; never reevaluate or repair a candidate.

    SAFE preservation is independent of execution faults. In particular a
    prior complete SAFE cannot hide a later numerical/transport/cleanup error.
    """
    from .common import inspect_safe_receipt
    raw = deepcopy(raw) if isinstance(raw, dict) else {'error': 'NO_METHOD_RESULT'}
    safe = inspect_safe_receipt(instance, raw, cutoff_s=job['method_seconds'])
    if not input_verified:
        safe.update(preserved=False, reason='INPUT_LOADER_NOT_VERIFIED', U_J=None)
    initial = raw.get('initialisation') or {}
    diagnostic = raw.get('diagnostic') or {}
    errors = []
    for source, item in (('method', raw), ('diagnostic', raw.get('solver_diagnostic') or {})):
        for key in ('error', 'fatal_error', 'cleanup_error'):
            if item.get(key): errors.append({'source': source, 'field': key, 'value': item[key]})
    if not input_verified:
        errors.append({'source': 'loader', 'field': 'input_identity', 'value': 'NOT_VERIFIED'})
    reasons = [raw.get('reason'), (raw.get('solver_diagnostic') or {}).get('reason')]
    if any(r in ('RESOURCE_LIMIT', 'INTERFACE_ERROR', 'INITIALISED_SOLVER_INTERFACE_ERROR',
                 'SOLVER_INTERFACE_ERROR') for r in reasons):
        errors.append({'source': 'method', 'field': 'reason', 'value': raw.get('reason')})
    numerical = bool(any(r in ('SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED',
                               'NUMERICAL_ADMISSION_STATUS_CONFLICT',
                               'NUMERICAL_CANDIDATE_ANOMALY') for r in reasons))
    admission = (initial.get('completion') or {}).get('numerical_acceptance')
    if isinstance(admission, dict) and admission.get('accepted_numerically') is False:
        numerical = True
    if initial.get('state') == 'SAFE_POINT_REJECTED' and not numerical:
        errors.append({'source': 'initial_point', 'field': 'point_rejected',
                       'value': (initial.get('completion') or {}).get('reason', initial.get('reason'))})
    cleanup = _cleanup(raw, method_dir)
    if cleanup['verified'] is not True:
        errors.append({'source': 'cleanup', 'field': 'verification', 'value': cleanup['verified']})
    budget_expired = (raw.get('budget_exhausted') is True or
        any(r in ('wall_time_limit', 'WALL_TIME_LIMIT', 'METHOD_BUDGET_EXHAUSTED',
                  'SOLVER_RETURN_AFTER_BUDGET') for r in reasons))
    if errors:
        status = 'TECHNICAL_FAILURE_CONFIRMED'
    elif numerical:
        status = 'NUMERICAL_ANOMALY_OBSERVED'
    elif budget_expired:
        status = 'NORMAL_TIME_LIMIT'
    elif any(r in ('EVALUATION_UNRESOLVED', 'FEEDBACK_UNRESOLVED') for r in reasons):
        status = 'STATUS_UNRESOLVED'
    else:
        status = 'NORMAL_COMPLETION'
    attempts = initial.get('attempts') or []
    cutoff = job['method_seconds']
    initial_legal = _timely(cutoff, *[a.get('schedule_completed_at_s') for a in attempts
        if isinstance(a, dict) and a.get('status') == 'COMPLETE_LEGAL_CANDIDATE'])
    native_legal = _timely(cutoff, diagnostic.get('first_legal_candidate_s'))
    initial_safe = _timely(cutoff, raw.get('first_initial_safe_s'))
    native_safe = _timely(cutoff, diagnostic.get('first_safe_receipt_s'))
    first_legal = (_timely(cutoff, raw.get('first_legal_candidate_at_s')) if job['id'] != 'whole_milp'
                   else _timely(cutoff, initial_legal, native_legal))
    first_safe = (_timely(cutoff, raw.get('first_safe_at_s')) if job['id'] != 'whole_milp'
                  else _timely(cutoff, initial_safe, native_safe))
    return {
        'schema': 'ch3-method-worker-result-v1', 'method_id': job['id'], 'job_id': job['id'],
        'plan_sha256': plan_sha256, 'common_input_sha256': input_sha256, 'input_sha256': input_sha256,
        'instance_sha256': _canonical(instance), 'input_identity_verified': bool(input_verified),
        'execution_status': status, 'errors': errors,
        'observed_numerical_rejection': numerical, 'numerical_anomaly': numerical,
        'cleanup_verified': cleanup['verified'], 'matlab_cleanup': cleanup,
        'stop_stage': raw.get('stop_stage'), 'method_state': raw.get('state'),
        'method_reason': raw.get('reason'), 'budget_exhausted': budget_expired,
        'method_elapsed_s': (raw.get('timing') or {}).get('method_elapsed_s'),
        'first_legal_candidate_at_s': first_legal, 'first_complete_SAFE_at_s': first_safe,
        'first_legal_candidate_s': first_legal, 'first_complete_safe_s': first_safe,
        'first_initial_legal_at_s': initial_legal, 'first_initial_SAFE_at_s': initial_safe,
        'first_native_legal_at_s': native_legal, 'first_native_SAFE_at_s': native_safe,
        'integer_solver_entered': raw.get('integer_solver_entered'),
        'matlab_worker_ready': raw.get('matlab_worker_ready'),
        'model_complete': raw.get('model_complete'), 'matrix_complete': raw.get('matrix_complete'),
        'initialisation_state': initial.get('state'), 'initialisation_reason': initial.get('reason'),
        'safe_witness_preserved': bool(safe['preserved']), 'SAFE_receipt_check': safe,
        'safe_evidence': safe,
        'safe_candidate': deepcopy(raw.get('safe_candidate')) if safe['preserved'] else None,
        'evaluation': deepcopy(raw.get('evaluation')) if safe['preserved'] else None,
        'safe_upper_bound_J': safe.get('U_J') if safe['preserved'] else None,
        'safe_solution_source': raw.get('safe_solution_source'),
        'raw_result': raw, 'independently_proven_optimal': False,
        'scope': 'one independent method, no repair or new post-budget evaluation',
    }


def production_bindings():
    """Called only after context/authorization/ticket checks in main."""
    folder = str(EXPERIMENTS)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    from formal_milp import execute_formal_milp
    from heuristic_runner import execute_heuristic
    from milp import build_model
    from matlab_bridge import MatlabSession
    from partial_bounds import independent_lower_bound
    return {'whole': execute_formal_milp, 'heuristic': execute_heuristic,
            'builder': build_model, 'session': MatlabSession,
            'lower': independent_lower_bound}


def _recover_current_result(method_dir):
    path = Path(method_dir)/'result.json'
    if path.is_file():
        try:
            value = _load(path)
            if isinstance(value, dict): return value
        except Exception:
            pass
    checkpoint = Path(method_dir)/'initial_receipt_checkpoint.json'
    if checkpoint.is_file():
        try:
            initial = _load(checkpoint)['initialisation']
            witness = initial.get('witness')
            if witness:
                return {'state': 'SAFE', 'safe_candidate': witness['candidate'],
                    'evaluation': witness['evaluation'],
                    'safe_upper_bound_J': witness['evaluation']['safe_upper_bound_J'],
                    'safe_solution_source': 'initial_constructor_checkpoint',
                    'initialisation': initial}
        except Exception:
            pass
    return {'state': 'UNRESOLVED', 'reason': 'NO_RETURNED_METHOD_RECEIPT'}


def run_method(context, job, out, *, bindings=None):
    """Run one original lifecycle, or injected mocks in pure tests."""
    from .common import verify_input
    out = Path(out)
    _require(not out.exists(), 'WORKER_OUTPUT_ALREADY_EXISTS')
    out.mkdir(parents=True)
    actual = bindings
    verify = (bindings or {}).get('verify_input', verify_input)
    identity = {'verified': False, 'instance': None}
    bounds = {}

    def loader(budget):
        budget.check()
        value = verify(context)
        identity.update(verified=True, instance=value['instance'])
        _save(out/'loader_identity.json', {
            'plan_sha256': context['plan_sha256'],
            'input_sha256': context['plan']['common_input_sha256'],
            'instance_sha256': _canonical(value['instance']),
            'config_sha256': _canonical(value['config']),
            'source_manifest_sha256': _canonical(context['plan']['source_sha256'])})
        if job['id'] == 'whole_milp':
            with budget.phase('comparison_independent_lower_bound'):
                bounds['L0'] = actual['lower'](value['instance'], None, budget)
        budget.check()
        return value['config'], value['instance']

    method_dir = out/'method'
    try:
        if actual is None:
            actual = production_bindings()
        _save(out/'method_call_started.json', {'job_id': job['id'],
            'plan_sha256': context['plan_sha256'], 'scope': 'method lifecycle entry, not native solver entry'})
        if job['id'] == 'whole_milp':
            raw = actual['whole'](loader, method_dir, seconds=job['method_seconds'],
                feedback_kind=job['feedback_kind'],
                model_builder=partial(actual['builder'],
                    prefilter_deadlines=job['builder_flags']['prefilter_deadlines'],
                    cumulative_precedence=job['builder_flags']['cumulative_precedence']),
                session_factory=partial(actual['session'], cut_max_iterations=job['cut_max_iterations']))
        else:
            raw = actual['heuristic'](loader, method_dir, method=job['method'],
                seconds=job['method_seconds'], seed=job['seed'], allow_auto_low=job['allow_auto_low'])
    except Exception as error:
        raw = _recover_current_result(method_dir)
        raw.update(error=type(error).__name__+': '+str(error),
                   reason='RESOURCE_LIMIT' if isinstance(error, MemoryError) else 'WORKER_METHOD_EXCEPTION')
    if bounds: _save(out/'independent_bounds.json', bounds)
    # If the lifecycle failed before loader, no candidate from it may be used.
    value = verify(context)
    normalized = normalize_result(raw, job, value['instance'],
        input_sha256=context['plan']['common_input_sha256'], plan_sha256=context['plan_sha256'],
        input_verified=identity['verified'], method_dir=method_dir)
    normalized['source_manifest_sha256'] = _canonical(context['plan']['source_sha256'])
    _save(out/'worker_result.json', normalized)
    return normalized


def validate_ticket(context, ticket_path, token, output, *, now=None):
    """Check a supervisor-created slot ticket before any production import."""
    now = time.monotonic() if now is None else now
    path, output = Path(ticket_path).resolve(), Path(output).resolve()
    ticket = _load(path)
    required = {'schema', 'plan_sha256', 'input_sha256', 'job_id', 'mode', 'slot_id',
                'worker_token', 'created_at_monotonic_s', 'absolute_deadline_monotonic_s',
                'method_output', 'ticket_claim_path', 'batch_claim_path', 'batch_output'}
    _require(set(ticket) == required and ticket['schema'] == 'ch3-method-entry-ticket-v1', 'TICKET_SCHEMA')
    _require(ticket['plan_sha256'] == context['plan_sha256'] and
             ticket['input_sha256'] == context['plan']['common_input_sha256'] and
             isinstance(token, str) and bool(token) and ticket['worker_token'] == token, 'TICKET_IDENTITY')
    jobs = {j['id']: j for j in context['plan']['jobs']}
    _require(ticket['job_id'] in jobs and ticket['mode'] in ('method', 'post'), 'TICKET_JOB_MODE')
    batch_output = Path(ticket['batch_output']).resolve()
    package = Path(__file__).resolve().parent
    _require(batch_output.is_relative_to((package/'results').resolve()), 'BATCH_OUTPUT_SCOPE')
    expected_slot = batch_output/'slots'/(ticket['job_id']+'__'+ticket['mode'])
    _require(path == expected_slot/'ticket.json' and ticket['slot_id'] == expected_slot.name,
             'SLOT_IDENTITY_SCOPE')
    batch_claim = Path(ticket['batch_claim_path']).resolve()
    _require(batch_claim == (package/'claims'/(context['plan_sha256']+'.json')).resolve(),
             'BATCH_CLAIM_SCOPE')
    batch_record = _load(batch_claim)
    _require(batch_record.get('plan_sha256') == context['plan_sha256']
             and batch_record.get('input_sha256') == context['plan']['common_input_sha256']
             and Path(batch_record.get('batch_output', '')).resolve() == batch_output
             and batch_record.get('authorization_sha256') == hashlib.sha256(
                 Path(context['authorization_path']).read_bytes()).hexdigest(), 'BATCH_CLAIM_IDENTITY')
    slot_record = _load(expected_slot/'slot_claim.json')
    _require(slot_record.get('slot_id') == ticket['slot_id']
             and slot_record.get('ticket_sha256') == hashlib.sha256(path.read_bytes()).hexdigest(),
             'SLOT_CLAIM_IDENTITY')
    created, deadline = ticket['created_at_monotonic_s'], ticket['absolute_deadline_monotonic_s']
    _require(_finite_time(created) and _finite_time(deadline) and created <= now < deadline, 'TICKET_DEADLINE')
    bound = jobs[ticket['job_id']]['process_wall_seconds' if ticket['mode'] == 'method' else 'independent_post_seconds']
    _require(0 < deadline-created <= bound, 'TICKET_BUDGET_EXTENSION')
    claim = Path(ticket['ticket_claim_path']).resolve()
    _require(claim.parent == path.parent and claim.name == 'worker_started.json' and not claim.exists(), 'TICKET_CLAIM_SCOPE')
    _require(not output.exists() and output.parent == path.parent, 'TICKET_OUTPUT_SCOPE')
    if ticket['mode'] == 'method':
        _require(ticket['method_output'] is None, 'METHOD_TICKET_HAS_FOREIGN_OUTPUT')
    else:
        _require(Path(ticket['method_output']).resolve() ==
                 batch_output/'slots'/(ticket['job_id']+'__method')/'worker', 'POST_METHOD_OUTPUT_SCOPE')
    return ticket, jobs[ticket['job_id']]


def run_post(context, ticket, out, *, bindings=None):
    """Recheck this invocation's final SAFE once, within the slot deadline."""
    from .common import verify_input
    out = Path(out); _require(not out.exists(), 'POST_OUTPUT_ALREADY_EXISTS'); out.mkdir(parents=True)
    deadline = ticket['absolute_deadline_monotonic_s']
    envelope = {'schema': 'ch3-method-post-result-v1', 'method_id': ticket['job_id'],
        'job_id': ticket['job_id'],
        'plan_sha256': context['plan_sha256'], 'common_input_sha256': context['plan']['common_input_sha256'],
        'input_sha256': context['plan']['common_input_sha256'],
        'source_manifest_sha256': _canonical(context['plan']['source_sha256']),
        'post_state': 'UNRESOLVED', 'errors': [], 'within_absolute_deadline': False,
        'cleanup_verified': True, 'matlab_cleanup': {'required': False, 'receipt': None, 'verified': True},
        'evaluation': None, 'new_method_result_accepted': False,
        'scope': 'independent verification only; never search, repair, or improve'}
    try:
        _require(time.monotonic() < deadline, 'POST_BUDGET_BEFORE_IMPORT')
        if bindings is None:
            folder = str(EXPERIMENTS)
            if folder not in sys.path: sys.path.insert(0, folder)
            from thermal import Budget, evaluate_candidate
            actual = {'Budget': Budget, 'evaluate': evaluate_candidate, 'verify_input': verify_input}
        else:
            actual = bindings
        value = actual.get('verify_input', verify_input)(context)
        source = Path(ticket['method_output'])/'worker_result.json'
        method = _load(source)
        _require(method['method_id'] == ticket['job_id'] and method['plan_sha256'] == context['plan_sha256']
                 and method['common_input_sha256'] == context['plan']['common_input_sha256']
                 and method['safe_witness_preserved'] is True, 'POST_FINAL_SAFE_IDENTITY')
        from .common import inspect_safe_receipt
        verified = inspect_safe_receipt(value['instance'], method['raw_result'], cutoff_s=300)
        _require(verified['preserved'] and verified['candidate'] == method['safe_candidate'],
                 'POST_METHOD_SAFE_RECEIPT_INVALID')
        envelope['method_receipt_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        before = time.monotonic(); remaining = deadline-before
        _require(remaining > 0, 'POST_BUDGET_BEFORE_EVALUATION')
        budget = actual['Budget'](seconds=remaining)
        # Align the existing evaluator clock exactly with the supervisor's
        # absolute cutoff; process startup/import/input work is never refunded.
        budget.start = before
        result = actual['evaluate'](value['instance'], method['safe_candidate'],
            value['config']['accuracy_targets'], budget)
        within = time.monotonic() < deadline
        envelope.update(within_absolute_deadline=within, evaluation=result,
                        evaluation_budget_origin_monotonic_s=before,
                        post_state=result.get('state') if within else 'UNRESOLVED')
        if envelope['post_state'] == 'SAFE':
            checked = inspect_safe_receipt(value['instance'], {
                'safe_candidate': method['safe_candidate'], 'evaluation': result,
                'safe_upper_bound_J': result.get('safe_upper_bound_J')}, cutoff_s=remaining)
            _require(checked['preserved'], 'POST_SAFE_RECEIPT_INVALID')
        kept_violations = []
        limits = {s['id']: s for s in value['instance']['scenarios']}
        nodes = value['instance']['platform']['node_order']
        for witness in result.get('violations', []):
            formed = witness.get('formed_at_elapsed_s')
            sid, node = witness.get('scene_id'), witness.get('node')
            if not (_finite_time(formed) and before+formed < deadline and sid in limits and node in nodes):
                continue
            low, high = map(F, witness['temperature_degC'])
            limit = F(limits[sid]['maximum_temperature_degC'][nodes.index(node)])
            if (result.get('evidence_identity') == {'input_sha256': _canonical(value['instance']),
                    'candidate_sha256': _canonical(method['safe_candidate'])}
                    and low <= high and low > limit and F(witness['limit_degC']) == limit
                    and F(0) <= F(witness['time_s']) <= F(value['instance']['window_ms'])/1000):
                kept_violations.append(deepcopy(witness))
        envelope['timely_violations_preserved'] = kept_violations
        if kept_violations:
            envelope['post_state'] = 'THERMAL_VIOLATION'
        _require(envelope['post_state'] in ('SAFE', 'UNRESOLVED', 'INVALID_SCHEDULE', 'THERMAL_VIOLATION'),
                 'UNEXPECTED_POST_STATE')
    except Exception as error:
        if str(error).startswith('POST_BUDGET_'):
            envelope.update(post_state='UNRESOLVED', reason=str(error))
        else:
            envelope.update(post_state='ERROR', errors=[type(error).__name__+': '+str(error)])
    _save(out/'post_result.json', envelope)
    return envelope


def wait_monitor_ready(context, ticket, *, clock=time.monotonic, sleep=time.sleep, pid=None):
    """No algorithm may start before the supervisor can observe this worker."""
    pid = os.getpid() if pid is None else pid
    path = Path(ticket['ticket_claim_path']).resolve().parent/'monitor_ready.json'
    while clock() < ticket['absolute_deadline_monotonic_s']:
        try:
            value = _load(path)
        except (FileNotFoundError, PermissionError, json.JSONDecodeError):
            sleep(min(0.01, max(0, ticket['absolute_deadline_monotonic_s']-clock())))
            continue
        _require(value == {'worker_token': ticket['worker_token'],
                           'plan_sha256': context['plan_sha256'], 'pid': pid},
                 'MONITOR_READY_IDENTITY')
        _require(clock() < ticket['absolute_deadline_monotonic_s'], 'MONITOR_READY_AFTER_DEADLINE')
        return True
    raise TimeoutError('MONITOR_NOT_READY_BEFORE_SLOT_DEADLINE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True); parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--authorization', required=True); parser.add_argument('--ticket', required=True)
    parser.add_argument('--token', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    from .common import load_context
    context = load_context(Path(args.plan), args.plan_sha256, Path(args.authorization))
    ticket, job = validate_ticket(context, args.ticket, args.token, args.output)
    _save(Path(ticket['ticket_claim_path']), {'plan_sha256': context['plan_sha256'],
        'slot_id': ticket['slot_id'], 'job_id': job['id'], 'mode': ticket['mode'],
        'started_monotonic_s': time.monotonic(), 'pid': os.getpid()})
    wait_monitor_ready(context, ticket)
    from .common import verify_sources
    verify_sources(context['plan'])
    result = (run_method(context, job, Path(args.output)) if ticket['mode'] == 'method'
              else run_post(context, ticket, Path(args.output)))
    if ticket['mode'] == 'post': return 0 if result['post_state'] in ('SAFE', 'UNRESOLVED') else 2
    return 0 if result['execution_status'] in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'STATUS_UNRESOLVED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
