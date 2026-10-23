"""One bounded technical READY/close check; no task input or solve request."""
import argparse
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCIENCE = REPO / 'research/chapter3_experiments'
RUNTIME = REPO / '.runtime/k183_host_handshake01'
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(SCIENCE))
from research.chapter4_scheduler.execution import protocol as p


def context():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    a = ctypes.WinDLL('advapi32', use_last_error=True)
    a.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    a.OpenProcessToken.restype = w.BOOL
    a.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]
    a.GetTokenInformation.restype = w.BOOL
    k.GetCurrentProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    token = w.HANDLE(); flag = w.DWORD(); size = w.DWORD()
    if not a.OpenProcessToken(k.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not a.GetTokenInformation(token, 29, ctypes.byref(flag), ctypes.sizeof(flag), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k.CloseHandle(token)
    return dict(token_is_appcontainer=bool(flag.value), temp=os.environ.get('TEMP'),
        tmp=os.environ.get('TMP'), python=sys.executable, pid=os.getpid())


def child():
    started = time.monotonic()
    result = dict(protocol='K183-one-host-READY-no-solve-v1', passed=False,
        technical_starts=1, research_calls=0, optimization_requests=0,
        thermal_integrations=0, task_input_loaded=False, context=context(), errors=[])
    session = None
    try:
        if result['context']['token_is_appcontainer']:
            raise RuntimeError('This declared diagnostic must run in the host context')
        from matlab_bridge import MatlabSession, cleanup_is_complete
        session = MatlabSession(RUNTIME / 'matlab', total_budget_s=120)
        ready = session.environment
        result.update(ready=ready.get('status'), release=ready.get('release'),
            license_test=bool(ready.get('license_test')), license_checkout=bool(ready.get('license_checkout')),
            intlinprog_path=ready.get('intlinprog_path'),
            startup_s=session.metadata['startup_wall_seconds'],
            session_total_requests=session.counter)
        session.close()
        result.update(cleanup_status=session.cleanup.get('cleanup_status'),
            cleanup_complete=cleanup_is_complete(session.cleanup),
            native_returncode=session.cleanup.get('returncode'))
        result['passed'] = (result['ready'] == 'READY' and result['release'] == '2023b'
            and result['license_checkout'] and session.counter == 0
            and result['cleanup_complete'] and result['native_returncode'] == 0)
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__, message=str(error)))
        cleanup = getattr(error, 'matlab_cleanup', {})
        if session is not None and not session.closed:
            session.close(); cleanup = session.cleanup
        result.setdefault('cleanup_status', cleanup.get('cleanup_status'))
    result['wall_s'] = time.monotonic() - started
    p.write_new(HERE / 'host_handshake.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result['passed'] else 2


def supervise():
    if context()['token_is_appcontainer']:
        raise RuntimeError('Host diagnostic cannot be launched from the restricted context')
    if RUNTIME.exists() or (HERE / 'host_handshake.json').exists():
        raise FileExistsError('One technical start only; never retry')
    plan = p.read(HERE / 'plan.json')
    if plan['technical_matlab_starts_at_most'] != 1 or plan['research_calls'] != 0:
        raise ValueError('Technical diagnostic scope mismatch')
    if any(p.sha(REPO / name) != digest for name, digest in plan['sources'].items()):
        raise ValueError('Original bridge or worker changed before probe')
    RUNTIME.mkdir(parents=True)
    p.write_new(HERE / 'launch.claim.json', dict(context=context(), started_utc=p.now(),
        script_sha256=p.sha(__file__), plan_sha256=p.sha(HERE/'plan.json'),
        technical_starts_reserved=1, research_calls=0, no_retry=True))
    from research.chapter3_experiments.linked_ablation_execution.supervise import run_child
    start = time.monotonic()
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=150)).isoformat()
    receipt = run_child([sys.executable, '-B', str(Path(__file__).resolve()), '--child'],
        RUNTIME, 'technical_startup', watchdog_s=150,
        slot_deadline_monotonic=start+150, calendar_deadline_utc=deadline)
    p.write_new(HERE / 'supervisor.json', receipt)
    print(json.dumps(receipt), flush=True)
    return 0 if receipt.get('returncode') == 0 and not receipt.get('watchdog_stop') else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    raise SystemExit(child() if args.child else supervise())
