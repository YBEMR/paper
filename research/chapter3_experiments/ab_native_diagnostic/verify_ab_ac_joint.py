"""Check one merged archived schedule with the original full-input evaluator."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
import time


AB, AC = 'AB_offset_0ms', 'AC_offset_0ms'
SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
ROOT = Path(__file__).resolve().parent
LIMIT_S = 60


def read_bound(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f'Input drift: {path.name}')
    return json.loads(raw)


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def verify(frozen, output, started):
    paths = [frozen, frozen/'baseline/research/chapter3_experiments', frozen/'baseline']
    sys.path[:0] = list(map(str, paths))
    import psutil
    from native_entry_prepared import load_frozen_inputs
    from scene_adapter import canonical_hash
    from shared_mapping_adapter import ParentOriginClock
    from thermal import evaluate_candidate
    from timing import MethodBudget

    budget = MethodBudget(LIMIT_S, clock=ParentOriginClock(time.monotonic, started))
    output.mkdir()
    summary = {'state': 'INCOMPLETE', 'joint_evaluations': 0, 'solver_calls': 0,
               'schedule_search_calls': 0, 'formal_experiment_result': False}
    try:
        available = psutil.virtual_memory().available
        if available < 2**31:
            raise MemoryError('Less than 2 GiB memory available before evaluation')
        summary['available_memory_start_bytes'] = available
        with budget.phase('verify_frozen_sources_and_assemble'):
            ab_path = ROOT/'fullpath_evidence/optimization/continuous_receipts.json'
            ac_path = ROOT/'ac_highs_evidence/POST_CANDIDATE_001.json'
            relift_path = ROOT/'ac_relift_evidence/thermal_receipt.json'
            sources = {ab_path: 'dc1978fb3a82c1d56088e10e18759faeb9ab224e3dacf794bc9770594394ee38',
                       ac_path: 'b0dc8c9688cf723576fe15efb342532128f0bded4e3696a68c7497e9d82c105a',
                       relift_path: '32f6550d125adf7a2ed5ce40105dfe5c2ceb729b8c7fda46a77e964c5d71e97f'}
            ab, ac, relift = [read_bound(p, digest) for p, digest in sources.items()]
            summary['source_artifact_sha256'] = {p.relative_to(ROOT).as_posix(): h for p, h in sources.items()}
            frozen_sha = sha256((ROOT/'ac_highs_evidence/UPSTREAM_FROZEN.json').read_bytes()).hexdigest()
            snapshot = read_bound(frozen/'FROZEN.json', frozen_sha)
            for name, expected in snapshot['files'].items():
                if name.startswith(('baseline/', 'inputs/')) or name in (
                        'native_entry_prepared.py', 'shared_mapping_adapter.py'):
                    budget.check()
                    if sha256((frozen/name).read_bytes()).hexdigest() != expected:
                        raise ValueError(f'Frozen science source drift: {name}')
            config, instance = load_frozen_inputs(budget, folder=frozen/'inputs')
            summary['input_sha256'] = {name: snapshot['files'][f'inputs/{name}']
                                       for name in ('input_instance.json', 'input_config.json')}
            summary['canonical_input_sha256'] = canonical_hash(instance)
            summary['frozen_manifest_sha256'] = frozen_sha
            old_ab = ab['aggregation']['scenes'][AB]
            if (old_ab['state'] != 'SAFE' or relift['state'] != 'SAFE'
                    or relift['identity']['candidate_sha256'] != canonical_hash(ac['candidate'])
                    or any(r['identity']['full_input_sha256'] != summary['canonical_input_sha256']
                           for r in (old_ab, relift))):
                raise ValueError('Archived schedule or original input identity mismatch')
            candidate = {'scenes': {AB: ab['aggregation']['safe_candidate']['scenes'][AB],
                                    AC: ac['candidate']['scenes'][AC]}}
            if any(len(candidate['scenes'][sid]) != 6 for sid in (AB, AC)):
                raise ValueError('Expected six stages per scene')
            summary['candidate_sha256'] = canonical_hash(candidate)
            summary['weights'] = {s['id']: s['weight'] for s in instance['scenarios']}
            summary['settings'] = instance['settings']
            save(output/'candidate.json', candidate)

        with budget.phase('original_joint_electrothermal_validation'):
            summary['joint_evaluations'] += 1
            receipt = evaluate_candidate(instance, candidate, config['accuracy_targets'], budget)
            save(output/'joint_receipt.json', receipt)
            summary['joint_state'] = receipt['state']
            summary['joint_reason'] = receipt['reason']
            if receipt['state'] != 'SAFE' or not receipt['rankable_energy']:
                return 1
            shared = receipt['legality']['shared_deployment']
            if {key: shared[key] for key in SHARED} != SHARED:
                raise ValueError('Full-input evaluator returned unexpected shared deployment')
            summary['shared_deployment'] = {key: shared[key] for key in SHARED}
            summary['weighted_energy_J'] = receipt['weighted_energy_J']
            summary['weighted_energy_rounded_J'] = str(Decimal(receipt['safe_upper_bound_J']).quantize(Decimal('0.000001')))
            summary['scenes'] = {sid: {key: receipt['scenes'][sid][key] for key in (
                'state', 'complete', 'energy_J', 'peaks_degC', 'covered_until_s', 'violations')} for sid in (AB, AC)}
            summary['per_scene_energy_intervals_match_archive'] = (
                receipt['scenes'][AB]['energy_J'] == old_ab['energy_J']
                and receipt['scenes'][AC]['energy_J'] == relift['energy_J'])
            budget.check()
        summary['state'] = 'JOINT_SAFE'
        return 0
    except Exception as error:
        summary['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        summary['timing'] = budget.summary()
        save(output/'summary.json', summary)
        print(summary['state'], flush=True)


if __name__ == '__main__':
    started_at = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path)
    parser.add_argument('new_output', type=Path)
    args = parser.parse_args()
    raise SystemExit(verify(args.frozen.resolve(), args.new_output.resolve(), started_at))
