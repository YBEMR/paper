"""K139 linked-pass lifecycle: fake native workers and one tiny physical echo.

Mock 10/8/7 energies are control-flow markers. The physical case echoes only
its freshly completed x0, without optimizer calls. No quality result is made.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch

import numpy as np

import fixed_unit_neighborhood
import linked_method
import linked_neighborhood as linked
import linked_neighborhood_adapter as linked_adapter
import matlab_bridge
import milp
import neighborhood
import scene_adapter
from control_policy import with_auto_low_idle
from inputs import load_config
from test_partial_deployment import small_case
from test_staged_method import StagedHarness


REPO = Path(__file__).resolve().parents[2]
RECORDS = {'scope': 'K139 linked lifecycle and tiny x0 echo, not quality evidence',
           'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0,
           'mock': {}, 'physical_tiny': {}}


def write(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=False), encoding='utf-8')


def declarations():
    _, _, parts = small_case()
    first = {sid: [r['stage_id'] for r in part['scenes'][sid] if 'A.pre' not in r['stage_id']]
             for sid, part in parts.items()}
    second = {sid: [r['stage_id'] for r in part['scenes'][sid] if 'A.pre' in r['stage_id']]
              for sid, part in parts.items()}
    return first, second


class LinkedHarness(StagedHarness):
    """Use the old deterministic transport fixture with the new exact domain."""
    def builder(self, instance, config, **kwargs):
        # The inherited fixture labels the second phase by protocol and builds
        # fabricated numerical rows only. Replace its second validator, leaving
        # every production checker and all first-pass behavior intact.
        with patch.object(fixed_unit_neighborhood, 'validate_fixed_unit_condition',
                          side_effect=linked.validate_linked_condition):
            return super().builder(instance, config, **kwargs)

    def second_condition_factory(self, *args, **kwargs):
        budget = kwargs['budget']; self.budgets.append(id(budget)); self.clock.tick()
        self.trace.append(('second_condition', self.clock.now))
        result = linked.make_linked_condition(*args, **kwargs)
        self.condition = result; self.conditions.append(result)
        if self.options.get('expire_transition'):
            self.clock.tick(400)
        return result

    def proposed(self, model, number):
        if model.phase == 1:
            return super().proposed(model, number)
        proposal = deepcopy(model.base_candidate)
        if number:
            sid = next(iter(proposal['scenes']))
            shared = next(r for r in proposal['scenes'][sid] if 'A.pre' in r['stage_id'])
            if not self.options.get('shared_AB_only') or sid == next(iter(self.seed_parts)):
                shared.update(opp='M', start_ms='0')
            if self.options.get('reset_closed'):
                next(r for r in proposal['scenes'][sid] if 'A.pre' not in r['stage_id'])['opp'] = 'H'
        return proposal

    def physical(self, platform, entry, limits, segments, window, accuracy, budget, *, scene_id):
        result = super().physical(platform, entry, limits, segments, window, accuracy,
                                  budget, scene_id=scene_id)
        a = next(s for s in segments if any('A.pre' in x for x in s['active_stage_ids']))
        if a['domain_opps']['CPU'] == 'M' and result['state'] == 'SAFE':
            result['energy_J'] = [str(Fraction(x)-1) for x in result['energy_J']]
        return result

    def evaluator(self, model, proposal, accuracy, budget):
        result = super().evaluator(model, proposal, accuracy, budget)
        sid = next(iter(proposal['scenes']))
        shared = next(r for r in proposal['scenes'][sid] if 'A.pre' in r['stage_id'])
        if shared['opp'] == 'M' and result['state'] == 'SAFE':
            result['weighted_energy_J'] = [str(Fraction(x)-1) for x in result['weighted_energy_J']]
            result['safe_upper_bound_J'] = str(Fraction(result['safe_upper_bound_J'])-1)
        return result

    def second_scene_evaluator(self, instance, condition, sid, proposal, *, budget, accuracy=None):
        self.budgets.append(id(budget)); self.clock.tick(); self.assert_original(instance)
        with patch.object(scene_adapter, 'evaluate_piecewise', side_effect=self.physical):
            return linked_adapter.evaluate_linked_scene(instance, condition, sid, proposal,
                                                        budget=budget, accuracy=accuracy)

    def run(self, directory, *, seconds=300, **extra):
        first, second = declarations()
        return linked_method.execute_linked_fixed_unit_opp_start(self.loader, directory,
            shared_deployment={'A.pre': 'CPU1'}, opened_by_scene=first,
            linked_opened_by_scene=second, seconds=seconds, clock=self.clock,
            seed_iterator=self.seed_iterator, seed_scene_evaluator=self.seed_scene_evaluator,
            condition_factory=self.condition_factory, second_condition_factory=self.second_condition_factory,
            n1_scene_evaluator=self.n1_scene_evaluator, second_scene_evaluator=self.second_scene_evaluator,
            model_builder=self.builder, initial_completer=self.completer, model_evaluator=self.evaluator,
            aggregator=self.aggregator, recorder_factory=self.recorder, session_factory=self.session_factory,
            augmented_context_factory=self.context_factory, feedback_adder=self.feedback, **extra)


class LinkedMethodTests(unittest.TestCase):
    def setUp(self):
        home = REPO/'.runtime/linked_method_correctness'; home.mkdir(parents=True, exist_ok=True)
        self.path = home/('case_'+uuid4().hex); self.path.mkdir()

    def run_fixture(self, **options):
        h = LinkedHarness(**options); out = h.run(self.path/uuid4().hex)
        self.assertEqual(out['state'], 'SAFE', out.get('error', out))
        self.assertEqual(out['safe_candidate'], out['aggregation']['safe_candidate'])
        self.assertEqual(out['safe_upper_bound_J'], out['aggregation']['safe_upper_bound_J'])
        return h, out

    def test_last_complete_first_pass_closed_choices_not_initial_seed(self):
        h, out = self.run_fixture()
        self.assertEqual(len(h.conditions), 2); old, new = h.conditions
        self.assertEqual([p['name'] for p in out['phases']], ['N1', 'linked_opp_start_warm_closed'])
        self.assertEqual(len(h.seed_views), 1); self.assertEqual(len(h.sessions), 1)
        self.assertEqual(set(h.budgets), {id(h.primary_budget)})
        second = [c for c in h.completions if c['phase'] == 2]
        self.assertEqual([h._local_opp(c['candidate'], c['sid']) for c in second], ['M', 'M'])
        for sid, rows in new['warm_options_by_scene'].items():
            for stage, row in rows.items():
                self.assertEqual(row['unit'], old['seed_options_by_scene'][sid][stage]['unit'])
                if stage not in new['opened_by_scene'][sid]:
                    self.assertEqual(row['opp'], 'M'); self.assertEqual(row['start_ms'], '15')
                    self.assertEqual(old['seed_options_by_scene'][sid][stage]['opp'], 'H')
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 7)
        self.assertEqual(out['linked_record_contract']['closed_anchor_candidate_sha256'],
                         new['warm_candidate_sha256'])
        self.assertEqual(out['linked_record_contract']['closed_anchor_phase_index'], 1)
        self.assertEqual(out['committed_safe_snapshot']['phase_index'], 2)
        # Complete second-pass updates improve the global U but may not mutate
        # the already frozen phase-1 anchor or its closed domain.
        self.assertNotEqual(scene_adapter.canonical_hash(out['safe_candidate']), new['warm_candidate_sha256'])
        self.assertEqual(new['condition_sha256'], neighborhood._condition_hash(new))
        RECORDS['mock']['committed_warm_closed'] = {'result': out, 'calls': h.calls,
                                                   'completions': h.completions}

    def test_partial_local_store_without_complete_aggregate_never_becomes_anchor(self):
        h, out = self.run_fixture(uncommitted_local=True, no_second_candidate=True)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 9)
        second = [c for c in h.completions if c['phase'] == 2]
        self.assertEqual([h._local_opp(c['candidate'], c['sid']) for c in second], ['M', 'H'])
        anchor = h.conditions[1]['warm_candidate']
        self.assertEqual([h._local_opp(anchor, sid) for sid in out['original_scene_order']], ['M', 'H'])
        self.assertTrue(any(r['state'] == 'UNRESOLVED' for r in out['aggregation_attempts']))
        RECORDS['mock']['uncommitted_local_not_anchor'] = {'result': out, 'completions': h.completions}

    def test_no_second_candidate_and_x0_rejection_keep_first_pass_complete_U(self):
        h, out = self.run_fixture(no_second_candidate=True, reject_second_x0=True)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 8)
        self.assertTrue(all(c['x0'] is None for c in h.calls[2:]))
        self.assertTrue(all(c['payload_dimension'] == 4 for c in h.calls[2:]))
        self.assertTrue(all(r['bare_MILP_fallback'] for r in out['phases'][1]['scenes'].values()))
        self.assertEqual(out['linked_record_contract']['closed_anchor_phase_index'], 1)

    def test_closed_reset_candidate_is_rejected_and_never_updates_complete_U(self):
        h, out = self.run_fixture(reset_closed=True)
        self.assertEqual(Fraction(out['safe_upper_bound_J']), 8)
        self.assertEqual(out['committed_safe_snapshot']['phase_index'], 1)
        self.assertTrue(all(row['opp'] == 'M' for rows in out['safe_candidate']['scenes'].values()
                            for row in rows if 'A.pre' not in row['stage_id']))

    def test_scene_workpoints_independent_but_specific_shared_unit_unchanged(self):
        h, out = self.run_fixture(shared_AB_only=True)
        a = [next(r for r in rows if 'A.pre' in r['stage_id'])
             for rows in out['safe_candidate']['scenes'].values()]
        self.assertEqual({r['unit'] for r in a}, {'CPU1'})
        self.assertEqual({r['opp'] for r in a}, {'M', 'H'})
        self.assertEqual(Fraction(out['safe_upper_bound_J']), Fraction(15, 2))

    def test_residual_budget_one_deadline_and_expired_transition_no_new_request(self):
        h = LinkedHarness(); out = h.run(self.path/'short', seconds=100)
        self.assertEqual(out['state'], 'SAFE', out)
        self.assertEqual(out['timing']['limit_s'], 100)
        self.assertEqual(set(h.budgets), {id(h.primary_budget)})
        self.assertLess(h.calls[2]['solver_max_time_s'], 60)
        self.assertAlmostEqual(h.calls[2]['solver_max_time_s'], h.calls[2]['budget_remaining_s']/2, places=10)
        late, stopped = self.run_fixture(expire_transition=True)
        self.assertTrue(stopped['budget_exhausted'])
        self.assertEqual(len(late.built), 2); self.assertEqual(len(late.calls), 2)
        self.assertEqual(Fraction(stopped['safe_upper_bound_J']), 8)

    def test_missing_seed_or_worker_failure_cannot_start_linked_pass(self):
        missing = LinkedHarness(no_seed_candidate=True)
        out = missing.run(self.path/'no_seed')
        self.assertNotEqual(out['state'], 'SAFE')
        self.assertFalse(missing.calls); self.assertFalse(missing.conditions)
        self.assertIsNone(out['linked_record_contract']['closed_anchor_candidate_sha256'])
        failed, out = self.run_fixture(fault_first=True)
        self.assertEqual(len(failed.calls), 1); self.assertEqual(len(failed.conditions), 1)
        self.assertTrue(out['search_failure_latched'])
        self.assertIsNone(out['linked_record_contract']['closed_anchor_candidate_sha256'])

    def test_domain_hooks_reserved_and_unbounded_caps_rejected_before_input(self):
        called = []
        def loader(budget):
            called.append(True); raise AssertionError('must reject before input')
        for override in ({'_second_phase': {}}, {'_method_identity': {}},
                         {'membership_checker': lambda *a: None}):
            with self.subTest(override=tuple(override)), self.assertRaises(ValueError):
                linked_method.execute_linked_fixed_unit_opp_start(loader, self.path/uuid4().hex,
                    shared_deployment={}, opened_by_scene={}, linked_opened_by_scene={}, **override)
        for cap in (None, True, 0, -1, 60.01, float('inf'), float('nan')):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                linked_method.execute_linked_fixed_unit_opp_start(loader, self.path/uuid4().hex,
                    shared_deployment={}, opened_by_scene={}, linked_opened_by_scene={}, scene_slice_s=cap)
        self.assertFalse(called)

    def test_true_tiny_complete_thermal_model_echo_and_phase0_anchor(self):
        config = with_auto_low_idle(load_config()); instance, shared, _ = small_case()
        first, second = declarations()
        models, calls, sessions, loads = [], [], [], []
        before = scene_adapter.canonical_hash(instance)
        def loader(budget):
            budget.check(); loads.append(id(budget)); return deepcopy(config), deepcopy(instance)
        def builder(original, cfg, **kwargs):
            model = milp.build_model(original, cfg, **kwargs); models.append(model); return model
        class Echo:
            def __init__(self, workdir, *, total_budget_s, budget):
                self.workdir = Path(workdir); self.workdir.mkdir(); self.budget = budget
                self.counter = 0; self.event_consumer = None; self.closed = self.request_blocked = False
                sessions.append(self)
            def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
                budget.check(); assert budget is self.budget and x0 is not None
                admitted = matlab_bridge._prepare(payload, x0=x0)
                assert admitted['x0_validation']['accepted_numerically']
                self.counter += 1; vector = np.asarray(x0).reshape(-1).tolist()
                prefix = self.workdir/('request_%03d'%self.counter)
                fval = float(payload['c'] @ np.asarray(vector))
                event = {'kind': 'callback', 'event_number': 2, 'x': vector, 'values': {'fval': fval}}
                for item in ({'kind': 'solver_entered', 'event_number': 1}, event):
                    write(Path(str(prefix)+'.event_%06d.json'%item['event_number']), item)
                    if self.event_consumer:
                        self.event_consumer(prefix)
                calls.append({'budget_id': id(budget), 'dimension': len(vector),
                    'original_n': len(models[self.counter-1].names),
                    'condition_sha256': models[self.counter-1].neighborhood_condition['condition_sha256'],
                    'x0_sha256': scene_adapter.canonical_hash(vector), 'x0_admitted': True})
                return {'status': 'SOLVED', 'x': vector, 'fval': fval, 'exitflag': 1,
                    'budget_valid': budget.remaining > 0, 'accepted_for_evaluation': budget.remaining > 0,
                    'intlinprog_entered': True, 'output': {}, 'callbacks': [event]}
            def close(self):
                self.event_consumer = None; self.closed = True
        out = linked_method.execute_linked_fixed_unit_opp_start(loader, self.path/'physical_tiny',
            shared_deployment=shared, opened_by_scene=first, linked_opened_by_scene=second,
            seconds=300, model_builder=builder, session_factory=Echo)
        self.assertEqual(out['state'], 'SAFE', out.get('error', out))
        self.assertEqual(out['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE', out.get('error', out))
        self.assertEqual(len(models), 4); self.assertEqual(len(calls), 4); self.assertEqual(len(sessions), 1)
        self.assertEqual(len(loads), 1); self.assertEqual(len({r['budget_id'] for r in calls}|set(loads)), 1)
        self.assertEqual(out['linked_record_contract']['closed_anchor_phase_index'], 0)
        self.assertEqual(out['weighted_energy_J'], out['initial_global_weighted_energy_J'])
        self.assertFalse(out['strict_improvement_over_initial_certified'])
        self.assertFalse(out['independently_proven_optimal']); self.assertFalse(out['independently_proven_infeasible'])
        self.assertEqual(before, scene_adapter.canonical_hash(instance)); self.assertTrue(sessions[0].closed)
        self.assertFalse(out['augmented_transport']['latched_unresolved'])
        self.assertEqual(len(out['augmented_transport']['requests']), 2)
        for model in models[2:]:
            condition = model.neighborhood_condition
            self.assertEqual(condition['warm_candidate'], condition['seed_candidate'])
            self.assertTrue(all(len(o) < len(condition['warm_options_by_scene'][sid])
                                for sid, o in condition['opened_by_scene'].items()))
        RECORDS['physical_tiny'] = {'input': instance, 'config': config, 'result': out,
            'model_summaries': [m.summary() for m in models], 'calls': calls,
            'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0}


if __name__ == '__main__':
    unittest.main(verbosity=2)
