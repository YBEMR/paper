"""Single-use E2-c1 runner with independent per-arm deadlines and cumulative accounting."""
import json,os,subprocess,sys,time,traceback
from datetime import datetime,timezone
from samples import ROOT,B,BASE,REPO,read,write,digest

def utc():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(["git",*args],cwd=REPO)
def regression():
    sys.path.insert(0,str(B))
    import base,assets_e2,verify_core
    assets_e2.HERE=verify_core.HERE=ROOT/"regression"
    verify_core.finite();verify_core.replay()
    assert all(read(ROOT/"regression"/"validation"/n)["passed"] for n in ("finite_gate.json","replay_gate.json"))

def run():
    import psutil
    sys.path.insert(0,str(B))
    from supervise import physical_cores
    dst=ROOT/"execution.json"
    assert not dst.exists() and git("rev-parse","HEAD^").decode().strip()==BASE
    freeze=git("rev-parse","HEAD").decode().strip()
    assert not git("status","--porcelain")
    inherited=read(ROOT/"samples.json")
    for name,v in {**inherited["sources"],**read(B/"manifest.json")["files"]}.items():
        assert digest((REPO/name).read_bytes())==v,name
    files={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert all(git("show",freeze+":"+(ROOT/p).relative_to(REPO).as_posix())==(ROOT/p).read_bytes() for p in files)
    write(ROOT/"manifest.json",dict(freeze=freeze,base=BASE,files=files,inputs=inherited["sources"],
          inherited_manifest=inherited["inherited_manifest_sha256"],seed_policy="historical outer seed and identical seeded CP calls"))
    t0=time.perf_counter();state=dict(start=utc(),status="REGRESSION",limit_s=2400,groups=[],phases={},numerical_s=0,c2_started=False)
    def update():
        state["numerical_s"]=sum(z["charged_s"] for z in state["groups"])+sum(z["charged_s"] for z in state["phases"].values())
        assert state["numerical_s"]<=2400
        write(dst,state)
    logs=ROOT/"logs";logs.mkdir()
    def phase(name,cap):
        state["status"]=name.upper();update()
        t=time.perf_counter()
        try:
            with (logs/(name+".txt")).open("wb") as f:
                q=subprocess.run([sys.executable,"-B","-u",__file__,name],stdout=f,stderr=subprocess.STDOUT,
                             timeout=min(cap,2400-state["numerical_s"])-1,check=True)
        finally:
            state["phases"][name]=dict(charged_s=time.perf_counter()-t,cap_s=cap);update()
        print(name,"PASS",round(time.perf_counter()-t,2),flush=True)
    live=[]
    def stop(recs):
        for proc,*_ in recs:
            if proc.poll() is None:proc.kill()
        for proc,*_ in recs:proc.wait()
    try:
        phase("regression",240);phase("structure",90)
        cores=physical_cores()[:min(3,len(physical_cores()))];samples=inherited["cases"]
        jobs=[(i,m) for i in range(27) for m in (("Old","New") if i%2==0 else ("New","Old"))]
        state.update(status="REPLAY",cpus=cores,design=jobs);update()
        for off in range(0,len(jobs),len(cores)):
            for slot,(i,m) in enumerate(jobs[off:off+len(cores)]):
                folder=ROOT/"replays"/samples[i]["id"]/m;folder.mkdir(parents=True,exist_ok=False)
                cpu=cores[(slot+off//len(cores))%len(cores)]
                with (logs/(samples[i]["id"]+"_"+m+".txt")).open("wb") as f:
                    t=time.perf_counter()
                    proc=subprocess.Popen([sys.executable,"-B","-u",str(ROOT/"replay.py"),str(i),m,str(t),str(cpu)],
                                          cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
                live.append((proc,i,m,t,folder,cpu))
            while live:
                for item in live.copy():
                    proc,i,m,t,folder,cpu=item;elapsed=time.perf_counter()-t;code=proc.poll()
                    if code is None and elapsed<29.83:continue
                    overdue=code is None
                    if overdue:proc.kill();proc.wait()
                    charged=time.perf_counter()-t
                    armfile=folder/"arm.json"
                    if overdue:
                        arm=read(armfile) if armfile.exists() else dict(id=samples[i]["id"],method=m,source=samples[i]["source"],
                            candidates=[],auxiliary={},core={},visits=[],fallback=None)
                        arm.update(status="TIME_LIMIT",elapsed_s=min(charged,30.),note="hard stop; only completed certified candidates rank")
                        write(armfile,arm)
                    state["groups"].append(dict(sample=samples[i]["id"],method=m,cpu=cpu,charged_s=charged,
                              watchdog=overdue,exit_code=code,status=read(armfile)["status"] if armfile.exists() else "FAILED"))
                    live.remove(item);update()
                    if not overdue and code:raise RuntimeError((samples[i]["id"],m,code))
                if live:time.sleep(.025)
            print("GROUPS",len(state["groups"]),"/54",round(state["numerical_s"],1),"s",flush=True)
        phase("audit",440)
        state["status"]="COMPLETE"
    except BaseException:
        stop(live)
        for proc,i,m,t,folder,cpu in live:
            state["groups"].append(dict(sample=samples[i]["id"],method=m,charged_s=time.perf_counter()-t,status="INTERRUPTED"))
        state.update(status="STOP",failure=traceback.format_exc());raise
    finally:
        state.update(end=utc(),wall_s=time.perf_counter()-t0);update()
if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="regression":regression()
    elif mode=="structure":
        import structure
        structure.run()
    elif mode=="audit":
        import audit
        audit.run()
    elif mode=="run":run()
    else:raise ValueError(mode)
