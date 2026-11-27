"""Device DP inputs, trace integration, and independent exhaustive correctness fixtures."""
import ctypes as ct
import itertools
import time
from pathlib import Path
import numpy as np

DP = ct.CDLL(str(Path(__file__).with_name("dp.so"))).frequency_dp
I,D,L = (np.ctypeslib.ndpointer(dtype=t,flags="C_CONTIGUOUS") for t in (np.int32,np.float64,np.int64))
DP.argtypes = [ct.c_int]*4+[ct.c_double,I,I,I,I,D,D,D,D,D,ct.c_int,I,L,D,ct.c_int]
DP.restype = ct.c_double
EX=ct.CDLL(str(Path(__file__).with_name("dp.so"))).exact_dp
U=np.ctypeslib.ndpointer(dtype=np.uint64,flags="C_CONTIGUOUS")
EX.argtypes=[ct.c_int]*4+[U,I,I,I,I,ct.c_int,I,L,D,ct.c_int]
EX.restype=ct.c_double

def integer_device(data,weights,compact=True,debug=False):
    ready,limit,epochs,dt,*_=data
    n,m=dt.shape;h=len(data[8])-1;tail=data[-1]
    assert max(weights[:1+m],default=0)*(h+2*n+2)+max(weights[1+m:],default=0)*n<2**126 and min(weights)>=0
    words=np.array([(v>>64,v%(1<<64)) for v in weights],dtype=np.uint64)
    path=np.zeros(n,np.int32);counts=np.zeros((n,3),np.int64)
    tab=np.full((n,h+1,m) if debug else (1,),np.inf)
    opt=EX(n,m,h,tail,words,ready,limit,epochs,dt,int(compact),path,counts,tab,h+1 if debug else 0)
    return opt,path,counts,tab

def device(data, compact=True, debug=False):
    a,latest,epochs,dt,act,rate,beta,ib,T,sw,tail=data
    n,m=dt.shape
    path=np.zeros(n,np.int32)
    counts=np.zeros((n,3),np.int64)
    h=len(T)-1
    table=np.full((n,h+1,m) if debug else (1,),np.inf)
    cost=DP(n,m,h,tail,sw,a,latest,epochs,dt,act,rate,beta,ib,T,int(compact),path,counts,table,h+1 if debug else 0)
    return cost,path,counts,table

def data_for(eng, ids, u, reserve, trace):
    h=eng.p.horizon
    m=10 if u==2 else 3
    i32=lambda x:np.ascontiguousarray(x,dtype=np.int32)
    f64=lambda x:np.ascontiguousarray(x,dtype=np.float64)
    integral=np.zeros(h+1)
    if trace is not None:
        t=np.r_[trace[:,0],trace[-1,1]]
        knots=np.r_[trace[:,14+u],trace[-1,18+u]]-35
        theta=np.interp(np.arange(h+1),t,knots)
        integral[1:]=np.cumsum((theta[1:]+theta[:-1])*.5)
    ids=list(ids)
    kinds=[eng.types[i] for i in ids]
    delta=eng.scale/10000
    idle0=eng.p.idle[u,0][1]
    return (i32([eng.a[i] for i in ids]),i32([eng.D[i]-eng.q[i]-reserve for i in ids]),
            i32([eng.p.req[i]["release_tick"]//10000*10000 for i in ids]),
            i32([[eng.length[t,u,k] for k in range(m)] for t in kinds]).reshape(-1,m),
            f64([[eng.inc[t,u,k] for k in range(m)] for t in kinds]).reshape(-1,m),
            f64([eng.rate[u,k] for k in range(m)]),
            f64([[(eng.p.profile[t+".main",u,k][2]-idle0)*delta for k in range(m)] for t in kinds]).reshape(-1,m),
            f64([(eng.p.idle[u,k][1]-idle0)*delta for k in range(m)]),
            integral,float(eng.sw),eng.p.req[-1]["release_tick"]//10000*10000)

def solve(eng,cfg,reserve,trace):
    start=time.perf_counter()
    answer=list(cfg);ledger=[];total=0.
    for u in (2,3):
        ids=[i for i,(v,_) in enumerate(cfg) if v==u]
        args=data_for(eng,ids,u,reserve,trace)
        if trace is None:
            m=args[3].shape[1]
            weights=[eng.sw,*[eng.rate[u,j] for j in range(m)],*[eng.inc[eng.types[i],u,j] for i in ids for j in range(m)]]
            cost,k,stats,_=integer_device(args,weights)
        else:
            cost,k,stats,_=device(args)
        ledger.append(dict(device=u,count=len(ids),states=stats[:,2].tolist(),predecessors=int(stats[:,0].sum()),
                           max_states=int(stats[:,2].max(initial=0)),finite=bool(np.isfinite(cost)),
                           objective_increment=cost/eng.scale if np.isfinite(cost) else None))
        if not np.isfinite(cost):return None,ledger,time.perf_counter()-start,None
        total+=cost
        for i,b in zip(ids,k):answer[i]=(u,int(b))
    return tuple(answer),ledger,time.perf_counter()-start,(total+eng.common_int)/eng.scale

def brute(data):
    a,latest,epochs,dt,act,rate,beta,ib,T,sw,tail=data
    n,m=dt.shape;h=len(T)-1;table=np.full((n,h+1,m),np.inf);best=np.inf
    def gap(t,s,old,new,decision):
        hold=rate[old]*(s-t)+sw*(old!=new)
        down=rate[old]*5+sw*(1+int(new!=0))
        early=old>0 and t>=decision and s-t>=5*(1+int(new!=0)) and down<hold
        return (down if early else hold)+ib[old]*(T[t+5 if early else s]-T[t])
    for row in itertools.product(range(m),repeat=n):
        v=0.;t=old=0
        for i,k in enumerate(row):
            s=max(a[i],t+5*(old!=k));z=s+dt[i,k]
            if z>min(h,latest[i]):break
            v+=gap(t,s,old,k,epochs[i])
            v+=act[i,k]+beta[i,k]*(T[z]-T[s])
            table[i,z,k]=min(table[i,z,k],v)
            t,old=z,k
        else:
            if t+5*(old!=0)<=h:best=min(best,v+gap(t,h,old,0,tail))
    return best,table

def gate():
    tests=[]
    for seed in range(12):
        rnd=np.random.default_rng(seed);n=4;m=3 if seed%2 else 10;h=80
        a=np.array([1,13,36,51],np.int32);limit=np.array([30,39,59,75],np.int32)-(seed%3)*4
        epochs=np.array([0,0,25,50],np.int32)
        dt=rnd.integers(4,22,size=(n,m),dtype=np.int32)
        rate=np.arange(m,dtype=float)*2
        T=np.arange(h+1,dtype=float)**2/160 if seed%3 else np.zeros(h+1)
        data=(a,limit,epochs,dt,rnd.integers(5,80,(n,m)).astype(float),rate,rnd.random((n,m)),rate*.02,T,15.,50)
        opt,reference=brute(data)
        for compact in (False,True):
            result,path,stats,tab=device(data,compact,True)
            assert np.array_equal(np.isfinite(tab),np.isfinite(reference))
            assert np.allclose(tab,reference,rtol=0,atol=1e-10) and np.isclose(opt,result)
        if not np.any(T):
            vals=[15,*map(int,rate),*map(int,data[4].ravel())]
            for compact in (False,True):
                result,path,counts,tab=integer_device(data,vals,compact,True)
                assert np.array_equal(tab,reference) and result==opt
        tests.append(dict(seed=seed,configs=m**n,layers=n,reachable=int(np.isfinite(reference).sum())))
    return tests
