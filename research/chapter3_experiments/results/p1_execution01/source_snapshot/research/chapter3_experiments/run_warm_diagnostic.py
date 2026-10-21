"""One 900 s original-scale call: rebuild a SAFE seed and then optimize.

No historical vector/candidate is an input. All initialization, MATLAB startup,
export, solving, callback checks and feedback share the original method clock.
"""
from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
import shutil
import time

from initial_point import solve_with_initial_witness
from inputs import build_instance, load_config
from matlab_bridge import MatlabSession
from method_runner import execute_milp
from milp import build_model
import run_initial_witness_diagnostic as seed

HERE, REPO = seed.HERE, seed.REPO
FLAGS = dict(seed.FLAGS)
LIMIT_SECONDS = 900


def source_paths():
    paths = dict(seed.source_paths())
    for name in ['method_runner.py', 'diagnostic_search.py', 'run_milp_precheck.py',
                 'run_warm_diagnostic.py', 'precheck_warm_diagnostic.py']:
        path = HERE/name
        paths[path.relative_to(REPO).as_posix()] = path
    return paths


def source_hashes():
    return {name: seed.digest(path) for name, path in source_paths().items()}


def validate_precheck(path):
    path = Path(path)
    record = json.loads(path.read_text(encoding='utf-8-sig'))
    checks = record.get('checks', [])
    if (record.get('passed') is not True or not checks
            or record.get('count') != len(checks)
            or not all(row.get('passed') is True for row in checks)
            or record.get('seconds') != LIMIT_SECONDS or record.get('flags') != FLAGS
            or record.get('original_benchmark_built_or_solved') is not False
            or record.get('native_small_domain_passed') is not True):
        raise ValueError('Passing complete warm-start diagnostic precheck is required')
    if record.get('source_sha256') != source_hashes():
        raise ValueError('Warm diagnostic precheck source mismatch')
    return {'path': str(path.resolve()), 'sha256': seed.digest(path), 'count': len(checks)}


def claim_original_run(precheck, out):
    claim = Path(precheck).parent/'original_warm_run_claim.json'
    with claim.open('x', encoding='utf-8') as stream:
        json.dump({'problem_id': 'base__R1', 'seconds': LIMIT_SECONDS,
                   'out': str(Path(out).resolve()), 'flags': FLAGS,
                   'source_sha256': source_hashes(), 'retries': 0,
                   'seed_attempts': 3, 'historical_candidate_input': False,
                   'formal_comparison': False}, stream, indent=2)
    return claim


def execute_warm(input_loader, out, *, seconds=LIMIT_SECONDS,
                 clock=time.monotonic, model_builder=build_model,
                 session_factory=MatlabSession, solver=solve_with_initial_witness):
    """Injected dependencies support small correctness fixtures, never research choices."""
    out = Path(out)

    def solve(model, session, accuracy, budget):
        def checkpoint(receipt):
            # Observation only. No vector/candidate is read back for search.
            seed.save(out/'initial_receipt_checkpoint.json', {
                'initialisation': receipt, 'publication_started_at_s': budget.elapsed,
                'scope': 'formed evidence only; checkpoint cost inside the method budget'})
        return solver(model, session, accuracy, budget, checkpoint=checkpoint)

    return execute_milp(input_loader, out, seconds=seconds, construct_only=False,
                        clock=clock, model_builder=partial(model_builder, **FLAGS),
                        session_factory=session_factory, solve=solve)


def run_original(out, core_precheck, precheck):
    prerequisites = {'core': seed.validate_core_precheck(core_precheck),
                     'entry': validate_precheck(precheck),
                     'support': seed.validate_support_prechecks()}
    out = Path(out)
    if out.exists():
        raise FileExistsError('Invocation directory already exists: '+str(out))
    before = source_hashes()
    claim = claim_original_run(precheck, out)

    def loader(budget):
        config = load_config()
        return config, build_instance(config, 'base__R1', budget=budget)

    result = execute_warm(loader, out)
    archive_start = time.monotonic()
    seed.save(out/'prerequisites.json', prerequisites)
    after = source_hashes()
    seed.save(out/'source_integrity.json', {'before': before, 'after': after,
        'unchanged': before == after, 'original_claim': str(claim.resolve())})
    snapshot = out/'source_snapshot'
    for name, path in source_paths().items():
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    seed.save(out/'source_archive_timing.json', {'seconds': time.monotonic()-archive_start,
        'scope': 'archive only; no new solve, decode or thermal evidence'})
    print(json.dumps({key: result.get(key) for key in ['state', 'reason',
        'initial_safe_upper_bound_J', 'milp_safe_upper_bound_J', 'safe_upper_bound_J',
        'safe_solution_source', 'milp_improved_initial_upper_bound',
        'strict_energy_improvement_certified', 'timing']}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--core-precheck', type=Path, required=True)
    parser.add_argument('--precheck', type=Path, required=True)
    args = parser.parse_args()
    run_original(args.out, args.core_precheck, args.precheck)
