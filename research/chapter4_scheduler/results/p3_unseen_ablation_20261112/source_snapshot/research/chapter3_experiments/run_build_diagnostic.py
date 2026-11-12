"""One 60 s construction-only call on the unchanged original baseline R1.

No solver, formal comparison, alternative case, reduced option domain or
budget extension is exposed through this diagnostic command.
"""
import argparse
import json

from method_runner import run_milp_method


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True,
                        help='New output directory; existing results are never overwritten')
    args = parser.parse_args()
    result = run_milp_method('base__R1', args.out)
    print(json.dumps({key: result.get(key) for key in (
        'problem_id', 'state', 'reason', 'model_complete', 'matrix_complete',
        'solver_started', 'timing', 'construction')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
