"""Full-flow auxiliary constraints. The energy proxy is used only inside this model."""
import bisect, itertools, sys
from samples import B
sys.path.insert(0,str(B))
from base import Access, Problem, bins, clock, unit_lists
from master import cp
from numerics import seeded
from neighborhood import proposals, projection

def selected(p,rows,w,it,stale,seed):
    windows=bins(p)
    ranked=proposals(p,rows)
    local=[r for r in ranked if r[1] in windows[w]]
    pool=[r for r in local if r[0]>0] or local
    ix=it//len(windows)+int(stale>=4)
    primary=pool[(seed-101+ix)%min(len(pool),max(1,2+ix))]
    around={i for j in (w-1,w,w+1) for i in windows.get(j,())}
    near=sorted((r for r in ranked if r[1]!=primary[1] and r[0]>0 and r[1] in around),
                key=lambda r:(abs(rows[r[1]][2]-rows[primary[1]][2])//500,-r[0],r[1]))
    targets=[primary]+near[:7]
    ids={r[1] for r in targets}
    trial=projection(p,rows,{primary[1]:primary[2]})
    path=set(trial["path"]);support=set(trial["support"]);units=unit_lists(rows)
    rivals=set()
    for i in ids:
        seq=units[rows[i][0]];j=seq.index(i)
        rivals.update(seq[max(0,j-2):j+3]);rivals.update(range(3*(i//3),3*(i//3)+3))
    extra=[]
    for i in (path|support|rivals)-ids:
        u,k,s=rows[i]
        saving=p.dur(i,u,k)-min(p.dur(i,a,b) for a,b in p.options[i] if a==u)
        if saving>0:extra.append((i not in path,i not in support,-saving,abs(s-rows[primary[1]][2]),i))
    comps=[v[-1] for v in sorted(extra)[:4]]
    return sorted(ids|set(comps)),dict(primary=primary[1],proposal=primary[2],targets=[r[1] for r in targets],
                compensators=comps,conditional_path=trial["path"],conditional_gap=trial["gap"])

def pairs(p,rows,levels):
    """Latest fixed job per OPP dominates earlier jobs on its own ordered CPU core."""
    units=unit_lists(rows)
    for seq in units:
        for i,j in zip(seq,seq[1:]):yield i,j,True
    fixed=[{},{}];variable=[[],[]]
    for j in sorted(units[0]+units[1],key=lambda i:(rows[i][2],p.finish(i,rows[i]),rows[i][1],i)):
        u=rows[j][0]
        for i in itertools.chain(fixed[1-u].values(),variable[1-u]):
            if len(levels[i])==len(levels[j])==1 and levels[i]==levels[j]:continue
            max_end=rows[i][2]+500+max(p.dur(i,rows[i][0],k) for k in levels[i])
            if max_end+5>rows[j][2]-500:yield i,j,False
        if len(levels[j])==1:fixed[u][levels[j][0]]=j
        else:variable[u].append(j)

class SupportModel:
    def __init__(self,p,rows,ids):
        self.rows=rows;self.p=p;self.m=m=cp.CpModel();self.starts=[];self.levels=[];self.x={}
        self.z=[];self.dev=[];self.ends=[];levels=[];gains=[]
        for i,(u,k,t) in enumerate(rows):
            options=sorted(f for a,f in p.options[i] if a==u) if i in ids else [k]
            levels.append(options)
            r=p.req[i//3];dmin=min(p.dur(i,u,f) for f in options)
            s=m.new_int_var(max(t-500,r["release_tick"]),min(t+500,r["deadline_tick"]-dmin),"s")
            z=m.new_bool_var("z");dev=m.new_int_var(0,500,"dt")
            m.add_abs_equality(dev,s-t);m.add(dev<=500*z)
            self.starts.append(s);self.z.append(z);self.dev.append(dev)
            if len(options)>1:
                xs={f:m.new_bool_var("opp") for f in options};m.add_exactly_one(xs.values());self.x[i]=xs
                rate=lambda f:round(10**6*(p.exact[p.kinds[i],u,f][2]-p.exact[p.kinds[i],u,0][0])*p.dur(i,u,f)/10000)
                gains.extend((rate(k)-rate(f))*v for f,v in xs.items())
                freq=m.new_int_var(min(options),max(options),"f");m.add(freq==sum(f*v for f,v in xs.items()))
                end=s+sum(p.dur(i,u,f)*v for f,v in xs.items());changed=1-xs[k]
                m.add(z>=changed);m.add(z<=changed+dev)
                for f,v in xs.items():
                    if f:m.add(s>=5).only_enforce_if(v);m.add(end<=p.horizon-5).only_enforce_if(v)
            else:
                freq=k;end=s+p.dur(i,u,k);m.add(z<=dev)
                if k:m.add(s>=5);m.add(end<=p.horizon-5)
            m.add(end<=r["deadline_tick"])
            self.levels.append(freq);self.ends.append(end)
            if i%3:m.add(self.ends[i-1]<=s)
        for i,j,same_unit in pairs(p,rows,levels):
            a,b=self.levels[i],self.levels[j]
            if same_unit:m.add(self.ends[i]<=self.starts[j])
            if isinstance(a,int) and isinstance(b,int):
                if a!=b:m.add(self.ends[i]+5<=self.starts[j])
            else:
                diff=m.new_bool_var("different");m.add(a!=b).only_enforce_if(diff);m.add(a==b).only_enforce_if(~diff)
                m.add(self.ends[i]+5<=self.starts[j]).only_enforce_if(diff)
        m.add(sum(self.z)<=24)
        self.gain=sum(gains)
        # A one-microjoule improvement dominates every possible tie-break difference.
        m.maximize(self.gain*300025-sum(self.z)*12001-sum(self.dev))
        assert not m.validate()

    def hint(self,rows):
        m=self.m;m.clear_hints()
        for i,((u,k,t),(_,old,ot)) in enumerate(zip(rows,self.rows)):
            m.add_hint(self.starts[i],t);m.add_hint(self.z[i],int(k!=old or t!=ot));m.add_hint(self.dev[i],abs(t-ot))
            if i in self.x:
                m.add_hint(self.levels[i],k)
                for f,x in self.x[i].items():m.add_hint(x,int(k==f))

    def decode(self,solver):
        return [(u,(solver.value(self.levels[i]) if i in self.x else k),solver.value(self.starts[i]))
                for i,(u,k,t) in enumerate(self.rows)]

def warm_candidate(p,rows,ids,primary):
    # Feasible primal hints only. The model retains all frequency options and all starts.
    options=[]
    for i in ids:
        u,k,_=rows[i]
        for a,f in p.options[i]:
            if a!=u or f==k:continue
            gain=p.proposal_cost[p.kinds[i],u,k]-p.proposal_cost[p.kinds[i],u,f]
            if gain>0:options.append((-gain,i!=primary,i,f))
    best=rows;hints={}
    for neg,_,i,f in sorted(options)[:10]:
        if i in hints:continue
        edits={**hints,i:(rows[i][0],f)}
        trial=projection(p,rows,edits)
        if not trial["feasible"] or len(trial["support"])>24:continue
        hints=edits;ts=dict(trial["placements"])
        best=[(*hints.get(j,r[:2]),ts.get(j,r[2])) for j,r in enumerate(rows)]
    return best

def solutions(p,rows,ids,primary,seed,until,log):
    started=clock();model=SupportModel(p,rows,ids)
    model.hint(warm_candidate(p,rows,ids,primary))
    log.update(tasks=len(rows),z_count=len(model.z),vars=len(model.m.proto.variables),
               constraints=len(model.m.proto.constraints),setup_s=clock()-started,solves=[])
    for limit in (4.5,2.5):
        remaining=min(limit,until-clock())
        if remaining<.15:
            log["solves"].append(dict(status="TIME_LIMIT",reason="construction or preceding work used allowance"));break
        sl=seeded(remaining,seed)
        status=sl.solve(model.m);label=sl.status_name(status)
        if status==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
        out=dict(status="TIME_LIMIT" if status==cp.UNKNOWN else label,raw_status=label,wall_s=sl.wall_time)
        log["solves"].append(out)
        if status not in (cp.FEASIBLE,cp.OPTIMAL):break
        plan=model.decode(sl);changed=[i for i in ids if plan[i][:2]!=rows[i][:2]]
        support=[i for i,r in enumerate(plan) if r!=rows[i]]
        assert support==[i for i,z in enumerate(model.z) if sl.value(z)] and len(support)<=24
        gain=sl.value(model.gain);out.update(proxy_gain_uJ=gain,support=support,changed=changed)
        yield plan,changed,support,gain
        model.m.add(sum(model.x[i][plan[i][1]] for i in model.x)<=len(model.x)-1)
        model.m.clear_hints()
