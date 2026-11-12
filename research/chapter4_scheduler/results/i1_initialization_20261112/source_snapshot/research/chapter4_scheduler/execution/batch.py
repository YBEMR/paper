"""Serial K181 controller. Importing/preparing it never starts research."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import time
import traceback

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from research.chapter4_scheduler.execution import protocol as p


def _method_audit(folder, slot, d, declaration_path):
    from research.chapter4_scheduler.execution.audit import admit_result
    receipt = p.read(folder / 'worker_return.json')
    if receipt.get('passed') is not True or receipt.get('not_scientific') is not False:
        return dict(eligible_for_post=False, normal_no_safe=False, technical_failure=True,
                    errors=['WORKER_RETURN_FAILED_OR_MOCK'])
    identity = p.read(folder / 'worker_identity.json')
    work = folder / 'method'
    closure = work / 'matlab/closed.json'
    native = dict(folder=folder, method_folder=work, native_started=identity.get('native_started'),
                  closure=p.read(closure) if closure.is_file() else None)
    instance, config = p.read(folder / 'input_instance.json'), p.read(folder / 'input_config.json')
    result = p.read(folder / 'result.json')
    audit = admit_result(slot['arm'], result, instance, config,
                         root_seconds=300, identity=identity, native_evidence=native)
    hashes = dict(result_sha256=p.sha(folder / 'result.json'),
        raw_result_sha256=p.sha(folder / 'wrapper_raw_result.json'),
        input_sha256=p.canonical(instance), config_sha256=p.canonical(config),
        declaration_sha256=p.sha(declaration_path))
    if hashes['result_sha256'] != hashes['raw_result_sha256']:
        audit.update(eligible_for_post=False, normal_no_safe=False, technical_failure=True)
        audit.setdefault('errors', []).append('RAW_RESULT_CHANGED')
    audit.update(hashes)
    return audit


def run(declaration_path, *, _runner=None, _audit=None, _clock=time.monotonic):
    """Consume each reserved slot once. Injected fake services cannot yield science."""
    path = Path(declaration_path).resolve()
    d, out = p._context(path)
    if (_runner is None) != (_audit is None):
        raise ValueError('Simulation must inject both inert process and audit services')
    fake = _runner is not None or _audit is not None
    if _runner is None:
        from research.chapter3_experiments.linked_ablation_execution.supervise import run_child
        _runner = run_child
    auditor = _audit or _method_audit
    start = _clock(); utc_start = datetime.now(timezone.utc)
    deadline = (utc_start + timedelta(seconds=4800)).isoformat()
    p.write_new(out / 'batch.claim.json', dict(protocol=p.PROTOCOL,
        declaration_sha256=p.sha(path), started_utc=utc_start.isoformat(),
        deadline_utc=deadline, monotonic_start=start, not_scientific=fake,
        max_method_calls=8, max_method_s=2400, max_post_calls=8, max_post_s=480,
        no_retry=True))
    states = []; errors = []
    try:
        for slot in d['slots']:
            if (_clock() - start > 4800-480 or
                    (datetime.fromisoformat(deadline)-datetime.now(timezone.utc)).total_seconds() < 480):
                raise TimeoutError('Insufficient declared slot/calendar allowance; no new slot')
            folder = p.claim_slot(path, slot['slot_id'])
            slot_started = _clock()
            command = [sys.executable, '-B', str(Path(__file__).with_name('worker.py')),
                'method', '--declaration', str(path), '--slot-id', slot['slot_id'], '--out', str(folder)]
            proc = _runner(command, folder, 'method', watchdog_s=420,
                slot_deadline_monotonic=slot_started+480, calendar_deadline_utc=deadline)
            p.write_new(folder / 'supervisor_method.json', proc)
            if (proc.get('returncode') != 0 or proc.get('process_closed') is not True
                    or proc.get('watchdog_stop') or proc.get('launched') is not True):
                raise RuntimeError('Method process failed, uncertain or watchdog-stopped')
            audit = auditor(folder, slot, d, path)
            if fake:
                audit.update(not_scientific=True, usable_as_research_evidence=False)
            p.write_new(folder / 'audit.json', audit)
            if audit.get('technical_failure') is True:
                raise RuntimeError('Method identity/numeric/native audit failed')
            posted = False
            if audit.get('eligible_for_post') is True:
                if (_clock() > slot_started+480-60 or
                        (datetime.fromisoformat(deadline)-datetime.now(timezone.utc)).total_seconds() < 60):
                    raise TimeoutError('Insufficient complete post allowance; preserve method evidence')
                p.write_new(folder / 'post_reservation.json', dict(seconds=60,
                    audit_sha256=p.sha(folder/'audit.json'), no_retry=True))
                command[3] = 'post'
                post = _runner(command, folder, 'post', watchdog_s=60,
                    slot_deadline_monotonic=slot_started+480, calendar_deadline_utc=deadline)
                p.write_new(folder / 'supervisor_post.json', post)
                if (post.get('returncode') != 0 or post.get('process_closed') is not True
                        or post.get('watchdog_stop') or post.get('launched') is not True
                        or p.read(folder / 'post_return.json').get('passed') is not True):
                    raise RuntimeError('Unique independent post failed or unresolved')
                posted = True
            elif audit.get('normal_no_safe') is not True:
                raise RuntimeError('Neither admitted SAFE nor normal no-SAFE')
            if not p.verify_files(d):
                raise RuntimeError('Frozen source/archive drift after slot')
            terminal = dict(slot_id=slot['slot_id'], continue_allowed=True,
                normal_no_safe=audit.get('normal_no_safe') is True,
                post_passed=posted, reserved_method_s=300, reserved_post_s=60 if posted else 0,
                not_scientific=fake, no_retry=True, returned_utc=p.now())
            p.write_new(folder / 'terminal.json', terminal); states.append(terminal)
    except BaseException as error:
        errors.append(dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    claims = list((out / 'calls').glob('*/slot.claim.json'))
    posts = list((out / 'calls').glob('*/post_reservation.json'))
    terminal = dict(protocol=p.PROTOCOL,
        state='COMPLETED' if len(states) == 8 and not errors else 'STOPPED',
        passed=len(states) == 8 and not errors, not_scientific=fake,
        declaration_sha256=p.sha(path), research_calls_reserved=len(claims),
        reserved_method_s=300*len(claims), posts_reserved=len(posts), reserved_post_s=60*len(posts),
        completed_slots=states, errors=errors, calendar_wall_s=_clock()-start,
        returned_utc=p.now(), no_retry=True)
    p.write_new(out / 'batch_terminal.json', terminal)
    return terminal


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.declaration)
    print(result['state'], 'reserved', result['research_calls_reserved'], flush=True)
    raise SystemExit(0 if result['passed'] else 2)
