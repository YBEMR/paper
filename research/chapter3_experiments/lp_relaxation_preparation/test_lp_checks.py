"""Hand-authored fixtures; no native/optimizer/thermal calls."""
from copy import deepcopy
import unittest

import numpy as np
from scipy import sparse

import lp_checks as lp


def fixture():
    return dict(c=np.array([2.,1.]), A=sparse.csc_matrix([[1.,1.]]), b=np.array([2.]),
        Aeq=sparse.csc_matrix((0,2)), beq=np.array([]),
        lb=np.array([0.,0.]), ub=np.array([1.,2.]),
        intcon=np.array([0],dtype=np.int64), x0=np.array([1.,.5]))


class LPChecks(unittest.TestCase):
    def test_omit_only_integrality(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertEqual(set(payload),set(lp.LP_KEYS))
        self.assertNotIn('x0',payload); self.assertNotIn('intcon',payload)
        self.assertTrue(lp.assert_identity(source,payload)['passed'])

    def test_copies_do_not_mutate_source(self):
        source=fixture(); payload=lp.make_relaxation(source)
        payload['lb'][0]=.5
        self.assertEqual(source['lb'][0],0.)

    def test_every_numerical_argument_drift_rejected(self):
        for key in lp.LP_KEYS:
            with self.subTest(key=key):
                source=fixture(); payload=lp.make_relaxation(source)
                if key=='A': payload[key].data[0]+=1e-12
                elif key=='Aeq': payload[key]=sparse.csc_matrix([[0.,0.]])
                elif key=='beq': payload[key]=np.array([0.])
                else: payload[key][0]+=1e-12
                with self.assertRaises(ValueError): lp.assert_identity(source,payload)

    def test_K189_fixed_bounds_rejected(self):
        source=fixture(); payload=lp.make_relaxation(source)
        payload['lb'][0]=payload['ub'][0]=source['x0'][0]
        with self.assertRaises(ValueError): lp.assert_identity(source,payload)

    def test_extra_intcon_or_x0_rejected(self):
        for key in ('intcon','x0'):
            source=fixture(); payload=lp.make_relaxation(source); payload[key]=source[key]
            with self.assertRaises(ValueError): lp.assert_identity(source,payload)

    def test_fractional_LP_vector_accepted_without_rounding(self):
        source=fixture(); payload=lp.make_relaxation(source); x=np.array([.5,.5]); before=x.copy()
        result=lp.check_vector(source,payload,x,1.5)
        self.assertTrue(result['accepted']); self.assertEqual(result['original_integer_distance'],.5)
        self.assertTrue(np.array_equal(x,before)); self.assertFalse(result['new_safe_or_U'])

    def test_original_bound_rejection(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertFalse(lp.check_vector(source,payload,[1.+1e-8,0.],2.+2e-8)['accepted'])

    def test_row_rejection(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertFalse(lp.check_vector(source,payload,[1.,1.1],3.1)['accepted'])

    def test_equality_rejection(self):
        source=fixture(); source['Aeq']=sparse.csc_matrix([[0.,1.]]); source['beq']=np.array([.5])
        payload=lp.make_relaxation(source)
        self.assertFalse(lp.check_vector(source,payload,[1.,.6],2.6)['accepted'])

    def test_bad_vectors(self):
        source=fixture(); payload=lp.make_relaxation(source)
        for x in ([],[1.],[1.,float('nan')],[1.,float('inf')],[1j,.5]):
            with self.subTest(vector=x): self.assertFalse(lp.check_vector(source,payload,x,0.)['accepted'])

    def test_objective_mismatch(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertFalse(lp.check_vector(source,payload,[1.,.5],100.)['accepted'])

    def test_reference_check_does_not_need_solver_objective(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertTrue(lp.check_vector(source,payload,source['x0'],require_objective=False)['accepted'])

    def test_missing_required_objective(self):
        source=fixture(); payload=lp.make_relaxation(source)
        self.assertFalse(lp.check_vector(source,payload,source['x0'])['accepted'])

    def test_nonnegative_zero_residuals(self):
        source=fixture(); payload=lp.make_relaxation(source)
        r=lp.check_vector(source,payload,[0.,0.],0.)
        self.assertTrue(r['accepted']); self.assertEqual(r['inequality_violation'],0.)

    def test_status_scope(self):
        self.assertEqual(lp.interpret(1,True,in_budget=True),'LP_OPTIMUM_SOLVER_REPORTED_ONLY')
        self.assertEqual(lp.interpret(0,True,in_budget=True),'LP_PRIMAL_ADMITTED_OPTIMALITY_UNRESOLVED')
        self.assertEqual(lp.interpret(-2,False,in_budget=True),'LP_NUMERICAL_INFEASIBILITY_STATUS_UNRESOLVED')
        self.assertEqual(lp.interpret(-3,False,in_budget=True),'LP_UNBOUNDED_STATUS_UNRESOLVED')
        self.assertEqual(lp.interpret(1,True,in_budget=False),'LATE_OR_TIMEOUT_UNRESOLVED')
        self.assertEqual(lp.interpret(1,True,in_budget=True,options_match=False),'OPTIONS_DRIFT_STOP')


if __name__=='__main__': unittest.main()
