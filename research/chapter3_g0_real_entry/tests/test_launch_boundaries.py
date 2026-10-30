"""Artificial authorization/process/checkpoint tests; never real research."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest

from .support import TemporaryDirectory
from ...chapter3_g0.tests.fixtures import FakeClock,bundle
from ...chapter3_g0.budget import G0Budget,ScopeExhausted
from ...chapter3_g0.contract import canonical_hash
from .. import gating,launch_contract as c,backend,real_runner
from ..worker import execute_method,execute_post
from ..persistence import CheckpointStore,recover
from .test_receipt_profile import setup_profile


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='launch-boundary-');self.folder=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def context(self):
        return {'plan_sha256':'SIMULATED_PLAN','approval_sha256':'SIMULATED_APPROVAL',
                'plan_file':'SIMULATED','approval_file':'SIMULATED',
                'plan':{'input_sha256':c.INPUT_SHA,'source_sha256':{'FAKE':'FAKE'},
                        'python_executable':'NEVER_EXECUTED_FAKE_PYTHON'}}

    def test_real_string_or_opaque_object_does_not_grant_permission(self):
        for make in (lambda:gating.WiringPermit('REAL'),
                     lambda:gating.require_permit(SimpleNamespace(kind='REAL')),
                     lambda:gating.RealPermit({},object())):
            with self.assertRaises(PermissionError):make()

    def test_validated_ticket_capability_rejects_all_injected_real_dependencies(self):
        with patch.object(c,'validate_worker_ticket',return_value={'ticket':{'mode':'method'}}):
            p=gating.consume_worker_ticket('FAKE','FAKE','FAKE','FAKE','FAKE','method')
        self.assertEqual(gating.require_permit(p),'REAL')
        self.assertEqual(gating.require_simulation_dependencies(p,None),'REAL')
        for fake in ({},{'initializer':lambda:None}):
            with self.assertRaises(PermissionError):gating.require_simulation_dependencies(p,fake)
        with self.assertRaises(PermissionError):gating.require_role(p,'post')
        with self.assertRaises(PermissionError):backend.G0Backend(self.folder,permit=p,dependencies={})

    def test_pending_or_drifted_approval_cannot_launch(self):
        plan=self.folder/'plan.json';approval=self.folder/'approval.json'
        c.save(plan,{'source_sha256':{'x':'x'}})
        for value in ({'status':'PENDING_USER_APPROVAL'},
                      {'status':'APPROVED','plan_sha256':'FOREIGN'}):
            c.save(approval,value)
            with patch.object(c,'verify_plan',side_effect=lambda x:x):
                with self.assertRaises(PermissionError):c.load_authorized(plan,approval,c.sha(approval))
                with self.assertRaises(PermissionError):c.load_authorized(plan,approval,'WRONG_BYTES')
        # Positive SOFTWARE validation, with a deliberately fake human reference.
        # verify_plan is mocked, so this never authorizes a production dispatch.
        c.save(approval,{'status':'APPROVED','plan_sha256':c.sha(plan),'scope':c.SCOPE,
                        'input_sha256':c.INPUT_SHA,'source_manifest_sha256':c.digest({'x':'x'}),
                        'user_authorization_reference':'SIMULATION_ONLY_NOT_USER_APPROVAL'})
        with patch.object(c,'verify_plan',side_effect=lambda x:x):
            self.assertEqual(c.load_authorized(plan,approval,c.sha(approval))['plan_sha256'],c.sha(plan))

    def test_plan_rejects_scope_input_source_and_executable_drift(self):
        from ..prepare import freeze
        p=freeze(self.folder/'plan')
        self.assertFalse(p['execution_authorized'])
        self.assertEqual(c.verify_plan(p),p)
        for field,value in (('scope',{}),('input_sha256','x'),('source_sha256',{}),
                            ('executable_sha256',{})):
            bad=deepcopy(p);bad[field]=value
            with self.assertRaises(ValueError):c.verify_plan(bad)
        a=read=self.folder/'plan'/'approval_TEMPLATE_NOT_AUTHORIZED.json'
        with self.assertRaises(PermissionError):c.load_authorized(self.folder/'plan'/'plan.json',a,c.sha(a))

    def test_atomic_claim_replay_and_reused_output_rejected(self):
        ctx=self.context()
        with patch.object(c,'HERE',self.folder):
            output=self.folder/'results'/'batch'
            claim=c.consume_claim(ctx,output)
            self.assertTrue(claim.is_file())
            with self.assertRaises(FileExistsError):c.consume_claim(ctx,self.folder/'results'/'second')
            with self.assertRaises(ValueError):c.consume_claim(ctx,output)

    def test_ticket_wrong_token_role_deadline_monitor_and_second_consume_rejected(self):
        now=100.;ctx=self.context();out=self.folder/'results'/'batch';slot=out/'method'
        import sys
        ctx['plan']['python_executable']=sys.executable
        ticket=slot/'ticket.json';claim=self.folder/'claims'/'SIMULATED_PLAN.json'
        c.save(claim,{'output':str(out),'approval_sha256':'SIMULATED_APPROVAL'})
        t={'mode':'method','token':'ONE_USE','plan_sha256':'SIMULATED_PLAN',
           'approval_sha256':'SIMULATED_APPROVAL','process_started_monotonic_s':99.,
           'absolute_deadline_monotonic_s':399.}
        c.save(ticket,t)
        c.save(slot/'monitor_ready.json',{'token':'ONE_USE','plan_sha256':'SIMULATED_PLAN','pid':os.getpid()})
        with patch.object(c,'HERE',self.folder),patch.object(c,'load_authorized',return_value=ctx),patch.object(c.time,'monotonic',return_value=now):
            for token,mode in (('WRONG','method'),('ONE_USE','post')):
                with self.assertRaises(PermissionError):c.validate_worker_ticket('x','x','SIMULATED_APPROVAL',ticket,token,mode)
            expired=deepcopy(t);expired['absolute_deadline_monotonic_s']=99.5;c.save(ticket,expired)
            with self.assertRaises(PermissionError):c.validate_worker_ticket('x','x','SIMULATED_APPROVAL',ticket,'ONE_USE','method')
            c.save(ticket,t)
            good=c.validate_worker_ticket('x','x','SIMULATED_APPROVAL',ticket,'ONE_USE','method')
            self.assertEqual(good['ticket'],t)
            with self.assertRaises(FileExistsError):c.validate_worker_ticket('x','x','SIMULATED_APPROVAL',ticket,'ONE_USE','method')

    def test_backend_preparation_charged_to_same_root_and_phase150(self):
        clock=FakeClock(100)
        class Prepared:
            def __init__(self,*a,**k):
                clock.advance(9);self.timings={};self.search_records=[];self.numeric_context=None
            def close(self):return {'verified':True}
        seen={}
        def coordinator(loader,obj,*,seconds,clock,_wiring,_budget):
            seen.update(start=_budget.start,elapsed=_budget.elapsed,remaining=_budget.remaining)
            with _budget.scope('phase1',150,kind='phase'):
                self.assertEqual(_budget.remaining,141)
            return {'stopped_s':_budget.elapsed,'failure':None}
        import research.chapter3_g0.method as method
        with patch.object(backend,'G0Backend',Prepared),patch.object(method,'run_g0',coordinator):
            backend.execute_wiring(lambda:None,self.folder,permit=gating.WiringPermit(),
                                   dependencies={'FAKE':True},clock=clock)
        self.assertEqual(seen,{'start':100.,'elapsed':9.,'remaining':291.})

    def test_import_overhead_and_input_start_use_original_root(self):
        clock=FakeClock(110)
        def run(loader,folder,**kw):
            self.assertEqual(kw['budget'].start,100)
            self.assertEqual(kw['budget'].elapsed,10)
            return {'reason':'ROOT_CUTOFF','stopped_s':300,'final':None,'stages':{}}
        with patch('research.chapter3_g0_real_entry.worker.execute_wiring',run):
            r=execute_method('FAKE','FAKE',self.folder,permit=gating.WiringPermit(),
                             dependencies={},clock=clock,started_at=100)
        self.assertEqual(r['execution_state'],'NORMAL_TIME_LIMIT')

    def test_expired_start_never_prepares_backend(self):
        clock=FakeClock(401)
        with patch.object(backend,'G0Backend',side_effect=AssertionError('LATE_BACKEND')):
            r=execute_method('FAKE','FAKE',self.folder,permit=gating.WiringPermit(),dependencies={},
                             started_at=100,clock=clock)
        self.assertEqual(r['execution_state'],'NORMAL_TIME_LIMIT')
        self.assertFalse(r['safe_retained'])

    def test_post_only_has_time_remaining_after_spawn_import(self):
        clock=FakeClock(158);config,instance,candidate=bundle()
        def ev(i,c,a,b):
            self.assertEqual(b.start,100);self.assertEqual(b.remaining,2)
            clock.advance(3);b.check()
        with patch('research.chapter3_g0_real_entry.worker.load_common',return_value=(config,instance)):
            r=execute_post('FAKE','FAKE',candidate,permit=gating.WiringPermit(),
                dependencies={'evaluate_candidate':ev},started_at=100,clock=clock)
        self.assertEqual(r['state'],'UNRESOLVED')
        self.assertEqual(r['reason'],'ROOT_CUTOFF')

    def checkpoint(self,*,use_token=True,nested=False):
        from contextlib import nullcontext
        config,instance,candidate=bundle();clock=FakeClock(100)
        from ..receipts import DEFAULT_ACCURACY
        config['accuracy_targets']=deepcopy(DEFAULT_ACCURACY)
        budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        with budget.scope('phase1',150,kind='phase') as phase:
            inner=budget.scope('p1:X',75,kind='slot') if nested else nullcontext(phase)
            with inner as token:
                scope=token if use_token else budget.scope_snapshot(token)
                with ledger.patched():bridge.assess(candidate,scope=scope)
                record=archive.snapshot()
                # Explicit test-only envelope for the recovery validator; no real permit.
                record['evidence_kind']='REAL'
                record['generation_sha256']=canonical_hash({k:v for k,v in record.items() if k!='generation_sha256'})
                ctx=self.context();fakepermit=SimpleNamespace(context=ctx)
                store=CheckpointStore(self.folder/'checkpoints',fakepermit,budget,config,instance)
                store(record)
        return config,instance,clock,budget,record,ctx,store

    def test_crash_recovery_revalidates_existing_complete_receipt_without_heat(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint()
        r=recover(store.folder,ctx,config,instance,100)
        self.assertTrue(r['retained'],r['rejected']);self.assertEqual(r['record'],record)
        from ..worker import normalize
        normalized=normalize({'final':record,'input_sha256':canonical_hash(instance),'stages':{},'reason':'ROOT_CUTOFF'},
                             input_sha256='FAKE_BYTES',method_seconds=300,process_seconds=301)
        self.assertTrue(normalized['safe_retained'])  # 313/625 and 0.50080 are exactly equal.
        # Incomplete temp is ignored, old durable generation survives.
        (store.folder/'000002.json.tmp').write_text('{')
        self.assertTrue(recover(store.folder,ctx,config,instance,100)['retained'])

    def test_checkpoint_late_foreign_tampered_or_partial_is_not_accepted(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint()
        p=store.folder/'000001.json';original=c.read(p)
        for field,value in (('plan_sha256','FOREIGN'),('written_at_elapsed_s',300)):
            e=deepcopy(original);e[field]=value;c.save(p,e)
            c.save(p.with_suffix('.seal.json'),{'checkpoint_sha256':c.digest(e),'published_at_elapsed_s':301})
            self.assertFalse(recover(store.folder,ctx,config,instance,100)['retained'])
        c.save(p,original)
        self.assertFalse(recover(store.folder,ctx,config,instance,101)['retained'])
        stale=deepcopy(original);stale['scope_evidence']['snapshot']['deadline_elapsed_s']=0
        c.save(p,stale)
        c.save(p.with_suffix('.seal.json'),{'checkpoint_sha256':c.digest(stale),'published_at_elapsed_s':0})
        self.assertFalse(recover(store.folder,ctx,config,instance,100)['retained'])

    def test_no_new_checkpoint_or_energy_after_root_deadline(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint()
        clock.advance(300);store(record)
        self.assertEqual(len(list(store.folder.glob('*.seal.json'))),1)
        self.assertTrue(recover(store.folder,ctx,config,instance,100)['retained'])

    def fake_runtime(self,mode='normal',delay=2):
        clock=FakeClock(100);counts={'launch':0,'kills':0,'samples':0}
        class Proc:
            pid=1234
            def poll(self):return 0 if clock()>=100+delay else None
            def kill(self):counts['kills']+=1
        class Monitor:
            root_identity=None if mode=='bad_identity' else (1234,90)
            samples=[]
            def __init__(self,*a,**k):pass
            def sample(self,**k):counts['samples']+=1
            def cleanup_verified(self):return mode!='cleanup_failure'
            def terminate_owned(self,**k):counts['kills']+=1
            def register_identities(self,*a,**k):pass
            def summary(self):return {'kind':'FAKE_MONITOR'}
        def launch(args,out,err):counts['launch']+=1;return Proc()
        return SimpleNamespace(clock=clock,sleep=clock.advance,launch=launch,monitor=Monitor),counts

    def test_actual_supervisor_code_mock_single_launch_memory_and_no_retry(self):
        rt,counts=self.fake_runtime()
        r=real_runner._slot(self.context(),self.folder,'method',1000,rt)
        self.assertEqual(counts['launch'],1);self.assertTrue(r['cleanup_verified'])
        self.assertTrue((self.folder/'method'/'memory.json').is_file())
        self.assertEqual(r['process_elapsed_s'],2)
        with self.assertRaises(FileExistsError):real_runner._slot(self.context(),self.folder,'method',1000,rt)
        self.assertEqual(counts['launch'],1)

    def test_hard_post_deadline_or_unknown_ownership_stops_once(self):
        for mode,delay in (('normal',1000),('bad_identity',2),('cleanup_failure',2)):
            root=self.folder/mode;root.mkdir()
            rt,counts=self.fake_runtime(mode,delay)
            r=real_runner._slot(self.context(),root,'post',1000,rt,candidate={})
            self.assertEqual(counts['launch'],1)
            if mode=='normal':self.assertTrue(r['wall_limit']);self.assertGreater(counts['kills'],0)
            elif mode=='bad_identity':self.assertIn('OWNERSHIP',r['error'])
            else:self.assertFalse(r['cleanup_verified'])

    def test_semantic_post_negative_is_not_nonzero_technical_failure(self):
        _,instance,candidate=bundle();method={'safe_candidate':candidate,'weighted_energy_J':['1','1']}
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE','UNRESOLVED'):
            slot={'error':None,'cleanup_verified':True,'within_process_deadline':True,'returncode':2,
                  'worker':{'result':{'state':state,'identity':{'input_sha256':c.digest(instance),
                                  'candidate_sha256':c.digest(candidate)}}}}
            self.assertEqual(real_runner.post_state(slot,method,instance),'POST_'+state)
            slot['within_process_deadline']=False
            self.assertEqual(real_runner.post_state(slot,method,instance),'POST_TIME_LIMIT_UNRESOLVED')

    def test_real_dispatch_without_user_approval_never_probes_or_launches(self):
        with patch.object(real_runner,'load_authorized',side_effect=PermissionError('PENDING')), patch.object(real_runner,'Runtime') as rt:
            with self.assertRaises(PermissionError):real_runner.run('x','x','x',self.folder)
            rt.return_value.probe.assert_not_called();rt.return_value.launch.assert_not_called()
