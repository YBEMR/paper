"""Read-only archived calibration arithmetic audit and descriptive summary.

No generator, scheduler, optimizer, or thermal evaluator is imported.
Writes only a new analysis directory; does not modify frozen execution evidence.
"""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compressed(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def metric_group(records, beta):
    answer = {"conditions": len(records), "independent_roots": len({r["call"]["root_id"] for r in records})}
    if not records:
        return answer
    for opp in ("H", "M", "L"):
        metrics = [r["metrics"][beta][opp] for r in records]
        request_count = sum(m["request_count"] for m in metrics)
        request_pass = sum(m["request_on_time_count"] for m in metrics)
        scenes = sum(m["scene_count"] for m in metrics)
        scene_pass = sum(m["scene_on_time_count"] for m in metrics)
        etas = [Fraction(m["minimum_eta"]) for m in metrics]
        thresholds = [Fraction(r["thresholds"][opp]["whole_family_beta_required"]) for r in records]
        answer[opp] = {"all_requests_on_time_conditions": sum(m["all_on_time"] for m in metrics),
                       "request_pass": request_pass, "request_count": request_count,
                       "request_rate": request_pass / request_count, "scene_pass": scene_pass,
                       "scene_count": scenes, "scene_rate": scene_pass / scenes,
                       "minimum_eta_median": float(statistics.median(etas)),
                       "minimum_eta_range": [float(min(etas)), float(max(etas))],
                       "whole_family_beta_median": float(statistics.median(thresholds)),
                       "whole_family_beta_range": [float(min(thresholds)), float(max(thresholds))],
                       "eta_at_least_point_one_conditions": sum(e >= Fraction(1, 10) for e in etas)}
    return answer


def summarize(execution, freeze, output):
    batch = read(execution / "batch_result.json")
    manifest = read(execution / "manifest.json")
    assert manifest == read(freeze / "manifest.json")
    expected = {c["condition_id"]: c for c in manifest["calls"]}
    rows, checks, by_id = [], [], {}
    for ledger in batch["rows"]:
        cid = ledger["condition_id"]
        target = execution / cid
        result_path = target / "result.json"
        if result_path.exists():
            assert sha(result_path) == ledger["result_sha256"]
        if ledger["state"] != "COMPLETE":
            continue
        result = read(result_path)
        assert result["state"] == "COMPLETE" and result["condition"] == expected[cid]
        assert result["elapsed_s"] <= ledger["limit_seconds"] <= 60
        assert not result["denied_imports"] and not result["denied_events"]
        assert result["counters"]["formal_method_calls"] == result["counters"]["thermal_integrations"] == 0
        for filename, key in (("evidence.json.gz", "evidence_sha256"), ("generated_workload.json.gz", "workload_sha256")):
            assert sha(target / filename) == result[key]
        e = compressed(target / "evidence.json.gz")
        assert compressed(target / "generated_workload.json.gz") == e["workload"]
        assert e["call"] == expected[cid] and e["state"] == "TIME_CALIBRATION_COMPLETE"
        assert all(c["state"] == "TIME_STRUCTURAL_VALID" for c in e["reference"]["checks"].values())
        assert e["thermal_status"] == e["energy_status"] == "NOT_EVALUATED" and e["beta_selected"] is None
        arithmetic_rows = 0
        for beta, metrics in e["metrics"].items():
            receipt = e["deadlines"][beta]
            for sid, reqs in receipt["requests"].items():
                for rid, r in reqs.items():
                    release = Fraction(r["release_ms"])
                    if e["call"]["kind"] == "base":
                        fh = Fraction(e["reference"]["checks"]["H"]["completions_ms"][sid][rid])
                        assert Fraction(r["deadline_ms"]) == release + Fraction(beta) * (fh - release)
                    else:
                        parent = by_id[e["call"]["parent_condition_id"]]
                        source = receipt["request_sources"][sid][rid]
                        pr = parent["deadlines"][beta]["requests"][source["source_scene"]][source["source_request"]]
                        assert receipt["deadline_origin_hash"] == parent["deadlines"][beta]["deadline_origin_hash"]
                        if source["policy"] == "absolute":
                            assert r == pr
                        else:
                            assert e["call"]["kind"] == "S7" and source["policy"] == "same_relative"
                            assert Fraction(r["relative_deadline_ms"]) == Fraction(pr["relative_deadline_ms"])
                            assert Fraction(r["deadline_ms"]) == release + Fraction(pr["relative_deadline_ms"])
            for opp, metric in metrics.items():
                for r in metric["requests"]:
                    deadline = receipt["requests"][r["scene"]][r["request"]]
                    due, release, finish = (Fraction(deadline["deadline_ms"]), Fraction(deadline["release_ms"]),
                                            Fraction(e["reference"]["checks"][opp]["completions_ms"][r["scene"]][r["request"]]))
                    assert Fraction(r["slack_ms"]) == due - finish
                    assert Fraction(r["eta"]) == (due - finish) / (due - release)
                    assert r["on_time"] == (finish <= due)
                    arithmetic_rows += 1
                assert metric["request_on_time_count"] == sum(r["on_time"] for r in metric["requests"])
                assert metric["all_on_time"] == all(r["on_time"] for r in metric["requests"])
        checks.append({"condition_id": cid, "archive_and_identity": True, "independent_deadline_arithmetic_rows": arithmetic_rows})
        rows.append(e)
        by_id[cid] = e
    assert len(rows) == batch["completed_conditions"]
    groups = {}
    base = [r for r in rows if r["call"]["kind"] == "base"]
    for scale in (6, 24, 96):
        group = [r for r in base if r["call"]["scale"] == scale]
        groups[f"base_{scale}"] = {b: metric_group(group, b) for b in ("1", "13/10", "8/5", "2")}
    for kind in ("base", "S4", "S5", "S7", "S3"):
        group = [r for r in rows if r["call"]["kind"] == kind]
        groups[kind] = {b: metric_group(group, b) for b in ("1", "13/10", "8/5", "2")}
    for topology in ("serial", "layered"):
        group = [r for r in rows if r["call"]["kind"] == "S4" and r["call"]["value"] == topology]
        groups["S4_" + topology] = {b: metric_group(group, b) for b in ("1", "13/10", "8/5", "2")}
    for pool in ("A", "B"):
        for compatibility in ("cpu_common", "heterogeneous"):
            group = [r for r in base if r["call"]["scene_pool"] == pool and r["call"]["compatibility_pool"] == compatibility]
            groups[pool + "_" + compatibility] = {b: metric_group(group, b) for b in ("1", "13/10", "8/5", "2")}
    # Joint strata are supplied without pretending small subgroups are inferential samples.
    strata = {}
    for scale in (6, 24, 96):
        for pool in ("A", "B"):
            for compatibility in ("cpu_common", "heterogeneous"):
                group = [r for r in base if (r["call"]["scale"], r["call"]["scene_pool"], r["call"]["compatibility_pool"]) == (scale, pool, compatibility)]
                strata[f"{scale}_{pool}_{compatibility}"] = metric_group(group, "13/10")
    profile_counts, special_counts = Counter(), Counter()
    for r in base:
        if r["call"]["scale"] != 96:
            continue
        for trace in r["workload"]["profile_traces"].values():
            profile_counts[trace["category"]] += 1
            special_counts[trace["pool"] + "_identities"] += 1
            if trace["specialized"]:
                special_counts[trace["pool"] + "_" + trace["category"]] += 1
    timing = [r["elapsed_s"] for r in batch["rows"]]
    due_by_scale = {}
    for scale in (6, 24, 96):
        ds = [Fraction(d["deadline_ms"]) for r in base if r["call"]["scale"] == scale
              for reqs in r["deadlines"]["13/10"]["requests"].values() for d in reqs.values()]
        due_by_scale[str(scale)] = {"range_ms": [float(min(ds)), float(max(ds))]} if ds else None
    repo = Path(__file__).resolve().parent.parent
    frozen_sources = read(freeze / "source_manifest.json")
    assert all(sha(repo / p) == digest for p, digest in frozen_sources.items())
    assert batch["protected_sources_before"] == batch["protected_sources_after"]
    assert all(sha(repo / p) == digest for p, digest in batch["protected_sources_after"].items())
    s1 = {}
    for pool in ("A", "B"):
        for n in ("1", "2", "4", "6", "8"):
            selected = [r for r in base if r["call"]["scene_pool"] == pool]
            s1[pool + "_" + n] = {
                "base_conditions": len(selected), "projection_only": True,
                "M_all_on_time": sum(r["S1_projections"][n]["metrics"]["13/10"]["M"]["all_on_time"] for r in selected),
                "L_all_on_time": sum(r["S1_projections"][n]["metrics"]["13/10"]["L"]["all_on_time"] for r in selected)}
    report = {"state": batch["state"], "archive_arithmetic_review": "PASS", "checks": checks,
              "conditions": len(rows), "independent_roots": len({r["call"]["root_id"] for r in rows}),
              "counters": batch["counters"], "batch_seconds": batch["elapsed_s"],
              "condition_time_range_s": [min(timing), max(timing)] if timing else [],
              "groups": groups, "base_joint_strata_beta13": strata, "S1_beta13_by_pool": s1,
              "unique_profile_categories_at_scale96": dict(profile_counts), "specialization": dict(special_counts),
              "deadline_beta13_ranges_by_scale": due_by_scale,
              "source_hashes_match": True, "protected_sources_unchanged": True,
              "independent_arithmetic_rows": sum(c["independent_deadline_arithmetic_rows"] for c in checks),
              "statistical_scope": "descriptive_only_derivatives_not_independent_samples",
              "beta_selected": None, "formal_algorithms": 0, "thermal_integrations": 0,
              "analysis_source_sha256": sha(Path(__file__))}
    output.mkdir(exist_ok=False)
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table = ["# 时间期限校准汇总", "", "β=1.3；分母为输入条件。完整准时指该条件全部8场景的所有请求均准时。", "",
             "| 条件 | 数量 | H完整准时 | M完整准时 | L完整准时 | M请求准时率 | L请求准时率 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key in ("base_6", "base_24", "base_96", "S4_serial", "S4_layered", "S5", "S7", "S3"):
        g = groups[key]["13/10"]
        if not g["conditions"]:
            continue
        table.append(f"| {key} | {g['conditions']} | {g['H']['all_requests_on_time_conditions']} | {g['M']['all_requests_on_time_conditions']} | {g['L']['all_requests_on_time_conditions']} | {g['M']['request_rate']:.2%} | {g['L']['request_rate']:.2%} |")
    (output / "tables.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print("\n".join(table))
    print(json.dumps({k: report[k] for k in ("conditions", "independent_roots", "counters", "batch_seconds", "condition_time_range_s", "independent_arithmetic_rows", "specialization", "deadline_beta13_ranges_by_scale")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    summarize(arguments.execution, arguments.freeze, arguments.output)
