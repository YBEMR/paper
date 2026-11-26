"""Audit the saved runs without generating candidates or invoking the heat evaluator."""
import csv
import gzip
import io
import json
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import platform
import sys
import numpy as np
import numba
import scipy

ROOT = Path(__file__).resolve().parent
DATA = ROOT/"data"
ORDER = ("L640","L800","L320","L480")
ARMS = ("C","D","D-quarter","C2","D2")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_csv(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as s:
        w = csv.DictWriter(s,fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)


def run():
    out = DATA/"audit"
    out.mkdir(exist_ok=True)
    meta = read(ROOT/"inputs/source_manifest.json")
    for name,entry in meta["sources"].items():
        assert sha256((ROOT/"frozen/p1"/name).read_bytes()).hexdigest()==entry["sha256"]
    for case,entry in meta["inputs"].items():
        assert sha256((ROOT/"inputs"/(case+".csv")).read_bytes()).hexdigest()==entry["sha256"]
    for lock in ("protocol_lock","revision_lock"):
        for record in read(DATA/(lock+".json")):
            path = ROOT/record["file"]
            if lock=="protocol_lock" and path.name=="search.py":
                path = ROOT/"versions/v1/search.py"
            assert sha256(path.read_bytes()).hexdigest()==record["Hash"].lower()
    flat,summary,pairs,forks = [],[],[],[]
    for case in ORDER:
        arms = {}
        for arm in ARMS:
            folder = DATA/("e1b" if arm in ("C2","D2") else "e1")/case/arm
            r = read(folder/"result.json")
            with gzip.open(folder/"trials.csv.gz","rt",encoding="utf-8") as s:
                trials=list(csv.DictReader(s))
            parents=defaultdict(list)
            for v in trials:
                parents[(int(v["window"]),v["parent"])].append(tuple(int(v[k]) for k in ("gpu","npu","x","y")))
            assert all(len(v)<=300 and len(v)==len(set(v)) for v in parents.values())
            assert all(max(Counter(a[:2] for a in v).values())<=10 for v in parents.values())
            beam = read(folder/"beam.json")
            ws = sorted(set(int(v["window"]) for v in beam))
            assert all(sum(s["window"]==j for s in beam)<=4 for j in ws)
            counts = Counter(v["result"] for v in trials)
            assert len(trials)==r["proposal_count"] and len(trials)-counts["duplicate"]==r["fifo_count"]
            assert not r["timeout"] and r["total_s"]<=300 and len(r["certificates"])==4
            for v in r["certificates"]:
                evidence=folder/"evidence"/case/v["plan"]
                raw=(evidence/"plan.json").read_bytes().rstrip(b"\r\n")
                assert sha256(raw).hexdigest()==v["plan"]
                plan=json.loads(raw)
                m=read(evidence/"certificate.json")["metrics"]
                trace=np.load(evidence/"trace.npz",allow_pickle=False)["events"]
                assert len(plan["rows"])==3*int(case[1:]) and m["min_deadline_slack_ms"]>=0
                assert m["status"]==v["status"] and m["E_J"]==v["E"] and max(m["peak_hi"])==v["peak"]
                assert np.all(trace[1:,0]==trace[:-1,1]) and np.max(abs(trace[1:,14:18]-trace[:-1,18:22]))<1e-10
                assert trace[0,0]==0 and trace[-1,1]==(int(case[1:])//80)*10000+3010
                assert abs(trace[:,26:30].sum()+m["external_J"]-v["E"])<1e-8
                assert abs(m["activity_J"]+m["base_J"]+m["switch_J"]+m["temperature_J"]+m["external_J"]-v["E"])<1e-8
                assert (v["peak"]<=80) if v["status"]=="SAFE" else True
                flat.append(dict(case=case,arm=arm,rank=v["rank"],status=v["status"],served=v["served"],
                         E_J=v["E"],E_lower=v["E_bounds"][0],E_upper=v["E_bounds"][1],E35_J=v["E35"],
                         peak_upper=v["peak"],peak_lower=v["peak_lo"],hotspot=["CPU1","CPU2","GPU","NPU"][v["hotspot"]],
                         peak_s=v["peak_s"],slack_ms=v["slack_ms"],predicted_peak=v["predicted_peak"],
                         activity_J=m["activity_J"],residency_J=m["base_J"],switch_J=m["switch_J"],
                         temp_J=m["temperature_J"],external_J=m["external_J"],elapsed_s=v["elapsed_s"],plan=v["plan"]))
            safe=[s for s in r["certificates"] if s["status"]=="SAFE"]
            best=min(safe,key=lambda s:s["E"]) if safe else {}
            summary.append(dict(case=case,arm=arm,safe=len(safe),hot=sum(s["status"]=="HOT" for s in r["certificates"]),
                    outside=sum(s["status"]=="OUT_OF_MODEL" for s in r["certificates"]),
                    unresolved=sum(s["status"]=="UNRESOLVED" for s in r["certificates"]),
                    best_safe_J=best.get("E"),best_safe_peak=best.get("peak"),best_sha=best.get("plan"),
                    best_slack=best.get("slack_ms"),min_certified_peak=min(s["peak"] for s in r["certificates"]),
                    first_safe=safe[0]["rank"] if safe else None,first_safe_s=safe[0]["elapsed_s"] if safe else None,
                    proposals=len(trials),fifo=r["fifo_count"],valid=counts["valid"],failed=counts["timing"],duplicate=counts["duplicate"],
                    certificates=len(r["certificates"]),search_s=r["search_s"],total_s=r["total_s"]))
            arms[arm]=(parents,beam,trials)
        for ca,da in (("C","D"),("C","D-quarter"),("C2","D2")):
            pa,ba,_=arms[ca]
            pb,bb,_=arms[da]
            common=sorted(pa.keys()&pb.keys())
            assert (0,sha256(b"").hexdigest()) in common
            assert all(pa[k]==pb[k] for k in common)
            a_sets=defaultdict(set)
            b_sets=defaultdict(set)
            for a in ba:a_sets[a["window"]].add(a["id"])
            for b in bb:b_sets[b["window"]].add(b["id"])
            diff=next((w for w in sorted(a_sets) if a_sets[w]!=b_sets[w]),None)
            pairs.append(dict(case=case,control=ca,treatment=da,common_parent_windows=len(common),
                         shared_actions_checked=sum(len(pa[k]) for k in common),first_different_window=(diff+1 if diff is not None else None)))
            if diff is not None:
                for name,items,other in [(ca,ba,b_sets[diff]),(da,bb,a_sets[diff])]:
                    for s in items:
                        if s["window"]==diff:
                            forks.append(dict(case=case,arm=name,comparison=ca+"/"+da,window=diff+1,rank=s["rank"],
                                shared=s["id"] in other,parent=s["parent"],prefix=s["id"],action=str(s["action"]),
                                ref_score=s["energy"],pred_peak=s["peak"],risk=s.get("risk")))
    write_csv(out/"summary.csv",summary)
    write_csv(out/"terminal_certificates.csv",flat)
    write_csv(out/"paired_permissions.csv",pairs)
    write_csv(out/"first_divergence.csv",forks)
    wc=read(DATA/"e0/window_calibration.json")
    err1=np.array([np.subtract(r["from_actual"],r["true_end"]) for r in wc])
    err2=np.array([np.subtract(r["from_recursive"],r["true_end"]) for r in wc])
    fn=[(r["case"],r["plan"],r["start_tick"],max(r["from_recursive"]),max(r["true_peak_hi"])) for r in wc if max(r["from_recursive"])<=80<max(r["true_peak_hi"])]
    gate=dict(status="PASS",input_cases=4,methods=5,experiments=len(summary),certificate_records=len(flat),
              unique_plans=len({v["plan"] for v in flat}),paired_comparisons=len(pairs),
              common_parent_action_checks=sum(r["shared_actions_checked"] for r in pairs),
              one_window_max_abs_C=float(abs(err1).max()),recursive_max_abs_C=float(abs(err2).max()),
              one_window_mean_abs_C=float(abs(err1).mean()),recursive_mean_abs_C=float(abs(err2).mean()),
              archived_false_safe_windows=fn,python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
              numba=numba.__version__,platform=platform.platform())
    (out/"verification.json").write_text(json.dumps(gate,indent=2),encoding="utf-8")
    print(json.dumps(gate,ensure_ascii=False))


if __name__=="__main__":
    run()
