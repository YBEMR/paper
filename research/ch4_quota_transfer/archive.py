"""Read-only post-clock collection of plans, static certificates, traces, and timing counters."""
import csv,gzip,hashlib,json,os,shutil,struct,sys,tarfile,zlib
from collections import Counter
from pathlib import Path
from control import CASES,ROOT,HERE
S=Path(os.environ["FAST_SCRATCH"])
sys.path[:0]=[str(S/"site"),str(ROOT/"driver/ch3_integrated_quality_v1")]
import evidence
import numpy as np

OUT=HERE/"results"
def read(p):return json.loads(p.read_bytes())
def logs(p):return evidence.logs(p)
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=1)+"\n",encoding="utf8")
def table(name,rows,fields=None):
    with (OUT/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fields or list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def zipped(source,dest):
    b=source.read_bytes()
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(gzip.compress(b,5,mtime=0))
def spans(evs,task,stop):
    start=None;secs=0.
    for e in evs:
        if e["t"]>stop:continue
        if e.get("task")==task and e["event"]=="begin":start=e["t"]
        if start is not None and (e.get("task")==task and e["event"]=="end" or task=="search_cert" and e["event"]=="certificate"):
            secs+=e["t"]-start;start=None
    return secs+(max(0,stop-start) if start is not None else 0.)


class Physical:
    def __init__(self,dest):
        self.dest=dest;dest.mkdir(parents=True,exist_ok=True)
        self.plans={};self.blocks={};self.static={};self.n=0;self.tar=None
    def add(self,folder,p,obj):
        key=p["plan"]
        plan=(folder/"plan.json").read_bytes();cert=(folder/"certificate.json").read_bytes()
        d=json.loads(cert);metrics=d["metrics"]
        assert sha(plan.strip())==d["plan_sha256"]==key
        assert metrics["status"]==p["status"] and metrics["E_J"]==p["J"] and metrics["E_bounds"]==p["bounds"]
        assert metrics["min_deadline_slack_ms"]==p["slack"]>=0 and max(metrics["peak_hi"])==p["peak"]
        if p["status"]=="SAFE":assert p["peak"]<=80
        cfg=json.loads(plan)
        mapping=sha(bytes(x[0] for x in cfg["rows"][1::3]))
        with np.load(folder/"trace.npz") as ar:a=ar["events"]
        assert a.shape[1]==31 and a.dtype==np.float64 and np.isfinite(a).all()
        assert a[0,0]==0 and a[-1,1]==obj["horizon_ticks"] and np.all(a[:,1]>a[:,0])
        assert np.array_equal(a[1:,0],a[:-1,1]) and np.array_equal(a[1:,14:18],a[:-1,18:22])
        E=a[:,26:30].sum()+metrics["external_J"]
        assert p["bounds"][0]<=E<=p["bounds"][1]
        tracehash=sha(a.tobytes());d.pop("cert_s")
        canonical=sha(json.dumps(d,sort_keys=True).encode())
        if key in self.plans:
            assert self.plans[key]["trace_sha"]==tracehash and self.static[key]==canonical
            return mapping
        if self.tar is None or self.tar.offset>32_000_000:
            if self.tar:self.tar.close()
            self.n+=1;self.name=f"part-{self.n:03d}.tar";self.tar=tarfile.open(self.dest/self.name,"w")
        evidence.put(self.tar,key+"/plan",zlib.compress(plan,5));evidence.put(self.tar,key+"/certificate",zlib.compress(cert,5))
        parts=[]
        for block in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
            b=block.tobytes();k=sha(b);parts.append(k)
            if k not in self.blocks:
                self.blocks[k]=self.name;evidence.put(self.tar,"blocks/"+k,zlib.compress(b,3))
        self.plans[key]=dict(archive=self.name,plan_sha=sha(plan),cert_sha=sha(cert),blocks=parts,shape=list(a.shape),trace_sha=tracehash)
        self.static[key]=canonical
        return mapping
    def finish(self):
        if self.tar:self.tar.close()
        dump(self.dest/"index.json",dict(plans=self.plans,blocks=self.blocks))
        evidence.verify(self.dest)


def main():
    OUT.mkdir(exist_ok=True)
    reg=S/"nt/research/m1i_generalization/registration"
    objs={o["case"].split("_")[0]:o for o in read(reg/"cases.json")["cases"] if o["ambient"]==35}
    summaries=[];curves=[];levels=[];deliveries=[];maps=[];late=0
    res=read(ROOT/"formal_account.json")
    assert res["actual_cpu_s"]<=1500
    for case in CASES:
        o=objs[case];assert sha((reg/"inputs"/o["input"]).read_bytes())==o["input_sha256"]
        input_dir=OUT/"inputs"
        input_dir.mkdir(exist_ok=True)
        zipped(reg/"inputs"/o["input"],input_dir/(case+".csv.gz"))
        dump(input_dir/(case+".json"),o)
        physical=Physical(OUT/"physical"/case)
        prefix=ROOT/"formal"/case
        prior=0.
        for path in sorted(prefix.glob("*/receipt.json"),key=lambda p:read(p)["order"]):
            d=path.parent;rc=read(path);cap=rc["bound"];arm=rc["arm"];rep=rc["rep"];end=rc["charged"]
            meta=dict(case=case,arm=arm,cap=cap,rep=rep)
            sc,rf=[logs(d/(name+".jsonl")) for name in ("search","refine")]
            assert rc["reason"] in ("wall","natural","cpu_guard")
            if sc:assert all(x["request_sha"]==o["input_sha256"] for x in sc if "request_sha" in x)
            ev=sorted([(e["t"],s,e) for s,lg in (("search",sc),("refine",rf)) for e in lg if e["event"]=="certificate"],key=lambda x:x[0])
            first=min((tt for tt,_,e in ev if tt<=cap and e["point"]["status"]=="SAFE"),default=None)
            split=cap-(5 if cap==60 else 3)
            cut=split if first is not None and first<split else cap
            best=None;last=None;post_safe=set();search_pts={};status=Counter()
            for tt,s,e in ev:
                if tt>(cut if s=="search" else cap):
                    late+=1;continue
                p=e["point"];stage="search/physical" if s=="search" else e["stage"]
                if s=="refine":assert stage.endswith("/direct")
                mapping=physical.add(d/stage/"evidence"/o["case"]/p["plan"],p,o)
                status[p["status"]]+=1
                deliveries.append(dict(**meta,t=tt,stage=stage,plan=p["plan"],mapping=mapping,status=p["status"],J=p["J"],lo=p["bounds"][0],hi=p["bounds"][1]))
                if s=="search":search_pts[p["plan"]]=(p,mapping)
                elif p["status"]=="SAFE":post_safe.add(e["rank"])
                if p["status"]=="SAFE" and (best is None or p["bounds"][1]<best["bounds"][0]):
                    best=p;last=tt
                    curves.append(dict(**meta,t=tt,J=p["J"],lo=p["bounds"][0],hi=p["bounds"][1],stage=stage,plan=p["plan"],mapping=mapping))
            post=[e for e in rf if e["t"]<=cap]
            select=next((e for e in post if e["event"]=="end" and e.get("task")=="selection"),{})
            assert len(select.get("seeds",[]))<=4
            hot=rec=finished=0
            for i,key in enumerate(select.get("seeds",[]),1):
                seed,mp=search_pts[key];is_hot=seed["status"]=="HOT";rank=4 if is_hot else i
                attempts=[e for e in post if e.get("rank")==rank]
                done=any(e["event"]=="stage_end" and e["stage"].endswith("/direct") for e in attempts)
                for e in attempts:
                    if e["event"]=="certificate":
                        assert next(x["mapping"] for x in reversed(deliveries) if x["plan"]==e["point"]["plan"])==mp
                hot+=is_hot;rec+=is_hot and rank in post_safe;finished+=done
                maps.append(dict(**meta,rank=rank,mapping=mp,seed=key,status=seed["status"],finished=int(done),recovered=int(is_hot and rank in post_safe)))
            ns=read(d/"native.json") if (d/"native.json").exists() else {}
            stop=min(end,cut,ns.get("search",{}).get("supervisor_t",cap))
            timing={k+"_s":spans(events,k,st) for k,events,st in (
                ("construct",sc,stop),("instance",sc,stop),("search_cert",sc,stop),("selection",rf,end),("handoff",rf,end),("dp_cert",rf,end))}
            dp=[e for p in d.glob("map*/events.jsonl") for e in logs(p) if e["t"]<=end and e["kind"]=="dp"]
            assert all(e["thermal"] for e in dp)
            timing["dp_s"]=sum(e["elapsed_s"] for e in dp)
            init=min(stop,sc[0]["t"]) if sc else end
            # Interval between timed process launch and first search record includes imports, stack and JIT setup.
            timing["before_search_s"]=init
            timing["other_s"]=end-sum(timing.values())
            assert timing["other_s"]>=-0.001, (meta,timing)
            layers=logs(d/"layers.jsonl")
            completed=sum(e["complete"] for e in layers)
            width=max((e["width"] for e in sc if e["event"]=="begin" and e.get("task")=="construct"),default=0)
            for e in layers:
                if e["complete"]:levels.append(dict(**meta,**e))
            counts=struct.unpack("=4q",(d/"counts.bin").read_bytes()) if (d/"counts.bin").exists() else (0,)*4
            summaries.append(dict(**meta,order=rc["order"],core=rc["core"],start=rc["start"],charged=end,wall=rc["wall"],cpu_s=rc["accounted_now"]-prior,
                     stop=rc["reason"],safe=int(best is not None),first_s=first,last_s=last,J=best["J"] if best else None,
                     lo=best["bounds"][0] if best else None,hi=best["bounds"][1] if best else None,plan=best["plan"] if best else None,
                     generated=counts[0],evaluated=counts[1],legal=counts[2],propagations=counts[3],complete_layers=completed,
                     width=width,certs=sum(status.values()),hot_certs=status["HOT"],maps=len(select.get("seeds",[])),dp_calls=len(dp),
                     completed_maps=finished,hot_nominated=hot,hot_recovered=rec,**timing))
            prior=rc["accounted_now"]
            for p in [*d.glob("*.json*"),*d.glob("*.bin"),*d.glob("*err.log"),*d.glob("map*/events.jsonl")]:
                zipped(p,OUT/"logs"/case/d.name/(str(p.relative_to(d))+".gz"))
        physical.finish()
        print("verified",case,len(physical.plans),flush=True)
    table("cells",summaries);table("improvements",curves);table("certificates",deliveries);table("maps",maps)
    table("completed_layers",levels)
    total=sum(r["cap"] for r in summaries);assert total<=1440
    for case in CASES:
        cells=sorted((r for r in summaries if r["case"]==case),key=lambda r:r["order"])
        assert len({r["core"] for r in cells})==1 and all(a["start"]+a["wall"]<=b["start"] for a,b in zip(cells,cells[1:]))
    diag=sorted(ROOT.glob("diag*/receipt.json"))
    diag_cpu=sum(read(p)["accounted_now"] for p in diag)
    assert diag_cpu<=120
    for folder in sorted(p.parent for p in diag):
        for p in [*folder.glob("*.jsonl"),folder/"receipt.json",folder/"stderr.log"]:
            zipped(p,OUT/"diagnostic"/folder.name/(p.name+".gz"))
    for p in (ROOT/"diag1"/"physical").glob("*/evidence/*/*/*"):
        if p.name in {"certificate.json","trace.npz","plan.json"}:
            target=OUT/"diagnostic"/"fixed_evidence"/p.relative_to(ROOT/"diag1"/"physical")
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
    res.update(diagnostic_cpu_s=diag_cpu,nominal_issued_s=total,charged_s=sum(r["charged"] for r in summaries),
       recorded_cells=len(summaries),late=late,unique_physical=sum(len(read(p)["plans"]) for p in (OUT/"physical").glob("*/index.json")),
       guards={p.parent.name:read(p) for p in (ROOT/"guards").glob("*/receipt.json")},setup=read(ROOT/"setup.json"))
    dump(OUT/"budget.json",res)


if __name__=="__main__":main()
