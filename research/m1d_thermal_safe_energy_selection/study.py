"""M1-d shared runtime. Blind planning and continuous certification."""
import csv
import gzip
import json
import os
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parent
OUT=Path(os.environ.get("M1D_OUTPUT",ROOT/"data")).resolve()
SRC=next(p for p in (ROOT.parent/"M1c_quota_20261126",ROOT.parent/"m1c_transient_thermal_quota_20261126") if (p/"run.py").exists())
os.environ["M1C_OUTPUT"]=str(OUT.parent/".m1d-scratch"/"stage")
sys.path.insert(0,str(SRC))
from common import CASES,M1,OLD,Case,WINDOW,digest,diverse,initial,load,materialize,np,p1,save,verify_inputs,window_types,write_rows
from expand import expand
from retain import retain
from run import gzjson,env_case,FIELDS

def check_source():
    raw=(SRC/"SHA256SUMS").read_bytes()
    assert digest(raw)=="b17bbc3446510040337cd4c4d350f38f9a7fd683a41481a0fbad56ab33ce0510"
    for line in raw.decode().splitlines():
        h,f=line.split("  ",1)
        assert digest((SRC/f).read_bytes())==h,f
    verify_inputs()

def case_for(label):
    c=env_case(label)
    c.eng.out=OUT/"physical"
    return c

def ranking(pool,method):
    energy=lambda s:(round(s["energy"],11),s["config"])
    ordered=sorted(pool.values(),key=energy)
    if method=="energy":return ordered
    if method=="legacy":
        top=diverse(ordered,True);ids={s["id"] for s in top}
        return top+[s for s in ordered if s["id"] not in ids]
    assert method=="safe_energy"
    return sorted(ordered,key=lambda s:(s["peak"]>80,max(0.,s["peak"]-80),*energy(s)))

def build(c,gen,rule,policy=retain):
    rows=[];beam=[];scores=[];forecasts=[];counts=Counter();stages=[]
    start=perf_counter(); states=[initial(c)]
    for j in range(c.windows):
        tick=perf_counter()
        pool,expired=expand(c,j,states,gen,gen!="O",counts,rows)
        built=perf_counter()
        assert pool and not expired
        if j+1!=c.windows:
            states,metrics=policy(c,j,list(pool.values()),rule,counts,forecasts)
            scores.append(metrics)
            beam.extend(dict(window=j+1,rank=i,**{k:v for k,v in s.items() if k!="config"}) for i,s in enumerate(states,1))
        stages.append(dict(window=j+1,valid=len(pool),generation_s=built-tick,retain_s=perf_counter()-built))
    spent=perf_counter()-start
    return pool,dict(build_s=spent,stages=stages,counts=dict(counts)),(rows,beam,scores,forecasts)

def raw_pool(folder,pool,info,raw,full=True):
    folder.mkdir(parents=True,exist_ok=True)
    save(folder/"build.json",info)
    rows,beam,scores,forecasts=raw
    gzjson(folder/"prefix_beam.json.gz",beam)
    gzjson(folder/"pool.json.gz",[{k:s[k] for k in ("id","parent","action","energy","peak","risk","drain","slack")} for s in pool.values()])
    if full:
        gzjson(folder/"scores.json.gz",scores);gzjson(folder/"probes.json.gz",forecasts)
        with gzip.open(folder/"actions.csv.gz","wt",newline="",encoding="utf8") as f:
            writer=csv.writer(f);writer.writerow(FIELDS);writer.writerows(rows)

def certify_order(c,pool,method,build_s,limit=16,wall=0.):
    start=perf_counter(); ranked=ranking(pool,method)
    rank_s=perf_counter()-start
    rec=[]
    for i,s in enumerate(ranked,1):
        tick=perf_counter()
        cert,_=c.certify(s["config"])
        stop=perf_counter()
        assert abs(s["energy"]-cert["E35_J"])<1e-8
        m=cert["metrics"]
        rec.append(dict(rank=i,id=s["id"],plan=cert["plan_sha256"],prediction=s["peak"],ref_E=s["energy"],
                    E=m["E_J"],bounds=m["E_bounds"],status=m["status"],peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],
                    cert_s=stop-tick,terminal_s=stop-start,total_s=build_s+stop-start))
        if i>=limit and build_s+stop-start>=wall:break
    return dict(method=method,build_s=build_s,rank_s=rank_s,wall_s=build_s+perf_counter()-start,records=rec)

def winner(rows):
    safe=[r for r in rows if r["status"]=="SAFE"]
    return min(safe,key=lambda r:r["E"]) if safe else {}

def outcome(rows):
    w=winner(rows); first=next((r for r in rows if r["status"]=="SAFE"),{})
    return dict(n=len(rows),safe=sum(r["status"]=="SAFE" for r in rows),best=w.get("E"),plan=w.get("plan"),
                first=first.get("rank"),first_s=first.get("total_s"),first_terminal_s=first.get("terminal_s"),
                elapsed=rows[-1]["total_s"] if rows else None)

def pool_check(c,folder,pool,raw,legacy):
    with gzip.open(folder/"candidates.csv.gz","rt") as f:
        prev=[r for r in csv.DictReader(f) if int(r["window"])==c.windows]
    new=[r for r in raw[0] if r[0]==c.windows]
    assert len(prev)==len(new)
    for x,y in zip(prev,new):
        assert (x["parent"],x["config"],x["result"],*(int(x[k]) for k in ("g","n","x","y")))==(y[1],y[6],y[9],*y[2:6])
        if x["result"]=="valid":
            assert (float(x["cost"]),float(x["peak"]))==(pool[x["config"]]["energy"],pool[x["config"]]["peak"])
    saved=load(folder/"result.json")["certificates"]
    assert [v["plan"] for v in saved]==[v["plan"] for v in legacy["records"][:4]]

def stage_one():
    check_source()
    n=0
    for label in CASES:
        c=case_for(label)
        for folder in sorted((SRC/"data/search"/label).iterdir()):
            dest=OUT/"terminal"/label/folder.name
            n+=1
            if (dest/"orders.json").exists():continue
            gen,rule=folder.name.split("_",1)
            pool,info,raw=build(c,gen,rule)
            legacy=certify_order(c,pool,"legacy",info["build_s"])
            result=[legacy]
            cutoff=legacy["records"][-1]["total_s"]
            for method in (("energy","safe_energy") if n%2 else ("safe_energy","energy")):
                result.append(certify_order(c,pool,method,info["build_s"],wall=cutoff))
            pool_check(c,folder,pool,raw,legacy)
            raw_pool(dest,pool,info,raw,False);save(dest/"orders.json",result)
            print(label,folder.name,len(pool),[(r["method"],winner(r["records"][:16]).get("E")) for r in result],flush=True)

if __name__=="__main__":stage_one()
