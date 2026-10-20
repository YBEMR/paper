"""K132 saved-array affine-coordinate audit. No repo imports or optimization."""
from pathlib import Path
from fractions import Fraction as F
import csv
import hashlib
import json
import math

import numpy as np
from scipy.io import loadmat
from scipy import sparse

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
OUT = ROOT / 'research/chapter3_experiments/results/numerical_conflict_audit01/numeric_route'
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / 'research/chapter3_experiments/results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat'
LABELS = OUT.parent / 'row_trace/labels.json'
m = loadmat(SRC)
a = m['A'].tocsr()
b, c, lb, ub, x = (m[k].reshape(-1) for k in ('b', 'c', 'lb', 'ub', 'x0'))
labels = json.loads(LABELS.read_text(encoding='utf-8'))
names, tags = labels['names'], labels['row_tags']
assert len(names) == a.shape[1] and len(tags) == a.shape[0]
joint = np.array([n.startswith('w:') for n in names])
theta = np.array([n.startswith('theta:') for n in names])
assert joint.any()
q = F.from_float


def finite_exact_float(value):
    try:
        v = float(value)
    except OverflowError:
        return None
    return v if math.isfinite(v) and q(v) == value else None


def exact_rhs(shift):
    rhs, bad, touched = [], [], 0
    for i in range(a.shape[0]):
        value = q(float(b[i]))
        seen = False
        for k in range(a.indptr[i], a.indptr[i + 1]):
            j = a.indices[k]
            if shift[j]:
                value -= q(float(a.data[k])) * shift[j]
                seen = True
        touched += seen
        v = finite_exact_float(value)
        if v is None:
            bad.append({'row_zero_based': i, 'tag': tags[i],
                        'exact_rhs': str(value),
                        'nearest_float': float(value),
                        'rounding_error_exact': str(q(float(value)) - value)})
        rhs.append(float(value))
    return np.array(rhs), bad, touched


def vector_exact_map(values, shift, direction):
    mapped, bad = [], []
    for j, value in enumerate(values):
        v = (q(float(value)) - shift[j]) * int(direction[j])
        f = finite_exact_float(v)
        if f is None:
            bad.append(j)
        mapped.append(float(v))
    return np.array(mapped), bad


def floating_stats(aa, bb, xx):
    residual = np.asarray(aa @ xx).reshape(-1) - bb
    magnitude = np.asarray(abs(aa) @ np.abs(xx)).reshape(-1) + np.abs(bb)
    positive = residual > 0
    active_physical = np.array([t.startswith(('thermal_propagation/', 'complete_energy/')) for t in tags])
    # Each archived physical row has at most one joint state gate.
    gate_active = np.zeros(a.shape[0], dtype=bool)
    for i in np.flatnonzero(active_physical):
        js = a.indices[a.indptr[i]:a.indptr[i + 1]]
        js = js[joint[js]]
        if len(js):
            assert len(js) == 1
            gate_active[i] = x[js[0]] == 1
    return {
        'maximum_positive_residual': float(max(0.0, np.max(residual))),
        'positive_residual_rows': int(sum(positive)),
        'positive_residual_rows_gt_1e9_negative_exponent': int(sum(residual > 1e-9)),
        'positive_residual_argmax_zero_based': int(np.argmax(residual)),
        'active_physical_row_count': int(sum(gate_active)),
        'active_physical_sum_abs_terms_plus_rhs_quantiles': np.quantile(magnitude[gate_active], [0, .5, .9, 1]).tolist(),
        'row_16380_residual': float(residual[16380]),
        'row_16380_sum_abs_terms_plus_rhs': float(magnitude[16380]),
        'row_13838_residual': float(residual[13838]),
        'row_13838_sum_abs_terms_plus_rhs': float(magnitude[13838]),
    }


# w = 1 - z for joint-state columns only; every other x_j = z_j.
t = [F(int(v)) for v in joint]
d = np.where(joint, -1, 1)
bn, bad_b, touched = exact_rhs(t)
an = a.copy()
an.data *= d[an.indices]
xn, bad_x = vector_exact_map(x, t, d)
lbn, ubn = lb.copy(), ub.copy()
lbn[joint] = 1.0 - ub[joint]
ubn[joint] = 1.0 - lb[joint]
cn = c * d
constant = sum((q(float(v)) for v in c[joint]), F(0))
bound_exact = all(q(float(lbn[j])) == 1-q(float(ub[j]))
                  and q(float(ubn[j])) == 1-q(float(lb[j])) for j in np.flatnonzero(joint))
xround = xn.copy()
xround[joint] = 1-xn[joint]
rhs_roundtrip_exact = None
if not bad_b:
    rhs_roundtrip_exact = 0
    for i in range(a.shape[0]):
        value = q(float(bn[i]))
        for k in range(a.indptr[i], a.indptr[i + 1]):
            if joint[a.indices[k]]:
                value += q(float(a.data[k]))
        rhs_roundtrip_exact += value == q(float(b[i]))

# A centered-temperature extension is evaluated only for exact representability.
# It is not emitted as a replacement model when it needs rounding.
tc = [v + F(25) if theta[j] else v for j, v in enumerate(t)]
_, bad_center, touched_center = exact_rhs(tc)

# Unique alternative requested after the strict full substitution failed:
# retain w for every original logical/strengthening row, add v+w=1, and
# substitute only the single-gate physical rows. No rounding is permitted.
physical = np.array([tag.startswith(('thermal_propagation/', 'complete_energy/')) for tag in tags])
alias_gate_columns = set()
physical_gate_count_bad = []
alias_b = b.copy()
alias_rhs_bad = []
for i in np.flatnonzero(physical):
    js = a.indices[a.indptr[i]:a.indptr[i + 1]]
    gate_js = js[joint[js]]
    if len(gate_js) > 1:
        physical_gate_count_bad.append(int(i))
    if len(gate_js) == 1:
        j = int(gate_js[0])
        alias_gate_columns.add(j)
        exact = q(float(b[i])) - q(float(a[i, j]))
        value = finite_exact_float(exact)
        if value is None:
            alias_rhs_bad.append({'row_zero_based': int(i), 'tag': tags[i], 'exact_rhs': str(exact),
                                  'nearest_float': float(exact),
                                  'rounding_error_exact': str(q(float(exact))-exact)})
        else:
            alias_b[i] = value
alias_gate_columns = sorted(alias_gate_columns)
alias_lookup = {j: a.shape[1]+k for k, j in enumerate(alias_gate_columns)}
alias_facts = {
    'eligible_physical_rows': int(sum(physical)),
    'physical_rows_with_more_than_one_joint_gate': physical_gate_count_bad,
    'new_alias_variables': len(alias_gate_columns),
    'nonrepresentable_physical_rhs_count': len(alias_rhs_bad),
    'nonrepresentable_physical_rhs_first_10': alias_rhs_bad[:10],
    'original_integer_index_array_unchanged': True,
    'original_objective_coefficients_unchanged_new_costs_zero': True,
    'original_variables_not_mapped_or_repaired': True,
    'native_acceptance_or_infeasibility_resolution_tested': False,
}
if not physical_gate_count_bad and not alias_rhs_bad:
    coo = a.tocoo()
    alias_cols, alias_data = coo.col.copy(), coo.data.copy()
    mask = physical[coo.row] & joint[coo.col]
    alias_cols[mask] = [alias_lookup[int(j)] for j in coo.col[mask]]
    alias_data[mask] *= -1
    alias_a = sparse.coo_matrix((alias_data, (coo.row, alias_cols)),
                               shape=(a.shape[0], a.shape[1]+len(alias_gate_columns))).tocsr()
    k = np.arange(len(alias_gate_columns))
    links = sparse.coo_matrix((np.ones(2*len(k)),
                                (np.r_[k, k], np.r_[alias_gate_columns, a.shape[1]+k])),
                               shape=(len(k), alias_a.shape[1])).tocsr()
    alias_x = np.r_[x, 1-x[alias_gate_columns]]
    link_residual = links@alias_x-1
    # Strict Fraction equality of every physical row after eliminating v.
    exact_rows = 0
    for i in np.flatnonzero(physical):
        js = a.indices[a.indptr[i]:a.indptr[i + 1]]
        gate_js = js[joint[js]]
        if not len(gate_js):
            exact_rows += 1
        else:
            j = int(gate_js[0])
            exact_rows += q(float(alias_b[i])) + q(float(a[i, j])) == q(float(b[i]))
    # An exact-arithmetic algebra check at a nonintegral joint vector. These
    # samples need not be legal schedules; no optimization or physics runs.
    sample_original = list(map(lambda v: q(float(v)), x))
    for k, j in enumerate(alias_gate_columns):
        sample_original[j] = F(1, 4) if k % 2 else F(3, 4)
    sample_alias = sample_original + [1-sample_original[j] for j in alias_gate_columns]
    sample_equal_rows = 0
    sample_link_equal_rows = 0
    for i in range(a.shape[0]):
        old = sum((q(float(a.data[k]))*sample_original[a.indices[k]]
                   for k in range(a.indptr[i], a.indptr[i+1])), F(0))-q(float(b[i]))
        new = sum((q(float(alias_a.data[k]))*sample_alias[alias_a.indices[k]]
                   for k in range(alias_a.indptr[i], alias_a.indptr[i+1])), F(0))-q(float(alias_b[i]))
        sample_equal_rows += old == new
    for j in alias_gate_columns:
        sample_link_equal_rows += sample_original[j]+sample_alias[alias_lookup[j]] == 1
    unchanged_intcon = m['intcon'].reshape(-1).astype(int)-1
    alias_facts.update({
        'new_total_variables': alias_a.shape[1],
        'new_inequality_rows': alias_a.shape[0],
        'new_equality_rows': links.shape[0],
        'new_total_rows': alias_a.shape[0]+links.shape[0],
        'new_inequality_nnz': alias_a.nnz,
        'new_equality_nnz': links.nnz,
        'new_total_nnz': alias_a.nnz+links.nnz,
        'physical_rows_exact_after_eliminating_alias': int(exact_rows),
        'nonphysical_original_rows_unchanged_exactly': bool(np.array_equal(alias_b[~physical], b[~physical])
                                                          and (alias_a[~physical, :a.shape[1]] != a[~physical]).nnz == 0
                                                          and alias_a[~physical, a.shape[1]:].nnz == 0),
        'x0_original_prefix_bitwise_unchanged': bool(np.array_equal(alias_x[:len(x)].view(np.uint64), x.view(np.uint64))),
        'x0_alias_exact_binary_complement': bool(np.all((alias_x[len(x):] == 0) | (alias_x[len(x):] == 1))),
        'x0_equality_max_abs_residual': float(np.max(np.abs(link_residual), initial=0.0)),
        'nonintegral_sample_joint_values_exact': ['1/4', '3/4'],
        'nonintegral_sample_original_new_exact_residual_equal_rows': int(sample_equal_rows),
        'nonintegral_sample_exact_link_equalities': int(sample_link_equal_rows),
        'nonintegral_sample_original_integer_coordinates_unchanged': bool(all(sample_original[j] == q(float(x[j])) for j in unchanged_intcon)),
        'original_Aeq_shape': list(m['Aeq'].shape),
        'original_Aeq_preserved_as_prefix': True,
        'original_objective_on_sample_exactly_preserved': sum((q(float(v))*xx for v, xx in zip(c, sample_original)), F(0)) == sum((q(float(v))*xx for v, xx in zip(np.r_[c, np.zeros(len(alias_gate_columns))], sample_alias)), F(0)),
        'x0_alias_inequality_float_stats': floating_stats(alias_a, alias_b, alias_x),
        'maximum_physical_gate_abs_coefficient': float(np.max(np.abs(coo.data[mask]), initial=0.0)),
        'one_link_tau_can_induce_original_row_residual_as_large_as': float(np.max(np.abs(coo.data[mask]), initial=0.0)*1e-9),
        'exact_projection_equivalence_to_stored_original': bool(exact_rows == sum(physical)),
        'floating_acceptance_region_identical': False,
    })

# Row-only powers of two: exact coefficient arithmetic, changed tolerance units.
row_max = np.asarray(abs(a).max(axis=1).toarray()).reshape(-1)
row_exp = np.zeros(a.shape[0], dtype=int)
nonempty = row_max > 0
row_exp[nonempty] = -np.floor(np.log2(row_max[nonempty])).astype(int)
row_scale = np.ldexp(np.ones(a.shape[0]), row_exp)
scaled = a.multiply(row_scale[:, None]).tocsr()
scaled_b = b * row_scale
row_scale_exact = all(q(float(vv)) == q(float(v))*q(float(row_scale[i]))
                      for i in range(a.shape[0])
                      for v, vv in zip(a.data[a.indptr[i]:a.indptr[i+1]],
                                       scaled.data[scaled.indptr[i]:scaled.indptr[i+1]]))
row_rhs_exact = all(q(float(v)) * q(float(s)) == q(float(v*s)) for v, s in zip(b, row_scale))

facts = {
    'scope': 'saved-array algebra only; no solve, MATLAB, thermal recomputation, or production change',
    'source_sha256': hashlib.sha256(SRC.read_bytes()).hexdigest(),
    'labels_sha256': hashlib.sha256(LABELS.read_bytes()).hexdigest(),
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'n': a.shape[1], 'm': a.shape[0], 'nnz': a.nnz,
    'joint_columns': int(sum(joint)),
    'joint_columns_in_intcon': int(sum(joint[m['intcon'].reshape(-1).astype(int)-1])),
    'joint_original_lb_values': np.unique(lb[joint]).tolist(),
    'joint_original_ub_values': np.unique(ub[joint]).tolist(),
    'joint_x0_values': np.unique(x[joint]).tolist(),
    'complement': {
        'rhs_rows_touched': touched, 'rhs_not_binary64_exact_count': len(bad_b),
        'rhs_failures_first_10': bad_b[:10],
        'coefficients_exact_sign_flip': bool(np.array_equal(an.indices, a.indices) and np.array_equal(an.indptr, a.indptr)
                                              and np.array_equal(an.data*d[an.indices], a.data)),
        'rhs_rational_roundtrip_exact_rows': rhs_roundtrip_exact,
        'rhs_rational_roundtrip_state': 'not_run_full_substitution_failed_exact_rhs_gate' if bad_b else 'completed',
        'x0_not_binary64_exact_count': len(bad_x),
        'x0_bitwise_value_roundtrip_equal': bool(np.array_equal(xround.view(np.uint64), x.view(np.uint64))),
        'x0_numeric_roundtrip_equal': bool(np.array_equal(xround, x)),
        'bounds_exact': bound_exact,
        'objective_coefficient_numeric_unchanged': bool(np.array_equal(cn, c)),
        'objective_constant_exact': str(constant),
        'integer_index_array_unchanged': True,
        'original_float_residuals': floating_stats(a, b, x),
        'complement_float_residuals': floating_stats(an, bn, xn),
        'maximum_row_dynamic_ratio_unchanged': True,
        'ideal_symbolic_complement_has_same_row_residual_units': True,
        'floating_stats_above_use_nearest_rhs_only_for_rejected_candidate_diagnosis': bool(bad_b),
        'rounded_candidate_not_emitted_as_model': True,
        'native_acceptance_or_infeasibility_resolution_tested': False,
    },
    'complement_and_theta_minus_25': {
        'rhs_rows_touched': touched_center,
        'rhs_not_binary64_exact_count': len(bad_center),
        'rhs_failures_first_10': bad_center[:10],
        'emitted_or_recommended_for_implementation': False,
    },
    'physical_alias_only': alias_facts,
    'row_max_power2_normalization': {
        'minimum_row_scale': float(min(row_scale)), 'maximum_row_scale': float(max(row_scale)),
        'all_coefficients_scaled_exactly': row_scale_exact,
        'all_rhs_scaled_exactly': row_rhs_exact,
        'row_dynamic_ratios_unchanged': True,
        'original_units_absolute_tolerance_min': float(min(1e-9 / row_scale)),
        'original_units_absolute_tolerance_max': float(max(1e-9 / row_scale)),
        'uniform_original_tolerance_preserved': bool(np.all(row_scale == 1)),
    },
    'certificates': {
        'exact_equivalence_of_stored_polyhedron_for_joint_complement': not bad_b and not bad_x and bound_exact and rhs_roundtrip_exact == len(b),
        'exact_x0_feasibility': False,
        'thermal_safety': False, 'native_solver_success': False,
    },
}
(OUT/'facts.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
(OUT/'rejected_full_complement_rhs.json').write_text(json.dumps(bad_b, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
(OUT/'audit_saved_affine_route.py').write_bytes(Path(__file__).read_bytes())
with (OUT/'joint_columns.csv').open('w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['column_zero_based', 'name', 'lb', 'ub', 'x0', 'c', 'complement_lb', 'complement_ub', 'complement_x0'])
    for j in np.flatnonzero(joint):
        w.writerow([j, names[j], lb[j], ub[j], x[j], c[j], lbn[j], ubn[j], xn[j]])
print(json.dumps({'full_complement_exact_rhs_failures': len(bad_b),
                  'alias_original_projection_exact': alias_facts.get('exact_projection_equivalence_to_stored_original', False),
                  'alias_continuous_sample_exact_equal_rows': alias_facts.get('nonintegral_sample_original_new_exact_residual_equal_rows'),
                  'output': str(OUT/'facts.json')}, ensure_ascii=False))
