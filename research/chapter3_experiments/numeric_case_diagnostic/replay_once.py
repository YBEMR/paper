"""One archived full-domain MILP replay for native stage logs; no new model or heat."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCIENCE = REPO / 'research/chapter3_experiments'
OLD = SCIENCE / 'results/natural_full_execution01/slots/whole_milp__method/worker/method/matlab'
OUT = SCIENCE / 'results/natural_full_numeric_replay01'
PRECHECK = SCIENCE / 'results/natural_full_numeric_precheck01.json'
ENTRY_FILE = Path(__file__).resolve()
REPRESENTATION = 'original_binary64_rows'
EQUALITY_REPRESENTATION = 'exact_opposite_rows_to_equalities_v1'
EQUALITY_HELPER = HERE / 'exact_equalities.py'
CONTROL = SCIENCE / 'results/fixed_integer_native03/source_snapshot/run_once.py'
CORE = SCIENCE / 'results/fixed_integer_native03/source_snapshot/core.py'
PLAN = SCIENCE / 'results/natural_full_preparation01/plan.json'
USER_REQUEST = '那你继续查清这个数值异常，先利用已保存的初始点、矩阵和求解记录定位根因，必要时做最小修复。不要靠删合法选项或调参凑结果，也不要扩展新实例，重点把这个实例的MILP求解问题解决。'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load_module('natural_numeric_frozen_control', CONTROL)
read, sha, write_new = common.read, common.sha, common.write_new


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO).decode('utf-8').strip()


def bindings():
    paths = source_entries() + [CONTROL, CORE, PLAN,
             SCIENCE / 'matlab_bridge.py', SCIENCE / 'solve_model.m',
             OLD / 'request_000001.mat', OLD / 'request_000001.native.mat',
             OLD / 'request_000001.response.json', OLD / 'ready.json']
    plan = read(PLAN)
    paths.append(Path(plan['native_executable']))
    return {str(p.resolve()): sha(p) for p in paths}


def source_entries():
    paths = [Path(__file__).resolve(), ENTRY_FILE, HERE / 'solve_model.m']
    if REPRESENTATION == EQUALITY_REPRESENTATION:
        paths.append(EQUALITY_HELPER)
    elif REPRESENTATION != 'original_binary64_rows':
        raise ValueError('Unrecognized fixed representation')
    return list(dict.fromkeys(paths))


def allowed_array_changes():
    return [] if REPRESENTATION == 'original_binary64_rows' else ['A', 'b', 'Aeq', 'beq']


def represented_payload(original):
    if REPRESENTATION == 'original_binary64_rows':
        return original, None, {}
    if REPRESENTATION != EQUALITY_REPRESENTATION:
        raise ValueError('Unrecognized fixed representation')
    helper = load_module('natural_exact_equalities', EQUALITY_HELPER)
    transformed, certificate = helper.transform(original)
    checks = helper.verify_equivalence(original, transformed, certificate)
    return transformed, certificate, checks


def bind_controller():
    # K191 uses these same runtime bindings; immutable controller bytes remain intact.
    common.REPO = REPO
    common.OUT = OUT
    common.admission = admission
    common.__file__ = str(ENTRY_FILE)
    return common


def bind_bridge():
    bridge = load_module('natural_numeric_original_bridge', SCIENCE / 'matlab_bridge.py')
    bridge.REPO = REPO
    bridge.HERE = HERE  # isolated solve_model.m differs only in Display
    return bridge


def identical_arrays(original, other, core):
    for key in core.KEYS:
        checker = core._same_matrix if key in ('A', 'Aeq') else core._same_array
        if not checker(original[key], other[key]):
            raise ValueError('Archived payload changed: ' + key)
    return True


def method_budget(launch, clock=time.monotonic):
    budget = common.RootBudget(clock=clock)
    origin = launch['calendar_start']
    if isinstance(origin, bool) or not isinstance(origin, (int, float)) or not math.isfinite(origin) or origin > budget.start:
        raise ValueError('Invalid parent origin')
    budget.start = float(origin)
    budget.deadline = budget.start + 300
    budget.check()
    return budget


def precheck():
    """Only saved-array arithmetic and source checks; never native or heat calls."""
    start = time.monotonic()
    import numpy as np
    from scipy.io import loadmat
    core = load_module('natural_numeric_saved_arrays', CORE)
    bridge = bind_bridge()
    original, receipt = core.load_original_mat(OLD / 'request_000001.mat')
    again, _ = core.load_original_mat(OLD / 'request_000001.mat')
    native_x0 = loadmat(OLD / 'request_000001.native.mat', variable_names=['initialPoint'])['initialPoint'].reshape(-1)
    original_admission = bridge._prepare(original, x0=original['x0'])['x0_validation']
    represented, certificate, equivalence = represented_payload(original)
    prepared = bridge._prepare(represented, x0=original['x0'])
    original_script = (SCIENCE / 'solve_model.m').read_bytes()
    expected_script = original_script.replace(b"'Display','off'", b"'Display','iter'")
    bound = bind_controller()
    plan = read(PLAN)
    archive = read(SCIENCE / 'results/natural_full_execution01/archive_checks.json')['files_sha256']
    root = method_budget({'calendar_start': 10.0}, clock=lambda: 20.0)
    checks = {
        'source_script_has_one_display_setting': original_script.count(b"'Display','off'") == 1,
        'isolated_script_only_changes_display': (HERE / 'solve_model.m').read_bytes() == expected_script,
        'all_original_payload_arrays_bitwise_unchanged': identical_arrays(original, again, core),
        'native_received_x0_bitwise_identical': core._same_array(original['x0'], native_x0),
        'integer_coordinates_unchanged': np.array_equal(prepared['intcon'], original['intcon'] + 1),
        'exported_matrix_arrays_match_expected_representation': all(core._same_matrix(prepared[k], represented[k]) for k in ('A', 'Aeq')),
        'exported_vectors_match_expected_representation': all(core._same_array(prepared[k], represented[k]) for k in ('c', 'b', 'beq', 'lb', 'ub', 'x0')),
        'original_variable_domain_objective_and_x0_unchanged': all(core._same_array(represented[k], original[k]) for k in ('c', 'lb', 'ub', 'intcon', 'x0')),
        'original_x0_numerically_admitted': original_admission['accepted_numerically'],
        'represented_x0_numerically_admitted': prepared['x0_validation']['accepted_numerically'],
        'controller_output_and_worker_bound': bound.OUT == OUT and bound.__file__ == str(ENTRY_FILE) and bound.admission is admission,
        'unchanged_controller_limits': (bound.SECONDS, bound.CALENDAR, bound.WATCHDOG) == (300, 480, 420),
        'parent_origin_counts_prior_preparation_and_imports': root.start == 10 and root.deadline == 310 and root.remaining == 290,
        'original_native_executable_unchanged': sha(plan['native_executable']) == plan['native_executable_sha256'],
        'historical_MAT_and_native_MAT_hashes_match': all(sha(OLD / name) == archive[(OLD / name).relative_to(REPO).as_posix()] for name in ('request_000001.mat', 'request_000001.native.mat')),
    }
    if not all(checks.values()):
        raise ValueError('Pure precheck failed: ' + str(checks))
    return dict(passed=True, checks=checks, payload=receipt, representation=REPRESENTATION,
        representation_certificate=certificate, representation_verification=equivalence,
        original_x0_admission=original_admission, x0_admission=prepared['x0_validation'],
        wall_seconds=time.monotonic() - start, native_calls=0, model_builds=0,
        thermal_calls=0, scope='saved arrays and source only; not execution authorization')


def prepare():
    if OUT.exists():
        raise FileExistsError('Never overwrite or reuse the diagnostic output/claim')
    subject = git('rev-parse', 'HEAD')
    for path in source_entries():
        relative = path.relative_to(REPO).as_posix()
        committed = subprocess.check_output(['git', 'show', subject + ':' + relative], cwd=REPO)
        if committed != path.read_bytes():
            raise ValueError('Commit the reviewed replay source before preparing: ' + relative)
    checks = precheck()
    certificate = checks.pop('representation_certificate')
    certificate_sha256 = None
    if certificate is not None:
        write_new(OUT / 'representation_certificate.json', certificate)
        certificate_sha256 = sha(OUT / 'representation_certificate.json')
    declaration = dict(protocol='natural-full-bounded-native-diagnostic-v2',
        authorized=True, authorization_source='USER_CURRENT_CONVERSATION',
        user_request=USER_REQUEST, subject_commit=subject,
        budget_basis='本轮诊断的执行上限，沿用会话既有每次300秒上限；不伪称用户新增数额答复。',
        method_seconds=300, calendar_seconds=480, worker_watchdog_seconds=420,
        cleanup_seconds_max=40, native_requests_max=1, thermal_post_calls_max=0,
        no_retry=True, no_new_SAFE_or_U=True, no_auto_followup=True,
        not_an_external_agent_loop_review=True, bindings=bindings(),
        representation=REPRESENTATION, representation_certificate_sha256=certificate_sha256,
        allowed_array_changes=allowed_array_changes(), allowed_option_changes=['Display: off -> iter', 'MaxTime: original root remaining'],
        original_options=read(OLD / 'request_000001.response.json')['options'],
        original_ready=read(OLD / 'ready.json'), created_utc=common.now())
    write_new(OUT / 'declaration.json', declaration)
    checks['declaration_sha256'] = sha(OUT / 'declaration.json')
    write_new(OUT / 'pure_checks.json', checks)
    print(json.dumps({'prepared': True, 'subject_commit': subject, 'declaration_sha256': checks['declaration_sha256']}, ensure_ascii=False))


def admission():
    declaration = read(OUT / 'declaration.json')
    if not declaration['authorized'] or declaration['user_request'] != USER_REQUEST:
        raise ValueError('Diagnostic authorization mismatch')
    if (declaration['method_seconds'], declaration['calendar_seconds'], declaration['native_requests_max'], declaration['thermal_post_calls_max']) != (300, 480, 1, 0):
        raise ValueError('Diagnostic limit mismatch')
    if not declaration['no_retry'] or declaration['allowed_array_changes'] != allowed_array_changes() or declaration['representation'] != REPRESENTATION:
        raise ValueError('Scope mismatch')
    certificate_digest = declaration['representation_certificate_sha256']
    if REPRESENTATION == EQUALITY_REPRESENTATION:
        if sha(OUT / 'representation_certificate.json') != certificate_digest:
            raise ValueError('Frozen exact-equivalence certificate drift')
    elif certificate_digest is not None:
        raise ValueError('Unexpected representation certificate')
    if git('rev-parse', 'HEAD') != declaration['subject_commit']:
        raise ValueError('Diagnostic subject drift')
    if bindings() != declaration['bindings']:
        raise ValueError('Frozen source or numerical payload drift')
    return declaration


def check_options(actual, original, max_time):
    expected = dict(original)
    expected['Display'] = 'iter'
    expected.pop('MaxTime', None)
    measured = dict(actual)
    limit = measured.pop('MaxTime', None)
    if measured != expected or not isinstance(limit, (int, float)) or isinstance(limit, bool) or not (0 < limit <= max_time):
        raise ValueError('Effective native options differ beyond Display/remaining MaxTime')
    return True


def worker():
    bind_controller()
    launch = read(OUT / 'launch.claim.json')
    budget = method_budget(launch)  # parent origin counts preparation and Python imports
    if launch['declaration_sha256'] != sha(OUT / 'declaration.json'):
        raise ValueError('Controller launch binding missing or stale')
    write_new(OUT / 'method.claim.json', dict(utc=common.now(), start=budget.start,
        deadline=budget.deadline, method_seconds=300, declaration_sha256=launch['declaration_sha256'],
        clock_origin='parent calendar_start before admission, host checks and child imports', no_retry=True))
    session = bridge = None
    result = numeric = cleanup = None
    errors, events = [], []
    state, options_match = 'NOT_COMPLETED', False
    try:
        declaration = admission()
        host = common.context()
        write_new(OUT / 'worker_host.json', host)
        if not common.resource_ok(host):
            raise RuntimeError('Original host/resource gate failed')
        core = load_module('natural_numeric_worker_arrays', CORE)
        bridge = bind_bridge()
        with budget.phase('saved_payload_load_and_numerical_admission'):
            original, receipt = core.load_original_mat(OLD / 'request_000001.mat')
            original_admission = bridge._prepare(original, x0=original['x0'])['x0_validation']
            represented, certificate, equivalence = represented_payload(original)
            if certificate is not None and certificate != read(OUT / 'representation_certificate.json'):
                raise ValueError('Runtime representation differs from frozen proof')
            prepared = bridge._prepare(represented, x0=original['x0'])
            write_new(OUT / 'input_precheck.json', dict(payload=receipt,
                original_x0=original_admission, represented_x0=prepared['x0_validation'],
                representation=REPRESENTATION, representation_verification=equivalence,
                representation_certificate_sha256=declaration['representation_certificate_sha256']))
        with budget.phase('MATLAB_startup'):
            session = bridge.MatlabSession(OUT / 'matlab', total_budget_s=budget.remaining,
                budget=budget, cut_max_iterations=10)
            for key in ('version', 'release', 'intlinprog_path'):
                if session.environment.get(key) != declaration['original_ready'].get(key):
                    raise ValueError('Native environment drift: ' + key)
        seen = set()
        def observe(prefix):
            for path in sorted(prefix.parent.glob(prefix.name + '.event_*.json')):
                if path.name in seen or budget.remaining <= 0:
                    continue
                try:
                    event = read(path)
                except (ValueError, PermissionError):
                    continue
                seen.add(path.name)
                events.append(dict(file=path.name, received_s=budget.elapsed, state=event.get('state'), values=event.get('values')))
        session.event_consumer = observe
        admission()
        budget.check()
        write_new(OUT / 'request.claim.json', dict(utc=common.now(), root_s=budget.elapsed,
            request_number=1, representation=REPRESENTATION,
            original_variable_domain_unchanged=True, Display='iter'))
        result = session.solve(represented, remaining_s=budget.remaining, budget=budget, x0=original['x0'])
        budget.check()
        with budget.phase('actual_transport_identity'):
            sent, sent_receipt = core.load_original_mat(OUT / 'matlab/request_000001.mat')
            identity = identical_arrays(represented, sent, core)
            write_new(OUT / 'transport_identity.json', dict(passed=identity, sent=sent_receipt,
                matches_expected_representation=True, representation=REPRESENTATION,
                original_variable_domain_unchanged=True))
        if result.get('options'):
            request = read(OUT / 'matlab/request_000001.request.json')
            options_match = check_options(result['options'], declaration['original_options'], request['remaining_s'])
        budget.check()
        if result.get('x') and result.get('budget_valid') and options_match:
            with budget.phase('returned_vector_original_rows'):
                checked = bridge._prepare(original, x0=result['x'])
                numeric = checked['x0_validation']
                represented_check = bridge._prepare(represented, x0=result['x'])['x0_validation']
                numeric['represented_rows_admission'] = represented_check
                numeric['original_all_inequality_rows_checked'] = original['A'].shape[0]
                difference = abs(numeric['initial_objective'] - float(result['fval']))
                if difference > 1e-9 * max(1.0, abs(numeric['initial_objective'])):
                    raise ValueError('Returned fval differs from original objective')
                numeric['fval_absolute_difference'] = difference
                budget.check()
                numeric['completed_at_root_s'] = budget.elapsed
        if result.get('exitflag') == -2:
            state = ('ORIGINAL_NUMERICAL_CONFLICT_REPRODUCED' if REPRESENTATION == 'original_binary64_rows'
                     else 'EQUIVALENT_REPRESENTATION_NUMERICAL_CONFLICT')
        elif numeric:
            state = 'ORIGINAL_ROWS_NUMERICALLY_ADMITTED'
        else:
            state = 'NATIVE_UNRESOLVED_NO_VECTOR'
        if not options_match:
            raise ValueError('No matched effective native options')
        budget.check()
    except BaseException as error:
        cleanup = getattr(error, 'matlab_cleanup', None)
        state = 'LATE_OR_TIMEOUT_UNRESOLVED' if isinstance(error, TimeoutError) else 'TECHNICAL_FAILURE'
        errors.append(dict(type=type(error).__name__, traceback=traceback.format_exc()))
    finally:
        stopped = budget.elapsed
        if session is not None:
            try:
                session.close()
                cleanup = session.cleanup
            except BaseException:
                errors.append(dict(type='CLEANUP_ERROR', traceback=traceback.format_exc()))
        lifecycle_complete = None
        if bridge is not None and (session is not None or cleanup is not None):
            lifecycle_complete = bridge.cleanup_is_complete(cleanup)
            if not lifecycle_complete:
                errors.append(dict(type='CLEANUP_UNRESOLVED'))
        try:
            admission()
            preserved = True
        except BaseException:
            preserved = False
            errors.append(dict(type='SOURCE_DRIFT', traceback=traceback.format_exc()))
        write_new(OUT / 'method_return.json', dict(state=state, result=result, numeric=numeric,
            representation=REPRESENTATION,
            method_elapsed_s=stopped, wall_including_cleanup_s=budget.elapsed, phases=budget.records,
            options_match_except_display_and_time=options_match, events=events, cleanup=cleanup,
            lifecycle_complete=lifecycle_complete, sources_preserved=preserved, errors=errors,
            request_attempts=0 if session is None else session.counter,
            thermal_integrations=0, new_SAFE_or_U=False, no_retry=True))
    return 2 if errors else 0


def execute():
    return bind_controller().execute()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('precheck', 'prepare', 'execute', 'worker', 'context'))
    action = parser.parse_args().action
    if action == 'precheck':
        checks = precheck()
        write_new(PRECHECK, checks)
        print(json.dumps({'passed': checks['passed'], 'checks': len(checks['checks']), 'native_calls': 0}))
    elif action == 'context':
        print(json.dumps(bind_controller().context()))
    else:
        return {'prepare': prepare, 'execute': execute, 'worker': worker}[action]() or 0


if __name__ == '__main__':
    raise SystemExit(main() or 0)
