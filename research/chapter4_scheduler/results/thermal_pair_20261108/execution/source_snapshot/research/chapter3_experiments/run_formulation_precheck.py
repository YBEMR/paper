"""Small-domain equivalence of deadline fixing, unit/OPP locks and integrality.

No original-scale model is built or solved. Input/platform values remain
frozen; named boundary fixtures are explicitly marked as correctness-only.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time

import numpy as np

import milp
from inputs import load_config
from thermal import Budget, evaluate_candidate
from run_milp_precheck import (fixtures, independent_assignments, independent_check,
    canonical_structure_vector, exact_row_residuals, candidate_key, require, equal, save)
import run_construction_precheck as reference

HERE = Path(__file__).resolve().parent
REFERENCE = 'e6eb79242b44d06320415d4b6bf191a3237f85dd'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
VARIANTS = {
    'legacy': (False, False, False),
    'deadline_only': (True, False, False),
    'aggregate_only': (False, True, False),
    'auxiliary_only': (False, False, True),
    'scheduling': (True, True, False),
    'scheduling_relaxed': (True, True, True),
}
LOCK_TAGS = {'active_locks_opp', 'unit_opp_aggregate_lock'}


def build(instance, config, starts, variant, physics=False):
    late, locks, relaxed = VARIANTS[variant]
    return milp.build_model(instance, config, starts=starts, include_physics=physics,
        budget=Budget(seconds=600), fix_late_options=late,
        aggregate_opp_locks=locks, relax_auxiliary_integrality=relaxed)


def extra_fixtures(data):
    result = dict(data)
    one = data['one_stage_energy']
    for name, deadline, times in (
        ('deadline_exact_fraction', '34/3', ['0', '5', '120']),
        ('deadline_just_below', str(F(34, 3)-F(1, 10**14)), ['0']),
        ('deadline_just_above', str(F(34, 3)+F(1, 10**14)), ['0']),
        ('deadline_all_late', None, ['300']),
    ):
        inst, starts = deepcopy(one)
        inst['id'] = 'fixture_'+name
        inst['fixture_scope'] = 'exact_deadline_boundary_correctness_only_not_research_input'
        scene = inst['scenarios'][0]
        if deadline is not None:
            scene['requests'][0]['deadline_ms'] = deadline
        starts[scene['id']][scene['stage_instances'][0]['id']] = times
        result[name] = (inst, starts)
    inst, starts = deepcopy(data['parallel_cpu'])
    inst['id'] = 'fixture_half_open_hold'
    sid = inst['scenarios'][0]['id']
    for stage in starts[sid]:
        starts[sid][stage] = ['0', '10', '20', '40']
    result['half_open_hold'] = (inst, starts)
    return result


def bound_valid(model, vector):
    return all(F.from_float(float(a)) <= F.from_float(float(x)) <= F.from_float(float(b))
               for a, b, x in zip(model.lb, model.ub, vector))


def same_core(old, new, variant):
    late, aggregate, relaxed = VARIANTS[variant]
    equal((old.names, old.options, old.option_vars, old.shared, old.scenes, old.c, old.lb),
          (new.names, new.options, new.option_vars, new.shared, new.scenes, new.c, new.lb))
    fixed = [y for o, y in zip(old.options, old.option_vars)
             if late and F(o['end_ms']) > F(o['request_deadline_ms'])]
    equal(new.deadline_fixed_options, fixed)
    expected = list(old.ub)
    for j in fixed:
        expected[j] = 0.0
    equal(new.ub, expected)
    equal(new.integer, old.option_vars if relaxed else old.integer)
    equal(new.logical_binary, old.integer)
    equal([r for r in old.rows if r['tag'] not in LOCK_TAGS],
          [r for r in new.rows if r['tag'] not in LOCK_TAGS])
    if not aggregate:
        equal(old.rows, new.rows)
    else:
        # Check each new group against original option membership, independently
        # of the implementation's by_unit_opp dictionary.
        expected_rows = []
        for meta in old.scenes.values():
            for l, active in enumerate(meta['active']):
                keys = sorted({(o['unit_id'], o['domain_id'], o['opp_id']) for o, _ in active})
                for unit, domain, opp in keys:
                    row = {y: 1.0 for o, y in active if o['unit_id'] == unit and o['opp_id'] == opp}
                    row[meta['rho'][l, domain, opp]] = -1.0
                    expected_rows.append(tuple(sorted(row.items())))
        observed = [r for r in new.rows if r['tag'] == 'unit_opp_aggregate_lock']
        equal(Counter(tuple(sorted(r['coef'].items())) for r in observed), Counter(expected_rows))
        require(all(r['rhs'] == 0 and F(r['rounding_allowance']) == 0 for r in observed),
                'aggregate logical row must be exact')
    for j in fixed:
        equal(new.bound_signature(j), (0, 1, 0, 1))
        equal(new.bound_magnitude(j), F(0))
        equal((F(new.bound_box(j).lo), F(new.bound_box(j).hi)), (F(0), F(0)))
    payload = new.as_solver_dict()
    require(np.array_equal(payload['ub'], np.array(expected)), 'exported upper bounds differ')
    require(np.array_equal(payload['intcon'], np.array(new.integer)), 'exported integrality differs')


def projection(old, models, instance, starts):
    # All common rows were compared exactly. Evaluate them once per assignment;
    # then evaluate each distinct lock family and each variant's bounds.
    common = [r for r in old.rows if r['tag'] not in LOCK_TAGS]
    locks = [r for r in old.rows if r['tag'] in LOCK_TAGS]
    agg = [r for r in models['aggregate_only'].rows if r['tag'] in LOCK_TAGS]
    mismatches, old_enclosure_extra, legal, total = [], [], [], 0
    for candidate in independent_assignments(instance, starts):
        total += 1
        valid = independent_check(instance, candidate)['valid']
        vector = canonical_structure_vector(old, candidate)
        common_ok = all(v <= 0 for v in exact_row_residuals(old, vector, common))
        lock_ok = all(v <= 0 for v in exact_row_residuals(old, vector, locks))
        agg_ok = all(v <= 0 for v in exact_row_residuals(old, vector, agg))
        if valid:
            legal.append(candidate)
        for name, model in models.items():
            late, aggregate, _ = VARIANTS[name]
            encoded = common_ok and (agg_ok if aggregate else lock_ok) and bound_valid(model, vector)
            # At a deliberately sub-ulp deadline boundary, old outer rows can
            # admit a mathematically late assignment. Never call it legal.
            if encoded and not valid and not late and 'deadline_just_below' in instance['id']:
                old_enclosure_extra.append(name)
            elif encoded != valid:
                mismatches.append({'variant': name, 'candidate': candidate,
                                   'oracle': valid, 'encoding': encoded})
    return {'assignments': total, 'legal': len(legal), 'mismatches': mismatches,
            'old_outer_enclosure_extra_count_by_variant': dict(Counter(old_enclosure_extra))}, legal


def auxiliary_checks(model, candidate):
    vector = canonical_structure_vector(model, candidate)
    equal(candidate_key(milp.decode(model, vector)), candidate_key(candidate))
    aux = [j for j in model.logical_binary if j not in set(model.option_vars)]
    require(aux and all(j not in model.integer for j in aux), 'auxiliary variables not relaxed')
    # Same near-integer threshold as the original decoder, even for implied
    # binary variables omitted from intcon.
    for prefix in ('x:', 'rho:', 'J:', 'w:'):
        j = next(j for j in aux if model.names[j].startswith(prefix))
        bad = list(vector); bad[j] = 0.5
        try:
            milp.decode(model, bad)
        except ValueError:
            pass
        else:
            raise AssertionError('fractional implied binary accepted: '+prefix)
        near = list(vector); near[j] += 5e-7 if near[j] == 0 else -5e-7
        equal(candidate_key(milp.decode(model, near)), candidate_key(candidate))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--with-matlab', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Never overwrite previous evidence')
    args.out.mkdir(parents=True)
    started = time.monotonic()
    hashes = reference.source_snapshot(args.out)
    reference.REFERENCE = REFERENCE
    old_module, old_meta = reference.reference_sources(args.out)
    save(args.out/'reference.json', old_meta)
    config = load_config()
    require(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest() == CONFIG_SHA,
            'frozen parameter file changed')
    checks, records, solutions = [], {}, {}

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'status': 'PASS'})
        except Exception as error:
            checks.append({'name': name, 'status': 'FAIL', 'error': repr(error)})
        save(args.out/'checks_in_progress.json', checks)

    data = extra_fixtures(fixtures(config))
    save(args.out/'fixtures.json', {n: {'instance': x[0], 'starts': x[1]} for n, x in data.items()})
    try:
        for name, (instance, starts) in data.items():
            old = old_module.build_model(instance, config, starts=starts, include_physics=False,
                                         budget=Budget(seconds=600))
            models = {v: build(instance, config, starts, v) for v in VARIANTS}
            check(name+'/legacy_matches_reference_rows', lambda: reference.compare_rows(old, models['legacy']))
            check(name+'/legacy_matches_reference_matrix', lambda: reference.compare_sparse(old, models['legacy']))
            for v, model in models.items():
                check(name+'/'+v+'/core_and_exact_lock_membership', lambda v=v, m=model: same_core(old, m, v))
            record, legal = projection(old, models, instance, starts)
            check(name+'/all_six_projections_vs_independent_oracle', lambda r=record: equal(r['mismatches'], []))
            record['variants'] = {v: m.summary() for v, m in models.items()}
            records[name] = record
            if legal:
                check(name+'/relaxed_auxiliary_decode_contract', lambda: auxiliary_checks(models['scheduling_relaxed'], legal[0]))
            if name == 'deadline_all_late':
                check(name+'/all_late_fixed_without_option_deletion', lambda: equal(
                    models['scheduling'].deadline_fixed_options, models['scheduling'].option_vars))
            if name == 'deadline_exact_fraction':
                model = models['scheduling']
                equality_options = [y for o, y in zip(model.options, model.option_vars)
                                    if F(o['end_ms']) == F(o['request_deadline_ms'])]
                check(name+'/exact_equality_is_retained', lambda: require(
                    bool(equality_options) and all(model.ub[y] == 1 for y in equality_options), 'lost equality'))
            save(args.out/'projection_records.json', records)
        # Full physics comparisons retain all coefficient enclosures and row
        # order after removing only the old/new lock family.
        physical = {}
        for name in ('one_stage_energy', 'parallel_cpu', 'accelerator_queue', 'deadline_exact_fraction'):
            instance, starts = data[name]
            old = old_module.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
            candidates = [c for c in independent_assignments(instance, starts) if independent_check(instance, c)['valid']]
            physical[name] = {}
            for v in ('legacy', 'deadline_only', 'aggregate_only', 'auxiliary_only', 'scheduling', 'scheduling_relaxed'):
                model = build(instance, config, starts, v, physics=True)
                physical[name][v] = model
                check('physics/'+name+'/'+v+'/all_common_rows_and_coefficients', lambda v=v, m=model: same_core(old, m, v))
                if v == 'auxiliary_only':
                    check('physics/'+name+'/auxiliary_only_same_LP_rows', lambda: reference.compare_rows(old, model))
                # One physical lift is enough to check index compatibility;
                # equality of every physical row covers other assignments too.
                if candidates:
                    lift = old_module.lift_candidate(old, candidates[0])
                    check('physics/'+name+'/'+v+'/same_lift_objective_and_domain', lambda m=model, x=lift: require(
                        max(exact_row_residuals(m, x), default=F(0)) <= F('2e-8') and bound_valid(m, x)
                        and np.dot(m.c, x) == np.dot(old.c, x), 'physical lift changed'))
            # All six original single-Stage modes, including high and low OPP,
            # receive one shared independent complete evaluation, not a solve.
            if name == 'one_stage_energy':
                oracle = [{'candidate': c, 'evaluation': evaluate_candidate(instance, c,
                           config['accuracy_targets'], Budget(seconds=60))} for c in candidates]
                save(args.out/'complete_energy_oracle.json', oracle)
                check('physics/all_six_complete_evaluations_safe', lambda: require(
                    len(oracle) == 6 and all(r['evaluation']['state'] == 'SAFE' for r in oracle), 'oracle'))
        if args.with_matlab and all(c['status'] == 'PASS' for c in checks):
            from matlab_bridge import MatlabSession
            with MatlabSession(args.out/'matlab', total_budget_s=900) as session:
                for v in ('legacy', 'scheduling', 'scheduling_relaxed'):
                    model = physical['one_stage_energy'][v]
                    response = session.solve(model.as_solver_dict(), remaining_s=60)
                    solutions[v] = response
                    check('native/'+v+'/integer_candidate', lambda r=response: require(r.get('accepted_for_evaluation'), str(r)))
                    if response.get('accepted_for_evaluation'):
                        candidate = milp.decode(model, response['x'])
                        receipt = evaluate_candidate(model.instance, candidate, config['accuracy_targets'], Budget(seconds=60))
                        response['candidate'] = candidate
                        response['common_evaluation'] = receipt
                        best = min(F(r['evaluation']['weighted_energy_J'][1]) for r in oracle)
                        check('native/'+v+'/safe_and_same_minimum_energy', lambda r=receipt: require(
                            r['state'] == 'SAFE' and F(r['weighted_energy_J'][0]) <= best
                            and F(r['weighted_energy_J'][1])-best <= F('1e-6'), 'energy mismatch'))
                    inst, starts = data['deadline_all_late']
                    infeasible = build(inst, config, starts, v)
                    response = session.solve(infeasible.as_solver_dict(), remaining_s=60)
                    solutions[v+'_all_late'] = response
                    check('native/'+v+'/all_late_reported_infeasible', lambda r=response: equal(r.get('exitflag'), -2))
                    save(args.out/'native_results.json', solutions)
        elif args.with_matlab:
            check('native/skipped_due_to_failed_gate', lambda: require(False, 'structural/physical prerequisite failed'))
    except Exception as error:
        checks.append({'name': 'precheck/unhandled', 'status': 'FAIL', 'error': repr(error)})
    after = {name: hashlib.sha256((reference.REPO/name).read_bytes()).hexdigest() for name in hashes}
    check('source/no_mutation_during_checks', lambda: equal(hashes, after))
    check('inputs/frozen_config_unchanged', lambda: equal(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest(), CONFIG_SHA))
    result = {'status': 'PASS' if all(x['status'] == 'PASS' for x in checks) else 'FAIL',
              'passed': sum(x['status'] == 'PASS' for x in checks), 'total': len(checks), 'checks': checks,
              'source_sha256': hashes, 'reference': old_meta, 'wall_seconds': time.monotonic()-started,
              'original_scale_constructed_or_solved': False, 'research_inputs_changed': False,
              'matlab_small_domain_requested': args.with_matlab,
              'variants': dict(zip(VARIANTS, VARIANTS.values())),
              'scope': 'small-domain projection/physical equivalence; no performance result'}
    save(args.out/'checks.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'total', 'wall_seconds')}))
    for c in checks:
        if c['status'] != 'PASS':
            print(c['name'], c.get('error'))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
