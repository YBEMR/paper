"""Frequency-indexed analytic replay; frozen primitive and peak enclosure reused.

Only interval-specific idle intercept/slope/eigenbasis indexing is new.
All periods propagate the preceding physical temperature.
"""
from common import *
from numba import njit
from thermal import _primitive, _tighten_peak, ROUND_GUARD, DEFAULT_PEAK_WIDTH, modes

@njit(cache=True)
def integrate(dt,activity,transfer,states,capacity,idle,slopes,lam,u,inv,
              board,board_share,tr_share,ta,tref,T0,repeats):
    T=T0.copy();lo=T0.copy()-ROUND_GUARD;hi=T0.copy()+ROUND_GUARD
    leak=np.zeros(4);base=np.zeros(4);act=np.zeros(4);common=0.;xfer=0.
    # Each row is a cumulative, continuously inherited prefix certificate.
    result=np.empty((repeats,30))
    for cycle in range(repeats):
        for i in range(len(dt)):
            h=dt[i];s=states[i];x=inv[s]@(T-ta)
            d=np.empty(4);int_x=np.empty(4);next_x=np.empty(4)
            heat=(idle[s]+board*board_share+activity[i]+slopes[s]*(ta-tref)+transfer[i]*tr_share)/capacity
            for k in range(4):
                force=0.
                for n in range(4):force+=inv[s,k,n]*heat[n]
                d[k]=lam[s,k]*x[k]+force
                phi,psi=_primitive(lam[s,k],h)
                int_x[k]=h*x[k]+psi*d[k];next_x[k]=x[k]+phi*d[k]
            for n in range(4):
                end=ta;integral=(ta-tref)*h;curvature=0.;coeff=np.empty(4)
                for k in range(4):
                    end+=u[s,n,k]*next_x[k];integral+=u[s,n,k]*int_x[k]
                    coeff[k]=u[s,n,k]*d[k];curvature+=abs(lam[s,k]*coeff[k])
                delta=h*h*curvature/8;observed=max(T[n],end)
                lower=observed-ROUND_GUARD;upper=observed+delta+ROUND_GUARD
                if delta>DEFAULT_PEAK_WIDTH or (lower<=80.<upper and delta>ROUND_GUARD):
                    lower,upper=_tighten_peak(T[n],end,h,80.,lam[s],coeff,DEFAULT_PEAK_WIDTH)
                lo[n]=max(lo[n],lower);hi[n]=max(hi[n],upper);T[n]=end
                leak[n]+=slopes[s,n]*integral
                base[n]+=idle[s,n]*h;act[n]+=activity[i,n]*h
            common+=board*h;xfer+=transfer[i]*h
        result[cycle,:4]=T;result[cycle,4:8]=lo;result[cycle,8:12]=hi
        result[cycle,12:16]=leak;result[cycle,16:20]=base;result[cycle,20:24]=act
        result[cycle,24]=common;result[cycle,25]=xfer
        result[cycle,26]=common+xfer+np.sum(leak)+np.sum(base)+np.sum(act)
        result[cycle,27]=cycle+1;result[cycle,28]=(cycle+1)*0.04
        result[cycle,29]=1 if np.max(hi)<=80 else -1 if np.max(lo)>80 else 0
    return result

def arguments(sched,opp,mode,ambient,initial,repeats):
    ls=levels(sched,opp,mode);choices=sorted(set(ls))
    kws=[thermal_kwargs(PLATFORM,o,ambient,True,"base") for o in choices]
    es=[modes(tuple(k["capacity_J_K"]),tuple(map(tuple,k["conductance_W_K"])),tuple(k["slope_W_K"])) for k in kws]
    k=kws[0]
    return (sched.duration_ns*1e-9,sched.active_w,sched.transfer_w,
        np.array([choices.index(o) for o in ls],dtype=np.int64),
        np.array(k["capacity_J_K"]),np.array([v["idle_W"] for v in kws]),
        np.array([v["slope_W_K"] for v in kws]),np.array([e[0] for e in es]),
        np.ascontiguousarray([e[1] for e in es]),np.ascontiguousarray([e[2] for e in es]),
        float(k["board_W"]),np.array(k["board_heat_fraction"]),np.array(k["transfer_heat_fraction"]),
        float(ambient),float(k["reference_C"]),np.array(initial,dtype=float),repeats)

def certificate(v):
    return dict(final_C=v[:4].tolist(),peak_lower_C=v[4:8].tolist(),peak_upper_C=v[8:12].tolist(),
        leakage_J=v[12:16].tolist(),idle_J=v[16:20].tolist(),activity_J=v[20:24].tolist(),
        common_J=float(v[24]),transfer_J=float(v[25]),energy_J=float(v[26]),
        frames=int(v[27]),duration_s=float(v[28]),thermal_status={1:"SAFE",-1:"VIOLATION",0:"UNRESOLVED"}[int(v[29])])
