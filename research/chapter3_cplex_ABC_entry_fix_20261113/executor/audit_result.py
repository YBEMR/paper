"""Independent read-only post-run audit. Can revoke, never create late success.

No CPLEX import/object/solve, no model rebuild and no thermal evaluation.
Residuals are recomputed with row-wise math.fsum rather than the worker CSR product.
"""
import argparse,hashlib,json,math
from fractions import Fraction
from pathlib import Path
import numpy as np
from scipy.io import loadmat

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))

def residuals(data,x,base):
    checks={}
    for key,rhs_name in [('A','b'),('Aeq','beq')]:
        a=data[key].tocsr();rhs=data[rhs_name].reshape(-1);worst=scaled=0.
        for i in range(a.shape[0]):
            begin,end=a.indptr[i:i+2];terms=[float(v)*float(x[j]) for v,j in zip(a.data[begin:end],a.indices[begin:end])]
            z=math.fsum(terms)-float(rhs[i]);v=abs(z) if key=='Aeq' else max(0.,z)
            worst=max(worst,v);scaled=max(scaled,v/(1+abs(float(rhs[i]))+math.fsum(map(abs,terms))))
        checks[key]=dict(absolute=worst,normalized=scaled,passed=worst<=1e-9 and scaled<=1e-9)
    for key,sign in [('lb',-1),('ub',1)]:
        bound=data[key].reshape(-1);v=[max(0.,sign*(float(a)-float(b))) for a,b in zip(x,bound) if math.isfinite(float(b))]
        checks[key]=dict(absolute=max(v,default=0.),passed=max(v,default=0.)<=1e-9)
    idx=data['intcon'].reshape(-1).astype(int)-base
    integer=max((abs(float(x[i])-round(float(x[i]))) for i in idx),default=0.)
    checks['integer']=dict(absolute=integer,passed=integer<=1e-6)
    return checks

def interval(e,scenes):
    if not e or e.get('state')!='SAFE' or e.get('rankable_energy') is not True:return None
    if set(e.get('scenes',{}))!=set(scenes):return None
    if not all(v.get('state')=='SAFE' and v.get('complete') is True and v.get('energy_accuracy_met') is True for v in e['scenes'].values()):return None
    if any(not isinstance(e.get(k),(int,float)) or not 0<=e[k]<590 for k in ('completed_at_elapsed_s','elapsed_s','archived_elapsed_s')):return None
    if e.get('numerical_protocol')!='directed-decimal60-taylor18-scaled100-v1':return None
    lo,hi=map(Fraction,e['weighted_energy_J']);return (lo,hi) if 0<=lo<=hi else None

def audit(root,plan_path,run):
    root=Path(root);run=Path(run);plan=read(plan_path);r=read(run/'controller_receipt.json');checks={}
    checks['plan_identity']=r['plan_sha256']==sha(plan_path)
    checks['all_recorded_files_unchanged']=all(sha(run/k)==h for k,h in r['evidence_hashes'].items())
    checks['frozen_inputs_unchanged']=all(sha(root/k)==h for k,h in plan['input_hashes'].items())
    checks['cleanup']=r['owned']['cleanup_ok'] is True and r['owned'].get('job_accounting',{}).get('active_processes',0)==0
    checks['within_method_window']=r['method_elapsed_s']<600
    c=read(run/'controller_completion.json') if (run/'controller_completion.json').exists() else {}
    checks['final_archive_completed_in_window']=bool(c.get('within_method_window') is True and c.get('after_receipt_and_hash_elapsed_s',600)<600 and
        c.get('receipt_sha256')==sha(run/'controller_receipt.json') and not (run/'budget_invalidated.json').exists())
    snapshot=r['outcome'].get('snapshot');details={};recomputed=False
    if snapshot:
        checks['snapshot_received_in_window']=r['outcome']['scientific_snapshot_accepted'] is True
        checks['calls_within_frozen_caps']=0<=snapshot['solve_attempts']<=1 and 0<=snapshot['complete_evaluation_attempts']<=4 and snapshot.get('full_build_attempts')==1
        if snapshot.get('native_response',{}):
            response=snapshot['native_response'];ack=snapshot.get('response_ack',{})
            checks['response_parent_received_by550']=ack.get('timely') is True and 0<=ack.get('received_elapsed_s',550)<550
            if response.get('vector') and (snapshot.get('final_admission') or {}).get('passed'):
                x=np.load(run/'final_vector.npy',allow_pickle=False)
                complement=loadmat(run/'complement_zero_based.mat')
                checks['final_binary64_shape_finite']=x.shape==(complement['c'].size,) and x.dtype==np.dtype('float64') and bool(np.isfinite(x).all())
                for name in ('original','complement'):
                    data=loadmat(run/(name+'_zero_based.mat'));n=data['c'].size
                    details[name]=residuals(data,x[:n],0)
                checks['independent_residuals']=all(q['passed'] for c in details.values() for q in c.values())
        initial=snapshot.get('initial');final=snapshot.get('final');validation=snapshot.get('final_admission') or {}
        scenes=plan['scene_ids'];a=interval(initial,scenes);b=interval(final,scenes)
        recomputed=bool(a and b and b[1]<a[0] and validation.get('same_initial') is False and validation.get('passed') is True and validation.get('legality',{}).get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED')
        checks['worker_strict_claim_recomputed']=recomputed==snapshot.get('strict_success',False)
    dispatch_file=run.parent/(run.name+'_dispatch_receipt.json')
    dispatch=read(dispatch_file)['record'] if dispatch_file.exists() else {}
    complete_file=run.parent/(run.name+'_outer_completion.json')
    complete=read(complete_file) if complete_file.exists() else {}
    checks['outer_cleanup_and_wall']=dispatch.get('outer_cleanup_ok') is True and dispatch.get('method_elapsed_including_shared_setup_s',600)<600 and not dispatch.get('supervisor_error')
    checks['outer_dispatch_archive']=complete.get('within_method_window') is True and not (run.parent/(run.name+'_outer_budget_invalidated.json')).exists()
    original_success=r['outcome']['strict_success'] is True
    return dict(audit_passed=all(checks.values()),checks=checks,independent_residual_details=details,
        retained_strict_success=bool(original_success and recomputed and all(checks.values())),original_strict_success=original_success,
        can_upgrade_scientific_credit=False,thermal_re_evaluations=0,solver_calls=0,
        limitation='Independent archival/timing/arithmetic audit only; SAFE uses sealed original evaluator evidence, not an independent physical implementation. Failed/partial runs remain failed/unknown.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--plan',required=True);p.add_argument('--run',required=True)
    a=p.parse_args();print(json.dumps(audit(a.workspace,a.plan,a.run),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
