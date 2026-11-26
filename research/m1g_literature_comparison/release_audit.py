"""Export the post-registered admission sensitivity separately from the main batch."""
import csv
import json
import tarfile
from statistics import mean,median
from audit import DATA,CUTS,read,table,verify
import numpy as np
from experiment import inputs,case_for
from m1g_diagnostics import windowed
from release_control import RAW

def main():
    with (DATA/"checkpoints.csv").open() as f:
        primary={(r["case"],int(r["budget_s"])):r for r in csv.DictReader(f) if r["method"]=="NT"}
    endpoints=[];marks=[];calls=[];windows=[];distinct=set()
    with tarfile.open(DATA/"release_evidence.tar.gz","w:gz",compresslevel=1) as tar:
        for i,(phase,src) in enumerate(inputs()):
            case=src.stem;n=int(case[1:].split("_")[0]);lane=RAW/f"lane{i%7}"
            for method in ("Z-release","Li-release"):
                path=lane/"runs"/case/(method+".json")
                result=read(path)
                tar.add(path,arcname=case+"/"+method+"/run.json")
                partial=lane/"partial"/case/(method+".json")
                if partial.exists():
                    tar.add(partial,arcname=case+"/"+method+"/partial.json")
                for r in result["stages"]:
                    calls.append(dict(case=case,method=method,**r))
                    key=case+"/"+r["plan"]
                    if key not in distinct:
                        folder=lane/"evidence"/key
                        cert,plan,h,shape=verify(folder,case,r["plan"],n)
                        with np.load(folder/"trace.npz") as z:
                            split=windowed(case_for(src).p,z["events"],plan["rows"],case,method+"/"+r["stage"])
                        assert abs(sum(row["E_J"] for row in split)-r["E_J"])<1e-7
                        windows.extend(split)
                        for name in ("certificate.json","plan.json","trace.npz"):
                            tar.add(folder/name,arcname=key+"/"+name)
                        distinct.add(key)
                final=result["stages"][-1] if result["stages"] else {}
                endpoints.append(dict(case=case,method=method,final_status=result["final_status"],actual_s=result["actual_s"],
                                      natural_E_J=final.get("E_J"),natural_peak_C=final.get("peak_C"),assigned_stages=result["assigned_stages"],
                                      failure_task=result["failure_task"],failure_stage=result["failure_stage"],
                                      stats=json.dumps(result["stats"])))
                for t in CUTS:
                    safe=[r for r in result["stages"] if r["status"]=="SAFE" and r["t_s"]<=t]
                    b=min(safe,key=lambda r:r["E_J"]) if safe else {}
                    a=primary[case,t]
                    verdict="only_NT" if a["SAFE_J"] else "neither"
                    saving=None
                    if b and a["SAFE_J"]:
                        verdict="win" if float(a["hi"])<b["lo"] else "loss" if b["hi"]<float(a["lo"]) else "tie"
                        saving=100*(b["E_J"]-float(a["SAFE_J"]))/b["E_J"]
                    elif b:
                        verdict="only_base"
                    marks.append(dict(case=case,method=method,budget_s=t,SAFE_J=b.get("E_J"),peak_C=b.get("peak_C"),plan=b.get("plan"),
                                      first_SAFE_s=safe[0]["t_s"] if safe else None,NT_result=verdict,NT_saving_pct=saving))
    table("release_runs.csv",endpoints);table("release_checkpoints.csv",marks)
    if calls:
        table("release_calls.csv",calls)
        table("release_windows.csv",windows)
    summary=[]
    for method in ("Z-release","Li-release"):
        for t in CUTS:
            rows=[r for r in marks if r["method"]==method and r["budget_s"]==t]
            savings=[r["NT_saving_pct"] for r in rows if r["NT_saving_pct"] is not None]
            summary.append(dict(method=method,budget_s=t,SAFE=sum(r["SAFE_J"] is not None for r in rows),
                                **{v:sum(r["NT_result"]==v for r in rows) for v in ("win","tie","loss","only_NT","only_base","neither")},
                                paired_mean=mean(savings) if savings else None,paired_median=median(savings) if savings else None))
    table("release_summary.csv",summary)
    print("runs",len(endpoints),"certificates",len(calls),"distinct",len(distinct))

if __name__=="__main__":
    main()
