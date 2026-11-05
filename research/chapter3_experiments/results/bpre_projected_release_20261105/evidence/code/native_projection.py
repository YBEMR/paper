"""Opt-in request-bound MATLAB adapter; native publications remain compressed.

This interface returns native_result and separately typed admission receipts.
It intentionally cannot masquerade as the legacy full-coordinate solve API.
No formal budget, MATLAB option, decoder or physical evaluator is changed.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse
from certified_projection import identity
from projection_admission import ProjectionAdmission, ProjectionRejected
from numeric_case_diagnostic.exact_equalities import transform as exact_equalities
from milp import decode, evaluate_model_candidate
from control_policy import resolve_idle_policy
from thermal import Exhausted


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def archive(path, value):
    # Unique derived filenames; never overwrite a MATLAB publication.
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def canonical(payload):
    if set(payload) != {'c','A','b','Aeq','beq','lb','ub','intcon'}:
        raise ProjectionRejected('Unexpected model fields')
    result = {}
    for key, value in payload.items():
        if key in ('A', 'Aeq'):
            if (not sparse.issparse(value) or value.format not in ('csr','csc')
                    or value.dtype != np.float64 or not value.has_canonical_format
                    or not value.has_sorted_indices or not np.isfinite(value.data).all()):
                raise ProjectionRejected('Canonical real binary64 sparse matrix required')
            # Validate buffers directly, not just possibly stale SciPy flags.
            value.check_format(full_check=True)
            for start, end in zip(value.indptr[:-1], value.indptr[1:]):
                if np.any(np.diff(value.indices[start:end]) <= 0):
                    raise ProjectionRejected('Unsorted or duplicate sparse coordinate')
            if np.any(value.data == 0):
                raise ProjectionRejected('Explicit stored sparse zero unsupported')
            matrix = value.tocsc(copy=True)
            result[key] = matrix
        else:
            expected = np.int64 if key == 'intcon' else np.float64
            valid_dtype = (value.dtype in (np.dtype('int32'),np.dtype('int64'))
                           if key=='intcon' and isinstance(value,np.ndarray)
                           else isinstance(value,np.ndarray) and value.dtype == expected)
            if not isinstance(value, np.ndarray) or value.ndim != 1 or not valid_dtype:
                raise ProjectionRejected('Strict one-dimensional model array required: '+key)
            # Windows frozen Model exports platform int32; widening signed
            # integer indices to int64 is exact and does not change index base.
            result[key] = value.astype(expected, copy=True)
    return result


class RequestRecorder:
    """Every vector gets original row admission before any decoding/evaluation.

    No schedule cache is used: callback and final each run complete original
    evaluation. This small opt-in adapter favors auditable boundary correctness.
    """
    def __init__(self, guard, model, accuracy, prefix, *, decoder=decode,
                 evaluator=evaluate_model_candidate, request_deadline=None):
        self.guard, self.model, self.accuracy = guard, model, accuracy
        self.budget, self.prefix = guard.budget, Path(prefix).resolve()
        self.decoder, self.evaluator = decoder, evaluator
        self.next_event, self.receipts, self.events = 1, [], []
        self.certificate_hash = digest(guard.certificate)
        self.array_identity = [identity(guard._original), identity(guard._reduced), identity(guard._rows)]
        self.best = None
        self.native_result = None
        self.request_deadline = self.budget.deadline if request_deadline is None else request_deadline

    def check_binding(self, prefix):
        self.guard._check()
        if self.budget.clock() >= self.request_deadline:
            raise ProjectionRejected('Original request deadline exhausted')
        if Path(prefix).resolve() != self.prefix:
            raise ProjectionRejected('Current request prefix identity mismatch')
        if digest(self.guard.certificate) != self.certificate_hash:
            raise ProjectionRejected('Request projection certificate drift')
        now = [identity(self.guard._original, check=self.guard._check),
               identity(self.guard._reduced, check=self.guard._check),
               identity(self.guard._rows, check=self.guard._check)]
        if now != self.array_identity:
            raise ProjectionRejected('Request model array identity drift')
        if self.budget.clock() >= self.request_deadline:
            raise ProjectionRejected('Request identity verification crossed deadline')

    def assess(self, native, *, final=False, publication=None):
        self.check_binding(self.prefix)
        def decoder(full):
            with self.budget.phase('projection_original_logic_decode'):
                return self.decoder(self.model, full)
        def evaluator(candidate, budget):
            if budget is not self.budget:
                raise ProjectionRejected('Original budget object changed')
            with self.budget.phase('projection_original_full_safe_evaluation'):
                return self.evaluator(self.model, candidate, self.accuracy, budget)
        call = self.guard.final_result if final else self.guard.callback_event
        with self.budget.phase('projection_original_rows_logic_full_safe'):
            receipt = call(native, decode=decoder, evaluate=evaluator)
        self.check_binding(self.prefix)
        receipt.update(request=self.prefix.name, certificate_sha256=self.certificate_hash,
                       native_vector_length=len(native['x']), original_vector_length=len(self.guard._rows['c']),
                       publication=publication, native_publication_modified=False)
        # This file records a prospective admission. Only the in-memory commit
        # after charged archival and the final binding check is authoritative.
        receipt['archive_is_not_acceptance_commit'] = True
        archive(self.prefix.parent/(self.prefix.name+f'.projection_receipt_{len(self.receipts)+1:06d}.json'), receipt)
        self.check_binding(self.prefix)  # archiving is charged before acceptance
        committed = self.budget.clock()
        if not (self.budget.start <= committed < self.budget.deadline
                and committed < self.request_deadline
                and committed-self.budget.start < self.budget.seconds):
            raise Exhausted('wall_time_limit')
        receipt['admission_committed_at_s'] = committed-self.budget.start
        self.receipts.append(receipt)
        if receipt['accepted_safe'] and (self.best is None or Fraction(
                receipt['evaluation']['safe_upper_bound_J']) < Fraction(self.best['evaluation']['safe_upper_bound_J'])):
            self.best = receipt
        return receipt

    def poll(self, prefix):
        self.check_binding(prefix)
        while self.budget.remaining > 0:
            number = self.next_event
            path = Path(f'{prefix}.event_{number:06d}.json')
            try:
                raw = path.read_bytes()
                event = json.loads(raw.decode('utf-8-sig'))
            except (FileNotFoundError, PermissionError, UnicodeDecodeError, json.JSONDecodeError):
                break
            self.check_binding(prefix)
            if not isinstance(event, dict) or event.get('event_number') != number:
                raise ProjectionRejected('Native callback sequence identity mismatch')
            self.next_event += 1
            publication = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'event_number': number,
                           'received_at_elapsed_s': float(self.budget.elapsed),
                           'metadata': {k:v for k,v in event.items() if k != 'x'}}
            self.events.append(publication)
            x = event.get('x')
            if x is not None and np.asarray(x).size:
                # MATLAB scalar encoding is normalized without changing the native file.
                raw_x = np.asarray(x)
                if raw_x.ndim > 1 or raw_x.dtype.kind not in 'fiu':
                    raise ProjectionRejected('Malformed callback vector')
                normalized = dict(event, x=raw_x.reshape(-1).tolist())
                self.assess(normalized, publication=publication)
            self.budget.check()


class ProjectedSession:
    def __init__(self, native_session, model, accuracy, budget):
        self.native, self.model, self.accuracy, self.budget = native_session, model, accuracy, budget
        if model.budget is not budget or native_session.budget is not budget:
            raise ProjectionRejected('Model/native session must share original budget object')
        self.records = []

    def solve(self, payload, *, remaining_s, budget, x0=None, solver_max_time_s=None):
        if budget is not self.budget:
            raise ProjectionRejected('Solve budget identity mismatch')
        budget.check()
        entered = budget.clock()
        if not np.isfinite(remaining_s) or remaining_s <= 0:
            raise ProjectionRejected('No finite positive request time remains')
        request_deadline = min(budget.deadline, entered+remaining_s)
        original = canonical(payload)
        if x0 is not None:
            raw_x0 = np.asarray(x0)
            if raw_x0.ndim != 1 or raw_x0.dtype.kind not in 'fiu' or not np.isfinite(raw_x0).all():
                raise ProjectionRejected('Malformed initial vector')
            original['x0'] = raw_x0.astype(np.float64, copy=True)
        else:
            # Exact-equality proof API requires x0. This zero vector is only a
            # proof placeholder; never admitted, evaluated, or sent to MATLAB.
            original['x0'] = np.zeros(len(original['c']), dtype=np.float64)
        with budget.phase('projection_exact_conversion_certificate_initial_admission'):
            represented, eqcert = exact_equalities(original)
            guard = ProjectionAdmission(represented, policy=resolve_idle_policy(self.model.instance),
                budget=budget, original_rows=original, equality_certificate=eqcert)
            native_x = None if x0 is None else guard.prepare_initial(x0)['native_x']
        reduced = guard.reduced
        reduced.pop('x0', None)
        prefix = self.native.workdir/f'request_{self.native.counter+1:06d}'
        record = RequestRecorder(guard, self.model, self.accuracy, prefix,
                                 request_deadline=request_deadline)
        archive(prefix.with_suffix('.projection_certificate.json'), guard.certificate)
        archive(prefix.with_suffix('.projection_equality_certificate.json'), eqcert)
        budget.check()
        old_consumer = getattr(self.native, 'event_consumer', None)
        def consume(prefix):
            try:
                record.poll(prefix)
            except Exhausted:
                # The original transport must generate its own timeout return,
                # Python publication and budget cancellation marker. This only
                # handles actual expiry, never numerical or binding failures.
                if budget.clock() < request_deadline:
                    raise
        self.native.event_consumer = consume
        self.records.append(record)
        try:
            remaining = request_deadline-budget.clock()
            if remaining <= 0:
                raise ProjectionRejected('Conversion exhausted original request time')
            returned = self.native.solve(reduced, remaining_s=remaining, budget=budget,
                x0=native_x, solver_max_time_s=solver_max_time_s)
            record.native_result = returned
            # Keep the exact original timeout return and cancellation evidence.
            # No binding scan, decoding or candidate assessment may start late.
            if budget.clock() >= request_deadline or not returned.get('budget_valid'):
                return {'native_result': returned, 'final_admission': None,
                        'callback_admissions': [r for r in record.receipts if r['source']=='callback'],
                        'best_safe': record.best, 'certificate_sha256': record.certificate_hash,
                        'request': prefix.name, 'budget_identity': guard._clock_identity,
                        'admission_stopped_at_deadline': True}
            record.check_binding(prefix)
            if returned.get('request_number') != self.native.counter or prefix.name != f'request_{self.native.counter:06d}':
                raise ProjectionRejected('Final request identity mismatch')
            final = None
            if returned.get('accepted_for_evaluation') and returned.get('x') and not returned.get('numerical_consistency'):
                path = prefix.with_suffix('.response.json')
                raw = path.read_bytes()
                publication = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
                final = record.assess(returned, final=True, publication=publication)
            return {'native_result': returned, 'final_admission': final,
                    'callback_admissions': [r for r in record.receipts if r['source']=='callback'],
                    'best_safe': record.best, 'certificate_sha256': record.certificate_hash,
                    'request': prefix.name, 'budget_identity': guard._clock_identity}
        except BaseException:
            # Fail closed while a native request may still be unwinding.
            if self.native.counter == int(prefix.name.split('_')[-1]):
                cancel = prefix.with_suffix('.cancel')
                if not cancel.exists():
                    cancel.write_text('projection admission stopped\n', encoding='ascii')
                self.native.request_blocked = True
            raise
        finally:
            self.native.event_consumer = old_consumer
