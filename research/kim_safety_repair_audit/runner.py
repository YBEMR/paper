"""Predeclared validation of actual selections and, only when needed, repairs."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

for env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[env] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "kim_scene_dvfs_admission"
sys.path.insert(0, str(PARENT))
import run as joint
from joint_thermal import compile_scene
from scene_events import OPPS, PLATFORM, evaluate_thermal, replay_sequence, thermal_kwargs, time_scene

BASE = "2d352e715463641d6e49e4691d4b16fb02296c80"
DEPLOYMENTS = ("A", "C")
N = len(OPPS)
EPS = 1e-9
RANK_BUDGET = 4096
NODES = ("cpu", "gpu", "dla0", "dla1")
INITIAL = np.array(PLATFORM["thermal"]["initial_C"], dtype=float)


def put_json(path, payload):
    path.write_bytes((json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)+"\n").encode())


def put_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_freeze(sha):
    if len(sha) != 40:
        raise ValueError("Specify the preregistration commit")
    root = HERE.parents[1]
    git = ["git", "-C", str(root)]
    parent = subprocess.check_output(git+["rev-parse", sha+"^"],text=True).strip()
    if parent != BASE:
        raise ValueError("Preregistration must be based on the pinned result")
    for name in ("runner.py", "design.py", "design.json", "protocol.md"):
        archived = subprocess.check_output(git+["show",f"{sha}:{(HERE/name).relative_to(root).as_posix()}"])
        if archived.replace(b"\r\n",b"\n") != (HERE/name).read_bytes().replace(b"\r\n",b"\n"):
            raise ValueError(f"Preregistered input changed: {name}")
    subprocess.run(git+["diff","--quiet",BASE,"--",
                         "research/kim_scene_dvfs_admission","research/kim_synthetic_platform_v1",
                         "research/kim_thermal_v1","research/kim_case_b_freeze"],check=True)


def encode(digits):
    code = 0
    for i in digits:
        code = code*N + int(i)
    return code


def digits(code):
    return [(int(code)//N**(3-j))%N for j in range(4)]


def choice(d, code, price):
    return dict(deployment=d, code=int(code), opps=[OPPS[i] for i in digits(code)],
                predicted_j=float(price))


def lowest(choices, field):
    available = [v for v in choices if v is not None]
    if not available:
        return None
    floor = min(v[field] for v in available)
    return min((v for v in available if v[field]<=floor+EPS),
               key=lambda v:(v["deployment"],v["code"]))


def scene_response(sched, kw, inlet):
    return evaluate_thermal(sched.duration_ns*1e-9, sched.active_w, transfer_W=sched.transfer_w,
                            **dict(kw, initial_C=inlet))


def local_tables(scenes, ambient):
    sched, scores, choices, rows = {}, {}, [], []
    kwargs = [thermal_kwargs(PLATFORM,o,ambient,True,"base") for o in OPPS]
    timing = {"scheduling_s":0., "reset_scoring_s":0.}
    for d in DEPLOYMENTS:
        t = perf_counter()
        sched[d] = [[time_scene(PLATFORM, sc, d, opp) for opp in OPPS] for sc in scenes]
        timing["scheduling_s"] += perf_counter()-t
        t = perf_counter()
        scores[d] = np.full((4,N),np.inf)
        seq = []
        for j, sc in enumerate(scenes):
            safe = []
            for k, opp in enumerate(OPPS):
                schedule = sched[d][j][k]
                h = scene_response(schedule,kwargs[k],INITIAL) if schedule.deadline_feasible else None
                status = h["thermal_status"] if h else "DEADLINE_FAILED"
                if h:
                    scores[d][j,k] = h["energy_J"]
                if status == "SAFE":
                    safe.append(k)
                rows.append(dict(deployment=d,scene_index=j,scene=sc.name,opp=opp,
                                 required=len(sc.requests), deadline_ok=schedule.deadline_feasible,
                                 status=status, energy_j=h["energy_J"] if h else None,
                                 min_slack_ms=schedule.min_slack_ns/1e6,
                                 **{"peak_"+n+"_c":h["peak_upper_C"][i] if h else None
                                    for i,n in enumerate(NODES)}))
            if safe:
                least = min(scores[d][j,k] for k in safe)
                seq.append(next(k for k in safe if scores[d][j,k]<=least+EPS))
        if len(seq)==4:
            choices.append(choice(d,encode(seq),sum(scores[d][j,k] for j,k in enumerate(seq))))
        timing["reset_scoring_s"] += perf_counter()-t
    return sched,kwargs,scores,choices,rows,timing


def lower_bound_certificate(d, sched, kw, scenes, ambient):
    # A constant componentwise lower bound for every reachable entry at any OPP.
    scalar = min(float(ambient), float(min(INITIAL)))
    inlet = np.full(4,scalar)
    rows, blocked = [], []
    for j,sc in enumerate(scenes):
        impossible = True
        for k,opp in enumerate(OPPS):
            s = sched[d][j][k]
            h = scene_response(s,kw[k],inlet) if s.deadline_feasible else None
            status = h["thermal_status"] if h else "DEADLINE_FAILED"
            if status not in ("VIOLATION","DEADLINE_FAILED"):
                impossible = False
            rows.append(dict(deployment=d,scene_index=j,scene=sc.name,opp=opp,
                             deadline_ok=s.deadline_feasible,status=status,inlet_c=scalar,
                             **{"peak_lo_"+n+"_c":h["peak_lower_C"][i] if h else None
                                for i,n in enumerate(NODES)}))
        if impossible:
            blocked.append(sc.name)
    return blocked, rows


def certify(scenes, case, sched, kw, output):
    started = perf_counter()
    options, solutions, lower_rows = [], {}, []
    unknown = False
    for d in DEPLOYMENTS:
        mark = perf_counter()
        blocked, lower = lower_bound_certificate(d,sched,kw,scenes,case["ambient"])
        lower_rows.extend(lower)
        cert_time = perf_counter()-mark
        if blocked:
            solutions[d] = dict(method="MONOTONE_CERTIFICATE",status="NO_SAFE",blocking_scenes=blocked,
                                lower_bound_s=cert_time,logical_action_count=N**4, safe=0,
                                complete_replay_calls=0)
            continue
        mark = perf_counter()
        tables = [[compile_scene(s.duration_ns*1e-9,s.active_w,s.transfer_w,kw[k])
                   if s.deadline_feasible else None for k,s in enumerate(phase)] for phase in sched[d]]
        compiled = perf_counter()-mark
        mark = perf_counter()
        w, states, energy, depths = joint.joint_search(tables)
        search_s = perf_counter()-mark
        count = np.bincount(states,minlength=4)
        unknown = unknown or bool(count[3])
        solutions[d] = dict(method="EXHAUSTIVE", status="SAFE_EXISTS" if count[1] else
                            ("UNRESOLVED" if count[3] else "NO_SAFE"),logical_action_count=N**4,
                            deadline_failed=int(count[0]),safe=int(count[1]),overtemp=int(count[2]),
                            unresolved=int(count[3]),deadline_valid_complete_sequences=int(sum(count[1:])),
                            deadline_valid_prefixes=depths,prefix_thermal_evaluations=sum(depths),
                            fallback_segment_replays=sum(kernel.fallback_calls for phase in tables
                                                         for kernel in phase if kernel is not None),
                            lower_bound_s=cert_time,compile_s=compiled,search_s=search_s)
        np.savez_compressed(output/f"space_{d}.npz",status=states,energy_j=energy)
        if w:
            options.append(choice(d,w["code"],w["predicted_j"]))
    put_csv(output/"lower_inlets.csv", lower_rows)
    winner = lowest(options,"predicted_j")
    p = None
    if winner:
        p = replay_sequence(PLATFORM,scenes,winner["deployment"],winner["opps"],case["ambient"])
        if not p["feasible"] or abs(p["energy_j"]-winner["predicted_j"])>1e-7:
            raise ArithmeticError("Oracle physical replay mismatch")
    method = "EXHAUSTIVE" if any(s["method"]=="EXHAUSTIVE" for s in solutions.values()) else "MONOTONE_CERTIFICATE"
    return dict(method=method,status="SAFE_EXISTS" if winner else ("UNRESOLVED" if unknown else "NO_SAFE"),
                deployment=winner["deployment"] if winner else None,code=winner["code"] if winner else None,
                opps=winner["opps"] if winner else None,energy_j=p["energy_j"] if p else None,
                physical=p,solutions=solutions,logical_complete_space=2*N**4,
                selected_full_replays=int(bool(winner)),optimality_proven=not unknown,total_s=perf_counter()-started)


def reset_score_tensor(table):
    return (table[0,:,None,None,None]+table[1,None,:,None,None]+
            table[2,None,None,:,None]+table[3,None,None,None,:]).ravel()


def enumerate_checks(method, seed, scores):
    candidates = []
    if method == "ranked":
        for d in DEPLOYMENTS:
            total = reset_score_tensor(scores[d])
            keys = np.flatnonzero(np.isfinite(total))
            if d == seed["deployment"]:
                keys = keys[keys!=seed["code"]]
            candidates.append((keys + DEPLOYMENTS.index(d)*N**4, total[keys]))
    else:
        d = seed["deployment"]
        actions = digits(seed["code"])
        codes, costs = [], []
        for j in range(4):
            for k in range(N):
                if actions[j]==k:
                    continue
                changed = list(actions)
                changed[j] = k
                value = sum(scores[d][m,i] for m,i in enumerate(changed))
                if np.isfinite(value):
                    codes.append(encode(changed)+DEPLOYMENTS.index(d)*N**4)
                    costs.append(value)
        candidates.append((np.asarray(codes,dtype=int),np.asarray(costs)))
    keys=np.concatenate([chunk[0] for chunk in candidates])
    costs=np.concatenate([chunk[1] for chunk in candidates])
    order=np.lexsort((keys,costs))
    return keys[order],costs[order]


def cached_replay(d, code, sched, kw):
    inlet=INITIAL
    status="SAFE"
    peak=np.full(4,-np.inf)
    energy=0.
    for j,k in enumerate(digits(code)):
        s=sched[d][j][k]
        if not s.deadline_feasible:
            raise ArithmeticError("A deadline failure entered the thermal scan")
        h=scene_response(s,kw[k],inlet)
        hstatus=h["thermal_status"]
        if hstatus=="VIOLATION" or status=="SAFE":
            status=hstatus
        energy+=h["energy_J"]
        peak=np.maximum(peak,h["peak_upper_C"])
        inlet=h["final_C"]
    return energy,status,peak


def compare_repair(method, seed, scores, sched, kw, oracle):
    t=perf_counter()
    keys,costs=enumerate_checks(method,seed,scores)
    ranking_s=perf_counter()-t
    checks=[]
    first,best=None,None
    budget=RANK_BUDGET if method=="ranked" else 104
    for i,(key,estimated) in enumerate(zip(keys[:budget],costs[:budget]),1):
        d=DEPLOYMENTS[int(key)//N**4]
        code=int(key)%N**4
        value,status,peak=cached_replay(d,code,sched,kw)
        elapsed=perf_counter()-t
        checks.append(dict(method=method,ordinal=i,deployment=d,code=code,
                           opps=" ".join(OPPS[k] for k in digits(code)),reset_j=float(estimated),
                           energy_j=value,status=status,elapsed_s=elapsed,
                           **{"peak_"+n+"_c":float(peak[j]) for j,n in enumerate(NODES)}))
        if status=="SAFE":
            record=choice(d,code,estimated)
            record.update(energy_j=value,first_or_examined_after=i,elapsed_s=elapsed,
                          gap_to_reference_j=value-oracle["energy_j"])
            if first is None:
                first=record
            if best is None or value<best["energy_j"]-EPS or (
                    abs(value-best["energy_j"])<=EPS and key<(DEPLOYMENTS.index(best["deployment"])*N**4+best["code"])):
                best=record
            if method=="ranked":
                break
    limited=len(checks)==budget and len(keys)>budget and not (method=="ranked" and first)
    return dict(deadline_legal_alternatives=len(keys),thermal_budget=budget,first_safe=first,
                best_examined=best,additional_full_replays=len(checks),common_seed_full_replay=1,
                segment_integrations=4*len(checks),rank_build_s=ranking_s,elapsed_s=perf_counter()-t,
                stopping_reason="BUDGET" if limited else (
                    "FIRST_SAFE" if method=="ranked" and first else "EXHAUSTED")),checks


def run_case(case, scenes, output):
    output.mkdir(exist_ok=True,parents=True)
    sched,kw,scores,options,rows,timing=local_tables(scenes,case["ambient"])
    put_csv(output/"local.csv",rows)
    seed=lowest(options,"predicted_j")
    info=dict(case=case,independent=seed,local_optima=options,timing=timing,oracle=None,
              repairs=None,requested=sum(len(s.requests) for s in scenes))
    if seed:
        t=perf_counter()
        seed["physical"]=replay_sequence(PLATFORM,scenes,seed["deployment"],seed["opps"],case["ambient"])
        info["timing"]["independent_replay_s"]=perf_counter()-t
        p=seed["physical"]
        if not p["deadline_ok"] or p["required"]!=p["completed"]:
            raise ArithmeticError("Reset-stage schedulability and continuous replay disagree")
        if p["thermal_status"]=="SAFE":
            info["classification"]="SELECTED_SAFE"
            return info
        if p["thermal_status"]!="VIOLATION":
            info["classification"]="UNRESOLVED"
            return info
    ref=certify(scenes,case,sched,kw,output)
    info["oracle"]=ref
    if ref["status"]=="UNRESOLVED":
        info["classification"]="UNRESOLVED"
    elif ref["status"]=="NO_SAFE":
        info["classification"]="SELECTED_HOT_NO_SAFE" if seed else "NO_SELECTION_NO_SAFE"
    elif not seed:
        info["classification"]="NO_SELECTION_SAFE_EXISTS"
    else:
        info["classification"]="SELECTED_HOT_SAFE_EXISTS"
        records=[]
        results={}
        for method in ("ranked","local"):
            results[method],attempts=compare_repair(method,seed,scores,sched,kw,ref)
            records.extend(attempts)
        info["repairs"]=results
        put_csv(output/"attempts.csv",records)
    return info


def main():
    from design import cases,make_scenes
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",required=True)
    parser.add_argument("--out",type=Path,default=HERE/"raw"/"new")
    args=parser.parse_args()
    check_freeze(args.freeze)
    start=perf_counter()
    joint.warmup()
    warmup=perf_counter()-start
    reports=[]
    for case in cases():
        scenes=make_scenes(case)
        if len(scenes)!=4:
            raise ValueError("The inherited exact solver requires four scenes")
        path=args.out/case["id"]
        row=run_case(case,scenes,path)
        row["freeze_commit"]=args.freeze
        reports.append(row)
        put_json(path/"result.json",row)
        print(case["id"],row["classification"],flush=True)
    put_json(args.out/"results.json",reports)
    put_json(args.out/"timing.json",dict(warmup_s=warmup,total_wall_s=perf_counter()-start,
                                        threads=1,case_count=len(reports)))


if __name__=="__main__":
    main()
