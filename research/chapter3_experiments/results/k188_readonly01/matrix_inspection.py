"""Inspect archived K187 arrays by sparse arithmetic only.

No solver, model builder, decoder, thermal evaluator, or optimization module is
imported. Index fields explicitly carry zero/one-based forms. Exact checks mean
the stored binary64 coefficients interpreted as rationals, not an assertion
about the original unrounded electrothermal model.
"""
from __future__ import annotations

import argparse
import bisect
import gc
import hashlib
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy import sparse


HERE = Path(__file__).resolve().parent
MAT = HERE.parent / "whole_long_budget01/method/matlab/request_000001.mat"
TOL = 1e-9
TOP = 24
EXACT_ROW_CAP = 64
PAIR_CERT_CAP = 32


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def q(value):
    return Fraction.from_float(float(value))


def rows_top(values, count=TOP, largest=True):
    values = np.asarray(values)
    ids = np.flatnonzero(np.isfinite(values))
    if not len(ids):
        return []
    take = min(count, len(ids))
    order = np.argsort(values[ids], kind="stable")
    chosen = ids[order[-take:][::-1] if largest else order[:take]]
    return [int(i) for i in chosen]


def summary(values):
    x = np.asarray(values).reshape(-1)
    finite = x[np.isfinite(x)]
    return {"count": int(x.size), "nonfinite": int(x.size - finite.size),
            "minimum": None if not finite.size else float(finite.min()),
            "maximum": None if not finite.size else float(finite.max()),
            "quantiles_0_25_50_75_90_99_100": None if not finite.size else
                [float(v) for v in np.quantile(finite, [0, .25, .5, .75, .9, .99, 1])]}


def row_data(A, row):
    start, stop = A.indptr[row:row + 2]
    return A.indices[start:stop], A.data[start:stop]


def exact_dot(A, row, x):
    indices, data = row_data(A, row)
    return sum((q(v) * q(x[int(j)]) for j, v in zip(indices, data)), Fraction())


def exact_integer_rhs(A, row, b, is_integer, fixed):
    indices, data = row_data(A, row)
    return q(b[row]) - sum((q(v) * int(fixed[int(j)])
                           for j, v in zip(indices, data) if is_integer[int(j)]), Fraction())


def detail(A, row, b, x, lhs, absolute_sum):
    indices, data = row_data(A, row)
    exact = exact_dot(A, row, x)
    residual = exact - q(b[row])
    products = [float(v) * float(x[int(j)]) for j, v in zip(indices, data)]
    stable_sum = math.fsum(products)
    return {"row_0based": int(row), "row_1based": int(row + 1), "nnz": int(len(indices)),
        "rhs_binary64": float(b[row]), "lhs_sparse_dot": float(lhs[row]),
        "lhs_fsum_rounded_products": stable_sum,
        "residual_sparse_dot_minus_rhs": float(lhs[row] - b[row]),
        "sum_absolute_products": float(absolute_sum[row]),
        "exact_binary64_lhs": str(exact), "exact_binary64_residual": str(residual),
        "exact_binary64_residual_float": float(residual),
        "dot_rounding_difference_from_exact": float(q(lhs[row]) - exact),
        "strict_stored_binary64_row_violated_by_x0": residual > 0,
        "exact_residual_above_1e_minus_9": residual > q(TOL),
        "coefficients": [{"column_0based": int(j), "column_1based": int(j + 1),
                          "value": float(v), "hex": float(v).hex(), "x0": float(x[int(j)])}
                         for j, v in zip(indices, data)]}


def pair_groups(A, b, *, mode, candidate_cap=TOP, attention_rows=(), activated=None, residual=None,
                rhs_semantics="original stored binary64 b; width totals use floating addition"):
    """Exact-sign pairs or rounded normalized near-sign candidates; no solve.

    Near signatures use 12 decimal digits after max-absolute normalization.
    They enumerate this explicit bucket rule, not all norm-near row pairs.
    """
    groups = {}
    for row in range(A.shape[0]):
        indices, data = row_data(A, row)
        if not data.size:
            continue
        positive = data[0] > 0
        orient = data if positive else -data
        if mode == "near":
            orient = np.round(orient / np.max(np.abs(orient)), 12)
            orient[orient == 0] = 0.0
        key = (indices.tobytes(), orient.tobytes())
        bucket = groups.setdefault(key, [[], []])
        bucket[0 if positive else 1].append(row)
    stats = {"mode": mode, "groups_with_both_signs": 0, "potential_pair_count": 0,
             "zero_float_width_pair_count": 0 if mode == "exact" else None,
             "negative_float_width_pair_count": 0 if mode == "exact" else None,
             "rhs_semantics": rhs_semantics,
             "note": "exact mode refers only to opposite coefficient signatures; all width/count aggregates here use the passed floating RHS, not rational substitution; only selected rational certificates establish exact widths"}
    selected = []
    attention_examples, active_examples = [], []
    attention_rows = set(attention_rows)
    for pos, neg in groups.values():
        if not pos or not neg:
            continue
        stats["groups_with_both_signs"] += 1
        stats["potential_pair_count"] += len(pos) * len(neg)
        if mode == "exact":
            p = min(pos, key=lambda r: b[r])
            n = min(neg, key=lambda r: b[r])
            negative_rhs = sorted(float(b[r]) for r in neg)
            stats["negative_float_width_pair_count"] += sum(bisect.bisect_left(negative_rhs, -float(b[r])) for r in pos)
            cpos, cneg = Counter(float(b[r]) for r in pos), Counter(float(b[r]) for r in neg)
            stats["zero_float_width_pair_count"] += sum(count * cneg.get(-v, 0) for v, count in cpos.items())
            width = float(b[p]) + float(b[n])
            max_norm_residual = 0.0
        else:
            def scaled_rhs(row):
                return float(b[row]) / float(np.max(np.abs(row_data(A, row)[1])))
            p = min(pos, key=scaled_rhs)
            n = min(neg, key=scaled_rhs)
            pv, nv = row_data(A, p)[1], row_data(A, n)[1]
            width = scaled_rhs(p) + scaled_rhs(n)
            max_norm_residual = float(np.max(np.abs(pv / np.max(np.abs(pv)) + nv / np.max(np.abs(nv)))))
        representative = {"positive_row_0based": int(p), "positive_row_1based": int(p + 1),
                         "negative_row_0based": int(n), "negative_row_1based": int(n + 1),
                         "float_width": width, "normalized_coefficient_residual_inf": max_norm_residual,
                         "pairs_in_signature": len(pos) * len(neg)}
        selected.append(representative)
        if p in attention_rows or n in attention_rows:
            attention_examples.append(representative)
        if (activated is not None and residual is not None and len(row_data(A, p)[0]) >= 4
                and abs(activated[p]) > 1 and abs(activated[n]) > 1
                and abs(residual[p]) <= TOL and abs(residual[n]) <= TOL):
            active_examples.append(representative)
    selected.sort(key=lambda v: (v["float_width"], v["positive_row_0based"], v["negative_row_0based"]))
    stats["narrowest_group_representatives"] = selected[:candidate_cap]
    stats["attention_row_pair_examples"] = attention_examples[:TOP]
    stats["active_large_integer_condition_pair_examples"] = active_examples[:TOP]
    stats["negative_float_width_group_representative_count"] = sum(v["float_width"] < 0 for v in selected)
    del groups
    gc.collect()
    return stats


def exact_pair_certificate(A_original, A_free, p, n, b, is_integer, fixed, free_cols, lb, ub, mode):
    pi, pv = row_data(A_free, p)
    ni, nv = row_data(A_free, n)
    if not np.array_equal(pi, ni):
        return {"verified": False, "reason": "SUPPORTS_DIFFER"}
    scale_p = Fraction(1) if mode == "exact" else 1 / q(np.max(np.abs(pv)))
    scale_n = Fraction(1) if mode == "exact" else 1 / q(np.max(np.abs(nv)))
    rhs_p = exact_integer_rhs(A_original, p, b, is_integer, fixed)
    rhs_n = exact_integer_rhs(A_original, n, b, is_integer, fixed)
    width = scale_p * rhs_p + scale_n * rhs_n
    combo = [(int(free_cols[int(j)]), scale_p * q(vp) + scale_n * q(vn))
             for j, vp, vn in zip(pi, pv, nv)]
    combo = [(j, value) for j, value in combo if value]
    exact_opposite = not combo
    min_lhs = Fraction()
    infinite = False
    for col, value in combo:
        bound = lb[col] if value > 0 else ub[col]
        if not np.isfinite(bound):
            infinite = True
            break
        min_lhs += value * q(bound)
    contradiction = None if infinite else min_lhs > width
    return {"positive_row_0based": p, "positive_row_1based": p + 1,
            "negative_row_0based": n, "negative_row_1based": n + 1,
            "mode": mode, "scale_positive_exact": str(scale_p), "scale_negative_exact": str(scale_n),
            "positive_substituted_rhs_exact": str(rhs_p), "negative_substituted_rhs_exact": str(rhs_n),
            "combined_rhs_exact": str(width), "combined_rhs_float": float(width),
            "exactly_opposite_free_coefficients": exact_opposite,
            "combined_nonzero_free_coefficients": len(combo),
            "box_minimum_lhs_exact": None if infinite else str(min_lhs),
            "box_minimum_lhs_float": None if infinite else float(min_lhs),
            "strict_contradiction_for_this_fixed_integer_assignment": contradiction,
            "contradiction_margin_exact": None if infinite else str(min_lhs - width),
            "scope": "necessary condition of stored binary64 inequalities and original variable bounds after fixing only actual intcon to round(x0); no physical/global infeasibility claim",
            "combined_coefficients": [{"column_0based": j, "column_1based": j + 1, "coefficient_exact": str(v)} for j, v in combo]}


def conditional_pair_example(A, p, n, b, x, is_integer, lhs):
    """One adjacent conditional pair at its archived gate values, not a fix."""
    pi, pv = row_data(A, p)
    ni, nv = row_data(A, n)
    left, right = dict(zip(map(int, pi), pv)), dict(zip(map(int, ni), nv))
    gates = [col for col in sorted(left.keys() & right.keys()) if left[col] * right[col] > 0]
    if not gates:
        return None
    combined = {col: q(left.get(col, 0)) + q(right.get(col, 0)) for col in left.keys() | right.keys()}
    width = q(b[p]) + q(b[n]) - sum((combined[col] * q(x[col]) for col in gates), Fraction())
    remaining = {col: value for col, value in combined.items() if col not in gates and value}
    rp, rn = exact_dot(A, p, x) - q(b[p]), exact_dot(A, n, x) - q(b[n])
    return {"positive_or_first_row_0based": p, "positive_or_first_row_1based": p + 1,
            "negative_or_second_row_0based": n, "negative_or_second_row_1based": n + 1,
            "first_float_residual": float(lhs[p] - b[p]), "second_float_residual": float(lhs[n] - b[n]),
            "first_exact_binary64_residual": str(rp), "second_exact_binary64_residual": str(rn),
            "all_gates_actual_intcon": all(is_integer[col] for col in gates),
            "gates": [{"column_0based": col, "column_1based": col + 1,
                       "actual_intcon": bool(is_integer[col]), "archived_x0_value": float(x[col]),
                       "first_coefficient": float(left[col]), "second_coefficient": float(right[col])} for col in gates],
            "width_after_conditioning_gates_to_x0_exact": str(width),
            "width_after_conditioning_gates_to_x0_float": float(width),
            "remaining_coefficients_exactly_opposite": not remaining,
            "remaining_sum_coefficients": [{"column_0based": col, "column_1based": col + 1,
                                            "coefficient_exact": str(value)} for col, value in sorted(remaining.items())],
            "contradiction_only_for_this_gate_slice": not remaining and width < 0,
            "scope": "illustrative gate slice at archived x0, not proposed fixing of auxiliary variables; not a fixed-actual-intcon infeasibility conclusion"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="matrix_inspection.json", help="new output path inside this inspection directory; never overwritten")
    args = parser.parse_args()
    out = Path(args.out)
    out = (out if out.is_absolute() else HERE / out).resolve()
    if not out.is_relative_to(HERE.resolve()):
        raise ValueError("Output must stay inside this inspection directory")
    if out.exists():
        raise FileExistsError("Refusing to overwrite prior inspection evidence: " + str(out))
    started = time.perf_counter()
    original_sha = sha(MAT)
    loaded = loadmat(MAT, variable_names=["A", "b", "x0", "lb", "ub", "intcon", "c"], struct_as_record=False)
    A = loaded.pop("A").tocsr()
    A.sort_indices()
    A.eliminate_zeros()
    b, x = loaded["b"].reshape(-1), loaded["x0"].reshape(-1)
    lb, ub, c = [loaded[key].reshape(-1) for key in ("lb", "ub", "c")]
    raw_intcon = loaded["intcon"].reshape(-1)
    if (not np.all(np.isfinite(raw_intcon)) or not np.all(raw_intcon == np.floor(raw_intcon))
            or not np.all((raw_intcon >= 1) & (raw_intcon <= A.shape[1]))
            or len(np.unique(raw_intcon)) != len(raw_intcon)):
        raise ValueError("Invalid or duplicate actual intcon indices")
    integer_cols = raw_intcon.astype(np.int64) - 1
    if not np.all((x[integer_cols] == 0) | (x[integer_cols] == 1)):
        raise ValueError("Archived x0 actual integer coordinates are not exactly binary")
    is_integer = np.zeros(A.shape[1], dtype=bool)
    is_integer[integer_cols] = True
    fixed = np.zeros(A.shape[1], dtype=np.int64)
    fixed[integer_cols] = x[integer_cols].astype(np.int64)
    free_cols = np.flatnonzero(~is_integer)
    lhs = np.asarray(A @ x).reshape(-1)
    residual = lhs - b
    absolute_sum = np.asarray(abs(A) @ abs(x)).reshape(-1)
    unit_roundoff = np.finfo(float).eps / 2
    operation_count = 2 * np.diff(A.indptr).astype(float) + 2
    gamma = operation_count * unit_roundoff / (1 - operation_count * unit_roundoff)
    # Standard floating-point dot/subtraction bound. Inflate the computed
    # positive magnitude sum to allow its own rounding; not interval software.
    arithmetic_bound = np.nextafter(gamma * (absolute_sum + abs(b)) / (1 - gamma), np.inf)
    cancellation = np.divide(absolute_sum, np.abs(lhs), out=np.full_like(lhs, np.inf), where=lhs != 0)
    cancellation[(absolute_sum == 0) & (lhs == 0)] = 1
    tight = abs(residual) <= TOL
    nnz = np.diff(A.indptr)
    padded_abs = np.r_[abs(A.data), 0.0]
    row_max = np.maximum.reduceat(padded_abs, A.indptr[:-1])
    padded_abs[-1] = np.inf
    row_min = np.minimum.reduceat(padded_abs, A.indptr[:-1])
    row_max[nnz == 0], row_min[nnz == 0] = 0.0, np.inf
    span = np.divide(row_max, row_min, out=np.zeros_like(row_max), where=np.isfinite(row_min) & (row_min > 0))
    integer_contribution = np.asarray(A[:, integer_cols] @ fixed[integer_cols]).reshape(-1)
    reduced_rhs = b - integer_contribution
    Afree = A[:, free_cols].tocsr()
    Afree.eliminate_zeros()
    free_nnz = np.diff(Afree.indptr)
    pure_integer = np.flatnonzero(free_nnz == 0)
    reduced_residual = np.asarray(Afree @ x[free_cols]).reshape(-1) - reduced_rhs
    core_rows = set(rows_top(residual) + rows_top(span) + rows_top(absolute_sum))
    finite_cancel = cancellation.copy()
    finite_cancel[~np.isfinite(finite_cancel)] = np.finfo(float).max
    core_rows.update(rows_top(finite_cancel, 12))
    important = sorted(core_rows, key=lambda r: (-residual[r], -span[r], r))[:EXACT_ROW_CAP]
    details = [detail(A, r, b, x, lhs, absolute_sum) for r in important]
    exact_full_pairs = pair_groups(A, b, mode="exact")
    near_full_pairs = pair_groups(A, b, mode="near")
    exact_free_pairs = pair_groups(Afree, reduced_rhs, mode="exact", candidate_cap=PAIR_CERT_CAP,
                                  attention_rows=important, activated=integer_contribution, residual=residual,
                                  rhs_semantics="scratch reduced_rhs=fl(b-fl(A_integer*z0)); aggregate widths are floating diagnostics only")
    near_free_pairs = pair_groups(Afree, reduced_rhs, mode="near", candidate_cap=PAIR_CERT_CAP,
                                 rhs_semantics="scratch reduced_rhs=fl(b-fl(A_integer*z0)); aggregate widths are floating diagnostics only")
    pair_certificates = []
    for mode, facts in (("exact", exact_free_pairs), ("near", near_free_pairs)):
        examples = (facts["narrowest_group_representatives"]
                    + facts["attention_row_pair_examples"]
                    + facts["active_large_integer_condition_pair_examples"])
        seen = set()
        for pair in examples:
            identity = (pair["positive_row_0based"], pair["negative_row_0based"])
            if identity in seen:
                continue
            seen.add(identity)
            pair_certificates.append(exact_pair_certificate(A, Afree,
                pair["positive_row_0based"], pair["negative_row_0based"], b, is_integer, fixed, free_cols, lb, ub, mode))
    pure_candidates = sorted((int(r) for r in pure_integer if reduced_rhs[r] <= TOL), key=lambda r: (reduced_rhs[r], r))
    all_pure_exact_rhs = [(int(r), exact_integer_rhs(A, int(r), b, is_integer, fixed)) for r in pure_integer]
    pure_exact = [{"row_0based": r, "row_1based": r + 1, "float_rhs_after_substitution": float(reduced_rhs[r]),
                   "exact_rhs_after_substitution": str(exact_integer_rhs(A, r, b, is_integer, fixed)),
                   "strict_contradiction_for_fixed_intcon": exact_integer_rhs(A, r, b, is_integer, fixed) < 0}
                  for r in pure_candidates[:EXACT_ROW_CAP]]
    conditional_examples = []
    seen_adjacent = set()
    for row in rows_top(residual):
        p = row if row % 2 == 0 else row - 1
        n = p + 1
        if n >= A.shape[0] or (p, n) in seen_adjacent:
            continue
        seen_adjacent.add((p, n))
        example = conditional_pair_example(A, p, n, b, x, is_integer, lhs)
        if example is not None:
            conditional_examples.append(example)
    source_preserved = sha(MAT) == original_sha
    output = {
        "protocol": "K188-archived-binary64-matrix-inspection-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(MAT), "sha256_before": original_sha, "sha256_after": sha(MAT),
                   "source_bytes_preserved": source_preserved, "bytes": MAT.stat().st_size},
        "index_convention": "all indices explicitly labelled; original MATLAB intcon is one-based and converted once",
        "scope": "pure sparse arithmetic on archived arrays; no model reconstruction, optimization, MATLAB, heat integration, or candidate evaluation",
        "scientific_calls": 0,
        "shape": {"rows": A.shape[0], "columns": A.shape[1], "nonzeros": int(A.nnz),
                  "integer_columns": int(len(integer_cols)), "continuous_columns": int(len(free_cols))},
        "coefficient_absolute": summary(abs(A.data)), "rhs": summary(b), "x0": summary(x),
        "row_nnz": summary(nnz), "row_coefficient_span": summary(span[nnz > 0]),
        "largest_span_rows_0based": rows_top(span),
        "lhs": summary(lhs), "row_residual_lhs_minus_rhs": summary(residual),
        "absolute_product_sum": summary(absolute_sum), "cancellation_ratio_finite": summary(cancellation[np.isfinite(cancellation)]),
        "infinite_cancellation_with_nonzero_terms_count": int(np.count_nonzero(~np.isfinite(cancellation) & (absolute_sum > 0))),
        "row_acceptance_at_x0": {"constraint_tolerance": TOL, "float_residual_positive_count": int(np.count_nonzero(residual > 0)),
            "float_residual_above_tolerance_count": int(np.count_nonzero(residual > TOL)),
            "tight_abs_residual_at_tolerance_count": int(np.count_nonzero(tight)),
            "float_residual_exact_zero_count": int(np.count_nonzero(residual == 0)),
            "tight_abs_residual_1e_minus_14_count": int(np.count_nonzero(abs(residual) <= 1e-14)),
            "max_residual_rows_0based": rows_top(residual)},
        "standard_roundoff_bound": {"formula": "gamma_(2*nnz+2)*(fl(sum(abs(a_j*x_j)))+abs(b))/(1-gamma), nextafter toward +infinity",
            "unit_roundoff": unit_roundoff, "scope": "standard finite IEEE binary64 nearest-rounding error model; no overflow/underflow; not a formally outward interval certificate",
            "bounds": summary(arithmetic_bound),
            "float_positive_residual_above_bound_count": int(np.count_nonzero(residual > arithmetic_bound)),
            "selected_exact_residuals_within_absolute_roundoff_bound": all(abs(v["dot_rounding_difference_from_exact"]) <= arithmetic_bound[v["row_0based"]] for v in details)},
        "x0_admission": {"objective_float": float(c @ x),
            "max_lower_bound_violation": float(np.max(lb - x)), "max_upper_bound_violation": float(np.max(x - ub)),
            "max_actual_integer_distance": float(np.max(abs(x[integer_cols] - fixed[integer_cols]))),
            "actual_integer_one_columns_0based": [int(i) for i in integer_cols[fixed[integer_cols] == 1]],
            "actual_integer_one_columns_1based": [int(i + 1) for i in integer_cols[fixed[integer_cols] == 1]],
            "integer_values_count": {str(int(v)): int(n) for v, n in zip(*np.unique(fixed[integer_cols], return_counts=True))}},
        "fixed_actual_intcon": {"fixed_columns_count": int(len(integer_cols)),
            "remaining_non_intcon_columns": int(len(free_cols)),
            "inspection_only": "integer columns removed only in scratch sparse arithmetic to inventory structure; no production row/column removal or model rewrite",
            "free_A_nonzeros": int(Afree.nnz), "eliminated_nonzeros": int(A.nnz - Afree.nnz),
            "rows_with_free_coefficients": int(np.count_nonzero(free_nnz)), "pure_integer_or_empty_rows_count": int(len(pure_integer)),
            "rows_with_negative_float_rhs_and_no_free_coefficients": [int(r) for r in pure_integer if reduced_rhs[r] < 0],
            "rhs_after_substitution": summary(reduced_rhs), "free_row_residual": summary(reduced_residual),
            "max_abs_change_in_x0_residual_due_to_substitution_order": float(np.max(abs(residual - reduced_residual))),
            "unused_continuous_columns_count": int(np.count_nonzero(np.diff(Afree.tocsc().indptr) == 0)),
            "continuous_columns_already_fixed_by_original_bounds_count": int(np.count_nonzero(lb[free_cols] == ub[free_cols])),
            "pure_integer_rows_exact_checked": pure_exact,
            "pure_integer_near_zero_rhs_candidates": len(pure_candidates), "pure_integer_detailed_example_cap": EXACT_ROW_CAP,
            "pure_integer_all_rows_rationally_checked": len(all_pure_exact_rhs),
            "pure_integer_all_rows_satisfied_at_fixed_values": all(rhs >= 0 for _, rhs in all_pure_exact_rhs),
            "pure_integer_exact_negative_rhs_rows": [{"row_0based": r, "row_1based": r + 1, "rhs_exact": str(rhs)} for r, rhs in all_pure_exact_rhs if rhs < 0],
            "pure_integer_exact_zero_rhs_count": sum(rhs == 0 for _, rhs in all_pure_exact_rhs)},
        "preconditions_verified_before_integer_substitution": {"intcon_indices_finite_integer_unique_in_range": True,
            "x0_actual_intcon_exactly_in_0_1": True, "no_rounding_or_repair": True},
        "selected_row_exact_checks": details,
        "full_matrix_exact_opposite_pairs": exact_full_pairs,
        "full_matrix_near_opposite_candidates": near_full_pairs,
        "fixed_integer_exact_opposite_pairs": exact_free_pairs,
        "fixed_integer_near_opposite_candidates": near_free_pairs,
        "fixed_integer_pair_rational_certificates": pair_certificates,
        "rational_pair_certificate_scope": "selected representative pairs only, not a complete rational LP feasibility or infeasibility certificate",
        "tight_adjacent_conditional_pair_examples": conditional_examples,
        "strict_fixed_configuration_pair_contradictions_found": sum(row.get("strict_contradiction_for_this_fixed_integer_assignment") is True for row in pair_certificates),
        "limitations": ["near-pair bucket scan is not exhaustive for all possible row combinations",
            "small rational checks treat stored binary64 coefficients exactly; physical interval-row validity is a separate question",
            "a fixed-configuration contradiction does not establish full-domain infeasibility, physical unsafety, or a solver defect",
            "no feasible point other than archived x0 is generated or searched"],
        "analysis_wall_seconds": time.perf_counter() - started,
    }
    HERE.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"written": str(out), "source_preserved": source_preserved,
                      "shape": output["shape"], "max_x0_residual": float(residual.max()),
                      "fixed_pair_contradictions": output["strict_fixed_configuration_pair_contradictions_found"],
                      "wall_seconds": output["analysis_wall_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
