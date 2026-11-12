"""Only fresh build/export/projection certification. Blocks process creation and evaluators."""
import time
ENTRY=time.monotonic()
from pathlib import Path
import argparse,json,sys,traceback
from contextlib import ExitStack
from unittest.mock import patch
from representation import load_science,build,export,certify,reduction_audit,digest,require

def save(path,value):
    with Path(path).open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,default=str,allow_nan=False)

def main(workspace,arm,out):
    out.mkdir(parents=True,exist_ok=False)
    import numpy as np
    from scipy.io import savemat,loadmat
    from scipy import optimize
    milp,cg=load_science(workspace)
    import thermal,matlab_bridge
    from timing import MethodBudget
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
    full=workspace/'work/stable_expression/full'
    instance=read(full/'input_instance.json'); config=read(full/'input_config.json')
    base=read(workspace/'work/equality_pair_source/bundle_manifest.json')['baseline_flags']
    budget=MethodBudget(900);budget.start=ENTRY;budget.deadline=ENTRY+900
    counts=dict(full_model_builds=0,native_calls=0,physical_evaluations=0,process_launches=0)
    def forbidden(*a,**k): raise AssertionError('Preflight forbids solver, MATLAB, subprocess and full physical evaluation')
    result=dict(arm=arm,passed=False,counts=counts,input_identity=digest(instance))
    try:
        with ExitStack() as stack:
            for target in ('subprocess.Popen','matlab_bridge.MatlabSession.__init__',
                           'thermal.evaluate_candidate','milp.evaluate_model_candidate'):
                stack.enter_context(patch(target,forbidden))
            stack.enter_context(patch.object(optimize,'milp',forbidden))
            stack.enter_context(patch.object(optimize,'linprog',forbidden))
            with budget.phase('fresh_full_build'):
                counts['full_model_builds']+=1
                model,gates=build(milp,instance,config,base,arm,budget)
            save(out/'model_summary.json',model.summary())
            save(out/'options.json',model.options)
            save(out/'gate_rows.json',[dict(row=i,gate=g) for i,g in gates.items()])
            with budget.phase('reduction_certificate_replay'):
                reduction=reduction_audit(model,config,arm,budget)
            save(out/'reduction_verification.json',reduction)
            with budget.phase('export'):
                old=export(model,np.zeros(len(model.names),dtype=np.float64))
            with budget.phase('complement_transform_and_exact_projection'):
                new,cert=certify(cg,old,gates,budget)
            save(out/'certificate.json',cert)
            for name,p in [('original',old),('represented',new)]:
                savemat(out/(name+'.mat'),p,do_compression=True,oned_as='column')
            historic=None
            if arm in ('B','C'):
                name='off' if arm=='B' else 'on'
                def payload(path):
                    d=loadmat(path,variable_names=list(cg.KEYS))
                    p={k:d[k].tocsc() if k in ('A','Aeq') else d[k].reshape(-1) for k in cg.KEYS}
                    p['intcon']=p['intcon'].astype(np.int64)-1
                    return p
                a,b=payload(full/(name+'.original.mat')),payload(full/(name+'.mat'))
                with budget.phase('historical_BC_exact_recheck'):
                    historic=cg.verify_equivalence(a,b,read(full/(name+'.certificate.json')))
                # x0 is intentionally construction-only zero in this preflight.
                for fresh,saved in [(old,a),(new,b)]:
                    hashes1=cg.array_digest(fresh);hashes2=cg.array_digest(saved)
                    require({k:v for k,v in hashes1.items() if k!='x0'}=={k:v for k,v in hashes2.items() if k!='x0'},'Fresh versus saved matrix drift')
            result.update(passed=True,original_variables=len(old['c']),represented_variables=len(new['c']),
                inequalities=old['A'].shape[0],represented_equalities=new['Aeq'].shape[0],
                integer_variables=len(old['intcon']),projection=cert['checks'],historical_exact_recheck=historic,
                zero_vector_is_feasible_or_SAFE_claim=False,initialization_not_executed=True)
    except Exception as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    result['timing']=budget.summary()
    result['timing']['clock_origin']='Process entry before imports and input reads; offline preflight, not a performance run'
    result['total_wall_s']=time.monotonic()-ENTRY
    save(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--arm',choices=['A','B','C'],required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();sys.exit(main(a.workspace,a.arm,a.out))
