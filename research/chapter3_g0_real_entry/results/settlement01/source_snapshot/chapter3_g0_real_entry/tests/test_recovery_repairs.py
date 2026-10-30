"""Focused repair tests. Only handmade receipts, fake processes and clocks."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from .support import TemporaryDirectory
from . import test_launch_boundaries as old_cases
from .test_transport import session_dependencies,FakeNativeMethods
from ...chapter3_g0.budget import G0Budget
from ...chapter3_g0.tests.fixtures import FakeClock
from .. import persistence,real_runner
from ..launch_contract import read,save,digest
from ..session import ScopedMatlabSession
from ..gating import WiringPermit


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='repair-');self.folder=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    context=old_cases.BoundaryTests.context
    checkpoint=old_cases.BoundaryTests.checkpoint

    def test_string_scope_self_contained_recovery_without_final_receipt(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint(nested=True)
        self.assertIsInstance(record['scope'],str)
        e=read(store.folder/'000001.json')
        self.assertEqual(e['schema'],'g0-complete-safe-checkpoint-v2')
        self.assertEqual(e['scope_evidence']['snapshot']['token'],record['scope'])
        self.assertEqual(len(e['scope_evidence']['parents']),1)
        self.assertEqual(e['record'],record)  # Original generation and hash are untouched.
        self.assertTrue(all(x['closed'] for x in budget.scope_records))
        self.assertFalse((self.folder/'result.json').exists())
        recovered=persistence.recover(store.folder,ctx,config,instance,100)
        self.assertEqual(recovered['status'],'RECOVERED',recovered)
        self.assertEqual(recovered['record'],record)

    def test_dictionary_scope_and_unknown_closed_token(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint(use_token=False)
        self.assertIsInstance(record['scope'],dict)
        self.assertEqual(persistence.recover(store.folder,ctx,config,instance,100)['status'],'RECOVERED')
        for scope in ('UNKNOWN_TOKEN',record['scope']['token']):
            bad=deepcopy(record);bad['scope']=scope
            with self.assertRaises(ValueError):store(bad)
        self.assertEqual(len(list(store.folder.glob('*.seal.json'))),1)

    def test_missing_parent_foreign_root_and_late_snapshot_fail_closed(self):
        config,instance,clock,budget,record,ctx,store=self.checkpoint(nested=True)
        p=store.folder/'000001.json';original=read(p)
        variants=[]
        bad=deepcopy(original);bad['scope_evidence']['parents']=[];variants.append(bad)
        bad=deepcopy(original);bad['scope_evidence']['snapshot']['root_identity']['token']='FOREIGN';variants.append(bad)
        bad=deepcopy(original);bad['scope_evidence']['snapshot']['deadline_elapsed_s']=0;variants.append(bad)
        bad=deepcopy(original);bad['scope_evidence']['snapshot']['deadline_elapsed_s']=200;variants.append(bad)
        bad=deepcopy(original);bad.pop('scope_evidence');variants.append(bad)
        for bad in variants:
            save(p,bad);save(p.with_suffix('.seal.json'),{'checkpoint_sha256':digest(bad),'published_at_elapsed_s':0})
            result=persistence.recover(store.folder,ctx,config,instance,100)
            self.assertEqual(result['status'],'ERROR');self.assertFalse(result['retained'])
        save(p,original);save(p.with_suffix('.seal.json'),{'checkpoint_sha256':digest(original),'published_at_elapsed_s':0})
        (store.folder/'000002.json.tmp').write_text('{')
        self.assertEqual(persistence.recover(store.folder,ctx,config,instance,100)['status'],'RECOVERED')
        (store.folder/'000003.json').write_text('{')  # No seal: interrupted publication, not a certificate.
        result=persistence.recover(store.folder,ctx,config,instance,100)
        self.assertEqual(result['status'],'RECOVERED');self.assertEqual(len(result['incomplete']),1)
        save(store.folder/'000003.seal.json',{'checkpoint_sha256':'BROKEN','published_at_elapsed_s':0})
        result=persistence.recover(store.folder,ctx,config,instance,100)
        self.assertEqual(result['status'],'ERROR');self.assertTrue(result['retained'])

    def method_packet(self):
        return {'error':None,'cleanup_verified':True,'wall_limit':False,'returncode':0,
                'within_process_deadline':True,'process_started_monotonic_s':100,
                'worker':{'result':{'execution_state':'NORMAL_TIME_LIMIT','safe_retained':True,
                    'post_eligible':True,'safe_candidate':{'HANDMADE':'A'},'safe_upper_bound_J':'1',
                    'weighted_energy_J':['1','1']}}}

    def recovered(self):
        return {'status':'RECOVERED','retained':True,'rejected':[],
                'record':{'candidate':{'HANDMADE':'A'},'U_J':'1.0','weighted_energy_J':['1','1']}}

    def run_fake(self,label,method,recovery,*,raises=False):
        folder=self.folder/label;folder.mkdir();calls=[]
        rt=SimpleNamespace(clock=lambda:100.,probe=lambda root:{'FAKE':True})
        def slot(ctx,out,mode,deadline,runtime,candidate=None):
            calls.append(mode)
            return deepcopy(method) if mode=='method' else {'FAKE_POST':'NO_EVALUATOR'}
        with patch.object(real_runner,'Runtime',return_value=rt), \
             patch.object(real_runner,'load_authorized',return_value=self.context()), \
             patch.object(real_runner,'host_gate',return_value={'passed':True}), \
             patch.object(real_runner,'consume_claim',return_value=folder/'SIMULATED_CLAIM_NO_REAL_CONSUMPTION'), \
             patch.object(real_runner,'verify_plan',return_value=None), \
             patch.object(real_runner,'read',return_value={'config':{},'instance':{}}), \
             patch.object(real_runner,'_slot',side_effect=slot), \
             patch.object(persistence,'recover',side_effect=RuntimeError('SIMULATED_RECOVERY_BUG') if raises else None,
                          return_value=recovery), \
             patch.object(real_runner,'post_state',return_value='COMPLETE_POST_SAFE'):
            result=real_runner.run('FAKE','FAKE','FAKE',folder)
        return result,calls

    def test_supervisor_stops_before_post_for_recovery_errors_and_mismatch(self):
        good=self.recovered();bad=deepcopy(good);bad['status']='ERROR';bad['rejected']=[{'error':'FAKE'}]
        empty={'status':'EMPTY','retained':False,'record':None,'rejected':[]}
        different=deepcopy(good);different['record']['candidate']={'HANDMADE':'OTHER'}
        contradictory=deepcopy(good);contradictory['status']='EMPTY'
        for label,recovered,raises,reason in (
                ('returned_error',bad,False,'RECOVERY_TECHNICAL_STOP'),
                ('thrown_error',None,True,'RECOVERY_TECHNICAL_STOP'),
                ('safe_missing_checkpoint',empty,False,'METHOD_SAFE_WITHOUT_VERIFIED_CHECKPOINT'),
                ('incoherent_status',contradictory,False,'RECOVERY_TECHNICAL_STOP'),
                ('foreign_candidate',different,False,'METHOD_CHECKPOINT_INCONSISTENCY')):
            result,calls=self.run_fake(label,self.method_packet(),recovered,raises=raises)
            self.assertEqual(calls,['method']);self.assertEqual(result['post_calls'],0)
            self.assertEqual(result['stop_reason'],reason)
            self.assertTrue(result['method']['worker']['result']['safe_retained'])

    def test_no_safe_is_not_technical_and_verified_safe_allows_only_one_mock_post(self):
        m=self.method_packet();m['worker']['result'].update(safe_retained=False,post_eligible=False,
                                                         execution_state='NO_SAFE_UNRESOLVED')
        empty={'status':'EMPTY','retained':False,'record':None,'rejected':[]}
        result,calls=self.run_fake('no_safe',m,empty)
        self.assertEqual(result['stop_reason'],'NO_COMPLETE_SAFE_NO_POST');self.assertEqual(calls,['method'])
        result,calls=self.run_fake('good',self.method_packet(),self.recovered())
        self.assertEqual(calls,['method','post']);self.assertEqual(result['post_calls'],1)
        self.assertEqual(result['stop_reason'],'COMPLETE_POST_SAFE')

    def test_late_ready_diagnostics_do_not_change_deadline_or_submit_request(self):
        clock=FakeClock();budget=G0Budget(300,clock=clock);folder=self.folder/'session'
        exe=self.folder/'fake_matlab.exe';exe.write_bytes(b'FAKE_NOT_EXECUTABLE')
        deps=session_dependencies(self.folder,clock);deps['matlab_path']=exe
        diag={'attempts':5,'transient_read_errors':{'FileNotFoundError':5},'last_read_error':'FAKE_MISSING_FILE'}
        class Timeout(TimeoutError):pass
        def read_timeout(path,deadline,*args):
            clock.advance(deadline-clock());e=Timeout('SIMULATED_PUBLICATION_TIMEOUT');e.diagnostics=deepcopy(diag);raise e
        def close_with_late_file(owner):
            clock.advance(9)
            (owner.workdir/'ready.json').write_text(json.dumps({'status':'READY','release':'2023b','license_checkout':True}))
            return FakeNativeMethods.close(owner)
        deps['read_json']=read_timeout
        deps['kernel'].MatlabSession=SimpleNamespace(solve=FakeNativeMethods.solve,close=close_with_late_file)
        with budget.scope('phase1',150,kind='phase'):
            with budget.scope('first_slot',48,kind='slot'):
                with self.assertRaises(Timeout) as caught:
                    ScopedMatlabSession(folder,budget=budget,permit=WiringPermit(),dependencies=deps)
        info=caught.exception.matlab_startup_metadata
        self.assertEqual(info['startup_publication_read'],diag)
        self.assertEqual(info['ready_read_deadline'],48)
        self.assertEqual(info['external_absolute_deadline'],300)
        self.assertEqual(info['startup_scope_snapshot']['kind'],'slot')
        self.assertEqual(info['startup_outcome'],'FAILED_OR_DEADLINE')
        late=info['failed_startup_publication_observation']
        self.assertTrue(late['observed']);self.assertEqual(late['status'],'READY')
        self.assertTrue(late['after_deadline']);self.assertFalse(late['accepted_for_startup'])
        self.assertEqual(deps['state']['requests'],[]);self.assertEqual(len(deps['state']['launches']),1)
