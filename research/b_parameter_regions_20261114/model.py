"""Independent vectorized RC evaluator; synthetic parameters only."""
import itertools,json,math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'nominal_synthetic_parameters.json').read_text(encoding='utf-8'))

def compositions(n):
    if n==0:yield ()
    for b in [1,2,4]:
        if b<=n:
            for rest in compositions(n-b):yield (b,)+rest

def catalogue():
    out=[]
    for comp in compositions(4):
        for waits in itertools.product([0.,.02],repeat=len(comp)):
            base='B-'+''.join(map(str,comp))+'-'+''.join('1' if w else '0' for w in waits)
            for dpm in [False,True]:
                out.append({'id':base+('-on' if dpm else '-off'),'base_id':base,'batches':comp,'waits':waits,'dpm':dpm})
    assert len(out)==92
    return out

def schedule(action,scenario):
    """Segments are (start,end,dynamic_GPU_W,extra_wake_GPU_W,awake_GPU)."""
    cfg=P['B'];arr=cfg['arrivals_s'];previous=0.;done=0;segs=[];finishes=[]
    wake=P['wake_duration_s']*scenario['wake_time_scale']
    active_dpm=action['dpm'] and scenario['sleepcontrast']>0
    for b,wait in zip(action['batches'],action['waits']):
        ready=max(previous,arr[done+b-1])+wait
        sleep=active_dpm and ready-previous>=P['sleep_gap_min_s']-1e-12
        if ready>previous+1e-12:segs.append((previous,ready,0.,0.,float(not sleep)))
        begin=ready
        if sleep:
            begin+=wake
            segs.append((ready,begin,0.,scenario['wake_energy_J']/wake,1.))
        duration=cfg['batch_duration_s'][str(b)]*(scenario['b2_time_scale'] if b==2 else 1.)
        power=cfg['batch_dynamic_W'][str(b)]*(scenario['b2_power_scale'] if b==2 else 1.)
        end=begin+duration
        segs.append((begin,end,power,0.,1.));finishes.extend([end]*b)
        previous=end;done+=b
    H=P['main_horizon_s']
    assert done==4 and previous<=H+1e-12
    if previous<H:
        sleep=active_dpm and H-previous>=P['sleep_gap_min_s']-1e-12
        segs.append((previous,H,0.,0.,float(not sleep)))
    assert abs(sum(e-s for s,e,*_ in segs)-H)<1e-12
    assert all(segs[i][1]<=segs[i+1][0]+1e-12 for i in range(len(segs)-1))
    feasible=all(f<=a+cfg['relative_deadline_s']+1e-12 for f,a in zip(finishes,arr))
    return segs,{'deadline_ok':feasible,'finishes_s':finishes,'wake_count':sum(s[3]>0 or (s[2]==0 and s[4]==1 and abs(s[1]-s[0]-wake)<1e-10) for s in segs),'finish_s':max(finishes)}

def constants(scenario):
    g=P['G_coupling_W_per_K']
    G=(np.diag(P['G_environment_W_per_K'])+np.array([[g,-g],[-g,g]]))/scenario['R_scale']
    C=np.array(P['C_J_per_K'])*scenario['C_scale']
    L=np.array(P['leak_at_40C_W'])*scenario['leak_scale']
    beta=P['leak_beta_per_K']*scenario['beta_scale']
    base=np.array(P['awake_base_W']);old_sleep=np.array(P['sleep_base_W'])
    sleep=base-scenario['sleepcontrast']*(base-old_sleep)
    sleep_gate=1-scenario['sleepcontrast']*(1-P['sleep_leak_factor'])
    assert np.linalg.eigvalsh(G).min()>0 and C.min()>0 and sleep.min()>=0
    return G,C,L,beta,base,sleep,sleep_gate

def evaluate(scenario,temperatures,actions=None,main_step=.002,tail_step=.02,cpu_fixed=None):
    actions=catalogue() if actions is None else actions
    na,nt=len(actions),len(temperatures)
    G,C,L,beta,base,sleep,sleep_gate=constants(scenario)
    y=np.zeros((na,nt,4));y[:,:,:2]=np.array(temperatures)[None,:,None]
    if cpu_fixed is not None:y[:,:,0]=cpu_fixed
    peak=y[:,:,:2].max(axis=2).copy()
    schedules=[schedule(a,scenario) for a in actions]
    edges=sorted({round(t,12) for segs,_ in schedules for seg in segs for t in seg[:2]})
    exact_base=np.zeros(na);exact_dyn=np.zeros(na);exact_wake=np.zeros(na)

    def integrate(start,end,dynamic,extra,awake,max_step):
        nonlocal y,peak
        b=np.empty((na,1,2));b[:,:,0]=base[0]
        b[:,:,1]=sleep[1]+(base[1]-sleep[1])*awake[:,None]
        q=np.zeros_like(b);q[:,:,1]=(dynamic+extra)[:,None]
        gate=np.ones_like(b);gate[:,:,1]=sleep_gate+(1-sleep_gate)*awake[:,None]
        def rhs(z):
            leak=L*np.exp(beta*(z[:,:,:2]-40))*gate
            heat=b+q+leak
            out=np.empty_like(z)
            out[:,:,:2]=(-(z[:,:,:2]-scenario['ambient_C'])@G.T+heat)/C
            out[:,:,2]=heat.sum(axis=2)+P['external_base_W']
            out[:,:,3]=leak.sum(axis=2)
            return out
        steps=max(1,math.ceil((end-start)/max_step-1e-10));dt=(end-start)/steps
        for _ in range(steps):
            k1=rhs(y);k2=rhs(y+dt*k1/2);k3=rhs(y+dt*k2/2);k4=rhs(y+dt*k3)
            y+=dt*(k1+2*k2+2*k3+k4)/6
            peak=np.maximum(peak,y[:,:,:2].max(axis=2))
        assert np.isfinite(y).all()
        return b[:,0,:].sum(axis=1)+P['external_base_W']

    for lo,hi in zip(edges,edges[1:]):
        if hi-lo<1e-12:continue
        mid=(lo+hi)/2
        chosen=[next(seg for seg in ss if seg[0]-1e-12<=mid<seg[1]+1e-12) for ss,_ in schedules]
        chosen=np.array(chosen)
        dyn,extra,awake=chosen[:,2],chosen[:,3],chosen[:,4]
        b=integrate(lo,hi,dyn,extra,awake,main_step)
        exact_base+=b*(hi-lo);exact_dyn+=dyn*(hi-lo);exact_wake+=extra*(hi-lo)
    main_y=y.copy();main_peak=peak.copy()
    H=P['main_horizon_s'];tail=P['continuation_s']
    tail_base=integrate(H,H+tail,np.zeros(na),np.zeros(na),np.zeros(na),tail_step)
    energy=np.stack([main_y[:,:,2],y[:,:,2]])
    components=np.empty((2,na,nt,4))
    for k,z in enumerate([main_y,y]):
        components[k,:,:,0]=(exact_base+(tail*tail_base if k else 0))[:,None]
        components[k,:,:,1]=exact_dyn[:,None]
        components[k,:,:,2]=z[:,:,3]
        components[k,:,:,3]=exact_wake[:,None]
    residual=float(np.max(np.abs(components.sum(axis=3)-energy)))
    assert residual<1e-9,residual
    peaks=np.stack([main_peak,peak])
    deadlines=np.array([m['deadline_ok'] for _,m in schedules])
    feasible=deadlines[None,:,None]&(peaks<=P['temperature_limit_C']-1e-5)
    return dict(energy=energy,components=components,peak=peaks,feasible=feasible,terminal=np.stack([main_y[:,:,:2],y[:,:,:2]]),accounting_error_J=residual,schedule_meta=[m for _,m in schedules])
