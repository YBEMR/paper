"""One-shot serial supervisor. The monotonic budget includes interpreter startup and I/O."""
import subprocess
from datetime import datetime,timezone
from common import *

def utc():
    return datetime.now(timezone.utc).isoformat()

def source_id():
    sources=[*sorted(ROOT.glob("*.py")),ROOT/"e0/model.md",ROOT/"taskbook.md"]
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sources}

def worker(args):
    phase=args[0]
    if phase=="inputs":
        from inputs import preflight
        preflight()
    elif phase=="E0":
        from validation import e0
        e0()
    elif phase=="E1":
        from experiment import run
        run(args[1],int(args[2]),float(args[3]))
    elif phase=="archive":
        from archive import archive
        archive()
    else:
        raise ValueError(phase)

def batch(repair=False):
    ledger="execution.json"
    if repair:
        state=read(ledger)
        assert state["status"]=="FAILED_E0" and not state.get("e1_started")
        assert not (ROOT/"e1").exists()
        numbered=ROOT/"e0"/f"attempt_{sum(x['phase']=='E0' for x in state['runs'])}"
        numbered.mkdir(exist_ok=False)
        for path in (ROOT/"e0").iterdir():
            if path.is_file() and path.name!="model.md":path.replace(numbered/path.name)
        state["sources"]=source_id()
    else:
        assert not (ROOT/ledger).exists() and not (ROOT/"manifest.json").exists()
        state=dict(started_utc=utc(),start=time.monotonic(),status="STARTED",runs=[],sources=source_id(),
                   wall_cap_s=9600,compute_cap_s=9000,seed=101,workers=1)
    def job(phase,cap,*args):
        assert source_id()==state["sources"]
        when=time.monotonic()
        used=sum(x.get("elapsed_s",0.) for x in state["runs"])
        allot=min(cap,9000-used,9600-(when-state["start"]))
        if allot<2:raise TimeoutError("batch cap")
        record=dict(phase=phase,args=list(args),start_utc=utc(),cap_s=allot)
        state["runs"].append(record);state["status"]="RUNNING_"+phase;save(ledger,state)
        label="_".join((phase,*args))+"_"+str(len(state["runs"]))
        path=ROOT/"run_logs"/(label+".txt");path.parent.mkdir(exist_ok=True)
        cmd=[sys.executable,"-B","-u",str(ROOT/"driver.py"),"worker",phase,*args]
        if phase=="E1":cmd.append(str(time.perf_counter()+allot-6))
        print("START",label,utc(),flush=True)
        with path.open("wb") as log:
            try:res=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=allot-.3);code=res.returncode
            except subprocess.TimeoutExpired:code=124
        record.update(elapsed_s=time.monotonic()-when,exit_code=code,log=path.relative_to(ROOT).as_posix())
        state["compute_s"]=sum(x["elapsed_s"] for x in state["runs"])
        state["wall_s"]=time.monotonic()-state["start"]
        state["status"]=("FINISHED_" if code==0 else "FAILED_")+phase;save(ledger,state)
        print(state["status"],label,round(record["elapsed_s"],2),flush=True)
        if code:
            print(path.read_text(encoding="utf8",errors="replace")[-4000:],flush=True)
            raise SystemExit(code)
    if not repair:job("inputs",300)
    used_e0=sum(x.get("elapsed_s",0) for x in state["runs"] if x["phase"]=="E0")
    job("E0",900-used_e0)
    assert read("e0/gate.json")["pass_E0"]
    assert sha((ROOT/"regions.json").read_bytes())==read("manifest.json")["region_sha256"]
    state["e1_started"]=utc();save(ledger,state)
    for key,region in read("regions.json")["regions"].items():
        if "ids" in region:
            for group in range(4):job("E1",300,key,str(group))
    job("archive",600)
    state["status"]="COMPLETE";state["completed_utc"]=utc()
    state["wall_s"]=time.monotonic()-state["start"];save(ledger,state)
    artifacts={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(ROOT.rglob("*"))
               if p.is_file() and "__pycache__" not in p.parts and p.name!="snapshot.json"}
    save("snapshot.json",dict(files=artifacts,execution=state["status"]))

if __name__=="__main__":
    if sys.argv[1]=="worker":worker(sys.argv[2:])
    elif sys.argv[1] in ("batch","repair-e0"):batch(sys.argv[1]=="repair-e0")
    else:raise SystemExit("batch | repair-e0")
