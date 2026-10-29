"""Serial one-shot supervisor. Real execution requires separately bound approval."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from .common import (HERE, ROOT, METHODS, require, read, save, sha, canonical, load_context,
                     verify_sources, verify_input, recover_archived_safe)
from .monitor import ProcessMonitor, default_host_probe, host_gate


class Runtime:
    clock = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)
    probe = staticmethod(default_host_probe)
    monitor = staticmethod(ProcessMonitor)

    @staticmethod
    def launch(args, stdout, stderr):
        return subprocess.Popen(args, cwd=str(ROOT), stdout=stdout, stderr=stderr,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def classify(envelope, process, cleanup):
    """Execution state never overwrites a separately preserved SAFE witness."""
    if process.get('wall_limit'):
        return 'PROCESS_WALL_LIMIT_STOP'
    if process.get('returncode') not in (0, None) or envelope.get('errors'):
        return 'TECHNICAL_FAILURE'
    if envelope.get('numerical_anomaly'):
        return 'NUMERICAL_ANOMALY'
    if cleanup is not True or envelope.get('cleanup_verified') is not True:
        return 'CLEANUP_UNVERIFIED'
    if envelope.get('budget_exhausted'):
        return 'NORMAL_TIME_LIMIT'
    if envelope.get('state') in ('WORKER_INTERRUPTED', 'ERROR'):
        return 'TECHNICAL_FAILURE'
    if envelope.get('execution_status') == 'STATUS_UNRESOLVED':
        return 'NORMAL_UNRESOLVED'
    if envelope.get('execution_status') not in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT'):
        return 'EXECUTION_STATUS_UNVERIFIED'
    return 'NORMAL_COMPLETION'


def _run_slot(ctx, job, mode, batch_out, batch_deadline, rt, batch_claim):
    plan = ctx['plan']; start = rt.clock()
    cap = job['process_wall_seconds'] if mode == 'method' else job['independent_post_seconds']
    require(batch_deadline-start >= cap, 'INSUFFICIENT_BATCH_TIME_NO_LAUNCH')
    slot_id = job['id']+'__'+mode
    folder = batch_out/'slots'/slot_id
    require(not folder.exists(), 'SLOT_ALREADY_EXISTS')
    folder.mkdir(parents=True)
    token = secrets.token_hex(24)
    worker_out = folder/'worker'
    ticket = {'schema': 'ch3-method-entry-ticket-v1', 'plan_sha256': ctx['plan_sha256'],
        'input_sha256': plan['common_input_sha256'], 'job_id': job['id'], 'mode': mode,
        'slot_id': slot_id, 'worker_token': token, 'created_at_monotonic_s': start,
        'absolute_deadline_monotonic_s': min(start+cap, batch_deadline),
        'ticket_claim_path': str((folder/'worker_started.json').resolve()),
        'method_output': str((batch_out/'slots'/(job['id']+'__method')/'worker').resolve()) if mode == 'post' else None,
        'batch_claim_path': str(batch_claim.resolve()), 'batch_output': str(batch_out.resolve())}
    save(folder/'ticket.json', ticket)
    save(folder/'slot_claim.json', {'slot_id': slot_id, 'ticket_sha256': sha(folder/'ticket.json')})
    args = [plan['python_executable'], '-B', '-m', 'research.chapter3_method_entry_executor.worker',
        '--plan', str(ctx['plan_dir']), '--plan-sha256', ctx['plan_sha256'],
        '--authorization', str(ctx['authorization_path']), '--ticket', str(folder/'ticket.json'),
        '--token', token, '--output', str(worker_out)]
    proc = monitor = None
    process = {'returncode': None, 'wall_limit': False, 'launch_attempted': True}
    with (folder/'stdout.txt').open('x', encoding='utf-8') as stdout, (folder/'stderr.txt').open('x', encoding='utf-8') as stderr:
        try:
            save(folder/'launch_attempt.json', {'slot_id': slot_id,
                'plan_sha256': ctx['plan_sha256'], 'launch_before_s': rt.clock()})
            proc = rt.launch(args, stdout, stderr)
            process['pid'] = proc.pid
            monitor = rt.monitor(proc.pid, clock=rt.clock)
            monitor.sample(force=True)
            save(folder/'monitor_ready.json', {'worker_token': token,
                'plan_sha256': ctx['plan_sha256'], 'pid': proc.pid})
            while proc.poll() is None:
                monitor.sample()
                if rt.clock() >= ticket['absolute_deadline_monotonic_s']:
                    process['wall_limit'] = True
                    process['termination'] = monitor.terminate_owned(force=True)
                    break
                rt.sleep(min(1.0, ticket['absolute_deadline_monotonic_s']-rt.clock()))
            # Cleanup only, never another worker/solver launch or new evidence.
            close_deadline = min(batch_deadline, rt.clock()+10.0)
            while proc.poll() is None and rt.clock() < close_deadline:
                rt.sleep(min(.1, close_deadline-rt.clock()))
            process['returncode'] = proc.poll()
        except Exception as error:
            process['error'] = type(error).__name__+': '+str(error)
            if monitor is not None:
                process['termination'] = monitor.terminate_owned(force=True)
            elif proc is not None and proc.poll() is None:
                # The worker cannot import algorithms before monitor_ready.
                # Only our own Popen child exists at this point.
                proc.kill()
                process['termination_scope'] = 'own unreleased Python worker only'
    process['process_wall_s'] = rt.clock()-start
    result_path = worker_out/('worker_result.json' if mode == 'method' else 'post_result.json')
    envelope = {
        'state': 'WORKER_INTERRUPTED', 'errors': ['NO_COMPLETE_WORKER_RECEIPT'], 'cleanup_verified': None,
        'safe_witness_preserved': False, 'safe_evidence': {'preserved': False, 'U_J': None}}
    if result_path.is_file():
        try:
            envelope = read(result_path)
            require(envelope.get('plan_sha256') == ctx['plan_sha256']
                    and envelope.get('input_sha256') == plan['common_input_sha256']
                    and envelope.get('job_id') == job['id']
                    and envelope.get('source_manifest_sha256') == canonical(plan['source_sha256']),
                    'WORKER_RECEIPT_IDENTITY_MISMATCH')
        except (ValueError, OSError) as error:
            envelope = {'state': 'WORKER_INTERRUPTED', 'errors': [str(error)],
                        'cleanup_verified': None, 'safe_witness_preserved': False}
    identities_verified = False
    try:
        verify_sources(plan)
        value = verify_input(ctx)
        identities_verified = True
        if mode == 'method' and result_path.is_file() and envelope.get('input_identity_verified'):
            for name, key in (('input_config.json', 'config'), ('input_instance.json', 'instance')):
                archived = worker_out/'method'/name
                if not archived.is_file() or canonical(read(archived)) != canonical(value[key]):
                    envelope.setdefault('errors', []).append('METHOD_INPUT_ARCHIVE_MISMATCH:'+name)
        if mode == 'method' and not envelope.get('safe_witness_preserved'):
            retained = recover_archived_safe(value['instance'], worker_out, job['method_seconds'])
            if retained['preserved']:
                envelope.update(safe_witness_preserved=True, safe_evidence=retained,
                                retention_scope='archival checkpoint only; interrupted worker status unchanged')
    except (ValueError, OSError) as error:
        envelope.setdefault('errors', []).append(type(error).__name__+': '+str(error))
        if not identities_verified:
            envelope['safe_witness_preserved'] = False
            envelope['SAFE_identity_unresolved'] = True
    if monitor is not None:
        closed = (envelope.get('matlab_cleanup') or {}).get('receipt') or {}
        identities = closed.get('process_tree_verification', {}).get('identities', [])
        try:
            if identities:
                monitor.register_identities(identities, source='worker MATLAB cleanup receipt')
            monitor.sample(force=True)
            cleanup = monitor.cleanup_verified()
            if cleanup is not True:
                process['parent_cleanup'] = monitor.terminate_owned(force=True)
                cleanup_deadline = min(batch_deadline, rt.clock()+10)
                while monitor.cleanup_verified() is False and rt.clock() < cleanup_deadline:
                    rt.sleep(min(.1, cleanup_deadline-rt.clock()))
                cleanup = monitor.cleanup_verified()
            memory = monitor.summary()
        except Exception as error:
            cleanup = None
            memory = {'state': 'UNAVAILABLE', 'error': str(error)}
            envelope.setdefault('errors', []).append('MONITOR_CLEANUP_ERROR:'+str(error))
    else:
        memory, cleanup = {'state': 'UNAVAILABLE'}, None
    if process.get('error'):
        envelope.setdefault('errors', []).append(process['error'])
    if mode == 'method':
        state = classify(envelope, process, cleanup)
    elif process['wall_limit'] and cleanup is True:
        if envelope.get('timely_violations_preserved'):
            state = 'POST_THERMAL_VIOLATION_STOP'
            envelope['post_state'] = 'THERMAL_VIOLATION'
        else:
            state = 'POST_TIME_LIMIT_UNRESOLVED'
            envelope['post_state'] = 'UNRESOLVED'
    elif process.get('error') or process.get('returncode') != 0 or envelope.get('errors'):
        state = 'TECHNICAL_FAILURE'
    elif cleanup is not True:
        state = 'CLEANUP_UNVERIFIED'
    else:
        state = 'NORMAL_COMPLETION'
    report = {'slot_id': slot_id, 'mode': mode, 'job_id': job['id'], 'execution_status': state,
              'process': process, 'memory': memory, 'monitor_cleanup_verified': cleanup,
              'worker': envelope, 'plan_sha256': ctx['plan_sha256'],
              'input_sha256': plan['common_input_sha256'], 'simulation_only': ctx.get('simulation_only', False)}
    save(folder/'slot_result.json', report)
    return report


def run_batch(ctx, output, *, runtime=None, started_at=None, claims_root=None):
    rt = runtime if runtime is not None else Runtime()
    started = rt.clock() if started_at is None else started_at
    deadline = started+ctx['plan']['batch_wall_seconds']
    require(ctx.get('authorized') is True, 'APPROVAL_REQUIRED')
    out = Path(output).resolve()
    require(out.is_relative_to((HERE/'results').resolve()) and not out.exists(), 'NEW_BATCH_OUTPUT_REQUIRED')
    out.mkdir(parents=True)
    report = {'state': 'RUNNING', 'plan_sha256': ctx['plan_sha256'],
              'input_sha256': ctx['plan']['common_input_sha256'],
              'methods': [], 'posts': [], 'not_run': list(METHODS), 'retry': False,
              'simulation_only': ctx.get('simulation_only', False), 'method_attempts': 0, 'post_attempts': 0}
    claim = None; claim_created = False
    try:
        verify_sources(ctx['plan']); verify_input(ctx)
        gate = host_gate(rt.probe(ROOT)); save(out/'host_prelaunch.json', gate)
        require(gate['passed'], 'HOST_RESOURCE_GATE_FAILED')
        require(rt.clock() < deadline, 'BATCH_WALL_LIMIT_BEFORE_CLAIM')
        claim = (Path(claims_root) if claims_root is not None else HERE/'claims')/(ctx['plan_sha256']+'.json')
        if claims_root is not None:
            require(ctx.get('simulation_only') is True, 'CUSTOM_CLAIM_ROOT_IS_TEST_ONLY')
        save(claim, {'plan_sha256': ctx['plan_sha256'], 'input_sha256': ctx['plan']['common_input_sha256'],
                     'batch_output': str(out), 'authorization_sha256': sha(ctx['authorization_path'])})
        claim_created = True
        for job in ctx['plan']['jobs']:
            require(rt.clock() < deadline, 'BATCH_WALL_LIMIT')
            verify_sources(ctx['plan'])
            gate = host_gate(rt.probe(ROOT)); save(out/('host_'+job['id']+'.json'), gate)
            require(gate['passed'], 'HOST_RESOURCE_GATE_FAILED')
            require(deadline-rt.clock() >= job['process_wall_seconds'], 'INSUFFICIENT_BATCH_TIME_NO_LAUNCH')
            report['method_attempts'] += 1
            report['not_run'].remove(job['id'])
            method = _run_slot(ctx, job, 'method', out, deadline, rt, claim)
            report['methods'].append(method)
            save(out/'ledger'/f"{len(report['methods']):02d}_method.json", method)
            require(method['execution_status'] in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_UNRESOLVED'),
                    'METHOD_ABNORMAL_STOP:'+method['execution_status'])
            if method['worker'].get('safe_witness_preserved'):
                report['post_attempts'] += 1
                post = _run_slot(ctx, job, 'post', out, deadline, rt, claim)
                report['posts'].append(post)
                require(post['execution_status'] in ('NORMAL_COMPLETION', 'POST_TIME_LIMIT_UNRESOLVED')
                        and post['worker'].get('post_state') in ('SAFE', 'UNRESOLVED'), 'POST_ABNORMAL_STOP')
        report['state'] = 'COMPLETE'
    except Exception as error:
        report.update(state='STOPPED', error=type(error).__name__+': '+str(error))
    slots = [out/'slots'/(mid+'__method') for mid in METHODS]
    report.update(batch_wall_s=rt.clock()-started, claim_created_here=claim_created,
        claims_consumed=claim_created, claim_already_exists=bool(claim is not None and claim.is_file() and not claim_created),
        method_process_launch_attempts=sum((p/'launch_attempt.json').is_file() for p in slots),
        method_worker_started=sum((p/'worker_started.json').is_file() for p in slots),
        method_lifecycle_entered=sum((p/'worker/method_call_started.json').is_file() for p in slots))
    save(out/'batch_result.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--authorization', required=True); p.add_argument('--output', required=True)
    args = p.parse_args()
    start = time.monotonic()
    ctx = load_context(args.plan, args.plan_sha256, args.authorization)
    result = run_batch(ctx, args.output, started_at=start)
    return 0 if result['state'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
