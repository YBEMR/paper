"""Counterfactuals, receipts, anytime curves and lossless physical archive; offline only."""
import os
import time
BEGIN = time.perf_counter()
import csv
import gzip
import hashlib
import shutil
import signal
from collections import Counter
from itertools import combinations
import run as experiment
from run import (ARC, OUT, OLD, CODES, setup, prior, study, failed_physical, read, save, sha,
                 seed, splice, encode, Timing, Boundary, np)
import archive_results as frozen_archive


def table(name, rows, fields=None):
    with (ARC / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def beats(a,b):
    return a["status"] == "SAFE" and (b["status"] != "SAFE" or a["bounds"][1] < b["bounds"][0])


def filehash(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def funnel(path):
    from json import loads
    out = Counter()
    for f in sorted(path.glob("pairs*.jsonl.gz")):
        try:
            with gzip.open(f, "rt") as h:
                for line in h:
                    row=loads(line)
                    if row["stage"] == "shortlist":
                        out["leg_unique"]+=row["unique"]
                        out["leg_pass_suffix"]+=row["valid"]
                        if row["label"].startswith("base-"):
                            out["blocked_saving"]+=row["trigger_candidates"]
                            out["blocked_selected"]+=len(row["blocked"])
                    if row["stage"] == "open" and row["label"].startswith("regen-"):
                        out["regenerated_rears"]+=1
                    if row["stage"] == "pair":
                        out["pairs"]+=1
                        out["pairs_legal"]+=row["legal"]
        except EOFError:
            out["capped_partial_ledgers"]+=1
    return {k:out[k] for k in ("leg_unique","leg_pass_suffix","blocked_saving","blocked_selected",
                                "regenerated_rears","pairs","pairs_legal","capped_partial_ledgers")}


def case_audit(case, shared):
    eng,_ = prior.engine(case, OUT / case / "offline")
    tm = Timing(eng)
    certdir = {}
    for p in sorted((OUT / case).glob("*/evidence/*/*/certificate.json")):
        if (p.parent/"trace.npz").is_file():
            certdir[p.parent.name] = p.parent
    cfg0, d0, path0 = seed(case)
    original=prior.endpoint(d0)
    certdir.setdefault(original["plan"],path0)
    byconfig={}
    for key, path in certdir.items():
        try:
            byconfig[encode(read(path/"plan.json"))]=path
        except (ValueError,OSError):
            pass
    def physical(c):
        if c in byconfig:
            return prior.endpoint(read(byconfig[c]/"certificate.json"))
        r=eng.replay(prior.dec(c))
        if r is None:
            assert not tm.check(c)[0]
            ident=sha(c)
            path=ARC/"failures"/(ident+".json.gz")
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True)
                with gzip.open(path,"wt",compresslevel=1) as f:
                    experiment.json.dump(failed_physical(eng,c),f,default=lambda x:x.tolist(),separators=(",",":"))
            return dict(status="TIMING",cfg=ident,detail=str(path.relative_to(ARC)))
        d,_=eng.cert(prior.dec(c),r)
        byconfig[c]=eng.out/"evidence"/eng.case/d["plan_sha256"]
        return prior.endpoint(d)
    stream, ends, counts, tracks, owners, intermediate = [], {}, {}, {}, set(), []
    for method in "SRPJ":
        folder=OUT/case/method
        receipt=read(folder/"receipt.json")
        owners.add((receipt["host"],receipt["core"]))
        assert receipt["status"] in ("NATURAL","CAP") and receipt["wall_s"]<=60
        dest=ARC/"logs"/case/method
        dest.mkdir(parents=True,exist_ok=True)
        for p in folder.iterdir():
            if p.is_file():shutil.copy2(p,dest/p.name)
        events=[x for x in study.event_rows(folder/"events.jsonl") if x["t"]<=60]
        certs=[x for x in events if x["kind"]=="cert"]
        assert len(certs)<=48 and all(v<=16 for v in Counter(x["turn"] for x in certs).values())
        assert all(x["n"]==i and x["plan"] in certdir for i,x in enumerate(certs,1))
        incs=[x for x in events if x["kind"]=="incumbent"]
        last=original
        for x in incs:
            assert beats(x,last)
            last=x
        counts[method], ends[method], tracks[method]=len(certs),last,[original]
        for x in certs:
            tracks[method].append(x if beats(x,tracks[method][-1]) else tracks[method][-1])
        assert last["plan"] == tracks[method][-1]["plan"]
        summary=dict(case=case,method=method,seed_J=original["J"],J=last["J"],
                     saving_pct=100*(1-last["J"]/original["J"]),lower=last["bounds"][0],upper=last["bounds"][1],
                     plan=last["plan"],stop=receipt["status"],wall_s=receipt["wall_s"],cpu_s=receipt["cpu_s"],
                     core=receipt["core"],rounds=sum(x["kind"]=="round" for x in events),new_certs=len(certs),
                     safe=sum(x["status"]=="SAFE" for x in certs),cache=sum(x["kind"]=="cache" for x in events),
                     timing_fail=sum(x["kind"]=="timing_fail" for x in events),
                     single_nominations=sum(len(x["selected"]) for x in events if x["kind"]=="single_pool"),
                     rear_branch_certs=sum(x["meta"]["role"]=="rear_branch" for x in certs),
                     joint_certs=sum(x["meta"]["role"] in ("R","P","J") for x in certs),peak_C=last["peak"],
                     slack_ms=last["slack"],switches=last["switches"],**last["energy"],**funnel(folder))
        for cut in (10,30,60):
            best=next((x for x in reversed(incs) if x["t"]<=cut),original)
            summary[f"J{cut}"]=best["J"]
        stream.append(summary)
        for n,z in enumerate(tracks[method]):
            shared["curves"].append(dict(case=case,method=method,n=n,J=z["J"],plan=z["plan"]))
        for turn in range(3):
            joint=[x for x in events if x["kind"] in ("cert","cache") and x["turn"]==turn and x["meta"]["role"] in ("R","P","J")]
            if not joint:continue
            parentkey=joint[0]["parent"]
            basepath=certdir[parentkey]
            parent=encode(read(basepath/"plan.json"))
            base=prior.endpoint(read(basepath/"certificate.json"))
            better=[x for x in joint if beats(x,base)]
            if not better:continue
            best=min(better,key=lambda x:(x["bounds"][1],x["plan"]))
            winner=next((x["chosen"] for x in events if x["kind"]=="close" and x["turn"]==turn),last["plan"])
            for z in {v["plan"]:v for v in [best,*[x for x in better if x["plan"]==winner]]}.values():
                m=z["meta"];w=m["win"]
                f=splice(parent,eng.groups[w],bytes.fromhex(m["front"]))
                b=splice(parent,eng.groups[w+1],bytes.fromhex(m["rear"]))
                joint_code=splice(b,eng.groups[w],bytes.fromhex(m["front"]))
                assert len({parent,f,b,joint_code})==4 and physical(joint_code)["plan"]==z["plan"]
                front,rear=physical(f),physical(b)
                b0=Boundary(eng,parent,eng.replay(prior.dec(parent)),tm)
                bj=Boundary(eng,joint_code,eng.replay(prior.dec(joint_code)),tm)
                oldmargin=b0.inspect(f,w)
                newmargin=bj.inspect(joint_code,w)
                tail=bj.inspect(joint_code,w+1)
                assert min(x["remaining"] for x in newmargin+tail)>=0
                if m["role"]=="J":
                    assert min(x["remaining"] for x in oldmargin)<0 and front["status"]=="TIMING"
                    assert [(x["finish"],x["last_freq"]) for x in oldmargin]==[tuple(a) for a in m["front_end"]]
                intermediate.append(dict(case=case,method=method,turn=turn,front_window=w+1,chosen=z["plan"]==winner,
                    parent=base,front_only=front,rear_only=rear,joint=physical(joint_code),
                    old_boundary=oldmargin,new_boundary=newmargin,after_two=tail,
                    reverse_feasible=rear["status"]=="SAFE",rear_strict=beats(rear,base),
                    joint_beats_rear=beats(physical(joint_code),rear),online_via=m.get("via")))
    assert len(owners)==1
    for r in stream:
        n=min(counts.values())
        r["common_n"],r["common_J"]=n,tracks[r["method"]][n]["J"]
    for l,r in combinations("SRPJ",2):
        a,b=ends[l],ends[r]
        shared["pairs"].append(dict(case=case,left=l,right=r,left_minus_right_J=a["J"]-b["J"],
            lower=a["bounds"][0]-b["bounds"][1],upper=a["bounds"][1]-b["bounds"][0],same_plan=a["plan"]==b["plan"]))
    shared["rows"].extend(stream)
    shared["witnesses"].extend(intermediate)
    # Include all four counterfactuals, failed timing records, and the gate's historical certificates.
    seen,partial=frozen_archive.archive.pack(case)
    assert all(x["plan"] in seen for x in ends.values())
    frozen_archive.validate_pack(ARC/(case+".tar.gz"),seen)
    shared["physical"][case]=dict(plans=len(seen),partial=partial)


def main():
    os.sched_setaffinity(0,{experiment.CPUS[0]})
    signal.alarm(max(1,115-int(time.perf_counter()-BEGIN)))
    setup()
    frozen_archive.archive.R, frozen_archive.archive.OUT = OUT, ARC
    shared=dict(rows=[],pairs=[],curves=[],witnesses=[],physical={})
    for case in CODES:
        case_audit(case,shared)
    table("results.csv",shared["rows"])
    table("paired.csv",shared["pairs"])
    table("certificate_curves.csv",shared["curves"])
    save(ARC/"counterfactuals.json",shared["witnesses"])
    for p in ARC.rglob("*"):
        if p.is_file() and p.stat().st_size>95*1024*1024:
            raise RuntimeError(f"Pack exceeds git limit: {p}")
    manifest="".join(filehash(p)+"  "+p.relative_to(ARC).as_posix()+"\n" for p in sorted(ARC.rglob("*")) if p.is_file())
    (ARC/"SHA256SUMS").write_text(manifest)
    gate=read(ARC/"gate/receipt.json")["wall_s"]
    lanes=sum(x["wall_s"] for x in shared["rows"])
    offline=time.perf_counter()-BEGIN+2
    assert gate<=120 and lanes<=960 and offline<=120 and len(shared["rows"])==16
    save(ARC/"receipt.json",dict(gate_s=gate,formal_s=lanes,offline_s=offline,total_upper_core_s=gate+lanes+offline,
         formal_cpu_s=sum(x["cpu_s"] for x in shared["rows"]),physical=shared["physical"],cases=4,cells=16,
         same_core_checks=True,startup_allowance_s=2,manifest_sha256=filehash(ARC/"SHA256SUMS")))
    print("Audit complete",gate+lanes+offline,flush=True)


if __name__=="__main__":main()
