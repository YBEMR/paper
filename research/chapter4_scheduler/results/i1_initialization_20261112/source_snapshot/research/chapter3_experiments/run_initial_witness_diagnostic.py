"""One seed-only original-scale diagnostic, without a MATLAB solver call.

The fixed 180 s wall budget includes input read, the unchanged complete MILP
build, bounded seed construction, continuous evaluation and numerical x0
admission. No optimization, candidate repair, retry or budget extension.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import numpy as np

from build_observer import BuildObserver
from initial_point import prepare_initial_witness
from inputs import build_instance, load_config
from milp import build_model
from thermal import Exhausted
from timing import MethodBudget

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LIMIT_SECONDS = 180
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
CORE_NAMES = ['config_v01.json', 'inputs.py', 'schedules.py', 'thermal.py',
              'milp.py', 'milp_coefficients.py', 'initial_schedule.py',
              'initial_point.py', 'matlab_bridge.py', 'solve_model.m',
              'timing.py', 'build_observer.py']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_paths():
    paths = [HERE/name for name in CORE_NAMES]
    paths += [HERE.parent/'v1_evaluator/interval.py', Path(__file__).resolve(),
              HERE/'precheck_initial_witness_diagnostic.py',
              HERE/'run_initial_point_precheck.py']
    return {path.relative_to(REPO).as_posix(): path for path in paths}


def source_hashes():
    return {name: digest(path) for name, path in source_paths().items()}


def save(path, value):
    """Archive formed evidence atomically; serialization never repeats work."""
    def encode(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)
    path = Path(path)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False, default=encode)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def _record(path):
    path = Path(path)
    raw = path.read_bytes()
    return path, json.loads(raw.decode('utf-8-sig')), hashlib.sha256(raw).hexdigest()


def validate_core_precheck(path):
    path, record, sha = _record(path)
    checks = record.get('checks', [])
    native = 'native/one_stage_same_180s_method_budget_and_continuous_safe_receipt'
    if (record.get('passed') is not True or record.get('count') != 109
            or len(checks) != 109 or not all(c.get('passed') is True for c in checks)
            or not any(c.get('name') == native for c in checks)
            or record.get('flags') != FLAGS):
        raise ValueError('Complete passing initial-point precheck with native evidence is required')
    required = [HERE/name for name in CORE_NAMES]+[HERE.parent/'v1_evaluator/interval.py',
                                                  HERE/'run_initial_point_precheck.py']
    recorded_sources = {name.replace('\\', '/'): value for name, value
                        in record.get('source_sha256', {}).items()}
    verified = {}
    for source in required:
        key = source.relative_to(HERE.parent).as_posix()
        current = digest(source)
        if recorded_sources.get(key) != current:
            raise ValueError('Core precheck source mismatch: '+key)
        verified[source.relative_to(REPO).as_posix()] = current
    if digest(HERE/'config_v01.json') != CONFIG_SHA:
        raise ValueError('Frozen input hash mismatch')
    return {'path': str(path.resolve()), 'sha256': sha, 'count': len(checks),
            'verified_sources': verified}


def validate_entry_precheck(path):
    path, record, sha = _record(path)
    checks = record.get('checks', [])
    if (record.get('passed') is not True or not checks
            or record.get('count') != len(checks)
            or not all(c.get('passed') is True for c in checks)
            or record.get('seconds') != LIMIT_SECONDS or record.get('flags') != FLAGS
            or record.get('original_benchmark_built_or_solved') is not False
            or record.get('integer_solver_calls') != 0):
        raise ValueError('Complete passing seed-diagnostic entry precheck is required')
    if record.get('source_sha256') != source_hashes():
        raise ValueError('Seed-diagnostic precheck source mismatch')
    return {'path': str(path.resolve()), 'sha256': sha, 'count': len(checks),
            'source_sha256': record['source_sha256']}


def validate_support_prechecks():
    """Reuse existing current interface evidence, respecting each schema."""
    required = [('initial_bridge_precheck02', 19), ('method_precheck19', 29),
                ('bridge_budget_precheck07', 9), ('milp_precheck18', 82)]
    verified = []
    for directory, count in required:
        path, record, sha = _record(HERE/'results'/directory/'checks.json')
        checks = record.get('checks', [])
        if len(checks) != count or not all(c.get('passed') is True
                if 'passed' in c else c.get('status') == 'PASS' for c in checks):
            raise ValueError('Incomplete support precheck: '+directory)
        passed = record.get('passed')
        if not (passed is True or (type(passed) is int and passed == count)):
            raise ValueError('Failed support precheck: '+directory)
        for name, sha_source in record.get('source_sha256', {}).items():
            norm = Path(name.replace('\\', '/'))
            choices = [norm, REPO/norm, HERE.parent/norm, HERE/norm,
                       HERE.parent/'v1_evaluator'/norm]
            source = next((p for p in choices if p.is_file()), None)
            if source is None or digest(source) != sha_source:
                raise ValueError('Support precheck source mismatch: '+name)
        verified.append({'path': str(path.resolve()), 'sha256': sha, 'count': count})
    return verified


def claim_original_run(precheck_path, out):
    claim = Path(precheck_path).parent/'original_seed_run_claim.json'
    with claim.open('x', encoding='utf-8') as stream:
        json.dump({'problem_id': 'base__R1', 'seconds': LIMIT_SECONDS,
                   'out': str(Path(out).resolve()), 'flags': FLAGS,
                   'source_sha256': source_hashes(), 'retries': 0,
                   'integer_solver_calls': 0, 'formal_comparison': False}, stream, indent=2)
    return claim


def execute_seed_diagnostic(input_loader, out, *, seconds=LIMIT_SECONDS,
                            clock=time.monotonic, model_builder=build_model,
                            prepare=prepare_initial_witness, prerequisites=None):
    """One invocation. Injected collaborators are for correctness fixtures only."""
    budget = MethodBudget(seconds, clock=clock)  # before case I/O
    out = Path(out)
    if out.exists():
        raise FileExistsError('Invocation directory already exists: '+str(out))
    out.mkdir(parents=True, exist_ok=False)
    result = {'state': 'UNRESOLVED', 'reason': None, 'point_ready': False,
              'model_complete': False, 'matrix_complete': False,
              'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'initialisation': None, 'x0_metadata': None,
              'matlab_actual_acceptance': 'NOT_TESTED',
              'integer_solver_entered': False, 'solver_request_attempts': 0,
              'independently_proven_optimal': False,
              'independently_proven_infeasible': False,
              'remaining_domain': 'retained', 'formal_comparison': False,
              'flags': dict(FLAGS), 'prerequisites': prerequisites}
    config = instance = model = observer = vector = None
    stage = 'input_read_and_expansion'
    try:
        with budget.phase(stage):
            config, instance = input_loader(budget)
        budget.check()
        result['problem_id'] = instance['id']
        observer = BuildObserver(budget, out/'build_progress.jsonl')
        stage = 'model_construction'
        with budget.phase(stage):
            model = model_builder(instance, config, budget=budget, progress=observer, **FLAGS)
            observer.finish('MODEL_CONSTRUCTED')
        budget.check()
        result['model_complete'] = True
        result['model_completed_at_s'] = budget.elapsed
        stage = 'initial_witness_and_point'
        initial = prepare(model, config['accuracy_targets'], budget)
        # Commit already formed receipts before checking expiry at reception.
        result['initialisation'] = {k: v for k, v in initial.items() if k != 'x0'}
        witness = initial.get('witness')
        evaluation = witness.get('evaluation', {}) if witness else {}
        safe = (evaluation.get('state') == 'SAFE' and evaluation.get('rankable_energy')
                and evaluation.get('safe_upper_bound_J') is not None
                and evaluation.get('completed_at_elapsed_s', seconds) < seconds)
        if safe:
            result.update(state='SAFE', safe_candidate=witness['candidate'],
                          safe_upper_bound_J=evaluation['safe_upper_bound_J'],
                          evaluation=evaluation,
                          first_initial_safe_s=evaluation['completed_at_elapsed_s'])
        completion = initial.get('completion') or {}
        numerical = completion.get('numerical_acceptance') or {}
        result['matrix_complete'] = bool(numerical) and completion.get('completed_at_s', seconds) < seconds
        ready = (safe and initial.get('state') == 'SAFE_POINT_READY'
                 and initial.get('x0') is not None
                 and completion.get('state') == 'INITIAL_POINT_READY'
                 and completion.get('decoded_roundtrip') is True
                 and numerical.get('accepted_numerically') is True
                 and completion.get('completed_at_s', seconds) < seconds)
        if ready:
            vector = initial['x0']
            result.update(point_ready=True, reason='SAFE_POINT_READY_NUMERICAL_ONLY',
                          x0_metadata={'length': int(len(vector)),
                                       'completed_at_s': completion['completed_at_s'],
                                       'scope': 'Python full-row numerical admission only',
                                       'numerical_acceptance': numerical})
        else:
            result['reason'] = ('SAFE_WITNESS_POINT_UNRESOLVED' if safe
                                else initial.get('reason', 'NO_SAFE_INITIAL_WITNESS'))
    except Exhausted as error:
        result.update(reason=str(error), stop_stage=stage)
    except MemoryError:
        result.update(reason='RESOURCE_LIMIT', stop_stage=stage)
    except Exception as error:
        result.update(reason='INTERFACE_ERROR', stop_stage=stage,
                      error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    stopped = budget.elapsed
    result['stop_stage'] = result.get('stop_stage', stage)
    result['timing'] = budget.summary(stopped)
    result['budget_exhausted'] = stopped >= seconds
    result['original_benchmark_requested'] = bool(
        instance is not None and instance['id'] == 'base__R1')
    result['original_benchmark_built_or_solved'] = bool(
        result['original_benchmark_requested'] and result['model_complete'])
    # Archival only below: no reconstruction, row checks or thermal evaluation.
    archive_start = clock()
    if observer is not None:
        result['construction'] = (observer.snapshot() if observer.finished_at is not None
                                  else observer.finish('CONSTRUCTION_INTERRUPTED'))
    if model is not None and result['model_complete']:
        result['model_summary'] = model.summary()
    if config is not None:
        save(out/'input_config.json', config)
    if instance is not None:
        save(out/'input_instance.json', instance)
    if vector is not None:
        save(out/'initial_point_vector.json', vector)
        result['x0_metadata']['archive_sha256'] = digest(out/'initial_point_vector.json')
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
                             'scope': 'seed-only diagnostic, no MATLAB solver process'}
    result['timing']['postprocess_before_serialization_s'] = clock()-archive_start
    save(out/'result.json', result)
    return result


def run_original(out, core_precheck, entry_precheck):
    # Protocol validation and source snapshots are explicit preparation; the
    # timed method begins before the original case is read, never after build.
    prerequisites = {'core': validate_core_precheck(core_precheck),
                     'entry': validate_entry_precheck(entry_precheck),
                     'support': validate_support_prechecks()}
    out = Path(out)
    if out.exists():
        raise FileExistsError('Invocation directory already exists: '+str(out))
    before = source_hashes()
    claim = claim_original_run(entry_precheck, out)

    def loader(budget):
        config = load_config()
        return config, build_instance(config, 'base__R1', budget=budget)

    result = execute_seed_diagnostic(loader, out, prerequisites=prerequisites)
    archive_start = time.monotonic()
    after = source_hashes()
    save(out/'source_integrity.json', {'before': before, 'after': after,
                                     'unchanged': before == after,
                                     'original_claim': str(claim.resolve())})
    snapshot = out/'source_snapshot'
    for name, source in source_paths().items():
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    save(out/'source_archive_timing.json', {'seconds': time.monotonic()-archive_start,
                                          'scope': 'archival only, outside evidence cutoff'})
    print(json.dumps({key: result.get(key) for key in ('state', 'reason', 'point_ready',
          'safe_upper_bound_J', 'matlab_actual_acceptance', 'timing')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--core-precheck', type=Path, required=True)
    parser.add_argument('--entry-precheck', type=Path, required=True)
    args = parser.parse_args()
    run_original(args.out, args.core_precheck, args.entry_precheck)
