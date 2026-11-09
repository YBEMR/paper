"""N1 lifecycle boundary tests; real receipts, fake physics and native worker.

All energies/temperatures in this module are fabricated control-flow markers.
No optimizer, thermal propagation, research call or historical answer is used.
The original-input adapters, condition identities and Recorder protocol are real.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from control_policy import with_auto_low_idle
from inputs import load_config
from milp import _digest
import neighborhood
import neighborhood_adapter
import scene_adapter as adapter
from schedules import validate_schedule
from test_partial_deployment import small_case
from thermal import Exhausted


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RECORDS = {'scope': 'mock physical/native lifecycle; not physical or performance evidence'}


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    def tick(self, seconds=0.2): self.now += seconds


class Harness:
    """Dependency seam exercising the actual outer and inner lifecycle."""
    def __init__(self, **options):
        self.options = options
        self.clock = Clock()
        self.trace = []
        self.budgets = []
        self.models = {}
        self.sessions = []
        self.requests = {}
        self.condition = None
        self.aggregate_values = []
        self.inside = False
        self.original_physics_calls = []
        self.model_physics_calls = []
        self.seed_views = []
        self.input_before = None
        self.receipts = []
        self.primary_budget = None

    def loader(self, budget):
        self.primary_budget = budget
        self.budgets.append(id(budget)); self.clock.tick()
        self.instance, self.mapping, self.seed_parts = small_case()
        self.input_before = deepcopy(self.instance)
        self.opened = {sid: [r['stage_id'] for r in c['scenes'][sid]
                            if 'A.pre' not in r['stage_id']]
                       for sid, c in self.seed_parts.items()}
        return with_auto_low_idle(load_config()), self.instance

    def seed_iterator(self, instance, starts=None, budget=None, max_attempts=3):
        self.budgets.append(id(budget)); self.clock.tick()
        self.seed_views.append(deepcopy(instance))
        self.trace.append(('seed_constructed', self.clock.now))
        if self.options.get('no_seed_candidate'):
            yield {'status': 'CONSTRUCTION_UNRESOLVED', 'details': {'reason': 'MOCK_CONSTRUCTION_FAILURE'}}
            return
        proposal = {'scenes': {sid: deepcopy(c['scenes'][sid]) for sid, c in self.seed_parts.items()}}
        yield {'status': 'COMPLETE_LEGAL_CANDIDATE', 'candidate': proposal,
               'rule_version': 'MOCK_SEED_CONSTRUCTION', 'template_rank': 1}

    def _local_opp(self, proposal, sid):
        return next(row['opp'] for row in proposal['scenes'][sid] if 'A.pre' not in row['stage_id'])

    def proposed(self, model, number):
        sid = model.instance['scenarios'][0]['id']
        out = deepcopy(self.seed_parts[sid])
        if number:
            row = next(r for r in out['scenes'][sid] if 'A.pre' not in r['stage_id'])
            row.update(opp={1: 'M', 2: 'L'}[int(number)], start_ms='15')
            if self.options.get('outside_n1'):
                row['unit'] = 'CPU1' if row['unit'] == 'CPU2' else 'CPU2'
            if self.options.get('closed_opp_escape'):
                next(r for r in out['scenes'][sid] if 'A.pre' in r['stage_id'])['opp'] = 'M'
        return out

    def physical(self, platform, entry, limits, segments, window, accuracy, budget, *, scene_id):
        local = next(s for s in segments
                     if any('A.pre' not in stage for stage in s['active_stage_ids']))
        opp = local['domain_opps']['CPU']
        self.original_physics_calls.append((scene_id, opp))
        if self.options.get('no_safe_seed') and self.condition is None:
            return {'scene_id': scene_id, 'state': 'UNRESOLVED', 'reason': 'MOCK_HEAT_UNRESOLVED',
                    'complete': False, 'rankable_energy': False, 'violations': [],
                    'energy_J': None, 'energy_accuracy_met': False,
                    'covered_until_s': '0', 'completed_at_elapsed_s': budget.elapsed}
        value = str({'H': 10, 'M': 8, 'L': 6}[opp])
        if self.options.get('late_physical_safe') and opp != 'H': self.clock.tick(100)
        return {'scene_id': scene_id, 'state': 'SAFE', 'reason': 'MOCK_COMPLETE_PHYSICS',
                'complete': True, 'rankable_energy': True, 'violations': [],
                'energy_J': [value, value], 'energy_accuracy_met': True,
                'covered_until_s': str(Fraction(window)/1000),
                'completed_at_elapsed_s': budget.elapsed}

    def seed_scene_evaluator(self, instance, sid, mapping, proposal, accuracy, budget):
        self.budgets.append(id(budget)); self.clock.tick()
        self.assert_original(instance)
        with patch.object(adapter, 'evaluate_piecewise', side_effect=self.physical):
            receipt = adapter.evaluate_partial_scene(instance, sid, mapping, proposal, accuracy, budget)
        self.receipts.append(receipt)
        self.trace.append(('seed_receipt', sid, receipt['state'], self.clock.now))
        return receipt

    def assert_original(self, instance):
        assert instance == self.input_before, 'Original full input must remain unchanged'
        assert len(instance['scenarios']) == 2, 'No projected input may claim original-input evaluation'

    def aggregator(self, instance, mapping, receipts, candidates, accuracy, budget):
        self.budgets.append(id(budget)); self.clock.tick()
        self.assert_original(instance)
        result = adapter.aggregate_partial_scene_receipts(instance, mapping, receipts, candidates, accuracy, budget)
        if result['state'] == 'SAFE':
            self.aggregate_values.append(result['safe_upper_bound_J'])
            self.trace.append(('aggregate', result['safe_upper_bound_J'], self.inside, budget.elapsed))
            if self.options.get('late_aggregate_transfer') and len(self.aggregate_values) > 1:
                self.clock.tick(100)
        return result

    def condition_factory(self, *args, **kwargs):
        budget = kwargs['budget']; self.budgets.append(id(budget)); self.clock.tick()
        assert self.aggregate_values, 'N1 must not precede an all-scene SAFE aggregate'
        self.trace.append(('condition', self.clock.now))
        result = neighborhood.make_n1_condition(*args, **kwargs)
        self.condition = result
        return result

    def builder(self, instance, config, **kwargs):
        budget = kwargs['budget']; sid = kwargs['fixed_scene_id']
        self.budgets.append(id(budget)); self.clock.tick()
        assert self.condition is not None, 'No N1 model before original-input SAFE seed'
        assert kwargs['neighborhood_condition'] == self.condition
        self.assert_original(instance)
        view = adapter.make_scene_instance(instance, sid)
        for shared, unit in kwargs['fixed_shared_deployment'].items():
            if shared in view['stage_modes']:
                view['stage_modes'][shared] = [m for m in view['stage_modes'][shared] if m['unit_id'] == unit]
        model = SimpleNamespace(instance=view, budget=budget, names=['y_fixture'], scenes={sid: {}},
            neighborhood_condition=deepcopy(self.condition), formulation={'fixed_device_neighborhood': True},
            preprocessing={'source_input_sha256': _digest(instance),
                           'fixed_shared_deployment': deepcopy(self.mapping),
                           'neighborhood_condition_sha256': self.condition['condition_sha256']})
        model.summary = lambda: {'problem_id': view['id'], 'variables': 1, 'rows': 0,
                                'neighborhood': {'condition_sha256': self.condition['condition_sha256']}}
        model.as_solver_dict = lambda: {'marker': sid}
        self.models[sid] = model
        self.trace.append(('model', sid, self.clock.now))
        if self.options.get('expire_construction'): self.clock.tick(100)
        return model

    def evaluator(self, model, proposal, accuracy, budget):
        self.budgets.append(id(budget)); self.clock.tick()
        sid = next(iter(proposal['scenes'])); opp = self._local_opp(proposal, sid)
        self.model_physics_calls.append((sid, opp))
        checked = validate_schedule(model.instance, proposal)
        assert checked['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED', checked
        violation = self.options.get('violation') and opp == 'M'
        unknown = self.options.get('unknown_heat') and opp == 'M'
        points = []
        if violation:
            points = [{'scene_id': sid, 'node': 'CPU1', 'time_s': '0',
                       'temperature_degC': ['81', '81'],
                       'limit_degC': model.instance['scenarios'][0]['maximum_temperature_degC'][0],
                       'formed_at_elapsed_s': budget.elapsed}]
        value = str({'H': 10, 'M': 8, 'L': 6}[opp])
        if (self.options.get('cached_energy_mismatch') and opp == 'H'
                and self.model_physics_calls.count((sid, 'H')) > 1):
            value = '11'
        return {'state': 'THERMAL_VIOLATION' if violation else ('UNRESOLVED' if unknown else 'SAFE'),
                'reason': 'MOCK_MODEL_PHYSICS', 'problem_id': model.instance['id'],
                'legality': checked, 'violations': points,
                'rankable_energy': not (violation or unknown),
                'weighted_energy_J': None if violation or unknown else [value, value],
                'safe_upper_bound_J': None if violation or unknown else value,
                'completed_at_elapsed_s': budget.elapsed,
                'evidence_identity': {'input_sha256': _digest(model.instance), 'candidate_sha256': _digest(proposal)}}

    def completer(self, model, proposal, evaluation, budget):
        self.budgets.append(id(budget)); self.clock.tick()
        assert evaluation['evidence_identity']['input_sha256'] == _digest(model.instance)
        assert proposal == self.seed_parts[model.instance['scenarios'][0]['id']]
        if self.options.get('reject_x0'):
            return {'state': 'INITIAL_POINT_REJECTED', 'reason': 'MOCK_NUMERICAL_REJECTION', 'x0': None}
        return {'state': 'INITIAL_POINT_READY', 'reason': 'INITIAL_POINT_READY', 'x0': [0.0]}

    def n1_scene_evaluator(self, instance, condition, sid, proposal, *, budget, accuracy=None):
        self.budgets.append(id(budget)); self.clock.tick()
        self.assert_original(instance)
        if self.options.get('expire_original_recheck') and self._local_opp(proposal, sid) != 'H':
            self.clock.tick(100)
        with patch.object(adapter, 'evaluate_piecewise', side_effect=self.physical):
            result = neighborhood_adapter.evaluate_n1_scene(instance, condition, sid, proposal,
                                                            budget=budget, accuracy=accuracy)
        self.trace.append(('n1_original', sid, result['state'], self.inside))
        return result

    def recorder(self, *args, **kwargs):
        from partial_method import PartialRecorder
        def decoder(model, x):
            if len(x) != 1 or x[0] not in (0, 1, 2): raise ValueError('Mock noninteger candidate')
            return self.proposed(model, int(x[0]))
        return PartialRecorder(*args, decoder=decoder, **kwargs)

    def feedback(self, model, proposal, evaluation):
        assert not self.inside, 'Feedback must wait for the native request to settle'
        assert evaluation['state'] == 'THERMAL_VIOLATION'
        self.clock.tick()
        self.trace.append(('feedback', next(iter(proposal['scenes']))))
        return {'state': 'ROWS_ADDED', 'rows_added': 1, 'scope': 'MOCK_N1_CONTROL_ONLY'}

    def session_factory(self, workdir, **kwargs):
        harness = self
        if self.options.get('startup_error'): raise RuntimeError('MOCK_STARTUP_ERROR')
        class Session:
            def __init__(self):
                self.workdir = Path(workdir); self.workdir.mkdir(parents=True)
                self.counter = 0; self.event_consumer = None
                harness.budgets.append(id(kwargs['budget'])); harness.clock.tick()
                harness.sessions.append(self)
            def solve(self, payload, **request):
                sid = payload['marker']; self.counter += 1
                harness.requests[sid] = harness.requests.get(sid, 0) + 1
                harness.budgets.append(id(request['budget']))
                harness.trace.append(('request', sid, request['remaining_s'], request.get('x0')))
                harness.inside = True
                prefix = self.workdir / ('request_%03d' % self.counter)
                if harness.options.get('reported_infeasible'):
                    harness.inside = False
                    return {'status': 'SOLVED', 'x': [], 'exitflag': -2,
                            'budget_valid': True, 'accepted_for_evaluation': False,
                            'intlinprog_entered': True, 'output': {'lowerbound': 999.0}}
                limit = 2 if harness.options.get('repeat_violation') else 1
                number = (0 if harness.options.get('return_seed') else
                          2 if harness.options.get('violation') and harness.requests[sid] > limit else 1)
                for sequence, event in enumerate(({'kind': 'solver_entered'},
                        {'kind': 'incumbent', 'x': [number], 'values': {'lowerbound': 999.0}}), 1):
                    harness.clock.tick()
                    Path(str(prefix) + '.event_%06d.json' % sequence).write_text(json.dumps(event), encoding='utf-8')
                    if self.event_consumer: self.event_consumer(prefix)
                cancelled = Path(str(prefix) + '.cancel').exists()
                harness.trace.append(('return', sid, cancelled))
                harness.inside = False; harness.clock.tick()
                if harness.options.get('raise_after_callback'): raise RuntimeError('MOCK_WORKER_ERROR')
                if harness.options.get('expire_after_callback'): harness.clock.tick(100)
                within = request['budget'].remaining > 0
                return {'status': 'SOLVED', 'x': [] if cancelled else [number],
                        'exitflag': -1 if cancelled else 1, 'budget_valid': within,
                        'accepted_for_evaluation': within and not cancelled,
                        'intlinprog_entered': True, 'output': {'lowerbound': 999.0}, 'callbacks': []}
            def close(self): harness.trace.append(('closed',)); harness.clock.tick(2)
        return Session()

    def run(self, directory, **extra):
        from neighborhood_method import execute_n1_neighborhood
        # Opening policy is explicit fixture input, not inferred by the method.
        instance, _, parts = small_case()
        opened = {sid: [r['stage_id'] for r in c['scenes'][sid] if 'A.pre' not in r['stage_id']]
                  for sid, c in parts.items()}
        return execute_n1_neighborhood(self.loader, directory,
            shared_deployment={'A.pre': 'CPU1'}, opened_by_scene=opened,
            seconds=60, clock=self.clock, seed_iterator=self.seed_iterator,
            seed_scene_evaluator=self.seed_scene_evaluator, condition_factory=self.condition_factory,
            model_builder=self.builder, initial_completer=self.completer, model_evaluator=self.evaluator,
            n1_scene_evaluator=self.n1_scene_evaluator, aggregator=self.aggregator,
            recorder_factory=self.recorder, session_factory=self.session_factory,
            feedback_adder=self.feedback, **extra)


class N1MethodLifecycle(unittest.TestCase):
    def setUp(self):
        home = REPO / '.runtime/neighborhood_method_unit'; home.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='unit_', dir=home)
        self.path = Path(self.temp.name).resolve(); self.path.relative_to(home.resolve())
    def tearDown(self): self.temp.cleanup()

    def test_seed_precedes_condition_and_models_with_one_budget(self):
        h = Harness(); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(len(set(h.budgets)), 1)
        self.assertEqual(len(h.sessions), 1)
        kinds = [r[0] for r in h.trace]
        self.assertLess(kinds.index('seed_constructed'), kinds.index('aggregate'))
        self.assertLess(kinds.index('aggregate'), kinds.index('condition'))
        self.assertLess(kinds.index('condition'), kinds.index('model'))
        self.assertEqual(h.instance, h.input_before)
        filtered = h.seed_views[0]
        self.assertTrue(all(m['unit_id'] == 'CPU1' for m in filtered['stage_modes']['A.pre']))
        self.assertEqual(filtered['stage_modes']['B.pre'], h.instance['stage_modes']['B.pre'])
        self.assertEqual(filtered['stage_modes']['C.pre'], h.instance['stage_modes']['C.pre'])
        RECORDS['mock_success'] = {'result': out, 'trace': h.trace}

    def test_callback_recheck_and_global_improvement_precede_native_return(self):
        h = Harness(); out = h.run(self.path/'run')
        self.assertLess(Fraction(out['safe_upper_bound_J']), 10)
        self.assertTrue(any(r[0] == 'n1_original' and r[3] for r in h.trace))
        self.assertTrue(any(r[0] == 'aggregate' and r[2] for r in h.trace))
        self.assertTrue(all(r[2] < 60 for r in h.trace if r[0] == 'request'))

    def test_callback_final_duplicates_do_not_repeat_original_physics(self):
        h = Harness(); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(len(h.aggregate_values), 3, h.trace)
        self.assertEqual(len(h.original_physics_calls), 4, h.original_physics_calls)

    def test_seed_reappearance_reuses_only_current_invocation_receipts(self):
        h = Harness(return_seed=True); out = h.run(self.path/'run')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.aggregate_values), 1, h.trace)
        self.assertEqual(len(h.original_physics_calls), 2, h.original_physics_calls)

    def test_violation_cancels_then_feedbacks_after_request_return(self):
        h = Harness(violation=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        cuts = [i for i, row in enumerate(h.trace) if row[0] == 'feedback']
        self.assertEqual(len(cuts), 2, h.trace)
        for i in cuts: self.assertTrue(any(row[0] == 'return' and row[2] for row in h.trace[:i]))
        self.assertTrue(all(count == 2 for count in h.requests.values()))
        RECORDS['mock_feedback'] = {'result': out, 'trace': h.trace}

    def test_cached_violation_is_cancelled_again_without_losing_next_round(self):
        h = Harness(violation=True, repeat_violation=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(sum(row[0] == 'feedback' for row in h.trace), 4)
        self.assertTrue(all(count == 3 for count in h.requests.values()))

    def test_violation_committed_before_deadline_is_not_discarded(self):
        h = Harness(violation=True, expire_after_callback=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertTrue(out['violations'])
        self.assertFalse(any(row[0] == 'feedback' for row in h.trace))
        self.assertTrue(out['budget_exhausted'])

    def test_no_safe_seed_does_not_create_condition_model_or_infeasibility(self):
        for option in ('no_safe_seed', 'no_seed_candidate'):
            with self.subTest(option=option):
                h = Harness(**{option: True}); out = h.run(self.path/option)
                self.assertNotEqual(out['state'], 'SAFE', out)
                self.assertIsNone(out['safe_upper_bound_J'])
                self.assertIsNone(h.condition); self.assertFalse(h.models); self.assertFalse(h.sessions)
                self.assertFalse(out['independently_proven_infeasible'])

    def test_x0_rejection_preserves_seed_and_allows_bare_conditional_search(self):
        h = Harness(reject_x0=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertTrue(h.requests)
        self.assertTrue(all(row[3] is None for row in h.trace if row[0] == 'request'))
        self.assertIsNotNone(out['initial_global_safe_upper_bound_J'])

    def test_construction_expiry_keeps_already_formed_seed(self):
        h = Harness(expire_construction=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertFalse(h.sessions)
        self.assertTrue(out['budget_exhausted'])

    def test_startup_failure_cannot_erase_seed(self):
        h = Harness(startup_error=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertFalse(h.requests)
        self.assertFalse(out['independently_proven_optimal'])

    def test_late_original_check_cannot_publish_new_upper_bound(self):
        h = Harness(expire_original_recheck=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.aggregate_values), 1)

    def test_late_safe_formation_is_not_accepted(self):
        h = Harness(late_physical_safe=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.aggregate_values), 1)

    def test_safe_aggregate_formed_before_cutoff_survives_late_transfer(self):
        h = Harness(late_aggregate_transfer=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertLess(Fraction(out['safe_upper_bound_J']), 10)
        self.assertTrue(out['budget_exhausted'])

    def test_callback_safe_survives_worker_failure_but_error_is_visible(self):
        h = Harness(raise_after_callback=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertLess(Fraction(out['safe_upper_bound_J']), 10)
        self.assertNotEqual(out['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')

    def test_fixed_device_escape_is_rejected_without_improving_or_deleting_domain(self):
        h = Harness(outside_n1=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertFalse(out['independently_proven_infeasible'])
        self.assertEqual(len(h.original_physics_calls), 2)
        self.assertNotEqual(out['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')

    def test_closed_stage_opp_cannot_change_even_with_original_legal_schedule(self):
        h = Harness(closed_opp_escape=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.original_physics_calls), 2)
        self.assertNotEqual(out['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')

    def test_cached_seed_energy_disagreement_keeps_seed_and_reports_error(self):
        h = Harness(return_seed=True, cached_energy_mismatch=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.original_physics_calls), 2)
        self.assertNotEqual(out['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')

    def test_unknown_heat_does_not_create_feedback_or_safe_candidate(self):
        h = Harness(unknown_heat=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 10)
        self.assertFalse(any(row[0] == 'feedback' for row in h.trace))
        self.assertFalse(out['independently_proven_infeasible'])

    def test_solver_reported_bound_and_infeasibility_are_not_global_certificates(self):
        h = Harness(reported_infeasible=True); out = h.run(self.path/'run')
        self.assertEqual(out['state'], 'SAFE')
        self.assertFalse(out['independently_proven_optimal'])
        self.assertFalse(out['independently_proven_infeasible'])
        self.assertFalse(out['global_deployment_search_performed'])
        self.assertFalse(out['solver_reported_bounds_aggregated'])
        for scene in out['scenes'].values():
            for bound in scene['solver_reported_bounds']:
                self.assertTrue(bound['solver_reported_only'])
                self.assertFalse(bound['independently_certified'])
        self.assertLess(Fraction(out['deployment_bounds']['L0']['lower_bound_J']), 999)

    def test_calls_rebuild_inputs_seeds_and_cannot_share_budget_identity(self):
        first = Harness(); a = first.run(self.path/'first')
        second = Harness(); b = second.run(self.path/'second')
        self.assertEqual(a['state'], 'SAFE'); self.assertEqual(b['state'], 'SAFE')
        self.assertNotEqual(first.condition['budget_identity'], second.condition['budget_identity'])
        self.assertIsNot(first.receipts[0], second.receipts[0])
        self.assertIsNot(first.sessions[0], second.sessions[0])

    def test_existing_invocation_directory_is_not_overwritten(self):
        h = Harness(); folder = self.path/'exists'; folder.mkdir()
        with self.assertRaises(FileExistsError): h.run(folder)
        self.assertIsNone(h.primary_budget)

    def test_conditional_bound_expiry_preserves_already_formed_global_bound(self):
        import partial_bounds
        original = partial_bounds.independent_lower_bound
        h = Harness()
        calls = []
        def interrupted(instance, mapping=None, budget=None):
            calls.append(mapping)
            if mapping is not None:
                h.clock.tick(100)
                raise Exhausted('wall_time_limit')
            return original(instance, None, budget)
        with patch.object(partial_bounds, 'independent_lower_bound', side_effect=interrupted):
            out = h.run(self.path/'run')
        self.assertEqual(calls, [None, {'A.pre': 'CPU1'}])
        self.assertIsNotNone(out['deployment_bounds']['L0'])
        self.assertIsNone(out['deployment_bounds']['L_a'])
        self.assertIsNone(out['safe_upper_bound_J'])
        self.assertFalse(h.seed_views)
        self.assertFalse(h.models); self.assertFalse(h.sessions)
        self.assertFalse(out['independently_proven_infeasible'])


if __name__ == '__main__':
    unittest.main()
