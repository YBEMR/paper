"""Rebuild same-domain and paired summaries from sealed results. No physical evaluation."""
import argparse
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import gzip
import hashlib
from itertools import product
import json
from math import isclose, isfinite
from pathlib import Path
import random
from statistics import mean, median
import sys
import tarfile

from catalog_ext import make_domain


HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "study_config.json").read_bytes())
SUBJECT = "6ec321468b4eb38686d13555b3a3124967805e34"
TOL = CONFIG["energy_tolerance_j"]
OPPS = tuple(map("".join, product("LMH", repeat=3)))
CASES = [f"{scene}_{temp}" for scene in CONFIG["cases"] for temp in CONFIG["ambient_suffixes"]]
METHODS = [tuple(m) for m in CONFIG["methods"]]
BASELINES = {"Kim-Adapt+SAFE", "Thermal-GA"}
STATUSES = {"SAFE", "DEADLINE", "VIOLATION", "UNRESOLVED"}
MEMBERS = {"reservation.json", "receipt.json", "console.txt", "events.jsonl.gz",
           "result.json.gz", "selection.json.gz"}
ARCHIVED_TABLE_HASHES = {
    "ch3_final_experiments/derived/instances.csv": "0ae803d6fd39c2d9cfa5d00f9ff2dea56d36dd0716c65af7f208890abfea6dc9",
    "ch3_final_experiments/formal/tables/run_results.csv": "542b791e6f8ce2174be3adc51527a39d1802a964d3beddcc1bfde2fd091c5290",
}


def check(ok, label):
    if not ok:
        raise ValueError(label)


def packed(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def unit_name(scope, method, seed):
    return f"{scope}_{method}_{seed}"


def raw_units(case, units, archives):
    names = {unit_name(s, m, k) for s, m in METHODS for k in CONFIG["seeds"]}
    if units:
        case_dir = units / case
        check({p.name for p in case_dir.iterdir() if p.is_dir()} == names, f"{case}: incomplete unit matrix")
        for name in sorted(names):
            folder = case_dir / name
            check(not folder.is_symlink() and all(p.is_file() and not p.is_symlink() for p in folder.iterdir()),
                  f"{case}/{name}: unexpected non-file result")
            files = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
            yield name, files
        return
    path = archives / (case + ".tar")
    with tarfile.open(path, mode="r:") as arc:
        index = defaultdict(dict)
        for entry in arc:
            if entry.isdir():
                check(entry.name.rstrip("/") in names, f"{path.name}: unexpected directory")
                continue
            parts = entry.name.split("/")
            check(entry.isfile() and len(parts) == 2 and parts[0] in names and parts[1] in MEMBERS,
                  f"{path.name}: unexpected member {entry.name!r}")
            name, filename = parts
            check(filename not in index[name], f"{path.name}: repeated member {entry.name}")
            index[name][filename] = entry
        check(set(index) == names, f"{case}: incomplete archive matrix")
        for name in sorted(names):
            yield name, {filename: arc.extractfile(entry).read() for filename, entry in index[name].items()}


def stream_definition(instance, fsm):
    scenes = instance["scene_order"].split("/")
    frames = dict(zip(scenes, map(int, instance["frames_execution_order"].split("/")), strict=True))
    canonical, offset = {}, 0
    for scene in sorted(scenes):
        canonical[scene] = offset
        offset += frames[scene]
    result, digest_rows, absolute = [], [], 0
    for scene in scenes:
        start_ns = absolute * 40_000_000
        jobs = {}
        for local_frame in range(frames[scene]):
            for app in fsm["active_apps"][scene]:
                rid = f"f{canonical[scene]+local_frame:04d}-a{app}"
                item = [app, absolute*40_000_000, (absolute+1)*40_000_000]
                jobs[rid] = item
                digest_rows.append([rid, *item])
            absolute += 1
        service_end = absolute * 40_000_000
        end_ns = service_end + (40_000_000 if scene == scenes[-1] else 0)
        result.append((scene, jobs, start_ns, service_end, end_ns))
    check(absolute == 250 and len(digest_rows) == 500 and result[-1][-1] == 10_040_000_000,
          "invalid request stream length")
    check(sha(packed(digest_rows).encode()) == instance["request_sha"], "archived request digest mismatch")
    return result


def thermal_status(lo, hi):
    check(len(lo) == len(hi) == 4 and all(isfinite(a) and isfinite(b) and a <= b for a,b in zip(lo, hi)),
          "invalid four-node bounds")
    return "VIOLATION" if max(lo) > 80 else "SAFE" if max(hi) <= 80 else "UNRESOLVED"


def check_selection(proof, result, instance, stream, domain):
    key, answer = result["selected_genome"], result["selected"]
    case, scope, method, seed = result["job"]
    p, stages = proof["physical"], proof["stages"]
    dep, indices = key[0], key[1:]
    check(proof["case"] == case and proof["ambient_c"] == float(instance["ambient_c"]) and
          proof["request_sha256"] == instance["request_sha"] and proof["dep"] == dep and
          proof["indices"] == indices and proof["opps"] == [OPPS[i] for i in indices], "selection identity")
    check(stages == domain.stages(dep), "selection differs from catalog decoder")
    check(sum(r.startswith("DLA") for chain in stages.values() for r, _, _ in chain) <= 4, "slot capacity")
    for app, chain in stages.items():
        pos = 0
        for device, first, last in chain:
            check(device in ("DLA0","DLA1","GPU") and first == pos and first <= last, "layer coverage")
            pos = last + 1
        check(pos == domain.sizes[int(app)], "incomplete frozen network")
    evidence = defaultdict(dict)
    for q in proof["completions"]:
        marker = q["request_id"]
        check(marker not in evidence[q["scene"]], "duplicate completion")
        evidence[q["scene"]][marker] = q
    segments = p["scene_rows"]
    check(1 <= len(segments) <= 4 and p["required"] == 500 and
          set(evidence) == {s["scene"] for s in segments}, "selected prefix coverage")
    previous = [30.] * 4
    lower, upper = previous[:], previous[:]
    counted, energies, min_slacks = 0, [], []
    for j, seg in enumerate(segments):
        scene, requests, start, service_end, end = stream[j]
        check((seg["index"], seg["scene"], seg["opp"], seg["required"]) ==
              (j, scene, OPPS[indices[j]], len(requests)), "segment identity")
        check(set(evidence[scene]) == set(requests), "per-scene request membership")
        slacks, late = [], set()
        for rid, (app, release, deadline) in requests.items():
            row = evidence[scene][rid]
            finish = row["completion_ns"]
            slack = deadline - finish
            check((row["app_id"], row["release_ns"], row["deadline_ns"], row["slack_ns"]) ==
                  (app, release, deadline, slack) and finish >= release, "request identity or timing")
            slacks.append(slack)
            counted += finish <= end
            if slack < 0:
                late.add(rid)
        min_slacks.append(min(slacks))
        if not seg["deadline_ok"]:
            check(j == len(segments)-1 and late and set(seg["late_ids"]) == late == set(answer["late_ids"]),
                  "deadline failure witness")
            continue
        check(not late and seg["min_slack_ns"] == min(slacks) and
              (seg["start_ns"], seg["service_end_ns"], seg["end_ns"]) == (start, service_end, end),
              "scene timing certificate")
        lo, hi = seg["peak_lower_c"], seg["peak_upper_c"]
        check(seg["entry_c"] == previous and seg["thermal_status"] == thermal_status(lo, hi) and
              len(seg["final_c"]) == 4 and all(isfinite(v) for v in seg["final_c"]), "thermal continuity")
        check(all(max(x, y) <= h + 1e-7 for x, y, h in zip(previous, seg["final_c"], hi)), "endpoint above upper bound")
        lower, upper = list(map(max, lower, lo)), list(map(max, upper, hi))
        previous = seg["final_c"]
        check(isfinite(seg["energy_j"]) and seg["energy_j"] >= 0, "invalid scene energy")
        energies.append(seg["energy_j"])
    check(counted == p["completed"] == answer["completed"] and min(min_slacks)/1e6 ==
          p["min_slack_ms"] == answer["slack_ms"], "whole-window timing")
    if p["fully_replayed"]:
        check(len(energies) == 4 and counted == 500 and p["deadline_ok"] and p["final_c"] == previous and
              p["thermal_status"] == answer["status"] == thermal_status(lower, upper) and
              p["peak_upper_c"] == answer["upper"] == upper and p["peak_lower_c"] == answer["lower"] == lower and
              isclose(sum(energies), p["energy_j"], abs_tol=TOL, rel_tol=0) and
              p["energy_j"] == answer["energy_j"] and p["feasible"] == (answer["status"] == "SAFE"),
              "four-node whole-window certificate")
    else:
        check(not (p["feasible"] or p["deadline_ok"] or segments[-1]["deadline_ok"]) and answer["status"] == "DEADLINE"
              and p["thermal_status"] == "NOT_EVALUATED" and p["energy_j"] is None and
              p["peak_upper_c"] is None and answer["energy_j"] is None, "invalid partial-window evidence")
    return stages


@lru_cache(maxsize=None)
def input_hashes(method):
    names = ["study_config.json", "catalog_manifest.json", "run_study.py", "physical.py", "catalog_ext.py",
             "baselines.py" if method in BASELINES else "cooperative.py"]
    return {n: sha((HERE/n).read_bytes()) for n in names}


def initial_population(method, seed, anchors, order):
    rng = random.Random(seed)
    if method == "Kim-Adapt+SAFE":
        return anchors + [rng.choice(order) for _ in range(CONFIG["kim_population"] - len(anchors))]
    population = []
    for i in range(CONFIG["ga_population"]):
        dep = anchors[i] if i < len(anchors) else rng.choice(order)
        population.append([dep, *(rng.randrange(len(OPPS)) for _ in range(4))])
    return population


def compact_result(result):
    return [result["status"], result["energy_j"], result["slack_ms"], result["completed"],
            result["lower"], result["upper"], len(result["late_ids"])]


def audit_run(files, job, instance, stream, domain):
    case, scope, method, seed = job
    receipt = json.loads(files["receipt.json"])
    reservation = json.loads(files["reservation.json"])
    check(set(files) <= MEMBERS and set(receipt["files"]) == set(files)-{"receipt.json"} and
          all(sha(files[n]) == h for n,h in receipt["files"].items()), "raw file hashes")
    check(receipt["job"] == reservation["job"] == list(job) and reservation["cap_s"] == 120 and
          reservation["inputs"] == receipt["inputs"] == input_hashes(method) and
          reservation["core"] == receipt["core"], "reservation or input identity")
    row = dict(case=case, ambient_c=float(instance["ambient_c"]), scope=scope, domain_count=domain.size,
               method=method, seed=seed, request_sha256=instance["request_sha"],
               receipt_state=receipt["state"], wall_s=receipt["elapsed_s"],
               evidence_sha256=sha(files["receipt.json"]), safety=0, outcome=receipt["state"])
    check(receipt["state"] in {"finished","hard_timeout","fault"} and receipt["elapsed_s"] >= 0, "receipt state")
    if receipt["state"] != "finished":
        return row
    result = json.loads(gzip.decompress(files["result.json.gz"]))
    anchors = ["A","C"] + random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A","C")], 6)
    digest = instance["request_sha"]
    check(receipt["exitcode"] == 0 and result["init_deps"] == anchors and result["domain_count"] == domain.size and
          result["request_sha256"] == digest and result["job"] == list(job) and
          0 <= result["search_end_s"] <= receipt["elapsed_s"], "result identity or timing")
    seen, positions, stats, action_counts = {}, {}, Counter(), Counter()
    initialized, settings_seen, events_seen, preceding, first_observed = [], False, Counter(), 0., None
    trace = gzip.decompress(files["events.jsonl.gz"])
    for line in trace.splitlines():
        t, event, v = json.loads(line)
        check(t >= preceding and t <= receipt["elapsed_s"], "trace clock")
        preceding = t
        events_seen[event] += 1
        if event == "identity":
            check(events_seen[event] == 1 and v["job"] == list(job) and v["domain"] == domain.size and
                  v["initial"] == anchors and v["request_sha256"] == digest, "trace identity")
        elif event == "initial_population":
            check(method in BASELINES and not settings_seen and
                  v == initial_population(method,seed,anchors,domain.order), "entire random initial population")
            settings_seen = True
        elif event == "cooperative_settings":
            check(method not in BASELINES and not settings_seen and v["initial_deps"] == anchors and
                  v["variant"] == method and v["seed"] == seed and v["rounds"] == CONFIG["cooperative"]["max_rounds"]
                  and v["candidates_per_round"] == CONFIG["cooperative"]["new_full_replays_per_round"],
                  "cooperative initialization")
            settings_seen = True
        elif event == "replay":
            genome, status, energy, slack, n, lo, hi, late = v
            key = tuple(genome)
            check(len(key) == 5 and genome[0] in domain.order and all(type(i) is int and 0<=i<27 for i in key[1:])
                  and key not in seen and status in STATUSES and isfinite(slack) and 0 <= n <= 500, "candidate domain")
            if status == "DEADLINE":
                check(energy is None and hi is None and lo is None and late>0 and slack < 0, "deadline observation")
            else:
                check(n == 500 and late == 0 and slack >= 0 and isfinite(energy) and energy >= 0 and
                      status == thermal_status(lo, hi), "continuous candidate")
            seen[key] = v[1:]
            stats[status] += 1
            if status == "SAFE" and first_observed is None:
                first_observed = t
        elif event in {"kim_check","ga_evaluation","cooperative_position"}:
            if event == "kim_check":
                key, detail = (v[0], *v[1]), v[2]
            elif event == "ga_evaluation":
                key, detail = tuple(v[0]), v[1]
            else:
                key, detail = tuple(v["genome"]), v["result"]
                action_counts[v["operator"]] += 1
                if v["operator"] == "initialize":
                    initialized.append(key[0])
            check(key not in positions and compact_result(detail) == seen[key],
                  "algorithm ledger differs from admitted physical result")
            positions[key] = detail
    summ = result["summary"]
    check(events_seen["identity"] == 1 and settings_seen and dict(stats) == result["unique_observations"] and
          result["safe"] == bool(stats["SAFE"]), "admitted observations")
    if first_observed is None:
        check(result["first_observed_safe_s"] is None, "unobserved SAFE time")
    else:
        check(first_observed - 1e-6 <= result["first_observed_safe_s"] <= result["search_end_s"], "first SAFE time")
    # A final in-flight observation may be excluded by the method's post-replay clock
    # check. Only positions actually admitted by that method can be its winner.
    safe_positions = [(v["energy_j"], k) for k,v in positions.items() if v["status"] == "SAFE"]
    if method == "Kim-Adapt+SAFE":
        check(events_seen["kim_generation"] == summ["completed_generations"] <= CONFIG["kim_max_gen"] and
              events_seen["kim_check"] == summ["completed_checks"] and events_seen["scene_proxy"] == summ["proxy_evaluations"] and
              len(safe_positions) <= 1, "Kim-Adapt+SAFE accounting")
    elif method == "Thermal-GA":
        check(events_seen["ga_generation"] == summ["completed_generations"] <= CONFIG["ga_max_gen"] and
              len(positions) == summ["unique_completed"], "Thermal-GA accounting")
    else:
        check(initialized == anchors[:len(initialized)] and len(initialized) == summ["initialized"] and
              action_counts == summ["action_counts"] and len(positions) == summ["unique_completed"] and
              summ["completed_rounds"] <= CONFIG["cooperative"]["max_rounds"], "cooperative accounting")
    check(Counter(v["status"] for v in positions.values()) == summ["unique_status_counts"], "method status counters")
    chosen, answer = result["selected_genome"], result["selected"]
    expected = list(min(safe_positions)[1]) if safe_positions else None
    check(summ["winner"] == expected == (chosen if result["safe"] else None), "minimum admitted SAFE genome")
    row.update(safety=int(result["safe"]), outcome="SAFE" if result["safe"] else "NO_SAFE_OBSERVED",
               search_s=result["search_end_s"], first_safe_s=result["first_observed_safe_s"],
               stop=summ["reason"], unique_replays=len(seen), physical_safe=stats["SAFE"],
               physical_deadline=stats["DEADLINE"], physical_overtemp=stats["VIOLATION"],
               physical_unresolved=stats["UNRESOLVED"], selection_role=result["selected_kind"],
               generations=summ.get("completed_generations"), rounds=summ.get("completed_rounds"),
               kim_checks=summ.get("completed_checks"), operator_counts=packed(summ.get("action_counts",{})))
    if chosen is None:
        check(not seen and answer is None and "selection.json.gz" not in files, "unexplained empty selection")
        return row
    obs = seen[tuple(chosen)]
    check(obs == compact_result(answer), "selected observation mismatch")
    proof = json.loads(gzip.decompress(files["selection.json.gz"]))
    stages = check_selection(proof, result, instance, stream, domain)
    cuts = {app: [last for device,first,last in chain if device.startswith("DLA")] for app,chain in stages.items()}
    peak = max(answer["upper"]) if answer["upper"] else None
    row.update(selected_status=answer["status"], deployment=chosen[0], originally_in_81=int(chosen[0] in domain.legacy_ids),
               cut_end_layers=packed(cuts), resident_stages=packed(stages), opp_indices=packed(chosen[1:]),
               frequency_sequence="/".join(proof["opps"]), actual_energy_j=answer["energy_j"],
               safe_energy_j=answer["energy_j"] if result["safe"] else None,
               peak_upper_c=peak, min_slack_ms=answer["slack_ms"], completed=answer["completed"],
               thermal_margin_c=80-peak if peak is not None else None)
    return row


def case_summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["case"], row["scope"], row["method"]].append(row)
    output = []
    for (case, scope, method), records in groups.items():
        safe = [r for r in records if r["safety"]]
        def stat(field, fn):
            return fn([r[field] for r in safe]) if safe else None
        output.append(dict(case=case, ambient_c=records[0]["ambient_c"], scope=scope, method=method,
            n=len(records), safe=len(safe), safe_fraction=len(safe)/len(records), energy_mean_j=stat("safe_energy_j",mean),
            energy_min_j=stat("safe_energy_j",min), energy_max_j=stat("safe_energy_j",max),
            peak_mean_c=stat("peak_upper_c",mean), peak_max_c=stat("peak_upper_c",max),
            thermal_margin_mean_c=stat("thermal_margin_c",mean), thermal_margin_min_c=stat("thermal_margin_c",min),
            deadline_slack_min_ms=stat("min_slack_ms",min), wall_median_s=median(r["wall_s"] for r in records),
            outcomes=packed(dict(Counter(r["outcome"] for r in records)))))
    return output


def pair_rows(rows):
    lookup = {(r["case"],r["scope"],r["method"],r["seed"]):r for r in rows}
    output = []
    for case in CASES:
        for scope, method in METHODS:
            if (scope, method) == ("extended", "full"):
                continue
            for seed in CONFIG["seeds"]:
                full = lookup[case,"extended","full",seed]
                other = lookup[case,scope,method,seed]
                both = bool(full["safety"] and other["safety"])
                diff = (other["safe_energy_j"] - full["safe_energy_j"]) if both else None
                output.append(dict(case=case, ambient_c=full["ambient_c"], seed=seed, comparator_scope=scope,
                    comparator_method=method, same_domain=int(scope=="extended"), full_safe=full["safety"],
                    comparator_safe=other["safety"], paired_safe=int(both), full_energy_j=full.get("safe_energy_j"),
                    comparator_energy_j=other.get("safe_energy_j"), full_saving_j=diff,
                    full_saving_pct=100*diff/other["safe_energy_j"] if both else None,
                    relation=("full_lower" if diff > TOL else "full_higher" if diff < -TOL else "tie") if both else "unpaired"))
    return output


def pair_summary(rows):
    groups = defaultdict(list)
    for r in rows:
        for group, label in (("case",r["case"]), ("ambient",str(r["ambient_c"])), ("all","all")):
            groups[group,label,r["comparator_scope"],r["comparator_method"]].append(r)
    output = []
    for (group,label,scope,method), records in groups.items():
        matched = [r for r in records if r["paired_safe"]]
        status = Counter((r["full_safe"],r["comparator_safe"]) for r in records)
        ranks = Counter(r["relation"] for r in matched)
        delta = [r["full_saving_pct"] for r in matched]
        output.append(dict(group=group,level=label,comparator_scope=scope,comparator_method=method,
            same_domain=int(scope=="extended"), planned_pairs=len(records), both_safe=len(matched),
            full_only_safe=status[1,0], comparator_only_safe=status[0,1], neither_safe=status[0,0],
            full_lower=ranks["full_lower"], ties=ranks["tie"], full_higher=ranks["full_higher"],
            paired_saving_mean_j=mean(r["full_saving_j"] for r in matched) if matched else None,
            paired_saving_mean_pct=mean(delta) if delta else None, paired_saving_median_pct=median(delta) if delta else None,
            paired_saving_min_pct=min(delta) if delta else None, paired_saving_max_pct=max(delta) if delta else None))
    return output


def history_and_witnesses(root, rows):
    path = root/"research/ch3_final_experiments/formal/tables/run_results.csv"
    history = [{k:r[k] for k in ("group","case","domain","method","seed","request_sha256","outcome",
               "safe_energy_j","peak_upper_c","margin_c","min_slack_ms","winner_dep","opp_code","wall_s",
               "exact_energy_j","certificate","source")} for r in read_csv(path)]
    check(len(history)==96, "accepted historical run count")
    refs = {r["case"]:float(r["safe_energy_j"]) for r in history
            if (r["group"], r["method"], r["domain"], r["outcome"]) == ("AB","CT-Joint","81","SAFE")}
    check(len(refs)==4 and set(refs) == {s+"_25C" for s in CONFIG["cases"]}, "old certificate scope")
    output=[]
    for case in CASES:
        for scope, method in [("extended","all_extended_methods"),*METHODS]:
            candidates=[r for r in rows if r["case"]==case and r["scope"]==scope and r["safety"]
                        and (method=="all_extended_methods" or r["method"]==method)]
            best=min(candidates,key=lambda r:r["safe_energy_j"],default=None)
            exact=refs.get(case)
            energy=best["safe_energy_j"] if best else None
            delta=exact-energy if energy is not None and exact is not None else None
            if scope=="legacy81" and delta is not None:
                check(delta<=TOL,"legacy witness contradicts corresponding finite-domain certificate")
            strict=(delta>TOL) if scope=="extended" and delta is not None else None
            if strict:
                check(not best["originally_in_81"],"legacy assignment contradicts old optimum")
            output.append(dict(case=case, scope=scope, method=method, best_observed_safe_j=energy,
                witness_method=best["method"] if best else None, witness_seed=best["seed"] if best else None,
                deployment=best["deployment"] if best else None, certificate_legacy81_j=exact,
                legacy_exact_minus_observed_j=delta, strict_improvement_over_legacy81_proved=int(strict) if strict is not None else None,
                proven_saving_lower_bound_pct=100*delta/exact if strict else None, extended_exact_j=None))
    return history, output


def main(args):
    root = args.source_root.resolve()
    sys.path.insert(0,str(root/"research/ch3_final_experiments/p2"))
    manifest = json.loads((HERE/"catalog_manifest.json").read_bytes())
    frozen_inputs = {**manifest["source_sha256"], **ARCHIVED_TABLE_HASHES}
    for name, expected in frozen_inputs.items():
        check(sha((root/"research"/name).read_bytes()) == expected, f"frozen input differs: {name}")
    domains={s:make_domain(root,s) for s in ("legacy81","extended")}
    instances={r["instance_id"]:r for r in read_csv(root/"research/ch3_final_experiments/derived/instances.csv")}
    fsm=json.loads((root/"research/kim_case_b_freeze/input.json").read_bytes())["fsm"]
    check(CONFIG["subject"]==SUBJECT and len(CASES)==12 and len(METHODS)==7 and len(CONFIG["seeds"])==5,"design")
    by_case=[]
    for case in CASES:
        instance=instances[case]
        stream=stream_definition(instance,fsm)
        jobs={unit_name(s,m,k):(case,s,m,k) for s,m in METHODS for k in CONFIG["seeds"]}
        for name, files in raw_units(case,args.units,args.archives):
            job=jobs[name]
            try:
                by_case.append(audit_run(files,job,instance,stream,domains[job[1]]))
            except Exception as error:
                raise ValueError(f"{case}/{name}: {error}") from error
    check(len(by_case)==420,"final run count")
    pairs=pair_rows(by_case)
    history,witnesses=history_and_witnesses(root,by_case)
    outputs={"run_results":by_case,"case_summary":case_summary(by_case),"paired_runs":pairs,
             "paired_summary":pair_summary(pairs),"historical_references":history,"domain_witnesses":witnesses}
    args.output.mkdir(parents=True,exist_ok=True)
    for name,table in outputs.items():
        write_csv(args.output/(name+".csv"),table)
    record=dict(subject=SUBJECT,runs=len(by_case),cases=len(CASES),seeds=CONFIG["seeds"],
        scope_counts=dict(Counter(r["scope"] for r in by_case)),receipts=dict(Counter(r["receipt_state"] for r in by_case)),
        outcomes=dict(Counter(r["outcome"] for r in by_case)),paired_rows=len(pairs),tolerance_j=TOL,
        source_inputs_sha256=frozen_inputs,
        table_sha256={name:sha((args.output/(name+".csv")).read_bytes()) for name in outputs})
    (args.output/"audit.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf8",newline="\n")
    print(packed(record))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--units",type=Path)
    source.add_argument("--archives",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args())
