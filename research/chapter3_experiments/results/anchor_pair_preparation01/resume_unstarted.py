"""Append-only K151 cutoff audit; run only the never-started second call.

This adapter cannot rerun old_linked4, alter its claims/ledger, change the
174-source search, accept a late vector or create a late safe bound.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

PREP = Path(__file__).resolve().parent
HERE = PREP.parents[1]
sys.path.insert(0, str(HERE))
import run_anchor_pair as runner
from execution_status import classify_execution, DEADLINE_REASONS

OUT = runner.TARGET
PROTOCOL = 'K151-append-only-cutoff-audit-and-unstarted-call-v1'
BEFORE = OUT/'recovery_before/original_sha256.json'
CHECKS = PREP/'recovery_precheck01.json'
RECOVERY_CLAIM = OUT/'claims/remaining_recovery.json'
RECOVERY_RESULT = OUT/'recovery_result.json'
NORMAL = {'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT',
          'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}


def read(path):
    return runner.read(path)


def sha(path):
    return runner.sha(path)


def save_new(path, value):
    path = Path(path)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False,
                  allow_nan=False, default=str)
        stream.write('\n')


def _complete(request):
    return (request.get('latched_unresolved') is False
        and request.get('within_budget') is True
        and not request.get('failure_reasons')
        and request.get('callback_publications_complete') is True
        and request.get('expected_callback_numbers') == request.get('checked_callback_numbers'))


def _last_mapping(r, folder):
    """Map a single unfinished final augmented request to its exact scene round."""
    requests = (r.get('augmented_transport') or {}).get('requests', [])
    if not requests or _complete(requests[-1]):
        raise ValueError('No unfinished final augmented request')
    request = requests[-1]
    phases = r.get('phases')
    if not isinstance(phases, list) or not phases:
        raise ValueError('Missing phases')
    phase = phases[-1]
    scenes = phase.get('scenes')
    if not isinstance(scenes, dict) or not scenes:
        raise ValueError('Missing last phase scenes')
    sid, scene = list(scenes.items())[-1]
    rounds = (scene.get('solver_result') or {}).get('rounds')
    if not isinstance(rounds, list) or not rounds:
        raise ValueError('Missing last scene round')
    last_round = rounds[-1]
    if last_round.get('augmented_admission') != request:
        raise ValueError('Final scene and transport request identities differ')
    number = last_round.get('request_number')
    if type(number) is not int or number <= 0:
        raise ValueError('Missing final native request number')
    pyfile = Path(folder)/'matlab'/f'request_{number:06d}.python.json'
    if sorted((Path(folder)/'matlab').glob('request_*.python.json'))[-1] != pyfile:
        raise ValueError('A later native result exists')
    python = read(pyfile)
    metadata = read(pyfile.with_name(f'request_{number:06d}.input.json'))
    if python.get('request_number') != number or metadata.get('request_number') != number:
        raise ValueError('Native request numbers differ')
    scope = f'{sid}:round:{len(rounds)}'
    scopes = {scope, f"phase:{phase['phase_index']}:{scope}"}
    return request, python, metadata, scopes


def correct_records(job, r, declaration, folder, *, input_valid, source_valid, errors=None):
    """Pure saved-evidence classification; preserve every unrelated error and U.

    The only relaxation is that a cancel publication may occur after 300 s but
    no later than the recorded method stop.  It grants no candidate admission.
    """
    original = runner.result_records(job, r, declaration, folder,
        input_valid=input_valid, source_valid=source_valid, errors=errors)
    context = deepcopy(original['context'])
    audit = {'protocol': PROTOCOL, 'applied': False, 'removed_hard_records': [],
        'original_execution_status': original['execution']['execution_status'],
        'new_safe_evaluation': False, 'late_candidate_accepted': False}
    try:
        timing = r.get('timing') or {}
        elapsed = timing.get('method_elapsed_s')
        if not (r.get('budget_exhausted') is True and r.get('reason') == 'wall_time_limit'
            and timing.get('limit_s') == runner.SECONDS and runner.finite(elapsed)
            and elapsed >= runner.SECONDS
            and all(context.get(k) is True for k in ('input_identity_valid',
                'source_identity_valid', 'current_request_identity_valid'))
            and context.get('observed_numerical_rejection') is False
            and context.get('prior_requests_complete') is True
            and context.get('worker_isolation') == 'VERIFIED'):
            raise ValueError('Root cutoff, identities, prior completion, numeric or isolation not verified')
        request, python, metadata, scopes = _last_mapping(r, folder)
        cancel = request.get('cancel_published_at_s')
        reasons = request.get('failure_reasons')
        transient = set((python.get('publication_read') or {}).get('transient_read_errors') or {})
        start = (r.get('condition') or {}).get('budget_identity', {}).get('start')
        if not (request.get('cancel_requested') is True and runner.finite(cancel)
            and runner.SECONDS <= cancel <= elapsed
            and request.get('native_status') == 'BUDGET_EXHAUSTED'
            and request.get('within_budget') is False
            and python.get('status') == 'BUDGET_EXHAUSTED'
            and python.get('response_may_arrive_later') is True
            and python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == []
            and transient <= {'FileNotFoundError'}
            and isinstance(reasons, list) and bool(reasons)
            and all(isinstance(v, str) and v in DEADLINE_REASONS for v in reasons)
            and metadata.get('method_deadline_bound') is True
            and F(str(metadata['absolute_deadline'])) == F(start)+runner.SECONDS):
            raise ValueError('Final request has no complete matching root-cutoff rejection chain')
        hard = context['hard_errors']
        keep, removed = [], []
        fields = {'scope', 'reason', 'status', 'technical_state', 'error'}
        for item in hard:
            blank_cutoff = (isinstance(item, dict) and set(item) == fields
                and item['scope'] in scopes and item['status'] == 'BUDGET_EXHAUSTED'
                and all(item[k] is None for k in ('reason', 'technical_state', 'error')))
            (removed if blank_cutoff else keep).append(item)
        context['hard_errors'] = keep
        context['root_deadline_confirmed'] = True
        context['deadline_causal_trace'] = True
        context['completion_verified'] = False
        context['last_request'] = {'state': 'PENDING', 'pending_at_cutoff': True,
            'refuses_late_candidate': True, 'deadline_causal_trace': True,
            'deadline_reasons': reasons}
        execution = classify_execution(r, context)
        if execution.get('usable_U_J') != original.get('usable_U_J'):
            raise ValueError('Post-audit would change already formed safe U')
        audit.update(applied=True, removed_hard_records=removed,
            exact_request_scopes=sorted(scopes), cancel_published_at_s=cancel,
            method_stop_s=elapsed, method_deadline_bound=True,
            absolute_deadline=metadata['absolute_deadline'])
        return {**original, 'execution': execution, 'context': context,
                'usable_U_J': execution['usable_U_J'], 'cutoff_audit': audit}
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
        audit['not_applied_reason'] = str(exc)
        return {**original, 'cutoff_audit': audit}


def verify_original():
    """Verify immutable consumed state and every old artifact before proceeding."""
    declaration = runner.admission(OUT)
    manifest = read(BEFORE)
    if len(manifest) != 12:
        raise ValueError('Expected bound twelve-file original manifest')
    for name, expected in manifest.items():
        path = runner.GLOBAL_CLAIM if name == 'GLOBAL_CLAIM' else OUT/name
        if sha(path) != expected:
            raise ValueError('Original audit artifact changed: '+name)
    ledger = read(OUT/'ledger.json')
    if (ledger.get('state') != 'BLOCKED' or ledger.get('consumed') != 1
        or ledger.get('reserved_method_budget_s') != runner.SECONDS
        or [c.get('id') for c in ledger.get('calls', [])] != ['old_linked4']):
        raise ValueError('Original ledger is not exactly one consumed old call')
    old_job, new_job = runner.jobs()
    old_claim = read(OUT/'claims/old_linked4.json')
    old_row = read(OUT/'claims/old_linked4_result.json')
    global_claim = read(runner.GLOBAL_CLAIM)
    if (any(old_claim.get(k) != v for k, v in old_job.items())
        or old_claim.get('seconds') != 300 or old_claim.get('no_retry') is not True
        or old_row.get('id') != old_job['id'] or old_row.get('state') != 'BLOCKED'
        or old_row.get('errors') != [] or old_row.get('source_identity_valid') is not True
        or global_claim.get('protocol') != runner.PROTOCOL
        or global_claim.get('out') != OUT.relative_to(runner.REPO).as_posix()
        or global_claim.get('declaration_sha256') != sha(OUT/'declaration.json')
        or global_claim.get('no_retry') is not True):
        raise ValueError('Old consumed/global claim identity mismatch')
    for name, digest in read(OUT/'claims/old_linked4_artifact_sha256.json').items():
        if sha(OUT/'old_linked4'/name) != digest:
            raise ValueError('Old method artifact changed: '+name)
    if (OUT/new_job['id']).exists() or (OUT/'claims'/f"{new_job['id']}.json").exists():
        raise FileExistsError('Second method has already started')
    raw = read(OUT/'old_linked4/wrapper_raw_result.json')
    corrected = correct_records(old_job, raw, declaration, OUT/'old_linked4',
        input_valid=True, source_valid=True, errors=old_row['errors'])
    if (corrected['execution']['execution_status'] != 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
        or corrected['cutoff_audit']['applied'] is not True
        or corrected['usable_U_J'] != old_row['usable_U_J']):
        raise ValueError('Old record is not independently explained by root cutoff')
    return declaration, corrected, manifest


def precheck():
    """Saved-record mutations only, no solver/model/thermal execution."""
    from contextlib import ExitStack
    from unittest.mock import patch
    import tempfile
    import shutil
    import scipy.optimize, milp, thermal, scene_adapter, linked_method, matlab_bridge
    before = runner.source_gate()
    declaration, corrected, manifest = verify_original()
    base = read(OUT/'old_linked4/wrapper_raw_result.json')
    guards = {k: 0 for k in ('research', 'matlab', 'milp', 'linprog', 'model', 'thermal', 'scene', 'Popen')}
    def blocked(name):
        def fail(*a, **kw):
            guards[name] += 1
            raise AssertionError('Forbidden pure-audit entry: '+name)
        return fail
    cases = []
    def trial(name, mutate=None, *, input_valid=True, source_valid=True, errors=None, accepted=False):
        result = deepcopy(base)
        fixture_root = runner.REPO/'.runtime/k151_recovery_fixtures'
        fixture_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=fixture_root) as folder:
            folder = Path(folder)
            (folder/'matlab').mkdir()
            for name_ in ('closed.json', 'request_000004.python.json', 'request_000004.input.json'):
                shutil.copyfile(OUT/'old_linked4/matlab'/name_, folder/'matlab'/name_)
            if mutate:
                mutate(result, folder)
            rec = correct_records(runner.jobs()[0], result, declaration, folder,
                input_valid=input_valid, source_valid=source_valid, errors=errors)
        good = rec['execution']['execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
        cases.append({'name': name, 'passed': good is accepted,
            'status': rec['execution']['execution_status'], 'audit': rec['cutoff_audit'],
            'U_unchanged': rec['usable_U_J'] == corrected['usable_U_J']})
        if good is not accepted:
            raise AssertionError(name+' classification unexpectedly '+rec['execution']['execution_status'])
    def modify_request(key, value):
        def apply(r, folder):
            request = r['augmented_transport']['requests'][-1]
            request[key] = value
            r['phases'][-1]['scenes']['AC_offset_0ms']['solver_result']['rounds'][-1]['augmented_admission'] = deepcopy(request)
        return apply
    def modify_file(name, key, value):
        def apply(r, folder):
            path = folder/'matlab'/name
            item = read(path);item[key] = value
            path.write_text(json.dumps(item), encoding='utf-8')
        return apply
    with ExitStack() as stack:
        for obj, attr, label in ((linked_method, 'execute_linked_fixed_unit_opp_start','research'),
            (matlab_bridge.MatlabSession,'__init__','matlab'),(scipy.optimize,'milp','milp'),
            (scipy.optimize,'linprog','linprog'),(milp,'build_model','model'),
            (thermal,'evaluate_piecewise','thermal'),(scene_adapter,'evaluate_piecewise','scene')):
            stack.enter_context(patch.object(obj, attr, side_effect=blocked(label)))
        stack.enter_context(patch('subprocess.Popen', side_effect=blocked('Popen')))
        trial('actual_cancel_after_300_and_at_method_stop', accepted=True)
        trial('cancel_before_root_cutoff_rejected', modify_request('cancel_published_at_s',299.999))
        trial('cancel_after_method_stop_rejected', modify_request('cancel_published_at_s',300.017))
        trial('real_error_preserved', errors=[{'scope':'AC_offset_0ms:round:1','error':'real I/O fault'}])
        trial('input_identity_rejected', input_valid=False)
        trial('source_identity_rejected', source_valid=False)
        trial('prior_request_incomplete_rejected', lambda r,f:r['augmented_transport']['requests'][0].update(latched_unresolved=True))
        trial('numeric_report_rejection_preserved', lambda r,f:r['augmented_transport']['requests'][0]['numerical_checks'][0]['report'].update(accepted=False))
        trial('unknown_deadline_reason_rejected', modify_request('failure_reasons',['UNKNOWN_FAILURE']))
        trial('late_vector_cannot_be_accepted', modify_file('request_000004.python.json','x',[1]))
        trial('wrong_absolute_deadline_rejected', modify_file('request_000004.input.json','absolute_deadline',1))
        trial('unbound_method_deadline_rejected', modify_file('request_000004.input.json','method_deadline_bound',False))
    passed = all(c['passed'] for c in cases) and not any(guards.values()) and before == runner.source_gate()
    record = {'protocol': PROTOCOL, 'passed': passed, 'cases': cases,
        'source_sha256': before, 'adapter_sha256': sha(__file__),
        'original_manifest_sha256': sha(BEFORE),
        'recovery_protocol_sha256': sha(PREP/'recovery_protocol.md'),
        'blocked_calls': guards, 'research_calls':0,'native_calls':0,
        'physical_models':0,'thermal_evaluations':0,'completed_at_utc':runner.now()}
    save_new(CHECKS, record)
    print(json.dumps({'passed':passed, 'cases':len(cases), 'checks':str(CHECKS)}), flush=True)
    return passed


def run(*, execution_authorized=False):
    if execution_authorized is not True:
        raise PermissionError('Original user execution authorization flag required')
    if RECOVERY_CLAIM.exists() or RECOVERY_RESULT.exists() or (OUT/'corrected_old_record.json').exists():
        raise FileExistsError('Recovery already consumed; no restart')
    gate = read(CHECKS)
    if (gate.get('protocol') != PROTOCOL or gate.get('passed') is not True
        or gate.get('adapter_sha256') != sha(__file__)
        or gate.get('source_sha256') != runner.source_gate()
        or gate.get('original_manifest_sha256') != sha(BEFORE)
        or gate.get('recovery_protocol_sha256') != sha(PREP/'recovery_protocol.md')
        or not gate.get('cases') or not all(c.get('passed') is True for c in gate['cases'])
        or any(gate.get('blocked_calls', {'missing':1}).values())
        or any(gate.get(k) != 0 for k in ('research_calls','native_calls','physical_models','thermal_evaluations'))):
        raise ValueError('Matching pure-recovery precheck missing or changed')
    declaration, corrected, manifest = verify_original()
    save_new(OUT/'corrected_old_record.json', corrected)
    job = runner.jobs()[1]
    claim = {'protocol':PROTOCOL, **job, 'claimed_at_utc':runner.now(),
        'method_seconds':300, 'original_consumed_calls':1,
        'cumulative_consumed_calls_after_claim':2, 'cumulative_reserved_method_s':600,
        'old_rerun':False, 'no_retry':True, 'source_sha256':runner.source_gate(),
        'adapter_sha256':sha(__file__), 'checks_sha256':sha(CHECKS),
        'original_manifest_sha256':sha(BEFORE),
        'recovery_protocol_sha256':sha(PREP/'recovery_protocol.md')}
    save_new(RECOVERY_CLAIM, claim)
    result, identity, errors = None, {'input_verified':None}, []
    start = time.monotonic()
    try:
        # execute starts its own fresh absolute 300-second method clock.
        result, identity = runner.execute(job, OUT, declaration, runner.entry_points())
    except BaseException:
        errors.append(traceback.format_exc())
    returned = time.monotonic()-start
    source_valid = True
    try:
        runner.admission(OUT)
        for name, expected in manifest.items():
            path = runner.GLOBAL_CLAIM if name == 'GLOBAL_CLAIM' else OUT/name
            if sha(path) != expected:
                raise ValueError('Original record mutated during new execution: '+name)
    except Exception:
        source_valid = False;errors.append(traceback.format_exc())
    folder = OUT/job['id']
    if isinstance(result, dict):
        save_new(folder/'wrapper_raw_result.json', result)
    try:
        records = correct_records(job, result, declaration, folder,
            input_valid=identity['input_verified'], source_valid=source_valid, errors=errors)
    except Exception:
        errors.append(traceback.format_exc())
        records = {'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},
                   'usable_U_J':None, 'record_errors':errors}
    okay = records['execution']['execution_status'] in NORMAL
    row = {**job, 'state':'COMPLETED' if okay else 'BLOCKED',
        'errors':errors, 'completed_at_utc':runner.now(),
        'method_return_inclusive_wall_s':returned, 'source_identity_valid':source_valid, **records}
    save_new(OUT/'claims/anchor_linked4_result.json', row)
    artifacts = {p.relative_to(folder).as_posix():sha(p)
                 for p in sorted(folder.rglob('*')) if p.is_file()} if folder.exists() else {}
    save_new(OUT/'claims/anchor_linked4_artifact_sha256.json', artifacts)
    saved = {'protocol':PROTOCOL,'completed':okay,'completed_at_utc':runner.now(),
        'cumulative_consumed_calls':2,'cumulative_reserved_method_budget_s':600,
        'old_rerun':False,'original_ledger_unchanged':source_valid,
        'old_execution_status':corrected['execution']['execution_status'],
        'old_usable_U_J':corrected['usable_U_J'],
        'new_execution_status':records['execution']['execution_status'],
        'new_usable_U_J':records.get('usable_U_J'),'new_method_return_wall_s':returned,
        'original_manifest_sha256':sha(BEFORE),
        'claim_sha256':sha(RECOVERY_CLAIM),
        'new_result_sha256':sha(OUT/'claims/anchor_linked4_result.json'),
        'new_artifact_manifest_sha256':sha(OUT/'claims/anchor_linked4_artifact_sha256.json'),
        'no_retry':True}
    save_new(RECOVERY_RESULT, saved)
    print(json.dumps(saved), flush=True)
    return okay


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--precheck',action='store_true')
    mode.add_argument('--run',action='store_true')
    parser.add_argument('--execution-authorized',action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if (precheck() if args.precheck else
        run(execution_authorized=args.execution_authorized)) else 1)
