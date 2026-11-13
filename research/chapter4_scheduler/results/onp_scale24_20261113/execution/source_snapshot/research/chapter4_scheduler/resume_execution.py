"""K184: only the seven unstarted K181 slots, original absolute deadline.

New control namespace; old STOPPED evidence and all scientific code stay intact.
The original worker runs against this explicit continuation protocol facade.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/'research/chapter3_experiments'))
from research.chapter4_scheduler.execution import protocol as original
from research.chapter4_scheduler.results.environment_diagnostic01.host_handshake_probe import context as execution_context

read, sha, canonical, write_new, now = original.read, original.sha, original.canonical, original.write_new, original.now
OLD = HERE/'results/execution_preparation01/frozen'
OUT = HERE/'results/resume_execution01'
PROTOCOL = 'K184-seven-unstarted-host-continuation-v1'
ORDER = original.ORDER[1:]
BUDGETS = dict(method_s=300, method_total_s=2100, post_s=60, post_total_s=420,
    method_return_s=420, slot_s=480, original_calendar_s=4800)


def make_declaration(output=OUT):
    old = read(OLD/'declaration.json')
    d = deepcopy(old)
    d.update(protocol=PROTOCOL, output_directory=Path(output).resolve().relative_to(REPO).as_posix(),
        slots=deepcopy(old['slots'][1:]), budgets=BUDGETS.copy(),
        calendar_deadline_utc=read(OLD/'batch.claim.json')['deadline_utc'],
        prior_declaration_sha256=sha(OLD/'declaration.json'),
        prior_terminal_sha256=sha(OLD/'batch_terminal.json'),
        frozen_at_utc=now(), continuation_only=True,
        host_context_required=True, inherited_consumed_method_calls=1,
        inherited_reserved_method_s=300, inherited_post_calls=0,
        initialization='Independent fresh input and initialization per unstarted slot; no old candidate/thermal cache')
    for p in [Path(__file__), HERE/'results/environment_diagnostic01/host_handshake_probe.py']:
        d['source_sha256'][p.relative_to(REPO).as_posix()] = sha(p)
    for p in [OLD/'declaration.json', OLD/'declaration_binding.json', OLD/'batch.claim.json',
            OLD/'batch_terminal.json', OLD/'authorization.json',
            HERE/'results/environment_diagnostic01/host_handshake.json',
            HERE/'results/environment_diagnostic01/independent_review.json']:
        d['frozen_dependency_sha256'][p.relative_to(REPO).as_posix()] = sha(p)
    validate(d)
    return d


def validate(d):
    old = read(OLD/'declaration.json'); terminal = read(OLD/'batch_terminal.json')
    if (d.get('protocol') != PROTOCOL or d.get('budgets') != BUDGETS
            or d.get('authorized') is not False or d.get('execution_enabled') is not False
            or d.get('output_directory') != OUT.relative_to(REPO).as_posix()
            or d.get('slots') != old['slots'][1:] or len(d['slots']) != 7
            or [(s['case_id'], s['arm']) for s in d['slots']] != ORDER
            or d.get('cases') != old['cases'] or d.get('solver_options') != old['solver_options']):
        raise ValueError('Only the exact seven original unstarted recipes may resume')
    if (d.get('calendar_deadline_utc') != read(OLD/'batch.claim.json')['deadline_utc']
            or d.get('prior_declaration_sha256') != sha(OLD/'declaration.json')
            or d.get('prior_terminal_sha256') != sha(OLD/'batch_terminal.json')
            or terminal.get('state') != 'STOPPED' or terminal.get('research_calls_reserved') != 1
            or terminal.get('posts_reserved') != 0
            or len(list((OLD/'calls').glob('*/slot.claim.json'))) != 1
            or not (OLD/'calls/base__R1__C/slot.claim.json').is_file()
            or any((OLD/'calls'/s['slot_id']).exists() for s in d['slots'])):
        raise ValueError('Prior consumption or absolute calendar binding drift')
    if (d.get('inherited_consumed_method_calls') != 1 or d.get('inherited_reserved_method_s') != 300
            or d.get('inherited_post_calls') != 0 or d.get('host_context_required') is not True):
        raise ValueError('No refund or context downgrade is allowed')
    if read(HERE/'results/environment_diagnostic01/host_handshake.json').get('passed') is not True:
        raise ValueError('Host startup diagnosis did not pass')
    return True


def verify_files(d):
    return original.verify_files(d)


def check_context(path):
    path = Path(path).resolve(); d = read(path); validate(d)
    if path != (OUT/'declaration.json').resolve():
        raise ValueError('Wrong continuation output namespace')
    if read(OUT/'declaration_binding.json')['declaration_sha256'] != sha(path):
        raise ValueError('Continuation declaration drift')
    auth = read(OUT/'authorization.json')
    if (auth.get('authorized') is not True or auth.get('execution_enabled') is not True
            or auth.get('origin') != 'direct human continuation authorization'
            or auth.get('confirmation') != '排查完问题就直接开始实验就行'
            or auth.get('declaration_sha256') != sha(path) or auth.get('budgets') != BUDGETS
            or auth.get('calendar_deadline_utc') != d['calendar_deadline_utc']):
        raise ValueError('No matching seven-slot continuation authorization')
    for name, digest in auth['precheck_sha256'].items():
        gate = read(REPO/name)
        if sha(REPO/name) != digest or gate.get('passed') is not True:
            raise ValueError('Continuation precheck missing or changed')
    if not auth['precheck_sha256'] or not verify_files(d):
        raise ValueError('Source, input or current precheck identity failed')
    if (OUT/'batch_terminal.json').exists():
        raise ValueError('Continuation is terminal; no retry')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(d['calendar_deadline_utc']):
        raise TimeoutError('Original absolute calendar cutoff reached')
    return d, OUT


def _batch(d, out, path):
    claim = read(out/'batch.claim.json')
    if (claim.get('declaration_sha256') != sha(path)
            or claim.get('deadline_utc') != d['calendar_deadline_utc']
            or claim.get('not_scientific') is not False):
        raise ValueError('Wrong continuation batch or fake execution')


def load_active(path, slot_id):
    d, out = check_context(path); _batch(d, out, path)
    if execution_context()['token_is_appcontainer']:
        raise ValueError('All continuation arms must run in the validated host context')
    slot = next((s for s in d['slots'] if s['slot_id'] == slot_id), None)
    if slot is None:
        raise ValueError('Already-consumed or unknown slot')
    folder = out/'calls'/slot_id
    if (read(folder/'slot.claim.json').get('slot') != slot
            or read(folder/'slot.claim.json').get('declaration_sha256') != sha(path)
            or (folder/'terminal.json').exists()):
        raise ValueError('No active once-only continuation slot')
    return d, slot, next(c for c in d['cases'] if c['common']['case_id'] == slot['case_id'])


def claim_slot(path, slot_id):
    d, out = check_context(path); _batch(d, out, path)
    for slot in d['slots']:
        folder = out/'calls'/slot['slot_id']
        if slot['slot_id'] == slot_id:
            if folder.exists():
                raise FileExistsError('Already consumed; never retry')
            folder.mkdir(parents=True)
            write_new(folder/'slot.claim.json', dict(slot=slot, declaration_sha256=sha(path),
                reserved_method_s=300, reserved_at_utc=now(), no_retry=True))
            return folder
        if read(folder/'terminal.json').get('continue_allowed') is not True:
            raise ValueError('Earlier continuation slot incomplete or failed')
    raise ValueError('Unknown or already-consumed slot')


def freeze(gate_path):
    if OUT.exists():
        raise FileExistsError('Continuation namespace exists')
    gate = read(gate_path)
    if gate.get('passed') is not True or gate.get('new_research_calls') != 0 or gate.get('control_sha256') != sha(__file__):
        raise ValueError('Current zero-research continuation precheck required')
    d = make_declaration()
    if not verify_files(d):
        raise ValueError('Original science or new execution control drift')
    OUT.mkdir(parents=True)
    write_new(OUT/'declaration.json', d)
    write_new(OUT/'declaration_binding.json', dict(declaration_sha256=sha(OUT/'declaration.json')))
    write_new(OUT/'authorization.json', dict(origin='direct human continuation authorization',
        confirmation='排查完问题就直接开始实验就行', recorded_at_utc=now(),
        authorized=True, execution_enabled=True, declaration_sha256=sha(OUT/'declaration.json'),
        budgets=BUDGETS, calendar_deadline_utc=d['calendar_deadline_utc'],
        precheck_sha256={Path(gate_path).relative_to(REPO).as_posix():sha(gate_path)}))
    return d


def run():
    path = OUT/'declaration.json'; d, out = check_context(path)
    if execution_context()['token_is_appcontainer']:
        raise ValueError('Continuation controller must run in host context')
    from research.chapter3_experiments.linked_ablation_execution.supervise import run_child
    from research.chapter4_scheduler.execution.batch import _method_audit
    start = time.monotonic(); deadline = d['calendar_deadline_utc']
    write_new(out/'batch.claim.json', dict(declaration_sha256=sha(path), started_utc=now(),
        deadline_utc=deadline, not_scientific=False, max_new_method_calls=7, no_retry=True))
    completed = []; errors = []
    try:
        for slot in d['slots']:
            if (datetime.fromisoformat(deadline)-datetime.now(timezone.utc)).total_seconds() < 480:
                raise TimeoutError('Original calendar cannot cover another complete slot')
            folder = claim_slot(path,slot['slot_id']); began = time.monotonic()
            command = [sys.executable,'-B',str(Path(__file__).resolve()),'method',
                '--slot-id',slot['slot_id']]
            proc = run_child(command,folder,'method',watchdog_s=420,
                slot_deadline_monotonic=began+480,calendar_deadline_utc=deadline)
            write_new(folder/'supervisor_method.json',proc)
            if proc.get('returncode') != 0 or not proc.get('process_closed') or proc.get('watchdog_stop'):
                raise RuntimeError('Method process failed; stop remaining slots')
            audit = _method_audit(folder,slot,d,path); write_new(folder/'audit.json',audit)
            if audit.get('technical_failure'):
                raise RuntimeError('Technical/numeric/identity/cleanup audit failed')
            posted = False
            if audit.get('eligible_for_post'):
                if time.monotonic() > began+420 or (datetime.fromisoformat(deadline)-datetime.now(timezone.utc)).total_seconds() < 60:
                    raise TimeoutError('Insufficient original allowance for complete post')
                write_new(folder/'post_reservation.json',dict(seconds=60,no_retry=True,audit_sha256=sha(folder/'audit.json')))
                command[3]='post'
                post=run_child(command,folder,'post',watchdog_s=60,
                    slot_deadline_monotonic=began+480,calendar_deadline_utc=deadline)
                write_new(folder/'supervisor_post.json',post)
                if (post.get('returncode') != 0 or not post.get('process_closed') or post.get('watchdog_stop')
                        or read(folder/'post_return.json').get('passed') is not True):
                    raise RuntimeError('Unique post failed; no repair or retry')
                posted=True
            elif audit.get('normal_no_safe') is not True:
                raise RuntimeError('Unclassified method result')
            if not verify_files(d):
                raise ValueError('Source drift after slot')
            terminal=dict(slot_id=slot['slot_id'],continue_allowed=True,post_passed=posted,
                normal_no_safe=audit.get('normal_no_safe') is True,returned_utc=now(),no_retry=True)
            write_new(folder/'terminal.json',terminal); completed.append(terminal)
            print(slot['slot_id'],'POST_PASS' if posted else 'NORMAL_NO_SAFE',flush=True)
    except BaseException as error:
        errors.append(dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
    claims=list((out/'calls').glob('*/slot.claim.json')); posts=list((out/'calls').glob('*/post_reservation.json'))
    terminal=dict(protocol=PROTOCOL,state='COMPLETED' if len(completed)==7 and not errors else 'STOPPED',
        passed=len(completed)==7 and not errors,completed_slots=completed,errors=errors,
        method_calls_reserved=len(claims),reserved_method_s=300*len(claims),post_calls_reserved=len(posts),reserved_post_s=60*len(posts),
        inherited_consumed_method_calls=1,combined_method_calls=1+len(claims),
        calendar_deadline_utc=deadline,resume_wall_s=time.monotonic()-start,returned_utc=now(),no_retry=True)
    write_new(out/'batch_terminal.json',terminal)
    return 0 if terminal['passed'] else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['freeze','run','method','post'])
    parser.add_argument('--gate',type=Path); parser.add_argument('--slot-id')
    args=parser.parse_args()
    if args.mode=='freeze':
        freeze(args.gate.resolve()); return 0
    if args.mode=='run':return run()
    # Explicit continuation contract for the unchanged original worker.
    from research.chapter4_scheduler.execution import worker
    worker.protocol=sys.modules[__name__]
    folder=OUT/'calls'/str(args.slot_id)
    returned=(worker.run_method if args.mode=='method' else worker.run_post)(OUT/'declaration.json',args.slot_id,folder)
    write_new(folder/(args.mode+'_host_context.json'),dict(context=execution_context(),no_new_scientific_evidence=True))
    return returned


if __name__=='__main__':raise SystemExit(main())
