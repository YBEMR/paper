"""Read-only archive consistency audit; no event simulation or thermal evaluation.

This checks saved evidence, not physical model accuracy or an external reviewer's
approval. Catalog graph expansion is static. All energy/temperature checks use
already archived arrays and recorded full-sequence replays.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "02f3f621cc9ce7f1cd991577388343fa906bbf56"
EPS = 1e-9
TOL = 1e-7
AC_CASES = {"forward_flat_27p5C", "forward_alternating_25C", "reverse_flat_25C", "reverse_alternating_25C"}
EXP_CASES = {"forward_flat_25C", "forward_alternating_25C", "reverse_flat_25C", "reverse_alternating_25C"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class Audit:
    def __init__(self):
        self.checks = 0
        self.counters = Counter()
        self.arrays = []
        self.section = "startup"

    def require(self, value, message):
        self.checks += 1
        if not value:
            raise AssertionError(f"{self.section}: {message}")

    def close(self, actual, expected, message, tol=TOL):
        self.require(actual is not None and expected is not None and
                     np.isfinite(float(actual)) and np.isfinite(float(expected)) and
                     abs(float(actual)-float(expected)) <= tol,
                     f"{message}: {actual!r} != {expected!r}")


def decode(code, opps):
    return [opps[(int(code)//len(opps)**(3-j)) % len(opps)] for j in range(4)]


def encode(levels, n):
    return sum(int(k)*n**(3-j) for j,k in enumerate(levels))


def choose(candidates, field="predicted_j"):
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        return None
    low = min(c[field] for c in candidates)
    return min((c for c in candidates if c[field] <= low+EPS),
               key=lambda c:(c["deployment"], c["code"]))


def choice_same(audit, actual, expected, message):
    audit.require((actual is None) == (expected is None), message+" existence")
    if expected is not None:
        audit.require((actual["deployment"], actual["code"], actual["opps"]) ==
                      (expected["deployment"], expected["code"], expected["opps"]), message+" identity")
        audit.close(actual["predicted_j"], expected["predicted_j"], message+" score")


def freeze_audit(audit):
    audit.section = "freeze"
    manifest_path = HERE/"freeze_manifest.json"
    manifest, receipt = read(manifest_path), read(HERE/"freeze_receipt.json")
    audit.require(manifest["base_commit"] == receipt["parent"] == BASE, "wrong base")
    audit.require(hashlib.sha256(manifest_path.read_bytes()).hexdigest() == receipt["manifest_sha256"],
                  "receipt/manifest mismatch")
    for relative, expected in manifest["files"].items():
        path = (ROOT/relative).resolve()
        audit.require(path.is_relative_to(ROOT), "manifest escapes root")
        audit.require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"source drift: {relative}")
    for item in receipt["files"]:
        data = (ROOT/item["path"]).read_bytes()
        digest = hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        audit.require(digest == item["git_blob_sha1"], "remote blob receipt mismatch: "+item["path"])
    audit.counters["frozen_files_checked"] = len(manifest["files"])
    return receipt


def catalog_audit(audit):
    audit.section = "catalog"
    import catalog
    frozen, meta = read(HERE/"expanded_input.json"), read(HERE/"catalog.json")
    audit.require(frozen == catalog.build_frozen(), "generated frozen input differs")
    audit.require(meta == json.loads(json.dumps(catalog.catalog_metadata())), "generated catalog differs")
    baseline = read(HERE.parent/"kim_case_b_freeze"/"input.json")
    opps = tuple("".join(row) for row in baseline["clock_policy"]["constant_opp_levels"])
    audit.require(len(opps) == 27 and len(set(opps)) == 27, "frequency domain")
    audit.require(len(frozen["deployments"]) == 81 and len(meta["physical_aliases"]) == 161,
                  "catalog size")
    alias_counts = Counter(row["representative"] for row in meta["physical_aliases"])
    audit.require(sorted(alias_counts.values()) == [1]+[2]*80, "global-swap orbits")
    for ident, dep in frozen["deployments"].items():
        resident = sum(r.startswith("DLA") for stages in dep["stages"].values() for r,_,_ in stages)
        audit.require(resident == dep["resident_dla_stages"] == dep["resident_dla_engines"] <= 4,
                      "resident cap: "+ident)
        for app in frozen["applications"]:
            stages = dep["stages"][str(app["id"])]
            covered = [i for _,a,b in stages for i in range(a,b+1)]
            audit.require(covered == list(range(app["layers"])), "layer coverage: "+ident)
        if ident in ("A","C"):
            audit.require(dep["stages"] == baseline["deployments"][ident]["stages"], "historical mapping changed")
    stage_features = csv_read(HERE/"stage_features.csv")
    feature = defaultdict(list)
    for row in stage_features:
        feature[row["candidate"], row["opp"]].append(row)
    for rows in feature.values():
        rows.sort(key=lambda r:int(r["chain_index"]))
        audit.require([int(r["chain_index"]) for r in rows] == list(range(len(rows))), "stage feature coverage")
    audit.counters["catalog_deployments"] = len(frozen["deployments"])
    audit.counters["physical_aliases"] = len(meta["physical_aliases"])
    return frozen, meta, opps, feature


def local_actions(audit, rows, deployment, opps):
    n = len(opps)
    own = [r for r in rows if r["deployment"] == deployment]
    audit.require(len(own) == 4*n, "local table missing or duplicated actions")
    by_key = {(int(r["scene"]), r["opp"]):r for r in own}
    audit.require(set(by_key) == {(j,o) for j in range(4) for o in opps}, "local grid keys")
    deadline = np.zeros((4,n), dtype=bool)
    safe_prices = np.full((4,n), np.inf)
    for j in range(4):
        for k,opp in enumerate(opps):
            row = by_key[j,opp]
            deadline[j,k] = row["deadline_ok"] == "True"
            status = int(row["status"])
            audit.require(status in (0,1,2,3) and (status != 0) == deadline[j,k], "local deadline/status")
            if status:
                audit.require(np.isfinite(float(row["energy_j"])), "local nonfinite energy")
            else:
                audit.require(row["energy_j"] == "", "deadline failure has energy")
            if status == 1:
                safe_prices[j,k] = float(row["energy_j"])
    selected = []
    for prices in safe_prices:
        indices = np.flatnonzero(np.isfinite(prices))
        if len(indices):
            selected.append(int(indices[np.flatnonzero(prices[indices] <= prices[indices].min()+EPS)[0]]))
    independent = None
    if len(selected) == 4:
        code = encode(selected,n)
        independent = dict(deployment=deployment,code=code,opps=decode(code,opps),
                           predicted_j=float(sum(safe_prices[j,k] for j,k in enumerate(selected))))
    return deadline, safe_prices, independent


def array_audit(audit, folder, deployment, record, local, opps):
    path = folder/f"space_{deployment}.npz"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if "array_archive" in record:
        archive = record["array_archive"]
        audit.require(archive["path"] == path.name and archive["bytes"] == path.stat().st_size
                      and archive["sha256"] == digest, "npz archive hash")
    audit.arrays.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=digest, bytes=path.stat().st_size))
    with np.load(path, allow_pickle=False) as data:
        audit.require(set(data.files) == {"status","energy_j"}, "npz members")
        states, energy = data["status"], data["energy_j"]
    n = len(opps)
    audit.require(states.shape == energy.shape == (n**4,), "array shape")
    audit.require(np.all(np.isin(states,[0,1,2,3])), "unrecognized status")
    deadline, prices, independent = local_actions(audit,local,deployment,opps)
    mask = (deadline[0,:,None,None,None] & deadline[1,None,:,None,None] &
            deadline[2,None,None,:,None] & deadline[3,None,None,None,:]).ravel()
    audit.require(np.array_equal(states != 0,mask) and np.array_equal(np.isfinite(energy),mask), "deadline mask")
    audit.require(np.all(energy[mask] >= 0), "negative complete energy")
    counts = np.bincount(states,minlength=4)
    for k,name in enumerate(("deadline_failed","safe","overtemp","unresolved")):
        audit.require(int(counts[k]) == record[name], "classification count: "+name)
    depths = np.cumprod(deadline.sum(axis=1)).tolist()
    audit.require(record["deadline_legal_prefixes"] == depths, "prefix coverage")
    prefix_field = "joint_prefix_evaluations" if "joint_prefix_evaluations" in record else "search_prefix_thermal_evaluations"
    audit.require(record[prefix_field] == sum(depths), "prefix evaluation count")
    audit.require(record["compiled_scene_actions"] == int(deadline.sum()), "compiled action count")
    if "finite_array_sha256" in record:
        audit.require(hashlib.sha256(states.tobytes()+energy.tobytes()).hexdigest() == record["finite_array_sha256"], "A/C raw array hash")
    safe = np.flatnonzero(states == 1)
    joint = None
    exact_min = None
    if len(safe):
        exact_min = float(np.min(energy[safe]))
        code = int(safe[np.flatnonzero(energy[safe] <= exact_min+EPS)[0]])
        joint = dict(deployment=deployment,code=code,opps=decode(code,opps),predicted_j=float(energy[code]))
    eligible = np.flatnonzero(states != 0)
    noheat = None
    if len(eligible):
        minimum = float(np.min(energy[eligible]))
        code = int(eligible[np.flatnonzero(energy[eligible] <= minimum+EPS)[0]])
        noheat = dict(deployment=deployment,code=code,opps=decode(code,opps),predicted_j=float(energy[code]))
    reset = (prices[0,:,None,None,None]+prices[1,None,:,None,None]+
             prices[2,None,None,:,None]+prices[3,None,None,None,:]).ravel()
    reset_safe = np.isfinite(reset)
    if "sets" in record:
        want = dict(reset_feasible=int(reset_safe.sum()),both_feasible=int((reset_safe & (states==1)).sum()),
                    reset_only=int((reset_safe & (states!=1)).sum()),continuous_only=int((~reset_safe & (states==1)).sum()))
        for field,value in want.items():
            audit.require(record["sets"][field] == value, "reset/continuous set accounting: "+field)
    audit.counters["npz_arrays"] += 1
    audit.counters["logical_sequences_checked"] += len(states)
    return dict(states=states,energy=energy,exact_min=exact_min,independent=independent,joint=joint,no_thermal_constraint=noheat)


def replay_audit(audit, choice, arrays, opps, case, replay_cache):
    if choice is None:
        return
    deployment,code = choice["deployment"],int(choice["code"])
    audit.require(choice["opps"] == decode(code,opps), "replay code/OPP mismatch")
    physical = choice["physical"]
    audit.require(physical["required"] == physical["completed"] == 500 and
                  physical["deadline_ok"] and physical["fully_replayed"], "replay request/deadline coverage")
    audit.close(physical["energy_j"], arrays[deployment]["energy"][code], "replay/array energy")
    status = {1:"SAFE",2:"VIOLATION",3:"UNRESOLVED"}[int(arrays[deployment]["states"][code])]
    audit.require(status == physical["thermal_status"] and physical["feasible"] == (status == "SAFE"), "replay classification")
    rows = physical["scene_rows"]
    audit.require(len(rows) == 4, "replay segment count")
    prior = np.full(4,30.)
    total = 0.
    lo, hi = prior.copy(),prior.copy()
    required = 0
    statuses = []
    for j,row in enumerate(rows):
        audit.require(row["scene"] == case["order"][j] and row["opp"] == choice["opps"][j], "replay scene/OPP")
        audit.require(np.allclose(row["entry_c"],prior,atol=1e-10,rtol=0), "thermal handoff state")
        prior = np.asarray(row["final_c"])
        total += row["energy_j"]
        lo = np.maximum(lo,row["peak_lower_c"])
        hi = np.maximum(hi,row["peak_upper_c"])
        required += row["required"]
        statuses.append(row["thermal_status"])
        audit.require(row["deadline_ok"] and row["min_slack_ns"] >= 0, "segment deadline")
        if j:
            audit.require(rows[j-1]["end_ns"] == row["start_ns"], "scene interval gap")
    audit.require(required == 500 and rows[0]["start_ns"] == 0 and rows[-1]["end_ns"] == 10_040_000_000,
                  "whole-window time/request coverage")
    audit.close(physical["energy_j"],total,"replay component sum")
    audit.require(np.allclose(physical["final_c"],prior,atol=1e-10,rtol=0), "replay final state")
    audit.require(np.allclose(physical["peak_lower_c"],lo,atol=1e-10,rtol=0) and
                  np.allclose(physical["peak_upper_c"],hi,atol=1e-10,rtol=0), "whole-window peak aggregation")
    audit.require(np.all(lo <= hi), "inverted peak bounds")
    if status == "SAFE":
        audit.require(np.max(hi) <= 80 and set(statuses) == {"SAFE"}, "SAFE lacks upper-bound witness")
    if status == "VIOLATION":
        audit.require(np.max(lo) > 80 and "VIOLATION" in statuses, "VIOLATION lacks lower-bound witness")
    key = deployment,code
    if key in replay_cache:
        audit.require(replay_cache[key] == physical, "same policy has conflicting saved replays")
    replay_cache[key] = physical
    audit.counters["saved_replay_references"] += 1


def ac_audit(audit, raw, opps):
    summary = read(raw/"summary.json")
    old = {r["case"]["id"]:r for r in read(HERE.parent/"kim_safety_repair_audit"/"raw"/"new"/"results.json")}
    audit.require({r["case"] for r in summary["cases"]} == AC_CASES and summary["complete_cases"] == 4, "A/C cases incomplete")
    audit.require(all(w["status"] == "COMPLETED" and w["returncode"] == 0 and
                      w["process_elapsed_s"] <= 120. for w in summary["workers"]), "A/C worker completion/cap")
    outputs = {}
    for entry in summary["cases"]:
        cid = entry["case"]
        audit.section = "A/C "+cid
        folder = raw/cid
        result = read(folder/"result.json")
        audit.require(result["case"] == old[cid]["case"], "A/C experimental conditions changed")
        local = csv_read(folder/"local.csv")
        arrays = {}
        for coverage in result["coverage"]:
            dep = coverage["deployment"]
            arrays[dep] = array_audit(audit,folder,dep,coverage,local,opps)
            saved = read(folder/f"coverage_{dep}.json")
            audit.require(saved["coverage"] == coverage, "duplicated A/C coverage differs")
        audit.require(set(arrays) == {"A","C"}, "A/C deployment coverage")
        independent = choose([r["independent"] for r in arrays.values()])
        choice_same(audit,result["independent"],independent,"A/C independent selector")
        choice_same(audit,result["independent"],old[cid]["independent"],"frozen historical selector")
        audit.close(result["independent"]["physical"]["energy_j"],old[cid]["independent"]["physical"]["energy_j"],"historical actual energy")
        actual_min = min(r["exact_min"] for r in arrays.values() if r["exact_min"] is not None)
        audit.close(result["minimum_safe_array_energy_j"],actual_min,"A/C exact finite min",tol=1e-12)
        audit.close(entry["optimal_safe_j"],actual_min,"A/C summary minimum")
        audit.close(result["best_safe_found"]["predicted_j"],actual_min,"A/C witness is actual finite minimum",tol=1e-12)
        audit.close(entry["independent_continuous_j"],result["independent"]["physical"]["energy_j"],"A/C summary independent energy")
        unresolved = sum(r["unresolved"] for r in result["coverage"])
        audit.require(result["optimality_proven"] == (unresolved == 0) == entry["optimality_proven"], "A/C optimality scope")
        cache = {}
        replay_audit(audit,result["independent"],arrays,opps,result["case"],cache)
        replay_audit(audit,result["best_safe_found"],arrays,opps,result["case"],cache)
        gap = result["independent"]["physical"]["energy_j"]-actual_min
        audit.close(result["unrounded_numeric_gap_j"],gap,"A/C raw gap",tol=1e-12)
        audit.close(entry["gap_j"],0. if abs(gap)<=TOL else gap,"A/C reported gap")
        outputs[cid] = dict(result=result, arrays=arrays)
    audit.counters["ac_cases"] = len(outputs)
    return outputs, old


def resource_audit(audit, folder, result, frozen, feature, opps):
    cid = result["case"]["id"]
    rows = csv_read(folder/"sc2_resources.csv")
    keys = [(r["deployment"],r["opp"]) for r in rows]
    audit.require(len(keys) == len(set(keys)), "duplicate resource rows")
    counts = dict.fromkeys(frozen["fsm"]["active_apps"]["sc2"],result["case"]["dwell_frames"][2])
    duration_ms = result["case"]["dwell_frames"][2]/result["case"]["fps"]*1000
    for row in rows:
        dep = frozen["deployments"][row["deployment"]]
        expected = Counter()
        by_app = Counter()
        for app,requests in counts.items():
            candidate = dep["per_app_candidate_ids"][app]
            actual = dep["stages"][str(app)]
            for f in feature[candidate,row["opp"]]:
                resource = f["resource"]
                index = int(f["chain_index"])
                if index>=2 and index<2+2*len(actual) and index%2 == 0:
                    resource = actual[(index-2)//2][0]
                value = requests*int(f["duration_ns"])/1e6
                expected[resource] += value
                if resource == "GPU":
                    by_app[app] += value
        audit.require(int(row["requests"]) == sum(counts.values()), "SC2 request count")
        for device in ("GPU","DLA0","DLA1","XFER"):
            field = device.lower()
            audit.close(row[field+"_requested_service_ms"],expected[device],"SC2 complete service "+device,tol=1e-6)
            busy = float(row[field+"_busy_ms"])
            audit.require(-TOL<=busy<=duration_ms+TOL and busy<=expected[device]+TOL,"SC2 busy interval bounds")
            audit.close(row[field+"_utilization"],busy/duration_ms,"SC2 utilization",tol=1e-10)
            if row["deadline_ok"] == "True":
                audit.close(busy,expected[device],"SC2 feasible task energy-window coverage",tol=1e-6)
        for app in range(4):
            audit.close(row[f"app{app}_gpu_requested_ms"],by_app[app],"SC2 per-network GPU work",tol=1e-6)
        audit.require(float(row["gpu_wait_sum_ms"])>=0 and float(row["gpu_wait_max_ms"])>=0,"negative GPU wait")
    for dep in result["completed_deployments"]:
        audit.require({opp for d,opp in keys if d == dep} == set(opps), "completed deployment SC2 grid")
    audit.counters["sc2_resource_rows"] += len(rows)


def lower_bound_audit(audit, folder, result, frozen, feature, opps):
    platform = read(HERE.parent/"kim_synthetic_platform_v1"/"platform.json")
    rows = read(folder/"relaxed_lower_bounds.json")
    audit.require({r["deployment"] for r in rows} == set(frozen["deployments"]), "relaxed bound coverage")
    frames = dict(zip(("sc0","sc1","sc2","sc3"),result["case"]["dwell_frames"]))
    for row in rows:
        dep = frozen["deployments"][row["deployment"]]
        per_scene = []
        for j,scene in enumerate(result["case"]["order"]):
            duration = frames[scene]/result["case"]["fps"]+(0.04 if j==3 else 0.)
            costs = []
            for opp in opps:
                idle = sum(platform["power"]["idle_by_domain_W"][domain]["LMH".index(level)]
                           for domain,level in zip(("CPU","GPU","DLA"),opp))
                work = sum(frames[scene]*sum(int(f["duration_ns"])*1e-9*float(f["active_w"])
                                  for f in feature[dep["per_app_candidate_ids"][app],opp])
                           for app in frozen["fsm"]["active_apps"][scene])
                costs.append((idle+platform["power"]["board_W"])*duration+work)
            per_scene.append(min(costs))
        audit.require(np.allclose(row["per_scene_lower_j"],per_scene,atol=1e-10,rtol=0), "static bound stage account")
        audit.close(row["lower_bound_j"],sum(per_scene),"static bound sum",tol=1e-10)
    return min(r["lower_bound_j"] for r in rows)


def expanded_audit(audit, raw, frozen, meta, opps, feature, ac, old):
    results = read(raw/"results.json")
    receipt = read(HERE/"freeze_receipt.json")
    started = read(raw/"started.json")
    audit.require(started["freeze_commit"] == receipt["commit"] and
                  started["manifest_sha256"] == receipt["manifest_sha256"], "expanded provenance receipt")
    audit.require({r["case"]["id"] for r in results} == EXP_CASES and len(results)==4,"expanded case coverage")
    audit.require(not (raw/"failure.json").exists(),"expanded execution has failure marker")
    audit.require(read(raw/"catalog_metadata.json") == meta,"runtime catalog differs")
    summary=[]
    for result in results:
        cid = result["case"]["id"]
        audit.section="expanded "+cid
        folder=raw/cid
        audit.require(read(folder/"result.json")==result,"duplicated result differs")
        audit.require(result["case"]==old[cid]["case"] and result["case"]["ambient"]==25,
                      "expanded experimental conditions changed")
        audit.require(result["provenance"]["freeze_commit"]==receipt["commit"] and
                      result["provenance"]["manifest_sha256"]==receipt["manifest_sha256"],"case provenance")
        rows=read(folder/"deployments.json")
        done=result["completed_deployments"]
        audit.require(done==meta["search_order"][:len(done)] and [r["deployment"] for r in rows]==done,"coverage order")
        audit.require(result["unsearched_or_incomplete_deployments"]==meta["search_order"][len(done):],"uncovered set")
        audit.require(result["coverage_complete"]==(len(done)==81),"coverage completeness claim")
        local=csv_read(folder/"local.csv")
        arrays={}; replay_cache={}
        choices={k:[] for k in ("independent","joint","no_thermal_constraint")}
        totals=Counter()
        for row in rows:
            dep=row["deployment"]
            audit.section="expanded "+cid+"/"+dep
            audit.require(read(folder/f"deployment_{dep}.json")==row,"duplicated deployment record")
            arrays[dep]=data=array_audit(audit,folder,dep,row,local,opps)
            audit.require(row["conditional_optimality_proven"]==(row["unresolved"]==0),"conditional optimum claim")
            if data["exact_min"] is None:
                audit.require(row["minimum_safe_array_j"] is None,"invented safe minimum")
            else:
                audit.close(row["minimum_safe_array_j"],data["exact_min"],"true array min",tol=1e-12)
            for method in choices:
                choice_same(audit,row[method],data[method],"per-deployment "+method)
                if data[method]: choices[method].append(data[method])
            for method in ("independent","joint"):
                replay_audit(audit,row[method],arrays,opps,result["case"],replay_cache)
            for field in ("deadline_failed","safe","overtemp","unresolved","compilation_original_integrations",
                          "independent_prefix_evaluations","joint_prefix_evaluations"):
                totals[field]+=row[field]
            totals["fallback_integrations"]+=row["independent_fallback_integrations"]+row["joint_fallback_integrations"]
            audit.require(row["total_batch_screen_entries"]==row["independent_prefix_evaluations"]+row["joint_prefix_evaluations"],"screen count sum")
        audit.section="expanded "+cid
        for method,opts in choices.items():
            choice_same(audit,result["decisions"][method],choose(opts),"global "+method)
            choice_same(audit,result["historical_ac"][method],choose([o for o in opts if o["deployment"] in ("A","C")]),"historical "+method)
            replay_audit(audit,result["decisions"][method],arrays,opps,result["case"],replay_cache)
            replay_audit(audit,result["historical_ac"][method],arrays,opps,result["case"],replay_cache)
        audit.require(result["full_policy_replays"]==len(replay_cache) and result["full_replay_segment_integrations"]==4*len(replay_cache),"unique full-replay accounting")
        for field in ("deadline_failed","safe","overtemp","unresolved"):
            audit.require(result["summed_classifications"][field]==totals[field],"aggregate classification "+field)
        partial=result["partial_deployment"]
        if partial:
            audit.require(partial["deployment"]==meta["search_order"][len(done)] and
                          read(folder/"partial_deployment.json")==partial,"partial deployment identity")
            audit.require(not (folder/f"space_{partial['deployment']}.npz").exists(),"partial classified as full")
            for field in ("compilation_original_integrations","independent_prefix_evaluations","fallback_integrations"):
                totals[field]+=partial.get(field,0)
        for field in ("compilation_original_integrations","independent_prefix_evaluations","joint_prefix_evaluations","fallback_integrations"):
            audit.require(result[field]==totals[field],"aggregate actual work "+field)
        proven=len(done)==81 and totals["unresolved"]==0
        audit.require(result["global_optimality_proven"]==proven,"global optimality scope")
        audit.require(result["logical_complete_sequences"]==len(done)*len(opps)**4 and
                      result["logical_catalog_sequences"]==81*len(opps)**4,"logical space counts")
        relaxed=lower_bound_audit(audit,folder,result,frozen,feature,opps)
        best=result["decisions"]["joint"]
        bound=min(v["exact_min"] for v in arrays.values() if v["exact_min"] is not None) if proven and best else relaxed
        audit.close(result["energy_lower_bound_j"],bound,"reported lower bound",tol=1e-10)
        if best:
            audit.close(result["best_feasible_energy_j"],best["physical"]["energy_j"],"reported feasible upper bound")
            audit.require(bound<=best["physical"]["energy_j"]+TOL,"lower bound exceeds feasible energy")
        historical=result["historical_ac"]["independent"]
        choice_same(audit,historical,old[cid]["independent"],"expanded historical independent")
        audit.close(historical["physical"]["energy_j"],old[cid]["independent"]["physical"]["energy_j"],"expanded historical energy")
        if cid in ac:
            for dep in ("A","C"):
                audit.require(np.array_equal(arrays[dep]["states"],ac[cid]["arrays"][dep]["states"]),"A/C reused classification")
                audit.require(np.allclose(arrays[dep]["energy"],ac[cid]["arrays"][dep]["energy"],atol=TOL,rtol=0,equal_nan=True),"A/C reused energy arrays")
        resource_audit(audit,folder,result,frozen,feature,opps)
        same=csv_read(folder/"same_opp_reference.csv")
        audit.require({r["deployment"] for r in same}==set(done),"same-OPP comparison coverage")
        for row in same:
            dep,code=row["deployment"],int(row["code"])
            audit.require(int(row["status"])==int(arrays[dep]["states"][code]),"same-OPP classification")
            if np.isfinite(arrays[dep]["energy"][code]):
                audit.close(row["continuous_j"],arrays[dep]["energy"][code],"same-OPP energy")
            else: audit.require(row["continuous_j"]=="","deadline-failed same-OPP has energy")
        audit.close(result["budget_overrun_s"],max(0.,result["elapsed_s"]-300.),"timing overrun account",tol=1e-9)
        summary.append(dict(case=cid,completed_deployments=len(done),uncovered=81-len(done),
                            global_optimality_proven=proven,archived_logical_sequences=len(done)*len(opps)**4,
                            unique_saved_replays=len(replay_cache)))
    audit.counters["expanded_cases"]=len(results)
    # Static stage-MAC records cover every actual deployment partition exactly.
    mac_rows=csv_read(raw/"stage_mac.csv")
    actual={(r["deployment"],int(r["app"]),int(r["first"]),int(r["last"])):r for r in mac_rows}
    expected=set()
    for dep,item in frozen["deployments"].items():
        for app in frozen["applications"]:
            a=app["id"]; parts=item["stages"][str(a)]
            candidate=item["per_app_candidate_ids"][a]
            inf=[f for f in feature[candidate,opps[0]] if f["mac"]!=""]
            total=sum(int(f["mac"]) for f in inf)
            for (device,first,last),f in zip(parts,inf,strict=True):
                key=dep,a,first,last; expected.add(key)
                r=actual[key]
                audit.require(r["resource"]==device and int(r["mac"])==int(f["mac"]) and
                              int(r["network_total_mac"])==total,"stage MAC conservation")
    audit.require(set(actual)==expected and len(actual)==len(mac_rows),"stage MAC table coverage")
    audit.counters["stage_mac_rows"]=len(mac_rows)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ac",type=Path,default=HERE/"raw"/"ac_closure")
    parser.add_argument("--expanded",type=Path,default=HERE/"raw"/"expanded")
    parser.add_argument("--output",type=Path,default=HERE/"raw"/"internal_archive_audit.json")
    args=parser.parse_args()
    audit=Audit(); start=perf_counter(); report={}
    try:
        receipt=freeze_audit(audit)
        frozen,meta,opps,feature=catalog_audit(audit)
        ac,old=ac_audit(audit,args.ac,opps)
        expanded=expanded_audit(audit,args.expanded,frozen,meta,opps,feature,ac,old)
        report=dict(status="PASS",preregistration_commit=receipt["commit"],expanded_coverage=expanded)
    except Exception as exc:
        report=dict(status="FAIL",section=audit.section,error_type=type(exc).__name__,error=str(exc))
    report.update(checks=audit.checks,counters=dict(audit.counters),elapsed_s=perf_counter()-start,
                  scientific_calls=0,external_review_approval=False,
                  scope="Read-only archived consistency checks. No new schedule, heat integration, search or physical replay.",
                  array_archives=audit.arrays)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="array_archives"},ensure_ascii=False,indent=2))
    if report["status"]!="PASS": raise SystemExit(1)


if __name__=="__main__":
    main()
