import csv
import gzip
import json
import platform
import sys
import scipy
import numba
import psutil
import matplotlib
from collections import Counter,defaultdict
from hashlib import sha256
from itertools import combinations
from base import ROOT,M1,np,load,save,check_base

DATA=ROOT/"data"
OUT=DATA/"audit"


def csv_out(name,rows):
    with (OUT/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def evidence(folder,case,sha):
    path=folder/"evidence"/case/sha
    raw=(path/"plan.json").read_bytes().rstrip(b"\r\n")
    assert sha256(raw).hexdigest()==sha
    p=json.loads(raw)
    cert=load(path/"certificate.json")
    m=cert["metrics"]
    with np.load(path/"trace.npz",allow_pickle=False) as f:
        tr=f["events"]
    assert cert["plan_sha256"]==sha and len(p["rows"])==3*int(case[1:]) and p["case"]==case
    assert tr[0,0]==0 and tr[-1,1]==int(case[1:])//80*10000+3010
    assert np.array_equal(tr[:-1,1],tr[1:,0]) and np.max(abs(tr[1:,14:18]-tr[:-1,18:22]))<1e-10
    assert abs(tr[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8 and m["min_deadline_slack_ms"]>=0
    assert abs(m["activity_J"]+m["base_J"]+m["switch_J"]+m["temperature_J"]+m["external_J"]-m["E_J"])<1e-8
    if m["status"]=="SAFE":
        assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20 and m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
    return m


def main():
    OUT.mkdir(exist_ok=True)
    check_base()
    for file,old in (("lock.json","initial"),("supplement_lock.json","supplement"),("screened_lock.json",None)):
        manifest=load(DATA/file)
        by_name={r["file"]:r["Hash"].lower() for r in manifest} if isinstance(manifest,list) else manifest
        for name,sha in by_name.items():
            f=ROOT/name
            if sha256(f.read_bytes()).hexdigest()!=sha:
                assert old is not None
                f=ROOT/"versions"/old/name
            assert sha256(f.read_bytes()).hexdigest()==sha,(name,old)
    summary=[];terminal=[];fair=[]
    for case in ("L800","L640","L480","L320"):
        parents={};results={}
        for folder in sorted((DATA/"search"/case).iterdir()):
            r=load(folder/"result.json")
            results[folder.name]=r
            groups=defaultdict(list)
            counter=Counter()
            with gzip.open(folder/"proposals.csv.gz","rt") as f:
                for v in csv.DictReader(f):
                    groups[(int(v["window"]),v["parent"],int(v["g"]),int(v["n"]))].append((int(v["x"]),int(v["y"])))
                    counter[v["result"]]+=1
            assert all(len(set(v))==len(v)<=10 for v in groups.values())
            assert sum(counter.values())==r["counts"]["proposals"]
            assert all(stage["retained"]<=(r["budget"] if stage==r["stages"][-1] else r["width"]) for stage in r["stages"])
            assert not r["expired"] and r["total_s"]<=300 and len(r["certificates"])==r["budget"]
            parents[folder.name]=groups
            for v in r["certificates"]:
                m=evidence(folder,case,v["plan"])
                assert m["E_J"]==v["E"] and m["status"]==v["status"] and m["E_bounds"]==v["interval"]
                terminal.append(dict(case=case,arm=folder.name,rank=v["rank"],plan=v["plan"],status=v["status"],
                    energy_J=v["E"],lower_J=v["interval"][0],upper_J=v["interval"][1],peak_upper_C=v["peak"],
                    hotspot=("CPU1","CPU2","GPU","NPU")[m["hotspot"]],peak_s=m["peak_tick"][m["hotspot"]]/10000,
                    slack_ms=v["slack"],elapsed_s=v["elapsed"],served=int(case[1:])))
            safe=[s for s in r["certificates"] if s["status"]=="SAFE"]
            best=min(safe,key=lambda s:s["E"]) if safe else {}
            summary.append(dict(case=case,arm=folder.name,width=r["width"],budget=r["budget"],SAFE=len(safe),
                best_J=best.get("E"),best_peak=best.get("peak"),best_slack=best.get("slack"),plan=best.get("plan"),
                first_safe=safe[0]["rank"] if safe else None,first_safe_s=safe[0]["elapsed"] if safe else None,
                min_peak=min(s["peak"] for s in r["certificates"]),proposals=r["counts"]["proposals"],
                fifo=r["counts"]["fifo"],pilot=r["counts"].get("calibration_fifo",0),cheap_time_points=r["counts"].get("cheap_time_points",0),
                valid=counter["valid"],generation_outside_O=r["counts"]["outside_old"],search_s=r["search_s"],total_s=r["total_s"]))
        assert len(results)==13
        for arm_a,arm_b in combinations(results,2):
            aa,bb=parents[arm_a],parents[arm_b]
            shared=aa.keys()&bb.keys()
            assert len(shared)>=30
            assert all(len(aa[k])==len(bb[k]) for k in shared)
            samegen=arm_a[0]==arm_b[0] and arm_a.endswith("s")==arm_b.endswith("s")
            if samegen:
                assert all(set(aa[k])==set(bb[k]) for k in shared),(case,arm_a,arm_b)
            fair.append(dict(case=case,a=arm_a,b=arm_b,shared_parent_frequency_groups=len(shared),
                paired_proposals=sum(len(aa[k]) for k in shared),same_generator=samegen,
                changed_sets=sum(set(aa[k])!=set(bb[k]) for k in shared)))
        for w in (4,8):
            a=results[f"OC_w{w}b4"];b=results[f"OC_w{w}b8"]
            assert [v["plan"] for v in a["certificates"]]==[v["plan"] for v in b["certificates"][:4]]
        for arm,old_arm in (("OC_w4b4","C2"),("OT_w4b4","D2")):
            old=load(M1/"data/e1b"/case/old_arm/"result.json")["certificates"]
            assert [v["plan"] for v in old]==[v["plan"] for v in results[arm]["certificates"]]
    csv_out("case_summary.csv",summary);csv_out("terminal_certificates.csv",terminal);csv_out("paired_action_audit.csv",fair)
    diagnostics=[]
    for folder in sorted((DATA/"diagnostic").glob("*_w*.json")):
        s=load(folder)
        if "timing_legal" not in s:
            assert s["prefix_peak_lower"]>80
            continue
        positive=Counter();total=valid=unresolved=0;keys=set()
        with gzip.open(folder.with_suffix(".csv.gz"),"rt") as f:
            for v in csv.DictReader(f):
                action=tuple(int(v[k]) for k in ("g","n","x","y"))
                assert all(0<=q<=lim for q,lim in zip(action,(9,2,40,60)))
                keys.add(action);total+=1
                valid+=v["physical_status"] not in ("timing","time_bound")
                unresolved+=v["physical_status"]=="unresolved"
                if v["physical_status"]=="safe_bound":
                    assert float(v["peak_hi"])<=80 and int(v["slack_ticks"])>=0
                    positive[v["origin"]]+=1
        assert total==len(keys)==s["actions"]==75030 and valid==s["timing_legal"] and not unresolved
        for v in s["witnesses"]:
            m=evidence(DATA/"diagnostic","L800",v["plan"])
            assert m["status"]==v["status"]=="SAFE" and m["E_J"]==v["E_J"]
        diagnostics.append(dict(group=folder.stem,parent=s["parent"],source=s["source"],window=s["window"],all_actions=total,
              timing_legal=valid,safe=sum(positive.values()),not_generated=positive["not_generated"],
              generated_pruned=positive["generated_pruned"],kept_without_this_certificate=positive["kept_not_full_certified"],
              already_certified=positive["full_certified"],unresolved=unresolved,scope=s["suffix_scope"]))
    csv_out("diagnostic_counts.csv",diagnostics)
    checks=load(DATA/"diagnostic_checks/checks.json")
    for v in checks:
        m=evidence(DATA/"diagnostic_checks","L800",v["plan"])
        assert m["status"]==v["status"] and m["E_J"]==v["E"]
    recovered=load(DATA/"recovered_checks/checks.json")
    for v in recovered:
        m=evidence(DATA/"recovered_checks","L800",v["plan"])
        assert m["status"]==v["status"]=="SAFE" and m["E_J"]==v["E"]
    assert sum(v["status"]=="SAFE" for v in checks)+len(recovered)==sum(r["safe"] for r in diagnostics)
    polish=[]
    for case in ("L480","L640"):
        r=load(DATA/"incumbent"/case/"result.json")
        for gen,group in r["certificates"].items():
            assert len(group)==4
            for v in group:
                m=evidence(DATA/"incumbent"/case,case,v["plan"])
                assert (m["status"]=="SAFE" and m["E_bounds"][1]<r["E0_bounds"][0])==v["strict"]
                polish.append(dict(case=case,gen=gen,source_plan=r["incumbent"],source_J=r["E0"],rank=v["rank"],
                        action=str(v["action"]),plan=v["plan"],status=v["status"],E_J=v["E"],peak=v["peak"],strict=v["strict"]))
    csv_out("incumbent_certificates.csv",polish)
    result=dict(status="PASS",base_commit="500069a9f67ebfcb2c994bd698f3ce5d172755c8",diagnostic_actions=sum(x["all_actions"] for x in diagnostics),
                diagnostic_timing_legal=sum(x["timing_legal"] for x in diagnostics),separate_prefix_hot_proofs=3,
                independent_diagnostic_checks=len(checks)+len(recovered),positive_action_occurrences=sum(r["safe"] for r in diagnostics),
                search_runs=len(summary),terminal_certificates=len(terminal),
                unique_terminal_plans=len({x["plan"] for x in terminal}),pair_comparisons=len(fair),incumbent_certificates=len(polish))
    save(OUT/"verification.json",result)
    save(OUT/"environment.json",dict(platform=platform.platform(),python=sys.version,numpy=np.__version__,
        scipy=scipy.__version__,numba=numba.__version__,psutil=psutil.__version__,matplotlib=matplotlib.__version__))
    print(result)


if __name__=="__main__":
    main()
