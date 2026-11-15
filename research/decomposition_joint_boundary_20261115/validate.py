"""Independent enumeration check and ODE verification; optional result replay."""
from pathlib import Path
import argparse,itertools,json,hashlib
import numpy as np
from scipy.integrate import solve_ivp
from model import enumerate_pool,physical,transitions,evaluate_pool
ROOT=Path(__file__).resolve().parent

def independent_pool(cfg,configs,deadline):
    # Cartesian enumeration, not the nested earliest-bound implementation.
    grid=cfg['start_grid_us']//100;D=deadline//100
    starts=np.array(list(itertools.product(range(0,D+1,grid),repeat=4)))
    records=[]
    for cid,c in enumerate(configs):
        end=starts+c[8:12]
        ok=np.all(end<=D,axis=1)
        for a,b in cfg['edges']:ok &= end[:,a]<=starts[:,b]
        shared=np.ones(len(starts),bool)
        for a,b in itertools.combinations(range(4),2):
            overlap=(starts[:,a]<end[:,b])&(starts[:,b]<end[:,a])
            if c[a]==c[b]:ok &= ~overlap
            if c[a]<2 and c[b]<2 and c[4+a]!=c[4+b]:shared &= ~overlap
        mid=sum(int(c[i])*4**(3-i) for i in range(4))
        for k in np.flatnonzero(ok):records.append((cid,mid,*starts[k],int(shared[k])))
    return np.array(records,dtype=np.int32)

def ivp_reference(row,configs,powers,cfg,coupling,leakage,shared,initial):
    C,G,ga,base,slopes,A=physical(cfg,coupling,leakage)
    c=configs[row[0]];start=row[2:6]*.0001;end=start+c[8:12]*.0001
    events=sorted(set([0.,.4,*start,*end]));freq=[0]*4
    y=np.array([initial-25.]*4+[0.,0.]);Ed=0.;Eb=0.;peak=initial
    for t,z in zip(events,events[1:]):
        for k in range(4):
            if abs(start[k]-t)<1e-12:
                u=c[k];f=c[4+k]
                if shared and u<2:freq[0]=freq[1]=f
                else:freq[u]=f
        code=sum(int(f)<<i for i,f in enumerate(freq));active=np.zeros(4)
        for k in range(4):
            if start[k]<=t+1e-12<end[k]-1e-12:active[c[k]]+=powers[row[0],k]
        b=(active+base[code])/C
        def fun(_,state):return np.r_[A[code]@state[:4]+b,slopes[code]@state[:4],ga@state[:4]]
        sol=solve_ivp(fun,(t,z),y,method='DOP853',rtol=2.3e-14,atol=1e-12,dense_output=True)
        assert sol.success
        peak=max(peak,float(sol.sol(np.linspace(t,z,101))[:4].max()+25))
        y=sol.y[:,-1];Ed+=active.sum()*(z-t);Eb+=base[code].sum()*(z-t)
    return Ed+Eb+y[4]+.12,y[:4]+25,peak

def main(results=None,replay=None):
    cfg=json.loads((ROOT/'protocol.json').read_text());checks=[];pools={}
    for i,shape in enumerate(cfg['work_shapes']):
        for d in cfg['deadlines_us']:
            p,c,q,_=enumerate_pool(cfg,shape,d);ind=independent_pool(cfg,c,d)
            assert np.array_equal(p,ind),(shape,d)
            pools[f'w{i}_d{d}']=(p,c,q)
            checks.append(dict(test='complete finite enumeration',shape=shape,deadline_us=d,count=len(p),status='PASS'))
    p,c,q=pools['w0_d115000'];tables=transitions(cfg,1,1,50)
    inds=[0,len(p)//2,len(p)-1]
    errors=[]
    for shared,initial in [(0,50.),(1,78.)]:
        m=evaluate_pool(p[inds],c,q,shared,initial,50,*tables)
        for j,k in enumerate(inds):
            if not np.isfinite(m[j,0]):continue
            E,T,peak=ivp_reference(p[k],c,q,cfg,1,1,shared,initial)
            err=abs(E-m[j,0]);terr=np.max(abs(T-m[j,13:17]))
            assert err<1e-8 and terr<1e-7
            assert m[j,5]-1e-7<=peak<=m[j,6]+1e-7
            errors.append(dict(energy_error_J=float(err),temperature_error_C=float(terr),peak_gap_C=float(m[j,6]-peak)))
    checks.append(dict(test='independent DOP853 and continuous-peak bound',comparisons=errors,status='PASS'))
    C,G,ga,base,slopes,A=physical(cfg,1,1);C2,G2,ga2,*_=physical(cfg,0,1)
    assert np.max(abs(ga-ga2))<1e-14 and np.allclose(G2,np.diag(ga))
    checks.append(dict(test='remove only lateral heat conductance, preserve ambient paths',status='PASS'))
    if results:
        summary=json.loads((results/'summary.json').read_text());assert summary['max_heat_balance_J']<1e-8
        assert summary['total_unresolved']==0
        checks.append(dict(test='all evaluated trajectories energy/heat conservation and safety resolution',max_balance_J=summary['max_heat_balance_J'],status='PASS'))
        maxdiff=0.
        for key in pools:
            for shared in [0,1]:
                arrays=[np.load(results/f'{key}_t{t}_c{co}l0s{shared}_raw.npz')['metrics'][:,0] for t in [50,78] for co in [0,1]]
                for x in arrays[1:]:maxdiff=max(maxdiff,float(np.nanmax(abs(x-arrays[0]))))
        assert maxdiff<1e-9
        checks.append(dict(test='no temperature-energy effect when leakage feedback disabled',max_difference_J=maxdiff,status='PASS'))
    if replay:
        compared=[]
        for pth in sorted(results.iterdir()):
            other=replay/pth.name
            if pth.name=='summary.json':
                a=json.loads(pth.read_text());b=json.loads(other.read_text());a.pop('wall_seconds');b.pop('wall_seconds');same=a==b
            elif pth.suffix=='.npz':
                with np.load(pth) as a,np.load(other) as b:same=all(np.array_equal(a[k],b[k],equal_nan=True) for k in a.files)
            else:same=pth.read_bytes()==other.read_bytes()
            assert same,pth.name
            compared.append(pth.name)
        checks.append(dict(test='complete deterministic replay',files=len(compared),status='PASS'))
    result=dict(status='PASS',scope='Finite-grid computational verification, not hardware calibration or an outward-rounded interval proof',checks=checks)
    name='validation_results.json' if results else 'validation_preflight.json'
    (ROOT/name).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path);ap.add_argument('--replay',type=Path);x=ap.parse_args();main(x.results,x.replay)
