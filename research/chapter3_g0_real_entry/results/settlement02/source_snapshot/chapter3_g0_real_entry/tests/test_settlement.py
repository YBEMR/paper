"""Ten bounded-settlement groups. Fake clocks/processes only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from .support import TemporaryDirectory
from . import test_transport as tr
from . import test_backend_driver as old
from ...chapter3_g0.tests.fixtures import FakeClock
from ...chapter3_g0.budget import G0Budget,ScopeExhausted
from ..session import ScopedMatlabSession
from ..settlement import BoundedSettlement,PROFILE
from ..gating import WiringPermit
from .. import backend as wired


def write(path,value):
    Path(path).write_text(json.dumps(value,default=str),encoding='utf-8')

class Harness:
    def __init__(self,folder):
        self.folder=Path(folder);self.clock=FakeClock();self.budget=G0Budget(300,clock=self.clock)
        deps=tr.session_dependencies(self.folder,self.clock)
        self.response_due=None;self.response={'status':'SOLVED','exitflag':-1,'x':[999],'fval':-999}
        self.publish=True;self.requests=0;self.mode='timeout'
        def capture(proc,phase):
            return {'root_identity':{'pid':proc.pid,'create_time':1},'root_identity_verified':True}
        def sleep(seconds):
            self.clock.advance(seconds)
            if self.publish and self.response_due is not None and self.clock()>=self.response_due:
                write(self.session.workdir/f'request_{self.session.counter:06d}.response.json',self.response)
        h=self
        class Kernel:
            @staticmethod
            def solve(owner,model,**kwargs):
                owner.counter+=1;h.requests+=1
                if h.mode=='normal':return {'status':'SOLVED','budget_valid':True,'x':[]}
                prefix=owner.workdir/f'request_{owner.counter:06d}'
                if h.mode=='unpublished':
                    h.clock.advance(owner.budget.remaining)
                    return {'status':'BUDGET_EXHAUSTED_BEFORE_PUBLICATION','budget_valid':False,'x':[]}
                write(prefix.with_suffix('.request.json'),{'request':owner.counter})
                h.clock.advance(owner.budget.remaining)
                prefix.with_suffix('.cancel').write_text('budget\n')
                owner.request_blocked=True
                return {'status':'BUDGET_EXHAUSTED','budget_valid':False,'x':[],
                        'response_may_arrive_later':True}
            close=staticmethod(tr.FakeNativeMethods.close)
        deps['kernel'].MatlabSession=Kernel;deps.update(capture_tree=capture,sleep=sleep)
        self.session=ScopedMatlabSession(self.folder/'session',budget=self.budget,
                                        permit=WiringPermit(),dependencies=deps)
        self.session.enable_bounded_settlement()

    def timeout(self,deadline=10):
        with self.budget.scope('slot',deadline,kind='slot'):
            result=self.session.solve({},budget=self.budget)
        return result

    def settle(self):return self.session.settle_pending(self.budget)


class SettlementScenario(old.WiringScenario):
    def dependency_map(self):
        deps,base,context,augmented=super().dependency_map();scenario=self
        class Session(BoundedSettlement,base):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.workdir.mkdir(parents=True,exist_ok=False)
                self.proc=tr.FakeProcess();self.clock=scenario.clock
                self.process_tree={'root_identity':{'pid':777,'create_time':1}}
                self.dependencies={'capture_tree':lambda proc,phase:{'root_identity':{'pid':777,'create_time':1},'root_identity_verified':True},
                                   'write_json':write,'sleep':self.pause}
                self.due=None
            def pause(self,seconds):
                self.clock.advance(seconds)
                if self.due is not None and self.clock()>=self.due:
                    write(self.workdir/f'request_{self.counter:06d}.response.json',
                          {'status':'SOLVED','exitflag':-1,'x':[999],'fval':-999})
            def solve(self,payload,**options):
                previous=self.counter;self.counter+=1
                scenario.native_requests.append({'root_is_same':options['budget'] is scenario.initializer_root,
                                                 'number':self.counter,'at_s':self.budget.elapsed})
                if self.counter>2:return {'status':'SOLVED','budget_valid':True,'x':[]}
                scope=self.budget.capture_scope();deadline=self.budget.effective_deadline_elapsed_s
                prefix=self.workdir/f'request_{self.counter:06d}'
                write(prefix.with_suffix('.request.json'),{'request':self.counter})
                self.clock.advance(self.budget.remaining);prefix.with_suffix('.cancel').write_text('cancel')
                self.request_blocked=True;self.request_settled=False;self.due=self.clock()+1
                result={'status':'BUDGET_EXHAUSTED','budget_valid':False,'x':[],'response_may_arrive_later':True}
                self.note_request_return(result,previous,scope,deadline)
                return result
        return deps,Session,context,augmented


class SettlementTests(unittest.TestCase):
    def fixture(self):
        folder=TemporaryDirectory(prefix='settlement-');self.addCleanup(folder.cleanup)
        return Harness(folder.name)

    def test_group01_cancel_settles_then_next_sequence_same_session(self):
        h=self.fixture();h.timeout();h.response_due=11;identity=h.budget.root_identity
        r=h.settle();self.assertEqual(r['outcome'],'CONTROL_SETTLED_LATE_NO_ADMISSION')
        self.assertTrue(h.session.is_idle());self.assertEqual(h.budget.root_identity,identity)
        h.mode='normal';h.session.solve({},budget=h.budget)
        self.assertEqual(h.session.counter,2);self.assertEqual(h.requests,2)
        h2=self.fixture();h2.timeout();h2.response_due=11
        h2.response={'status':'BUDGET_EXHAUSTED_BEFORE_SOLVER','intlinprog_entered':False,
                     'error_identifier':'chapter3:requestReadCancelled'}
        h2.settle();self.assertTrue(h2.session.is_idle())

    def test_group02_late_vector_objective_events_never_admitted(self):
        h=self.fixture();h.timeout();h.response_due=11
        sentinel={'candidate':'ORIGINAL_SAFE','U':'123/100','scope':'original'};before=deepcopy(sentinel)
        write(h.session.workdir/'request_000001.event_000001.json',{'x':[999],'fval':-999})
        r=h.settle();self.assertFalse(r['late_candidate_admitted']);self.assertEqual(sentinel,before)
        self.assertNotIn('x',r);self.assertNotIn('fval',r)
        h2=self.fixture();h2.timeout();h2.session.event_consumer=lambda *args:None
        with self.assertRaisesRegex(RuntimeError,'CONSUMER'):h2.settle()

    def test_group03_missing_partial_locked_publications_bounded(self):
        for data in (None,b'{',b'\xff'):
            h=self.fixture();h.timeout();h.publish=False
            if data is not None:(h.session.workdir/'request_000001.response.json').write_bytes(data)
            with self.assertRaisesRegex(RuntimeError,'TIME_LIMIT'):h.settle()
            self.assertLessEqual(h.budget.elapsed,20.000001);self.assertFalse(h.session.is_idle())
        h=self.fixture();h.timeout();h.response_due=11
        original=Path.read_bytes
        def locked(path):
            if path.name.endswith('.response.json') and h.clock()<10.5:raise PermissionError('FAKE_LOCK')
            return original(path)
        with patch.object(Path,'read_bytes',locked):h.settle()
        self.assertTrue(h.session.is_idle())

    def test_group04_exact_late_read_and_archive_cutoff_do_not_unlock(self):
        for due in (20,21):
            h=self.fixture();h.timeout();h.response_due=due
            with self.assertRaisesRegex(RuntimeError,'TIME_LIMIT'):h.settle()
            self.assertFalse(h.session.is_idle())
        h=self.fixture();h.timeout();h.response_due=11
        def slow(path,value):write(path,value);h.clock.advance(10)
        h.session.dependencies['write_json']=slow
        with self.assertRaises(RuntimeError):h.settle()
        self.assertFalse(h.session.is_idle())
        self.assertFalse(h.session.settlement_records[-1]['queue_reuse_authorized'])

    def test_group05_phase_boundary_uses_same_absolute_drain_deadline(self):
        h=self.fixture()
        with h.budget.scope('phase1',150,kind='phase'):
            h.timeout(149);h.response_due=151
            deadline=h.session.pending_settlement['drain_deadline_s']
            with self.assertRaises(ScopeExhausted) as caught:h.settle()
            self.assertEqual(caught.exception.kind,'phase')
        self.assertEqual(h.session.pending_settlement['drain_deadline_s'],deadline)
        h.settle();self.assertEqual(deadline,159);self.assertGreaterEqual(h.budget.elapsed,151)
        self.assertLess(h.budget.root_remaining,149.001)

    def test_group06_root_deadline_never_allows_drain_or_new_work(self):
        h=self.fixture();h.timeout(300);h.response_due=300
        with self.assertRaises(ScopeExhausted) as caught:h.settle()
        self.assertEqual(caught.exception.kind,'root');self.assertFalse(h.session.is_idle())
        self.assertEqual(h.requests,1)

    def test_group07_native_callback_and_numerical_latches_not_recovered(self):
        for response in ({'status':'ERROR'},{'status':'SOLVED','exitflag':-2},
                         {'status':'SOLVED','exitflag':-1,'callback_error':'bad'},
                         {'status':'SOLVED','exitflag':-1,'numerical_consistency':{'state':'bad'}}):
            h=self.fixture();h.timeout();h.response=response;h.response_due=11
            with self.assertRaisesRegex(RuntimeError,'NOT_WHITELISTED'):h.settle()
            self.assertFalse(h.session.is_idle())
        h=self.fixture();h.timeout();b=object.__new__(wired.G0Backend)
        b.execution_organization=PROFILE;b.budget=h.budget;b.session=h.session
        b.numeric_context=SimpleNamespace(failed=True)
        with self.assertRaisesRegex(RuntimeError,'NUMERICAL_FAILURE_LATCH'):b.settle_pending(h.budget)

    def test_group08_wrong_prefix_owner_exit_or_next_request_stops(self):
        for fault in ('prefix','counter','owner','exit','next','request'):
            h=self.fixture();h.timeout();h.response_due=11
            if fault=='prefix':h.session.pending_settlement['prefix']+='-wrong'
            if fault=='counter':h.session.counter+=1
            if fault=='owner':h.session.process_tree['root_identity']['create_time']=2
            if fault=='exit':h.session.proc.returncode=1
            if fault=='next':write(h.session.workdir/'request_000002.request.json',{})
            if fault=='request':write(h.session.workdir/'request_000001.request.json',{'changed':True})
            with self.assertRaises(RuntimeError):h.settle()
            self.assertFalse(h.session.is_idle())

    def test_group09_coordinator_two_phase_same_safe_and_original_scopes(self):
        config,instance,anchor=old.simulation_bundle()
        s=SettlementScenario(config,instance,anchor,FakeClock(),init_delay=140)
        with TemporaryDirectory(prefix='settlement-coordinator-') as folder:
            result=s.run(Path(folder)/'run',execution_organization=PROFILE)
            write(Path(folder)/'trace.json',result)
        self.assertIsNone(result['failure'],result['failure'])
        self.assertEqual(result['S0']['candidate'],result['final']['candidate'])
        self.assertEqual(result['S0']['U_J'],result['final']['U_J'])
        self.assertEqual(result['S0']['scope'],result['final']['scope'])
        self.assertEqual(len(s.sessions),1);self.assertEqual(len(s.native_requests),4)
        self.assertGreater(result['phase2_started_s'],150)
        self.assertEqual([x['number'] for x in s.native_requests],[1,2,3,4])
        self.assertTrue(all(x['root_is_same'] for x in s.native_requests))
        self.assertTrue(all(not x['late_candidate_admitted'] for x in result['settlement_records']))

    def test_group10_unpublished_reserved_number_is_terminal_no_overwrite(self):
        h=self.fixture();h.mode='unpublished';h.timeout()
        self.assertEqual(h.session.counter,1)
        with self.assertRaisesRegex(RuntimeError,'UNPUBLISHED_RESERVED_SEQUENCE_STOP'):h.settle()
        with self.assertRaises(RuntimeError):h.session.solve({},budget=h.budget)
        self.assertEqual(h.requests,1)
        self.assertFalse((h.session.workdir/'request_000001.request.json').exists())
        self.assertFalse((h.session.workdir/'request_000002.request.json').exists())
