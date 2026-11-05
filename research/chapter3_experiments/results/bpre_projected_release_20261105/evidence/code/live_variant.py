"""One online enhanced-HEFT seeded MILP variant, with one 600-second root.

prepare writes metadata only. run consumes one external claim and launches one
worker. Observation never decodes or evaluates candidates or feeds the recorder.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
REFERENCE_SHA256 = '66263b16bfaa3026e44aa8ea5462e3c6185cef9c2ad9479e6094c0ddaedb9f57'
SUBJECT_COMMIT = 'e0c4d2858e386e16348955f7c4f7f430a11fc2fd'
SCOPE = dict(method='online_heft_seeded_projected_milp', method_calls=1, method_seconds=600, post_calls=0, retries=0)
WATCHDOG_SECONDS = 705
REQUIRED_EXTERNAL_CODE = frozenset({'live_variant.py', 'run_logged.py', 'test_live_variant.py',
                                    'live_heft_initializer.py', 'test_live_heft_initializer.py',
                                    'native_projection.py','projection_admission.py','certified_projection.py',
                                    'projected_integration.py','bootstrap.py','test_projected_integration.py'})


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False, default=str)
        handle.write('\n')


def anchor():
    before = time.monotonic(); utc = datetime.now(timezone.utc).isoformat(); after = time.monotonic()
    return dict(monotonic_before=before, utc=utc, monotonic_after=after,
                meaning='UTC sampled between monotonic endpoints; not an exact publication timestamp')


def external_path(path):
    path = Path(path).resolve()
    require(path.is_relative_to(HERE) and path != HERE, 'PATH_MUST_BE_IN_VARIANT_DIRECTORY')
    return path


def external_code_hashes():
    """Bind every top-level external Python implementation/test, without import."""
    paths = sorted(HERE.glob('*.py'))
    require(REQUIRED_EXTERNAL_CODE <= {p.name for p in paths}, 'EXTERNAL_CODE_INVENTORY_INCOMPLETE')
    return {p.name: sha(external_path(p)) for p in paths}


def verify_external_contract(manifest):
    require(manifest.get('external_code_sha256') == external_code_hashes(), 'EXTERNAL_CODE_DRIFT')
    path = external_path(manifest['protocol_file'])
    require(path == HERE / 'protocol.json' and sha(path) == manifest['protocol_sha256'], 'PROTOCOL_BYTES_DRIFT')
    protocol = read(path)
    require(protocol.get('schema') == 'online-heft-milp-protocol-v1'
            and protocol.get('scope') == SCOPE
            and protocol.get('reference_subject_commit') == SUBJECT_COMMIT
            and protocol.get('reference_plan_sha256') == REFERENCE_SHA256,
            'VARIANT_PROTOCOL_DRIFT')
    cleanup = protocol.get('cleanup') or {}
    require(cleanup.get('grace_seconds') == 20 and cleanup.get('total_seconds') == 40
            and cleanup.get('watchdog_seconds') == WATCHDOG_SECONDS, 'PROTOCOL_CLEANUP_DRIFT')


def import_reference(repo):
    repo = Path(repo).resolve()
    sys.path.insert(0, str(repo)); sys.path.insert(0, str(repo / 'research/chapter3_experiments'))
    from research.chapter3_experiments import bpre_formal_entry as entry
    require(entry.base.ROOT == repo, 'IMPORTED_REPOSITORY_MISMATCH')
    return entry


def verify_reference(manifest, *, check_git):
    require(manifest['reference_plan_sha256'] == REFERENCE_SHA256
            and sha(manifest['reference_plan']) == REFERENCE_SHA256, 'REFERENCE_PLAN_DRIFT')
    require(manifest['subject_commit'] == SUBJECT_COMMIT, 'SUBJECT_DRIFT')
    entry = import_reference(manifest['repo'])
    entry.configure()  # Same B.pre paths, flags, equality adapter and native options.
    plan = read(manifest['reference_plan'])
    require(len(plan['source_sha256']) == 3185, 'FROZEN_MANIFEST_COUNT_DRIFT')
    entry.validate_plan(plan)
    entry.base.verify_sources(plan)
    require(str(Path(sys.executable).resolve()) == plan['python_executable']
            and sys.version == plan['python_version'], 'PYTHON_DRIFT')
    require(all(metadata.version(name) == version for name, version in plan['dependencies'].items()), 'DEPENDENCY_DRIFT')
    require(sha(plan['native_executable']) == plan['native_executable_sha256'], 'NATIVE_BINARY_DRIFT')
    if check_git:
        head = subprocess.check_output([manifest['git_executable'], 'rev-parse', 'HEAD'],
            cwd=manifest['repo'], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).decode().strip()
        require(head == SUBJECT_COMMIT, 'GIT_HEAD_DRIFT')
    return entry, plan


def verify_manifest(path, *, check_git):
    path = external_path(path)
    manifest = read(path)
    require(manifest.get('schema') == 'bpre-online-heft-milp-600-v1' and manifest.get('scope') == SCOPE,
            'VARIANT_SCOPE_DRIFT')
    require(manifest.get('watchdog_seconds') == WATCHDOG_SECONDS and manifest.get('cleanup_grace_seconds') == 20
            and manifest.get('cleanup_total_seconds') == 40, 'TIMING_POLICY_DRIFT')
    require(manifest.get('script') == str(SCRIPT) and manifest.get('script_sha256') == sha(SCRIPT), 'EXTERNAL_SCRIPT_DRIFT')
    verify_external_contract(manifest)
    external_path(manifest['authorization_file'])
    authorization = read(manifest['authorization_file'])
    require(sha(manifest['authorization_file']) == manifest['authorization_sha256'], 'AUTHORIZATION_BYTES_DRIFT')
    require(authorization.get('source') == 'USER_CURRENT_CONVERSATION'
            and authorization.get('scope') == SCOPE
            and isinstance(authorization.get('authorization_text'), str)
            and authorization['authorization_text'].strip(), 'ONCE_600_VARIANT_AUTHORIZATION_REQUIRED')
    for key in ('output', 'claim'):
        external_path(manifest[key])
    entry, plan = verify_reference(manifest, check_git=check_git)
    return manifest, entry, plan


def prepare(args):
    manifest_path, output, claim = map(external_path, (args.manifest, args.output, args.claim))
    require(not any(path.exists() for path in (manifest_path, output, claim)), 'NEW_DIAGNOSTIC_PATHS_REQUIRED')
    require(len({manifest_path, output, claim}) == 3, 'DISTINCT_DIAGNOSTIC_PATHS_REQUIRED')
    authorization = external_path(args.authorization_file)
    protocol = external_path(args.protocol_file)
    manifest = dict(schema='bpre-online-heft-milp-600-v1', scope=SCOPE,
        repo=str(Path(args.repo).resolve()), reference_plan=str(Path(args.reference_plan).resolve()),
        reference_plan_sha256=REFERENCE_SHA256, subject_commit=SUBJECT_COMMIT,
        git_executable=args.git, script=str(SCRIPT), script_sha256=sha(SCRIPT),
        authorization_file=str(authorization), authorization_sha256=sha(authorization),
        protocol_file=str(protocol), protocol_sha256=sha(protocol), external_code_sha256=external_code_hashes(),
        output=str(output), claim=str(claim), watchdog_seconds=WATCHDOG_SECONDS,
        cleanup_grace_seconds=20, cleanup_total_seconds=40,
        purpose='One online enhanced-HEFT seeded MILP variant; original baseline unchanged',
        reference_plan_use='Frozen science/input/options reference only; old seven-method authorization is not reused',
        late_observation='Read-only bytes/timing; never evaluate, replay or accept a late candidate',
        created_anchor=anchor())
    auth = read(authorization)
    require(auth.get('source') == 'USER_CURRENT_CONVERSATION' and auth.get('scope') == SCOPE
            and isinstance(auth.get('authorization_text'), str) and auth['authorization_text'].strip(),
            'ONCE_600_VARIANT_AUTHORIZATION_REQUIRED')
    verify_external_contract(manifest)
    verify_reference(manifest, check_git=True)
    save(manifest_path, manifest)
    return dict(state='PREPARED_ONLY', manifest=str(manifest_path), sha256=sha(manifest_path), method_started=False)


def configure_variant(entry):
    """Keep original 600-second B.pre validator, audits and repaired session."""
    entry.configure()
    require(entry.base.METHOD_SECONDS == 600 and entry.base.METHOD_WATCHDOG_SECONDS == WATCHDOG_SECONDS,
            'ORIGINAL_600_TIMING_BINDINGS_REQUIRED')
    require(entry.base.NATIVE_RESPONSE_VALIDATOR is entry.prior.validate_response_600,
            'ORIGINAL_600_NATIVE_VALIDATOR_REQUIRED')
    require(entry.base.run_whole is entry.prior.run_whole
            and entry.base.native_session_factory is entry.repaired.native_session_factory,
            'ORIGINAL_600_LIFECYCLE_REQUIRED')


def variant_outcome(raw, audit, safe, context):
    """Describe existing evidence; never relabel a numerical/technical failure."""
    source = raw.get('safe_solution_source')
    label = ('online_enhanced_heft_only' if safe.get('preserved') and source == 'initial_constructor'
             else 'online_heft_seeded_milp_candidate' if safe.get('preserved') and source == 'MILP_candidate'
             else 'no_final_admitted_safe_witness')
    return dict(variant=SCOPE['method'], outcome=label,
        original_safe_solution_source=source, final_safe_preserved=safe.get('preserved') is True,
        usable_U_J=safe.get('U_J'), original_audit_execution_status=audit['execution']['execution_status'],
        integer_solver_entered=raw.get('integer_solver_entered'),
        milp_improved_initial_upper_bound=raw.get('milp_improved_initial_upper_bound'),
        strict_energy_improvement_certified=raw.get('strict_energy_improvement_certified'),
        original_method_reason=raw.get('reason'), initializer_context_available=bool(context),
        initialization='This invocation online enhanced HEFT; no archived candidate input',
        failure_policy='Original audit status preserved even when an earlier SAFE witness survives',
        original_baseline_replaced=False, old_seven_method_authority_reused=False)


def observe(folder, deadline, seen, handle):
    """Read complete native publications; no science imports or candidate calls."""
    session = folder / 'worker' / 'method' / 'matlab'
    for pattern in ('request_*.event_*.json', 'request_*.response.json'):
        for path in sorted(session.glob(pattern)):
            try:
                before = path.stat(); data = path.read_bytes(); after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    continue
                value = json.loads(data.decode('utf-8-sig'))
                if not isinstance(value, dict):
                    continue
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            digest = hashlib.sha256(data).hexdigest()
            key = (str(path), digest)
            if key in seen:
                continue
            stamp = anchor(); seen.add(key)
            row = dict(path=str(path), sha256=digest, size_bytes=len(data), anchor=stamp,
                first_observed_after_deadline=stamp['monotonic_after'] >= deadline,
                scientific_deadline=deadline, used_for_evaluation=False, delivered_to_recorder=False,
                timing_scope='First complete read by external observer; actual publication time is not inferred')
            handle.write(json.dumps(row, ensure_ascii=False) + '\n'); handle.flush()


def worker(args):
    ticket_path = external_path(args.ticket); ticket = read(ticket_path)
    output = external_path(ticket['output'])
    require(ticket_path == output / 'ticket.json' and ticket['token'] == args.token, 'WORKER_TICKET_BINDING')
    manifest, entry, plan = verify_manifest(ticket['manifest'], check_git=False)
    require(ticket['manifest_sha256'] == sha(ticket['manifest']) and output == Path(manifest['output']), 'MANIFEST_BINDING')
    require(sha(manifest['claim']) == ticket['claim_sha256'], 'CLAIM_BINDING')
    claim = read(manifest['claim'])
    require(claim['manifest_sha256'] == ticket['manifest_sha256'] and claim['output'] == str(output)
            and claim['scope'] == SCOPE and claim['token'] == args.token, 'CLAIM_SCOPE')
    require(ticket.get('job') == {'id': 'whole_milp', 'method': 'whole_milp', 'seed': None,
                                  'variant': SCOPE['method']}, 'NATIVE_JOB_VARIANT_BINDING')
    origin, deadline = ticket['origin'], ticket['scientific_deadline']
    require(type(origin) in (int, float) and math.isfinite(origin) and deadline == origin + 600
            and origin <= time.monotonic() < deadline, 'ROOT_DEADLINE')
    from research.chapter3_method_entry_executor.monitor import PsutilProvider
    provider = PsutilProvider(); parent = provider.describe(os.getppid())
    require(parent.get('state') == 'ACTIVE' and [parent.get('pid'), parent.get('create_time')] == ticket['parent_identity'], 'PARENT_IDENTITY')
    while not (output / 'go.json').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    require((output / 'go.json').exists(), 'NO_MONITOR_HANDSHAKE')
    go = read(output / 'go.json'); own = provider.describe(os.getpid())
    require(go['ticket_sha256'] == sha(ticket_path)
            and go['worker_identity'] == [own.get('pid'), own.get('create_time')], 'WORKER_IDENTITY')
    configure_variant(entry)
    folder = output / 'worker'; folder.mkdir()
    result = dict(scope=SCOPE, manifest_sha256=sha(ticket['manifest']), ticket_sha256=sha(ticket_path),
                  start_anchor=anchor(), origin=origin, scientific_deadline=deadline,
                  state='UNRESOLVED', status='TECHNICAL_FAILURE')
    initializer_context = {}
    try:
        from live_heft_initializer import install_initializer
        instance = read(entry.base.ROOT / entry.base.INPUT)
        config = read(entry.base.ROOT / entry.base.CONFIG)
        from projected_integration import install_projection
        with install_projection(entry,folder), install_initializer(instance, config, folder / 'online_heft', origin=origin,
                                 deadline=deadline, audit_context=initializer_context):
            raw, audit = entry.base.run_whole(ticket, plan, folder)
        save(folder / 'raw_result.json', raw)
        from research.chapter3_method_entry_executor.common import inspect_safe_receipt
        from schedules import validate_schedule
        instance = read(entry.base.ROOT / entry.base.INPUT)
        safe = inspect_safe_receipt(instance, raw, 600)
        if safe['preserved']:
            require(validate_schedule(instance, safe['candidate'])['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'FINAL_SCHEDULE_INVALID')
        require((raw.get('safe_upper_bound_J') is None or safe['preserved'])
                and audit.get('usable_U_J') == safe.get('U_J'), 'FINAL_SAFE_ADMISSION')
        late_acceptance = [index for index, row in enumerate(raw.get('rounds', []))
                           if row.get('budget_valid') is False and row.get('accepted_for_evaluation') is True]
        require(not late_acceptance, 'LATE_ROUND_ACCEPTANCE')
        save(folder / 'no_late_admission.json', dict(method_seconds=600, invalid_late_acceptance_rounds=late_acceptance,
            final_safe_preserved=safe['preserved'], observer_evaluates_candidates=False, observer_delivers_to_recorder=False,
            scope='Original budget and receipt guards; no post-deadline physical evaluation or replay'))
        result.update(state=raw.get('state'), status=audit['execution']['execution_status'], safe=safe,
                      whole_audit=audit, method_reason=raw.get('reason'),
                      variant_outcome=variant_outcome(raw, audit, safe, initializer_context))
    except BaseException as error:
        result.update(error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
    finally:
        # This is archival only: no evaluation or attempt to repair the initializer.
        try:
            context_path = folder / 'initializer_context.json'
            save(context_path, initializer_context)
            result['initializer_context_archive'] = dict(path=str(context_path), sha256=sha(context_path))
        except BaseException as error:
            result.update(status='TECHNICAL_FAILURE', initializer_context=initializer_context,
                          initializer_archive_error=type(error).__name__ + ': ' + str(error))
    result.update(end_anchor=anchor(), elapsed_seconds=time.monotonic() - origin)
    save(folder / 'worker_result.json', result)
    return result


def run(args):
    started = anchor(); manifest_path = external_path(args.manifest)
    manifest, entry, plan = verify_manifest(manifest_path, check_git=True)
    output, claim_path = Path(manifest['output']), Path(manifest['claim'])
    require(not output.exists() and not claim_path.exists(), 'SINGLE_USE_DIAGNOSTIC_ALREADY_CONSUMED')
    from research.chapter3_method_entry_executor.monitor import ProcessMonitor, PsutilProvider, default_host_probe, host_gate
    probe = default_host_probe(entry.base.ROOT)
    require(host_gate(probe)['passed'], 'HOST_RESOURCE_GATE_FAILED')
    parent = PsutilProvider().describe(os.getpid())
    require(parent.get('state') == 'ACTIVE' and parent.get('create_time') is not None, 'PARENT_IDENTITY')
    origin = time.monotonic(); deadline = origin + 600; token = secrets.token_hex(24)
    save(claim_path, dict(manifest_sha256=sha(manifest_path), output=str(output), scope=SCOPE,
                         origin=origin, token=token, no_retry=True, anchor=anchor()))
    output.mkdir()
    save(output / 'host_prelaunch.json', probe)
    ticket = dict(output=str(output), manifest=str(manifest_path), manifest_sha256=sha(manifest_path),
        claim_sha256=sha(claim_path), token=token, origin=origin, scientific_deadline=deadline,
        parent_identity=[parent['pid'], parent['create_time']], job={'id': 'whole_milp', 'method': 'whole_milp', 'seed': None, 'variant': SCOPE['method']})
    save(output / 'ticket.json', ticket)
    command = [sys.executable, '-B', str(SCRIPT), 'worker', '--ticket', str(output / 'ticket.json'), '--token', token]
    record = dict(state='STARTING', scope=SCOPE, command_argv=command, cwd=str(HERE),
        controller_start_anchor=started, root_origin=origin, scientific_deadline=deadline,
        watchdog_deadline=origin + WATCHDOG_SECONDS, manifest_sha256=sha(manifest_path), observations='observations.jsonl',
        formal_comparison=False, variant=SCOPE['method'], original_baseline_replaced=False, post_calls=0, retries=0)
    save(output / 'controller_started.json', record)
    process = monitor = None; seen = set()
    with (output / 'worker_stdout.log').open('xb') as stdout, (output / 'observations.jsonl').open('x', encoding='utf-8') as observations:
        try:
            # Match the original controller: this per-job disk check and fresh
            # resource probe are charged after origin, before worker startup.
            entry.base.verify_sources(plan)
            job_probe = default_host_probe(entry.base.ROOT)
            save(output / 'host_whole_milp.json', job_probe)
            require(host_gate(job_probe)['passed'], 'PER_JOB_HOST_RESOURCE_GATE_FAILED')
            require(time.monotonic() < deadline, 'ROOT_EXHAUSTED_BEFORE_SPAWN')
            process = subprocess.Popen(command, cwd=str(HERE), stdout=stdout, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            monitor = ProcessMonitor(process.pid)
            require(monitor.root_identity is not None, 'ROOT_IDENTITY_UNVERIFIED')
            save(output / 'go.json', dict(ticket_sha256=sha(output / 'ticket.json'), worker_identity=list(monitor.root_identity)))
            while process.poll() is None and time.monotonic() < origin + WATCHDOG_SECONDS:
                monitor.sample(); observe(output, deadline, seen, observations); time.sleep(.05)
            if process.poll() is None:
                record['watchdog_fired'] = True
                record['watchdog_signals'] = monitor.terminate_owned(force=True)
            process.wait(timeout=10)
            record['returncode'] = process.returncode
            saved = output / 'worker' / 'worker_result.json'
            require(saved.is_file(), 'WORKER_RESULT_MISSING')
            if saved.exists():
                result = read(saved)
                require(result['manifest_sha256'] == sha(manifest_path)
                        and result['ticket_sha256'] == sha(output / 'ticket.json'), 'WORKER_RECEIPT_BINDING')
                record['worker'] = result
            record['state'] = 'COMPLETED' if process.returncode == 0 and not record.get('watchdog_fired') else 'FAILED'
        except BaseException as error:
            record.update(state='FAILED', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        finally:
            cleanup_errors = []
            def attempt(label, operation):
                try:
                    return operation()
                except BaseException as error:
                    cleanup_errors.append(dict(operation=label, error=type(error).__name__ + ': ' + str(error)))
                    return None
            if process is not None and process.poll() is None:
                try:
                    process.kill(); process.wait(timeout=10)
                    record['own_child_handle_closed'] = True
                except Exception as error:
                    record['own_child_handle_error'] = str(error)
            if monitor is not None:
                def original_cleanup_predicate():
                    from matlab_bridge import cleanup_is_complete
                    return cleanup_is_complete
                cleanup_is_complete = attempt('import_original_cleanup', original_cleanup_predicate)
                closed_paths = attempt('discover_native_closed_receipts',
                    lambda: sorted((output / 'worker').glob('**/closed.json')))
                native_receipts = []
                for path in closed_paths or []:
                    def admit_receipt(path=path):
                        closed = read(path)
                        identities = (closed.get('process_tree_verification') or {}).get('identities') or []
                        registration = monitor.register_identities(identities, source='this diagnostic original native close receipt') if identities else []
                        elapsed = closed.get('cleanup_wall_seconds')
                        return dict(path=str(path), sha256=sha(path), raw=closed,
                            original_cleanup_complete=bool(cleanup_is_complete and cleanup_is_complete(closed)),
                            registration=registration,
                            within_40_seconds=type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 40)
                    receipt = attempt('admit_native_receipt:' + str(path), admit_receipt)
                    if receipt is not None:
                        native_receipts.append(receipt)
                record['native_cleanup_receipts'] = native_receipts
                if attempt('monitor_cleanup_check', monitor.cleanup_verified) is not True:
                    record['supervisor_cleanup_signals'] = attempt('terminate_owned', lambda: monitor.terminate_owned(force=True))
                    until = min(time.monotonic() + 10, origin + WATCHDOG_SECONDS + 20)
                    while attempt('monitor_cleanup_confirmation', monitor.cleanup_verified) is False and time.monotonic() < until:
                        attempt('observe_cleanup', lambda: observe(output, deadline, seen, observations)); time.sleep(.05)
                attempt('monitor_final_sample', lambda: monitor.sample(force=True))
                record['monitor'] = attempt('monitor_summary', monitor.summary)
                attempt('save_memory_samples', lambda: save(output / 'memory_samples.json', monitor.samples))
                cleanup_ok = (record.get('monitor') or {}).get('cleanup_verified_observed_tree') is True and all(
                    row['original_cleanup_complete'] and row['within_40_seconds'] and all(row['registration']) for row in native_receipts)
                native_directory_exists = attempt('native_session_marker', lambda: (output / 'worker' / 'method' / 'matlab').exists())
                if native_directory_exists is not False and not native_receipts:
                    cleanup_ok = False
                    record['missing_native_cleanup_receipt'] = True
                record['cleanup_ok'] = cleanup_ok
                if not cleanup_ok:
                    record['state'] = 'CLEANUP_FAILURE'
            else:
                record['state'] = 'FAILED'
            attempt('terminal_observation', lambda: observe(output, deadline, seen, observations))
            record['cleanup_errors'] = cleanup_errors
            if cleanup_errors or record.get('own_child_handle_error'):
                record['state'] = 'CLEANUP_FAILURE'
    record.update(end_anchor=anchor(), elapsed_from_root_seconds=time.monotonic() - origin,
                  observations_count=len(seen))
    try:
        record['host_after'] = default_host_probe(entry.base.ROOT)
    except BaseException as error:
        record['host_after_error'] = type(error).__name__ + ': ' + str(error)
    try:
        save(output / 'controller_result.json', record)
    except BaseException as error:
        record.update(state='CLEANUP_FAILURE', terminal_write_error=type(error).__name__ + ': ' + str(error))
        print(json.dumps({'terminal_write_failed_record': record}, ensure_ascii=False, default=str), flush=True)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    for name in ('repo', 'reference-plan', 'authorization-file', 'protocol-file', 'manifest', 'output', 'claim'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--git', default='<LOCAL_PATH>/git.exe')
    p = sub.add_parser('run'); p.add_argument('--manifest', required=True)
    p = sub.add_parser('worker'); p.add_argument('--ticket', required=True); p.add_argument('--token', required=True)
    args = parser.parse_args(argv)
    result = {'prepare': prepare, 'run': run, 'worker': worker}[args.action](args)
    print(json.dumps({key: result.get(key) for key in ('state', 'status', 'manifest', 'sha256', 'error')}, ensure_ascii=False), flush=True)
    normal = ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
    return 0 if (args.action == 'prepare' or (args.action == 'worker' and result.get('status') in normal)
                 or (args.action == 'run' and result.get('state') == 'COMPLETED')) else 2


if __name__ == '__main__':
    raise SystemExit(main())
