"""One 900 s original-scale diagnostic; no retry or automatic extension.

The historical input file's formal-comparison budget stays unchanged. This
explicit diagnostic override starts before input read, includes all stages,
and ends at one absolute deadline. Explicit prechecked auxiliary integrality
and valid energy-bound variants are selectable; solver options stay unchanged.
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


def validate_energy_precheck(path):
    """Reuse unchanged mathematical sources; live precheck covers wiring."""
    path = Path(path)
    record = json.loads(path.read_text(encoding='utf-8'))
    if (record.get('status') != 'PASS' or not record.get('checks') or
            record.get('passed') != record.get('total') or
            len(record['checks']) != record.get('total') or
            record.get('matlab_small_domain_requested') is not True or
            not all(c.get('status') == 'PASS' for c in record['checks'])):
        raise ValueError('Passing energy lower-bound precheck is required')
    repo = HERE.parents[1]
    required = [HERE/name for name in ('config_v01.json', 'inputs.py', 'schedules.py',
        'thermal.py', 'milp.py', 'milp_coefficients.py', 'matlab_bridge.py', 'solve_model.m',
        'run_energy_bound_precheck.py', 'run_milp_precheck.py',
        'run_construction_precheck.py')]+[HERE.parent/'v1_evaluator/interval.py']
    checked = {}
    for source in required:
        key = source.relative_to(repo).as_posix()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if record.get('source_sha256', {}).get(key) != digest:
            raise ValueError('Energy precheck source mismatch: '+key)
        checked[key] = digest
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'passed': record['passed'], 'checked_sources': checked,
            'scope': 'unchanged mathematics/input/thermal acceptance; current wiring checked separately'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--precheck', required=True)
    parser.add_argument('--relax-auxiliary-integrality', action='store_true')
    parser.add_argument('--auxiliary-precheck')
    parser.add_argument('--strengthen-energy-lower-bounds', action='store_true')
    parser.add_argument('--energy-lower-bound-precheck')
    args = parser.parse_args()
    checks = json.loads(Path(args.precheck).read_text(encoding='utf-8'))
    if not checks.get('all_passed') or checks.get('source_hashes') != source_hashes():
        raise ValueError('Passing precheck with matching sources is required')
    formulation = dict(fix_late_options=True, aggregate_opp_locks=True,
                       relax_auxiliary_integrality=args.relax_auxiliary_integrality)
    if args.strengthen_energy_lower_bounds:
        formulation['energy_lower_bounds'] = True
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
    energy = None
    if args.strengthen_energy_lower_bounds:
        if not args.energy_lower_bound_precheck:
            raise ValueError('Energy lower-bound precheck is required')
        energy = validate_energy_precheck(args.energy_lower_bound_precheck)
    # Claim this protocol once before any original-scale invocation. A crash
    # retains the claim and requires discussion, never an automatic retry.
    claim = Path(args.precheck).parent/'original_run_claim.json'
    with claim.open('x', encoding='utf-8') as f:
        json.dump({'problem_id': 'base__R1', 'seconds': 900, 'out': str(Path(args.out).resolve()),
                   'formal_comparison': False, 'retries': 0, 'source_hashes': source_hashes(),
                   'formulation': formulation, 'auxiliary_precheck': args.auxiliary_precheck,
                   'energy_lower_bound_precheck': energy}, f, indent=2)
    result = run_milp_method('base__R1', args.out, construct_only=False, diagnostic_seconds=900,
                           relax_auxiliary_integrality=args.relax_auxiliary_integrality,
                           strengthen_energy_lower_bounds=args.strengthen_energy_lower_bounds)
    print(json.dumps({k: result.get(k) for k in ('state', 'reason', 'integer_solver_entered',
          'safe_upper_bound_J', 'timing', 'diagnostic')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
