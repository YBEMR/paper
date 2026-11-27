"""Re-open online certificates, audit every hard exclusion, preserve its physical prefix."""
import gzip

from collections import Counter
from functools import lru_cache
import psutil
from shared import *

def check(k,stack):
    obj=cases()[k];base=HERE/"results"/k;phys=base/"physical";dest=base/"proofs"
    dest.mkdir(exist_ok=True);block=trace_reader(phys)
    pmap={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((phys/"plans.jsonl.gz").read_bytes()).splitlines())}
    f=stack[0].Flow(obj["word"],35,obj["case"],RAW,A/"registration/inputs"/obj["input"]);b=Builder(f,f.eng)
    from heat import integrate
    def trace(key):
        plan=pmap[key];data=b"".join(block(h) for h in plan["blocks"])
        assert sha(data)==plan["trace_sha256"] and sha(u.raw(plan["plan"]))==key
        return np.frombuffer(data,"<f8").reshape(plan["shape"])
    for key in pmap:
        tr=trace(key);cert=pmap[key]["certificate"];m=cert["metrics"]
        if m["status"]=="SAFE":
            cfg=u.encoded(row[:2] for row in pmap[key]["plan"]["rows"][1::3])
            r=stack[3](f,cfg);assert r is not None
            ev=f.eng.build(src.genes(cfg),r)["ev"]
            assert np.array_equal(ev,tr[:,:14]) and m["E_bounds"][0]<=float(tr[:,26:30].sum()+.3*tr[-1,1]/10000)<=m["E_bounds"][1]
            assert tr[:,22:26].max()<=80 and m["min_deadline_slack_ms"]>=0
    @lru_cache(maxsize=150)
    def opened(c,cut):return open_proof(f,c,cut)
    @lru_cache(maxsize=20)
    def complete(c):
        r=stack[3](f,c);assert r is not None
        return f.eng.build(src.genes(c),r)["ev"]
    seen_evidence={};stats={}
    for m in "RPDCH":
        run=read(base/f"runs/{m}.json");cache={};count=Counter();opened_code=None
        delivered=[];returned=[]
        for a in events(base,run):
            if a[0]=="open_start":opened_code=bytes.fromhex(a[1]);cut=a[2]
            if a[0]=="open_done":
                c=bytes.fromhex(a[1]);assert opened_code==c and cut==a[2]
                w,upper,tr=opened(c,cut)
                assert upper==a[3] and w==a[4] and sha(tr.astype("<f8").tobytes())==a[6]
                count["open_exact"]+=1
            if a[0]=="strict_proof":
                prefix=bytes.fromhex(a[1]);w=a[2];origin=a[3]
                if origin=="open":_,_,tr=opened(opened_code,cut);cfg=opened_code
                else:
                    tr=trace(origin);cfg=u.encoded(row[:2] for row in pmap[origin]["plan"]["rows"][1::3])
                assert settled_key(cfg,w["tick"],b)==prefix and hot(tr)==w
                h=w["events_sha256"];part=tr[:w["rows"]]
                if h not in seen_evidence:
                    p=f.p
                    out=integrate(part[:,:14].copy(),p.initial,p.G,p.cap,float(p.ta),np.empty(0,np.int64),True)
                    assert float(min(out[3]))>=20 and max(out[2])<=100 and max(out[1])>80
                    data=part.astype("<f8").tobytes()
                    (dest/(h+".f64.gz")).write_bytes(gzip.compress(data,5,mtime=0))
                    seen_evidence[h]=dict(rows=len(part),cols=31,trace_sha256=sha(data),proof=w)
                cache.setdefault(prefix,(h,part[:,:14].copy()))
            if a[0] in ("branch_skip","terminal_skip"):
                c,pr=map(bytes.fromhex,a[2:4]);h,ev=cache[pr]
                assert c.startswith(pr)
                if a[0]=="terminal_skip":assert np.array_equal(complete(c)[:len(ev)],ev)
                count[a[0]]+=1
            if a[0]=="cert" and a[1]["t"]<=10:
                cert=a[1];ref=pmap[cert["plan"]]["certificate"]["metrics"]
                assert cert["status"]==ref["status"] and cert["J"]==ref["E_J"]
                returned.append(cert)
            if a[0]=="delivered" and a[2]<=10:delivered.append(dict(a[1],t=a[2]))
        assert returned==run["certificates"] and delivered==run["delivered"]
        stats[m]=count
    put(base/"verified.json",dict(physical=len(pmap),proofs=seen_evidence,by_route=stats))
    print("checked",k,len(pmap),len(seen_evidence),flush=True)

if __name__=="__main__":
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    for k in cases():
        if not (HERE/"results"/k/"verified.json").exists():check(k,stack)
