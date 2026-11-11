"""Seal existing evidence only: no model build, thermal call or solver call."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(name, value):
    with (ROOT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


stamp = datetime.now(timezone.utc).isoformat()
comparison = ROOT / "static_pair/comparison.json"
write_new("scope_clarification.json", {
    "recorded_utc": stamp,
    "original_comparison_sha256": sha(comparison),
    "original_output_preserved": True,
    "clarification": {
        "cache_old_ON_to_optimized_ON": "All exported numerical arrays are byte-identical: algebraic continuous LP relaxation, integer feasible set and objective are identical.",
        "prior_pruning_OFF_to_ON": "The prior cross-dimension projection argument requires exact integer original y. It does not assert identical LP relaxations.",
        "native_solver_scope": "Native near-integer/row-tolerance acceptance, solver returns, finite-precision search paths and remaining time under a total budget were not exercised.",
        "inherited_precision_scope": "The original comparison.json generic phrase 'not LP ... equivalence' concerns prior pruning and must not be read as denying algebraic LP identity of the two ON matrices. The frozen comparator and its original output remain unchanged."
    },
    "new_model_builds": 0,
    "new_thermal_calls": 0,
    "new_solver_calls": 0
})
report = ROOT / "REPORT.md"
report.write_text(report.read_text(encoding="utf-8") + "\n原比较输出的precision_scope沿用此前剪枝的泛化措辞，两个ON矩阵相同所蕴含的LP代数一致性另见 `scope_clarification.json`；原输出和冻结比较脚本保持不变。最终独立只读审查见 `safety_review/FINAL_REPORT_REVIEW.md`，其回执保留加本说明之前的报告快照哈希。完整文件封存见根 `manifest.json`。\n", encoding="utf-8")
write_new("executed_commands.json", {
    "cwd": str(REPO),
    "exact_scientific_command_indexes": [
        "implementation/commands.json", "validation/commands.json",
        "validation/command_receipts.json", "validation/rev2/command_receipts.json",
        "static_pair/commands.json", "static_pair/old_on.command_receipt.json",
        "static_pair/optimized_on.command_receipt.json", "static_pair/off.command_receipt.json"
    ],
    "helper_replay_plan_and_receipts": ["safety_review/replay_plan.json", "safety_review/replay_result.json"],
    "final_integrity_commands": [
        "python3 research/chapter3_pruning_audit_optimization_20261111/finalize_records.py > research/chapter3_pruning_audit_optimization_20261111/finalize.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/finalize.stderr.log",
        "python3 research/chapter3_pruning_audit_optimization_20261111/seal_records.py"
    ],
    "seal_activity": "Existing-file hashes, scope annotation and manifest only; no scientific recomputation."
})
plan = json.loads((ROOT / "master_plan.json").read_text())
for name, expected in plan["history_sha256"].items():
    assert sha(REPO / name) == expected, name
completion_path = ROOT / "completion_record.json"
completion = json.loads(completion_path.read_text())
for name, expected in completion["source_sha256"].items():
    assert sha(REPO / name) == expected, name
completion["final_records_sealed_utc"] = datetime.now(timezone.utc).isoformat()
completion["scope_clarification_sha256"] = sha(ROOT / "scope_clarification.json")
completion["final_report_review_receipt"] = "safety_review/final_report_review_receipt.json"
completion_path.write_text(json.dumps(completion, ensure_ascii=False, indent=2) + "\n")
files = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != "manifest.json":
        files.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path)})
# Include existing component manifests, excluding only this new root manifest.
for path in sorted(ROOT.rglob("manifest.json")):
    if path.parent != ROOT:
        files.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path)})
write_new("manifest.json", {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "file_count": len(files), "total_bytes": sum(f["bytes"] for f in files),
    "history_files_unchanged": len(plan["history_sha256"]),
    "exclusions": ["root manifest.json (self)", "__pycache__", "*.pyc"],
    "files": sorted(files, key=lambda f: f["path"])
})
for entry in files:
    assert sha(ROOT / entry["path"]) == entry["sha256"]
print(json.dumps({"sealed_utc": completion["final_records_sealed_utc"], "files": len(files), "history_unchanged": len(plan["history_sha256"]), "manifest_sha256": sha(ROOT / "manifest.json"), "new_scientific_calls": 0}))
