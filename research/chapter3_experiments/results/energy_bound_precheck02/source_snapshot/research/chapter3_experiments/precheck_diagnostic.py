"""Deterministic receipt-boundary checks plus a real R2023b small fixture."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from diagnostic_search import Recorder, solve_diagnostic
from method_runner import execute_milp
from milp import build_model
from inputs import load_config
from run_milp_precheck import fixtures
from run_extended_diagnostic import source_hashes
from timing import MethodBudget
from thermal import Exhausted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--relax-auxiliary-integrality', action='store_true')
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=False)
    before = source_hashes()
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        (folder/'checks.json').write_text(json.dumps({'all_passed': False, 'checks': checks}, indent=2), encoding='utf-8')
        if not condition:
            raise AssertionError(name)

    now = [0.0]
    budget = MethodBudget(10, clock=lambda: now[0])
    candidate = {'scenes': {'fixture': [{'x': 1}]}}
    calls = []

    def decoder(model, x):
        if x == [0.5]:
            raise ValueError('noninteger')
        return deepcopy(candidate)

    def evaluator(model, value, accuracy, active_budget):
        calls.append(value)
        now[0] += 1
        return {'state': 'SAFE', 'rankable_energy': True, 'completed_at_elapsed_s': now[0],
                'safe_upper_bound_J': '3/2'}

    r = Recorder(None, {}, budget, folder, decoder=decoder, evaluator=evaluator)
    r.assess([0.5], 'bad')
    check('invalid_integer_not_safe', r.best is None and not calls)
    now[0] = 2
    r.assess([1], 'first')
    check('three_distinct_times', r.first_candidate_s == 0 and r.first_legal_s == 2 and r.first_safe_s == 3)
    r.assess([1], 'duplicate')
    check('duplicate_checked_once', len(calls) == 1 and r.duplicates == 1)
    now[0] = 10
    try:
        r.assess([1], 'late')
        raised = False
    except Exhausted:
        raised = True
    check('late_candidate_rejected_prior_safe_retained', raised and r.best is not None and len(calls) == 1)

    now[0] = 0
    late = Recorder(None, {}, budget, folder, decoder=decoder,
        evaluator=lambda *a: {'state': 'SAFE', 'rankable_energy': True,
                              'completed_at_elapsed_s': 10, 'safe_upper_bound_J': '1'})
    late.assess([1], 'late_commit')
    check('deadline_equal_not_accepted', late.best is None and late.first_safe_s is None)
    unresolved = Recorder(None, {}, budget, folder, decoder=decoder,
        evaluator=lambda *a: {'state': 'UNRESOLVED', 'rankable_energy': False,
                              'safe_upper_bound_J': '0.1'})
    unresolved.assess([1], 'prefix')
    check('prefix_energy_never_upper_bound', unresolved.best is None and not unresolved.cache)
    violation = Recorder(None, {}, budget, folder, decoder=decoder,
        evaluator=lambda *a: {'state': 'THERMAL_VIOLATION', 'rankable_energy': False, 'violations': ['witness']})
    violation.assess([1], 'violation')
    check('violation_receipt_retained_without_safe', violation.best is None and len(violation.evaluations) == 1)

    prefix = folder/'mock'
    Path(f'{prefix}.event_000001.json').write_text(json.dumps({'kind': 'solver_entered'}), encoding='utf-8')
    Path(f'{prefix}.event_000002.json').write_text(json.dumps({'kind': 'callback', 'values': {'lowerbound': 999}, 'x': []}), encoding='utf-8')
    r.poll(prefix); r.poll(prefix)
    check('ordered_events_deduplicated', r.event_count == 2 and r.solver_entered_s == 0)
    check('internal_bound_not_promoted', r.best['evaluation']['safe_upper_bound_J'] == '3/2' and not r.summary()['solver_bounds_independently_certified'])

    ranking = Recorder(None, {}, budget, folder, decoder=lambda m, x: {'value': x[0]},
        evaluator=lambda m, c, a, b: {'state': 'SAFE', 'rankable_energy': True,
            'completed_at_elapsed_s': b.elapsed, 'safe_upper_bound_J': str(c['value'])})
    ranking.assess([2], 'first'); ranking.assess([3], 'worse'); ranking.assess([1], 'better')
    check('best_uses_validated_energy_not_solver_score', ranking.best['evaluation']['safe_upper_bound_J'] == '1')
    now[0] = 10
    Path(f'{prefix}.event_000003.json').write_text(json.dumps({'kind': 'callback', 'x': [1]}), encoding='utf-8')
    r.poll(prefix)
    check('late_event_not_consumed', r.event_count == 2 and r.next_event[str(prefix)] == 3)
    now[0] = 0

    # Transfer an early safe receipt, then interrupt the transport. The final
    # result must preserve that receipt even without a returned solver vector.
    class FakeSession:
        workdir = folder/'mock_session'
        def solve(self, *a, **kw):
            rec = self.event_consumer.__self__
            rec.decoder = decoder
            rec.evaluator = evaluator
            now[0] = 2
            rec.assess([1], 'callback_before_timeout')
            now[0] = 10
            raise Exhausted('wall_time_limit')
    out = solve_diagnostic(SimpleNamespace(as_solver_dict=lambda: {}), FakeSession(), {}, budget)
    check('safe_survives_transport_interrupt', out['state'] == 'SAFE' and out['reason'] == 'wall_time_limit' and out['diagnostic']['first_safe_receipt_s'] == 3)

    # Real small physical model with unchanged frozen parameters. This is a
    # correctness fixture, not an original-scale research invocation.
    def loader(b):
        config = load_config()
        instance, starts = fixtures(config)['one_stage_energy']
        loader.starts = starts
        return config, instance
    def builder(instance, config, budget, progress):
        return build_model(instance, config, budget=budget, starts=loader.starts, progress=progress,
                           relax_auxiliary_integrality=args.relax_auxiliary_integrality)
    actual = execute_milp(loader, folder/'native', seconds=180, construct_only=False,
                          model_builder=builder, solve=solve_diagnostic)
    check('native_solver_entry_received', actual['integer_solver_entered'] is True)
    check('native_safe_independent_receipt', actual['state'] == 'SAFE' and actual['diagnostic']['first_safe_receipt_s'] < 180)
    check('native_callback_candidate_received', actual['diagnostic']['candidate_receipts'] >= 1 and any(':event' in e['source'] for e in actual['diagnostic']['evaluations']))
    check('native_complete_candidate_reused', actual['diagnostic']['duplicate_receipts'] >= 1)
    check('native_no_optimality_promotion', actual['independently_proven_optimal'] is False)
    formulation = dict(fix_late_options=True, aggregate_opp_locks=True,
                       relax_auxiliary_integrality=args.relax_auxiliary_integrality)
    check('native_requested_formulation', actual['model_summary']['formulation'] == formulation)
    check('source_unchanged_during_precheck', before == source_hashes())
    result = {'all_passed': all(c['passed'] for c in checks), 'checks': checks,
              'formulation': formulation,
              'source_hashes': before, 'scope': 'correctness fixtures, not research cases',
              'precheck_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (folder/'checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'passed': len(checks), 'all_passed': result['all_passed']}))


if __name__ == '__main__':
    main()
