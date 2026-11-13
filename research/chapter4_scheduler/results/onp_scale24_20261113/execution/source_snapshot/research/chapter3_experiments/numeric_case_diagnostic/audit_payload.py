"""Inspect saved transport arrays and numeric residuals; no optimization."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def audit(folder):
    matrix = folder / 'request_000001.mat'
    native = folder / 'request_000001.native.mat'
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (matrix, native)}
    d = loadmat(matrix, squeeze_me=True)
    received = loadmat(native, variable_names=['initialPoint'], squeeze_me=True)['initialPoint']
    a = d['A'].tocsr(); x = d['x0']; b = d['b']
    integer = d['intcon'].astype(int)-1
    residue = a @ x-b
    terms = np.where(a.data > 0, a.data*d['lb'][a.indices], a.data*d['ub'][a.indices])
    box_min = np.zeros(a.shape[0])
    np.add.at(box_min, np.repeat(np.arange(a.shape[0]), np.diff(a.indptr)), terms)
    response = json.loads((folder/'request_000001.response.json').read_text(encoding='utf-8'))
    result = {
        'source_sha256': hashes,
        'matrix_shape': list(a.shape), 'nonzeros': a.nnz,
        'native_received_identical_x0': bool(np.array_equal(x, received)),
        'intcon_exactly_first_613_columns': bool(np.array_equal(integer, np.arange(613))),
        'max_float_inequality_residual': float(residue.max()),
        'positive_float_residual_rows': int((residue > 0).sum()),
        'integer_residual': float(abs(x[integer]-np.rint(x[integer])).max()),
        'bound_violations': int(((x < d['lb']) | (x > d['ub'])).sum()),
        'single_row_box_contradictions_float': int((box_min > b).sum()),
        'coefficient_absolute_min_max': [float(abs(a.data).min()), float(abs(a.data).max())],
        'tiny_nonzeros_below_1e_9': int((abs(a.data) < 1e-9).sum()),
        'native_exitflag': response['exitflag'],
        'final_numfeaspoints': response['output']['numfeaspoints'],
        'callback_counts': [{k: v.get(k) for k in ('state', 'values')} for v in response['callbacks']],
        'effective_options': response['options'],
        'scope': 'Archived floating residuals and transport identity, not exact feasibility or optimality.',
        'solver_calls': 0, 'model_builds': 0, 'thermal_evaluations': 0,
    }
    assert all(hashlib.sha256((folder/n).read_bytes()).hexdigest() == h for n, h in hashes.items())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive_folder', type=Path)
    parser.add_argument('new_output', type=Path)
    args = parser.parse_args()
    result = audit(args.archive_folder)
    args.new_output.parent.mkdir(parents=True, exist_ok=True)
    with args.new_output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print('Saved-array identity and residual inspection complete; zero solver calls.')
