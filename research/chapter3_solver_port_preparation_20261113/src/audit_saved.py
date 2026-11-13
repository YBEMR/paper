"""Read saved arrays/certificates and deep-copy roundtrip. No physical reconstruction.

Usage: python audit_saved.py --workspace <workspace-root> --output <new-json>
Published inputs are in the historical mechanism trial archive, not regenerated.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from contract import MatrixPacket, FakeBackend


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root):
    started=time.perf_counter()
    base=root/'work/mechanism_trials_execution_v1/C_noheur'
    records={};packets={}
    for name,intbase in [('original_zero_based.mat',0),('matlab/request_000001.mat',1)]:
        path=base/name
        d=loadmat(path,variable_names=['c','A','b','Aeq','beq','lb','ub','intcon','x0'])
        n=d['c'].size
        p=MatrixPacket.read(d,intcon_base=intbase,sense='min',objective_constant=0.,column_ids=range(n))
        p.assert_same(FakeBackend().load_and_readback(p));packets[name]=p
        records[name]=dict(file_sha256=sha(path),canonical_arrays_sha256=p.hashes(),variables=n,
            inequality_rows=p.A[0][0],equality_rows=p.Aeq[0][0],nnz=len(p.A[3])+len(p.Aeq[3]),
            integer_count=len(p.intcon),all_integer_columns_binary_bounds=bool(np.all(p.lb[p.intcon]==0)&np.all(p.ub[p.intcon]==1)),
            continuous_variables=n-len(p.intcon),bounds_all_finite=bool(np.isfinite(p.lb).all()&np.isfinite(p.ub).all()),
            complete_start_length=len(p.x0),roundtrip='BITWISE_IDENTICAL_FAKE_BACKEND_ONLY')
    old,new=packets.values()
    checks=dict(integer_indices_unchanged=np.array_equal(old.intcon,new.intcon),
                original_prefix_x0_bitwise=old.x0.tobytes()==new.x0[:old.n].tobytes(),
                original_prefix_c_bitwise=old.c.tobytes()==new.c[:old.n].tobytes(),
                added_objective_coefficients_zero=bool(np.all(new.c[old.n:]==0)))
    sources=[base/x for x in ['representation_certificate.json','reduction_verification.json','initialization.json',
        'initial_admission.json','initial_evaluation_1.json','options.json','model_summary.json','gate_rows.json']]
    sources += [root/'work/stable_expression/full'/x for x in ['input_config.json','input_instance.json']]
    sources += [root/'work/root_tail_observer_v1'/x for x in ['plan.json','plan.identity.json']]
    sources += [root/'work/publish_repo/research/chapter3_experiments/milp.py']
    cert=json.loads((base/'representation_certificate.json').read_text(encoding='utf-8'))
    admission=json.loads((base/'initial_admission.json').read_text(encoding='utf-8'))
    return dict(mode='SAVED_ARRAY_READ_ONLY_NO_NATIVE_OBJECT',records=records,checks=checks,
        source_hashes={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sources},
        certificate_checks=cert.get('checks'),
        inherited_numerical_admission={k:admission[k] for k in ('original','transformed')},
        admission_note='Historical 1e-9/1e-6 tolerance checks only; not a new exact-feasibility or native start-acceptance proof',
        elapsed_s=time.perf_counter()-started,optimization_calls=0,MATLAB_sessions=0,full_R1_builds=0,
        thermal_evaluations=0,native_model_constructions=0,real_backend_readback='NOT_RUN',native_start_acceptance='UNKNOWN')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=run(a.workspace.resolve())
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('checks','elapsed_s','records')},ensure_ascii=True))
