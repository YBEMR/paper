"""Serial engineering gate and paired, single-core formal jobs with parent wall-clock limits."""
import concurrent.futures,ctypes,hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
BUDGET={"S32":300,"S80":900,"D1":900,"D2":900}
METHODS=("Compact","AB","Proposed")
def read(path):return json.loads(path.read_bytes())
def dump(path,value):
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf8",newline="\n");tmp.replace(path)
def utc():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(["git","-C",str(REPO),*args]).decode().strip()

def physical_cores():
    import psutil
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    count=w.DWORD();kernel.GetLogicalProcessorInformationEx(0,None,ctypes.byref(count))
    buf=ctypes.create_string_buffer(count.value)
    assert kernel.GetLogicalProcessorInformationEx(0,buf,ctypes.byref(count))
    raw=buf.raw;pos=0;allowed=set(psutil.Process().cpu_affinity());cores=[]
    while pos<len(raw):
        size=int.from_bytes(raw[pos+4:pos+8],"little")
        assert size>=40
        mask=int.from_bytes(raw[pos+32:pos+40],"little")
        ids=[i for i in sorted(allowed) if mask>>i&1]
        if ids:cores.append(ids[0])
        pos+=size
    assert cores
    return cores[:3]

def launch(root,action,name,method,seed,limit,cpu,charged=0):
    label="init_"+name if action=="init" else f"{action}_{name}_{method}_{seed}"
    folder=root/label;folder.mkdir()
    import psutil
    info=dict(action=action,case=name,method=method,seed=seed,physical_cpu=cpu,limit_s=limit,
              prior_charge_s=charged,utc=utc())
    dump(folder/"start.json",info)
    begin=time.perf_counter();end=begin+limit
    args=[sys.executable,"-B","-u",str(ROOT/"worker.py"),action,name,method,str(seed),str(folder),
          str(begin),str(end),str(limit+charged),str(charged)]
    with (folder/"worker.log").open("xb") as f:
        proc=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
        try:
            psutil.Process(proc.pid).cpu_affinity([cpu])
            code=proc.wait(timeout=max(.05,end-time.perf_counter()))
            status="OK" if code==0 and (folder/"result.json").is_file() else "ERROR"
        except subprocess.TimeoutExpired:
            proc.kill();proc.wait();status="TIME_LIMIT"
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    info.update(end=utc(),elapsed_s=time.perf_counter()-begin,status=status,exit_code=proc.returncode)
    dump(folder/"receipt.json",info)
    if status!="OK":raise RuntimeError(f"{label}: {status}; see {folder}/worker.log")
    return info

def smoke():
    out=ROOT/"engineering";out.mkdir()
    cpu=physical_cores()[0]
    for case,method,limit in (("S16","Proposed",45),("S80","AB",55),("D3","Proposed",100)):
        launch(out,"smoke",case,method,101,limit,cpu)
    dump(out/"gate.json",dict(status="PASS",utc=utc()))

def main():
    assert read(ROOT/"witness_gate.json")["status"]==read(ROOT/"model_gate.json")["status"]=="PASS"
    assert read(ROOT/"finite_gate.json")["status"]=="PASS"
    assert read(ROOT/"engineering/gate.json")["status"]=="PASS"
    assert git("remote","get-url","origin")=="https://github.com/YBEMR/paper.git"
    assert git("branch","--show-current")=="codex/critical-interval-g2"
    assert not git("diff","HEAD","--name-only","--","research/critical_interval_coordination_g2")
    out=ROOT/"runs";out.mkdir()
    cores=physical_cores()
    files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(ROOT.glob("*.py"))}
    dump(out/"freeze.json",dict(head=git("rev-parse","HEAD"),utc=utc(),cores=cores,sources=files,
          budgets=BUDGET,seeds=[101,102,103],methods=METHODS,diagnostic_budget=600))
    try:
        charged={}
        for i,name in enumerate((*BUDGET,"D3")):
            limit=0.20*BUDGET.get(name,600)
            r=launch(out,"init",name,"common",101,limit,cores[i%len(cores)])
            charged[name]=r["elapsed_s"]
        def wave(tasks):
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(cores)) as pool:
                pending=[pool.submit(launch,out,*task) for task in tasks]
                for job in pending:job.result()
        for case,cap in BUDGET.items():
            for idx,seed in enumerate((101,102,103)):
                wave([("main",case,m,seed,cap-charged[case],cores[(i+idx)%len(cores)],charged[case])
                      for i,m in enumerate(METHODS)])
        for name in ("S80","D3"):
            wave([("strong",name,m,101,600,cores[i%len(cores)],0) for i,m in enumerate(("AB","Proposed"))])
        outcome="COMPLETED"
    except BaseException:
        outcome="STOP";dump(out/"stop.json",dict(utc=utc(),error=traceback.format_exc()));raise
    finally:dump(out/"end.json",dict(utc=utc(),outcome=outcome))
if __name__=="__main__":
    if sys.argv[1:]==["smoke"]:smoke()
    elif not sys.argv[1:]:main()
