"""Exact complement-gate extension of explicitly identified inequality rows.

For an identified row a*x + alpha*g <= b, introduce h = 1-g and
replace only that occurrence by a*x - alpha*h <= b-alpha. Every original
column stays in place. Integer and continuous projected feasible domains are
identical. This module never discovers row semantics, solves a model, changes
physical precision, widens an interval, or rounds an unrepresentable constant.
"""
from fractions import Fraction
import hashlib
from collections.abc import Mapping
import numpy as np
from scipy import sparse

KEYS = ('c','A','b','Aeq','beq','lb','ub','intcon','x0')
PROOF_RULE = 'explicit_conditional_rows_exact_complement_gate_v1'

class ExactRepresentationError(ValueError):
    """The requested complete conversion cannot be encoded without rounding."""

def _require(condition, message):
    if not condition:
        raise ExactRepresentationError(message)

def _q(value):
    value=float(value)
    _require(np.isfinite(value), 'Nonfinite number in exact transformation')
    return Fraction.from_float(value)

def _binary64(value, label):
    value=Fraction(value)
    try:result=float(value)
    except OverflowError as error:raise ExactRepresentationError(label+': binary64 overflow') from error
    _require(np.isfinite(result) and Fraction.from_float(result)==value,
             label+': exact rational is not binary64 representable: '+str(value))
    return result

def array_digest(payload):
    result={}
    for key in KEYS:
        value=payload[key];h=hashlib.sha256()
        if sparse.issparse(value):
            h.update((str(value.shape)+str(value.dtype)+value.format).encode())
            for part in (value.data,value.indices,value.indptr):
                h.update((str(part.shape)+str(part.dtype)).encode());h.update(part.tobytes())
        else:
            value=np.asarray(value);h.update((str(value.shape)+str(value.dtype)).encode());h.update(value.tobytes())
        result[key]=h.hexdigest()
    return result

def _same(a,b):
    a=np.asarray(a);b=np.asarray(b)
    return a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes()

def _validate(payload):
    _require(set(payload)==set(KEYS), 'Payload fields must exactly match KEYS')
    n=len(payload['c'])
    _require(n>0, 'Empty variable set')
    for key in ('c','b','beq','lb','ub','x0'):
        v=np.asarray(payload[key])
        _require(v.ndim==1 and v.dtype==np.float64 and np.isfinite(v).all(), 'Finite 1D binary64 required: '+key)
    for key in ('lb','ub','x0'):_require(len(payload[key])==n,'Variable dimension mismatch: '+key)
    for key,rhs in [('A','b'),('Aeq','beq')]:
        a=payload[key]
        _require(sparse.issparse(a) and a.format in ('csr','csc') and a.has_canonical_format,
                 'Canonical CSR/CSC required: '+key)
        _require(a.dtype==np.float64 and np.isfinite(a.data).all() and a.shape==(len(payload[rhs]),n),
                 'Invalid matrix: '+key)
    ix=np.asarray(payload['intcon'])
    _require(ix.ndim==1 and np.issubdtype(ix.dtype,np.integer), 'Zero-based integer intcon required')
    _require(len(set(map(int,ix)))==len(ix) and all(0<=int(i)<n for i in ix),'Invalid intcon')

def forward_rational(vector, certificate):
    """Exact map over rational coordinates, including arbitrary fractional gates."""
    n=certificate['original_variables'];gates=certificate['gate_columns']
    _require(len(vector)==n,'Invalid rational forward vector')
    x=[v if isinstance(v,Fraction) else _q(v) for v in vector]
    return x+[1-x[g] for g in gates]+[Fraction(v['value_exact']) for v in certificate.get('fixed_constants',[])]

def inverse_rational(vector, certificate):
    _require(len(vector)==certificate['derived_variables'],'Invalid rational inverse vector')
    return list(vector[:certificate['original_variables']])

def forward_vector(vector, certificate):
    """Exact binary64 extension when representable; otherwise reject, never repair."""
    n=certificate['original_variables'];gates=certificate['gate_columns']
    x=np.asarray(vector,dtype=np.float64)
    _require(x.ndim==1 and len(x)==n and np.isfinite(x).all(),'Invalid forward vector')
    tail=[_binary64(1-_q(x[g]),'x0 complement column '+str(g)) for g in gates]
    tail += [_binary64(Fraction(v['value_exact']),'Fixed constant') for v in certificate.get('fixed_constants',[])]
    return np.concatenate((x,np.array(tail,dtype=np.float64)))

def inverse_vector(vector, certificate):
    """Coordinate projection only; it does not assert vector feasibility."""
    z=np.asarray(vector,dtype=np.float64)
    _require(z.ndim==1 and len(z)==certificate['derived_variables'] and np.isfinite(z).all(),'Invalid inverse vector')
    return z[:certificate['original_variables']].copy()

def transform(payload, *, row_gates, gate_columns, mode='strict'):
    """Transform every requested row, or reject the entire request.

    row_gates maps zero-based A row indices to explicit original gate columns.
    gate_columns must name exactly the same gates. Only these A rows change;
    other uses of g in A or Aeq are preserved. Bounds 0<=g<=1 are mandatory.
    The input payload is never mutated, including on failure.
    """
    _require(mode in ('strict','split_constant_v1'),'Unknown representation mode')
    _validate(payload);before=array_digest(payload);n=len(payload['c']);m=payload['A'].shape[0]
    _require(isinstance(row_gates,Mapping) and len(row_gates)>0,'Nonempty explicit row_gates mapping required')
    _require(all(isinstance(i,(int,np.integer)) and not isinstance(i,bool) and isinstance(g,(int,np.integer)) and not isinstance(g,bool) for i,g in row_gates.items()),'Row and gate indices must be integers')
    pairs=sorted((int(i),int(g)) for i,g in row_gates.items())
    supplied=list(gate_columns)
    _require(all(isinstance(g,(int,np.integer)) and not isinstance(g,bool) for g in supplied),'Gate indices must be integers')
    gates=sorted(map(int,supplied))
    _require(len(gates)==len(set(gates)) and gates==sorted({g for i,g in pairs}),'Explicit gate list differs from row mapping')
    _require(all(0<=i<m and 0<=g<n for i,g in pairs),'Row or gate out of range')
    _require(all(payload['lb'][g]==0.0 and payload['ub'][g]==1.0 for g in gates),'Every gate must have original bounds [0,1]')
    target={g:n+k for k,g in enumerate(gates)};a=payload['A'].tocsr()
    new_rhs=payload['b'].copy();details=[];constants=[]
    # Preflight every constant before constructing output. No partial fallback.
    for i,g in pairs:
        alpha=float(a[i,g]);_require(alpha!=0,'Selected row does not contain gate: '+str(i))
        rhs=_q(payload['b'][i])-_q(alpha)
        fixed_column=None;lo=Fraction(0)
        if mode=='strict':hi=_binary64(rhs,'row '+str(i)+' RHS')
        else:
            hi=float(rhs);_require(np.isfinite(hi),'Split constant high part overflow')
            lo=rhs-_q(hi);low=_binary64(lo,'row '+str(i)+' exact low part')
            _require(_q(hi)+_q(low)==rhs,'Split constant identity failure')
            if lo:
                fixed_column=n+len(gates)+len(constants)
                constants.append(dict(column=fixed_column,original_row=i,value_exact=str(lo),value_binary64_hex=low.hex()))
        new_rhs[i]=hi
        details.append(dict(original_row=i,derived_row=i,gate_column=g,complement_column=target[g],
            original_gate_coefficient_exact=str(_q(alpha)),original_rhs_exact=str(_q(payload['b'][i])),
            shifted_rhs_exact=str(rhs),derived_rhs_exact=str(_q(hi)),low_part_exact=str(lo),fixed_constant_column=fixed_column))
    new_n=n+len(gates)+len(constants)
    cert=dict(proof_rule=PROOF_RULE,mode=mode,original_variables=n,derived_variables=new_n,
        original_inequalities=m,original_equalities=payload['Aeq'].shape[0],gate_columns=gates,
        fixed_constants=constants,
        row_mappings=details,gate_complements=[dict(gate_column=g,complement_column=target[g],
            equality_row=payload['Aeq'].shape[0]+k) for k,g in enumerate(gates)],
        original_columns_retained_in_order=True,integer_projection_preserved=True,continuous_projection_preserved=True,
        mathematical_identity='h=1-g; when needed t=lo and rhs=hi with hi+lo=b-alpha exactly, row is a*x-alpha*h-t<=hi. Substitute h and fixed t to recover the original row. Appended objective coefficients are zero.',
        precision_scope='All saved binary64 values interpreted as exact rationals. Strict mode rejects inexact shifted RHS. Split mode stores exact hi+lo via a fixed continuous column; no net rounding or interval widening. No x0 rounding.',
        initial_point_scope='Same original coordinates; exact complement extension only; no new SAFE claim',
        physical_parameters_changed=False,objective_changed=False,solver_calls=0,model_builds=0,thermal_evaluations=0)
    z0=forward_vector(payload['x0'],cert)
    coo=payload['A'].tocoo(copy=True);row_map=dict(pairs)
    col=coo.col.copy();data=coo.data.copy()
    for k,(i,j) in enumerate(zip(coo.row,coo.col)):
        gate=row_map.get(int(i))
        if gate is not None and int(j)==gate:col[k]=target[gate];data[k]=-data[k]
    rows=coo.row.copy()
    if constants:
        rows=np.r_[rows,[v['original_row'] for v in constants]]
        col=np.r_[col,[v['column'] for v in constants]]
        data=np.r_[data,-np.ones(len(constants))]
    changed=sparse.coo_matrix((data,(rows,col)),shape=(m,new_n)).asformat(payload['A'].format)
    old_eq=sparse.hstack((payload['Aeq'],sparse.csc_matrix((payload['Aeq'].shape[0],new_n-n))),format=payload['Aeq'].format)
    rr=np.repeat(np.arange(len(gates)),2);cc=np.array([c for g in gates for c in (g,target[g])])
    added=sparse.coo_matrix((np.ones(2*len(gates)),(rr,cc)),shape=(len(gates),new_n)).asformat(payload['Aeq'].format)
    lows=np.array([float(Fraction(v['value_exact'])) for v in constants],dtype=np.float64)
    derived={key:value.copy() for key,value in payload.items()}
    derived.update(A=changed,b=new_rhs,Aeq=sparse.vstack((old_eq,added),format=payload['Aeq'].format),
        beq=np.r_[payload['beq'],np.ones(len(gates))],c=np.r_[payload['c'],np.zeros(new_n-n)],
        lb=np.r_[payload['lb'],np.zeros(len(gates)),lows],ub=np.r_[payload['ub'],np.ones(len(gates)),lows],x0=z0)
    cert['source_array_sha256']=before;cert['derived_array_sha256']=array_digest(derived)
    cert['checks']=verify_equivalence(payload,derived,cert)
    _require(array_digest(payload)==before,'Input arrays mutated')
    return derived,cert

def verify_equivalence(original,derived,certificate):
    """Verify by exact inverse substitution, independently of sparse assembly."""
    _validate(original);_validate(derived);c=certificate;n=len(original['c']);gates=c['gate_columns'];k=len(gates);fixed=c.get('fixed_constants',[])
    new_n=n+k+len(fixed)
    _require(c['proof_rule']==PROOF_RULE,'Unknown proof rule')
    _require(c['source_array_sha256']==array_digest(original),'Original array identity mismatch')
    _require(c['derived_array_sha256']==array_digest(derived),'Derived array identity mismatch')
    _require(c['mode'] in ('strict','split_constant_v1'),'Unknown representation mode')
    _require(c['mode']!='strict' or not fixed,'Strict mode must not add split constants')
    _require(c['original_variables']==n and c['derived_variables']==new_n,'Variable map mismatch')
    _require(derived['A'].shape==(original['A'].shape[0],new_n) and derived['Aeq'].shape==(original['Aeq'].shape[0]+k,new_n),'Row coverage mismatch')
    for key in ['c','lb','ub','x0']:_require(_same(original[key],derived[key][:n]),'Original coordinate drift: '+key)
    _require(_same(original['intcon'],derived['intcon']),'Integer domain drift')
    _require(np.array_equal(derived['c'][n:],np.zeros(new_n-n)) and np.array_equal(derived['lb'][n:n+k],np.zeros(k)) and np.array_equal(derived['ub'][n:n+k],np.ones(k)),'Complement objective or bounds changed')
    fixed_values={}
    for offset,item in enumerate(fixed):
        col=n+k+offset;value=Fraction(item['value_exact'])
        _require(item['column']==col and value!=0 and _q(derived['lb'][col])==value and _q(derived['ub'][col])==value,'Fixed low-part bounds mismatch')
        fixed_values[col]=value
    _require(all(original['lb'][g]==0 and original['ub'][g]==1 for g in gates),'Invalid gate bounds')
    _require(_same(derived['x0'],forward_vector(original['x0'],c)),'Initial point mapping drift')
    complement={n+i:g for i,g in enumerate(gates)}
    expected={r['original_row']:r for r in c['row_mappings']}
    _require(len(expected)==len(c['row_mappings']),'Duplicate row mapping')
    for key,rhs in [('A','b'),('Aeq','beq')]:
        source=original[key].tocsr();target=derived[key].tocsr()
        for i in range(source.shape[0]):
            old={int(j):_q(v) for j,v in zip(source.getrow(i).indices,source.getrow(i).data) if v!=0}
            rec={};constant=Fraction(0);tail=[]
            row=target.getrow(i)
            for j,value in zip(row.indices,row.data):
                j=int(j);value=_q(value)
                if j<n:rec[j]=rec.get(j,Fraction(0))+value
                elif j in complement:
                    g=complement[j];rec[g]=rec.get(g,Fraction(0))-value;constant+=value;tail.append(j)
                else:
                    _require(j in fixed_values,'Unknown appended column')
                    constant+=value*fixed_values[j];tail.append(j)
            rec={j:v for j,v in rec.items() if v}
            _require(rec==old and _q(derived[rhs][i])-constant==_q(original[rhs][i]),'Inverse row mismatch: '+key+':'+str(i))
            if key=='A' and i in expected:
                info=expected[i];g=info['gate_column'];h=info['complement_column']
                fc=info['fixed_constant_column'];expected_tail=[h]+([] if fc is None else [fc])
                _require(info['derived_row']==i and h==n+gates.index(g) and tail==expected_tail,'Explicit transformed row map mismatch')
                _require(_q(derived['b'][i])==Fraction(info['derived_rhs_exact']),'Row certificate RHS mismatch')
                _require(Fraction(info['derived_rhs_exact'])+Fraction(info['low_part_exact'])==Fraction(info['shifted_rhs_exact']),'Split RHS certificate identity mismatch')
                _require(Fraction(info['shifted_rhs_exact'])==_q(original['b'][i])-_q(source[i,g]),'Original RHS shift mismatch')
                if fc is not None:
                    _require(fc in fixed_values and fixed_values[fc]==Fraction(info['low_part_exact']) and _q(target[i,fc])==-1,'Fixed low-part row mismatch')
                else:_require(Fraction(info['low_part_exact'])==0,'Missing nonzero low part')
            else:_require(not tail,'Unselected original row changed')
    target=derived['Aeq'].tocsr();old_eq=original['Aeq'].shape[0]
    for offset,g in enumerate(gates):
        row=target.getrow(old_eq+offset);actual={int(j):_q(v) for j,v in zip(row.indices,row.data) if v!=0}
        _require(actual=={g:Fraction(1),n+offset:Fraction(1)} and derived['beq'][old_eq+offset]==1.0,'Complement equality mismatch')
    return dict(all_original_rows_recovered_by_exact_inverse_substitution=True,all_appended_equalities_exact=True,
        objective_and_original_bounds_preserved=True,all_original_integer_columns_preserved=True,
        exact_initial_point_extension=True,integer_schedule_projection_preserved=True,
        continuous_relaxation_projection_preserved=True,no_rounded_constants=True,all_split_constants_exactly_fixed=True)
