"""Read the immutable G1 kernels; place all new evidence in the G2 directory."""
from pathlib import Path
import sys, os, json, hashlib, subprocess, time
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
G1=ROOT.parent/"global_config_coordination_g1"
sys.path.insert(0,str(G1))
os.environ.setdefault("G1_ORTOOLS",str(REPO.parent/"P1_worktree"/".runtime-domain-cpsat"))
import g1io
g1io.OUT=ROOT/"evidence"
from g1io import problem, assess, read, write, load, record, sha, Layout, Q
from construct import assemble, idle_plan, Frontier
def utc(): return datetime.now(timezone.utc).isoformat()
def git(*args): return subprocess.check_output(["git","-C",str(REPO),*args]).decode().strip()
def check_inputs():
    lock=read(G1/"input_lock.json")
    assert git("rev-parse","f55b11df^{tree}")=="44d680eec78a714066eb66d8f7dd0d89210d7d3f"
    assert git("branch","--show-current")=="codex/critical-interval-g2"
    assert git("remote","get-url","origin")=="https://github.com/YBEMR/paper.git"
    for row in lock["upstream"]:
        assert sha((REPO/row["path"]).read_bytes())==row["sha256"]
        assert git("rev-parse",row["commit"]+":"+row["path"])==row["git_blob"]
    for n,h in lock["new_instances"].items(): assert sha((G1/"instances"/n).read_bytes())==h
    for n,h in lock["solver_runtime_files"]: assert sha((g1io.runtime/n).read_bytes())==h
    for file in sorted(G1.glob("*.py")):
        assert git("hash-object",str(file))==git("rev-parse","f55b11df:"+file.relative_to(REPO).as_posix())
    return lock
