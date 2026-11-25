"""Certified comparison trajectory plus a separate 40-degree reference relaxation."""
from bisect import bisect_right
import math
import numpy as np
import sympy as sp
from common import *
from compact import Layout,permissions,idle_exact
from profiles import CFG as PHY
from heat import integrate

def barrier(p):
    idle_exact(p);G=sp.Matrix(PHY["G"]);one=sp.ones(4,1)
    b=sp.Matrix([p.node_idle[u,0][0] for u in range(4)])
    l=sp.diag(*[p.node_idle[u,0][1] for u in range(4)])
    entry=(G-l).inv()*(G*one*p.ta+b-l*one*35)
    slopes=[v[j] for v in p.exact.values() for j in (1,3)]
    face=[min(v[j]+5*v[j+1] for (_,w,k),v in p.exact.items() if w==i for j in (0,2))
          -sum(PHY["G"][i])*(40-p.ta) for i in range(4)]
    inc=min(v[2]-v[0]+5*(v[3]-v[1]) for v in p.exact.values())
    cpu_slope=min(v[3]-v[1] for (_,u,k),v in p.exact.items() if u<2)
    ok=bool(min(entry)>=40 and min(slopes)>=0 and min(face)>=0 and inc>=0 and cpu_slope>=0 and
            all(G[i,j]<=0 for i in range(4) for j in range(4) if i!=j))
    return dict(valid=ok,entry=list(map(str,entry)),min_beta=str(min(slopes)),face_W=list(map(str,face)),min_increment40_W=str(inc),cpu_busy_minus_idle_slope=str(cpu_slope))
def relaxation(p,base,region,g,master):
    lay=Layout(p,base[0]);fixed,free=permissions(lay,region)
    cert=barrier(p)
    if not cert["valid"]:
        lb=float(Q(p.lower(base[0],region["ids"],g<3)["total"]))-1e-8
        return dict(lb=lb,residual=None,barrier=cert,method="original_lower")
    policy=fixed if g==0 else lay.normalize(base[1])
    ev=lay.events(policy);cuts=set(ev[:,0])|{p.horizon}
    if g==0:
        other=lay.events(fixed.union(free));cuts.update(other[:,0])
    else:
        for v in region["mask"].values():
            if v:cuts.update(v)
    pts=np.array(sorted(cuts));seg=ev[np.searchsorted(ev[:,0],pts[:-1],side="right")-1].copy()
    seg[:,0]=pts[:-1];seg[:,1]=pts[1:]
    ref40=seg[:,2:6]+5*seg[:,6:10];beta=seg[:,6:10].copy()
    ids=set(region["ids"])
    if g==0:
        alt=other[np.searchsorted(other[:,0],pts[:-1],side="right")-1]
        ref40=np.minimum(ref40,alt[:,2:6]+5*alt[:,6:10]);beta=np.minimum(beta,alt[:,6:10])
        reference=float(sum(lay.components(fixed,40).values())+sum(min(Q(0),lay.gap_delta(k,40)) for k in free))
    else:
        # Original segments contain every fixed stage boundary. Known same-domain
        # work fixes the shared OPP even on its unoccupied sibling.
        for d,units in enumerate(MEMBERS):
            if region["mask"][d] is None:continue
            lo,hi=region["mask"][d];mask=(pts[:-1]>=lo)&(pts[:-1]<hi)
            for u in units:
                vals=[v for (n,w,k),v in p.exact.items() if w==u]
                ref40[mask,u]=float(min(v[0]+5*v[1] for v in vals))
                beta[mask,u]=float(min(min(v[1],v[3]) for v in vals))
            for w in units:
                for s,e,k,i in lay.by_unit[w]:
                    if i in ids:continue
                    ix=mask&(pts[:-1]>=s)&(pts[:-1]<e)
                    if not np.any(ix):continue
                    for u in units:
                        b,v=p.node_idle[u,k]
                        ref40[ix,u]=np.maximum(ref40[ix,u],float(b+5*v))
                        beta[ix,u]=np.maximum(beta[ix,u],float(v)) if u<2 else beta[ix,u]
                    _,_,b,v=p.exact[p.kinds[i],w,k]
                    ref40[ix,w]=float(b+5*v);beta[ix,w]=float(v)
        reference=float(np.sum(ref40.sum(axis=1)*np.diff(pts))/10000+.30*p.horizon/10000)
        for i in ids:
            vals=[]
            for u,k in master.opts[i]:
                b,l,v,h=p.exact[p.kinds[i],u,k]
                floor=(b+5*l if u<2 else min(x[0]+5*x[1] for (w,f),x in p.node_idle.items() if w==u))
                vals.append((v+5*h-floor)*p.dur(i,u,k)/10000)
            reference+=float(min(vals))
    seg[:,2:6]=ref40-5*beta;seg[:,6:10]=beta
    out=integrate(seg,p.initial,p.G,p.cap,float(p.ta),np.array([],np.int64),True)
    floor_integral=np.sum(ref40.sum(axis=1)*np.diff(pts))/10000+.30*p.horizon/10000
    # Integral of beta_min*(T_lower-40); 0 is separately valid by invariance.
    residual=max(0.,out[0]-out[6]-float(floor_integral)-1e-8)
    return dict(lb=reference+residual-1e-8,residual=residual,reference40_lower_J=reference,barrier=cert,
                method="comparison_temperature_plus_reference",comparison_panels=out[-1],outward_padding_J=1e-8)
