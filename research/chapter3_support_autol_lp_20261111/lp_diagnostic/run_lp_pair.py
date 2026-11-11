"""Bounded, one-shot LP diagnosis of the two published matrices only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import warnings

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
SOURCE=REPO/'research/chapter3_native_log_review_20261111/github_verified_run01'
UTC=dt.timezone.utc

def now(): return dt.datetime.now(UTC).isoformat()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,obj):
    with p.open('x',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def fingerprint(a):
    import numpy as np
    from scipy.sparse import issparse
    h=hashlib.sha256()
    if issparse(a):
        h.update(str((a.format,a.shape)).encode())
        for v in [a.data,a.indices,a.indptr]:
            h.update(str((v.dtype.str,v.shape)).encode());h.update(v.tobytes())
    else:
        a=np.asarray(a);h.update(str((a.dtype.str,a.shape)).encode());h.update(a.tobytes())
    return h.hexdigest()

def load_original(path):
    import numpy as np
    from scipy.io import loadmat
    m=loadmat(path)
    arrays={k:m[k] for k in ['c','A','b','Aeq','beq','lb','ub']}
    hashes={k:fingerprint(v) for k,v in arrays.items()}
    c=m['c'].ravel();b=m['b'].ravel();beq=m['beq'].ravel();lb=m['lb'].ravel();ub=m['ub'].ravel()
    ix=m['intcon'].ravel()
    assert len(c)==m['A'].shape[1]==m['Aeq'].shape[1]==len(lb)==len(ub)
    assert m['A'].shape[0]==len(b) and m['Aeq'].shape[0]==len(beq)
    assert np.all(np.isfinite(c)) and np.all(np.isfinite(b)) and np.all(np.isfinite(beq))
    assert np.all(np.isfinite(m['A'].data)) and np.all(np.isfinite(m['Aeq'].data))
    assert np.all(lb<=ub) and not np.any(np.isnan(lb)) and not np.any(np.isnan(ub))
    assert np.all(ix==np.round(ix)) and len(np.unique(ix))==len(ix) and np.all((ix>=1)&(ix<=len(c)))
    return m,hashes,dict(variables=len(c),inequality_rows=len(b),equality_rows=len(beq),
        nonzeros=int(m['A'].nnz+m['Aeq'].nnz),integer_indices=len(ix),index_origin='MATLAB one-based',
        integer_index_sha256=fingerprint(m['intcon']))

def freeze():
    import scipy,numpy
    import scipy.optimize._highspy._core as hc
    records={}
    archive=SOURCE/'R1_native_pair_20261110_run01_results.zip'
    assert digest(archive)=='b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1'
    source_manifest=read(SOURCE/'raw/local_records/execution_file_manifest.json')['files_sha256']
    for v in ['off','on']:
        p=SOURCE/f'raw/local_records/r1_pair_run01/{v}/method/matlab/request_000001.mat'
        assert digest(p)==source_manifest[f'local_records/r1_pair_run01/{v}/method/matlab/request_000001.mat']
        _,hashes,shape=load_original(p)
        records[v]=dict(path=str(p.relative_to(REPO)),sha256=digest(p),array_fingerprints=hashes,**shape)
    plan=dict(schema='archived-hold-last-lp-pair-v1',frozen_utc=now(),
        original_archive_sha256='b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1',
        original_source_commit='2fc52c63814d06b039e24a3bde887a2b411be298',records=records,
        environment=dict(python=sys.version,scipy=scipy.__version__,numpy=numpy.__version__,
            highs=f'{hc.HIGHS_VERSION_MAJOR}.{hc.HIGHS_VERSION_MINOR}.{hc.HIGHS_VERSION_PATCH}',platform=sys.platform),
        method='highs-ds',options=dict(presolve=False,disp=True,maxiter=100000,
            primal_feasibility_tolerance=1e-9,dual_feasibility_tolerance=1e-9,
            simplex_dual_edge_weight_strategy='steepest-devex'),
        method_budget_s_each=300,residual_and_archive_reserve_s=2,slot_watchdog_s=330,
        native_time_limit='remaining absolute per-slot budget minus 2s reserve; loading and verification counted',
        order=['off','on'],new_calls_each=1,retry=False,integrality_passed=False,x0_passed=False,
        changes='Only omit integer restrictions. Seven original arrays and bounds retained; no objective shift or model rebuilding.',
        comparison='Independent SciPy/HiGHS LP diagnosis, not MATLAB R2023b root LP or new auto-L scheduling comparison',
        residual_acceptance_tolerance=1e-9,numerical_certificate_only=True,
        thread_environment=dict(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'),
        highs_unchanged_defaults={k:getattr(hc.HighsOptions(),k) for k in ['small_matrix_value','large_matrix_value','threads','random_seed','parallel','simplex_strategy']},
        code_sha256=digest(Path(__file__)),documentation='https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.linprog-highs-ds.html')
    save(HERE/'plan.json',plan)
    print(json.dumps(plan,ensure_ascii=False,indent=2))

def worker(variant):
    # Scientific time includes NumPy/SciPy imports and all source/array checks.
    start=time.monotonic();started=now();deadline=start+300
    folder=HERE/variant;folder.mkdir(exist_ok=True)
    result=dict(variant=variant,started_utc=started,status='ERROR',new_lp_calls=0,
                independent_optimality_certificate=False,SAFE_claim=False)
    save(folder/'claim.json',dict(pid=os.getpid(),started_utc=started,plan_sha256=digest(HERE/'plan.json')))
    try:
        plan=read(HERE/'plan.json');assert digest(Path(__file__))==plan['code_sha256']
        import numpy as np
        import scipy
        from scipy.optimize import linprog
        assert scipy.__version__==plan['environment']['scipy'] and np.__version__==plan['environment']['numpy']
        source=REPO/plan['records'][variant]['path'];assert digest(source)==plan['records'][variant]['sha256']
        m,hashes,shape=load_original(source)
        assert hashes==plan['records'][variant]['array_fingerprints']
        result.update(source_sha256=digest(source),array_fingerprints_before=hashes,dimensions=shape,
                      load_and_verification_s=time.monotonic()-start)
        options=dict(plan['options']);options['time_limit']=max(0,deadline-time.monotonic()-plan['residual_and_archive_reserve_s'])
        if options['time_limit']<=0: raise RuntimeError('No remaining solver budget')
        result.update(options=options,solver_entered_at_s=time.monotonic()-start,new_lp_calls=1)
        save(folder/'solver_entered.json',dict(options=options,method=plan['method'],entered_utc=now(),at_method_s=time.monotonic()-start))
        t=time.monotonic()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            res=linprog(m['c'].ravel(),A_ub=m['A'],b_ub=m['b'].ravel(),A_eq=m['Aeq'],
                b_eq=m['beq'].ravel(),bounds=np.column_stack([m['lb'].ravel(),m['ub'].ravel()]),
                method=plan['method'],options=options)
        result.update(solver_call_s=time.monotonic()-t,solver_returned_at_s=time.monotonic()-start,
            warnings=[str(w.message) for w in caught],status=int(res.status),message=str(res.message),
            success=bool(res.success),objective=None if res.fun is None else float(res.fun),
            iterations=int(res.nit),crossover_iterations=int(res.crossover_nit))
        result['array_fingerprints_after']={k:fingerprint(m[k]) for k in hashes}
        result['seven_arrays_unchanged']=result['array_fingerprints_after']==hashes
        assert result['seven_arrays_unchanged'] and digest(source)==plan['records'][variant]['sha256']
        if res.x is not None:
            x=res.x;assert np.all(np.isfinite(x))
            a=m['A']@x-m['b'].ravel();eq=m['Aeq']@x-m['beq'].ravel()
            lb=m['lb'].ravel();ub=m['ub'].ravel()
            viol=dict(inequality=max(0.,float(a.max(initial=0))),equality=float(np.abs(eq).max(initial=0)),
                      lower_bound=max(0.,float((lb-x).max(initial=0))),upper_bound=max(0.,float((x-ub).max(initial=0))))
            result.update(residuals=viol,primal_residual_within_1e_9=max(viol.values())<=1e-9,
                          objective_recomputed=float(m['c'].ravel()@x),
                          max_original_integer_distance=float(np.abs(x[m['intcon'].ravel().astype(int)-1]-np.round(x[m['intcon'].ravel().astype(int)-1])).max(initial=0)))
            dual=res.ineqlin.marginals;deq=res.eqlin.marginals;dl=res.lower.marginals;du=res.upper.marginals
            station=m['c'].ravel()-m['A'].T@dual-m['Aeq'].T@deq-dl-du
            result['numerical_dual_checks']=dict(stationarity_inf=float(np.abs(station).max(initial=0)),
                inequality_sign_violation=max(0.,float(dual.max(initial=0))),
                lower_sign_violation=max(0.,float((-dl).max(initial=0))),upper_sign_violation=max(0.,float(du.max(initial=0))))
            np.savez_compressed(folder/'solution.npz',x=x,inequality_marginals=dual,equality_marginals=deq,lower_marginals=dl,upper_marginals=du)
        else:result['residuals']=None
    except Exception:
        result['error']=traceback.format_exc()
    result.update(ended_utc=now(),method_elapsed_s=time.monotonic()-start)
    result['completed_within_method_budget']=result['method_elapsed_s']<=300
    save(folder/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

def run():
    plan=read(HERE/'plan.json');assert digest(Path(__file__))==plan['code_sha256']
    save(HERE/'batch_claim.json',dict(started_utc=now(),plan_sha256=digest(HERE/'plan.json')))
    for variant in plan['order']:
        folder=HERE/variant;folder.mkdir(exist_ok=True)
        started=now();t=time.monotonic();cmd=[sys.executable,'-u',str(Path(__file__).resolve()),'worker','--variant',variant]
        env=os.environ.copy();env.update(plan['thread_environment'])
        with (folder/'stdout.log').open('xb') as out,(folder/'stderr.log').open('xb') as err:
            p=subprocess.Popen(cmd,stdout=out,stderr=err,env=env)
            try:rc=p.wait(timeout=plan['slot_watchdog_s']);expired=False
            except subprocess.TimeoutExpired:p.kill();rc=p.wait();expired=True
        record=dict(variant=variant,started_utc=started,ended_utc=now(),wall_s=time.monotonic()-t,
            argv=cmd,returncode=rc,watchdog_expired=expired)
        save(folder/'worker_return.json',record);print(json.dumps(record),flush=True)
    save(HERE/'batch_completed.json',dict(ended_utc=now(),new_calls_expected=2,retries=0))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run','worker']);a.add_argument('--variant',choices=['off','on']);args=a.parse_args()
    {'freeze':freeze,'run':run,'worker':lambda:worker(args.variant)}[args.action]()
