"""Owned-process wall-clock supervision; no scientific backend imports.

The caller records root_origin before input preparation, copying or process
creation. A worker must use that inherited origin and must not spawn children.
This supervisor stops/reaps only the Popen object it created. Receipt content
and formation timestamps need separate validation; mere arrival proves no SAFE.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time


class ProcessContractError(ValueError):
    pass


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProcessContractError(name + ' must be finite')
    return float(value)


def supervise(command, *, cwd, root_origin, limit_s, slot_deadline, batch_deadline,
              stop_file, receipt_file, grace_s=5, poll_s=.02,
              clock=time.monotonic, popen=subprocess.Popen, sleep=time.sleep,
              allow_test_limits=False):
    """Run one owned worker under the earliest root, slot and batch deadline.

    Non-production limits require both allow_test_limits=True and an explicit
    --e1-mock-worker marker in command. No test switch authorizes research.
    The archive grace is for stopping/serialization only. Slot and batch absolute
    deadlines remain hard caps, including when they precede the root deadline.
    A receipt observed late is retained only for subsequent identity and formed-
    time validation. No receipt is accepted as research evidence here.
    """
    if not isinstance(command, (list, tuple)) or not command or any(not isinstance(x, str) for x in command):
        raise ProcessContractError('command must be a nonempty string argv')
    command = list(command)
    origin = _finite(root_origin, 'root_origin')
    limit = _finite(limit_s, 'limit_s')
    grace = _finite(grace_s, 'grace_s')
    poll = _finite(poll_s, 'poll_s')
    slot = _finite(slot_deadline, 'slot_deadline')
    batch = _finite(batch_deadline, 'batch_deadline')
    if limit <= 0 or grace < 0 or poll <= 0 or grace > 5:
        raise ProcessContractError('invalid limit, polling interval or archive grace')
    if limit not in (300.0, 60.0) and not (allow_test_limits is True and '--e1-mock-worker' in command):
        raise ProcessContractError('short limits are restricted to explicit mock workers')
    if allow_test_limits is not False and allow_test_limits is not True:
        raise ProcessContractError('allow_test_limits must be boolean')
    if not callable(clock) or not callable(popen) or not callable(sleep):
        raise ProcessContractError('clock, popen and sleep must be callable')
    root_deadline = origin + limit
    if not math.isfinite(root_deadline):
        raise ProcessContractError('root deadline overflow')
    evidence_deadline = min(root_deadline, slot, batch)
    # Root grace never extends a slot or batch hard cap.
    hard_deadline = min(root_deadline + grace, slot, batch)
    stop = Path(stop_file).resolve()
    receipt = Path(receipt_file).resolve()
    out_path = receipt.with_name(receipt.name + '.stdout.log')
    err_path = receipt.with_name(receipt.name + '.stderr.log')
    paths = [stop, receipt, out_path, err_path]
    if len(set(paths)) != len(paths) or any(path.exists() for path in paths):
        raise ProcessContractError('stale or overlapping worker artifacts')
    start = _finite(clock(), 'clock')
    if start < origin:
        raise ProcessContractError('clock precedes inherited root origin')
    cwd = Path(cwd).resolve()
    if not cwd.is_dir():
        raise ProcessContractError('worker cwd does not exist')
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    packed = json.dumps(command, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    record = dict(command=command, command_sha256=hashlib.sha256(packed).hexdigest(), cwd=str(cwd),
                  root_origin=origin, limit_s=limit, root_deadline=root_deadline,
                  slot_deadline=slot, batch_deadline=batch,
                  evidence_deadline=evidence_deadline, hard_deadline=hard_deadline,
                  evidence_cutoff='strict monotonic time < evidence_deadline',
                  archive_grace_s=grace, launch_requested_elapsed_s=start-origin,
                  pid=None, returncode=None, killed=False, reaped=False,
                  stop_signal_written=False, stop_reason=None,
                  stop_file=str(stop), receipt_file=str(receipt),
                  stdout_file=str(out_path), stderr_file=str(err_path),
                  receipt_observed_elapsed_s=None, usable_as_research_evidence=False,
                  scientific_backend_invocations_by_supervisor=0,
                  test_limits=allow_test_limits is True)

    last = start
    def now():
        nonlocal last
        current = _finite(clock(), 'clock')
        if current < last:
            raise ProcessContractError('non-monotonic parent clock')
        last = current
        return current

    def reasons(at):
        return [name for name, deadline in (('ROOT_LIMIT', root_deadline),
                ('SLOT_LIMIT', slot), ('BATCH_LIMIT', batch)) if at >= deadline]

    def stop_signal(at):
        if record['stop_signal_written']:
            return
        payload = dict(state='ARCHIVE_ONLY_STOP_NEW_WORK', reasons=reasons(at),
                       root_origin=origin, limit_s=limit, evidence_deadline=evidence_deadline,
                       observed_elapsed_s=at-origin, no_new_evidence=True)
        with stop.open('xb') as stream:
            stream.write((json.dumps(payload, sort_keys=True)+'\n').encode('utf-8'))
        record.update(stop_signal_written=True, stop_signal_elapsed_s=at-origin,
                      stop_reason=payload['reasons'])

    def observe_receipt(at):
        if record['receipt_observed_elapsed_s'] is None and receipt.is_file():
            record['receipt_observed_elapsed_s'] = at-origin

    def reap():
        try:
            proc.wait(timeout=2.)
            record.update(returncode=proc.returncode, reaped=True)
            return True
        except subprocess.TimeoutExpired:
            record.update(classification='PROCESS_CLEANUP_FAULT', cleanup_pending=True,
                          error_type='TimeoutExpired', error='owned worker did not reap within 2 seconds')
            return False

    def finish(at):
        observe_receipt(at)
        record.update(method_elapsed_s=at-origin,
                      deadline_overshoot_s=max(0., at-evidence_deadline),
                      root_deadline_overshoot_s=max(0., at-root_deadline),
                      hard_deadline_overshoot_s=max(0., at-hard_deadline),
                      finished_monotonic=at)
        if receipt.is_file():
            raw = receipt.read_bytes()
            record.update(receipt_bytes=len(raw), receipt_sha256=hashlib.sha256(raw).hexdigest(),
                          receipt_requires_independent_validation=True,
                          receipt_arrival='LATE_ARCHIVAL_ONLY' if
                              record['receipt_observed_elapsed_s'] >= evidence_deadline-origin
                              else 'OBSERVED_BEFORE_CUTOFF_UNVERIFIED')
        record['supervisor_return_elapsed_s'] = now()-origin
        return record

    if start >= evidence_deadline:
        stop_signal(start)
        record.update(classification='START_SKIPPED_DEADLINE', startup_elapsed_s=0.)
        return finish(now())

    proc = None
    with out_path.open('xb') as stdout, err_path.open('xb') as stderr:
        try:
            before_spawn = now()
            if before_spawn >= evidence_deadline:
                stop_signal(before_spawn)
                record.update(classification='START_SKIPPED_DEADLINE', startup_elapsed_s=0.)
                return finish(now())
            kwargs = dict(cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                          shell=False, close_fds=True)
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            proc = popen(command, **kwargs)
            after_spawn = now()
            record.update(pid=proc.pid, startup_elapsed_s=after_spawn-before_spawn,
                          spawned_elapsed_s=after_spawn-origin)
            while True:
                at = now()
                observe_receipt(at)
                code = proc.poll()
                if code is not None:
                    record.update(returncode=code,
                        classification=('NONZERO_EXIT_FAULT' if code != 0 else
                            ('NORMAL_TIME_CUTOFF' if record['stop_signal_written'] or at >= evidence_deadline
                             else 'NATURAL_EXIT')))
                    reap()
                    if at >= evidence_deadline:
                        stop_signal(at)
                    return finish(now())
                if at >= evidence_deadline:
                    stop_signal(at)
                if at >= hard_deadline:
                    proc.kill()
                    record.update(killed=True, kill_elapsed_s=at-origin)
                    record['classification'] = 'WATCHDOG_KILLED'
                    reap()
                    return finish(now())
                next_boundary = hard_deadline if at >= evidence_deadline else evidence_deadline
                sleep(min(poll, max(0., next_boundary-at)))
        except Exception as error:
            # No broad process-name cleanup: only our returned process handle.
            record.update(classification='SPAWN_FAULT' if proc is None else 'SUPERVISOR_FAULT',
                          error_type=type(error).__name__, error=str(error))
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                    record['killed'] = True
                reap()
            return finish(now())
