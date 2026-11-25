"""Persistent, private numerical worker. Pipe messages are emitted per certificate."""
from settings import clock
import c1r_assets
from bounded import CompactModel, options, graph, propagate, legal_assignment, proxy
from support import selected, warm_candidate, seeded, cp
from base import Problem, Access, Core, Layout, bins, evaluate, key, dynamic_region, transitions
from compact import permissions
from numerics import cp_candidates, rights_check
from neighborhood import select
from verify_core import check

class LocalDeadline(Exception):
    pass

class Engine:
    def __init__(self):
        self.p=Problem("D3")
        self.windows=bins(self.p)
        self.memo={}

    def execute(self,send,kind,job):
        self.send=send
        self.base,self.metric,self.src,self.method,self.seed,self.it,self.stale,self.end,grant=job
        assert key(self.p,self.base)==self.src and self.metric["status"]=="SAFE"
        self.memo[self.src]=self.metric
        self.window=(self.it%len(self.windows)+self.it//len(self.windows)+self.seed-101)%len(self.windows)
        self.note("start",kind=kind,source=self.src,window=self.window,iteration=self.it)
        if kind=="auxiliary":self.auxiliary()
        else:self.core(grant)

    def note(self,event,**data):
        self.send(("note",dict(event=event,at=clock(),**data)))

    def check_time(self,margin=0):
        if clock()>=self.end-margin:raise LocalDeadline

    def offer(self,plan,stage,access,region,cpdata=None):
        self.check_time(.06)
        p=self.p;ident=key(p,plan)
        self.note("candidate",sha=ident,stage=stage)
        delta=rights_check(p,self.base,plan,access,region)
        if cpdata is not None: check(p,plan,*cpdata)
        lay=Layout(p,plan[0])
        assert lay.switches(plan[1])==transitions(p,*plan)[1]
        self.check_time(.045)
        cached=ident in self.memo
        if not cached:self.memo[ident]=evaluate(p,plan,cert=True)
        m=self.memo[ident];stamp=clock()
        edits=[(i,plan[0][i]) for i in sorted(set(delta["config"])|set(delta["moved"]))]
        msg=dict(stage=stage,sha=ident,source=self.src,at=stamp,metrics=m,cached=cached,
                 edits=edits,low_add=delta["gap_added"],low_drop=delta["gap_removed"],scenes=delta["scenes"])
        self.send(("cert",msg))

    def assignment(self,rows,tag,ids,grantable):
        cfg=[i for i in ids if rows[i][:2]!=self.base[0][i][:2]]
        st=[i for i,r in enumerate(rows) if r!=self.base[0][i]]
        assert set(cfg)<=set(st) and len(st)<=24 and len(cfg)<=12
        access=Access(set(cfg),set(st),{},set(),set())
        region=dynamic_region(self.p,self.base,st,cfg,1)
        lay=Layout(self.p,rows)
        fixed,free=permissions(lay,region)
        preserve=fixed|{g for g in free if region["prior"].get(lay.flex[g],(False,False))[1]}
        reference=fixed|{g for g in free if lay.gap_delta(g,35)<0}
        for label,low in (("preserve",preserve),("reference",reference)):
            self.offer((rows,frozenset(low)),tag+"_"+label,access,region)
        if grantable and cfg:self.send(("rights",dict(stage=tag,sf=cfg,st=st,at=clock())))

    def auxiliary(self):
        p=self.p;rows=self.base[0]
        ids,sel=selected(p,rows,self.window,self.it,self.stale,self.seed)
        self.note("selection",ids=ids,selection=sel)
        hint=warm_candidate(p,rows,ids,sel["primary"])
        cfg=[i for i,r in enumerate(hint) if r[:2]!=rows[i][:2]]
        st=[i for i,r in enumerate(hint) if r!=rows[i]]
        self.note("hint",edits=[(i,hint[i]) for i in st],config=cfg,gain=proxy(p,rows,hint))
        if cfg:self.assignment(hint,"hint",ids,True)
        self.check_time(.15)
        levels=options(p,rows,ids);edges=graph(p,rows,levels)
        early,late=propagate(p,rows,levels,edges)
        self.check_time(.15)
        model=CompactModel(p,rows,ids,levels,edges,early,late)
        if all(-early[i]<=r[2]-rows[i][2]<=late[i] for i,r in enumerate(hint)) and legal_assignment(p,rows,hint,ids,levels,edges):
            model.hint(hint)
        for n,cap in enumerate((4.5,2.5),1):
            limit=min(cap,self.end-clock()-.65)
            if limit<.12:raise LocalDeadline
            sl=seeded(limit,self.seed);status=sl.solve(model.m)
            self.note("aux_solve",call=n,status=sl.status_name(status),limit=limit,seconds=sl.wall_time)
            if status==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
            if status not in (cp.FEASIBLE,cp.OPTIMAL):break
            rs=model.decode(sl);gain=sl.value(model.gain)
            assert gain==proxy(p,rows,rs) and legal_assignment(p,rows,rs,ids,levels,edges)
            assert [i for i,z in enumerate(model.z) if sl.value(z)]==[i for i,r in enumerate(rs) if r!=rows[i]]
            self.assignment(rs,"cp"+str(n),ids,gain>=0)
            model.m.add(sum(model.x[i][rs[i][1]] for i in model.x)<=len(model.x)-1)
            model.m.clear_hints()

    def core(self,grant):
        p=self.p;current=self.base
        full=self.it%4==3
        if grant:
            mode=1
            acc=Access(set(grant["sf"]),set(grant["st"]),{},set(),set())
            origin="compact_core";fallback=False
        else:
            selector="CP-LNS" if full else "Proposed-NoOrder" if self.method=="Hybrid-Old" else "CP-FO"
            mode,acc,trace=select(p,current[0],self.windows,self.window,self.it,self.stale,self.seed,selector)
            fallback=not full and (self.method=="Hybrid-New" or trace["fallback"])
            origin="ordinary_full" if full else "fallback" if fallback else "core"
            self.note("operator",trace=trace)
        assert mode==(3 if full else 1) and acc.sf<=acc.st and len(acc.st)<=24 and len(acc.sf)<=12
        region=dynamic_region(p,current,acc.st,acc.sf,mode)
        self.note("core_region",source=self.src,region=region["identity"],sf=sorted(acc.sf),st=sorted(acc.st),
                  full=full,mode=mode,origin=origin,fallback=fallback,grant=grant)
        self.check_time(.25)
        core=Core(p,current,sorted(acc.st),mode,region=region,access=acc)
        warm=core.m.clone()
        for v,x in core.assignment(current):warm.add(v==x)
        rem=self.end-clock()
        if rem>.35:
            sl=seeded(min(2,rem-.25),self.seed);status=sl.solve(warm)
            assert status not in (cp.INFEASIBLE,cp.MODEL_INVALID)
            self.note("core_seed",status=sl.status_name(status))
            if status in (cp.OPTIMAL,cp.FEASIBLE):
                assert core.plan(sl)==current
                check(p,current,{k:sl.value(v) for k,v in core.parts.items()},core.switches(sl))
                core.m.clear_hints()
                for j in range(len(core.m.proto.variables)):
                    v=core.m.get_int_var_from_proto_index(j);core.m.add_hint(v,sl.value(v))
        for alt,cap in ((False,7),(True,6)):
            limit=min(cap,self.end-clock()-(1.6 if alt else 2.5))
            if limit<.08:raise LocalDeadline
            sols,log=cp_candidates(core,current,self.seed,limit,alt)
            self.note("core_solve",record=log,candidates=[key(p,z[0]) for z in sols])
            for plan,parts,sw in sols:self.offer(plan,origin,acc,region,(parts,sw))

def service(pipe):
    import traceback
    try:
        eng=Engine()
        pipe.send(("ready",))
        while True:
            cmd=pipe.recv()
            if cmd is None:return
            try:
                eng.execute(pipe.send,*cmd);pipe.send(("done","COMPLETE"))
            except LocalDeadline:pipe.send(("done","TIME_LIMIT"))
    except (EOFError,BrokenPipeError):pass
    except Exception:pipe.send(("error",traceback.format_exc()))
    finally:pipe.close()
