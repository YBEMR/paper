"""Exact small-domain equivalence against the pre-optimization constructor.

This checks representation equality, not solver performance. The old sources
come from the declared Git revision and are archived before loading. The five
existing correctness domains, plus explicit boundary fixtures, are unrelated
to the formal research workload. No MATLAB solve or original-scale build runs.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from inputs import load_config
from run_milp_precheck import (fixtures, independent_assignments,
    independent_check, canonical_structure_vector, exact_row_residuals)
from thermal import Budget, I, Exhausted

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = 'bb53928'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   default=str)+'\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(left, right, label=''):
    require(left == right, f'{label}: {left!r} != {right!r}')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_sources(folder):
    full_revision = subprocess.check_output(['git', 'rev-parse', REFERENCE], cwd=REPO,
                                            text=True).strip()
    old_folder = folder/'reference_source'
    old_folder.mkdir()
    records = {}
    for name in ('milp.py', 'milp_coefficients.py'):
        data = subprocess.check_output(['git', 'show',
            f'{full_revision}:research/chapter3_experiments/{name}'], cwd=REPO)
        (old_folder/name).write_bytes(data)
        records[name] = sha(data)
    coefficients = load_module('_construction_reference_coefficients', old_folder/'milp_coefficients.py')
    current = sys.modules.get('milp_coefficients')
    try:
        sys.modules['milp_coefficients'] = coefficients
        old = load_module('_construction_reference_milp', old_folder/'milp.py')
    finally:
        if current is None:
            sys.modules.pop('milp_coefficients', None)
        else:
            sys.modules['milp_coefficients'] = current
    return old, {'revision': full_revision, 'sha256': records}


def source_snapshot(folder):
    paths = sorted(HERE.glob('*.py'))+[HERE/'solve_model.m', HERE/'config_v01.json',
        REPO/'research/v1_evaluator/interval.py']
    records = {}
    for path in paths:
        relative = path.relative_to(REPO)
        target = folder/'source_snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        target.write_bytes(data)
        records[str(relative).replace('\\', '/')] = sha(data)
    return records


def numerical_row(row):
    """Normalize only certificate text spelling, not matrix coefficients."""
    normalized = dict(row)
    normalized['rounding_allowance'] = F(normalized['rounding_allowance'])
    normalized['rhs_interval'] = tuple(map(F, normalized['rhs_interval']))
    if 'big_M' in normalized:
        normalized['big_M'] = F(normalized['big_M'])
    return normalized


def row_digest(rows):
    data = json.dumps([numerical_row(row) for row in rows], sort_keys=True,
                      separators=(',', ':'), default=str).encode('utf-8')
    return sha(data)


def compare_rows(old, new):
    equal(len(old.rows), len(new.rows), 'row count')
    for index, (a, b) in enumerate(zip(old.rows, new.rows)):
        equal(numerical_row(a), numerical_row(b), 'row '+str(index))
        equal(a, b, 'raw row certificate '+str(index))
    if hasattr(new, 'row_nonzeros'):
        equal(new.row_nonzeros, sum(len(row['coef']) for row in new.rows), 'incremental nnz')


def compare_sparse(old, new):
    a, b = old.as_solver_dict(), new.as_solver_dict()
    for key in ('c', 'b', 'beq', 'lb', 'ub', 'intcon'):
        require(np.array_equal(a[key], b[key]), 'solver array '+key)
        if a[key].dtype.kind == 'f':
            require(np.array_equal(a[key].view(np.uint64), b[key].view(np.uint64)),
                    'solver float bit pattern '+key)
    for key in ('A', 'Aeq'):
        left, right = a[key], b[key]
        equal(left.shape, right.shape, key+' shape')
        for attribute in ('indptr', 'indices', 'data'):
            require(np.array_equal(getattr(left, attribute), getattr(right, attribute)),
                    key+'.'+attribute)


def compare_models(old, new, check, prefix):
    check(prefix+'/complete_options', lambda: equal(old.options, new.options))
    check(prefix+'/variables_bounds_integrality_objective', lambda: equal(
        (old.names, old.lb, old.ub, old.bounds, old.integer, old.c, old.option_vars, old.shared),
        (new.names, new.lb, new.ub, new.bounds, new.integer, new.c, new.option_vars, new.shared)))
    check(prefix+'/event_control_metadata', lambda: equal(old.scenes, new.scenes))
    check(prefix+'/all_rows_coefficients_enclosures_and_bigM', lambda: compare_rows(old, new))
    check(prefix+'/exported_sparse_matrix', lambda: compare_sparse(old, new))
    check(prefix+'/independent_model_budget_and_cache', lambda: require(
        old.budget is not new.budget and old.coefficients is not new.coefficients and
        old.coefficients.cache is not new.coefficients.cache, 'shared budget or coefficient cache'))


def boundary_fixture(source):
    instance, starts = deepcopy(source)
    instance['id'] = 'fixture_construction_half_open_hold'
    sid = instance['scenarios'][0]['id']
    for stage in instance['scenarios'][0]['stage_instances']:
        starts[sid][stage['id']] = ['0', '10', '20', '40']
    return instance, starts


def primitive_checks(old_module, new_module, instance, check, records):
    def prepare(module):
        model = module.Model(instance, Budget(seconds=600))
        model.var('binary', integer=True)
        model.var('signed_temperature', -20, 40)
        model.var('fractional_bounds', F(-2, 3), F(7, 3))
        model.var('fixed_fraction', F(1, 3), F(1, 3))
        model.var('large_signed', -(2**54), 2**54)
        return model
    old, new = prepare(old_module), prepare(new_module)
    tests = [
        ('integer_binary', {0: 1}, 1, False),
        ('integer_cancelled_zero', {0: 0, 1: -1, 2: 2}, -1, False),
        ('integer_beyond_exact_double', {4: 2**54+1}, 2**54+3, False),
        ('integer_exact_binary64_boundary', {4: 2**53, 1: -(2**53)}, 2**53, False),
        ('integer_past_binary64_boundary', {4: 2**53+1, 1: -(2**53+1)}, 2**53+1, False),
        ('signed_zero_rhs_interval', {0: 1, 1: -1}, I('-0'), False),
        ('real_fraction_coefficients', {1: F(1, 3), 2: F(-2, 7), 3: F(5, 11)}, F(1, 9), False),
        ('finite_binary_fraction', {0: F(1, 8), 1: F(-3, 16)}, F(5, 32), False),
        ('temperature_interval', {1: I('-0.123456789', '0.234567891'),
                                  2: I.rational(F(1, 3))}, I('-2.01', '-1.99'), False),
        ('conditional_integer', {1: 1, 2: -2}, 3, True),
        ('conditional_fraction', {1: F(-3, 7), 2: F(2, 3), 3: F(1, 11)}, F(-1, 9), True),
        ('conditional_interval', {1: I('-0.01', '0.03'), 2: I.rational(F(-1, 3))}, I('0.99', '1.01'), True),
    ]
    for name, row, rhs, conditional in tests:
        for model in (old, new):
            if conditional:
                model.conditional_eq(row, rhs, 0, name)
            else:
                model.eq(row, rhs, name)
        check('primitives/'+name, lambda: compare_rows(old, new))
    for module, model in ((old_module, old), (new_module, new)):
        row = {1: 1}
        module._plus(row, 1, -1)
        module._plus(row, 2, F(1, 3))
        module._plus(row, 2, F(2, 3))
        module._plus(row, 3, I('-0.1', '0.1'))
        model.le(row, 1, 'mixed_accumulation')
    check('primitives/mixed_accumulation', lambda: compare_rows(old, new))
    check('primitives/exported_matrix', lambda: compare_sparse(old, new))
    records['primitive_rows'] = len(old.rows)
    records['primitive_digest'] = row_digest(old.rows)


def feedback_checks(old_module, new_module, config, source, check, records):
    instance, starts = deepcopy(source)
    instance['id'] = 'fixture_construction_feedback'
    scene = instance['scenarios'][0]
    scene['maximum_temperature_degC'][0] = '50'
    sid, stage = scene['id'], scene['stage_instances'][0]['id']
    starts[sid][stage] = ['0', '40']
    instance['fixture_scope'] = 'existing_correctness_threshold_fixture_not_research_input'
    old = old_module.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
    new = new_module.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
    bad = {'scenes': {sid: [{'stage_id': stage, 'unit': 'CPU1', 'opp': 'H', 'start_ms': '0'}]}}
    delayed = deepcopy(bad)
    delayed['scenes'][sid][0]['start_ms'] = '40'
    old_receipt = old_module.evaluate_model_candidate(old, bad, config['accuracy_targets'], Budget(seconds=60))
    new_receipt = new_module.evaluate_model_candidate(new, bad, config['accuracy_targets'], Budget(seconds=60))
    def physical_witnesses(receipt):
        # Independent checks have independent wall clocks. Their timestamps
        # are retained in receipts, but are not thermal model coefficients.
        return [{key: value for key, value in witness.items() if key != 'formed_at_elapsed_s'}
                for witness in receipt['violations']]
    check('feedback/independently_detected_same_violation', lambda: equal(
        (old_receipt['state'], physical_witnesses(old_receipt)),
        ('THERMAL_VIOLATION', physical_witnesses(new_receipt))))
    check('feedback/new_detected_violation', lambda: equal(new_receipt['state'], 'THERMAL_VIOLATION'))
    old_safe = old_module.evaluate_model_candidate(old, delayed, config['accuracy_targets'], Budget(seconds=60))
    new_safe = new_module.evaluate_model_candidate(new, delayed, config['accuracy_targets'], Budget(seconds=60))
    check('feedback/delayed_same_configuration_safe', lambda: equal((old_safe['state'], new_safe['state']), ('SAFE', 'SAFE')))
    for index in range(3):
        left = old_module.add_thermal_feedback(old, bad, old_receipt)
        right = new_module.add_thermal_feedback(new, bad, new_receipt)
        check(f'feedback/round_{index}/actions', lambda a=left, b=right: equal(a, b))
        compare_models(old, new, check, f'feedback/round_{index}')
    for module, model in ((old_module, old), (new_module, new)):
        vector = module.lift_candidate(model, delayed)
        check('feedback/'+module.__name__+'/safe_not_excluded', lambda m=model, v=vector: require(
            max(exact_row_residuals(m, v), default=F(0)) < F('0.00000002'), 'safe delayed candidate removed'))
    check('feedback/logs_and_coverage_identity', lambda: equal(
        (old.feedback_log, old.feedback_identities, old.excluded_schedules),
        (new.feedback_log, new.feedback_identities, new.excluded_schedules)))
    records['feedback'] = {'old': old.summary(), 'new': new.summary(), 'rows_digest': row_digest(new.rows),
        'unsafe': bad, 'safe_delayed': delayed, 'original_research_parameters_changed': False}
    records['feedback']['independent_receipts'] = {
        'old_unsafe': old_receipt, 'new_unsafe': new_receipt,
        'old_safe': old_safe, 'new_safe': new_safe}


def observation_checks(old_module, new_module, config, source, check):
    for module in (old_module, new_module):
        instance, starts = source
        budget = Budget(seconds=0)
        def expired():
            try:
                module.build_model(instance, config, starts=starts, budget=budget)
            except Exhausted:
                return
            raise AssertionError('expired construction returned model')
        check('budget/'+module.__name__+'/preexpired', expired)
        calls = []
        observed = module.build_model(instance, config, starts=starts, include_physics=False,
            budget=Budget(seconds=600), progress=lambda phase, model, detail: calls.append((phase, len(model.rows))))
        plain = module.build_model(instance, config, starts=starts, include_physics=False, budget=Budget(seconds=600))
        check('observation/'+module.__name__+'/read_only', lambda a=observed, b=plain: compare_rows(a, b))
        check('observation/'+module.__name__+'/reports_complete', lambda: require(
            any(phase == 'complete' for phase, _ in calls), 'no completion report'))
        def interrupted(_stage, model, _detail):
            if len(model.rows) >= 20:
                raise Exhausted('fixture interruption')
        def no_partial_model():
            try:
                module.build_model(instance, config, starts=starts, include_physics=False,
                    budget=Budget(seconds=600), progress=interrupted)
            except Exhausted:
                return
            raise AssertionError('interrupted construction returned partial model')
        check('budget/'+module.__name__+'/no_partial_ready_model', no_partial_model)


def thermal_optimization_checks(old_module, new_module, instance, check):
    old_exp = old_module.Coefficients.get.__globals__['exponential']
    new_globals = new_module.Coefficients.get.__globals__
    new_exp = new_globals['exponential']
    matrices = [[[F(0)]], [[F(-3), F(1)], [F(2), F(-4)]]]
    def data(matrix):
        return [[v.data() for v in row] for row in matrix]
    for i, matrix in enumerate(matrices):
        for duration in map(F, ('0', '1/1000', '1/4', '4')):
            check(f'kernel/matrix_{i}/duration_{duration}', lambda m=matrix, t=duration:
                  equal(data(old_exp(m, t)), data(new_exp(m, t))))
    state = tuple(next(iter(d['opps'])) for d in instance['platform']['domains'].values())
    old = old_module.Coefficients(instance['platform'], Budget(seconds=600))
    new = new_module.Coefficients(instance['platform'], Budget(seconds=600))
    for duration in map(F, ('0', '1/3000', '1/1000', '2/5', '1/1000')):
        a, b = old.get(state, duration), new.get(state, duration)
        check('kernel/state_duration_'+str(duration), lambda a=a, b=b: equal(
            (data(a['temperature']), [v.data() for v in a['energy']]),
            (data(b['temperature']), [v.data() for v in b['energy']])))
    check('kernel/one_state_many_durations', lambda: equal((len(new.kernel_cache), new.calls), (1, 4)))
    other = new_module.Coefficients(instance['platform'], Budget(seconds=600))
    check('kernel/no_cross_model_cache', lambda: require(not other.kernel_cache and
          other.kernel_cache is not new.kernel_cache, 'shared kernel cache'))

    class StopAfter:
        def __init__(self, allowed): self.remaining = allowed
        def check(self):
            self.remaining -= 1
            if self.remaining < 0: raise Exhausted('injected kernel interruption')
    interrupted = new_module.Coefficients(instance['platform'], StopAfter(4))
    def preparation_atomic():
        try: interrupted.get(state, F('1/1000'))
        except Exhausted: pass
        else: raise AssertionError('kernel preparation did not stop')
        equal((interrupted.kernel_cache, interrupted.cache, interrupted.calls), ({}, {}, 0))
    check('kernel/interrupted_preparation_not_published', preparation_atomic)
    saved_kernel = new.kernel_cache[state]
    new.budget = StopAfter(1)
    def evaluation_atomic():
        try: new.get(state, F('1/1700'))
        except Exhausted: pass
        else: raise AssertionError('kernel evaluation did not stop')
        require(new.kernel_cache[state] is saved_kernel, 'lost complete kernel')
        require((state, F('1/1700')) not in new.cache, 'published partial coefficient')
    check('kernel/interrupted_evaluation_not_published', evaluation_atomic)

    old_m = old_module.Model(instance, Budget(seconds=600))
    new_m = new_module.Model(instance, Budget(seconds=600))
    for model in (old_m, new_m):
        model.var('signed', F(-2, 3), F(5, 3))
    limit = new_module._EXPORT_CACHE_LIMIT
    def cache_eviction():
        try:
            new_module._EXPORT_CACHE_LIMIT = 4  # fixture-only eviction pressure
            for q in [F(i, 37) for i in range(1, 12)]+[F(1, 37)]:
                for model in (old_m, new_m): model.le({0: q}, F(2, 7), 'cache_probe')
            compare_rows(old_m, new_m)
            require(len(new_m._coefficient_exports) <= 4, 'cache bound exceeded')
        finally:
            new_module._EXPORT_CACHE_LIMIT = limit
    check('row_cache/eviction_preserves_raw_rows', cache_eviction)
    check('row_cache/no_cross_model_sharing', lambda: require(
        new_module.Model(instance, Budget())._coefficient_exports is not new_m._coefficient_exports,
        'shared conversion cache'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    folder = args.out.resolve()
    if folder.exists():
        raise SystemExit('Refusing to overwrite precheck output: '+str(folder))
    folder.mkdir(parents=True)
    started = time.monotonic()
    checks, records = [], {}
    def check(name, operation):
        stamp = time.monotonic()
        try:
            operation()
            entry = {'name': name, 'passed': True}
        except Exception as error:
            entry = {'name': name, 'passed': False, 'error': repr(error)}
        entry['elapsed_s'] = time.monotonic()-stamp
        checks.append(entry)
        if not entry['passed']:
            print('FAIL '+name+': '+entry['error'], flush=True)
    sources = source_snapshot(folder)
    old_module, reference = reference_sources(folder)
    import milp as new_module
    config = load_config()
    check('input/frozen_config_sha256', lambda: equal(sha((HERE/'config_v01.json').read_bytes()), CONFIG_SHA))
    fixture_map = fixtures(config)
    try:
        all_assignment_count = 0
        for name, (instance, starts) in fixture_map.items():
            fixture_record = {'assignments': 0, 'legal': 0, 'models': []}
            save(folder/(name+'_input.json'), {'instance': instance, 'starts': starts})
            for physical in (False, True):
                label = name+('/physics' if physical else '/scheduling')
                print('BUILD '+label, flush=True)
                old_start = time.monotonic()
                old = old_module.build_model(instance, config, starts=starts, include_physics=physical, budget=Budget(seconds=600))
                old_elapsed = time.monotonic()-old_start
                new_start = time.monotonic()
                new = new_module.build_model(instance, config, starts=starts, include_physics=physical, budget=Budget(seconds=600))
                new_elapsed = time.monotonic()-new_start
                compare_models(old, new, check, label)
                fixture_record['models'].append({'physics': physical, 'old': old.summary(), 'new': new.summary(),
                    'old_elapsed_s': old_elapsed, 'new_elapsed_s': new_elapsed,
                    'rows_digest': row_digest(new.rows), 'timing_scope': 'single correctness run, not performance evidence'})
                if not physical:
                    mismatch = []
                    for candidate in independent_assignments(instance, starts):
                        valid = independent_check(instance, candidate)['valid']
                        fixture_record['assignments'] += 1
                        fixture_record['legal'] += int(valid)
                        left = canonical_structure_vector(old, candidate)
                        right = canonical_structure_vector(new, candidate)
                        equal(left, right, label+' lifted structure')
                        old_valid = all(v <= 0 for v in exact_row_residuals(old, left))
                        new_valid = all(v <= 0 for v in exact_row_residuals(new, right))
                        if (old_valid, new_valid) != (valid, valid):
                            mismatch.append({'candidate': candidate, 'oracle': valid, 'old': old_valid, 'new': new_valid})
                    check(label+'/complete_cartesian_projection', lambda: equal(mismatch, []))
            all_assignment_count += fixture_record['assignments']
            records[name] = fixture_record
        check('coverage/original_five_domains_438_assignments', lambda: equal(all_assignment_count, 438))
        instance, starts = boundary_fixture(fixture_map['parallel_cpu'])
        old = old_module.build_model(instance, config, starts=starts, include_physics=False, budget=Budget(seconds=600))
        new = new_module.build_model(instance, config, starts=starts, include_physics=False, budget=Budget(seconds=600))
        compare_models(old, new, check, 'boundary/half_open_idle_hold')
        saw_empty = any(not active for scene in new.scenes.values() for active in scene['active'])
        check('boundary/empty_active_interval_present', lambda: require(saw_empty, 'no idle interval'))
        def half_open_check():
            simultaneous = False
            for meta in new.scenes.values():
                for index, when in enumerate(meta['events'][:-1]):
                    ended = {y for option, y in meta['options'] if F(option['end_ms'])/1000 == when}
                    started_here = {y for option, y in meta['options'] if F(option['start_ms'])/1000 == when}
                    active = {y for _, y in meta['active'][index]}
                    require(not (ended & active), 'finished option remains active at half-open boundary')
                    require(started_here <= active, 'starting option missing from activity')
                    simultaneous |= bool(ended and started_here)
            require(simultaneous, 'fixture did not exercise simultaneous end/start')
        check('boundary/ends_removed_before_starts', half_open_check)
        for label, allowed in [('initial_idle', ['40']), ('no_option', [])]:
            instance, starts = deepcopy(fixture_map['one_stage_energy'])
            instance['id'] = 'fixture_construction_'+label
            sid = instance['scenarios'][0]['id']
            for stage_id in starts[sid]:
                starts[sid][stage_id] = allowed
            old = old_module.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
            new = new_module.build_model(instance, config, starts=starts, budget=Budget(seconds=600))
            compare_models(old, new, check, 'boundary/'+label)
            if label == 'no_option':
                check('boundary/no_option_produces_impossible_unique_row', lambda: require(any(
                    not row['coef'] and row['rhs'] < 0 for row in new.rows), 'empty stage did not produce contradiction'))
        primitive_checks(old_module, new_module, fixture_map['one_stage_energy'][0], check, records)
        feedback_checks(old_module, new_module, config, fixture_map['one_stage_energy'], check, records)
        observation_checks(old_module, new_module, config, fixture_map['one_stage_energy'], check)
        thermal_optimization_checks(old_module, new_module, fixture_map['one_stage_energy'][0], check)
    except Exception as error:
        checks.append({'name': 'suite_execution', 'passed': False, 'error': repr(error)})
    after = {relative: sha((REPO/relative).read_bytes()) for relative in sources}
    check('source/stable_during_precheck', lambda: equal(sources, after))
    result = {'status': 'PASS' if all(c['passed'] for c in checks) else 'FAIL',
        'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'checks': checks,
        'wall_s': time.monotonic()-started, 'python': sys.version, 'platform': platform.platform(),
        'reference': reference, 'source_sha256': sources, 'source_sha256_after': after,
        'records': records, 'scope': 'small-domain construction equivalence only; no solver or original-scale build',
        'formal_comparisons_run': False, 'formal_experiments_ready': False}
    save(folder/'checks.json', result)
    print(f"{result['status']} {result['passed']}/{result['total']} checks", flush=True)
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
