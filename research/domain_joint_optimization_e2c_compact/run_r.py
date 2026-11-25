"""One shot, with a closed correctness gate, per-arm deadlines and a collective allowance."""
import subprocess,sys,time,traceback
from datetime import datetime,timezone
from assets import ROOT,C,BASE,REPO,git,read,write,digest
import psutil

def utc():return datetime.now(timezone.utc).isoformat()
def stop(p):
    try:
        children=psutil.Process(p.pid).children(recursive=True)
    except psutil.NoSuchProcess:children=[]
    for proc in reversed(children):
        try:proc.kill()
        except psutil.NoSuchProcess:pass
    if p.poll() is None:p.kill()
    p.wait()
    psutil.wait_procs(children,timeout=.5)

def run():
    t0=time.perf_counter();dst=ROOT/"execution.json";assert not dst.exists()
    assert git("rev-parse","HEAD^").decode().strip()==BASE and not git("status","--porcelain")
    head=git("rev-parse","HEAD").decode().strip();inputs=read(ROOT/"samples.json")
    own={}
    for p in ROOT.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            blob=p.read_bytes();assert git("show",head+":"+p.relative_to(REPO).as_posix())==blob;own[p.relative_to(ROOT).as_posix()]=digest(blob)
    for file,sha in read(C/"snapshot.json")["files"].items():assert digest((C/file).read_bytes())==sha
    from samples import B
    bm=read(B/"manifest.json");assert digest((B/"manifest.json").read_bytes())==read(C/"manifest.json")["inherited_manifest"]
    for file,sha in bm["files"].items():assert digest((REPO/file).read_bytes())==sha
    from support import Problem
    from supervise import physical_cores
    cores=physical_cores()[:2];assert len(cores)==2
    write(ROOT/"manifest.json",dict(freeze=head,base=BASE,support_blob=inputs["support_blob"],sources=own,
        c1_snapshot_sha=digest((C/"snapshot.json").read_bytes()),inherited_manifest_sha=digest((B/"manifest.json").read_bytes()),
        case_inputs=inputs["files"],python=sys.version,physical_cores=cores,arm_s=30,aux_s=11,total_s=1200))
    logs=ROOT/"logs";logs.mkdir()
    init=time.perf_counter()-t0
    state=dict(start=utc(),status="CORRECTNESS",groups=[],phases={"asset_verification":init},c2_started=False)
    def update():
        state["replay_s"]=sum(g["charged_s"] for g in state["groups"])
        state["ancillary_s"]=sum(state["phases"].values());state["numerical_s"]=state["replay_s"]+state["ancillary_s"]
        write(dst,state)
        assert state["replay_s"]<=660 and state["ancillary_s"]<=540 and state["numerical_s"]<=1200
    def phase(name,cap):
        start=time.perf_counter()
        with (logs/(name+".txt")).open("wb") as f:
            proc=subprocess.Popen([sys.executable,"-B","-u",str(ROOT/(name+".py"))],stdout=f,stderr=subprocess.STDOUT)
            psutil.Process(proc.pid).cpu_affinity([cores[0]])
            try:code=proc.wait(timeout=min(cap,540-sum(state["phases"].values()))-1)
            except subprocess.TimeoutExpired:stop(proc);code=124
        state["phases"][name]=time.perf_counter()-start;update()
        if code:raise RuntimeError((name,code,(logs/(name+".txt")).read_text(errors="replace")[-1500:]))
        print(name,"PASS",round(state["phases"][name],2),flush=True)
    live=[]
    try:
        update();phase("checks",260)
        assert read(ROOT/"validation"/"gate.json")["passed"]
        state["status"]="REPLAYS";update()
        for ix,s in enumerate(inputs["cases"]):
            variants=("Full-Hint","Compact-Hint") if ix%2==0 else ("Compact-Hint","Full-Hint")
            for slot,method in enumerate(variants):
                folder=ROOT/"runs"/s["id"]/method;folder.mkdir(parents=True,exist_ok=False)
                with (logs/(s["id"]+"_"+method+".txt")).open("wb") as f:
                    t=time.perf_counter()
                    p=subprocess.Popen([sys.executable,"-B","-u",str(ROOT/"arm_r.py"),"arm",s["id"],method,str(t),str(cores[slot])],
                                       stdout=f,stderr=subprocess.STDOUT)
                live.append((p,method,t,folder,cores[slot]))
            while live:
                for item in live.copy():
                    p,method,t,folder,cpu=item;code=p.poll()
                    if code is None and time.perf_counter()-t<29.81:continue
                    killed=code is None
                    if killed:stop(p)
                    wall=time.perf_counter()-t
                    state["groups"].append(dict(sample=s["id"],method=method,cpu=cpu,charged_s=wall,hard_stop=killed,code=code))
                    live.remove(item);update()
                    if killed:
                        r=read(folder/"arm.json");r.update(status="TIME_LIMIT",stopped_at_s=wall);write(folder/"arm.json",r)
                    elif code:raise RuntimeError((s["id"],method,code))
                if live:time.sleep(.015)
            print(s["id"],len(state["groups"]),"/22",round(state["numerical_s"],1),"s",flush=True)
        state["status"]="AUDIT";update();phase("review",200)
        state["status"]="COMPLETE"
    except BaseException:
        for p,m,t,f,cpu in live:
            stop(p);state["groups"].append(dict(sample=s["id"],method=m,cpu=cpu,status="INTERRUPTED",charged_s=time.perf_counter()-t))
        state.update(status="STOP",error=traceback.format_exc());raise
    finally:
        state.update(end=utc(),wall_s=time.perf_counter()-t0);update()
if __name__=="__main__":run()
