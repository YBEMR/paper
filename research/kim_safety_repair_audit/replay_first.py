"""Re-run every historical first-safe neighbour query on the pinned thermal model.

Only event schedules and constant parameters are reused. Each trial starts from
the specified 30 C four-node state and integrates every scene through the tail.
"""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import sys
from time import perf_counter

for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np

from history import check_input, digits, neighbors, STRIDES

HERE = Path(__file__).resolve().parent
JOINT = Path(os.environ.get("KIM_JOINT_INPUT",HERE.parent/"kim_scene_dvfs_admission")).resolve()
sys.path.insert(0,str(JOINT))
from scene_events import OPPS, PLATFORM, evaluate_thermal, split_workload, thermal_kwargs, time_scene


def prepare():
    scenes = split_workload("10s",25)
    local = {}
    with (JOINT/"raw"/"local.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["ambient"]=="25":
                local[r["deployment"],int(r["scene"]),r["opp"]]=r
    prepared={}
    for d in ("A","C"):
        scores=np.full((4,27),np.inf)
        physical_input={}
        for i,scene in enumerate(scenes):
            for j,opp in enumerate(OPPS):
                sched=time_scene(PLATFORM,scene,d,opp)
                row=local[d,i,opp]
                if sched.deadline_feasible != (row["deadline_ok"]=="True"):
                    raise AssertionError("archive deadline mismatch")
                if not sched.deadline_feasible:
                    continue
                if int(row["status"])!=1 or len(sched.completions_ns)!=len(scene.requests):
                    raise AssertionError("25 C local input changed")
                scores[i,j]=float(row["energy_j"])
                kw=thermal_kwargs(PLATFORM,opp,25,True,"base")
                physical_input[i,j]=(sched.duration_ns*1e-9,sched.active_w,sched.transfer_w,kw)
        reset=(scores[0,:,None,None,None]+scores[1,None,:,None,None]
               +scores[2,None,None,:,None]+scores[3,None,None,None,:]).ravel()
        prepared[d]=(reset,physical_input)
    return prepared


def fresh_replay(code, physical_input):
    entry=np.asarray(PLATFORM["thermal"]["initial_C"], dtype=float)
    energy=0.
    conservative_peak=-np.inf
    statuses=[]
    for s,j in enumerate(digits(code)):
        dt, activity, transfer, kw=physical_input[s,int(j)]
        result=evaluate_thermal(dt,activity,transfer_W=transfer,**dict(kw,initial_C=entry))
        entry=result["final_C"]
        statuses.append(result["thermal_status"])
        conservative_peak=max(conservative_peak,max(result["peak_upper_C"]))
        energy+=result["energy_J"]
    if any(x not in ("SAFE","VIOLATION") for x in statuses):
        raise AssertionError("Unresolved historical trial")
    return ("VIOLATION" if "VIOLATION" in statuses else "SAFE"),energy,conservative_peak


def run(raw):
    check_input(JOINT/"raw")
    with (raw/"historical_repairs.csv").open(encoding="utf8",newline="") as stream:
        sources=list(csv.DictReader(stream))
    if len(sources)!=4707:
        raise ValueError("historical candidate list incomplete")
    start=perf_counter()
    prepared=prepare()
    prepare_s=perf_counter()-start
    trials=[]
    search_start=perf_counter()
    actual_energy_error=0.
    physical_s=0.
    keys=set()
    for row in sources:
        d,source=row["deployment"],int(row["code"])
        if (d,source) in keys:
            raise ValueError("duplicate source")
        keys.add((d,source))
        reset,physical_input=prepared[d]
        hood=neighbors(source)
        eligible=hood[np.isfinite(reset[hood])]
        ordered=eligible[np.lexsort((eligible,reset[eligible]))]
        for n,code in enumerate(ordered, start=1):
            before=perf_counter()
            status,energy,peak=fresh_replay(int(code),physical_input)
            physical_s+=perf_counter()-before
            trials.append(dict(deployment=d,source_code=source,attempt=n,trial_code=int(code),
                               status=status,energy_j=energy,peak_upper_c=peak))
            if status=="SAFE":
                break
        if status!="SAFE" or n!=int(row["first_search_queries"]) or int(code)!=int(row["first_safe_code"]):
            raise AssertionError(f"first-safe outcome mismatch {d}/{source}")
        actual_energy_error=max(actual_energy_error,abs(energy-float(row["first_safe_j"])))
    search_s=perf_counter()-search_start
    if actual_energy_error>1.e-7:
        raise AssertionError("winner energy differs from frozen reference")
    # The full archive is consulted here, only after all query decisions are final.
    all_trial_error=0.
    for d in ("A","C"):
        with np.load(JOINT/"raw"/f"space_25_{d}.npz",allow_pickle=False) as archive:
            status,energy=archive["status"],archive["energy_j"]
            for r in trials:
                if r["deployment"]!=d:
                    continue
                c=r["trial_code"]
                if status[c] != (1 if r["status"]=="SAFE" else 2):
                    raise AssertionError(f"archive disagrees on {d}/{c}")
                all_trial_error=max(all_trial_error,abs(float(energy[c])-r["energy_j"]))
    if all_trial_error>1.e-7:
        raise AssertionError("trial energy differs from frozen reference")
    with (raw/"historical_first_attempts.csv").open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(trials[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(trials)
    summary={"input_commit":"2d352e715463641d6e49e4691d4b16fb02296c80",
             "historical_condition":"25 C / 10s 25 FPS / baseline / 4 scenes / leakage on / common 30 C initial",
             "source_candidates":len(sources),"fresh_full_thermal_replays":len(trials),
             "original_four_node_segment_integrations":4*len(trials),
             "returned_status":dict(Counter(t["status"] for t in trials)),
             "unique_attempts":len({(r["deployment"],r["trial_code"]) for r in trials}),
             "maximum_selected_energy_error_vs_archive_j":actual_energy_error,
             "maximum_any_trial_energy_error_vs_archive_j":all_trial_error,
             "event_schedule_preparation_s":prepare_s,"all_neighbour_search_wall_s":search_s,
             "fresh_thermal_wall_s_within_search":physical_s,
             "raw_timing":"Single-process wall clock (perf_counter); any JIT initialization in original thermal kernel is included in thermal time. Search time includes bookkeeping and ranking, excludes preparatory event scheduling, post-run checks and disk writes.",
             "cache_policy":"Event arrays and OPP parameters reused, integrals and thermal prefix maps never cached. Every successful and failed trial integrated all four scenes. Frozen NPZ outcomes read only after the trial decisions to audit them. Source detection from the prior audit and the original rejected-source replay are outside these repair-query counts."}
    (raw/"historical_first_replay.json").write_bytes((json.dumps(summary,indent=2)+"\n").encode())
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=HERE/"raw")
    print(json.dumps(run(parser.parse_args().raw),indent=2))
