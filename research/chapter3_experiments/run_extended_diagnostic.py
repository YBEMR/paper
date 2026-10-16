"""One 900 s original-scale diagnostic; no retry or automatic extension.

The historical input file's formal-comparison budget stays unchanged. This
explicit diagnostic override starts before input read, includes all stages,
and ends at one absolute deadline. Only an explicit, prechecked equivalent
auxiliary integrality variant is selectable; solver options remain unchanged.
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
    parser.add_argument('--relax-auxiliary-integrality', action='store_true')
    parser.add_argument('--auxiliary-precheck')
    args = parser.parse_args()
    checks = json.loads(Path(args.precheck).read_text(encoding='utf-8'))
    if not checks.get('all_passed') or checks.get('source_hashes') != source_hashes():
        raise ValueError('Passing precheck with matching sources is required')
    formulation = dict(fix_late_options=True, aggregate_opp_locks=True,
                       relax_auxiliary_integrality=args.relax_auxiliary_integrality)
    if checks.get('formulation') != formulation:
        raise ValueError('Precheck must cover the exact requested formulation')
    if checks.get('precheck_source_sha256') != hashlib.sha256((HERE/'precheck_diagnostic.py').read_bytes()).hexdigest():
        raise ValueError('Live precheck script changed')
    auxiliary = None
    if args.relax_auxiliary_integrality:
        if not args.auxiliary_precheck:
            raise ValueError('Auxiliary numerical acceptance precheck is required')
        auxiliary = json.loads(Path(args.auxiliary_precheck).read_text(encoding='utf-8'))
        if not auxiliary.get('all_passed') or auxiliary.get('source_hashes') != source_hashes():
            raise ValueError('Auxiliary precheck must pass and match sources')
        if auxiliary.get('precheck_source_sha256') != hashlib.sha256((HERE/'run_auxiliary_precheck.py').read_bytes()).hexdigest():
            raise ValueError('Auxiliary precheck script changed')
        if auxiliary.get('formulation') != formulation:
            raise ValueError('Auxiliary precheck formulation mismatch')
    # Claim this protocol once before any original-scale invocation. A crash
    # retains the claim and requires discussion, never an automatic retry.
    claim = Path(args.precheck).parent/'original_run_claim.json'
    with claim.open('x', encoding='utf-8') as f:
        json.dump({'problem_id': 'base__R1', 'seconds': 900, 'out': str(Path(args.out).resolve()),
                   'formal_comparison': False, 'retries': 0, 'source_hashes': source_hashes(),
                   'formulation': formulation, 'auxiliary_precheck': args.auxiliary_precheck}, f, indent=2)
    result = run_milp_method('base__R1', args.out, construct_only=False, diagnostic_seconds=900,
                           relax_auxiliary_integrality=args.relax_auxiliary_integrality)
    print(json.dumps({k: result.get(k) for k in ('state', 'reason', 'integer_solver_entered',
          'safe_upper_bound_J', 'timing', 'diagnostic')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
