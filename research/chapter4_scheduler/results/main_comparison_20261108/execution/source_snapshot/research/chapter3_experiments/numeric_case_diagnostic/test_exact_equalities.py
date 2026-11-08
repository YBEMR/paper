"""Hand-made algebraic examples only; no numerical optimizer or heat calls."""
import copy
import unittest

import numpy as np
from scipy import sparse

from exact_equalities import transform, verify_equivalence


def payload(rows, rhs, *, existing_eq=None, existing_rhs=None):
    n = len(rows[0])
    return {'c': np.arange(1, n+1, dtype=np.float64),
            'A': sparse.csc_matrix(np.asarray(rows, dtype=np.float64)),
            'b': np.asarray(rhs, dtype=np.float64),
            'Aeq': sparse.csc_matrix((0, n)) if existing_eq is None else sparse.csc_matrix(np.asarray(existing_eq, dtype=np.float64)),
            'beq': np.asarray([] if existing_rhs is None else existing_rhs, dtype=np.float64),
            'lb': np.full(n, -10.0), 'ub': np.full(n, 10.0),
            'intcon': np.array([0], dtype=np.int64), 'x0': np.zeros(n)}


class ExactEqualityTests(unittest.TestCase):
    def test_true_equality_and_original_equations(self):
        original = payload([[1, 2], [-1, -2], [1, 0]], [3, -3, 5],
                           existing_eq=[[0, 1]], existing_rhs=[1])
        new, cert = transform(original)
        self.assertEqual(cert['original_le_pair_to_new_eq'], [[0, 1, 1]])
        self.assertEqual(new['A'].shape, (1, 2))
        self.assertEqual(new['Aeq'].shape, (2, 2))
        np.testing.assert_array_equal(new['Aeq'].toarray(), [[0, 1], [1, 2]])
        for key in ('c', 'lb', 'ub', 'intcon', 'x0'):
            self.assertEqual(new[key].tobytes(), original[key].tobytes())

    def test_tiny_positive_width_is_not_an_equality(self):
        width = 2.0**-60
        original = payload([[1], [-1]], [0, width])
        new, cert = transform(original)
        self.assertEqual(cert['exact_pairs_moved'], 0)
        np.testing.assert_array_equal(new['b'], [0, width])

    def test_coefficient_difference_is_not_tolerated(self):
        original = payload([[1], [-np.nextafter(1.0, 2.0)]], [0, 0])
        _, cert = transform(original)
        self.assertEqual(cert['exact_pairs_moved'], 0)

    def test_duplicate_rows_are_not_consumed_twice(self):
        original = payload([[1], [1], [-1]], [1, 1, -1])
        new, cert = transform(original)
        self.assertEqual(cert['exact_pairs_moved'], 1)
        self.assertEqual(cert['original_le_pair_to_new_eq'], [[1, 2, 0]])
        self.assertEqual(cert['retained_le_row_ranges'], [[0, 1]])
        self.assertEqual(new['A'].shape[0], 1)

    def test_empty_rows_and_conditional_big_m_are_retained(self):
        original = payload([[0, 0], [0, 0], [1, 60], [-1, 60]], [1, -1, 60, 60])
        new, cert = transform(original)
        self.assertEqual(cert['exact_pairs_moved'], 0)
        self.assertEqual(cert['empty_rows_retained'], 2)
        np.testing.assert_array_equal(new['A'].toarray(), original['A'].toarray())

    def test_mapping_and_original_row_recheck(self):
        original = payload([[1, 1], [-1, -1], [1, 0]], [2, -2, 3])
        new, cert = transform(original)
        self.assertTrue(all(verify_equivalence(original, new, cert).values()))
        for x in (np.array([1, 1.0]), np.array([1, 0.0]), np.array([4, -2.0])):
            old_ok = bool(np.all(original['A']@x <= original['b']))
            new_ok = bool(np.all(new['A']@x <= new['b']) and np.all(new['Aeq']@x == new['beq']))
            self.assertEqual(old_ok, new_ok)
        corrupted = copy.deepcopy(cert)
        corrupted['original_le_pair_to_new_eq'][0][0] = 2
        with self.assertRaises(ValueError):
            verify_equivalence(original, new, corrupted)
        corrupted = copy.deepcopy(cert)
        corrupted['retained_le_row_ranges'] = []
        with self.assertRaises(ValueError):
            verify_equivalence(original, new, corrupted)


if __name__ == '__main__':
    unittest.main()
