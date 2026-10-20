"""Read saved MAT arrays only: no model construction, evaluator, or optimizer."""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy.io import loadmat


AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parent


def analyze(path):
    m = loadmat(path)
    a = m['A'].tocsr()
    b = m['b'].reshape(-1)
    nz = np.abs(a.data[a.data != 0])
    bn = np.abs(b[b != 0])
    row_min = np.full(a.shape[0], np.inf)
    row_max = np.zeros(a.shape[0])
    for i in range(a.shape[0]):
        r = np.abs(a.data[a.indptr[i]:a.indptr[i + 1]])
        r = r[r != 0]
        if len(r):
            row_min[i] = min(r)
            row_max[i] = max(r)
    dynamic = row_max / row_min
    j = int(np.argmax(dynamic))
    row = a.getrow(j)
    return {
        'file': str(path.relative_to(ROOT)),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'A_shape': list(a.shape), 'A_nnz': int(a.nnz),
        'A_min_abs_nonzero': float(min(nz)), 'A_max_abs': float(max(nz)),
        'A_global_dynamic_ratio': float(max(nz) / min(nz)),
        'b_min_abs_nonzero': float(min(bn)), 'b_max_abs': float(max(bn)),
        'b_zero_count': int(sum(b == 0)),
        'empty_row_count': int(sum(~np.isfinite(row_min))),
        'max_row_dynamic_ratio': float(dynamic[j]),
        'max_ratio_row_index_zero_based': j,
        'max_ratio_row_min_abs_nonzero': float(row_min[j]),
        'max_ratio_row_max_abs': float(row_max[j]),
        'max_ratio_row_rhs': float(b[j]),
        'max_ratio_row_entries': [
            {'column_zero_based': int(k), 'coefficient': float(v),
             'objective_coefficient': float(m['c'].reshape(-1)[k]),
             'lb': float(m['lb'].reshape(-1)[k]),
             'ub': float(m['ub'].reshape(-1)[k])}
            for k, v in zip(row.indices, row.data)],
        'max_ratio_row_family': 'not_located_in_saved_payload',
        'row_dynamic_ratio_quantiles_including_empty_as_zero':
            np.quantile(dynamic, [0, .5, .9, .99, 1]).tolist(),
        'rows_dynamic_ratio_gt_1e6': int(sum(dynamic > 1e6)),
        'rows_dynamic_ratio_gt_1e9': int(sum(dynamic > 1e9)),
        'nonzero_coefficients_abs_lt_1e9_negative_exponent': int(sum(nz < 1e-9)),
        'nonzero_coefficients_abs_lt_1e12_negative_exponent': int(sum(nz < 1e-12)),
    }


facts = {'scope': 'saved numerical arrays only; no solve, rebuild, or thermal evaluation',
         'root_cause_established': False, 'production_files_changed': False,
         'models': []}
for branch in ('all_opp_start', 'old_n1'):
    for path in sorted((ROOT / branch / 'matlab').glob('request_*.mat')):
        if '.native.' not in path.name:
            facts['models'].append(analyze(path))
(AUDIT / 'scale_facts.json').write_text(
    json.dumps(facts, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
    encoding='utf-8')
print(json.dumps({'models_read': len(facts['models']),
                  'output': str(AUDIT / 'scale_facts.json')}, ensure_ascii=False))
