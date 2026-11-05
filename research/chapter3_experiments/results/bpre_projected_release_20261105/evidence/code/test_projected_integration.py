import bootstrap
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import json
import numpy as np
from pathlib import Path
import tempfile
from test_native_projection import BoundaryTests, Clock, payload
from timing import MethodBudget
from thermal import Exhausted
import native_projection as n
import projected_integration as p
from initial_point import _InitialSession
from matlab_bridge import _read_json_until, PublicationTimeout


class CommitTests(BoundaryTests):
    def test_commit_clock_exactly_at_deadline_rejected(self):
        checks=[0]
        original=self.r.check_binding
        def boundary(prefix):
            checks[0]+=1
            original(prefix)
            if checks[0]==3:self.clock.now=100
        self.r.check_binding=boundary
        with self.assertRaises(Exhausted):self.r.assess({'x':self.x})
        self.assertEqual(self.r.receipts,[]);self.assertIsNone(self.r.best)
    def test_archive_expiry_never_commits(self):
        real=n.archive
        def expire(path,value):
            real(path,value);self.clock.now=100
        with patch.object(n,'archive',side_effect=expire):
            with self.assertRaises(Exhausted):self.r.assess({'x':self.x})
        self.assertEqual(self.r.receipts,[])
        self.assertIsNone(self.r.best)
    def test_callback_expiry_reaches_original_publication_timeout(self):
        outer=self
        class Native:
            budget=outer.budget;workdir=outer.folder;counter=0;event_consumer=None
            def solve(self,*args,**kwargs):
                self.counter+=1
                prefix=self.workdir/'request_000001'
                with outer.assertRaises(PublicationTimeout):
                    _read_json_until(prefix.with_suffix('.response.json'),100,outer.clock,
                        on_poll=lambda:self.event_consumer(prefix))
                prefix.with_suffix('.cancel').write_text('budget\n',encoding='ascii')
                return dict(status='BUDGET_EXHAUSTED',request_number=1,budget_valid=False,
                            accepted_for_evaluation=False,x=[])
        def expired_poll(record,prefix):
            self.clock.now=100
            raise Exhausted('wall_time_limit')
        adapter=n.ProjectedSession(Native(),self.model,{},self.budget)
        with patch.object(n,'resolve_idle_policy',return_value='auto_low_immediate_v1'), \
             patch.object(n.RequestRecorder,'poll',expired_poll):
            packet=adapter.solve(payload(),remaining_s=100,budget=self.budget)
        self.assertEqual(packet['native_result']['status'],'BUDGET_EXHAUSTED')
        self.assertIsNone(packet['final_admission'])
        self.assertEqual((self.folder/'request_000001.cancel').read_text(),'budget\n')
    def test_final_expiry_retains_native_result(self):
        outer=self
        returned=dict(status='SOLVED',request_number=1,budget_valid=True,accepted_for_evaluation=True,x=self.x)
        class Native:
            budget=outer.budget;workdir=outer.folder;counter=0;event_consumer=None
            def solve(self,*args,**kwargs):
                self.counter=1
                (self.workdir/'request_000001.response.json').write_text(json.dumps(returned))
                return returned
        def expired_assess(record,*args,**kwargs):
            self.clock.now=100;raise Exhausted('wall_time_limit')
        adapter=n.ProjectedSession(Native(),self.model,{},self.budget)
        with patch.object(n,'resolve_idle_policy',return_value='auto_low_immediate_v1'), \
             patch.object(n.RequestRecorder,'assess',expired_assess):
            with self.assertRaises(Exhausted):adapter.solve(payload(),remaining_s=100,budget=self.budget)
        self.assertIs(adapter.records[0].native_result,returned)
        self.assertIsNone(adapter.records[0].best)
    def test_numerical_conflict_is_never_assessed(self):
        outer=self
        class Native:
            budget=outer.budget;workdir=outer.folder;counter=0;event_consumer=None
            def solve(self,*args,**kwargs):
                self.counter=1
                return dict(status='SOLVED',request_number=1,budget_valid=True,accepted_for_evaluation=True,
                    x=outer.x,numerical_consistency={'state':'NUMERICAL_ADMISSION_STATUS_CONFLICT'})
        adapter=n.ProjectedSession(Native(),self.model,{},self.budget)
        with patch.object(n,'resolve_idle_policy',return_value='auto_low_immediate_v1'), \
             patch.object(n.RequestRecorder,'assess') as assess:
            packet=adapter.solve(payload(),remaining_s=100,budget=self.budget)
        assess.assert_not_called();self.assertIsNone(packet['final_admission'])


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.budget=MethodBudget(600,clock=self.clock)
        self.model=SimpleNamespace(budget=self.budget,as_solver_dict=lambda:{'round':len(self.calls)})
        self.native=SimpleNamespace(workdir=Path('.'),event_consumer=None)
        self.session=_InitialSession(self.native,np.array([1.]))
        self.calls=[]
    def test_typed_two_round_feedback_first_x0_only(self):
        outer=self
        class Adapter:
            records=[]
            def __init__(self,*args):pass
            def solve(self,model,**kw):
                outer.calls.append((model,kw));i=len(outer.calls)
                return dict(native_result=dict(request_number=i,budget_valid=True,accepted_for_evaluation=True,
                    x=[1],exitflag=0),final_admission=dict(accepted_safe=i==2,candidate={'scenes':{}},
                    evaluation={'state':'SAFE' if i==2 else 'THERMAL_VIOLATION'}))
        with patch.object(p,'_checked_thermal_witnesses',return_value=[1]), \
             patch.object(p,'add_thermal_feedback',return_value={'rows_added':1}) as feedback:
            result=p.solve_projected_diagnostic(self.model,self.session,{},self.budget,adapter_factory=Adapter)
        self.assertEqual(result['reason'],'SAFE_INCUMBENT');self.assertEqual(len(result['rounds']),2)
        self.assertIs(self.calls[0][1]['x0'],self.session.x0);self.assertIsNone(self.calls[1][1]['x0'])
        self.assertEqual([v[0]['round'] for v in self.calls],[0,1]);feedback.assert_called_once()
        self.assertTrue(all(v[1]['budget'] is self.budget for v in self.calls))
    def test_final_expiry_round_preserved_once_and_safe_fallback_record(self):
        outer=self
        native=dict(request_number=1,budget_valid=True,accepted_for_evaluation=True,x=[1])
        safe=dict(accepted_safe=True,source='callback',candidate={'scenes':{}},
            evaluation={'safe_upper_bound_J':'1','completed_at_elapsed_s':20},
            numeric={'completed_at_elapsed_s':19},admission_committed_at_s=21)
        class Adapter:
            def __init__(self,*args):
                self.records=[SimpleNamespace(native_result=native,events=[],receipts=[safe],best=safe,
                    budget=outer.budget,request_deadline=600)]
            def solve(self,*args,**kw):
                outer.clock.now=600;raise Exhausted('wall_time_limit')
        result=p.solve_projected_diagnostic(self.model,self.session,{},self.budget,adapter_factory=Adapter)
        self.assertEqual(result['rounds'],[native]);self.assertIs(result['rounds'][0],native)
        self.assertEqual(result['safe_upper_bound_J'],'1');self.assertEqual(result['reason'],'wall_time_limit')
    def test_no_initial_admission_no_solver(self):
        with self.assertRaises(ValueError):
            p.solve_projected_diagnostic(self.model,self.native,{},self.budget)
    def test_missing_native_request_number_is_preserved_without_finally_error(self):
        returned=dict(status='WORKER_EXITED',budget_valid=False,accepted_for_evaluation=False,x=[])
        class Adapter:
            records=[]
            def __init__(self,*args):pass
            def solve(self,*args,**kw):return {'native_result':returned}
        result=p.solve_projected_diagnostic(self.model,self.session,{},self.budget,adapter_factory=Adapter)
        self.assertEqual(result['rounds'],[returned])
        self.assertEqual(result['reason'],'SOLVER_RETURN_AFTER_BUDGET')


if __name__=='__main__':unittest.main(verbosity=2)
