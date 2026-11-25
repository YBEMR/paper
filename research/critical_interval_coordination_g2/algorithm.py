"""Common automatic construction, full FIFO and matched local searches, and shared E2-a refinement."""
import gzip,random
from time import perf_counter
from assets import ROOT,G1,read,write,record,assess,assemble,idle_plan,Layout,Q,g1io
from fifo import Compact
from feedback import targets,neighborhood
from reference_objective import Core
from master import solver,cp

def summary(c):
    m=c["metrics"]
    return dict(plan=c["plan"],status=m["status"],J=m["E_J"],bounds=m["E_bounds"],activity_J=m["activity_J"],
                residency_J=m["base_J"],switch_J=m["switch_J"],temperature_J=m["temperature_J"],
                peak_upper_C=max(m["peak_hi"]),deadline_slack_ms=m["min_deadline_slack_ms"])

def load_at(path,h):
    obj=__import__("json").loads(gzip.decompress((path/"plans"/(h+".json.gz")).read_bytes()))
    return list(map(tuple,obj["rows"])),frozenset(map(tuple,obj["low"]))

def automatic(p,m,end,folder):
    best=None;attempts=[]
    now=perf_counter()
    legacy,depth=m.f.search(1024,True,now+.35*max(0,end-now-2))
    row=dict(algorithm="G1 automatic",width=1024,priced=True,depth=depth)
    if legacy is not None:
        _,c=assess(p,legacy);row.update(summary(c))
        if perf_counter()<=end and c["metrics"]["status"]=="SAFE":best=summary(c)
    attempts.append(row)
    for width,priced in ((1,False),(32,True),(128,True),(256,False),(512,True)):
        if perf_counter()>=end-2:break
        cfg,depth=m.construct(width,end-2,priced)
        row=dict(width=width,priced=priced,depth=depth)
        if cfg is not None:
            plan=idle_plan(p,assemble(p,cfg));_,c=assess(p,plan)
            row.update(summary(c))
            if perf_counter()<=end and c["metrics"]["status"]=="SAFE" and (best is None or c["metrics"]["E_bounds"][1]<best["bounds"][0]):
                best=summary(c)
        attempts.append(row)
    write(folder/"construction.json",attempts)
    return best

def refine(p,plan,seed,turn,end):
    # Shared E2-a full-permission local timing solve. Four whole requests span pre, main and post.
    rng=random.Random(seed+7919*turn)
    center=rng.randrange(len(p.req));near=sorted(range(len(p.req)),key=lambda j:(abs(j-center),j))[:4]
    ids=sorted(3*j+k for j in near for k in range(3))
    region={"prior":{},"envelopes":[]}
    model=Core(p,plan,ids,3,region=region)
    left=end-perf_counter()
    if left<.25:return [],dict(status="BUILD_BUDGET",ids=ids)
    sl=solver(min(left-.1,24));sl.parameters.random_seed=seed;sl.parameters.max_presolve_iterations=2
    found=[]
    class Callback(cp.CpSolverSolutionCallback):
        def on_solution_callback(self):
            item=(model.plan(self),model.switches(self),self.value(model.total))
            if len(found)<3:found.append(item)
            else:found[-1]=item
    status=sl.solve(model.m,Callback())
    if status==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
    return found,dict(status=sl.status_name(status),ids=ids,branches=sl.num_branches)

def run(p,m,plan,initial,method,seed,folder,start,end,budget,charged,smoke=False):
    best=initial;ordinary_seed=seed;phase_end=end-.20*budget
    turn=0;before_post=None
    def stamp():return charged+perf_counter()-start
    def evaluate(candidate,until,sw=None):
        nonlocal best,plan
        h,c=assess(p,candidate,expected_switches=sw);res=summary(c)
        res["elapsed_s"]=stamp();res["in_time"]=perf_counter()<=until
        res["accepted"]=res["in_time"] and res["status"]=="SAFE" and res["bounds"][1]<best["bounds"][0]
        if res["accepted"]:best=summary(c);plan=candidate
        return res
    def update(phase):
        write(folder/"progress.json",dict(phase=phase,turn=turn,best=best,elapsed_s=stamp()))
    update("initial")
    import math
    rounds=max(1,math.ceil((phase_end-perf_counter())/30))
    while perf_counter()<phase_end-1.2 and turn<rounds:
        tick=perf_counter();limit=min(phase_end,tick+29.6)
        if limit-tick<1:break
        seed_cfg=[row[:2] for row in plan[0][1::3]]
        before=best
        if method=="Compact":
            ids=set(range(m.n));hint=seed_cfg;trace=[];target=();kind="full"
        else:
            groups=targets(m,seed_cfg,seed)
            active=[j for j,v in enumerate(groups) if v]
            if not active:break
            which=active[turn%len(active)];opts=groups[which];kind=("single","group1","group4","group8")[which]
            target=opts[(turn//len(active))%len(opts)]
            size=min(m.n,(12,24,32)[turn%3])
            ids,hint,trace=neighborhood(m,seed_cfg,target,method,size,min(tick+5,limit-1))
        pool=[]
        def keep(cfg,cost):
            if len(pool)<4:pool.append((cfg,cost))
            else:pool[-1]=(cfg,cost)
        res=m.search(seed_cfg,ids,hint,limit-(2 if m.n<=160 else 4),turn+seed,keep)
        judged=[]
        for cfg,cost in reversed(pool):
            if perf_counter()>=limit-(.2 if m.n<=160 else 1):break
            item=evaluate(idle_plan(p,assemble(p,cfg)),limit);judged.append(item)
        delta=[[i,a,b[:2]] for i,(a,b) in enumerate(zip(seed_cfg,plan[0][1::3])) if a!=b[:2]]
        record(folder/"rounds.jsonl",dict(turn=turn,phase="configuration",target_type=kind,target=target,scope=sorted(ids),
               feedback=trace,before=before,after=best,real_changes=delta,solver=res,candidates=judged,
               pool=len(pool),elapsed_s=stamp(),round_s=perf_counter()-tick))
        turn+=1;update("configuration")
        if smoke or (method=="Compact" and res["status"]=="EXACT_REFERENCE"):break
        if perf_counter()-tick<.05 and not pool and turn>500:break
    before_post=best
    npost=0
    post_end=min(end,perf_counter()+.20*budget)
    while perf_counter()<post_end-2 and npost<math.ceil(.20*budget/30):
        tick=perf_counter();limit=min(post_end,tick+29.6)
        before=best
        found,stats=refine(p,plan,ordinary_seed,npost,limit-(2 if m.n<=160 else 4))
        judged=[]
        for cand,sw,pj in reversed(found):
            if perf_counter()>=limit-(.2 if m.n<=160 else 1):break
            from reference_objective import error_bound
            assert abs(sum(Layout(p,cand[0]).components(cand[1]).values())-Q(pj,10**12))<=error_bound(p)
            judged.append(evaluate(cand,limit,sw))
        record(folder/"rounds.jsonl",dict(turn=npost,phase="timing",solver=stats,before=before,after=best,
                                        candidates=judged,elapsed_s=stamp(),round_s=perf_counter()-tick))
        npost+=1;update("timing")
        if smoke:break
    return dict(initial=initial,configuration=before_post,final=best,configuration_rounds=turn,post_rounds=npost,
                elapsed_charged_s=stamp())
