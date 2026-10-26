"""K189: execute the approved K188 fixed-intcon diagnostic exactly once."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / 'research/chapter3_experiments/results/fixed_integer_native01'
OLD = REPO / 'research/chapter3_experiments/results/whole_long_budget01'
PROPOSAL = REPO / 'research/chapter3_experiments/results/k188_readonly01/protocol_proposal.json'
FROZEN = OLD / 'source_snapshot/research/chapter3_experiments'
SECONDS, CALENDAR, WATCHDOG = 300, 480, 420


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


class RootBudget:
    """Transport-compatible deadline starting before scientific imports."""
    def __init__(self, seconds=SECONDS, clock=time.monotonic):
        self.clock = clock
        self.start = clock()
        self.seconds = float(seconds)
        self.deadline = self.start + self.seconds
        self.records = []

    @property
    def elapsed(self):
        return self.clock() - self.start

    @property
    def remaining(self):
        return max(0.0, self.deadline - self.clock())

    def check(self):
        if self.clock() >= self.deadline:
            raise TimeoutError('original 300-second diagnostic root exhausted')

    @contextmanager
    def phase(self, name):
        self.check()
        start = self.elapsed
        try:
            yield
        finally:
            self.records.append({'phase': name, 'start_s': start, 'end_s': self.elapsed})


def context():
    """Read-only host/memory inventory; does not start MATLAB."""
    import psutil
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    a = ctypes.WinDLL('advapi32', use_last_error=True)
    a.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    a.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]
    k.GetCurrentProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    token, flag, size = w.HANDLE(), w.DWORD(), w.DWORD()
    if not a.OpenProcessToken(k.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError()
    try:
        if not a.GetTokenInformation(token, 29, ctypes.byref(flag), ctypes.sizeof(flag), ctypes.byref(size)):
            raise ctypes.WinError()
    finally:
        k.CloseHandle(token)
    class Memory(ctypes.Structure):
        _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [(n, ctypes.c_ulonglong) for n in
            ('total_phys', 'avail_phys', 'total_page', 'avail_page', 'total_virtual', 'avail_virtual', 'avail_extended')]
    mem = Memory()
    mem.length = ctypes.sizeof(mem)
    if not k.GlobalMemoryStatusEx(ctypes.byref(mem)):
        raise ctypes.WinError()
    processes = [p.info for p in psutil.process_iter(['name', 'pid', 'create_time'])
                 if (p.info['name'] or '').lower() == 'matlab.exe']
    return dict(utc=now(), token_is_appcontainer=bool(flag.value), python=sys.executable,
        pid=os.getpid(), temp=os.environ.get('TEMP'), physical_available_bytes=mem.avail_phys,
        commit_available_bytes=mem.avail_page, disk_free_bytes=shutil.disk_usage(REPO).free,
        matlab_processes=processes)


def resource_ok(host):
    return (not host['token_is_appcontainer'] and not host['matlab_processes']
        and host['physical_available_bytes'] >= 2 * 1024**3
        and host['commit_available_bytes'] >= 4 * 1024**3
        and host['disk_free_bytes'] >= 2 * 1024**3)


def prepare():
    if OUT.exists():
        raise FileExistsError('Preparation already exists; never overwrite or reuse')
    p = read(PROPOSAL)
    for name, info in p['source_files'].items():
        if sha(REPO / name) != info['sha256']:
            raise ValueError('Original source drift: ' + name)
    sources = {x.name: sha(x) for x in sorted(HERE.iterdir()) if x.suffix in ('.py', '.md')}
    declaration = dict(protocol='K189-execution-of-K188-fixed-intcon-original-objective-v1',
        authorized=True, authorization='Explicit user message: execute K188 once, 300s root, 480s calendar, no heat/retry/extension',
        authorization_utc=now(), proposal_sha256=sha(PROPOSAL), source_files=p['source_files'],
        wrapper_sha256=sources, method_seconds=SECONDS, native_requests_max=1,
        thermal_post_calls_max=0, calendar_seconds=CALENDAR, worker_watchdog_seconds=WATCHDOG,
        cleanup_seconds_max=40, frozen_at_utc=now(), numerical_version=p['transformation']['numerical_version'],
        objective='original c', actual_intcon_only=True,
        root_origin='before scientific imports and archived input read',
        runtime_path_binding='frozen bridge HERE unchanged; only REPO restores original MATLAB prefs directory',
        original_ready=read(OLD / 'method/matlab/ready.json'),
        original_python_environment=read(OLD / 'pure_checks.json')['environment'],
        original_options=read(OLD / 'method/matlab/request_000001.response.json')['options'],
        minimum_resources={'physical_GiB': 2, 'commit_GiB': 4, 'disk_GiB': 2},
        no_new_safe_or_U=True, no_retry=True)
    write_new(OUT / 'declaration.json', declaration)
    for name in sources:
        target = OUT / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / name, target)
    (OUT / '.gitattributes').write_bytes(b'* -text\n')
    print(json.dumps({'prepared': True, 'declaration_sha256': sha(OUT / 'declaration.json')}))


def admission():
    d = read(OUT / 'declaration.json')
    if not d['authorized'] or (d['method_seconds'], d['native_requests_max'], d['calendar_seconds'], d['thermal_post_calls_max']) != (300, 1, 480, 0):
        raise ValueError('Authorization or budget drift')
    if sha(PROPOSAL) != d['proposal_sha256']:
        raise ValueError('Original proposal drift')
    for name, info in d['source_files'].items():
        if sha(REPO / name) != info['sha256']:
            raise ValueError('Original source drift: ' + name)
    for name, digest in d['wrapper_sha256'].items():
        if sha(HERE / name) != digest or sha(OUT / 'source_snapshot' / name) != digest:
            raise ValueError('Execution wrapper drift: ' + name)
    return d


def bind_bridge():
    spec = importlib.util.spec_from_file_location('k189_frozen_bridge', FROZEN / 'matlab_bridge.py')
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    bridge.REPO = REPO
    return bridge


def check_python_environment(expected):
    import platform
    import numpy
    import scipy
    import mpmath
    actual = dict(python=sys.version, platform=platform.platform(), numpy=numpy.__version__,
                  scipy=scipy.__version__, mpmath=mpmath.__version__)
    mismatches = {k: {'expected': expected[k], 'actual': actual.get(k)} for k in actual
                  if k in expected and expected[k] != actual.get(k)}
    if mismatches:
        raise ValueError('Python environment drift: ' + str(mismatches))
    return actual


def classify(result, numeric, within_budget, options_match):
    if not within_budget or not result.get('budget_valid', False):
        return 'UNRESOLVED_BUDGET_OR_LATE'
    if not options_match:
        return 'NATIVE_OPTIONS_DRIFT'
    if result.get('exitflag') == -2:
        return 'NUMERICAL_ADMISSION_STATUS_CONFLICT'
    if result.get('status') != 'SOLVED':
        return 'TECHNICAL_OR_NATIVE_UNRESOLVED'
    if not result.get('x'):
        return 'UNRESOLVED_EMPTY_NATIVE_VECTOR'
    if numeric and numeric.get('accepted'):
        return 'FIXED_CONFIGURATION_NUMERICALLY_ADMITTED'
    return 'NUMERICAL_VECTOR_REJECTED'


def worker():
    # First scientific clock, before loading numpy/scipy, bridge or input.
    budget = RootBudget()
    if not (OUT / 'launch.claim.json').exists():
        raise RuntimeError('Controller claim missing; direct worker execution prohibited')
    launch = read(OUT / 'launch.claim.json')
    if launch['declaration_sha256'] != sha(OUT / 'declaration.json'):
        raise ValueError('Launch identity drift')
    write_new(OUT / 'method.claim.json', dict(utc=now(), start=budget.start, deadline=budget.deadline,
        seconds=SECONDS, declaration_sha256=launch['declaration_sha256'], no_retry=True))
    session, bridge = None, None
    result, numeric, cleanup = None, None, None
    errors, events = [], []
    state, options_match, admitted_at = 'NOT_COMPLETED', False, None
    phase_markers = {}
    try:
        d = admission()
        host = context()
        write_new(OUT / 'worker_host.json', host)
        if not resource_ok(host):
            raise RuntimeError('Worker host/resource gate failed; no MATLAB request')
        import core
        bridge = bind_bridge()
        environment = check_python_environment(d['original_python_environment'])
        write_new(OUT / 'python_environment.json', environment)
        budget.check()
        with budget.phase('load_and_fix_original_integer_options'):
            original, loaded = core.load_original_mat(OLD / 'method/matlab/request_000001.mat')
            original_key = (OLD / 'method/matlab/request_000001.mat').relative_to(REPO).as_posix()
            if loaded['sha256'] != d['source_files'][original_key]['sha256']:
                raise ValueError('Loaded original MAT identity drift')
            fixed, transform = core.fix_actual_intcon(original)
            identity = core.assert_only_fixed_integer_bounds_changed(original, fixed)
            initial = core.verify_vector(original['x0'], original, fixed, require_objective=False)
            if not initial['accepted']:
                raise ValueError('Original x0 failed fixed numerical admission')
            write_new(OUT / 'input_precheck.json', dict(load=loaded, transform=transform, identity=identity, initial=initial))
        budget.check()
        phase_markers['pre_native_ready_s'] = budget.elapsed
        with budget.phase('MATLAB_startup'):
            session = bridge.MatlabSession(OUT / 'matlab', total_budget_s=budget.remaining,
                budget=budget, cut_max_iterations=10)
            for key in ('version', 'release', 'intlinprog_path'):
                if session.environment.get(key) != d['original_ready'].get(key):
                    raise ValueError('Native environment drift: ' + key)
        seen = set()
        def observer(prefix):
            # Original callback files are retained. No candidate decoding or thermal work.
            for path in sorted(prefix.parent.glob(prefix.name + '.event_*.json')):
                if path.name in seen or budget.remaining <= 0:
                    continue
                try:
                    event = read(path)
                except (ValueError, PermissionError):
                    continue
                seen.add(path.name)
                events.append(dict(file=path.name, received_s=budget.elapsed, kind=event.get('kind'),
                    callback_state=event.get('state'), values=event.get('values'),
                    returned_vector_length=len(event.get('x') or [])))
        session.event_consumer = observer
        admission()
        budget.check()
        write_new(OUT / 'request.claim.json', dict(utc=now(), root_s=budget.elapsed,
            original_integer_fixed_only=True, original_objective=True, request_number=1))
        phase_markers['native_request_call_s'] = budget.elapsed
        result = session.solve(fixed, remaining_s=budget.remaining, budget=budget, x0=original['x0'])
        phase_markers['bridge_return_s'] = budget.elapsed
        if budget.remaining > 0 and (OUT / 'matlab/request_000001.mat').exists():
            with budget.phase('actual_transport_array_identity'):
                sent, sent_receipt = core.load_original_mat(OUT / 'matlab/request_000001.mat')
                sent_identity = core.assert_only_fixed_integer_bounds_changed(original, sent)
                write_new(OUT / 'transport_identity.json', dict(load=sent_receipt, identity=sent_identity))
        if result.get('options'):
            expected = {k: v for k, v in d['original_options'].items() if k != 'MaxTime'}
            actual = {k: v for k, v in result['options'].items() if k != 'MaxTime'}
            options_match = expected == actual
        if result.get('x') and result.get('budget_valid') and budget.remaining > 0 and options_match:
            with budget.phase('original_matrix_and_fixed_bounds_acceptance'):
                numeric = core.verify_vector(result['x'], original, fixed, objective=result.get('fval'))
                admitted_at = budget.elapsed
        state = classify(result, numeric, budget.remaining > 0, options_match)
        # Preserve no later claim than the completed numerical checks.
        phase_markers['classification_completed_s'] = budget.elapsed
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'traceback': traceback.format_exc()})
        cleanup = getattr(error, 'matlab_cleanup', None)
        state = 'UNRESOLVED_BUDGET_OR_LATE' if isinstance(error, TimeoutError) else 'TECHNICAL_FAILURE'
    finally:
        method_stopped = budget.elapsed
        if session is not None:
            try:
                session.close()
                cleanup = getattr(session, 'cleanup', None)
            except BaseException:
                errors.append({'type': 'CLEANUP_ERROR', 'traceback': traceback.format_exc()})
        lifecycle_complete = None
        if bridge is not None and (session is not None or cleanup is not None):
            lifecycle_complete = bridge.cleanup_is_complete(cleanup)
            if not lifecycle_complete:
                errors.append({'type': 'CLEANUP_UNRESOLVED', 'detail': 'Frozen bridge did not verify complete owned-process cleanup'})
        # Only serialization and provenance checks after cutoff, never new numeric acceptance.
        try:
            admission()
            source_preserved = True
        except Exception:
            source_preserved = False
            errors.append({'type': 'SOURCE_DRIFT', 'traceback': traceback.format_exc()})
        write_new(OUT / 'method_return.json', dict(utc=now(), state=state,
            method_elapsed_s=method_stopped, wall_including_cleanup_s=budget.elapsed,
            numeric_admission_completed_s=admitted_at, numeric=numeric, result=result,
            phase_markers=phase_markers, phases=budget.records, options_match_except_time=options_match,
            events=events, consumer_scope='raw_event_archive_only; generic bridge metadata does not imply thermal evaluation',
            cleanup=cleanup, lifecycle_complete=lifecycle_complete,
            source_preserved=source_preserved, errors=errors,
            technical_completion='COMPLETE' if not errors else 'ERROR_OR_UNRESOLVED',
            request_attempts=0 if session is None else session.counter,
            new_safe_or_U=False, thermal_integrations=0, complete_candidate_evaluations=0,
            no_retry=True))
    return 0 if not errors else 2


def capture_owned(proc, identities):
    import psutil
    if proc.poll() is not None:
        return
    try:
        root = psutil.Process(proc.pid)
        for p in [root] + root.children(recursive=True):
            identities[(p.pid, p.create_time())] = True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def stop_owned(identities, deadline):
    import psutil
    actions = []
    for pid, created in reversed(list(identities)):
        if time.monotonic() >= deadline:
            break
        try:
            p = psutil.Process(pid)
            if p.create_time() == created:
                p.kill()
                actions.append({'pid': pid, 'create_time': created, 'kill_requested': True})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return actions


def inspect_owned(identities):
    import psutil
    records = []
    for pid, created in identities:
        try:
            p = psutil.Process(pid)
            state = 'ALIVE' if p.create_time() == created else 'PID_REUSED_ORIGINAL_EXITED'
        except psutil.NoSuchProcess:
            state = 'EXITED'
        except psutil.AccessDenied:
            state = 'UNRESOLVED_ACCESS'
        records.append({'pid': pid, 'create_time': created, 'state': state})
    return records


def execute():
    start = time.monotonic()
    deadline = start + CALENDAR
    d = admission()
    pure = read(OUT / 'pure_checks.json')
    if not pure['passed'] or pure['declaration_sha256'] != sha(OUT / 'declaration.json'):
        raise ValueError('Pure checks missing or stale')
    host = context()
    if not resource_ok(host):
        print(json.dumps({'not_started': 'host_or_resources', 'context': host}))
        return 3
    write_new(OUT / 'launch.claim.json', dict(utc=now(), calendar_start=start, calendar_deadline=deadline,
        host=host, declaration_sha256=sha(OUT / 'declaration.json'), no_retry=True))
    identities, terminated, error = {}, [], None
    proc = None
    try:
        worker_start = time.monotonic()
        with (OUT / 'worker.stdout.txt').open('xb') as log:
            proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), 'worker'],
                cwd=str(REPO), stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while proc.poll() is None:
                capture_owned(proc, identities)
                if time.monotonic() >= min(worker_start + WATCHDOG, deadline - 40):
                    error = 'WORKER_RETURN_WATCHDOG'
                    terminated = stop_owned(identities, deadline)
                    break
                time.sleep(0.5)
            proc.wait(timeout=max(0.1, min(10.0, deadline - time.monotonic())))
    except BaseException:
        error = traceback.format_exc()
        terminated += stop_owned(identities, deadline)
    final_processes = inspect_owned(identities)
    if any(x['state'] in ('ALIVE', 'UNRESOLVED_ACCESS') for x in final_processes):
        terminated += stop_owned(identities, deadline)
        cleanup_deadline = min(deadline, time.monotonic() + 10)
        while time.monotonic() < cleanup_deadline:
            final_processes = inspect_owned(identities)
            if all(x['state'] in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED') for x in final_processes):
                break
            time.sleep(0.25)
    owned_exited = all(x['state'] in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED') for x in final_processes)
    if not owned_exited:
        error = (error or '') + '\nOWNED_PROCESS_CLEANUP_UNRESOLVED'
    write_new(OUT / 'terminal.json', dict(utc=now(), wall_s=time.monotonic()-start,
        calendar_seconds=CALENDAR, returncode=None if proc is None else proc.poll(), error=error,
        terminated=terminated, observed_owned_processes=[{'pid': p, 'create_time': t} for p, t in identities],
        final_processes=final_processes, observed_owned_processes_exited=owned_exited,
        method_calls=int((OUT / 'method.claim.json').exists()),
        native_request_slots_consumed=int((OUT / 'request.claim.json').exists()),
        thermal_post_calls=0, retries=0, no_auto_followup=True))
    print(json.dumps(read(OUT / 'terminal.json')))
    return 0 if not error and proc is not None and proc.returncode == 0 else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'execute', 'worker', 'context'])
    args = parser.parse_args()
    action = {'prepare': prepare, 'execute': execute, 'worker': worker,
              'context': lambda: print(json.dumps(context()))}[args.action]
    raise SystemExit(action() or 0)
