"""Read archived one-window certificates and boundary clocks; no new search, replay or certification."""
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_bytes())
def csvrows(p):
    with p.open(newline="") as f:return list(csv.DictReader(f))
def main(data,nt,out):
    proc=psutil.Process();proc.cpu_affinity(proc.cpu_affinity()[:1])
    t=time.perf_counter();history=ROOT.parent/"m5a_mixed_frequency_quota"/"history"
    reg=nt/"m1i_generalization/registration";cases=read(reg/"cases.json")["cases"]
    folder=nt/"m1_transient_thermal_quota_20261126/frozen/p1/config"
    lens={}
    for name,pin in [("gpu_profiles.csv","c77aa183d451e7d8cd15e1d0510e8f8bc21f6f40"),("cpu_npu_profiles.csv","a6eeae251d0ecd0107601ab8621c3c54ea753aa3")]:
        b=(folder/name).read_bytes();assert hashlib.sha1(("blob %d\0"%len(b)).encode()+b).hexdigest()==pin
        for row in csvrows(folder/name):
            if row.get("domain")=="cpu":
                if int(row["k"])==0:lens[row["stage"],0]=int(row["ticks"])
            else:
                b=int(row["k"])+(10 if name.startswith("cpu_npu") else 0)
                lens[row["stage"],b]=int(row["ticks"])
    result={}
    for c in ["A02","A06","C10","C11"]:
        plan=read(history/c/"plan.json");cert=read(history/c/"certificate.json")
        obj=next(x for x in cases if x["case"]==plan["case"]);p=reg/"inputs"/obj["input"]
        assert hashlib.sha256(p.read_bytes()).hexdigest()==obj["input_sha256"]
        req=csvrows(p);parent=bytes(k+10*(u==3) for u,k,s in plan["rows"][1::3])
        old=read(data/"gate"/c/"audit.json")["old_rejected"]
        observed={};chains=[]
        for meth in "ACDER":
            current=parent
            prev=None
            for line in (data/"logs"/c/meth/"events.jsonl").read_bytes().splitlines():
                if not line.endswith(b"}"):continue
                r=json.loads(line);m=r.get("meta",{})
                if r["kind"]=="certificate" and r["role"]=="search" and r["status"]=="SAFE" and m["parent"]==cert["plan_sha256"]:
                    observed[r["cfg"]]=dict(meta=m,plan=r["plan"],J=r["J"],method=meth)
                if r["kind"]=="accepted":
                    win=m["win"];ids=[i for i,row in enumerate(req) if int(row["scene"])==win]
                    updated=current[:ids[0]]+bytes.fromhex(m["patch"])+current[ids[-1]+1:]
                    if prev and prev[0]==win+1:
                        # The certified grandchild fixes the upstream exit clocks; the downstream edit cannot affect them.
                        before=prev[1];ends=[0,0];freq=[0,0];pre=0
                        for i in range(ids[-1]+1):
                            typ=req[i]["kind"]
                            pre=max(pre,int(req[i]["release_tick"]))+lens[typ+".pre",0]
                            b=updated[i];dev=b//10;k=b%10
                            ends[dev]=max(pre,ends[dev]+5*(k!=freq[dev]))+lens[typ+".main",b]
                            freq[dev]=k
                        def margins(config):
                            answer=[]
                            for dev in (0,1):
                                bound=obj["horizon_ticks"];after=0
                                for i in range(len(req)-1,ids[-1],-1):
                                    b=config[i]
                                    if b//10!=dev:continue
                                    k=b%10;typ=req[i]["kind"]
                                    latest=min(int(req[i]["deadline_tick"])-lens[typ+".post",0],bound-5*(k!=after))
                                    bound=latest-lens[typ+".main",b];after=k
                                answer.append(bound-5*(freq[dev]!=after)-ends[dev])
                            return answer
                        old_m,new_m=margins(before),margins(updated)
                        assert min(new_m)>=0
                        chains.append(dict(method=meth,parent=prev[2],next_window_edit=prev[3],combined=r["plan"],
                                     upstream_window=win,original_margins=old_m,new_margins=new_m,
                                     compensation=min(old_m)<0,combined_J=r["J"]))
                    prev=(win,current,m["parent"],r["plan"]);current=updated
        pairs=0;witness=[]
        for changed,v in observed.items():
            m=v["meta"];win=m["win"];pids=[i for i,row in enumerate(req) if int(row["scene"])==win]
            cc=parent[:pids[0]]+bytes.fromhex(m["patch"])+parent[pids[-1]+1:]
            assert hashlib.sha256(cc).hexdigest()==changed
            if win==0:continue
            for oldrow in old:
                if oldrow["win"]+1!=win:continue
                pairs+=1;margins=[]
                for d in oldrow["devices"]:
                    ids=[i for i in range(pids[0],len(req)) if cc[i]//10==d["device"]-2]
                    bound=obj["horizon_ticks"];after=0
                    for i in reversed(ids):
                        code=cc[i];freq=code%10;typ=req[i]["kind"]
                        latest=min(int(req[i]["deadline_tick"])-lens[typ+".post",0],bound-5*(freq!=after))
                        bound=latest-lens[typ+".main",code];after=freq
                    margins.append(bound-5*(d["last_freq"]!=after)-d["finish"])
                if min(margins)>=0:
                    witness.append(dict(upstream=oldrow["cfg"],upstream_window=oldrow["win"],adjacent_plan=v["plan"],
                               adjacent_cfg=changed,adjacent_window=win,adjacent_J=v["J"],original_margins=[d["remaining"] for d in oldrow["devices"]],
                               relaxed_margins=margins))
        result[c]=dict(distinct_safe_first_parent_edits=len(observed),adjacent_pairs=pairs,main_capacity_witnesses=witness,observed_adjoining_chains=chains)
    out.write_bytes((json.dumps(dict(cases=result,wall_s=time.perf_counter()-t,cpu_s=time.process_time(),
                new_candidates=0,thermal_calls=0),separators=(",",":"))+"\n").encode())
if __name__=="__main__":main(*map(Path,sys.argv[1:]))
