"""One independently timed old/new replay, from the saved full historical pre-state."""
import gzip,json,sys,time,traceback
from pathlib import Path
from samples import ROOT,read,write,stream
from support import selected,solutions
from base import (Problem,Access,Core,Layout,bins,changes,clock,components,decode,dynamic_region,
                  evaluate,key,np,obj,raw,transitions)
from compact import permissions
from neighborhood import select
from numerics import cp_candidates,rights_check,seeded
from verify_core import check
from master import cp

class Replay:
    def __init__(self,sample,method,folder,start):
        self.s=sample;self.method=method;self.folder=folder;self.start=start;self.end=start+29.6
        self.p=Problem(sample["case"]);self.base=decode(json.loads(gzip.decompress(
            (ROOT/"prestates"/(sample["source"]+".json.gz")).read_bytes())))
        assert key(self.p,self.base)==sample["source"]
        self.r=dict(id=sample["id"],method=method,source=sample["source"],seed=sample["seed"],
                    primary=sample["primary"],historical_option=sample["proposal"],status="RUNNING",
                    candidates=[],auxiliary={},core={},fallback=None,visits=[],unreturned=[])
        self.known={};self.checkpoint()

    def checkpoint(self):
        self.r["elapsed_s"]=clock()-self.start
        write(self.folder/"arm.json",self.r)

    def offer(self,plan,origin,rights,region,cpdata=None):
        p=self.p;k=key(p,plan);self.r["visits"].append([origin,k])
        if k in self.known:
            if cpdata is not None:check(p,plan,*cpdata)
            rights_check(p,self.base,plan,rights,region)
            return
        body=obj(p.case,plan)
        path=self.folder/(k+".json.gz")
        path.write_bytes(gzip.compress(raw(body),compresslevel=2,mtime=0))
        self.r["pending"]=dict(sha=k,origin=origin)
        self.checkpoint()
        lay=Layout(p,plan[0]);assert transitions(p,*plan)[1]==lay.switches(plan[1])
        delta=rights_check(p,self.base,plan,rights,region)
        exact=lay.components(plan[1])
        if cpdata is not None:assert check(p,plan,*cpdata)[0]==exact
        metric=evaluate(p,plan,cert=True,trace=True)
        ev=np.asarray(metric.pop("events"))
        np.savez_compressed(self.folder/(k+".npz"),events=ev)
        cfg=delta["config"];moved=delta["moved"];support=sorted(set(cfg)|set(moved));i=self.s["primary"]
        assert len(cfg)<=12 and len(support)<=24
        record=dict(sha=k,origin=origin,changes=delta,config_values=[[j,plan[0][j][:2]] for j in cfg],
                    support=support,primary_changed=i in cfg,
                    original_proposal_recovered=i in cfg and tuple(self.s["proposal"])==plan[0][i][:2],
                    reference={name:str(v) for name,v in exact.items()},reference_J=str(sum(exact.values())),
                    metrics=metric,certified_s=clock()-self.start)
        record["on_time"]=record["certified_s"]<=30
        if k==self.s["source"]:assert metric["E_bounds"]==self.s["prior_metrics"]["E_bounds"]
        self.r["candidates"].append(record);self.known[k]=record
        del self.r["pending"];self.checkpoint()

    def auxiliary(self):
        s=self.s;p=self.p;rows=self.base[0];a=self.r["auxiliary"];before=clock()
        ids,selection=selected(p,rows,s["window"],s["iteration"],s["stale"],s["seed"])
        assert selection["primary"]==s["primary"] and tuple(selection["proposal"])==tuple(s["proposal"])
        a.update(selection=selection,config_candidates=ids,assignments=[]);self.checkpoint()
        selected_rights=None
        until=min(before+11,self.end-11)
        for rs,cfg,support,gain in solutions(p,rows,ids,s["primary"],s["seed"],until,a):
            rights=Access(set(cfg),set(support),{},set(),set());region=dynamic_region(p,self.base,rights.st,rights.sf,1)
            a["assignments"].append(dict(changed=[[i,rs[i]] for i in support],region=region["identity"],
                                         Sf=cfg,St=support,proxy_gain_uJ=gain));self.checkpoint()
            # Persist the complete counterexample even if the original physical builder rejects it.
            self.r["checking_aux_assignment"]=a["assignments"][-1];self.checkpoint()
            lay=Layout(p,rs);fixed,free=permissions(lay,region)
            preserved=fixed|{g for g in free if region["prior"].get(lay.flex[g],(False,False))[1]}
            optimal=fixed|{g for g in free if lay.gap_delta(g,35)<0}
            for label,low in (("aux_preserve",preserved),("aux_reference",optimal)):
                self.offer((rs,frozenset(low)),label,rights,region)
            del self.r["checking_aux_assignment"]
            if selected_rights is None and cfg and gain>=0:selected_rights=rights
            self.checkpoint()
        a["wall_s"]=clock()-before
        return selected_rights

    def run(self):
        p=self.p;s=self.s;r=self.r;current=self.base
        rights=self.auxiliary() if self.method=="New" else None
        if rights is None:
            method="CP-LNS" if self.method=="New" else "Proposed-NoOrder"
            mode,rights,trace=select(p,current[0],bins(p),s["window"],s["iteration"],s["stale"],s["seed"],method)
            # Every selected historical fallback comes from a specialised (not full-permission) turn.
            if self.method=="New" and mode==2:
                mode=1;rights.reorder=set()
            r["fallback"]=(self.method=="New" or trace["fallback"])
        else:mode=1;trace=dict(operator="support_constrained");r["fallback"]=False
        assert mode==1
        region=dynamic_region(p,current,rights.st,rights.sf,mode)
        c=r["core"];c.update(Sf=sorted(rights.sf),St=sorted(rights.st),region=region["identity"],operator=trace,solves=[])
        self.checkpoint()
        self.offer(current,"source",rights,region)
        if self.end-clock()>1.0:
            core=Core(p,current,sorted(rights.st),mode,region=region,access=rights)
            warm=core.m.clone()
            for v,x in core.assignment(current):warm.add(v==x)
            rem=self.end-clock()
            if rem>.35:
                sl=seeded(min(2,rem-.25),s["seed"]);status=sl.solve(warm)
                assert status not in (cp.INFEASIBLE,cp.MODEL_INVALID)
                c["warm"]=sl.status_name(status)
                if status in (cp.OPTIMAL,cp.FEASIBLE):
                    assert core.plan(sl)==current
                    check(p,current,{k:sl.value(v) for k,v in core.parts.items()},core.switches(sl))
                    core.m.clear_hints()
                    for j in range(len(core.m.proto.variables)):
                        v=core.m.get_int_var_from_proto_index(j);core.m.add_hint(v,sl.value(v))
            for alternate,cap in ((False,7),(True,6)):
                limit=min(cap,self.end-clock()-(1.6 if alternate else 2.5))
                if limit<.08:
                    r["unreturned"].append([alternate,"insufficient_time"]);continue
                sols,log=cp_candidates(core,current,s["seed"],limit,alternate);c["solves"].append(log)
                if not sols:r["unreturned"].append([alternate,log["status"]])
                self.checkpoint()
                for plan,parts,sw in sols:
                    if self.end-clock()<.15:
                        pending=r.setdefault("uncertified",[])
                        k=key(p,plan);pending.append(k)
                        (self.folder/(k+".json.gz")).write_bytes(gzip.compress(raw(obj(p.case,plan)),compresslevel=2,mtime=0))
                        continue
                    self.offer(plan,"core_alt" if alternate else "core_main",rights,region,(parts,sw))
        else:r["unreturned"].append(["both","insufficient_time_for_core"])
        r["status"]="COMPLETE";self.checkpoint()

def main(idx,method,start,cpu):
    import psutil
    psutil.Process().cpu_affinity([cpu])
    sample=read(ROOT/"samples.json")["cases"][idx];folder=ROOT/"replays"/sample["id"]/method
    proc=Replay(sample,method,folder,start)
    try:proc.run()
    except Exception:
        proc.r["status"]="CORRECTNESS_OR_RUNTIME_STOP";proc.r["traceback"]=traceback.format_exc()
        proc.checkpoint();raise
if __name__=="__main__":main(int(sys.argv[1]),sys.argv[2],float(sys.argv[3]),int(sys.argv[4]))
