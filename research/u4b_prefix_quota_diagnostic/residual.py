"""Post-audit adjudication of recorded terminal schedules without a reusable past violation."""
import psutil
from shared import *
from archive_results import pack

def run(k):

    obj=cases()[k];dest=HERE/"offline"/k;root=A/"results"/k
    t=read(dest/"terminal_evidence.json")
    missing=[s for s in t["complete"] if not s["matches"]]
    if not missing:put(dest/"residual.json",[]);return
    srcphys=root/"physical"
    plans={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((srcphys/"plans.jsonl.gz").read_bytes()).splitlines())}
    inp=A/"registration/inputs"/obj["input"]
    work=RAW/"offline_residual";f=stack[0].Flow(obj["word"],35,obj["case"],work,inp);e=f.eng
    pack.DEST=HERE/"offline";phy=pack.Physics(k);records=[]
    for s in missing:
        cfg=bytes.fromhex(s["config"]);r=stack[3](f,cfg);assert r is not None
        built=e.build(src.genes(cfg),r)
        key=sha(u.raw(dict(case=obj["case"],rows=built["rows"],low=sorted(built["low"]))))
        if key in plans:
            cert=plans[key]["certificate"];origin="frozen full certificate"
        else:
            cert,tr=e.cert(src.genes(cfg),r,built)
            assert cert["plan_sha256"]==key
            phy.add(work/"evidence"/obj["case"]/key,obj)
            origin="offline new full certificate"
        records.append(dict(rank=s["rank"],plan=key,origin=origin,metrics=cert["metrics"]))
    phy.close();put(dest/"residual.json",records)
    print(k,"remaining",len(records),"new certificates",len(phy.plans),flush=True)
if __name__=="__main__":
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    for k in FOCUS:
        if not (HERE/"offline"/k/"residual.json").exists():run(k)
