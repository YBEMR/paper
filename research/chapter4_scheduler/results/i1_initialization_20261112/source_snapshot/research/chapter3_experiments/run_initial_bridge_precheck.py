"""Optional x0 transport checks; small-domain tests, never an original-case run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import sparse

import matlab_bridge as bridge
from timing import MethodBudget

HERE = Path(__file__).resolve().parent


def require(value, message='assertion failed'):
    if not value:
        raise AssertionError(message)


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def fixture():
    return {'c': np.array([2., 1.]), 'A': sparse.csc_matrix([[1., 1.]]),
            'b': np.array([1.]), 'Aeq': sparse.csc_matrix([[1., 1.]]),
            'beq': np.array([1.]), 'lb': np.zeros(2), 'ub': np.ones(2),
            'intcon': np.array([0, 1])}


def reject(model, x0):
    try:
        bridge._prepare(model, x0=x0)
    except bridge.InitialPointRejected as exc:
        require(not exc.diagnostics['accepted_numerically'])
        require(bool(exc.diagnostics['reasons']))
        json.dumps(exc.diagnostics, allow_nan=False)
        return exc.diagnostics
    raise AssertionError('invalid initial point accepted')


class Clock:
    def __init__(self): self.now = 100.
    def __call__(self): return self.now


def fake_session(directory, clock):
    directory.mkdir()
    session = object.__new__(bridge.MatlabSession)
    session.closed = False; session.request_blocked = False
    session.clock = clock; session.started = clock(); session.deadline = clock() + 10
    session.budget = None; session.counter = 0; session.workdir = directory
    session.metadata = {}; session.proc = None
    return session


def run(out, with_matlab=False):
    out.mkdir(parents=True, exist_ok=False)
    records = []; details = {}
    source_files = [Path(__file__), HERE/'matlab_bridge.py', HERE/'solve_model.m',
                    HERE/'timing.py']
    initial_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    snapshot = out/'source_snapshot'; snapshot.mkdir()
    for p in source_files:
        (snapshot/p.name).write_bytes(p.read_bytes())

    def check(name, function):
        try:
            value = function()
            records.append({'name': name, 'passed': True})
            if value is not None: details[name] = value
        except Exception as exc:
            records.append({'name': name, 'passed': False,
                            'error': f'{type(exc).__name__}: {exc}'})
        save(out/'checks_in_progress.json', {'checks': records, 'details': details})

    def default_unchanged():
        source = HERE/'results/base_long_diagnostic04/source_snapshot/matlab_bridge.py'
        spec = importlib.util.spec_from_file_location('bridge_before_x0', source)
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        expected = old._prepare(fixture()); actual = bridge._prepare(fixture())
        require(actual.keys() == expected.keys())
        for key in expected:
            if sparse.issparse(expected[key]):
                require(actual[key].shape == expected[key].shape and
                        (actual[key] != expected[key]).nnz == 0, key)
            else:
                require(np.array_equal(actual[key], expected[key]), key)
        require('x0' not in actual and 'x0_validation' not in actual)
    check('no_x0_payload_exactly_matches_preserved_bridge', default_unchanged)

    def accepted_point():
        point = np.array([1., 0.]); original = point.copy()
        result = bridge._prepare(fixture(), x0=point)
        require(np.array_equal(result['x0'], point) and np.array_equal(point, original))
        info = result['x0_validation']
        require(info['accepted_numerically'] and info['initial_objective'] == 2.)
        require(not info['thermal_safe_claim'] and not info['independent_certificate'])
        return info
    check('valid_point_passed_without_rounding_and_without_safe_claim', accepted_point)

    failures = {
        'wrong_length': ([1., 0., 0.], fixture()),
        'matrix_shape': (np.zeros((2, 2)), fixture()),
        'nan': ([np.nan, 0.], fixture()),
        'infinity': ([np.inf, 0.], fixture()),
        'nonnumeric': (['bad', 0.], fixture()),
        'complex': ([1.+1j, 0.], fixture()),
        'lower_bound': ([-2e-9, 1. + 2e-9], fixture()),
        'upper_bound': ([1. + 2e-9, -2e-9], fixture()),
        'integer': ([.4, .6], fixture()),
    }
    inequality = fixture(); inequality['A'] = sparse.csc_matrix([[1., 0.]])
    inequality['b'] = np.array([.5])
    failures['inequality'] = ([1., 0.], inequality)
    equality = fixture(); equality['beq'] = np.array([.75])
    failures['equality'] = ([1., 0.], equality)
    overflow = {'c': [1e308], 'lb': [0.], 'ub': [2.], 'intcon': [0]}
    failures['objective_overflow'] = ([2.], overflow)
    for name, (point, model) in failures.items():
        check('reject_' + name, lambda point=point, model=model: reject(model, point))

    def near_integer():
        model = fixture(); model['Aeq'] = sparse.csc_matrix((0, 2)); model['beq'] = []
        point = np.array([1.-5e-7, 5e-7])
        result = bridge._prepare(model, x0=point)
        require(np.array_equal(result['x0'], point))
        require(result['x0_validation']['integer_violation'] <= 1e-6)
    check('integer_tolerance_does_not_round_point', near_integer)

    def strict_constraint():
        model = fixture(); model['intcon'] = []
        model['Aeq'] = sparse.csc_matrix((0, 2)); model['beq'] = []
        model['ub'] = [2., 2.]
        bridge._prepare(model, x0=[1.+.9e-9, 0.])
        reject(model, [1.+1.1e-9, 0.])
        reject(model, [1.+2e-8, 0.])
    check('constraint_tolerance_is_1e_9_not_old_lift_2e_8', strict_constraint)

    def rejected_before_publication():
        session = fake_session(out/'rejection_transport', Clock())
        try:
            session.solve(fixture(), x0=[.4, .6])
        except bridge.InitialPointRejected:
            pass
        else:
            raise AssertionError('bridge did not reject x0')
        require((session.workdir/'request_000001.initial.json').exists())
        require(not list(session.workdir.glob('*.mat')))
        require(not list(session.workdir.glob('*.request.json')))
    check('rejection_is_archived_before_mat_or_solver_submission', rejected_before_publication)

    def expiry_during_validation():
        clock = Clock(); session = fake_session(out/'budget_transport', clock)
        original = bridge._check_initial_point
        def slow(payload, point):
            value = original(payload, point); clock.now += 10
            return value
        with patch.object(bridge, '_check_initial_point', side_effect=slow):
            result = session.solve(fixture(), x0=[1., 0.])
        require(not result['budget_valid'] and not result['accepted_for_evaluation'])
        require(not list(session.workdir.glob('*.mat')))
        require(not list(session.workdir.glob('*.request.json')))
        return result
    check('validation_and_archive_cost_do_not_extend_absolute_deadline', expiry_during_validation)

    if with_matlab and all(r['passed'] for r in records):
        def native_transport():
            budget = MethodBudget(60)
            with bridge.MatlabSession(out/'matlab_transport', total_budget_s=60,
                                      budget=budget) as session:
                no_point = session.solve(fixture(), budget=budget)
                with_point = session.solve(fixture(), budget=budget, x0=[1., 0.])
            require(no_point['accepted_for_evaluation'] and with_point['accepted_for_evaluation'])
            require(no_point['status'] == with_point['status'] == 'SOLVED')
            require(not no_point['initial_point']['provided'])
            require(with_point['initial_point']['provided'])
            require(with_point['initial_point']['initial_objective'] == 2.)
            for result in (no_point, with_point):
                require(np.allclose(result['x'], [0., 1.], rtol=0, atol=1e-9))
                require(abs(result['fval'] - 1.) <= 1e-9)
                for option, value in {'ConstraintTolerance':1e-9, 'IntegerTolerance':1e-6,
                                      'AbsoluteGapTolerance':0., 'RelativeGapTolerance':0.}.items():
                    require(result['options'][option] == value, option)
            return {'without_x0': no_point, 'with_x0': with_point,
                    'budget': budget.summary(), 'scope':'small solver transport, no thermal claim'}
        check('native_matlab_optional_x0_and_original_no_x0_same_budget', native_transport)

    check('sources_unchanged_during_precheck', lambda: require(initial_hashes ==
          {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}))
    report = {'passed': all(r['passed'] for r in records), 'checks': records,
              'count':len(records), 'details':details, 'source_sha256':initial_hashes,
              'original_benchmark_built_or_solved':False, 'formal_comparison':False}
    save(out/'checks.json', report)
    print(json.dumps({'passed':report['passed'], 'count':len(records), 'out':str(out)}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--with-matlab', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out, args.with_matlab)['passed'] else 1)
