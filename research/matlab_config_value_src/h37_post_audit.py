"""Read-only result checks plus a SHA256 manifest; no simulation or fitting.

Usage: python h37_post_audit.py <run directory returned by run_h37>
Run after MATLAB exits so console.txt is closed. Only writes audit.json,
manifest.json and this postprocessing source copy inside the chosen run.
"""
from pathlib import Path
import csv
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def audit(folder):
    folder = Path(folder).resolve()
    assert folder.is_relative_to(HERE / "h37_reports") and folder.is_dir()
    summary = read_csv(folder / "summary.csv")
    schedules = read_csv(folder / "schedules.csv")
    checks = read_csv(folder / "checks.csv")
    inputs = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))["trials"]
    frozen = json.loads((HERE / "thermal_reports/run_20260923_204922_828/inputs.json").read_text(encoding="utf-8"))["trials"]
    same_inputs = inputs == frozen
    current_source_equal = all(sha(p) == sha(HERE / p.name) for p in (folder / "source").glob("*.m"))
    history = []
    for run in ("reports/run_20260923_170646_889", "thermal_reports/run_20260923_204922_828"):
        files = list((HERE / run / "source").glob("*.m"))
        history.append({"run": run, "count": len(files), "unchanged": all(sha(p) == sha(HERE / p.name) for p in files)})
    outcome = {}
    for version in ("P0", "P1"):
        rows = [r for r in summary if r["version"] == version]
        outcome[version] = {
            "rows": len(rows), "completed": sum(r["status"] == "completed" for r in rows),
            "safe": sum(r["thermal"] == "safe" for r in rows),
            "recovered": sum(r["recovered"] == "1" for r in rows),
            "thermal_evaluations": sum(int(r["thermal_evaluations"]) for r in rows),
            "rejected": sum(int(r["rejected"]) for r in rows),
            "elapsed_min_s": min(float(r["elapsed_case_version_s"]) for r in rows),
            "elapsed_max_s": max(float(r["elapsed_case_version_s"]) for r in rows),
        }
    signatures = {}
    for r in schedules:
        if r["scope"] == "main":
            key = (r["trial"], r["tie_index"], r["version"])
            signatures.setdefault(key, []).append(tuple(r[f] for f in ("stage", "mode", "start_s", "finish_s", "increment_W", "state")))
    identical = all(sorted(v) == sorted(signatures[(trial, tie, "P1")]) for (trial, tie, ver), v in signatures.items() if ver == "P0")
    input_digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    prior_inputs = {}
    for run in sorted((HERE / "h37_reports").glob("run_*")):
        data = json.loads((run / "inputs.json").read_text(encoding="utf-8"))["trials"]
        prior_inputs[run.name] = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = {"formal_run": folder.name, "inputs_match_36": same_inputs,
              "input_content_sha256": input_digest, "all_h37_input_digests": prior_inputs,
              "current_matlab_source_matches_snapshot": current_source_equal,
              "historical_sources": history, "main_outcomes": outcome,
              "P0_P1_main_timelines_identical": identical,
              "matlab_checks": len(checks), "passed": sum(r["passed"] == "1" for r in checks),
              "scope": "No simulation. Same deterministic cases; no statistical generalization."}
    assert same_inputs and current_source_equal and all(r["unchanged"] for r in history)
    (folder / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "postprocessing_source.py").write_bytes(Path(__file__).read_bytes())
    manifest = {"algorithm": "SHA256", "files": [
        {"path": p.relative_to(folder).as_posix(), "sha256": sha(p)}
        for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "manifest.json"
    ]}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    audit(sys.argv[1])
