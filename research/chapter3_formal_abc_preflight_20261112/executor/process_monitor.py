import time
WATCHDOG=680.0

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

