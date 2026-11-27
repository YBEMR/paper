"""Tie the first online SAFE to actual changed slots or quota actions, and compare fallback action prefixes."""
from collections import defaultdict
import gzip
import json
import psutil
from foundation import *
from pack_c import table

def main():
    psutil.Process().cpu_affinity([8]);stack=u.stack();rows=[]
    for k,o in cases().items():
        base=HOME_C/"results"/k;f=stack[0].Flow(o["word"],35,o["case"],OUT_C,frozen.A/"registration/inputs"/o["input"])
        b=Builder(f,f.eng);ns=[0,*limits(b)]
        runs={p.stem:read(p) for p in (base/"runs").glob("*.json")}
        maps={p["certificate"]["plan_sha256"]:u.encoded(r[:2] for r in p["plan"]["rows"][1::3]) for p in map(json.loads,gzip.decompress((base/"physical/plans.jsonl.gz").read_bytes()).splitlines())}
        control_actions=[a[2] for a in events(base,runs["Control"]) if a[0]=="nt_actions"]
        seeds={}
        for m,run in runs.items():
            first=next(iter(run["delivered"]),None)
            seed=maps[first["plan"]] if first and first["phase"]=="terminal" else None
            parent={};actions=defaultdict(list);changed=[];fallback=[];at=None
            for ev in events(base,run):
                tag=ev[0]
                if tag=="nt_actions":fallback.append(ev[2])
                if tag=="parent":parent[ev[1]]=bytes.fromhex(ev[2])
                if tag=="begin" and ev[1]=="fallback":at=ev[2]
                if not seed:continue
                if tag=="slot" and ev[2]!=ev[3] and ev[3][-1]==seed[:ns[ev[1]+1]].hex():changed.append(ev[1]+1)
                if tag=="q4_action":
                    _,pi,j,pair,q,d,t=ev
                    if t[-1] or parent[pi]!=seed[:ns[j]]:continue
                    if f.extension(b.types[j],*b.counts[j],*pair,*q)==seed[ns[j]:ns[j+1]]:
                        actions[j+1].append(dict(pair=pair,q=q,d=d))
            shared=min(len(control_actions),len(fallback))
            equal=control_actions[:shared]==fallback[:shared]
            added=[j for j,options in actions.items() if all(x["d"]!=[0,0] for x in options)]
            if seed:assert len(actions)==len(b.types)
            seeds[m]=dict(first=first,admitted_via_fourth=changed,quota_actions=dict(actions))
            rows.append(dict(case=k,arm=m,direct_seed=bool(seed),changed_fourth_on_seed=" ".join(map(str,changed)),
                     nonbalance_on_seed=" ".join(map(str,sorted(added))),fallback_begin_s=at,
                     control_fallback_actions=len(control_actions),arm_fallback_actions=len(fallback),
                     comparable_actions=shared,identical_on_overlap=equal if shared else None))
        put(base/"seed_lineage.json",seeds)
    table("lineage",rows)
if __name__=="__main__":main()
