import csv
import gzip
from base import ROOT, M1, Case, load, save, materialize, np
from diagnose import same_events
from events import suffix_events


def main():
    src=ROOT/"data/diagnostic"
    target=ROOT/"data/diagnostic_checks"
    case=Case("L800",target)
    checks=[]
    for summary in sorted(src.glob("*_w*.json")):
        r=load(summary)
        if "timing_legal" not in r:
            continue
        with gzip.open(summary.with_suffix(".csv.gz"),"rt") as stream:
            rows=[v for v in csv.DictReader(stream) if v["peak_hi"]]
        subset=[v for v in rows if v["physical_status"] in ("unresolved","safe_bound")]
        subset.extend([min(rows,key=lambda v:abs(float(v["peak_hi"])-t)) for t in (80.,90.,100.)])
        seen=set()
        for v in subset:
            action=tuple(int(v[k]) for k in ("g","n","x","y"))
            if action in seen:
                continue
            seen.add(action)
            hist=list(r["reference_actions"])
            j=r["window"]-1
            hist[j]=action
            cfg=materialize(case,hist)
            cert,tr=case.certify(cfg)
            m=cert["metrics"]
            l=case.ledger(cfg,0,case.p.horizon,10000,True,False)
            same_events(suffix_events(case,cfg,l,j*10000),tr,j*10000)
            assert abs(float(v["E_J"])-m["E_J"])<1e-6
            assert float(v["peak_lo"])<=max(m["peak_hi"])+1e-8
            assert abs(float(v["peak_hi"])-max(m["peak_hi"]))<1e-5
            assert v["physical_status"]=="unresolved" or {"safe_bound":"SAFE","hot":"HOT","outside":"OUT_OF_MODEL"}[v["physical_status"]]==m["status"]
            checks.append(dict(group=summary.stem,action=action,status=m["status"],E=m["E_J"],
                               peak=max(m["peak_hi"]),plan=cert["plan_sha256"],slack=m["min_deadline_slack_ms"]))
    save(target/"checks.json",checks)
    print("Independent full-plan checks",len(checks),"SAFE",sum(v["status"]=="SAFE" for v in checks))


if __name__=="__main__":
    main()
