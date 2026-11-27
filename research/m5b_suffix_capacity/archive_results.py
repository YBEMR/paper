"""Read-only reconciliation, disjoint-interval comparisons and physical archive verification."""
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tarfile
import zlib
from collections import Counter
from itertools import combinations
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/"m5a_mixed_frequency_quota"
R=ROOT/"results";OUT=ROOT/"archive"
spec=importlib.util.spec_from_file_location("prior_archive",OLD/"archive.py")
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
archive.R=R;archive.OUT=OUT
read=archive.read;write=archive.write;sha=archive.sha
def table(name,rows,fields=None):
    with (OUT/name).open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def beats(a,b):
    return a.get("status")=="SAFE" and (b.get("status")!="SAFE" or a["bounds"][1]<b["bounds"][0])
def refuted(s,base):
    return s["status"]!="SAFE" or s["plan"]==base["plan"] or s["bounds"][0]>=base["bounds"][1]
def read_csv(p):
    with p.open(newline="") as f:return list(csv.DictReader(f))
def readlogs(p):
    return [json.loads(l) for l in p.read_bytes().splitlines() if l.endswith(b"}")]
def validate_pack(path,expected):
    with tarfile.open(path,"r|gz") as tar:
        blocks={};plans=set();certs=set();index={}
        for ent in tar:
            b=tar.extractfile(ent).read();name=ent.name
            if name=="events.json":index=json.loads(b)
            elif name.startswith("blocks/"):
                key=name.split("/")[1];raw=zlib.decompress(b);assert sha(raw)==key;blocks[key]=raw
            elif name.endswith("/plan.json"):
                key=name.split("/")[0];assert sha(b.strip())==key;plans.add(key)
            elif name.endswith("/certificate.json"):
                d=json.loads(b);assert d["plan_sha256"]==name.split("/")[0];certs.add(d["plan_sha256"])
        assert expected==set(index)==certs==plans
        for k,r in index.items():
            a=b"".join(blocks[s] for s in r["blocks"]);assert sha(a)==r["hash"] and len(a)==r["shape"][0]*31*8
def main():
    OUT.mkdir(exist_ok=False)
    shutil.copytree(R/"gate",OUT/"gate",ignore=shutil.ignore_patterns("evidence"))
    results=[];funnels=[];comparisons=[];witnesses=[];ends={};proof_counts=Counter()
    source=read(R/"gate"/"receipt.json");charge=0.
    for case in ("A02","A06","C10","C11"):
        seen,partial=archive.pack(case);validate_pack(OUT/(case+".tar.gz"),seen)
        proof_counts[case]=len(seen)
        historical={}
        for meth in "ABCDE":
            z=read(OLD/"archive/endpoints"/case/meth/"certificate.json");historical[meth]=archive.snapshot(z)
        for method in "ACDER":
            path=R/case/method;rc=read(path/"receipt.json");charge+=rc["wall_s"]
            logs=OUT/"logs"/case/method;logs.mkdir(parents=True)
            for file in path.iterdir():
                if file.is_file():shutil.copy2(file,logs/file.name)
            ev=[q for q in readlogs(path/"events.jsonl") if q["t"]<=30]
            hist=archive.snapshot(read(OLD/"history"/case/"certificate.json"))
            end=hist;accept=[];certs=[q for q in ev if q["kind"]=="certificate"]
            assert rc["status"] in ("NATURAL","CAP") and all(q["plan"] in seen for q in certs)
            for a in (q for q in ev if q["kind"]=="accepted"):
                assert a["status"]=="SAFE" and a["bounds"][1]<end["bounds"][0]
                end=a;accept.append(a)
            ends[case,method]=end
            gens=[q for q in ev if q["kind"]=="generation"]
            cum=Counter()
            measures="mappings device_raw device_own device_suffix device_top paired unique_window_family prefilter_tested prefilter_pass refill_after_rank3 window_top3 nominated".split()
            for g in gens:
                for row in g["coverage"]:
                    counts={s:row.get(s,0) for s in measures};cum.update(counts)
                    funnels.append(dict(case=case,method=method,turn=g["turn"],window=row["window"],parent=g["parent"],**counts))
            search=[x for x in certs if x["role"]=="search"]
            missed=sum(x["kind"]=="timing_reject" and x["role"]=="search" for x in ev)
            duplicates=sum(x["kind"]=="duplicate" and x["role"]=="search" for x in ev)
            results.append(dict(case=case,method=method,J=end["J"],lower=end["bounds"][0],upper=end["bounds"][1],
                   saving_pct=100*(hist["J"]-end["J"])/hist["J"],seed_J=hist["J"],plan=end["plan"],
                   status=rc["status"],wall_s=rc["wall_s"],cpu=rc["cpu"],accepts=len(accept),last_gain_s=accept[-1]["t"] if accept else 0,
                   peak_C=end["peak"],switches=end["switches"],slack_ms=end["slack"],
                   replay_legal=len(search),replay_fail=missed,search_duplicates=duplicates,
                   legal_rate=len(search)/(len(search)+missed) if len(search)+missed else "",
                   certs=len(certs),search_certs=len(search),search_SAFE=sum(x["status"]=="SAFE" for x in search),
                   projection_certs=len(certs)-len(search),generation_s=sum(x["phase_s"] for x in gens),
                   cert_archive_s=sum(x["cert_archive_s"] for x in certs),**end["energy"],**{k:cum[k] for k in measures}))
            for x in ev:
                if x["kind"]!="factorial":continue
                one,two=x["singles"];base=x["parent"];joint=x["joint"]
                assert beats(joint,base)
                x.update(case=case,method=method,joint_better_than_both=x["genuine"] and beats(joint,one) and beats(joint,two),
                         requires_both=x["genuine"] and refuted(one,base) and refuted(two,base))
                witnesses.append(x)
            p=next(path.glob("evidence/*/"+end["plan"]));dst=OUT/"endpoints"/case/method;dst.mkdir(parents=True)
            for name in ("plan.json","certificate.json"):shutil.copy2(p/name,dst/name)
            for h,y in historical.items():
                comparisons.append(dict(case=case,left=method,right="historical_"+h,delta_J=end["J"]-y["J"],
                   lo=end["bounds"][0]-y["bounds"][1],hi=end["bounds"][1]-y["bounds"][0]))
        for a,b in combinations("ACDER",2):
            x,y=ends[case,a],ends[case,b]
            comparisons.append(dict(case=case,left=a,right=b,delta_J=x["J"]-y["J"],
                   lo=x["bounds"][0]-y["bounds"][1],hi=x["bounds"][1]-y["bounds"][0]))
    table("results.csv",results);table("funnel.csv",funnels);table("paired.csv",comparisons)
    write(OUT/"witnesses.json",witnesses)
    assert len(results)==20 and charge<=600 and source["wall_s"]<=120 and source["wall_s"]+charge<=720
    write(OUT/"audit.json",dict(cells=len(results),restored_plans=proof_counts,gate_core_s_upper=source["wall_s"],
         main_core_s_upper=charge,total_core_s_upper=charge+source["wall_s"],run=source["run"],source=source["source"],
         factorial=len(witnesses),genuine=sum(x["genuine"] for x in witnesses),
         requires_both=sum(x["requires_both"] for x in witnesses)))
    (OUT/"SHA256SUMS").write_text("".join(sha(x.read_bytes())+"  "+x.relative_to(OUT).as_posix()+"\n" for x in sorted(OUT.rglob("*")) if x.is_file()))
    print(read(OUT/"audit.json"),flush=True)
if __name__=="__main__":main()
