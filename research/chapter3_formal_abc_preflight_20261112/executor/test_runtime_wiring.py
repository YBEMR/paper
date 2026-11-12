"""Exercise production fresh-preparation wiring with synthetic builder/evaluator receipts."""
import time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_control import test_directory,safe
from representation import load_science,digest
from guard import read,environment_snapshot

class RuntimeWiring(unittest.TestCase):
    def test_all_arms_prepare_fresh_and_certify_without_scientific_calls(self):
        workspace=Path(__file__).resolve().parents[2]
        milp,cg=load_science(workspace)
        import numpy as np
        from scipy.sparse import csc_matrix
        import runtime,initial_point,initial_schedule
        instance=read(workspace/'work/stable_expression/full/input_instance.json')
        initial={'scenes':{s['id']:[] for s in instance['scenarios']}}
        plan={'input_identity':digest(instance),'initial_candidate_identity':digest(initial),'baseline_flags':{},'environment':environment_snapshot()}
        payload=dict(c=np.array([1.]),A=csc_matrix([[1.]]),b=np.array([1.]),
            Aeq=csc_matrix((0,1)),beq=np.array([],dtype=float),lb=np.array([0.]),ub=np.array([1.]),intcon=np.array([0],dtype=np.int64))
        observed=[]
        def fake_build(m,i,c,b,arm,budget):
            observed.append(arm)
            return SimpleNamespace(instance=i,options=[],names=['synthetic'],summary=lambda:{'mock':True},
                                   as_solver_dict=lambda:{k:v.copy() for k,v in payload.items()}),{0:0}
        def iterator(*a,**k):
            self.assertEqual(k['max_attempts'],3)
            yield dict(status='COMPLETE_LEGAL_CANDIDATE',candidate=initial)
        with patch('subprocess.Popen',side_effect=AssertionError('Forbidden native/process entry')), \
             patch.object(runtime,'build',fake_build),patch.object(runtime,'reduction_audit',return_value={'mock':True}), \
             patch.object(initial_schedule,'iter_initial_candidates',iterator), \
             patch.object(initial_point,'complete_initial_point',side_effect=lambda *a,**k:{'state':'INITIAL_POINT_READY','x0':np.array([0.])}), \
             patch.object(milp,'evaluate_model_candidate',side_effect=lambda *a,**k:safe(.1)), \
             patch.object(runtime,'decode',return_value=(initial,{'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'})):
            for arm in ['A','B','C']:
                with test_directory() as t:
                    r=runtime.Runtime(workspace,Path(__file__).parent,Path('unused'),plan,Path(t),time.monotonic(),arm=arm)
                    r.prepare()
                    self.assertEqual(r.model_builds,1);self.assertEqual(r.evaluations,1);self.assertIsNone(r.session)
                    self.assertTrue(all(r.certificate['checks'].values()))
                    self.assertEqual(r.native_new['x0_validation']['provided'],True)
        self.assertEqual(observed,['A','B','C'])

if __name__=='__main__':unittest.main(verbosity=2)
