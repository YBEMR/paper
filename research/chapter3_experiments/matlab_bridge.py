"""R2023b intlinprog transport, not a proof engine.

One worker process can serve independent small models.  Its lifetime is a
precheck guard, not an experimental method budget.  Each solve has a separate
external deadline; late results are retained only as diagnostics.  A method
session binds the caller's absolute deadline before startup, so repeated solves
never replenish model construction, transport, or evaluation time.
No incumbent, constraint, or cache is shared between solve requests.
The worker fixes IntegerPreprocess='none' after the isolated small-model
compatibility check in results/milp_numeric_diagnostic04. Other gap/tolerance
settings are unchanged; this neither relaxes the model nor certifies bounds.
"""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from scipy import sparse
from scipy.io import savemat


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_MATLAB = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe')


def _json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


class PublicationTimeout(TimeoutError):
    def __init__(self, path, diagnostics):
        super().__init__(f'No complete readable publication within deadline: {path}')
        self.diagnostics = diagnostics


class WorkerExited(RuntimeError):
    def __init__(self, returncode, diagnostics):
        super().__init__(f'MATLAB worker exited before publication, code {returncode}')
        self.returncode = returncode
        self.diagnostics = diagnostics


def _read_json_until(path, deadline, clock=time.monotonic, process=None,
                     sleep=time.sleep, on_poll=None):
    """Wait for a complete readable message without moving the deadline.

    Existence alone is insufficient on Windows: publication or a transient
    file lock can make the name visible before Python can read it.  A result
    is formed only after reading and decoding the full message inside the
    original deadline.  Diagnostics retain retries rather than hiding them.
    """
    diagnostics = {'attempts': 0, 'transient_read_errors': {}, 'last_read_error': None}
    while True:
        if clock() >= deadline:
            raise PublicationTimeout(path, diagnostics)
        if on_poll is not None:
            on_poll()
            if clock() >= deadline:
                raise PublicationTimeout(path, diagnostics)
        diagnostics['attempts'] += 1
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, PermissionError, json.JSONDecodeError,
                UnicodeDecodeError) as exc:
            name = type(exc).__name__
            diagnostics['transient_read_errors'][name] = (
                diagnostics['transient_read_errors'].get(name, 0) + 1)
            diagnostics['last_read_error'] = f'{name}: {exc}'
            if isinstance(exc, FileNotFoundError) and process is not None:
                returncode = process.poll()
                if returncode is not None:
                    raise WorkerExited(returncode, diagnostics) from exc
            sleep(min(.005, max(0.0, deadline - clock())))
            continue
        if clock() >= deadline:
            raise PublicationTimeout(path, diagnostics)
        if not isinstance(value, dict):
            raise ValueError(f'MATLAB publication is not a JSON object: {path}')
        if on_poll is not None:
            on_poll()  # drain events published immediately before final response
            if clock() >= deadline:
                raise PublicationTimeout(path, diagnostics)
        return value, diagnostics


def _finite_vector(value, name, length=None, allow_infinity=False):
    result = np.asarray(value, dtype=float).reshape(-1)
    if length is not None and len(result) != length:
        raise ValueError(f'{name} length must equal {length}')
    bad = np.isnan(result) if allow_infinity else ~np.isfinite(result)
    if bad.any():
        raise ValueError(f'{name} contains unsupported nonfinite values')
    return result


def _matrix(value, name, n):
    result = sparse.csc_matrix(value, dtype=float)
    if result.shape[1] != n or not np.isfinite(result.data).all():
        raise ValueError(f'{name} has invalid dimensions or coefficients')
    return result


def _prepare(model):
    """Convert numerical solver input; exact legality is checked by the caller."""
    c = _finite_vector(model['c'], 'c')
    n = len(c)
    if n == 0:
        raise ValueError('Empty models must be handled before invoking solver')
    A = _matrix(model.get('A', sparse.csc_matrix((0, n))), 'A', n)
    Aeq = _matrix(model.get('Aeq', sparse.csc_matrix((0, n))), 'Aeq', n)
    b = _finite_vector(model.get('b', []), 'b', A.shape[0])
    beq = _finite_vector(model.get('beq', []), 'beq', Aeq.shape[0])
    lb = _finite_vector(model.get('lb', np.zeros(n)), 'lb', n, True)
    ub = _finite_vector(model.get('ub', np.ones(n)), 'ub', n, True)
    if (lb > ub).any():
        raise ValueError('Inconsistent variable bounds')
    indices = np.asarray(model.get('intcon', np.arange(n)))
    if indices.ndim > 1 or not np.isfinite(indices).all():
        raise ValueError('intcon must be a finite one-dimensional index array')
    if ((indices != np.floor(indices)).any() or (indices < 0).any()
            or (indices >= n).any() or len(set(indices.tolist())) != len(indices)):
        raise ValueError('intcon must contain unique zero-based integer indices')
    return {'c': c, 'A': A, 'b': b, 'Aeq': Aeq, 'beq': beq,
            'lb': lb, 'ub': ub, 'intcon': indices.astype(float) + 1}


def _absolute_deadline(budget):
    """Accept a caller budget using the same monotonic clock as the bridge."""
    deadline = float(budget.deadline)
    if not math.isfinite(deadline):
        raise ValueError('budget.deadline must be a finite absolute monotonic time')
    return deadline


class MatlabSession:
    """File-handshake worker with external deadline checks on every request.

    ``remaining_s`` passed to solve is the caller's remaining *case* budget.
    Startup may be amortized only for correctness prechecks.  Formal method
    timing must instantiate a fresh session inside the method budget and pass
    ``budget=...``. Its ``deadline`` must use the bridge's monotonic clock.
    """

    def __init__(self, workdir, total_budget_s=600, matlab_path=DEFAULT_MATLAB,
                 clock=time.monotonic, budget=None):
        if not math.isfinite(total_budget_s) or total_budget_s <= 0:
            raise ValueError('total_budget_s must be positive and finite')
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + float(total_budget_s)
        self.budget = budget
        if budget is not None:
            self.deadline = min(self.deadline, _absolute_deadline(budget))
        self.workdir = Path(workdir).resolve()
        self.counter = 0
        self.closed = False
        self.request_blocked = False
        self.proc = None
        self.log = None
        if self.clock() >= self.deadline:
            raise TimeoutError('Method budget exhausted before MATLAB session preparation')
        self.workdir.mkdir(parents=True, exist_ok=False)
        prefs = REPO / '.runtime/matlab_prefs'
        prefs.mkdir(parents=True, exist_ok=True)
        self.metadata = {
            'scope': ('method_absolute_deadline_transport' if budget is not None
                      else 'small_domain_precheck_transport_not_formal_comparison'),
            'matlab_executable': str(matlab_path), 'preference_directory': str(prefs),
            'worker_guard_seconds': float(total_budget_s),
            'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), HERE / 'solve_model.m']},
            'warm_start_shared': False, 'candidate_or_thermal_cache_shared': False,
            'external_absolute_deadline': self.deadline,
            'method_deadline_bound': budget is not None,
            'deadline_is_not_a_hard_realtime_interrupt': True,
            'callback_candidates': 'recorded_only_not_independently_thermal_checked',
            'external_evaluation': 'final_returned_candidate_only_within_method_deadline',
            'engineering_compatibility': {
                'IntegerPreprocess': 'none',
                'basis': 'results/milp_numeric_diagnostic04',
                'mathematical_model_unchanged': True,
                'general_solver_defect_claim': False,
            },
        }
        _json(self.workdir / 'session.json', self.metadata)
        quote = lambda p: Path(p).as_posix().replace("'", "''")
        try:
            guard = self.deadline - self.clock()
            if guard <= 0:
                raise TimeoutError('Method budget exhausted during MATLAB session preparation')
            # MATLAB cannot share Python's monotonic epoch. This relative
            # guard is advisory; Python's original deadline controls receipt.
            script = "addpath('%s'); solve_model('%s',%.17g);" % (
                quote(HERE), quote(self.workdir), guard)
            self.log = (self.workdir / 'matlab.log').open('wb')
            if self.clock() >= self.deadline:
                raise TimeoutError('Method budget exhausted before MATLAB process launch')
            self.proc = subprocess.Popen(
                [str(matlab_path), '-batch', script],
                env=dict(os.environ, MATLAB_PREFDIR=str(prefs)),
                stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.metadata['pid'] = self.proc.pid
            _json(self.workdir / 'session.json', self.metadata)
            ready = self.workdir / 'ready.json'
            self.environment, read_info = _read_json_until(
                ready, self.deadline, self.clock, self.proc)
            self.metadata['ready_publication_read'] = read_info
            if self.environment.get('status') != 'READY':
                raise RuntimeError('MATLAB worker unavailable: ' + str(self.environment))
            if self.environment.get('release') != '2023b':
                raise RuntimeError('This bridge is checked only against MATLAB R2023b')
            self.metadata['startup_wall_seconds'] = self.clock() - self.started
            self.metadata['startup_outcome'] = 'READY'
            _json(self.workdir / 'session.json', self.metadata)
            if self.clock() >= self.deadline:
                raise TimeoutError('Method budget exhausted before MATLAB startup receipt')
        except BaseException as exc:
            # Startup evidence only, not a retry or an accepted solver result.
            self.metadata['startup_outcome'] = 'FAILED_OR_DEADLINE'
            self.metadata['startup_wall_seconds'] = self.clock()-self.started
            self.metadata['startup_error'] = f'{type(exc).__name__}: {exc}'
            if hasattr(exc, 'diagnostics'):
                self.metadata['startup_publication_read'] = exc.diagnostics
            try:
                _json(self.workdir / 'session.json', self.metadata)
            except Exception as archive_error:
                self.metadata['startup_archive_error'] = repr(archive_error)
            self.close()
            # A failed constructor has no session handle for the caller's
            # finally block. Expose cleanup separately from startup timing.
            exc.matlab_cleanup = self.cleanup
            exc.matlab_workdir = str(self.workdir)
            raise

    def solve(self, model, remaining_s=None, budget=None):
        if self.closed or self.request_blocked:
            raise RuntimeError('Worker is closed or a timed-out request still needs cleanup')
        started = self.clock()
        deadline = self.deadline
        if budget is not None:
            deadline = min(deadline, _absolute_deadline(budget))
        if self.budget is not None:
            deadline = min(deadline, _absolute_deadline(self.budget))
        if remaining_s is not None:
            if not math.isfinite(remaining_s):
                raise ValueError('remaining_s must be finite')
            deadline = min(deadline, started + float(remaining_s))
        if started >= deadline:
            return {'status': 'BUDGET_EXHAUSTED', 'budget_valid': False,
                    'x': [], 'accepted_for_evaluation': False}
        method_bound = budget is not None or self.budget is not None
        phase = getattr(budget if budget is not None else self.budget, 'phase',
                        lambda name: nullcontext())
        self.counter += 1
        prefix = self.workdir / f'request_{self.counter:06d}'
        if getattr(self, 'event_consumer', None) is not None:
            self.metadata['callback_candidates'] = 'immutable live publications; independently evaluated by diagnostic consumer'
            self.metadata['external_evaluation'] = 'callback and final candidates within one absolute method deadline'
            _json(self.workdir/'session.json', self.metadata)
        def expire_before_submission(phase):
            result = {'status': 'BUDGET_EXHAUSTED_BEFORE_PUBLICATION',
                      'phase': phase, 'budget_valid': False, 'x': [],
                      'accepted_for_evaluation': False,
                      'wall_seconds': self.clock()-started,
                      'absolute_deadline': deadline}
            _json(prefix.with_suffix('.python.json'), result)
            return result
        with phase('transport_numerical_conversion'):
            payload = _prepare(model)
        if self.clock() >= deadline:
            return expire_before_submission('numerical_conversion')
        request_info = {
            'request_number': self.counter, 'case_budget_at_entry_s': deadline-started,
            'absolute_deadline': deadline, 'method_deadline_bound': method_bound,
            'session_elapsed_at_entry_s': started - self.started,
            'model_metadata': model.get('metadata', {}),
            'intcon_convention': 'Python_zero_based_converted_to_MATLAB_one_based',
        }
        with phase('transport_input_metadata'):
            _json(prefix.with_suffix('.input.json'), request_info)
        if self.clock() >= deadline:
            return expire_before_submission('input_metadata')
        # The numerical conversion, sparse serialization, and publication are
        # inside the request budget.  MATLAB receives only the time still left.
        temporary = prefix.with_suffix('.mat.tmp')
        payload['remaining_s'] = max(0.0, deadline - self.clock())
        with phase('transport_mat_serialization'):
            savemat(str(temporary), payload, appendmat=False, oned_as='column')
        if self.clock() >= deadline:
            return expire_before_submission('mat_serialization')
        with phase('transport_mat_publication'):
            temporary.replace(prefix.with_suffix('.mat'))
        allocated = deadline - self.clock()
        if allocated <= 0:
            return expire_before_submission('mat_publication')
        # Separate JSON is written last so the worker never reads partial MAT.
        with phase('transport_request_publication'):
            _json(prefix.with_suffix('.request.json'), {
                'remaining_s': allocated,
                'stream_events': bool(getattr(self, 'event_consumer', None))})
        response = prefix.with_suffix('.response.json')
        try:
            with phase('solver_wait_and_response_read'):
                extra = {}
                if getattr(self, 'event_consumer', None) is not None:
                    extra['on_poll'] = lambda: self.event_consumer(prefix)
                result, read_info = _read_json_until(
                    response, deadline, self.clock, self.proc, **extra)
        except PublicationTimeout as exc:
            prefix.with_suffix('.cancel').write_text('budget\n', encoding='ascii')
            result = {'status': 'BUDGET_EXHAUSTED', 'budget_valid': False,
                      'accepted_for_evaluation': False, 'x': [],
                      'request_number': self.counter,
                      'wall_seconds': self.clock() - started,
                      'response_may_arrive_later': True,
                      'publication_read': exc.diagnostics}
            _json(prefix.with_suffix('.python.json'), result)
            # A timed-out request may still be unwinding.  Do not enqueue
            # another request and accidentally reuse additional case time.
            self.request_blocked = True
            if not method_bound:
                self.close()
            return result
        except WorkerExited as exc:
            result = {'status': 'WORKER_EXITED', 'budget_valid': False,
                      'accepted_for_evaluation': False, 'x': [],
                      'returncode': exc.returncode, 'publication_read': exc.diagnostics}
            _json(prefix.with_suffix('.python.json'), result)
            return result
        result['publication_read'] = read_info
        # MATLAB jsonencode collapses a one-element numeric vector to a
        # scalar; the public Python interface always returns a vector.
        raw_x = result.get('x')
        result['x'] = ([] if raw_x is None else
                       np.asarray(raw_x, dtype=float).reshape(-1).tolist())
        result['wall_seconds'] = self.clock() - started
        result['budget_valid'] = bool(self.clock() < deadline)
        result['accepted_for_evaluation'] = bool(
            result['budget_valid'] and result.get('status') == 'SOLVED' and result['x'])
        result['request_number'] = self.counter
        result['evidence_scope'] = 'solver_reported_only_no_thermal_or_optimality_certificate'
        result['solver_response_complete_at_monotonic'] = self.clock()
        _json(prefix.with_suffix('.python.json'), result)
        # Archiving is part of method execution, not free extra candidate time.
        # Even a timely solver response is not returned for thermal evaluation
        # when transport/archiving consumes the remaining method budget.
        if self.clock() >= deadline:
            result['budget_valid'] = False
            result['accepted_for_evaluation'] = False
            result['status'] = 'BUDGET_EXHAUSTED_BEFORE_RETURN'
            result['x'] = []
            _json(prefix.with_suffix('.python.json'), result)
        return result

    def close(self):
        if self.closed:
            return
        cleanup_started = self.clock()
        self.closed = True
        (self.workdir / 'stop').write_text('close\n', encoding='ascii')
        cleanup = {'graceful_stop_requested': True,
                   'cleanup_started_at_monotonic': cleanup_started,
                   'cleanup_not_available_for_new_evidence': True}
        if self.proc is not None:
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # Only this session's child process tree, never other MATLABs.
                if os.name == 'nt':
                    stopped = subprocess.run(
                        ['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                        stdout=self.log, stderr=subprocess.STDOUT, timeout=10)
                    cleanup['own_process_tree_kill_returncode'] = stopped.returncode
                else:
                    self.proc.kill()
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    cleanup['cleanup_pending_pid'] = self.proc.pid
            cleanup['returncode'] = self.proc.poll()
        if self.log is not None:
            self.log.close()
        cleanup['session_wall_seconds'] = self.clock() - self.started
        cleanup['cleanup_wall_seconds'] = self.clock() - cleanup_started
        self.cleanup = cleanup
        _json(self.workdir / 'closed.json', cleanup)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

