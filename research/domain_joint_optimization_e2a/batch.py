"""Serial budget supervisor. A repair uses only the original stage's remaining allocation."""
import json,os,subprocess,sys,time,traceback
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
def stamp():return datetime.now(timezone.utc).isoformat()
def main(repair):
    path=ROOT/"execution.json"
    steps=[("inputs",300),("finite",1200),("replay",900)]+[(f"{n}_P{g}",60) for n in ("D1","D2","R1","R2","R3","R4") for g in (1,2,3)]+[("audit",600)]
    def save():
        tmp=path.with_suffix(".tmp");tmp.write_bytes((json.dumps(state,ensure_ascii=False,indent=2)+"\n").encode());tmp.replace(path)
    if repair:
        state=json.loads(path.read_bytes());assert state["status"]=="FAILED"
        import shutil
        dest=ROOT/"failures"/str(len(state["runs"]));dest.mkdir(parents=True)
        for suffix in ("execution.json","validation/counterexample.json","validation/finite.csv","validation/replay.csv","validation/permissions.csv"):
            p=ROOT/suffix
            if p.exists():shutil.copy2(p,dest/p.name)
    else:
        assert not path.exists()
        state=dict(start_monotonic=time.monotonic(),start_utc=stamp(),runs=[],status="NEW")
    for stage,cap in steps:
        prior=[r for r in state["runs"] if r["stage"]==stage]
        if any(r["code"]==0 for r in prior):continue
        now=time.monotonic();cap=min(cap-sum(r["s"] for r in prior),4080-sum(r["s"] for r in state["runs"]),4500-(now-state["start_monotonic"]))
        assert cap>=2
        name=stage+"_"+str(len(state["runs"])+1);log=ROOT/"logs"/(name+".txt");log.parent.mkdir(exist_ok=True)
        gitid=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip()
        assert not subprocess.check_output(["git","diff","--name-only","HEAD","--","*.py","model.md","taskbook.md","inputs.lock.json"],cwd=ROOT)
        r=dict(stage=stage,cap_s=cap,start_utc=stamp(),source=gitid);state["runs"].append(r);state["status"]="RUNNING";save()
        print("START",name,stamp(),flush=True)
        cmd=[sys.executable,"-B","-u",str(ROOT/"batch.py"),"worker",stage,str(time.perf_counter()+cap-1.6)]
        with log.open("wb") as fh:
            try:ret=subprocess.run(cmd,cwd=ROOT,stdout=fh,stderr=subprocess.STDOUT,timeout=cap-.25).returncode
            except subprocess.TimeoutExpired:ret=124
        r.update(code=ret,s=time.monotonic()-now,log=str(log.relative_to(ROOT).as_posix()))
        state["compute_s"]=sum(x["s"] for x in state["runs"]);state["wall_s"]=time.monotonic()-state["start_monotonic"]
        state["status"]="FAILED" if ret else "STAGE_DONE";save();print(state["status"],stage,round(r["s"],2),flush=True)
        if ret:
            print(log.read_text(errors="replace")[-3500:],flush=True)
            raise SystemExit(ret)
    state["status"]="COMPLETE";state["end_utc"]=stamp();save()
    from assets_e2 import sha,write
    write("snapshot.json",dict(freeze=state["runs"][0]["source"],files={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name!="snapshot.json" and "__pycache__" not in p.parts}))
if __name__=="__main__":
    if sys.argv[1]=="worker":
        from run_stage import inputs,smoke,audit
        from verify_core import finite,replay
        stage=sys.argv[2]
        if stage in ("inputs","finite","replay","audit"):dict(inputs=inputs,finite=finite,replay=replay,audit=audit)[stage]()
        else:
            n,g=stage.split("_P");smoke(n,int(g),float(sys.argv[3]))
    else:main(sys.argv[1]=="repair")
