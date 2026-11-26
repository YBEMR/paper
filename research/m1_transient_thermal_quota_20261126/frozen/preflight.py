import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):
    os.environ[key]='1'
import sys, math, time, csv, io, json, hashlib, platform
from pathlib import Path
from fractions import Fraction as Q
from itertools import product
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'p1'))
from profiles import CFG, requests
from model import Problem, transitions, event_arrays, independent_events
from heat import evaluate
from time import perf_counter as clock
P1='be641ce06a4f496d2b1f233a09bdfc3776738668'
FORMAL='e8ebada59faa1f9ad3f5ba4638c7b48a596d8c55'
PIN={'model.py':'738809425d68d7de1d0939d3d37596550820e89f','heat.py':'69bef3c1917b874a9ceacf2ecaabfe14addfbd7e','config/p1_frozen.json':'1cde1d8142c6253a0deb4f78dbe6960c7c99fb70','config/gpu_profiles.csv':'c77aa183d451e7d8cd15e1d0510e8f8bc21f6f40','config/cpu_npu_profiles.csv':'a6eeae251d0ecd0107601ab8621c3c54ea753aa3'}
INPUT_PIN={'S32':'0e508561a5b7f0275fd4865da969a06962bf6a73','S80':'999f187af7ef04b3d536fded3362a92f4ffcbeb9','D1':'da20f1af4edad70d7f8a954ccb7fa8c91d444167','D2':'0f74cf2d32297beaef07fc38975551f806cc9689','F1':'571a056eadbc008a60b086f0cbfa4593f1911b77','F2':'01734a5d2ef32a4a97a49b361dfb0741b791fb6e','D3':'7114a567306a30ccf6aee007a68fba1cf43a11d2'}
EXTRA={'S32':[['L','H'],Q(1,5),35,1],'S80':[['L','H'],Q(1,2),35,1],'F1':[list('LMH'),Q(1,2),35,1],'F2':[list('HLH'),Q(1,2),35,1],'R320':[list('LH')*2,1,35,1],'R800':[list('LH')*5,1,35,1],'L640':[list('LH'),4,35,1],'L800':[list('LH'),5,35,1]}
CASES=list(INPUT_PIN)+['R320','R800','L640','L800']
CFG['instances'].update(EXTRA)
PAIRS=list(product(range(10),range(3)))
FIXED={1,4,8,16,32,64}

def sha(b): return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def default(o):
    if isinstance(o,np.generic):return o.item()
    if isinstance(o,np.ndarray):return o.tolist()
    if isinstance(o,Q):return str(o)
    raise TypeError(type(o))
def raw(o):return json.dumps(o,default=default,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
def put(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw(obj)+b'\n')

def audit(out):
    src={}
    for f,h in PIN.items():
        b=(ROOT/'p1'/f).read_bytes();v=blob(b);assert v==h,(f,v,h);src[f]={'blob':v,'sha256':sha(b)}
    ins={}
    for case in CASES:
        r=requests(case);s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=r[0],lineterminator='\n');w.writeheader();w.writerows(r);b=s.getvalue().encode();h=blob(b)
        assert case not in INPUT_PIN or h==INPUT_PIN[case],(case,h,INPUT_PIN.get(case))
        assert all(x['deadline_ms']-x['release_ms']==300 for x in r)
        p=out/'inputs'/(case+'.csv');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        ins[case]={'blob':h,'sha256':sha(b),'count':len(r),'source': 'P1' if case=='D3' else 'formal_frozen' if case in INPUT_PIN else 'derived_P1_rule','cap_multiplier':CFG['instances'][case][3]}
    put(out/'manifest.json',{'P1':P1,'formal_inputs':FORMAL,'sources':src,'inputs':ins,'algorithm_sha256':sha(Path(__file__).read_bytes()),'protocol_sha256':sha((ROOT/'PROTOCOL.md').read_bytes()),'adapter_sha256':sha((ROOT/'p1/profiles.py').read_bytes()),'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'thread_env':{k:os.environ[k] for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')}})
    print('SOURCE_AND_INPUT_HASHES_PASS',len(src),len(ins),flush=True)

class Engine:
    def __init__(self,case,out):
        self.p=p=Problem(case);p.horizon=int(p.horizon);p.boundaries=list(map(int,p.boundaries));self.n=len(p.req);self.out=out;self.case=case
        self.dur=int(CFG['instances'][case][1]*10000);self.groups=[[i for i,r in enumerate(p.req) if r['scene']==j] for j in range(len(CFG['instances'][case][0]))];self.types=[r['kind'] for r in p.req];self.kindidx=[0 if t=='A' else 1 for t in self.types];self.D=[r['deadline_tick'] for r in p.req];self.a=[];self.ps=[];self.q=[];t=0
        for i,r in enumerate(p.req):
            s=max(t,r['release_tick']);t=s+p.dur(3*i,0,0);self.a.append(t);self.ps.append(s);self.q.append(p.dur(3*i+2,1,0))
        self.scale=math.lcm(1000,*[v.denominator for vs in p.exact.values() for v in (vs[0],vs[2])])*10000
        self.sw=int(Q(3,2000)*self.scale);self.rate={};self.inc={};self.length={}
        for t in 'AB':
            for u,k in [(u,k) for u,count in [(2,10),(3,3)] for k in range(count)]:
                stage=t+'.main';b,_,busy,_=p.exact[stage,u,k];lo=p.exact[stage,u,0][0];l=p.profile[stage,u,k][0];self.length[t,u,k]=l
                self.rate[u,k]=int((b-lo)*self.scale/10000);self.inc[t,u,k]=int((busy-lo)*l*self.scale/10000)
        self.common=Q(31,20)*p.horizon/10000
        for i,t in enumerate(self.types):
            for a,u in [('pre',0),('post',1)]:
                b,_,busy,_=p.exact[t+'.'+a,u,0];self.common+=(busy-b)*p.profile[t+'.'+a,u,0][0]/10000
        self.common_int=int(self.common*self.scale);assert Q(self.common_int,self.scale)==self.common
    def gap(self,u,old,k,dt):
        rate=self.rate[u,old];hold=rate*dt+self.sw*(old!=k)
        down=rate*5+self.sw*(1+(k!=0))
        early=old>0 and dt>=5*(1+(k!=0)) and down<hold
        return (down if early else hold),early
    def op(self,i,u,k):return self.length[self.types[i],u,k],self.inc[self.types[i],u,k]
    def replay(self,c):
        f=[0,0];k=[0,0];cost=0;ends=[];starts=[];low=[];p=self.p
        for i,(u,v) in enumerate(c):
            j=u-2;l,e=self.op(i,u,v);s=max(self.a[i],f[j]+5*(k[j]!=v));z=s+l;g,early=self.gap(u,k[j],v,s-f[j]);cost+=g+e
            if early:low.append((u-1,3*i+1))
            f[j]=z;k[j]=v;starts.append(s);ends.append(z)
        if any(f[j]+5*(k[j]!=0)>p.horizon for j in range(2)):return None
        post=0;posts=[0]*len(c);slack=10**10
        for i in sorted(range(len(c)),key=lambda i:(ends[i],i)):
            s=max(post,ends[i]);post=s+self.q[i];slack=min(slack,self.D[i]-post);posts[i]=s
        if slack<0 or post>p.horizon:return None
        tail=0
        for j in range(2):
            g,early=self.gap(j+2,k[j],0,p.horizon-f[j]);tail+=g
            if early:low.append((j+1,-1))
        return dict(f=tuple(f),k=tuple(k),cost=cost,tail=tail,ends=ends,starts=starts,posts=posts,slack=slack,low=low)
    def quota(self,r,j,pair,counts):
        a,b=counts;g,n=pair
        ag,ae=self.length['A',2,g],self.inc['A',2,g];an,ane=self.length['A',3,n],self.inc['A',3,n];bg,be=self.length['B',2,g],self.inc['B',2,g];bn,bne=self.length['B',3,n],self.inc['B',3,n]
        avail=[max(j*self.dur,r['f'][i]+5*(r['k'][i]!=pair[i])) for i in range(2)];best=None
        for x in range(a+1):
            num=avail[0]+(a-x)*ag+b*bg-avail[1]-x*an;den=bg+bn
            for y in (max(0,min(b,num//den)),max(0,min(b,-(-num//den)))):
                z=max(avail[0]+(a-x)*ag+(b-y)*bg,avail[1]+x*an+y*bn);e=(a-x)*ae+x*ane+(b-y)*be+y*bne
                v=(z,e,x,y)
                if best is None or v<best:best=v
        return best[2:]
    def construct(self,mode,width):
        states=[((),dict(f=(0,0),k=(0,0)),[])];trials=0;visited=0;logs=[]
        for j,ids in enumerate(self.groups):
            counts=[sum(self.kindidx[i]==h for i in ids) for h in range(2)];nexts=[]
            for c,r,hist in states:
                for pair in PAIRS:
                    q=self.quota(r,j,pair,counts) if mode=='quota' else None;seen=[0,0];ext=[];f=list(r['f']);k=list(r['k'])
                    for i in ids:
                        if q is not None:
                            h=self.kindidx[i];z=seen[h];seen[h]+=1;u=int((z+1)*q[h]//counts[h]>z*q[h]//counts[h]);v=pair[u]
                        else:
                            choices=[]
                            for u,v in enumerate(pair):
                                l,e=self.op(i,u+2,v);s=max(self.a[i],f[u]+5*(k[u]!=v));choices.append((s+l,e+self.gap(u+2,k[u],v,s-f[u])[0],u,v))
                            _,_,u,v=min(choices)
                        l,_=self.op(i,u+2,v);f[u]=max(self.a[i],f[u]+5*(k[u]!=v))+l;k[u]=v;ext.append((u+2,v))
                    nc=c+tuple(ext);nr=self.replay(nc);trials+=1;visited+=len(nc)
                    if nr is None:continue
                    score=nr['cost']+(nr['tail'] if j==len(self.groups)-1 else 0);nexts.append((score,nc,nr,hist+[[pair,q]]))
            logs.append({'scene':j,'feasible_candidates':len(nexts),'input_states':len(states)})
            if not nexts:return None,{'trials':trials,'request_replays':visited,'failed_scene':j+1,'scenes':logs}
            nexts.sort(key=lambda x:(x[0],x[1]));states=[];seen=set()
            for _,c,r,hist in nexts:
                if c in seen:continue
                seen.add(c);states.append((c,r,hist))
                if len(states)==width:break
        c,r,h=states[0];return (c,r),{'trials':trials,'request_replays':visited,'choices':h,'scenes':logs}
    def build(self,c,r):
        assert len(c)==self.n
        rows=[]
        for i,(u,k) in enumerate(c):rows.extend([(0,0,self.ps[i]),(u,k,r['starts'][i]),(1,0,r['posts'][i])])
        low=frozenset(r['low']);_,sw,_=transitions(self.p,rows,low);ev,ss,_=event_arrays(self.p,rows,low);iev,isw=independent_events(self.p,rows,low)
        assert sw==ss==isw and np.array_equal(ev,iev),(self.case,'event mismatch')
        e35=(r['cost']+r['tail']+self.common_int)/self.scale
        ref=float(np.sum((ev[:,1]-ev[:,0])*(ev[:,2:6].sum(axis=1)+.3))/10000)
        assert abs(e35-ref)<1e-9,(self.case,e35,ref)
        return dict(rows=rows,low=low,ev=ev,e35=e35,ref_exact=str(Q(r['cost']+r['tail']+self.common_int,self.scale)),switches=sw)
    def cert(self,c,r,built=None):
        b=built or self.build(c,r);payload={'case':self.case,'rows':b['rows'],'low':sorted(b['low'])};key=sha(raw(payload));t=clock()
        metrics=evaluate(self.p,(b['rows'],b['low']),cert=True,trace=True);elapsed=clock()-t;trace=np.asarray(metrics.pop('events'));assert np.array_equal(trace[:,:14],b['ev']);assert abs(metrics['E_J']-metrics['temperature_J']-b['e35'])<1e-8
        d={'plan_sha256':key,'metrics':metrics,'E35_J':b['e35'],'E35_exact':b['ref_exact'],'switches':b['switches'],'cert_s':elapsed}
        path=self.out/'evidence'/self.case/key;put(path/'plan.json',payload);put(path/'certificate.json',d);np.savez_compressed(path/'trace.npz',events=trace)
        return d,trace
    def candidates(self,c,r,mode):
        proposed=[];scan=0;eligible=0;p=self.p
        for u in (2,3):
            ids=[i for i,op in enumerate(c) if op[0]==u];L=[0]*len(ids)
            for j in range(len(ids)-1,-1,-1):
                i=ids[j];k=c[i][1];L[j]=min(self.D[i]-self.q[i],p.horizon-5*(k!=0) if j==len(ids)-1 else L[j+1]-self.op(ids[j+1],*c[ids[j+1]])[0]-5*(k!=c[ids[j+1]][1]))
            i=0
            while i<len(ids):
                hi=i+1;k=c[ids[i]][1]
                while hi<len(ids) and c[ids[hi]][1]==k:hi+=1
                if k>0:
                    for lo in range(i,hi):
                        best=None;z=r['ends'][ids[lo-1]] if lo else 0;before=c[ids[lo-1]][1] if lo else 0;newk=k-1;delta=0;own=True
                        for j in range(lo,min(hi,lo+64)):
                            id=ids[j];l,e=self.op(id,u,newk);z=max(self.a[id],z+5*(j==lo and before!=newk))+l;delta+=self.op(id,u,k)[1]-e;own=own and z+self.q[id]<=self.D[id];scan+=1
                            length=j-lo+1
                            if mode=='fixed' and length not in FIXED:continue
                            after=c[ids[j+1]][1] if j+1<len(ids) else 0;latest=L[j+1]-self.op(ids[j+1],*c[ids[j+1]])[0]-5*(newk!=after) if j+1<len(ids) else p.horizon-5*(newk!=0)
                            if not own or z>latest:continue
                            eligible+=1;gain=delta-self.sw*((before!=newk)+(newk!=after)-(before!=k)-(k!=after))
                            if gain>0 and (best is None or gain>best[0]):best=(gain,tuple(ids[lo:j+1]),u,newk)
                        if best:proposed.append(best)
                i=hi
        proposed.sort(key=lambda x:(-x[0],x[1][0],-len(x[1]),x[1]));pool=[];seen=set();chosen=proposed[:8]
        for gain,ids,u,k in chosen:
            nc=list(c)
            for i in ids:nc[i]=(u,k)
            nc=tuple(nc)
            if nc in seen:continue
            seen.add(nc);nr=self.replay(nc)
            if nr is not None:pool.append(dict(c=nc,r=nr,b=self.build(nc,nr),ids=ids,u=u,k=k))
        pool.sort(key=lambda x:(x['r']['cost']+x['r']['tail'],x['ids'][0],x['c']))
        return pool,dict(scan=scan,eligible=eligible,replays=len(chosen),legal=len(pool))
    @staticmethod
    def temp_estimate(ev,trace):
        # Original per-event temperature endpoints, approximate piecewise linear interpolation.
        tt=np.r_[trace[:,0],trace[-1,1]]/10000;temp=np.vstack((trace[:,14:18],trace[-1,18:22]))-35
        pref=np.vstack((np.zeros((1,4)),np.cumsum(np.diff(tt)[:,None]*(temp[:-1]+temp[1:])/2,axis=0)))
        t=np.r_[ev[:,0],ev[-1,1]]/10000;ix=np.clip(np.searchsorted(tt,t,side='right')-1,0,len(tt)-2);h=t-tt[ix];v=pref[ix]+h[:,None]*(temp[ix]+(temp[ix+1]-temp[ix])*(h/(tt[ix+1]-tt[ix]))[:,None]/2)
        return float(np.sum(np.diff(t)[:,None]*ev[:,2:6])+np.sum(np.diff(v,axis=0)*ev[:,6:10])+.3*t[-1])
    def optimize(self,init,group,select):
        c,r,d,tr=init;counts=Counter();history=[];t0=clock();timing=Counter();ncert=1
        for turn in range(3):
            t=clock();pool,work=self.candidates(c,r,group);timing['candidate_s']+=clock()-t;counts.update(work)
            if not pool:history.append({'turn':turn,'stop':'empty_pool',**work});break
            if select=='union':
                t=clock();for_heat=min(pool,key=lambda x:(self.temp_estimate(x['b']['ev'],tr),x['ids'][0],x['c']));timing['thermal_rank_s']+=clock()-t;counts['heat_ranked']+=len(pool);selected=[pool[0]] if for_heat is pool[0] else [pool[0],for_heat]
            else:selected=pool[:int(select)]
            vals=[];candidates=[]
            for x in selected:
                t=clock();v,trace=self.cert(x['c'],x['r'],x['b']);timing['cert_and_archive_s']+=clock()-t;ncert+=1;candidates.append({'ids':list(x['ids']),'new_opp':x['k'],'ref_rank':next(i+1 for i,y in enumerate(pool) if y is x),'plan':v['plan_sha256'],'status':v['metrics']['status'],'E_bounds':v['metrics']['E_bounds']})
                if v['metrics']['status']=='SAFE' and v['metrics']['E_bounds'][1]<d['metrics']['E_bounds'][0]:vals.append((v['metrics']['E_bounds'][1],x,v,trace))
            log={'turn':turn,**work,'pool_size':len(pool),'evaluated':candidates,'before':d['plan_sha256']}
            if not vals:history.append({**log,'stop':'no_strict_improvement'});break
            _,x,d,tr=min(vals,key=lambda z:(z[0],z[2]['plan_sha256']));c=x['c'];r=x['r'];history.append({**log,'accepted':d['plan_sha256'],'group_size':len(x['ids'])})
        return {'status':d['metrics']['status'],'final':d,'ncert_including_initial':ncert,**counts,'optimization_s_including_archive':clock()-t0,'timing':dict(timing),'rounds':history}

def main():
    out=ROOT/'run';assert not out.exists(),'Existing run preserved; no overwrite';out.mkdir();audit(out)
    # Compile the original numerical kernel once and explicitly report the cold/warmup duration.
    eng=Engine('S32',out);cr,info=eng.construct('quota',1);t=clock();d,tr=eng.cert(*cr);cold=clock()-t;put(out/'warmup.json',{'seconds_including_first_kernel_call_and_archive':cold,'plan':d['plan_sha256'],'status':d['metrics']['status']});print('WARMUP',cold,d['metrics']['status'],flush=True)
    all=[]
    for case in CASES:
        t=clock();e=Engine(case,out);model_s=clock()-t;cons={};initial=None
        for name,mode,w in [('EFT1','eft',1),('Q1','quota',1),('Q4','quota',4)]:
            t=clock();cr,info=e.construct(mode,w);construct_s=clock()-t;row={**info,'construct_s':construct_s,'status':'NO_CONSTRUCTION'}
            if cr is not None:
                t=clock();d,tr=e.cert(*cr);row.update(status=d['metrics']['status'],cert_and_archive_s=clock()-t,certificate=d)
                if name=='Q4' and row['status']=='SAFE':initial=(*cr,d,tr)
            cons[name]=row
        arms={}
        if initial:
            for name,group,select in [('Fixed2','fixed','2'),('Adaptive1','adaptive','1'),('Adaptive2','adaptive','2'),('Adaptive3','adaptive','3'),('ThermalUnion','adaptive','union')]:
                arms[name]=e.optimize(initial,group,select)
        result={'case':case,'n':e.n,'model_s':model_s,'construction':cons,'optimization':arms};all.append(result);put(out/'cases'/f'{case}.json',result)
        print(case,'construct',[(k,x['status'],round(x.get('certificate',{}).get('metrics',{}).get('E_J',0),6)) for k,x in cons.items()],'opt',[(k,round(x['final']['metrics']['E_J'],6),x['ncert_including_initial'],x.get('replays',0)) for k,x in arms.items()],flush=True)
    put(out/'summary.json',all)
    print('COMPLETE',len(all),flush=True)
if __name__=='__main__':main()
