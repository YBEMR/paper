"""Quota synthesis by integer slices of four-node transient capacity constraints."""
from base import np, WINDOW
from scipy.linalg import expm


def load_planes(c,j,s,g,n,a,b):
    d=c.eng.length
    ag,bg=d["A",2,g],d["B",2,g]
    an,bn=d["A",3,n],d["B",3,n]
    av=[max(0,s["f"][i]+5*(s["k"][i]!=z)-j*WINDOW) for i,z in enumerate((g,n))]
    return np.array([[av[0]+a*ag+b*bg,-ag,-bg],[av[1],an,bn]],float)/WINDOW


def cuts(planes,caps,xs,b):
    base=planes[:,0,None]+planes[:,1,None]*xs
    sy=planes[:,2,None]
    ratios=(caps[:,None]-base)/np.where(abs(sy)>1.e-12,sy,1.)
    low=np.maximum(0,np.max(np.where(sy< -1.e-12,ratios,-np.inf),axis=0))
    high=np.minimum(b,np.min(np.where(sy>1.e-12,ratios,np.inf),axis=0))
    constant_ok=~np.any((abs(sy)<=1.e-12)&(base>caps[:,None]+1.e-10),axis=0)
    return low,high,constant_ok


def gridpoints(xs,ys,b):
    return np.column_stack((np.broadcast_to(xs,ys.shape).ravel(),np.clip(ys,0,b).ravel())).astype(int)


def anchors(time,center,a,b):
    xs=np.arange(a+1)
    bal=(time[1,0]-time[0,0]+(time[1,1]-time[0,1])*xs)/(time[0,2]-time[1,2])
    ridge=gridpoints(xs,np.array([np.floor(bal),np.ceil(bal)]),b)
    z=np.max(time[:,0]+ridge@time[:,1:].T,axis=1)
    p=np.array(center)
    z0=max(time[:,0]+time[:,1:]@p)
    good=ridge[z<=z0+.05+1e-10]
    q=max(map(tuple,good),key=lambda v:(sum((v-p)**2),-v[0],-v[1]))
    low,high,ok=cuts(time,np.repeat(z0+.12,2),xs,b)
    ix=ok&(low<=high)
    side=gridpoints(xs[ix],np.array([np.ceil(low[ix]),np.floor(high[ix])]),b)
    options=[tuple(v) for v in side]+[(0,0),(0,b),(a,0),(a,b)]
    if tuple(q)==center:
        q=max(options,key=lambda v:sum((v-p)**2))
    delta=np.array(q)-p
    det=lambda v:abs(delta[0]*(v[1]-p[1])-delta[1]*(v[0]-p[0]))
    possible=[v for v in options if max(time[:,0]+time[:,1:]@v)<=z0+.12+1e-9 and det(v)>0]
    r=max(possible or options,key=lambda v:(det(v),-v[0],-v[1]))
    assert det(r)>0
    return [center,tuple(map(int,q)),tuple(map(int,r))],bal


def capacity(c,temp,points,observations,durations,forecast):
    # Each column is a calibration action. Fixed slopes give the same F/H to
    # all columns and preserve affinity in integer quota coordinates.
    temps=np.repeat((temp-35)[:,None],3,axis=1)
    samples=[]
    means=list(observations.transpose(1,0,2))
    steps=list(durations)
    if forecast:
        means.append(observations.mean(axis=1))
        steps.append(1.)
    for m,h in zip(means,steps):
        slope=m[0,4:]
        A=(np.diag(slope)-c.p.G)/c.p.cap[:,None]
        F=expm(h*A)
        H=np.linalg.solve(A,(F-np.eye(4))/c.p.cap[None,:])
        power=m[:,:4].T+(m[:,4:].T-slope[:,None])*temps[:,0,None]
        temps=F@temps+H@power
        samples.append(temps.T+35)
    design=np.column_stack((np.ones(3),points))
    return np.linalg.solve(design,np.concatenate(samples,axis=1)).T


def synthesize(time,planes,points,bal,cost,a,b,k):
    xs=np.arange(a+1)
    ts=np.repeat(1.3,2)
    lo,hi,ok=cuts(time,ts,xs,b)
    active=ok&(lo<=hi)
    if not np.any(active):
        return list(points)
    limits=np.r_[ts,np.repeat(80.,len(planes))]
    constraints=np.vstack((time,planes))
    low,high,_=cuts(constraints,limits,xs,b)
    # Search only integer neighbours of interval ends / balance lines.
    # Project the approximate thermal bounds back to the timing interval
    # even when the approximate thermal polygon has no integer interior.
    targets=np.clip(np.array([lo,hi,low,high,bal,(low+high)*.5]),lo,hi)
    targets=targets[:,active]
    y=np.concatenate([np.floor(targets),np.ceil(targets)],axis=0)
    pool=np.unique(gridpoints(xs[active],y,b),axis=0)
    if not len(pool):
        return list(points)
    energy=cost[0]+pool@cost[1:]
    timing=np.max(time[:,0]+pool@time[:,1:].T,axis=1)
    if len(planes):
        risk=np.max(planes[:,0]+pool@planes[:,1:].T,axis=1)
        exceed=np.maximum(0,risk-80)
    else:
        risk=timing
        exceed=np.maximum(0,timing-1.3)
    eligible=timing<=1.3+1e-9
    def order(*keys):
        # Primary key appears first in caller.
        return np.lexsort(tuple(reversed((*keys,pool[:,0],pool[:,1]))))
    picked=list(points)
    def take(indices):
        for idx in indices:
            v=tuple(map(int,pool[idx]))
            if eligible[idx] and v not in picked:
                picked.append(v)
                break
    take(order(exceed,energy))
    take(order(risk,energy))
    # Add separated boundary points by farthest-point sampling on the best
    # attainable thermal/time band; then use energy as deterministic tie break.
    while len(picked)<k:
        ds=np.min(np.sum(((pool[:,None,:]-np.array(picked)[None,:,:])/np.array([a,b]))**2,axis=2),axis=1)
        previous=len(picked)
        take(order(exceed,-ds,energy))
        if previous==len(picked):
            break
    return picked[:k]
