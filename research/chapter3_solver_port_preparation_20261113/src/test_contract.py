"""All cases synthetic. No optimize/linprog/milp, native models, MATLAB or heat evaluation."""
import copy
import json
import sys
import time
import unittest
from pathlib import Path
import numpy as np
from scipy import sparse
from contract import (ContractError, MatrixPacket, FakeBackend, native_quota,
                      license_gate, interval, classify_mock, native_execution)


def arrays():
    return dict(c=np.array([1., 0., -0.]), A=sparse.coo_matrix(([1e-63, 1.5], ([0, 0], [0, 2])), shape=(1, 3)),
                b=np.array([1e-63]), Aeq=sparse.coo_matrix(([1., -1.], ([0, 0], [1, 2])), shape=(1, 3)),
                beq=np.array([0.]), lb=np.array([0., -np.inf, -1.]), ub=np.array([1., np.inf, 2.]),
                intcon=np.array([1.]), x0=np.array([1., 0., 0.]))


def packet(d=None, **kw):
    args=dict(intcon_base=1, sense='min', objective_constant=0., column_ids=range(3))
    args.update(kw)
    return MatrixPacket.read(arrays() if d is None else d, **args)


def receipt():
    return dict(mode='SIMULATION_ONLY', source_identity=True, matrix_identity=True, cleanup_ok=True,
                native_calls=1, native_received_s=549., evidence_sealed_s=599., bound_conflict=False,
                has_native_vector=True, old_matrix_admitted=True, new_matrix_admitted=True, schedule_legal=True,
                full_safe_AB=True, full_safe_AC=True, different_schedule=True,
                initial_energy=['1.08488637130371118030', '1.08488637130371118032'],
                candidate_energy=['1.02999999999999999999', '1.03000000000000000001'], native_status='TIME_LIMIT')


class ContractTests(unittest.TestCase):
    def test_copy_roundtrip(self):
        p=packet(); q=FakeBackend().load_and_readback(p); p.assert_same(q)
        self.assertIsNot(p.x0, q.x0)

    def test_zero_one_based(self):
        d=arrays(); p=packet(); d['intcon']=np.array([0], dtype=np.int64)
        p.assert_same(packet(d, intcon_base=0))

    def test_unsorted_coordinates(self):
        d=arrays(); d['A']=sparse.coo_matrix(([1.5,1e-63],([0,0],[2,0])),shape=(1,3))
        packet().assert_same(packet(d))

    def test_all_fields_bit_drift(self):
        for field in ('c','b','beq','lb','ub','x0'):
            with self.subTest(field=field):
                p=packet(); q=copy.deepcopy(p); a=getattr(q,field); a[0]=np.nextafter(a[0], np.inf)
                with self.assertRaises(ContractError):p.assert_same(q)

    def test_sparse_bit_drift(self):
        for field in ('A','Aeq'):
            p=packet(); q=copy.deepcopy(p); a=getattr(q,field)[3]; a[0]=np.nextafter(a[0],np.inf)
            with self.assertRaises(ContractError):p.assert_same(q)

    def test_metadata_drift(self):
        for key,value in [('sense','max'),('objective_constant',1.),('column_ids',(1,0,2)),('intcon',np.array([1],dtype='<i8'))]:
            p=packet(); q=copy.deepcopy(p); setattr(q,key,value)
            with self.assertRaises(ContractError):p.assert_same(q)

    def test_sparse_row_column_and_count_drift(self):
        p=packet()
        for mode in ('row','col','shape','drop'):
            q=copy.deepcopy(p); shape,row,col,data=q.A
            if mode=='row':row[0]=1
            if mode=='col':col[0]=1
            if mode=='shape':shape=(2,3)
            if mode=='drop':row,col,data=row[1:],col[1:],data[1:]
            q.A=shape,row,col,data
            with self.assertRaises(ContractError):p.assert_same(q)

    def test_invalid_integer_indices(self):
        for value in ([0.],[4.],[1.5],[1.,1.],[np.nan],[True]):
            d=arrays();d['intcon']=np.array(value)
            with self.subTest(value=value),self.assertRaises(ContractError):packet(d)

    def test_no_base_guess(self):
        for base in (None,True,2):
            with self.assertRaises(ContractError):packet(intcon_base=base)

    def test_duplicate_sparse_not_summed(self):
        d=arrays();d['A']=sparse.coo_matrix(([1.,-1.],([0,0],[0,0])),shape=(1,3))
        with self.assertRaises(ContractError):packet(d)

    def test_explicit_zero_not_dropped(self):
        d=arrays();d['A'].data[0]=0.
        with self.assertRaises(ContractError):packet(d)

    def test_float32_not_upcast(self):
        d=arrays();d['c']=d['c'].astype('f4')
        with self.assertRaises(ContractError):packet(d)

    def test_signed_zero_preserved(self):
        p=packet();q=copy.deepcopy(p);q.c[2]=0.
        with self.assertRaises(ContractError):p.assert_same(q)

    def test_wrong_objective_and_column_order(self):
        for kw in (dict(sense='max'),dict(objective_constant=1.),dict(objective_constant=-0.),dict(column_ids=[2,1,0])):
            with self.assertRaises(ContractError):packet(**kw)

    def test_bounds_explicit_infinity(self):
        p=packet();self.assertTrue(np.isneginf(p.lb[1]) and np.isposinf(p.ub[1]))
        for field, value in [('lb',np.inf),('ub',-np.inf),('c',np.inf),('b',np.nan)]:
            d=arrays();d[field][0]=value
            with self.assertRaises(ContractError):packet(d)

    def test_missing_or_partial_start(self):
        d=arrays();d['x0']=np.array([1.])
        with self.assertRaises(ContractError):packet(d)

    def test_x0_transport_is_not_admission(self):
        d=arrays();d['x0'][0]=2.;p=packet(d)
        p.assert_same(FakeBackend().load_and_readback(p))
        # Infeasibility is left to an independent verifier, never repaired here.
        self.assertGreater(p.x0[0],p.ub[0])

    def test_empty_equalities(self):
        d=arrays();d['Aeq']=sparse.coo_matrix((0,3));d['beq']=np.empty((0,0))
        self.assertEqual(packet(d).Aeq[0],(0,3))

    def test_budget_slow_start_and_boundary(self):
        for elapsed,expected in [(0,540),(65.844,474),(510,30),(510.001,0),(550,0),(700,0)]:
            self.assertEqual(native_quota(elapsed),expected)
        for t in (-1,float('nan'),float('inf')):
            with self.assertRaises(ContractError):native_quota(t)

    def test_license_gate_limits_unknown_and_absent(self):
        args=dict(installed=True,entitlement='verified_full',max_variables=None,max_rows=None,n=23780,m=101818)
        self.assertTrue(license_gate(**args))
        for changes in [dict(installed=False),dict(entitlement='unknown'),dict(max_variables=2000,max_rows=2000),dict(max_variables=1000,max_rows=1000)]:
            self.assertFalse(license_gate(**(args|changes)))

    def test_real_execution_always_disabled(self):
        with self.assertRaises(ContractError):native_execution(approved=True,license_verified=True)

    def test_timeout_can_have_strict_success(self):
        self.assertEqual(classify_mock(receipt()),'STRICT_IMPROVEMENT')

    def test_empty_vector_never_external_incumbent_success(self):
        r=receipt();r['has_native_vector']=False
        self.assertEqual(classify_mock(r),'NO_NATIVE_CANDIDATE')

    def test_candidate_rejection_and_safe_unknown(self):
        for k in ('old_matrix_admitted','new_matrix_admitted','schedule_legal'):
            r=receipt();r[k]=False;self.assertEqual(classify_mock(r),'CANDIDATE_REJECTED')
        for k in ('full_safe_AB','full_safe_AC'):
            r=receipt();r[k]=None;self.assertEqual(classify_mock(r),'SAFE_NOT_ESTABLISHED')

    def test_same_schedule_is_not_improvement(self):
        r=receipt();r['different_schedule']=False
        self.assertEqual(classify_mock(r),'COMMON_SCHEDULE_SAFE_ONLY')

    def test_exact_interval_no_float_rounding(self):
        r=receipt();r['initial_energy']=['1.00000000000000000001','1.00000000000000000002']
        r['candidate_energy']=['1','1.00000000000000000000']
        self.assertEqual(classify_mock(r),'STRICT_IMPROVEMENT')
        r['candidate_energy'][1]=r['initial_energy'][0]
        self.assertEqual(classify_mock(r),'SAFE_WITHOUT_STRICT_IMPROVEMENT')

    def test_bad_interval_fails(self):
        for x in ([1.,2.],['2','1'],['nan','1'],None):
            with self.assertRaises((ContractError,ValueError)):interval(x)

    def test_late_response_or_archive(self):
        for k,v in [('native_received_s',550.001),('evidence_sealed_s',600.001)]:
            r=receipt();r[k]=v;self.assertEqual(classify_mock(r),'LATE_UNCREDITED')

    def test_integrity_cleanup_and_call_count(self):
        for k,v in [('source_identity',False),('matrix_identity',False),('cleanup_ok',False),('native_calls',2),('native_received_s',float('nan'))]:
            r=receipt();r[k]=v;self.assertEqual(classify_mock(r),'INTEGRITY_STOP')

    def test_lower_bound_conflict(self):
        r=receipt();r['bound_conflict']=True
        self.assertEqual(classify_mock(r),'BOUND_CONFLICT_STOP')

    def test_cannot_accept_real_receipt(self):
        r=receipt();r['mode']='REAL'
        with self.assertRaises(ContractError):classify_mock(r)


if __name__=='__main__':
    started=time.perf_counter()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(mode='PURE_SYNTHETIC_CONTROL',tests_run=result.testsRun,passed=result.wasSuccessful(),
                failures=len(result.failures),errors=len(result.errors),elapsed_s=time.perf_counter()-started,
                optimization_calls=0,MATLAB_sessions=0,full_R1_builds=0,thermal_evaluations=0,
                real_backend_validated=False)
    if len(sys.argv)>1:
        with Path(sys.argv[1]).open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    sys.exit(not result.wasSuccessful())
