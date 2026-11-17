"""Vectorized finite-catalogue simulator, dimensionless and entirely synthetic.

Nonpreemptive work integration, separate requested/applied frequency and thermal
cap. No paper-specific hardware constants are used here.
"""
import json,time
from pathlib import Path
import numpy as np
from scipy.linalg import expm

ROOT=Path(__file__).resolve().parent;P=json.loads((ROOT/'design.json').read_text())
DEADLINE=None
TEMPLATES=P['templates'];MAP=np.array([x['map'] for x in TEMPLATES]);FREQ=np.array([x['frequency'] for x in TEMPLATES])
WORK=np.tile(P['work'],3);ARR=np.repeat(P['arrivals'],4);DEAD=ARR+P['relative_deadline'];RATES=np.array(P['rates']);PREV=np.array([-1,0,-1,2, -1,4,-1,6, -1,8,-1,10]);TYPE=np.arange(12)%4
ALL_SEQUENCES=np.array(np.meshgrid(*([np.arange(16)]*3),indexing='ij')).reshape(3,-1).T

def constants(s,dt):
    C=np.array(P['C'])*s['c_scale'];g=np.array(P['Genv'])*s['g_scale'];gc=P['Gcouple']*s['coupling_scale'];leak=np.array(P['leak_coefficient'])
    K=np.diag(g+gc-leak)+np.array([[0.,-gc],[-gc,0.]])
    assert np.linalg.eigvalsh(K).min()>0 and C.min()>0
    # State [x0,x1,E,constant_power0,constant_power1]; includes exact leakage
    # energy integration under the per-tick average active power assumption.
    A=np.zeros((5,5));A[:2,:2]=-K/C[:,None];A[:2,3:]=np.diag(1/C);A[2,:2]=leak;A[2,3:]=1
    F=expm(A*dt)
    return C,K,F

def simulate(s,sequences,dt=None,hardware=True,reactive=False,cold_table=False,trace=False,prefix=True,stop_at=None):
    seq=np.asarray(sequences,dtype=int).reshape(-1,3);n=len(seq);dt=P['dt'] if dt is None else dt
    C,K,F=constants(s,dt);maps=MAP[seq].reshape(n,12);req_per_job=FREQ[seq]
    # Per job requested frequency, chosen before execution; never remapped.
    jobfreq=np.take_along_axis(np.repeat(req_per_job,4,axis=1),maps[:,:,None],axis=2)[:,:,0]
    x=np.broadcast_to(s['initial'],(n,2)).copy();energy=np.zeros(n);switchE=np.zeros(n);baseE=np.zeros(n);activeE=np.zeros(n)
    rem=np.broadcast_to(WORK,(n,12)).copy();done=np.zeros((n,12),bool);started=done.copy();start=np.full((n,12),np.nan);finish=np.full((n,12),np.nan)
    busy=np.full((n,2),-1,int);requested=np.full((n,2),.5);applied=requested.copy();stall=np.zeros((n,2));cap=np.zeros((n,2),bool);hot=np.zeros((n,2),int);cool=hot.copy();software=np.zeros(n,bool)
    peak=x.copy();entries=np.zeros((n,2),int);capbusy=np.zeros((n,2));first=np.full((n,2),np.nan);changes=np.zeros((n,2),int);log=[];mid=None;main=None
    sample_ticks=int(round(P['hardware_sample']/dt));trip_count=1+int(round(s['trip_confirm']/P['hardware_sample']));release_count=1+int(round(s['release_confirm']/P['hardware_sample']))
    if not np.isclose(sample_ticks*dt,P['hardware_sample']):raise ValueError('dt must divide hardware sample')
    idx=np.arange(n)

    def step_control(t):
        nonlocal hot,cool,cap,software,applied,x,energy,switchE,stall,entries,first,changes
        if hardware and not cold_table:
            hot=np.where((~cap)&(x>=P['trip']),hot+1,0);cool=np.where(cap&(x<=P['release']),cool+1,0)
            new=(~cap)&(hot>=trip_count);release=cap&(cool>=release_count)
            first=np.where(new&np.isnan(first),t,first);entries+=new;cap=(cap|new)&~release
        if reactive and not cold_table:
            software=np.where(x[:,0]>=P['reactive_trip'],True,np.where(x[:,0]<=P['reactive_release'],False,software))

    def advance(t,k,serve):
        nonlocal x,energy,switchE,baseE,activeE,peak,applied,stall,changes
        if k%sample_ticks==0:step_control(t)
        if serve:
            ready=(~started)&(ARR[None,:]<=t+1e-9)
            ready[:,PREV>=0]&=done[:,PREV[PREV>=0]]
            for dev in [0,1]:
                choices=ready&(maps==dev);has=(busy[:,dev]<0)&choices.any(axis=1);j=choices.argmax(axis=1);rows=idx[has];jj=j[has]
                busy[has,dev]=jj;started[rows,jj]=True;start[rows,jj]=t;requested[has,dev]=jobfreq[rows,jj]
        target=np.minimum(requested,np.where(cap,P['throttled_frequency'],1.))
        if reactive:target[:,0]=np.minimum(target[:,0],np.where(software,.5,1.))
        change=np.abs(target-applied)>1e-12
        if change.any():
            jump=change*P['frequency_transition_energy'];x+=jump/C;energy+=jump.sum(axis=1);switchE+=jump.sum(axis=1);changes[:]+=change
            applied[:]=target;stall[change]=t+P['frequency_transition_time']
        fractions=np.zeros((n,2))
        for dev in [0,1]:
            j=busy[:,dev];working=(j>=0)&(stall[:,dev]<=t+1e-9)&serve;rr=idx[working];jj=j[working]
            speed=RATES[dev,TYPE[jj]]*applied[working,dev];assert (speed>0).all()
            frac=np.minimum(1.,rem[rr,jj]/(dt*speed));fractions[working,dev]=frac
            capbusy[working,dev]+=dt*frac*(cap[working,dev]&(requested[working,dev]>.5))
            rem[rr,jj]=np.maximum(0.,rem[rr,jj]-dt*speed)
            completed=rem[rr,jj]<=1e-10;cr=rr[completed];cj=jj[completed]
            done[cr,cj]=True;finish[cr,cj]=t+dt*frac[completed];busy[cr,dev]=-1
        active=fractions*(np.array(P['active_base'])+np.array(P['dynamic_coefficient'])*applied**3)
        power=np.array(P['idle_power'])+active
        if cold_table:
            x[:]=.2;energy+=dt*(power.sum(axis=1)+np.array(P['leak_coefficient'])@np.array([.2,.2])+P['external_power'])
        else:
            z=np.column_stack((x,np.zeros(n),power));z=z@F.T;x[:]=z[:,:2];energy+=z[:,2]+dt*P['external_power']
        baseE+=dt*(sum(P['idle_power'])+P['external_power']);activeE+=dt*active.sum(axis=1);peak=np.maximum(peak,x)
        if trace and k%sample_ticks==0:
            for row in range(n):log.append({'trajectory':row,'t':round(t+dt,8),'x':x[row].tolist(),'energy':float(energy[row]),'busy':busy[row].tolist(),'requested':requested[row].tolist(),'actual':applied[row].tolist(),'hardware_cap':cap[row].astype(int).tolist(),'software_cap':bool(software[row]),'completed':int(done[row].sum())})

    H=P['main_horizon'];end=H+P['tail'] if stop_at is None else stop_at
    for k in range(int(round(end/dt))):
        if k%50==0 and DEADLINE is not None and time.monotonic()>DEADLINE:raise TimeoutError('Frozen simulation wall-clock budget reached')
        t=k*dt
        if prefix and abs(t-16.)<dt/10:
            mid={'energy':energy.copy(),'x':x.copy(),'requested':requested.copy(),'applied':applied.copy(),'cap':cap.copy(),'hot':hot.copy(),'cool':cool.copy(),'stall':stall.copy(),'first8_feasible':(done[:,:8]&(finish[:,:8]<=DEAD[None,:8]+1e-9)).all(axis=1)}
        if abs(t-H)<dt/10:
            main={'energy':energy.copy(),'x':x.copy(),'completed':done.sum(axis=1).copy(),'unfinished_work':rem.sum(axis=1).copy()};busy[:]=-1
        advance(t,k,t<H)
    if main is None:main={'energy':energy.copy(),'x':x.copy(),'completed':done.sum(axis=1).copy(),'unfinished_work':rem.sum(axis=1).copy()}
    feasible=done.all(axis=1)&np.all(finish<=DEAD[None,:]+1e-9,axis=1)
    return {'energy':energy,'main_energy':main['energy'],'tail_energy':energy-main['energy'],'components':np.column_stack([baseE,activeE,energy-baseE-activeE-switchE,switchE]),'feasible':feasible,'completed':main['completed'],'unfinished_work':main['unfinished_work'],'deadline_misses':((finish>DEAD[None,:]+1e-9)|~done).sum(axis=1),'start':start,'finish':finish,'peak':peak,'terminal':x,'hw_entries':entries,'cap_busy_time':capbusy,'first_trip':first,'frequency_changes':changes,'prefix':mid,'trace':log}

def prefix_idle_energy(s,mid,dt=None):
    """Exact same idle/hardware mechanism from the 16-unit lookahead endpoint."""
    dt=P['dt'] if dt is None else dt;C,K,F=constants(s,dt);x=mid['x'].copy();n=len(x);energy=mid['energy'].copy();requested=mid['requested'];applied=mid['applied'].copy();cap=mid['cap'].copy();hot=mid['hot'].copy();cool=mid['cool'].copy()
    sample=int(round(.1/dt));up=1+int(round(s['trip_confirm']/.1));down=1+int(round(s['release_confirm']/.1));power=np.broadcast_to(P['idle_power'],(n,2))
    for k in range(int(round(P['tail']/dt))):
        if k%50==0 and DEADLINE is not None and time.monotonic()>DEADLINE:raise TimeoutError('Frozen simulation wall-clock budget reached')
        if k%sample==0:
            hot=np.where((~cap)&(x>=P['trip']),hot+1,0);cool=np.where(cap&(x<=P['release']),cool+1,0);cap=(cap|((~cap)&(hot>=up)))&~(cap&(cool>=down))
        target=np.minimum(requested,np.where(cap,.5,1.));change=abs(target-applied)>1e-12;jump=change*P['frequency_transition_energy'];x+=jump/C;energy+=jump.sum(axis=1);applied=target
        z=np.column_stack([x,np.zeros(n),power])@F.T;x=z[:,:2];energy+=z[:,2]+dt*P['external_power']
    return energy
