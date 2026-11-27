"""Post hoc physical replay of each constituent of up to two observed accepted groups; no search."""
import csv
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from common_u2 import *

def run():
    from review_u2 import TABLE,DEST,unpack,emit
    import ast
    with (TABLE/"candidate_effects.csv").open() as inp:
        candidates=[r for r in csv.DictReader(inp) if r["rep"]=="1" and r["turn"]=="1" and r["accepted"]=="True" and int(r["length"])>1 and r["method"] in ("Fixed2","Adaptive2") and float(r["system_saving_J"])>0]
    selected=[]
    def choose(rows):
        if rows:
            selected.append(min(rows,key=lambda r:(r["all_singletons_nonpositive"]!="True",-int(r["singleton_nonpositive"])/int(r["length"]),-float(r["system_saving_J"]),r["case"])))
    choose([r for r in candidates if r["method"]=="Fixed2"])
    choose([r for r in candidates if r["method"]=="Adaptive2" and int(r["length"]) not in (1,4,8,16,32,64) and all(r["case"]!=s["case"] for s in selected)])
    records=[];cases=[];st=stack()
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);evid=tmp/"singletons";evid.mkdir()
        for s in selected:
            code=s["case"];obj=next(o for o in CASES if o["case"].startswith(code+"_"))
            sub=tmp/code;sub.mkdir();root,_,_=unpack(DEST/code,sub)
            source=root/"r1"/s["method"]/"evidence"/obj["case"]
            parent=read(source/s["parent"]/"plan.json");p0=read(source/s["parent"]/"certificate.json")
            ids=json.loads(s["requests"]);seed=tuple(tuple(v[:2]) for v in parent["rows"][1::3])
            out=evid/code;flow=make_flow(st[0],obj,out);eng=st[1].Engine(obj["case"],out)
            def assess(c):
                r=st[3](flow,encoded(c))
                return eng.cert(c,r)[0] if r is not None else None
            dc=assess(seed);assert dc["plan_sha256"]==s["parent"] and dc["metrics"]==p0["metrics"]
            changed=list(seed)
            for i in ids:changed[i]=(seed[i][0],seed[i][1]-1)
            dg=assess(tuple(changed));assert dg["plan_sha256"]==s["plan"] and dg["metrics"]==read(source/s["plan"]/"certificate.json")["metrics"]
            info=dict(case=code,method=s["method"],parent=s["parent"],group=s["plan"],group_size=len(ids),group_requests=ids,
                      parent_J=dc["metrics"]["E_J"],group_J=dg["metrics"]["E_J"],group_saving_J=dc["metrics"]["E_J"]-dg["metrics"]["E_J"])
            cases.append(info)
            for i in ids:
                c=list(seed);c[i]=changed[i];dd=assess(tuple(c))
                base=dict(case=code,method=s["method"],request=i)
                if dd is None:records.append(dict(base,status="TIMING_INFEASIBLE"));continue
                m=dd["metrics"];records.append(dict(base,status=m["status"],J=m["E_J"],saving_J=dc["metrics"]["E_J"]-m["E_J"],
                    strict_gain=m["status"]=="SAFE" and m["E_bounds"][1]<dc["metrics"]["E_bounds"][0],switches=m["switch_count"],
                    peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],plan=dd["plan_sha256"]))
        save(evid/"cases.json",cases);save(evid/"singletons.json",records)
        output=DEST/"mechanism_witness";output.mkdir(exist_ok=True)
        tarpath=tmp/"singleton-evidence.tar.gz"
        with tarfile.open(tarpath,"w:gz",compresslevel=2) as tar:tar.add(evid,arcname="singletons")
        import hashlib
        digest=hashlib.sha256();parts=[]
        with tarpath.open("rb") as f:
            while b:=f.read(16*1024*1024):
                name=f"physical.tar.gz.part{len(parts):03d}"
                (output/name).write_bytes(b);parts.append(dict(name=name,sha256=sha(b),bytes=len(b)));digest.update(b)
        save(output/"manifest.json",dict(archive_sha256=digest.hexdigest(),parts=parts,search_calls=0,cases=cases,individual_replays=len(records)))
    emit("witness_groups",cases);emit("witness_singletons",records)
    print("GROUP WITNESSES",len(cases),len(records))
if __name__=="__main__":run()
