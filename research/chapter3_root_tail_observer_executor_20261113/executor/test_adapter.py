"""Toy MAT/JSON transport wiring with fake science and fake MATLAB session."""
import io,json,sys,tempfile,time,types,unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse
from scipy.io import savemat
from runtime import Runtime
from guard import save,sha
from saved_adapter_base import digest
from test_control import safe,profile_fixture

class AdapterTests(unittest.TestCase):
    def test_saved_adapter_uses_same_arrays_initialization_options_and_one_fake_request(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);full=root/'work/stable_expression/full';full.mkdir(parents=True)
            source=root/'saved';(source/'matlab').mkdir(parents=True)
            dest=root/'run';dest.mkdir();package=root/'package';(package/'native').mkdir(parents=True)
            (package/'native/solve_model.m').write_text('SYNTHETIC_NOT_MATLAB')
            sci=root/'work/equality_pair_source/research/chapter3_experiments';sci.mkdir(parents=True)
            (sci/'matlab_bridge.py').write_text('SYNTHETIC_FAKE_BRIDGE')
            instance={'scenarios':[{'id':'AB'},{'id':'AC'}]}
            initial={'scenes':{s:[dict(stage_id='s',unit='u',opp='f',start_ms='0')] for s in ('AB','AC')}}
            options=[dict(scenario_id=s,stage_instance_id='s',unit_id='u',opp_id='f',start_ms='0') for s in ('AB','AC')]
            old=dict(c=np.array([.5,.5]),A=sparse.csc_matrix((0,2)),b=np.array([]),Aeq=sparse.csc_matrix((0,2)),beq=np.array([]),
                lb=np.zeros(2),ub=np.ones(2),intcon=np.array([0,1],dtype=np.int64),x0=np.ones(2))
            new={**old,'intcon':np.array([1.,2.])}
            savemat(source/'original_zero_based.mat',old,oned_as='column');savemat(source/'matlab/request_000001.mat',new,oned_as='column')
            def arrays(p): return {k:digest(p[k].toarray().tolist() if sparse.issparse(p[k]) else p[k].tolist()) for k in p}
            cert={'source_array_sha256':arrays(old),'derived_array_sha256':arrays(old),'checks':{'mock':True},'gate_complements':[],'fixed_constants':[]}
            for path,data in [(full/'input_instance.json',instance),(full/'input_config.json',{'accuracy_targets':{}}),
                (source/'options.json',options),(source/'initialization.json',{'attempts':[{'candidate':initial}]}),(source/'representation_certificate.json',cert)]:save(path,data)
            cg=types.SimpleNamespace(KEYS=list(old),array_digest=arrays,inverse_vector=lambda x,c:x)
            calls=[]
            class Budget:
                def __init__(self,_): self.start=time.monotonic();self.deadline=self.start+600
                @property
                def elapsed(self): return time.monotonic()-self.start
                def phase(self,name): return contextmanager(lambda: (yield))()
            class Exhausted(Exception): pass
            def evaluate(inst,candidate,accuracy,budget):
                calls.append(('fake_evaluate',inst,candidate));return safe(budget.elapsed)
            bridge=types.SimpleNamespace(HERE=sci,REPO=root,subprocess=types.SimpleNamespace(),_read_json_until=lambda *a:None,
                _json=lambda p,v:save(p,v),InitialPointRejected=ValueError,
                _prepare=lambda p,x0:dict(x0_validation={'provided':True,'mock':True}),
                _check_initial_point=lambda p,x:(x,{'mock':True}),cleanup_is_complete=lambda c:True)
            plan=dict(environment={'mock':True},saved_directory='saved',input_identity=digest(instance),initial_candidate_identity=digest(initial),
                      matlab='FORBIDDEN_FAKE_PATH',native_options={'Display':'iter','Heuristics':'none','MaxTime':'dynamic'})
            clock=[80.2]
            r=Runtime(root,package,package/'plan.json',plan,dest,time.monotonic()-clock[0])
            native_options=None
            class Session:
                def __init__(self,folder,**kw):
                    calls.append(('fake_session',bridge.HERE,kw));self.folder=folder;folder.mkdir();self.cleanup={}
                    save(folder/'ready.json',{'release':'2023b'})
                    save(folder/'session.json',{'source_sha256':{'solve_model.m':sha(package/'native/solve_model.m'),'matlab_bridge.py':sha(sci/'matlab_bridge.py')}})
                def solve(self,p,**kw):
                    calls.append(('fake_solve',p,kw));savemat(self.folder/'request_000001.mat',new,oned_as='column')
                    bridge._json(self.folder/'request_000001.request.json',{'remaining_s':469.8})
                    profile,obs=profile_fixture()
                    for entry in profile['FunctionTable']: entry['FileName']=str(package/'native/solve_model.m')
                    savemat(self.folder/'request_000001.profile.mat',{'profileData':profile})
                    obs.update(profile_archived=True,profile_status={'ProfilerStatus':'on','Timer':'performance','DetailLevel':'mmex','HistoryTracking':'timestamp','HistorySize':100000},profile_status_after={'ProfilerStatus':'off'})
                    opt=dict(plan['native_options'],MaxTime=r.allocation['native_seconds'])
                    return dict(status='SOLVED',budget_valid=True,accepted_for_evaluation=True,x=[1.,1.],options=opt,observation=obs)
                def close(self): calls.append(('fake_close',))
            bridge.MatlabSession=Session
            class Sampler:
                def __init__(self,*a): pass
                def start_thread(self): calls.append(('fake_sampler_start',))
                def stop(self):return dict(complete=True,sample_count=10)
            modules={'complement_gate':cg,'matlab_bridge':bridge,'timing':types.SimpleNamespace(MethodBudget=Budget),
                     'thermal':types.SimpleNamespace(evaluate_candidate=evaluate,Exhausted=Exhausted),
                     'schedules':types.SimpleNamespace(validate_schedule=lambda *a:{'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'})}
            with patch.dict(sys.modules,modules),patch('runtime.environment_snapshot',return_value={'mock':True}),patch.object(r,'_permit'),patch('runtime.OwnedSampler',Sampler):
                r.prepare();e=r.evaluate_initial();self.assertEqual(r.evaluations,1)
                r.start_native();n=r.solve(None);identity=r.inspect_identity(n);self.assertEqual(identity['state'],'VERIFIED')
                v=r.validate_returned(n['x']);self.assertEqual(v['state'],'ADMITTED');self.assertTrue(v['same_initial'])
                r.evaluate_returned(v['candidate']);packet=r.finish_observation(n)
                self.assertTrue(packet['profile_packet_timely']);self.assertTrue(packet['profile_settings_verified'])
                self.assertEqual(packet['profile_analysis']['alignment'],'BOUNDED')
                self.assertEqual(r.evaluations,2)
                with self.assertRaises(RuntimeError): r.solve(None)
                with self.assertRaises(RuntimeError): r.start_native()
                with self.assertRaises(RuntimeError): r.evaluate_initial()
                r.close()
            self.assertEqual([c[0] for c in calls].count('fake_solve'),1)
            self.assertEqual([c[0] for c in calls].count('fake_session'),1)
            solve=[c for c in calls if c[0]=='fake_solve'][0]
            self.assertTrue(np.array_equal(solve[1]['intcon'],old['intcon']))
            self.assertTrue(np.array_equal(solve[2]['x0'],old['x0']))
            self.assertIsNone(solve[2]['solver_max_time_s'])
