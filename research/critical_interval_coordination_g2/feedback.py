"""Target generator and the two compensation rules; the joint solver receives no forced move."""
from time import perf_counter

def targets(m,base,seed):
    import random
    rng=random.Random(seed)
    all_targets=[[],[],[],[]]
    for i,old in enumerate(base):
        for op in m.ops:
            if m.busy[i][op]<m.busy[i][old]:
                all_targets[0].append(((i,op),))
    for device in (2,3):
        ids=[i for i,op in enumerate(base) if op[0]==device]
        for ix in range(len(ids)):
            for group,n in enumerate((1,4,8),1):
                block=ids[ix:ix+n]
                if len(block)!=n or any(base[i][1]==0 for i in block):continue
                all_targets[group].append(tuple((i,(device,base[i][1]-1)) for i in block))
    for part in all_targets:
        rng.shuffle(part)
        part.sort(key=lambda a:sum(m.busy[i][op]-m.busy[i][base[i]] for i,op in a))
    return all_targets

def virtual(m,cfg):
    finish=[0,0];freq=[0,0];last=[None,None]
    events=[];parents=[];spans=[]
    for i,(u,k) in enumerate(cfg):
        a=u-2;switch=5*(freq[a]!=k)
        forced=finish[a]+switch
        st=max(m.f.pre[i],forced);e=st+m.dt[i][(u,k)]
        parents.append(last[a] if last[a] is not None and forced>=m.f.pre[i] else None)
        spans.append((st,e,switch));events.append((e,i))
        finish[a]=e;freq[a]=k;last[a]=i
    posts=[];late=[];tail=0;blocker=None
    for e,i in sorted(events):
        if e>=tail:blocker=i
        tail=max(tail,e)+m.q[i]
        if tail>m.d[i]:late.append((tail-m.d[i],i,blocker))
    return sum(v for v,_,_ in late),late,parents,spans

def ordinary(m,base,ids):
    anchors=[(m.f.pre[i],base[i][0]) for i in ids]
    return sorted((i for i in range(m.n) if i not in ids),
        key=lambda i:(min(abs(m.f.pre[i]-t)+40*(base[i][0]!=u) for t,u in anchors),i))

def neighborhood(m,base,target,method,size,until):
    ids={i for i,_ in target};ordinary_order=ordinary(m,base,ids)
    hints=list(base)
    for i,op in target:hints[i]=op
    cfg=hints.copy();trace=[]
    if method=="Proposed":
        while len(ids)<size and perf_counter()<until:
            total,late,parents,spans=virtual(m,cfg)
            if not late:break
            missing,victim,b=max(late,key=lambda row:(row[0],-row[1]))
            chain=[];j=b
            while j is not None:chain.append(j);j=parents[j]
            chain.reverse();best=None
            log=dict(victim=victim,post_blocking_main=b,deficit_ticks=missing,total_violation=total,
                     interval=[spans[chain[0]][0]-spans[chain[0]][2],spans[b][1]],
                     chain=[[j,*spans[j]] for j in chain])
            for j in reversed(chain):
                if j in ids:continue
                old=cfg[j];u=old[0]
                for op in m.ops:
                    if op==old:continue
                    if perf_counter()>=until:break
                    cfg[j]=op;trial=virtual(m,cfg);cfg[j]=old
                    dt=m.dt[j][old]-m.dt[j][op]
                    release=m.dt[j][old] if op[0]!=u else dt
                    actual=spans[b][1]-trial[3][b][1]
                    if trial[0]>total or (trial[0]==total and max(actual,release)<=0):continue
                    rank=(trial[0],-actual,-release,m.busy[j][op]-m.busy[j][old],j,op)
                    if best is None or rank<best[0]:best=(rank,j,op,dt,release,actual)
                if perf_counter()>=until:break
            if best is None:
                log["selected"]=None;trace.append(log);break
            rank,j,op,dt,release,actual=best;old=cfg[j]
            log.update(selected=j,old=old,virtual_op=op,dt_ticks=dt,release_ticks=release,
                       destination_load_ticks=m.dt[j][op] if op[0]!=old[0] else 0,
                       blocker_advance_ticks=actual,after_violation=rank[0],
                       busy_delta_J=(m.busy[j][op]-m.busy[j][old])/m.f.scale)
            trace.append(log);cfg[j]=op;ids.add(j)
    for j in ordinary_order:
        if len(ids)>=size:break
        ids.add(j)
    return ids,hints,trace
