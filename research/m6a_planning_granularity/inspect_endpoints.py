"""Compare existing winning schedules against common physical boundaries, without a solver."""
import csv
import io
import json
import os
import sys
import tarfile
import time
from collections import defaultdict
from pathlib import Path

def readcsv(path):
    with path.open() as f:return list(csv.DictReader(f))

root=Path(__file__).resolve().parent
def run(nt):
    start=time.monotonic()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    regs=nt/"research/m1i_generalization/registration"
    profiles=nt/"research/m1_transient_thermal_quota_20261126/frozen/p1/config"
    lengths={}
    for filename,unit in (("gpu_profiles.csv",2),("cpu_npu_profiles.csv",3)):
        for r in readcsv(profiles/filename):
            if unit==3 and r["domain"]!="npu":continue
            lengths[r["stage"],unit,int(r["k"])]=int(r["ticks"])
    cases={x["case"].split("_")[0]:x for x in json.loads((regs/"cases.json").read_bytes())["cases"]}
    table=readcsv(root/"tables/results.csv")
    out=[]
    for code,c in cases.items():
        base=[r for r in table if r["case"]==code and r["cut"]=="60" and r["arm"]=="B"]
        if not base:continue
        req=readcsv(regs/"inputs"/c["input"])
        schedules={}
        for r in (r for r in table if r["case"]==code and r["cut"]=="60" and r["arm"] in "BCD" and r["plan"]):
            arm=r["arm"]
            folder=f'formal/{code}/{arm}/native/physical/evidence/{c["case"]}/{r["plan"]}'
            with tarfile.open(root/"evidence"/f"{code}-{arm}.tar.gz") as arc:
                body=json.load(arc.extractfile(folder+"/plan.json"))
            schedules[arm]=body["rows"][1::3]
            assert len(schedules[arm])==len(req)
        for arm,plan in schedules.items():
            result=dict(case=code,arm=arm,requests=len(req),moved_device=0,changed_opp_same_device=0)
            used=defaultdict(set)
            for i,((u,k,t),(base_u,base_k,_)) in enumerate(zip(plan,schedules["B"])):
                release=int(req[i]["release_tick"])
                end=t+lengths[req[i]["kind"]+".main",u,k]
                used[release//10000,u].add(k)
                result["moved_device"]+=u!=base_u
                result["changed_opp_same_device"]+=u==base_u and k!=base_k
                for width in (10000,5000,2500):
                    boundary=(release//width+1)*width
                    field=str(width//10)+"ms"
                    for metric,test in (("unfinished",end>boundary),("waiting",t>=boundary),
                                        ("executing",t<boundary<end)):
                        label=field+"_"+metric
                        result[label]=result.get(label,0)+test
            result["seconds_within_device_opp_change"]=len({j for (j,u),ks in used.items() if len(ks)>1})
            out.append(result)
    dst=root/"tables/common_boundaries.csv"
    with dst.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=out[0],lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    (root/"tables/endpoint-audit.json").write_text(json.dumps(dict(elapsed_single_core_s=time.monotonic()-start,
        source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],units="physical release ticks",
        definition="unfinished counts each request once at its next boundary, including tail entry"),indent=2)+"\n")
if __name__=="__main__":run(Path(sys.argv[1]))

