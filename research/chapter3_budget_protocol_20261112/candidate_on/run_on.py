"""Approved one-shot ON launch. No approval is implied by prepare, test, or commit."""
import time
PROCESS_ENTRY = time.monotonic()
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
from control import execute, SECONDS, WATCHDOG
from guard import read, sha, save, verify_plan, verify_approval, claim_once, inside

PACKAGE = Path(__file__).resolve().parent


def terminate_owned_tree(process_module, pid, created):
    """Watchdog only: never kill a reused PID or an unrelated process tree."""
    try:
        root = process_module.Process(pid)
    except process_module.NoSuchProcess:
        return dict(complete=False, reason='ROOT_ALREADY_GONE_DESCENDANTS_UNKNOWN')
    if root.create_time() != created:
        return dict(complete=False, reason='ROOT_PID_REUSED_NO_SIGNAL_SENT')
    processes = [*root.children(recursive=True), root]
    identities = [(p, p.create_time()) for p in processes]
    errors = []
    for p, identity in identities:
        try:
            if p.create_time() != identity:
                errors.append('PID_REUSED:'+str(p.pid))
            else:
                p.kill()
        except process_module.NoSuchProcess:
            pass
        except Exception as error:
            errors.append(repr(error))
    gone, alive = process_module.wait_procs(processes, timeout=10)
    return dict(complete=not alive and not errors, signaled_identities=[dict(pid=p.pid, create_time=t) for p,t in identities],
                alive_pids=[p.pid for p in alive], errors=errors,
                scope='Observed descendant identities only; not a system-wide process isolation guarantee')


def monitor_owned(proc, created, start, process_module, clock=time.monotonic, sleep=time.sleep):
    """Track descendants while the parent exists; clean captured survivors on abnormal exit."""
    identities = {proc.pid: created}; capture_errors = []; forced = []
    while proc.poll() is None and clock() < start+WATCHDOG:
        try:
            root = process_module.Process(proc.pid)
            if root.create_time() != created: raise RuntimeError('Worker PID identity changed')
            for child in root.children(recursive=True): identities[child.pid] = child.create_time()
        except process_module.NoSuchProcess:
            break
        except Exception as error:
            capture_errors.append(repr(error))
        sleep(min(.25, max(0., start+WATCHDOG-clock())))
    timed_out = proc.poll() is None
    if timed_out:
        try:
            root = process_module.Process(proc.pid)
            if root.create_time() == created:
                for child in root.children(recursive=True): identities[child.pid] = child.create_time()
        except process_module.NoSuchProcess:
            pass
        except Exception as error:
            capture_errors.append(repr(error))
    survivors = []
    for pid, identity in reversed(list(identities.items())):
        try:
            p = process_module.Process(pid)
            if p.create_time() == identity and p.is_running(): survivors.append(p)
        except process_module.NoSuchProcess:
            pass
    # A stopped worker has no further authorized use for its children. Only recorded identities are signaled.
    for p in survivors:
        try:
            if p.create_time() == identities[p.pid]:
                p.kill(); forced.append(p.pid)
        except process_module.NoSuchProcess:
            pass
        except Exception as error:
            capture_errors.append(repr(error))
    _, alive = process_module.wait_procs(survivors, timeout=10) if survivors else ([], [])
    proc.poll()
    return dict(returncode=proc.returncode, watchdog_expired=timed_out, forced_pids=forced,
                observed_identities=[dict(pid=p, create_time=t) for p,t in identities.items()],
                capture_errors=capture_errors, captured_tree_terminated=not alive,
                complete=not alive and not capture_errors,
                scope='Observed owned identities; capture failure prevents an integrity claim.')


def run(workspace, plan_path, approval_path, start=PROCESS_ENTRY):
    # No scientific import and no native process creation before both checks and the durable claim.
    workspace = Path(workspace).resolve(); plan_path = Path(plan_path).resolve(); approval_path = Path(approval_path).resolve()
    plan = verify_plan(plan_path, workspace, PACKAGE)
    verify_approval(read(approval_path), sha(plan_path))
    import psutil
    token = secrets.token_hex(32)
    claim = dict(plan_sha256=sha(plan_path), approval_sha256=sha(approval_path),
                 parent_start_monotonic=start, parent_pid=os.getpid(), parent_create_time=psutil.Process().create_time(),
                 worker_token=token, once_only=True)
    folder = claim_once(workspace, plan, claim)
    save(folder / 'approval_consumed.json', read(approval_path))
    if time.monotonic()-start >= SECONDS:
        save(folder / 'controller.json', dict(state='EXPIRED_BEFORE_WORKER_NO_CALL', native_calls=0))
        return
    temp = folder / 'temp'; temp.mkdir()
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), PYTHONDONTWRITEBYTECODE='1')
    argv = [sys.executable, '-B', str(PACKAGE/'run_on.py'), '_worker', '--workspace', str(workspace),
            '--plan', str(plan_path), '--approval', str(approval_path), '--token', token]
    save(folder / 'command.json', dict(argv=argv, cwd=str(PACKAGE), hidden_window=True))
    with (folder/'stdout.log').open('x', encoding='utf-8') as stdout, (folder/'stderr.log').open('x', encoding='utf-8') as stderr:
        proc = subprocess.Popen(argv, cwd=PACKAGE, env=env, stdout=stdout, stderr=stderr,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        created = psutil.Process(proc.pid).create_time()
        monitor = monitor_owned(proc, created, start, psutil)
        save(folder/'process_monitor.json', monitor)
        code = monitor['returncode']
    receipt = read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
    complete = code == 0 and receipt is not None and monitor['complete'] and not monitor['forced_pids']
    save(folder/'controller.json', dict(returncode=code, process_monitor=monitor, wall_s=time.monotonic()-start,
        receipt_present=receipt is not None, state='COMPLETED' if complete else 'INCOMPLETE_NO_RETRY',
        progress_usable=bool(complete and receipt.get('progress_usable')),
        native_request_attempts=receipt.get('native_request_attempts') if receipt else None,
        retries=0, next_action='STOP_NO_AUTOMATIC_ABC'))


def worker(workspace, plan_path, approval_path, token):
    workspace = Path(workspace).resolve(); plan_path = Path(plan_path).resolve()
    plan = verify_plan(plan_path, workspace, PACKAGE)
    verify_approval(read(approval_path), sha(plan_path))
    folder = inside(workspace, plan['execution_directory']); claim = read(folder/'claim.json')
    if (claim['worker_token'] != token or claim['plan_sha256'] != sha(plan_path)
            or claim['approval_sha256'] != sha(approval_path)):
        raise PermissionError('Worker does not match the single parent claim')
    import psutil
    parent = psutil.Process(claim['parent_pid'])
    if parent.create_time() != claim['parent_create_time'] or os.getppid() != claim['parent_pid']:
        raise PermissionError('Worker parent identity mismatch')
    save(folder/'worker_claim.json', dict(pid=os.getpid(), start_monotonic=claim['parent_start_monotonic']))
    # The preceding exclusive file also rejects direct duplicate worker invocations.
    from adapter import Runtime
    runtime = Runtime(workspace, PACKAGE, plan_path, plan, folder, claim['parent_start_monotonic'])
    result = execute(runtime)
    result['actual_native_entry_events'] = runtime.actual_native_entries
    result['native_calls_observed'] = (1 if runtime.actual_native_entries or (result['native'] or {}).get('intlinprog_entered') is True
                                     else (0 if not runtime.solve_attempted else None))
    result['physical_evaluations_observed'] = runtime.evaluations
    result['native_call_count_scope'] = 'Request attempts and entry events separate; missing entry event does not prove no native call.'
    save(folder/'receipt.json', result)
    print(result['terminal_state'], result['progress_usable'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run', '_worker'])
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=PACKAGE/'plan.json')
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--token')
    args = parser.parse_args()
    if args.command == 'run': run(args.workspace, args.plan, args.approval)
    else: worker(args.workspace, args.plan, args.approval, args.token)
