"""Look for an in-domain past crossing even when the complete trajectory later leaves the model."""

import psutil
from shared import *

def inspect_case(k):
    from heat import integrate
    o=cases()[k];root=A/"results"/k;d=HERE/"offline"/k
    f=stack[0].Flow(o["word"],35,o["case"],RAW,A/"registration/inputs"/o["input"])
    b=Builder(f,f.eng);p=f.p
    plans={v["certificate"]["plan_sha256"]:v for v in map(json.loads,gzip.decompress((root/"physical/plans.jsonl.gz").read_bytes()).splitlines())}
    block=trace_reader(root/"physical");proofs={};stats={}
    for m in ("Base","Ordinary","Previous","Source"):
        rows=read(root/f"runs/{m}.json")["certificates"];cache={};recs=[]
        for r in rows:
            if r["phase"] not in ("terminal","repair"):continue
            key=r["plan"];rec=plans[key]
            data=b"".join(block(h) for h in rec["blocks"]);assert sha(data)==rec["trace_sha256"]
            tr=np.frombuffer(data,"<f8").reshape(rec["shape"])
            cfg=u.encoded(row[:2] for row in rec["plan"]["rows"][1::3])
            w=hot(tr)
            if w and w["events_sha256"] not in proofs:
                part=tr[:w["rows"],:14].copy()
                out=integrate(part,p.initial,p.G,p.cap,float(p.ta),np.empty(0,np.int64),True)
                assert min(out[3])>=20 and max(out[2])<=100 and max(out[1])>80
                assert np.array_equal(out[10],tr[:w["rows"],14:])
                proofs[w["events_sha256"]]=dict(source=key,source_status=r["status"],proof=w,
                    prefix=settled_key(cfg,w["tick"],b).hex(),upper=max(out[2]),minimum_lower=min(out[3]))
            prev=cache.get(w["events_sha256"]) if w else None
            if w:cache.setdefault(w["events_sha256"],key)
            assert not w or r["status"]!="SAFE"
            recs.append(dict(plan=key,status=r["status"],proof=w["events_sha256"] if w else None,
                             same_prior_physics=prev,kernel_s=r["kernel_s"]))
        stats[m]=recs
    put(d/"domain_prefixes.json",dict(proofs=proofs,within_run=stats))
if __name__=="__main__":
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    for k in FOCUS:
        if not (HERE/"offline"/k/"domain_prefixes.json").exists():inspect_case(k)
