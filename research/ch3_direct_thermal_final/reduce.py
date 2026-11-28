"""Verify immutable physical evidence, then summarize only on-time online deliveries."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import zlib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_analytic_quota"))
import analyze as audit
sys.path.insert(0,str(ROOT.parent/"ch3_center_confirmation"))
from lane import CASES

def endpoint(p):
    if not p:
        return {}
    return dict(plan=p["plan"],status=p["status"],J=p["J"],lo=p["bounds"][0],hi=p["bounds"][1],
                E35_J=p["e35"],temperature_J=p["energy"]["temperature_J"],peak_C=p["peak"],slack_ms=p["slack"],
                **{k:v for k,v in p["energy"].items() if k!="temperature_J"})

def records(c,arm,rep,budget,folder,bundle):
    dest=folder/"paired_results"/c/f"{arm}-{budget}"
    rc=audit.read(dest/"receipt.json")
    assert rc["repeat"]==rep and rc["commit"]==os.environ["SCIENCE_SHA"] and str(rc["run"])==os.environ["SCIENCE_RUN"]
    order=["A","B"] if (CASES.index(c)+rep-1)%2==0 else ["B","A"]
    assert rc["position"]==order.index(arm)+1 and audit.lines(dest/"start.jsonl")[0]["core"]==[rc["core"]]
    audit.ROOT=folder
    cell=audit.cell(c,arm,budget,bundle)
    row=cell["row"]
    ids={e["request_sha"] for e in audit.lines(dest/"search.jsonl") if e.get("request_sha")}
    assert len(ids)==1
    row.update(repeat=rep,order=rc["position"],request_sha=ids.pop())
    if arm=="B":
        assert row["ordinary_DP_s"]==0
    post=[e for e in audit.lines(dest/"refine.jsonl") if e["t"]<=budget]
    selection=[e for e in post if e["event"]=="end" and e.get("task")=="selection"]
    assert len(selection)<=1
    search={e["point"]["plan"]:e for e in cell["certs"] if e["stage"]=="search"}
    idx=audit.read(dest.parent/"physical/index.json")["plans"]
    updates={(u["stage"],u["plan"],u["t"]) for u in cell["updates"]}
    maps=[]
    stages=[]
    for i,key in enumerate(selection[0]["seeds"] if selection else [],1):
        seed=search[key]
        pre=seed["point"]
        rank=4 if pre["status"]=="HOT" else i
        meta=dict(case=c,arm=arm,budget_s=budget,repeat=rep,rank=rank,mapping=seed["mapping"],seed=key,trace=idx[key]["trace_sha"],seed_status=pre["status"])
        events=[e for e in post if e.get("rank")==rank]
        current=pre if pre["status"]=="SAFE" else None
        outcomes=[]
        replaced=False
        for stage in (("ordinary","thermal") if arm=="A" else ("direct",)):
            tag=f"map{rank}/{stage}"
            certs=[e for e in cell["certs"] if e["stage"]==tag]
            assert len(certs)<=1 and all(e["mapping"]==seed["mapping"] for e in certs)
            point=certs[0]["point"] if certs else None
            if point and point["status"]=="SAFE" and (current is None or point["bounds"][1]<current["bounds"][0]):
                current=point
            if certs and (tag,point["plan"],certs[0]["t"]) in updates:
                replaced=True
            completed=any(e["event"]=="stage_end" and e.get("stage")==tag for e in events)
            begun=any(e["event"]=="begin" and e.get("task")=="refinement" and e.get("stage")==tag for e in events)
            stages.append(dict(**meta,stage=stage,started=begun,completed=completed,certificate_delivered=bool(certs),
                               certificate_s=certs[0]["t"] if certs else None,**endpoint(point)))
            outcomes.append(completed)
        final=bool(current and row["plan"]==current["plan"] and row["mapping"]==meta["mapping"])
        maps.append(dict(**meta,selected_s=selection[0]["t"],started=any(e["event"]=="map_start" for e in events),
                         stages_complete=all(outcomes),map_end=any(e["event"]=="map_end" for e in events),
                         recovered=pre["status"]=="HOT" and bool(current),improved_global=replaced,
                         final_winner=final,**{"before_"+k:v for k,v in endpoint(pre).items()},
                         **{"after_"+k:v for k,v in endpoint(current).items()}))
    assert len(maps)<=4 and len({r["mapping"] for r in maps})==len(maps)
    row.update(nominated=len(maps),completed_maps=sum(m["stages_complete"] for m in maps),hot_nominated=sum(m["seed_status"]=="HOT" for m in maps),
               hot_recovered=sum(m["recovered"] for m in maps),hot_final=sum(m["seed_status"]=="HOT" and m["final_winner"] for m in maps))
    return dict(row=row,updates=cell["updates"],config=cell["config"],visited=sorted(cell["maps"]),maps=maps,stages=stages)

def main(c,budget,out):
    src=ROOT/"lanes"/str(budget)/c
    for line in (src/"SHA256SUMS").read_text().splitlines():
        digest,path=line.split(maxsplit=1)
        with (src/path).open("rb") as stream:
            assert hashlib.file_digest(stream,"sha256").hexdigest()==digest
    out.mkdir(parents=True)
    data=[]
    with tarfile.open(out/f"{c}-endpoints.tar.gz","w:gz") as bundle:
        for rep in (1,2,3):
            # Frozen endpoint writer has no repetition prefix; use one inner tar per repeat.
            inner=out/f"r{rep}.tar"
            with tarfile.open(inner,"w") as unit:
                for arm in ("A","B"):
                    data.append(records(c,arm,rep,budget,src/f"r{rep}",unit))
            bundle.add(inner,arcname=inner.name)
            inner.unlink()
    assert len({(r["row"]["host"],r["row"]["core"],r["row"]["request_sha"]) for r in data})==1
    with gzip.open(out/f"{c}.json.gz","wt",encoding="utf8") as outstream:
        json.dump(data,outstream,separators=(",",":"))

if __name__=="__main__":
    main(sys.argv[1],int(sys.argv[2]),Path(sys.argv[3]))
