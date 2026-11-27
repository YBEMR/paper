"""Post-run audit and lossless archive. Does not call a scheduler, replay or certifier."""
import csv
import hashlib
import io
import json
import os
import shutil
import tarfile
import zlib
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
R=ROOT/"results"
OUT=ROOT/"archive"
def read(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,sort_keys=True,ensure_ascii=False,indent=1),encoding="utf8")
def table(name,rows):
    with (OUT/name).open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
def snapshot(d):
    m=d["metrics"]
    return dict(plan=d["plan_sha256"],J=m["E_J"],bounds=m["E_bounds"],peak=max(m["peak_hi"]),
                slack=m["min_deadline_slack_ms"],switches=m["switch_count"],
                energy={k:m[k] for k in ("base_J","activity_J","switch_J","temperature_J","external_J")})
def member(t,name,data):
    h=tarfile.TarInfo(name);h.size=len(data);t.addfile(h,io.BytesIO(data))
def pack(code):
    seen=set();blocks=set();index={};partial=[]
    path=OUT/(code+".tar.gz")
    with tarfile.open(path,"w:gz",compresslevel=3) as tar:
        for src in sorted((R/code).glob("*/evidence/*/*")):
            key=src.name
            if key in seen:continue
            try:
                plan=(src/"plan.json").read_bytes();cert=(src/"certificate.json").read_bytes()
                with np.load(src/"trace.npz") as f:a=f["events"]
            except (OSError,ValueError,EOFError,__import__("zipfile").BadZipFile) as exc:
                partial.append(str(src.relative_to(R)));continue
            assert sha(plan.strip())==key==json.loads(cert)["plan_sha256"]
            assert a.dtype==np.dtype("<f8") and a.shape[1]==31 and a[0,0]==0
            assert np.array_equal(a[1:,0],a[:-1,1]) and np.array_equal(a[1:,14:18],a[:-1,18:22])
            seen.add(key)
            for name,body in (("plan.json",plan),("certificate.json",cert)):
                member(tar,key+"/"+name,body)
            ids=[];h=hashlib.sha256()
            for part in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
                b=part.tobytes();k=sha(b);ids.append(k);h.update(b)
                if k not in blocks:
                    blocks.add(k);z=zlib.compress(b,4);assert zlib.decompress(z)==b
                    member(tar,"blocks/"+k,z)
            assert sha(a.tobytes())==h.hexdigest()
            index[key]=dict(hash=h.hexdigest(),shape=a.shape,blocks=ids)
        member(tar,"events.json",json.dumps(index).encode())
    return seen,partial
def main():
    OUT.mkdir(exist_ok=False)
    shutil.copytree(R/"gate",OUT/"gate",ignore=shutil.ignore_patterns("evidence"))
    rows=[];pairs=[];proofs=[];physical={};charge=0;summary=[]
    for code in ("A02","A06","C10","C11"):
        hist=snapshot(read(ROOT/"history"/code/"certificate.json"))
        seen,partial=pack(code);physical[code]={"complete":len(seen),"partial":partial}
        ends={}
        for method in "ABCDE":
            folder=R/code/method;receipt=read(folder/"receipt.json")
            dest=OUT/"logs"/code/method;dest.mkdir(parents=True)
            for file in ("receipt.json","events.jsonl"):shutil.copy2(folder/file,dest/file)
            events=[]
            for line in (folder/"events.jsonl").read_bytes().splitlines():
                if line.endswith(b"}"):
                    row=json.loads(line)
                    if row["t"]<=60:events.append(row)
            accepted=[x for x in events if x["kind"]=="accepted"]
            certs=[x for x in events if x["kind"]=="certificate"]
            assert all(x["plan"] in seen for x in certs)
            prev=hist
            for a in accepted:
                assert a["status"]=="SAFE" and a["bounds"][1]<prev["bounds"][0]
                prev=a
            ends[method]=prev
            src=next(folder.glob("evidence/*/"+prev["plan"]));dst=OUT/"endpoints"/code/method
            dst.mkdir(parents=True)
            for name in ("plan.json","certificate.json"):shutil.copy2(src/name,dst/name)
            receipts=receipt["wall_s"];charge+=receipts
            gen=[x for x in events if x["kind"]=="generation"]
            legal=sum(x["kind"]=="native_replay" and x["legal"] for x in events) if method=="B" else len(certs)
            rejects=sum(x["kind"]=="timing_reject" or x["kind"]=="native_replay" and not x["legal"] for x in events)
            proposals=(sum(x["work"]["replays"] for x in gen) if method=="B" else sum(len(x["proposals"]) for x in gen))
            summary.append(dict(case=code,method=method,seed_J=hist["J"],J=prev["J"],saving_pct=100*(hist["J"]-prev["J"])/hist["J"],
                       J10=next((x["J"] for x in reversed(accepted) if x["t"]<=10),hist["J"]),
                       J30=next((x["J"] for x in reversed(accepted) if x["t"]<=30),hist["J"]),
                       plan=prev["plan"],end=receipt["status"],wall_s=receipts,proposals=proposals,
                       timing_reject=rejects,legal_replays=legal,certificates=len(certs),safe=sum(x["status"]=="SAFE" for x in certs),
                       probes=sum(x.get("role") in ("frequency_only","mapping_only") for x in certs),accepted=len(accepted),
                       generation_s=sum(x["phase_s"] for x in gen),cert_archive_s=sum(x["cert_archive_s"] for x in certs),
                       replay_s=sum(x.get("replay_s",0) for x in events),peak_C=prev["peak"],slack_ms=prev["slack"],
                       switches=prev["switches"],**prev["energy"]))
            for row in events:
                if row["kind"]=="factorial":proofs.append(dict(case=code,**row))
            for cut in (10,30,60):
                z=next((x for x in reversed(accepted) if x["t"]<=cut),hist)
                rows.append(dict(case=code,method=method,cut=cut,J=z["J"],plan=z["plan"],
                                 best_certified_search_J=min([hist["J"]]+[x["J"] for x in certs if x["t"]<=cut and x["status"]=="SAFE" and x["role"] not in ("mapping_only","frequency_only")])))
        for a,b in combinations("ABCDE",2):
            x,y=ends[a],ends[b]
            pairs.append(dict(case=code,left=a,right=b,left_minus_right_J=x["J"]-y["J"],
                 lower=x["bounds"][0]-y["bounds"][1],upper=x["bounds"][1]-y["bounds"][0]))
    table("results.csv",summary);table("cuts.csv",rows);table("paired.csv",pairs)
    write(OUT/"witnesses.json",proofs)
    gate=read(R/"gate"/"environment.json")["wall_s"]
    assert len(summary)==20 and charge<=1200 and gate+90<=300
    write(OUT/"audit.json",dict(physical=physical,cells=len(summary),gate_wall_s=gate,
               historical_intake_reserved_core_s=90,search_core_s_upper=charge,
               total_core_s_upper=charge+gate+90,source=os.environ.get("GITHUB_SHA"),run=os.environ.get("GITHUB_RUN_ID")))
    (OUT/"SHA256SUMS").write_text("".join(sha(x.read_bytes())+"  "+x.relative_to(OUT).as_posix()+"\n" for x in sorted(OUT.rglob("*")) if x.is_file()))
    print("Verified 20 cells, upper charge",charge+gate+90,flush=True)
if __name__=="__main__":main()
