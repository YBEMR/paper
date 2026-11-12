"""Read stored ABC matrices only: no model construction or optimizer calls."""
from pathlib import Path
import hashlib,json
import numpy as np
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parent/'formal_abc_execution_v1'
def j(p):return json.loads(p.read_text(encoding='utf-8'))
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def vec(v):return np.asarray(v).reshape(-1)
def stats(M):
    M=M.tocsr(); a=np.abs(M.data); positive=a[a>0]
    ratios=[]
    for i in range(M.shape[0]):
        d=np.abs(M.data[M.indptr[i]:M.indptr[i+1]]);d=d[d>0]
        if len(d):ratios.append(float(d.max()/d.min()))
    return dict(shape=M.shape,nnz=M.nnz,zero_stored=int(np.sum(a==0)),abs_min=float(positive.min()) if len(positive) else None,
                abs_max=float(positive.max()) if len(positive) else None,global_abs_ratio=float(positive.max()/positive.min()) if len(positive) else None,
                row_ratio_quantiles=np.quantile(ratios,[0,.5,.9,.99,1]).tolist() if ratios else [],
                rows_ratio_gt_1e6=sum(x>1e6 for x in ratios),rows_ratio_gt_1e12=sum(x>1e12 for x in ratios))
out={'scope':'read-only saved matrices, no construction, solver or physical evaluation','arms':{}}
payload={}
for arm in 'ABC':
    p=ROOT/arm
    old=loadmat(p/'original_zero_based.mat'); new=loadmat(p/'matlab/request_000001.mat')
    payload[arm]=old
    m=j(p/'model_summary.json')
    out['arms'][arm]={'original':{k:stats(old[k]) for k in ['A','Aeq']},'represented':{k:stats(new[k]) for k in ['A','Aeq']},
      'n_original':len(vec(old['c'])),'n_represented':len(vec(new['c'])),'n_integer':len(vec(old['intcon'])),
      'logical_binary':m['logical_binary_variables'],'events_per_scene':m['events_per_scene'],
      'gate_count':len(set(x['gate'] for x in j(p/'gate_rows.json'))),'options_sha256':h(p/'options.json'),
      'objective_nonzero_count':int(np.count_nonzero(old['c'])),'objective_sum':float(np.sum(old['c'])),
      'initial_objective':float(vec(old['c']) @ vec(old['x0'])),
      'original_x0_min':float(vec(old['x0']).min()),'original_x0_max':float(vec(old['x0']).max())}
    if arm=='C':
        nat=loadmat(p/'matlab/request_000001.native.mat',variable_names=['x','fval','exitflag','output'],simplify_cells=True)
        out['C_final']={'identical_to_represented_initial':bool(np.array_equal(vec(nat['x']),vec(new['x0']))),'different_coordinates':int(np.count_nonzero(vec(nat['x'])!=vec(new['x0']))),'output':nat['output']}
out['BC_options_byte_equal']=h(ROOT/'B/options.json')==h(ROOT/'C/options.json')
out['BC_intcon_equal']=bool(np.array_equal(vec(payload['B']['intcon']),vec(payload['C']['intcon'])))
# Derive deletion embedding from saved state proof order, not new model construction.
meta=j(ROOT/'C/model_summary.json')['preprocessing']['joint_state_pruning']['scenes']
bg=j(ROOT/'B/gate_rows.json');cg=j(ROOT/'C/gate_rows.json')
bgates=sorted(set(x['gate'] for x in bg));cgates=sorted(set(x['gate'] for x in cg))
states=[r for scene in meta.values() for interval in scene['interval_reports'] for r in interval['states']]
assert len(states)==len(bgates)
removed={g for g,s in zip(bgates,states) if s['status']!='UNKNOWN_NOT_PROVED'}
kept=[g for g in bgates if g not in removed]
assert len(kept)==len(cgates)
keepcols=np.array([i for i in range(payload['B']['A'].shape[1]) if i not in removed])
assert list(np.searchsorted(keepcols,kept))==cgates
droprows={x['row'] for x in bg if x['gate'] in removed}
keeprows=np.array([i for i in range(payload['B']['A'].shape[0]) if i not in droprows])
restricted=payload['B']['A'].tocsr()[keeprows][:,keepcols]
delta=(restricted-payload['C']['A']).tocsr();delta.eliminate_zeros()
diffrows=np.flatnonzero(np.diff(delta.indptr))
bdiff=vec(payload['B']['b'])[keeprows]-vec(payload['C']['b'])
out['BC_zero_deleted_gate_embedding']={
    'removed_gate_variables':len(removed),'removed_gate_off_rows':len(droprows),
    'kept_gate_index_mapping_matches_C':True,'matrix_difference_nnz':delta.nnz,
    'matrix_difference_row_count':len(diffrows),'matrix_difference_rows':diffrows.tolist(),
    'b_identical':bool(np.array_equal(vec(payload['B']['b'])[keeprows],vec(payload['C']['b']))),
    'b_difference_count':int(np.count_nonzero(bdiff)),'b_difference_rows':np.flatnonzero(bdiff).tolist(),
    'b_difference_min':float(bdiff.min()),'b_difference_max':float(bdiff.max()),
    'b_differences':[[int(i),float(vec(payload['B']['b'])[keeprows][i]),float(vec(payload['C']['b'])[i])] for i in np.flatnonzero(bdiff)],
    **{key+'_identical':bool(np.array_equal(vec(payload['B'][key])[keepcols],vec(payload['C'][key]))) for key in ('lb','ub','c','x0')},
    'max_abs_matrix_difference':float(np.max(np.abs(delta.data))) if delta.nnz else 0,
    'different_rows_are_last_424_energy_cuts':bool(np.all(diffrows>=restricted.shape[0]-424))}
Path(__file__).with_suffix('.json').write_text(json.dumps(out,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)),encoding='utf-8')
print(json.dumps(out,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)))
