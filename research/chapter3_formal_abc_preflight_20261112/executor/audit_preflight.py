"""Saved-artifact audit only; no rebuild, evaluator or optimizer."""
from pathlib import Path
import json,sys,time
from guard import read,save,sha
from representation import load_science,require,digest

def run(workspace,out):
    start=time.monotonic()
    import numpy as np
    from scipy.io import loadmat
    _,cg=load_science(workspace)
    root=workspace/'work/formal_abc_preflight_v1';full=workspace/'work/stable_expression/full'
    records={}
    def payload(path,native=False):
        d=loadmat(path,variable_names=list(cg.KEYS))
        p={k:d[k].tocsc() if k in ('A','Aeq') else d[k].reshape(-1) for k in cg.KEYS}
        if native:p['intcon']=p['intcon'].astype(np.int64)-1
        return p
    for arm,directory in [('A','A'),('B','B'),('C','C_corrected')]:
        folder=root/directory;old=payload(folder/'original.mat');new=payload(folder/'represented.mat')
        certificate=read(folder/'certificate.json');t=time.monotonic()
        verification=cg.verify_equivalence(old,new,certificate)
        same=None
        if arm!='A':
            tag='off' if arm=='B' else 'on'
            same={}
            for name,p,q in [('original',old,payload(full/(tag+'.original.mat'),True)),
                             ('represented',new,payload(full/(tag+'.mat'),True))]:
                tests={}
                for k in cg.KEYS:
                    if k=='x0':continue
                    tests[k]=((p[k]!=q[k]).nnz==0 if k in ('A','Aeq') else np.array_equal(p[k],q[k]))
                require(all(tests.values()),'Fresh physical matrices differ: '+arm+name)
                same[name]=dict(exact_values_identical=tests,fresh_integer_index_dtype=str(p['intcon'].dtype),
                    historical_integer_index_dtype=str(q['intcon'].dtype),integer_values_identical=True)
        records[arm]=dict(directory=directory,projection=verification,exact_audit_s=time.monotonic()-t,
            original_variables=len(old['c']),represented_variables=len(new['c']),rows=old['A'].shape[0],
            equalities=new['Aeq'].shape[0],integer_variables=len(old['intcon']),historical_comparison=same,
            reduction=read(folder/'reduction_verification.json'),
            certificate_file_sha256=sha(folder/'certificate.json'),original_file_sha256=sha(folder/'original.mat'),
            represented_file_sha256=sha(folder/'represented.mat'))
    oldplan=read(workspace/'work/budget_protocol_v2/candidate_on/plan.json');protected=0
    for key,base in [('workspace_files',workspace),('package_files',workspace/'work/budget_protocol_v2/candidate_on')]:
        for name,expected in oldplan[key].items():
            require(sha(base/name)==expected,'Historical frozen source changed: '+name);protected+=1
    small=read(workspace/'work/stable_expression/small_run/results.json');require(small['passed'],'Historical small gate failed')
    instance=read(full/'input_instance.json')
    identity=dict(stages=sum(len(s['stage_instances']) for s in instance['scenarios']),
        modes=sum(len(v) for v in instance['stage_modes'].values()),input_sha256=digest(instance))
    require(identity['stages']==12 and identity['modes']==66,'R1 task drift')
    result=dict(passed=True,groups=records,input=identity,historical_small_counts=small['counts'],
        historical_small_sha256=sha(workspace/'work/stable_expression/small_run/results.json'),
        historical_frozen_files_unchanged=protected,wall_s=time.monotonic()-start,
        this_audit_counts=dict(builds=0,physical_evaluations=0,native_calls=0),
        engineering_corrections=['B byte comparison was index-storage width int32/int64 only; exact numerical values identical',
            'C empty deleted-state set has no states list; replay accepts only states_checked=0 and empty expected set',
            'Preflight zero x0 is a coordinate-map placeholder, not a feasible or SAFE witness',
            'A/B early timing labels incorrectly said imports excluded; actual ENTRY preceded imports; labels corrected by this addendum'])
    save(out,result);print(json.dumps(dict(passed=True,groups=list(records),wall_s=result['wall_s'])))

if __name__=='__main__':
    run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]))
