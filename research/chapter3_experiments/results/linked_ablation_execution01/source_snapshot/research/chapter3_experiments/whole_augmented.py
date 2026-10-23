"""Opt-in whole-model complement transport; no solver/model work on import.

Keep the complete whole Recorder, evaluator and final-candidate feedback loop.
Only numeric transport/admission changes.  Native receipts are never rewritten
as projected receipts.  Local PartialRecorder/slice/publication rules are not
used here.  A caller still needs a separately authorized invocation budget.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from augmented_method import build_live_augmented_payload, matrix_identity, vector_present
from augmented_payload import append_complements, validate_projected_vector
from diagnostic_search import Recorder
from matlab_bridge import MatlabSession, NUMERICAL_CONSISTENCY_CONFLICT
from thermal import Exhausted


PROTOCOL = 'whole-original-prefix-gated-selected-exact-complement-v1'


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _identity(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


class _WholeRequest:
    def __init__(self, context, recorder):
        self.context, self.recorder, self.budget = context, recorder, recorder.budget
        self.original = self.augmented = self.mapping = None
        self.folder = self.prefix = None
        self.checks, self.events, self.seen_callbacks = [], [], set()
        self.receipt = {
            'request_index': len(context.requests) + 1, 'protocol': PROTOCOL,
            'started_at_s': self.budget.elapsed, 'failure_reasons': [],
            'failure_categories': [], 'numerical_checks': self.checks,
            'events': self.events, 'native_called': False,
            'native_round_index': None, 'native_prefix': None,
            'thermal_safe_claim': False, 'independent_certificate': False,
            'candidate_coordinates': 'augmented; only admitted original prefix is decoded'}

    def fail(self, reason, category='numerical'):
        """Latch without replacing a budget/other existing cancellation file."""
        if reason not in self.receipt['failure_reasons']:
            self.receipt['failure_reasons'].append(reason)
        if category not in self.receipt['failure_categories']:
            self.receipt['failure_categories'].append(category)
        self.context.fail(reason, category)
        if self.prefix is None:
            return
        path = self.prefix.with_suffix('.cancel')
        try:
            with path.open('x', encoding='ascii') as stream:
                stream.write('budget\n' if category == 'budget' else
                             'whole augmented numerical admission unresolved\n')
            self.receipt['cancel_created'] = True
        except FileExistsError:
            self.receipt['existing_cancel_preserved'] = True
        except OSError as error:
            self.receipt['cancel_error'] = f'{type(error).__name__}: {error}'
        if path.is_file():
            try:
                self.receipt['cancel_sha256'] = _sha(path)
            except OSError as error:
                self.receipt['cancel_hash_error'] = f'{type(error).__name__}: {error}'
        self.receipt['cancel_requested_at_s'] = self.budget.elapsed

    def assess_vector(self, vector, source, *, objective=None, require_objective=False):
        record = {'source': source, 'started_at_s': self.budget.elapsed,
                  'accepted': False}
        self.checks.append(record)
        if self.budget.remaining <= 0:
            self.fail('BUDGET_BEFORE_NUMERICAL_ADMISSION', 'budget')
            record['reason'] = 'BUDGET_BEFORE_NUMERICAL_ADMISSION'
            return None
        if self.context.failed:
            record['reason'] = 'FAILURE_LATCH_ALREADY_SET'
            return None
        projected = None
        try:
            with self.budget.phase('whole_augmented_numerical_admission'):
                projected, report = validate_projected_vector(
                    vector, self.original, self.augmented, self.mapping)
                record['report'] = report
                if require_objective or objective is not None:
                    calculated = (report.get('original') or {}).get('objective')
                    try:
                        raw = np.asarray(objective)
                        values = np.asarray(objective, dtype=float).reshape(-1)
                        valid = (not np.iscomplexobj(raw) and values.size == 1
                                 and np.isfinite(values).all() and calculated is not None)
                        tolerance = None if calculated is None else 1e-9 * max(1., abs(calculated))
                        consistent = bool(valid and abs(float(values[0]) - calculated) <= tolerance)
                    except (TypeError, ValueError, OverflowError):
                        consistent, tolerance = False, None
                    record['objective_check'] = {
                        'consistent': consistent, 'original_c_dot_x': calculated,
                        'engineering_tolerance': tolerance,
                        'independent_energy_or_bound_claim': False}
                    if not consistent:
                        self.fail('NATIVE_OBJECTIVE_MISSING_OR_MISMATCH')
                if not report['accepted']:
                    self.fail('ORIGINAL_OR_AUGMENTED_NUMERICAL_CHECK_FAILED')
        except Exhausted:
            self.fail('BUDGET_DURING_NUMERICAL_ADMISSION', 'budget')
        except Exception as error:
            record['error'] = f'{type(error).__name__}: {error}'
            self.fail('NUMERICAL_ADMISSION_EXCEPTION')
        record.update(completed_at_s=self.budget.elapsed,
                      within_budget=self.budget.remaining > 0)
        if not record['within_budget']:
            self.fail('BUDGET_DURING_NUMERICAL_ADMISSION', 'budget')
        record['accepted'] = bool(projected is not None and record['within_budget']
                                  and not self.context.failed)
        return projected if record['accepted'] else None

    def archive(self):
        if self.folder is not None:
            # After cutoff this only serializes already formed records.  It
            # never rechecks a vector or adds an energy/thermal receipt.
            self.receipt['latched_unresolved'] = self.context.failed
            self.receipt['serialized_at_s'] = self.budget.elapsed
            try:
                _save(self.folder / 'admission.json', self.receipt)
            except (OSError, TypeError, ValueError) as error:
                self.receipt['archive_error'] = f'{type(error).__name__}: {error}'
                self.fail('WHOLE_AUGMENTED_ADMISSION_ARCHIVE_FAILED', 'interface')
                return False
        return True


class WholeAugmentedContext:
    """One whole invocation; fresh mapping per request, one failure latch."""
    def __init__(self, *, session_factory=MatlabSession, recorder_kwargs=None):
        self.native_session_factory = session_factory
        self.recorder_kwargs = dict(recorder_kwargs or {})
        self.recorder = self.current = None
        self.requests, self.native_rounds = [], []
        self.failure_reasons, self.failure_categories = [], []
        self.failed = False

    def fail(self, reason, category='numerical'):
        self.failed = True
        if reason not in self.failure_reasons:
            self.failure_reasons.append(reason)
        if category not in self.failure_categories:
            self.failure_categories.append(category)

    def recorder_factory(self, model, accuracy, budget, folder, **kwargs):
        if self.recorder is not None:
            raise ValueError('One whole invocation must not replace its Recorder')
        options = dict(self.recorder_kwargs)
        options.update(kwargs)
        self.recorder = WholeAugmentedRecorder(self, model, accuracy, budget, folder, **options)
        return self.recorder

    def session_factory(self, *args, **kwargs):
        return WholeAugmentedSession(self.native_session_factory(*args, **kwargs), self)

    def prepare(self, payload):
        if self.failed:
            raise ValueError('This whole invocation has a latched unresolved request')
        if self.recorder is None or self.recorder.model is None:
            raise ValueError('Whole recorder must be bound before a numeric request')
        recorder, budget = self.recorder, self.recorder.budget
        request = _WholeRequest(self, recorder)
        self.requests.append(request)
        self.current = recorder.request = request
        budget.check()
        with budget.phase('whole_augmented_payload_transform'):
            labels = {'names': list(recorder.model.names),
                      'row_tags': [row['tag'] for row in recorder.model.rows]}
            augmented, mapping = build_live_augmented_payload(payload, labels)
            identities = {'original': matrix_identity(payload),
                          'augmented': matrix_identity(augmented)}
        budget.check()
        request.original, request.augmented, request.mapping = payload, augmented, mapping
        with budget.phase('whole_augmented_request_metadata'):
            folder = recorder.folder / 'augmented_requests' / f'request_{len(self.requests):06d}'
            folder.mkdir(parents=True, exist_ok=False)
            request.folder = folder
            for name, value in (('mapping', mapping), ('labels', labels),
                                ('matrix_identities', identities)):
                path = folder / (name + '.json')
                _save(path, value)
                request.receipt[name + '_path'] = str(path)
                request.receipt[name + '_sha256'] = _sha(path)
            request.receipt.update(original_n=mapping['original_n'],
                augmented_n=mapping['augmented_n'],
                matrix_identity_sha256=_identity(identities),
                original_matrix_identity_sha256=_identity(identities['original']),
                augmented_matrix_identity_sha256=_identity(identities['augmented']))
        budget.check()
        return request

    def summary(self):
        return {'protocol': PROTOCOL, 'latched_unresolved': self.failed,
                'failure_reasons': list(self.failure_reasons),
                'failure_categories': list(self.failure_categories),
                'requests': [deepcopy(item.receipt) for item in self.requests],
                'native_rounds_count': len(self.native_rounds),
                'thermal_safe_claim': False, 'independent_certificate': False,
                'solver_bounds_independently_certified': False,
                'whole_lifecycle_preserved': True,
                'scope': 'numeric transport/admission; complete whole evaluation and final feedback unchanged'}

    def solve_formal_diagnostic(self, model, session, accuracy, budget, **kwargs):
        from formal_milp import solve_formal_diagnostic
        if 'recorder_factory' in kwargs:
            raise ValueError('The whole augmented recorder binding cannot be overridden')
        result = solve_formal_diagnostic(model, session, accuracy, budget,
                                        recorder_factory=self.recorder_factory, **kwargs)
        for request in self.requests:
            request.archive()
        # The unchanged formal loop uses budget_valid before its consistency
        # branch.  A native technical failure may set that flag false while
        # root time remains; keep its old reason as evidence, not a timeout.
        if (self.failed and set(self.failure_categories) - {'budget'}
                and budget.remaining > 0
                and result.get('reason') == 'SOLVER_RETURN_AFTER_BUDGET'):
            result['formal_reason_before_admission_classification'] = result['reason']
            result['reason'] = 'WHOLE_AUGMENTED_TRANSPORT_UNRESOLVED'
        if any(item.receipt.get('archive_error') for item in self.requests):
            result['reason'] = 'WHOLE_AUGMENTED_ADMISSION_ARCHIVE_UNRESOLVED'
        result['native_rounds'] = deepcopy(self.native_rounds)
        result['whole_augmented'] = self.summary()
        return result


class WholeAugmentedRecorder(Recorder):
    """The original complete Recorder, with a numeric gate before its decoder."""
    def __init__(self, context, *args, **kwargs):
        self.context, self.request = context, None
        super().__init__(*args, **kwargs)

    def assess(self, vector, source, *, reported_objective=None, require_objective=False):
        if self.request is None:
            self.context.fail('CANDIDATE_WITHOUT_CURRENT_WHOLE_REQUEST', 'interface')
            return None, None
        projected = self.request.assess_vector(vector, source,
            objective=reported_objective, require_objective=require_objective)
        if projected is None:
            return None, None
        return super().assess(projected.tolist(), source)

    def poll(self, prefix):
        prefix = Path(prefix)
        request = self.request
        if request is None:
            self.context.fail('CALLBACK_WITHOUT_CURRENT_WHOLE_REQUEST', 'interface')
            return
        if request.prefix is not None and request.prefix != prefix:
            request.fail('CALLBACK_REQUEST_PREFIX_CHANGED', 'interface')
            return
        request.prefix = prefix
        if self.context.failed:
            request.fail(self.context.failure_reasons[-1], self.context.failure_categories[-1])
            return
        number = self.next_event.get(str(prefix), 1)
        try:
            while self.budget.remaining > 0:
                path = Path(f'{prefix}.event_{number:06d}.json')
                try:
                    raw = path.read_bytes()
                    event = json.loads(raw.decode('utf-8-sig'))
                except (FileNotFoundError, PermissionError, UnicodeDecodeError, json.JSONDecodeError):
                    break
                self.budget.check()
                if (not isinstance(event, dict) or type(event.get('event_number')) is not int
                        or event['event_number'] != number):
                    request.fail('CALLBACK_EVENT_IDENTITY_MISMATCH', 'interface')
                    break
                self.next_event[str(prefix)] = number + 1
                self.event_count += 1
                stamp = self.budget.elapsed
                row = {key: value for key, value in event.items() if key != 'x'}
                row.update(event='worker_event_received', method_elapsed_s=stamp,
                           request=prefix.name, evidence='solver-reported')
                self.progress.append(row)
                if event.get('kind') == 'solver_entered' and self.solver_entered_s is None:
                    self.solver_entered_s = stamp
                request.events.append({'number': number, 'kind': event.get('kind'),
                    'received_at_s': stamp, 'file': str(path),
                    'file_sha256': hashlib.sha256(raw).hexdigest()})
                if event.get('kind') == 'callback':
                    request.seen_callbacks.add(number)
                    request.events[-1]['callback_summary_sha256'] = _identity(
                        {key: value for key, value in event.items() if key != 'x'})
                self.log(row)
                if vector_present(event.get('x')):
                    values = event.get('values', {})
                    if not isinstance(values, dict):
                        request.fail('CALLBACK_VALUES_NOT_AN_OBJECT', 'interface')
                    else:
                        self.assess(event['x'], f'{prefix.name}:event{number}',
                            reported_objective=values.get('fval'),
                            require_objective='fval' in values)
                number += 1
                if self.context.failed:
                    break
        except Exhausted:
            request.fail('BUDGET_DURING_CALLBACK_ADMISSION', 'budget')
            raise
        except Exception:
            request.fail('CALLBACK_PROCESSING_EXCEPTION', 'interface')
            raise

    def summary(self):
        result = super().summary()
        result['whole_augmented_transport'] = self.context.summary()
        return result


class WholeAugmentedSession:
    """Delegate native lifecycle; retain raw native returns independently."""
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

    def _derived(self, native, request):
        result = deepcopy(native)
        if self.context.failed:
            result['accepted_for_evaluation'] = False
            if set(self.context.failure_categories) <= {'budget'}:
                result.update(status='BUDGET_EXHAUSTED_WHOLE_AUGMENTED_ADMISSION',
                              budget_valid=False, x=[])
            else:
                result['numerical_consistency'] = {
                    'state': NUMERICAL_CONSISTENCY_CONFLICT, 'protocol': PROTOCOL,
                    'reasons': list(self.context.failure_reasons),
                    'categories': list(self.context.failure_categories),
                    'native_consistency': deepcopy(native.get('numerical_consistency')),
                    'scope': 'transport/admission unresolved; previously formed complete SAFE retained'}
        token = {'protocol': PROTOCOL,
                 'request_index': None if request is None else request.receipt['request_index'],
                 'native_round_index': None if request is None else request.receipt['native_round_index'],
                 'native_return_sha256': None if request is None else request.receipt.get('native_return_sha256'),
                 'matrix_identity_sha256': None if request is None else request.receipt.get('matrix_identity_sha256'),
                 'candidate_coordinates': 'augmented'}
        result['whole_augmented_request'] = token
        if request is not None:
            request.receipt['derived_return_sha256'] = _identity(result)
            if not request.archive():
                # An archival fault cannot discard a SAFE already held by the
                # complete Recorder.  It does block further numeric admission.
                result['accepted_for_evaluation'] = False
                result['numerical_consistency'] = {
                    'state': NUMERICAL_CONSISTENCY_CONFLICT, 'protocol': PROTOCOL,
                    'reasons': list(self.context.failure_reasons),
                    'categories': list(self.context.failure_categories),
                    'native_consistency': deepcopy(native.get('numerical_consistency')),
                    'scope': 'admission archive unresolved; prior complete SAFE retained'}
                request.receipt['derived_return_sha256'] = _identity(result)
        return result

    def solve(self, payload, **kwargs):
        request = None
        native = {'status': 'WHOLE_AUGMENTED_INTERFACE_ERROR', 'budget_valid': False,
                  'x': [], 'accepted_for_evaluation': False}
        if self.context.failed:
            return self._derived(native, None)
        try:
            request = self.context.prepare(payload)
            if kwargs.get('budget', request.budget) is not request.budget:
                raise ValueError('Whole augmented transport requires the identical MethodBudget')
            if kwargs.get('x0') is not None:
                kwargs['x0'] = append_complements(kwargs['x0'], request.mapping)
                if request.assess_vector(kwargs['x0'], 'request_initial_point') is None:
                    return self._derived(native, request)
            request.budget.check()
            before = getattr(self.session, 'counter', 0)
            if type(before) is not int or before < 0:
                raise ValueError('Native session counter must be a nonnegative integer')
            request.prefix = Path(self.session.workdir) / f'request_{before + 1:06d}'
            request.receipt['native_prefix'] = str(request.prefix)
            request.receipt['expected_native_request_number'] = before + 1
            request.receipt['native_called'] = True
            native = self.session.solve(request.augmented, **kwargs)
            if not isinstance(native, dict):
                raise ValueError('Native return must be a dictionary')
            # Capture the unmodified original return before any admission or
            # cutoff handling.  A late return is evidence, not a new safe U.
            self.context.native_rounds.append(deepcopy(native))
            request.receipt.update(native_round_index=len(self.context.native_rounds),
                native_return_sha256=_identity(native),
                native_request_number=native.get('request_number'))
            explicit_budget_status = (isinstance(native.get('status'), str)
                                      and native['status'].startswith('BUDGET_'))
            budget_stop = (not native.get('error') and
                (explicit_budget_status or (request.budget.remaining <= 0
                    and native.get('status') not in ('WORKER_EXITED', 'INTERFACE_ERROR'))))
            # An explicitly budget-stopped request may end before submission
            # and lack a native number.  Every numbered/submitted result must
            # match the counter and prefix chosen for this very request.
            supplied_number = native.get('request_number')
            number_valid = (type(supplied_number) is int and supplied_number == before + 1)
            unnumbered_budget = budget_stop and supplied_number is None
            request.receipt['native_request_number_matches'] = number_valid
            request.receipt['unnumbered_budget_stop'] = unnumbered_budget
            if not number_valid and not unnumbered_budget:
                request.fail('NATIVE_REQUEST_NUMBER_MISMATCH', 'interface')
            path = request.prefix.with_suffix('.python.json')
            request.receipt['native_json_path'] = str(path)
            if path.is_file():
                raw = path.read_bytes()
                request.receipt['native_json_sha256'] = hashlib.sha256(raw).hexdigest()
                if json.loads(raw.decode('utf-8-sig')) != native:
                    request.fail('NATIVE_PYTHON_RETURN_IDENTITY_MISMATCH', 'interface')
            else:
                if unnumbered_budget:
                    request.receipt['native_unpublished_budget_stop'] = True
                else:
                    request.fail('NATIVE_PYTHON_RETURN_MISSING', 'interface')
            if budget_stop:
                request.fail('BUDGET_BEFORE_FINAL_NUMERICAL_ADMISSION', 'budget')
                return self._derived(native, request)
            if not native.get('budget_valid'):
                request.fail('NATIVE_TECHNICAL_OR_INTERFACE_FAILURE', 'interface')
                return self._derived(native, request)
            if native.get('status') != 'SOLVED' or native.get('error'):
                request.fail('NATIVE_TECHNICAL_OR_INTERFACE_FAILURE', 'interface')
                return self._derived(native, request)
            request.recorder.poll(request.prefix)
            callbacks, expected = native.get('callbacks', []), []
            if not isinstance(callbacks, list):
                request.fail('CALLBACK_RESPONSE_NOT_A_LIST', 'interface')
            else:
                for callback in callbacks:
                    number = callback.get('event_number') if isinstance(callback, dict) else None
                    if type(number) is not int or number < 1 or number in expected:
                        request.fail('CALLBACK_RESPONSE_IDENTITY_INVALID', 'interface')
                    else:
                        expected.append(number)
                        summary = _identity({key: value for key, value in callback.items()
                                             if key != 'x'})
                        published = next((event for event in request.events
                                          if event['kind'] == 'callback'
                                          and event['number'] == number), None)
                        if published is not None and summary != published['callback_summary_sha256']:
                            request.fail('CALLBACK_RESPONSE_CONTENT_IDENTITY_MISMATCH', 'interface')
            complete = set(expected) == request.seen_callbacks
            if native.get('intlinprog_entered') and not any(
                    event['kind'] == 'solver_entered' for event in request.events):
                complete = False
            request.receipt.update(expected_callback_numbers=sorted(expected),
                checked_callback_numbers=sorted(request.seen_callbacks),
                callback_publications_complete=complete)
            if not complete:
                request.fail('CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED', 'interface')
            if (native.get('numerical_consistency') or {}).get('state') == NUMERICAL_CONSISTENCY_CONFLICT:
                request.fail('NATIVE_NUMERICAL_CONSISTENCY_CONFLICT')
            if vector_present(native.get('x')):
                request.assess_vector(native['x'], 'final_return',
                                      objective=native.get('fval'), require_objective=True)
            if request.budget.remaining <= 0:
                request.fail('BUDGET_DURING_FINAL_NUMERICAL_ADMISSION', 'budget')
            return self._derived(native, request)
        except Exhausted:
            request = request or self.context.current
            if request is not None:
                request.fail('BUDGET_DURING_WHOLE_AUGMENTED_TRANSPORT', 'budget')
            else:
                self.context.fail('BUDGET_DURING_WHOLE_AUGMENTED_TRANSPORT', 'budget')
            return self._derived(native, request)
        except Exception as error:
            request = request or self.context.current
            if request is not None:
                request.fail('WHOLE_AUGMENTED_TRANSPORT_EXCEPTION', 'interface')
                request.receipt['exception'] = f'{type(error).__name__}: {error}'
            else:
                self.context.fail('WHOLE_AUGMENTED_TRANSPORT_EXCEPTION', 'interface')
            # The complete original result remains in native_rounds if the
            # native call returned.  Never append another request after error.
            derived_native = deepcopy(native)
            derived_native['error'] = f'{type(error).__name__}: {error}'
            return self._derived(derived_native, request)

    def close(self):
        self.event_consumer = None
        return self.session.close()


def execute_whole_augmented(input_loader, out, *, seconds,
                            feedback_kind='conditional', clock=time.monotonic,
                            session_factory=MatlabSession, model_builder=None):
    """Opt-in full entry; original InitialSession remains outside this adapter."""
    from formal_milp import execute_formal_milp
    context = WholeAugmentedContext(session_factory=session_factory)
    options = {} if model_builder is None else {'model_builder': model_builder}
    return execute_formal_milp(input_loader, out, seconds=seconds, clock=clock,
        feedback_kind=feedback_kind, session_factory=context.session_factory,
        diagnostic_solver=context.solve_formal_diagnostic, **options)


def audit_whole_augmented_evidence(result, folder=None):
    """Read-only record-identity audit, not a numeric/thermal/optimality proof.

    This does not relax audit_whole's native equality rule.  The new derived
    result has its own identity, paired with the original saved Python return.
    No model is reconstructed and no vector is re-admitted by this function.
    """
    checks, errors = [], []

    def check(name, passed):
        checks.append({'id': name, 'passed': bool(passed)})
        if not passed:
            errors.append(name)

    def resolve(value):
        path = Path(value)
        return path if path.is_absolute() or folder is None else Path(folder) / path

    if not isinstance(result, dict):
        return {'passed': False, 'checks': [{'id': 'result_object', 'passed': False}],
                'errors': ['result_object'], 'scope': 'record_identity_only'}
    context = result.get('whole_augmented') or {}
    if not isinstance(context, dict):
        return {'passed': False, 'checks': [{'id': 'context_object', 'passed': False}],
                'errors': ['context_object'], 'scope': 'record_identity_only'}
    requests, rounds, native = (context.get('requests', []), result.get('rounds', []),
                                result.get('native_rounds', []))
    check('protocol', context.get('protocol') == PROTOCOL)
    check('record_shapes', all(isinstance(value, list) for value in (requests, rounds, native)))
    if not checks[-1]['passed']:
        return {'passed': False, 'checks': checks, 'errors': errors,
                'scope': 'record_identity_only; not a physical safety or optimality certificate'}
    check('native_rounds_count', context.get('native_rounds_count') == len(native))
    check('all_rounds_have_request', len(rounds) == len(requests))
    used_native = []
    for index, request in enumerate(requests, 1):
        prefix = f'request{index}:'
        try:
            check(prefix + 'index', request['request_index'] == index)
            derived = rounds[index - 1]
            token = derived.get('whole_augmented_request') or {}
            check(prefix + 'derived_identity', _identity(derived) == request['derived_return_sha256'])
            check(prefix + 'derived_binding', token.get('protocol') == PROTOCOL
                  and token.get('request_index') == index
                  and token.get('native_round_index') == request['native_round_index']
                  and token.get('native_return_sha256') == request.get('native_return_sha256')
                  and token.get('matrix_identity_sha256') == request.get('matrix_identity_sha256'))
            for name in ('mapping', 'labels', 'matrix_identities'):
                if name + '_path' in request:
                    path = resolve(request[name + '_path'])
                    check(prefix + name + '_file', _sha(path) == request[name + '_sha256'])
            if 'matrix_identities_path' in request:
                identities = _load(resolve(request['matrix_identities_path']))
                check(prefix + 'matrix_binding', _identity(identities) == request['matrix_identity_sha256']
                      and _identity(identities['original']) == request['original_matrix_identity_sha256']
                      and _identity(identities['augmented']) == request['augmented_matrix_identity_sha256'])
            number = request.get('native_round_index')
            if number is not None:
                check(prefix + 'native_index', type(number) is int and 1 <= number <= len(native)
                      and number not in used_native)
                used_native.append(number)
                raw = native[number - 1]
                check(prefix + 'native_return_identity', _identity(raw) == request['native_return_sha256'])
                expected_number = request['expected_native_request_number']
                check(prefix + 'native_request_number', type(expected_number) is int
                      and expected_number == index
                      and Path(request['native_prefix']).name == f'request_{expected_number:06d}'
                      and ((type(raw.get('request_number')) is int
                            and raw['request_number'] == expected_number)
                           or (raw.get('request_number') is None
                               and request.get('unnumbered_budget_stop') is True
                               and not derived.get('budget_valid')
                               and not derived.get('accepted_for_evaluation'))))
                if not request.get('native_unpublished_budget_stop'):
                    path = resolve(request['native_json_path'])
                    check(prefix + 'native_file_identity', _sha(path) == request['native_json_sha256']
                          and _load(path) == raw)
                else:
                    check(prefix + 'unpublished_budget_not_accepted',
                          request.get('unnumbered_budget_stop') is True
                          and request.get('failure_categories') == ['budget']
                          and not derived.get('accepted_for_evaluation'))
                # Only an admitted path claims complete callback coverage;
                # refusal/cutoff keeps raw evidence without claiming coverage.
                admitted = bool(derived.get('accepted_for_evaluation'))
                check(prefix + 'callback_coverage', not admitted or
                      request.get('callback_publications_complete') is True)
                if admitted and vector_present(raw.get('x')):
                    check(prefix + 'final_numeric_gate', any(
                        item.get('source') == 'final_return' and item.get('accepted')
                        and item.get('within_budget') and item.get('report', {}).get('accepted')
                        and item.get('objective_check', {}).get('consistent')
                        for item in request.get('numerical_checks', [])))
            else:
                check(prefix + 'no_native_accepted', not derived.get('accepted_for_evaluation'))
            for event in request.get('events', []):
                path = resolve(event['file'])
                check(prefix + f"event{event['number']}_identity", _sha(path) == event['file_sha256'])
            check(prefix + 'failure_not_admitted', not request.get('failure_reasons')
                  or not derived.get('accepted_for_evaluation'))
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, OSError,
                json.JSONDecodeError):
            check(prefix + 'required_record_or_file', False)
    check('native_rounds_used_once', sorted(used_native) == list(range(1, len(native) + 1)))
    check('no_certificate_upgrade', context.get('independent_certificate') is False
          and context.get('thermal_safe_claim') is False)
    return {'passed': not errors, 'checks': checks, 'errors': errors,
            'scope': 'record_identity_only; not a physical safety or optimality certificate'}
