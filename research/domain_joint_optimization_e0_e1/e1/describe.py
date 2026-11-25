"""Read-only physical decisions for saved witnesses. No search, propagation or solver calls."""
from pathlib import Path
import csv,gzip,hashlib,json,math
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
E1=ROOT/"e1"
DEV=("CPU1","CPU2","GPU","NPU")

def load(path):
    return json.loads(path.read_bytes())

def rows(path):
    return json.loads(gzip.decompress(path.read_bytes()))["rows"]

def order(rs,ids):
    seq=[sorted((t,i) for i,(unit,k,t) in enumerate(rs) if unit==u) for u in range(4)]
    return {(u,i,j) for u,work in enumerate(seq) for (_,i),(_,j) in zip(work,work[1:]) if i in ids or j in ids}

def mapping_order(rs):
    return [tuple(i for t,i in sorted((s,i) for i,(w,k,s) in enumerate(rs) if w==u)) for u in range(4)]

def table(name,records):
    with (E1/name).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator="\n")
        w.writeheader();w.writerows(records)

def check_receipts():
    state=load(ROOT/"execution.json")
    assert state["status"]=="COMPLETE"
    groups=[r for r in state["runs"] if r["phase"]=="E1"]
    assert len(groups)==len({tuple(r["args"]) for r in groups})==24
    assert all(r["exit_code"]==0 and r["elapsed_s"]<=r["cap_s"] for r in state["runs"])
    assert state["compute_s"]<=9000 and state["wall_s"]<=9600
    checkpoint=E1/"numerical_snapshot.json"
    snap=load(checkpoint if checkpoint.exists() else ROOT/"snapshot.json")
    for name,expected in snap["files"].items():
        path=E1/"numerical_decision.md" if checkpoint.exists() and name=="decision.md" else ROOT/name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,name
    observed=Counter();total=0;maximum_gap=0.
    for p in sorted((E1/"logs").glob("*.json")):
        z=load(p);counts=Counter();seen=set()
        with gzip.open(p.with_name(p.stem+"_candidates.jsonl.gz"),"rt",encoding="utf8") as f:
            for line in f:
                key,edits,extra,removed,proxy,status,en,peak=json.loads(line)
                assert key not in seen and en[0]<=en[1]
                counts[status]+=1;seen.add(key);maximum_gap=max(maximum_gap,en[1]-en[0])
        assert z["own_plan"] in seen and counts==z["counts"] and len(seen)==z["independent_candidates"]
        observed.update(counts);total+=len(seen)
    for p in (E1/"plans").glob("*.json.gz"):
        assert hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()==p.name.split(".")[0]
    return dict(arm_candidate_evaluations=total,counts=dict(observed),max_candidate_energy_interval_width_J=maximum_gap,
                numeric_snapshot_files=len(snap["files"]),individual_arms=len(groups),source_freeze=load(ROOT/"manifest.json")["freeze"])

def describe():
    receipt=check_receipts()
    inputs=load(ROOT/"manifest.json")
    regs=load(ROOT/"regions.json")["regions"]
    with (E1/"results.csv").open(encoding="utf8") as f:results=list(csv.DictReader(f))
    changes=[];members=[];tight=[];diffs=[]
    for name,r in regs.items():
        if "ids" not in r:continue
        case=r["case"];ids=r["ids"];baseline=inputs["plans"][case]["g3"]
        base=rows(ROOT.parent/"cross_scene_taskflow_diagnostic"/"logs/plans"/(baseline+".json.gz"))
        regional=[z for z in results if z["region"]==name]
        picks=[(z["group"],z["independent_plan"]) for z in regional]
        if case in ("D1","D2"):
            witness=inputs["plans"][case]["historical"]
            picks.append(("v1.1",witness))
        pool=[]
        for label,sha in [("G3",baseline),*picks]:
            loc=E1/"plans"/(sha+".json.gz")
            if label=="G3":loc=ROOT.parent/"cross_scene_taskflow_diagnostic"/"logs/plans"/(sha+".json.gz")
            if label=="v1.1":loc=ROOT.parent/"cross_scene_taskflow_followup"/"results/plans"/(sha+".json.gz")
            actual=rows(loc)
            assert len(base)==len(actual) and all(a==b for i,(a,b) in enumerate(zip(base,actual)) if i not in ids)
            differences=[]
            for i in ids:
                u,k,t=actual[i];v,h,s=base[i]
                if (u,k,t)!=(v,h,s):
                    differences.append(dict(stage=i,from_unit=DEV[v],unit=DEV[u],from_opp=h,opp=k,
                                      from_tick=s,tick=t,shift_ms=(t-s)/10))
            before=order(base,ids);after=order(actual,ids)
            def edges(es):
                return [[DEV[u],i,j] for u,i,j in sorted(es)]
            changes.append(dict(region=name,case=case,solution=label,plan=sha,changes=differences,
                              removed_edges=edges(before-after),added_edges=edges(after-before)))
            # Every endpoint already passed the common timing/gap checks in its origin domain.
            allowed=[base==actual, mapping_order(base)==mapping_order(actual),all(a[0]==b[0] for a,b in zip(base,actual)),True]
            if label in ("v1.1","G3"):
                replay=next(z for z in load(ROOT/"e0/replay.json") if z["case"]==case and z["historical"]==(label=="v1.1"))
                assert allowed==replay["membership"] or label=="v1.1" and not replay["membership"][-1]
                sha=replay["normalized_sha"]
                if not replay["membership"][-1]:allowed=[False]*4
            else:assert allowed[int(label[1:])]
            met=load(E1/"certificates"/(sha+".json"))["metrics"]
            assert met["status"]=="SAFE" and allowed==sorted(allowed)
            pool.append((label,sha,met,allowed));members.append(dict(region=name,origin=label,sha=sha,
                                    **{f"P{g}":allowed[g] for g in range(4)}))
        winners=[]
        for g,z in enumerate(regional):
            label,k,met,_=min((entry for entry in pool if entry[3][g]),key=lambda entry:entry[2]["E_bounds"][1])
            lo,hi=met["E_bounds"];lb=float(z["true_L_J"])
            assert lb<=hi<=float(z["true_U_J"])+1e-13
            tight.append(dict(region=name,group=z["group"],true_L_J=lb,true_U_J=hi,point_J=met["E_J"],origin=label,sha=k))
            winners.append((lb,k,met))
            if g:
                old_l,old_k,old_m=winners[g-1]
                left=max(0.,math.nextafter(old_l-hi,-math.inf))
                right=max(0.,math.nextafter(old_m["E_bounds"][1]-lb,math.inf))
                if left>0:status="已证严格额外节能"
                elif right<=inputs["tolerance_J"]:status="已证改善不超过容差"
                elif hi<old_m["E_bounds"][0]:status="观察到额外节能"
                else:status="有限搜索未发现改善"
                diffs.append(dict(region=name,change=f"P{g-1}→P{g}",lower_J=left,upper_J=right,
                                  observed_J=old_m["E_J"]-met["E_J"],status=status))
    path=E1/"decision_changes.json"
    path.write_text(json.dumps(changes,ensure_ascii=False,indent=2)+"\n",encoding="utf8",newline="\n")
    print(len(changes),"plan comparisons",hashlib.sha256(path.read_bytes()).hexdigest())
    table("endpoint_membership.csv",members);table("endpoint_bounds.csv",tight);table("endpoint_conditional.csv",diffs)
    (E1/"receipt_audit.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8",newline="\n")

if __name__=="__main__":describe()
