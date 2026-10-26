"""Handwritten numerical fixtures only; no original workload or native solver."""
from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
from scipy.io import loadmat, savemat

import core


def fixture():
    # y=1 fixes only coordinate 0. t may move throughout [0, 2].
    return dict(c=np.array([2., 1., 0.]),
        A=sparse.csc_matrix([[0., 1., 0.], [0., -1., 0.]]),
        b=np.array([2., 0.]), Aeq=sparse.csc_matrix([[0., 0., 1.]]),
        beq=np.array([.5]), lb=np.array([0., 0., -.5]),
        ub=np.array([1., 3., 1.]), intcon=np.array([0], dtype=np.int64),
        x0=np.array([1., 1., .5]))


def load_handwritten_mat(source, *, hashes=('fixture-sha', 'fixture-sha')):
    """Use real MAT serialization without relying on Windows temp ACLs."""
    stream = BytesIO()
    savemat(stream, source)
    data = stream.getvalue()
    def read_memory(_path, **kwargs):
        return loadmat(BytesIO(data), **kwargs)
    with patch.object(core, '_sha_file', side_effect=hashes), \
            patch.object(core, 'loadmat', side_effect=read_memory):
        return core.load_original_mat('handwritten-fixture.mat')


class PureCoreTests(unittest.TestCase):
    def test_only_actual_integer_bounds_change(self):
        original = fixture()
        before = deepcopy(original)
        fixed, receipt = core.fix_actual_intcon(original)
        self.assertTrue(receipt['passed'])
        self.assertEqual(fixed['lb'][0], 1.)
        self.assertEqual(fixed['ub'][0], 1.)
        self.assertTrue(np.array_equal(original['lb'], before['lb']))
        self.assertTrue(np.array_equal(original['ub'], before['ub']))
        self.assertIsNot(fixed['A'], original['A'])
        self.assertIsNot(fixed['x0'], original['x0'])
        self.assertTrue(core.assert_only_fixed_integer_bounds_changed(original, fixed)['passed'])

    def test_load_one_based_converts_once(self):
        source = fixture()
        source['intcon'] = np.array([1.])
        original, receipt = load_handwritten_mat(source)
        self.assertEqual(original['intcon'].tolist(), [0])
        self.assertTrue(receipt['source_unchanged'])
        self.assertEqual(receipt['conversion_count'], 1)
        fixed, _ = core.fix_actual_intcon(original)
        self.assertEqual(fixed['lb'][0], 1.)

    def test_bad_one_based_indices(self):
        for indices in ([0.], [4.], [1.5], [1., 1.], [np.nan], [np.inf]):
            with self.subTest(indices=indices):
                source = fixture(); source['intcon'] = np.array(indices)
                with self.assertRaises(ValueError):
                    load_handwritten_mat(source)

    def test_source_drift_during_load_rejected(self):
        source = fixture(); source['intcon'] = np.array([1.])
        with self.assertRaises(ValueError):
            load_handwritten_mat(source, hashes=('before', 'after'))

    def test_zero_based_out_of_range_rejected(self):
        for indices in ([-1], [3], [0, 0], [.5]):
            with self.subTest(indices=indices):
                source = fixture(); source['intcon'] = np.array(indices)
                with self.assertRaises(ValueError):core.fix_actual_intcon(source)

    def test_near_binary_x0_cannot_be_fixed_by_rounding(self):
        for value in (1. - 1e-8, 1. + 1e-10, .5, -1e-12):
            with self.subTest(value=value):
                source = fixture(); source['x0'][0] = value
                with self.assertRaises(ValueError):core.fix_actual_intcon(source)

    def test_binary_x0_must_be_inside_original_bound(self):
        source = fixture(); source['ub'][0] = 1. - 1e-12
        with self.assertRaises(ValueError):core.fix_actual_intcon(source)

    def test_original_x0_admitted_without_fval(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        report = core.verify_vector(original['x0'], original, fixed, require_objective=False)
        self.assertTrue(report['accepted'])
        self.assertTrue(report['vector_equals_original_x0_bitwise'])
        self.assertFalse(report['rounding_or_repair_performed'])

    def test_auxiliary_change_allowed_with_original_objective(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        vector = np.array([1., 1.5, .5])
        self.assertTrue(core.verify_vector(vector, original, fixed, 3.5)['accepted'])
        self.assertFalse(core.verify_vector(vector, original, fixed, 3.)['accepted'])

    def test_returned_choice_change_rejected_by_fixed_bound(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        report = core.verify_vector([0., 1., .5], original, fixed, 1.)
        self.assertTrue(report['original']['accepted'])
        self.assertFalse(report['fixed']['accepted'])
        self.assertFalse(report['accepted'])

    def test_small_fixed_bound_violation_not_repaired(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        vector = np.array([1. - 2e-9, 1., .5]); before = vector.copy()
        report = core.verify_vector(vector, original, fixed, 2 * vector[0] + 1.)
        self.assertFalse(report['accepted'])
        self.assertGreater(report['fixed']['lower_bound_violation'], 1e-9)
        self.assertLess(report['original']['integer_violation'], 1e-6)
        self.assertTrue(np.array_equal(vector, before))

    def test_tolerated_near_integer_is_not_replaced(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        vector = np.array([1. - 1e-10, 1., .5]); before = vector.copy()
        report = core.verify_vector(vector, original, fixed, 2 * vector[0] + 1.)
        self.assertTrue(report['accepted'])
        self.assertFalse(report['vector_equals_original_x0_bitwise'])
        self.assertGreater(report['fixed']['integer_violation'], 0.)
        self.assertTrue(np.array_equal(vector, before))

    def test_original_inequality_rejection(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        report = core.verify_vector([1., 2. + 2e-9, .5], original, fixed, 4. + 2e-9)
        self.assertFalse(report['accepted'])
        self.assertGreater(report['original']['inequality_violation'], 1e-9)

    def test_original_equality_rejection(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        report = core.verify_vector([1., 1., .5 + 2e-9], original, fixed, 3.)
        self.assertFalse(report['accepted'])
        self.assertGreater(report['original']['equality_violation'], 1e-9)

    def test_empty_equality_matrix(self):
        original = fixture(); original['Aeq'] = sparse.csc_matrix((0, 3))
        original['beq'] = np.array([])
        fixed, _ = core.fix_actual_intcon(original)
        self.assertTrue(core.verify_vector(original['x0'], original, fixed, 3.)['accepted'])

    def test_invalid_vector_shape_dimension_and_values(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        for vector in ([], [1., 1.], [1., np.nan, .5], [1., np.inf, .5],
                       [1., 1j, .5], np.ones((2, 2))):
            with self.subTest(vector=str(vector)):
                self.assertFalse(core.verify_vector(vector, original, fixed, 3.)['accepted'])

    def test_missing_invalid_or_inconsistent_objective(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        for objective in (None, [], [3., 3.], float('nan'), float('inf'), 3j, 4.):
            with self.subTest(objective=objective):
                self.assertFalse(core.verify_vector(original['x0'], original, fixed, objective)['accepted'])

    def test_unpermitted_changes_are_rejected(self):
        original = fixture(); fixed, _ = core.fix_actual_intcon(original)
        for key in ('c', 'b', 'beq', 'intcon', 'x0', 'A', 'Aeq', 'lb', 'ub'):
            with self.subTest(key=key):
                changed = deepcopy(fixed)
                if key in ('A', 'Aeq'):changed[key].data[0] += .01
                elif key in ('lb', 'ub'):changed[key][1] += .01
                else:changed[key][0] += 1
                with self.assertRaises(ValueError):
                    core.assert_only_fixed_integer_bounds_changed(original, changed)

    def test_original_signed_zero_coefficients_not_changed(self):
        original = fixture(); original['c'][2] = -0.
        fixed, _ = core.fix_actual_intcon(original)
        changed = deepcopy(fixed); changed['c'][2] = 0.
        with self.assertRaises(ValueError):
            core.assert_only_fixed_integer_bounds_changed(original, changed)


if __name__ == '__main__':
    unittest.main()
