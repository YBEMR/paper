"""K173 one declared method slot; no post, retries or scientific fallback.

The CLI exposes only frozen declaration/slot/output identities.  The private
services hook is for non-scientific fake lifecycle tests and marks its records
ineligible for scientific admission.  Importing this file starts no method.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback


SCIENCE = Path(__file__).resolve().parent.parent
REPO = SCIENCE.parents[1]
PROTOCOL = 'K173-linked-ablation-single-slot-worker-v1'
METHOD_SECONDS = 300


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_new(path, value):
    """Exclusive evidence file; bounded publication retry is never a method retry."""
    path = Path(path)
    if path.exists():
        raise FileExistsError('Refusing to replace worker evidence: ' + str(path))
    pending = path.with_name(path.name + '.pending')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        stream.write('\n')
    end = time.monotonic() + 1.0
    while True:
        try:
            if path.exists():
                raise FileExistsError('Worker evidence appeared during publication: ' + str(path))
            os.rename(pending, path)
            return
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32) or time.monotonic() >= end:
                raise
            time.sleep(min(0.02, max(0.0, end - time.monotonic())))


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str), flush=True)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _environment():
    packages = {}
    for name in ('numpy', 'scipy'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {'python_executable': str(Path(sys.executable).resolve()),
        'python_version': sys.version, 'platform': platform.platform(),
        'packages': packages, 'pid': os.getpid(),
        'thread_environment': {name: os.environ.get(name) for name in
            ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}}


def _native_archival(method_folder):
    """Copy raw cleanup/session evidence only; this is not an isolation verdict."""
    records = {}
    for name in ('session.json', 'closed.json', 'ready.json'):
        path = method_folder / 'matlab' / name
        if path.is_file():
            try:
                records[name] = {'path': str(path), 'sha256': _sha(path), 'raw': _read(path)}
            except Exception as error:
                records[name] = {'path': str(path), 'archival_error': repr(error)}
    return {'records': records, 'scope': 'raw original worker files; no new process-isolation approval'}


def _source_check(declaration, repo):
    failures = []
    for field in ('source_sha256', 'frozen_dependency_sha256', 'protected_archive_sha256'):
        for name, expected in declaration[field].items():
            path = (repo / name).resolve()
            path.relative_to(repo)
            if not path.is_file() or _sha(path) != expected:
                failures.append(name)
    return {'passed': not failures, 'mismatches': failures,
            'source_count': len(declaration['source_sha256']),
            'dependency_count': len(declaration['frozen_dependency_sha256']),
            'protected_archive_count': len(declaration['protected_archive_sha256'])}


def run_worker(declaration_path, slot_id, out, *, _services=None):
    """Run one fresh entry; return code 0 means saved and reviewable, never SAFE.

    ``_services`` is inaccessible through CLI.  Fake tests can replace the
    common budget class, module importer, registry and environment observer;
    every such result is explicitly NOT_SCIENTIFIC and must fail real admission.
    """
    services = {} if _services is None else dict(_services)
    if set(services) - {'budget_class', 'import_module', 'registry', 'clock', 'environment'}:
        raise ValueError('Unknown private fake service')
    fake = _services is not None
    clock = services.get('clock', time.monotonic)
    importer = services.get('import_module', importlib.import_module)
    declaration_path, out = Path(declaration_path).resolve(), Path(out).resolve()
    if str(SCIENCE) not in sys.path:
        sys.path.insert(0, str(SCIENCE))
    bootstrap_start = clock()
    budget_class = services.get('budget_class')
    if budget_class is None:
        # Identical common support imports for A/B/C. No selected arm is imported.
        budget_class = importlib.import_module('timing').MethodBudget
    bootstrap_end = clock()
    root_start = clock()
    budget = budget_class(METHOD_SECONDS, clock=clock)
    budget.start, budget.deadline = root_start, root_start + METHOD_SECONDS
    identity = {'protocol': PROTOCOL, 'slot_id': slot_id,
        'declaration_path': str(declaration_path), 'out': str(out),
        'not_scientific': fake, 'scientific_admission_eligible': not fake,
        'input_verified': False, 'source_verified': False, 'environment_verified': False,
        'fresh_input_calls': 0, 'worker_root_start_s': budget.start,
        'worker_root_deadline_s': budget.deadline, 'limit_s': METHOD_SECONDS,
        'budget_identity': None,
        'clock_policy': 'common support imports outside root and separately measured; selected arm imports and all case work inside one root',
        'common_support_import_start_s': bootstrap_start,
        'common_support_import_end_s': bootstrap_end,
        'common_support_import_elapsed_s': bootstrap_end - bootstrap_start}
    result = None
    errors = []
    declaration = slot = recipe = common = registry = None
    scientific_call_started = False
    method_started = method_stopped = None
    event_count = 0
    saved = False
    out_authorized = False
    method_folder = out / 'method'
    worker_started_utc = _now()
    try:
        budget.check()
        with budget.phase('worker_declaration_and_identity_validation'):
            registry = services.get('registry') or importer('linked_ablation_execution.registry')
            declaration = registry.load_declaration(declaration_path)
            repo = Path(registry.REPO).resolve()
            expected_out = declaration_path.parent / 'calls' / slot_id
            if out != expected_out.resolve():
                raise ValueError('Worker output differs from frozen slot path')
            out_authorized = True
            slot = registry.slot_spec(declaration, slot_id)
            case = registry.case_spec(declaration, slot['case_id'])
            common, recipe = case['common'], case['recipes'][slot['variant']]
            if declaration['budgets']['method_s'] != METHOD_SECONDS or slot['method_seconds'] != METHOD_SECONDS:
                raise ValueError('Worker root budget differs from the frozen 300 seconds')
            out.mkdir(parents=True, exist_ok=True)
            if method_folder.exists() or any((out / name).exists() for name in (
                    'worker_started.json', 'wrapper_raw_result.json', 'result.json',
                    'worker_return.json', 'worker_identity.json', 'input_config.json', 'input_instance.json')):
                raise FileExistsError('This slot was already started; no retry')
            identity.update(case_id=slot['case_id'], variant=slot['variant'],
                declaration_sha256=_sha(declaration_path), recipe_sha256=_canonical(recipe),
                source_manifest_sha256=_canonical(declaration['source_sha256']))
            global_claim_path = Path(registry.GLOBAL_CLAIM)
            slot_claim_path = declaration_path.parent / 'claims' / (slot_id + '.json')
            global_claim, slot_claim = _read(global_claim_path), _read(slot_claim_path)
            if (global_claim.get('protocol') != registry.PROTOCOL
                    or global_claim.get('declaration_sha256') != identity['declaration_sha256']
                    or global_claim.get('no_retry') is not True
                    or global_claim.get('call_limit') != 6
                    or global_claim.get('method_seconds_limit') != 1800
                    or global_claim.get('post_calls_limit') != 6
                    or global_claim.get('post_seconds_limit') != 360):
                raise ValueError('Batch once-only authorization claim mismatch')
            if (any(slot_claim.get(k) != slot[k] for k in (
                    'slot_id', 'case_id', 'variant', 'ordinal', 'method_seconds', 'post_seconds_max'))
                    or slot_claim.get('protocol') != registry.PROTOCOL
                    or slot_claim.get('declaration_sha256') != identity['declaration_sha256']
                    or slot_claim.get('state') != 'CONSUMED_BEFORE_LAUNCH'
                    or slot_claim.get('no_retry') is not True):
                raise ValueError('Slot was not consumed exactly once before launch')
            global_end = global_claim.get('calendar_deadline_monotonic')
            slot_end = slot_claim.get('slot_deadline_monotonic')
            if (any(isinstance(t, bool) or not isinstance(t, (int, float))
                    or not math.isfinite(t) for t in (global_end, slot_end))
                    or budget.deadline > min(global_end, slot_end)):
                raise ValueError('Full declared method cannot fit the remaining calendar/slot window')
            identity.update(global_claim_sha256=_sha(global_claim_path),
                slot_claim_sha256=_sha(slot_claim_path),
                global_calendar_deadline_monotonic=global_end, slot_deadline_monotonic=slot_end)
            source_before = _source_check(declaration, repo)
            identity['source_before'] = source_before
            if not source_before['passed']:
                raise ValueError('Frozen source/dependency mismatch before entry')
            identity['source_verified'] = True
            observed = (services.get('environment') or _environment)()
            frozen_env = declaration['environment']
            matlab_executable = Path(frozen_env['matlab_executable']).resolve()
            observed['matlab_executable'] = str(matlab_executable)
            observed['matlab_executable_sha256'] = _sha(matlab_executable)
            if (Path(observed['python_executable']).resolve() != Path(frozen_env['python_executable']).resolve()
                    or observed['python_version'] != frozen_env['python_version']
                    or observed['platform'] != frozen_env['platform']
                    or observed['matlab_executable_sha256'] != frozen_env['matlab_executable_sha256']):
                raise ValueError('Frozen Python/platform environment changed')
            identity.update(environment_verified=True, environment_observed=observed,
                            environment_frozen=deepcopy(frozen_env))
            _write_new(out / 'worker_started.json', {
                'protocol': PROTOCOL, 'slot_id': slot_id, 'pid': os.getpid(),
                'started_utc': worker_started_utc, 'declaration_sha256': identity['declaration_sha256'],
                'not_scientific': fake, 'root_start_s': budget.start,
                'root_deadline_s': budget.deadline, 'no_retry': True})
        _emit({'event': 'START', 'slot_id': slot_id, 'case_id': slot['case_id'],
               'variant': slot['variant'], 'root_limit_s': METHOD_SECONDS, 'not_scientific': fake})
        budget.check()
        with budget.phase('worker_selected_arm_imports'):
            arm = importer(recipe['entry_module'])
            bridge = importer('matlab_bridge')
            inputs = importer('p0_batch.run_p0')
            if Path(bridge.DEFAULT_MATLAB).resolve() != matlab_executable:
                raise ValueError('Original session default MATLAB differs from the frozen executable')
            entry = getattr(arm, recipe['entry_function'])
            session_factory = partial(bridge.MatlabSession, cut_max_iterations=10)

        def loader(active_budget):
            if active_budget is not budget or identity['fresh_input_calls']:
                raise ValueError('Input loader must be called exactly once on the same root')
            identity['fresh_input_calls'] += 1
            raw, config, instance = inputs.fresh_input(slot['case_id'], active_budget)
            actual = {'raw_config_sha256': _canonical(raw), 'config_sha256': _canonical(config),
                      'input_sha256': _canonical(instance)}
            identity.update(actual)
            identity['input_verified'] = (actual['config_sha256'] == common['config_sha256']
                                          and actual['input_sha256'] == common['input_sha256'])
            if not identity['input_verified']:
                raise ValueError('Billed fresh input/config differs from frozen P0 identity')
            with budget.phase('worker_input_evidence_checkpoint'):
                _write_new(out / 'input_config.json', config)
                _write_new(out / 'input_instance.json', instance)
            budget.check()
            return config, instance

        def observer(current_result, update):
            nonlocal event_count
            # No new assessment/energy calculation: only an original full commit.
            if (update.get('safe_upper_bound_J') is None
                    or update.get('safe_upper_bound_J') != current_result.get('safe_upper_bound_J')):
                raise ValueError('Observer does not match the published complete SAFE generation')
            event_count += 1
            event = {'event': 'SAFE_AGGREGATE_UPDATE', 'slot_id': slot_id,
                'index': event_count, 'phase_index': update.get('phase_index'),
                'committed_at_s': update.get('committed_at_s'),
                'observed_at_s': budget.elapsed, 'safe_upper_bound_J': update['safe_upper_bound_J'],
                'update': deepcopy(update)}
            with (out / 'observer_updates.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False, default=str) + '\n')
            _emit({k: event[k] for k in ('event', 'slot_id', 'index', 'phase_index',
                                       'committed_at_s', 'safe_upper_bound_J')})

        budget.check()
        method_started = clock()
        scientific_call_started = True
        result = entry(loader, method_folder, **deepcopy(recipe['kwargs']),
            budget=budget, clock=budget.clock, session_factory=session_factory,
            on_global_update=observer)
        method_stopped = clock()
        if not isinstance(result, dict):
            raise TypeError('Scientific entry did not return its original result object')
        # Save returned physical evidence first.  No cutoff re-check can erase
        # an already completed original SAFE; these copies do not form new U.
        _write_new(out / 'wrapper_raw_result.json', result)
        _write_new(out / 'result.json', result)
        saved = True
    except BaseException as error:
        if method_started is not None and method_stopped is None:
            method_stopped = clock()
        errors.append({'exception_type': type(error).__name__, 'message': str(error),
            'traceback': traceback.format_exc(),
            'matlab_cleanup': deepcopy(getattr(error, 'matlab_cleanup', None)),
            'matlab_startup_metadata': deepcopy(getattr(error, 'matlab_startup_metadata', None))})
    # Archival/identity inspection only after the method; never a solver,
    # candidate recovery, replacement U or post-budget thermal evaluation.
    archival_start = clock()
    if not out_authorized or not out.is_dir():
        _emit({'event': 'WORKER_RETURN', 'slot_id': slot_id, 'passed': False,
               'state': 'WORKER_PREPARATION_FAILED', 'errors': errors})
        return 2
    try:
        budget_id = deepcopy(getattr(budget, '_scene_adapter_budget_identity', None))
        if isinstance(result, dict):
            condition_budget = (result.get('condition') or {}).get('budget_identity')
            aggregate_budget = ((result.get('aggregation') or {}).get('identity') or {}).get('budget')
            reference = condition_budget or aggregate_budget
            if reference is not None:
                if budget_id is not None and budget_id != reference:
                    raise ValueError('Original method receipt budget identity differs from the root object')
                budget_id = deepcopy(reference)
        identity['budget_identity'] = budget_id
        if declaration is not None and registry is not None:
            source_after = _source_check(declaration, Path(registry.REPO).resolve())
            identity['source_after_return'] = source_after
            identity['source_verified'] = identity['source_verified'] and source_after['passed']
        identity.update(observer_update_count=event_count,
            original_result_saved=saved, scientific_call_started=scientific_call_started,
            method_dispatch_started_s=method_started, method_dispatch_stopped_s=method_stopped,
            method_dispatch_elapsed_s=None if method_started is None or method_stopped is None
                                      else method_stopped - method_started,
            original_method_timing=None if result is None else deepcopy(result.get('timing')),
            wrapper_root_elapsed_at_method_return_s=None if method_stopped is None
                                                     else method_stopped - budget.start,
            wrapper_archival_scope='copy/identity/source inspection only; no new scientific evidence',
            wrapper_archival_started_s=archival_start)
        _write_new(out / 'worker_identity.json', identity)
        receipt = {'protocol': PROTOCOL, 'state': 'RETURNED' if saved and not errors else 'WORKER_FAILED',
            'passed': bool(saved and not errors), 'not_scientific': fake,
            'scientific_call_started': scientific_call_started, 'slot_id': slot_id,
            'case_id': identity.get('case_id'), 'variant': identity.get('variant'),
            'out': str(out), 'method_workdir': str(method_folder),
            'declaration_sha256': identity.get('declaration_sha256'),
            'identity_sha256': _sha(out / 'worker_identity.json'),
            'result_sha256': _sha(out / 'result.json') if (out / 'result.json').is_file() else None,
            'wrapper_raw_result_sha256': _sha(out / 'wrapper_raw_result.json')
                                       if (out / 'wrapper_raw_result.json').is_file() else None,
            'method_started_s': method_started, 'method_stopped_s': method_stopped,
            'method_elapsed_s': identity['method_dispatch_elapsed_s'],
            'worker_root_start_s': budget.start, 'worker_root_deadline_s': budget.deadline,
            'worker_started_utc': worker_started_utc, 'returned_utc': _now(),
            'wrapper_archival_elapsed_s': clock() - archival_start,
            'native_archival': _native_archival(method_folder), 'errors': errors,
            'exit_zero_scope': 'files saved and reviewable only; not scientific SAFE or native cleanup approval',
            'no_retry': True, 'new_post_or_thermal_evidence': False}
        _write_new(out / 'worker_return.json', receipt)
        _emit({'event': 'WORKER_RETURN', 'slot_id': slot_id, 'state': receipt['state'],
            'passed': receipt['passed'], 'not_scientific': fake,
            'scientific_state': None if result is None else result.get('state'),
            'errors': len(errors)})
        return 0 if receipt['passed'] else 2
    except BaseException as error:
        _emit({'event': 'WORKER_RETURN', 'slot_id': slot_id, 'passed': False,
            'state': 'WORKER_ARCHIVE_FAILED', 'error': repr(error),
            'prior_scientific_files_preserved': saved})
        return 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--slot-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    return run_worker(args.declaration, args.slot_id, args.out)


if __name__ == '__main__':
    raise SystemExit(main())
