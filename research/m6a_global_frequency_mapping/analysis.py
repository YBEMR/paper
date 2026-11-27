"""Read archived endpoints and certificates only; quantify paired effects and check witnesses."""
import csv
import gzip
import hashlib
import io
import json
import math
import tarfile
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARC=ROOT/"archive"
OUT=ROOT/"analysis"
DEV=("A02","A06","C10","C11")
def read(p):return json.loads(p.read_bytes())
def write(name,rows):
    if not rows:return
    with (OUT/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def lines(f):return [json.loads(s) for s in f.read_bytes().splitlines() if s.endswith(b"}")]
def main():
    OUT.mkdir(exist_ok=True)
    with (ARC/"endpoints.csv").open() as f:
        pts={(r["cell"],r["stage"]):r for r in csv.DictReader(f)}
    basic=read(ARC/"gate.json");budget=read(ARC/"budget.json")
    plans={};certs={}
    for tar in sorted((ARC/"physical").glob("*.tar.gz")):
        with tarfile.open(tar,"r|gz") as file:
            for member in file:
                key,name=member.name.split("/")
                if name=="plan.json":
                    b=file.extractfile(member).read()
                    assert hashlib.sha256(b.strip()).hexdigest()==key
                    plans[key]=json.loads(b)
                elif name=="certificate.json":certs[key]=json.load(file.extractfile(member))
    assert len(plans)==len(certs)==budget["unique_physical"]
    # Read-only sufficient evidence of conservatism: current certified SAFE paths
    # whose own main-stage completion could not survive the uniform reserve.
    base=R.parent
    reg=base/"m1i_generalization/registration"
    cfgdir=base/"m1_transient_thermal_quota_20261126/frozen/p1/config"
    duration={}
    for filename,u in (("gpu_profiles.csv",2),("cpu_npu_profiles.csv",3)):
        for row in csv.DictReader((cfgdir/filename).open()):
            unit=1 if row["stage"].endswith(".post") else u
            duration[row["stage"],unit,int(row["k"])]=int(row["ticks"])
    inputs={}
    for obj in read(reg/"cases.json")["cases"]:
        if obj["ambient"]!=35:continue
        path=reg/"inputs"/obj["input"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==obj["input_sha256"]
        inputs[obj["case"]]=list(csv.DictReader(path.open()))
    reserve_examples=[]
    for key,plan in plans.items():
        if certs[key]["metrics"]["status"]!="SAFE":continue
        req=inputs[plan["case"]];margins=[]
        for item,(u,k,start) in zip(req,plan["rows"][1::3]):
            kind=item["kind"]
            margins.append(int(item["deadline_tick"])-duration[kind+".post",1,0]-start-duration[kind+".main",u,k])
        assert len(margins)==len(req) and min(margins)>=0
        reserve_examples.append(dict(plan=key,case=plan["case"],min_unreserved_ticks=min(margins),excluded_requests=sum(s<13 for s in margins)))
    write("reserve_conservatism.csv",reserve_examples)
    def config(key):return [r[:2] for r in plans[key]["rows"][1::3]]
    for (_,stage),r in pts.items():
        d=certs[r["plan"]]["metrics"]
        assert float(r["J"])==d["E_J"] and d["status"]=="SAFE"
        assert d["E_bounds"][0]<=d["E_J"]<=d["E_bounds"][1]
        assert abs(sum(d[v] for v in ("base_J","activity_J","switch_J","external_J","temperature_J"))-d["E_J"])<1e-7
    def ids(a,b):
        x=config(a);y=config(b)
        assert len(x)==len(y)
        return sum(f!=g for (u,f),(v,g) in zip(x,y)),sum(u!=v for (u,f),(v,g) in zip(x,y))
    def point(cell,stage):
        p=pts.get((cell,stage))
        if p:return p
        if stage=="thermal":return point(cell,"ordinary")
        if stage=="ordinary":return pts[cell,"seed"]
        return None
    paired=[];development=[];scheduling=[];dpstats=[]
    for case in DEV:
        cells={arm:"stage1/"+case+"/"+arm for arm in ("dp","adaptive")}
        base=point(cells["dp"],"seed")
        ordinary=point(cells["dp"],"ordinary");heat=point(cells["dp"],"thermal");adaptive=point(cells["adaptive"],"final")
        assert ids(base["plan"],heat["plan"])[1]==0
        development.append(dict(case=case,seed_J=base["J"],adaptive_J=adaptive["J"],ordinary_J=ordinary["J"],heat_J=heat["J"],
            ordinary_changed=ids(base["plan"],ordinary["plan"])[0],thermal_additional_changes=ids(ordinary["plan"],heat["plan"])[0],
            seed_sw=base["switches"],ordinary_sw=ordinary["switches"],thermal_sw=heat["switches"],ordinary_slack=ordinary["slack"],heat_slack=heat["slack"]))
    subjects=sorted({a.split("/")[1] for a,k in pts if a.startswith("stage2/")})
    for case in subjects:
        cells=["stage2/"+case+"/"+m for m in ("NT","ZQ-Beam")]
        if not all((c,"seed") in pts for c in cells):continue
        line=dict(case=case)
        for name,stage in (("seed","seed"),("ordinary","ordinary"),("heat","thermal")):
            a,b=(point(c,stage) for c in cells)
            line.update({name+"_nt":a["J"],name+"_zhou":b["J"],name+"_nt_minus_zhou":float(a["J"])-float(b["J"]),
                         name+"_winner":"NT" if float(a["upper"])<float(b["lower"]) else "Zhou" if float(b["upper"])<float(a["lower"]) else "tie"})
        a,b=(point(c,"seed") for c in cells)
        line["different_device_assignments"]=ids(a["plan"],b["plan"])[1]
        line["requests"]=len(config(a["plan"]))
        for m,cell in zip(("nt","zhou"),cells):
            line[m+"_reference_gain"]=float(line["seed_"+m])-float(line["ordinary_"+m])
            line[m+"_thermal_gain"]=float(line["ordinary_"+m])-float(line["heat_"+m])
            line[m+"_overhead_s"]=point(cell,"final")["wall_s"]
        paired.append(line)
    for log in sorted(ARC.rglob("events.jsonl")):
        cell=str(log.parent.relative_to(ARC))
        events=lines(log);attempt=Counter();per=defaultdict(dict)
        for event in events:
            if event["kind"]=="dp":
                k=event["tag"],event["reserve"]
                per[k]=dict(cell=cell,tag=k[0],thermal=event["thermal"],reserve=k[1],dt=event["elapsed_s"],
                    reachable=sum(sum(s["states"]) for s in event["stats"]),peak=max(s["max_states"] for s in event["stats"]),objective=event["objective"],
                    outcome="no_device_path" if event["objective"] is None else "awaiting_replay")
            if event["kind"] in ("physical","illegal_post"):
                r=per[event["tag"],event["reserve"]]
                r["outcome"]=event.get("status","TIMING");r["slack_ticks"]=event.get("slack_ticks")
                r["plan"]=event.get("plan");r["energy"]=event.get("J")
        dpstats.extend(per.values())
        if not cell.startswith("stage3/"):continue
        for s in (e for e in events if e["kind"]=="nominated"):
            candidates=[]
            for p in s["picks"]:
                t=str(s["turn"])+"-"+str(p["request"])
                result=next((e for e in events if e["kind"]=="joint" and e["tag"]==t),{})
                candidates.append(dict(cell=cell,turn=s["turn"],parent=s["parent"]["plan"],parent_J=s["parent"]["J"],**p,
                    best_plan=result.get("plan"),best_J=result.get("J")))
            scheduling.extend(candidates)
    factors=[]
    for f in read(ARC/"witnesses.json"):
        parent,frequency,joint=(f[k] for k in ("parent","freq_only","joint"))
        c=config(parent["plan"]);n=len(f["direct"])
        assert n==(3 if c[f["request"]][0]==2 else 10)
        assert ids(parent["plan"],joint["plan"])[1]==1 and ids(parent["plan"],frequency["plan"])[1]==0
        assert joint["bounds"][1]<parent["bounds"][0]
        valid=[d for d in f["direct"] if d["status"]!="TIMING"]
        safe=[d for d in valid if d["status"]=="SAFE"]
        for d in safe:assert d["J"]==certs[d["plan"]]["metrics"]["E_J"]
        best_direct=min(safe,key=lambda d:d["J"]) if safe else None
        independent=joint["bounds"][1]<frequency["bounds"][0] and all(joint["bounds"][1]<d["bounds"][0] for d in safe)
        factors.append(dict(cell=f["cell"],tag=f["tag"],request=f["request"],parent_J=parent["J"],parent=parent["plan"],freq_J=frequency["J"],
            joint_J=joint["J"],joint=joint["plan"],gain=parent["J"]-joint["J"],target_opps=n,timing_legal=len(valid),direct_SAFE=len(safe),
            best_direct_J=best_direct["J"] if best_direct else None,best_direct_margin_ticks=max([d["slack_ticks"] for d in f["direct"] if d["status"]=="TIMING"],default=None),
            beats_all=independent,peak_C=joint["peak"],slack_ms=joint["slack"],switches=joint["switches"]))
    write("development.csv",development);write("paired.csv",paired);write("dp_statistics.csv",dpstats)
    write("mapping_nominations.csv",scheduling);write("matched_witnesses.csv",factors)
    totals=dict(recovered=len([r for r in basic["history"] if "plan" in r]),pairs=len(paired),physical=len(plans),attempts=len(dpstats),
                reserve_calls=sum(r["reserve"]==13 for r in dpstats),factorials=len(factors),scientific_core_s=budget["total"])
    (OUT/"verified.json").write_text(json.dumps(totals,indent=2)+"\n")
    print(json.dumps(totals))
if __name__=="__main__":main()
