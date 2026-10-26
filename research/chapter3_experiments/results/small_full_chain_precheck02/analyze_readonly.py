"""Reproduce K192 facts from saved receipts; no evaluator/solver imports."""
from fractions import Fraction as Q
from hashlib import sha256
from pathlib import Path
import argparse
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(name):
    return json.loads((HERE / name).read_bytes())


def analyze():
    protocol, terminal, counts = map(load, ['precheck_protocol.json', 'terminal.json', 'domain_counts.json'])
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    identity = {key: digest(ROOT / key) == expected
                for key, expected in protocol['source_and_frozen_sha256'].items()}
    assert all(identity.values())
    assert load('execution_claim.json')['protocol_sha256'] == digest(HERE / 'precheck_protocol.json')
    assert terminal['calls_consumed'] == 5 and terminal['scene_trajectories'] == 6
    assert terminal['root_elapsed_s'] < 120
    instance = load('restricted_input.json')
    rows = []
    for name in terminal['calls_started']:
        saved = load(name + '_receipt.json')
        result = saved['receipt']
        assert saved['state'] == 'SAFE' and saved['complete']
        assert result['rankable_energy'] and saved['returned_before_call_deadline']
        assert saved['formed_before_root_deadline']
        assert saved['elapsed_s'] < (60 if name == 'complete_witness' else 15)
        for scene in result['scenes'].values():
            assert scene['complete'] and scene['state'] == 'SAFE'
            assert Q(scene['covered_until_s']) == Q(2, 5)
            assert all(Q(peak[1]) <= 80 for peak in scene['peaks_degC'].values())
        rows.append({'id': name, 'wall_s': saved['elapsed_s'], 'state': saved['state'],
                     'panels': result['panels'], 'refinements': result['refinements']})
    old_sources = json.loads((ROOT / 'research/chapter3_experiments/results/whole_long_budget01/declaration.json').read_bytes())['source_sha256']
    old_names = ['thermal.py', 'schedules.py', 'control_policy.py', 'start_domain.py',
                 'scene_adapter.py', 'inputs.py', 'initial_schedule.py', 'heft_method.py',
                 'heuristic_common.py', 'interval.py']
    old = {key: digest(ROOT / key) == expected for key, expected in old_sources.items()
           if any(key.endswith('/' + name) for name in old_names)}
    assert len(old) == 10 and all(old.values())
    full = load('complete_witness_receipt.json')['receipt']
    witness = {'energy_J': full['weighted_energy_J'], 'energy_upper_J': full['safe_upper_bound_J'],
        'scenes': {sid: {'peak_upper_degC': max(Q(v[1]) for v in result['peaks_degC'].values()),
            'request_completion_ms': full['legality']['scenes'][sid]['request_completion_ms']}
            for sid, result in full['scenes'].items()}}
    assert counts['global_legal_complete_arrangements'] == 450*90 + 650*360
    assert counts['scene_evaluations_for_full_coverage'] == 450 + 650 + 90 + 360
    return {'state': 'SAVED_EVIDENCE_CONSISTENT', 'frozen_identities_checked': len(identity),
        'all_frozen_identities_match': True, 'K187_ten_core_sources_unchanged': old,
        'pure_checks': {'domain': 13, 'lifecycle': 10, 'physical_calls_in_tests': 0,
                       'logs': ['../../small_domain_precheck/domain_tests.txt', '../../small_domain_precheck/lifecycle_tests.txt']},
        'thermal_precheck': {'calls': rows, 'complete_witness': witness,
            'root_elapsed_s': terminal['root_elapsed_s'], 'scene_trajectories': 6},
        'enumeration': {'scene_count': 1550, 'joint_count': 274500,
            'timing_point_estimate_s': terminal['cost_estimate']['sum_projected_seconds'],
            'is_cost_upper_bound': False, 'is_optimality_result': False},
        'method_interface_status': 'option catalogs, structural constructors and SA encoding checked; no formal method wrapper execution certified',
        'formal_solving_authorized': False, 'optimization_calls': 0, 'MATLAB_starts': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = analyze()
    if args.out:
        with args.out.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, default=str)
            stream.write('\n')
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
