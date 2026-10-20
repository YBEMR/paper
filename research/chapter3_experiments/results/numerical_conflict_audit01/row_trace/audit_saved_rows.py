"""Only saved arrays and exactly matched labels; no rebuild or optimization.

Exact dyadic arithmetic diagnoses the recorded x0, not general feasibility.
Opposite-row tests inspect either the whole saved model or the branch fixing
all recorded logical controls to their exact 0/1 x0 values. Neither test is an
LP/MILP solve or an independent feasible/optimal/infeasible certificate.
"""
from collections import Counter
import csv
from fractions import Fraction as F
import json
from pathlib import Path
import time

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MAT = ROOT / 'research/chapter3_experiments/results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat'


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                       allow_nan=False) + '\n', encoding='utf-8')


def encoded(q):
    return {'fraction': str(q), 'float': float(q)}


def main():
    started = time.monotonic()
    assert json.loads((HERE/'rebuild_comparison.json').read_text())['all_arrays_identical']
    labels = json.loads((HERE / 'labels.json').read_text(encoding='utf-8'))
    names, tags = labels['names'], labels['row_tags']
    mat = loadmat(MAT)
    a = mat['A'].tocsr()
    b, x0, lb, ub = [mat[k].reshape(-1) for k in ('b', 'x0', 'lb', 'ub')]
    floating_residual = a @ x0-b
    exact_x0 = [F(float(x)) for x in x0]
    physical_tags = {'thermal_propagation/upper', 'thermal_propagation/lower',
        'complete_energy/upper', 'complete_energy/lower', 'activity_power/upper',
        'activity_power/lower', 'energy_state_lower_bound', 'dependency'}
    tight_rows = [i for i, tag in enumerate(tags)
                  if tag in physical_tags and abs(floating_residual[i]) <= 1e-9]
    exact_positive = []
    per_family = {}
    for i in tight_rows:
        left, right = a.indptr[i:i+2]
        residual = sum((F(float(v))*exact_x0[j] for j, v in
                        zip(a.indices[left:right], a.data[left:right])), F(0))-F(float(b[i]))
        item = per_family.setdefault(tags[i], {'rows_checked': 0, 'exact_positive_count': 0,
            'float_positive_count': 0, 'max_exact_residual': None, 'max_exact_residual_row_zero_based': None})
        item['rows_checked'] += 1
        item['exact_positive_count'] += int(residual > 0)
        item['float_positive_count'] += int(floating_residual[i] > 0)
        if item['max_exact_residual'] is None or residual > F(item['max_exact_residual']['fraction']):
            item['max_exact_residual'] = encoded(residual)
            item['max_exact_residual_row_zero_based'] = i
        if residual > 0:
            exact_positive.append({'row_zero_based': i, 'tag': tags[i],
                'exact_Ax0_minus_b': encoded(residual),
                'float_Ax0_minus_b': float(floating_residual[i])})
    save('tight_row_dyadic_facts.json', {
        'scope': 'exact evaluation of archived binary64 coefficients and x0 on selected tight physical rows',
        'selection': 'physical/dependency tags and abs(saved binary64 Ax0-b)<=1e-9',
        'rows_checked': len(tight_rows), 'families': per_family,
        'exact_positive_count': len(exact_positive),
        'max_positive_rows': sorted(exact_positive,
            key=lambda r: F(r['exact_Ax0_minus_b']['fraction']), reverse=True)[:30],
        'interpretation': 'x0 remains tolerance accepted; positive exact dyadic residual does not imply model infeasibility',
    })
    spots = []
    for i in (13838, 16380, 39455, 19388):
        left, right = a.indptr[i:i+2]
        exact = sum((F(float(v))*exact_x0[j] for j, v in
                     zip(a.indices[left:right], a.data[left:right])), F(0))-F(float(b[i]))
        spots.append({'row_zero_based': i, 'tag': tags[i],
                      'exact_Ax0_minus_b': encoded(exact),
                      'float_Ax0_minus_b': float(floating_residual[i])})
    save('spot_row_dyadic_facts.json', spots)

    # These are controls recorded as exactly 0 or 1, including relaxed
    # auxiliaries. Their substitution examines this fixed branch only.
    logical_families = {'y', 'x', 'rho', 'J', 'w'}
    logical = {j for j, name in enumerate(names) if name.split(':', 1)[0] in logical_families}
    assert all(x0[j] in (0, 1) for j in logical)

    def opposite_row_scan(fix_recorded_controls):
        groups = {}
        zero_rows = []
        for i in range(a.shape[0]):
            left, right = a.indptr[i:i+2]
            rhs = F(float(b[i]))
            entries = []
            for j, v in zip(a.indices[left:right], a.data[left:right]):
                if fix_recorded_controls and j in logical:
                    if x0[j]:
                        rhs -= F(float(v))
                elif v:
                    entries.append((int(j), float(v)))
            if not entries:
                zero_rows.append((i, rhs))
                continue
            sign = 1 if entries[0][1] > 0 else -1
            key = tuple((j, sign*v) for j, v in entries)
            pair = groups.setdefault(key, {})
            if sign not in pair or rhs < pair[sign][1]:
                pair[sign] = (i, rhs)
        widths = []
        for pair in groups.values():
            if 1 in pair and -1 in pair:
                i, bp = pair[1]
                j, bm = pair[-1]
                widths.append((bp+bm, i, j, bp, bm))
        widths.sort()
        return {
            'scope': ('saved rows after exact substitution of recorded 0/1 logical controls; only that branch'
                      if fix_recorded_controls else 'all saved rows without substitutions'),
            'opposite_coefficient_groups': len(widths),
            'negative_width_group_count': sum(w[0] < 0 for w in widths),
            'zero_width_group_count': sum(w[0] == 0 for w in widths),
            'constant_row_count': len(zero_rows),
            'constant_row_negative_rhs_count': sum(q < 0 for _, q in zero_rows),
            'minimum_width_groups': [
                {'width': encoded(w), 'positive_row_zero_based': i, 'negative_row_zero_based': j,
                 'positive_tag': tags[i], 'negative_tag': tags[j],
                 'positive_rhs_after_substitution': encoded(bp),
                 'negative_rhs_after_substitution': encoded(bm)}
                for w, i, j, bp, bm in widths[:20]],
            'negative_constant_rows': [{'row_zero_based': i, 'tag': tags[i], 'rhs': encoded(q)}
                                       for i, q in zero_rows if q < 0][:20],
        }
    opposite = {
        'arithmetic': 'exact fractions of saved binary64 coefficients/RHS; no tolerance',
        'complete_global': opposite_row_scan(False),
        'recorded_controls_branch': opposite_row_scan(True),
        'logical_column_family_counts': dict(Counter(names[j].split(':', 1)[0] for j in logical)),
        'limitation': 'absence of opposite-row contradictions is not full feasibility or solver diagnosis',
    }
    save('opposite_row_facts.json', opposite)

    boundary = {}
    for family in ('theta', 'q', 'energy', 'rho', 'J', 'w'):
        indices = [j for j, name in enumerate(names) if name.startswith(family+':')]
        if not indices:
            continue
        lower = [(F(float(x0[j]))-F(float(lb[j])), j) for j in indices]
        upper = [(F(float(ub[j]))-F(float(x0[j])), j) for j in indices]
        positive_lower = sorted((q, j) for q, j in lower if q > 0)
        positive_upper = sorted((q, j) for q, j in upper if q > 0)
        boundary[family] = {
            'count': len(indices), 'fixed_bound_count': int(sum(lb[j] == ub[j] for j in indices)),
            'exactly_at_lower_bound_count': sum(q == 0 for q, _ in lower),
            'exactly_at_upper_bound_count': sum(q == 0 for q, _ in upper),
            'bound_violation_count': sum(q < 0 for q, _ in lower+upper),
            'smallest_positive_lower_distances': [
                {'column_zero_based': j, 'name': names[j], 'distance': encoded(q),
                 'x0': float(x0[j]), 'lb': float(lb[j])} for q, j in positive_lower[:3]],
            'smallest_positive_upper_distances': [
                {'column_zero_based': j, 'name': names[j], 'distance': encoded(q),
                 'x0': float(x0[j]), 'ub': float(ub[j])} for q, j in positive_upper[:3]],
        }
    save('auxiliary_boundary_facts.json', boundary)
    tiny = Counter(tags[i] for i in range(len(tags)) if 0 < abs(b[i]) < 1e-12)
    fact = {
        'scope': 'saved numerical row/variable arithmetic only; no rebuild, optimization or thermal evaluation',
        'wall_s': time.monotonic()-started,
        'tight_physical_rows_checked_dyadically': len(tight_rows),
        'x0_exact_positive_tight_physical_row_count': len(exact_positive),
        'float_positive_residual_count_all_rows': int(sum(floating_residual > 0)),
        'max_float_residual': float(max(floating_residual)),
        'nonzero_abs_rhs_lt_1e12_negative_exponent_by_tag': dict(tiny),
        'all_row_families': dict(Counter(tags)),
        'root_cause_established': False,
    }
    save('offline_row_facts.json', fact)
    print(json.dumps(fact, ensure_ascii=False))


if __name__ == '__main__':
    main()
