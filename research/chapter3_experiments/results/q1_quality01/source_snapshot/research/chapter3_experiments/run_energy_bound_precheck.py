"""Small-domain checks for exported-row energy lower-bound strengthening.

Only the five existing correctness fixtures are constructed. The original
research instance is never built or solved. Rational comparisons establish
cut validity over the old exported row boxes; scipy/Matlab results are merely
numerical implementation checks, not independent optimality certificates.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback
from unittest.mock import patch

import numpy as np
from scipy.optimize import linprog

import milp
from inputs import load_config
from thermal import Budget, Exhausted, evaluate_candidate
from run_milp_precheck import (fixtures, independent_assignments, independent_check,
    canonical_structure_vector, exact_row_residuals, candidate_key)
import run_construction_precheck as reference

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = '1074340'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
CUT_TAG = 'energy_state_lower_bound'
IO_RETRY_EVENTS = []
CURRENT_PHASE = {'name': 'startup'}


def phase(name):
    CURRENT_PHASE['name'] = name


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(left, right, message=''):
    require(left == right, f'{message}: {left!r} != {right!r}')


def save(path, value):
    """Publish a fixed JSON payload atomically; retry IO, never the check.

    A Windows reader/antivirus lock may temporarily reject opening/replacing
    a file. Only errno 13/22/32 are retried, at most three times. The exact same
    pre-serialized bytes are used throughout; no planning/evaluation repeats.
    """
    path = Path(path)
    payload = (json.dumps(value, ensure_ascii=False, indent=2,
                          default=str)+'\n').encode('utf-8')
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    delays = (0.01, 0.05, 0.1)
    for attempt in range(4):
        operation = 'write_temporary'
        try:
            temporary.write_bytes(payload)
            operation = 'atomic_replace'
            os.replace(temporary, path)
            return
        except OSError as error:
            record = {'phase': CURRENT_PHASE['name'], 'path': str(path),
                      'temporary_path': str(temporary), 'operation': operation,
                      'attempt': attempt+1, 'errno': error.errno,
                      'winerror': getattr(error, 'winerror', None), 'error': repr(error),
                      'payload_sha256': hashlib.sha256(payload).hexdigest(),
                      'will_retry': error.errno in (13, 22, 32) and attempt < len(delays)}
            IO_RETRY_EVENTS.append(record)
            error.publication_context = record
            print('JSON_PUBLICATION_IO '+json.dumps(record, ensure_ascii=False), flush=True)
            if not record['will_retry']:
                raise
            time.sleep(delays[attempt])


def q(value):
    return F.from_float(float(value))


def expected_certificate(model, certificate):
    """Reconstruct the derivation from old exported doubles as rationals."""
    target = certificate['target']
    sources = list(certificate['sources'])
    gates = list(certificate['gates'])
    indices = list(certificate['source_rows'])
    equal(len(gates), len(indices), 'gate/row pairing')
    require(gates and len(set(gates)) == len(gates), 'empty or duplicate state gates')
    require(len(set([target]+sources+gates)) == 1+len(sources)+len(gates),
            'target/source/gate alias')
    equal(len(certificate['onehot_rows']), 2, 'one-hot premise count')
    for index, sign in zip(certificate['onehot_rows'], (1.0, -1.0)):
        row = model.rows[index]
        equal((row['coef'], row['rhs']), ({j: sign for j in gates}, sign),
              'one-hot premise must be exact')
    rows = [model.rows[i] for i in indices]
    for gate, row in zip(gates, rows):
        equal(row['tag'], 'complete_energy/lower', 'wrong premise row')
        equal(q(row['coef'].get(target, 0)), F(-1), 'energy coefficient')
        require(set(row['coef']) <= {target, gate, *sources}, 'unexpected premise variable')
    slopes = [min(q(row['coef'].get(j, 0)) for row in rows) for j in sources]
    offsets = []
    for gate, row in zip(gates, rows):
        offset = q(row['coef'].get(gate, 0))-q(row['rhs'])
        for j, slope in zip(sources, slopes):
            difference = q(row['coef'].get(j, 0))-slope
            lo, hi = q(model.lb[j]), q(model.ub[j])
            offset += min(difference*lo, difference*hi)
        offsets.append(offset)
    return slopes, offsets


def box_certificate_check(model, certificate, cut_override=None):
    """For each integral state, new residual <= old lower-row residual.

    Maximizing the difference over the full exported variable box covers all
    old integer enclosure points, including nonphysical enclosure slack.
    No solver tolerance or physical-only energy bound enters this proof.
    """
    target = certificate['target']
    sources = list(certificate['sources'])
    gates = list(certificate['gates'])
    cut = model.rows[certificate['cut_row']] if cut_override is None else cut_override
    equal(cut['tag'], CUT_TAG, 'cut tag')
    equal(q(cut['coef'].get(target, 0)), F(-1), 'cut energy coefficient')
    require(set(cut['coef']) <= {target, *sources, *gates}, 'unexpected cut variable')
    maxima = []
    for gate, index in zip(gates, certificate['source_rows']):
        old = model.rows[index]
        maximum = (q(cut['coef'].get(gate, 0))-q(cut['rhs'])
                   -q(old['coef'].get(gate, 0))+q(old['rhs']))
        for j in sources:
            delta = q(cut['coef'].get(j, 0))-q(old['coef'].get(j, 0))
            maximum += max(delta*q(model.lb[j]), delta*q(model.ub[j]))
        maxima.append(maximum)
    require(all(x <= 0 for x in maxima), 'new row removes an old exported-box integer point: '+str(maxima))
    return maxima


def core_unchanged(old, new):
    equal((old.names, old.lb, old.ub, old.bounds, old.integer, old.logical_binary,
           old.c, old.options, old.option_vars, old.shared, old.scenes,
           old.deadline_fixed_options),
          (new.names, new.lb, new.ub, new.bounds, new.integer, new.logical_binary,
           new.c, new.options, new.option_vars, new.shared, new.scenes,
           new.deadline_fixed_options), 'variables, events and legal domain')
    equal(new.rows[:len(old.rows)], old.rows, 'all old rows and enclosure metadata')
    require(all(row['tag'] == CUT_TAG for row in new.rows[len(old.rows):]), 'non-bound row appended')
    count = sum(len(meta['energy']) for meta in old.scenes.values())
    equal(len(new.rows)-len(old.rows), count, 'one cut per segment')
    equal(len(new.energy_bound_certificates), count, 'one certificate per segment')
    equal(new.row_nonzeros, sum(len(row['coef']) for row in new.rows), 'incremental nonzero count')
    old_payload, new_payload = old.as_solver_dict(), new.as_solver_dict()
    for name in ('c', 'lb', 'ub', 'intcon', 'beq'):
        require(np.array_equal(old_payload[name], new_payload[name]), 'solver array '+name)
    require(np.array_equal(old_payload['b'], new_payload['b'][:len(old.rows)]), 'old solver rhs')
    for name in ('A', 'Aeq'):
        a = old_payload[name]
        b = new_payload[name][:a.shape[0], :]
        for attribute in ('indptr', 'indices', 'data'):
            require(np.array_equal(getattr(a, attribute), getattr(b, attribute)), name+'.'+attribute)


def build(instance, config, starts, strengthened=False, relaxed=False, physics=True):
    return milp.build_model(instance, config, starts=starts, include_physics=physics,
        budget=Budget(seconds=600), fix_late_options=True, aggregate_opp_locks=True,
        relax_auxiliary_integrality=relaxed,
        strengthen_energy_lower_bounds=strengthened)


def structural_rows(model):
    return [row for row in model.rows if not any(
        model.names[j].startswith(('theta:', 'q:', 'energy:')) for j in row['coef'])]


def projection_check(model, instance, starts):
    rows = structural_rows(model)
    legal, mismatches, total = [], [], 0
    for candidate in independent_assignments(instance, starts):
        total += 1
        actual = independent_check(instance, candidate)['valid']
        vector = canonical_structure_vector(model, candidate)
        rows_ok = all(x <= 0 for x in exact_row_residuals(model, vector, rows))
        # This vector contains only scheduling values. Test scheduling bounds,
        # not its deliberately unfilled temperature/energy coordinates.
        bounds_ok = all(q(model.lb[j]) <= q(vector[j]) <= q(model.ub[j])
                        for j in model.logical_binary)
        if actual != (rows_ok and bounds_ok):
            mismatches.append(candidate_key(candidate))
        if actual:
            legal.append(candidate)
    require(not mismatches, str(mismatches))
    return {'assignments': total, 'legal': len(legal), 'mismatches': mismatches}, legal


def full_lifts(old, new, legal):
    records, vectors = [], []
    for candidate in legal:
        vector = milp.lift_candidate(old, candidate)
        vectors.append(vector)
        old_res = max(exact_row_residuals(old, vector), default=F(0))
        new_res = max(exact_row_residuals(new, vector), default=F(0))
        bounds = max([0.0]+[a-v for a, v in zip(new.lb, vector)]+
                     [v-b for v, b in zip(vector, new.ub)])
        energy = float(np.dot(old.c, vector))
        old_physical_rows_feasible = old_res <= F('2e-8') and bounds <= 2e-8
        if old_physical_rows_feasible:
            require(new_res <= F('2e-8'),
                    'strengthening removed an old feasible physical lift: '+str((candidate, old_res, new_res, bounds)))
        require(energy == float(np.dot(new.c, vector)), 'physical energy changed')
        equal(candidate_key(milp.decode(new, vector)), candidate_key(candidate), 'decode roundtrip')
        tails = []
        for sid, meta in old.scenes.items():
            require(meta['events'][-1] == F(old.instance['window_ms'])/1000, 'window tail omitted')
            tail_q = [float(vector[j]) for j in meta['q'][-1]]
            tails.append({'scene': sid, 'last_segment_end_s': str(meta['events'][-1]),
                          'last_activity_W': tail_q,
                          'last_energy_J': float(vector[meta['energy'][-1]])})
        records.append({'candidate': candidate, 'old_maximum_row_residual': float(old_res),
                        'new_maximum_row_residual': float(new_res),
                        'maximum_bound_residual': bounds, 'complete_energy_J': energy,
                        'old_physical_rows_feasible': old_physical_rows_feasible,
                        'scope': 'complete physical trajectory for every scheduling-legal assignment; '
                                 'endpoint rows alone do not certify continuous thermal safety',
                        'tail': tails})
    return records, vectors


def lp_check(old, new):
    records = {}
    for name, model in [('old', old), ('strengthened', new)]:
        payload = model.as_solver_dict()
        answer = linprog(payload['c'], A_ub=payload['A'], b_ub=payload['b'],
                         bounds=list(zip(payload['lb'], payload['ub'])), method='highs',
                         options={'time_limit': 60})
        require(answer.success, name+' small LP did not finish: '+str(answer.message))
        records[name] = {'objective_J': float(answer.fun), 'status': int(answer.status),
                         'iterations': int(answer.nit), 'message': answer.message,
                         'max_exported_row_residual': float(max(exact_row_residuals(model, answer.x), default=F(0))),
                         'x': answer.x.tolist()}
    require(records['strengthened']['objective_J']+1e-7 >= records['old']['objective_J'], 'LP objective fell')
    records['strict_increase_observed'] = records['strengthened']['objective_J'] > records['old']['objective_J']+1e-7
    records['scope'] = 'solver-reported small-fixture LP comparison; not a certified bound or original-scale performance result'
    return records


def status_checks(model, candidate, receipt, check):
    class FakeSession:
        def __init__(self, values, exitflag=1, accepted=True):
            self.values, self.exitflag, self.accepted = values, exitflag, accepted
        def solve(self, _model, remaining_s):
            return {'x': list(self.values), 'exitflag': self.exitflag, 'budget_valid': True,
                    'accepted_for_evaluation': self.accepted, 'status': 'SOLVED'}
    vector = milp.lift_candidate(model, candidate)
    unknown = deepcopy(receipt)
    unknown.update(state='UNRESOLVED', rankable_energy=False, safe_upper_bound_J=None,
                   weighted_energy_J=None, violations=[])
    count = len(model.rows)
    with patch.object(milp, 'evaluate_model_candidate', return_value=unknown):
        unresolved = milp.solve_with_feedback(model, FakeSession(vector), {}, Budget(seconds=30))
    check('status/unresolved_retains_domain_without_feedback', lambda: equal(
        (unresolved['state'], unresolved['reason'], unresolved['safe_upper_bound_J'], len(model.rows), unresolved['feedback']),
        ('UNRESOLVED', 'EVALUATION_UNRESOLVED', None, count, [])))
    reported = milp.solve_with_feedback(model, FakeSession([], -2, False), {}, Budget(seconds=30))
    check('status/reported_infeasibility_is_not_a_certificate', lambda: equal(
        (reported['reason'], reported['independently_proven_infeasible'], reported['safe_upper_bound_J']),
        ('SOLVER_REPORTED_INFEASIBLE', False, None)))
    safe = deepcopy(receipt); safe['completed_at_elapsed_s'] = 0.01
    with patch.object(milp, 'evaluate_model_candidate', return_value=safe):
        result = milp.solve_with_feedback(model, FakeSession(vector), {}, Budget(seconds=30))
    check('status/safe_still_requires_external_receipt_not_internal_bound', lambda: require(
        result['state'] == 'SAFE' and result['safe_upper_bound_J'] == receipt['safe_upper_bound_J']
        and not result['independently_proven_optimal'], str(result)))
    noop = milp.add_thermal_feedback(model, candidate, unknown)
    check('feedback/unresolved_never_adds_exclusion', lambda: equal((noop['rows_added'], len(model.rows)), (0, count)))
    return {'unresolved': unresolved, 'safe': result, 'reported_infeasible': reported,
            'scope': 'state-machine injection only; no new physical or research input'}


def synthetic_row_checks(instance, check):
    """Pure row algebra, not a new workload or physical parameter experiment."""
    def fixture(slopes, offsets, bounds, coefficient_error=F(0)):
        model = milp.Model(instance, Budget(seconds=60))
        target = model.var('test_energy', -100, 100)
        sources = [model.var('test_source:'+str(i), *bound) for i, bound in enumerate(bounds)]
        gates = [model.var('test_gate:'+str(i), integer=True) for i in range(len(slopes))]
        onehot_rows = (len(model.rows), len(model.rows)+1)
        model.eq({j: 1 for j in gates}, 1, 'joint_unique')
        source_rows = []
        for gate, a, b in zip(gates, slopes, offsets):
            row = {target: -1, gate: F(10)}
            row.update({j: value for j, value in zip(sources, a)})
            # M is a syntactic coefficient here; activation yields E>=a*z+b.
            model.le(row, F(10)-b+coefficient_error, 'complete_energy/lower')
            source_rows.append(len(model.rows)-1)
        milp.add_energy_lower_bound(model, target, sources, gates, source_rows, onehot_rows)
        certificate = model.energy_bound_certificates[-1]
        values = box_certificate_check(model, certificate)
        return model, certificate, values

    cases = [
        ('negative_slopes_negative_bounds', [[F(-2), F(1, 3)], [F(1), F(-3, 7)]],
         [F(-1), F(3)], [(F(-4), F(2)), (F(-3), F(5))], F(0)),
        ('mixed_offsets_fractional_exports', [[F(2, 3)], [F(7, 11)]],
         [F(-4, 13), F(5, 17)], [(F(-2, 5), F(8, 9))], F(1, 10**15)),
        ('zero_sources', [[], []], [F(-1, 3), F(2, 7)], [], F(1, 10**15)),
    ]
    records = []
    for name, slopes, offsets, bounds, error in cases:
        try:
            model, certificate, values = fixture(slopes, offsets, bounds, error)
            check('algebra/'+name+'/full_box_exported_validity', lambda: require(all(x <= 0 for x in values), str(values)))
            expected = expected_certificate(model, certificate)
            check('algebra/'+name+'/exact_derivation_fields', lambda: equal(
                (list(map(F, certificate['common_slopes'])), list(map(F, certificate['state_offsets']))), expected))
            invalid = deepcopy(model.rows[certificate['cut_row']])
            invalid['rhs'] = float(q(invalid['rhs'])-1)
            def reject_invalid():
                try:
                    box_certificate_check(model, certificate, invalid)
                except AssertionError:
                    return
                raise AssertionError('invalid stronger row was certified')
            check('algebra/'+name+'/reject_unjustified_stronger_constant', reject_invalid)
            records.append({'name': name, 'certificate': certificate, 'full_box_maxima': list(map(str, values))})
        except Exception as error:
            check('algebra/'+name+'/fixture', lambda error=error: (_ for _ in ()).throw(error))
    # One original outer row E>=c-delta admits a point excluded by naive E>=c.
    c, delta = F(1), F(1, 10**8)
    energy = c-delta/2
    check('algebra/physical_constant_cannot_replace_outer_energy_variable', lambda: require(
        -energy <= -(c-delta) and -energy > -c,
        'expected explicit integer outer-enclosure counterexample'))
    model, certificate, values = fixture([[]], [F(1)], [], F(0))
    invalid = deepcopy(model.rows[certificate['cut_row']])
    gate = certificate['gates'][0]
    equal(q(invalid['coef'][gate]), F(1), 'exact one-state intercept')
    equal(q(invalid['rhs']), F(0), 'zero export allowance in exact fixture')
    invalid['coef'][gate] = math.nextafter(invalid['coef'][gate], math.inf)
    def reject_one_ulp():
        try:
            box_certificate_check(model, certificate, invalid)
        except AssertionError:
            return
        raise AssertionError('one-ULP invalid stronger row was certified')
    check('algebra/one_ULP_stronger_intercept_rejected_exactly', reject_one_ulp)
    records.append({'name': 'one_ULP_rejection', 'valid_row': model.rows[certificate['cut_row']],
                    'invalid_row': invalid, 'scope': 'exact rational rejection, no epsilon threshold'})

    # Invalid premises must fail before publishing any new row/certificate.
    model, certificate, _ = fixture([[F(1)], [F(2)]], [F(1), F(-1)], [(F(-2), F(3))])
    def reject_bad_premise(kind):
        rows = deepcopy(model.rows)
        count, certificates = len(rows), len(model.energy_bound_certificates)
        arguments = (model, certificate['target'], certificate['sources'], certificate['gates'],
                     certificate['source_rows'], certificate['onehot_rows'])
        if kind == 'nonexact_onehot':
            model.rows[certificate['onehot_rows'][0]]['rhs'] = math.nextafter(1.0, math.inf)
        elif kind == 'extra_column':
            model.rows[certificate['source_rows'][0]]['coef'][certificate['gates'][1]] = 1.0
        elif kind == 'wrong_energy_coefficient':
            model.rows[certificate['source_rows'][0]]['coef'][certificate['target']] = -0.5
        elif kind == 'missing_onehot':
            arguments = arguments[:-1]+([],)
        try:
            milp.add_energy_lower_bound(*arguments)
        except ValueError:
            equal((len(model.rows), len(model.energy_bound_certificates)), (count, certificates),
                  'invalid premise was partially published')
        else:
            raise AssertionError('invalid premise accepted: '+kind)
        finally:
            model.rows = rows
    for kind in ('nonexact_onehot', 'extra_column', 'wrong_energy_coefficient', 'missing_onehot'):
        check('algebra/helper_rejects_'+kind, lambda kind=kind: reject_bad_premise(kind))
    return records


def interruption_check(instance, starts, config):
    budget = Budget(seconds=600)
    reached = []
    def interrupt(stage, _model, _detail):
        if stage == 'energy_lower_bounds':
            reached.append(stage)
            budget.start -= 601
    try:
        milp.build_model(instance, config, starts=starts, budget=budget, progress=interrupt,
                         strengthen_energy_lower_bounds=True)
    except Exhausted:
        require(reached == ['energy_lower_bounds'], 'interruption was not in new cut phase')
        return
    raise AssertionError('expired strengthening returned a solver-ready model')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--with-matlab', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Never overwrite existing evidence')
    args.out.mkdir(parents=True)
    started = time.monotonic()
    phase('source_snapshot')
    hashes = reference.source_snapshot(args.out)
    reference.REFERENCE = REFERENCE
    previous, previous_info = reference.reference_sources(args.out)
    save(args.out/'reference.json', previous_info)
    config = load_config()
    require(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest() == CONFIG_SHA, 'frozen inputs changed')
    checks, records, models, lp_records, lifts = [], {}, {}, {}, {}
    def check(name, action):
        phase('check/'+name)
        try:
            action(); checks.append({'name': name, 'status': 'PASS'})
        except Exception as error:
            checks.append({'name': name, 'status': 'FAIL', 'error': repr(error),
                           'failure_phase': CURRENT_PHASE['name'],
                           'traceback': traceback.format_exc(),
                           'publication_context': getattr(error, 'publication_context', None)})
        save(args.out/'checks_in_progress.json', checks)
    data = fixtures(config)
    save(args.out/'fixtures.json', {name: {'instance': i, 'starts': s} for name, (i, s) in data.items()})
    try:
        for name, (instance, starts) in data.items():
            phase(name+'/build_default')
            old = build(instance, config, starts)
            phase(name+'/build_committed_reference')
            historical = previous.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
            check(name+'/default_matches_committed_old_rows', lambda: reference.compare_rows(historical, old))
            check(name+'/default_matches_committed_old_matrix', lambda: reference.compare_sparse(historical, old))
            check(name+'/default_metadata_unchanged', lambda: equal(old.formulation, historical.formulation))
            phase(name+'/build_strengthened')
            strong = build(instance, config, starts, True)
            phase(name+'/build_auxiliary_relaxed')
            relaxed = build(instance, config, starts, False, True)
            phase(name+'/build_strengthened_auxiliary_relaxed')
            relaxed_strong = build(instance, config, starts, True, True)
            models[name] = {'old': old, 'strong': strong, 'relaxed': relaxed, 'relaxed_strong': relaxed_strong}
            for tag, baseline, amended in [('integer_aux', old, strong), ('continuous_aux', relaxed, relaxed_strong)]:
                check(name+'/'+tag+'/only_valid_rows_appended', lambda a=baseline, b=amended: core_unchanged(a, b))
                certificate_records = []
                for index, certificate in enumerate(amended.energy_bound_certificates):
                    phase(name+'/'+tag+f'/derive_certificate_{index}')
                    expected = expected_certificate(amended, certificate)
                    check(name+'/'+tag+f'/certificate_{index}_derivation', lambda c=certificate, e=expected: equal(
                        (list(map(F, c['common_slopes'])), list(map(F, c['state_offsets']))), e))
                    check(name+'/'+tag+f'/certificate_{index}_all_integer_outer_points',
                          lambda m=amended, c=certificate: box_certificate_check(m, c))
                    certificate_records.append(certificate)
                save(args.out/(name+'_'+tag+'_certificates.json'), certificate_records)
            check(name+'/auxiliary_switch_leaves_strengthened_LP_identical', lambda: equal(
                (strong.rows, strong.lb, strong.ub, strong.c),
                (relaxed_strong.rows, relaxed_strong.lb, relaxed_strong.ub, relaxed_strong.c)))
            phase(name+'/independent_projection')
            projection, legal = projection_check(old, instance, starts)
            records[name] = dict(projection, models={k: m.summary() for k, m in models[name].items()})
            check(name+'/independent_complete_scheduling_projection', lambda: equal(projection['mismatches'], []))
            phase(name+'/complete_physical_lifts')
            lifts[name], physical_vectors = full_lifts(old, strong, legal)
            check(name+'/all_legal_assignments_have_complete_physical_lift', lambda: equal(len(lifts[name]), len(legal)))
            check(name+'/all_legal_assignments_decode_with_relaxed_auxiliaries', lambda: require(all(
                candidate_key(milp.decode(relaxed_strong, v)) == candidate_key(c)
                for c, v in zip(legal, physical_vectors)), 'decode'))
            phase(name+'/small_LP_pair')
            lp_records[name] = lp_check(old, strong)
            check(name+'/LP_objective_does_not_decrease', lambda: require(
                lp_records[name]['strengthened']['objective_J']+1e-7 >= lp_records[name]['old']['objective_J'], 'LP'))
            save(args.out/'projection_records.json', records)
            save(args.out/'complete_physical_lifts.json', lifts)
            save(args.out/'small_LP_results.json', lp_records)
        save(args.out/'LP_observation.json', {
            'strict_increase_observed_in_any_fixture': any(r['strict_increase_observed'] for r in lp_records.values()),
            'scope': 'observational result; absence of improvement is not a correctness failure'})
        instance, starts = data['one_stage_energy']
        oracle = []
        for candidate in independent_assignments(instance, starts):
            if independent_check(instance, candidate)['valid']:
                phase('one_stage_energy/continuous_oracle_'+str(len(oracle)))
                receipt = milp.evaluate_model_candidate(models['one_stage_energy']['strong'], candidate,
                    config['accuracy_targets'], Budget(seconds=60))
                oracle.append({'candidate': candidate, 'evaluation': receipt})
        check('physics/all_six_modes_independently_continuous_safe', lambda: require(
            len(oracle) == 6 and all(x['evaluation']['state'] == 'SAFE' for x in oracle), 'six modes'))
        save(args.out/'continuous_energy_oracle.json', oracle)
        safe = next(x for x in oracle if x['evaluation']['state'] == 'SAFE')
        save(args.out/'status_checks.json', status_checks(models['one_stage_energy']['strong'],
             safe['candidate'], safe['evaluation'], check))
        save(args.out/'algebra_cases.json', synthetic_row_checks(instance, check))
        phase('structural_model_without_physics')
        no_physics = build(instance, config, starts, True, physics=False)
        check('scope/structural_model_has_no_energy_cuts', lambda: equal(no_physics.energy_bound_certificates, []))
        check('budget/interrupted_cut_phase_never_returns_ready_model',
              lambda: interruption_check(instance, starts, config))
        if args.with_matlab and all(c['status'] == 'PASS' for c in checks):
            from matlab_bridge import MatlabSession
            native = {}
            best_upper = min(F(x['evaluation']['weighted_energy_J'][1]) for x in oracle)
            with MatlabSession(args.out/'matlab', total_budget_s=600) as session:
                for label, model in models['one_stage_energy'].items():
                    phase('native/'+label+'/solve')
                    response = session.solve(model.as_solver_dict(), remaining_s=60)
                    native[label] = response
                    check('native/'+label+'/candidate', lambda r=response: require(r.get('accepted_for_evaluation'), str(r)))
                    if response.get('accepted_for_evaluation'):
                        phase('native/'+label+'/decode_and_continuous_evaluation')
                        candidate = milp.decode(model, response['x'])
                        receipt = evaluate_candidate(instance, candidate, config['accuracy_targets'], Budget(seconds=60))
                        response.update(candidate=candidate, common_evaluation=receipt)
                        check('native/'+label+'/same_safe_small_domain_minimum', lambda r=receipt: require(
                            r['state'] == 'SAFE' and F(r['weighted_energy_J'][0]) <= best_upper and
                            F(r['weighted_energy_J'][1])-best_upper <= F('1e-6'), str(r)))
                    save(args.out/'native_results.json', native)
        elif args.with_matlab:
            check('native/not_dispatched_after_failed_precheck', lambda: require(False, 'earlier checks failed'))
    except Exception as error:
        checks.append({'name': 'precheck/unhandled', 'status': 'FAIL', 'error': repr(error),
                       'failure_phase': CURRENT_PHASE['name'], 'traceback': traceback.format_exc(),
                       'publication_context': getattr(error, 'publication_context', None)})
    check('inputs/frozen_config_hash', lambda: equal(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest(), CONFIG_SHA))
    after = {name: hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in hashes}
    check('sources/not_changed_during_precheck', lambda: equal(hashes, after))
    report = {'status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'FAIL',
              'passed': sum(c['status'] == 'PASS' for c in checks), 'total': len(checks), 'checks': checks,
              'wall_seconds': time.monotonic()-started, 'source_sha256': hashes,
              'reference': previous_info, 'original_scale_constructed_or_solved': False,
              'research_inputs_changed': False, 'formal_algorithm_comparison': False,
              'matlab_small_domain_requested': args.with_matlab,
              'publication_io_events': list(IO_RETRY_EVENTS),
              'scope': 'existing small domains; exact exported-row cut validity and numerical physical/LP checks'}
    phase('final_report_publication')
    save(args.out/'checks.json', report)
    save(args.out/'publication_io_events.json', IO_RETRY_EVENTS)
    print(json.dumps({k: report[k] for k in ('status', 'passed', 'total', 'wall_seconds')}))
    for item in checks:
        if item['status'] != 'PASS':
            print(item['name'], item.get('error'))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
