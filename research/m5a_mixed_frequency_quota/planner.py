"""One arrival-window integer neighbourhood. All final proposals are whole configurations."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
import hashlib

import numpy as np

def digest(code):
    return hashlib.sha256(code).hexdigest()

def groups(values):
    return sorted(set(int(v) for v in values))

def quotas(types, code):
    return sorted((a, int(b >= 10) + 2, int(b % 10), int(n))
                  for (a,b),n in Counter(zip(types, code)).items())

def mappings(method, original, types, ticks):
    """Expand type quotas deterministically, retaining unaffected assignments."""
    base = original >= 10
    yield "original", base
    if method == "C":
        return
    periods = np.zeros(len(types), int) if method=="A" else ticks//5000
    seen={base.tobytes()}
    for half in groups(periods):
        for da,db in ((-1,0),(1,0),(0,-1),(0,1),(-2,0),(2,0),(0,-2),(0,2),
                      (-4,0),(4,0),(0,-4),(0,4),(-1,1),(1,-1),(-2,2),(2,-2)):
            mapped = base.copy()
            for typ,delta in enumerate((da,db)):
                if not delta:
                    continue
                ix = np.flatnonzero((types==typ)&(periods==half))
                q = int(base[ix].sum()) + delta
                if not 0<=q<=len(ix):
                    break
                if method=="A":
                    mapped[ix]=np.diff(np.arange(len(ix)+1)*q//len(ix))>0
                else:
                    eligible=ix[base[ix] == (delta<0)]
                    places=((2*np.arange(abs(delta))+1)*len(eligible))//(2*abs(delta))
                    mapped[eligible[places]]=delta>0
            else:
                key=mapped.tobytes()
                if key not in seen:
                    seen.add(key)
                    yield f"{half}/{da}/{db}",mapped

@dataclass
class Option:
    cost: float
    freq: np.ndarray
    policy: tuple
    fixed: bool

def options(eng, parent, state, ix, dev, window, method, data):
    if not len(ix):
        return [Option(0.,np.empty(0,np.uint8),(0,0,0),True)]
    n=len(ix)
    release,ready,limits,kinds,dt,inc,old_ids = data
    half=int(np.searchsorted(release[ix],window*10000+5000))
    cuts={half}
    if method in "CE":
        cuts.update([1,n-1,*[int(round(n*q/8)) for q in range(1,8)],max(0,half-1),min(n,half+1)])
    choices=[]
    levels=range(10 if dev==0 else 3)
    for k in levels:
        choices.append((0,k,k))
        if method=="A":
            continue
        for l in levels:
            if k==l: continue
            for cut in cuts:
                if 0<cut<n and (cut==half or abs(k-l)<=2):
                    choices.append((cut,k,l))
    arr=np.asarray(choices);cut,k,l=arr.T
    freq=np.where(np.arange(n)<cut[:,None],k[:,None],l[:,None])
    # Earliest legal main-stage finish, with the true already-committed backlog at window entry.
    earlier=old_ids[dev];pos=np.searchsorted(earlier,eng.groups[window][0])
    prev=earlier[pos-1] if pos else None
    start=state['ends'][prev] if prev is not None else 0
    old=parent[prev]%10 if prev is not None else 0
    switch=np.empty_like(freq);switch[:,0]=(freq[:,0]!=old)
    switch[:,1:]=(freq[:,1:]!=freq[:,:-1])
    lengths=dt[dev][kinds[ix],freq]
    work=np.cumsum(lengths+5*switch,axis=1)
    finish=work+np.maximum(start,np.maximum.accumulate(ready[ix]+lengths-work,axis=1))
    valid=np.all(finish<=limits[ix],axis=1)
    # Exit switch estimate includes first unchanged task (or return to zero).
    later=np.searchsorted(earlier,eng.groups[window][-1],side="right")
    nxt=parent[earlier[later]]%10 if later<len(earlier) else 0
    cost=np.sum(inc[dev][kinds[ix],freq],axis=1)+.0015*(switch.sum(axis=1)+(freq[:,-1]!=nxt))
    results=[]
    # Retain fixed cuts explicitly, including in the variable-cut arm.
    for mask in (valid, valid&((cut==0)|(cut==half))):
        which=np.flatnonzero(mask)
        if len(which):
            ranked=which[np.argsort(cost[which],kind="stable")[:4]]
            for j in ranked:
                boundary=(int(ix[cut[j]]) if cut[j]>0 else -1)
                row=Option(float(cost[j]),freq[j].astype(np.uint8),(boundary,int(k[j]),int(l[j])),
                           bool(cut[j]==0 or cut[j]==half))
                if all(x.policy!=row.policy for x in results): results.append(row)
    return results

def generate(eng, code, state, method):
    parent=np.frombuffer(code,dtype=np.uint8)
    release=np.array([r["release_tick"] for r in eng.p.req]);ready=np.array(eng.a)
    limits=np.array(eng.D)-np.array(eng.q);types=np.array(eng.kindidx)
    inc=[np.array([[eng.inc[t,d,k]/eng.scale for k in range(n)] for t in "AB"]) for d,n in ((2,10),(3,3))]
    dt=[np.array([[eng.length[t,d,k] for k in range(n)] for t in "AB"]) for d,n in ((2,10),(3,3))]
    old_ids=[np.flatnonzero((parent>=10)==dev) for dev in (0,1)]
    data=release,ready,limits,types,dt,inc,old_ids
    # Deduplicate window patches before any complete plan is nominated.
    buckets=defaultdict(dict);coverage=[]
    for win,ids in enumerate(eng.groups):
        ids=np.asarray(ids);base=parent[ids];kind=types[ids];old_map=base>=10
        ref=0.
        for dev in (0,1):
            idx=ids[old_map==dev];level=parent[idx]%10
            if not len(idx): continue
            complete=old_ids[dev];a,b=np.searchsorted(complete,[idx[0],idx[-1]])
            before=parent[complete[a-1]]%10 if a else 0
            after=parent[complete[b+1]]%10 if b+1<len(complete) else 0
            ref+=inc[dev][types[idx],level].sum()+.0015*np.count_nonzero(np.diff(np.r_[before,level,after]))
        count=Counter()
        cached={}
        for tag,mapped in mappings(method,base,kind,release[ids]%10000):
            count["mapping_templates"]+=1
            bydev=[]
            for dev in (0,1):
                ix=ids[mapped==dev]
                cachekey=dev,ix.tobytes()
                if cachekey not in cached:
                    cached[cachekey]=options(eng,parent,state,ix,dev,win,method,data)
                bydev.append(cached[cachekey])
            if not all(bydev):
                count["no_device_deadline_feasible_option"]+=1
                continue
            for a,b in product(*bydev):
                count["ranked_option_pairs"]+=1
                patch=np.empty_like(base)
                patch[~mapped]=a.freq;patch[mapped]=10+b.freq
                if np.array_equal(patch,base): continue
                key=patch.tobytes()
                fixed=a.fixed and b.fixed
                family=("same" if tag=="original" else "map")+("_fixed" if fixed else "_var")
                hint=float(a.cost+b.cost-ref)
                rec=(hint,win,key,tag,a.policy,b.policy,family)
                buckets[(win,family)].setdefault(key,rec)
        coverage.append(dict(window=win,**count))
    pools=defaultdict(list)
    for (win,family),unique in buckets.items():
        best=sorted(unique.values())[:3]
        pools[family].extend(best)
        coverage[win]["unique_"+family]=len(unique)
    for pool in pools.values():pool.sort()
    # Reserve seats for different mechanisms, then refill by the common surrogate.
    heads=[v[0] for v in pools.values() if v]
    ranked=sorted(heads)+sorted(set(z for v in pools.values() for z in v)-set(heads))
    proposals=[]
    for hint,win,patch,tag,a,b,family in ranked[:16]:
        ids=eng.groups[win];start,end=ids[0],ids[-1]+1
        result=code[:start]+patch+code[end:]
        x=quotas([eng.types[i] for i in ids],patch)
        load_ticks=[sum(n*eng.length[t,u,k] for t,u,k,n in x if u==dev) for dev in (2,3)]
        assert sum(row[3] for row in x)==len(ids)
        meta=dict(win=win,mapping=tag,policy=[a,b],family=family,hint_delta_J=hint,
                  patch=patch.hex(),quota=x,device_work_ticks=load_ticks)
        proposals.append((result,meta))
    return proposals,coverage

def projections(eng, parent, joint, meta):
    """Keep either the joint mapping or its two device frequency policies on the exact same parent."""
    ids=np.asarray(eng.groups[meta["win"]]);orig=np.frombuffer(parent,np.uint8)
    changed=np.frombuffer(joint,np.uint8)
    map_only=orig.copy();freq_only=orig.copy()
    for dev,policy in enumerate(meta["policy"]):
        old=ids[(orig[ids]>=10)==dev];new=ids[(changed[ids]>=10)==dev]
        cut,lo,hi=policy
        freq_only[old]=10*dev+np.where(old<cut,lo,hi)
        if len(old):
            # Extend the parent's frequency by next original request on that device, holding its tail.
            map_only[new]=orig[old[np.minimum(np.searchsorted(old,new),len(old)-1)]]
        else:map_only[new]=10*dev
    return map_only.tobytes(),freq_only.tobytes()
