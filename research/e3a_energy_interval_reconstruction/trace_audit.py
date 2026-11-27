"""Descriptive resident OPP exposure and zero-slack physical predecessors, using saved seeds only."""
from shared import *
def main():
    rows=[]
    for case in ('D1','D2','C10'):
        p,(plan,low)=load_native(case)
        from model import transitions,DOM
        units,sw,_=transitions(p,plan,low)
        durs=[];freqs={}
        for d in range(3):
            clock=level=0;parts=[]
            for s,e,_,old,new in (w for w in sw if w[2]==d):
                assert old==level
                if s>clock:parts.append((clock,s,level))
                clock=e;level=new
            if clock<p.horizon:parts.append((clock,p.horizon,level))
            freqs[d]=parts
        preds={}
        for work in units:
            for prev,nxt in zip(work,work[1:]):
                if prev[1]<=nxt[0]:preds[nxt[3]]=prev[3]
        for region in read(RUN/case/'diagnostic/regions.json'):
            a,b=region['start'],region['end']
            levels={d:{k:sum(max(0,min(b,z)-max(a,s)) for s,z,v in parts if v==k)
                       for k in sorted(set(v for _,_,v in parts))} for d,parts in freqs.items()}
            rec=dict(case=case,region=region['id'],class_name=region['kind'],window=[a,b],domain_residency_ticks=levels)
            if region['kind']=='minimum_slack_ticks':
                jobs=[j for j in range(len(p.req)) if a<=p.finish(3*j+1,plan[3*j+1])<b]
                victim=min(jobs,key=lambda j:(p.req[j]['deadline_tick']-p.finish(3*j+2,plan[3*j+2]),j))
                chain=[];todo=[3*victim+2];seen=set()
                while todo:
                    i=todo.pop()
                    if i in seen:continue
                    seen.add(i);u,k,t=plan[i];edges=[]
                    if i%3 and p.finish(i-1,plan[i-1])==t:edges.append(('job_precedence',i-1))
                    if i in preds:
                        v=preds[i];end=p.finish(v,plan[v])
                        if end==t:edges.append(('busy_same_unit',v))
                        elif any(d==DOM[u] and end==s and z==t for s,z,d,_,_ in sw):edges.append(('switch_after_busy',v))
                    chain.append(dict(stage=i,unit=u,start=t,end=p.finish(i,plan[i]),binding=edges))
                    todo.extend(v for _,v in edges)
                rec.update(victim_request=victim,deadline_tick=p.req[victim]['deadline_tick'],binding_chain=chain)
            rows.append(rec)
    put(HERE/'results'/'seed_window_audit.json',rows)
if __name__=='__main__':main()
