"""Validate timing and evidence, export calls, staircases and independently replayable certificates."""
import base64
import csv
import gzip
import hashlib
import json
import tarfile
from pathlib import Path
from statistics import mean,median
import numpy as np
from batch import RAW,ROOT
from experiment import inputs, METHODS, OUT

DATA=ROOT/"data"
CUTS=(10,30,60)


def read(path):
    return json.loads(path.read_bytes())


def table(name,rows):
    path=DATA/name
    opener=gzip.open if name.endswith(".gz") else open
    with opener(path,"wt",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify(folder,case,plan,count):
    body=(folder/"plan.json").read_bytes().strip()
    assert hashlib.sha256(body).hexdigest()==plan
    payload=json.loads(body)
    assert payload["case"]==case and len(payload["rows"])==3*count
    cert=read(folder/"certificate.json")
    assert cert["plan_sha256"]==plan
    m=cert["metrics"]
    with np.load(folder/"trace.npz",allow_pickle=False) as pack:
        ar=pack["events"]
    assert ar[0,0]==0 and ar[-1,1]==count//80*10000+3010
    assert np.all(ar[:,0]<ar[:,1]) and np.array_equal(ar[1:,0],ar[:-1,1])
    assert np.allclose(ar[1:,14:18],ar[:-1,18:22],rtol=0,atol=1e-9)
    assert np.allclose(ar[:,22:26].max(axis=0),m["peak_hi"],rtol=0,atol=1e-7)
    assert abs(ar[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8
    assert abs(cert["E35_J"]+m["temperature_J"]-m["E_J"])<1e-8
    assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1] and m["min_deadline_slack_ms"]>=0
    if m["status"]=="SAFE":
        assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
    return cert,payload,hashlib.sha256(ar.tobytes()).hexdigest(),ar.shape


def calls_for(run,baseline):
    if not baseline:
        return run["stages"]
    result=[]
    for n,r in enumerate(run["records"],1):
        c=r["cert"]
        m=c["metrics"]
        result.append(dict(stage="W"+str(r["width"]),elapsed_s=r["end_s"],start_s=r["start_s"],
                           cert_s=r["cert_s"],rank=r["rank"],plan=c["plan_sha256"],status=m["status"],
                           E_J=m["E_J"],lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                           peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"]))
    return result


def main():
    evidence=DATA/"certificates"
    evidence.mkdir(parents=True,exist_ok=True)
    checkpoints=[]; all_calls=[]; runs=[]; updates=[]; phases=[]; stage_log=[]
    count_unique=count_raw=0
    for i,(phase,src) in enumerate(inputs()):
        case=src.stem; nreq=int(case.split("_")[0][1:])
        lane=RAW/f"lane{i%7}"
        assert (lane/"engine/validation_inputs"/src.name).read_bytes().splitlines()==src.read_bytes().splitlines()
        literature=lane/"literature"
        unique=set()
        archived=set()
        with gzip.open(evidence/(case+".jsonl.gz"),"wt",encoding="utf8") as out, tarfile.open(evidence/(case+"_literature.tar.gz"),"w:gz",compresslevel=1) as tar:
            def archive(folder,filename):
                if filename not in archived:
                    tar.add(folder,arcname=filename,recursive=False)
                    archived.add(filename)
            for method in METHODS:
                baseline=method in ("NT","C2")
                raw=read(lane/"engine/runs"/case/method/"run.json") if baseline else read(literature/"standalone"/case/(method+".json"))
                individual=calls_for(raw,baseline)
                assert all(a["elapsed_s"]<=b["elapsed_s"] for a,b in zip(individual,individual[1:]))
                if baseline:
                    assert raw["budget_s"]==60 and raw["wall_s"]>=60.
                    stage_log.extend(dict(case=case,method=method,**s) for s in raw["stages"])
                else:
                    archive(literature/"standalone"/case/(method+".json"),method+"/run.json")
                    part=literature/"partial"/case/(method+".json")
                    if part.exists():
                        archive(part,method+"/partial.json")
                best=None
                for call,r in enumerate(individual,1):
                    plan=r["plan"]; time=r["elapsed_s"]
                    folder=((lane/"engine/physical") if baseline else literature)/"evidence"/case/plan
                    if not baseline:
                        for name in ("plan.json","certificate.json","trace.npz"):
                            archive(folder/name,plan+"/"+name)
                    # Native execution may produce the same physical plan under a second method.
                    if plan not in unique:
                        cert,payload,digest,shape=verify(folder,case,plan,nreq)
                        evidence_row=dict(case=case,plan=plan,certificate=cert,event_array_sha256=digest,shape=shape)
                        if baseline:
                            cfg=bytes(k+(10 if u==3 else 0) for u,k,t in payload["rows"][1::3])
                            evidence_row["config_b64"]=base64.b64encode(cfg).decode()
                        else:
                            evidence_row["payload"]=payload
                        out.write(json.dumps(evidence_row,ensure_ascii=False,separators=(",",":"))+"\n")
                        unique.add(plan)
                    assert read(folder/"certificate.json")["metrics"]["E_J"]==r["E_J"]
                    count_raw+=1
                    all_calls.append(dict(case=case,method=method,call=call,stage=r["stage"],t_s=time,start_s=r.get("start_s"),
                                          cert_wall_s=r.get("cert_s"),rank=r.get("rank"),within_60=time<=60,status=r["status"],
                                          E_J=r["E_J"],lo=r["lo"],hi=r["hi"],peak_C=r["peak_C"],slack_ms=r["slack_ms"],plan=plan))
                    if r["status"]=="SAFE" and time<=60 and (best is None or r["E_J"]<best["E_J"]):
                        best=r
                        updates.append(dict(case=case,method=method,t_s=time,stage=r["stage"],E_J=r["E_J"],peak_C=r["peak_C"],plan=plan))
                for cut in CUTS:
                    done=[r for r in individual if r["elapsed_s"]<=cut]
                    safe=[r for r in done if r["status"]=="SAFE"]
                    chosen=min(safe,key=lambda r:r["E_J"]) if safe else {}
                    checkpoints.append(dict(phase=phase,case=case,method=method,budget_s=cut,calls=len(done),safe_calls=len(safe),
                                first_SAFE_s=safe[0]["elapsed_s"] if safe else None,SAFE_J=chosen.get("E_J"),lo=chosen.get("lo"),
                                hi=chosen.get("hi"),peak_C=chosen.get("peak_C"),slack_ms=chosen.get("slack_ms"),plan=chosen.get("plan"),
                                actual_stop_s=raw["wall_s"]))
                final=individual[-1] if individual and not baseline else {}
                runs.append(dict(phase=phase,case=case,method=method,actual_s=raw["wall_s"],calls=len(individual),
                          final_status=raw.get("final_status","BUDGET"),natural_E_J=final.get("E_J"),natural_peak_C=final.get("peak_C"),
                          natural_plan=final.get("plan"),missing_stages=raw.get("missing_stages"),stats=json.dumps(raw.get("stats",{}))))
        count_unique+=len(unique)
        phases.append(read(lane/"environment.json"))
        print(case,len(unique),flush=True)
    paired=[]; summary=[]
    for cut in CUTS:
        points={(r["case"],r["method"]):r for r in checkpoints if r["budget_s"]==cut}
        for other in METHODS[1:]:
            sub=[]
            for phase,src in inputs():
                a=points[src.stem,"NT"];b=points[src.stem,other]
                if a["SAFE_J"] is None or b["SAFE_J"] is None:
                    verdict="only_NT" if a["SAFE_J"] is not None else "only_base" if b["SAFE_J"] is not None else "neither"
                    saving=None
                else:
                    verdict="win" if a["hi"]<b["lo"] else "loss" if b["hi"]<a["lo"] else "tie"
                    saving=100*(b["SAFE_J"]-a["SAFE_J"])/b["SAFE_J"]
                sub.append(dict(phase=phase,case=src.stem,base=other,budget_s=cut,result=verdict,saving_pct=saving))
            paired.extend(sub)
            for group in ("all","development8","former_holdout6"):
                selected=[r for r in sub if group=="all" or r["phase"]==group]
                values=[r["saving_pct"] for r in selected if r["saving_pct"] is not None]
                summary.append(dict(sample=group,base=other,budget_s=cut,paired=len(values),
                                  **{s:sum(r["result"]==s for r in selected) for s in ("win","tie","loss","only_NT","only_base","neither")},
                                  mean_saving_pct=mean(values) if values else None,median_saving_pct=median(values) if values else None))
    table("calls.csv.gz",all_calls);table("improvements.csv",updates)
    table("checkpoints.csv",checkpoints);table("runs.csv",runs);table("paired.csv",paired)
    table("summary.csv",summary);table("baseline_stages.csv",stage_log)
    (DATA/"environment.json").write_text(json.dumps(phases[:7],indent=2)+"\n")
    (DATA/"audit.json").write_text(json.dumps(dict(runs=len(runs),cuts=len(checkpoints),actual_calls=count_raw,
          unique_case_plans=count_unique,on_time=sum(r["within_60"] for r in all_calls),improvements=len(updates)),indent=2)+"\n")


if __name__=="__main__":
    main()
