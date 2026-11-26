"""Bound independent audit and seal bytes for the explicitly scoped publication."""
import subprocess
import sys
import time
from design_d import ROOT,REPO,BASE,read,write,sha

def run():
    st=read(ROOT/"execution.json")
    assert st["status"] in ("PREFLIGHT_STOP","FORMAL_INTERRUPTION","AUDIT")
    m=read(ROOT/"manifest.json")
    start=time.time(); assert not (ROOT/"postprocess.json").exists()
    write(ROOT/"postprocess.json",dict(start=start,status="AUDIT"))
    remaining=900-st["preflight_s"]-40
    with (ROOT/"logs"/"independent.txt").open("xb") as f:
        p=subprocess.run([sys.executable,"-B","-u",str(ROOT/"report_d.py")],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=max(1,remaining))
    if p.returncode:raise RuntimeError("independent audit failed; see logs/independent.txt")
    for rel,h in {**m["source_hashes"],**m["inherited"]}.items():assert sha((REPO/rel).read_bytes())==h,rel
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()==m["freeze"]
    duration=time.time()-start
    assert st["preflight_s"]+duration<900 and st["formal_s"]<=8100
    verified=read(ROOT/"decision.json")["verified"]
    write(ROOT/"postprocess.json",dict(start=start,status="VERIFIED",duration=duration,verified=verified))
    write(ROOT/"budget.json",dict(publication_started=start,preflight_s=st["preflight_s"],formal_s=st["formal_s"],
          independent_to_seal_s=duration,limit=9000))
    files={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(ROOT.rglob("*"))
           if p.is_file() and "__pycache__" not in p.parts and p.name!="snapshot.json"}
    assert not any(k.endswith(".tmp") for k in files)
    write(ROOT/"snapshot.json",dict(base=BASE,freeze=m["freeze"],verified=verified,files=files))
if __name__=="__main__":run()
