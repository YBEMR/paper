"""One-time offline verification following a terminal experiment receipt."""
import subprocess
import sys
import time
from settings import ROOT,read,write

TERMINAL={"AWAITING_INDEPENDENT_AUDIT","PREFLIGHT_STOP","FORMAL_INTERRUPTION"}

def finalize():
    assert not (ROOT/"postprocess.json").exists()
    while True:
        try:state=read(ROOT/"execution.json")
        except PermissionError:
            time.sleep(.1);continue
        if state["status"] in TERMINAL:break
        time.sleep(5)
    start=time.time();record=dict(status="VERIFYING",start=start,terminal=state["status"],calls=[])
    write(ROOT/"postprocess.json",record)
    try:
        for name,args in [("outcome",[]),("figures",[])]:
            before=time.time()
            with (ROOT/"logs"/("post_"+name+".txt")).open("xb") as f:
                proc=subprocess.run([sys.executable,"-B","-u",str(ROOT/(name+".py")),*args],cwd=ROOT,
                                    stdout=f,stderr=subprocess.STDOUT,timeout=max(.02,780-(before-start)))
            record["calls"].append(dict(name=name,elapsed_s=time.time()-before,code=proc.returncode))
            if proc.returncode:raise RuntimeError((name,proc.returncode))
        record["status"]="VERIFIED";record["verified_at"]=time.time()
        write(ROOT/"postprocess.json",record)
        from seal import seal
        seal(start)
    except Exception:
        import traceback
        record.update(status="AUDIT_EXCEPTION",traceback=traceback.format_exc(),stopped_at=time.time())
        write(ROOT/"postprocess.json",record)
        raise
if __name__=="__main__":finalize()
