"""Static pre-registration only. No scheduler, selector or thermal evaluator is called."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
EXP=HERE.parent/"kim_multidnn_expansion"
def read(p):
    return json.loads(p.read_bytes())
def write(p,value):
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    design=read(HERE/"design.json")
    hist=read(HERE/"history.json")
    assert len(hist["branches"])==32 and len(hist["queries"])==160
    assert all("error" not in row and len(row["commits"])<100 for row in hist["queries"])
    existing=read(HERE.parent/"kim_safety_repair_audit"/"design.json")
    fsm=read(EXP/"expanded_input.json")["fsm"]
    registered=read(EXP/"raw"/"expanded"/"results.json")
    seen={tuple(x["case"]["order"]) for x in registered}
    seen.update(map(tuple,existing["orders"].values()))
    seen.add(tuple(read(HERE.parent/"kim_synthetic_platform_v1"/"experiments.json")["order"]))
    assert seen=={("sc0","sc1","sc2","sc3"),("sc3","sc2","sc1","sc0")}
    checks=[]
    for case in design["holdouts"]:
        order=case["order"]
        assert tuple(order) not in seen and all([a,b] in fsm["edges"] for a,b in zip(order,order[1:]))
        counts=Counter()
        frames=dict(zip(existing["scene_key_order"],case["dwell_frames"]))
        canonical={}
        start=0
        for name,n in frames.items():
            canonical[name]=start
            start+=n
        jobs=[]
        frame=0
        for scene in order:
            for j in range(frames[scene]):
                for a in fsm["active_apps"][scene]:
                    counts[a]+=1
                    jobs.append([f"f{canonical[scene]+j:04d}-a{a}",a,frame*40000000,(frame+1)*40000000])
                frame+=1
        assert frame==250 and counts=={i:125 for i in range(4)} and len(jobs)==len({j[0] for j in jobs})==500
        checks.append(dict(case=case["id"],order=order,frames=frames,count_by_app=counts,tail_ns=40000000,
                          absolute_jobs_sha256=hashlib.sha256(json.dumps(jobs,separators=(",",":")).encode()).hexdigest()))
    write(HERE/"holdout_receipt.json",dict(registered_orders=sorted(seen),holdouts=checks,
        scope="All 32 visible pretrial branch heads, five catalog/workload paths, alternate multi-DNN branch protocol, and baseline case/design registries. Proposal appearances excluded. No matching recorded runs found.",thermal_calls=0))
    caps=Counter()
    for job in design["jobs"]:
        assert job["cap"]<=120
        caps[job["stage"]]+=job["cap"]
    assert dict(caps)=={"e0":130,"fixed":110,"dev":1440,"holdout":2160}
    assert design["fixed_subset"]==read(EXP/"catalog.json")["search_order"][:4]
    files=dict(read(EXP/"freeze_manifest.json")["files"])
    for name,expected in files.items():
        assert sha(ROOT/name)==expected,name
    for spec in read(EXP/"diagnostics/search_mechanism_20261119/input_hashes.json")["arrays"]:
        path=ROOT/spec["path"]
        assert sha(path)==spec["sha256"]
        files[spec["path"]]=spec["sha256"]
    for p in [EXP/"raw/expanded/forward_flat_25C/deployment_C.json",EXP/"raw/expanded/forward_alternating_25C/deployment_D019.json"]:
        files[p.relative_to(ROOT).as_posix()]=sha(p)
    for p in HERE.iterdir():
        if p.is_file() and p.name!="freeze.json":
            if p.suffix==".py":
                ast.parse(p.read_text(encoding="utf-8"))
            files[p.relative_to(ROOT).as_posix()]=sha(p)
    write(HERE/"freeze.json",dict(parent=design["parent"],files=files,domain="81 x 27^4",caps=caps,
        scope="Registered code, inputs, archived overlap verification, protocol and workload evidence."))
    print("Static checks passed",len(files),sha(HERE/"freeze.json"))
if __name__=="__main__":
    main()
