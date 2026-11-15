"""Two work-progress states, two thermal nodes; no hardware prediction claim."""
import math
import numpy as np
from numba import njit

KEYS=['ambient_C','R_jp_K_W','R_pa_K_W','C_j_J_K','C_p_J_K','leak_45_W',
      'leak_beta_K_inv','P_A_W','P_B_W','P_base_W','P_external_W','P_host_busy_W',
      'slowdown','stall_power_fraction','throttle_on_C','throttle_off_C',
      'throttle_rate','throttle_power_exponent','safety_j_C','safety_plate_C',
      'launch_energy_J','work_A_s','work_B_s','horizon_s','deadline_s']
METRICS=['energy_J','dynamic_J','leak_J','base_J','host_J','launch_J',
         'finish_A_s','finish_B_s','peak_j_C','peak_p_C','end_j_C','end_p_C',
         'overlap_s','throttle_busy_s','remaining_A_s','remaining_B_s',
         'heat_balance_residual_J','end_throttle','rejected_heat_J']
ACTIONS=['C','A25','A50','A75','B25','B50','B75','S_AB','S_BA']

def pack(d): return np.array([d[k] for k in KEYS],dtype=float)

@njit(cache=True)
def rhs(Tj,Tp,dynamic,host,p,leak_on):
    leak=p[5]*math.exp((p[6] if leak_on else 0.0)*(Tj-45.0))
    jp=(Tj-Tp)/p[1]; outward=(Tp-p[0])/p[2]
    return (dynamic+host+leak-jp)/p[3],(jp+p[9]-p[10]-outward)/p[4],leak,outward

@njit(cache=True)
def cycle(p,Tj,Tp,action,leak_on=True,contention_on=True,throttle_on=False,dt=0.001,mode=0):
    a=p[21];b=p[22];H=p[23];rA=a;rB=b
    releaseA=0.0;releaseB=0.0
    if 1<=action<=3:releaseB=(action*.25)*a
    if 4<=action<=6:releaseA=((action-3)*.25)*b
    if action==7:releaseB=1e30
    if action==8:releaseA=1e30
    startedA=False;startedB=False;finishA=math.inf;finishB=math.inf
    t=0.;peakj=Tj;peakp=Tp;initialU=p[3]*Tj+p[4]*Tp
    Ed=0.;El=0.;Eb=0.;Eh=0.;Es=0.;Q=0.;overlap=0.;throttled=0.
    while t<H-1e-12:
        if action==7 and rA<=1e-12:releaseB=t
        if action==8 and rB<=1e-12:releaseA=t
        if not startedA and t>=releaseA-1e-12:
            startedA=True;Es+=p[20];Tj+=p[20]/p[3]
        if not startedB and t>=releaseB-1e-12:
            startedB=True;Es+=p[20];Tj+=p[20]/p[3]
        peakj=max(peakj,Tj)
        activeA=startedA and rA>1e-12;activeB=startedB and rB>1e-12
        if throttle_on:
            if Tj>=p[14]:mode=1
            elif Tj<=p[15]:mode=0
        else:mode=0
        freq=p[16] if mode else 1.0
        both=activeA and activeB
        slow=p[12] if both and contention_on else 1.0
        rate=freq/slow
        dynamic=(p[7]*activeA+p[8]*activeB)*freq**p[17]*(p[13]+(1-p[13])/slow)
        host=p[11] if rA>1e-12 or rB>1e-12 else 0.0
        h=min(dt,H-t)
        if not startedA and releaseA>t:h=min(h,releaseA-t)
        if not startedB and releaseB>t:h=min(h,releaseB-t)
        if activeA:h=min(h,rA/rate)
        if activeB:h=min(h,rB/rate)
        k1=rhs(Tj,Tp,dynamic,host,p,leak_on)
        k2=rhs(Tj+h*.5*k1[0],Tp+h*.5*k1[1],dynamic,host,p,leak_on)
        k3=rhs(Tj+h*.5*k2[0],Tp+h*.5*k2[1],dynamic,host,p,leak_on)
        k4=rhs(Tj+h*k3[0],Tp+h*k3[1],dynamic,host,p,leak_on)
        Tj+=h*(k1[0]+2*k2[0]+2*k3[0]+k4[0])/6
        Tp+=h*(k1[1]+2*k2[1]+2*k3[1]+k4[1])/6
        El+=h*(k1[2]+2*k2[2]+2*k3[2]+k4[2])/6
        Q+=h*(k1[3]+2*k2[3]+2*k3[3]+k4[3])/6
        Ed+=h*dynamic;Eb+=h*p[9];Eh+=h*host
        if both:overlap+=h
        if mode and (activeA or activeB):throttled+=h
        t+=h
        if activeA:
            rA=max(0.,rA-rate*h)
            if rA<=1e-12:rA=0.;finishA=t
        if activeB:
            rB=max(0.,rB-rate*h)
            if rB<=1e-12:rB=0.;finishB=t
        peakj=max(peakj,Tj);peakp=max(peakp,Tp)
        if not math.isfinite(Tj) or Tj>200:break
    E=Ed+El+Eb+Eh+Es
    balance=E-p[10]*t-Q-(p[3]*Tj+p[4]*Tp-initialU)
    return np.array([E,Ed,El,Eb,Eh,Es,finishA,finishB,peakj,peakp,Tj,Tp,overlap,
                     throttled,rA,rB,balance,float(mode),Q])

def feasible(v,p,throttle):
    limit=p[18] if throttle else p[14]
    return bool(max(v[6:8])<=p[24]+1e-9 and v[8]<=limit+1e-6 and v[9]<=p[19]+1e-6
                and np.isfinite(v).all() and max(v[14:16])<1e-10)

def initial_states(p):
    # Smallest stable idle equilibrium reached by monotone fixed-point iteration.
    Tj=p[0];Tp=p[0];converged=False
    for _ in range(10000):
        leak=p[5]*math.exp(p[6]*(Tj-45))
        np_=p[0]+(p[9]-p[10]+leak)*p[2]
        nj=np_+leak*p[1]
        if nj>p[14] or np_>p[19]:return None,'idle equilibrium unsafe/runaway'
        if abs(nj-Tj)<1e-11:converged=True;Tj=nj;Tp=np_;break
        Tj=nj;Tp=np_
    if not converged:return None,'idle equilibrium did not converge'
    states=[(Tj,Tp)]
    for power in [10.,15.,20.,25.]:
        Tp=p[0]+(power-p[10])*p[2]
        Tj=Tp+(power-p[9])*p[1]
        leak=p[5]*math.exp(p[6]*(Tj-45))
        required_dynamic=power-p[9]-p[11]-leak
        if required_dynamic<0:return None,'preload would require negative dynamic power'
        if Tj>p[14] or Tp>p[19]:return None,'preload equilibrium exceeds fixed-clock proxy guard'
        if power<=p[9]+p[5]*math.exp(p[6]*(states[0][0]-45)):return None,'preload below idle input'
        states.append((Tj,Tp))
    return np.array(states),'valid'

@njit(cache=True)
def sequence(p,initial,policy,threshold,below,above,cycles=240,reset=False,throttle=False,dt=.001):
    # policy 0: fixed `below`; policy 1: single-temperature threshold; 2: myopic enumeration.
    Tj=initial[0];Tp=initial[1];mode=0;rows=np.zeros((cycles,24))
    for k in range(cycles):
        if reset:Tj=initial[0];Tp=initial[1];mode=0
        chosen=below
        if policy==1:chosen=below if Tj<threshold else above
        if policy==2:
            best=1e300
            for a in range(9):
                v=cycle(p,Tj,Tp,a,True,True,throttle,dt,mode)
                limit=p[18] if throttle else p[14]
                ok=max(v[6],v[7])<=p[24]+1e-9 and v[8]<=limit+1e-6 and v[9]<=p[19]+1e-6
                if ok and v[0]<best:best=v[0];chosen=a
        v=cycle(p,Tj,Tp,chosen,True,True,throttle,dt,mode)
        rows[k,0]=k;rows[k,1]=Tj;rows[k,2]=Tp;rows[k,3]=chosen
        rows[k,4:23]=v
        limit=p[18] if throttle else p[14]
        rows[k,23]=1.0 if (max(v[6],v[7])<=p[24]+1e-9 and v[8]<=limit+1e-6 and v[9]<=p[19]+1e-6) else 0.0
        Tj=v[10];Tp=v[11];mode=int(v[17])
        # Do not silently drop or defer incomplete packets into a following period.
        if max(v[14],v[15])>1e-10:
            for j in range(k+1,cycles):rows[j,:]=math.nan
            break
    return rows
