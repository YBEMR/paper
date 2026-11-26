"""Replay the preregistered virtual targets on the two fixed initial configurations."""
import argparse
from collections import defaultdict
import csv
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys
import tempfile

BUNDLE = Path(__file__).resolve().parent.parent / "chapter4_cross_analysis_v5"
sys.path.insert(0, str(BUNDLE))
import analyze_cross as audit
from feedback_frozen import targets, virtual


def compact_json(value):
    return json.dumps(value, separators=(",", ":"))


def save(path, rows):
    with path.open("x", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def busy_band(mj):
    if mj <= 0:
        return "nonpositive"
    if mj < 1:
        return "(0,1)mJ"
    return "[1,10)mJ" if mj < 10 else "[10,inf)mJ"


def scan(model, config):
    if virtual(model, config)[1]:
        raise ValueError("Fixed initial schedule has a virtual deadline violation")
    records = {}
    for kind, group in zip(("single", "group1", "group4", "group8"), targets(model, config, 101)):
        for target in group:
            key = kind, target
            if key in records:
                raise ValueError("Duplicate target within a category")
            cfg = list(config)
            for i, op in target:
                cfg[i] = op
            saved = Fraction(1000 * sum(model.busy[i][config[i]] - model.busy[i][op] for i, op in target), model.f.scale)
            total, late, _, _ = virtual(model, cfg)
            records[key] = dict(before=compact_json([(i, config[i]) for i, _ in target]),
                                busy_saving_mJ=float(saved), band=busy_band(saved), late_requests=len(late),
                                max_late_ms=max((x[0] for x in late), default=0) / 10,
                                total_late_ms=total / 10)
    return records


def analyze(repo, run, dest):
    audit.check_bundle()
    ids = audit.identities()
    hist = repo / "research/chapter3_final_evaluation"
    sys.path.insert(0, str(hist))
    from setup_inputs import checked_problem
    from fifo import Compact
    from run_cross import check_repo
    checks = check_repo(repo)
    if not checks["versions_match"]:
        raise ValueError("Frozen source or environment changed")
    details = []
    grouped = defaultdict(list)
    for case in audit.CASES:
        model = Compact(checked_problem(case))
        scanned = {}
        for name in ("G2", "Q4"):
            identity = ids[case, name]
            digest = identity["original_plan_sha256"]
            if name == "G2":
                plan, cert = audit.Store(hist / "formal/cells" / f"{case}_AB_T3_101", case).get(digest)
                status, bounds = cert["metrics"]["status"], cert["metrics"]["E_bounds"]
            else:
                pool = run / "pools" / case
                result = audit.read(pool / "result.json")
                raw = gzip.decompress((pool / "evidence/plans" / (digest + ".json.gz")).read_bytes())
                if audit.sha(raw) != digest or result["plan"] != digest:
                    raise ValueError("Q4 pool identity mismatch")
                plan = json.loads(raw)
                status, bounds = result["status"], result["E_bounds"]
            if plan["case"] != case or status != "SAFE" or not all(audit.close(a, b) for a, b in zip(bounds, identity["E_bounds"], strict=True)):
                raise ValueError("Fixed initial certificate mismatch")
            cfg = tuple((u, k) for u, k, _ in plan["rows"][1::3])
            scanned[name] = scan(model, cfg)
        for name, scans in scanned.items():
            other = scanned["Q4" if name == "G2" else "G2"]
            for key, row in sorted(scans.items()):
                kind, target = key
                shared = key in other
                same_source = shared and row["before"] == other[key]["before"]
                details.append(dict(case=case, initial=name, category=kind, target=compact_json(target),
                                    common_target=shared, same_source_and_target=same_source, **row))
                subsets = ["all"]
                if shared:
                    subsets.append("common_target")
                if same_source:
                    subsets.append("same_source_and_target")
                for subset in subsets:
                    for band in ("all", row["band"]):
                        grouped[case, name, kind, subset, band].append(row)
    summary = []
    for case in audit.CASES:
        for name in ("G2", "Q4"):
            for kind in ("single", "group1", "group4", "group8"):
                for subset in ("all", "common_target", "same_source_and_target"):
                    for band in ("all", "nonpositive", "(0,1)mJ", "[1,10)mJ", "[10,inf)mJ"):
                        rows = grouped[case, name, kind, subset, band]
                        n = len(rows)
                        blocked = sum(r["late_requests"] > 0 for r in rows)
                        summary.append(dict(case=case, initial=name, category=kind, subset=subset, band=band,
                                            target_count=n, blocked_count=blocked, blocked_fraction=blocked/n if n else None))
    save(dest / "initial_targets.csv", details)
    save(dest / "initial_target_summary.csv", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "run", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(out)
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage = Path(temp) / "results"
        stage.mkdir()
        analyze(args.repo.resolve(), args.run.resolve(), stage)
        stage.rename(out)
