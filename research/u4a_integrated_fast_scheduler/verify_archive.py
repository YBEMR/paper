"""Read back physical blocks, frozen timing & event models, and candidate identities. Never search."""
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import zlib
import psutil
HERE=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def trace_reader(base):
    info=load(base/"manifest.json")
    index=json.loads(gzip.decompress((base/"block-index.json.gz").read_bytes()))
    parts=[]
    for x in info["parts"]:
        b=(base/x["name"]).read_bytes()
        assert sha(b)==x["sha256"] and len(b)==x["bytes"]
        parts.append(b)
    @lru_cache(maxsize=200)
    def block(h):
        i,start,n=index[h];b=zlib.decompress(parts[i][start:start+n])
        assert sha(b)==h
        return b
    return block
def main():
    cpu=int(os.environ.get("U4_ARCHIVE_CPU","8"))
    psutil.Process().cpu_affinity([cpu])
    os.environ["U3B_RUNS"]=os.environ.get("U4_RUNS",str(HERE))
    sys.path.insert(0,os.environ["U3B_SRC"])
    import worker
    u,np=worker.u,worker.np;stack=u.stack()
    sums=Counter()
    for obj in load(HERE/"registration/cases.json"):
        root=HERE/"results"/obj["id"]
        if not (root/"complete.json").exists():continue
        report=root/"verified.json"
        if report.exists() and "--resume" in sys.argv:sums.update(load(report));continue
        base=root/"physical";block=trace_reader(base)
        case=obj["case"];inp=HERE/"registration/inputs"/obj["input"]
        assert sha(inp.read_bytes())==obj["input_sha256"]
        flow=stack[0].Flow(obj["word"],35,case,HERE,inp)
        assert u.table(flow.p.req)==inp.read_bytes() and flow.p.horizon==obj["horizon_ticks"]
        e=flow.eng
        known={};stats=Counter()
        for s in gzip.decompress((base/"plans.jsonl.gz").read_bytes()).splitlines():
            rec=json.loads(s);body=rec["plan"];cert=rec["certificate"];key=cert["plan_sha256"]
            assert key==sha(u.raw(body)) and key not in known and body["case"]==case
            rows,low=u.decode(body)
            cfg=tuple(r[:2] for r in rows[1::3]);r=e.replay(cfg)
            assert r is not None and len(cfg)==obj["requests"]
            assert rows==[entry for i,(v,k) in enumerate(cfg) for entry in ((0,0,e.ps[i]),(v,k,r["starts"][i]),(1,0,r["posts"][i]))]
            ev,sw,_=stack[1].event_arrays(e.p,rows,low);other,sw2=stack[1].independent_events(e.p,rows,low)
            assert sw==sw2 and u.raw(sw)==u.raw(cert["switches"]) and np.array_equal(ev,other)
            b=b"".join(block(h) for h in rec["blocks"])
            assert sha(b)==rec["trace_sha256"]
            tr=np.frombuffer(b,dtype="<f8").reshape(rec["shape"])
            assert np.array_equal(tr[:,:14],ev) and np.array_equal(tr[:-1,18:22],tr[1:,14:18])
            assert tr[0,0]==0 and tr[-1,1]==e.p.horizon and np.array_equal(tr[:-1,1],tr[1:,0])
            m=cert["metrics"];total=float(tr[:,26:30].sum()+.3*e.p.horizon/10000)
            assert m["E_bounds"][0]<=total<=m["E_bounds"][1] and abs(max(m["peak_hi"])-tr[:,22:26].max())<1e-7
            assert m["min_deadline_slack_ms"]>=0 and (m["status"]!="SAFE" or max(m["peak_hi"])<=80)
            known[key]=(m["E_J"],m["status"],u.encoded(cfg))
            stats["unique_plans"]+=1;stats["event_segments"]+=len(tr)
        assert len(known)==load(root/"complete.json")["unique_plans"]
        @lru_cache(maxsize=40000)
        def ext(j,g,n,x,y):
            kinds=flow.kinds[e.groups[j]]
            return flow.extension(kinds,int(sum(kinds==0)),int(sum(kinds==1)),g,n,x,y)
        for p in sorted((root/"runs").glob("*.json")):
            unit=load(p);cap=unit["receipt"]["cap"];starts={};parents={};nt={sha(b""):b""};chosen=set()
            counts=Counter();eligible=[];in_time_certs=[]
            last_cert=None
            for name in unit["journal"]:
                payload=gzip.decompress((root/name).read_bytes());assert sha(payload)==Path(name).name.split(".")[0]
                for line in payload.splitlines():
                    a=json.loads(line);typ=a[0];counts[typ]+=1
                    if typ=="parent":parents[a[1]]=bytes.fromhex(a[2])
                    elif typ=="q4_action":
                        _,pi,j,pair,quota,delta,t=a
                        cfg=parents[pi]+ext(j,*pair,*quota)
                        if len(cfg)==e.n and t[-1]==0:chosen.add(cfg)
                    elif typ=="native_action":
                        _,pi,j,pair,quota,s,t=a
                        assert bytes.fromhex(s)==ext(j,*pair,*quota)
                    elif typ=="choice":assert bytes.fromhex(a[3]) in chosen
                    elif typ=="nt_actions":
                        j,pk,g,n,x,y,k=a[2][:7]
                        cfg=nt[pk]+ext(j-1,g,n,x,y)
                        assert sha(cfg)==k
                        if a[2][9]=="valid":nt[k]=cfg
                    elif typ=="nt_terminals":
                        assert all(nt[k].hex()==code for k,code in a[2])
                    elif typ=="group_pool":
                        parent=bytes.fromhex(a[1])
                        for c,ids,unitid,opp in a[2]:
                            changed=bytearray(parent)
                            for i in ids:changed[i]=opp+10*(unitid==3)
                            assert changed.hex()==c
                    elif typ=="cert_start":starts[a[1]]=bytes.fromhex(a[4])
                    elif typ=="cert":
                        v=a[1];last_cert=v
                        if v["t"]<=cap:
                            rec=known[v["plan"]];assert rec[:2]==(v["J"],v["status"])
                            if v["n"] in starts:assert rec[2]==starts[v["n"]]
                            in_time_certs.append(v)
                    elif typ=="delivered" and a[2]<=cap:
                        assert a[1]==last_cert and last_cert["status"]=="SAFE"
                        eligible.append(dict(a[1],t=a[2]))
            assert dict(counts)==unit["counts"] and eligible==unit["delivered"] and in_time_certs==unit["certificates"]
            stats.update(dict(cells=1,nt_actions=counts["nt_actions"],q4_actions=counts["q4_action"]+counts["native_action"],
                              completed_certificates=len(in_time_certs)))
        if report.exists():
            assert load(report)==dict(stats)
        else:
            report.write_bytes((json.dumps(stats,sort_keys=True)+"\n").encode())
        sums.update(stats)
        print("verified",obj["id"],stats["unique_plans"],flush=True)
    print(dict(sums),flush=True)
if __name__=="__main__":main()
