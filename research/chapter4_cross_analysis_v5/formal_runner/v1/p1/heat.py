"""Continuous Taylor enclosure and independent fourth-order prediction.

All times in native computation are seconds. See numerical_bounds.md.
"""
import math
import numpy as np
from numba import njit
from model import event_arrays, independent_events, Invalid


@njit(cache=True)
def integrate(events, initial, G, cap, ta, resets, rigorous):
    n=len(events)
    traces=np.zeros((n,17))
    x=initial.copy()
    maxima=x.copy()
    upper=x.copy()
    mins=x.copy()
    minlo=x.copy()
    node_time=np.zeros(4)
    energy=np.zeros(4)
    bases=np.zeros(4)
    temps=np.zeros(4)
    round_T=2.e-12
    round_E=0.
    panels=0
    for l in range(n):
        t,e=int(events[l,0]),int(events[l,1])
        for boundary in resets:
            if boundary==t: x=initial.copy()
        b=events[l,2:6]; slope=events[l,6:10]
        A=-G/cap.reshape((4,1))
        for u in range(4): A[u,u]+=slope[u]/cap[u]
        a=(G@np.full(4,ta)+b-35*slope)/cap
        norm=np.max(np.sum(np.abs(A),axis=1))
        if (np.max(np.sum(A,axis=1))>=0 or norm>5 or np.max(np.abs(a))>400
            or np.max(np.abs(slope))>.1 or np.max(np.abs(b))>12):
            raise ValueError("certification constants out of range")
        dt=(e-t)/10000.
        steps=max(1,int(math.ceil(dt/(0.002 if rigorous else .011))))
        h=dt/steps
        el=np.zeros(4)
        segment_peak=x.copy()
        segment_upper=x.copy()+round_T
        traces[l,0:4]=x
        for j in range(steps):
            start=x.copy()
            v=A@x+a
            if np.max(np.abs(x))>150 or np.max(np.abs(v))>1000: raise ValueError("state outside proof envelope")
            if rigorous:
                term=h*v
                delta=term.copy()
                int_x=h*(x+term/2)
                for order in range(2,10):
                    term=(h/order)*(A@term)
                    delta+=term
                    int_x+=(h/(order+1))*term
                x+=delta
                round_T+=3.e-12
            else:
                k2=A@(x+h*v/2)+a
                k3=A@(x+h*k2/2)+a
                k4=A@(x+h*k3)+a
                x+=(h/6)*(v+2*k2+2*k3+k4)
                int_x=h*(start+x)/2
            # Cooperative contraction bounds ||exp(At)v||_inf by ||v||_inf.
            # Derivative sign or the secant interpolation error controls every interior time.
            curvature=norm*(np.max(np.abs(v))+1.e-8)+1.e-8
            for u in range(4):
                local=max(start[u],x[u])
                interp=0. if abs(v[u])>curvature*h+norm*round_T+1.e-9 else curvature*h*h/8
                up=local+interp+round_T
                upper[u]=max(upper[u],up)
                minlo[u]=min(minlo[u],min(start[u],x[u])-interp-round_T)
                mins[u]=min(mins[u],x[u])
                segment_peak[u]=max(segment_peak[u],local)
                segment_upper[u]=max(segment_upper[u],up)
                if x[u]>maxima[u]:
                    maxima[u]=x[u]
                    node_time[u]=t/10000+(j+1)*h
            correction=slope*(int_x-35*h)
            energy+=h*b+correction
            el+=h*b+correction
            temps+=correction
            bases+=h*events[l,10:14]
            round_E+=h*np.sum(np.abs(slope))*round_T+2.e-12
            panels+=1
        traces[l,4:8]=x
        traces[l,8:12]=segment_upper
        traces[l,12:16]=el
        traces[l,16]=round_T
    Ej=np.sum(energy)+.3*events[-1,1]/10000
    return (Ej,maxima-round_T,upper,minlo,mins+round_T,node_time,round_E+1.e-10,
            energy,bases,temps,traces,panels)


def evaluate(p,plan,*,cert=False,reset=False,trace=False):
    rows,low=plan
    if cert:
        ev,sw=independent_events(p,rows,low)
    else:
        ev,sw,_=event_arrays(p,rows,low)
    boundaries=np.array(p.boundaries if reset else [],dtype=np.int64)
    out=integrate(ev,p.initial,p.G,p.cap,float(p.ta),boundaries,cert)
    E,lo,hi,mn,mnu,at,err,nodes,base,tc,tr,panels=out
    status="UNRESOLVED"
    if cert:
        if max(lo)>100 or min(mnu)<20: status="OUT_OF_MODEL"
        elif min(mn)>=20 and max(hi)<=100 and err<=1e-6 and max(hi)-max(lo)<=.001:
            status="SAFE" if max(hi)<=80 else "HOT" if max(lo)>80 else "UNRESOLVED"
    result=dict(status=status,E_J=float(E),E_bounds=[float(E-err),float(E+err)] if cert else None,
                peak_lo=list(lo),peak_hi=list(hi),peak_tick=[float(z*10000) for z in at],
                minimum_lo=list(mn),hotspot=int(np.argmax(lo)),panels=panels,
                peak_C=float(max(lo)),safe_margin_K=80-float(max(hi)),switch_count=len(sw),
                energy_by_node_J=list(nodes),base_J=sum(base),temperature_J=sum(tc),
                switch_J=len(sw)*.0015,external_J=p.horizon*.3/10000,
                activity_J=sum(nodes)-sum(base)-sum(tc)-len(sw)*.0015,
                min_deadline_slack_ms=min((r["deadline_tick"]-p.finish(3*j+2,rows[3*j+2]))/10+
                                          float(r["deadline_ms"]-r["deadline_tick"]/10)
                                          for j,r in enumerate(p.req)))
    if trace: result["events"]=np.column_stack((ev,tr)).tolist()
    return result
