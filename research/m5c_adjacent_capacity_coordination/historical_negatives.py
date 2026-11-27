"""Recover individual IDs and both margins from M5-b's archived negative pairs. No search/certification."""
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
B=ROOT.parent/"m5b_suffix_capacity"
A=ROOT.parent/"m5a_mixed_frequency_quota"


def recover(nt, target):
    start=time.perf_counter()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    load=lambda p:json.loads(p.read_bytes())
    profiles=nt/"research/m1_transient_thermal_quota_20261126/frozen/p1/config"
    registration=nt/"research/m1i_generalization/registration"
    lens={}
    for name in ("cpu_npu_profiles.csv","gpu_profiles.csv"):
        with (profiles/name).open() as src:
            for r in csv.DictReader(src):
                if r.get("domain")=="cpu":
                    if int(r["k"])==0:lens[r["stage"],0]=int(r["ticks"])
                else:
                    lens[r["stage"],int(r["k"])+10*(name=="cpu_npu_profiles.csv")]=int(r["ticks"])
    results=[]
    for case,history in load(B/"adjacent_capacity.json")["cases"].items():
        p=A/"history"/case
        plan,cert=load(p/"plan.json"),load(p/"certificate.json")
        parent=bytes(k+10*(u==3) for u,k,_ in plan["rows"][1::3])
        item=next(i for i in load(registration/"cases.json")["cases"] if i["case"]==plan["case"])
        path=registration/"inputs"/item["input"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item["input_sha256"]
        with path.open() as src:req=list(csv.DictReader(src))
        seen={}
        for arm in "ACDER":
            for l in (B/"archive/logs"/case/arm/"events.jsonl").read_bytes().splitlines():
                row=json.loads(l)
                if row["kind"]=="certificate" and row["status"]=="SAFE" and row["role"]=="search" and row["meta"]["parent"]==cert["plan_sha256"]:
                    seen[row["cfg"]]=row
        old=load(B/"archive/gate"/case/"audit.json")["old_rejected"]
        count=0
        for identity,rear in seen.items():
            win=rear["meta"]["win"]
            ids=[i for i,r in enumerate(req) if int(r["scene"])==win]
            cfg=parent[:ids[0]]+bytes.fromhex(rear["meta"]["patch"])+parent[ids[-1]+1:]
            assert hashlib.sha256(cfg).hexdigest()==identity
            for front in old:
                if front["win"]+1!=win:continue
                margins=[]
                for dev in front["devices"]:
                    bound,after=item["horizon_ticks"],0
                    for i in range(len(req)-1,ids[0]-1,-1):
                        b=cfg[i]
                        if b//10!=dev["device"]-2:continue
                        k,typ=b%10,req[i]["kind"]
                        bound=min(int(req[i]["deadline_tick"])-lens[typ+".post",0],bound-5*(k!=after))-lens[typ+".main",b]
                        after=k
                    margins.append(bound-5*(after!=dev["last_freq"])-dev["finish"])
                assert min(margins)<0
                results.append(dict(case=case,parent=cert["plan_sha256"],front_window=win,rear_window=win+1,
                    front_cfg=front["cfg"],rear_cfg=identity,rear_plan=rear["plan"],original_gpu_ticks=front["devices"][0]["remaining"],
                    original_npu_ticks=front["devices"][1]["remaining"],paired_gpu_ticks=margins[0],paired_npu_ticks=margins[1]))
                count+=1
        assert count==history["adjacent_pairs"]
    assert len(results)==161
    target.mkdir(parents=True,exist_ok=True)
    with (target/"historical_negative_pairs.csv").open("w",newline="") as out:
        w=csv.DictWriter(out,fieldnames=list(results[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(results)
    (target/"historical_receipt.json").write_text(json.dumps(dict(rows=len(results),new_candidates=0,new_certs=0,
                 wall_s=time.perf_counter()-start+1,startup_allowance_s=1))+"\n")


if __name__=="__main__":recover(Path(sys.argv[1]),Path(sys.argv[2]))
