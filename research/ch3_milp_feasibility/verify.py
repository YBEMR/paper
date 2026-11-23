"""Audit stored records and prove the reported lower bounds independently of HiGHS.

No new physical case or search is run. Count complete codes by disjoint prefixes.
Use only analytic energy bounds and point-temperature witnesses from archived kernels.
"""
import csv
from collections import Counter
from hashlib import sha256
import json
from math import prod
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
ATOL = 1e-7


def read(path):
    return json.loads(path.read_bytes())


def filehash(path):
    return sha256(path.read_bytes()).hexdigest()


def readcsv(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def check(ok, message):
    if not ok:
        raise ValueError(message)


def verify_lower_bound(grid, k, target):
    """Pad every interval outwards. All temperatures here are relative to the 30 C inlet."""
    coverage = Counter()
    for d, slots in grid.items():
        counts = [len(s) for s in slots]
        legal = prod(counts)
        coverage["deadline"] += 27**4 - legal
        if not legal:
            continue
        low = high = np.zeros(4)
        mins = []
        for slot in slots:
            ids = list(slot.values())
            F, w = k["F"][ids], k["w"][ids]
            mins.append(float(np.min(k["e"][ids] + (np.maximum(w,0)*low).sum(axis=1)
                                 + (np.minimum(w,0)*high).sum(axis=1)))-1e-10)
            offsets = k["b"][ids]
            pos, neg = np.maximum(F,0), np.minimum(F,0)
            low,high = ((offsets+pos@low+neg@high).min(axis=0)-1e-8,
                        (offsets+pos@high+neg@low).max(axis=0)+1e-8)
        def cover(j, delta, energy):
            if energy+sum(mins[j:])-1e-9 >= target:
                coverage["energy_bound"] += prod(counts[j:])
                return
            if j==4:
                raise ValueError(f"unexplained code below declared lower bound in {d}")
            for i in slots[j].values():
                if max(k["peak"][i]+k["h"][i]@delta) > 80.+1e-6:
                    coverage["overtemp_witness"] += prod(counts[j+1:])
                else:
                    cover(j+1,k["b"][i]+k["F"][i]@delta,energy+k["e"][i]+k["w"][i]@delta)
        cover(0,np.zeros(4),0.)
    check(sum(coverage.values())==len(grid)*27**4, "incomplete domain coverage")
    return coverage


def verify_certificate(e, grid, k, expected, spec, order, frames):
    rows = e["completions"]
    p = e["physical"]
    packed = [[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]] for r in rows]
    digest = sha256(json.dumps(packed,separators=(",",":")).encode()).hexdigest()
    check(digest==e["request_sha256"]==spec["request_sha256"], "ledger stream digest")
    check(len(rows)==len(set(r["request_id"] for r in rows))==p["completed"]==p["required"]==500,
          "ledger coverage")
    check(all(r["release_ns"]<=r["completion_ns"]<=r["deadline_ns"] and
              r["deadline_ns"]-r["release_ns"]==40000000 and
              r["deadline_ns"]-r["completion_ns"]==r["slack_ns"] for r in rows), "request deadlines")
    check(p["min_slack_ms"]==min(r["slack_ns"] for r in rows)/1e6,"minimum slack")
    check(e["case"]==spec["id"] and e["dep"]==expected["deployment"]
          and e["indices"]==expected["opp"], "selection")
    inlet = np.full(4,30.)
    energy, start = 0., 0
    sequence = p["scene_rows"]
    check(len(sequence)==4 and p["fully_replayed"] and p["deadline_ok"], "complete scenes")
    for j,s in enumerate(sequence):
        check(s["start_ns"]==start and s["service_end_ns"]-start==frames[j]*40000000
              and s["scene"]==order[j] and np.allclose(s["entry_c"],inlet,atol=ATOL,rtol=0),
              "scene coverage/thermal inheritance")
        subset = [r for r in rows if r["scene"]==s["scene"]]
        check(len(subset)==s["required"] and s["min_slack_ns"]==min(r["slack_ns"] for r in subset),
              "scene ledger")
        i = grid[e["dep"]][j][str(e["indices"][j])]
        delta = inlet-30
        check(abs(s["energy_j"]-(k["e"][i]+k["w"][i]@delta))<ATOL,"scene affine energy")
        inlet = 30+k["b"][i]+k["F"][i]@delta
        check(max(abs(inlet-s["final_c"]))<ATOL,"scene affine outlet")
        check(np.all(k["peak"][i]+k["h"][i]@delta<=np.array(s["peak_upper_c"])+ATOL),
              "witness exceeds certified maximum")
        energy += s["energy_j"]
        start = s["end_ns"]
    check(start==10040000000 and sequence[-1]["service_end_ns"]==10000000000,"terminal 40 ms")
    lo,hi = (np.max([s[key] for s in sequence],axis=0) for key in ("peak_lower_c","peak_upper_c"))
    check(list(lo)==p["peak_lower_c"] and list(hi)==p["peak_upper_c"] and np.all(lo<=hi),"peaks")
    classification = "VIOLATION" if max(lo)>80 else "SAFE" if max(hi)<=80 else "UNRESOLVED"
    check(classification==p["thermal_status"]==expected["status"]
          and abs(expected["energy_j"]-energy)<ATOL and abs(p["energy_j"]-energy)<ATOL,"certificate")


def main():
    protocol = read(HERE/"protocol.json")
    catalog = read(RESEARCH/"kim_multidnn_expansion/catalog.json")
    inputs = readcsv(RESEARCH/"ch3_final_experiments/derived/instances.csv")
    m2 = next(r for r in readcsv(RESEARCH/"kim_multidnn_search_trial/results/run_metrics.csv")
              if r["id"]=="dev-0-M2")
    pressure = [r for r in read(RESEARCH/"kim_pressure_feasibility/raw_execution/summary.json")
                if r["case_id"]=="reverse_flat_27p5C"]
    check({r["deployment"] for r in pressure}==set(protocol["cases"]["B"]["deployments"]) and
          all(sum(r["counts"].values())==27**4 and r["counts"]["unresolved"]==0 for r in pressure),
          "historical pressure classification scope")
    audit, table = {}, []
    for label, spec in protocol["cases"].items():
        directory = HERE/"raw"/label
        res,receipt,grid = (read(directory/name) for name in ("result.json","receipt.json","grid.json"))
        events = [json.loads(r) for r in (directory/"events.jsonl").read_text().splitlines()]
        k = dict(np.load(directory/"kernels.npz",allow_pickle=False))
        best, costs = res["best"],res["cost"]
        historical = (float(m2["best_safe_j"]) if label=="A" else
                      min(r["strict_minimum_known_safe_j"] for r in pressure if r["safe_witness"]))
        historic_physical = (historical if label=="A" else
                             min(r["physical"]["energy_j"] for r in pressure if r["safe_witness"]))
        input_event = next(e for e in events if e["event"]=="input")
        check(input_event["catalog_sha256"]==filehash(RESEARCH/"kim_multidnn_expansion/catalog.json")
              and input_event["request_sha256"]==spec["request_sha256"],"input provenance")
        deps = spec["deployments"] or catalog["search_order"]
        check(receipt["config_sha256"]==filehash(HERE/"protocol.json") and receipt["exit_code"]==0 and
              not receipt["killed"] and receipt["wall_s"]<=120 and res["certificate_s"]<=receipt["wall_s"],
              "budget/receipt")
        check(list(grid)==deps and len(deps)==spec["domain"]==res["finished_deployments"],"domain")
        instance = next(r for r in inputs if r["instance_id"]==spec["id"])
        order = instance["scene_order"].split("/")
        frames = list(map(int,instance["frames_execution_order"].split("/")))
        check({i for slots in grid.values() for s in slots for i in s.values()}==set(range(len(k["e"]))),
              "kernel reachability")
        check(all(len(slots)==4 and all(0<=int(f)<27 for s in slots for f in s) for slots in grid.values()),
              "clock domain")
        for c in res["certificates"]:
            e = read(directory/c["file"])
            check(e["stages"]==catalog["deployments"][e["dep"]]["stages"],"deployment bindings")
            verify_certificate(e,grid,k,c,spec,order,frames)
        for d,prefix in res["cuts"]:
            matches = [read(directory/c["file"]) for c in res["certificates"]
                       if c["status"]=="VIOLATION" and c["deployment"]==d and c["opp"][:len(prefix)]==prefix]
            check(any(max(s["peak_lower_c"])>80 for e in matches
                      for s in e["physical"]["scene_rows"][:len(prefix)]),"prefix cut without a violation")
        target = res["lower_bound_j"]
        check(res["status"]=="optimal_within_tolerance" and 0<=best["energy_j"]-target<=ATOL
              and abs(best["energy_j"]-historical)<ATOL, "proof/archived objective")
        coverage = verify_lower_bound(grid,k,target)
        legal = len(deps)*27**4-coverage["deadline"]
        historic_legal = int(m2["legal_codes"]) if label=="A" else sum(
            r["counts"]["safe"]+r["counts"]["overtemp"] for r in pressure)
        check(legal==historic_legal,"deadline scope against historical independent classification")
        check(res["first_safe_s"]==min(c["time_s"] for c in res["certificates"] if c["status"]=="SAFE"),
              "first safe timestamp")
        audit[label] = dict(domain_codes=len(deps)*27**4, deadline_legal_codes=legal,
                            lower_bound_coverage=dict(coverage), checked_lower_bound_j=target,
                            historic_j=historical, actual_frames=frames,
                            physical_certificates=len(res["certificates"]), unique_requests_each=500)
        last = res["solves"][-1]
        model_ready = next(e["time_s"] for e in events if e["event"]=="model")
        row = dict(case=label,case_id=spec["id"],deployments=len(deps),candidate_codes=len(deps)*27**4,
                   deadline_legal=legal,first_safe_s=res["first_safe_s"],best_safe_first_s=best["time_s"],
                   proof_s=res["certificate_s"],wall_s=receipt["wall_s"],first_model_ready_s=model_ready,
                   **costs,build_accounted_s=costs["schedule_s"]+costs["coefficient_s"]+costs["matrix_s"],
                   other_wall_s=receipt["wall_s"]-sum(costs.values()),solver_calls=len(res["solves"]),
                   **last["size"],deployment=best["deployment"],opps="/".join(read(directory/best["file"])["opps"]),
                   safe_j=best["energy_j"],lower_bound_j=target,gap_j=best["energy_j"]-target,
                   peak_lower_c=best["peak_lower_c"],peak_upper_c=best["peak_upper_c"],
                   completed=best["completed"],min_slack_ms=best["slack_ms"],historic_j=historical,
                   historic_physical_j=historic_physical,energy_difference_j=best["energy_j"]-historic_physical,status=res["status"])
        table.append(row)
    with (HERE/"summary.csv").open("w",newline="",encoding="utf-8") as stream:
        writer = csv.DictWriter(stream,fieldnames=table[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    (HERE/"verification.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2))


if __name__=="__main__":
    main()
