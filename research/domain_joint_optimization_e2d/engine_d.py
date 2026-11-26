"""Same E2-c2 auxiliary program split at the warm-hint boundary for ablation."""
from contextlib import contextmanager
from design_d import use_aux,clock
from cp_worker import Engine as FrozenEngine,LocalDeadline
from bounded import CompactModel,options,graph,propagate,legal_assignment,proxy
from support import selected,warm_candidate,seeded,cp

class Engine(FrozenEngine):
    @contextmanager
    def measured(self,module):
        t=clock();self.note("module_begin",module=module)
        try:yield
        finally:self.note("module_end",module=module,seconds=clock()-t)

    def auxiliary(self):
        with self.measured("hint"):
            ids,hint=self.make_hint()
        if use_aux(self.variant):
            with self.measured("aux_cp"):
                self.solve_compact(ids,hint)

    def make_hint(self):
        p=self.p;rows=self.base[0]
        ids,sel=selected(p,rows,self.window,self.it,self.stale,self.seed)
        self.note("selection",ids=ids,selection=sel)
        hint=warm_candidate(p,rows,ids,sel["primary"])
        cfg=[i for i,r in enumerate(hint) if r[:2]!=rows[i][:2]]
        st=[i for i,r in enumerate(hint) if r!=rows[i]]
        self.note("hint",edits=[(i,hint[i]) for i in st],config=cfg,gain=proxy(p,rows,hint))
        if cfg:self.assignment(hint,"hint",ids,True)
        return ids,hint

    def solve_compact(self,ids,hint):
        p=self.p;rows=self.base[0]
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
        module="compact_core" if grant else "ordinary_full" if self.it%4==3 else "fallback"
        with self.measured(module):
            super().core(grant)
