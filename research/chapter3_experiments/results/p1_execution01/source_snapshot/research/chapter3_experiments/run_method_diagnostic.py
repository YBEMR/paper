"""One original base__R1 full-method diagnostic under one 60 s deadline.

No reduced domain, changed parameters, prior session, candidate or cache can
be supplied. Construction, fresh MATLAB startup, transport, solving, feedback
and continuous evaluation all use the existing method lifecycle. Not a formal
comparison. This entry neither retries a timeout nor changes the budget.
"""
import argparse
import json
from method_runner import run_milp_method


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New invocation directory')
    args = parser.parse_args()
    result = run_milp_method('base__R1', args.out, construct_only=False)
    print(json.dumps({key: result.get(key) for key in (
        'problem_id', 'state', 'reason', 'stop_stage', 'model_complete', 'matrix_complete',
        'matlab_worker_ready', 'solver_request_attempts', 'integer_solver_entered',
        'safe_upper_bound_J', 'timing')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
