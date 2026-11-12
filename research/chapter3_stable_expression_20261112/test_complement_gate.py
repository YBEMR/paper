import copy
import unittest
from fractions import Fraction as Q
import numpy as np
from scipy import sparse
from complement_gate import transform,verify_equivalence,forward_vector,inverse_vector,forward_rational,inverse_rational,array_digest,ExactRepresentationError

def fixture(fmt='csc'):
    # x target in [0,4], binary/continuous gate in [0,1]. Active interval is [1,1.25].
    return dict(c=np.array([2.,0.]),A=sparse.coo_matrix([[1.,4.],[-1.,3.],[0.,1.]]).asformat(fmt),
        b=np.array([5.25,2.,1.]),Aeq=sparse.coo_matrix([[0.,0.]]).asformat(fmt),beq=np.array([0.]),
        lb=np.array([0.,0.]),ub=np.array([4.,1.]),intcon=np.array([1],dtype=np.int64),x0=np.array([1.,1.]))

class ComplementTests(unittest.TestCase):
    def test_exact_transform_and_inverse_all_rows(self):
        p=fixture();before=array_digest(p);d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1])
        self.assertEqual(array_digest(p),before);self.assertEqual(d['A'].shape,(3,3));self.assertEqual(d['Aeq'].shape,(2,3))
        self.assertTrue(all(verify_equivalence(p,d,c).values()));self.assertTrue(np.array_equal(inverse_vector(d['x0'],c),p['x0']))
        self.assertTrue(np.array_equal(d['b'],[1.25,-1.,1.]));self.assertTrue(np.array_equal(d['intcon'],[1]))
    def test_continuous_projection_not_only_binary_gates(self):
        p=fixture('csr');d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1])
        for gate in [0.,.25,.5,.75,1.]:
            for target in [0.,.5,1.,1.25,2.,3.,4.]:
                x=np.array([target,gate]);z=forward_vector(x,c)
                self.assertTrue(np.array_equal(p['A']@x-p['b'],d['A']@z-d['b']))
                self.assertTrue(np.array_equal(d['Aeq']@z,d['beq']))
                self.assertEqual(p['c']@x,d['c']@z)
    def test_nonrepresentable_rhs_rejects_whole_transform(self):
        p=fixture();p['A']=sparse.csc_matrix([[1.,.3],[-1.,3.],[0.,1.]])
        p['b'][0]=1.;before=array_digest(p)
        with self.assertRaisesRegex(ExactRepresentationError,'RHS'):transform(p,row_gates={0:1,1:1},gate_columns=[1])
        self.assertEqual(array_digest(p),before)
    def test_nonrepresentable_complement_x0_rejected(self):
        p=fixture();p['x0'][1]=.3
        with self.assertRaisesRegex(ExactRepresentationError,'x0 complement'):transform(p,row_gates={0:1,1:1},gate_columns=[1])
    def test_split_constant_preserves_exact_shift_and_fixed_bounds(self):
        p=fixture();p['A']=sparse.csc_matrix([[1.,.3],[-1.,3.],[0.,1.]])
        p['b'][0]=1.;before=array_digest(p)
        d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1],mode='split_constant_v1')
        self.assertEqual(array_digest(p),before);self.assertEqual(len(c['fixed_constants']),1)
        item=c['fixed_constants'][0];j=item['column'];v=Q(item['value_exact'])
        self.assertEqual(j,3);self.assertEqual(Q.from_float(d['lb'][j]),v);self.assertEqual(Q.from_float(d['ub'][j]),v)
        self.assertEqual(d['A'][0,j],-1.);self.assertTrue(all(verify_equivalence(p,d,c).values()))
        self.assertTrue(np.array_equal(inverse_vector(d['x0'],c),p['x0']))
    def test_split_constant_rational_projection_fractional_gate(self):
        p=fixture();p['A']=sparse.csc_matrix([[1.,.3],[-1.,3.],[0.,1.]]);p['b'][0]=1.
        d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1],mode='split_constant_v1')
        for gate in [Q(0),Q(1,3),Q.from_float(.3),Q(7,8),Q(1)]:
            for target in [Q(0),Q(4,3),Q(4)]:
                x=[target,gate];z=forward_rational(x,c);self.assertEqual(inverse_rational(z,c),x)
                for i in range(3):
                    old=sum((Q.from_float(float(p['A'][i,j]))*x[j] for j in range(2)),Q(0))-Q.from_float(p['b'][i])
                    new=sum((Q.from_float(float(d['A'][i,j]))*z[j] for j in range(len(z))),Q(0))-Q.from_float(d['b'][i])
                    self.assertEqual(old,new)
                self.assertEqual(z[1]+z[2],1)
    def test_fixed_constant_tampering_is_rejected(self):
        p=fixture();p['A']=sparse.csc_matrix([[1.,.3],[-1.,3.],[0.,1.]]);p['b'][0]=1.
        d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1],mode='split_constant_v1')
        d['ub'][-1]=np.nextafter(d['ub'][-1],np.inf);c['derived_array_sha256']=array_digest(d)
        with self.assertRaisesRegex(ExactRepresentationError,'Fixed low-part bounds'):verify_equivalence(p,d,c)
    def test_nonzero_interval_not_replaced_by_equality(self):
        p=fixture();d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1])
        # Distinct active endpoints both retained; only h+g=1 is an added equality.
        for target in [1.,1.125,1.25]:
            z=forward_vector([target,1.],c);self.assertTrue(np.all(d['A']@z<=d['b']))
        self.assertEqual(d['A'].shape[0],p['A'].shape[0])
    def test_gate_domain_and_explicit_maps_required(self):
        p=fixture()
        with self.assertRaises(ExactRepresentationError):transform(p,row_gates={0:1},gate_columns=[0])
        with self.assertRaises(ExactRepresentationError):transform(p,row_gates={2:0},gate_columns=[0])
        p['ub'][1]=2
        with self.assertRaises(ExactRepresentationError):transform(p,row_gates={0:1},gate_columns=[1])
    def test_tamper_detected_even_with_rehashed_payload(self):
        p=fixture();d,c=transform(p,row_gates={0:1,1:1},gate_columns=[1])
        d['b'][0]=np.nextafter(d['b'][0],np.inf);c['derived_array_sha256']=array_digest(d)
        with self.assertRaisesRegex(ExactRepresentationError,'Inverse row mismatch'):verify_equivalence(p,d,c)

if __name__=='__main__':unittest.main(verbosity=2)
