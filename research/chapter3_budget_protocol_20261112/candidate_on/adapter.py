"""Saved-ON adapter. Scientific dependencies load only in prepare, after authorization.

No builders, option expansion, pruning, transforms, LP probes, or alternate solver.
"""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import os
import sys
import time
from control import SECONDS, NATIVE_SECONDS, RESERVE, StopWindow, InsufficientNativeBudget
from guard import read, save, sha, verify_plan, verify_approval
from budget_policy import NEXT_ON, ResponseBudget, box_objective_bound
from startup_observer import observe_startup


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def schedule_key(candidate):
    return {s: sorted((r['stage_id'], r['unit'], r['opp'], Fraction(r['start_ms'])) for r in rows)
            for s, rows in candidate['scenes'].items()}


def decode(instance, options, vector, tolerance, validate_schedule):
    import numpy as np
    x = np.asarray(vector, dtype=float).reshape(-1)
    if len(x) < len(options) or not np.isfinite(x).all():
        raise ValueError('Malformed option vector')
    y = x[:len(options)]
    if ((abs(y-np.rint(y)) > tolerance).any() or (y < -tolerance).any() or (y > 1+tolerance).any()):
        raise ValueError('Nonbinary option prefix')
    candidate = {'scenes': {s['id']: [] for s in instance['scenarios']}}
    for o, value in zip(options, y):
        if round(float(value)) == 1:
            candidate['scenes'][o['scenario_id']].append(dict(stage_id=o['stage_instance_id'], unit=o['unit_id'],
                                                           opp=o['opp_id'], start_ms=o['start_ms']))
    legality = validate_schedule(instance, candidate)
    if legality.get('state') != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('Decoded schedule rejected: ' + str(legality.get('reason')))
    return candidate, legality


class Runtime:
    def __init__(self, workspace, package, plan_path, plan, folder, start):
        self.workspace = Path(workspace); self.package = Path(package); self.plan_path = Path(plan_path)
        self.plan = plan; self.folder = Path(folder); self.start = start
        self.events = []; self.seen = set(); self.scene_count = 0; self.objective_reference = None
        self.objective_lower_bound = None
        self.session = None; self.startup_cleanup = None; self.budget = None
        self.solve_attempted = False; self.evaluations = 0; self.actual_native_entries = 0
        self.solver_evidence_cutoff_s = NEXT_ON.response_cutoff

    @property
    def elapsed(self): return time.monotonic() - self.start

    @property
    def remaining(self): return max(0., SECONDS-self.elapsed)

    def check(self):
        if self.remaining <= 0: raise StopWindow()

    def _call(self, phase, function, *args, **kwargs):
        self.check()
        try:
            with self.budget.phase(phase):
                return function(*args, **kwargs)
        except self.Exhausted as error:
            stop = StopWindow(str(error))
            if hasattr(error, 'matlab_cleanup'): stop.matlab_cleanup = error.matlab_cleanup
            raise stop from error
        except TimeoutError as error:
            if self.remaining > 0: raise
            stop = StopWindow(str(error))
            if hasattr(error, 'matlab_cleanup'): stop.matlab_cleanup = error.matlab_cleanup
            raise stop from error

    def payload(self, path):
        import numpy as np
        from scipy.io import loadmat
        d = loadmat(path, variable_names=list(self.cg.KEYS))
        p = {k: d[k].tocsc() if k in ('A', 'Aeq') else d[k].reshape(-1) for k in self.cg.KEYS}
        i = p['intcon']
        if not np.isfinite(i).all() or not np.equal(i, np.floor(i)).all():
            raise ValueError('Malformed integer column indices')
        p['intcon'] = i.astype(np.int64)-1
        return p

    def prepare(self):
        import numpy as np
        sys.path.insert(0, str(self.workspace / 'work/stable_expression'))
        import complement_gate
        self.cg = complement_gate
        sys.path.insert(0, str(self.workspace / 'work/equality_pair_source/research/chapter3_experiments'))
        import matlab_bridge
        from timing import MethodBudget
        from thermal import evaluate_candidate, Exhausted
        from schedules import validate_schedule
        self.bridge = matlab_bridge; self.evaluate = evaluate_candidate
        self.validate_schedule = validate_schedule; self.Exhausted = Exhausted
        runtime = self
        class GuardedBudget(MethodBudget):
            @contextmanager
            def phase(self, name):
                if name == 'transport_request_publication':
                    allocation = NEXT_ON.allocate(runtime.elapsed)
                    save(runtime.folder/'publication_allocation.json', allocation)
                    if not allocation['can_submit'] or not NEXT_ON.allocate(runtime.elapsed)['can_submit']:
                        raise InsufficientNativeBudget('No time to retain the unchanged native cap before publication')
                with super().phase(name):
                    yield
        self.budget = GuardedBudget(SECONDS)
        self.budget.start = self.start; self.budget.deadline = self.start + SECONDS
        self.check()
        with self.budget.phase('saved_input_read_and_admission'):
            full = self.workspace / 'work/stable_expression/full'
            self.instance = read(full / 'input_instance.json'); self.config = read(full / 'input_config.json')
            self.initial = read(full / 'initial_candidate.json'); self.options = read(full / 'options.json')['options']
            self.old = self.payload(full / 'on.original.mat'); self.new = self.payload(full / 'on.mat')
            self.certificate = read(full / 'on.certificate.json')
            n = len(self.old['c'])
            for k in ('c', 'lb', 'ub', 'x0'):
                if not np.array_equal(self.old[k], self.new[k][:n]): raise ValueError('Original coordinate changed: '+k)
            if not np.array_equal(self.old['intcon'], self.new['intcon']): raise ValueError('Integer columns changed')
            if list(self.old['intcon']) != list(range(len(self.options))): raise ValueError('Option prefix identity changed')
            if digest(self.instance) != self.plan['input_identity'] or digest(self.initial) != self.plan['initial_candidate_identity']:
                raise ValueError('Canonical input or initial identity changed')
            self.native_old = self.bridge._prepare(self.old, x0=self.old['x0'])
            self.native_new = self.bridge._prepare(self.new, x0=self.new['x0'])
            candidate, _ = decode(self.instance, self.options, self.old['x0'], 1e-6, self.validate_schedule)
            if schedule_key(candidate) != schedule_key(self.initial): raise ValueError('Initial schedule changed')
            self.scene_count = len(self.instance['scenarios'])
            self.objective_reference = self.objective(self.old['x0'])
            self.objective_lower_bound = box_objective_bound(self.old['c'],self.old['lb'],self.old['ub'])
            save(self.folder / 'saved_input_admission.json', dict(original=self.native_old['x0_validation'],
                transformed=self.native_new['x0_validation'], objective_reference_exact=self.objective_reference,
                box_objective_lower_bound_exact=self.objective_lower_bound,
                scope='Numerical tolerance admission only; not an exact feasible-point certificate.'))
        self.check()

    def objective(self, vector):
        return str(sum((Fraction.from_float(float(c))*Fraction.from_float(float(x)) for c,x in zip(self.old['c'],vector)), Fraction(0)))

    def _evaluate(self, candidate, filename):
        if self.evaluations >= 2: raise RuntimeError('Physical evaluation limit consumed')
        self.evaluations += 1
        result = self._call(filename, self.evaluate, self.instance, candidate, self.config['accuracy_targets'], budget=self.budget)
        save(self.folder / (filename+'.json'), result)
        return result

    def evaluate_initial(self): return self._evaluate(self.initial, 'initial_complete_evaluation')

    def evaluate_returned(self, candidate): return self._evaluate(candidate, 'returned_complete_evaluation')

    def start_native(self):
        self._permit()
        self.bridge.REPO = self.folder / 'isolated_preferences'
        records=[]
        try:
            with observe_startup(self.bridge,time.monotonic,records):
                self.session = self._call('native_startup', self.bridge.MatlabSession, self.folder / 'matlab',
                                         total_budget_s=self.remaining, budget=self.budget, matlab_path=self.plan['matlab'])
        except Exception as error:
            self.startup_cleanup = getattr(error, 'matlab_cleanup', None)
            raise
        finally:
            save(self.folder/'startup_timing_observer.json',dict(records=records,
                clock='same Python monotonic clock',poll_cadence_changed=False,
                interpretation='READY wait overlaps MATLAB initialization/license work; not a root-cause decomposition.'))
        self.session.event_consumer = self.poll

    def _permit(self):
        approval = read(self.folder / 'approval_consumed.json')
        verify_approval(approval, sha(self.plan_path))
        claim = read(self.folder / 'claim.json')
        worker_claim = read(self.folder / 'worker_claim.json')
        if (claim['plan_sha256'] != sha(self.plan_path) or claim['parent_start_monotonic'] != self.start
                or worker_claim['pid'] != os.getpid() or worker_claim['start_monotonic'] != self.start):
            raise PermissionError('Native entry requires this authorized worker claim')

    def capture(self, event):
        # Never backdate using native request_wall_seconds. Time is receipt after complete JSON read.
        elapsed = self.elapsed
        if elapsed >= self.solver_evidence_cutoff_s: return
        number = event.get('event_number')
        if number in self.seen: return
        self.seen.add(number)
        row = dict(event, received_elapsed_s=elapsed)
        self.events.append(row)
        if row.get('kind') == 'solver_entered': self.actual_native_entries += 1
        with (self.folder / 'progress.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')

    def poll(self, prefix):
        for path in sorted((self.folder / 'matlab').glob('request_000001.event_*.json')):
            if self.remaining <= 0: break
            try: event = read(path)
            except (PermissionError, json.JSONDecodeError): continue
            self.capture(event)

    def solve(self, cap):
        self._permit()
        if self.solve_attempted: raise RuntimeError('Single native request already consumed')
        if cap != NATIVE_SECONDS: raise ValueError('Native cap changed')
        allocation=NEXT_ON.allocate(self.elapsed)
        if not allocation['can_submit']:raise InsufficientNativeBudget('Frozen native cap no longer fits')
        save(self.folder/'native_allocation.json',allocation)
        self.solve_attempted = True
        response_budget=ResponseBudget(self.budget,NEXT_ON,time.monotonic)
        result = self._call('native_request_total', self.session.solve, self.new, x0=self.new['x0'],
                            budget=response_budget, solver_max_time_s=NATIVE_SECONDS)
        self.poll(None)
        if result.get('budget_valid') and self.remaining > 0:
            for event in result.get('callbacks', []): self.capture(event)
        save(self.folder / 'native_receipt.json', result)
        return result

    def inspect_identity(self, native, after_cleanup=False):
        """Read-only checks even for an empty timeout receipt. No late candidate evaluation."""
        root = self.folder / 'matlab'
        checks = {}
        if (root / 'request_000001.mat').exists():
            checks['actual_arrays'] = self.cg.array_digest(self.payload(root / 'request_000001.mat')) == self.cg.array_digest(self.new)
        else: checks['actual_arrays'] = None
        raw = read(root / 'request_000001.response.json') if (root / 'request_000001.response.json').exists() else native
        checks['native_options'] = raw.get('options') == self.plan['native_options'] if 'options' in raw else None
        checks['matlab_release'] = read(root / 'ready.json').get('release') == '2023b' if (root / 'ready.json').exists() else None
        state = 'INVALID' if False in checks.values() else ('VERIFIED' if all(v is True for v in checks.values()) else 'UNKNOWN')
        result = dict(state=state, checks=checks, checked_at_elapsed_s=self.elapsed,
                      post_cutoff=self.elapsed >= SECONDS, scope='Identity only; no late scientific evidence credit')
        save(self.folder / ('identity_checks_after_cleanup.json' if after_cleanup else 'identity_checks.json'), result)
        return result

    def validate_returned(self, vector):
        def check():
            try:
                _, new_check = self.bridge._check_initial_point(self.native_new, vector)
                projected = self.cg.inverse_vector(vector, self.certificate)
                _, old_check = self.bridge._check_initial_point(self.native_old, projected)
                candidate, legality = decode(self.instance, self.options, projected, 1e-6, self.validate_schedule)
            except (self.bridge.InitialPointRejected, ValueError) as error:
                result = dict(state='REJECTED', reason=str(error), diagnostics=getattr(error, 'diagnostics', None))
            else:
                q = lambda x: Fraction.from_float(float(x))
                gate_error = max((abs(q(vector[r['gate_column']])+q(vector[r['complement_column']])-1)
                                  for r in self.certificate['gate_complements']), default=Fraction(0))
                offset_error = max((abs(q(vector[r['column']])-Fraction(r['value_exact']))
                                    for r in self.certificate.get('fixed_constants', [])), default=Fraction(0))
                objective = self.objective(projected)
                self.check()
                self.objective_reference = str(min(Fraction(self.objective_reference), Fraction(objective)))
                result = dict(state='ADMITTED', transformed_rows=new_check, original_rows=old_check,
                              legality=legality, candidate=candidate, same_initial=schedule_key(candidate)==schedule_key(self.initial),
                              objective_exact_binary64=objective, maximum_complement_residual_exact=str(gate_error),
                              maximum_fixed_constant_residual_exact=str(offset_error), independent_exact_feasibility_certificate=False)
            result['completed_at_elapsed_s'] = self.elapsed
            save(self.folder / 'returned_vector_validation.json', result)
            return result
        return self._call('new_original_rows_and_decode', check)

    def close(self):
        self.method_stopped = self.elapsed
        if self.session is not None:
            self.session.close()
            return dict(complete=self.bridge.cleanup_is_complete(self.session.cleanup), receipt=self.session.cleanup)
        if self.startup_cleanup is not None:
            return dict(complete=self.bridge.cleanup_is_complete(self.startup_cleanup), receipt=self.startup_cleanup)
        return dict(complete=True, scope='No native session created')

    def verify_after(self):
        verify_plan(self.plan_path, self.workspace, self.package)
        if self.budget:
            timing = self.budget.summary(self.method_stopped)
            timing['clock_origin'] = 'parent entry before configuration read and child imports'
            save(self.folder / 'timing_after_cleanup.json', timing)
        identity = self.inspect_identity({}, after_cleanup=True) if self.solve_attempted else None
        return dict(state='VERIFIED', source_unchanged=True, checked_at_elapsed_s=self.elapsed,
                    native_identity_after=identity)
