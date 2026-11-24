"""Exact affine energy enumeration; original continuous safety screens and replay."""
import numpy as np
EPS=1e-7
def decode(c):return [(int(c)//54**(3-j))%54 for j in range(4)]

def enumerate_energy(tables,initial,allowed,check):
    codes=np.array([0],dtype=np.int32);T=np.array(initial)[None,:];E=np.zeros(1)
    for j,table in enumerate(tables):
        cc=[];tt=[];ee=[]
        for i in allowed:
            check();k=table[i]
            if k is None:continue
            e,end=k.affine(T);cc.append(codes*54+i);tt.append(end);ee.append(E+e)
        if not cc:return np.empty(0,dtype=np.int32),np.empty(0)
        codes,T,E=map(np.concatenate,[cc,tt,ee])
    return codes,E

def exact(tables,initial,allowed,check,emit):
    codes,E=enumerate_energy(tables,initial,allowed,check)
    rank=np.lexsort((codes,E));tested=0;unresolved=[]
    for begin in range(0,len(rank),128):
        check();ix=rank[begin:begin+128];choices=np.array([decode(codes[q]) for q in ix])
        T=np.repeat(np.array(initial)[None,:],len(ix),axis=0);status=np.ones(len(ix),dtype=np.int8)
        for j,table in enumerate(tables):
            for i in np.unique(choices[:,j]):
                check();mask=np.flatnonzero((choices[:,j]==i)&(status==1))
                if not len(mask):continue
                k=table[int(i)];s=k.batch_safe(T[mask]);_,T[mask]=k.affine(T[mask]);status[mask]=s
        for q,st in zip(ix,status):
            tested+=1
            if st<0:unresolved.append(float(E[q]))
            if st==1:
                proof=dict(legal_sequences=len(codes),tested_by_energy_order=tested,unresolved_before=len(unresolved),
                    safe_energy_J=float(E[q]),valid_lower_bound_J=min([float(E[q])]+unresolved),
                    finite_domain_optimal=not unresolved or min(unresolved)>=float(E[q])-EPS,
                    deployment_choices=len(allowed)//27,frequency_choices=27,energy_tolerance_J=EPS)
                emit('exact_certificate',**proof)
                return decode(codes[q]),proof
        if begin%4096==0:emit('exact_progress',tested=tested,total=len(codes))
    proof=dict(legal_sequences=len(codes),tested_by_energy_order=tested,unresolved_before=len(unresolved),
               finite_domain_optimal=not unresolved,proven_no_safe=not unresolved)
    emit('exact_certificate',**proof);return None,proof

def greedy_current(table,entry,use_heat):
    """Only current scene options and entry temperature; no later tables."""
    records=[]
    for i,k in enumerate(table):
        if k is None:continue
        e,end=k.affine(np.array(entry))
        state=int(k.batch_safe(np.array(entry)[None,:])[0]) if use_heat else None
        records.append(dict(index=i,path='D038' if i<27 else 'D040',opp=k.opp,energy_J=float(e),status=state,
                            exit_C=end.tolist()))
    valid=[r for r in records if not use_heat or r['status']==1]
    if not valid:return None,records
    minimum=min(r['energy_J'] for r in valid)
    winner=min((r for r in valid if r['energy_J']<=minimum+1e-9),key=lambda r:r['index'])
    return winner['index'],records
