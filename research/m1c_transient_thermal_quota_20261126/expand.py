"""Candidate expansion adapted from search_b.py at e4cb520. Keep fixed generators and cross-window replay."""
from itertools import groupby
from time import perf_counter
from common import WINDOW,digest,window_types,load_planes,anchors,grouped_means,capacity,make_filter,synthesize,np


def expand(c,j,states,gen,thermal,counts,rows,deadline=float("inf")):
    screened=gen=="Hs"
    gen="H" if screened else gen
    needT=thermal or gen=="H"
    expired=False
    lo=j*WINDOW
    end=(j+1)*WINDOW
    final=j==c.windows-1
    right=c.p.horizon if final else end
    t,a,b=window_types(c,j)
    nexts={}

    for parent in states:
        for (g,n),actions in groupby(c.candidates(j,parent),key=lambda pair:pair[0][:2]):
            if perf_counter()>=deadline:
                expired=True
                break
            original={tuple(action[2:]):tail for action,tail in actions}
            time=load_planes(c,j,parent,g,n,a,b)
            cache={}
            pilots=[]
            def trial(xy):
                if xy in cache:
                    return cache[xy]
                ext=original.get(xy)
                if ext is None:
                    ext=c.extension(t,a,b,g,n,*xy)
                cfg=parent["config"]+ext
                k=digest(cfg)
                if k in nexts and xy not in pilots:
                    cache[xy]=(cfg,k,None,None,None)
                    return cache[xy]
                fine=500 if gen=="H" and final and xy in pilots else 2500
                l=c.ledger(cfg,lo,right,fine,final,needT)
                counts["fifo"]+=1
                if xy in pilots:
                    counts["calibration_fifo"]+=1
                duration=np.minimum(fine,right-lo-np.arange(len(l[8]))*fine)/WINDOW
                cache[xy]=(cfg,k,l,duration,fine)
                return cache[xy]
            if gen=="O":
                chosen=list(original)
            else:
                center=c.eng.quota(parent,j,(g,n),(a,b))
                pilots,bal=anchors(time,center,a,b)
                observations=[]
                values=[]
                for xy in pilots:
                    _,_,l,durations,fine=trial(xy)
                    values.append(l[1])
                    if gen=="H":
                        obs=l[8]
                        if final:
                            obs=np.vstack((grouped_means(obs[:20],durations[:20],5),obs[20:]))
                        observations.append(obs)
                if gen=="H":
                    steps=np.r_[np.repeat(.25,4),durations[20:]] if final else np.repeat(.25,4)
                    planes=capacity(c,parent["temperature"],pilots,np.array(observations),steps,not final)
                else:
                    planes=np.empty((0,3))
                eco=np.linalg.solve(np.column_stack((np.ones(3),pilots)),values)
                checker=make_filter(c,parent,j,g,n,counts) if screened else None
                chosen=synthesize(time,planes,pilots,bal,eco,a,b,len(original),checker)
                for xy in original:
                    if len(chosen)>=len(original):
                        break
                    if xy not in chosen:
                        chosen.append(xy)
                assert len(chosen)==len(original) and set(pilots)<=set(chosen)
            for xy in chosen:
                action=(g,n,*xy)
                cfg,key,l,duration,fine=trial(xy)
                tag="pilot" if xy in pilots else "legacy" if xy in original else "generated"
                info=[j+1,parent["id"],*action,key,tag,int(xy in original)]
                counts["proposals"]+=1
                counts["outside_old"]+=xy not in original
                if key in nexts:
                    rows.append((*info,"duplicate",None,None,None,None))
                    continue
                assert l is not None
                if not l[0]:
                    rows.append((*info,"timing",l[-1],None,None,None))
                    continue
                energy=l[1]+(c.base*c.p.horizon/WINDOW if final else 0)
                temp=parent["temperature"]
                peak=parent["peak"]
                if needT:
                    means=l[8]
                    if fine==500:
                        means=grouped_means(means,duration,5)
                    qdur=np.minimum(2500,right-lo-2500*np.arange(len(means)))/WINDOW
                    for m,h in zip(means,qdur):
                        temp=c.propagate(temp,m,h)
                        peak=max(peak,max(temp))
                risk=max(time[:,0]+time[:,1:]@xy)
                if thermal:
                    risk=peak if final else max(peak,max(c.propagate(temp,means[:4].mean(axis=0),1)))
                state=dict(config=cfg,id=key,f=l[2],k=l[3],temperature=temp,peak=peak,risk=risk,energy=energy,
                           drain=max(max(l[2]),max(l[6]+c.args[4][:len(cfg)])),action=action,parent=parent["id"],
                           slack=int(l[-1]),history=parent["history"]+[action])
                nexts[key]=state
                rows.append((*info,"valid",l[-1],energy,risk,peak if needT else None))
        if expired:
            break
    return nexts,expired
