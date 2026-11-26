"""Pre-run checks. Reproduce old W4 decisions and complete physical certificates."""
import argparse
import csv
import gzip
import io
import json
import os
import tarfile
from pathlib import Path
from time import perf_counter
from design import ROOT, REG, METHODS, write_json, sha

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("case")
    arg=parser.parse_args().case
    out=ROOT/"work"/"preflight"/arg
    os.environ["M1G_RAW"]=str(out/"cache")
    from adapter import Flow,builder,e,h,flow,np
    from heat import integrate
    dest=REG/"checks"
    if arg=="ambient":
        checks=[]
        for item in json.loads((REG/"cases.json").read_bytes())["cases"]:
            c=flow(item,out)
            p=c.p;ta=p.ta
            b=p.idle35;s=p.idle_beta
            residual=p.G@(p.initial-ta)-b-s*(p.initial-35)
            assert max(abs(residual))<1e-12
            signature=[]
            # Apply equal moments to the two independent implementations across each boundary and tail.
            t=p.initial.copy();rows=[];ends=[]
            for tick in list(range(0,c.windows*10000,2500))+[c.windows*10000,c.windows*10000+2500]:
                end=min(tick+2500,p.horizon)
                u=(tick//2500)%4
                moment=np.r_[b.copy(),s.copy()]
                stage=("A.pre","A.post","A.main","B.main")[u]
                _,moment[u],moment[4+u]=p.profile[stage,u,0]
                rows.append([tick,end,*moment,*b])
                t=c.propagate(t,moment,(end-tick)/10000)
                ends.append(t.copy())
            arr=np.asarray(rows,dtype=float)
            ref=integrate(arr,p.initial,p.G,p.cap,float(ta),np.array([],np.int64),True)
            error=float(np.max(np.abs(np.asarray(ends)-ref[-2][:,4:8])))
            assert error<1e-8
            assert arr[0,0]==0 and arr[-1,1]==p.horizon and np.all(arr[1:,0]==arr[:-1,1])
            # Same duration-weighted b35 contributes to the reference energy at every ambient.
            E35=float(np.sum((arr[:,1]-arr[:,0])*(arr[:,2:6].sum(axis=1)+.3))/10000)
            assert abs(E35+sum(ref[9])-ref[0])<1e-8
            checks.append(dict(case=c.label,requests=p.n//3,task_stages=p.n,ta=ta,initial=p.initial.tolist(),
                               boundaries=p.boundaries,horizon=p.horizon,max_end_error_K=error,idle_residual=float(max(abs(residual))),
                               probe_E35_J=E35,probe_continuous_J=ref[0],same_reference_input_sha256=sha(arr.tobytes())))
        for flow_id in {c["flow"] for c in json.loads((REG/"cases.json").read_bytes())["cases"]}:
            ids=[i for i,c in enumerate(json.loads((REG/"cases.json").read_bytes())["cases"]) if c["flow"]==flow_id]
            assert len({checks[i]["same_reference_input_sha256"] for i in ids})==1
        write_json(dest/"ambient.json",checks)
        print("verified ambient",len(checks),flush=True)
        return
    src=ROOT.parent/"m1h_common_beam/data/evidence"/arg
    inp=next(p for _,p in h.inputs() if p.stem==arg)
    c=Flow(arg.split("_")[1],35,arg,out,inp)
    with gzip.open(src/"traces.csv.gz","rt") as f:
        trace={r["plan"]:r for r in csv.DictReader(f)}
    results=[]
    with tarfile.open(src/"runs.tar.xz") as rr,tarfile.open(src/"W4-search.tar") as ss:
        for method in METHODS:
            ref=json.load(rr.extractfile(method+"/run.json"))["records"][:4]
            with gzip.open(ss.extractfile(method+"/w4.json.gz")) as f:stage0=json.load(f)
            stage=dict(actions=[],groups=[],beam=[])
            ordered=builder(method)[0](c,method,4,perf_counter(),float("inf"),stage)
            assert stage["beam"]==stage0["beam"]
            assert len(ordered)==stage0["terminal"]
            assert e.p1.raw(stage["actions"])==e.p1.raw(stage0["actions"])
            for state,r in zip(ordered[:4],ref,strict=True):
                cert,arr=c.certify(state["config"]);plan=cert["plan_sha256"]
                assert state["id"]==r["id"]
                key=lambda v:e.p1.raw({k:x for k,x in v.items() if k!="cert_s"})
                assert key(cert)==key(r["cert"])
                z=out/"evidence"/arg/plan/"trace.npz"
                assert sha(z.read_bytes())==trace[plan]["npz_file_sha256"]
                results.append(dict(method=method,rank=r["rank"],id=state["id"],plan=plan,
                                    E_J=cert["metrics"]["E_J"],status=cert["metrics"]["status"],npz=sha(z.read_bytes())))
    assert len(results)==16
    write_json(dest/(arg+".json"),results)
    print("verified old fixed",arg,flush=True)
if __name__=="__main__":
    main()
