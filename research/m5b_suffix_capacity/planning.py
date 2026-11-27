"""M5-a permissions and ranking with the suffix test inserted before device truncation."""
import gzip
import hashlib
import json
from collections import Counter,defaultdict
from itertools import product
from pathlib import Path
import numpy as np

from planner import Option, mappings, quotas
from suffix import Boundary

def hashcode(c):return hashlib.sha256(c).hexdigest()
def bits(mask):return np.packbits(mask,bitorder="little").tobytes().hex()

def choices(n,half,dev,method):
    if n==0:return [(0,0,0)]
    cuts={half}
    if method in ("C","E"):
        cuts.update([1,n-1,*[int(round(n*q/8)) for q in range(1,8)],max(0,half-1),min(n,half+1)])
    rows=[];levels=range(3 if dev else 10)
    for k in levels:
        rows.append((0,k,k))
        if method!="A":
            for l in levels:
                if l==k:continue
                for cut in cuts:
                    if 0<cut<n and (cut==half or abs(k-l)<=2):rows.append((cut,k,l))
    return rows

def domain(bound,ix,dev,win,method,release,inc):
    start,old,cap,target,_=bound.limits(dev,win)
    n=len(ix);half=int(np.searchsorted(release[ix],win*10000+5000))
    recipe=choices(n,half,dev,method);cut,k,l=np.array(recipe).T
    t=bound.t
    if n:
        freq=np.where(np.arange(n)<cut[:,None],k[:,None],l[:,None])
        switch=np.empty_like(freq);switch[:,0]=freq[:,0]!=old;switch[:,1:]=freq[:,1:]!=freq[:,:-1]
        lengths=t.lengths[ix,10*dev+freq]
        work=np.cumsum(lengths+5*switch,axis=1)
        finish=work+np.maximum(start,np.maximum.accumulate(t.ready[ix]+lengths-work,axis=1))
        own=np.all(finish<=t.limits[ix],axis=1)
        suffix=finish[:,-1]<=cap-5*(freq[:,-1]!=target)
        cost=inc[ix,10*dev+freq].sum(axis=1)+.0015*(switch.sum(axis=1)+(freq[:,-1]!=target))
    else:
        freq=np.empty((1,0),np.uint8);own=np.array([True])
        suffix=np.array([start<=cap-5*(old!=target)])
        cost=np.array([0.])  # frozen empty-window ranking convention
    valid=own & suffix;keep=[]
    for mask in (valid,valid&((cut==0)|(cut==half))):
        which=np.flatnonzero(mask)
        for j in which[np.argsort(cost[which],kind="stable")[:4]]:
            if int(j) not in keep:keep.append(int(j))
    opts=[]
    for j in keep:
        boundary=int(ix[cut[j]]) if cut[j] else -1
        opts.append(Option(float(cost[j]),freq[j].astype(np.uint8),(boundary,int(k[j]),int(l[j])),bool(cut[j]==0 or cut[j]==half)))
    log=dict(ids=ix.tolist(),half_count=half,raw=len(recipe),own=int(own.sum()),suffix=int(valid.sum()),top=len(keep),
             own_bits=bits(own),suffix_bits=bits(suffix),keep=keep)
    return opts,log

def watch_device(record,series,dev,method):
    if not series:target=(0,0,0)
    else:
        cuts=[i for i in range(1,len(series)) if series[i]!=series[i-1]]
        if len(cuts)>1:return "not_generated"
        target=(cuts[0] if cuts else 0,series[0],series[-1])
    rec=choices(len(series),record["half_count"],dev,method)
    if target not in rec:return "not_generated"
    j=rec.index(target)
    for field,tag in (("own_bits","local_deadline"),("suffix_bits","suffix_deadline")):
        if not (bytes.fromhex(record[field])[j//8]>>(j%8))&1:return tag
    return "paired" if j in record["keep"] else "device_top4"

def generate(eng,code,state,method,timing,ledger_path,watch=None):
    mode="E" if method=="R" else method
    watch={} if watch is None else watch
    bound=Boundary(eng,code,state,timing);parent=bound.parent
    release=np.array([r["release_tick"] for r in eng.p.req]);kinds=np.array(eng.kindidx)
    inc=np.array([[eng.inc[t,2+int(k>=10),k%10]/eng.scale for k in range(13)] for t in "AB"])[kinds]
    buckets=defaultdict(dict);pools=defaultdict(list);stats=[];stages={};bywin=defaultdict(list)
    for key,(win,patch) in watch.items():
        bywin[win].append((key,np.frombuffer(patch,np.uint8)));stages[key]="not_generated"
    def emit(row):
        log.write(json.dumps(row,separators=(",",":"))+"\n")
    with gzip.open(ledger_path,"wt",compresslevel=1,encoding="utf8",newline="\n") as log:
        for win,group in enumerate(eng.groups):
            ids=np.array(group);base=parent[ids];oldmap=base>=10;ref=0.
            for dev in range(2):
                idx=ids[oldmap==dev]
                if not len(idx):continue
                _,old,_,nxt,_=bound.limits(dev,win);levels=parent[idx]%10
                ref+=inc[idx,parent[idx]].sum()+.0015*np.count_nonzero(np.diff(np.r_[old,levels,nxt]))
            count=Counter();cache={}
            for tag,mapped in mappings(mode,base,kinds[ids],release[ids]%10000):
                count["mappings"]+=1;options=[];records=[];refs=[]
                for dev in range(2):
                    ix=ids[mapped==dev];key=(dev,ix.tobytes())
                    if key not in cache:
                        opts,record=domain(bound,ix,dev,win,mode,release,inc)
                        label=len(cache);cache[key]=(opts,record,label)
                        for k in ("raw","own","suffix","top"):count["device_"+k]+=record[k]
                        emit(dict(stage="device",window=win,dev=dev,id=label,**record))
                    opts,record,label=cache[key];options.append(opts);records.append(record);refs.append(label)
                emit(dict(stage="mapping",window=win,tag=tag,devices=refs))
                for ident,desired in bywin[win]:
                    if np.array_equal(desired>=10,mapped):
                        checks=[watch_device(records[j],(desired[mapped==j]%10).tolist(),j,mode) for j in range(2)]
                        order=["not_generated","local_deadline","suffix_deadline","device_top4","paired"]
                        stages[ident]=min(checks,key=order.index)
                for a,b in product(*options):
                    count["paired"]+=1
                    patch=np.empty_like(base);patch[~mapped]=a.freq;patch[mapped]=10+b.freq
                    if np.array_equal(patch,base):continue
                    key=patch.tobytes()
                    family=("same" if tag=="original" else "map")+("_fixed" if a.fixed and b.fixed else "_var")
                    rec=(float(a.cost+b.cost-ref),win,key,tag,a.policy,b.policy,family)
                    buckets[(win,family)].setdefault(key,rec)
            stats.append(count)
        for (win,family),unique in buckets.items():
            count=stats[win];count["unique_window_family"]+=len(unique);picked=[]
            ids=eng.groups[win];lo,hi=ids[0],ids[-1]+1
            for rank,row in enumerate(sorted(unique.values())):
                if len(picked)==3:break
                if method=="R":
                    cfg=code[:lo]+row[2]+code[hi:];ok,i,over=timing.check(cfg)
                    count["prefilter_tested"]+=1;count["prefilter_pass"]+=int(ok)
                    emit(dict(stage="prefilter",window=win,family=family,rank=rank+1,patch=row[2].hex(),
                              ok=bool(ok),first_miss=int(i),over_ticks=int(over)))
                    if not ok:
                        for ident,p in bywin[win]:
                            if p.tobytes()==row[2]:stages[ident]="full_prescreen_fail"
                        continue
                    count["refill_after_rank3"]+=int(rank>=3)
                picked.append(row)
            pools[family].extend(picked);count["window_top3"]+=len(picked)
            emit(dict(stage="window",window=win,family=family,unique=len(unique),selected=[r[2].hex() for r in picked]))
            for ident,target in bywin[win]:
                p=target.tobytes()
                if p in unique and stages[ident]=="paired":
                    stages[ident]="global_top16" if p in [r[2] for r in picked] else "window_top3"
    for pool in pools.values():pool.sort()
    heads=[v[0] for v in pools.values() if v];headset=set(heads)
    ranked=sorted(heads)+sorted(set(r for v in pools.values() for r in v)-headset)
    proposals=[]
    for hint,win,patch,tag,a,b,family in ranked[:16]:
        ids=eng.groups[win];cfg=code[:ids[0]]+patch+code[ids[-1]+1:]
        for ident,target in bywin[win]:
            if patch==target.tobytes():stages[ident]="nominated"
        meta=dict(win=win,mapping=tag,policy=[a,b],family=family,hint_delta_J=hint,patch=patch.hex(),
                  quota=quotas([eng.types[i] for i in ids],patch))
        proposals.append((cfg,meta));stats[win]["nominated"]+=1
    return proposals,[dict(window=i,**v) for i,v in enumerate(stats)],stages
