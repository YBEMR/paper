"""One replay. The auxiliary process has its own enforceable wall deadline."""
import gzip,json,subprocess,sys,time,traceback
from assets import ROOT,C,read,write
from bounded import CompactModel,options,graph,propagate,legal_assignment,proxy
from support import SupportModel,selected,warm_candidate,seeded,cp
from replay import Replay
from base import Access,Layout,clock,dynamic_region,raw
from compact import permissions

def get_rights(sf,st):
    return Access(set(sf),set(st),{},set(),set())

class TimedReplay(Replay):
    def offer(self,plan,origin,rights,region,cpdata=None):
        t=clock()
        super().offer(plan,origin,rights,region,cpdata)
        self.r.setdefault("offer_s",{}).setdefault(origin,[]).append(clock()-t)
        self.checkpoint()

class Auxiliary(TimedReplay):
    def checkpoint(self):
        self.r["elapsed_s"]=clock()-self.start
        write(self.folder/"aux.json",self.r)

    def certify_assignment(self,rows,tag,cfg,st,gain):
        a=self.r["auxiliary"];rights=get_rights(cfg,st);region=dynamic_region(self.p,self.base,rights.st,rights.sf,1)
        item=dict(tag=tag,Sf=cfg,St=st,region=region["identity"],proxy_gain_uJ=gain,
                  edits=[[i,rows[i]] for i in st],complete=False)
        a["assignments"].append(item);self.checkpoint()
        lay=Layout(self.p,rows);fixed,free=permissions(lay,region)
        inherited=fixed|{k for k in free if region["prior"].get(lay.flex[k],(False,False))[1]}
        optimized=fixed|{k for k in free if lay.gap_delta(k,35)<0}
        for label,low in (("preserve",inherited),("reference",optimized)):
            self.offer((rows,frozenset(low)),tag+"_"+label,rights,region)
        item["complete"]=True
        self.checkpoint()
        return dict(Sf=cfg,St=st)

    def solve_stage(self,which):
        t=clock();deadline=t+11;s=self.s;p=self.p;rows=self.base[0];a=self.r["auxiliary"]
        a.update(start=t,assignments=[],solves=[],hint_rights=None,cp_rights=None)
        self.checkpoint();write(self.folder/"phase.json",dict(begin=t,until=deadline))
        ids,selection=selected(p,rows,s["window"],s["iteration"],s["stale"],s["seed"])
        assert selection["primary"]==s["primary"] and tuple(selection["proposal"])==tuple(s["proposal"])
        a.update(config_candidates=ids,selection=selection,select_s=clock()-t)
        tt=clock();hint=warm_candidate(p,rows,ids,s["primary"])
        cfg=[i for i,r in enumerate(hint) if r[:2]!=rows[i][:2]]
        st=[i for i,r in enumerate(hint) if r!=rows[i]]
        gain=proxy(p,rows,hint)
        a.update(hint_gen_s=clock()-tt,hint_cfg=cfg,hint_support=st,hint_gain_uJ=gain)
        assert set(cfg)<=set(ids) and len(st)<=24
        (self.folder/"hint.json.gz").write_bytes(gzip.compress(raw(dict(rows=hint,z=[int(i in st) for i in range(len(rows))],config=cfg,proxy_gain_uJ=gain)),mtime=0))
        if cfg:a["hint_rights"]=self.certify_assignment(hint,"hint",cfg,st,gain)
        self.checkpoint();tt=clock()
        levels=options(p,rows,ids);edges=graph(p,rows,levels)
        a["graph_s"]=clock()-tt;pt=clock()
        if which=="Compact-Hint":
            early,late=propagate(p,rows,levels,edges);a["propagate_s"]=clock()-pt
            mt=clock();model=CompactModel(p,rows,ids,levels,edges,early,late)
            retained=model.retained;fits=all(-early[i]<=r[2]-rows[i][2]<=late[i] for i,r in enumerate(hint))
            a["envelopes"]=[[i,early[i],late[i]] for i in retained]
        else:
            a["propagate_s"]=0;mt=clock();model=SupportModel(p,rows,ids);retained=list(range(len(rows)));fits=True
        a.update(build_s=clock()-mt,vars=len(model.m.proto.variables),constraints=len(model.m.proto.constraints),
                 retained=len(retained),tasks=len(rows),hint_inside_envelope=fits)
        fits=fits and legal_assignment(p,rows,hint,ids,levels,edges)
        if fits:model.hint(hint)
        a["hint_injected"]=fits;self.checkpoint()
        for ix,cap in enumerate((4.5,2.5),1):
            remaining=min(cap,deadline-clock()-.65)
            if remaining<.12:
                a["solves"].append(dict(call=ix,status="TIME_LIMIT",reason="auxiliary deadline"));break
            solver=seeded(remaining,s["seed"]);result=solver.solve(model.m);status=solver.status_name(result)
            log=dict(call=ix,limit_s=remaining,wall_s=solver.wall_time,seed=s["seed"],raw_status=status,
                     status="TIME_LIMIT" if result==cp.UNKNOWN else status)
            a["solves"].append(log);self.checkpoint()
            if result==cp.MODEL_INVALID:raise ValueError(solver.response_stats())
            if result not in (cp.OPTIMAL,cp.FEASIBLE):break
            rs=model.decode(solver);sf=[i for i in ids if rs[i][:2]!=rows[i][:2]];su=[i for i,r in enumerate(rs) if r!=rows[i]]
            g=solver.value(model.gain);assert g==proxy(p,rows,rs)
            log.update(config=sf,support=su,proxy_gain_uJ=g,edits=[[i,rs[i]] for i in su]);self.checkpoint()
            assert legal_assignment(p,rows,rs,ids,levels,edges) and su==[i for i,z in enumerate(model.z) if solver.value(z)]
            rights=self.certify_assignment(rs,"cp"+str(ix),sf,su,g)
            if a["cp_rights"] is None and sf and g>=0:a["cp_rights"]=rights
            self.checkpoint()
            model.m.add(sum(model.x[i][rs[i][1]] for i in model.x)<=len(model.x)-1);model.m.clear_hints()
        a["wall_s"]=clock()-t;self.r["status"]="AUX_DONE";self.checkpoint()

class Arm(TimedReplay):
    def auxiliary(self):
        folder=self.folder
        with (folder/"aux.log").open("wb") as f:
            child=subprocess.Popen([sys.executable,"-B","-u",__file__,"aux",self.s["id"],self.variant,str(self.start),str(self.cpu)],
                                   stdout=f,stderr=subprocess.STDOUT)
        phase=None;killed=False
        while child.poll() is None:
            if phase is None and (folder/"phase.json").exists():phase=read(folder/"phase.json")
            if (phase and clock()>=phase["until"]-.045) or clock()>=self.end-1:
                child.kill();killed=True;break
            time.sleep(.008)
        child.wait()
        receipt=read(folder/"aux.json");a=receipt["auxiliary"]
        if (not killed and child.returncode) or receipt["status"]=="ERROR":
            raise RuntimeError(receipt.get("traceback",(folder/"aux.log").read_text(errors="replace")))
        if not phase:phase=read(folder/"phase.json")
        if killed:a.update(hard_stop=True,wall_s=min(11,clock()-phase["begin"]))
        else:assert a["wall_s"]<=11
        a["stage_status"]="TIME_LIMIT" if killed else "COMPLETE"
        self.r["auxiliary"]=a;self.r["variant"]=self.variant
        if receipt.get("pending"):self.r["aux_pending"]=receipt["pending"]
        self.r["offer_s"]=receipt.get("offer_s",{})
        # Transfer only completed, on-time certificates. The fresh process used
        # the identical physical/certification routine that the Core phase uses.
        self.r["candidates"]=[c for c in receipt["candidates"] if self.start+c["certified_s"]<=phase["until"]]
        self.known={c["sha"]:c for c in self.r["candidates"]}
        self.r["visits"]=[v for v in receipt["visits"] if v[1] in self.known]
        for name in ("cp_rights","hint_rights"):
            if a.get(name) is not None:
                self.r["region_source"]=name;self.checkpoint()
                return get_rights(**{k.lower():v for k,v in a[name].items()})
        self.r["region_source"]="ordinary";self.checkpoint()
        return None

def main():
    import psutil
    mode,ident,variant,t,cpu=sys.argv[1:];cpu=int(cpu);psutil.Process().cpu_affinity([cpu])
    s=next(x for x in read(ROOT/"samples.json")["cases"] if x["id"]==ident)
    folder=ROOT/"runs"/ident/variant
    if mode=="aux":arm=Auxiliary(s,"New",folder,float(t))
    else:arm=Arm(s,"New",folder,float(t));arm.variant=variant;arm.cpu=cpu
    try:
        if mode=="aux":arm.solve_stage(variant)
        else:arm.run()
    except Exception:
        arm.r.update(status="ERROR",traceback=traceback.format_exc());arm.checkpoint();raise
if __name__=="__main__":main()
