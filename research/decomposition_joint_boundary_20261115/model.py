"""Finite four-stage DAG; exact affine electrothermal flow plus peak bounds.

Parameters and equations are inherited from the repository's synthetic input,
not from a measured device. No parameter tuning or optimizer is present here.
"""
from fractions import Fraction as F
import itertools,math
import numpy as np
from scipy.linalg import expm
from numba import njit

METRICS=['energy_J','activity_J','baseline_J','temperature_correction_J','external_J',
         'peak_sample_C','peak_bound_C','minimum_bound_C','heat_balance_J',
         'peak_CPU1_C','peak_CPU2_C','peak_GPU_C','peak_NPU_C',
         'end_CPU1_C','end_CPU2_C','end_GPU_C','end_NPU_C']

def make_modes(config,shape):
    p=config['source_platform'];modes=[]
    for i,name in enumerate(config['stages']):
        row=[]
        for unit,node in enumerate(p['units']):
            cls=node['device_class'];profile=config['catalog'][name]['profiles'].get(cls)
            if profile is None:continue
            dom=p['domains'][node['domain_id']];ref=dom['opps']['H']
            for fi,opp in enumerate(config['opps']):
                x=dom['opps'][opp];ratio=F(x['frequency_GHz'])/F(ref['frequency_GHz'])
                scale=F(str(shape[i-1])) if i in [1,2] else F(1)
                d=F(profile['d_ref_ms'])*scale*(1-F(profile['alpha'])+F(profile['alpha'])/ratio)*10
                assert d.denominator==1 # time unit = 100 microseconds
                power=F(profile['q_ref_W'])*(F(x['voltage_V'])/F(ref['voltage_V']))**2*ratio
                row.append((unit,fi,int(d),float(power)))
        modes.append(row)
    return modes

def enumerate_pool(config,shape,deadline_us):
    modes=make_modes(config,shape);D=deadline_us//100;grid=config['start_grid_us']//100
    rows=[];cfgs=[];mapping=[]
    def ceilgrid(x):return ((x+grid-1)//grid)*grid
    for cid,opts in enumerate(itertools.product(*modes)):
        u=np.array([o[0] for o in opts]);freq=np.array([o[1] for o in opts]);d=np.array([o[2] for o in opts]);power=[o[3] for o in opts]
        cfgs.append(dict(config_id=cid,units=u.tolist(),frequencies=freq.tolist(),duration_ticks=d.tolist(),activity_W=power))
        mid=int(sum(int(u[i])*4**(3-i) for i in range(4)))
        for a in range(0,max(0,D-int(d[0]+max(d[1:3])+d[3]))+1,grid):
            first=ceilgrid(a+int(d[0]))
            for b in range(first,D-int(d[1]+d[3])+1,grid):
                for c in range(first,D-int(d[2]+d[3])+1,grid):
                    overlap=b<c+d[2] and c<b+d[1]
                    if u[1]==u[2] and overlap:continue
                    shared_ok=not(u[1]<2 and u[2]<2 and freq[1]!=freq[2] and overlap)
                    for z in range(ceilgrid(max(b+d[1],c+d[2])),D-int(d[3])+1,grid):
                        rows.append((cid,mid,a,b,c,z,int(shared_ok)))
                        if len(rows)>config['candidate_cap']:raise RuntimeError('Frozen candidate cap exceeded')
    arr=np.array(rows,dtype=np.int32)
    configs=np.array([[*q['units'],*q['frequencies'],*q['duration_ticks']] for q in cfgs],dtype=np.int32)
    powers=np.array([q['activity_W'] for q in cfgs])
    return arr,configs,powers,cfgs

def physical(config,coupling,leakage):
    p=config['source_platform'];C=np.array(list(map(float,p['heat_capacity_J_per_K'])))
    G=np.array([[float(x) for x in row] for row in p['conductance_W_per_K']])
    ambient_g=G.sum(axis=1)
    if not coupling:G=np.diag(ambient_g)
    baselines=np.zeros((16,4));slopes=np.zeros((16,4))
    for code in range(16):
        for j,cls in enumerate(['CPU','CPU','GPU','NPU']):
            opp=config['opps'][(code>>j)&1];dom=p['domains'][cls]
            baselines[code,j]=float(dom['baseline_W'][opp])/(2 if j<2 else 1)
            slopes[code,j]=float(dom['local_temperature_slope_W_per_K'][opp]) if leakage else 0.
    A=np.array([np.diag(1/C)@(np.diag(s)-G) for s in slopes])
    assert max(np.max(np.real(np.linalg.eigvals(a))) for a in A)<0
    return C,G,ambient_g,baselines,slopes,A

def transitions(config,coupling,leakage,step_ticks):
    C,G,ga,base,slopes,A=physical(config,coupling,leakage)
    tables=np.zeros((16,step_ticks+1,3,4,4));norms=np.max(np.sum(abs(A),axis=2),axis=1)
    # Block exponential avoids cancellation in double-integral matrices.
    for code,a in enumerate(A):
        B=np.zeros((12,12));B[:4,:4]=a;B[:4,4:8]=np.eye(4);B[8:12,:4]=np.eye(4)
        for tick in range(1,step_ticks+1):
            m=expm(B*tick*.0001)
            tables[code,tick,0]=m[:4,:4];tables[code,tick,1]=m[:4,4:8];tables[code,tick,2]=m[8:12,4:8]
    return tables,norms,C,ga,base,slopes

@njit(cache=True)
def evaluate_pool(pool,configs,powers,shared,initial,step_ticks,tables,norms,C,ga,base,slopes,horizon_ticks=4000):
    result=np.full((len(pool),17),np.nan)
    for rid in range(len(pool)):
        row=pool[rid]
        if shared and row[6]==0:continue
        cfg=configs[row[0]];start=row[2:6];end=start+cfg[8:12]
        events=np.sort(np.concatenate((np.array([0,horizon_ticks]),start,end)))
        theta=np.full(4,initial-25.);initialU=np.dot(C,theta);peaks=np.full(4,initial)
        peaklower=initial;peakupper=initial;minbound=initial
        Ed=0.;Eb=0.;El=0.;Qout=0.;freqcode=0
        for seg in range(len(events)-1):
            t=events[seg];stop=events[seg+1]
            if stop==t:continue
            for task in range(4):
                if start[task]==t:
                    u=cfg[task];f=cfg[4+task]
                    if shared and u<2:freqcode=(freqcode&12)|(3 if f else 0)
                    else:freqcode=(freqcode&~(1<<u))|(f<<u)
            activity=np.zeros(4)
            for task in range(4):
                if start[task]<=t<end[task]:activity[cfg[task]]+=powers[row[0],task]
            b=(activity+base[freqcode])/C
            hfull=(stop-t)*.0001;Ed+=np.sum(activity)*hfull;Eb+=np.sum(base[freqcode])*hfull
            while t<stop:
                ticks=min(step_ticks,stop-t);h=ticks*.0001
                Phi=tables[freqcode,ticks,0];Gamma=tables[freqcode,ticks,1];Lambda=tables[freqcode,ticks,2]
                integ=Gamma@theta+Lambda@b
                nxt=Phi@theta+Gamma@b
                El+=np.dot(slopes[freqcode],integ);Qout+=np.dot(ga,integ)
                an=norms[freqcode];bn=np.max(np.abs(b));tn=np.max(np.abs(theta))
                bound=np.exp(an*h)*tn+np.expm1(an*h)/an*bn
                second=an*(an*bound+bn)
                interpolation_error=second*h*h/8+1e-9
                for node in range(4):
                    v=max(theta[node],nxt[node])+25.
                    peaks[node]=max(peaks[node],v)
                    peaklower=max(peaklower,v);peakupper=max(peakupper,v+interpolation_error)
                    minbound=min(minbound,min(theta[node],nxt[node])+25.-interpolation_error)
                theta=nxt;t+=ticks
        external=.30*horizon_ticks*.0001;E=Ed+Eb+El+external
        balance=E-external-Qout-(np.dot(C,theta)-initialU)
        result[rid,:9]=np.array([E,Ed,Eb,El,external,peaklower,peakupper,minbound,balance])
        result[rid,9:13]=peaks;result[rid,13:17]=theta+25.
    return result
