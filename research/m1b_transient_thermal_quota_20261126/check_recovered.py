import csv
import gzip
from base import ROOT,Case,load,save,materialize


if __name__=="__main__":
    src=ROOT/"data/diagnostic"
    dest=ROOT/"data/recovered_checks"
    c=Case("L800",dest)
    verified=[]
    for j in (7,8):
        name=f"recovered_w{j+1}"
        hist=load(src/(name+".json"))["reference_actions"]
        with gzip.open(src/(name+".csv.gz"),"rt") as f:
            for row in csv.DictReader(f):
                if row["physical_status"]!="safe_bound":
                    continue
                actions=list(hist)
                actions[j]=[int(row[k]) for k in ("g","n","x","y")]
                cert,_=c.certify(materialize(c,actions))
                m=cert["metrics"]
                assert m["status"]=="SAFE" and abs(m["E_J"]-float(row["E_J"]))<1e-6
                assert abs(max(m["peak_hi"])-float(row["peak_hi"]))<1e-5
                verified.append(dict(group=name,action=actions[j],origin=row["origin"],status="SAFE",E=m["E_J"],peak=max(m["peak_hi"]),plan=cert["plan_sha256"]))
    save(dest/"checks.json",verified)
    print("Recovered full P1 SAFE certificates",len(verified))
