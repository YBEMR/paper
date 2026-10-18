"""Independent method lifecycle. No formal comparison entry is enabled here.

Input expansion, construction, MATLAB startup, export, solve, continuous
evaluation and feedback share one budget. Cleanup and report never run search.
The injected dependencies below are for deterministic timing prechecks only.
"""
import hashlib
from functools import partial
import json
from pathlib import Path
import platform
import shutil
import sys
import time

from build_observer import BuildObserver
from inputs import build_instance, load_config
from matlab_bridge import MatlabSession
from milp import build_model, solve_with_feedback
from thermal import Exhausted
from timing import MethodBudget

HERE = Path(__file__).resolve().parent
SOURCES = ['config_v01.json', 'inputs.py', 'schedules.py', 'thermal.py',
           'milp.py', 'milp_coefficients.py', 'matlab_bridge.py', 'solve_model.m',
           'build_observer.py', 'timing.py', 'method_runner.py', 'run_build_diagnostic.py',
           'run_method_diagnostic.py', 'diagnostic_search.py', 'run_extended_diagnostic.py']


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                    encoding='utf-8')


def execute_milp(input_loader, workdir, *, seconds=60, construct_only=True,
                 clock=time.monotonic, model_builder=build_model,
                 session_factory=MatlabSession, solve=solve_with_feedback):
    """One isolated invocation; input_loader(budget) returns (config, instance).

    The same interface can later wrap other methods. No candidate/cache/session
    can be supplied from a previous call. Precheck dependency injection is not
    an alternative research workload or a runtime algorithm choice.
    """
    budget = MethodBudget(float(seconds), clock=clock)  # before ANY case I/O
    result = {'state': 'UNRESOLVED', 'reason': None, 'safe_candidate': None,
              'safe_upper_bound_J': None, 'evaluation': None,
              'independently_proven_optimal': False,
              'independently_proven_infeasible': False,
              'remaining_domain': 'retained', 'formal_comparison': False,
              'construct_only': construct_only, 'model_complete': False,
              'matrix_complete': False, 'solver_started': False,
              'matlab_worker_ready': False,
              'solver_started_semantics': 'legacy field means MATLAB worker ready, not intlinprog entry'}
    session = model = observer = config = instance = None
    active_stage = 'invocation_setup'
    constructor_cleanup_s = 0.0
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(f'Invocation directory already exists: {workdir}')
    workdir.mkdir(parents=True, exist_ok=False)
    try:
        with budget.phase('input_read_and_expansion'):
            active_stage = 'input_read_and_expansion'
            config, instance = input_loader(budget)
        budget.check()
        result['problem_id'] = instance['id']
        observer = BuildObserver(budget, workdir/'build_progress.jsonl')
        with budget.phase('model_construction'):
            active_stage = 'model_construction'
            model = model_builder(instance, config, budget=budget, progress=observer)
            observer.finish('MODEL_CONSTRUCTED')
        budget.check()
        result['model_complete'] = True
        result['model_completed_at_s'] = budget.elapsed
        if construct_only:
            with budget.phase('matrix_export'):
                active_stage = 'matrix_export'
                exported = model.as_solver_dict()
            budget.check()
            result['matrix_complete'] = True
            result['matrix_completed_at_s'] = budget.elapsed
            result['matrix'] = {'shape': list(exported['A'].shape),
                                'nonzeros': int(exported['A'].nnz)}
            result.update(state='CONSTRUCTION_COMPLETE', reason='CONSTRUCT_ONLY_NO_SOLVE')
        else:
            with budget.phase('solver_startup'):
                active_stage = 'solver_startup'
                session = session_factory(workdir/'matlab', total_budget_s=budget.remaining,
                                          budget=budget)
            budget.check()
            result['solver_started'] = True
            result['matlab_worker_ready'] = True
            active_stage = 'candidate_search'
            solved = solve(model, session, config['accuracy_targets'], budget=budget)
            result.update(solved)
            # solve owns receipt preservation at an expiry boundary. Never
            # discard a SAFE/violation receipt merely because return is late.
        result['stop_stage'] = active_stage
    except Exhausted as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        result.update(reason=str(error), stop_stage=active_stage)
    except MemoryError:
        result.update(reason='RESOURCE_LIMIT', stop_stage=active_stage)
    except Exception as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        search_stopped_s = budget.elapsed-constructor_cleanup_s
        result.update(reason=('WALL_TIME_LIMIT' if search_stopped_s >= budget.seconds else 'INTERFACE_ERROR'),
                      error=f'{type(error).__name__}: {error}', stop_stage=active_stage)
    finally:
        stopped = budget.elapsed
        result['timing'] = budget.summary(stopped)
        result['timing']['startup_failure_cleanup_in_method_elapsed_s'] = constructor_cleanup_s
        result['timing']['method_elapsed_excluding_cleanup_s'] = max(0.0, stopped-constructor_cleanup_s)
        result['timing']['wall_until_constructor_cleanup_return_s'] = stopped
        result['timing']['method_elapsed_s'] = max(0.0, stopped-constructor_cleanup_s)
        result['timing']['deadline_overshoot_s'] = max(0.0, stopped-constructor_cleanup_s-budget.seconds)
        if constructor_cleanup_s:
            # A failed constructor cannot return a session to the finally
            # block. Its known internal cleanup is removed from phase cost.
            totals = result['timing']['phases_exclusive_s']
            totals['solver_startup'] = max(0.0, totals.get('solver_startup', 0)-constructor_cleanup_s)
            for frame in result['timing']['phase_records']:
                if frame['phase']=='solver_startup':
                    frame['startup_cleanup_inclusive_s'] = constructor_cleanup_s
                    frame['exclusive_s'] = max(0.0, frame['exclusive_s']-constructor_cleanup_s)
            result['timing']['unattributed_s'] = max(0.0, stopped-constructor_cleanup_s-sum(totals.values()))
        result['timing']['cleanup_s'] = constructor_cleanup_s
        cleanup_start = clock()
        if session is not None:
            try:
                session.close()
            except Exception as error:
                result['cleanup_error'] = f'{type(error).__name__}: {error}'
        result['timing']['cleanup_s'] += clock()-cleanup_start
        result['budget_exhausted'] = stopped-constructor_cleanup_s >= budget.seconds
        result['counted_energy_source'] = 'only complete independent evaluator receipt'
        result['callback_candidates_independently_thermal_checked'] = 'diagnostic' in result
        result['candidate_and_cache_shared_between_calls'] = False
        result['solver_request_attempts'] = getattr(session, 'counter', 0)
        rounds = result.get('rounds', [])
        known_solver_entries = [r.get('intlinprog_entered') for r in rounds]
        result['integer_solver_entered'] = (True if True in known_solver_entries else
            False if not result['solver_request_attempts'] or
                (known_solver_entries and all(v is False for v in known_solver_entries)) else None)
        result['integer_solver_entry_evidence'] = 'returned worker record only; null means unconfirmed'
        if result.get('diagnostic', {}).get('solver_entered_received_s') is not None:
            result['integer_solver_entered'] = True
            result['integer_solver_entry_evidence'] = 'in-budget immutable worker entry event received'
        completed_exports = [f for f in budget.records if f['phase']=='matrix_export'
                             and 'exception' not in f and f['end_s']<budget.seconds]
        if completed_exports:
            result['matrix_complete'] = True
            result['matrix_completed_at_s'] = completed_exports[-1]['end_s']

    # Post-budget code is archival only: no re-solve, re-evaluation or repair.
    report_start = clock()
    if observer is not None:
        status = 'MODEL_CONSTRUCTED' if result['model_complete'] else 'CONSTRUCTION_INTERRUPTED'
        result['construction'] = (observer.snapshot() if observer.finished_at is not None
                                  and result['model_complete'] else observer.finish(status))
    if model is not None and result['model_complete']:
        result['model_summary'] = model.summary()
    if config is not None:
        _save(workdir/'input_config.json', config)
    if instance is not None:
        _save(workdir/'input_instance.json', instance)
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
                             'scope': 'construction/full-method diagnostic or correctness precheck, not a formal comparison'}
    result['timing']['postprocess_before_serialization_s'] = clock()-report_start
    _save(workdir/'result.json', result)
    _save(workdir/'archive_timing.json', {
        'report_wall_s': clock()-report_start,
        'scope': 'serialization of existing evidence only; no new search evidence',
        'includes_own_file_write': False})
    return result


def run_milp_method(problem_id, workdir, *, config_path=None, construct_only=True,
                    diagnostic_seconds=60, relax_auxiliary_integrality=False,
                    strengthen_energy_lower_bounds=False):
    """One isolated 60 s diagnostic; full route is explicitly requested."""
    if diagnostic_seconds not in (60, 900):
        raise ValueError('Only existing 60 s and user-authorized 900 s diagnostic protocols')
    if diagnostic_seconds == 900 and (problem_id != 'base__R1' or construct_only):
        raise ValueError('900 s is only authorized for the complete original base__R1 diagnostic')
    config_path = Path(config_path) if config_path else HERE/'config_v01.json'
    source_paths = {name: HERE/name for name in SOURCES}
    source_paths['interval.py'] = HERE.parent/'v1_evaluator/interval.py'
    before_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for name, path in source_paths.items()}

    def loader(budget):
        config = load_config(config_path)
        if float(config['run_protocol']['wall_clock_budget_s']) != 60:
            raise ValueError('This diagnostic is fixed to the current 60 s protocol')
        return config, build_instance(config, problem_id, budget)

    solve = solve_with_feedback
    if diagnostic_seconds == 900:
        from diagnostic_search import solve_diagnostic
        solve = solve_diagnostic
    result = execute_milp(loader, workdir, seconds=diagnostic_seconds,
                          construct_only=construct_only, solve=solve,
                          model_builder=partial(build_model, fix_late_options=True,
                              aggregate_opp_locks=True,
                              relax_auxiliary_integrality=relax_auxiliary_integrality,
                              strengthen_energy_lower_bounds=strengthen_energy_lower_bounds))
    # Source snapshots are not algorithm inputs and are archived after stop.
    snapshot_started = time.monotonic()
    snapshot = Path(workdir)/'source_snapshot'
    snapshot.mkdir()
    hashes = {}
    for name, path in source_paths.items():
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copyfile(path, snapshot/name)
    _save(Path(workdir)/'source_hashes.json', hashes)
    _save(Path(workdir)/'source_integrity.json', {
        'before': before_hashes, 'after': hashes, 'match': before_hashes == hashes,
        'snapshot_scope': 'source archival outside method time, never a search input'})
    _save(Path(workdir)/'source_archive_timing.json', {
        'source_snapshot_and_hash_wall_s': time.monotonic()-snapshot_started,
        'scope': 'additional archival after result serialization; no new search evidence',
        'includes_own_file_write': False})
    return result
