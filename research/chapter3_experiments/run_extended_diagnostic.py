"""One 900 s original-scale diagnostic; no retry or automatic extension.

The historical input file's formal-comparison budget stays unchanged. This
explicit diagnostic override starts before input read, includes all stages,
and ends at one absolute deadline. No model or solver-option override.
"""
import argparse
import hashlib
import json
from pathlib import Path
from method_runner import HERE, SOURCES, run_milp_method


def source_hashes():
    paths = {name: HERE/name for name in SOURCES}
    paths['interval.py'] = HERE.parent/'v1_evaluator/interval.py'
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--precheck', required=True)
    args = parser.parse_args()
    checks = json.loads(Path(args.precheck).read_text(encoding='utf-8'))
    if not checks.get('all_passed') or checks.get('source_hashes') != source_hashes():
        raise ValueError('Passing precheck with matching sources is required')
    # Claim this protocol once before any original-scale invocation. A crash
    # retains the claim and requires discussion, never an automatic retry.
    claim = Path(args.precheck).parent/'original_run_claim.json'
    with claim.open('x', encoding='utf-8') as f:
        json.dump({'problem_id': 'base__R1', 'seconds': 900, 'out': str(Path(args.out).resolve()),
                   'formal_comparison': False, 'retries': 0, 'source_hashes': source_hashes()}, f, indent=2)
    result = run_milp_method('base__R1', args.out, construct_only=False, diagnostic_seconds=900)
    print(json.dumps({k: result.get(k) for k in ('state', 'reason', 'integer_solver_entered',
          'safe_upper_bound_J', 'timing', 'diagnostic')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
