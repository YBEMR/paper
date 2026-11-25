"""Precommitted one-shot design, wall clocks and durable process receipts."""
import gzip
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from importlib.metadata import version
import psutil
from settings import BASE,INITIAL,METHODS,ROOT,REPO,design,sha,read,write,clock

def utc():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(["git",*args],cwd=REPO)
def record(state):write(ROOT/"execution.json",state)

def manifest():
    sys.path.insert(0,str(ROOT.parent/"domain_joint_optimization_e2b"))
    from supervise import physical_cores
    cpus=physical_cores();free=psutil.virtual_memory().available
    old_peaks=[read(p)["peak_bytes"] for p in (ROOT.parent/"domain_joint_optimization_e2b"/"runs").glob("D3_*/summary.json") if "G3" not in p.parent.name]
    # Two resident numerical processes per hybrid; charge their historical peak
    # with 25% margin and reserve 256 MiB for the OS. A serial pilot measures
    # actual behavior when available memory only permits one slot.
    per_run=int(2.5*max(old_peaks))
    workers=max(1,min(5,len(cpus),int((free-256*2**20)/per_run)))
    cpus=cpus[:workers]
    head=git("rev-parse","HEAD").decode().strip()
    git("merge-base","--is-ancestor",BASE,head)
    history=["be641ce06a4f496d2b1f233a09bdfc3776738668","d313094505db8eb1114b0d5859210b058f7bfa76","34d36f56a78166360503e41a1a057171e29fd4eb","b32f92114afc26fc90f86f2f6b74c4db6d2876bc",BASE]
    for rev in history:git("cat-file","-e",rev+"^{commit}")
    sources={}
    for f in [*ROOT.glob("*.py"),ROOT/"taskbook.md",ROOT/"protocol.md"]:
        rel=f.relative_to(REPO).as_posix();assert git("show",head+":"+rel)==f.read_bytes(),rel
        sources[rel]=sha(f.read_bytes())
    old=ROOT.parent/"domain_joint_optimization_e2b";p1=ROOT.parent/"cross_scene_taskflow_diagnostic"
    inherited=read(old/"manifest.json")["files"].copy()
    for f in [*(f for d in (old,ROOT.parent/"domain_joint_optimization_e2c",ROOT.parent/"domain_joint_optimization_e2c_compact") for f in d.glob("*.py")),p1/"logs"/"plans"/(INITIAL+".json.gz"),p1/"g3_thermal"/"D3_G3.json"]:
        rel=f.relative_to(REPO).as_posix()
        blob=git("rev-parse",BASE+":"+rel).decode().strip()
        assert git("hash-object",str(f)).decode().strip()==blob
        inherited[rel]=sha(f.read_bytes())
    for rel,h in inherited.items():assert sha((REPO/rel).read_bytes())==h,rel
    data=dict(freeze=head,base=BASE,history=history,study="D3",initial=INITIAL,source_J=63.39163095183008,
              runs=design(cpus),cpus=cpus,free_bytes=free,estimated_bytes_per_run=per_run,source_hashes=sources,inherited=inherited,
              python=sys.version,initial_lower=read(old/"manifest.json")["inputs"]["D3"]["lower"],
              budgets=dict(preflight=900,main=21600,archive=900,total=23400),seeds=[101,102,103],core_limits=[7,6],
              auxiliary_limits=[4.5,2.5],local_s=30,aux_s=11,cycles=6,broad_s=180,deep_s=120)
    write(ROOT/"manifest.json",data)
    return data

def launch(name,args):
    path=ROOT/"logs"/(name+".txt");path.parent.mkdir(exist_ok=True)
    with path.open("xb") as log:
        return subprocess.Popen([sys.executable,"-B","-u",*map(str,args)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
def clean(proc):
    try:
        kids=psutil.Process(proc.pid).children(recursive=True)
    except psutil.NoSuchProcess:kids=[]
    for kid in kids:
        try:kid.kill()
        except psutil.NoSuchProcess:pass
    if proc.poll() is None:proc.kill()
    proc.wait(timeout=2)

def run_wave(specs,where,pilot,state):
    live=[];out=state["pilot_runs" if pilot else "runs"]
    try:
        for s in specs:
            method=s["method"];tag=method+"_"+str(s["seed"]);root=ROOT/where/tag
            duration=(40 if method=="G3" else 100) if pilot else 1800
            t=clock();receipt=dict(**s,tag=tag,begin=t,utc=utc(),limit=duration,status="RUNNING")
            p=launch(where.replace("/","_")+"_"+tag,["flow_run.py",root,method,s["seed"],s["cpu"],t,int(pilot)])
            out.append(receipt);live.append((p,receipt,root));record(state)
        while live:
            for item in live.copy():
                p,r,root=item;code=p.poll();elapsed=clock()-r["begin"]
                if code is None and elapsed<r["limit"]-.10:continue
                if code is None and not (root/"summary.json").is_file():
                    clean(p);code=124
                if code is None:
                    # Numerical owner has already closed its streams and written its endpoint.
                    try:code=p.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:clean(p);code=124
                r.update(code=code,observed_exit_s=clock()-r["begin"],end_utc=utc(),charged_s=r["limit"])
                live.remove(item)
                if code or not (root/"summary.json").exists():
                    r["status"]="INTERRUPTED";record(state);raise RuntimeError(("run interruption",r["tag"],code))
                z=read(root/"summary.json")
                assert z["initial"]==INITIAL and z["seed"]==r["seed"] and z["elapsed_s"]<=r["limit"]
                r.update(status="COMPLETE",endpoint_s=z["elapsed_s"],final=z["final"]);record(state)
            if live:time.sleep(.04)
    finally:
        for p,r,root in live:
            clean(p);r.update(status="INTERRUPTED",charged_s=min(r["limit"],clock()-r["begin"]),end_utc=utc())
        record(state)

def pilot_check(spec):
    folder=ROOT/"preflight"/"pilots"/(spec["method"]+"_"+str(spec["seed"]))
    z=read(folder/"summary.json");ph=z["phases"]
    prev=INITIAL
    for q in ph:
        assert q["before"]["sha"]==prev;prev=q["after"]["sha"]
        assert q["actual_end"]<=q["scheduled_end"]+.10
    assert prev==z["final"]
    if z["method"]=="G3":
        assert len(ph)==1 and z["moves"]>0
        return dict(method=z["method"],attempts=z["moves"])
    assert [q["phase"] for q in ph]==["G3","joint","G3","joint"]
    for a,b in zip(ph,ph[1:]):
        for k in ("sha","rng","steps","index","bounds"):assert a["after"][k]==b["before"][k],k
    import collections
    with gzip.open(folder/"events.jsonl.gz","rb") as f:events=[json.loads(l) for l in f]
    starts=[x for x in events if x["event"]=="start"]
    steps=[x for x in events if x["event"]=="subproblem"]
    assert steps and [z["it"] for z in steps]==list(range(len(steps)))
    assert all(z["elapsed"]<=30 for z in steps)
    rngdata=ph[1]["before"]["rng"]
    assert rngdata==ph[1]["after"]["rng"] and ph[2]["after"]["steps"]>ph[1]["after"]["steps"]
    regions=[z for z in events if z["event"]=="core_region"]
    assert regions and all(r["mode"]==(3 if r["it"]%4==3 else 1) for r in regions)
    certified=[z for z in events if z["event"]=="certificate" and z["on_time"]]
    assert certified and all(z["source"]==next(s["source"] for s in steps if s["it"]==z["it"]) for z in certified)
    if z["method"]=="Hybrid-New":assert any(x["event"]=="hint" for x in events)
    report=dict(method=z["method"],handoffs=ph,steps=len(steps),certificates=len(certified),
                deadlines=[s["phases"] for s in steps],physical_changes=z["initial"]!=z["final"])
    return report

def run():
    assert not (ROOT/"execution.json").exists(),"single experimental registration"
    t=clock();state=dict(status="PREFLIGHT",start_utc=utc(),pilot_runs=[],runs=[])
    record(state)
    try:
        man=manifest();cpus=man["cpus"]
        child=launch("correctness",["preflight.py"])
        try:code=child.wait(timeout=450)
        except subprocess.TimeoutExpired:clean(child);raise
        assert code==0,"preflight.py failed; see logs/correctness.txt"
        state["verification_s"]=clock()-t;record(state)
        specs=[dict(seed=101,method=m,cpu=cpus[i%len(cpus)]) for i,m in enumerate(METHODS)]
        for i in range(0,4,len(cpus)):run_wave(specs[i:i+len(cpus)],"preflight/pilots",True,state)
        tcheck=clock();audit=[pilot_check(spec) for spec in specs]
        state["preflight_s"]=state["verification_s"]+sum(r["charged_s"] for r in state["pilot_runs"])+clock()-tcheck
        assert state["preflight_s"]<900
        write(ROOT/"preflight"/"gate.json",dict(passed=True,verification=audit))
        state["status"]="FORMAL";record(state)
        for w in sorted({v["wave"] for v in man["runs"]}):
            run_wave([v for v in man["runs"] if v["wave"]==w],"runs",False,state)
        state["status"]="AWAITING_INDEPENDENT_AUDIT"
    except Exception:
        import traceback
        state.update(status="FORMAL_INTERRUPTION" if state["runs"] else "PREFLIGHT_STOP",error=traceback.format_exc())
        if not state["runs"]:
            state["preflight_s"]=state.get("verification_s",clock()-t)+sum(v.get("charged_s",0) for v in state["pilot_runs"])
        raise
    finally:
        state.update(end_utc=utc(),main_charge=sum(v.get("charged_s",0) for v in state["runs"]))
        record(state)
if __name__=="__main__":run()
