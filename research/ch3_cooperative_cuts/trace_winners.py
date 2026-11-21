"""Reconstruct cooperative winner ancestry from completed slot logs, without physical replay."""
import argparse
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from catalog_ext import make_domain


HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "study_config.json").read_bytes())
ACTIONS = ("initialize", "cut", "binding", "exchange", "dvfs", "cut+dvfs", "binding+dvfs", "exchange+dvfs")
METHODS = {"full", "no_heat", "no_contention", "no_coord"}


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def list_text(values):
    return "|".join(str(x) for x in values)


def references(root):
    path = root / "research/ch3_final_experiments/formal/tables/run_results.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if
                (r["group"], r["domain"], r["method"], r["outcome"]) == ("AB", "81", "CT-Joint", "SAFE")]
    result = {r["case"]: float(r["safe_energy_j"]) for r in rows}
    if len(rows) != len(result) or set(result) != {name + "_25C" for name in CONFIG["cases"]}:
        raise ValueError("Archived 81-deployment exact references differ.")
    return result


class UnitReader:
    def __init__(self, units, case, slot, archive):
        self.dir = units / case / slot
        self.slot = slot
        self.archive = archive

    def read(self, name):
        if self.archive is None:
            return (self.dir / name).read_bytes()
        member = self.archive.getmember(f"{self.slot}/{name}")
        if not member.isfile():
            raise ValueError(f"Expected a regular archive member: {member.name}")
        with self.archive.extractfile(member) as stream:
            return stream.read()


def fingerprint(stages):
    """Per-app cut endpoints and DLA bindings; GPU suffix is implicit in this catalog."""
    return tuple(tuple((row[2], int(row[0][-1])) for row in stages[str(app)] if row[0].startswith("DLA"))
                 for app in range(4))


def cut_vector(mapping):
    return tuple(tuple(cut for cut, _ in app) for app in mapping)


def core_counts(mapping):
    counts = Counter(core for app in mapping for _, core in app)
    return [counts[0], counts[1]]


def exchange_detail(parent, child):
    delta = [len(b)-len(a) for a, b in zip(parent, child)]
    if sorted(delta) == [-1,0,0,1]:
        return "slot_transfer", delta.index(-1), delta.index(1)
    if any(delta) or cut_vector(parent) != cut_vector(child):
        raise ValueError(f"Unclassified two-app exchange: {parent} -> {child}")
    return "binding_swap", None, None


def map_edits(start, final):
    # Naming the same physical solution after a global DLA swap must not count as a four-app edit.
    swapped = tuple(tuple((cut, bit ^ 1) for cut, bit in app) for app in final)
    distance = lambda other: sum(a != b for a, b in zip(start, other))
    relabel = distance(swapped) < distance(final)
    aligned = swapped if relabel else final
    cuts_a, cuts_b = cut_vector(start), cut_vector(final)
    changed_map = [app for app in range(4) if start[app] != aligned[app]]
    changed_cuts = [app for app in range(4) if cuts_a[app] != cuts_b[app]]
    slots_a, slots_b = [len(x) for x in start], [len(x) for x in final]
    return dict(start_cuts=encode(cuts_a), winner_cuts=encode(cuts_b),
                changed_mapping_apps=list_text(changed_map), changed_cut_apps=list_text(changed_cuts),
                global_swap_to_align=int(relabel), start_dla_slots=encode(slots_a),
                winner_dla_slots=encode(slots_b), slot_delta_by_app=encode([b-a for a, b in zip(slots_a, slots_b)]),
                start_slots_by_core=encode(core_counts(start)), winner_slots_by_core=encode(core_counts(final)),
                start_slots_total=sum(slots_a), winner_slots_total=sum(slots_b))


def job_trace(job, reader, reference, describe):
    case, scope, method, seed = job
    receipt = json.loads(reader.read("receipt.json"))
    if receipt["job"] != list(job):
        raise ValueError(f"Receipt job mismatch: {job}")
    row = dict(case=case, scope=scope, method=method, seed=seed, state=receipt["state"], safe=0,
               old81_exact_j=reference, unit=f"{case}/{reader.slot}")
    if receipt["state"] != "finished":
        return row, []

    def verified(name):
        data = reader.read(name)
        if sha256(data).hexdigest() != receipt["files"][name]:
            raise ValueError(f"Receipt digest mismatch: {job}/{name}")
        return gzip.decompress(data)

    result = json.loads(verified("result.json.gz"))
    if result["job"] != list(job):
        raise ValueError(f"Result job mismatch: {job}")
    nodes, anchor_states = {}, Counter()
    rounds = 0
    active_anchor = None
    for raw in verified("events.jsonl.gz").splitlines():
        _, event, info = json.loads(raw)
        if event == "identity" and info["job"] != list(job):
            raise ValueError(f"Event job mismatch: {job}")
        if event == "cooperative_round":
            active_anchor = tuple(info["anchor"])
            if info["index"] != rounds or active_anchor not in nodes:
                raise ValueError(f"Unknown or out-of-order expansion anchor: {job}")
            rounds += 1
            anchor_states[nodes[active_anchor]["status"]] += 1
        if event != "cooperative_position":
            continue
        key = tuple(info["genome"])
        parent = tuple(info["parent"]) if info["parent"] is not None else None
        if (key in nodes or parent != active_anchor
                or ((parent is None) != (info["operator"] == "initialize"))):
            raise ValueError(f"Invalid parent or duplicate observation: {job}/{key}")
        nodes[key] = dict(step=len(nodes)+1, parent=parent, action=info["operator"], time=info["at_s"],
                          status=info["result"]["status"], energy=info["result"]["energy_j"],
                          slack=info["result"]["slack_ms"], peaks=info["result"]["upper"])
    summary = result["summary"]
    observed = Counter(n["action"] for n in nodes.values())
    if (rounds not in (summary["completed_rounds"], summary["completed_rounds"]+1)
            or len(nodes) != summary["unique_completed"] or observed != Counter(summary["action_counts"])
            or set(observed)-set(ACTIONS)):
        raise ValueError(f"Logged observations disagree with result: {job}")
    exchanges = {}
    for key, n in nodes.items():
        if n["action"].split("+")[0] == "exchange":
            exchanges[key] = exchange_detail(describe(n["parent"][0])[0], describe(key[0])[0])
    row.update(safe=int(result["safe"]), verified_positions=len(nodes), action_counts=encode(dict(sorted(observed.items()))),
               selected_anchor_rounds=rounds, completed_rounds=summary["completed_rounds"],
               violation_anchor_rounds=anchor_states["VIOLATION"], unresolved_anchor_rounds=anchor_states["UNRESOLVED"],
               deadline_anchor_rounds=anchor_states["DEADLINE"], safe_anchor_rounds=anchor_states["SAFE"],
               exchange_types=encode(dict(sorted(Counter(d[0] for d in exchanges.values()).items()))))
    safe_nodes = [(k, n) for k, n in nodes.items() if n["status"] == "SAFE"]
    winner = tuple(summary["winner"]) if summary["winner"] is not None else None
    if (winner is None) != (not safe_nodes) or bool(safe_nodes) != result["safe"]:
        raise ValueError(f"Missing or spurious SAFE winner: {job}")
    if winner is None:
        return row, []
    if min(safe_nodes, key=lambda item: (item[1]["energy"], item[0]))[0] != winner:
        raise ValueError(f"Winner is not the recorded minimum SAFE genome: {job}")
    win = nodes[winner]
    ordered_path = []
    key = winner
    while key is not None:
        ordered_path.append(key)
        key = nodes[key]["parent"]
    ordered_path.reverse()
    start = ordered_path[0]
    if start[0] not in result["init_deps"] or win["energy"] != result["selected"]["energy_j"]:
        raise ValueError(f"Winner ancestry or physical selection mismatch: {job}")

    def milestone(prefix, item):
        if item is None:
            return {}
        k, n = item
        milestone_fields = {prefix+"_step": n["step"], prefix+"_s": n["time"], prefix+"_action": n["action"],
                            prefix+"_genome": encode(k), prefix+"_j": n["energy"]}
        if prefix == "first_below_old25":
            mapping, _, novel, old, _ = describe(k[0])
            milestone_fields.update(first_below_old25_is_old_dep=int(old),
                                    first_below_old25_cut_endpoints=encode(cut_vector(mapping)),
                                    first_below_old25_new_boundary_apps=list_text(novel))
            if old:
                raise ValueError(f"Legacy-domain witness contradicts accepted certified optimum: {job}/{k}")
        return milestone_fields

    def below(sequence):
        if reference is not None:
            return next(((k, nodes[k]) for k in sequence if nodes[k]["status"] == "SAFE"
                         and nodes[k]["energy"] < reference - CONFIG["energy_tolerance_j"]), None)

    earliest_min = next(item for item in safe_nodes if item[1]["energy"] == win["energy"])
    projected = [k for k in ordered_path if nodes[k]["action"] != "initialize"]
    root_map = describe(start[0])[0]
    win_map, novel_shapes, novel_cuts, is_old, endpoints = describe(winner[0])
    ancestry_states = Counter(nodes[k]["status"] for k in ordered_path[:-1])
    row.update(winner_dep=winner[0], winner_genome=encode(winner), winner_safe_j=win["energy"],
               winner_step=win["step"], winner_s=win["time"], start_dep=start[0], start_genome=encode(start),
               start_status=nodes[start]["status"], start_actual_j=nodes[start]["energy"],
               winner_is_old_deployment=int(is_old), winner_novel_shape_apps=list_text(novel_shapes),
               winner_new_boundary_apps=list_text(novel_cuts), winner_new_boundaries=encode(endpoints),
               path_moves=len(projected), violation_ancestors=ancestry_states["VIOLATION"],
               unresolved_ancestors=ancestry_states["UNRESOLVED"], deadline_ancestors=ancestry_states["DEADLINE"],
               path_action_counts=encode(dict(sorted(Counter(nodes[k]["action"] for k in projected).items()))),
               path_exchange_types=encode(dict(sorted(Counter(exchanges[k][0] for k in projected if k in exchanges).items()))),
               new_cut_on_path=int(any(describe(k[0])[2] for k in ordered_path)),
               **map_edits(root_map, win_map), **milestone("energy_min", earliest_min),
               **milestone("first_below_old25", below(nodes)),
               **milestone("path_first_below_old25", below(ordered_path)))
    path_rows = []
    for depth, k in enumerate(ordered_path):
        n = nodes[k]
        mapping, shapes, cuts, old, _ = describe(k[0])
        exch, donor, receiver = exchanges.get(k, (None, None, None))
        path_rows.append(dict(case=case, scope=scope, method=method, seed=seed, path_step=depth,
                              observation_step=n["step"], at_s=n["time"], operator=n["action"],
                              exchange_type=exch, slot_donor_app=donor, slot_receiver_app=receiver,
                              dep=k[0], opp_indices=list_text(k[1:]), is_old_dep=int(old),
                              cut_endpoints=encode(cut_vector(mapping)),
                              dla_binding=encode([[b for _, b in net] for net in mapping]),
                              novel_shape_apps=list_text(shapes), new_boundary_apps=list_text(cuts),
                              status=n["status"], actual_energy_j=n["energy"],
                              peak_upper_c=max(n["peaks"]) if n["peaks"] is not None else None,
                              min_slack_ms=n["slack"]))
    return row, path_rows


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    tmp = path.with_suffix(".csv.partial")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def check_summary(rows, path, partial):
    with path.open(encoding="utf-8-sig", newline="") as f:
        entries = [r for r in csv.DictReader(f) if r["method"] in METHODS]
    data = {(r["case"], r["scope"], r["method"], int(r["seed"])): r for r in entries}
    if len(data) != len(entries) or (not partial and len(data) != len(rows)):
        raise ValueError(f"Invalid number of cooperative slots in {path}")
    for r in rows:
        key = (r["case"], r["scope"], r["method"], r["seed"])
        entry = data[key]
        if (entry["receipt_state"] != r["state"] or int(entry["safety"]) != r["safe"]
                or (r["safe"] and (float(entry["safe_energy_j"]) != r["winner_safe_j"]
                                    or entry["deployment"] != r["winner_dep"]
                                    or json.loads(entry["opp_indices"]) != json.loads(r["winner_genome"])[1:]))):
            raise ValueError(f"Official run summary and raw ancestry disagree: {key}")


def mechanism_summary(rows):
    groups = defaultdict(list)
    for r in rows:
        temperature = float(r["case"].rsplit("_", 1)[1][:-1].replace("p", "."))
        groups[(r["scope"], r["method"], temperature)].append(r)
    output = []
    for (scope, method, temp), group in sorted(groups.items()):
        complete = [r for r in group if r["state"] == "finished"]
        winners = [r for r in complete if r["safe"]]
        def total(field):
            return sum(r[field] for r in complete)
        all_actions = Counter()
        for r in complete:
            all_actions.update(json.loads(r["action_counts"]))
        actions = [json.loads(r["path_action_counts"]) for r in winners]
        exchanges = [json.loads(r["path_exchange_types"]) for r in winners]
        cutlists = [json.loads(r["winner_new_boundaries"]) for r in winners]
        distinct = sorted({tuple(cut) for cuts in cutlists for cut in cuts})
        rounds, hot = total("selected_anchor_rounds"), total("violation_anchor_rounds")
        output.append(dict(scope=scope, method=method, ambient_c=temp, slots=len(group), finished_slots=len(complete),
                           safe_winners=len(winners), selected_anchor_rounds=rounds,
                           completed_rounds=total("completed_rounds"), violation_anchor_rounds=hot,
                           violation_anchor_fraction=hot/rounds if rounds else None,
                           safe_anchor_rounds=total("safe_anchor_rounds"), unresolved_anchor_rounds=total("unresolved_anchor_rounds"),
                           deadline_anchor_rounds=total("deadline_anchor_rounds"),
                           verified_positions=total("verified_positions"),
                           observed_pure_dvfs=all_actions["dvfs"],
                           observed_joint_dvfs=sum(n for op, n in all_actions.items() if op.endswith("+dvfs")),
                           runs_with_violation_anchor=sum(r["violation_anchor_rounds"]>0 for r in complete),
                           winners_with_violation_ancestor=sum(r["violation_ancestors"]>0 for r in winners),
                           winners_with_unresolved_ancestor=sum(r["unresolved_ancestors"]>0 for r in winners),
                           winners_with_deadline_ancestor=sum(r["deadline_ancestors"]>0 for r in winners),
                           winners_with_slot_transfer=sum(e.get("slot_transfer", 0)>0 for e in exchanges),
                           winners_with_binding_swap=sum(e.get("binding_swap", 0)>0 for e in exchanges),
                           winners_with_single_app_binding=sum("binding" in a or "binding+dvfs" in a for a in actions),
                           winners_with_dvfs_action=sum(any("dvfs" in op for op in a) for a in actions),
                           winners_with_any_new_boundary=sum(bool(cuts) for cuts in cutlists),
                           winner_new_boundary_occurrences=sum(map(len, cutlists)),
                           distinct_new_boundary_count=len(distinct), distinct_new_app_endpoints=encode(distinct)))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path, help="Repository with the frozen 6ec3214 source inputs")
    parser.add_argument("--out-dir", type=Path, default=HERE / "tables")
    parser.add_argument("--units", type=Path, default=HERE / "units")
    parser.add_argument("--archives", type=Path, default=HERE / "archives")
    parser.add_argument("--run-results", type=Path, help="Audited run_results.csv (default tables/run_results.csv)")
    parser.add_argument("--partial", action="store_true", help="Summarize completed receipts only")
    args = parser.parse_args()
    old = references(args.source_root)
    domain = make_domain(args.source_root, "extended")
    original = [cut_vector(fingerprint(domain.stages(d))) for d in domain.legacy_ids]
    old_shapes = [{m[i] for m in original} for i in range(4)]
    old_endpoints = [{v for shape in old_shapes[i] for v in shape} for i in range(4)]

    @lru_cache(maxsize=16384)
    def describe(dep):
        mapping = fingerprint(domain.stages(dep))
        cuts = cut_vector(mapping)
        novel_shapes = [i for i in range(4) if cuts[i] not in old_shapes[i]]
        endpoints = [(i, end) for i in range(4) for end in cuts[i] if end not in old_endpoints[i]]
        novel_cuts = sorted({i for i, _ in endpoints})
        return mapping, novel_shapes, novel_cuts, dep in domain.legacy_ids, endpoints

    rows, steps = [], []
    for scene in CONFIG["cases"]:
        for suffix in CONFIG["ambient_suffixes"]:
            case = f"{scene}_{suffix}"
            path = args.archives / (case + ".tar")
            archive = tarfile.open(path, "r:") if path.exists() else None
            try:
                for scope, method in CONFIG["methods"]:
                    if method not in METHODS:
                        continue
                    for seed in CONFIG["seeds"]:
                        slot = f"{scope}_{method}_{seed}"
                        reader = UnitReader(args.units, case, slot, archive)
                        if args.partial and archive is None and not (reader.dir/"receipt.json").is_file():
                            continue
                        row, trace = job_trace((case, scope, method, seed), reader, old.get(case), describe)
                        rows.append(row)
                        steps.extend(trace)
            finally:
                if archive is not None:
                    archive.close()
    results_path = args.run_results or HERE / "tables/run_results.csv"
    if not args.partial or args.run_results or results_path.is_file():
        check_summary(rows, results_path, args.partial)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "winner_paths.csv", rows)
    write_csv(args.out_dir / "winner_path_steps.csv", steps)
    write_csv(args.out_dir / "mechanism_summary.csv", mechanism_summary(rows))
    print(f"Cooperative slots {len(rows)}; SAFE winners {sum(r.get('safe', 0) for r in rows)}; "
          f"ancestry rows {len(steps)}")


if __name__ == "__main__":
    main()
