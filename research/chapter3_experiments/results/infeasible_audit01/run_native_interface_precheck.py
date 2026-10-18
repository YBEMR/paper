"""One two-variable native interface check, never a research-method call."""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

import numpy as np
from scipy import sparse
from matlab_bridge import MatlabSession
from run_formal_comparison import signature, source_paths
from timing import MethodBudget


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def run(out):
    budget = MethodBudget(60)
    out.mkdir(parents=True, exist_ok=False)
    before = signature()
    save(out/'predeclaration.json', {
        'scope': 'one_two_variable_native_interface_correctness_check',
        'native_solver_calls_limit': 1, 'budget_seconds': 60,
        'research_problem_or_Q1_run': False, 'thermal_evaluation': False,
        'retry_or_budget_extension': False,
        'source_sha256': before,
    })
    for key, source in source_paths().items():
        target = out/'source_snapshot'/key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    fixture = {
        'c': np.array([2., 1.]), 'A': sparse.csc_matrix([[1., 1.]]),
        'b': np.array([1.]), 'Aeq': sparse.csc_matrix([[1., 1.]]),
        'beq': np.array([1.]), 'lb': np.zeros(2), 'ub': np.ones(2),
        'intcon': np.array([0, 1]),
    }
    try:
        with MatlabSession(out/'matlab', total_budget_s=60, budget=budget) as session:
            returned = session.solve(fixture, budget=budget, x0=[1., 0.])
            environment = session.environment
        save(out/'returned.json', returned)
        options = returned.get('options', {})
        checks = {
            'actual_R2023b': environment.get('release') == '2023b',
            'timely_numerical_candidate': returned.get('accepted_for_evaluation') is True,
            'native_solution': returned.get('exitflag') == 1 and
                np.allclose(returned.get('x', []), [0., 1.], rtol=0, atol=1e-9),
            'objective': returned.get('fval') == 1.,
            'explicit_current_x0_received': (returned.get('initial_point') or {}).get('provided') is True,
            'LP_preprocess_none_explicitly_archived': options.get('LPPreprocess') == 'none',
            'integer_preprocess_none_retained': options.get('IntegerPreprocess') == 'none',
            'constraint_tolerance_unchanged': options.get('ConstraintTolerance') == 1e-9,
            'integer_tolerance_unchanged': options.get('IntegerTolerance') == 1e-6,
            'absolute_gap_unchanged': options.get('AbsoluteGapTolerance') == 0,
            'relative_gap_unchanged': options.get('RelativeGapTolerance') == 0,
            'ordinary_success_not_conflict': 'numerical_consistency' not in returned,
            'source_unchanged': before == signature(),
        }
        record = {'passed': all(checks.values()), 'count': len(checks), 'checks': checks,
                  'native_solver_calls': 1, 'research_calls': 0, 'thermal_evaluations': 0,
                  'budget': budget.summary(), 'source_sha256': before}
    except Exception as error:
        record = {'passed': False, 'error': f'{type(error).__name__}: {error}',
                  'no_retry': True, 'source_sha256': before}
    save(out/'checks.json', record)
    print(json.dumps({key: record.get(key) for key in ('passed', 'count', 'error')}), flush=True)
    return record['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
