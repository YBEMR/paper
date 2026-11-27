"""Read-only arithmetic audit of the already submitted candidates and a capacity relaxation."""
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path

for k in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[k]="1"
import psutil
process=psutil.Process()
process.cpu_affinity(process.cpu_affinity()[:1])
import numpy as np
from scipy.optimize import linprog

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def ascode(plan):return bytes(k+(u==3)*10 for u,k,_ in plan["rows"][1::3])
def csvrows(p):
    with p.open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def write(p, rows):
    with p.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def timing(genes,req,dur):
    free=[0,0];old=[0,0];pre=0;ends=[];q=[];dline=[];ready=[]
    for i,(v,r) in enumerate(zip(genes,req)):
        t=r["kind"];u=int(v>=10);k=v%10
        pre=max(pre,int(r["release_tick"]))+dur[t+".pre",0,0]
        ready.append(pre);q.append(dur[t+".post",1,0]);dline.append(int(r["deadline_tick"]))
        free[u]=max(pre,free[u]+5*(old[u]!=k))+dur[t+".main",u+2,k];ends.append(free[u]);old[u]=k
    post=0;late=[];mainlate=[]
    for i in sorted(range(len(req)),key=lambda j:(ends[j],j)):
        post=max(post,ends[i])+q[i]
        if ends[i]+q[i]>dline[i]:mainlate.append(i)
        if post>dline[i]:late.append((i,post-dline[i]))
    return late,mainlate,ready,q
def structure(req,hist,body):
    m=sum(a!=b for a,b in zip([v//10 for v in hist],[v//10 for v in body]))
    bad=[];mixed=[]
    for window in sorted({int(r["scene"]) for r in req}):
        for dev in (0,1):
            ids=[i for i,r in enumerate(req) if int(r["scene"])==window and body[i]//10==dev]
            for j in range(1,len(ids)):
                i,h=ids[j-1:j+1]
                if body[i]!=body[h]:
                    mixed.append((window,dev,i,h))
                    if int(req[i]["release_tick"])//5000==int(req[h]["release_tick"])//5000:
                        bad.append(dict(window=window+1,device=dev+2,first=i,second=h,k1=body[i]%10,k2=body[h]%10,
                                   release1=int(req[i]["release_tick"]),release2=int(req[h]["release_tick"])))
    return dict(mapping_changes=m,count_window_boundaries=len(mixed),within_half=bad)

def capacity(req,obj,cfg,prof,dur,ready,q):
    # 40 C is a subsolution on every thermal mode. Validate the signs and room at each face.
    g=[[Q(str(v)) for v in row] for row in cfg["G"]];assert all(g[i][j]<=0 for i in range(4) for j in range(4) if i!=j)
    modes={d:[] for d in range(4)}
    for (stage,d,k),v in prof.items():
        modes[d].extend([v[:2],v[2:]])
    low={}
    for d,m in modes.items():
        assert all(beta>=0 for _,beta in m)
        low[d]=min(b+5*s for b,s in m)
        assert low[d]>=5*sum(g[d])
        b,s=prof[("A.pre" if d==0 else "A.post" if d==1 else "A.main"),d,0][:2]
        assert sum(g[d])-s>0 and b>=5*(sum(g[d])-s)
    common=(Q(3,10)+sum(low.values()))*obj["horizon_ticks"]/10000
    for r in req:
        for stage,d in (("pre",0),("post",1)):
            key=r["kind"]+"."+stage,d,0
            b,s=prof[key][2:];common+=(b+5*s-low[d])*dur[key]/10000
    windows=obj["windows"];kinds=[(w,t) for w in range(windows) for t in "AB"]
    n=Counter((int(r["scene"]),r["kind"]) for r in req)
    choices=[(d,k) for d,lev in ((2,10),(3,3)) for k in range(lev)]
    cols=[(w,t,d,k) for w,t in kinds for d,k in choices]
    cost=[]
    for w,t,d,k in cols:
        key=t+".main",d,k;b,s=prof[key][2:]
        cost.append((b+5*s-low[d])*dur[key]/10000)
    eq=np.array([[int((a,b)==(w,t)) for a,b,d,k in cols] for w,t in kinds])
    mat=[];caps=[];labels=[]
    for left in range(windows):
        for right in range(left,windows):
            ids=[i for i,r in enumerate(req) if left<=int(r["scene"])<=right]
            cap=max(int(req[i]["deadline_tick"])-q[i] for i in ids)-min(ready[i] for i in ids)
            for dev in (2,3):
                mat.append([dur[t+".main",d,k] if d==dev and left<=w<=right else 0 for w,t,d,k in cols])
                caps.append(cap);labels.append([left,right,dev])
    kwargs=dict(A_ub=np.array(mat),b_ub=caps,A_eq=eq,b_eq=[n[x] for x in kinds],method="highs",
                options={"threads":1,"parallel":False})
    import warnings
    from scipy.optimize import OptimizeWarning
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore",message="Unrecognized options detected.*",category=OptimizeWarning)
        opt=linprog(np.array(cost,float),**kwargs)
    assert opt.success,opt.message
    # Only the rationalized nonnegative weights are trusted. Recompute the dual lower bound exactly.
    lam=[Q(max(0,round(-v*10**10)),10**10) for v in opt.ineqlin.marginals]
    nonzero=[j for j,x in enumerate(lam) if x]
    dualc=[c+sum(lam[j]*mat[j][i] for j in nonzero) for i,c in enumerate(cost)]
    width=len(choices)
    lb=common+sum(n[key]*min(dualc[i*width:(i+1)*width]) for i,key in enumerate(kinds))-sum(lam[j]*caps[j] for j in nonzero)
    no_cap=common+sum(n[key]*min(cost[i*width:(i+1)*width]) for i,key in enumerate(kinds))
    return dict(floor_J=(lb*10**6).__floor__()/10**6,exact_J=str(lb),constant_J=str(common),
                no_capacity_floor_J=(no_cap*10**6).__floor__()/10**6,
                nonzero_dual=[[labels[j],str(lam[j]),caps[j]] for j in nonzero],
                interval_constraints=len(mat),variables=len(cols))
def main(nt,archive,out):
    start=time.perf_counter()
    out.mkdir(exist_ok=True,parents=True)
    frozen=nt/"m1_transient_thermal_quota_20261126/frozen/p1/config"
    reg=nt/"m1i_generalization/registration";cases=read(reg/"cases.json")["cases"]
    cfg=read(frozen/"p1_frozen.json")
    pins={"p1_frozen.json":"1cde1d8142c6253a0deb4f78dbe6960c7c99fb70","gpu_profiles.csv":"c77aa183d451e7d8cd15e1d0510e8f8bc21f6f40","cpu_npu_profiles.csv":"a6eeae251d0ecd0107601ab8621c3c54ea753aa3"}
    for name,pin in pins.items():
        blob=(frozen/name).read_bytes()
        assert hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()==pin
    prof={};dur={}
    for name in ("gpu_profiles.csv","cpu_npu_profiles.csv"):
        for row in csvrows(frozen/name):
            units=(2,) if name.startswith("gpu") else (3,) if row["domain"]=="npu" else (0,1)
            for d in units:
                key=row["stage"],d,int(row["k"])
                prof[key]=tuple(Q(row[v]) for v in ("idle_W","idle_slope","busy_W","busy_slope"))
                dur[key]=int(row["ticks"])
    bad=[];details={};bounds={};top={}
    for c in ("A02","A06","C10","C11"):
        seed=read(ROOT/"history"/c/"plan.json");orig=ascode(seed)
        obj=next(r for r in cases if r["case"]==seed["case"]);src=reg/"inputs"/obj["input"]
        assert sha(src.read_bytes())==obj["input_sha256"];req=csvrows(src)
        zero,_,ready,q=timing(orig,req,dur);assert not zero
        bounds[c]=capacity(req,obj,cfg,prof,dur,ready,q)
        gen=lambda m:[json.loads(v) for v in (archive/"logs"/c/m/"events.jsonl").read_bytes().splitlines() if v.endswith(b"}")]
        r=next(r for r in gen("E") if r["kind"]=="generation")
        rejects={v["cfg"] for v in gen("E") if v["kind"]=="timing_reject"}
        for item in r["proposals"]:
            meta=item["meta"];w=meta["win"];ids=[i for i,qrow in enumerate(req) if int(qrow["scene"])==w]
            policy=orig[:ids[0]]+bytes.fromhex(meta["patch"])+orig[ids[-1]+1:]
            assert sha(policy)==item["cfg"] and item["cfg"] in rejects
            late,mainlate,_,_=timing(policy,req,dur)
            assert late
            j,l=late[0]
            bad.append(dict(case=c,cfg=item["cfg"],window=w+1,first_late_request=j,
                late_arrival_window=int(req[j]["scene"])+1,first_late_ms=l/10,
                missed=len(late),worst_ms=max(z for _,z in late)/10,main_already_late=len(mainlate),
                first_late_main_feasible=j not in mainlate))
        details[c]={}
        for m in "BCD":
            p=read(archive/"endpoints"/c/m/"plan.json");body=ascode(p)
            st=structure(req,orig,body);st["nominated_in_E"]=sha(body) in rejects
            st["plan_hash"]=sha(json.dumps(p,sort_keys=True,separators=(",",":")).encode())
            details[c][m]=st
        top[c]=dict(covered=sorted(set(i["meta"]["win"]+1 for i in r["proposals"])),windows=obj["windows"],
                   families=dict(Counter(i["meta"]["family"] for i in r["proposals"])),
                   mapped_templates=sum(z["mapping_templates"] for z in r["coverage"]),
                   ranked_pairs=sum(z.get("ranked_option_pairs",0) for z in r["coverage"]))
    write(out/"rejections.csv",bad)
    for k,v in (("structure",details),("capacity_dual",bounds),("nomination",top)):
        (out/(k+".json")).write_bytes(json.dumps(v,indent=1).encode("utf8"))
    (out/"receipt.json").write_text(json.dumps(dict(wall_s=time.perf_counter()-start,cpu_s=time.process_time(),
           affinity=process.cpu_affinity(),search_cells=0,thermal_certificates=0,recorded_proposals=64)))
if __name__=="__main__":main(*map(Path,sys.argv[1:]))
