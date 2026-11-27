"""Identify which decisions changed; compare only observed prefixes at hard cutoffs."""
import gzip
import json
from pathlib import Path
from summarize import HERE,emit,read

def events(root,r):
    for part in r["journal"]:
        for s in gzip.decompress((root/part).read_bytes()).splitlines():
            yield json.loads(s)
def main():
    matched=[];native=[]
    for o in read(HERE/"registration/cases.json"):
        root=HERE/"results"/o["id"]
        allruns={p.stem:read(p) for p in (root/"runs").glob("*.json")}
        def sequence(m,phases):
            return [c["plan"] for c in allruns[m]["certificates"] if c["phase"] in phases]
        def rank(m):
            return [(v[1],v[2],v[3]) for v in events(root,allruns[m]) if v[0]=="choice"]
        for other in ("Ordinary","Previous"):
            left,right=allruns["Source"],allruns[other]
            a=left.get("location",{}).get("selected_w");b=right.get("location",{}).get("selected_w")
            c,d=rank("Source"),rank(other)
            common=min(len(c),len(d))
            t,u=sequence("Source",{"terminal"}),sequence(other,{"terminal"})
            assert t[:min(len(t),len(u))]==u[:min(len(t),len(u))]
            s1,s2=left["delivered"],right["delivered"]
            matched.append(dict(cohort=o["cohort"],case=o["id"],comparison="Source/"+other,
                       source_w=a,control_w=b,both_located=a is not None and b is not None,
                       different_windows=a!=b if a is not None and b is not None else None,
                       same_observed_choice_prefix=c[:common]==d[:common],source_choices=len(c),control_choices=len(d),
                       source_seed=s1[0]["plan"] if s1 else None,control_seed=s2[0]["plan"] if s2 else None,
                       source_end=s1[-1]["plan"] if s1 else None,control_end=s2[-1]["plan"] if s2 else None,
                       source_stop=left["receipt"]["status"],control_stop=right["receipt"]["status"],
                       source_replays=left["replays"],control_replays=right["replays"],
                       source_repair_s=left["phases"].get("repair"),control_repair_s=right["phases"].get("repair")))
        base=allruns["Q4"]
        if not base["delivered"]:continue
        key=base["delivered"][-1]["plan"]
        plans={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((root/"physical/plans.jsonl.gz").read_bytes()).splitlines())}
        rows=plans[key]["plan"]["rows"]
        records={c["plan"] for m,r in allruns.items() if m!="Q4" for c in r["certificates"]}
        same=[k for k in records if plans[k]["plan"]["rows"]==rows]
        assert len(set(same))<=1
        causal=plans[same[0]]["certificate"]["metrics"] if same else {}
        native.append(dict(cohort=o["cohort"],case=o["id"],native_plan=key,native_J=base["delivered"][-1]["J"],
                           corresponding_archived_causal_plan=same[0] if same else None,causal_J=causal.get("E_J"),causal_status=causal.get("status")))
    emit("locator_paths",matched)
    emit("q4_idle_sensitivity",native)
if __name__=="__main__":main()
