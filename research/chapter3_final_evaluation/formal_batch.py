"""Immutable roster with one attempt per cell, parent wall clock and one physical core per worker."""
import concurrent.futures
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
from time import perf_counter
import psutil

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"formal"
CASES=("S32","S80","D1","D2","F1","F2")
MAIN=("Greedy","GA","SA","Adapted-ETA-TS","Adapted-eFLS","AB","Proposed")
SEEDS=(101,102,103)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")
    tmp.replace(path)


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def roster():
    rows=[]
    for case in CASES:
        methods=[(m,"T3") for m in MAIN]
        if case in ("S32","S80","D1","D2"):
            methods.append(("Compact","T3"))
        if case in ("S80","D1","D2"):
            methods.extend(("Proposed",mode) for mode in ("T0","T1","T2"))
        for seed in SEEDS:
            for method,mode in methods:
                rows.append(dict(case=case,method=method,mode=mode,seed=seed,
                            id=f"{case}_{method}_{mode}_{seed}",budget_s=300 if case=="S32" else 900))
    assert len(rows)==165 and sum(r["budget_s"] for r in rows)==134100
    return rows


def physical_cpus():
    if sys.platform!="win32":
        return psutil.Process().cpu_affinity()[:1]
    from ctypes import wintypes
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    count=wintypes.DWORD()
    kernel.GetLogicalProcessorInformationEx(0,None,ctypes.byref(count))
    buf=ctypes.create_string_buffer(count.value)
    if not kernel.GetLogicalProcessorInformationEx(0,buf,ctypes.byref(count)):
        raise ctypes.WinError()
    raw=buf.raw
    pos=0
    allowed=set(psutil.Process().cpu_affinity())
    cores=[]
    while pos<len(raw):
        size=int.from_bytes(raw[pos+4:pos+8],"little")
        if size<40:
            raise ValueError("Unexpected physical topology")
        mask=int.from_bytes(raw[pos+32:pos+40],"little")
        group=[i for i in sorted(allowed) if mask>>i&1]
        if group:
            cores.append(group[0])
        pos+=size
    return cores


def run_process(action,row,folder,cpu,charge,subject):
    folder.mkdir()
    budget=row["budget_s"]
    info=dict(**row,action=action,cpu=cpu,prior_charge_s=charge,subject=subject,utc=utc())
    write(folder/"start.json",info)
    begin=perf_counter()
    end=begin+budget-charge
    args=[sys.executable,"-B","-u",str(ROOT/"formal_worker.py"),action,row["case"],row.get("method","pool"),
          row.get("mode","pool"),str(row.get("seed",101)),str(folder),str(begin),str(end),str(budget),str(charge)]
    env=dict(os.environ,OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",NUMBA_NUM_THREADS="1")
    with (folder/"worker.log").open("xb") as log:
        process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            psutil.Process(process.pid).cpu_affinity([cpu])
            code=process.wait(timeout=max(.01,end-perf_counter()))
            status="COMPLETE" if code==0 and (folder/"result.json").is_file() else "ERROR"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            status="TIME_LIMIT"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    elapsed=perf_counter()-begin
    info.update(status=status,exit_code=process.returncode,wall_s=elapsed,charged_s=charge+elapsed,ended=utc())
    # Output generated after the actual deadline is never a completed endpoint.
    result=folder/"result.json"
    if result.exists() and action!="pool" and read(result)["elapsed_s"]>budget:
        info["status"]="LATE_OUTPUT"
    write(folder/"receipt.json",info)
    return info


def main():
    lock=read(ROOT/"execution_lock.json")
    for path,digest in lock["files"].items():
        if sha(ROOT/path)!=digest:
            raise RuntimeError(f"Execution source drift: {path}")
    if lock["roster"]!=roster():
        raise ValueError("Run roster changed")
    freeze=read(ROOT/"publication_freeze.json")
    subject=freeze["remote_protocol_commit"]
    cpus=physical_cpus()
    if not cpus:
        raise RuntimeError("No physical cores available")
    OUT.mkdir()
    (OUT/"pools").mkdir()
    (OUT/"cells").mkdir()
    write(OUT/"batch_start.json",dict(utc=utc(),subject=subject,protocol_sha256=sha(ROOT/"execution_lock.json"),
          cores=cpus,physical_jobs=165,alias="T3 uses the exact main Proposed execution in S80/D1/D2"))
    slots=queue.Queue()
    for cpu in cpus:
        slots.put(cpu)
    def launch(action,row,path,charge):
        cpu=slots.get()
        try:
            return run_process(action,row,path,cpu,charge,subject)
        finally:
            slots.put(cpu)
    outcome="INTERRUPTED"
    try:
        with concurrent.futures.ThreadPoolExecutor(len(cpus)) as pool:
            initial={c:pool.submit(launch,"pool",dict(case=c,budget_s=60 if c=="S32" else 180),
                     OUT/"pools"/c,0) for c in CASES}
            init={c:f.result() for c,f in initial.items()}
            if any(r["status"]!="COMPLETE" for r in init.values()):
                outcome="POOL_ERROR"
                return
            tasks=[pool.submit(launch,"cell",r,OUT/"cells"/r["id"],init[r["case"]]["charged_s"]) for r in roster()]
            statuses={}
            for future in concurrent.futures.as_completed(tasks):
                row=future.result()
                statuses[row["status"]]=statuses.get(row["status"],0)+1
                write(OUT/"batch_progress.json",dict(at=utc(),outcomes=statuses,total=165))
            outcome="FINISHED"
    finally:
        write(OUT/"batch_end.json",dict(utc=utc(),outcome=outcome))


if __name__=="__main__":
    main()

