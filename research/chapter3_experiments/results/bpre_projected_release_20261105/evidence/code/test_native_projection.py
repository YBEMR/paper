import bootstrap
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import json
import numpy as np
import sys
sys.path.insert(0, str(bootstrap.WORK/'bpre_projection_impl_20261105T030028Z/tests'))
from fixtures import payload
from timing import MethodBudget
from thermal import Exhausted
from projection_admission import ProjectionAdmission, ProjectionRejected
import native_projection as n


class Clock:
    now=0.
    def __call__(self): return self.now


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=bootstrap.ROOT)
        self.folder=Path(self.temp.name)
        self.clock=Clock(); self.budget=MethodBudget(100,clock=self.clock)
        self.model=SimpleNamespace(budget=self.budget,instance={})
        self.guard=ProjectionAdmission(payload(x0=True),policy='auto_low_immediate_v1',budget=self.budget)
        self.calls=[]
        self.r=n.RequestRecorder(self.guard,self.model,{},self.folder/'request_000001',
            decoder=self.decode,evaluator=self.safe)
        self.x=[0.,1.,0.]
    def tearDown(self): self.temp.cleanup()
    def decode(self,m,x):
        self.calls.append(('decode',len(x)))
        return {'scenes': {'fixture': []}}
    def safe(self,m,c,a,b):
        self.calls.append(('evaluate', id(b)))
        return {'state':'SAFE','rankable_energy':True,'safe_upper_bound_J':'1',
            'weighted_energy_J':['1','1'],'scenes':{'fixture':{'state':'SAFE','complete':True}},
            'completed_at_elapsed_s':b.elapsed}
    def final(self):
        return dict(x=self.x,status='SOLVED',budget_valid=True,accepted_for_evaluation=True)
    def write_event(self,x=None,number=1):
        p=self.folder/'request_000001.event_000001.json'
        p.write_text(json.dumps({'x':self.x if x is None else x,'event_number':number}),encoding='utf-8')
        return p
    def test_both_paths_full_vector_and_original_budget(self):
        p=self.write_event(); before=p.read_bytes()
        self.r.poll(self.r.prefix); self.r.assess(self.final(),final=True)
        self.assertEqual(self.calls,[('decode',5),('evaluate',id(self.budget))]*2)
        self.assertEqual(p.read_bytes(),before)
        self.assertEqual(len(self.r.receipts),2)
    def test_bad_rows_never_cache_bypass(self):
        self.r.assess({'x':self.x}); self.calls.clear()
        with self.assertRaises(ProjectionRejected): self.r.assess({'x':[0.,1.,1.]})
        self.assertEqual(self.calls,[])
    def test_wrong_request(self):
        with self.assertRaises(ProjectionRejected): self.r.poll(self.folder/'request_000002')
        self.assertEqual(self.calls,[])
    def test_wrong_event_number(self):
        self.write_event(number=2)
        with self.assertRaises(ProjectionRejected): self.r.poll(self.r.prefix)
    def test_certificate_drift(self):
        self.guard._certificate['policy']='changed'
        with self.assertRaises(ProjectionRejected): self.r.assess({'x':self.x})
        self.assertEqual(self.calls,[])
    def test_array_drift(self):
        self.guard._rows['b'][0]+=1
        with self.assertRaises(ProjectionRejected): self.r.assess({'x':self.x})
        self.assertEqual(self.calls,[])
    def test_final_late_native_receipt(self):
        x=self.final();x['budget_valid']=False
        with self.assertRaises(ProjectionRejected): self.r.assess(x,final=True)
    def test_root_expired(self):
        self.clock.now=100
        with self.assertRaises(Exhausted): self.r.assess(self.final(),final=True)
    def test_short_request_expired(self):
        self.r.request_deadline=10;self.clock.now=10
        with self.assertRaises(ProjectionRejected): self.r.assess({'x':self.x})
    def test_evaluation_crosses_short_deadline(self):
        self.r.request_deadline=10
        def late(*args):
            result=self.safe(*args);self.clock.now=11;return result
        self.r.evaluator=late
        with self.assertRaises(ProjectionRejected):self.r.assess({'x':self.x})
        self.assertIsNone(self.r.best)
    def test_late_evaluator_with_early_stamp_rejected(self):
        def late(*args):
            result=self.safe(*args);self.clock.now=101;return result
        self.r.evaluator=late
        with self.assertRaises(Exhausted):self.r.assess({'x':self.x})
        self.assertIsNone(self.r.best)
    def test_multidimensional_event_rejected(self):
        self.write_event(x=[[0.,1.,0.]])
        with self.assertRaises(ProjectionRejected):self.r.poll(self.r.prefix)
    def test_partial_json_waits_without_admission(self):
        p=self.write_event();p.write_text('{',encoding='utf-8')
        self.r.poll(self.r.prefix);self.assertEqual(self.calls,[])
    def test_incomplete_safe_receipt_rejected(self):
        self.r.evaluator=lambda *a:dict(self.safe(*a),scenes={})
        result=self.r.assess({'x':self.x})
        self.assertFalse(result['accepted_safe']);self.assertIsNone(self.r.best)
    def test_complex_model_rejected(self):
        p=payload();p['c']=p['c'].astype(complex)
        with self.assertRaises(ProjectionRejected):n.canonical(p)
    def test_multidimensional_model_rejected(self):
        p=payload();p['b']=p['b'].reshape(-1,1)
        with self.assertRaises(ProjectionRejected):n.canonical(p)
    def test_windows_int32_indices_widen_exactly(self):
        p=payload();p['intcon']=p['intcon'].astype(np.int32)
        result=n.canonical(p)
        self.assertEqual(result['intcon'].dtype,np.int64)
        np.testing.assert_array_equal(result['intcon'],p['intcon'])
    def test_noncanonical_sparse_rejected(self):
        p=payload();p['A'].has_canonical_format=False
        with self.assertRaises(ProjectionRejected):n.canonical(p)


class SessionTests(BoundaryTests):
    def fake_native(self, *, fail=False, mutate=None):
        outer=self
        class Native:
            budget=outer.budget
            workdir=outer.folder
            counter=0
            event_consumer='old consumer'
            def solve(self,payload,**kwargs):
                self.counter+=1;outer.sent=(payload,kwargs)
                if mutate: mutate(self)
                if fail:raise RuntimeError('native interruption')
                return {'status':'SOLVED','request_number':self.counter,
                    'accepted_for_evaluation':False,'budget_valid':True,'x':[]}
        return Native()
    def invoke(self,native,**kwargs):
        adapter=n.ProjectedSession(native,self.model,{},self.budget)
        with patch.object(n,'resolve_idle_policy',return_value='auto_low_immediate_v1'):
            return adapter.solve(payload(),remaining_s=20,budget=self.budget,**kwargs)
    def test_consumer_restored_on_success(self):
        native=self.fake_native();self.invoke(native)
        self.assertEqual(native.event_consumer,'old consumer')
        self.assertIsNone(self.sent[1]['x0'])
        self.assertNotIn('x0',self.sent[0])
    def test_consumer_restored_and_cancelled_on_failure(self):
        native=self.fake_native(fail=True)
        with self.assertRaises(RuntimeError):self.invoke(native)
        self.assertEqual(native.event_consumer,'old consumer');self.assertTrue(native.request_blocked)
        self.assertTrue((self.folder/'request_000001.cancel').exists())
    def test_conversion_time_deducted(self):
        native=self.fake_native();real=n.exact_equalities
        def slow(x): self.clock.now+=4;return real(x)
        with patch.object(n,'exact_equalities',side_effect=slow):self.invoke(native)
        self.assertEqual(self.sent[1]['remaining_s'],16)
    def test_wrong_final_request_identity(self):
        native=self.fake_native(mutate=lambda x:setattr(x,'counter',2))
        with self.assertRaises(ProjectionRejected):self.invoke(native)
        self.assertEqual(native.event_consumer,'old consumer')
    def test_complex_initial_rejected_before_native(self):
        native=self.fake_native()
        with self.assertRaises(ProjectionRejected):self.invoke(native,x0=np.ones(5,dtype=complex))
        self.assertEqual(native.counter,0)
    def test_other_budget_rejected(self):
        native=self.fake_native();a=n.ProjectedSession(native,self.model,{},self.budget)
        with self.assertRaises(ProjectionRejected):a.solve(payload(),remaining_s=20,budget=MethodBudget(1))


if __name__=='__main__':unittest.main(verbosity=2)
