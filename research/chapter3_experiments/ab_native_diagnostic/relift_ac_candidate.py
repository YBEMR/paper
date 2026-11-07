"""Reconstruct one archived AC schedule, with zero optimizer calls."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
import time


LIMIT_S = 90
TOLERANCE = Fraction('1e-9')
ORIGINAL_PAYLOAD_SHA = '7c6454a946273f5ccc2d76b0ebfa264a2fee7ce326de537b474db9bb493c6e1c'
SCENE = 'AC_offset_0ms'
MAPPING = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def audit_exact_rows(matrix, rhs, vector, budget):
    """Recompute every original row using exact arithmetic on stored binary64s."""
    a = matrix.tocsr()
    x = [Fraction(float(v)) for v in vector]
    cache = {}
    worst = Fraction(0)
    worst_row = None
    above_tolerance = 0
    for i, bound in enumerate(rhs):
        if i % 256 == 0:
            budget.check()
        residual = -Fraction(float(bound))
        for k in range(a.indptr[i], a.indptr[i+1]):
            value = x[a.indices[k]]
            if value:
                coef = float(a.data[k])
                if coef not in cache:
                    cache[coef] = Fraction(coef)
                residual += cache[coef] * value
        above_tolerance += residual > TOLERANCE
        if residual > worst:
            worst, worst_row = residual, i
    return {'rows_checked': a.shape[0], 'above_1e_9': above_tolerance,
            'maximum_positive_residual': float(worst), 'exact_fraction': str(worst),
            'worst_row_zero_based': worst_row}


def main(frozen, mat_path, output, origin):
    evidence = Path(__file__).resolve().with_name('ac_highs_evidence')
    paths = [frozen, frozen/'native_source/research/chapter3_experiments',
             frozen/'baseline/research/chapter3_experiments', frozen/'baseline']
    sys.path[:0] = list(map(str, paths))
    import numpy as np
    from scipy.io import loadmat
    from initial_point import _key, _propose_vector
    from matlab_bridge import InitialPointRejected, _check_initial_point, _prepare
    from milp import build_model, decode
    from native_entry_prepared import load_frozen_inputs
    from scene_adapter import evaluate_partial_scene
    from scene_method import DEFAULT_BUILDER_OPTIONS
    from shared_mapping_adapter import ParentOriginClock, payload_sha256
    from thermal import _accuracy
    from timing import MethodBudget

    budget = MethodBudget(LIMIT_S, clock=ParentOriginClock(time.monotonic, origin))
    output.mkdir()
    result = {'state': 'INCOMPLETE', 'optimizer_calls': 0, 'thermal_calls': 0,
              'formal_comparison': False, 'exact_zero_residual_claim': False}

    def admission(payload, vector):
        try:
            return _check_initial_point(payload, vector)[1]
        except InitialPointRejected as error:
            return error.diagnostics

    try:
        with budget.phase('input_identity'):
            manifest = json.loads((evidence/'manifest.json').read_bytes())
            hashes = {row['path']: row['sha256'] for row in manifest['files']}
            for name in ('POST_CANDIDATE_001.json', 'callback_0001.npz', 'UPSTREAM_FROZEN.json'):
                require(digest(evidence/name) == hashes[name], f'Archive drift: {name}')
            require(digest(frozen/'FROZEN.json') == hashes['UPSTREAM_FROZEN.json'], 'Frozen source manifest drift')
            snapshot = json.loads((frozen/'FROZEN.json').read_bytes())
            for name, expected in snapshot['files'].items():
                if name.startswith(('baseline/', 'inputs/', 'native_source/')) or name in (
                        'native_entry_prepared.py', 'shared_mapping_adapter.py'):
                    budget.check()
                    require(digest(frozen/name) == expected, f'Frozen source/input drift: {name}')
            result['equivalent_mat_sha256'] = digest(mat_path)
            require(result['equivalent_mat_sha256'] == manifest['model_mat_sha256'], 'Equivalent MAT drift')
            result['source_posterior_sha256'] = hashes['POST_CANDIDATE_001.json']
            old = json.loads((evidence/'POST_CANDIDATE_001.json').read_bytes())
            candidate = old['candidate']
            require(set(candidate['scenes']) == {SCENE} and len(candidate['scenes'][SCENE]) == 6,
                    'Expected the single archived six-stage schedule')
            require(old['receipt']['state'] == 'SAFE' and not old['original_linear_pass'], 'Unexpected archived status')
            config, instance = load_frozen_inputs(budget, folder=frozen/'inputs')

        with budget.phase('rebuild_original_matrix'):
            model = build_model(instance, config, budget=budget, fixed_scene_id=SCENE,
                                fixed_shared_deployment=MAPPING, **DEFAULT_BUILDER_OPTIONS)
            payload = model.as_solver_dict()
            result['original_payload_sha256'] = payload_sha256(payload)
            require(result['original_payload_sha256'] == ORIGINAL_PAYLOAD_SHA, 'Original matrix identity drift')
            prepared = _prepare(payload)

        with budget.phase('deterministic_completion'):
            vector = _propose_vector(model, candidate, budget)
            result['witness_vector_sha256'] = sha256(vector.tobytes()).hexdigest()
            np.savez(output/'relifted_vector.npz', x=vector)
            decoded = decode(model, vector)
            result['decoded_roundtrip'] = _key(decoded) == _key(candidate)
            require(result['decoded_roundtrip'], 'Relift changed the schedule')

        with budget.phase('original_and_equivalent_matrix_admission'):
            with np.load(evidence/'callback_0001.npz', allow_pickle=False) as archive:
                raw = archive['x']
            result['raw_vector_sha256'] = sha256(raw.tobytes()).hexdigest()
            require(result['raw_vector_sha256'] == old['vector_sha256'], 'Callback vector identity drift')
            require(_key(decode(model, raw)) == _key(decoded), 'Callback and relift decoded schedules differ')
            result['raw_original_admission'] = admission(prepared, raw)
            result['original_admission'] = admission(prepared, vector)
            equivalent = loadmat(mat_path, variable_names=tuple(prepared))
            for name in ('c', 'b', 'beq', 'lb', 'ub', 'intcon'):
                equivalent[name] = equivalent[name].ravel()
            for name in ('c', 'lb', 'ub', 'intcon'):
                require(np.array_equal(prepared[name], equivalent[name]), f'MAT {name} differs from original')
            result['equivalent_admission'] = admission(equivalent, vector)
            result['matrix_dimensions'] = {
                'variables': len(vector), 'original_inequalities': prepared['A'].shape[0],
                'original_equalities': prepared['Aeq'].shape[0], 'equivalent_inequalities': equivalent['A'].shape[0],
                'equivalent_equalities': equivalent['Aeq'].shape[0], 'integer_variables': len(payload['intcon'])}
            integer_values = vector[payload['intcon']]
            result['exact_binary_columns'] = int(np.count_nonzero((integer_values == 0) | (integer_values == 1)))
            result['exact_integer_match_to_rounded_callback'] = bool(
                np.array_equal(integer_values, np.rint(raw[payload['intcon']])))
            result['exact_original_row_audit'] = audit_exact_rows(prepared['A'], prepared['b'], vector, budget)
            if not (result['original_admission']['accepted_numerically']
                    and result['equivalent_admission']['accepted_numerically']
                    and result['exact_binary_columns'] == len(integer_values)
                    and result['exact_original_row_audit']['above_1e_9'] == 0):
                result['state'] = 'COMPLETION_FAILED_NUMERIC_ADMISSION'
                return 1

        with budget.phase('independent_continuous_thermal_posterior'):
            result['thermal_calls'] += 1
            receipt = evaluate_partial_scene(instance, SCENE, MAPPING, decoded,
                                             _accuracy(config['accuracy_targets']), budget)
            save(output/'thermal_receipt.json', receipt)
            result['thermal_state'] = receipt['state']
            require(receipt['state'] == 'SAFE' and receipt['rankable_energy'], 'Fresh posterior did not yield complete SAFE')
            for name in ('candidate_sha256', 'full_input_sha256', 'scenario_sha256', 'source_sha256'):
                require(receipt['identity'][name] == old['receipt']['identity'][name], f'Thermal identity drift: {name}')
            result['physical_energy_J'] = receipt['energy_J']
            result['same_physical_energy_interval'] = receipt['energy_J'] == old['receipt']['energy_J']
            require(result['same_physical_energy_interval'], 'Physical energy differs from archived interval')
            budget.check()
        result['state'] = 'RELIFTED_ORIGINAL_NUMERIC_AND_CONTINUOUS_SAFE'
        return 0
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        result['timing'] = budget.summary()
        save(output/'result.json', result)
        print(result['state'], flush=True)


if __name__ == '__main__':
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path)
    parser.add_argument('equivalent_mat', type=Path)
    parser.add_argument('new_output', type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.frozen.resolve(), args.equivalent_mat.resolve(), args.new_output.resolve(), started))
