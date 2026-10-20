"""Independent saved-array arithmetic review; no model construction/solve.

Does not import the route script or create an augmented matrix. Rechecks the
original MAT gate coefficients and exact RHS arithmetic directly.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = HERE.parents[4]
matpath = ROOT / 'research/chapter3_experiments/results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat'
m = loadmat(matpath)
a = m['A'].tocsr()
b, lb, ub, x0, c = [m[k].reshape(-1) for k in ('b', 'lb', 'ub', 'x0', 'c')]
labels = json.loads((HERE/'labels.json').read_text(encoding='utf-8'))
assert json.loads((HERE/'rebuild_comparison.json').read_text())['all_arrays_identical']
joint = {j for j, name in enumerate(labels['names']) if name.startswith('w:')}
integer = {int(j)-1 for j in m['intcon'].reshape(-1)}
physical = [i for i, tag in enumerate(labels['row_tags'])
            if tag.startswith(('thermal_propagation/', 'complete_energy/'))]
physical_set = set(physical)
physical_rhs_bad, physical_gate_bad, all_rhs_bad = [], [], []
gate_coefficients = []
used = set()
for i in range(a.shape[0]):
    row = a.getrow(i)
    gates = [(int(j), float(v)) for j, v in zip(row.indices, row.data) if j in joint]
    rhs_global = F(float(b[i]))-sum((F(v) for _, v in gates), F(0))
    if F(float(rhs_global)) != rhs_global:
        all_rhs_bad.append(i)
    if i in physical_set:
        if len(gates) != 1:
            physical_gate_bad.append(i)
            continue
        j, coefficient = gates[0]
        used.add(j)
        gate_coefficients.append(abs(coefficient))
        rhs = F(float(b[i]))-F(coefficient)
        if F(float(rhs)) != rhs:
            physical_rhs_bad.append(i)
        assert F(float(rhs))+F(coefficient) == F(float(b[i]))

facts = json.loads((AUDIT/'numeric_route/facts.json').read_text(encoding='utf-8'))
route = facts['physical_alias_only']
max_gate = max(gate_coefficients)
declaration = json.loads((AUDIT/'declaration.json').read_text(encoding='utf-8'))
source_changes = [p for p, h in declaration['source_sha256'].items()
                  if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h]
artifact_changes = [p for p, h in declaration['K131_artifact_sha256'].items()
                    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h]
result = {
    'scope': 'independent review of source MAT and labels only; no augmented matrix/model/solver/evaluator created',
    'original_mat_sha256': hashlib.sha256(matpath.read_bytes()).hexdigest(),
    'route_script_sha256_matches_facts': hashlib.sha256((AUDIT/'numeric_route/audit_saved_affine_route.py').read_bytes()).hexdigest() == facts['script_sha256'],
    'source_sha256_matches_route': hashlib.sha256(matpath.read_bytes()).hexdigest() == facts['source_sha256'],
    'frozen_production_source_count_checked': len(declaration['source_sha256']),
    'frozen_production_source_changes': source_changes,
    'frozen_K131_artifact_count_checked': len(declaration['K131_artifact_sha256']),
    'frozen_K131_artifact_changes': artifact_changes,
    'physical_row_count': len(physical),
    'physical_rows_without_exactly_one_gate': physical_gate_bad,
    'physical_b_minus_gate_not_exact_binary64_rows': physical_rhs_bad,
    'full_global_complement_not_exact_binary64_rows_count': len(all_rhs_bad),
    'full_global_complement_failure_tags': sorted({labels['row_tags'][i] for i in all_rhs_bad}),
    'gate_columns_total': len(joint), 'gate_columns_used_in_physical_rows': len(used),
    'all_gate_bounds_0_1': all(lb[j] == 0 and ub[j] == 1 for j in joint),
    'all_gate_x0_exactly_0_1': all(x0[j] in (0, 1) for j in joint),
    'gate_columns_in_intcon': len(joint & integer),
    'gate_objective_zero': all(c[j] == 0 for j in joint),
    'original_Aeq_shape': list(m['Aeq'].shape),
    'route_reported_counts_match': bool(route['eligible_physical_rows'] == len(physical)
        and route['new_alias_variables'] == len(joint)
        and route['nonrepresentable_physical_rhs_count'] == len(physical_rhs_bad)
        and facts['complement']['rhs_not_binary64_exact_count'] == len(all_rhs_bad)),
    'exact_projection_argument': 'Keep all x and original nonphysical rows. For each w in [0,1], v=1-w is the unique v in [0,1] satisfying v+w=1. Substitution recovers each original physical row with exact stored coefficients/RHS. Projection preserves all original integer coordinates and objective.',
    'link_error_identity': 'r_original = r_augmented + M*(w+v-1)',
    'maximum_abs_physical_gate_coefficient': max_gate,
    'link_tolerance_example': 1e-9,
    'maximum_link_induced_original_row_shift': max_gate*1e-9,
    'maximum_original_row_residual_if_both_augmented_and_link_reach_tau': (1+max_gate)*1e-9,
    'same_tolerance_acceptance_region': False,
    'required_future_check': 'Every final/callback original-variable prefix must independently pass the original saved matrix residual checks; retain augmented/link/original residuals separately. No tolerance relaxation or new SAFE/solver claim.',
    'optimizer_calls': 0, 'matlab_starts': 0, 'thermal_evaluations': 0,
}
(HERE/'independent_affine_facts.json').write_text(json.dumps(result, ensure_ascii=False,
    indent=2, allow_nan=False)+'\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
