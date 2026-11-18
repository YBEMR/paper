"""Read-only audit of every frozen condition, decision, and archived event stream.

This checker does not invoke the scheduler, thermal solver or selection code.
Run from any directory: python -B check_results.py
"""
import argparse
import csv
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOURCES = ("cpu0", "cpu1", "cpu2", "cpu3", "cpu4", "cpu5", "cpu6", "cpu7",
             "gpu", "dla0", "dla1", "xfer")
NODES = ("cpu", "gpu", "dla0", "dla1")
FREQS = tuple("".join(f) for f in itertools.product("LMH", repeat=3))
MODES = ("independent", "continuous")
ACTIONS = tuple(itertools.product("AC", FREQS))
ACTIVE = ((0,), (0, 1, 2), (1, 2, 3), (3,))


def require(ok, description):
    if not ok:
        raise ValueError(description)


def same(x, y, field):
    # Accommodates decimal CSV serialization and two integration orders.
    require(math.isclose(float(x), float(y), rel_tol=1e-9, abs_tol=1e-8),
            f"{field}: {x} != {y}")


def flag(value):
    require(str(value).lower() in {"true", "false", "1", "0"}, f"invalid flag: {value}")
    return str(value).lower() in {"true", "1"}


def read_csv(file):
    with file.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def case_key(row):
    return (row["window"], int(row["fps"]), int(float(row["ambient_c"])), row["leakage"], row["variation"])


def expected_cases():
    cases = set(itertools.product(("short", "10s", "20s"), (20, 25, 30), (25, 30),
                                  ("on", "off"), ("base",)))
    return cases | {("10s", 25, ambient, "on", variant)
                    for ambient in (25, 30) for variant in ("r080", "r120")}


def expected_requests(window, fps):
    # Derive release/deadline independently from exact absolute frame indices.
    block_frames = 10 * fps
    if window == "short":
        scenes = range(4)
    else:
        one = [i for i in range(4) for _ in range(((i+1)*block_frames)//4-i*block_frames//4)]
        scenes = one * (2 if window == "20s" else 1)

    def to_ns(i):
        quotient, remainder = divmod(i*10**9, fps)
        return quotient + (2*remainder >= fps)

    jobs = {f"f{i:04d}-a{app}": (app, to_ns(i), to_ns(i+1))
            for i, scene in enumerate(scenes) for app in ACTIVE[scene]}
    return jobs, to_ns(len(scenes)+1)


def status(row):
    fail = []
    if not flag(row["deadline_ok"]):
        fail.append("deadline")
    if int(row["completed"]) != int(row["required"]):
        fail.append("unfinished_in_window")
    if row["thermal_status"] != "SAFE":
        fail.append(row["thermal_status"].lower())
    return "+".join(fail) or "feasible"


def energy_terms(row):
    names = ["common_j", "transfer_j"]
    names += [f"{part}_{node}_j" for part in ("idle", "activity", "leakage") for node in NODES]
    values = [float(row[n]) for n in names]
    require(all(math.isfinite(v) and v >= 0 for v in values), "invalid energy component")
    same(sum(values), row["energy_j"], "energy sum")
    return values


def audit_rows(rows, platform):
    grouped = defaultdict(dict)
    schedules = defaultdict(list)
    case_names = {}
    limits = platform["thermal"]["limits_C"]
    grids = {(w, f): expected_requests(w, f) for w in ("short", "10s", "20s") for f in (20,25,30)}
    for r in rows:
        condition = case_key(r)
        dep, opp, mode = r["deployment"], r["opp"], r["mode"]
        key = (dep, opp, mode)
        require(key not in grouped[condition], f"duplicate {condition} {key}")
        grouped[condition][key] = r
        schedules[r["sched_id"]].append(r)
        name = r["case_id"]
        require(case_names.setdefault(name, condition) == condition, f"aliased case {name}")
        jobs, ns = grids[condition[:2]]
        same(r["window_s"], ns / 1e9, "window s")
        require(int(r["required"]) == int(r["final_completed"]) == len(jobs),
                f"request count or drain failure {name}/{dep}/{opp}")
        require(0 <= int(r["completed"]) <= len(jobs), "invalid within-window completion count")
        require(0 <= int(r["late_count"]) <= len(jobs), "invalid miss count")
        require(flag(r["deadline_ok"]) == (int(r["late_count"]) == 0 and int(r["completed"]) == len(jobs)),
                "inconsistent deadline certificate")
        therm = r["thermal_status"]
        require(therm in ("SAFE", "VIOLATION", "UNRESOLVED") and flag(r["thermal_ok"]) == (therm == "SAFE"),
                "invalid thermal certificate")
        lows, highs = [], []
        for node in NODES:
            lo, hi = float(r[f"peak_lo_{node}_c"]), float(r[f"peak_{node}_c"])
            final = float(r[f"final_{node}_c"])
            require(all(math.isfinite(v) for v in (lo, hi, final)) and
                    30-1e-8 <= lo <= hi+1e-8 and 25-1e-8 <= final <= hi+1e-8,
                    f"invalid continuous peak bracket or final physical state: {name}/{node}")
            lows.append(lo)
            highs.append(hi)
        if any(lo > limit for lo,limit in zip(lows,limits)):
            expected_status = "VIOLATION"
        elif all(hi <= limit for hi,limit in zip(highs,limits)):
            expected_status = "SAFE"
        else:
            expected_status = "UNRESOLVED"
        require(therm == expected_status, "invalid continuous peak certification")
        energy_terms(r)
        same(r["common_j"], platform["power"]["board_W"]*ns/1e9, "single board base")
        for unit in RESOURCES:
            busy, idle = float(r[f"busy_{unit}_s"]), float(r[f"idle_{unit}_s"])
            require(min(busy, idle) >= -1e-10, "negative busy/idle times")
            same(busy + idle, ns/1e9, "busy+idle " + unit)
        if condition[3] == "off":
            same(sum(float(r[f"leakage_{n}_j"]) for n in NODES), 0, "leakage-off decomposition")

    expected = {(d, o, m) for d, o in ACTIONS for m in MODES}
    require(set(grouped) == expected_cases() and len(case_names) == 40, "incorrect scenario grid")
    for case, entries in grouped.items():
        require(set(entries) == expected, f"incomplete action/evaluation grid in {case}")
        for d, o in ACTIONS:
            ind, cont = (entries[d,o,m] for m in MODES)
            require(ind["sched_id"] == cont["sched_id"], "reset altered timing evidence")
            if case[3] == "off":
                same(ind["energy_j"], cont["energy_j"], "leakage-off paired energies")

    expected_schedule_keys = set(itertools.product(("short", "10s", "20s"), (20,25,30), "AC", FREQS))
    schedule_keys = []
    for sid, conditions in schedules.items():
        variants = {(r["window"], int(r["fps"]), r["deployment"], r["opp"]) for r in conditions}
        require(len(variants) == 1, f"schedule reused for different timelines: {sid}")
        schedule_keys.append(variants.pop())
    require(len(schedule_keys)==len(expected_schedule_keys) and set(schedule_keys)==expected_schedule_keys,
            "schedule IDs must be shared across thermals but cover all 486 timing inputs")
    return grouped, schedules, grids


def audit_lengths(grouped):
    paired = 0
    for case, short in grouped.items():
        if case[0] != "10s" or case[-1] != "base":
            continue
        long = grouped[("20s", *case[1:])]
        for action, a in short.items():
            b = long[action]
            require(int(b["required"]) == 2*int(a["required"]), "wrong repeated long workload")
            same(float(b["window_s"]) - float(a["window_s"]), 10, "long-window extension")
            if flag(a["deadline_ok"]) and flag(b["deadline_ok"]):
                # A successful first block ends without carry-in to the second block.
                # Common and idle base contain one tail in each evaluation.
                for term in ("transfer_j", *(f"activity_{n}_j" for n in NODES)):
                    same(2*float(a[term]), b[term], "doubled active work " + term)
                if case[3] == "off":
                    idle_w = (float(a["common_j"]) + sum(float(a[f"idle_{n}_j"]) for n in NODES)) / float(a["window_s"])
                    tail_s = float(a["window_s"])-10
                    same(2*float(a["energy_j"]) - idle_w*tail_s, b["energy_j"],
                         "long-window one idle tail")
                paired += 1
    return paired

def audit_decisions(decisions, replays, grouped):
    replay_lookup = {(case_key(r), r["selector"]): r for r in replays}
    require(len(replay_lookup) == len(replays), "duplicate physical replay")
    used, decision_cases = set(), set()
    for drow in decisions:
        case = case_key(drow)
        require(case not in decision_cases, "duplicate decision")
        decision_cases.add(case)
        selected = {}
        for prefix, mode in (("ind", "independent"), ("cont", "continuous")):
            candidates = grouped[case]
            admissible = [(d, o) for d, o in ACTIONS if status(candidates[d,o,mode]) == "feasible"]
            reported = drow[prefix+"_pick"]
            require(int(drow[prefix+"_feasible_candidates"]) == len(admissible), "bad feasible-shape count")
            if not admissible:
                require(not reported and drow[prefix+"_physical_status"] == "no_selection",
                        "declared a winner with no admissible deployment")
                selected[prefix] = None
                continue
            minimum = min(float(candidates[d,o,mode]["energy_j"]) for d,o in admissible)
            tied = [(d,o) for d,o in admissible if float(candidates[d,o,mode]["energy_j"]) <= minimum+1e-9]
            # ACTIONS uses A then C and the lexicographic order L,M,H in each clock.
            dep, opp = tied[0]
            require(reported == f"{dep}-{opp}" and drow[prefix+"_tie_set"].split("|") ==
                    [f"{d}-{o}" for d,o in tied], "wrong selection or tie set")
            evaluated, physical = candidates[dep,opp,mode], candidates[dep,opp,"continuous"]
            same(drow[prefix+"_predicted_j"], evaluated["energy_j"], "selection score")
            same(drow[prefix+"_physical_j"], physical["energy_j"], "physical replay score")
            same(drow[prefix+"_history_j"], float(physical["energy_j"])-
                 float(candidates[dep,opp,"independent"]["energy_j"]), "history correction")
            require(drow[prefix+"_physical_status"] == status(physical), "mislabelled continuous decision")
            idx = (case, prefix)
            used.add(idx)
            actual = replay_lookup[idx]
            # The physical replay explicitly reruns the selected action. Validate
            # all columns, including thermal peaks, timing, and disaggregated terms.
            for field, value in physical.items():
                require(actual[field] == value, f"replay differs on {field}: {idx}")
            selected[prefix] = physical
        i, c = selected["ind"], selected["cont"]
        regret = drow["physical_regret_j"]
        if i is not None and c is not None and status(i) == "feasible":
            difference = float(i["energy_j"])-float(c["energy_j"])
            require(difference >= -1.01e-9, "continuous selector worse than eligible replay")
            same(regret, difference, "physical selection gap")
            same(drow["physical_regret_pct"], 100*difference/float(i["energy_j"]), "normalized selection gap")
        else:
            require(regret == "" and drow["physical_regret_pct"] == "",
                    "energy gain assigned to an invalid comparison")
    require(used == set(replay_lookup) and decision_cases == set(grouped), "missing or extraneous replay/decision")


def shapes(frozen, dep):
    resource_chains = {}
    for app, stages in frozen["deployments"][dep]["stages"].items():
        prefix = f"app{app}."
        chain = [(prefix+"pre", "CPU"+app), (prefix+"input", "XFER")]
        for unit, first, last in stages:
            chain.extend([(prefix+f"{unit}[{first}-{last}]", unit), (prefix+f"after_{last}", "XFER")])
        chain.append((prefix+"post", "CPU"+app))
        resource_chains[int(app)] = chain
    return resource_chains


def audit_ledger(raw, schedules, grids, frozen):
    from archive import iter_schedules  # lossless decoder and digest check only
    from hashlib import sha256

    seen = set()
    shape = {dep: shapes(frozen, dep) for dep in ("A", "C")}
    job_count = stage_count = 0
    for sid, timeline in iter_schedules(raw):
        require(sid not in seen and sid in schedules, "duplicate/unreferenced timeline")
        seen.add(sid)
        records = schedules[sid]
        first = records[0]
        jobs, stop = grids[first["window"], int(first["fps"])]
        require(timeline["window_ns"] == stop, "ledger length mismatch")
        archived = timeline["requests"]
        actual = {j["id"]: (j["app"],j["release_ns"],j["deadline_ns"]) for j in archived}
        require(actual == jobs and len(archived) == len(jobs), "archived releases/workload changed")
        digest = sha256("\n".join(f"{rid},{app},{rel},{due}" for rid,(app,rel,due) in jobs.items()).encode()).hexdigest()
        finish = {j["id"]: j["completion_ns"] for j in archived}
        ready_ns = {rid: rel for rid, (app,rel,due) in jobs.items()}
        stage_no = dict.fromkeys(jobs, 0)
        available = dict.fromkeys(RESOURCES, 0)
        busy = dict.fromkeys(RESOURCES, 0)
        activity = dict.fromkeys((*NODES, "xfer"), 0.)
        after = 0
        chains = shape[first["deployment"]]
        for row in timeline["rows"]:
            rid = row["request"]
            app = actual[rid][0]
            idx = stage_no[rid]
            unit = row["resource"].lower()
            start, end, watts = row["start_ns"], row["end_ns"], row["activity_w"]
            require(row["stage_index"] == idx and (row["stage"],row["resource"]) == chains[app][idx],
                    f"wrong stage or mapping {sid} {rid}")
            require(start >= ready_ns[rid] and start >= available[unit] and end > start and watts >= 0,
                    f"noncausal or conflicting service interval {sid} {rid}/{idx}")
            available[unit] = ready_ns[rid] = end
            stage_no[rid] += 1
            covered_ns = max(0, min(end, stop)-start)
            busy[unit] += covered_ns
            domain = "cpu" if unit.startswith("cpu") else unit
            activity[domain] += covered_ns*1e-9*watts
            after += end > stop
        require(all(stage_no[rid] == len(chains[app]) and ready_ns[rid] == finish[rid]
                    for rid,(app,rel,due) in jobs.items()), "partial or missing job")
        job_count += len(jobs)
        stage_count += len(timeline["rows"])
        completed = sum(t <= stop for t in finish.values())
        late = sum(finish[rid] > due for rid, (app,rel,due) in jobs.items())
        slack = min(due-finish[rid] for rid,(app,rel,due) in jobs.items())
        response = max(finish[rid]-rel for rid,(app,rel,due) in jobs.items())
        for r in records:
            require(int(r["completed"]) == completed and int(r["late_count"]) == late and
                    int(r["stages_touching_after_window"]) == after and r["request_sha256"] == digest,
                    f"archived job/window statistics differ from candidate {sid}")
            same(r["min_slack_ms"], slack/1e6, "critical slack")
            same(r["max_response_ms"], response/1e6, "critical response")
            same(r["last_finish_s"], max(finish.values())/1e9, "last completion")
            for unit in RESOURCES:
                same(r[f"busy_{unit}_s"], busy[unit]/1e9, unit+" busy timeline")
            for node in NODES:
                same(r[f"activity_{node}_j"], activity[node], node+" event-integrated active watts")
            same(r["transfer_j"], activity["xfer"], "transfer event power")
    require(seen == set(schedules), "missing event archives")
    return job_count, stage_count


def main(folder):
    p = json.loads((folder/"platform.json").read_text(encoding="utf-8-sig"))
    f = json.loads((folder.parent/"kim_case_b_freeze"/"input.json").read_text(encoding="utf-8-sig"))
    raw = folder/"raw"
    rows = read_csv(raw/"candidates.csv")
    groups, schedules, grids = audit_rows(rows, p)
    paired = audit_lengths(groups)
    decisions = read_csv(folder/"decisions.csv")
    replays = read_csv(raw/"physical_replays.csv")
    audit_decisions(decisions, replays, groups)
    jobs, stages = audit_ledger(raw, schedules, grids, f)
    return {"status":"PASS", "conditions":len(groups), "candidate_evaluations":len(rows),
            "fixed_actions_paired":len(rows)//2, "unique_event_schedules":len(schedules),
            "archived_requests_checked":jobs, "archived_stages_checked":stages,
            "selected_physical_replays":len(replays), "feasible_nested_windows_checked":paired}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE)
    args = parser.parse_args()
    print(json.dumps(main(args.root), indent=2, ensure_ascii=False))
