"""Direct CPLEX matrix loader/readback. Contains no algorithm invocation."""
import ctypes,hashlib,os
from pathlib import Path
import numpy as np
from transport_contract import MatrixPacket,ContractError

def seal_algorithms(api):
    attempts=[];blocked=[]
    def deny(name):
        def f(*args,**kwargs):
            attempts.append(name)
            raise RuntimeError('D282 forbids algorithm entry: '+name)
        return f
    for name in ('solve','populate_solution_pool'):
        setattr(api.Cplex,name,deny('Cplex.'+name));blocked.append('Cplex.'+name)
    for module in (api._internal._procedural,api._internal._pycplex):
        for name in dir(module):
            low=name.lower()
            if callable(getattr(module,name)) and any(word in low for word in (
                'mipopt','lpopt','qpopt','baropt','hybbaropt','hybnetopt','primopt','dualopt','siftopt',
                'multiobjopt','populate','feasopt','feasoptext','presolve','refineconflict','refinemipstart','tuneparam')):
                setattr(module,name,deny(module.__name__+'.'+name));blocked.append(module.__name__+'.'+name)
    return attempts,blocked,deny

def seal_instance(m,deny):
    m.feasopt=deny('feasopt')
    m.presolve.presolve=deny('presolve.presolve')
    m.conflict.refine=deny('conflict.refine')
    m.conflict.refine_MIP_start=deny('conflict.refine_MIP_start')
    m.parameters.tune_problem=deny('parameters.tune_problem')
    m.parameters.tune_problem_set=deny('parameters.tune_problem_set')

def loaded_dll():
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];k.GetModuleHandleW.restype=ctypes.c_void_p
    k.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint32];k.GetModuleFileNameW.restype=ctypes.c_uint32
    h=k.GetModuleHandleW('cplex2220.dll')
    if not h:raise ctypes.WinError(ctypes.get_last_error())
    b=ctypes.create_unicode_buffer(32768);n=k.GetModuleFileNameW(h,b,len(b))
    if n==0 or n>=len(b):raise RuntimeError('Incomplete DLL path')
    return b.value

def bounds_to_native(a,infinity):
    if np.any(np.isfinite(a)&(np.abs(a)>=infinity)):
        raise ContractError('Finite bound collides with native infinity; no lossy substitute')
    return np.where(np.isposinf(a),infinity,np.where(np.isneginf(a),-infinity,a)).tolist()

def bounds_from_native(a,expected,infinity):
    a=np.array(a,dtype='<f8')
    if len(a)!=len(expected):raise ContractError('Bound length mismatch')
    for sign in (-1,1):
        mask=np.isinf(expected)&(np.signbit(expected)==(sign<0))
        if np.any(a[mask]!=sign*infinity):raise ContractError('Infinity sentinel mismatch')
        a[mask]=sign*np.inf
    return a

def column_names(n):return ['v_'+str(j).zfill(8) for j in range(n)]
def row_names(prefix,start,stop):return [prefix+'_'+str(j).zfill(8) for j in range(start,stop)]

def load(m,api,p,check,progress,block_rows=2048):
    check()
    m.objective.set_sense(m.objective.sense.minimize);m.objective.set_offset(0.)
    types=['C']*p.n
    for j in p.intcon:types[int(j)]='I'
    m.variables.add(obj=p.c.tolist(),lb=bounds_to_native(p.lb,api.infinity),
                    ub=bounds_to_native(p.ub,api.infinity),types=''.join(types),names=column_names(p.n))
    for key,prefix,sense,rhs in [('A','le','L',p.b),('Aeq','eq','E',p.beq)]:
        shape,row,col,data=getattr(p,key)
        starts=np.searchsorted(row,np.arange(shape[0]+1))
        for begin in range(0,shape[0],block_rows):
            check();end=min(begin+block_rows,shape[0])
            rows=[api.SparsePair(ind=col[starts[i]:starts[i+1]].tolist(),val=data[starts[i]:starts[i+1]].tolist()) for i in range(begin,end)]
            m.linear_constraints.add(lin_expr=rows,senses=sense*(end-begin),rhs=rhs[begin:end].tolist(),names=row_names(prefix,begin,end))
            progress('load_rows',matrix=key,completed=end,total=shape[0])
    check()
    m.MIP_starts.add(api.SparsePair(ind=list(range(p.n)),val=p.x0.tolist()),m.MIP_starts.effort_level.check_feasibility,'common_complete_x0')
    progress('complete_start_stored',length=p.n)

def readback(m,api,p,check,progress,block_rows=2048):
    check();nr=p.A[0][0];ne=p.Aeq[0][0]
    invariants=dict(num_columns=m.variables.get_num()==p.n,num_rows=m.linear_constraints.get_num()==nr+ne,
        column_order=m.variables.get_names()==column_names(p.n),
        row_order=m.linear_constraints.get_names()==row_names('le',0,nr)+row_names('eq',0,ne),
        direction=m.objective.get_sense()==m.objective.sense.minimize,
        objective_constant=float(m.objective.get_offset()).hex()=='0x0.0p+0',
        row_senses=m.linear_constraints.get_senses()==['L']*nr+['E']*ne,
        nnz_count=m.linear_constraints.get_num_nonzeros()==len(p.A[3])+len(p.Aeq[3]),
        no_quadratic_constraints=m.quadratic_constraints.get_num()==0,
        no_indicator_constraints=m.indicator_constraints.get_num()==0,no_SOS=m.SOS.get_num()==0,
        start_count=m.MIP_starts.get_num()==1)
    if not invariants['num_columns'] or not invariants['num_rows']:
        raise ContractError('Native shape drift: '+repr(invariants))
    actual_types=m.variables.get_types();wanted=['C']*p.n
    for j in p.intcon:wanted[int(j)]='I'
    invariants['exact_integer_types']=actual_types==wanted
    start,effort=m.MIP_starts.get_starts(0)
    invariants['start_column_order']=list(start.ind)==list(range(p.n))
    invariants['start_effort_checkfeas']=effort==m.MIP_starts.effort_level.check_feasibility
    invariants['start_name']=m.MIP_starts.get_names()==['common_complete_x0']
    matrices={}
    for name,count,offset in [('A',nr,0),('Aeq',ne,nr)]:
        rows=[];cols=[];values=[]
        for begin in range(0,count,block_rows):
            check();end=min(begin+block_rows,count)
            pairs=m.linear_constraints.get_rows(offset+begin,offset+end-1)
            if len(pairs)!=end-begin:raise ContractError('Incomplete native row packet')
            for i,pair in enumerate(pairs,begin):
                if len(pair.ind)!=len(pair.val):raise ContractError('Row coordinate/value mismatch')
                rows.extend([i]*len(pair.ind));cols.extend(pair.ind);values.extend(pair.val)
            progress('read_rows',matrix=name,completed=end,total=count)
        matrices[name]=((count,p.n),np.array(rows,dtype='<i8'),np.array(cols,dtype='<i8'),np.array(values,dtype='<f8'))
    check();rhs=np.asarray(m.linear_constraints.get_rhs(),dtype='<f8')
    q=MatrixPacket(p.n,matrices['A'],matrices['Aeq'],np.asarray(m.objective.get_linear(),dtype='<f8'),
        rhs[:nr],rhs[nr:],bounds_from_native(m.variables.get_lower_bounds(),p.lb,api.infinity),
        bounds_from_native(m.variables.get_upper_bounds(),p.ub,api.infinity),
        np.asarray([i for i,t in enumerate(actual_types) if t in ('I','B')],dtype='<i8'),
        np.asarray(start.val,dtype='<f8'),tuple(range(p.n)))
    return q,invariants

def difference(a,b,name):
    a=np.asarray(a);b=np.asarray(b)
    if a.shape!=b.shape:return dict(field=name,shape_equal=False,expected=list(a.shape),actual=list(b.shape),mismatch_count=None)
    floating=a.dtype.kind=='f'
    neq=a.view('<u8')!=b.view('<u8') if floating else a!=b
    idx=np.flatnonzero(neq)
    return dict(field=name,shape_equal=True,compared=int(a.size),mismatch_count=int(len(idx)),
        examples=[dict(index=int(i),expected=float(a[i]).hex() if floating else int(a[i]),
                       actual=float(b[i]).hex() if floating else int(b[i])) for i in idx[:12]])

def compare(p,q,invariants):
    diffs=[difference(getattr(p,k),getattr(q,k),k) for k in ('c','b','beq','lb','ub','intcon','x0')]
    for name in ('A','Aeq'):
        for i,label in [(0,'shape'),(1,'row'),(2,'col'),(3,'data')]:
            diffs.append(difference(np.asarray(getattr(p,name)[i]),np.asarray(getattr(q,name)[i]),name+'.'+label))
    return dict(passed=all(invariants.values()) and all(x['mismatch_count']==0 for x in diffs),
                invariants=invariants,fields=diffs,expected_hashes=p.hashes(),native_hashes=q.hashes())

def archive_packet(path,p):
    data={k:getattr(p,k) for k in ('c','b','beq','lb','ub','intcon','x0')}
    for name in ('A','Aeq'):
        for i,k in enumerate(('shape','row','col','data')):data[name+'_'+k]=getattr(p,name)[i]
    # Binary64 arrays remain binary; npz is only a lossless archive container.
    with Path(path).open('xb') as f:np.savez_compressed(f,**data)
