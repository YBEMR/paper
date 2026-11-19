"""Re-derive the audit from the parent policy arrays and the frozen discrete-event model.

This file does not import history.py, peak_audit.py or runner.py. All numbers of
queries in the historical section refer to archived physical outcomes.
"""
import argparse
import csv
import json
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "kim_scene_dvfs_admission" / "raw"
OPPS = tuple("".join(v) for v in product("LMH",repeat=3))
RADIX = len(OPPS)
EPS = 1e-9
PHYSICAL_TOL = 1e-7
NODES = ("cpu","gpu","dla0","dla1")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def close(actual, expected, tol=PHYSICAL_TOL):
    require(abs(float(actual)-float(expected)) <= tol, f"{actual} differs from {expected}")


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digits(code):
    return tuple(int(x) for x in np.unravel_index(code,(RADIX,)*4))


def code(actions):
    return int(np.ravel_multi_index(tuple(actions),(RADIX,)*4))


def audit_history(raw):
    repair_rows = csv_rows(raw/"historical_repairs.csv")
    peak_rows = csv_rows(raw/"historical_peaks.csv")
    fields = csv_rows(PARENT/"local.csv")
    peaks = {(r["deployment"],int(r["code"])):r for r in peak_rows}
    source, rank, all_legal = {}, {}, []
    expected_false = set()
    for dep in "AC":
        with np.load(PARENT/f"space_25_{dep}.npz",allow_pickle=False) as z:
            status, energy = z["status"],z["energy_j"]
        local = {(int(r["scene"]),OPPS.index(r["opp"])):float(r["energy_j"])
                 for r in fields if r["deployment"]==dep and r["ambient"]=="25" and int(r["status"])==1}
        # Materialize tuples independently of the vectorized producer.
        reset = {}
        options = [[i for i in range(RADIX) if (scene,i) in local] for scene in range(4)]
        for seq in product(*options):
            key = code(seq)
            estimated = sum(local[scene,i] for scene,i in enumerate(seq))
            reset[key] = estimated
            all_legal.append((estimated,dep,key))
            if status[key]==2:
                expected_false.add((dep,key))
        source[dep] = status,energy,reset
        rank[dep] = {key:i for i,key in enumerate(sorted(reset,key=lambda k:(reset[k],k)),1)}
    global_rank = {(dep,k):i for i,(_,dep,k) in enumerate(sorted(all_legal),1)}
    global_min = min(np.min(e[s==1]) for s,e,_ in source.values())
    repairs = {(r["deployment"],int(r["code"])):r for r in repair_rows}
    require(len(peak_rows)==len(repair_rows)==len(expected_false)==4707,"missing or duplicated historical records")
    require(set(peaks)==set(repairs)==expected_false,"incorrect historical membership")
    first_counts = []
    physical_samples = []
    for dep in "AC":
        by_code = sorted(key for d,key in expected_false if d==dep)
        physical_samples.extend((dep,by_code[i]) for i in (0,len(by_code)//2,-1))
    for (dep,key),r in repairs.items():
        state,energy,reset=source[dep]
        sequence=digits(key)
        require(r["opps"].split()==[OPPS[i] for i in sequence],"unmatched policy encoding")
        close(r["reset_j"],reset[key])
        close(r["continuous_j"],energy[key])
        require(int(r["global_reset_rank"])==global_rank[dep,key] and
                int(r["deployment_reset_rank"])==rank[dep][key],"incorrect energy rank")
        p=peaks[dep,key]
        close(p["continuous_energy_j"],energy[key])
        bounds=[(float(p[f"peak_{n}_lo_c"]),float(p[f"peak_{n}_hi_c"])) for n in NODES]
        require(all(a<=b for a,b in bounds),"incorrect peak enclosure")
        close(p["peak_excess_lo_c"],max(a for a,b in bounds)-80)
        close(p["peak_excess_hi_c"],max(b for a,b in bounds)-80)
        require(float(p["peak_excess_lo_c"])>0 and p["first_violation_scene"] in {"sc0","sc1","sc2","sc3"},
                "peak does not certify a violation")
        require(all(dict(zip(NODES,bounds))[n][0]>80 for n in p["confirmed_nodes_in_first_scene"].split("|")),
                "reported violating node does not exceed limit")
        eligible=[]
        for scene in range(4):
            for replacement in range(RADIX):
                if replacement==sequence[scene]:
                    continue
                k=code(sequence[:scene]+(replacement,)+sequence[scene+1:])
                if state[k]!=0:
                    eligible.append(k)
        eligible.sort(key=lambda k:(reset[k],k))
        safe=[k for k in eligible if state[k]==1]
        checks=next((i+1 for i,k in enumerate(eligible) if state[k]==1),len(eligible))
        first_counts.append(checks)
        require(int(r["nominal_neighbors"])==4*(RADIX-1)
                and int(r["all_search_queries"])==len(eligible)
                and int(r["safe_neighbors"])==len(safe)
                and int(r["first_search_queries"])==checks,"incorrect neighborhood accounting")
        if not safe:
            require(not r["first_safe_code"] and not r["best_safe_code"],"spurious safe repair")
            continue
        first=safe[0]
        min_energy=min(energy[k] for k in safe)
        best=min(k for k in safe if energy[k]<=min_energy+EPS)
        require(int(r["first_safe_code"])==first and int(r["best_safe_code"])==best,"wrong safe neighbor")
        close(r["first_safe_j"],energy[first])
        close(r["best_safe_j"],energy[best])
        close(r["first_minus_original_j"],energy[first]-energy[key])
        close(r["best_minus_original_j"],energy[best]-energy[key])
        close(r["first_minus_best_j"],energy[first]-energy[best])
        close(r["best_minus_global_min_j"],energy[best]-global_min)
    from design import make_scenes
    from scene_events import PLATFORM, replay_sequence
    case=dict(fps=25,order=["sc0","sc1","sc2","sc3"],dwell_frames=[62,63,62,63])
    scenes=make_scenes(case)
    # Sample locations are first/middle/last by numeric code for each deployment.
    for dep,k in physical_samples:
        for action,want in ((k,False),(int(repairs[dep,k]["first_safe_code"]),True)):
            p=replay_sequence(PLATFORM,scenes,dep,[OPPS[i] for i in digits(action)],25)
            require(p["feasible"]==want and p["deadline_ok"] and p["completed"]==500,"direct sample replay")
            close(p["energy_j"],source[dep][1][action])
            if not want:
                sample=peaks[dep,k]
                first=next(s for s in p["scene_rows"] if s["thermal_status"]=="VIOLATION")
                require(first["scene"]==sample["first_violation_scene"],"first crossing scene")
                for j,n in enumerate(NODES):
                    require(float(sample[f"peak_{n}_lo_c"])<=p["peak_upper_c"][j]+1e-7 and
                            float(sample[f"peak_{n}_hi_c"])>=p["peak_lower_c"][j]-1e-7,"peak witness mismatch")
    return dict(historical_members=len(repairs), all_ranked=len(global_rank),
                historical_neighborhoods_rechecked=len(repairs), conceptual_first_queries=sum(first_counts),
                independent_direct_replays=2*len(physical_samples))



def audit_new(raw):
    from design import cases, make_scenes
    from scene_events import PLATFORM, time_scene, thermal_kwargs, evaluate_thermal, replay_sequence

    registered = {case["id"]:case for case in cases()}
    results = read(raw/"new"/"results.json")
    require(len(results)==len(registered)==12 and {r["case"]["id"] for r in results}==set(registered),
            "missing or extraneous conditions")
    require({(c["order_id"],c["dwell_id"],c["ambient"]) for c in registered.values()}==
            set(product(("forward","reverse"),("flat","alternating"),(25,27.5,30))),
            "incomplete factorial")
    old = {r["ambient"]:r for r in read(PARENT/"decisions.json") if r["method"]=="independent"}
    totals=Counter()
    coverage={}
    job_ids={}
    for result in results:
        case=result["case"]
        cid=case["id"]
        require(case==registered[cid] and read(raw/"new"/cid/"result.json")==result,"condition drift")
        ambient=case["ambient"]
        scenes=make_scenes(case)
        require(len(scenes)==4 and scenes[-1].end_ns==10_040_000_000 and scenes[-1].service_end_ns==10**10,
                "service/tail duration")
        reqs=tuple(q for s in scenes for q in s.requests)
        ids={q.id for q in reqs}
        require(len(reqs)==len(ids)==result["requested"]==500 and
                Counter(q.app for q in reqs)=={a:125 for a in range(4)} and
                all(q.deadline_ns-q.release_ns==40_000_000 for q in reqs),"request/period mismatch")
        if case["dwell_id"] in job_ids:
            require(ids==job_ids[case["dwell_id"]],"paired request IDs differ")
        job_ids[case["dwell_id"]]=ids
        folder=raw/"new"/cid
        local=csv_rows(folder/"local.csv")
        require(len(local)==216 and len({(r["deployment"],r["scene_index"],r["opp"]) for r in local})==216,
                "local search coverage")
        opts={}; schedules={}; scores={}; records={}
        for row in local:
            dep,j,opp=row["deployment"],int(row["scene_index"]),row["opp"]
            key=dep,j,opp
            schedules[key]=s=time_scene(PLATFORM,scenes[j],dep,opp)
            require(len(s.requests)==int(row["required"]) and row["scene"]==scenes[j].name,"dropped job")
            require((row["deadline_ok"]=="True")==s.deadline_feasible,"deadline check")
            close(row["min_slack_ms"],s.min_slack_ns/1e6)
            records[key]=row
            if not s.deadline_feasible:
                require(row["status"]=="DEADLINE_FAILED" and row["energy_j"]=="","invalid deadline failure")
                continue
            kw=thermal_kwargs(PLATFORM,opp,ambient,True,"base")
            h=evaluate_thermal(s.duration_ns*1e-9,s.active_w,transfer_W=s.transfer_w,**kw)
            close(h["energy_J"],row["energy_j"])
            require(h["thermal_status"]==row["status"],"local temperature check")
            scores[key]=h["energy_J"]
            for n,v in zip(NODES,h["peak_upper_C"]):
                close(row["peak_"+n+"_c"],v)
        totals["local_actions_rechecked"]+=len(local)
        for dep in "AC":
            seq=[]
            for j in range(4):
                safe=[o for o in OPPS if records[dep,j,o]["status"]=="SAFE"]
                if not safe: break
                floor=min(scores[dep,j,o] for o in safe)
                seq.append(next(o for o in safe if scores[dep,j,o]<=floor+EPS))
            if len(seq)==4:
                opts[dep]=(sum(scores[dep,j,o] for j,o in enumerate(seq)),seq)
        selected=result["independent"]
        if opts:
            f=min(p for p,seq in opts.values())
            dep=next(d for d in sorted(opts) if opts[d][0]<=f+EPS)
            e,seq=opts[dep]
            require(selected and (selected["deployment"],selected["opps"])==(dep,seq),"independent choice")
            close(selected["predicted_j"],e)
            physical=replay_sequence(PLATFORM,scenes,dep,seq,ambient)
            p=selected["physical"]
            close(physical["energy_j"],p["energy_j"])
            require(p["thermal_status"]==physical["thermal_status"] and p["required"]==p["completed"]==500
                    and p["deadline_ok"] and physical["deadline_ok"],"selected policy replay")
            status=p["thermal_status"]
            totals["selected_policies_replayed"]+=1
        else:
            require(selected is None,"invented independent choice")
            status="NO_SELECTION"
        if case["historic_repeat"]:
            legacy=old[ambient]
            require((legacy["deployment"],legacy["opps"])==
                    ((selected["deployment"],selected["opps"]) if selected else (None,None)),
                    "legacy independent decision mismatch")
            if selected:
                close(legacy["physical"]["energy_j"],selected["physical"]["energy_j"])
            totals["baseline_regressions"]+=1
        oracle=result["oracle"]
        if status=="SAFE":
            require(result["classification"]=="SELECTED_SAFE" and oracle is None and result["repairs"] is None,
                    "unexpected treatment of correct selection")
            totals[result["classification"]]+=1
            continue
        if status=="UNRESOLVED":
            require(result["classification"]=="UNRESOLVED","unresolved initial assessment")
            totals["UNRESOLVED"]+=1
            continue
        require(oracle and set(oracle["solutions"])=={"A","C"},"missing proof")
        oracle_states={}
        lower_rows=csv_rows(folder/"lower_inlets.csv")
        require(len(lower_rows)==216,"lower bound action table")
        for dep in "AC":
            sol=oracle["solutions"][dep]
            if sol["method"]=="MONOTONE_CERTIFICATE":
                require(sol["status"]=="NO_SAFE" and sol["safe"]==0 and sol["blocking_scenes"],
                        "incomplete monotone no-solution certificate")
                for scene in sol["blocking_scenes"]:
                    j=case["order"].index(scene)
                    certificate=[r for r in lower_rows if r["deployment"]==dep and int(r["scene_index"])==j]
                    require({r["opp"] for r in certificate}==set(OPPS),"incomplete blocking-scene grid")
                    for r in certificate:
                        o=r["opp"]
                        s=schedules[dep,j,o]
                        inlet=min(30.,ambient)
                        close(r["inlet_c"],inlet)
                        if not s.deadline_feasible:
                            require(r["status"]=="DEADLINE_FAILED","deadline certificate")
                            continue
                        kw=thermal_kwargs(PLATFORM,o,ambient,True,"base")
                        g=np.asarray(kw["conductance_W_K"])
                        require(np.all(g-np.diag(np.diag(g))<=0) and np.all(g.sum(axis=1)>=0) and
                                ambient>=inlet>=kw["reference_C"],"monotone lower inlet prerequisites")
                        kw["initial_C"]=np.full(4,inlet)
                        h=evaluate_thermal(s.duration_ns*1e-9,s.active_w,transfer_W=s.transfer_w,**kw)
                        require(r["status"]==h["thermal_status"]=="VIOLATION" and max(h["peak_lower_C"])>80,
                                "blocking action lacks a confirmed violation")
                    totals["blocking_scene_certificates_checked"]+=1
                oracle_states[dep]={"status":"NO_SAFE"}
            else:
                require(sol["method"]=="EXHAUSTIVE","unrecognized proof")
                with np.load(folder/f"space_{dep}.npz",allow_pickle=False) as archive:
                    states=archive["status"]; energy=archive["energy_j"]
                grid=np.array([[schedules[dep,j,o].deadline_feasible for o in OPPS] for j in range(4)])
                deadline_mask=(grid[0,:,None,None,None] & grid[1,None,:,None,None] &
                               grid[2,None,None,:,None] & grid[3,None,None,None,:]).ravel()
                require(len(states)==RADIX**4 and np.array_equal(states!=0,deadline_mask)
                        and np.array_equal(np.isfinite(energy),deadline_mask),"full-space mask")
                for i,field in enumerate(["deadline_failed","safe","overtemp","unresolved"]):
                    require(np.sum(states==i)==sol[field],"incorrect oracle totals")
                safe=np.flatnonzero(states==1)
                if len(safe):
                    best=float(np.min(energy[safe]))
                    k=int(safe[(energy[safe]<=best+EPS).nonzero()[0][0]])
                    oracle_states[dep]={"status":"SAFE_EXISTS","energy":float(energy[k]),"code":k}
                else:
                    oracle_states[dep]={"status":"UNRESOLVED" if np.any(states==3) else "NO_SAFE"}
                require(sol["status"]==oracle_states[dep]["status"],"oracle feasibility")
                totals["exhaustive_sequences_checked"]+=len(states)
        refopts={d:x for d,x in oracle_states.items() if x["status"]=="SAFE_EXISTS"}
        if refopts:
            best=min(x["energy"] for x in refopts.values())
            dep=next(d for d,x in sorted(refopts.items()) if x["energy"]<=best+EPS)
            k=refopts[dep]["code"]
            require(oracle["status"]=="SAFE_EXISTS" and (oracle["deployment"],oracle["code"])==(dep,k),
                    "oracle joint winner")
            physical=replay_sequence(PLATFORM,scenes,dep,[OPPS[i] for i in digits(k)],ambient)
            require(physical["feasible"] and physical["completed"]==500,"oracle replay failed")
            close(oracle["energy_j"],physical["energy_j"])
            want="NO_SELECTION_SAFE_EXISTS" if not selected else "SELECTED_HOT_SAFE_EXISTS"
        elif any(v["status"]=="UNRESOLVED" for v in oracle_states.values()):
            require(oracle["status"]=="UNRESOLVED","oracle remained undecided")
            want="UNRESOLVED"
        else:
            require(oracle["status"]=="NO_SAFE","infeasible physical selector")
            want="NO_SELECTION_NO_SAFE" if not selected else "SELECTED_HOT_NO_SAFE"
        require(result["classification"]==want,"genuine failure vs recoverability differs")
        if want=="SELECTED_HOT_SAFE_EXISTS":
            totals["repair_candidates_replayed"]+=audit_attempts(folder,result,scores,schedules,scenes)
        else:
            require(result["repairs"] is None,"repair invoked on a non-repairable or unselected policy")
        totals[want]+=1
    return dict(registered_conditions=len(results), **dict(totals))



def audit_attempts(folder,result,scores,schedules,scenes):
    from scene_events import PLATFORM, evaluate_thermal, thermal_kwargs
    seed=result["independent"]
    attempts=csv_rows(folder/"attempts.csv")
    all_scores=[]
    for d in "AC":
        choices=[[OPPS.index(o) for o in OPPS if (d,j,o) in scores] for j in range(4)]
        for seq in product(*choices):
            k=code(seq)
            if (d,k)!=(seed["deployment"],seed["code"]):
                all_scores.append((sum(scores[d,j,OPPS[i]] for j,i in enumerate(seq)),d,k))
    all_scores.sort()
    for method in ("ranked","local"):
        policy=result["repairs"][method]
        trace=[r for r in attempts if r["method"]==method]
        if method=="ranked":
            expected=all_scores
        else:
            origin=digits(seed["code"])
            expected=[x for x in all_scores if x[1]==seed["deployment"] and
                      sum(a!=b for a,b in zip(origin,digits(x[2])))==1]
        require(policy["deadline_legal_alternatives"]==len(expected),"repair order candidate pool")
        require(policy["additional_full_replays"]==len(trace) and policy["common_seed_full_replay"]==1
                and policy["segment_integrations"]==4*len(trace),"repair evaluation accounting")
        require(len(trace)<=min(len(expected),4096 if method=="ranked" else 104),"repair budget")
        first=None; safe=[]
        for i,(r,(score,d,k)) in enumerate(zip(trace,expected),1):
            require((r["deployment"],int(r["code"]),int(r["ordinal"]))==(d,k,i),"repair sequence scan/sorting")
            close(r["reset_j"],score)
            state=np.full(4,30.)
            total=0.; statuses=[]
            for j,level in enumerate(digits(k)):
                opp=OPPS[level]
                kw=thermal_kwargs(PLATFORM,opp,result["case"]["ambient"],True,"base")
                kw["initial_C"]=state
                s=schedules[d,j,opp]
                h=evaluate_thermal(s.duration_ns*1e-9,s.active_w,transfer_W=s.transfer_w,**kw)
                state=h["final_C"]; total+=h["energy_J"]; statuses.append(h["thermal_status"])
            status=("VIOLATION" if "VIOLATION" in statuses else
                    "UNRESOLVED" if "UNRESOLVED" in statuses else "SAFE")
            require(status==r["status"],"attempt thermal safety")
            close(total,r["energy_j"])
            if status=="SAFE":
                if first is None:
                    first=(d,k,total,i)
                safe.append((total,d,k))
        if first:
            p=policy["first_safe"]; d,k,e,i=first
            require((p["deployment"],p["code"],p["first_or_examined_after"])==(d,k,i),"first safe repair")
            close(p["energy_j"],e); close(p["gap_to_reference_j"],e-result["oracle"]["energy_j"])
            f=min(x[0] for x in safe)
            best_e,best_d,best_k=min((x for x in safe if x[0]<=f+EPS),key=lambda x:(x[1],x[2]))
            best=policy["best_examined"]
            require((best["deployment"],best["code"])==(best_d,best_k),"best checked repair")
            close(best["energy_j"],best_e)
            require(method!="ranked" or i==len(trace),"global sorted search not stopped at first safe")
        else:
            require(policy["first_safe"] is None and policy["best_examined"] is None,"false repair")
        if method=="local" or not first:
            require(len(trace)==min(len(expected),policy["thermal_budget"]),"early incomplete search")
    return len(attempts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=HERE/"raw")
    parser.add_argument("--history-only",action="store_true")
    parser.add_argument("--json",type=Path)
    args=parser.parse_args()
    output={"status":"PASS","history":audit_history(args.raw)}
    if not args.history_only:
        output["finite_validation"]=audit_new(args.raw)
    contents=json.dumps(output,indent=2,allow_nan=False)+"\n"
    if args.json:
        args.json.write_bytes(contents.encode("utf8"))
    print(contents,end="")


if __name__=="__main__":
    main()
