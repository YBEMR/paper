"""K133 offline payload checks. Never invokes production, MATLAB or a solver."""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from scipy import sparse
from scipy.io import loadmat

sys.dont_write_bytecode = True
from augmented_payload import (append_complements, build_augmented_payload,
                               validate_projected_vector)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUDIT = HERE / 'results/numerical_conflict_audit01'
SOURCE = HERE / 'results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat'
LABELS = AUDIT / 'row_trace/labels.json'
ARRAY_KEYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_fingerprint(payload):
    result = hashlib.sha256()
    for key in ARRAY_KEYS:
        result.update(key.encode('ascii'))
        value = payload[key]
        if sparse.issparse(value):
            value = value.tocsr()
            arrays = [np.array(value.shape, dtype='<i8'),
                      value.indptr.astype('<i8'), value.indices.astype('<i8'),
                      value.data.astype('<f8')]
        else:
            value = np.asarray(value)
            arrays = [np.array(value.shape, dtype='<i8'), value.astype('<f8')]
        for item in arrays:
            result.update(item.tobytes())
    return result.hexdigest()


def toy():
    return ({'c': np.array([2., 0., 5.]),
             'A': sparse.csr_matrix([[1., 64., 0.], [-1., 32., 0.], [0., 1., -1.]]),
             'b': np.array([65., 32., 0.]),
             'Aeq': sparse.csr_matrix([[1., 0., 2.]]), 'beq': np.array([2.5]),
             'lb': np.zeros(3), 'ub': np.array([2., 1., 1.]),
             'intcon': np.array([2])},
            {'names': ['y', 'w:continuous', 'z:integer'],
             'row_tags': ['thermal_propagation/upper', 'complete_energy/lower',
                          'unchanged_logic']})


def exact_residuals_equal(old, new, x, xnew):
    """Exact binary64-as-rational row checks, including continuous gate values."""
    original_values = [F.from_float(float(v)) for v in x]
    augmented_values = [F.from_float(float(v)) for v in xnew]
    equal = 0
    for i in range(old['A'].shape[0]):
        def residual(payload, values):
            a = payload['A']
            return sum((F.from_float(float(a.data[k])) * values[a.indices[k]]
                        for k in range(a.indptr[i], a.indptr[i + 1])), F(0)) - F.from_float(float(payload['b'][i]))
        equal += residual(old, original_values) == residual(new, augmented_values)
    return int(equal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=HERE / 'results/augmented_payload_precheck01')
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if not out.is_relative_to(ROOT.resolve()):
        raise ValueError('output must stay within this workspace')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    checks = []
    details = {}

    def check(name, condition, **evidence):
        checks.append({'name': name, 'passed': bool(condition), **evidence})
        if not condition:
            raise AssertionError(name)

    def rejects(name, operation, match=None):
        try:
            operation()
        except (TypeError, ValueError) as exc:
            check(name, match is None or match in str(exc), error=str(exc))
        else:
            check(name, False)

    error = None
    try:
        original, labels = toy()
        before = array_fingerprint(original)
        augmented, meta = build_augmented_payload(original, labels)
        check('toy_single_continuous_gate_added', meta['new_variables'] == 1
              and meta['gate_columns'] == [1] and meta['new_columns'] == [3]
              and np.array_equal(augmented['intcon'], [2]))
        check('toy_nonempty_Aeq_prefix_preserved', augmented['Aeq'].shape == (2, 4)
              and (augmented['Aeq'][:1, :3] != original['Aeq']).nnz == 0
              and augmented['Aeq'][:1, 3:].nnz == 0
              and np.array_equal(augmented['beq'][:1], original['beq']))
        check('toy_nonphysical_row_preserved',
              (augmented['A'][2:3, :3] != original['A'][2:3]).nnz == 0
              and augmented['A'][2:3, 3:].nnz == 0
              and augmented['b'][2] == original['b'][2])
        x = np.array([.5, .75, 1.])
        xnew = append_complements(x, meta)
        prefix, validation = validate_projected_vector(xnew, original, augmented, meta)
        check('toy_final_and_callback_projection_accepted', validation['accepted']
              and np.array_equal(prefix.view(np.uint64), x.view(np.uint64)))
        check('toy_continuous_gate_exact_residuals',
              exact_residuals_equal(original, augmented, x, xnew) == 3)
        check('toy_original_objective_and_integer_indices_preserved',
              np.array_equal(augmented['c'], [2., 0., 5., 0.])
              and validation['original']['objective'] == validation['augmented']['objective'] == 6.)
        check('toy_inputs_not_mutated', before == array_fingerprint(original))
        # Construct an augmented-acceptable vector whose original physical row
        # fails: link epsilon=5e-10 times M=64 gives 3.2e-8 in the old row.
        trap = {'c': np.array([1., 0.]), 'A': sparse.csr_matrix([[1., 64.]]),
                'b': np.array([64.]), 'Aeq': sparse.csr_matrix((0, 2)),
                'beq': np.array([]), 'lb': np.zeros(2), 'ub': np.array([1., 1.]),
                'intcon': np.array([], dtype=int)}
        trap_labels = {'names': ['y', 'w:gate'], 'row_tags': ['complete_energy/upper']}
        trap_new, trap_meta = build_augmented_payload(trap, trap_labels)
        trap_x = np.array([64 * 5e-10, 1., 5e-10])
        trap_prefix, trap_report = validate_projected_vector(trap_x, trap, trap_new, trap_meta)
        check('link_tolerance_cannot_false_admit_original_violation',
              trap_report['augmented']['accepted'] and trap_report['link_accepted']
              and not trap_report['original']['accepted'] and not trap_report['accepted']
              and trap_prefix is None,
              original_violation=trap_report['original']['inequality_violation'],
              augmented_violation=trap_report['augmented']['inequality_violation'],
              link_violation=trap_report['link_max_abs_residual'])
        details['link_tolerance_trap'] = trap_report
        nonrepresentable = deepcopy(trap)
        nonrepresentable['A'] = sparse.csr_matrix([[1., 2.**-54]])
        nonrepresentable['b'] = np.array([1.])
        rejects('nonrepresentable_binary64_rhs_rejected',
                lambda: build_augmented_payload(nonrepresentable, trap_labels), 'not exactly representable')
        multi_labels = deepcopy(labels)
        multi_labels['names'][2] = 'w:another'
        multi = deepcopy(original)
        multi['A'] = sparse.csr_matrix([[1., 64., 1.], [-1., 32., 0.], [0., 1., -1.]])
        rejects('multiple_gate_physical_row_rejected',
                lambda: build_augmented_payload(multi, multi_labels), 'exactly one')
        no_gate = deepcopy(trap)
        no_gate['A'] = sparse.csr_matrix([[1., 0.]])
        rejects('missing_gate_physical_row_rejected',
                lambda: build_augmented_payload(no_gate, trap_labels), 'exactly one')
        bad_labels = deepcopy(labels)
        bad_labels['row_tags'].pop()
        rejects('illegal_label_length_rejected', lambda: build_augmented_payload(original, bad_labels), 'labels')
        bad_rhs = deepcopy(original)
        bad_rhs['b'] = np.array([1.])
        rejects('illegal_rhs_length_rejected', lambda: build_augmented_payload(bad_rhs, labels), 'length')
        bad_eq = deepcopy(original)
        bad_eq['beq'] = np.array([])
        rejects('illegal_Aeq_rhs_length_rejected', lambda: build_augmented_payload(bad_eq, labels), 'length')
        bad_int = deepcopy(original)
        bad_int['intcon'] = np.array([3])
        rejects('one_based_or_out_of_range_intcon_rejected',
                lambda: build_augmented_payload(bad_int, labels), 'zero-based')
        integer_gate = deepcopy(original)
        integer_gate['intcon'] = np.array([1, 2])
        rejects('integer_joint_gate_rejected',
                lambda: build_augmented_payload(integer_gate, labels), 'continuous')
        rejects('illegal_x0_length_rejected', lambda: append_complements(x[:-1], meta), 'length')
        for name, value in [('short', xnew[:-1]), ('nonfinite', [0., .75, 1., np.nan]),
                            ('complex', xnew.astype(complex) + 1j),
                            ('matrix', np.ones((2, 2)))]:
            prefix_bad, report_bad = validate_projected_vector(value, original, augmented, meta)
            check(f'illegal_{name}_callback_or_final_rejected', prefix_bad is None and not report_bad['accepted'])
        rejects('relaxed_constraint_tolerance_rejected',
                lambda: validate_projected_vector(xnew, original, augmented, meta,
                                                   constraint_tolerance=1e-8), 'unchanged')
        violated_link = xnew.copy()
        violated_link[-1] += 1e-5
        rejected_prefix, rejected_report = validate_projected_vector(violated_link, original, augmented, meta)
        check('link_failure_rejects_projection', rejected_prefix is None
              and not rejected_report['link_accepted'] and not rejected_report['accepted'])
        violated_integer = xnew.copy()
        violated_integer[2] -= 1e-5
        rejected_prefix, rejected_report = validate_projected_vector(violated_integer, original, augmented, meta)
        check('original_integer_tolerance_enforced', rejected_prefix is None
              and rejected_report['original']['integer_violation'] > 1e-6)

        facts = json.loads((AUDIT / 'numeric_route/facts.json').read_text(encoding='utf-8'))
        comparison = json.loads((AUDIT / 'row_trace/rebuild_comparison.json').read_text(encoding='utf-8'))
        source_sha, labels_sha = digest(SOURCE), digest(LABELS)
        check('archived_mat_and_matched_labels_SHA_match_K132',
              source_sha == facts['source_sha256'] and labels_sha == facts['labels_sha256']
              and comparison['all_arrays_identical'] is True and comparison['labels_usable'] is True,
              source_sha256=source_sha, labels_sha256=labels_sha)
        check('K132_route_script_SHA_matches_facts',
              digest(AUDIT / 'numeric_route/audit_saved_affine_route.py') == facts['script_sha256'])
        mat = loadmat(SOURCE)
        saved = {key: (mat[key].tocsr() if sparse.issparse(mat[key])
                        else np.asarray(mat[key]).reshape(-1)) for key in ARRAY_KEYS}
        saved['intcon'] = saved['intcon'].astype(np.int64) - 1
        labels = json.loads(LABELS.read_text(encoding='utf-8'))
        x0 = np.asarray(mat['x0']).reshape(-1)
        before = array_fingerprint(saved)
        adapted, mapping = build_augmented_payload(saved, labels)
        x0new = append_complements(x0, mapping)
        prefix, x0report = validate_projected_vector(x0new, saved, adapted, mapping)
        route = facts['physical_alias_only']
        check('archive_counts_match_K132',
              len(saved['c']) == facts['n'] == 8525
              and saved['A'].shape == (39733, 8525) and saved['A'].nnz == facts['nnz'] == 357483
              and len(saved['intcon']) == 441
              and mapping['new_variables'] == route['new_alias_variables'] == 2400
              and mapping['physical_rows_rewritten'] == route['eligible_physical_rows'] == 24000
              and mapping['nonphysical_rows_unchanged'] == 15733
              and len(adapted['c']) == route['new_total_variables'] == 10925
              and adapted['A'].shape == (39733, 10925)
              and adapted['Aeq'].shape == (2400, 10925)
              and adapted['A'].nnz == route['new_inequality_nnz'] == 357483
              and adapted['Aeq'].nnz == route['new_equality_nnz'] == 4800)
        physical = np.zeros(saved['A'].shape[0], dtype=bool)
        physical[mapping['physical_rows']] = True
        check('archive_15733_nonphysical_rows_and_rhs_preserved',
              (adapted['A'][~physical, :8525] != saved['A'][~physical]).nnz == 0
              and adapted['A'][~physical, 8525:].nnz == 0
              and np.array_equal(adapted['b'][~physical], saved['b'][~physical]))
        exact_rhs_count = sum(F.from_float(float(adapted['b'][i]))
                              + F.from_float(float(coefficient))
                              == F.from_float(float(saved['b'][i]))
                              for i, coefficient in zip(mapping['physical_rows'],
                                                        mapping['physical_gate_coefficients']))
        check('archive_24000_rhs_restore_exactly', exact_rhs_count == 24000)
        check('archive_objective_bounds_and_441_integer_indices_preserved',
              np.array_equal(adapted['c'][:8525].view(np.uint64), saved['c'].view(np.uint64))
              and not adapted['c'][8525:].any()
              and np.array_equal(adapted['lb'][:8525].view(np.uint64), saved['lb'].view(np.uint64))
              and np.array_equal(adapted['ub'][:8525].view(np.uint64), saved['ub'].view(np.uint64))
              and np.array_equal(adapted['intcon'], saved['intcon']))
        check('archive_original_x0_prefix_bitwise_unchanged_and_numerically_accepted',
              x0report['accepted'] and prefix is not None
              and np.array_equal(x0new[:8525].view(np.uint64), x0.view(np.uint64))
              and x0report['link_max_abs_residual'] == 0.)
        sample = x0.copy()
        sample[mapping['gate_columns']] = [.25 if k % 2 else .75
                                           for k in range(mapping['new_variables'])]
        sample_new = append_complements(sample, mapping)
        exact_equal = exact_residuals_equal(saved, adapted, sample, sample_new)
        check('archive_all_39733_continuous_gate_exact_residuals_equal', exact_equal == 39733)
        check('archive_all_2400_continuous_sample_links_exact',
              all(F.from_float(float(sample[j])) + F.from_float(float(sample_new[k])) == 1
                  for j, k in zip(mapping['gate_columns'], mapping['new_columns'])))
        check('archive_inputs_not_mutated', before == array_fingerprint(saved)
              and source_sha == digest(SOURCE) and labels_sha == digest(LABELS))
        details['archive'] = {
            'source_sha256': source_sha, 'labels_sha256': labels_sha,
            'original_payload_fingerprint': before,
            'augmented_payload_fingerprint': array_fingerprint(adapted),
            'x0_validation': x0report,
            'counts': {key: mapping[key] for key in
                       ('original_n', 'augmented_n', 'original_inequality_rows',
                        'original_eq_rows', 'new_variables', 'new_link_equalities',
                        'physical_rows_rewritten', 'nonphysical_rows_unchanged')},
            'exact_continuous_sample_equal_rows': exact_equal,
        }
    except Exception:
        error = traceback.format_exc()
    report = {'stage': 'K133_offline_payload_precheck',
              'passed': error is None and all(v['passed'] for v in checks),
              'check_count': len(checks), 'passed_count': sum(v['passed'] for v in checks),
              'checks': checks, 'details': details, 'error': error,
              'wall_s': time.monotonic() - started,
              'solver_calls': 0, 'MATLAB_startups': 0, 'production_model_builds': 0,
              'research_method_calls': 0, 'candidate_thermal_evaluations': 0,
              'existing_SAFE_changed': False,
              'module_sha256': digest(HERE / 'augmented_payload.py'),
              'precheck_script_sha256': digest(Path(__file__))}
    (out / 'checks.json').write_text(json.dumps(report, ensure_ascii=False,
                                               indent=2, allow_nan=False) + '\n',
                                    encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks),
                      'wall_s': report['wall_s'], 'output': str(out), 'error': error},
                     ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
