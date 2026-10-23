"""K167 whole transport fixtures, never a scientific or native experiment.

Only hand-written small sparse arrays, a fake native session and explicit
decoder/evaluator stubs are used. Real code objects are guarded as well as
module attributes, so captured defaults cannot silently bypass the guard.
Every invocation requires a fresh --out directory; failures are retained.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
from functools import partial
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
import scipy.linalg
import scipy.optimize

import augmented_method
from augmented_payload import validate_projected_vector
import diagnostic_search
import formal_milp
import initial_point
import initial_schedule
import matlab_bridge
import milp
import milp_coefficients
import scene_adapter
import thermal
from timing import MethodBudget
import whole_augmented


HERE = Path(__file__).resolve().parent
OUT = None
FIXTURE_RECORDS = []


class ScientificGuardViolation(KeyboardInterrupt):
    """Abort the entire suite before a forbidden real entry can execute."""


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Clock:
    def __init__(self):
        self.value = 0.

    def __call__(self):
        return self.value

    def tick(self, seconds):
        self.value += seconds


class ToyModel:
    """Shared integer deployment plus two scenes, with no physical model."""
    def __init__(self, budget, *, mixed=False):
        self.budget = budget
        self.names = ['x:shared:A:CPU0', 'w:AB:0:state', 'z:AB',
                      'w:AC:0:state', 'z:AC']
        self.logical_binary = [0, 1, 3]
        self.instance = {'id': 'handwritten_fixture',
                         'scenarios': [{'id': 'AB'}, {'id': 'AC'}]}
        self.rows = [
            {'coef': {1: 1000., 2: 1.}, 'rhs': 1000., 'tag': 'thermal_propagation/AB/upper'},
            {'coef': {3: 1000., 4: 1.}, 'rhs': 1000., 'tag': 'complete_energy/AC/upper'},
            {'coef': {0: -1., 1: 1.}, 'rhs': 0., 'tag': 'shared_link/AB'},
            {'coef': {0: -1., 3: 1.}, 'rhs': 0., 'tag': 'shared_link/AC'}]
        if mixed:
            self.rows.append({'coef': {1: 2. ** -54, 2: 1.}, 'rhs': 1.,
                              'tag': 'thermal_propagation/retained/upper'})

    def as_solver_dict(self):
        self.budget.check()
        return {'c': np.array([0., 0., .5, 0., .5]),
                'A': sparse.csr_matrix([[r['coef'].get(j, 0.) for j in range(5)]
                                       for r in self.rows]),
                'b': np.array([r['rhs'] for r in self.rows]),
                'Aeq': sparse.csr_matrix((0, 5)), 'beq': np.empty(0),
                'lb': np.zeros(5), 'ub': np.ones(5), 'intcon': np.array([0])}


GOOD = [1., 1., 0., 1., 0., 0., 0.]
SLOW = [1., 0., 1., 0., 1., 1., 1.]


class FakeNative:
    """Explicit vectors and immutable publications, no numerical optimizer."""
    def __init__(self, scripts, clock):
        self.scripts, self.clock = list(scripts), clock
        self.calls, self.sessions = [], []

    def factory(self, workdir, *, total_budget_s, budget):
        owner = self

        class Session:
            def __init__(self):
                self.workdir = Path(workdir)
                self.workdir.mkdir(parents=True, exist_ok=False)
                self.counter, self.event_consumer = 0, None
                self.budget, self.closed, self.request_blocked = budget, False, False
                owner.sessions.append(self)

            def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
                assert budget is self.budget
                item = owner.scripts.pop(0)
                self.counter += 1
                prefix = self.workdir / f'request_{self.counter:06d}'
                owner.calls.append({'payload': deepcopy(payload), 'x0': deepcopy(x0),
                                    'remaining_s': remaining_s, 'budget_id': id(budget),
                                    'prefix': str(prefix)})
                if item.get('preexisting_budget_cancel'):
                    prefix.with_suffix('.cancel').write_text('budget\n', encoding='ascii')
                owner.clock.tick(item.get('advance_before_callback', 0.))
                callbacks = item.get('callbacks', [GOOD])
                events = [{'kind': 'solver_entered', 'event_number': 1}]
                for number, vector in enumerate(callbacks, 2):
                    dimension_ok = np.asarray(vector).size == len(payload['c'])
                    value = float(payload['c'] @ np.asarray(vector)) if dimension_ok else 0.
                    events.append({'kind': 'callback', 'event_number': number, 'x': vector,
                                   'values': {'fval': item.get('callback_fval', value)}})
                for event in events:
                    if not (item.get('omit_publication') and event['kind'] == 'callback'):
                        write(Path(str(prefix) + f'.event_{event["event_number"]:06d}.json'), event)
                    if self.event_consumer is not None:
                        self.event_consumer(prefix)
                if item.get('raise_after_callback'):
                    raise RuntimeError('EXPLICIT_FAKE_NATIVE_FAILURE')
                owner.clock.tick(item.get('advance_after_callback', 0.))
                final = item.get('final', callbacks[-1] if callbacks else [])
                dimension_ok = np.asarray(final).size == len(payload['c'])
                value = float(payload['c'] @ np.asarray(final)) if dimension_ok else 0.
                result = {'request_number': item.get('request_number', self.counter),
                          'status': item.get('status', 'SOLVED'),
                          'x': final, 'fval': item.get('final_fval', value),
                          'exitflag': item.get('exitflag', 1),
                          'budget_valid': item.get('budget_valid', budget.remaining > 0),
                          'accepted_for_evaluation': budget.remaining > 0,
                          'intlinprog_entered': True, 'output': {},
                          'callbacks': [event for event in events if event['kind'] == 'callback']}
                if item.get('native_conflict'):
                    result['numerical_consistency'] = {'state': matlab_bridge.NUMERICAL_CONSISTENCY_CONFLICT}
                write(prefix.with_suffix('.python.json'), result)
                return result

            def close(self):
                self.event_consumer, self.closed = None, True

        return Session()


class WholeAugmentedTests(unittest.TestCase):
    def setUp(self):
        self.path = OUT / 'fixtures' / self._testMethodName
        self.path.mkdir(parents=True, exist_ok=False)

    def harness(self, scripts, *, seed=True, evaluator=None, feedback=None,
                seconds=10., mixed=False):
        clock = Clock()
        budget = MethodBudget(seconds, clock=clock)
        model, native = ToyModel(budget, mixed=mixed), FakeNative(scripts, clock)
        decoded, evaluated = [], []

        def decode_stub(model, vector):
            self.assertEqual(len(vector), 5, 'augmented coordinates reached decoder')
            diagnostics = milp.logical_candidate_diagnostics(model, vector)
            if not diagnostics['accepted']:
                raise ValueError(diagnostics['reason'])
            decoded.append(list(vector))
            return {'scenes': {'AB': [{'shared': float(vector[0]), 'score': float(vector[2])}],
                               'AC': [{'shared': float(vector[0]), 'score': float(vector[4])}]},
                    'prefix': list(map(float, vector))}

        def evaluate_stub(model, candidate, accuracy, owning_budget):
            self.assertEqual(set(candidate['scenes']), {'AB', 'AC'})
            self.assertIs(owning_budget, budget)
            evaluated.append(deepcopy(candidate))
            if evaluator is not None:
                return evaluator(model, candidate, accuracy, budget)
            energy = 1 + (candidate['prefix'][2] + candidate['prefix'][4]) / 2
            return {'state': 'SAFE', 'rankable_energy': True,
                    'safe_upper_bound_J': str(energy),
                    'weighted_energy_J': [str(energy), str(energy)],
                    'completed_at_elapsed_s': budget.elapsed,
                    'fixture_only_not_a_physical_safety_receipt': True}

        context = whole_augmented.WholeAugmentedContext(
            session_factory=native.factory,
            recorder_kwargs={'decoder': decode_stub, 'evaluator': evaluate_stub})
        session = context.session_factory(self.path / 'matlab', total_budget_s=seconds, budget=budget)
        used = initial_point._InitialSession(session, GOOD[:5]) if seed else session
        with patch.object(formal_milp, '_checked_thermal_witnesses', lambda *args: [True]), \
             patch.object(formal_milp, 'add_thermal_feedback',
                          feedback or (lambda *args: {'rows_added': 0})):
            result = context.solve_formal_diagnostic(model, used, {}, budget, max_rounds=2)
        fixture = {'test': self._testMethodName, 'state': result.get('state'),
                   'reason': result.get('reason'), 'fake_native_requests': len(native.calls),
                   'stub_evaluator_calls': len(evaluated),
                   'latched_unresolved': context.summary().get('latched_unresolved'),
                   'no_research_safe_U_claim': True}
        FIXTURE_RECORDS.append(fixture)
        write(self.path / 'fixture_result.json', result)
        return type('Harness', (), dict(result=result, model=model, native=native,
                    context=context, session=session, budget=budget, clock=clock,
                    decoded=decoded, evaluated=evaluated))()

    def test_callback_final_project_prefix_and_duplicate_cache(self):
        h = self.harness([{'callbacks': [GOOD, GOOD]}])
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertEqual(len(h.evaluated), 1)
        self.assertGreaterEqual(h.result['diagnostic']['duplicate_receipts'], 2)
        self.assertTrue(all(len(x) == 5 for x in h.decoded))
        self.assertFalse(h.result['independently_proven_optimal'])
        self.assertIsNone(h.session.event_consumer)

    def test_original_x0_wrapper_appends_only_once(self):
        h = self.harness([{}])
        self.assertEqual(list(h.native.calls[0]['x0']), GOOD)
        self.assertEqual(list(h.native.calls[0]['x0'][:5]), GOOD[:5])
        self.assertEqual(h.native.calls[0]['budget_id'], id(h.budget))

    def test_no_x0_preserves_domain(self):
        h = self.harness([{}], seed=False)
        self.assertIsNone(h.native.calls[0]['x0'])
        self.assertEqual(h.native.calls[0]['payload']['A'].shape, (4, 7))

    def test_whole_evaluator_sees_both_scenes_shared_choice(self):
        h = self.harness([{}])
        candidate = h.evaluated[0]
        self.assertEqual(candidate['scenes']['AB'][0]['shared'],
                         candidate['scenes']['AC'][0]['shared'])
        self.assertEqual(set(candidate['scenes']), {'AB', 'AC'})

    def test_mixed_exact_and_retained_rows(self):
        h = self.harness([{}], mixed=True)
        requests = h.context.summary()['requests']
        mapping = json.loads(Path(requests[0]['mapping_path']).read_text(encoding='utf8'))
        retained = mapping['exact_row_selection']['retained_nonrepresentable_physical_rows']
        self.assertEqual([row['row'] for row in retained], [4])
        row = h.native.calls[0]['payload']['A'].getrow(4).toarray().reshape(-1)
        self.assertEqual(row[1], 2. ** -54)
        self.assertEqual(row[2], 1.)
        self.assertEqual(h.native.calls[0]['payload']['b'][4], 1.)

    def test_continuous_projection_preserves_rows_and_integer_prefix(self):
        model = ToyModel(MethodBudget(10, clock=Clock()), mixed=True)
        original = model.as_solver_dict()
        augmented, meta = augmented_method.build_live_augmented_payload(original,
            {'names': model.names, 'row_tags': [row['tag'] for row in model.rows]})
        for gate in (.0, .25, .5, 1.):
            prefix = np.array([1., gate, 0., gate, 0.])
            vector = np.r_[prefix, 1-gate, 1-gate]
            projected, report = validate_projected_vector(vector, original, augmented, meta)
            self.assertTrue(report['accepted'], report)
            self.assertTrue(np.array_equal(projected, prefix))
            self.assertTrue(np.array_equal(augmented['intcon'], original['intcon']))
            self.assertEqual(float(augmented['c'] @ vector), float(original['c'] @ prefix))

    def test_original_row_catches_link_tolerance_amplification(self):
        bad = [1., 1., 4e-7, 1., 0., 5e-10, 0.]
        h = self.harness([{'callbacks': [bad], 'final': GOOD}])
        self.assertFalse(h.evaluated)
        self.assertTrue(h.context.summary()['latched_unresolved'])
        self.assertNotEqual(h.result['state'], 'SAFE')

    def test_bad_dimension_latches_before_decoder(self):
        h = self.harness([{'callbacks': [GOOD[:5]], 'final': GOOD}])
        self.assertFalse(h.decoded)
        self.assertTrue(h.context.summary()['latched_unresolved'])

    def test_near_integer_is_not_repaired(self):
        point = [1 - 5e-7, 0., 0., 0., 0., 1., 1.]
        h = self.harness([{'callbacks': [point], 'final': point}])
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertEqual(h.decoded[0][0], point[0])

    def test_outside_integer_tolerance_rejected(self):
        point = [1 - 2e-6, 0., 0., 0., 0., 1., 1.]
        h = self.harness([{'callbacks': [point], 'final': GOOD}])
        self.assertFalse(h.evaluated)
        self.assertTrue(h.context.summary()['latched_unresolved'])

    def test_fractional_implied_binary_is_not_safe(self):
        point = [1., .5, 0., .5, 0., .5, .5]
        h = self.harness([{'callbacks': [point], 'final': point}])
        self.assertFalse(h.evaluated)
        self.assertNotEqual(h.result['state'], 'SAFE')

    def test_final_objective_mismatch_preserves_old_safe(self):
        h = self.harness([{'callbacks': [GOOD], 'final_fval': 9.}])
        self.assertEqual(len(h.evaluated), 1)
        self.assertEqual(h.result['state'], 'SAFE')
        self.assertTrue(h.context.summary()['latched_unresolved'])

    def test_invalid_after_safe_does_not_erase_safe(self):
        h = self.harness([{'callbacks': [GOOD, GOOD[:5]], 'final': GOOD}])
        self.assertEqual(h.result['state'], 'SAFE')
        self.assertEqual(len(h.evaluated), 1)
        self.assertTrue(h.context.summary()['latched_unresolved'])

    def test_native_conflict_is_not_infeasibility_proof(self):
        h = self.harness([{'callbacks': [GOOD], 'native_conflict': True, 'exitflag': -2}])
        self.assertEqual(h.result['state'], 'SAFE')
        self.assertTrue(h.context.summary()['latched_unresolved'])
        self.assertFalse(h.result['independently_proven_infeasible'])

    def test_no_candidate_no_safe_output(self):
        h = self.harness([{'callbacks': [], 'final': [], 'exitflag': 0}], seed=False)
        self.assertEqual(h.result['state'], 'UNRESOLVED')
        self.assertIsNone(h.result['safe_upper_bound_J'])
        self.assertFalse(h.result['independently_proven_infeasible'])

    def test_missing_callback_file_cannot_claim_complete(self):
        h = self.harness([{'omit_publication': True}])
        self.assertTrue(h.context.summary()['latched_unresolved'])
        self.assertFalse(h.evaluated)

    def test_budget_after_safe_keeps_safe_without_new_evaluation(self):
        h = self.harness([{'callbacks': [GOOD], 'advance_after_callback': 10.}], seconds=10.)
        self.assertEqual(h.result['state'], 'SAFE')
        self.assertEqual(len(h.evaluated), 1)
        self.assertLessEqual(len(h.native.calls), 1)
        self.assertFalse(h.result['independently_proven_optimal'])
        self.assertEqual(h.context.summary()['failure_categories'], ['budget'])

    def test_late_first_candidate_never_reaches_evaluator(self):
        h = self.harness([{'callbacks': [GOOD], 'advance_before_callback': 10.}], seconds=10.)
        self.assertFalse(h.evaluated)
        self.assertNotEqual(h.result['state'], 'SAFE')
        self.assertEqual(h.context.summary()['failure_categories'], ['budget'])

    def test_existing_budget_cancel_is_never_overwritten(self):
        h = self.harness([{'callbacks': [GOOD[:5]], 'final': GOOD,
                          'preexisting_budget_cancel': True}])
        path = Path(h.native.calls[0]['prefix']).with_suffix('.cancel')
        self.assertEqual(path.read_text(encoding='ascii'), 'budget\n')
        self.assertTrue(h.context.summary()['requests'][0]['existing_cancel_preserved'])

    def test_technical_exception_keeps_previous_safe_and_stops(self):
        h = self.harness([{'callbacks': [GOOD], 'raise_after_callback': True}])
        self.assertEqual(h.result['state'], 'SAFE')
        self.assertEqual(len(h.evaluated), 1)
        self.assertTrue(h.context.summary()['latched_unresolved'])
        self.assertNotEqual(h.result['reason'], 'SOLVER_RETURN_AFTER_BUDGET')

    def test_native_failure_with_remaining_budget_is_technical(self):
        h = self.harness([{'callbacks': [], 'final': [], 'status': 'WORKER_EXITED',
                          'budget_valid': False}], seed=False)
        self.assertGreater(h.budget.remaining, 0)
        self.assertTrue(set(h.context.summary()['failure_categories']) & {'technical', 'interface'})
        self.assertNotIn('budget', h.context.summary()['failure_categories'])
        self.assertFalse(h.evaluated)
        self.assertEqual(h.result['state'], 'UNRESOLVED')
        self.assertNotEqual(h.result['reason'], 'SOLVER_RETURN_AFTER_BUDGET')

    def test_native_request_number_mismatch_blocks_final_and_offline_audit(self):
        h = self.harness([{'callbacks': [], 'final': GOOD, 'request_number': 2}], seed=False)
        self.assertFalse(h.evaluated)
        self.assertTrue(h.context.summary()['latched_unresolved'])
        audit = whole_augmented.audit_whole_augmented_evidence(h.result)
        self.assertFalse(audit['passed'], audit)

    def test_feedback_rebinds_current_arrays_and_x0_not_reused(self):
        def evaluator(model, candidate, accuracy, budget):
            if candidate['prefix'][1] == 1.:
                return {'state': 'THERMAL_VIOLATION', 'rankable_energy': False,
                        'violations': [{'fixture_only': True}],
                        'completed_at_elapsed_s': budget.elapsed}
            return {'state': 'SAFE', 'rankable_energy': True, 'safe_upper_bound_J': '1.25',
                    'completed_at_elapsed_s': budget.elapsed}

        def feedback(model, candidate, evaluation):
            model.rows.append({'coef': {2: 1.}, 'rhs': .5,
                               'tag': 'continuous_thermal_feedback/fixture'})
            return {'rows_added': 1}

        second = [1., 0., .25, 0., .25, 1., 1.]
        h = self.harness([{}, {'callbacks': [second], 'final': second}],
                         evaluator=evaluator, feedback=feedback)
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertEqual(len(h.native.calls), 2)
        self.assertIsNone(h.native.calls[1]['x0'])
        self.assertEqual([call['payload']['A'].shape[0] for call in h.native.calls], [4, 5])
        requests = h.context.summary()['requests']
        identities = [json.loads(Path(r['matrix_identities_path']).read_text(encoding='utf8'))
                      for r in requests]
        self.assertNotEqual(identities[0]['original']['A'], identities[1]['original']['A'])

    def test_native_round_stays_exact_and_derived_tamper_is_detected(self):
        h = self.harness([{}])
        self.assertEqual(len(h.result['native_rounds']), 1)
        raw_path = Path(h.native.calls[0]['prefix']).with_suffix('.python.json')
        raw = json.loads(raw_path.read_text(encoding='utf8'))
        self.assertEqual(h.result['native_rounds'][0], raw)
        checked = whole_augmented.audit_whole_augmented_evidence(h.result)
        self.assertTrue(checked['passed'], checked)
        tampered = deepcopy(h.result)
        tampered['rounds'][0]['fval'] = 9.
        self.assertFalse(whole_augmented.audit_whole_augmented_evidence(tampered)['passed'])

    def test_native_round_tamper_is_detected(self):
        h = self.harness([{}])
        tampered = deepcopy(h.result)
        tampered['native_rounds'][0]['fval'] = 9.
        self.assertFalse(whole_augmented.audit_whole_augmented_evidence(tampered)['passed'])

    def test_formal_entry_default_and_explicit_solver_hooks(self):
        observed = []

        def fake_warm(loader, out, **kwargs):
            observed.append(kwargs['solver'].keywords['diagnostic_solver'])
            return {'state': 'UNRESOLVED', 'fixture_only': True}

        def supplied(*args, **kwargs):
            raise AssertionError('The wrapper inspection must not execute a solve')

        with patch.object(formal_milp, 'execute_warm', fake_warm):
            formal_milp.execute_formal_milp(lambda: None, self.path, seconds=10)
            formal_milp.execute_formal_milp(lambda: None, self.path, seconds=10,
                                          diagnostic_solver=supplied)
        self.assertIs(observed[0].func, formal_milp.solve_formal_diagnostic)
        self.assertIs(observed[1].func, supplied)


def run(out):
    global OUT
    OUT = Path(out).resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), HERE / 'whole_augmented.py', HERE / 'formal_milp.py',
                    HERE / 'augmented_payload.py', HERE / 'augmented_method.py',
                    HERE / 'diagnostic_search.py', HERE / 'initial_point.py',
                    HERE / 'matlab_bridge.py', HERE / 'milp.py', HERE / 'thermal.py']
    before = {str(p): sha(p) for p in source_paths}
    forbidden = {}

    def register(obj, name):
        code = getattr(obj, '__code__', None)
        if code is not None:
            forbidden[code] = name

    originals = [
        (milp, 'build_model'), (milp, 'evaluate_model_candidate'),
        (thermal, 'evaluate_piecewise'), (thermal, 'evaluate_candidate'),
        (scene_adapter, 'evaluate_scene'), (scene_adapter, 'evaluate_partial_scene'),
        (initial_point, '_propose_vector'), (initial_point, 'prepare_initial_witness'),
        (initial_point, 'complete_initial_point'),
        (initial_schedule, 'iter_initial_candidates'),
        (scipy.optimize, 'milp'), (scipy.optimize, 'linprog'),
        (scipy.linalg, 'expm')]
    for module, name in originals:
        if hasattr(module, name):
            register(getattr(module, name), module.__name__ + '.' + name)
    for cls, name in [(matlab_bridge.MatlabSession, '__init__'),
                      (matlab_bridge.MatlabSession, 'solve'), (milp.Model, '__init__'),
                      (milp_coefficients.Coefficients, '__init__'),
                      (subprocess.Popen, '__init__')]:
        register(getattr(cls, name), cls.__name__ + '.' + name)
    counters = {name: 0 for name in forbidden.values()}

    def block(name):
        def denied(*args, **kwargs):
            counters[name] = counters.get(name, 0) + 1
            raise ScientificGuardViolation('SCIENTIFIC_ENTRY_FORBIDDEN: ' + name)
        return denied

    def profile(frame, event, arg):
        if event == 'call' and frame.f_code in forbidden:
            name = forbidden[frame.f_code]
            counters[name] += 1
            raise ScientificGuardViolation('CAPTURED_SCIENTIFIC_DEFAULT_FORBIDDEN: ' + name)

    log = io.StringIO()
    previous_profile = sys.getprofile()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(subprocess, 'Popen', block('subprocess.Popen')))
            for module, name in originals:
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name,
                                                    block(module.__name__ + '.' + name)))
            # Patch aliases too; code-object profiling remains the final guard
            # against defaults captured before these attributes were replaced.
            stack.enter_context(patch.object(formal_milp, 'build_model', block('formal_milp.build_model')))
            stack.enter_context(patch.object(diagnostic_search, 'evaluate_model_candidate',
                                             block('diagnostic_search.evaluate_model_candidate')))
            sys.setprofile(profile)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(WholeAugmentedTests)
            try:
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            except ScientificGuardViolation as error:
                # CPython disables a profile hook if it raises. Abort rather
                # than continuing later tests with only attribute patches.
                result = unittest.TestResult()
                result.errors.append(('scientific_guard', str(error)))
                log.write('\nABORTED_BY_SCIENTIFIC_GUARD: ' + str(error) + '\n')
    finally:
        sys.setprofile(previous_profile)
    after = {str(p): sha(p) for p in source_paths}
    report = {'protocol': 'K167-handwritten-whole-augmented-fixtures-v1',
              'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'test_successful': result.wasSuccessful(),
              'source_sha256_before': before, 'source_sha256_after': after,
              'source_unchanged': before == after,
              'guard': {'strategy': 'Explicit fake dependencies plus real-function code-object profile guard and attribute patches; captured defaults are blocked',
                        'blocked_entry_attempts': counters,
                        'all_scientific_attempts_zero': all(value == 0 for value in counters.values()),
                        'guarded_code_objects': sorted(set(forbidden.values())),
                        'real_solver_calls': 0, 'real_model_builds': 0, 'real_thermal_evaluations': 0,
                        'research_calls': 0},
              'fixture_records': FIXTURE_RECORDS,
              'scope': 'Handwritten small arrays, explicit fake native and stub SAFE for lifecycle only; no research safety, repair, performance or solver compatibility claim'}
    report['passed'] = (report['test_successful'] and report['source_unchanged']
                        and report['guard']['all_scientific_attempts_zero'])
    (OUT / 'unittest.txt').write_text(log.getvalue(), encoding='utf8')
    write(OUT / 'checks.json', report)
    print(json.dumps({'passed': report['passed'], 'tests_run': result.testsRun,
                      'failures': len(result.failures), 'errors': len(result.errors),
                      'guard_zero': report['guard']['all_scientific_attempts_zero'],
                      'checks': str(OUT / 'checks.json')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().out))
