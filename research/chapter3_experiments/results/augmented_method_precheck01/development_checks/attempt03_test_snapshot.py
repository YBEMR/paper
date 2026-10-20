"""K134 augmented payload integration checks, with no native optimizer.

Real small-domain physics is used in one complete two-scene lifecycle. Other
fixtures isolate numerical admission, event completeness, feedback identity and
absolute-deadline failures. They are control-flow fixtures, not research cases.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
from scipy.io import loadmat

import augmented_method
from augmented_payload import build_augmented_payload
import fixed_unit_method
import matlab_bridge
import milp
import partial_method
import scene_adapter
from control_policy import with_auto_low_idle
from initial_point import _InitialSession
from inputs import load_config
from test_neighborhood_method import Clock, Harness
from test_partial_deployment import small_case
from thermal import Exhausted
from timing import MethodBudget

REPO = Path(__file__).resolve().parents[2]
RECORDS = {'scope': 'K134 fake native integration only; no research/native calls',
           'native_calls': 0, 'research_calls': 0}


def _write(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=True), encoding='utf-8')


class ToyModel:
    def __init__(self, budget, *, coefficient=1000.0):
        self.budget = budget
        self.names = ['z:choice', 'w:gate']
        self.rows = [{'coef': {0: 1., 1: coefficient}, 'rhs': coefficient,
                      'tag': 'thermal_propagation/toy'}]
        self.c = [1., 0.]

    def as_solver_dict(self):
        self.budget.check()
        return {'c': np.array(self.c),
            'A': sparse.csr_matrix([[r['coef'].get(j, 0.) for j in range(2)] for r in self.rows]),
            'b': np.array([r['rhs'] for r in self.rows]),
            'Aeq': sparse.csr_matrix((0, 2)), 'beq': np.empty(0),
            'lb': np.zeros(2), 'ub': np.ones(2), 'intcon': np.array([0])}


class NativeScript:
    """Immutable native publications; all candidate content is explicit input."""
    def __init__(self, scripts, clock=None):
        self.scripts = list(scripts)
        self.clock = clock
        self.calls, self.sessions = [], []

    def factory(self, workdir, *, total_budget_s, budget):
        owner = self
        class Session:
            def __init__(self):
                self.workdir = Path(workdir); self.workdir.mkdir(parents=True)
                self.budget = budget; self.event_consumer = None; self.counter = 0
                self.closed = self.request_blocked = False
                owner.sessions.append(self)

            def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
                assert budget is self.budget
                item = owner.scripts.pop(0)
                self.counter += 1
                prefix = self.workdir/('request_%03d' % self.counter)
                values = item.get('callbacks', [np.asarray(x0).tolist() if x0 is not None
                                              else [0., 1., 0.]])
                owner.calls.append({'payload': payload, 'x0': deepcopy(x0),
                    'prefix': prefix, 'remaining_s': remaining_s, 'budget': budget})
                if item.get('advance_before_callback'):
                    owner.clock.tick(item['advance_before_callback'])
                events = [{'kind': 'solver_entered', 'event_number': 1}]
                for number, vector in enumerate(values, 2):
                    fval = item.get('callback_fval', float(payload['c'] @ np.asarray(vector))
                                    if np.asarray(vector).size == len(payload['c']) else 0.)
                    events.append({'kind': 'callback', 'event_number': number,
                                   'x': vector, 'values': {'fval': fval}})
                for event in events:
                    if not (item.get('omit_publication') and event['kind'] == 'callback'):
                        _write(Path(str(prefix)+'.event_%06d.json' % event['event_number']), event)
                    if self.event_consumer:
                        self.event_consumer(prefix)
                if item.get('raise_after_callback'):
                    raise RuntimeError('FAKE_NATIVE_FAILURE_AFTER_CALLBACK')
                if item.get('advance_after_callback'):
                    owner.clock.tick(item['advance_after_callback'])
                final = item.get('final', values[-1] if values else [])
                result = {'status': 'SOLVED', 'x': final, 'exitflag': item.get('exitflag', 1),
                    'budget_valid': budget.remaining > 0,
                    'accepted_for_evaluation': budget.remaining > 0,
                    'intlinprog_entered': True, 'output': {},
                    'callbacks': [e for e in events if e['kind'] == 'callback']}
                if not item.get('omit_fval'):
                    result['fval'] = item.get('final_fval', float(payload['c'] @ np.asarray(final))
                        if np.asarray(final).size == len(payload['c']) else 0.)
                return result

            def close(self):
                self.event_consumer = None; self.closed = True
        return Session()


class AugmentedMethodTests(unittest.TestCase):
    def setUp(self):
        home = REPO/'.runtime/augmented_method_correctness'
        home.mkdir(parents=True, exist_ok=True)
        self.path = home/('case_'+uuid4().hex); self.path.mkdir()

    def toy(self, scripts, *, seed=True, evaluate=None, feedback=None,
            clock=None, seconds=60, before_solve=None):
        clock = clock or Clock(); budget = MethodBudget(seconds, clock=clock)
        model = ToyModel(budget)
        native = NativeScript(scripts, clock)
        context = augmented_method.AugmentedMethodContext(session_factory=native.factory)
        session = context.session_factory(self.path/'native', total_budget_s=seconds, budget=budget)
        checked, published = [], []
        def evaluator(_model, candidate, accuracy, owning_budget):
            checked.append(deepcopy(candidate))
            if evaluate is not None:
                return evaluate(_model, candidate, accuracy, owning_budget)
            return {'state': 'SAFE', 'rankable_energy': True,
                    'safe_upper_bound_J': '1', 'weighted_energy_J': ['1','1'],
                    'completed_at_elapsed_s': owning_budget.elapsed}
        recorder = context.recorder_factory(model, {}, budget, self.path,
            decoder=lambda model, vector: {'original_prefix': list(vector)},
            model_evaluator=evaluator, on_evaluation=lambda *args: None,
            on_safe=lambda *args: published.append(args),
            witness_validator=lambda *args: [True])
        if before_solve is not None:
            before_solve(context, recorder, model, budget)
        used = _InitialSession(session, [0., 1.]) if seed else session
        result = partial_method._solve_scene(model, used, {}, budget, recorder,
            feedback_adder=feedback or (lambda *args: {'rows_added': 0}),
            witness_validator=lambda *args: [True], max_rounds=4)
        return SimpleNamespace(result=result, native=native, context=context, session=session,
            recorder=recorder, checked=checked, published=published, model=model, budget=budget)

    def test_augmented_callback_and_final_project_before_decode_and_reuse(self):
        h = self.toy([{'callbacks': [[0.,1.,0.], [0.,1.,0.]]}])
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertEqual(h.checked, [{'original_prefix': [0., 1.]}])
        self.assertEqual(h.result['diagnostic']['duplicate_receipts'], 2)
        self.assertEqual(len(h.native.calls[0]['x0']), 3)
        self.assertTrue(np.array_equal(h.native.calls[0]['x0'][:2], [0., 1.]))
        self.assertFalse(h.result['independently_proven_optimal'])
        self.assertIsNone(h.native.sessions[0].event_consumer)

    def test_no_x0_preserves_same_augmented_search_domain(self):
        h = self.toy([{}], seed=False)
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertIsNone(h.native.calls[0]['x0'])
        self.assertEqual(h.native.calls[0]['payload']['A'].shape, (1, 3))

    def test_invalid_callback_latches_despite_good_final_and_keeps_prior_safe(self):
        for bad in ([0., 1.], 0, [0.,1.,1.], [float('nan'),1.,0.]):
            with self.subTest(bad=bad):
                sub = self.path/uuid4().hex; sub.mkdir()
                original = self.path; self.path = sub
                try:
                    h = self.toy([{'callbacks': [[0.,1.,0.], bad], 'final': [0.,1.,0.]}])
                finally:
                    self.path = original
                self.assertEqual(h.result['state'], 'SAFE', h.result)
                self.assertEqual(len(h.checked), 1)
                self.assertFalse(h.result['worker_reusable'])
                self.assertTrue(Path(str(h.native.calls[0]['prefix'])+'.cancel').exists())
                self.assertNotIn(h.result['reason'], ('SAFE_ENGINEERING_CONVERGENCE', 'SAFE_RETURNED_INCUMBENT'))

    def test_final_objective_or_vector_failure_keeps_callback_safe_but_blocks_reuse(self):
        failures = ({'final': [0.,1.]}, {'final_fval': 3.}, {'omit_fval': True},
                    {'callback_fval': 3.})
        for item in failures:
            with self.subTest(item=item):
                sub = self.path/uuid4().hex; sub.mkdir(); original = self.path; self.path = sub
                try: h = self.toy([dict({'callbacks': [[0.,1.,0.]]}, **item)])
                finally: self.path = original
                self.assertFalse(h.result['worker_reusable'])
                self.assertFalse(h.result['independently_proven_infeasible'])
                if 'callback_fval' not in item:
                    self.assertEqual(h.result['state'], 'SAFE')
                else:
                    self.assertFalse(h.checked)
                self.assertTrue(Path(str(h.native.calls[0]['prefix'])+'.cancel').exists())

    def test_link_tolerance_cannot_bypass_violated_original_physical_row(self):
        bad = [4e-7, 1., 5e-10]
        h = self.toy([{'callbacks': [bad], 'final': [0.,1.,0.]}])
        self.assertFalse(h.checked)
        self.assertFalse(h.result['worker_reusable'])
        self.assertEqual(h.result['state'], 'UNRESOLVED')

    def test_missing_callback_publication_cannot_be_reported_as_checked(self):
        h = self.toy([{'omit_publication': True}])
        self.assertFalse(h.result['worker_reusable'])
        self.assertFalse(h.checked)
        self.assertNotEqual(h.result['state'], 'SAFE')

    def test_feedback_rebuilds_mapping_and_new_original_row_rejects_old_point(self):
        def violated(model, candidate, accuracy, budget):
            return {'state': 'THERMAL_VIOLATION', 'rankable_energy': False,
                    'safe_upper_bound_J': None, 'completed_at_elapsed_s': budget.elapsed}
        def add(model, candidate, evaluation):
            model.rows.append({'coef': {0:-1.}, 'rhs': -1., 'tag':'thermal_feedback/toy'})
            return {'state': 'ROWS_ADDED', 'rows_added': 1}
        h = self.toy([{}, {}], evaluate=violated, feedback=add)
        self.assertEqual(len(h.native.calls), 2, h.result)
        self.assertEqual(len(h.result['feedback']), 1)
        self.assertEqual(len(h.checked), 1, 'second original-row violation must not reach heat cache')
        self.assertEqual(h.native.calls[0]['payload']['A'].shape, (1,3))
        self.assertEqual(h.native.calls[1]['payload']['A'].shape, (2,3))
        self.assertIsNotNone(h.native.calls[0]['x0'])
        self.assertIsNone(h.native.calls[1]['x0'])
        self.assertFalse(h.result['worker_reusable'])
        self.assertFalse(h.result['independently_proven_infeasible'])
        receipts = h.result['diagnostic']['augmented_transport']['requests']
        left, right = [json.loads(Path(r['identities_path']).read_text(encoding='utf-8')) for r in receipts]
        self.assertNotEqual(left['original']['A'], right['original']['A'])
        mappings = [json.loads(Path(r['mapping_path']).read_text(encoding='utf-8')) for r in receipts]
        self.assertEqual([m['original_inequality_rows'] for m in mappings], [1,2])
        self.assertNotEqual(mappings[0], mappings[1])

    def test_late_callback_and_final_do_not_create_safe_receipt(self):
        h = self.toy([{'advance_before_callback': 61.}], seconds=60)
        self.assertFalse(h.checked)
        self.assertFalse(h.published)
        self.assertNotEqual(h.result['state'], 'SAFE')
        self.assertFalse(h.result['independently_proven_optimal'])

    def test_safe_callback_receipt_survives_late_final_without_new_evaluation(self):
        h = self.toy([{'advance_after_callback': 61.}], seconds=60)
        self.assertEqual(h.result['state'], 'SAFE', h.result)
        self.assertEqual(len(h.checked), 1)
        self.assertFalse(h.result['worker_reusable'])
        self.assertTrue(h.budget.remaining == 0)

    def test_same_sized_methods_have_independent_context_cache_and_close(self):
        first = self.toy([{}])
        folder = self.path/'second'; folder.mkdir(); self.path = folder
        second = self.toy([{}])
        self.assertIsNot(first.context, second.context)
        self.assertIsNot(first.session, second.session)
        self.assertIsNot(first.budget, second.budget)
        self.assertEqual(len(first.checked), 1); self.assertEqual(len(second.checked), 1)
        first.session.close(); second.session.close()
        self.assertTrue(first.native.sessions[0].closed)
        self.assertTrue(second.native.sessions[0].closed)

    def test_validation_crossing_deadline_does_not_reach_decode_or_heat(self):
        clock = Clock()
        original = augmented_method.validate_projected_vector
        def crosses(*args, **kwargs):
            answer = original(*args, **kwargs)
            clock.tick(61.)
            return answer
        with patch.object(augmented_method, 'validate_projected_vector', side_effect=crosses):
            h = self.toy([{}], seed=False, clock=clock)
        self.assertFalse(h.checked)
        self.assertFalse(h.published)
        self.assertNotEqual(h.result['state'], 'SAFE')
        self.assertFalse(h.result['worker_reusable'])

    def test_same_context_same_dimension_new_scene_uses_new_original_rows(self):
        clock = Clock(); budget = MethodBudget(60, clock=clock)
        native = NativeScript([{}, {}], clock)
        context = augmented_method.AugmentedMethodContext(session_factory=native.factory)
        session = context.session_factory(self.path/'shared_worker', total_budget_s=60, budget=budget)
        evaluated, results = [], []
        for index in range(2):
            model = ToyModel(budget, coefficient=1000. if index == 0 else 500.)
            if index:
                model.rows.append({'coef': {0:-1.}, 'rhs':-1., 'tag':'scene_specific/exclusion'})
            folder = self.path/('scene_'+str(index)); folder.mkdir()
            def evaluator(model, candidate, accuracy, owning_budget):
                evaluated.append(index)
                return {'state':'SAFE', 'rankable_energy':True,
                        'safe_upper_bound_J':'1', 'weighted_energy_J':['1','1'],
                        'completed_at_elapsed_s':owning_budget.elapsed}
            recorder = context.recorder_factory(model, {}, budget, folder,
                decoder=lambda model, vector: {'same_candidate':list(vector)},
                model_evaluator=evaluator, on_evaluation=lambda *a:None,
                on_safe=lambda *a:None, witness_validator=lambda *a:[])
            results.append(partial_method._solve_scene(model, session, {}, budget, recorder,
                feedback_adder=lambda *a:{'rows_added':0}, witness_validator=lambda *a:[], max_rounds=1))
        self.assertEqual(evaluated, [0])
        self.assertEqual(results[0]['state'], 'SAFE')
        self.assertNotEqual(results[1]['state'], 'SAFE')
        self.assertFalse(results[1]['worker_reusable'])
        self.assertEqual(native.calls[0]['payload']['A'].shape, (1,3))
        self.assertEqual(native.calls[1]['payload']['A'].shape, (2,3))

    def test_poll_exception_blocks_worker_and_requests_cancel(self):
        def prepare(context, recorder, model, budget):
            def broken_log(row):
                raise OSError('FAKE_PUBLICATION_FAILURE')
            recorder.log = broken_log
        h = self.toy([{}], before_solve=prepare)
        self.assertFalse(h.result['worker_reusable'])
        self.assertFalse(h.checked)
        self.assertTrue(Path(str(h.native.calls[0]['prefix'])+'.cancel').exists())
        self.assertTrue(h.session.request_blocked)

    def test_release_detaches_large_live_objects_but_archived_receipts_remain(self):
        h = self.toy([{}])
        self.assertIsNone(h.recorder.model)
        self.assertIsNone(h.recorder.request)
        self.assertIsNone(h.context.recorder)
        self.assertIsNone(h.context.current)
        requests = h.result['diagnostic']['augmented_transport']['requests']
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0]['numerical_checks'])
        self.assertTrue(requests[0]['callback_publications_complete'])

    def test_admission_archive_crossing_deadline_blocks_final_thermal(self):
        clock = Clock(); original = augmented_method._save
        def crosses(path, value):
            original(path, value)
            if Path(path).name == 'admission.json':
                clock.tick(61.)
        with patch.object(augmented_method, '_save', side_effect=crosses):
            h = self.toy([{'callbacks':[], 'final':[0.,1.,0.]}], clock=clock)
        self.assertFalse(h.checked)
        self.assertFalse(h.published)
        self.assertNotEqual(h.result['state'], 'SAFE')
        self.assertFalse(h.result['worker_reusable'])
        request = h.context.summary()['requests'][0]
        self.assertFalse(request['within_budget'])
        self.assertTrue(request['latched_unresolved'])

    def test_selected_exact_rows_restore_original_and_other_rows_keep_original_bits(self):
        model = ToyModel(MethodBudget(60, clock=Clock()))
        model.rows.append({'coef':{0:1.,1:1000.}, 'rhs':.1,
                           'tag':'complete_energy/nonrepresentable'})
        original = model.as_solver_dict()
        labels = {'names':model.names, 'row_tags':[row['tag'] for row in model.rows]}
        with self.assertRaises(ValueError):
            build_augmented_payload(original, labels)
        changed, mapping = augmented_method.build_live_augmented_payload(original, labels)
        selection = mapping['exact_row_selection']
        self.assertEqual(selection['selected_original_physical_rows'], [0])
        self.assertEqual([row['row'] for row in selection['retained_nonrepresentable_physical_rows']], [1])
        self.assertEqual(original['A'].getrow(1).toarray().tobytes(),
                         changed['A'].getrow(1).toarray()[:,:2].tobytes())
        self.assertEqual(np.float64(original['b'][1]).tobytes(),
                         np.float64(changed['b'][1]).tobytes())
        self.assertEqual(float(changed['A'][1,2]), 0.)
        # Substitute v=1-w in exact rational arithmetic, independently of the
        # transformation's gate replacement and RHS implementation.
        row = changed['A'].getrow(0).toarray().reshape(-1)
        restored = [Fraction.from_float(float(value)) for value in row[:2]]
        restored[1] -= Fraction.from_float(float(row[2]))
        restored_rhs = Fraction.from_float(float(changed['b'][0]))-Fraction.from_float(float(row[2]))
        self.assertEqual(restored, [Fraction.from_float(float(v)) for v in original['A'].toarray()[0]])
        self.assertEqual(restored_rhs, Fraction.from_float(float(original['b'][0])))
        for key in ('c','lb','ub'):
            self.assertEqual(changed[key][:2].tobytes(), original[key].tobytes())
        self.assertEqual(changed['intcon'].tobytes(), original['intcon'].tobytes())
        unsupported = deepcopy(original); unsupported['b'][0] = .1
        with self.assertRaisesRegex(ValueError, 'no exact physical rows'):
            augmented_method.build_live_augmented_payload(unsupported, labels)
        bad_labels = deepcopy(labels); bad_labels['names'][0] = 'w:other'
        with self.assertRaisesRegex(ValueError, 'exactly one joint gate'):
            augmented_method.build_live_augmented_payload(original, bad_labels)
        RECORDS['selected_exact_row_equivalence'] = {'selected_rows':[0], 'retained_rows':[1],
            'original_rhs_bits_unchanged':True, 'selected_row_Fraction_elimination_equal':True,
            'unsupported_all_rows_rejected':True, 'no_physical_parameter_change':True}

    def test_saved_K133_AB_live_arrays_equal_original_strict_arrays(self):
        here = Path(__file__).resolve().parent
        payload_path = here/'results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat'
        labels_path = here/'results/numerical_conflict_audit01/row_trace/labels.json'
        raw = loadmat(payload_path)
        original = {key:raw[key] for key in ('c','A','b','Aeq','beq','lb','ub')}
        original['intcon'] = raw['intcon'].reshape(-1).astype(np.int64)-1
        labels = json.loads(labels_path.read_text(encoding='utf-8-sig'))
        strict, strict_mapping = build_augmented_payload(original, labels)
        live, live_mapping = augmented_method.build_live_augmented_payload(original, labels)
        strict_identity, live_identity = (augmented_method.matrix_identity(value) for value in (strict,live))
        self.assertEqual(strict_identity, live_identity)
        self.assertEqual(live_mapping['exact_row_selection']['retained_nonrepresentable_physical_rows'], [])
        self.assertEqual(live_mapping['physical_rows'], strict_mapping['physical_rows'])
        RECORDS['K133_saved_AB_compatibility'] = {'eight_arrays_equal':True,
            'source_mat_sha256':hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            'labels_sha256':hashlib.sha256(labels_path.read_bytes()).hexdigest(),
            'array_identities':live_identity,
            'strict_physical_rows_rewritten':strict_mapping['physical_rows_rewritten'],
            'new_model_construction':False, 'thermal_evaluations':0, 'native_calls':0}

    def test_old_n1_default_protocol_remains_unadapted(self):
        old = Harness(closed_opp_escape=True)
        result = old.run(self.path/'old_n1')
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertEqual(float(result['safe_upper_bound_J']), 10.)
        self.assertNotEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertNotIn('augmented', result['protocol'])

    def test_real_small_model_physics_full_aggregate_echo_chain(self):
        config = with_auto_low_idle(load_config())
        instance, shared, _ = small_case()
        before = scene_adapter.canonical_hash(instance)
        models, calls, sessions = [], [], []
        def loader(budget):
            budget.check(); return deepcopy(config), deepcopy(instance)
        def builder(original, cfg, **kwargs):
            model = milp.build_model(original, cfg, **kwargs); models.append(model); return model
        class Echo:
            def __init__(self, workdir, *, total_budget_s, budget):
                self.workdir = Path(workdir); self.workdir.mkdir()
                self.budget = budget; self.counter = 0; self.event_consumer = None
                self.closed = self.request_blocked = False; sessions.append(self)
            def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
                budget.check(); self.counter += 1
                self.assertion = matlab_bridge._prepare(payload, x0=x0)
                assert x0 is not None and self.assertion['x0_validation']['accepted_numerically']
                vector = np.asarray(x0).reshape(-1).tolist()
                fval = float(payload['c'] @ np.asarray(vector))
                prefix = self.workdir/('request_%03d' % self.counter)
                callback = {'kind':'callback', 'event_number':2, 'x':vector, 'values':{'fval':fval}}
                for event in ({'kind':'solver_entered', 'event_number':1}, callback):
                    _write(Path(str(prefix)+'.event_%06d.json' % event['event_number']), event)
                    if self.event_consumer: self.event_consumer(prefix)
                calls.append({'dimension':len(vector), 'original_n':len(models[self.counter-1].names),
                    'accepted_x0':True, 'complete_native_calls':0})
                return {'status':'SOLVED', 'x':vector, 'fval':fval, 'exitflag':1,
                    'budget_valid':budget.remaining>0, 'accepted_for_evaluation':budget.remaining>0,
                    'intlinprog_entered':True, 'output':{}, 'callbacks':[callback]}
            def close(self):
                self.event_consumer = None; self.closed = True
        result = fixed_unit_method.execute_augmented_fixed_unit_opp_start(loader,
            self.path/'real', shared_deployment=shared, seconds=180,
            model_builder=builder, session_factory=Echo)
        self.assertEqual(result['state'], 'SAFE', result.get('error', result))
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE', result.get('error', result))
        self.assertEqual(result['weighted_energy_J'], result['initial_global_weighted_energy_J'])
        self.assertFalse(result['strict_improvement_over_initial_certified'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertEqual(len(calls), 2); self.assertEqual(len(models), 2)
        self.assertTrue(all(row['dimension'] > row['original_n'] for row in calls))
        self.assertTrue(sessions[0].closed)
        self.assertEqual(scene_adapter.canonical_hash(instance), before)
        RECORDS['real_small_two_scene_echo'] = {'result': result, 'calls': calls,
            'model_summaries':[model.summary() for model in models],
            'native_calls':0, 'research_calls':0}


if __name__ == '__main__':
    unittest.main(verbosity=2)
