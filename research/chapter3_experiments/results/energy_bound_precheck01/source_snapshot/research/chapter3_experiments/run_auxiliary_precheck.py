"""Numerical acceptance checks before the one auxiliary-relaxed diagnostic.

Only small-domain structural models and synthetic logical-vector stress
fixtures are used. No MATLAB invocation, original-scale construction, physical
parameter change or search run occurs here. Synthetic vectors test decoding;
they are not claimed to satisfy the exported MILP or model solver roundoff.
"""
import argparse
import ast
from copy import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np

import milp
from diagnostic_search import Recorder
from inputs import load_config
from run_extended_diagnostic import source_hashes
from run_milp_precheck import (fixtures, independent_assignments, independent_check,
    canonical_structure_vector, candidate_key, require, equal, save)
from thermal import Budget, Exhausted
from timing import MethodBudget

HERE = Path(__file__).resolve().parent
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
TOL = 1e-6


def rejected(model, vector):
    try:
        milp.decode(model, vector)
    except ValueError:
        return
    raise AssertionError('invalid numerical vector was accepted')


def same_candidate(model, vector, expected):
    decoded = milp.decode(model, vector)
    equal(candidate_key(decoded), candidate_key(expected))
    require(independent_check(model.instance, decoded)['valid'],
            'decoded schedule violates independent exact oracle')


def perturb(vector, index, value):
    out = list(vector)
    out[index] = value
    return out


def synthetic_holds(model, vector, count, step):
    """Append continuous implied binary values without building a MILP.

    No claim is made that these added columns are physical control states or
    satisfy MILP rows. They exercise the all-logical decoder at the two known
    event-chain lengths, using an otherwise real small scheduling fixture.
    """
    synthetic = copy(model)
    synthetic.names = list(model.names)
    synthetic.logical_binary = list(model.logical_binary)
    synthetic.lb, synthetic.ub = list(model.lb), list(model.ub)
    result = list(vector)
    start = len(result)
    for position in range(count):
        j = len(result)
        synthetic.names.append(f'rho:synthetic_hold:{position}:low')
        synthetic.logical_binary.append(j)
        synthetic.lb.append(0.0)
        synthetic.ub.append(1.0)
        result.append(position * step)
    return synthetic, result, start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    hashes = source_hashes()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    checks, details = [], {}
    snapshot = args.out/'source_snapshot'
    snapshot.mkdir()
    names = ['milp.py', 'diagnostic_search.py', 'run_auxiliary_precheck.py',
             'run_milp_precheck.py', 'run_extended_diagnostic.py', 'config_v01.json']
    for name in names:
        (snapshot/name).write_bytes((HERE/name).read_bytes())

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'status': 'PASS'})
        except Exception as exc:
            checks.append({'name': name, 'status': 'FAIL', 'error': repr(exc)})
        save(args.out/'checks_in_progress.json', checks)

    check('frozen_input_hash', lambda: equal(
        hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest(), CONFIG_SHA))
    config = load_config()
    built = {}
    for name, (instance, starts) in fixtures(config).items():
        regular = milp.build_model(instance, config, starts=starts,
            include_physics=False, budget=Budget(seconds=60),
            fix_late_options=True, aggregate_opp_locks=True,
            relax_auxiliary_integrality=False)
        model = milp.build_model(instance, config, starts=starts,
            include_physics=False, budget=Budget(seconds=60),
            fix_late_options=True, aggregate_opp_locks=True,
            relax_auxiliary_integrality=True)
        check(name+'/only_integer_declarations_change', lambda a=regular, b=model: equal(
            (a.names, a.options, a.rows, a.lb, a.ub, a.c, a.logical_binary),
            (b.names, b.options, b.rows, b.lb, b.ub, b.c, b.logical_binary)))
        check(name+'/only_y_remains_declared_integer', lambda m=model: equal(m.integer, m.option_vars))
        check(name+'/all_logical_columns_remain_checked', lambda a=regular, b=model: equal(
            b.logical_binary, a.integer))
        valid = [c for c in independent_assignments(instance, starts)
                 if independent_check(instance, c)['valid']]
        require(valid, 'fixture needs a legal assignment')
        for pos, candidate in enumerate(valid):
            vector = canonical_structure_vector(model, candidate)
            check(name+f'/legal_roundtrip_{pos}', lambda m=model, v=vector, c=candidate:
                  same_candidate(m, v, c))
        candidate = valid[0]
        vector = canonical_structure_vector(model, candidate)
        built[name] = model, candidate, vector
        details[name] = {'summary': model.summary(), 'valid_assignments': len(valid)}

    model, candidate, vector = built['parallel_cpu']
    aux = [j for j in model.logical_binary if j not in set(model.option_vars)]
    family_counts = {}
    for prefix in ('y:', 'x:', 'rho:', 'J:', 'w:'):
        family = [j for j in model.logical_binary if model.names[j].startswith(prefix)]
        require(family, 'missing family '+prefix)
        family_counts[prefix] = len(family)
        zero = next(j for j in family if vector[j] == 0)
        one = next((j for j in family if vector[j] == 1), None)
        for value in (0.5, -1, 2):
            check(prefix+f'/reject_{value}', lambda j=zero, v=value:
                  rejected(model, perturb(vector, j, v)))
        for value in (np.nan, np.inf, -np.inf):
            check(prefix+f'/reject_nonfinite_{value}', lambda j=zero, v=value:
                  rejected(model, perturb(vector, j, v)))
        for label, value, accepted in (
            ('inside', np.nextafter(TOL, 0), True),
            ('equal', TOL, True),
            ('outside', np.nextafter(TOL, np.inf), False),
            ('negative_inside', -np.nextafter(TOL, 0), True),
            ('negative_outside', -np.nextafter(TOL, np.inf), False),
        ):
            fn = (lambda j=zero, v=value: same_candidate(model, perturb(vector, j, v), candidate)) if accepted else (
                lambda j=zero, v=value: rejected(model, perturb(vector, j, v)))
            check(prefix+'/tolerance_'+label, fn)
        if one is not None:
            check(prefix+'/near_one_inside', lambda j=one:
                  same_candidate(model, perturb(vector, j, 1-TOL/2), candidate))
            check(prefix+'/near_one_outside', lambda j=one:
                  rejected(model, perturb(vector, j, 1-2*TOL)))
    details['families'] = family_counts
    report = milp.logical_candidate_diagnostics(model, vector)
    check('diagnostics_exact_vector_accepted', lambda: require(
        report['vector_valid'] and report['accepted'] and report['integer_tolerance'] == TOL,
        'wrong exact-vector diagnostics'))
    for prefix, count in family_counts.items():
        check(prefix+'/diagnostics_count', lambda p=prefix, n=count: equal(
            report['families'][p[:-1]]['count'], n))
    j = aux[-1]
    report_bad = milp.logical_candidate_diagnostics(model, perturb(vector, j, 0.25))
    check('diagnostics_worst_aux_variable', lambda: require(
        not report_bad['accepted'] and report_bad['families'][model.names[j].split(':')[0]]['worst_variable'] == model.names[j],
        'worst auxiliary variable was not recorded'))
    # Reproduce the old decoder defect from the immutable pre-fix commit.
    # Only its decode function is executed; no historical model/search runs.
    old_source = subprocess.run(['git', 'show', '8bf2ba1:research/chapter3_experiments/milp.py'],
        cwd=HERE.parents[1], check=True, capture_output=True).stdout
    (args.out/'old_milp_8bf2ba1.py').write_bytes(old_source)
    function = next(n for n in ast.parse(old_source.decode('utf-8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'decode')
    namespace = {'np': np, 'validate_schedule': milp.validate_schedule}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<historical-decode>', 'exec'), namespace)
    old_failures = []
    for value in (-1, 2):
        old_candidate = namespace['decode'](model, perturb(vector, aux[0], value))
        old_failures.append({'aux_variable': model.names[aux[0]], 'value': value,
            'expected': 'reject_outside_binary', 'observed': 'accepted',
            'same_schedule': candidate_key(old_candidate) == candidate_key(candidate)})
    save(args.out/'historical_failure_record.json', {
        'source_commit': '8bf2ba1', 'old_source_sha256': hashlib.sha256(old_source).hexdigest(),
        'reproduced_after_fix_from_immutable_old_source': True, 'failures': old_failures})
    check('historical_outside_binary_defect_reproduced', lambda: require(
        all(x['same_schedule'] for x in old_failures), 'old defect reproduction failed'))
    old_text = old_source.decode('utf-8')
    current_text = (HERE/'milp.py').read_bytes().decode('utf-8')
    def build_function(text):
        parsed = ast.parse(text)
        node = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == 'build_model')
        return ast.get_source_segment(text, node)
    old_build, current_build = build_function(old_text), build_function(current_text)
    details['build_model_source_identity'] = {
        'reference_commit': '8bf2ba1', 'equal': old_build == current_build,
        'old_sha256': hashlib.sha256(old_build.encode()).hexdigest(),
        'current_sha256': hashlib.sha256(current_build.encode()).hexdigest(),
        'scope': 'exact build_model function source; numerical acceptance wrapper changes separately checked'}
    check('build_model_source_unchanged', lambda: equal(old_build, current_build))
    check('wrong_length_short', lambda: rejected(model, vector[:-1]))
    check('wrong_length_long', lambda: rejected(model, vector+[0.0]))
    synthetic_continuous = copy(model)
    synthetic_continuous.names = model.names+['energy:synthetic']
    check('nonfinite_unrelated_continuous_column', lambda: rejected(
        synthetic_continuous, vector+[np.nan]))

    missing = list(vector)
    for j in model.option_vars:
        missing[j] = 0.0
    check('integral_options_missing_stage_rejected', lambda: rejected(model, missing))
    extra = list(vector)
    extra[next(j for j in model.option_vars if vector[j] == 0)] = 1.0
    check('integral_options_duplicate_stage_rejected', lambda: rejected(model, extra))
    fractional = list(vector)
    fractional[aux[-1]] = 0.5
    check('last_auxiliary_column_not_skipped', lambda: rejected(model, fractional))

    # 928 increments of <1e-9 cannot alone exceed 1e-6. Check that actual
    # arithmetic rather than asserting an impossible accumulation example.
    details['synthetic_holds'] = []
    for length in (851, 928):
        for step, accepted in ((0.9e-9, True), (2e-9, False)):
            synthetic, values, first = synthetic_holds(model, vector, length, step)
            maximum = max(abs(values[j]-round(values[j])) for j in range(first, len(values)))
            details['synthetic_holds'].append({'length': length, 'step': step,
                'max_integrality_error': maximum, 'expected_accepted': accepted,
                'scope': 'decoder-only; no MILP row-feasibility assertion'})
            fn = (lambda m=synthetic, v=values: same_candidate(m, v, candidate)) if accepted else (
                lambda m=synthetic, v=values: rejected(m, v))
            check(f'hold_{length}/drift_{step}', fn)
        synthetic, values, first = synthetic_holds(model, vector, length, 0)
        for offset in (0, length//2, length-1):
            bad = perturb(values, first+offset, 1.1e-6)
            check(f'hold_{length}/bad_column_{offset}', lambda m=synthetic, v=bad: rejected(m, v))

    # Wrong auxiliary semantics must not become an energy proof: the common
    # evaluator reconstructs state from the exact decoded schedule, never
    # trusts auxiliary values or solver objective. All values below are binary.
    changed = list(vector)
    changed[aux[0]] = 1-changed[aux[0]]
    check('binary_auxiliary_is_not_physical_certificate', lambda:
          same_candidate(model, changed, candidate))
    now = [0.0]
    budget = MethodBudget(10, clock=lambda: now[0])
    evaluator_inputs = []

    def evaluator(_model, decoded, _accuracy, _budget):
        evaluator_inputs.append(decoded)
        now[0] += 0.25
        return {'state': 'SAFE', 'rankable_energy': True,
                'completed_at_elapsed_s': now[0], 'safe_upper_bound_J': '1'}

    recorder = Recorder(model, {}, budget, args.out, evaluator=evaluator)
    recorder.assess(perturb(vector, aux[0], 0.5), 'nonintegral_aux')
    check('invalid_aux_not_legal_or_thermal', lambda: require(
        recorder.first_legal_s is None and not evaluator_inputs and recorder.best is None,
        'invalid auxiliary vector reached evaluator'))
    check('invalid_aux_rejection_logged', lambda: require(
        recorder.summary()['decode_rejections'] == 1 and len(recorder.decode_records) == 1,
        'auxiliary rejection diagnostics missing'))
    recorder.assess(vector, 'exact')
    check('legal_and_safe_times_separate', lambda: require(
        recorder.first_legal_s == 0.0 and recorder.first_safe_s == 0.25,
        'candidate and full evaluation commits conflated'))
    recorder.assess(changed, 'same_schedule_other_binary_aux')
    check('cache_identity_uses_exact_schedule', lambda: require(
        len(evaluator_inputs) == 1 and recorder.duplicates == 1,
        'auxiliary change bypassed exact-schedule identity'))
    check('evaluator_receives_schedule_not_aux', lambda: equal(
        candidate_key(evaluator_inputs[0]), candidate_key(candidate)))
    def late_decoder(_model, value):
        decoded = milp.decode(_model, value)
        now[0] = 10.0
        return decoded
    now[0] = 0.0
    late = Recorder(model, {}, budget, args.out, decoder=late_decoder, evaluator=evaluator)
    def crossing_budget():
        before_calls = len(evaluator_inputs)
        try:
            late.assess(vector, 'decode_completed_at_deadline')
        except Exhausted:
            require(late.first_legal_s is None and late.first_safe_s is None and
                    len(evaluator_inputs) == before_calls, 'late decode created in-budget evidence')
            return
        raise AssertionError('decode across budget did not stop')
    check('decode_crossing_budget_never_legal_or_evaluated', crossing_budget)
    # An invalid candidate whose decoder completes after the deadline remains
    # a late diagnostic, not an in-budget numerical-stop decision.
    now[0] = 0.0
    def late_reject_decoder(_model, _value):
        now[0] = 10.0
        raise ValueError('injected_late_decode_rejection')
    late_reject = Recorder(model, {}, budget, args.out,
                           decoder=late_reject_decoder, evaluator=evaluator)
    def rejection_crosses_budget():
        before_calls = len(evaluator_inputs)
        try:
            late_reject.assess(vector, 'decode_rejects_at_deadline')
        except Exhausted:
            require(late_reject.first_legal_s is None and late_reject.first_safe_s is None and
                    len(evaluator_inputs) == before_calls and
                    late_reject.decode_records[-1]['state'] == 'REJECTED' and
                    not late_reject.decode_records[-1]['within_budget'],
                    'late rejection became accepted evidence or lost its diagnostic')
            return
        raise AssertionError('late decode rejection returned without budget interruption')
    check('late_decode_rejection_remains_budget_exhaustion', rejection_crosses_budget)
    # A legal receipt completed before the deadline survives later logging
    # overhead, but no thermal evaluation may start after that deadline.
    now[0] = 0.0
    log_late = Recorder(model, {}, budget, args.out, evaluator=evaluator)
    original_log = log_late.log
    def delayed_log(row):
        original_log(row)
        if row.get('event') == 'candidate_decoded':
            now[0] = 10.0
    log_late.log = delayed_log
    def logging_crosses_budget():
        before_calls = len(evaluator_inputs)
        try:
            log_late.assess(vector, 'logging_after_legal_receipt_crosses_deadline')
        except Exhausted:
            require(log_late.first_legal_s == 0.0 and log_late.first_safe_s is None and
                    len(evaluator_inputs) == before_calls and
                    log_late.decode_records[-1]['within_budget'],
                    'logging erased legal receipt or started late thermal evaluation')
            return
        raise AssertionError('logging across budget did not stop')
    check('legal_receipt_survives_logging_cross_budget', logging_crosses_budget)
    check('source_unchanged_during_precheck', lambda: equal(hashes, source_hashes()))
    save(args.out/'details.json', details)
    result = {'all_passed': all(c['status'] == 'PASS' for c in checks),
        'checks': checks, 'source_hashes': hashes, 'precheck_source_sha256': own_hash,
        'formulation': {'fix_late_options': True, 'aggregate_opp_locks': True,
                        'relax_auxiliary_integrality': True},
        'elapsed_s': time.monotonic()-started,
        'scope': 'small correctness fixtures and synthetic decoder stress only; no MATLAB or original benchmark',
        'limitations': ['Does not certify floating MILP constraints or arbitrary solver roundoff.',
            'Binary auxiliary consistency is not independently certified; accepted schedules are reconstructed from y and undergo exact legality and full thermal-energy evaluation.',
            'Synthetic holding drift is not a physical or solver-feasible trajectory.']}
    save(args.out/'checks.json', result)
    print(json.dumps({'all_passed': result['all_passed'], 'passed': sum(c['status'] == 'PASS' for c in checks),
                      'total': len(checks), 'failed': [c['name'] for c in checks if c['status'] == 'FAIL']}))
    raise SystemExit(0 if result['all_passed'] else 1)


if __name__ == '__main__':
    main()
