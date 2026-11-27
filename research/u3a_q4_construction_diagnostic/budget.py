"""Single sequential worker with cumulative CPU watchdog, including child setup and teardown."""
import subprocess
from runtime import *

def main():
    path=OUTPUT/"offline_budget.json"
    book=read(path) if path.exists() else dict(limit_cpu_s=600.,reserve_cpu_s=2.,cases=[])
    if any(x["status"]!="complete" for x in book["cases"]):
        raise RuntimeError("Existing incomplete receipt. Inspect it before continuing the batch.")
    for code in ("A06","B07","C10","C11"):
        if read(OUTPUT/code/"policies.json")["first_safe"] is not None:continue
        if any(x["case"]==code for x in book["cases"]):continue
        if (OUTPUT/code/"audit.json").exists():raise RuntimeError("orphan audit; reconcile before resume")
        used=sum(x["charged_cpu_s"] for x in book["cases"])
        if used>=book["limit_cpu_s"]-book["reserve_cpu_s"]:break
        receipt=dict(case=code,status="started",charged_cpu_s=0.)
        book["cases"].append(receipt)
        save(path,book)
        start=perf_counter()
        child=subprocess.Popen([sys.executable,"-Bu",str(HERE/"audit.py"),code])
        handle=psutil.Process(child.pid)
        last=0.
        killed=False
        while child.poll() is None:
            try:
                reading=handle.cpu_times()
                last=reading.user+reading.system
            except psutil.NoSuchProcess:break
            if used+max(last,perf_counter()-start)>=book["limit_cpu_s"]-book["reserve_cpu_s"]:
                child.kill()
                killed=True
                break
            __import__("time").sleep(.08)
        rc=child.wait()
        # On Windows a retained process handle gives the lifetime CPU even after exit.
        try:
            reading=handle.cpu_times()
            last=max(last,reading.user+reading.system)
        except psutil.NoSuchProcess:pass
        wall=perf_counter()-start
        receipt.update(observed_cpu_s=last,wall_s=wall,charged_cpu_s=max(wall,last+.25),
                       status="budget_stop" if killed else "complete" if rc==0 else "interrupted",exit=rc)
        save(path,book)
        print(code,receipt,flush=True)
        if rc or killed:break
    assert sum(x["charged_cpu_s"] for x in book["cases"])<=600
if __name__=="__main__":main()
