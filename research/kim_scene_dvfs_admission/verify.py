"""Independent audit of enumerated archives. The oracle imports only frozen physics and events."""
import argparse
import csv
import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "kim_synthetic_platform_v1"
sys.path.insert(0, str(BASE))

from events import Request, simulate
from profiles import build_chains, thermal_kwargs
from thermal import evaluate_thermal
from workloads import FROZEN, workload

OPPS = tuple("".join(p) for p in product("LMH", repeat=3))
SUBSET = ("LHL", "HHH")
STATUS = {"SAFE": 1, "VIOLATION": 2, "UNRESOLVED": 3}
TIE_J = 1e-9
CHECK_J = 1e-7
N = len(OPPS)
PLATFORM = json.loads((BASE / "platform.json").read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def encode(seq):
    index = 0
    for opp in seq:
        index = index * N + OPPS.index(opp)
    return index


def decode(index):
    coords = np.unravel_index(index, (N,)*4)
    return tuple(OPPS[i] for i in coords)


@dataclass(frozen=True)
class Candidate:
    d: str
    seq: tuple
    energy: float


def choose(candidates):
    if not candidates:
        return None
    floor = min(c.energy for c in candidates)
    ties = (c for c in candidates if c.energy <= floor+TIE_J)
    return min(ties, key=lambda c:(c.d, encode(c.seq)))


@lru_cache(maxsize=108)
def local_time(d, scene, opp):
    # Derive shifts afresh from the workload in the parent commit. A future
    # prefix cannot repair a missed absolute deadline in an earlier scene.
    jobs, breaks, end = workload("10s", 25)
    start = breaks[scene][0]
    stop = breaks[scene+1][0] if scene < 3 else end
    local = [Request(q.id, q.app, q.release_ns-start, q.deadline_ns-start)
             for q in jobs if start <= q.release_ns < stop]
    return simulate(local, build_chains(PLATFORM,FROZEN,d,opp), stop-start)


def original_replay(d, seq, ambient, reset=False):
    initial = np.full(4, 30.0)
    energy, required, phases = 0.0, 0, []
    lower, upper = np.full(4,-np.inf), np.full(4,-np.inf)
    state = initial
    min_slack = np.inf
    for s, opp in enumerate(seq):
        schedule = local_time(d,s,opp)
        required += len(schedule.requests)
        min_slack = min(min_slack, schedule.min_slack_ns)
        if not schedule.deadline_feasible:
            return {"status":0}
        require(len(schedule.completions_ns)==len(schedule.requests), "job omitted by oracle")
        kwargs = thermal_kwargs(PLATFORM,opp,ambient,True,"base")
        kwargs["initial_C"] = initial if reset else state
        result = evaluate_thermal(schedule.duration_ns*1.e-9,schedule.active_w,**kwargs,
                                  transfer_W=schedule.transfer_w)
        state = np.asarray(result["final_C"])
        energy += result["energy_J"]
        lower = np.maximum(lower,result["peak_lower_C"])
        upper = np.maximum(upper,result["peak_upper_C"])
        phases.append(STATUS[result["thermal_status"]])
    status = 2 if 2 in phases else 3 if 3 in phases else 1
    return dict(status=status, energy=energy, required=required, min_slack_ms=min_slack/1e6,
                lower=lower,upper=upper,end=state)


def audit_archive(d, ambient, local, file):
    with np.load(file,allow_pickle=False) as obj:
        status, energy = obj["status"], obj["energy_j"]
    require(status.dtype == np.uint8 and energy.dtype==np.float64, "wrong archive dtypes")
    require(status.shape == energy.shape == (N**4,), "incomplete search space")
    require(set(np.unique(status)) <= {0,1,2,3}, "unrecognized classification")
    require(np.array_equal(np.isnan(energy), status==0), "missing energy differs from deadline policy")
    require(np.all(np.isfinite(energy[status!=0])) and np.all(energy[status!=0]>0), "invalid energy")
    scene_legal = np.array([[int(local[d,s,o]["status"])!=0 for o in OPPS] for s in range(4)])
    expected = (scene_legal[0,:,None,None,None] & scene_legal[1,None,:,None,None] &
                scene_legal[2,None,None,:,None] & scene_legal[3,None,None,None,:])
    require(np.array_equal(status!=0,expected.ravel()),"full product deadline mask mismatch")
    counts = np.bincount(status,minlength=4)
    require(sum(counts)==N**4, "combination count failed")
    return status,energy


def audit_fixed(d, ambient, state, energy, old):
    for o in OPPS:
        k = encode((o,)*4)
        r = old[(ambient,d,o)]
        deadline_ok = r["deadline_ok"].lower()=="true"
        expected = STATUS[r["thermal_status"]] if deadline_ok else 0
        require(state[k]==expected,f"frozen fixed safety differs: {(d,ambient,o)}")
        if expected:
            require(abs(energy[k]-float(r["energy_j"]))<CHECK_J,f"fixed energy mismatch: {(d,ambient,o)}")


def selections(d, space, local):
    state, energy = space
    fixed = [Candidate(d,(o,)*4,float(energy[encode((o,)*4)])) for o in OPPS if state[encode((o,)*4)]==1]
    safe = np.flatnonzero(state==1)
    joint = None
    if len(safe):
        floor = np.min(energy[safe])
        winner = safe[np.flatnonzero(energy[safe]<=floor+TIE_J)[0]]
        joint = Candidate(d,decode(winner),float(energy[winner]))
    greedy, greedy_energy = [], 0.
    for s in range(4):
        feasible = [(o,float(local[d,s,o]["energy_j"])) for o in OPPS if int(local[d,s,o]["status"])==1]
        if not feasible:
            break
        floor = min(v for _,v in feasible)
        o,e = next((o,e) for o,e in feasible if e<=floor+TIE_J)
        greedy.append(o)
        greedy_energy += e
    independent = Candidate(d,tuple(greedy),greedy_energy) if len(greedy)==4 else None
    return {"fixed":choose(fixed),"independent":independent,"joint":joint}


def check_decision(row, wanted, space, ambient):
    method = row["method"]
    if wanted is None:
        require(row["deployment"] is None and row["physical"] is None, f"spurious {method} selection")
        return
    require((row["deployment"],tuple(row["opps"]))==(wanted.d,wanted.seq), f"wrong {method} selection")
    require(abs(row["predicted_j"]-wanted.energy)<CHECK_J, "selection estimate mismatch")
    code, energy = space[wanted.d]
    idx = encode(wanted.seq)
    oracle = original_replay(wanted.d,wanted.seq,ambient)
    require(oracle["status"]==code[idx]!=0, "selected continuous status mismatch")
    require(abs(energy[idx]-oracle["energy"])<CHECK_J, "selected physical energy mismatch")
    phys = row["physical"]
    require(phys["feasible"] == (code[idx]==1), "selected feasibility mismatch")
    require(abs(phys["energy_j"]-oracle["energy"])<CHECK_J, "published replay energy mismatch")
    require(phys["deadline_ok"] and phys["required"]==phys["completed"]==oracle["required"]==500,
            "uncompleted or late selected workload")
    require(abs(phys["min_slack_ms"]-oracle["min_slack_ms"])<=1e-9, "deadline slack mismatch")
    require(np.max(np.abs(phys["final_c"]-oracle["end"]))<=1e-7, "final physical state mismatch")
    require(np.all(oracle["lower"]<=np.array(phys["peak_upper_c"])+1e-7)
            and np.all(oracle["upper"]>=np.array(phys["peak_lower_c"])-1e-7),
            "physical peak certificates disjoint")
    if method=="independent":
        reset = original_replay(wanted.d,wanted.seq,ambient,reset=True)
        require(reset["status"]==1 and abs(reset["energy"]-wanted.energy)<CHECK_J, "independent reset mismatch")


def load_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def main(raw):
    local_rows = load_csv(raw/"local.csv")
    decisions = json.loads((raw/"decisions.json").read_text(encoding="utf-8"))
    methods = ("fixed","independent","joint")
    require(len(decisions)==6 and len(local_rows)==2*2*4*N,"audit counts differ from design")
    published = {(r["ambient"],r["method"]):r for r in decisions}
    require(len(published)==6,"duplicate method record")
    old = {(int(r["ambient_c"]),r["deployment"],r["opp"]):r
           for r in load_csv(BASE/"raw"/"candidates.csv")
           if (r["mode"],r["window"],r["fps"],r["leakage"],r["variation"])==
           ("continuous","10s","25","on","base")}
    require(len(old)==108,"frozen base diagonal incomplete")
    matches = 0
    checks = []
    for a in (25,30):
        local = {(r["deployment"],int(r["scene"]),r["opp"]):r for r in local_rows if int(r["ambient"])==a}
        require(len(local)==216,"duplicate/missing scene/OPP")
        space,method_values = {}, {m:[] for m in methods}
        for d in ("A","C"):
            state,energy = audit_archive(d,a,local,raw/f"space_{a}_{d}.npz")
            space[d] = (state,energy)
            audit_fixed(d,a,state,energy,old)
            bests = selections(d,space[d],local)
            for m,v in bests.items():
                if v is not None:
                    method_values[m].append(v)
            if bests["joint"] is not None:
                joint_j = bests["joint"].energy
                for v in [bests["fixed"],bests["independent"]]:
                    if v is not None and state[encode(v.seq)]==1:
                        require(joint_j <= energy[encode(v.seq)] + TIE_J, "joint misses admissible competitor")
            for seq in product(SUBSET,repeat=4):
                k = encode(seq)
                truth = original_replay(d,seq,a)
                require(state[k]==truth["status"],f"two-OPP oracle status mismatch {(a,d,seq)}")
                if truth["status"]:
                    require(abs(energy[k]-truth["energy"])<CHECK_J,f"two-OPP oracle energy mismatch {(a,d,seq)}")
                matches+=1
            checks.append({"ambient":a, "deployment":d, "deadline_failed":int(np.sum(state==0)),
                           "safe":int(np.sum(state==1)),"overtemp":int(np.sum(state==2)),
                           "unresolved":int(np.sum(state==3))})
        for m in methods:
            check_decision(published[a,m],choose(method_values[m]),space,a)
    return {"status":"PASS","full_policy_records":4*N**4, "frozen_fixed_rows":len(old),
            "independent_original_solver_subset":list(SUBSET),"oracle_policy_replays":matches,
            "methods_verified":6,"counts":checks}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=HERE/"raw")
    args=parser.parse_args()
    print(json.dumps(main(args.raw),indent=2))
