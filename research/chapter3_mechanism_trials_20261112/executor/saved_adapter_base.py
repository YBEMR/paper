"""Shared vector admission, live receipt capture and owned MATLAB lifecycle.
Scientific preparation and dispatch are implemented only by the fresh Runtime.
"""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import os
import sys
import time
from evidence import SECONDS, StopWindow
from guard import read, save, sha, verify_plan, verify_approval
from budget_policy import ABC_DYNAMIC
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
        self.solver_evidence_cutoff_s = ABC_DYNAMIC.response_cutoff

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


    def objective(self, vector):
        return str(sum((Fraction.from_float(float(c))*Fraction.from_float(float(x)) for c,x in zip(self.old['c'],vector)), Fraction(0)))



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

