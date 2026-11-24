"""Original continuous peak bounds for candidate coverage, not a new scheduler."""
import numpy as np
from numba import njit

@njit(cache=True)
def bounds(delta,u,left,right,upper,witness,at):
    lo=np.full(len(delta),-np.inf);hi=lo.copy()
    for i in range(len(delta)):
        for b in range(len(upper)):
            for n in range(4):
                l=witness[b,n]-1e-6;h=upper[b,n]+1e-6
                for m in range(4):
                    c=u[n,m]*delta[i,m]
                    l+=c*at[b,n,m];h+=c*(left[b,m] if c>=0 else right[b,m])
                lo[i]=max(lo[i],l);hi[i]=max(hi[i],h)
    return lo,hi

def enumerate_bounds(tables,initial,check):
    codes=np.array([0],dtype=np.int32);T=np.array(initial)[None,:]
    L=np.array([max(initial)]);U=L.copy();E=np.zeros(1)
    for table in tables:
        cc=[];tt=[];ll=[];uu=[];ee=[]
        for i,k in enumerate(table):
            check()
            if k is None:continue
            d=T-k.initial
            l,u=bounds(np.ascontiguousarray(d@k.inverse.T),k.u,k.left_exp,k.right_exp,k.upper,k.witness_temp,k.witness_exp)
            cc.append(codes*27+i);tt.append(k.final0+d@k.F.T);ee.append(E+k.energy0+d@k.w)
            ll.append(np.maximum(L,l));uu.append(np.maximum(U,u))
        codes,T,L,U,E=map(np.concatenate,[cc,tt,ll,uu,ee])
    return codes,L,U,E
