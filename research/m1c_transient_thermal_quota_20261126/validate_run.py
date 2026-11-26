"""Rebuild local first-three selections, check paired pools, certificates and time cutoffs."""
from collections import Counter,defaultdict
from itertools import combinations
import platform
import psutil
import scipy
import numba
from common import *
from audit import evidence
from retain import RULES
from history_check import witness

def best(records):
    good=[v for v in records if v["status"]=="SAFE"]
    return min(good,key=lambda v:v["E"]) if good else {}

def csvread(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def readblob(path):
    with gzip.open(path,"rb") as f:return json.load(f)

def main():
    verify_inputs()
    for lock in ("design_lock","guard_lock"):
        for row in load(ROOT/(lock+".json")):
            file=ROOT/row["name"]
            if sha256(file.read_bytes()).hexdigest()!=row["Hash"].lower():
                file=ROOT/"versions/initial"/row["name"]
            assert sha256(file.read_bytes()).hexdigest()==row["Hash"].lower()
    summary=[];term=[];equal=[];paired=[];paths=[];stages=[];verified=set();initial_equal=0
    report=DATA/"audit"
    for case in CASES:
        c=Case(case,report)
        if case=="L800":
            h,_=witness(c);ref=[digest(materialize(c,h[:j])) for j in range(c.windows+1)]
        loc=DATA/"ordinary"/case
        times=load(loc/"budget.json")
        ordinary=[]
        for wave in sorted(loc.glob("w*/result.json"),key=lambda p:int(p.parent.name[1:])):
            r=load(wave)
            for z in r["certificates"]:
                ordinary.append(dict(**z,width=r["width"]))
            if r["width"]==4:
                old=load(OLD/"data/search"/case/"OC_w4b4/result.json")["certificates"]
                assert [z["plan"] for z in r["certificates"][:4]]==[z["plan"] for z in old]
        assert len(set(v["config"] for v in ordinary))==len(ordinary)
        groups={}
        target_dirs=sorted((DATA/"search"/case).glob("*/result.json"))
        assert len(target_dirs)==(15 if case=="L800" else 5)
        for path in target_dirs:
            d=path.parent;name=d.name;r=load(path);gen=r["generator"];rule=r["rule"];cs=r["certificates"]
            assert r["status"]=="complete" and r["budget"]==r["width"]==4 and len(cs)==4
            assert {s["rank"] for s in cs}=={1,2,3,4}
            if rule=="original":
                arm={"N":"NT_w4b4","H":"HT_w4b4","Hs":"HT_w4b4s"}[gen]
                old=load(OLD/"data/search"/case/arm/"result.json")
                assert [v["plan"] for v in cs]==[v["plan"] for v in old["certificates"]]
            forecasts=readblob(d/"probe_details.json.gz")
            counts=r["counts"]
            assert len(forecasts)==counts.get("look_fifo",0)
            assert sum(len(v["next_moments"] or []) for v in forecasts)==counts.get("look_thermal_steps",0)
            assert 3*counts.get("opp_centers",0)==30*len(forecasts)
            assert sum(v["generation_s"]+v["retention_s"] for v in r["stages"])<=r["before_cert_s"]+.001
            if rule=="guarded":
                assert counts["guard_checks"]==c.windows-1
            min_safe=best(cs)
            inc=next((v for v in cs if v["status"]=="SAFE"),{})
            look_money=sum(v["retention_s"] for v in r["stages"][:-1]) if rule in ("time_energy","suffix","guarded") else 0.
            summary.append(dict(case=case,arm=name,safe=sum(v["status"]=="SAFE" for v in cs),best_J=min_safe.get("E"),
                       peak_C=min_safe.get("peak"),slack_ms=min_safe.get("slack_ms"),plan=min_safe.get("plan"),
                       min_peak_C=min(v["peak"] for v in cs),seconds=r["elapsed_s"],first_safe_s=inc.get("elapsed_s"),
                       generation_fifo=counts["fifo"],look_fifo=len(forecasts),thermal_steps=counts.get("look_thermal_steps",0),
                       centers=counts.get("opp_centers",0),look_s=look_money,design_s=counts.get("probe_design_s",0),
                       look_fifo_s=counts.get("look_fifo_s",0),thermal_s=counts.get("look_thermal_s",0),
                       retention_s=counts["retention_s"],cert_s=sum(v["cert_s"] for v in cs),
                       guard_open=counts.get("guard_opened",0),guard_replace=counts.get("guard_replaced",0)))
            stages.extend([dict(case=case,arm=name,**s) for s in r["stages"]])
            limit=times["cutoffs"][name]
            assert limit==r["elapsed_s"]
            admitted=[v for v in ordinary if v["elapsed_s"]<=limit]
            b=best(admitted)
            equal.append(dict(case=case,arm=name,limit_s=limit,ordinary_completed=len(admitted),
                        ordinary_largest_certified_width=max(v["width"] for v in admitted),ordinary_safe=sum(v["status"]=="SAFE" for v in admitted),
                        ordinary_best_J=b.get("E"),ordinary_plan=b.get("plan"),ordinary_min_peak_C=min(v["peak"] for v in admitted),
                        ordinary_last_complete_s=admitted[-1]["elapsed_s"],ordinary_first_safe_s=next((v["elapsed_s"] for v in admitted if v["status"]=="SAFE"),None),
                        method_best_J=min_safe.get("E")))
            beam=load(d/"beam.json")
            grouped=defaultdict(list)
            with gzip.open(d/"candidates.csv.gz","rt") as f:
                trials=list(csv.DictReader(f))
            for v in trials:grouped[int(v["window"])].append(v)
            cache={digest(b""):b""}; action_sets=defaultdict(list)
            for j in range(1,c.windows+1):
                current=[s for s in beam if s["window"]==j]
                for s in current:
                    cfg=materialize(c,s["history"])
                    assert digest(cfg)==s["id"] and s["parent"] in cache
                    cache[s["id"]]=cfg
                candidates=[];matched=None
                for v in grouped[j]:
                    act=tuple(int(v[k]) for k in ("g","n","x","y"))
                    action_sets[(j,v["parent"])].append(act)
                    if v["result"]!="valid":continue
                    cfg=cache[v["parent"]]+c.extension(*window_types(c,j-1),*act)
                    assert digest(cfg)==v["config"]
                    l=c.ledger(cfg,(j-1)*WINDOW,j*WINDOW if j<c.windows else c.p.horizon,2500,j==c.windows,False)
                    assert l[0] and int(v["slack"])==l[-1]
                    candidates.append(dict(config=cfg,id=v["config"],energy=float(v["cost"]),risk=float(v["risk"]),
                                  drain=max(max(l[2]),max(l[6]+c.args[4][:len(cfg)]))))
                    if case=="L800" and v["config"]==ref[j]:matched=v
                baseline=diverse(sorted(candidates,key=lambda s:(round(s["energy"],11),s["config"])),j==c.windows)
                assert [s["id"] for s in current[:3]]==[s["id"] for s in baseline[:3]]
                if j==c.windows or rule=="original":
                    assert [s["id"] for s in current]==[s["id"] for s in baseline]
                initial_equal+=1
                if case=="L800":
                    reach=(j,ref[j-1]) in action_sets
                    rank=next((v["rank"] for v in current if v["id"]==ref[j]),None)
                    paths.append(dict(arm=name,window=j,reference_generated=bool(matched),parent_reached=reach,rank=rank,
                               reason="retained" if rank else "parent_lost" if not reach else
                                      "terminal_not_certified" if matched and j==c.windows else "pruned" if matched else "not_generated"))
            groups[name]=action_sets
            for v in cs:term.append(dict(case=case,arm=name,**v))
        for a,b in combinations(groups,2):
            if a.split("_")[0]!=b.split("_")[0]:continue
            aa,bb=groups[a],groups[b]
            joint=aa.keys()&bb.keys()
            assert joint and all(aa[k]==bb[k] for k in joint)
            paired.append(dict(case=case,a=a,b=b,same_parent_windows=len(joint),identical_actions=sum(len(aa[k]) for k in joint)))
        for v in ordinary:term.append(dict(case=case,arm="ordinary_w"+str(v["width"]),**v))
    for v in term:
        key=(v["case"],v["plan"])
        if key not in verified:
            evidence(DATA/"physical",*key)
            verified.add(key)
        m=load(DATA/"physical/evidence"/key[0]/key[1]/"certificate.json")["metrics"]
        assert (m["E_J"],m["status"],max(m["peak_hi"]),m["E_bounds"])==(v["E"],v["status"],v["peak"],v["interval"])
    for folder in ("historical","same_pool"):
        for path in (DATA/folder/"evidence/L800").iterdir():evidence(DATA/folder,"L800",path.name)
    reference_labels={(r["full"],r["status"]) for r in csvread(DATA/"historical/splices.csv")}
    checked=0
    for v in csvread(DATA/"same_pool/fixed_suffix_labels.csv"):
        if v["full"] in {k[0] for k in reference_labels}:
            assert (v["full"],v["status"]) in reference_labels
            checked+=1
    for name,rows in (("summary",summary),("terminals",term),("common_parents",paired),("equal_time",equal),("path_from_empty",paths),("timing_by_window",stages)):
        write_rows(report/(name+".csv"),rows)
    save(report/"verification.json",dict(status="PASS",fixed_searches=len(summary),certificates=len(term),
         unique_online_plans=len(verified),prefix_beams_rebuilt=initial_equal,paired_checks=len(paired),
         matching_splice_labels=checked,source_commit="e4cb520305fdf32af11070f81d3ca416fc353751",
         python=sys.version,platform=platform.platform(),numpy=np.__version__,scipy=scipy.__version__,numba=numba.__version__,
         cpu_affinity=psutil.Process().cpu_affinity()))
    print("AUDIT PASS",len(summary),len(term),len(verified),initial_equal,flush=True)

if __name__=="__main__":
    main()
