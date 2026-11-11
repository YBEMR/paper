"""Opt-in live transport for K133's independently checked row expression.

The physical model, original coordinates, feedback rows and evaluator stay
unchanged. Each request gets a fresh complement mapping. Only its original
prefix can reach PartialRecorder's decoder and continuous evaluator.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from augmented_payload import (append_complements, build_augmented_payload,
                               validate_projected_vector, PHYSICAL_PREFIXES)
from matlab_bridge import MatlabSession, NUMERICAL_CONSISTENCY_CONFLICT
from partial_method import PartialRecorder


PROTOCOL = 'live-original-prefix-gated-selected-exact-row-complement-transport-v1'


def build_live_augmented_payload(original, labels):
    """Select exact b-M rows explicitly; every other row keeps its old bits.

    K133's strict helper is unchanged. A physical row may retain its original
    expression only when the *sole* unsupported operation is exact binary64
    representation of b-M. Structural ambiguity still rejects the request.
    """
    names, tags = list(labels['names']), list(labels['row_tags'])
    matrix = original['A'].tocsr(copy=False)
    if (len(names) != matrix.shape[1] or len(tags) != matrix.shape[0]
            or not all(isinstance(value, str) for value in [*names, *tags])
            or len(set(names)) != len(names)):
        raise ValueError('labels have invalid lengths, types or duplicate variable names')
    rhs = np.asarray(original['b']).reshape(-1)
    low, high = (np.asarray(original[key]).reshape(-1) for key in ('lb', 'ub'))
    integer = set(np.asarray(original['intcon']).reshape(-1).tolist())
    selected_labels = {'names': names, 'row_tags': list(tags)}
    selected, retained = [], []
    for row, tag in enumerate(tags):
        if not tag.startswith(PHYSICAL_PREFIXES):
            continue
        begin, end = matrix.indptr[row:row+2]
        positions = [position for position in range(begin, end)
                     if names[int(matrix.indices[position])].startswith('w:')]
        if len(positions) != 1:
            raise ValueError(f'physical row {row} must have exactly one joint gate')
        position = positions[0]
        gate, coefficient = int(matrix.indices[position]), float(matrix.data[position])
        if not math.isfinite(coefficient) or coefficient <= 0:
            raise ValueError(f'physical row {row} must have a finite positive M gate coefficient')
        if low[gate] != 0 or high[gate] != 1 or gate in integer:
            raise ValueError(f'physical row {row} requires a continuous gate with bounds [0,1]')
        exact = Fraction.from_float(float(rhs[row]))-Fraction.from_float(coefficient)
        try:
            rounded = float(exact)
            representable = math.isfinite(rounded) and Fraction.from_float(rounded) == exact
        except OverflowError:
            representable = False
        if representable:
            selected.append(row)
        else:
            retained.append({'row': row, 'original_tag': tag,
                'gate_column': gate, 'reason': 'b-M_not_exactly_representable_binary64',
                'original_expression_retained_bitwise': True})
            # The selection label is sent only to the strict transformation
            # helper. The complete original label table is archived separately.
            selected_labels['row_tags'][row] = 'retained_original_physical/'+tag
    if not selected:
        raise ValueError('no exact physical rows eligible for complement transformation')
    augmented, mapping = build_augmented_payload(original, selected_labels)
    mapping['exact_row_selection'] = {
        'selected_original_physical_rows': selected,
        'retained_nonrepresentable_physical_rows': retained,
        'all_original_labels_preserved_in_labels_json': True,
        'unselected_rows_keep_original_expression': True,
        'strict_K133_helper_unchanged': True,
        'nonphysical_rows_unchanged_field_includes_retained_physical_rows': True}
    return augmented, mapping


def vector_present(value):
    """A scalar zero is a candidate, rather than an empty publication."""
    if value is None:
        return False
    try:
        return np.asarray(value).size != 0
    except (TypeError, ValueError):
        return True


def _save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def matrix_identity(payload):
    """Hash the actual exported arrays, not a rebuilt model."""
    identity = {}
    for key in ('A', 'Aeq'):
        matrix = payload[key].tocsc(copy=True)
        matrix.sort_indices()
        digest = hashlib.sha256()
        for value in (np.asarray(matrix.shape, dtype='<i8'),
                      matrix.indptr.astype('<i8'), matrix.indices.astype('<i8'),
                      matrix.data.astype('<f8')):
            digest.update(value.tobytes())
        identity[key] = {'shape': list(matrix.shape), 'nnz': int(matrix.nnz),
                         'canonical_sha256': digest.hexdigest()}
    for key in ('c', 'b', 'beq', 'lb', 'ub', 'intcon'):
        value = np.asarray(payload[key], dtype='<i8' if key == 'intcon' else '<f8').reshape(-1)
        identity[key] = {'length': len(value),
                         'sha256': hashlib.sha256(value.tobytes()).hexdigest()}
    return identity


class _Request:
    def __init__(self, context, recorder, original, augmented, mapping, folder, labels):
        self.context, self.recorder, self.budget = context, recorder, recorder.budget
        self.original, self.augmented, self.mapping = original, augmented, mapping
        self.folder, self.prefix = folder, None
        self.events, self.checks, self.seen_callbacks = [], [], set()
        self.final_objective = None
        self.receipt = {'request_index': len(context.requests) + 1,
            'protocol': PROTOCOL, 'prepared_at_s': self.budget.elapsed,
            'mapping_path': str(folder/'mapping.json'),
            'identities_path': str(folder/'matrix_identities.json'),
            'label_sha256': hashlib.sha256(json.dumps(labels, sort_keys=True,
                separators=(',', ':')).encode()).hexdigest(),
            'failure_reasons': [], 'numerical_checks': self.checks,
            'events': self.events, 'thermal_safe_claim': False,
            'independent_certificate': False}

    def fail(self, reason, prefix=None):
        if reason not in self.receipt['failure_reasons']:
            self.receipt['failure_reasons'].append(reason)
        self.context.fail(reason)
        prefix = self.prefix if prefix is None else Path(prefix)
        if prefix is not None and not self.receipt.get('cancel_requested'):
            try:
                prefix.with_suffix('.cancel').write_text(
                    'augmented numerical admission unresolved\n', encoding='ascii')
                self.receipt['cancel_requested'] = True
                self.receipt['cancel_published_at_s'] = self.budget.elapsed
            except OSError as error:
                self.receipt['cancel_error'] = f'{type(error).__name__}: {error}'

    def assess_vector(self, vector, source, *, objective=None, require_objective=False):
        record = {'source': source, 'started_at_s': self.budget.elapsed,
                  'accepted': False}
        self.checks.append(record)
        if self.budget.remaining <= 0:
            record['reason'] = 'BUDGET_BEFORE_NUMERICAL_ADMISSION'
            self.fail(record['reason'])
            return None
        try:
            with self.budget.phase('augmented_numerical_admission'):
                projected, report = validate_projected_vector(
                    vector, self.original, self.augmented, self.mapping)
                record['report'] = report
                if require_objective or objective is not None:
                    calculated = (report.get('original') or {}).get('objective')
                    try:
                        raw = np.asarray(objective)
                        value = np.asarray(objective, dtype=float).reshape(-1)
                        valid = (not np.iscomplexobj(raw) and value.size == 1
                            and np.isfinite(value).all() and calculated is not None)
                        tolerance = None if calculated is None else 1e-9*max(1., abs(calculated))
                        consistent = bool(valid and abs(float(value[0])-calculated) <= tolerance)
                    except (TypeError, ValueError, OverflowError):
                        consistent, tolerance = False, None
                    record['objective_check'] = {'consistent': consistent,
                        'original_c_dot_x': calculated,
                        'engineering_tolerance': tolerance,
                        'independent_energy_or_bound_claim': False}
                    if not consistent:
                        self.fail('NATIVE_OBJECTIVE_MISSING_OR_MISMATCH')
                if not report['accepted']:
                    self.fail('ORIGINAL_OR_AUGMENTED_NUMERICAL_CHECK_FAILED')
        except Exception as error:
            record['error'] = f'{type(error).__name__}: {error}'
            self.fail('NUMERICAL_ADMISSION_EXCEPTION')
            projected = None
        record.update(completed_at_s=self.budget.elapsed,
                      within_budget=self.budget.remaining > 0)
        if not record['within_budget']:
            self.fail('BUDGET_DURING_NUMERICAL_ADMISSION')
        record['accepted'] = bool(projected is not None and record['within_budget']
                                  and not self.context.failed)
        return projected if record['accepted'] else None

    def archive(self):
        self.receipt.update(latched_unresolved=self.context.failed,
            completed_at_s=self.budget.elapsed,
            within_budget=self.budget.remaining > 0)
        _save(self.folder/'admission.json', self.receipt)


class AugmentedMethodContext:
    """One invocation, one failure latch, no reusable model-dimension cache."""
    def __init__(self, *, session_factory=MatlabSession):
        self.native_session_factory = session_factory
        self.recorder = None
        self.current = None
        self.requests, self.failure_reasons = [], []
        self.failed = False

    def fail(self, reason):
        self.failed = True
        if reason not in self.failure_reasons:
            self.failure_reasons.append(reason)

    def recorder_factory(self, *args, **kwargs):
        self.recorder = AugmentedPartialRecorder(self, *args, **kwargs)
        return self.recorder

    def session_factory(self, *args, **kwargs):
        return AugmentedSession(self.native_session_factory(*args, **kwargs), self)

    def prepare(self, payload):
        if self.failed:
            raise ValueError('This invocation has a latched numerical admission failure')
        recorder = self.recorder
        if recorder is None or recorder.model is None:
            raise ValueError('The current model recorder must be bound before solve')
        budget = recorder.budget
        budget.check()
        with budget.phase('augmented_payload_transform'):
            labels = {'names': list(recorder.model.names),
                      'row_tags': [row['tag'] for row in recorder.model.rows]}
            augmented, mapping = build_live_augmented_payload(payload, labels)
        budget.check()
        folder = recorder.folder/'augmented_requests'/f'request_{len(self.requests)+1:06d}'
        with budget.phase('augmented_request_metadata'):
            folder.mkdir(parents=True, exist_ok=False)
            request = _Request(self, recorder, payload, augmented, mapping, folder, labels)
            _save(folder/'mapping.json', mapping)
            _save(folder/'labels.json', labels)
            _save(folder/'matrix_identities.json', {
                'original': matrix_identity(payload), 'augmented': matrix_identity(augmented)})
        self.current = request
        self.requests.append(request.receipt)
        recorder.request = request
        budget.check()
        return request

    def summary(self):
        return {'protocol': PROTOCOL, 'latched_unresolved': self.failed,
            'failure_reasons': list(self.failure_reasons),
            'requests': deepcopy(self.requests),
            'original_rows_required_for_every_candidate': True,
            'thermal_safe_claim': False, 'independent_certificate': False,
            'native_MaxTime_semantics': 'cooperative limit; actual call duration and stop delay require phase/wall-clock audit'}


class AugmentedPartialRecorder(PartialRecorder):
    def __init__(self, context, *args, **kwargs):
        self.context, self.request = context, None
        super().__init__(*args, **kwargs)

    def assess(self, vector, source, *, reported_objective=None, require_objective=False):
        if self.request is None:
            self.context.fail('CANDIDATE_WITHOUT_CURRENT_REQUEST')
            return None, None
        projected = self.request.assess_vector(vector, source,
            objective=reported_objective, require_objective=require_objective)
        if projected is None:
            return None, None
        # Includes logical diagnostics, exact decode, cache, original-input
        # SAFE publication and thermal witness handling in the existing path.
        return super().assess(projected.tolist(), source)

    def poll(self, prefix):
        prefix = Path(prefix)
        if self.request is None:
            self.context.fail('CALLBACK_WITHOUT_CURRENT_REQUEST')
            return
        request = self.request
        request.prefix = prefix
        if self.context.failed:
            request.fail(self.context.failure_reasons[-1], prefix)
            return
        previous, self.current_prefix = self.current_prefix, prefix
        try:
            self._cancel_slice_if_due(prefix)
            number = self.next_event.get(str(prefix), 1)
            while self.budget.remaining > 0:
                path = Path(f'{prefix}.event_{number:06d}.json')
                try:
                    event = json.loads(path.read_text(encoding='utf-8-sig'))
                except (FileNotFoundError, PermissionError, UnicodeDecodeError,
                        json.JSONDecodeError):
                    break
                self.budget.check()
                self.next_event[str(prefix)] = number + 1
                self.event_count += 1
                if (not isinstance(event, dict)
                        or isinstance(event.get('event_number'), bool)
                        or not isinstance(event.get('event_number'), int)
                        or event.get('event_number') != number):
                    request.fail('CALLBACK_EVENT_IDENTITY_MISMATCH', prefix)
                    break
                stamp = self.budget.elapsed
                row = {key: value for key, value in event.items() if key != 'x'}
                row.update(event='worker_event_received', method_elapsed_s=stamp,
                           request=prefix.name, evidence='solver-reported')
                self.progress.append(row)
                if event.get('kind') == 'solver_entered' and self.solver_entered_s is None:
                    self.solver_entered_s = stamp
                request.events.append({'number': number, 'kind': event.get('kind'),
                    'received_at_s': stamp, 'file': path.name,
                    'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                if event.get('kind') == 'callback':
                    request.seen_callbacks.add(number)
                self.log(row)
                if vector_present(event.get('x')):
                    values = event.get('values', {})
                    if not isinstance(values, dict):
                        request.fail('CALLBACK_VALUES_NOT_AN_OBJECT', prefix)
                        # Record the array gate as well, but the already
                        # latched interface failure forbids physical use.
                        self.assess(event['x'], f'{prefix.name}:event{number}')
                    else:
                        self.assess(event['x'], f'{prefix.name}:event{number}',
                            reported_objective=values.get('fval'),
                            require_objective='fval' in values)
                number += 1
                if self.context.failed:
                    break
            self._cancel_slice_if_due(prefix)
        except Exception:
            request.fail('CALLBACK_PROCESSING_EXCEPTION', prefix)
            raise
        finally:
            self.current_prefix = previous

    def summary(self):
        result = super().summary()
        result['augmented_transport'] = self.context.summary()
        return result

    def release(self):
        request = self.request
        if self.context.current is request:
            self.context.current = None
        if self.context.recorder is self:
            self.context.recorder = None
        self.request = None
        if request is not None:
            request.recorder = None
        super().release()


class AugmentedSession:
    """Transparent lifecycle wrapper; immutable native events stay native."""
    def __init__(self, session, context):
        self.session, self.context = session, context
        self._consumer = getattr(session, 'event_consumer', None)

    def __getattr__(self, name):
        return getattr(self.session, name)

    @property
    def event_consumer(self):
        return self._consumer

    @event_consumer.setter
    def event_consumer(self, value):
        self._consumer = value
        self.session.event_consumer = value

    @property
    def request_blocked(self):
        return self.context.failed or getattr(self.session, 'request_blocked', False)

    def _conflict(self, returned, request=None):
        result = dict(returned)
        prior = result.get('numerical_consistency')
        result.update(accepted_for_evaluation=False,
            numerical_consistency={'state': NUMERICAL_CONSISTENCY_CONFLICT,
                'protocol': PROTOCOL, 'reasons': list(self.context.failure_reasons),
                'native_consistency': prior,
                'scope': 'numerical path unresolved; existing independent SAFE receipts retained'})
        if request is not None:
            result['augmented_admission'] = deepcopy(request.receipt)
        return result

    def solve(self, payload, **kwargs):
        if self.context.failed:
            return self._conflict({'status': 'NUMERICAL_ADMISSION_BLOCKED',
                                  'budget_valid': False, 'x': []})
        request = None
        returned = {'status': 'AUGMENTED_INTERFACE_ERROR', 'budget_valid': False,
                    'x': [], 'accepted_for_evaluation': False}
        try:
            request = self.context.prepare(payload)
            if kwargs.get('budget', request.budget) is not request.budget:
                raise ValueError('Augmented transport requires the identical MethodBudget')
            if kwargs.get('x0') is not None:
                kwargs['x0'] = append_complements(kwargs['x0'], request.mapping)
                if request.assess_vector(kwargs['x0'], 'request_initial_point') is None:
                    raise ValueError('The augmented original initial point failed admission')
            request.budget.check()
            returned = self.session.solve(request.augmented, **kwargs)
            prefix = request.prefix
            if prefix is None:
                prefix = Path(self.session.workdir)/f'request_{getattr(self.session, "counter", 0):06d}'
                request.prefix = prefix
            request.recorder.poll(prefix)
            callbacks = returned.get('callbacks', [])
            expected = []
            if not isinstance(callbacks, list):
                request.fail('CALLBACK_RESPONSE_NOT_A_LIST')
            else:
                for callback in callbacks:
                    value = callback.get('event_number') if isinstance(callback, dict) else None
                    if (isinstance(value, bool) or not isinstance(value, int)
                            or value < 1 or value in expected):
                        request.fail('CALLBACK_RESPONSE_IDENTITY_INVALID')
                    else:
                        expected.append(value)
            complete = set(expected) == request.seen_callbacks
            if returned.get('intlinprog_entered') and not any(
                    event['kind'] == 'solver_entered' for event in request.events):
                complete = False
            request.receipt.update(expected_callback_numbers=sorted(expected),
                checked_callback_numbers=sorted(request.seen_callbacks),
                callback_publications_complete=complete)
            if not complete:
                request.fail('CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED')
            if (returned.get('numerical_consistency') or {}).get('state') == NUMERICAL_CONSISTENCY_CONFLICT:
                request.fail('NATIVE_NUMERICAL_CONSISTENCY_CONFLICT')
            if vector_present(returned.get('x')):
                request.final_objective = returned.get('fval')
                projected = request.assess_vector(returned['x'], 'final_return',
                    objective=request.final_objective, require_objective=True)
            if request.budget.remaining <= 0:
                request.fail('BUDGET_BEFORE_FINAL_ADMISSION')
            request.receipt['native_status'] = returned.get('status')
            request.receipt['native_exitflag'] = returned.get('exitflag')
            request.receipt['solver_reported_only'] = True
            request.archive()
            if request.budget.remaining <= 0:
                request.fail('BUDGET_DURING_ADMISSION_ARCHIVE')
                # Pure serialization of an already formed refusal; cannot
                # add a candidate/heat/energy receipt after the cutoff.
                request.archive()
            if self.context.failed:
                returned = self._conflict(returned, request)
            else:
                returned = dict(returned)
                returned['augmented_admission'] = deepcopy(request.receipt)
            return returned
        except Exception as error:
            self.context.fail('AUGMENTED_TRANSPORT_EXCEPTION')
            if request is not None:
                request.fail('AUGMENTED_TRANSPORT_EXCEPTION')
                request.receipt['exception'] = f'{type(error).__name__}: {error}'
                try:
                    request.archive()
                except Exception:
                    pass
            # An exception in live polling can unwind a still-active worker.
            # Do not reuse it or publish another request. The existing outer
            # finally remains responsible for closing the owned worker.
            try:
                self.session.request_blocked = True
            except (AttributeError, TypeError):
                pass  # The wrapper's request_blocked property still latches.
            returned['budget_valid'] = bool(
                request.budget.remaining > 0 if request is not None
                else self.context.recorder is not None
                and self.context.recorder.budget.remaining > 0)
            returned['error'] = f'{type(error).__name__}: {error}'
            return self._conflict(returned, request)

    def close(self):
        self.event_consumer = None
        return self.session.close()
