"""Compare completed fixed-mapping optimizations on every recorded pre-DP nomination."""
import csv
import hashlib
import json
import os
import sys
import tarfile
import time
import zlib
from pathlib import Path

from budget import ROOT, OUT, CASES
import numpy as np
sys.path.insert(0,str(ROOT.parent/"ch3_integrated_quality_v3"))
from hot import f, m, valid

ARCHIVE=ROOT.parent/"ch3_center_confirmation/lanes"
DEADLINE=float(os.environ["CASE_DEADLINE"])
sha=lambda b:hashlib.sha256(b).hexdigest()


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(value,separators=(",",":"),allow_nan=False)+"\n")
    temp.replace(path)


def records(path):
    return [json.loads(l) for l in path.read_bytes().splitlines() if l.endswith(b"}")]


def source(c):
    return ARCHIVE/c/"r1/paired_results"/c


def nominations(c,budget):
    folder=source(c)/f"center-{budget}"
    events=[e for e in records(folder/"refine.jsonl") if e["t"]<=budget]
    select=[e for e in events if e["event"]=="end" and e.get("task")=="selection"]
    assert len(select)==1
    seeds=select[0]["seeds"]
    assert 1<=len(seeds)<=4
    certs=records(folder/"certificates.jsonl")
    searches={e["point"]["plan"]:e for e in records(folder/"search.jsonl") if e["event"]=="certificate" and e["t"]<=budget-5}
    rows=[]
    for i,key in enumerate(seeds,1):
        event=searches[key]
        old=next(e for e in certs if e["stage"]=="search" and e["point"]==event["point"] and e["t"]==event["t"])
        rank=4 if old["point"]["status"]=="HOT" else i
        provenance={}
        ev=[e for e in events if e.get("rank")==rank]
        for e in ev:
            if e["event"]=="map_start":
                assert e["seed"]==key
        for stage in ("ordinary","thermal"):
            label=f"map{rank}/{stage}"
            end=next((e for e in ev if e["event"]=="stage_end" and e.get("stage")==label),None)
            cert=next((e for e in ev if e["event"]=="certificate" and e.get("stage")==label),None)
            if cert:
                assert any(x["stage"]==label and x["point"]==cert["point"] and x["mapping"]==old["mapping"] for x in certs)
            if end:
                assert end["attempt"]==(cert["point"]["plan"] if cert else None)
            provenance[stage]=dict(completed=end is not None,point=cert["point"] if cert else None,
                                   incumbent=end.get("incumbent") if end else None)
        rows.append(dict(case=c,budget=budget,rank=rank,seed=key,point=old["point"],mapping=old["mapping"],
                         nomination_s=select[0]["t"],search_certificate_s=old["t"],history=provenance))
    assert len({r["mapping"] for r in rows})==len(rows)
    return rows


class Store:
    def __init__(self,c,eng):
        self.c=c
        self.eng=eng
        self.physical=source(c)/"physical"
        self.index=f.read(self.physical/"index.json")
        self.handles={}
        self.cache={}

    def data(self,archive,name):
        if archive not in self.handles:
            self.handles[archive]=tarfile.open(self.physical/archive,"r:")
        return zlib.decompress(self.handles[archive].extractfile(name).read())

    def load(self,pt):
        key=pt["plan"]
        if key not in self.cache:
            row=self.index["plans"][key]
            p=self.data(row["archive"],key+"/plan")
            d=self.data(row["archive"],key+"/certificate")
            assert sha(p.strip())==key and sha(p)==row["plan_sha"] and sha(d)==row["cert_sha"]
            chunks=[]
            for k in row["blocks"]:
                b=self.data(self.index["blocks"][k],"blocks/"+k)
                assert sha(b)==k
                chunks.append(b)
            raw=b"".join(chunks)
            assert sha(raw)==row["trace_sha"]
            tr=np.frombuffer(raw,dtype=np.float64).reshape(row["shape"])
            plan=json.loads(p)
            cert=json.loads(d)
            cfg=m.genes(plan)
            assert valid(tr,self.eng.p.horizon) and sha(bytes(u for u,k in cfg))==row["mapping"]
            replay=self.eng.replay(cfg)
            assert replay is not None
            built=self.eng.build(cfg,replay)
            assert f.raw(built["rows"])==f.raw(plan["rows"]) and f.raw(sorted(built["low"]))==f.raw(plan["low"])
            assert f.raw(built["switches"])==f.raw(cert["switches"]) and np.array_equal(tr[:,:14],built["ev"])
            assert cert["E35_exact"]==built["ref_exact"]
            self.cache[key]=(cfg,replay,cert,tr)
            dest=OUT/"evidence"/self.c/"historical"/key
            dest.mkdir(parents=True,exist_ok=True)
            (dest/"plan.json").write_bytes(p)
            (dest/"certificate.json").write_bytes(d)
            dump(dest/"trace_source.json",dict(source_commit="479f0ce02a1b0d1ed5ba3fd081d647dccec89e12",
                 directory=self.physical.relative_to(ROOT.parents[1]).as_posix(),**row))
        value=self.cache[key]
        assert m.endpoint(value[2])==pt
        return value

    def close(self):
        for handle in self.handles.values():
            handle.close()


def point(result):
    return m.endpoint(result[2]) if result is not None else None


def accept(current,result):
    return result if result is not None and f.strict(point(result),point(current)) else current


def verify(seed,value,horizon):
    if value is not None:
        assert tuple(u for u,k in seed[0])==tuple(u for u,k in value[0])
        assert valid(value[3],horizon)
        p=point(value)
        if p["status"]=="SAFE":
            assert p["slack"]>=0 and p["peak"]<=80


def trace_summary(seed,result):
    if result is None:
        return None
    a,b=seed[3],result[3]
    t=np.union1d(np.r_[a[:,0],a[-1,1]],np.r_[b[:,0],b[-1,1]])
    def temperatures(tr,node):
        return np.interp(t,np.r_[tr[:,0],tr[-1,1]],np.r_[tr[:,14+node],tr[-1,18+node]])
    delta=np.column_stack([temperatures(b,i)-temperatures(a,i) for i in range(4)])
    return dict(trace=sha(b.tobytes()),max_abs_delta_C=np.abs(delta).max(axis=0).tolist(),
                end_delta_C=delta[-1].tolist(),peak_upper_delta_C=point(result)["peak"]-point(seed)["peak"])


def evaluate_case(c,rows,verified):
    obj=next(o for o in m.u2.CASES if m.label(o)==c)
    eng,flow=m.build(obj,ROOT/"scratch"/c)
    archive=Store(c,eng)
    cache={}
    by_seed={}
    for r in rows:
        by_seed.setdefault(r["seed"],[]).append(r)
    try:
        for r in rows:
            if time.monotonic()+1>=DEADLINE:
                return
            key=r["seed"]
            seed=archive.load(r["point"])
            tracehash=sha(seed[3].tobytes())
            assert r["mapping"]==sha(bytes(u for u,k in seed[0]))
            cachekey=(key,tracehash)
            if cachekey not in cache:
                statuses=r["point"]["status"]
                assert statuses in ("SAFE","HOT")
                folder=OUT/"evidence"/c/"computed"/key
                folder.mkdir(parents=True,exist_ok=True)
                def solve(stage,parent,thermal):
                    eng.out=folder/stage
                    result=m.optimize(eng,flow,seed[0],parent,folder,stage,thermal)
                    verify(seed,result,eng.p.horizon)
                    return result
                incumbent=seed if statuses=="SAFE" else None
                sources={}
                guide=seed
                for stage in ("ordinary","thermal"):
                    actual=[x["history"][stage] for x in by_seed[key] if x["history"][stage]["completed"]]
                    # The immutable seed hash indexes the actual rows; the physical store has a single verified trace for it.
                    if actual:
                        assert all(z["point"]==actual[0]["point"] and z["incumbent"]==actual[0]["incumbent"] for z in actual)
                    archived=actual[0]["point"] if actual else None
                    prove=bool(actual) and (statuses,stage) not in verified
                    if actual and not prove:
                        result=archive.load(archived) if archived else None
                        sources[stage]="archived_complete"
                    else:
                        result=solve(stage,guide,stage=="thermal")
                        sources[stage]="replayed_match" if prove else "completed_offline"
                        if prove:
                            assert point(result)==archived
                            if result is not None:
                                reference=archive.load(archived)
                                assert np.array_equal(result[3],reference[3])
                            verified.add((statuses,stage))
                    verify(seed,result,eng.p.horizon)
                    incumbent=accept(incumbent,result)
                    if actual:
                        assert actual[0]["incumbent"]==(point(incumbent)["plan"] if incumbent else None)
                    if stage=="ordinary":
                        ordinary=result
                        control=incumbent
                        guide=(result if result is not None and point(result)["status"] in ("SAFE","HOT") else seed) if statuses=="HOT" else incumbent
                    else:
                        corrected=result
                direct=solve("direct",seed,True)
                b=accept(seed if statuses=="SAFE" else None,direct)
                outcomes=dict(A=incumbent,B=b,C=control)
                proposals=dict(ordinary=ordinary,thermal=corrected,direct=direct)
                all_results={**outcomes,**proposals}
                diag=dict(seed=key,trace=tracehash,source=sources,guide=point(guide)["plan"],
                          guide_trace=sha(guide[3].tobytes()),outcomes={k:point(v) for k,v in outcomes.items()},
                          proposed={k:point(v) for k,v in proposals.items()},
                          traces={k:trace_summary(seed,v) for k,v in all_results.items()})
                with (folder/"request_frequencies.csv").open("w",newline="") as out:
                    w=csv.writer(out,lineterminator="\n")
                    w.writerow(["request","device","seed",*all_results])
                    for i,(u,k) in enumerate(seed[0]):
                        w.writerow([i,u,k,*[v[0][i][1] if v else None for v in all_results.values()]])
                dump(folder/"comparison.json",diag)
                cache[cachekey]=diag
            diag=cache[cachekey]
            # Check even a certificate published immediately before a truncated stage_end.
            for stage,z in r["history"].items():
                if z["point"]:
                    assert z["point"]==diag["proposed"][stage]
            dump(OUT/"slots"/c/f"{r['budget']}-{r['rank']}.json",dict(**r,comparison=diag))
    finally:
        archive.close()


def main():
    manifest=[r for c in CASES for b in (60,600) for r in nominations(c,b)]
    assert len(manifest)<=96
    dump(OUT/"nominees.json",manifest)
    m.CLOCK=float(os.environ["STUDY_START"])
    m.RUN=m.u2.stack()
    verified=set()
    for c in CASES:
        evaluate_case(c,[r for r in manifest if r["case"]==c],verified)
    print("verified historical status/stage classes",sorted(verified),flush=True)


if __name__=="__main__":
    main()
