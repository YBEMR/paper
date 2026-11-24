"""Frozen D017 residency; only full inference path selection is added."""
from copy import deepcopy
from pathlib import Path
import sys, json, hashlib
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/kim_multidnn_expansion"))
import catalog
from events import Request, simulate
from profiles import build_chains, thermal_kwargs
import thermal
import numpy as np

PERIOD = 40_000_000
NODES = ("cpu", "gpu", "dla0", "dla1")
MODES = ("constant", "gpu_idle", "gpu_dla_idle")
IDS = (("D078", "D077*", "D076*"), ("D055", "D054", "D053"), ("D019", "D018", "D017"))
PLATFORM = catalog.PLATFORM
BASE = json.loads((ROOT / "research/kim_multidnn_expansion/expanded_input.json").read_bytes())
SOURCE = json.loads((ROOT / "research/multidnn_model_review/protocol.json").read_bytes())
CONFIG_PATH = HERE / "config.json"

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, x): Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")

def definitions():
    d17 = BASE["deployments"]["D017"]["stages"]
    full = {"0": [["GPU",0,53]], "3": [["GPU",0,178]]}
    paths = {}
    for p in range(3):
        for q in range(3):
            stages = deepcopy(d17)
            for app, choice in [("0",p),("3",q)]:
                if choice == 0: stages[app] = full[app]
                elif choice == 1: stages[app] = [deepcopy(d17[app][0]), ["GPU",d17[app][0][2]+1,full[app][0][2]]]
            paths[IDS[p][q]] = dict(stages=stages, paths=[p,q], resident_dla_engines=4)
    frozen = deepcopy(BASE)
    frozen["deployments"] = paths
    loads = {}
    for name in ("balanced","concurrent"):
        for sc, active in SOURCE["loads"][name]["active"].items():
            key = "a"+"".join(map(str,active))
            row = loads.setdefault(key, dict(active=active, frames=[], sources=[]))
            n = SOURCE["scene_frames"][sc]
            row["frames"] = sorted(set(row["frames"]+[n]))
            row["sources"].append(dict(load=name, scene=sc, frames=n))
    return frozen, loads

def jobs(active, n=1):
    return tuple(Request(f"f{f:04d}-a{a}", a, f*PERIOD, (f+1)*PERIOD) for f in range(n) for a in active)

def schedule(frozen, load, path, opp, n=1):
    return simulate(jobs(load["active"],n), build_chains(PLATFORM,frozen,path,opp),n*PERIOD)

def levels(schedule, opp, mode):
    out=[]
    for active in schedule.active_w:
        gpu="L" if mode!="constant" and active[1]==0 else opp[1]
        dla="L" if mode=="gpu_dla_idle" and active[2]==0 and active[3]==0 else opp[2]
        out.append(opp[0]+gpu+dla)
    return out
