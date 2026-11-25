"""One-shot serial controller. Numerical workers have process-level wall deadlines."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime,timezone
from assets import CFG,DATA,HERE,digest,encode,read,write

def now(): return datetime.now(timezone.utc).isoformat()
def log(row):
    with (DATA/"calls.jsonl").open("ab") as f:f.write(encode(dict(utc=now(),**row))+b"\n")

def worker(kind,case,num,arm,end,last):
    from diagnostic import preflight,select,search,assessment
    if kind=="preflight":
        preflight()
        patch=subprocess.check_output(["git","diff","--binary",CFG["base"],"HEAD","--","."],cwd=HERE)
        (DATA/"source.patch").write_bytes(patch)
    elif kind=="selection":select(case,end)
    elif kind=="search":search(case,num,end)
    elif kind=="counterfactual":
        assessment(case,num)
        if last:
            from decision import gate
            gate()
    elif kind=="arm":
        search(case,num,end-6,arm)
        assessment(case,num,arm)
    elif kind=="archive":
        from decision import audit
        audit()

def main():
    if DATA.exists():raise RuntimeError("existing batch, no reruns")
    if subprocess.check_output(["git","status","--porcelain"],cwd=HERE).strip():raise RuntimeError("unfrozen source")
    DATA.mkdir()
    start=time.perf_counter()
    global_end=start+CFG["budget_s"]["whole"]
    def call(kind,limit,case="ALL",num=-1,arm="",last=False):
        begin=time.perf_counter()
        end=min(begin+limit,global_end)
        reserve=2.5 if kind in ("search","selection","arm") else 1
        args=[sys.executable,"-B",str(HERE/"run.py"),"worker",kind,case,str(num),arm,str(end-reserve),str(int(last))]
        log(dict(event="begin",kind=kind,case=case,target=num,arm=arm,limit_s=limit,start_s=begin-start))
        print(f"{kind} {case} {num} {arm}",flush=True)
        try:
            proc=subprocess.run(args,cwd=HERE,capture_output=True,timeout=max(.001,end-time.perf_counter()-.35))
            state="OK" if proc.returncode==0 else "ERROR"
            error=proc.stderr.decode(errors="replace")[-4000:]
        except subprocess.TimeoutExpired:
            state="TIME_LIMIT";error="hard subprocess cutoff"
        duration=time.perf_counter()-begin
        log(dict(event="end",kind=kind,case=case,target=num,arm=arm,limit_s=limit,elapsed_s=duration,
                 end_s=time.perf_counter()-start,state=state,error=error))
        if state!="OK": raise RuntimeError(f"{kind} {state}: {error}")
        return duration
    try:
        call("preflight",90)
        charge={}
        for c in CFG["cases"]: charge[c]=call("selection",35,c)
        all_targets=[(c,j) for c in CFG["cases"] for j in range(len(read("targets/"+c+".json")["targets"]))]
        if not all_targets: raise ValueError("no positive-energy targets in either case")
        frozen={c:digest((DATA/"targets"/(c+".json")).read_bytes()) for c in CFG["cases"]}
        write("target_freeze.json",dict(files=frozen,selection_seconds=charge,rule="all target lists bound before first search"))
        for c,j in all_targets:
            call("search",120-(charge[c] if j==0 else 0),c,j)
        hashes={c+"_"+str(j):digest((DATA/"pools"/f"{c}_{j}.json").read_bytes()) for c,j in all_targets}
        write("pool_freeze.json",dict(files=hashes,rule="all common pools bound before first C0/C1/C2 comparison"))
        for n,(c,j) in enumerate(all_targets):call("counterfactual",45,c,j,last=(n==len(all_targets)-1))
        if read("gate.json")["trigger"]:
            groups=read("ablation/groups.json")
            for arm in CFG["arms"]:call("arm",45,groups["case"],groups["target"],arm)
        audit_start=time.perf_counter()
        call("archive",min(115,global_end-audit_start-3))
        for c,h in frozen.items():assert digest((DATA/"targets"/(c+".json")).read_bytes())==h
        for label,h in hashes.items():assert digest((DATA/"pools"/(label+".json")).read_bytes())==h
        files={p.relative_to(DATA).as_posix():digest(p.read_bytes()) for p in sorted(DATA.rglob("*")) if p.is_file()}
        write("snapshot.json",dict(files=files,snapshot=digest(encode(files)),freeze=read("preflight.json")["freeze"],
             archive_s=time.perf_counter()-audit_start,wall_s=time.perf_counter()-start,seeds=[101,102],threads=1))
        assert time.perf_counter()<=min(audit_start+120,global_end)
    except Exception as e:
        write("stop.json",dict(reason=str(e),wall_s=time.perf_counter()-start,status="UNRESOLVED",retry=False))
        raise

if __name__=="__main__":
    if sys.argv[1:2]==["worker"]:
        _,_,kind,case,num,arm,end,last=sys.argv
        worker(kind,case,int(num),arm,float(end),bool(int(last)))
    elif sys.argv[1:]==["batch"]:main()
    else:raise SystemExit("python -B run.py batch")
