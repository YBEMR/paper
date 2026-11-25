"""Publish only the data sealed in this run, with byte-for-byte Git verification."""
import hashlib
import os
import subprocess
import tempfile
import time
from settings import BASE,ROOT,REPO,read,write,sha

BRANCH="codex/domain-joint-e2c2"
REMOTE="https://github.com/YBEMR/paper.git"
def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO)
def paths(buf):
    return {v.decode("utf8") for v in buf.split(b"\0") if v}
def publish():
    # Single registered execution. No numerical processes are launched here.
    while not (ROOT/"snapshot.json").is_file():
        state=ROOT/"postprocess.json"
        if state.is_file():
            try:fail=read(state)["status"]=="AUDIT_EXCEPTION"
            except PermissionError:fail=False
            if fail:raise RuntimeError("independent audit requires inspection")
        time.sleep(5)
    snap=read(ROOT/"snapshot.json");manifest=read(ROOT/"manifest.json");budget=read(ROOT/"budget.json")
    assert snap["freeze"]==manifest["freeze"]==git("rev-parse","HEAD").decode().strip()
    assert git("branch","--show-current").decode().strip()==BRANCH and git("remote","get-url","origin").decode().strip()==REMOTE
    assert git("rev-parse","HEAD^").decode().strip()==BASE
    assert not git("diff","--cached","--name-only","-z")
    prefix=ROOT.relative_to(REPO).as_posix()+"/"
    expected={prefix+p for p in snap["files"]}|{prefix+"snapshot.json"}
    for p,h in snap["files"].items():
        file=ROOT/p
        assert file.resolve().is_relative_to(ROOT) and file.is_file() and sha(file.read_bytes())==h,p
        assert file.stat().st_size<99*2**20,p
    tracked=paths(git("ls-files","-z","--",prefix))
    new=paths(git("ls-files","--others","--exclude-standard","-z","--",prefix))
    assert not git("diff","--name-only","-z","--",prefix) and expected==tracked|new
    def stage(names):
        with tempfile.NamedTemporaryFile(delete=False,suffix=".nul") as f:
            f.write(b"".join(s.encode()+b"\0" for s in sorted(names)))
        try:git("add","--pathspec-from-file="+f.name,"--pathspec-file-nul")
        finally:os.unlink(f.name)
        assert paths(git("diff","--cached","--name-only","-z"))==names
        git("diff","--cached","--check","--",prefix+"*.py",prefix+"*.md",prefix+"*.csv")
    stage(new)
    for rec in git("ls-files","-s","-z","--",prefix).split(b"\0"):
        if not rec:continue
        info,rel=rec.split(b"\t")
        b=(REPO/rel.decode()).read_bytes()
        assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==info.split()[1].decode(),rel
    assert time.time()-budget["publication_started"]<870
    git("commit","-m","Archive D3 E2-c2 timed replays, independent SAFE certificates and paired decision")
    result=git("rev-parse","HEAD").decode().strip()
    def push_checked():
        git("push","origin","HEAD:refs/heads/"+BRANCH)
        rev=git("ls-remote","--heads","origin",BRANCH).decode().split()[0]
        assert rev==git("rev-parse","HEAD").decode().strip()
    push_checked()
    elapsed=time.time()-budget["publication_started"]
    total=budget["preflight_s"]+budget["formal_s"]+elapsed
    receipt=dict(result=result,freeze=snap["freeze"],remote=REMOTE,branch=BRANCH,verified_utc_epoch=time.time(),
                 audit_and_publication_s=elapsed,total_charge_s=total,within_budget=(elapsed<=900 and total<=23400))
    write(ROOT/"publication.json",receipt)
    stage({prefix+"publication.json"})
    git("commit","-m","Record verified remote identity and cumulative D3 experiment budget")
    push_checked()
    assert not git("status","--porcelain","--",prefix)
    print(result,git("rev-parse","HEAD").decode().strip(),total,flush=True)
if __name__=="__main__":publish()
