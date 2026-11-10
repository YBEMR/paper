"""Read-only delivery checks. No thermal kernel or scheduling is imported."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

OUT = Path(__file__).resolve().parent
BASE = OUT.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    started = datetime.now(timezone.utc).isoformat()
    began = time.monotonic()
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    old = read(OUT / "coordination_start.json")["original_artifacts_sha256"]
    for name, value in old.items():
        path = BASE / name
        check("original unchanged: " + name, path.is_file() and sha(path) == value)

    table_manifest = read(OUT / "tables/tables_manifest.json")
    for name, value in table_manifest["files_sha256"].items():
        path = OUT / "tables" / name
        check("table artifact hash: " + name, path.is_file() and sha(path) == value)
    derivation = read(OUT / "tables/derivation_checks.json")
    check("table derivation passed", derivation["passed"])
    check("table derivation includes no heat or search", derivation["new_search_calls"] == derivation["new_thermal_evaluations"] == 0)

    for filename, count, key in [
        ("main_experiment_table.csv", 7, "方案ID"),
        ("periodic_supplement_table.csv", 9, "配置ID"),
    ]:
        with (OUT / "tables" / filename).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        check(filename + ": row count and unique IDs", len(rows) == len({r[key] for r in rows}) == count)
    exact = read(OUT / "tables/table_data_exact.json")
    check("all five SA seeds retained", {r["scheme_id"] for r in exact["main"] if r["scheme_id"].startswith("t50_sa")} == {f"t50_sa{s}" for s in range(101, 106)})
    check("six original null records preserved", len(exact["important_original_null_fields"]) == 6)

    figure_audit = read(OUT / "figure/figure_audit.json")
    check("figure source audit passed", figure_audit["passed"])
    check("exactly ten figure-only original kernel calls", figure_audit["actual_original_kernel_calls"] == 10)
    check("rendering added no heat calls", figure_audit["postprocessing_new_kernel_calls"] == 0)
    point_run = read(OUT / "figure/point_run01/summary.json")
    check("all ten plotting calls complete without search", point_run["complete_all_calls"] and point_run["fatal"] is None and point_run["new_scheduling_search_calls"] == 0)
    historical_log_snapshots = []
    for filename in ["figure_manifest.json", "figure_final_manifest.json"]:
        manifest = read(OUT / "figure" / filename)
        for name, value in manifest["files_sha256"].items():
            path = OUT / "figure" / name
            if filename == "figure_manifest.json" and name == "render_stdout.log" and path.is_file() and sha(path) != value:
                # v1 sealed this live log before its final stdout line. Retain
                # that historical snapshot; final manifest verifies closed log.
                check("v1 stdout mismatch is its documented empty snapshot", value == hashlib.sha256(b"").hexdigest())
                historical_log_snapshots.append({"manifest": filename, "file": name, "snapshot_sha256": value, "closed_log_sha256": sha(path)})
            else:
                check(filename + ": " + name, path.is_file() and sha(path) == value)

    images = {}
    for extension, signature in [("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF-")]:
        files = sorted((OUT / "figure").glob("AB_NPU0_startup_and_periodic_v3." + extension))
        check("one final " + extension + " figure", len(files) == 1)
        path = files[0]
        check(extension + " file signature", path.read_bytes().startswith(signature))
        images[extension] = {"path": str(path.relative_to(OUT)), "size_bytes": path.stat().st_size, "sha256": sha(path)}
    files = sorted((OUT / "figure").glob("AB_NPU0_startup_and_periodic_v3.svg"))
    check("one final svg figure", len(files) == 1)
    check("svg document", "<svg" in files[0].read_text()[:2000])
    images["svg"] = {"path": str(files[0].relative_to(OUT)), "size_bytes": files[0].stat().st_size, "sha256": sha(files[0])}

    result = {
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "wall_s": time.monotonic() - began,
        "passed": True,
        "original_artifacts_unchanged": len(old),
        "checks": checks,
        "assertion_count": len(checks),
        "figure_files": images,
        "historical_live_log_snapshot_differences": historical_log_snapshots,
        "scope": "Original-artifact hashes, table integrity and figure format checks only. Scientific figure and table provenance are reviewed separately; no new heat, matrix solution or search.",
        "argv": sys.argv,
    }
    with (OUT / "delivery_checks.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ["passed", "original_artifacts_unchanged", "assertion_count", "wall_s"]}))


if __name__ == "__main__":
    main()
