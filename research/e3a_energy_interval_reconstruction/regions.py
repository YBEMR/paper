"""Rank actual full-horizon accelerator/CPU traces and retain reproducible request neighborhoods."""
def windows(p,plan):
    from model import transitions,DOM
    rows,low=plan
    units,sw,_=transitions(p,rows,low)
    gaps=[];high=[]
    for u,busy in enumerate(units):
        changes=[(s,e,'switch',k) for s,e,d,old,k in sw if d==DOM[u]]
        spans=sorted(changes+[(s,e,'busy',k) for s,e,k,i in busy])
        last=freq=0
        for s,e,kind,k in spans+[(p.horizon,p.horizon,'end',0)]:
            if s>last:
                gaps.append((last,s))
                if freq: high.append((last,s))
            last=e;freq=k
    mains=[(r[2],p.finish(i,r),i//3) for i,r in enumerate(rows) if i%3==1]
    scores=[]
    for s in range(0,p.horizon,500):
        e=min(p.horizon,s+1000)
        slack=[p.req[j]['deadline_tick']-p.finish(j*3+2,rows[j*3+2]) for _,z,j in mains if s<=z<e]
        scores.append(dict(start=s,end=e,fragment=sum(a<e and b>s for a,b in gaps),
            high_idle=sum(max(0,min(b,e)-max(a,s)) for a,b in high),
            switches=sum(a<e and b>s for a,b,*_ in sw),minimum_slack_ticks=min(slack,default=None)))
    selected=[]
    for kind in ['fragment','high_idle','switches','minimum_slack_ticks']:
        pool=[x for x in scores if (x[kind] is not None if kind=='minimum_slack_ticks' else x[kind]>0)]
        pool.sort(key=lambda x:((1 if kind=='minimum_slack_ticks' else -1)*x[kind],x['start']))
        picked=[]
        for x in pool:
            if any(x['start']<z['end'] and z['start']<x['end'] for z in picked):continue
            s,e=x['start'],x['end'];mid=(s+e)/2
            near=sorted(mains,key=lambda v:(max(v[0]-mid,mid-v[1],0),v[2]))
            ids=[j for _,_,j in near[:4]]
            selected.append(dict(id=len(selected),kind=kind,start=s,end=e,score=x[kind],requests=ids))
            picked.append(x)
            if len(picked)==2:break
    return scores,selected
