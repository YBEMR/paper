"""Preregistered full search of four scene-level clocks; no objective-based pruning."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform as host
import subprocess
import sys
from time import perf_counter

# Small matrix products have no benefit from launching multiple BLAS workers.
for env_name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[env_name] = "1"
import numpy as np

from joint_thermal import SAFE, VIOLATION, compile_scene
from scene_events import (OPPS, PLATFORM, compare_frozen_fixed, replay_sequence,
                          split_workload, thermal_kwargs, time_scene)

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE/"protocol.json").read_text(encoding="utf-8"))
N = len(OPPS)
EPS = CFG["energy_tie_J"]
SIZE = N**4
INITIAL = np.array(CFG["reference_C"], dtype=float)


def verify_freeze(commit):
    if len(commit)!=40:
        raise ValueError("Expected the full protocol commit")
    relative = HERE.relative_to(HERE.parents[1]).as_posix()
    cmd = ["git", "-C", str(HERE.parents[1])]
    parent = subprocess.check_output(cmd+["rev-parse",commit+"^"],text=True).strip()
    if parent!=CFG["base"]:
        raise ValueError("Wrong frozen parent")
    for f in ("protocol.json","protocol.md","run.py","joint_thermal.py","scene_events.py"):
        original = subprocess.check_output(cmd+["show",f"{commit}:{relative}/{f}"])
        if original.replace(b"\r\n",b"\n")!=(HERE/f).read_bytes().replace(b"\r\n",b"\n"):
            raise ValueError(f"Runtime differs from preregistration: {f}")
    changed = subprocess.run(cmd + ["diff","--quiet",commit,"--","research/kim_synthetic_platform_v1",
                                   "research/kim_thermal_v1","research/kim_case_b_freeze"])
    if changed.returncode:
        raise ValueError("Parent model, data or evaluator differs from preregistration")


def write_json(path, data):
    path.write_bytes((json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8"))


def write_csv(path, data):
    with path.open("w",encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(data[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def decode(code):
    return [OPPS[(int(code)//(N**(3-s)))%N] for s in range(4)]


def candidate(key, value):
    return dict(code=int(key),opps=decode(key),predicted_j=float(value))


def pick(codes, scores):
    if not len(codes):
        return None
    near = np.flatnonzero(scores <= float(np.min(scores))+EPS)
    i = near[np.argmin(codes[near])]
    return candidate(codes[i],scores[i])


def combine(previous, local):
    return np.where((previous==2)|(local==VIOLATION), 2,
                    np.where((previous==3)|(local!=SAFE),3,1)).astype(np.uint8)


def local_selection(tables, schedules, ambient, deployment):
    rows = []
    local_scores = np.full((4,N), np.inf)
    choices = []
    for scene, kernels in enumerate(tables):
        for i, kernel in enumerate(kernels):
            sched = schedules[scene][i]
            state, value = 0, None
            if kernel is not None:
                e, _, code = kernel.batch(INITIAL[None,:])
                state = int(combine(np.uint8(1),code[0]))
                value = float(e[0])
                if state==1:
                    local_scores[scene,i] = value
            rows.append(dict(ambient=ambient,deployment=deployment,scene=scene,opp=OPPS[i],
                             deadline_ok=sched.deadline_feasible,status=state,energy_j=value,
                             requested=len(sched.requests),min_slack_ms=sched.min_slack_ns/1e6))
        finite = np.flatnonzero(np.isfinite(local_scores[scene]))
        if len(finite):
            e = local_scores[scene,finite]
            choices.append(int(finite[np.flatnonzero(e<=e.min()+EPS)[0]]))
    choice = None
    if len(choices)==4:
        ix = sum(k*N**(3-j) for j,k in enumerate(choices))
        choice = candidate(ix,sum(local_scores[j,k] for j,k in enumerate(choices)))
    return choice, local_scores, rows


def fixed_selection(tables):
    ok, energies = [], []
    deadline_count = unresolved = 0
    for i in range(N):
        if any(table[i] is None for table in tables):
            continue
        deadline_count += 1
        T = INITIAL[None,:]
        state, energy = np.ones(1,dtype=np.uint8), 0.
        for table in tables:
            e,T,s=table[i].batch(T)
            energy += e[0]
            state = combine(state,s)
        if state[0]==1:
            ok.append(i*(N**3+N**2+N+1))
            energies.append(energy)
        elif state[0]==3:
            unresolved += 1
    return pick(np.array(ok),np.array(energies)), len(ok),deadline_count,unresolved


def joint_search(tables):
    keys, temps = np.array([0],dtype=np.int32), INITIAL[None,:]
    eprev, sprev = np.zeros(1), np.ones(1,dtype=np.uint8)
    by_depth = []
    for table in tables:
        keys_next, temps_next, scores_next, status_next = [], [], [], []
        for i,kernel in enumerate(table):
            if kernel is None or not len(keys):
                continue
            e,end,status = kernel.batch(temps)
            keys_next.append(keys*N+i)
            temps_next.append(end)
            scores_next.append(eprev+e)
            status_next.append(combine(sprev,status))
        if not keys_next:
            keys=np.empty(0,dtype=np.int32)
            eprev,sprev=np.empty(0),np.empty(0,dtype=np.uint8)
            by_depth.append(0)
            continue
        keys,temps = np.concatenate(keys_next),np.concatenate(temps_next)
        eprev,sprev = np.concatenate(scores_next), np.concatenate(status_next)
        by_depth.append(len(keys))
    energies = np.full(SIZE,np.nan)
    states = np.zeros(SIZE,dtype=np.uint8)
    energies[keys],states[keys] = eprev,sprev
    ok = np.flatnonzero(states==1)
    return pick(ok,energies[ok]),states,energies,by_depth


def compare_sets(local,states,energy):
    # Enumerate reset scores by broadcasting the additive objective on the
    # same action IDs. Inf denotes a reset-infeasible action in some scene.
    reset = (local[0,:,None,None,None] + local[1,None,:,None,None]
             +local[2,None,None,:,None] + local[3,None,None,None,:]).ravel()
    reset_ok, cont_ok = np.isfinite(reset), states==1
    both = np.flatnonzero(reset_ok & cont_ok)
    reset_winner=pick(both,reset[both])
    if reset_winner:
        reset_winner["physical_j"]=float(energy[reset_winner["code"]])
    return dict(reset_feasible=int(np.count_nonzero(reset_ok)),both_feasible=len(both),
                reset_only=int(np.sum(reset_ok & ~cont_ok)),
                continuous_only=int(np.sum(~reset_ok & cont_ok)),
                both_feasible_lowest_reset_score=reset_winner)


def warmup():
    kw=thermal_kwargs(PLATFORM,"LLL",25,True,"base")
    kernel=compile_scene(np.array([.005,.003]),np.zeros((2,4)),np.zeros(2),kw)
    kernel.batch(INITIAL[None,:])


def run(freeze, raw):
    verify_freeze(freeze)
    raw.mkdir(exist_ok=True,parents=True)
    start = perf_counter()
    warmup()
    timing={"warmup_s":perf_counter()-start}
    start = perf_counter()
    scenes=split_workload(CFG["window"],CFG["fps"])
    schedules={d:[[time_scene(PLATFORM,s,d,o) for o in OPPS] for s in scenes] for d in CFG["deployments"]}
    timing["shared_scheduling_s"]=perf_counter()-start
    timing["machine"]=dict(python=sys.version.split()[0],os=host.platform(),cpu=host.processor(),
                           threads=1)
    all_rows, all_decisions, deploy_rows, counters, comparisons, clocks = [],[],[],[],[],[]
    for ambient in CFG["ambient"]:
        picks={method:[] for method in CFG["methods"]}
        for d in CFG["deployments"]:
            tt={"ambient":ambient,"deployment":d}
            t=perf_counter()
            tables=[]
            for scheds in schedules[d]:
                table=[]
                for opp,s in zip(OPPS,scheds):
                    kw=thermal_kwargs(PLATFORM,opp,ambient,True,"base")
                    table.append(compile_scene(s.duration_ns*1e-9,s.active_w,s.transfer_w,kw)
                                 if s.deadline_feasible else None)
                tables.append(table)
            tt["compile_s"]=perf_counter()-t
            t=perf_counter()
            fixed, nf, nd, nu = fixed_selection(tables)
            tt["fixed_search_s"]=perf_counter()-t
            t=perf_counter()
            independent, local, rows=local_selection(tables,schedules[d],ambient,d)
            tt["independent_search_s"]=perf_counter()-t
            all_rows.extend(rows)
            kernels=[k for table in tables for k in table if k is not None]
            fallback0=sum(k.fallback_calls for k in kernels)
            t=perf_counter()
            joint, states, energy, depths=joint_search(tables)
            tt["joint_search_s"]=perf_counter()-t
            fallback=sum(k.fallback_calls for k in kernels)-fallback0
            counts=np.bincount(states,minlength=4)
            t=perf_counter()
            np.savez_compressed(raw/f"space_{ambient}_{d}.npz",status=states,energy_j=energy)
            tt["npz_write_s"]=perf_counter()-t
            t=perf_counter()
            diag=compare_sets(local,states,energy)
            comparisons.append(dict(ambient=ambient,deployment=d,**diag))
            tt["score_diagnostic_s"]=perf_counter()-t
            clocks.append(tt)
            counters.append(dict(ambient=ambient,deployment=d,space=SIZE,deadline_failed=int(counts[0]),
                                 safe=int(counts[1]),overtemp=int(counts[2]),unresolved=int(counts[3]),
                                 deadline_valid_prefixes=depths,joint_prefix_evaluations=sum(depths),
                                 joint_fallback_segment_replays=fallback,
                                 fixed_safe=nf,fixed_deadline_pass=nd,fixed_unresolved=nu))
            for method, choice in zip(CFG["methods"],(fixed,independent,joint),strict=True):
                if choice is not None:
                    picks[method].append(dict(deployment=d,**choice))
                deploy_rows.append(dict(ambient=ambient,deployment=d,method=method,
                                        opps=" ".join(choice["opps"]) if choice else "",
                                        predicted_j=choice["predicted_j"] if choice else ""))
            print(f"{ambient} C / {d}: exhaustive archive ready",flush=True)
        for method,opts in picks.items():
            mark=perf_counter()
            row=dict(ambient=ambient,method=method,deployment=None,opps=None,predicted_j=None,physical=None)
            if opts:
                floor=min(x["predicted_j"] for x in opts)
                winner=next(x for x in opts if x["predicted_j"]<=floor+EPS)
                row.update(winner)
                result=replay_sequence(PLATFORM,scenes,winner["deployment"],winner["opps"],ambient)
                if not result["deadline_ok"]:
                    raise AssertionError("Selected candidate missed a deadline")
                if method!="independent" and (not result["feasible"] or
                        abs(result["energy_j"]-winner["predicted_j"])>1e-7):
                    raise AssertionError("Predicted continuous optimum failed physical replay")
                if method=="fixed":
                    row["previous_fixed"]=compare_frozen_fixed("10s",25,winner["deployment"],winner["opps"][0],
                                                               ambient,result)
                row["physical"]=result
            row["selection_and_replay_s"]=perf_counter()-mark
            all_decisions.append(row)
    write_csv(raw/"local.csv",all_rows)
    write_csv(raw/"by_deployment.csv",deploy_rows)
    write_json(raw/"decisions.json",all_decisions)
    write_json(raw/"counts.json",counters)
    write_json(raw/"comparison_sets.json",comparisons)
    timing["by_environment_deployment"]=clocks
    timing["clock"]="perf_counter, single process, seconds; one measurement"
    timing["freeze_commit"]=freeze
    write_json(raw/"timing.json",timing)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",required=True)
    parser.add_argument("--raw",type=Path,default=HERE/"raw")
    args=parser.parse_args()
    run(args.freeze,args.raw)
