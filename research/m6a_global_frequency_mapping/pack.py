"""Losslessly consolidate repeated online evidence and verify every byte before publishing."""
import csv
import hashlib
import json
import os
import tarfile
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
BASE=ROOT/"archive"
def get(p):return json.loads(p.read_bytes())
def h(b):return hashlib.sha256(b).hexdigest()
def put(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
def csvout(p,rows):
    if not rows:return
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def main():
    phys=BASE/"physical";phys.mkdir(exist_ok=True)
    locations=defaultdict(list)
    for p in BASE.rglob("plan.json"):
        if p.parent.parent.parent.name=="evidence":locations[p.parent.name].append(p.parent)
    members=defaultdict(list)
    for key,paths in locations.items():
        p=paths[0];assert h((p/"plan.json").read_bytes().strip())==key
        cert=get(p/"certificate.json");assert cert["plan_sha256"]==key
        for other in paths[1:]:
            assert (other/"plan.json").read_bytes()==(p/"plan.json").read_bytes()
            assert get(other/"certificate.json")["metrics"]==cert["metrics"]
            assert h((other/"trace.npz").read_bytes())==h((p/"trace.npz").read_bytes())
        members[p.parent.name].append((key,p))
    index=[]
    for case,items in members.items():
        size=0;num=0;tar=None
        for key,p in sorted(items):
            if tar is None or size>45_000_000:
                if tar:tar.close()
                num+=1;name=f"{case}-{num:02d}.tar.gz";tar=tarfile.open(phys/name,"w:gz",compresslevel=2);size=0
            row=dict(case=case,plan=key,archive=name)
            for n in ("plan.json","certificate.json","trace.npz"):
                b=(p/n).read_bytes();row[n]=h(b);tar.add(p/n,arcname=key+"/"+n);size+=len(b)
            index.append(row)
        tar.close()
    lookup={r["plan"]:r for r in index}
    for archive in phys.glob("*.tar.gz"):
        with tarfile.open(archive,"r|gz") as t:
            for ent in t:
                key,n=ent.name.split("/");assert h(t.extractfile(ent).read())==lookup[key][n]
    csvout(BASE/"physical_index.csv",index)
    rows=[]; receipts=[];witnesses=[]; nominations=[]
    for p in sorted(BASE.rglob("receipt.json")):
        rc=get(p);receipts.append(dict(cell=str(p.parent.relative_to(BASE)),**rc))
        if not (p.parent/"seed.json").is_file():continue
        seed=get(p.parent/"seed.json");prev=seed
        for kind in ("seed","ordinary","thermal","final"):
            f=p.parent/(kind+".json")
            if not f.exists() and kind=="final":x=prev
            elif not f.exists():continue
            else:x=get(f)
            prev=x;assert x["plan"] in lookup
            row={k:v for k,v in x.items() if k not in ("bounds","energy")}
            rows.append(dict(cell=str(p.parent.relative_to(BASE)),stage=kind,wall_s=rc["wall_s"],run_status=rc["status"],
                **row,**x["energy"],lower=x["bounds"][0],upper=x["bounds"][1]))
        events=p.parent/"events.jsonl"
        if events.exists():
            for line in events.read_bytes().splitlines():
                if not line.endswith(b"}"):continue
                e=json.loads(line)
                if e["kind"]=="factorial":
                    for pt in (e["parent"],e["freq_only"],e["joint"],*[d for d in e["direct"] if d["status"]!="TIMING"]):
                        assert pt["plan"] in lookup
                    witnesses.append(dict(cell=str(p.parent.relative_to(BASE)),**e))
                if e["kind"] in ("joint","nominated","screen"):nominations.append(dict(cell=str(p.parent.relative_to(BASE)),**e))
    csvout(BASE/"endpoints.csv",rows);put(BASE/"witnesses.json",witnesses);put(BASE/"nominations.json",nominations)
    totals={name:sum(r["wall_s"] for r in receipts if r["cell"].split("/")[0] in names) for name,names in
            [("preflight",["correctness","regression"]),("stage1",["stage1"]),("stage2",["stage2"]),("stage3",["stage3"])]}
    totals["preflight"]+=get(BASE/"environment.json")["startup_s"]
    for k,lim in zip(totals,(300,960,2880,1440)):assert totals[k]<=lim
    put(BASE/"budget.json",dict(by_stage=totals,total=sum(totals.values()),receipts=receipts,unique_physical=len(index)))
    # Only generated per-call duplicate physical files are released after a verified round trip.
    for paths in locations.values():
        for p in paths:
            for n in ("plan.json","certificate.json","trace.npz"):(p/n).unlink()
    with (BASE/"SHA256SUMS").open("w") as f:
        for p in sorted(BASE.rglob("*")):
            if p.is_file() and p.name!="SHA256SUMS":f.write(h(p.read_bytes())+"  "+str(p.relative_to(BASE))+"\n")
    print("VERIFIED",len(index),"plans;",len(witnesses),"factorials; charged",totals,flush=True)
if __name__=="__main__":main()
