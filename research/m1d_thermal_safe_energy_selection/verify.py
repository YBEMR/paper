"""Audit candidate identities, ordering, actual completions, physical traces and freeze."""
import platform
from collections import defaultdict
from itertools import pairwise
import numba
import psutil
import scipy
from study import *
from validation import lockfiles

def unzip(file):
    with gzip.open(file,"rt",encoding="utf8") as f:return json.load(f)

def pool_map(folder,label):
    if label.startswith("V"):
        source=OUT/"validation_inputs"/(label+".csv")
    else:source=M1/"inputs"/(label+".csv")
    with source.open(encoding="utf-8-sig") as f:req=list(csv.DictReader(f))
    kinds=defaultdict(list)
    for r in req:kinds[int(r["release_tick"])//WINDOW].append(int(r["kind"]=="B"))
    def ext(j,act):
        t=np.array(kinds[j],int)
        return Case.extension(t,len(t)-sum(t),sum(t),*act)
    cfgs={digest(b""):b""}
    for v in unzip(folder/"prefix_beam.json.gz"):
        cfg=cfgs[v["parent"]]+ext(v["window"]-1,v["action"])
        assert digest(cfg)==v["id"];cfgs[v["id"]]=cfg
    group={}
    for v in unzip(folder/"pool.json.gz"):
        cfg=cfgs[v["parent"]]+ext(len(kinds)-1,v["action"])
        assert digest(cfg)==v["id"] and v["id"] not in group
        group[v["id"]]=dict(v,config=cfg)
    return group,len(req),len(kinds)*WINDOW+3010

def physical(label,v,n,horizon):
    base=OUT/"physical/evidence"/label/v["plan"]
    raw=(base/"plan.json").read_bytes().rstrip(b"\r\n")
    plan=json.loads(raw)
    assert digest(raw)==v["plan"] and plan["case"]==label and len(plan["rows"])==3*n
    cfg=bytes(k+(10 if u==3 else 0) for u,k,_ in plan["rows"][1::3])
    assert digest(cfg)==v["id"]
    cert=load(base/"certificate.json")
    m=cert["metrics"]
    with np.load(base/"trace.npz",allow_pickle=False) as tr:arr=tr["events"]
    assert arr[0,0]==0 and arr[-1,1]==horizon and np.array_equal(arr[1:,0],arr[:-1,1])
    assert np.all(arr[:,1]>arr[:,0]) and np.max(abs(arr[1:,14:18]-arr[:-1,18:22]))<1.e-10
    assert abs(arr[:,26:30].sum()+m["external_J"]-m["E_J"])<1.e-8 and m["min_deadline_slack_ms"]>=0
    assert abs(m["activity_J"]+m["base_J"]+m["switch_J"]+m["temperature_J"]+m["external_J"]-m["E_J"])<1e-8
    if m["status"]=="SAFE":
        assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
    assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
    return (v["id"],m["status"],m["E_J"],m["E_bounds"],max(m["peak_hi"]),m["min_deadline_slack_ms"],cert["E35_J"])

def audit():
    check_source()
    for name in ("terminal_lock","conditional_lock"):
        for v in load(ROOT/(name+".json")):assert digest((ROOT/v["file"]).read_bytes())==v["Hash"].lower()
    report=[];verified={}; totals=Counter()
    def examine(stage,folder,label,arm,tracks):
        pool,n,horizon=pool_map(folder,label)
        for o in tracks:
            order=ranking(pool,o["method"])
            rec=o["records"]
            assert len(rec)>=16 and [r["id"] for r in rec]==[s["id"] for s in order[:len(rec)]]
            assert all(a["total_s"]<b["total_s"] for a,b in pairwise(rec))
            assert o["rank_s"]+sum(r["cert_s"] for r in rec)<=rec[-1]["terminal_s"]+1e-5
            for i,v in enumerate(rec,1):
                key=(label,v["plan"])
                if key not in verified:verified[key]=physical(label,v,n,horizon)
                ident,status,e,bounds,peak,slack,ref=verified[key]
                assert (v["id"],v["status"],v["E"],v["bounds"],v["peak"],v["slack"])==(ident,status,e,bounds,peak,slack)
                assert abs(ref-v["ref_E"])<1e-8 and abs(v["total_s"]-v["terminal_s"]-o["build_s"])<1e-6 and v["rank"]==i
                report.append(dict(stage=stage,case=label,pool=arm,method=o["method"],**v))
            totals[stage+"_orders"]+=1
        totals[stage+"_pools"]+=1
    for p in sorted((OUT/"terminal").glob("*/*/orders.json")):
        group=load(p);label=p.parent.parent.name
        legacy=next(o for o in group if o["method"]=="legacy")
        before=load(SRC/"data/search"/label/p.parent.name/"result.json")
        assert [v["plan"] for v in legacy["records"][:4]]==[r["plan"] for r in before["certificates"]]
        examine("terminal",p.parent,label,p.parent.name,group)
    assert totals["terminal_pools"]==30 and totals["terminal_orders"]==90
    for p in sorted((OUT/"prefix").glob("*/*/orders.json")):
        examine("prefix",p.parent,p.parent.parent.name,p.parent.name,load(p))
    phase=load(OUT/"terminal_decision.json");freeze=load(OUT/"algorithm_freeze.json")
    assert freeze["code"]==lockfiles()
    if phase["run_stage2"]:
        assert totals["prefix_pools"]==12
        for p in (OUT/"prefix").glob("*/feasible_cost/scores.json.gz"):
            probes=unzip(p.parent/"probes.json.gz")
            for j,rows in enumerate(unzip(p),1):
                for r in rows:
                    s=[z for z in probes if z["window"]==j and z["prefix"]==r["id"]]
                    assert len(s)==3 and sum(z["ok"] for z in s)==r["timed"]
                    good=[z for z in s if z["ok"] and z["projected_peak"]<=80]
                    assert len(good)==r["feasible"] and (r["cost"] is None if not good else abs(r["cost"]-min(z["ref_cost"] for z in good))<1e-9)
    for p in sorted((OUT/"validation").glob("*/trajectories.json")):
        track=load(p);label=p.parent.name
        examine("validation",p.parent/"ordinary",label,"C2",[track["C2"]])
        examine("validation",p.parent/"H_original",label,"H_original",[track["H_legacy"]])
        examine("validation",p.parent/("H_"+freeze["prefix"]),label,"frozen",[track["frozen"]])
    assert totals["validation_orders"]==(24 if freeze["holdout_enabled"] else 0)
    dirs={(p.parent.parent.name,p.parent.name) for p in (OUT/"physical/evidence").glob("*/*/certificate.json")}
    assert dirs==set(verified)
    write_rows(OUT/"certifications.csv.gz",report)
    save(OUT/"verification.json",dict(status="PASS",counts=dict(totals),certifications=len(report),unique_plans=len(verified),
          python=sys.version,numpy=np.__version__,scipy=scipy.__version__,numba=numba.__version__,platform=platform.platform(),
          affinity=psutil.Process().cpu_affinity(),source="44f8d7e2cb79c97391681406e7c03988a983d72e"))
    print("verified",len(report),len(verified),dict(totals),flush=True)

if __name__=="__main__":audit()
