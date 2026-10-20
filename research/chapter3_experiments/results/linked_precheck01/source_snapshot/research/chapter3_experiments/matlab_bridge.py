"""R2023b intlinprog transport, not a proof engine.

One worker process can serve independent small models.  Its lifetime is a
precheck guard, not an experimental method budget.  Each solve has a separate
external deadline; late results are retained only as diagnostics.  A method
session binds the caller's absolute deadline before startup, so repeated solves
never replenish model construction, transport, or evaluation time.
No incumbent, constraint, or cache is shared between solve requests.
The worker fixes IntegerPreprocess='none' after the isolated small-model
compatibility check in results/milp_numeric_diagnostic04, and LPPreprocess='none'
after the fixed-logic numerical check in results/infeasible_audit01. The domain,
objective and gap/tolerance settings are unchanged; no bound is certified here.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import math
from numbers import Real
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
NUMERICAL_CONSISTENCY_CONFLICT = 'NUMERICAL_ADMISSION_STATUS_CONFLICT'
NUMERICAL_CONSISTENCY_UNRESOLVED = 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED'


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


class InitialPointRejected(ValueError):
    """An explicit initial point failed the unchanged numerical contract."""

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('Initial point rejected: ' + '; '.join(diagnostics['reasons']))


def _check_initial_point(payload, x0):
    """Check, without rounding or repairing, the optional numerical x0.

    These floating residuals are an admission check, not a thermal witness or
    independent mathematical certificate.  The receiving solver still checks
    x0 under its own implementation of the same declared tolerances.
    """
    info = {'provided': True, 'accepted_numerically': False,
            'constraint_tolerance': 1e-9, 'integer_tolerance': 1e-6,
            'reasons': [], 'thermal_safe_claim': False,
            'independent_certificate': False,
            'rounding_or_repair_performed': False}
    if np.iscomplexobj(x0):
        info['reasons'].append('x0 must be real; imaginary parts cannot be discarded')
        raise InitialPointRejected(info)
    try:
        raw = np.asarray(x0, dtype=float)
    except (TypeError, ValueError) as exc:
        info['reasons'].append('x0 cannot be converted to a numerical vector')
        raise InitialPointRejected(info) from exc
    if raw.ndim > 2 or (raw.ndim == 2 and min(raw.shape) != 1):
        info['reasons'].append('x0 must be a vector')
        raise InitialPointRejected(info)
    x = raw.reshape(-1)
    info['length'] = int(len(x))
    if len(x) != len(payload['c']):
        info['reasons'].append('x0 length differs from model variable count')
    if not np.isfinite(x).all():
        info['reasons'].append('x0 contains nonfinite values')
    if info['reasons']:
        raise InitialPointRejected(info)
    indices = payload['intcon'].astype(np.int64) - 1
    with np.errstate(over='ignore', invalid='ignore'):
        residual = np.asarray(payload['A'] @ x).reshape(-1) - payload['b']
        equality = np.asarray(payload['Aeq'] @ x).reshape(-1) - payload['beq']
        lower = payload['lb'] - x
        upper = x - payload['ub']
        integer = np.abs(x[indices] - np.rint(x[indices]))
        objective = float(payload['c'] @ x)
    if (not np.isfinite(residual).all() or not np.isfinite(equality).all()
            or not math.isfinite(objective)):
        info['reasons'].append('x0 produces nonfinite residuals or objective')
    info.update({
        'inequality_violation': float(max(0.0, np.max(residual, initial=0.0))),
        'equality_violation': float(np.max(np.abs(equality), initial=0.0)),
        'lower_bound_violation': float(max(0.0, np.max(lower, initial=0.0))),
        'upper_bound_violation': float(max(0.0, np.max(upper, initial=0.0))),
        'integer_violation': float(np.max(integer, initial=0.0)),
        'initial_objective': objective if math.isfinite(objective) else None,
    })
    for key in ('inequality_violation', 'equality_violation',
                'lower_bound_violation', 'upper_bound_violation'):
        if info[key] > info['constraint_tolerance']:
            info['reasons'].append(key + ' exceeds ConstraintTolerance')
    if info['integer_violation'] > info['integer_tolerance']:
        info['reasons'].append('integer_violation exceeds IntegerTolerance')
    # Error diagnostics must remain valid JSON even for overflowed products.
    for key in ('inequality_violation', 'equality_violation',
                'lower_bound_violation', 'upper_bound_violation',
                'integer_violation'):
        if not math.isfinite(info[key]):
            info[key] = None
    if info['reasons']:
        raise InitialPointRejected(info)
    info['accepted_numerically'] = True
    return x, info


def _prepare(model, x0=None):
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
    result = {'c': c, 'A': A, 'b': b, 'Aeq': Aeq, 'beq': beq,
              'lb': lb, 'ub': ub, 'intcon': indices.astype(float) + 1}
    if x0 is not None:
        result['x0'], result['x0_validation'] = _check_initial_point(result, x0)
    return result


def _initial_point_status_conflict(initial_point, returned, *, explicit_x0,
                                   request_number, within_budget):
    """Same-request engineering diagnostic, never an exact feasibility proof.

    Python's tolerance admission and native infeasibility can disagree without
    establishing a mathematical contradiction. Do not infer admission from a
    previous request or from the worker merely reporting that x0 was received.
    """
    if not (explicit_x0 and initial_point.get('provided') is True
            and initial_point.get('accepted_numerically') is True
            and returned.get('status') == 'SOLVED' and returned.get('exitflag') == -2):
        return None
    native_initial = returned.get('initial_point') or {}
    return {'state': NUMERICAL_CONSISTENCY_CONFLICT,
            'request_number': request_number,
            'explicit_x0_in_this_request': True,
            'python_x0_admission': deepcopy(initial_point),
            'worker_reported_x0_received': native_initial.get('provided'),
            'worker_solver_x0_acceptance': native_initial.get('solver_acceptance', 'not_independently_observed'),
            'solver_reported_status': returned.get('status'),
            'solver_reported_exitflag': returned.get('exitflag'),
            'formed_within_request_budget': bool(within_budget),
            'independent_certificate': False, 'thermal_safe_claim': False,
            'retry_performed': False,
            'scope': 'current numerical payload admission versus solver-reported status only; no exact contradiction or solver-defect claim'}


def _absolute_deadline(budget):
    """Accept a caller budget using the same monotonic clock as the bridge."""
    deadline = float(budget.deadline)
    if not math.isfinite(deadline):
        raise ValueError('budget.deadline must be a finite absolute monotonic time')
    return deadline


def _solver_time_cap(value):
    """Optional native MaxTime only; never an evidence/response deadline."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError('solver_max_time_s must be positive and finite')
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError('solver_max_time_s must be positive and finite')
    return result


def _cut_iteration_limit(value):
    """Optional native cut-pass limit; None leaves the R2023b default alone."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError('cut_max_iterations must be an integer from 1 to 50 or None')
    if not 1 <= value <= 50 or value != int(value):
        raise ValueError('cut_max_iterations must be an integer from 1 to 50 or None')
    return int(value)


def _capture_owned_process_tree(proc, previous=None, *, phase):
    """Observe only this Popen root and descendants, retaining pid/create_time."""
    tree = deepcopy(previous) if previous else {
        'root_pid': proc.pid, 'root_identity': None, 'identities': [],
        'capture_complete': True, 'capture_errors': [], 'observations': []}
    observation = {'phase': phase, 'root_identity_verified': False}
    tree['root_identity_verified'] = False
    root_loaded = False
    try:
        import psutil
        tree['psutil_version'] = psutil.__version__
        if tree['root_pid'] != proc.pid:
            raise ValueError('owned Popen root PID changed')
        root = psutil.Process(proc.pid)
        actual = {'pid': int(root.pid), 'create_time': float(root.create_time())}
        root_loaded = True
        if not math.isfinite(actual['create_time']) or actual['create_time'] <= 0:
            raise ValueError('invalid owned root creation time')
        expected = tree['root_identity']
        if expected is not None and actual != expected:
            # This new process is not ours. Do not enumerate or signal it.
            observation['state'] = 'ROOT_PID_REUSED_ORIGINAL_EXITED'
        elif proc.poll() is not None:
            observation['state'] = 'ROOT_EXITED'
            if expected is None:
                raise ValueError('root exited before its ownership identity was captured')
        else:
            tree['root_identity'] = actual
            tree['root_identity_verified'] = True
            observation.update(state='ROOT_OBSERVED', root_identity_verified=True)
            known = {(item['pid'], item['create_time']) for item in tree['identities']}
            if (actual['pid'], actual['create_time']) not in known:
                tree['identities'].append(actual)
                known.add((actual['pid'], actual['create_time']))
            for process in root.children(recursive=True):
                identity = {'pid': int(process.pid), 'create_time': float(process.create_time())}
                if not math.isfinite(identity['create_time']) or identity['create_time'] <= 0:
                    raise ValueError('invalid owned descendant creation time')
                key = (identity['pid'], identity['create_time'])
                if key not in known:
                    tree['identities'].append(identity)
                    known.add(key)
    except Exception as error:
        # A previously identified root may have exited before this observation.
        if (type(error).__name__ == 'NoSuchProcess' and not root_loaded
                and tree.get('root_identity') is not None):
            observation['state'] = 'ROOT_EXITED'
        else:
            tree['capture_complete'] = False
            tree['capture_errors'].append({'phase': phase, 'error': repr(error)})
            observation.update(state='UNRESOLVED', error=repr(error))
    tree['observations'].append(observation)
    return tree


def _verify_owned_process_tree(tree):
    """Check saved identities without signalling any process or reused PID."""
    result = {'capture_complete': bool(tree and tree.get('capture_complete')),
              'identities': [], 'verified_terminated': False}
    identities = (tree or {}).get('identities', [])
    for identity in identities:
        item = dict(identity)
        try:
            import psutil
            process = psutil.Process(identity['pid'])
            if float(process.create_time()) != identity['create_time']:
                item['state'] = 'PID_REUSED_ORIGINAL_EXITED'
            else:
                item['state'] = 'RUNNING' if process.is_running() else 'EXITED'
        except Exception as error:
            if type(error).__name__ == 'NoSuchProcess':
                item['state'] = 'EXITED'
            else:
                item.update(state='UNRESOLVED', error=repr(error))
        result['identities'].append(item)
    result['verified_terminated'] = bool(result['capture_complete'] and identities
        and (tree or {}).get('root_identity') in identities
        and all(item['state'] in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED')
                for item in result['identities']))
    return result


def _wait_owned_process_tree(tree, *, clock, deadline, pause=None):
    """Confirm only captured identities until the existing cleanup cutoff."""
    pause = time.sleep if pause is None else pause
    started, checks = clock(), 0
    while True:
        result = _verify_owned_process_tree(tree)
        checks += 1
        if result['verified_terminated']:
            reason = 'ALL_CAPTURED_IDENTITIES_EXITED'
            break
        if (not result['capture_complete'] or not result['identities']
                or any(item['state'] == 'UNRESOLVED' for item in result['identities'])):
            reason = 'IDENTITY_OR_ACCESS_UNRESOLVED'
            break
        remaining = deadline - clock()
        if remaining <= 0:
            reason = 'CONFIRMATION_WINDOW_EXHAUSTED'
            break
        pause(min(0.1, remaining))
    result['confirmation_wait'] = {'started_at_monotonic': started,
        'deadline_monotonic': deadline, 'wall_seconds': max(0.0, clock() - started),
        'checks': checks, 'stop_reason': reason,
        'scope': 'previously captured identities only; no new cleanup window or signals'}
    return result


def _cleanup_has_error(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if (key in ('error', 'errors') or key.endswith(('_error', '_errors')) or 'pending' in key):
                if item not in (None, False, '', [], {}):
                    return True
            if _cleanup_has_error(item):
                return True
    elif isinstance(value, list):
        return any(_cleanup_has_error(item) for item in value)
    return False


def cleanup_is_complete(receipt):
    """Pure receipt check; historical nonzero exits are never upgraded."""
    if not isinstance(receipt, dict) or _cleanup_has_error(receipt):
        return False
    code = receipt.get('returncode')
    if isinstance(code, bool) or not isinstance(code, int):
        return False
    if 'cleanup_status' not in receipt:
        return code == 0
    status = receipt['cleanup_status']
    verified = receipt.get('process_tree_verification')
    if not isinstance(verified, dict) or not isinstance(verified.get('identities'), list):
        return False
    identities = verified['identities']
    count = receipt.get('observed_tree_identity_count')
    if (status not in ('graceful_closed', 'forced_closed')
            or receipt.get('observed_tree_verified_terminated') is not True
            or receipt.get('observed_tree_capture_complete') is not True
            or verified.get('capture_complete') is not True
            or verified.get('verified_terminated') is not True
            or isinstance(count, bool) or not isinstance(count, int) or count <= 0
            or count != len(identities)):
        return False
    for item in identities:
        if not isinstance(item, dict):
            return False
        pid, created = item.get('pid'), item.get('create_time')
        if (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
                or isinstance(created, bool) or not isinstance(created, Real)
                or not math.isfinite(created) or created <= 0
                or item.get('state') not in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED')):
            return False
    if status == 'graceful_closed':
        return code == 0 and receipt.get('force_requested') is False
    return (receipt.get('force_requested') is True
        and receipt.get('force_termination_succeeded') is True
        and (receipt.get('own_process_tree_kill_returncode') == 0
             or receipt.get('own_process_kill_succeeded') is True))


class MatlabSession:
    """File-handshake worker with external deadline checks on every request.

    ``remaining_s`` passed to solve is the caller's remaining *case* budget.
    Optional ``solver_max_time_s`` limits only native intlinprog MaxTime; it
    never moves the absolute deadline for callbacks, evidence, or responses.
    Optional session-level ``cut_max_iterations`` sets only CutMaxIterations
    for every request; None leaves that native default unset by this bridge.
    Startup may be amortized only for correctness prechecks.  Formal method
    timing must instantiate a fresh session inside the method budget and pass
    ``budget=...``. Its ``deadline`` must use the bridge's monotonic clock.
    """

    def __init__(self, workdir, total_budget_s=600, matlab_path=DEFAULT_MATLAB,
                 clock=time.monotonic, budget=None, cut_max_iterations=None):
        self.cut_max_iterations = _cut_iteration_limit(cut_max_iterations)
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
                'LPPreprocess': 'none',
                'LPPreprocess_basis': 'results/infeasible_audit01/fixed_logic_no_lp_preprocess_probe',
                'mathematical_model_unchanged': True,
                'general_solver_defect_claim': False,
            },
        }
        if self.cut_max_iterations is not None:
            self.metadata['cut_max_iterations_declared'] = self.cut_max_iterations
            self.metadata['cut_max_iterations_scope'] = 'native_cut_pass_limit_only'
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
            self.process_tree = _capture_owned_process_tree(self.proc, phase='ready')
            self.metadata['process_tree_at_ready'] = deepcopy(self.process_tree)
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
            try:
                self.close()
            except BaseException as cleanup_error:
                # Preserve the original startup exception even if an
                # unexpected cleanup failure escapes the best-effort steps.
                self.cleanup = getattr(self, 'cleanup', {})
                self.cleanup['cleanup_error'] = repr(cleanup_error)
            # A failed constructor has no session handle for the caller's
            # finally block. Expose cleanup separately from startup timing.
            exc.matlab_cleanup = self.cleanup
            exc.matlab_workdir = str(self.workdir)
            exc.matlab_startup_metadata = dict(self.metadata)
            raise

    def solve(self, model, remaining_s=None, budget=None, x0=None,
              solver_max_time_s=None):
        if self.closed or self.request_blocked:
            raise RuntimeError('Worker is closed or a timed-out request still needs cleanup')
        solver_cap = _solver_time_cap(solver_max_time_s)
        cut_limit = _cut_iteration_limit(getattr(self, 'cut_max_iterations', None))
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
        try:
            with phase('transport_numerical_conversion'):
                payload = _prepare(model) if x0 is None else _prepare(model, x0=x0)
        except InitialPointRejected as exc:
            _json(prefix.with_suffix('.initial.json'), exc.diagnostics)
            raise
        initial_point = payload.get('x0_validation', {'provided': False})
        if x0 is not None:
            _json(prefix.with_suffix('.initial.json'), initial_point)
        if self.clock() >= deadline:
            return expire_before_submission('numerical_conversion')
        request_info = {
            'request_number': self.counter, 'case_budget_at_entry_s': deadline-started,
            'absolute_deadline': deadline, 'method_deadline_bound': method_bound,
            'session_elapsed_at_entry_s': started - self.started,
            'model_metadata': model.get('metadata', {}),
            'intcon_convention': 'Python_zero_based_converted_to_MATLAB_one_based',
            'initial_point': initial_point,
        }
        if solver_cap is not None:
            request_info['solver_max_time_s_declared'] = solver_cap
            request_info['solver_max_time_s_scope'] = 'native_MaxTime_only_not_response_or_evidence_deadline'
        if cut_limit is not None:
            request_info['cut_max_iterations_declared'] = cut_limit
            request_info['cut_max_iterations_scope'] = 'native_cut_pass_limit_only'
        with phase('transport_input_metadata'):
            _json(prefix.with_suffix('.input.json'), request_info)
        if self.clock() >= deadline:
            return expire_before_submission('input_metadata')
        # The numerical conversion, sparse serialization, and publication are
        # inside the request budget.  MATLAB receives only the time still left.
        temporary = prefix.with_suffix('.mat.tmp')
        payload['remaining_s'] = max(0.0, deadline - self.clock())
        if cut_limit is not None:
            payload['cut_max_iterations'] = cut_limit
        if solver_cap is not None:
            payload['solver_max_time_s_declared'] = solver_cap
            payload['solver_max_time_s'] = min(solver_cap, payload['remaining_s'])
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
        request = {
            'remaining_s': allocated,
            'stream_events': bool(getattr(self, 'event_consumer', None))}
        if cut_limit is not None:
            request['cut_max_iterations'] = cut_limit
        if solver_cap is not None:
            request['solver_max_time_s_declared'] = solver_cap
            request['solver_max_time_s'] = min(solver_cap, allocated)
        with phase('transport_request_publication'):
            _json(prefix.with_suffix('.request.json'), request)
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
        consistency = _initial_point_status_conflict(initial_point, result,
            explicit_x0=x0 is not None, request_number=self.counter,
            within_budget=result['budget_valid'])
        if consistency is not None:
            # Keep native status/exitflag/output intact. The loop consumes the
            # separate diagnostic only after its original budget checks.
            result['numerical_consistency'] = consistency
        result['accepted_for_evaluation'] = bool(
            result['budget_valid'] and result.get('status') == 'SOLVED'
            and result['x'] and consistency is None)
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
        cleanup_deadline = cleanup_started + 40.0
        self.closed = True
        cleanup = {'graceful_stop_requested': False, 'force_requested': False,
                   'force_termination_succeeded': False, 'cleanup_status': 'unresolved',
                   'cleanup_started_at_monotonic': cleanup_started,
                   'cleanup_not_available_for_new_evidence': True}
        # Publish the in-memory receipt before any fallible file/process step.
        # Archive failures must neither leak this session's process nor erase
        # the startup error which led here.
        self.cleanup = cleanup
        if self.proc is not None:
            self.process_tree = _capture_owned_process_tree(
                self.proc, getattr(self, 'process_tree', None), phase='close_begin')
        try:
            (self.workdir / 'stop').write_text('close\n', encoding='ascii')
            cleanup['graceful_stop_requested'] = True
        except Exception as error:
            cleanup['stop_write_error'] = repr(error)
        if self.proc is not None:
            try:
                self.proc.wait(timeout=min(20.0, max(0.0, cleanup_deadline - self.clock())))
            except subprocess.TimeoutExpired:
                # Only this session's child process tree, never other MATLABs.
                cleanup['force_requested'] = True
                self.process_tree = _capture_owned_process_tree(
                    self.proc, self.process_tree, phase='before_force')
                try:
                    if not self.process_tree.get('root_identity_verified'):
                        cleanup['force_identity_error'] = 'Owned root identity not verified; no PID signal sent'
                    elif self.clock() >= cleanup_deadline:
                        cleanup['force_window_error'] = 'Existing 40 second cleanup window exhausted'
                    elif os.name == 'nt':
                        stopped = subprocess.run(
                            ['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                            stdout=self.log, stderr=subprocess.STDOUT,
                            timeout=min(10.0, max(0.0, cleanup_deadline - self.clock())))
                        cleanup['own_process_tree_kill_returncode'] = stopped.returncode
                        cleanup['force_termination_succeeded'] = stopped.returncode == 0
                        if stopped.returncode != 0 and self.proc.poll() is None:
                            self.proc.kill()
                            cleanup['own_process_kill_succeeded'] = True
                            cleanup['force_termination_succeeded'] = True
                    else:
                        self.proc.kill()
                        cleanup['own_process_kill_succeeded'] = True
                        cleanup['force_termination_succeeded'] = True
                except Exception as error:
                    cleanup['process_kill_error'] = repr(error)
                    try:
                        if (self.process_tree.get('root_identity_verified') and self.proc.poll() is None
                                and self.clock() < cleanup_deadline):
                            self.proc.kill()
                            cleanup['own_process_kill_succeeded'] = True
                            cleanup['force_termination_succeeded'] = True
                    except Exception as fallback_error:
                        cleanup['process_kill_fallback_error'] = repr(fallback_error)
                try:
                    self.proc.wait(timeout=min(10.0, max(0.0, cleanup_deadline - self.clock())))
                except subprocess.TimeoutExpired:
                    cleanup['cleanup_pending_pid'] = self.proc.pid
                except Exception as error:
                    cleanup['process_wait_error'] = repr(error)
            except Exception as error:
                cleanup['process_wait_error'] = repr(error)
            try:
                cleanup['returncode'] = self.proc.poll()
                if cleanup['returncode'] is None:
                    cleanup['cleanup_pending_pid'] = self.proc.pid
            except Exception as error:
                cleanup['process_poll_error'] = repr(error)
                cleanup['cleanup_pending_pid'] = self.proc.pid
        tree = getattr(self, 'process_tree', None)
        verification = _wait_owned_process_tree(tree, clock=self.clock,
            deadline=min(cleanup_deadline, self.clock() + 10.0))
        cleanup.update(process_tree_observation=deepcopy(tree),
            process_tree_verification=verification,
            observed_tree_capture_complete=verification['capture_complete'],
            observed_tree_identity_count=len(verification['identities']),
            observed_tree_verified_terminated=verification['verified_terminated'])
        pending = [item for item in verification['identities']
                   if item['state'] not in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED')]
        if pending:
            cleanup['cleanup_pending_identities'] = pending
        if verification['verified_terminated']:
            if cleanup['force_requested'] and cleanup['force_termination_succeeded']:
                cleanup['cleanup_status'] = 'forced_closed'
            elif not cleanup['force_requested'] and cleanup.get('returncode') == 0:
                cleanup['cleanup_status'] = 'graceful_closed'
        if _cleanup_has_error(cleanup):
            cleanup['cleanup_status'] = 'unresolved'
        if self.log is not None:
            try:
                self.log.close()
            except Exception as error:
                cleanup['log_close_error'] = repr(error)
        cleanup['session_wall_seconds'] = self.clock() - self.started
        cleanup['cleanup_wall_seconds'] = self.clock() - cleanup_started
        if _cleanup_has_error(cleanup):
            cleanup['cleanup_status'] = 'unresolved'
        try:
            _json(self.workdir / 'closed.json', cleanup)
        except Exception as error:
            cleanup['cleanup_archive_error'] = repr(error)
            cleanup['cleanup_status'] = 'unresolved'

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

