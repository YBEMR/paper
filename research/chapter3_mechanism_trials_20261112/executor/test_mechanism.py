"""Finite trial wiring and single-option intervention tests; no scientific execution."""
import json,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from guard import TRIALS,read,save,sha,verify_approval,verify_plan
from test_control import test_directory
from control import next_arms
from evidence import progress
from runtime import Runtime
from saved_adapter_base import Runtime as BaseRuntime

PACKAGE=Path(__file__).resolve().parent
WORKSPACE=PACKAGE.parents[1]

class MechanismControls(unittest.TestCase):
    def test_fixed_mapping_and_order(self):
        self.assertEqual(list(TRIALS),['C_repeat','B_repeat','C_noheur'])
        self.assertEqual([v['model_arm'] for v in TRIALS.values()],['C','B','C'])
        self.assertEqual([v['Heuristics'] for v in TRIALS.values()],['basic','basic','none'])
    def test_native_variant_only_one_assignment(self):
        original=(WORKSPACE/'work/equality_pair_source/research/chapter3_experiments/solve_model.m').read_bytes()
        variant=(PACKAGE/'native_none/solve_model.m').read_bytes()
        line="        opts.Heuristics = 'none'; % Predeclared mechanism trial; sole native option intervention.\n"
        line=line.encode('utf-8');self.assertEqual(variant.count(line),1);self.assertEqual(variant.replace(line,b''),original)
    def test_script_selection_and_restoration_without_launch(self):
        for trial in TRIALS:
            r=Runtime(WORKSPACE,PACKAGE,Path('unused'),{'trials':TRIALS},Path('unused'),0,arm=trial)
            original=Path('original');r.bridge=SimpleNamespace(HERE=original)
            observed=[]
            with patch.object(BaseRuntime,'start_native',lambda s:observed.append(s.bridge.HERE)):
                r.start_native()
            self.assertEqual(observed,[PACKAGE/'native_none' if trial=='C_noheur' else original])
            self.assertEqual(r.bridge.HERE,original)
    def test_script_selection_restored_after_error(self):
        r=Runtime(WORKSPACE,PACKAGE,Path('unused'),{'trials':TRIALS},Path('unused'),0,arm='C_noheur')
        original=Path('original');r.bridge=SimpleNamespace(HERE=original)
        with patch.object(BaseRuntime,'start_native',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):r.start_native()
        self.assertEqual(r.bridge.HERE,original)
    def test_model_scoped_stops_cover_both_c_trials(self):
        base=dict(cleanup={'complete':True},identity_after={'state':'VERIFIED'},fault_scope='FEATURE',affected_arms=['C'])
        self.assertEqual(next_arms(list(TRIALS),[],base,TRIALS),['B_repeat'])
        base['affected_arms']=['B','C'];self.assertEqual(next_arms(list(TRIALS),[],base,TRIALS),[])
    def test_trial_local_fault_does_not_censor_other_c_trial(self):
        base=dict(cleanup={'complete':True},identity_after={'state':'VERIFIED'},fault_scope='ARM',affected_arms=['C_repeat'])
        self.assertEqual(next_arms(list(TRIALS),['C_repeat'],base,TRIALS),['B_repeat','C_noheur'])
    def test_shared_or_cleanup_fault_stops_all_trials(self):
        base=dict(cleanup={'complete':True},identity_after={'state':'VERIFIED'},fault_scope='ALL',affected_arms=[])
        self.assertEqual(next_arms(list(TRIALS),[],base,TRIALS),[])
        base.update(fault_scope=None,cleanup={'complete':False});self.assertEqual(next_arms(list(TRIALS),[],base,TRIALS),[])
    def test_prior_abc_approval_rejected(self):
        old=dict(approved=True,plan_sha256='hash',protocol='full-R1-fresh-ABC-v1',arms=['A','B','C'],maximum_native_calls_per_arm=1,total_window_s=600,retries=0,user_decision_reference='old')
        with self.assertRaises(PermissionError):verify_approval(old,'hash')
        new=dict(old,protocol='full-R1-mechanism-trials-v1',arms=list(TRIALS),user_decision_reference='current explicit design then execute instruction')
        verify_approval(new,'hash')
        new['arms'].append('C_retry')
        with self.assertRaises(PermissionError):verify_approval(new,'hash')
    def test_rootlp_fval_separate_from_global_lowerbound(self):
        p=progress([dict(event_number=1,received_elapsed_s=10,values={'phase':'rootlp','fval':.75})],'1',550,'0')
        self.assertTrue(p['root_lp_completion_observed']);self.assertFalse(p['root_lp_completion_via_later_phase'])
        self.assertEqual(p['root_lp_completion_basis'],'ROOTLP_CALLBACK');self.assertEqual(p['finite_bounds'],[])
        self.assertEqual(p['root_lp_native_objectives'][0]['value'],.75)
    def test_init_done_counter_does_not_prove_completion_or_candidate(self):
        p=progress([dict(event_number=1,kind='callback',state='done',received_elapsed_s=10,values={'phase':'','numfeaspoints':1},x=[])],'1',550,'0')
        self.assertFalse(p['root_lp_completion_observed']);self.assertEqual(p['callback_vectors'],[])
    def test_actual_trial_options_and_native_script_identity(self):
        for trial in TRIALS:
            with test_directory() as t:
                folder=Path(t);root=folder/'matlab';root.mkdir()
                plan={'trials':TRIALS,'native_options':{'Heuristics':'basic','MaxTime':'dynamic'}}
                r=Runtime(WORKSPACE,PACKAGE,Path('unused'),plan,folder,time.monotonic(),arm=trial)
                r.new='payload';r.cg=SimpleNamespace(array_digest=lambda a:a);r.payload=lambda p:'payload'
                r.allocation={'native_seconds':400}
                (root/'request_000001.mat').write_bytes(b'mocked by test')
                save(root/'request_000001.request.json',{'solver_max_time_s':400,'solver_max_time_s_declared':400})
                save(root/'ready.json',{'release':'2023b'})
                script=(PACKAGE/'native_none/solve_model.m' if trial=='C_noheur' else WORKSPACE/'work/equality_pair_source/research/chapter3_experiments/solve_model.m')
                session={'source_sha256':{'solve_model.m':sha(script),'matlab_bridge.py':sha(WORKSPACE/'work/equality_pair_source/research/chapter3_experiments/matlab_bridge.py')}}
                save(root/'session.json',session)
                n={'options':{'Heuristics':TRIALS[trial]['Heuristics'],'MaxTime':400}}
                self.assertEqual(r.inspect_identity(n)['state'],'VERIFIED')
                n['options']['Heuristics']='advanced'
                self.assertEqual(r.inspect_identity(n,True)['state'],'INVALID')

if __name__=='__main__':unittest.main(verbosity=2)
