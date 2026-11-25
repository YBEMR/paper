"""Frozen wave order, physical affinity, time budgets and admission gate."""
import ctypes,csv,gzip,hashlib,itertools,json,math,os,random,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
E2=ROOT.parent/"domain_joint_optimization_e2a"
REPO=ROOT.parents[1]
BASE="d313094505db8eb1114b0d5859210b058f7bfa76"
def utc():return datetime.now(timezone.utc).isoformat()
def h(b):return hashlib.sha256(b).hexdigest()
def rd(p):return json.loads(Path(p).read_bytes())
def wr(p,x):
    p=Path(p);p.parent.mkdir(exist_ok=True,parents=True);tmp=p.with_suffix(".tmp")
    tmp.write_bytes((json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False,default=str)+"\n").encode());tmp.replace(p)
def git(*a):return subprocess.check_output(["git",*a],cwd=REPO)
def physical_cores():
    class Entry(ctypes.Structure):
        _fields_=[("mask",ctypes.c_size_t),("relation",ctypes.c_int),("reserved",ctypes.c_uint64*2)]
    size=ctypes.c_uint32();q=ctypes.windll.kernel32.GetLogicalProcessorInformation
    q(None,ctypes.byref(size));buf=(Entry*(size.value//ctypes.sizeof(Entry)))()
    assert q(ctypes.byref(buf),ctypes.byref(size))
    allowed=psutil.Process().cpu_affinity()
    return [min(i for i in allowed if x.mask&(1<<i)) for x in buf if x.relation==0 and any(x.mask&(1<<i) for i in allowed)]
def design():
    methods=["G3","CP-FO","CP-LNS","Proposed","Proposed-Single"]
    cells=[(c,m,s) for s in (101,102,103) for c in ("D1","D2","D3") for m in methods+(["Proposed-NoOrder"] if c=="D3" else [])]
    return [cells[(17*i)%48] for i in range(48)]
def verify():
    hist=rd(E2/"manifest.json");s=rd(E2/"snapshot.json");lock=rd(ROOT/"inputs.lock.json")
    head=git("rev-parse","HEAD").decode().strip()
    assert git("rev-parse","HEAD^").decode().strip()==BASE and len(design())==len(set(design()))==48
    files={}
    for source,mapping in [(REPO,hist["inputs"]),(E2,s["files"])]:
        for k,v in mapping.items():
            path=source/k;assert h(path.read_bytes())==v,path;files[path.relative_to(REPO).as_posix()]=v
    for k,blob in lock.items():
        p=REPO/k;b=p.read_bytes();assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==blob
        files[k]=h(b)
    for p in [*ROOT.glob("*.py"),ROOT/"taskbook.md",ROOT/"protocol.md",ROOT/"inputs.lock.json"]:
        rel=p.relative_to(REPO).as_posix();b=p.read_bytes()
        assert git("show",head+":"+rel)==b
        files[rel]=h(b)
    from base import archived,Problem
    from importlib.metadata import version
    inputs={}
    for c in ("D1","D2","D3"):
        p=Problem(c);k,_=archived(c)
        inputs[c]=dict(g3=k,release_windows=len({r["release_tick"]//2500 for r in p.req}),stages=p.n,lower=p.lower())
    wr(ROOT/"manifest.json",dict(freeze=head,results_base=BASE,files=files,inputs=inputs,design=design(),python=sys.version,
        packages={n:version(n) for n in ("ortools","numpy","scipy","numba","psutil")},physical_cpus=physical_cores(),
        main_budget=86400,preflight_and_archive=1800,per_run=1800,per_step=30))
    # Re-run E2-a encoding, rational optima, all archived memberships and independent rights.
    import verify_core,assets_e2
    dest=ROOT/"preflight"/"regression";assets_e2.HERE=dest;verify_core.HERE=dest
    verify_core.finite();verify_core.replay()
    assert rd(dest/"validation/finite_gate.json")["passed"] and rd(dest/"validation/replay_gate.json")["passed"]
def command(case,method,seed,cpu,path,begin,cap,pilot):
    return [sys.executable,"-B","-u",str(ROOT/"arm.py"),case,method,str(seed),str(cpu),str(path),str(begin),str(begin+cap),str(int(pilot))]
def boundary_replay():
    from base import Problem,decode,key,dynamic_region,Core
    from verify_core import fix,check
    results=[]
    for dest in sorted((ROOT/"preflight").glob("pilot_*")):
        z=rd(dest/"summary.json");p=Problem(z["case"])
        with gzip.open(dest/"iterations.jsonl.gz","rt",encoding="utf8") as f:r=json.loads(f.readline())
        with gzip.open(dest/"plans.jsonl.gz","rt",encoding="utf8") as f:plans=[json.loads(line) for line in f]
        for ident,body in plans:
            plan=decode(body);st=set(r["St"]);region=dynamic_region(p,plan,st,set(r["Sf"]),1)
            assert region["source"]==ident==key(p,plan)
            assert (region["identity"]==r["region"])==(ident==z["initial"])
            core=Core(p,plan,sorted(st),1,region=region,pin={i:plan[0][i] for i in st})
            state,data=fix(core,plan);assert state=="ACCEPT"
            check(p,plan,*data,True)
            results.append(dict(pilot=dest.name,source=ident,region=region["identity"],current_window_centered=True))
    wr(ROOT/"preflight/boundary_replay.json",results)
def launch(tag,cmd):
    folder=ROOT/"logs";folder.mkdir(exist_ok=True);log=(folder/(tag+".txt")).open("wb")
    try:return subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    finally:log.close()
def batch():
    path=ROOT/"execution.json";assert not path.exists(),"one-shot experiment"
    state=dict(start=utc(),status="PREFLIGHT",runs=[]);wr(path,state);t0=time.perf_counter()
    def phase(tag,cmd,limit):
        began=time.perf_counter();p=launch(tag,cmd)
        try:code=p.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            kill(p);code=124
        if code:raise RuntimeError((tag,code,(ROOT/"logs"/(tag+".txt")).read_text(errors="replace")[-2500:]))
        return time.perf_counter()-began
    def kill(p):
        try:
            for child in psutil.Process(p.pid).children(recursive=True):child.kill()
        except psutil.NoSuchProcess:pass
        p.kill();p.wait()
    try:
        phase("verification",[sys.executable,"-B","-u",__file__,"verify"],400)
        cpus=physical_cores();pilots=[]
        for c,m in itertools.product(("D1","D2","D3"),("CP-LNS","Proposed")):
            tag="pilot_"+c+"_"+m;dest=ROOT/"preflight"/tag;begin=time.perf_counter()
            phase(tag,command(c,m,101,cpus[0],dest,begin,65,True),min(66,600-(begin-t0)))
            z=rd(dest/"summary.json")
            with gzip.open(dest/"iterations.jsonl.gz","rt",encoding="utf8") as f:item=json.loads(f.readline())
            assert item["source"]==z["initial"] and item["region"] and item["mode"]==1
            pilots.append(dict(case=c,method=m,**z["counts"],peak=z["peak_bytes"],seconds=item["outer_s"],
                               actual_seed=[x["seed"] for x in item["solves"]],region=item["region"]))
        gate=all(p.get("nonseed",0)>0 and p["actual_seed"] and all(s==101 for s in p["actual_seed"]) and
                 p.get("watchdog",0)==0 and p["seconds"]<=30 for p in pilots)
        gate=gate and all(any(x.get("joint",0)>0 for x in pilots if x[k]==v) for k,vs in
                         [("case",["D1","D2","D3"]),("method",["CP-LNS","Proposed"])] for v in vs)
        phase("boundary_replay",[sys.executable,"-B","-u",__file__,"boundary"],min(100,600-(time.perf_counter()-t0)))
        wr(ROOT/"preflight/gate.json",dict(passed=gate,pilots=pilots))
        state["preflight_s"]=time.perf_counter()-t0
        if not gate:
            state["status"]="ENGINEERING_GATE_STOP";wr(path,state);return
        workers=max(1,min(6,len(cpus),int((psutil.virtual_memory().available-640*2**20)/
                       (max(x["peak"] for x in pilots)*1.2+50*2**20))))
        state.update(status="MAIN",workers=workers,cpus=cpus[:workers],seed_policy="outer and all CP calls use run seed")
        wr(path,state);print("GATE PASS",workers,"workers",flush=True)
        cases=design()
        for offset in range(0,len(cases),workers):
            wave=cases[offset:offset+workers];live=[]
            try:
                for slot,(c,m,s) in enumerate(wave):
                    tag=f"{c}_{m}_{s}";cpu=cpus[(slot+offset//workers)%workers];begin=time.perf_counter()
                    record=dict(id=tag,case=c,method=m,seed=s,cpu=cpu,wave=offset//workers+1,start_utc=utc(),begin=begin)
                    dest=ROOT/"runs"/tag
                    p=launch(tag,command(c,m,s,cpu,dest,begin,1800,False));live.append((record,p,dest));state["runs"].append(record)
                wr(path,state);print("WAVE",offset//workers+1,"START"," ".join(r["id"] for r,p,d in live),flush=True)
                while live:
                    for item in live.copy():
                        r,p,dest=item;code=p.poll()
                        if code is None:
                            if time.perf_counter()>r["begin"]+1801:kill(p);raise TimeoutError(r["id"])
                            continue
                        if code:raise RuntimeError((r["id"],code,(ROOT/"logs"/(r["id"]+".txt")).read_text(errors="replace")[-2500:]))
                        z=rd(dest/"summary.json");assert z["elapsed_s"]<=1800 and z["elapsed_s"]>=1790
                        r.update(end_utc=utc(),elapsed_s=z["elapsed_s"],status="COMPLETE");live.remove(item);wr(path,state)
                    if live:time.sleep(.15)
                print("WAVE",offset//workers+1,"DONE",flush=True)
            except BaseException:
                for _,p,_ in live:
                    if p.poll() is None:kill(p)
                raise
        state["status"]="AUDIT";wr(path,state)
        state["audit_s"]=phase("audit",[sys.executable,"-B","-u",str(ROOT/"assessment.py")],min(1200,1800-state["preflight_s"]))
        state.update(status="COMPLETE",end=utc(),wall_s=time.perf_counter()-t0);wr(path,state)
        snapshot()
    except BaseException as e:
        state.update(status="FAILED",error=str(e),end=utc(),wall_s=time.perf_counter()-t0);wr(path,state);raise
def snapshot():
    wr(ROOT/"snapshot.json",dict(files={p.relative_to(ROOT).as_posix():h(p.read_bytes()) for p in sorted(ROOT.rglob("*"))
        if p.is_file() and p.name!="snapshot.json" and "__pycache__" not in p.parts},freeze=rd(ROOT/"manifest.json")["freeze"]))
if __name__=="__main__":
    if sys.argv[1]=="verify":verify()
    elif sys.argv[1]=="boundary":boundary_replay()
    else:batch()
