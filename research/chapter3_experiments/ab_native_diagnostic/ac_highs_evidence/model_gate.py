"""highspy option and model readback; deterministic no-deletion scaling audit."""
from pathlib import Path
import hashlib,json
import numpy as np
from scipy import sparse
from scipy.io import loadmat
import highspy
EXPECTED='bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7'
OPTIONS={'small_matrix_value':1e-12,'time_limit':300.0,'presolve':'off','mip_rel_gap':0.0,'threads':1}
def array_hash(a):
 a=np.asarray(a);return hashlib.sha256(str(a.shape).encode()+str(a.dtype).encode()+a.tobytes()).hexdigest()
def read_source(path):
 if hashlib.sha256(path.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('AC input identity mismatch')
 d=loadmat(path);m=sparse.vstack((d['A'],d['Aeq']),format='csc');n=m.shape[1]
 ints=np.zeros(n,np.int32);indices=d['intcon'].ravel()
 if not np.array_equal(indices,indices.astype(int)):raise ValueError('Nonintegral intcon')
 ints[indices.astype(int)-1]=1
 return d,m,ints
def compare(h,d,m,ints):
 lp=h.getLp();a=lp.a_matrix_
 if a.format_!=highspy.MatrixFormat.kColwise:raise ValueError('Unexpected native matrix format')
 v=np.asarray(a.value_,float);ix=np.asarray(a.index_,np.int32);ptr=np.asarray(a.start_,np.int32)
 checks={'dimensions':(lp.num_row_,lp.num_col_)==m.shape,'objective':np.array_equal(lp.col_cost_,d['c'].ravel()),
  'offset':lp.offset_==0,'sense':lp.sense_==highspy.ObjSense.kMinimize,'lower_bounds':np.array_equal(lp.col_lower_,d['lb'].ravel()),
  'upper_bounds':np.array_equal(lp.col_upper_,d['ub'].ravel()),'integer_domain':np.array_equal(np.array([int(i) for i in lp.integrality_]),ints),
  'row_lower':np.array_equal(lp.row_lower_,np.r_[np.full(d['A'].shape[0],-np.inf),d['beq'].ravel()]),
  'row_upper':np.array_equal(lp.row_upper_,np.r_[d['b'].ravel(),d['beq'].ravel()]),
  'CSC_values':np.array_equal(v,m.data),'CSC_indices':np.array_equal(ix,m.indices),'CSC_pointers':np.array_equal(ptr,m.indptr),
  'nonzeros':h.getNumNz()==m.nnz}
 checks={k:bool(v) for k,v in checks.items()}
 hashes={'native_values':array_hash(v),'source_values':array_hash(m.data),'native_indices':array_hash(ix),'source_indices':array_hash(m.indices),
  'native_pointers':array_hash(ptr),'source_pointers':array_hash(m.indptr)}
 return {'checks':checks,'all_passed':all(checks.values()),'hashes':hashes,'native_rows':lp.num_row_,'native_columns':lp.num_col_,
  'native_nonzeros':h.getNumNz(),'integers':int(np.sum(ints)),'is_scaled_public_lp':bool(lp.is_scaled_)}
def scaling_audit(d,m,ints,small):
 a=m.tocsr();scales=np.ones(m.shape[0]);v=a.data.copy();deletions=0
 for i in range(a.shape[0]):
  s,e=a.indptr[i:i+2];continuous=ints[a.indices[s:e]]==0
  if s==e or not np.any(continuous):continue
  maximum=np.max(abs(a.data[s:e][continuous]));p=-np.log2(maximum)
  power=np.floor(p+.5) if p>=0 else np.ceil(p-.5);scale=np.exp2(power)
  if scale==1:continue
  scales[i]=scale;v[s:e]*=scale;deletions+=int(np.sum(abs(v[s:e])<=small))
 if deletions:raise ValueError('Source-equivalent MIP row scaling would delete nonzero entries')
 scaled=sparse.csr_matrix((v,a.indices.copy(),a.indptr.copy()),shape=a.shape).tocsc();cs=np.ones(a.shape[1])
 for i in range(a.shape[1]):
  if ints[i]:continue
  s,e=scaled.indptr[i:i+2]
  if s==e:continue
  p=-np.log2(max(abs(scaled.data[s:e])));k=np.floor(p+.5) if p>=0 else np.ceil(p-.5);cs[i]=np.exp2(k);scaled.data[s:e]*=cs[i]
 restored=scaled.multiply((1/scales)[:,None]).multiply((1/cs)[None,:]).tocsc()
 cc=d['c'].ravel();lb=d['lb'].ravel();ub=d['ub'].ravel();rhs=np.r_[d['b'].ravel(),d['beq'].ravel()]
 inverse={'matrix':bool((restored!=m).nnz==0),'objective':bool(np.array_equal((cc*cs)/cs,cc)),
  'lower_bounds':bool(np.array_equal((lb/cs)*cs,lb)),'upper_bounds':bool(np.array_equal((ub/cs)*cs,ub)),
  'row_rhs':bool(np.array_equal((rhs*scales)/scales,rhs)),'integer_scalings_one':bool(np.all(cs[ints!=0]==1))}
 if not all(inverse.values()):raise ValueError('Power-of-two scaling inverse failed')
 return {'predicted_deletions':deletions,'predicted_nonzeros':m.nnz,'minimum_absolute_after_row_scaling':float(min(abs(v))),
  'row_scalings':int(np.sum(scales!=1)),'continuous_column_scalings':int(np.sum(cs!=1)),'inverse_checks':inverse,
  'scope':'offline reconstruction of official1.15.1 scaleMIP; not runtime internal MIP snapshot'},scales,cs
def prepare(source):
 d,m,ints=read_source(source);h=highspy.Highs();setters={};effective={}
 for key,value in OPTIONS.items():
  status=h.setOptionValue(key,value);s,v=h.getOptionValue(key)
  setters[key]=str(status);effective[key]={'status':str(s),'value':v}
  if status!=highspy.HighsStatus.kOk or s!=highspy.HighsStatus.kOk or v!=value:raise ValueError('Option setter/readback mismatch: '+key)
 lp=highspy.HighsLp();lp.num_col_=m.shape[1];lp.num_row_=m.shape[0];lp.col_cost_=d['c'].ravel();lp.col_lower_=d['lb'].ravel();lp.col_upper_=d['ub'].ravel()
 lp.row_lower_=np.r_[np.full(d['A'].shape[0],-np.inf),d['beq'].ravel()];lp.row_upper_=np.r_[d['b'].ravel(),d['beq'].ravel()]
 lp.integrality_=[highspy.HighsVarType.kInteger if i else highspy.HighsVarType.kContinuous for i in ints]
 lp.a_matrix_.format_=highspy.MatrixFormat.kColwise;lp.a_matrix_.num_col_=m.shape[1];lp.a_matrix_.num_row_=m.shape[0]
 lp.a_matrix_.start_=m.indptr;lp.a_matrix_.index_=m.indices;lp.a_matrix_.value_=m.data
 imported=h.passModel(lp)
 if imported!=highspy.HighsStatus.kOk:raise ValueError('Native passModel did not return kOk: '+str(imported))
 readback=compare(h,d,m,ints)
 if not readback['all_passed']:raise ValueError('Native model readback mismatch: '+str(readback))
 no_initial_point=not h.getSolution().value_valid and not h.getBasis().valid
 if not no_initial_point:raise ValueError('Unexpected preexisting solution/basis')
 audit,rs,cs=scaling_audit(d,m,ints,effective['small_matrix_value']['value'])
 defaults={}
 for key in ['mip_abs_gap','mip_feasibility_tolerance','primal_feasibility_tolerance','dual_feasibility_tolerance','random_seed','simplex_scale_strategy']:
  s,v=h.getOptionValue(key);defaults[key]={'status':str(s),'value':v}
 report={'version':h.version(),'git_hash':h.githash(),'setters':setters,'effective_options':effective,'unchanged_default_options':defaults,
  'import_status':str(imported),'readback':readback,'no_initial_point_or_basis':no_initial_point,'scaling_audit':audit,'gate_passed':True}
 return h,d,m,ints,report,rs,cs
